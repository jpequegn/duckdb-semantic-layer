"""Command-line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="semantic-layer",
        description="Query a bounded RDF semantic layer backed by DuckDB.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
