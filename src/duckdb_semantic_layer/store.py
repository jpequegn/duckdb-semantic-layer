"""High-level semantic store over a DuckDB connection."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import duckdb

from duckdb_semantic_layer.errors import Diagnostic, SemanticLayerError
from duckdb_semantic_layer.ingest import IngestionStats, create_schema, ingest_file
from duckdb_semantic_layer.planner import QueryPlan, build_query_plan
from duckdb_semantic_layer.sparql import parse_sparql


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    plan: QueryPlan

    def records(self) -> Iterator[dict[str, Any]]:
        for row in self.rows:
            yield dict(zip(self.columns, row, strict=True))


class SemanticStore:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self.database = str(database)
        self._connection = duckdb.connect(self.database)
        create_schema(self._connection)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def load(self, path: str | Path) -> IngestionStats:
        return ingest_file(self._connection, path)

    def explain(self, query_text: str, *, source: str | None = None) -> QueryPlan:
        return build_query_plan(parse_sparql(query_text, source=source))

    def query(self, query_text: str, *, source: str | None = None) -> QueryResult:
        plan = self.explain(query_text, source=source)
        try:
            cursor = self._connection.execute(plan.sql, list(plan.parameters))
            columns = tuple(item[0] for item in cursor.description)
            rows = tuple(cursor.fetchall())
        except duckdb.Error as exc:
            raise SemanticLayerError(
                Diagnostic(
                    code="QUERY_EXECUTION_ERROR",
                    message=f"DuckDB query execution failed: {exc}",
                    source=source,
                )
            ) from exc
        return QueryResult(columns=columns, rows=rows, plan=plan)
