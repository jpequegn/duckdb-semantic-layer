# DuckDB Semantic Layer

A local learning project that stores bounded RDF data in DuckDB and translates a deliberately small SPARQL subset into parameterized, inspectable SQL.

## What it does

- Parses IRI and literal terms from a bounded N-Triples grammar.
- Stores canonical triples in DuckDB with idempotent ingestion.
- Parses PREFIX, SELECT, basic graph patterns, and equality FILTER expressions.
- Resolves shared variables into joins that preserve RDF term identity.
- Shows generated SQL, parameter metadata, variable bindings, and plan steps.
- Compares five translated queries with independent direct SQL over synthetic data.
- Rejects unsupported syntax, unknown prefixes, unbound variables, oversized queries, and injection-shaped input.

This is not a complete RDF store, Turtle parser, SPARQL implementation, or production semantic layer.

## Quickstart

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

~~~bash
git clone https://github.com/jpequegn/duckdb-semantic-layer.git
cd duckdb-semantic-layer
uv sync --all-groups --locked --no-editable
~~~

Load the synthetic organization graph:

~~~bash
uv run semantic-layer --db semantic.duckdb load fixtures/organization.nt
~~~

Query employees who live in New York City:

~~~bash
uv run semantic-layer --db semantic.duckdb query \
  --file fixtures/queries/01-nyc-employees.rq \
  --format markdown
~~~

Inspect the generated SQL without running it:

~~~bash
uv run semantic-layer --db semantic.duckdb explain \
  --file fixtures/queries/02-engineers.rq
~~~

Run all five differential comparisons and write JSON and Markdown evidence:

~~~bash
uv run semantic-layer demo \
  --fixture fixtures/organization.nt \
  --output artifacts/demo
~~~

Expected result:

~~~text
PASS: 5/5 differential queries matched; report: artifacts/demo
~~~

## Supported query shape

~~~sparql
PREFIX org: <urn:org:>
SELECT ?person ?name WHERE {
  ?person org:name ?name .
  ?person org:homeCity org:nyc .
  FILTER (?name = "Alice")
}
~~~

The parser supports:

- one or more selected variables
- full IRIs and declared prefixed names
- basic graph patterns terminated by a period
- shared variables as explicit joins
- plain, language-tagged, and typed string literals
- equality filters between supported terms

It rejects SELECT *, OPTIONAL, UNION, SERVICE, property paths, updates, subqueries, aggregation, and every other unlisted feature.

## Architecture

~~~text
N-Triples -> grammar -> typed RDF terms -> canonical hashes -> DuckDB
SPARQL    -> grammar -> typed AST -> query planner -> parameterized SQL
                                               |-> redacted explanation
                                               |-> DuckDB result
                                               |-> direct-SQL comparison
~~~

DuckDB and the original triple values remain authoritative. The translator never interpolates parsed IRIs or literals into SQL. The explain command redacts parameter values unless the caller explicitly passes --show-parameter-values.

## Development

~~~bash
uv sync --all-groups --locked --no-editable
uv run ruff check .
uv run coverage run -m pytest
uv run coverage report --fail-under=90
uv build
~~~

See [the semantic model](docs/SEMANTIC_MODEL.md), [diagnostics](docs/DIAGNOSTICS.md), and [capabilities and extensions](docs/CAPABILITIES.md).

Source project: [jpequegn/project-ideas#254](https://github.com/jpequegn/project-ideas/issues/254).
