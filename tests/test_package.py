from duckdb_semantic_layer import __version__
from duckdb_semantic_layer.cli import main


def test_package_version() -> None:
    assert __version__ == "0.1.0"


def test_empty_cli_succeeds() -> None:
    assert main([]) == 0
