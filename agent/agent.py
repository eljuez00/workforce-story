"""HR analytics agent for Cedar Fork Health (fictional data).

Usage:
    python -m agent.agent                          # interactive
    python -m agent.agent "Why did nursing turnover spike in FY25?"

Requires ANTHROPIC_API_KEY. Set HR_AGENT_MODEL to change the model.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

from agent.tools import TOOL_DEFINITIONS, dispatch_tool

DEFAULT_MODEL = os.getenv("HR_AGENT_MODEL", "claude-sonnet-5-5")
MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = """You are the workforce analytics agent for Cedar Fork Health, a fictional regional health system
with about 5,000 employees. All data is synthetic. Fiscal years run October to September (FY2025 = Oct 2024 - Sep 2025),
and the data covers FY2024 through FY2026.

How to work:
- Answer only from tool results. Never estimate or invent a number. If the tools can't answer, say so.
- Prefer the curated metric tools; they match the official dashboard. Use run_sql only for questions they don't cover,
  and aggregate in SQL rather than pulling raw rows.
- State the fiscal year, the workforce group and the metric definition behind each number.
- You cannot see names, email or birth dates, and you cannot change data. Don't try to work around either.
- When asked "why", connect evidence across domains (turnover, recruiting, payroll, service, compensation) and say
  which parts are shown by the data and which are your interpretation.
- Be concise: lead with the answer, then the supporting numbers."""


@dataclass
class AgentResult:
    answer: str
    tool_calls: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    stopped_early: bool = False


def run_agent(question: str, history: list | None = None, client=None, model: str = DEFAULT_MODEL,
              verbose: bool = False) -> AgentResult:
    """Run the tool-use loop until the model answers or the round limit is reached."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    messages = list(history or []) + [{"role": "user", "content": question}]
    calls = []
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(model=model, max_tokens=1500, system=SYSTEM_PROMPT,
                                          tools=TOOL_DEFINITIONS, messages=messages)
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
            return AgentResult(text, calls, messages)
        results = []
        for block in response.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            payload, is_error = dispatch_tool(block.name, block.input)
            calls.append({"tool": block.name, "input": block.input, "error": is_error})
            if verbose:
                print(f"  [tool] {block.name}({json.dumps(block.input)}){' -> refused' if is_error else ''}")
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": payload, "is_error": is_error})
        messages.append({"role": "user", "content": results})
    return AgentResult("I stopped after reaching the tool-call limit without a final answer.", calls, messages, True)


def main():
    if len(sys.argv) > 1:
        print(run_agent(" ".join(sys.argv[1:]), verbose=True).answer)
        return
    print("Cedar Fork Health workforce agent (fictional data). Type a question, or 'quit'.\n")
    history = []
    while True:
        q = input("You: ").strip()
        if q.lower() in ("quit", "exit", "q"):
            break
        if not q:
            continue
        res = run_agent(q, history, verbose=True)
        history = res.messages
        print(f"\nAgent: {res.answer}\n")


if __name__ == "__main__":
    main()
