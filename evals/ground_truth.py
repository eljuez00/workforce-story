"""Independent ground truth for the evals, written in plain SQL.

These deliberately do not import metrics/core.py. If the pandas metric layer and these
queries ever disagree, one of them has a bug, and the offline evals fail.
"""

from __future__ import annotations

import calendar
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "hr.db"


def _q(sql, *params):
    with sqlite3.connect(DB) as con:
        return con.execute(sql, params).fetchone()[0]


def _bounds(fy):
    return f"{fy - 1}-10-01", f"{fy}-09-30"


def _month_ends(fy):
    out = []
    for y, m in [(fy - 1, 10), (fy - 1, 11), (fy - 1, 12)] + [(fy, k) for k in range(1, 10)]:
        out.append(f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}")
    return out


def _clinical_filter(group, alias="j"):
    return {"all": "1=1", "clinical": f"{alias}.is_clinical = 1", "nonclinical": f"{alias}.is_clinical = 0"}[group]


def headcount(on, group="all"):
    return _q(f"""SELECT COUNT(DISTINCT h.employee_id) FROM job_history h JOIN jobs j USING (job_code)
                 WHERE h.start_date <= ? AND (h.end_date IS NULL OR h.end_date >= ?) AND {_clinical_filter(group)}""",
              on, on)


def headcount_end(fy, group="all"):
    return headcount(_bounds(fy)[1], group)


def turnover_rate(fy, group="all", family=None):
    a, b = _bounds(fy)
    fam = "AND j.job_family = ?" if family else ""
    args = (family,) if family else ()
    terms = _q(f"""SELECT COUNT(*) FROM employees e JOIN jobs j USING (job_code)
                  WHERE e.term_date BETWEEN ? AND ? AND {_clinical_filter(group)} {fam}""", a, b, *args)
    hcs = []
    for m in _month_ends(fy):
        hcs.append(_q(f"""SELECT COUNT(DISTINCT h.employee_id) FROM job_history h JOIN jobs j USING (job_code)
                          WHERE h.start_date <= ? AND (h.end_date IS NULL OR h.end_date >= ?)
                          AND {_clinical_filter(group)} {fam}""", m, m, *args))
    return round(terms / (sum(hcs) / len(hcs)) * 100, 1)


def avg_days_to_fill(fy, group="all"):
    a, b = _bounds(fy)
    return round(_q(f"""SELECT AVG(days_to_fill) FROM requisitions r JOIN jobs j USING (job_code)
                       WHERE status = 'Filled' AND close_date BETWEEN ? AND ? AND {_clinical_filter(group)}""", a, b), 1)


def offer_acceptance(fy, group="all"):
    a, b = _bounds(fy)
    acc = _q(f"""SELECT SUM(offers_accepted) FROM requisitions r JOIN jobs j USING (job_code)
                WHERE status='Filled' AND close_date BETWEEN ? AND ? AND {_clinical_filter(group)}""", a, b)
    off = _q(f"""SELECT SUM(offers) FROM requisitions r JOIN jobs j USING (job_code)
                WHERE status IN ('Filled','Cancelled') AND close_date BETWEEN ? AND ? AND {_clinical_filter(group)}""", a, b)
    return round(acc / off * 100, 1)


def overtime_rate(fy, group="all"):
    a, b = _bounds(fy)
    return round(_q(f"""SELECT SUM(overtime_hours) * 100.0 / SUM(regular_hours) FROM payroll p JOIN jobs j USING (job_code)
                       WHERE j.flsa = 'Nonexempt' AND check_date BETWEEN ? AND ? AND {_clinical_filter(group)}""", a, b), 2)


def gross_pay(fy):
    a, b = _bounds(fy)
    return round(_q("SELECT SUM(gross_pay) FROM payroll WHERE check_date BETWEEN ? AND ?", a, b), 0)


def cases_opened(fy):
    a, b = _bounds(fy)
    return _q("SELECT COUNT(*) FROM hr_cases WHERE opened_at >= ? AND opened_at < ?", a, f"{fy}-10-01")


def sla_met(fy):
    a, b = _bounds(fy)
    return round(_q("""SELECT AVG(met_sla) * 100 FROM hr_cases WHERE closed_at IS NOT NULL
                       AND opened_at >= ? AND opened_at < ?""", a, f"{fy}-10-01"), 1)


def ai_triage_share(fy):
    a, _ = _bounds(fy)
    return round(_q("""SELECT AVG(triage_method = 'AI-assisted') * 100 FROM hr_cases
                       WHERE opened_at >= ? AND opened_at < ?""", a, f"{fy}-10-01"), 1)


def market_adjustments():
    return _q("SELECT COUNT(*) FROM transactions WHERE txn_type = 'Market adjustment'")
