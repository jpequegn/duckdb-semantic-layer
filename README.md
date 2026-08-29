# DuckDB Semantic Layer

A local learning project that loads a bounded RDF representation into DuckDB and translates a deliberately small SPARQL subset into parameterized, inspectable SQL.

## Scope

The project will support N-Triples ingestion, typed query parsing, basic graph patterns, explicit joins, equality filters, query-plan explanations, and differential verification against direct SQL. It will fail closed on syntax outside that subset.

It is not a complete RDF store, Turtle parser, SPARQL implementation, or production semantic layer.

## Architecture

\`\`\`text
N-Triples -> typed RDF terms -> DuckDB triples
SPARQL text -> grammar -> typed AST -> query plan -> parameterized SQL
                                             |-> explanation
                                             |-> DuckDB result
\`\`\`

## Development

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

\`\`\`bash
uv sync --all-groups --no-editable
uv run ruff check .
uv run pytest
\`\`\`

Source project: [jpequegn/project-ideas#254](https://github.com/jpequegn/project-ideas/issues/254).
