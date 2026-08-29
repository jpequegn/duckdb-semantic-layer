"""Bounded N-Triples parsing and DuckDB ingestion."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import duckdb
from lark import Lark, Transformer, UnexpectedInput

from duckdb_semantic_layer.errors import Diagnostic, SemanticLayerError
from duckdb_semantic_layer.rdf import IRI, RDFLiteral, Triple

_NTRIPLES_GRAMMAR = r"""
    start: iri iri object "."
    ?object: iri | literal
    iri: IRIREF
    literal: ESCAPED_STRING language? datatype?
    language: LANGTAG
    datatype: "^^" iri

    IRIREF: /<[^<>"{}|^\x00-\x20]*>/
    LANGTAG: /@[a-zA-Z]+(?:-[a-zA-Z0-9]+)*/

    %import common.ESCAPED_STRING
    %import common.WS_INLINE
    %ignore WS_INLINE
"""

_NTRIPLES_PARSER = Lark(_NTRIPLES_GRAMMAR, parser="lalr", propagate_positions=True)


class _TripleTransformer(Transformer[object, Triple]):
    def IRIREF(self, token: object) -> IRI:
        return IRI(str(token)[1:-1])

    def iri(self, items: list[object]) -> IRI:
        return items[0]  # type: ignore[return-value]

    def ESCAPED_STRING(self, token: object) -> str:
        return json.loads(str(token))

    def LANGTAG(self, token: object) -> str:
        return str(token)[1:].lower()

    def language(self, items: list[object]) -> tuple[str, str]:
        return ("language", str(items[0]))

    def datatype(self, items: list[object]) -> tuple[str, str]:
        iri = items[0]
        assert isinstance(iri, IRI)
        return ("datatype", iri.value)

    def literal(self, items: list[object]) -> RDFLiteral:
        value = str(items[0])
        language = None
        datatype = None
        for marker, content in items[1:]:  # type: ignore[misc]
            if marker == "language":
                language = content
            else:
                datatype = content
        return RDFLiteral(value=value, language=language, datatype=datatype)

    def start(self, items: list[object]) -> Triple:
        subject, predicate, object_ = items
        assert isinstance(subject, IRI)
        assert isinstance(predicate, IRI)
        assert isinstance(object_, (IRI, RDFLiteral))
        return Triple(subject=subject, predicate=predicate, object=object_)


_TRANSFORMER = _TripleTransformer()


@dataclass(frozen=True, slots=True)
class IngestionStats:
    source_lines: int
    parsed_triples: int
    inserted_triples: int
    duplicates: int


def parse_ntriple_line(
    line: str,
    *,
    source: str | None = None,
    line_number: int = 1,
) -> Triple | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    try:
        return _TRANSFORMER.transform(_NTRIPLES_PARSER.parse(stripped))
    except UnexpectedInput as exc:
        raise SemanticLayerError(
            Diagnostic(
                code="RDF_PARSE_ERROR",
                message="Malformed N-Triples input",
                source=source,
                line=line_number,
                column=exc.column,
            )
        ) from exc


def create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rdf_triples (
            triple_hash VARCHAR PRIMARY KEY,
            subject VARCHAR NOT NULL,
            predicate VARCHAR NOT NULL,
            object_kind VARCHAR NOT NULL CHECK (object_kind IN ('iri', 'literal')),
            object_value VARCHAR NOT NULL,
            object_language VARCHAR,
            object_datatype VARCHAR,
            CHECK (NOT (object_language IS NOT NULL AND object_datatype IS NOT NULL))
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS rdf_sp_idx ON rdf_triples(subject, predicate)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS rdf_po_idx ON rdf_triples(predicate, object_value)"
    )


def ingest_lines(
    connection: duckdb.DuckDBPyConnection,
    lines: Iterable[str],
    *,
    source: str | None = None,
) -> IngestionStats:
    create_schema(connection)
    source_lines = 0
    parsed: list[Triple] = []
    for line_number, line in enumerate(lines, start=1):
        source_lines += 1
        triple = parse_ntriple_line(line, source=source, line_number=line_number)
        if triple is not None:
            parsed.append(triple)

    before = connection.execute("SELECT count(*) FROM rdf_triples").fetchone()[0]
    rows = []
    for triple in parsed:
        object_ = triple.object
        rows.append(
            (
                triple.triple_hash,
                triple.subject.value,
                triple.predicate.value,
                triple.object_kind,
                object_.value,
                object_.language if isinstance(object_, RDFLiteral) else None,
                object_.datatype if isinstance(object_, RDFLiteral) else None,
            )
        )
    if rows:
        connection.executemany(
            """
            INSERT OR IGNORE INTO rdf_triples
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    after = connection.execute("SELECT count(*) FROM rdf_triples").fetchone()[0]
    inserted = after - before
    return IngestionStats(
        source_lines=source_lines,
        parsed_triples=len(parsed),
        inserted_triples=inserted,
        duplicates=len(parsed) - inserted,
    )


def ingest_file(
    connection: duckdb.DuckDBPyConnection,
    path: str | Path,
) -> IngestionStats:
    source_path = Path(path)
    with source_path.open(encoding="utf-8") as handle:
        return ingest_lines(connection, handle, source=str(source_path))
