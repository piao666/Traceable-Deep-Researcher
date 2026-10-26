import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.probes.structured_output import parse_fixture_draft

ROOT = Path(__file__).parents[2]


def test_structured_draft_rejects_unknown_evidence():
    good = {"claims": [{"text": "A costs 10", "evidence_ids": ["e1"]}]}
    assert parse_fixture_draft(good, {"e1"}).claims[0].text == "A costs 10"
    with pytest.raises(ValueError, match="unknown evidence"):
        parse_fixture_draft(good, {"e2"})
    with pytest.raises(ValidationError):
        parse_fixture_draft({"claims": [{"text": "", "evidence_ids": []}]}, {"e1"})


def test_sqlite_transaction_and_reopen(tmp_path):
    from evals.probes.recovery import probe_sqlite
    assert probe_sqlite(tmp_path / "events.sqlite") == {"persisted_seq": [1], "duplicate_rejected": True}


def test_langgraph_interrupt_survives_process_restart(tmp_path):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    database = tmp_path / "graph.sqlite"
    results = []
    for stage in ("pause", "resume"):
        result = subprocess.run([sys.executable, "-m", "evals.probes.recovery", "--database", str(database),
                                 "--stage", stage], cwd=ROOT, capture_output=True, text=True,
                                env=os.environ | {"LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false"}, timeout=30)
        assert result.returncode == 0, result.stderr
        results.append(json.loads(result.stdout))
    assert results[0]["status"] == "waiting_for_review"
    assert results[1]["status"] == "resumed"
    assert results[1]["decision"] == "approve"
