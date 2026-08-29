"""Structured errors shared by semantic-layer components."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    source: str | None = None
    line: int | None = None
    column: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class SemanticLayerError(Exception):
    """An expected failure with a stable machine-readable diagnostic."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic
