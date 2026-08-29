import json
from pathlib import Path

from duckdb_semantic_layer.cli import main
from duckdb_semantic_layer.evidence import CASES, run_evidence

FIXTURE = Path("fixtures/organization.nt")


def test_five_queries_match_direct_sql() -> None:
    report = run_evidence(FIXTURE)

    assert len(CASES) == 5
    assert report.passed
    assert report.parsed_triples == 20
    assert report.inserted_triples == 19
    assert report.duplicates == 1
    assert all(case.translated_rows == case.direct_rows for case in report.cases)


def test_evidence_is_repeatable() -> None:
    first = run_evidence(FIXTURE)
    second = run_evidence(FIXTURE)

    assert first.as_dict() == second.as_dict()


def test_demo_writes_json_and_markdown(tmp_path: Path) -> None:
    output = tmp_path / "evidence"

    assert main(["demo", "--fixture", str(FIXTURE), "--output", str(output)]) == 0

    payload = json.loads((output / "evidence.json").read_text(encoding="utf-8"))
    markdown = (output / "evidence.md").read_text(encoding="utf-8")
    assert payload["passed"] is True
    assert len(payload["cases"]) == 5
    assert "Overall result: PASS" in markdown
    assert "Generated SQL" in markdown
    assert "Direct SQL" in markdown
