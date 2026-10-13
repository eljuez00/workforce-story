"""Tools the HR analytics agent can call.

Most tools wrap the same metric functions the dashboard uses (metrics/core.py), so the
agent and the dashboard report identical numbers. run_sql is the escape hatch for
questions the curated tools don't cover, and it runs behind the guardrails.
"""

from __future__ import annotations

import json
import sqlite3
import time

from agent.guardrails import DB_PATH, PII_COLUMNS, GuardrailError, audit, run_readonly_sql
from metrics.core import DEFINITIONS, FISCAL_YEARS, GROUPS, HRMetrics

_metrics: HRMetrics | None = None


def metrics() -> HRMetrics:
    global _metrics
    if _metrics is None:
        _metrics = HRMetrics()
    return _metrics


FY = {"type": "integer", "enum": list(FISCAL_YEARS),
      "description": "Fiscal year. FY runs October to September, so FY2025 is Oct 2024 - Sep 2025."}
GROUP = {"type": "string", "enum": list(GROUPS), "default": "all",
         "description": "Workforce group: all, clinical or nonclinical."}


def _tool(name, description, props=None, required=None):
    props = props or {}
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props, "required": required or []}}


TOOL_DEFINITIONS = [
    _tool("enterprise_summary", "Headcount (start, end, average), FTE, hires, terminations, turnover rates, gross payroll "
          "and labor cost per FTE for a fiscal year.", {"fiscal_year": FY, "group": GROUP}, ["fiscal_year"]),
    _tool("retention_summary", "Turnover, voluntary and involuntary turnover, early-tenure turnover share, retention rate "
          "and the top voluntary reason for a fiscal year.", {"fiscal_year": FY, "group": GROUP}, ["fiscal_year"]),
    _tool("turnover_breakdown", "Turnover for a fiscal year broken down by job_family, dept_name, division (as rates), "
          "or by tenure_band or term_reason (as counts and shares).",
          {"fiscal_year": FY, "group": GROUP,
           "by": {"type": "string", "enum": ["job_family", "dept_name", "division", "tenure_band", "term_reason"]}},
          ["fiscal_year", "by"]),
    _tool("monthly_turnover", "Monthly headcount, terminations and annualized turnover from Oct 2023 to Sep 2026, "
          "optionally for one job family (for example Nursing).",
          {"job_family": {"type": "string"}, "group": GROUP}),
    _tool("recruiting_summary", "Requisitions opened and filled, days to fill, open requisitions and vacancy rate at "
          "year end, offer acceptance rate and applicants per filled requisition.",
          {"fiscal_year": FY, "group": GROUP}, ["fiscal_year"]),
    _tool("recruiting_breakdown", "Recruiting metrics for a fiscal year by job_family, dept_name or job_title "
          "(days to fill, offer acceptance), or hires by source_of_hire.",
          {"fiscal_year": FY, "group": GROUP,
           "by": {"type": "string", "enum": ["job_family", "dept_name", "job_title", "source_of_hire"]}},
          ["fiscal_year", "by"]),
    _tool("recruiting_funnel", "Applicant funnel counts from applied to hired for requisitions filled in a fiscal year.",
          {"fiscal_year": FY, "group": GROUP}, ["fiscal_year"]),
    _tool("payroll_summary", "Gross pay, overtime pay and rate, shift differential, other pay, premium pay share and "
          "off-cycle corrections for a fiscal year.", {"fiscal_year": FY, "group": GROUP}, ["fiscal_year"]),
    _tool("payroll_breakdown", "Gross pay, overtime pay and overtime rate for a fiscal year by dept_name or job_family.",
          {"fiscal_year": FY, "group": GROUP, "by": {"type": "string", "enum": ["dept_name", "job_family"]}},
          ["fiscal_year", "by"]),
    _tool("service_summary", "HR service center cases, SLA met rate, resolution time, first contact resolution, CSAT, "
          "AI-assisted triage share and time to assign for a fiscal year.",
          {"fiscal_year": FY, "group": GROUP}, ["fiscal_year"]),
    _tool("service_breakdown", "HR case metrics for a fiscal year by category, subcategory, channel, priority or "
          "triage_method.",
          {"fiscal_year": FY, "group": GROUP,
           "by": {"type": "string", "enum": ["category", "subcategory", "channel", "priority", "triage_method"]}},
          ["fiscal_year", "by"]),
    _tool("compensation_summary", "Compa-ratio, share below range midpoint, merit increases, promotions, market "
          "adjustments and the within-job gender pay ratio at fiscal year end.",
          {"fiscal_year": FY, "group": GROUP}, ["fiscal_year"]),
    _tool("compensation_breakdown", "Compa-ratio, range penetration and average annual pay at fiscal year end by "
          "job_family, job_title, grade or dept_name.",
          {"fiscal_year": FY, "group": GROUP,
           "by": {"type": "string", "enum": ["job_family", "job_title", "grade", "dept_name"]}},
          ["fiscal_year", "by"]),
    _tool("pay_compression", "Compare pay for recent hires (under 1 year) and experienced staff (5+ years) in one job "
          "code, for example RN100 (Registered Nurse).",
          {"fiscal_year": FY, "job_code": {"type": "string", "default": "RN100"}}, ["fiscal_year"]),
    _tool("metric_definitions", "Definitions of the metrics, so answers can state exactly what was measured."),
    _tool("describe_schema", "List the tables and columns available to run_sql."),
    _tool("run_sql", "Run one read-only SQLite SELECT against the HR database for questions the other tools don't "
          "cover. Names, email and birth year are blocked; use employee_id. Results are capped at 200 rows, so "
          "aggregate in SQL. Dates are ISO strings (YYYY-MM-DD).",
          {"sql": {"type": "string"}}, ["sql"]),
]


def _schema() -> dict:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    tables = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})") if (t, r[1]) not in PII_COLUMNS]
        tables[t] = cols
    con.close()
    return {"tables": tables, "notes": [
        "employees holds each person's latest job; job_history is effective-dated (end_date null = current).",
        "pay_rate is hourly for Hourly jobs and annual for Salary jobs (see jobs.pay_basis).",
        "Fiscal year runs Oct-Sep. Data covers 2023-10-01 to 2026-09-30.",
        "Restricted PII columns are hidden: first_name, last_name, email, birth_year."]}


def _dispatch(name: str, args: dict):
    m = metrics()
    fy, group, by = args.get("fiscal_year"), args.get("group", "all"), args.get("by")
    if fy is not None and fy not in FISCAL_YEARS:
        raise GuardrailError(f"fiscal_year must be one of {list(FISCAL_YEARS)}.")
    if group not in GROUPS:
        raise GuardrailError(f"group must be one of {list(GROUPS)}.")
    table = {
        "enterprise_summary": lambda: m.enterprise_summary(fy, group),
        "retention_summary": lambda: m.retention_summary(fy, group),
        "turnover_breakdown": lambda: m.turnover_by(fy, by, group),
        "monthly_turnover": lambda: m.monthly_turnover(args.get("job_family"), group),
        "recruiting_summary": lambda: m.recruiting_summary(fy, group),
        "recruiting_breakdown": lambda: m.recruiting_by(fy, by, group),
        "recruiting_funnel": lambda: m.recruiting_funnel(fy, group),
        "payroll_summary": lambda: m.payroll_summary(fy, group),
        "payroll_breakdown": lambda: m.payroll_by(fy, by, group),
        "service_summary": lambda: m.service_summary(fy, group),
        "service_breakdown": lambda: m.service_by(fy, by, group),
        "compensation_summary": lambda: m.compensation_summary(fy, group),
        "compensation_breakdown": lambda: m.compensation_by(fy, by, group),
        "pay_compression": lambda: m.pay_compression(fy, args.get("job_code", "RN100")),
        "metric_definitions": lambda: DEFINITIONS,
        "describe_schema": _schema,
        "run_sql": lambda: run_readonly_sql(args["sql"]),
    }
    if name not in table:
        raise GuardrailError(f"Unknown tool: {name}")
    return table[name]()


def dispatch_tool(name: str, args: dict) -> tuple[str, bool]:
    """Execute a tool call. Returns (JSON result, is_error). Every call is audited."""
    t0 = time.perf_counter()
    try:
        result = _dispatch(name, args or {})
        payload, ok, detail = json.dumps(result, default=str), True, ""
    except GuardrailError as exc:
        payload, ok, detail = json.dumps({"error": str(exc)}), False, str(exc)
    except Exception as exc:  # never crash the loop; report the failure to the model
        payload, ok, detail = json.dumps({"error": f"{type(exc).__name__}: {exc}"}), False, repr(exc)
    audit(name, args, ok, (time.perf_counter() - t0) * 1000, detail)
    return payload, not ok
