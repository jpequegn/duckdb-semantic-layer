# Capabilities, usage, and extensions

## What this project demonstrates

The project makes a graph query explainable in relational terms. A user writes a small SPARQL query, the parser produces a typed AST, and the planner shows the exact parameterized SQL that DuckDB executes. The evidence runner checks the translated result against independent direct SQL.

This is useful for learning where semantic meaning enters a data system:

- namespace declarations expand short domain names into stable IRIs
- shared variables express relationships without manually writing joins
- RDF term metadata prevents false matches between IRIs and literals
- generated plans make translation decisions reviewable
- differential tests detect parser or planner regressions

## Practical usage patterns

### Small semantic data products

Load a controlled export of triples and offer a narrow query vocabulary for analysts who need relationships but should not write SQL joins. Keep the supported grammar explicit and versioned.

### Translation verification

Use direct SQL as an independent oracle while developing a new query feature. Promote a feature only after fixtures cover term kinds, missing relationships, duplicate triples, and namespace errors.

### Explainable agent data access

Let an agent propose a bounded graph query, then require the plan explanation and parameter list before execution. The agent never receives an arbitrary SQL execution interface.

### Semantic contract tests

Store synthetic examples of business entities and relationships. Run known graph queries in CI to detect schema, namespace, or translator changes that alter expected meaning.

## Extension paths

### Query features

Add each feature as a grammar, AST, planner, and differential-test change. Useful next additions are LIMIT, deterministic ordering, numeric comparison over recognized datatypes, and a carefully scoped OPTIONAL.

### Import formats

Add a standards-backed Turtle parser behind the existing typed RDF models. Do not extend the current N-Triples grammar until conformance fixtures define the intended behavior.

### Provenance

Attach source document, ingestion run, and evidence identifiers to each stored triple. Query plans could then return both semantic results and source receipts.

### Ontology-aware validation

Load a small SHACL or application-specific constraint set and check type, cardinality, and allowed relationship rules during ingestion.

### Natural-language query proposals

Map natural language into the supported AST, not directly into SQL. Show the resolved prefixes, graph patterns, generated SQL, and differential or policy checks before execution.

### DuckDB extension

Once the prototype grammar and planner are stable, move the contract behind a DuckDB extension or table function. The Python implementation remains a useful reference oracle for conformance tests.

## Boundaries

The repository uses synthetic, non-sensitive data. It does not connect to enterprise systems, infer an ontology, execute arbitrary SQL from a query author, or claim compatibility with full RDF, Turtle, or SPARQL standards.
