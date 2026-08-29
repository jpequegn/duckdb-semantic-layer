import pytest

from duckdb_semantic_layer.errors import SemanticLayerError
from duckdb_semantic_layer.query import EqualityFilter, TriplePattern, Variable
from duckdb_semantic_layer.rdf import IRI, RDFLiteral
from duckdb_semantic_layer.sparql import parse_sparql

QUERY = """
PREFIX ex: <urn:example:>
SELECT ?employee ?name
WHERE {
  ?employee ex:name ?name .
  ?employee ex:city "NYC" .
  FILTER (?name = "Alice")
}
"""


def test_parse_prefix_patterns_join_and_filter() -> None:
    query = parse_sparql(QUERY)

    assert [variable.name for variable in query.selected] == ["employee", "name"]
    assert query.patterns == (
        TriplePattern(Variable("employee"), IRI("urn:example:name"), Variable("name")),
        TriplePattern(
            Variable("employee"),
            IRI("urn:example:city"),
            RDFLiteral("NYC"),
        ),
    )
    assert query.filters == (EqualityFilter(Variable("name"), RDFLiteral("Alice")),)


def test_resolve_prefixed_datatype() -> None:
    query = parse_sparql(
        """
        PREFIX ex: <urn:example:>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT ?person WHERE {
          ?person ex:age "42"^^xsd:integer .
        }
        """
    )
    assert query.patterns[0].object == RDFLiteral(
        "42", datatype="http://www.w3.org/2001/XMLSchema#integer"
    )


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (
            "SELECT ?x WHERE { ?x missing:name ?name . }",
            "SPARQL_UNKNOWN_PREFIX",
        ),
        (
            "PREFIX ex: <urn:a:> PREFIX ex: <urn:b:> SELECT ?x WHERE { ?x ex:p ?v . }",
            "SPARQL_DUPLICATE_PREFIX",
        ),
        (
            "SELECT ?missing WHERE { ?x <urn:p> ?value . }",
            "SPARQL_UNBOUND_VARIABLE",
        ),
        (
            "SELECT ?x WHERE { ?x <urn:p> ?value . FILTER (?missing = \"x\") }",
            "SPARQL_UNBOUND_VARIABLE",
        ),
        (
            "SELECT ?x ?x WHERE { ?x <urn:p> ?value . }",
            "SPARQL_DUPLICATE_SELECT",
        ),
        (
            "SELECT ?x WHERE { ?x <urn:p> ?value . OPTIONAL { ?x <urn:q> ?y . } }",
            "SPARQL_PARSE_ERROR",
        ),
        (
            "SELECT * WHERE { ?x <urn:p> ?value . }",
            "SPARQL_PARSE_ERROR",
        ),
    ],
)
def test_invalid_queries_fail_closed(text: str, code: str) -> None:
    with pytest.raises(SemanticLayerError) as caught:
        parse_sparql(text, source="query.rq")
    assert caught.value.diagnostic.code == code


def test_parse_error_contains_location() -> None:
    with pytest.raises(SemanticLayerError) as caught:
        parse_sparql("SELECT ?x WHERE {\n  ?x <urn:p> .\n}", source="bad.rq")
    diagnostic = caught.value.diagnostic
    assert diagnostic.code == "SPARQL_PARSE_ERROR"
    assert diagnostic.source == "bad.rq"
    assert diagnostic.line == 2
    assert diagnostic.column > 0
