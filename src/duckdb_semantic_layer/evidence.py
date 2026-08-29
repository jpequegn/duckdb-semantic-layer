"""Differential evidence runner for the synthetic organization fixture."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from duckdb_semantic_layer.store import SemanticStore


@dataclass(frozen=True, slots=True)
class DifferentialCase:
    name: str
    query_file: str
    direct_sql: str
    direct_parameters: tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class CaseEvidence:
    name: str
    query_file: str
    query: str
    generated_plan: dict[str, Any]
    direct_sql: str
    translated_rows: tuple[tuple[Any, ...], ...]
    direct_rows: tuple[tuple[Any, ...], ...]
    matched: bool


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    fixture: str
    source_lines: int
    parsed_triples: int
    inserted_triples: int
    duplicates: int
    cases: tuple[CaseEvidence, ...]

    @property
    def passed(self) -> bool:
        return all(case.matched for case in self.cases)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


CASES = (
    DifferentialCase(
        name="NYC employees",
        query_file="01-nyc-employees.rq",
        direct_sql="""
            SELECT DISTINCT person.subject AS person, name.object_value AS name
            FROM rdf_triples AS person
            JOIN rdf_triples AS name ON name.subject = person.subject
            JOIN rdf_triples AS city ON city.subject = person.subject
            WHERE person.predicate = ?
              AND person.object_kind = 'iri' AND person.object_value = ?
              AND name.predicate = ?
              AND city.predicate = ?
              AND city.object_kind = 'iri' AND city.object_value = ?
            ORDER BY 1, 2
        """,
        direct_parameters=(
            "urn:org:type",
            "urn:org:Employee",
            "urn:org:name",
            "urn:org:homeCity",
            "urn:org:nyc",
        ),
    ),
    DifferentialCase(
        name="Engineering department",
        query_file="02-engineers.rq",
        direct_sql="""
            SELECT DISTINCT employee.subject AS person, name.object_value AS name
            FROM rdf_triples AS employee
            JOIN rdf_triples AS name ON name.subject = employee.subject
            JOIN rdf_triples AS department ON department.subject = employee.object_value
            WHERE employee.predicate = ?
              AND employee.object_kind = 'iri'
              AND name.predicate = ?
              AND department.predicate = ?
              AND department.object_kind = 'literal'
              AND department.object_value = ?
            ORDER BY 1, 2
        """,
        direct_parameters=(
            "urn:org:department",
            "urn:org:name",
            "urn:org:name",
            "Engineering",
        ),
    ),
    DifferentialCase(
        name="US residents",
        query_file="03-us-residents.rq",
        direct_sql="""
            SELECT DISTINCT resident.subject AS person, resident.object_value AS city
            FROM rdf_triples AS resident
            JOIN rdf_triples AS country ON country.subject = resident.object_value
            WHERE resident.predicate = ?
              AND resident.object_kind = 'iri'
              AND country.predicate = ?
              AND country.object_kind = 'iri'
              AND country.object_value = ?
            ORDER BY 1, 2
        """,
        direct_parameters=("urn:org:homeCity", "urn:org:country", "urn:org:usa"),
    ),
    DifferentialCase(
        name="Typed salary",
        query_file="04-salary.rq",
        direct_sql="""
            SELECT DISTINCT subject AS person
            FROM rdf_triples
            WHERE predicate = ?
              AND object_kind = 'literal'
              AND object_value = ?
              AND object_language IS NULL
              AND object_datatype = ?
            ORDER BY 1
        """,
        direct_parameters=(
            "urn:org:salary",
            "150000",
            "http://www.w3.org/2001/XMLSchema#integer",
        ),
    ),
    DifferentialCase(
        name="Equality filter",
        query_file="05-name-filter.rq",
        direct_sql="""
            SELECT DISTINCT subject AS person, object_value AS name
            FROM rdf_triples
            WHERE predicate = ?
              AND object_kind = 'literal'
              AND object_value = ?
              AND object_language IS NULL
              AND object_datatype IS NULL
            ORDER BY 1, 2
        """,
        direct_parameters=("urn:org:name", "Alice"),
    ),
)


def run_evidence(
    fixture: str | Path,
    *,
    output_directory: str | Path | None = None,
) -> EvidenceReport:
    fixture_path = Path(fixture)
    query_directory = fixture_path.parent / "queries"
    evidence: list[CaseEvidence] = []
    with SemanticStore(":memory:") as store:
        stats = store.load(fixture_path)
        for case in CASES:
            query_path = query_directory / case.query_file
            query_text = query_path.read_text(encoding="utf-8")
            translated = store.query(query_text, source=str(query_path))
            direct = store._fetch_validation_sql(case.direct_sql, case.direct_parameters)
            matched = (
                translated.columns == direct.columns
                and translated.rows == direct.rows
            )
            evidence.append(
                CaseEvidence(
                    name=case.name,
                    query_file=str(query_path),
                    query=query_text.strip(),
                    generated_plan=translated.plan.as_dict(),
                    direct_sql=case.direct_sql.strip(),
                    translated_rows=translated.rows,
                    direct_rows=direct.rows,
                    matched=matched,
                )
            )

    report = EvidenceReport(
        fixture=str(fixture_path),
        source_lines=stats.source_lines,
        parsed_triples=stats.parsed_triples,
        inserted_triples=stats.inserted_triples,
        duplicates=stats.duplicates,
        cases=tuple(evidence),
    )
    if output_directory is not None:
        _write_report(report, Path(output_directory))
    return report


def _write_report(report: EvidenceReport, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "evidence.json").write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Semantic layer evidence",
        "",
        f"- Fixture: {report.fixture}",
        f"- Parsed triples: {report.parsed_triples}",
        f"- Inserted triples: {report.inserted_triples}",
        f"- Duplicate source triples: {report.duplicates}",
        f"- Overall result: {'PASS' if report.passed else 'FAIL'}",
        "",
    ]
    for case in report.cases:
        lines.extend(
            [
                f"## {case.name}",
                "",
                f"- Query: {case.query_file}",
                f"- Differential result: {'PASS' if case.matched else 'FAIL'}",
                "",
                "### Generated SQL",
                "",
                "~~~sql",
                case.generated_plan["sql"],
                "~~~",
                "",
                "### Direct SQL",
                "",
                "~~~sql",
                case.direct_sql,
                "~~~",
                "",
            ]
        )
    (output_directory / "evidence.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
