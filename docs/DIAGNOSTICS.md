# Diagnostics

Expected failures use JSON-serializable diagnostics with a stable code and message. Source, line, and column appear when available.

~~~json
{
  "error": {
    "code": "SPARQL_PARSE_ERROR",
    "message": "Unsupported or malformed SPARQL query",
    "source": "query.rq",
    "line": 2,
    "column": 14
  }
}
~~~

| Code | Meaning |
| --- | --- |
| IO_ERROR | A requested local file could not be read |
| QUERY_EXECUTION_ERROR | DuckDB rejected an otherwise planned query |
| RDF_PARSE_ERROR | An N-Triples line is malformed or unsupported |
| SPARQL_DUPLICATE_PREFIX | A prefix name is declared more than once |
| SPARQL_DUPLICATE_SELECT | A selected variable appears more than once |
| SPARQL_PATTERN_LIMIT | The query exceeds 32 graph patterns |
| SPARQL_PARSE_ERROR | The query is malformed or uses unsupported syntax |
| SPARQL_QUERY_TOO_LARGE | The UTF-8 query exceeds 65,536 bytes |
| SPARQL_TERM_TYPE_MISMATCH | A literal is constrained into an IRI-only position |
| SPARQL_UNBOUND_VARIABLE | A selected or filtered variable has no graph-pattern binding |
| SPARQL_UNKNOWN_PREFIX | A prefixed name has no declaration |

CLI domain and file failures exit with status 2 and write the diagnostic to standard error. A differential demo mismatch exits with status 1.
