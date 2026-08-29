"""Structured errors shared by semantic-layer components."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

KNOWN_DIAGNOSTIC_CODES = frozenset(
    {
        "IO_ERROR",
        "QUERY_EXECUTION_ERROR",
        "RDF_PARSE_ERROR",
        "SPARQL_DUPLICATE_PREFIX",
        "SPARQL_DUPLICATE_SELECT",
        "SPARQL_PATTERN_LIMIT",
        "SPARQL_PARSE_ERROR",
        "SPARQL_QUERY_TOO_LARGE",
        "SPARQL_TERM_TYPE_MISMATCH",
        "SPARQL_UNBOUND_VARIABLE",
        "SPARQL_UNKNOWN_PREFIX",
    }
)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    source: str | None = None
    line: int | None = None
    column: int | None = None

    def __post_init__(self) -> None:
        if self.code not in KNOWN_DIAGNOSTIC_CODES:
            raise ValueError(f"unregistered diagnostic code: {self.code}")

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class SemanticLayerError(Exception):
    """An expected failure with a stable machine-readable diagnostic."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic
