"""Translate typed semantic queries into parameterized DuckDB SQL."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from duckdb_semantic_layer.errors import Diagnostic, SemanticLayerError
from duckdb_semantic_layer.query import SelectQuery, Variable
from duckdb_semantic_layer.rdf import IRI, RDFLiteral


@dataclass(frozen=True, slots=True)
class TermReference:
    alias: str
    position: str

    @property
    def value_sql(self) -> str:
        return f"{self.alias}.{_VALUE_COLUMNS[self.position]}"

    @property
    def is_object(self) -> bool:
        return self.position == "object"


@dataclass(frozen=True, slots=True)
class VariableBinding:
    variable: str
    alias: str
    position: str
    value_sql: str


@dataclass(frozen=True, slots=True)
class PlanStep:
    pattern_index: int
    alias: str
    constraints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QueryPlan:
    sql: str
    parameters: tuple[str | None, ...]
    bindings: tuple[VariableBinding, ...]
    steps: tuple[PlanStep, ...]

    def as_dict(self, *, include_parameter_values: bool = False) -> dict[str, Any]:
        parameters: list[Any]
        if include_parameter_values:
            parameters = list(self.parameters)
        else:
            parameters = [
                {"index": index, "type": _parameter_type(value), "redacted": True}
                for index, value in enumerate(self.parameters, start=1)
            ]
        return {
            "sql": self.sql,
            "parameters": parameters,
            "bindings": [asdict(binding) for binding in self.bindings],
            "steps": [asdict(step) for step in self.steps],
        }


_VALUE_COLUMNS = {
    "subject": "subject",
    "predicate": "predicate",
    "object": "object_value",
}


def _parameter_type(value: str | None) -> str:
    return "null" if value is None else "string"


def _term_reference(alias: str, position: str) -> TermReference:
    return TermReference(alias, position)


def _add_object_iri_constraint(reference: TermReference, constraints: list[str]) -> None:
    condition = f"{reference.alias}.object_kind = 'iri'"
    if reference.is_object and condition not in constraints:
        constraints.append(condition)


def _join_references(
    left: TermReference,
    right: TermReference,
    constraints: list[str],
) -> None:
    constraints.append(f"{left.value_sql} = {right.value_sql}")
    if left.is_object and right.is_object:
        constraints.extend(
            [
                f"{left.alias}.object_kind = {right.alias}.object_kind",
                (
                    f"{left.alias}.object_language IS NOT DISTINCT FROM "
                    f"{right.alias}.object_language"
                ),
                (
                    f"{left.alias}.object_datatype IS NOT DISTINCT FROM "
                    f"{right.alias}.object_datatype"
                ),
            ]
        )
    elif left.is_object:
        _add_object_iri_constraint(left, constraints)
    elif right.is_object:
        _add_object_iri_constraint(right, constraints)


def _constrain_constant(
    reference: TermReference,
    term: IRI | RDFLiteral,
    constraints: list[str],
    parameters: list[str | None],
) -> None:
    if isinstance(term, IRI):
        if reference.is_object:
            constraints.append(f"{reference.alias}.object_kind = 'iri'")
        constraints.append(f"{reference.value_sql} = ?")
        parameters.append(term.value)
        return

    if not reference.is_object:
        raise SemanticLayerError(
            Diagnostic(
                code="SPARQL_TERM_TYPE_MISMATCH",
                message=f"Literal cannot appear in {reference.position} position",
            )
        )
    constraints.extend(
        [
            f"{reference.alias}.object_kind = 'literal'",
            f"{reference.value_sql} = ?",
            f"{reference.alias}.object_language IS NOT DISTINCT FROM ?",
            f"{reference.alias}.object_datatype IS NOT DISTINCT FROM ?",
        ]
    )
    parameters.extend([term.value, term.language, term.datatype])


def _constant_equal(left: IRI | RDFLiteral, right: IRI | RDFLiteral) -> bool:
    return left == right


def build_query_plan(query: SelectQuery) -> QueryPlan:
    constraints: list[str] = []
    parameters: list[str | None] = []
    occurrences: dict[str, list[TermReference]] = {}
    steps: list[PlanStep] = []

    for index, pattern in enumerate(query.patterns):
        alias = f"t{index}"
        step_constraints: list[str] = []
        for position, term in (
            ("subject", pattern.subject),
            ("predicate", pattern.predicate),
            ("object", pattern.object),
        ):
            reference = _term_reference(alias, position)
            if isinstance(term, Variable):
                previous = occurrences.setdefault(term.name, [])
                if previous:
                    _join_references(previous[0], reference, step_constraints)
                previous.append(reference)
            else:
                _constrain_constant(reference, term, step_constraints, parameters)
        constraints.extend(step_constraints)
        steps.append(PlanStep(index, alias, tuple(step_constraints)))

    for filter_ in query.filters:
        left = filter_.left
        right = filter_.right
        if isinstance(left, Variable) and isinstance(right, Variable):
            _join_references(
                occurrences[left.name][0],
                occurrences[right.name][0],
                constraints,
            )
        elif isinstance(left, Variable):
            assert isinstance(right, (IRI, RDFLiteral))
            _constrain_constant(occurrences[left.name][0], right, constraints, parameters)
        elif isinstance(right, Variable):
            assert isinstance(left, (IRI, RDFLiteral))
            _constrain_constant(occurrences[right.name][0], left, constraints, parameters)
        else:
            constraints.append("TRUE" if _constant_equal(left, right) else "FALSE")

    bindings = tuple(
        VariableBinding(
            variable=variable.name,
            alias=occurrences[variable.name][0].alias,
            position=occurrences[variable.name][0].position,
            value_sql=occurrences[variable.name][0].value_sql,
        )
        for variable in query.selected
    )
    select_sql = ", ".join(
        f'{binding.value_sql} AS "{binding.variable}"' for binding in bindings
    )
    from_sql = "rdf_triples AS t0"
    for index in range(1, len(query.patterns)):
        from_sql += f"\nJOIN rdf_triples AS t{index} ON TRUE"
    where_sql = "\n  AND ".join(constraints) if constraints else "TRUE"
    order_sql = ", ".join(str(index) for index in range(1, len(bindings) + 1))
    sql = (
        f"SELECT DISTINCT {select_sql}\n"
        f"FROM {from_sql}\n"
        f"WHERE {where_sql}\n"
        f"ORDER BY {order_sql}"
    )
    return QueryPlan(
        sql=sql,
        parameters=tuple(parameters),
        bindings=bindings,
        steps=tuple(steps),
    )
