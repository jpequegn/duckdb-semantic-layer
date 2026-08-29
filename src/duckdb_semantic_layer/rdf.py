"""Typed RDF terms used by ingestion and query planning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal as TypingLiteral


@dataclass(frozen=True, slots=True)
class IRI:
    value: str

    def canonical(self) -> tuple[str, str, str, str]:
        return ("iri", self.value, "", "")


@dataclass(frozen=True, slots=True)
class RDFLiteral:
    value: str
    language: str | None = None
    datatype: str | None = None

    def __post_init__(self) -> None:
        if self.language and self.datatype:
            raise ValueError("an RDF literal cannot have both a language and datatype")

    def canonical(self) -> tuple[str, str, str, str]:
        return ("literal", self.value, self.language or "", self.datatype or "")


RDFObject = IRI | RDFLiteral


@dataclass(frozen=True, slots=True)
class Triple:
    subject: IRI
    predicate: IRI
    object: RDFObject

    @property
    def triple_hash(self) -> str:
        payload = (
            self.subject.value,
            self.predicate.value,
            *self.object.canonical(),
        )
        encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def object_kind(self) -> TypingLiteral["iri", "literal"]:
        return "iri" if isinstance(self.object, IRI) else "literal"
