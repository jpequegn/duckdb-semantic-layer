"""Typed AST for the supported SPARQL subset."""

from __future__ import annotations

from dataclasses import dataclass

from duckdb_semantic_layer.rdf import IRI, RDFLiteral


@dataclass(frozen=True, slots=True)
class Variable:
    name: str


QueryTerm = Variable | IRI | RDFLiteral


@dataclass(frozen=True, slots=True)
class Prefix:
    name: str
    iri: str


@dataclass(frozen=True, slots=True)
class TriplePattern:
    subject: Variable | IRI
    predicate: Variable | IRI
    object: QueryTerm

    def variables(self) -> set[str]:
        return {
            term.name
            for term in (self.subject, self.predicate, self.object)
            if isinstance(term, Variable)
        }


@dataclass(frozen=True, slots=True)
class EqualityFilter:
    left: QueryTerm
    right: QueryTerm

    def variables(self) -> set[str]:
        return {
            term.name for term in (self.left, self.right) if isinstance(term, Variable)
        }


@dataclass(frozen=True, slots=True)
class SelectQuery:
    prefixes: tuple[Prefix, ...]
    selected: tuple[Variable, ...]
    patterns: tuple[TriplePattern, ...]
    filters: tuple[EqualityFilter, ...]
