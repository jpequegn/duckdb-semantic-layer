from pathlib import Path

import duckdb
import pytest

from duckdb_semantic_layer.errors import SemanticLayerError
from duckdb_semantic_layer.ingest import ingest_file, ingest_lines, parse_ntriple_line
from duckdb_semantic_layer.rdf import IRI, RDFLiteral


def test_parse_iri_and_literal_terms() -> None:
    iri_triple = parse_ntriple_line("<urn:alice> <urn:knows> <urn:bob> .")
    assert iri_triple is not None
    assert iri_triple.object == IRI("urn:bob")

    literal_triple = parse_ntriple_line(
        r'<urn:alice> <urn:name> "Alice\nA."@EN-us .'
    )
    assert literal_triple is not None
    assert literal_triple.object == RDFLiteral("Alice\nA.", language="en-us")

    typed = parse_ntriple_line(
        '<urn:alice> <urn:age> "42"^^<http://www.w3.org/2001/XMLSchema#integer> .'
    )
    assert typed is not None
    assert typed.object == RDFLiteral(
        "42", datatype="http://www.w3.org/2001/XMLSchema#integer"
    )


def test_ingestion_is_idempotent_and_reports_duplicates() -> None:
    connection = duckdb.connect(":memory:")
    lines = [
        "<urn:a> <urn:p> <urn:b> .\n",
        "<urn:a> <urn:p> <urn:b> .\n",
        "# comment\n",
        "\n",
    ]

    first = ingest_lines(connection, lines, source="fixture.nt")
    second = ingest_lines(connection, lines, source="fixture.nt")

    assert first.source_lines == 4
    assert first.parsed_triples == 2
    assert first.inserted_triples == 1
    assert first.duplicates == 1
    assert second.inserted_triples == 0
    assert second.duplicates == 2
    assert connection.execute("SELECT count(*) FROM rdf_triples").fetchone()[0] == 1


def test_file_ingestion_preserves_optional_literal_fields(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.nt"
    fixture.write_text(
        '<urn:a> <urn:label> "hello"@en .\n'
        '<urn:a> <urn:count> "7"^^<urn:integer> .\n',
        encoding="utf-8",
    )
    connection = duckdb.connect(":memory:")

    stats = ingest_file(connection, fixture)

    assert stats.inserted_triples == 2
    rows = connection.execute(
        """
        SELECT object_value, object_language, object_datatype
        FROM rdf_triples ORDER BY object_value
        """
    ).fetchall()
    assert rows == [("7", None, "urn:integer"), ("hello", "en", None)]


def test_malformed_line_has_structured_location() -> None:
    with pytest.raises(SemanticLayerError) as caught:
        parse_ntriple_line(
            "<urn:a> <urn:p> missing .",
            source="bad.nt",
            line_number=17,
        )

    assert caught.value.diagnostic.as_dict() == {
        "code": "RDF_PARSE_ERROR",
        "message": "Malformed N-Triples input",
        "source": "bad.nt",
        "line": 17,
        "column": 17,
    }


def test_literal_cannot_have_language_and_datatype() -> None:
    with pytest.raises(ValueError, match="both"):
        RDFLiteral("value", language="en", datatype="urn:string")
