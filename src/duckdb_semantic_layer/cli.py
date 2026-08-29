"""Command-line interface for ingestion, querying, and explanation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from duckdb_semantic_layer.errors import Diagnostic, SemanticLayerError
from duckdb_semantic_layer.evidence import run_evidence
from duckdb_semantic_layer.store import QueryResult, SemanticStore


def _add_query_source(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", help="Inline SPARQL query text")
    group.add_argument("--file", type=Path, help="Path to a SPARQL query file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="semantic-layer",
        description="Query a bounded RDF semantic layer backed by DuckDB.",
    )
    parser.add_argument(
        "--db",
        default="semantic.duckdb",
        help="DuckDB database path (default: semantic.duckdb)",
    )
    subparsers = parser.add_subparsers(dest="command")

    load = subparsers.add_parser("load", help="Load an N-Triples file")
    load.add_argument("source", type=Path)
    load.add_argument("--format", choices=("text", "json"), default="text")

    query = subparsers.add_parser("query", help="Run a supported SPARQL query")
    _add_query_source(query)
    query.add_argument(
        "--format",
        choices=("table", "json", "markdown"),
        default="table",
    )

    explain = subparsers.add_parser("explain", help="Show a query plan without executing it")
    _add_query_source(explain)
    explain.add_argument(
        "--show-parameter-values",
        action="store_true",
        help="Include parameter values in the local explanation",
    )

    demo = subparsers.add_parser("demo", help="Run differential fixture verification")
    demo.add_argument(
        "--fixture",
        type=Path,
        default=Path("fixtures/organization.nt"),
    )
    demo.add_argument("--output", type=Path, default=Path("artifacts/demo"))
    return parser


def _query_text(args: argparse.Namespace) -> tuple[str, str | None]:
    if args.query is not None:
        return args.query, None
    assert args.file is not None
    return args.file.read_text(encoding="utf-8"), str(args.file)


def _format_table(result: QueryResult) -> str:
    widths = [
        max(len(column), *(len(str(row[index])) for row in result.rows))
        for index, column in enumerate(result.columns)
    ]
    header = " | ".join(column.ljust(widths[index]) for index, column in enumerate(result.columns))
    separator = "-+-".join("-" * width for width in widths)
    rows = [
        " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))
        for row in result.rows
    ]
    return "\n".join([header, separator, *rows])


def _format_markdown(result: QueryResult) -> str:
    header = "| " + " | ".join(result.columns) + " |"
    separator = "| " + " | ".join("---" for _ in result.columns) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in result.rows]
    return "\n".join([header, separator, *rows])


def _write_result(result: QueryResult, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(list(result.records()), indent=2, sort_keys=True))
    elif output_format == "markdown":
        print(_format_markdown(result))
    else:
        print(_format_table(result))


def _run(args: argparse.Namespace) -> int:
    if args.command is None:
        build_parser().print_help()
        return 0

    if args.command == "demo":
        report = run_evidence(args.fixture, output_directory=args.output)
        print(
            f"{'PASS' if report.passed else 'FAIL'}: "
            f"{sum(case.matched for case in report.cases)}/{len(report.cases)} "
            f"differential queries matched; report: {args.output}"
        )
        return 0 if report.passed else 1

    with SemanticStore(args.db) as store:
        if args.command == "load":
            stats = store.load(args.source)
            payload = {
                "source_lines": stats.source_lines,
                "parsed_triples": stats.parsed_triples,
                "inserted_triples": stats.inserted_triples,
                "duplicates": stats.duplicates,
            }
            if args.format == "json":
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(
                    f"Loaded {stats.inserted_triples} triples "
                    f"({stats.duplicates} duplicates, {stats.source_lines} source lines)"
                )
            return 0

        query_text, source = _query_text(args)
        if args.command == "explain":
            plan = store.explain(query_text, source=source)
            print(
                json.dumps(
                    plan.as_dict(include_parameter_values=args.show_parameter_values),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        _write_result(store.query(query_text, source=source), args.format)
        return 0


def _io_diagnostic(exc: OSError) -> Diagnostic:
    filename = str(exc.filename) if exc.filename else None
    return Diagnostic(code="IO_ERROR", message=str(exc), source=filename)


def _print_error(diagnostic: Diagnostic) -> None:
    payload: dict[str, Any] = {"error": diagnostic.as_dict()}
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except SemanticLayerError as exc:
        _print_error(exc.diagnostic)
        return 2
    except OSError as exc:
        _print_error(_io_diagnostic(exc))
        return 2
