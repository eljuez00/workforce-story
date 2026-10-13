import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _audit_to_tmp(tmp_path, monkeypatch):
    """Keep test runs out of the real audit log."""
    import agent.guardrails as g
    monkeypatch.setattr(g, "AUDIT_LOG", tmp_path / "audit.jsonl")
    original = g.audit
    monkeypatch.setattr("agent.tools.audit", lambda *a, **k: original(*a, log_path=tmp_path / "audit.jsonl", **k))
