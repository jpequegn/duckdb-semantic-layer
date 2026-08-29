"""Parser for the deliberately bounded SPARQL subset."""

from __future__ import annotations

import json
from dataclasses import dataclass

from lark import Lark, Transformer, UnexpectedInput
from lark.exceptions import VisitError

from duckdb_semantic_layer.errors import Diagnostic, SemanticLayerError
from duckdb_semantic_layer.query import (
    EqualityFilter,
    Prefix,
    QueryTerm,
    SelectQuery,
    TriplePattern,
    Variable,
)
from duckdb_semantic_layer.rdf import IRI, RDFLiteral

_SPARQL_GRAMMAR = r"""
    start: prefix_decl* select_query
    prefix_decl: "PREFIX"i PREFIX_NAME IRIREF
    select_query: "SELECT"i variable+ "WHERE"i "{" pattern+ filter_expr* "}"
    pattern: subject predicate object "."
    filter_expr: "FILTER"i "(" term "=" term ")"

    ?subject: variable | iri | prefixed
    ?predicate: variable | iri | prefixed
    ?object: term
    ?term: variable | iri | prefixed | literal
    variable: VAR
    iri: IRIREF
    prefixed: PNAME_LN
    literal: ESCAPED_STRING language? datatype?
    language: LANGTAG
    datatype: "^^" (iri | prefixed)

    VAR: /\?[A-Za-z_][A-Za-z0-9_]*/
    PREFIX_NAME: /[A-Za-z][A-Za-z0-9_-]*:/
    PNAME_LN: /[A-Za-z][A-Za-z0-9_-]*:[A-Za-z_][A-Za-z0-9._-]*/
    IRIREF: /<[^<>"{}|^\x00-\x20]*>/
    LANGTAG: /@[a-zA-Z]+(?:-[a-zA-Z0-9]+)*/

    %import common.ESCAPED_STRING
    %import common.WS
    %ignore WS
    %ignore /#[^\n]*/
"""

_PARSER = Lark(_SPARQL_GRAMMAR, parser="lalr", propagate_positions=True)


@dataclass(frozen=True, slots=True)
class _PrefixedName:
    prefix: str
    local: str


@dataclass(frozen=True, slots=True)
class _RawPrefix:
    name: str
    iri: str


@dataclass(frozen=True, slots=True)
class _RawQuery:
    selected: tuple[Variable, ...]
    patterns: tuple[TriplePattern, ...]
    filters: tuple[EqualityFilter, ...]


_RawTerm = Variable | IRI | RDFLiteral | _PrefixedName


class _QueryTransformer(Transformer[object, object]):
    def VAR(self, token: object) -> Variable:
        return Variable(str(token)[1:])

    def variable(self, items: list[object]) -> Variable:
        return items[0]  # type: ignore[return-value]

    def IRIREF(self, token: object) -> IRI:
        return IRI(str(token)[1:-1])

    def iri(self, items: list[object]) -> IRI:
        return items[0]  # type: ignore[return-value]

    def PNAME_LN(self, token: object) -> _PrefixedName:
        prefix, local = str(token).split(":", 1)
        return _PrefixedName(prefix, local)

    def prefixed(self, items: list[object]) -> _PrefixedName:
        return items[0]  # type: ignore[return-value]

    def ESCAPED_STRING(self, token: object) -> str:
        return json.loads(str(token))

    def LANGTAG(self, token: object) -> str:
        return str(token)[1:].lower()

    def language(self, items: list[object]) -> tuple[str, str]:
        return ("language", str(items[0]))

    def datatype(self, items: list[object]) -> tuple[str, _RawTerm]:
        return ("datatype", items[0])  # type: ignore[return-value]

    def literal(self, items: list[object]) -> RDFLiteral | tuple[str, _RawTerm]:
        value = str(items[0])
        language = None
        datatype: _RawTerm | None = None
        for marker, content in items[1:]:  # type: ignore[misc]
            if marker == "language":
                language = str(content)
            else:
                datatype = content
        if isinstance(datatype, _PrefixedName):
            return ("pending_literal", (value, language, datatype))  # type: ignore[return-value]
        if isinstance(datatype, IRI):
            return RDFLiteral(value, language=language, datatype=datatype.value)
        return RDFLiteral(value, language=language)

    def prefix_decl(self, items: list[object]) -> _RawPrefix:
        name = str(items[0])[:-1]
        iri = items[1]
        assert isinstance(iri, IRI)
        return _RawPrefix(name, iri.value)

    def pattern(self, items: list[object]) -> tuple[str, tuple[_RawTerm, _RawTerm, _RawTerm]]:
        return ("pattern", (items[0], items[1], items[2]))  # type: ignore[return-value]

    def filter_expr(self, items: list[object]) -> tuple[str, tuple[_RawTerm, _RawTerm]]:
        return ("filter", (items[0], items[1]))  # type: ignore[return-value]

    def select_query(self, items: list[object]) -> _RawQuery:
        selected: list[Variable] = []
        patterns: list[TriplePattern] = []
        filters: list[EqualityFilter] = []
        for item in items:
            if isinstance(item, Variable):
                selected.append(item)
            elif item[0] == "pattern":  # type: ignore[index]
                patterns.append(item)  # type: ignore[arg-type]
            else:
                filters.append(item)  # type: ignore[arg-type]
        return _RawQuery(tuple(selected), tuple(patterns), tuple(filters))

    def start(self, items: list[object]) -> tuple[tuple[_RawPrefix, ...], _RawQuery]:
        prefixes = tuple(item for item in items if isinstance(item, _RawPrefix))
        query = next(item for item in items if isinstance(item, _RawQuery))
        return prefixes, query


def _resolve_term(term: object, prefixes: dict[str, str]) -> QueryTerm:
    if isinstance(term, _PrefixedName):
        try:
            return IRI(prefixes[term.prefix] + term.local)
        except KeyError as exc:
            raise SemanticLayerError(
                Diagnostic(
                    code="SPARQL_UNKNOWN_PREFIX",
                    message=f"Unknown prefix: {term.prefix}",
                )
            ) from exc
    if isinstance(term, tuple) and term[0] == "pending_literal":
        value, language, datatype = term[1]
        resolved = _resolve_term(datatype, prefixes)
        assert isinstance(resolved, IRI)
        return RDFLiteral(value, language=language, datatype=resolved.value)
    assert isinstance(term, (Variable, IRI, RDFLiteral))
    return term


def _resolve_query(raw_prefixes: tuple[_RawPrefix, ...], raw: _RawQuery) -> SelectQuery:
    prefix_map: dict[str, str] = {}
    for prefix in raw_prefixes:
        if prefix.name in prefix_map:
            raise SemanticLayerError(
                Diagnostic(
                    code="SPARQL_DUPLICATE_PREFIX",
                    message=f"Duplicate prefix declaration: {prefix.name}",
                )
            )
        prefix_map[prefix.name] = prefix.iri

    patterns: list[TriplePattern] = []
    for _, raw_terms in raw.patterns:  # type: ignore[misc]
        subject, predicate, object_ = (
            _resolve_term(term, prefix_map) for term in raw_terms
        )
        assert isinstance(subject, (Variable, IRI))
        assert isinstance(predicate, (Variable, IRI))
        patterns.append(TriplePattern(subject, predicate, object_))

    filters: list[EqualityFilter] = []
    for _, raw_terms in raw.filters:  # type: ignore[misc]
        left, right = (_resolve_term(term, prefix_map) for term in raw_terms)
        filters.append(EqualityFilter(left, right))

    bound = set().union(*(pattern.variables() for pattern in patterns))
    selected_names = {variable.name for variable in raw.selected}
    if len(selected_names) != len(raw.selected):
        raise SemanticLayerError(
            Diagnostic(code="SPARQL_DUPLICATE_SELECT", message="Duplicate selected variable")
        )
    unbound = selected_names - bound
    for filter_ in filters:
        unbound.update(filter_.variables() - bound)
    if unbound:
        names = ", ".join(f"?{name}" for name in sorted(unbound))
        raise SemanticLayerError(
            Diagnostic(
                code="SPARQL_UNBOUND_VARIABLE",
                message=f"Unbound variable: {names}",
            )
        )

    return SelectQuery(
        prefixes=tuple(Prefix(prefix.name, prefix.iri) for prefix in raw_prefixes),
        selected=raw.selected,
        patterns=tuple(patterns),
        filters=tuple(filters),
    )


def parse_sparql(text: str, *, source: str | None = None) -> SelectQuery:
    try:
        raw_prefixes, raw_query = _QueryTransformer().transform(_PARSER.parse(text))
        return _resolve_query(raw_prefixes, raw_query)
    except UnexpectedInput as exc:
        raise SemanticLayerError(
            Diagnostic(
                code="SPARQL_PARSE_ERROR",
                message="Unsupported or malformed SPARQL query",
                source=source,
                line=exc.line,
                column=exc.column,
            )
        ) from exc
    except VisitError as exc:
        if isinstance(exc.orig_exc, SemanticLayerError):
            raise exc.orig_exc from exc
        raise
