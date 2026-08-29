import pytest

from duckdb_semantic_layer.errors import SemanticLayerError
from duckdb_semantic_layer.planner import build_query_plan
from duckdb_semantic_layer.query import (
    EqualityFilter,
    SelectQuery,
    TriplePattern,
    Variable,
)
from duckdb_semantic_layer.rdf import IRI, RDFLiteral
from duckdb_semantic_layer.sparql import parse_sparql


def test_single_pattern_plan_parameterizes_constants() -> None:
    query = parse_sparql(
        """
        PREFIX ex: <urn:example:>
        SELECT ?person WHERE { ?person ex:city "NYC" . }
        """
    )

    plan = build_query_plan(query)

    assert "urn:example:city" not in plan.sql
    assert "NYC" not in plan.sql
    assert plan.parameters == ("urn:example:city", "NYC", None, None)
    assert plan.sql == (
        'SELECT DISTINCT t0.subject AS "person"\n'
        "FROM rdf_triples AS t0\n"
        "WHERE t0.predicate = ?\n"
        "  AND t0.object_kind = 'literal'\n"
        "  AND t0.object_value = ?\n"
        "  AND t0.object_language IS NOT DISTINCT FROM ?\n"
        "  AND t0.object_datatype IS NOT DISTINCT FROM ?\n"
        "ORDER BY 1"
    )


def test_shared_variable_creates_explicit_join() -> None:
    plan = build_query_plan(
        parse_sparql(
            """
            PREFIX ex: <urn:example:>
            SELECT ?person ?city WHERE {
              ?person ex:livesIn ?city .
              ?city ex:country ex:usa .
            }
            """
        )
    )

    assert "JOIN rdf_triples AS t1 ON TRUE" in plan.sql
    assert "t0.object_value = t1.subject" in plan.sql
    assert "t0.object_kind = 'iri'" in plan.sql
    assert [binding.variable for binding in plan.bindings] == ["person", "city"]


def test_repeated_object_variable_compares_full_term_identity() -> None:
    plan = build_query_plan(
        parse_sparql(
            """
            SELECT ?value WHERE {
              <urn:a> <urn:p> ?value .
              <urn:b> <urn:p> ?value .
            }
            """
        )
    )

    assert "t0.object_kind = t1.object_kind" in plan.sql
    assert "t0.object_language IS NOT DISTINCT FROM t1.object_language" in plan.sql
    assert "t0.object_datatype IS NOT DISTINCT FROM t1.object_datatype" in plan.sql


def test_filter_is_parameterized() -> None:
    plan = build_query_plan(
        parse_sparql(
            """
            SELECT ?name WHERE {
              <urn:alice> <urn:name> ?name .
              FILTER (?name = "Alice")
            }
            """
        )
    )

    assert plan.parameters[-3:] == ("Alice", None, None)
    assert "Alice" not in plan.sql


def test_explanation_redacts_parameters_by_default() -> None:
    plan = build_query_plan(
        parse_sparql("SELECT ?value WHERE { <urn:a> <urn:p> ?value . }")
    )

    redacted = plan.as_dict()
    revealed = plan.as_dict(include_parameter_values=True)

    assert redacted["parameters"] == [
        {"index": 1, "type": "string", "redacted": True},
        {"index": 2, "type": "string", "redacted": True},
    ]
    assert revealed["parameters"] == ["urn:a", "urn:p"]


def test_literal_filter_on_subject_variable_is_rejected() -> None:
    query = SelectQuery(
        prefixes=(),
        selected=(Variable("subject"),),
        patterns=(
            TriplePattern(Variable("subject"), IRI("urn:p"), Variable("value")),
        ),
        filters=(EqualityFilter(Variable("subject"), RDFLiteral("not-an-iri")),),
    )

    with pytest.raises(SemanticLayerError) as caught:
        build_query_plan(query)
    assert caught.value.diagnostic.code == "SPARQL_TERM_TYPE_MISMATCH"
