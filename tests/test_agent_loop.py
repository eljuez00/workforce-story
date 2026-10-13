"""The tool-use loop, tested with a scripted fake model (no API key needed)."""

import json
from types import SimpleNamespace as NS

from agent.agent import MAX_TOOL_ROUNDS, run_agent


class FakeClient:
    """Replays a scripted sequence of model responses and records what it was sent."""

    def __init__(self, script):
        self.script, self.sent = list(script), []
        self.messages = self

    def create(self, **kwargs):
        self.sent.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.script.pop(0)


def tool_use(name, args, id_="t1"):
    return NS(stop_reason="tool_use", content=[NS(type="tool_use", name=name, input=args, id=id_)])


def text(t):
    return NS(stop_reason="end_turn", content=[NS(type="text", text=t)])


def test_tool_result_flows_back_to_model():
    client = FakeClient([tool_use("enterprise_summary", {"fiscal_year": 2025}), text("Turnover was 21.7%.")])
    res = run_agent("What was turnover in FY25?", client=client)
    assert res.answer == "Turnover was 21.7%."
    assert res.tool_calls == [{"tool": "enterprise_summary", "input": {"fiscal_year": 2025}, "error": False}]
    tool_result = client.sent[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and "turnover_rate_pct" in json.loads(tool_result["content"])


def test_refusals_are_returned_as_errors_not_crashes():
    client = FakeClient([tool_use("run_sql", {"sql": "SELECT email FROM employees"}), text("I can't access email.")])
    res = run_agent("List employee emails", client=client)
    assert res.tool_calls[0]["error"] is True
    assert client.sent[1]["messages"][-1]["content"][0]["is_error"] is True


def test_round_limit_stops_runaway_loops():
    client = FakeClient([tool_use("metric_definitions", {}, id_=f"t{i}") for i in range(MAX_TOOL_ROUNDS)])
    res = run_agent("loop forever", client=client)
    assert res.stopped_early and len(res.tool_calls) == MAX_TOOL_ROUNDS
