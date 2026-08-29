import json

import duckdb
import pytest

from duckdb_semantic_layer.errors import (
    KNOWN_DIAGNOSTIC_CODES,
    Diagnostic,
    SemanticLayerError,
)
from duckdb_semantic_layer.ingest import ingest_lines
from duckdb_semantic_layer.planner import build_query_plan
from duckdb_semantic_layer.sparql import parse_sparql
from duckdb_semantic_layer.store import SemanticStore


@pytest.mark.parametrize(
    "fragment",
    [
        "OPTIONAL { ?x <urn:q> ?y . }",
        "{ ?x <urn:q> ?y . } UNION { ?x <urn:r> ?z . }",
        "SERVICE <https://example.invalid> { ?x <urn:q> ?y . }",
        "?x <urn:p>/<urn:q> ?y .",
        "BIND(\"value\" AS ?bound)",
        "VALUES ?x { <urn:a> }",
    ],
)
def test_unsupported_syntax_fails_closed(fragment: str) -> None:
    query = f"SELECT ?x WHERE {{ ?x <urn:p> ?value . {fragment} }}"
    with pytest.raises(SemanticLayerError) as caught:
        parse_sparql(query)
    assert caught.value.diagnostic.code == "SPARQL_PARSE_ERROR"


def test_query_byte_limit_precedes_parsing() -> None:
    with pytest.raises(SemanticLayerError) as caught:
        parse_sparql(" " * 101, source="large.rq", max_query_bytes=100)

    assert caught.value.diagnostic.as_dict() == {
        "code": "SPARQL_QUERY_TOO_LARGE",
        "message": "Query is 101 bytes; maximum is 100",
        "source": "large.rq",
    }


def test_graph_pattern_limit() -> None:
    patterns = "\n".join(f"?s <urn:p{i}> ?o{i} ." for i in range(4))
    query = f"SELECT ?s WHERE {{ {patterns} }}"

    with pytest.raises(SemanticLayerError) as caught:
        parse_sparql(query, max_graph_patterns=3)

    assert caught.value.diagnostic.code == "SPARQL_PATTERN_LIMIT"


def test_injection_shaped_literal_stays_parameterized() -> None:
    attack = 'x\\" ); DROP TABLE rdf_triples; --'
    query = (
        "SELECT ?subject WHERE { "
        f'?subject <urn:label> "{attack}" . '
        "}"
    )
    plan = build_query_plan(parse_sparql(query))

    assert "DROP TABLE" not in plan.sql
    assert 'x" ); DROP TABLE rdf_triples; --' in plan.parameters

    with SemanticStore(":memory:") as store:
        result = store.query(query)
        count = store._fetch_validation_sql(
            "SELECT count(*) AS count FROM rdf_triples"
        )
    assert result.rows == ()
    assert count.rows == ((0,),)


def test_malformed_ingestion_does_not_partially_write() -> None:
    connection = duckdb.connect(":memory:")
    ingest_lines(connection, ["<urn:a> <urn:p> <urn:b> ."])

    with pytest.raises(SemanticLayerError):
        ingest_lines(
            connection,
            [
                "<urn:c> <urn:p> <urn:d> .",
                "<urn:broken> <urn:p> missing .",
            ],
        )

    assert connection.execute(
        "SELECT subject, object_value FROM rdf_triples ORDER BY subject"
    ).fetchall() == [("urn:a", "urn:b")]


def test_diagnostics_have_registered_codes_and_json_shape() -> None:
    diagnostic = Diagnostic(
        code="SPARQL_PARSE_ERROR",
        message="bad query",
        source="query.rq",
        line=2,
        column=4,
    )
    encoded = json.dumps({"error": diagnostic.as_dict()}, sort_keys=True)
    assert json.loads(encoded)["error"]["code"] in KNOWN_DIAGNOSTIC_CODES

    with pytest.raises(ValueError, match="unregistered"):
        Diagnostic(code="NEW_UNSTABLE_CODE", message="not registered")
