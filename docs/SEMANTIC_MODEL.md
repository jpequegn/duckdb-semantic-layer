# Semantic model and query boundary

## Stored triples

The rdf_triples table stores one canonical row per RDF triple:

| Column | Meaning |
| --- | --- |
| triple_hash | SHA-256 over the canonical subject, predicate, object kind, lexical value, language, and datatype |
| subject | Full subject IRI |
| predicate | Full predicate IRI |
| object_kind | Either iri or literal |
| object_value | Full object IRI or literal lexical value |
| object_language | Normalized language tag when present |
| object_datatype | Full datatype IRI when present |

The primary key makes repeated ingestion idempotent. Ingestion statistics still report every parsed source line and duplicate.

Subjects and predicates must be IRIs. Objects may be IRIs or string literals. Blank nodes, RDF-star, collections, relative IRIs, numeric shorthand, and Turtle syntax are outside this version.

## Query model

The parser produces typed prefixes, variables, triple patterns, equality filters, and a select projection. Prefixes resolve before planning. Unknown or duplicate prefixes fail before SQL generation.

A shared variable means RDF term equality:

- subject-to-subject and predicate-to-predicate joins compare their IRI values
- object-to-subject or object-to-predicate joins also require the object kind to be iri
- object-to-object joins compare lexical value, object kind, language, and datatype

This prevents a plain literal and an IRI with the same text from joining accidentally.

## SQL boundary

The planner controls table aliases, column names, and generated clauses. The grammar restricts variable names before they become quoted result aliases. Every parsed IRI and literal becomes a positional DuckDB parameter.

Plans include:

- generated SQL
- ordered parameter metadata
- selected-variable bindings
- constraints introduced for each graph pattern

Parameter values remain redacted by default.

## Limits

- Maximum UTF-8 query size: 65,536 bytes
- Maximum basic graph patterns: 32
- Supported filter operator: equality only
- Result projection: explicitly named variables only

Unsupported syntax fails as a complete query. The parser does not drop unknown clauses or execute a supported prefix of a larger query.
