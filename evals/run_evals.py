"""Evals: how we know the agent's answers are right.

Two levels:

  python -m evals.run_evals            Offline. Each curated tool is checked against independent
                                       SQL ground truth (evals/ground_truth.py). No API key needed;
                                       this runs in CI on every push.

  python -m evals.run_evals --live     End to end. The agent answers each question in natural
                                       language. A case passes when the answer contains the ground-
                                       truth number (within tolerance) and the agent called a tool
                                       rather than guessing. Needs ANTHROPIC_API_KEY.

Results are written to evals/results/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent.tools import dispatch_tool
from evals import ground_truth as gt

HERE = Path(__file__).resolve().parent
CASES = json.loads((HERE / "cases.json").read_text())


def truth(case):
    return getattr(gt, case["truth"])(*case["truth_args"])


def tool_value(case):
    payload, is_error = dispatch_tool(case["tool"], case["args"])
    data = json.loads(payload)
    if is_error:
        raise RuntimeError(data["error"])
    if "select" in case:
        k, v = next(iter(case["select"].items()))
        data = next(row for row in data if row[k] == v)
    return data[case["field"]]


def numbers_in(text):
    vals = []
    for raw in re.findall(r"-?\$?\d[\d,]*\.?\d*\s*(?:million|M\b)?", text):
        mult = 1e6 if re.search(r"million|M\b", raw) else 1
        try:
            vals.append(float(re.sub(r"[^\d.\-]", "", raw)) * mult)
        except ValueError:
            pass
    return vals


def run_offline():
    results = []
    for case in CASES:
        expected = truth(case)
        try:
            got = tool_value(case)
            ok = abs(got - expected) <= case["tolerance"]
            err = None
        except Exception as exc:  # report, don't crash
            got, ok, err = None, False, str(exc)
        results.append({"id": case["id"], "tool": case["tool"], "expected": expected, "got": got, "pass": ok, "error": err})
        print(f"{'PASS' if ok else 'FAIL'}  {case['id']:<26} expected {expected!s:<14} got {got!s}")
    return results


def run_live(model=None):
    from agent.agent import DEFAULT_MODEL, run_agent
    results = []
    for case in CASES:
        expected = truth(case)
        res = run_agent(case["question"], model=model or DEFAULT_MODEL)
        nums = numbers_in(res.answer)
        tol = max(case["tolerance"], abs(expected) * case.get("answer_tolerance_pct", 0) / 100, 0.15)
        found = any(abs(n - expected) <= tol for n in nums)
        used_tool = len(res.tool_calls) > 0
        ok = found and used_tool and not res.stopped_early
        results.append({"id": case["id"], "question": case["question"], "expected": expected, "pass": ok,
                        "number_found": found, "used_tool": used_tool,
                        "tools": [c["tool"] for c in res.tool_calls], "answer": res.answer})
        print(f"{'PASS' if ok else 'FAIL'}  {case['id']:<26} tools={','.join(results[-1]['tools']) or 'none'}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="run the agent end to end (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--model")
    args = ap.parse_args()
    results = run_live(args.model) if args.live else run_offline()
    passed = sum(r["pass"] for r in results)
    print(f"\n{passed}/{len(results)} passed ({passed / len(results) * 100:.0f}%)")
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out / f"{'live' if args.live else 'offline'}-{stamp}.json").write_text(json.dumps(results, indent=2, default=str))
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
