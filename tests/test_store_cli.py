import json
from pathlib import Path

import pytest

from duckdb_semantic_layer.cli import main
from duckdb_semantic_layer.store import SemanticStore

FIXTURE = """
<urn:alice> <urn:name> "Alice" .
<urn:alice> <urn:city> "NYC" .
<urn:bob> <urn:name> "Bob" .
<urn:bob> <urn:city> "Paris" .
""".lstrip()

QUERY = """
SELECT ?person ?name WHERE {
  ?person <urn:name> ?name .
  ?person <urn:city> "NYC" .
}
"""


def _write_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "people.nt"
    fixture.write_text(FIXTURE, encoding="utf-8")
    return fixture


def test_store_load_query_and_explain(tmp_path: Path) -> None:
    database = tmp_path / "semantic.duckdb"
    with SemanticStore(database) as store:
        stats = store.load(_write_fixture(tmp_path))
        result = store.query(QUERY, source="people.rq")
        plan = store.explain(QUERY)

    assert stats.inserted_triples == 4
    assert result.columns == ("person", "name")
    assert result.rows == (("urn:alice", "Alice"),)
    assert "SELECT DISTINCT" in plan.sql


def test_cli_end_to_end_json_and_explain(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "semantic.duckdb"
    fixture = _write_fixture(tmp_path)

    assert main(["--db", str(database), "load", str(fixture), "--format", "json"]) == 0
    load_output = json.loads(capsys.readouterr().out)
    assert load_output["inserted_triples"] == 4

    assert (
        main(
            [
                "--db",
                str(database),
                "query",
                "--query",
                QUERY,
                "--format",
                "json",
            ]
        )
        == 0
    )
    query_output = json.loads(capsys.readouterr().out)
    assert query_output == [{"name": "Alice", "person": "urn:alice"}]

    assert main(["--db", str(database), "explain", "--query", QUERY]) == 0
    plan_output = json.loads(capsys.readouterr().out)
    assert plan_output["parameters"][0]["redacted"] is True


def test_cli_markdown_and_table_outputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "semantic.duckdb"
    fixture = _write_fixture(tmp_path)
    assert main(["--db", str(database), "load", str(fixture)]) == 0
    capsys.readouterr()

    assert main(["--db", str(database), "query", "--query", QUERY]) == 0
    assert "urn:alice | Alice" in capsys.readouterr().out

    assert (
        main(
            [
                "--db",
                str(database),
                "query",
                "--query",
                QUERY,
                "--format",
                "markdown",
            ]
        )
        == 0
    )
    assert "| urn:alice | Alice |" in capsys.readouterr().out


def test_cli_reads_query_file_and_reports_structured_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    query_file = tmp_path / "bad.rq"
    query_file.write_text("SELECT * WHERE {}", encoding="utf-8")

    assert main(["--db", ":memory:", "query", "--file", str(query_file)]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["code"] == "SPARQL_PARSE_ERROR"
    assert error["error"]["source"] == str(query_file)

    missing = tmp_path / "missing.rq"
    assert main(["query", "--file", str(missing)]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["code"] == "IO_ERROR"
