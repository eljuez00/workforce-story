"""HR metric definitions, shared by the dashboard build and the agent's tools.

One implementation means the dashboard and the agent can never disagree about a number.
Every function takes a fiscal year (2024-2026; FY runs Oct-Sep) and a workforce group
("all", "clinical" or "nonclinical"), and returns plain JSON-serializable values.
"""

from __future__ import annotations

import sqlite3
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "hr.db"
FISCAL_YEARS = (2024, 2025, 2026)
GROUPS = ("all", "clinical", "nonclinical")

DEFINITIONS = {
    "headcount": "Employees active on a date (hired on or before it, not terminated before it).",
    "turnover_rate": "Terminations in the fiscal year divided by average month-end headcount.",
    "voluntary_turnover_rate": "Voluntary terminations divided by average month-end headcount.",
    "early_turnover_share": "Share of terminations with less than one year of tenure.",
    "days_to_fill": "Days from requisition open date to offer acceptance, for filled requisitions.",
    "offer_acceptance_rate": "Accepted offers divided by offers extended on requisitions closed in the year.",
    "vacancy_rate": "Open requisitions divided by headcount plus open requisitions at fiscal year end.",
    "overtime_rate": "Overtime hours divided by regular hours (nonexempt employees).",
    "premium_pay_share": "Overtime, shift differential and other pay as a share of gross pay.",
    "sla_met_rate": "Closed HR cases resolved within their priority's SLA target.",
    "first_contact_resolution": "Tier 1 cases resolved on first contact.",
    "compa_ratio": "Current pay divided by the midpoint of the job's pay range.",
}


def fy_bounds(fy: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    return pd.Timestamp(fy - 1, 10, 1), pd.Timestamp(fy, 9, 30)


def month_ends(fy: int) -> list[pd.Timestamp]:
    a, b = fy_bounds(fy)
    return list(pd.date_range(a, b, freq="ME"))


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame rows as dicts, with NaN converted to None (JSON null)."""
    return [{k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in row.items()}
            for row in df.to_dict("records")]


def _r(x, n=1):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), n)


class HRMetrics:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"{self.db_path} not found. Run: python -m generator.generate")

    # ------------------------------------------------------------ data access
    def _read(self, sql: str) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as con:
            return pd.read_sql_query(sql, con)

    @cached_property
    def jobs(self):
        return self._read("SELECT * FROM jobs")

    @cached_property
    def depts(self):
        return self._read("SELECT * FROM departments")

    @cached_property
    def employees(self):
        df = self._read("SELECT employee_id, gender, birth_year, hire_date, term_date, term_type, term_reason, "
                        "job_code, dept_id, source_of_hire, performance_rating FROM employees")
        for c in ("hire_date", "term_date"):
            df[c] = pd.to_datetime(df[c])
        return df.merge(self.jobs[["job_code", "job_family", "is_clinical"]], on="job_code")

    @cached_property
    def history(self):
        df = self._read("SELECT * FROM job_history")
        df["start_date"] = pd.to_datetime(df["start_date"])
        df["end_date"] = pd.to_datetime(df["end_date"]).fillna(pd.Timestamp("2099-12-31"))
        return df.merge(self.jobs[["job_code", "job_title", "job_family", "is_clinical", "grade", "pay_basis",
                                   "range_min", "range_mid", "range_max"]], on="job_code") \
                 .merge(self.depts[["dept_id", "dept_name", "division"]], on="dept_id")

    @cached_property
    def reqs(self):
        df = self._read("SELECT * FROM requisitions")
        for c in ("open_date", "close_date", "hire_date"):
            df[c] = pd.to_datetime(df[c])
        return df.merge(self.jobs[["job_code", "job_title", "job_family", "is_clinical"]], on="job_code") \
                 .merge(self.depts[["dept_id", "dept_name"]], on="dept_id")

    @cached_property
    def payroll(self):
        df = self._read("SELECT * FROM payroll")
        df["period_end"] = pd.to_datetime(df["period_end"])
        df["check_date"] = pd.to_datetime(df["check_date"])
        return df.merge(self.jobs[["job_code", "job_family", "is_clinical", "flsa"]], on="job_code") \
                 .merge(self.depts[["dept_id", "dept_name"]], on="dept_id")

    @cached_property
    def corrections(self):
        df = self._read("SELECT * FROM payroll_corrections")
        df["period_end"] = pd.to_datetime(df["period_end"])
        return df

    @cached_property
    def cases(self):
        df = self._read("SELECT * FROM hr_cases")
        df["opened_at"] = pd.to_datetime(df["opened_at"])
        df = df.merge(self.history_latest[["employee_id", "is_clinical"]], on="employee_id", how="left")
        return df

    @cached_property
    def history_latest(self):
        h = self.history.sort_values("start_date")
        return h.groupby("employee_id").tail(1)

    @cached_property
    def txns(self):
        df = self._read("SELECT * FROM transactions")
        df["effective_date"] = pd.to_datetime(df["effective_date"])
        return df

    # ------------------------------------------------------------ filters
    @staticmethod
    def _group(df: pd.DataFrame, group: str) -> pd.DataFrame:
        if group == "clinical":
            return df[df["is_clinical"] == 1]
        if group == "nonclinical":
            return df[df["is_clinical"] == 0]
        return df

    def snapshot(self, on: pd.Timestamp, group: str = "all") -> pd.DataFrame:
        """Job assignment of every employee active on a date (effective-dated)."""
        h = self.history
        h = h[(h["start_date"] <= on) & (h["end_date"] >= on)]
        return self._group(h, group)

    def headcount(self, on: pd.Timestamp, group: str = "all") -> int:
        return int(self.snapshot(on, group)["employee_id"].nunique())

    def terminations(self, fy: int, group: str = "all") -> pd.DataFrame:
        a, b = fy_bounds(fy)
        e = self.employees
        t = e[(e["term_date"] >= a) & (e["term_date"] <= b)].copy()
        t["tenure_years"] = (t["term_date"] - t["hire_date"]).dt.days / 365.25
        return self._group(t, group)

    def hires(self, fy: int, group: str = "all") -> pd.DataFrame:
        a, b = fy_bounds(fy)
        e = self.employees
        first_job = self.history.sort_values("start_date").groupby("employee_id").head(1)[["employee_id", "is_clinical", "job_family"]]
        h = e[(e["hire_date"] >= a) & (e["hire_date"] <= b)].drop(columns=["is_clinical", "job_family"]) \
            .merge(first_job, on="employee_id")
        return self._group(h, group)

    def avg_headcount(self, fy: int, group: str = "all") -> float:
        return float(np.mean([self.headcount(m, group) for m in month_ends(fy)]))

    # ------------------------------------------------------------ enterprise
    def enterprise_summary(self, fy: int, group: str = "all") -> dict:
        a, b = fy_bounds(fy)
        terms = self.terminations(fy, group)
        avg = self.avg_headcount(fy, group)
        pay = self._group(self.payroll[(self.payroll["check_date"] >= a) & (self.payroll["check_date"] <= b)], group)
        snap = self.snapshot(b, group)
        fte = float(snap["fte"].sum())
        return {
            "fiscal_year": fy, "group": group,
            "headcount_start": self.headcount(a, group),
            "headcount_end": self.headcount(b, group),
            "average_headcount": _r(avg),
            "fte_end": _r(fte),
            "hires": int(len(self.hires(fy, group))),
            "terminations": int(len(terms)),
            "turnover_rate_pct": _r(len(terms) / avg * 100),
            "voluntary_turnover_rate_pct": _r((terms["term_type"] == "Voluntary").sum() / avg * 100),
            "gross_payroll_usd": _r(pay["gross_pay"].sum(), 0),
            "labor_cost_per_fte_usd": _r(pay["gross_pay"].sum() / fte, 0) if fte else None,
        }

    def headcount_trend(self, group: str = "all") -> list[dict]:
        rows = []
        for fy in FISCAL_YEARS:
            for m in month_ends(fy):
                a = m.replace(day=1)
                e = self.employees
                hires = self._group(e[(e["hire_date"] >= a) & (e["hire_date"] <= m)], group)
                terms = self._group(e[(e["term_date"] >= a) & (e["term_date"] <= m)], group)
                rows.append({"month": m.strftime("%Y-%m"), "fiscal_year": fy,
                             "headcount": self.headcount(m, group), "hires": int(len(hires)),
                             "terminations": int(len(terms)),
                             "voluntary": int((terms["term_type"] == "Voluntary").sum())})
        return rows

    # ------------------------------------------------------------ retention
    def turnover_by(self, fy: int, by: str = "job_family", group: str = "all") -> list[dict]:
        """Turnover rate by a dimension: job_family, dept_name, division, tenure_band, term_reason."""
        terms = self.terminations(fy, group).copy()
        if by == "term_reason":
            out = terms.groupby(["term_type", "term_reason"]).size().reset_index(name="terminations") \
                       .sort_values("terminations", ascending=False)
            out["share_pct"] = (out["terminations"] / out["terminations"].sum() * 100).round(1)
            return _records(out)
        if by == "tenure_band":
            bins = [0, 0.25, 1, 3, 5, 10, 100]
            labels = ["Under 90 days", "90 days-1 year", "1-3 years", "3-5 years", "5-10 years", "10+ years"]
            terms["tenure_band"] = pd.cut(terms["tenure_years"], bins, labels=labels, right=False)
            out = terms.groupby("tenure_band", observed=False).size().reset_index(name="terminations")
            out["tenure_band"] = out["tenure_band"].astype(str)
            out["share_pct"] = (out["terminations"] / max(1, out["terminations"].sum()) * 100).round(1)
            return _records(out)
        # rate dimensions need average headcount per member
        hist = self.history
        key = by
        if by in ("dept_name", "division"):
            terms = terms.merge(self.depts[["dept_id", "dept_name", "division"]], on="dept_id")
        hc = []
        for m in month_ends(fy):
            s = self._group(hist[(hist["start_date"] <= m) & (hist["end_date"] >= m)], group)
            hc.append(s.groupby(key)["employee_id"].nunique())
        avg = pd.concat(hc, axis=1).fillna(0).mean(axis=1)
        tc = terms.groupby(key).size()
        vol = terms[terms["term_type"] == "Voluntary"].groupby(key).size()
        out = pd.DataFrame({"average_headcount": avg, "terminations": tc, "voluntary": vol}).fillna(0)
        out = out[out["average_headcount"] >= 5]
        out["turnover_rate_pct"] = (out["terminations"] / out["average_headcount"] * 100).round(1)
        out["voluntary_rate_pct"] = (out["voluntary"] / out["average_headcount"] * 100).round(1)
        out["average_headcount"] = out["average_headcount"].round(1)
        out = out.reset_index(names=key).sort_values("turnover_rate_pct", ascending=False)
        for c in ("terminations", "voluntary"):
            out[c] = out[c].astype(int)
        return _records(out)

    def retention_summary(self, fy: int, group: str = "all") -> dict:
        terms = self.terminations(fy, group)
        avg = self.avg_headcount(fy, group)
        a, _ = fy_bounds(fy)
        start = self.snapshot(a, group)["employee_id"].unique()
        retained = 1 - terms["employee_id"].isin(start).sum() / max(1, len(start))
        return {
            "fiscal_year": fy, "group": group,
            "turnover_rate_pct": _r(len(terms) / avg * 100),
            "voluntary_turnover_rate_pct": _r((terms["term_type"] == "Voluntary").sum() / avg * 100),
            "involuntary_turnover_rate_pct": _r((terms["term_type"] == "Involuntary").sum() / avg * 100),
            "early_turnover_share_pct": _r((terms["tenure_years"] < 1).mean() * 100),
            "under_90_days_share_pct": _r((terms["tenure_years"] < 0.25).mean() * 100),
            "retention_rate_pct": _r(retained * 100),
            "top_voluntary_reason": terms[terms["term_type"] == "Voluntary"]["term_reason"].value_counts().idxmax()
            if len(terms) else None,
        }

    def monthly_turnover(self, job_family: str | None = None, group: str = "all") -> list[dict]:
        """Annualized monthly turnover rate, optionally for one job family."""
        rows = []
        hist, e = self.history, self.employees
        for fy in FISCAL_YEARS:
            for m in month_ends(fy):
                a = m.replace(day=1)
                s = self._group(hist[(hist["start_date"] <= m) & (hist["end_date"] >= m)], group)
                t = self._group(e[(e["term_date"] >= a) & (e["term_date"] <= m)], group)
                if job_family:
                    s, t = s[s["job_family"] == job_family], t[t["job_family"] == job_family]
                hc = s["employee_id"].nunique()
                rows.append({"month": m.strftime("%Y-%m"), "headcount": int(hc), "terminations": int(len(t)),
                             "annualized_turnover_pct": _r(len(t) / hc * 1200) if hc else None})
        return rows

    # ------------------------------------------------------------ talent acquisition
    def recruiting_summary(self, fy: int, group: str = "all") -> dict:
        a, b = fy_bounds(fy)
        r = self._group(self.reqs, group)
        closed = r[(r["close_date"] >= a) & (r["close_date"] <= b)]
        filled = closed[closed["status"] == "Filled"]
        opened = r[(r["open_date"] >= a) & (r["open_date"] <= b)]
        open_end = r[(r["open_date"] <= b) & ((r["hire_date"].isna() & (r["status"] == "Open")) | (r["hire_date"] > b))
                     & ~((r["status"] == "Cancelled") & (r["close_date"] <= b))]
        hc = self.headcount(b, group)
        offers = filled["offers"].sum() + closed[closed["status"] == "Cancelled"]["offers"].sum()
        return {
            "fiscal_year": fy, "group": group,
            "requisitions_opened": int(len(opened)),
            "requisitions_filled": int(len(filled)),
            "growth_requisitions_opened": int((opened["req_type"] == "Growth").sum()),
            "avg_days_to_fill": _r(filled["days_to_fill"].mean()),
            "median_days_to_fill": _r(filled["days_to_fill"].median()),
            "open_requisitions_at_year_end": int(len(open_end)),
            "vacancy_rate_pct": _r(len(open_end) / (hc + len(open_end)) * 100),
            "offer_acceptance_rate_pct": _r(filled["offers_accepted"].sum() / offers * 100) if offers else None,
            "applicants_per_filled_req": _r(filled["applicants"].mean()),
        }

    def recruiting_by(self, fy: int, by: str = "job_family", group: str = "all") -> list[dict]:
        a, b = fy_bounds(fy)
        r = self._group(self.reqs, group)
        f = r[(r["close_date"] >= a) & (r["close_date"] <= b) & (r["status"] == "Filled")]
        if by == "source_of_hire":
            out = f.groupby(by).size().reset_index(name="hires").sort_values("hires", ascending=False)
            out["share_pct"] = (out["hires"] / out["hires"].sum() * 100).round(1)
            return _records(out)
        out = f.groupby(by).agg(filled=("req_id", "count"), avg_days_to_fill=("days_to_fill", "mean"),
                                offers=("offers", "sum"), accepted=("offers_accepted", "sum"),
                                applicants=("applicants", "mean")).reset_index()
        out["offer_acceptance_rate_pct"] = (out["accepted"] / out["offers"] * 100).round(1)
        out["avg_days_to_fill"] = out["avg_days_to_fill"].round(1)
        out["applicants"] = out["applicants"].round(1)
        out = out[out["filled"] >= 5].sort_values("avg_days_to_fill", ascending=False)
        return _records(out.rename(columns={"applicants": "avg_applicants"}))

    def recruiting_funnel(self, fy: int, group: str = "all") -> list[dict]:
        a, b = fy_bounds(fy)
        r = self._group(self.reqs, group)
        f = r[(r["close_date"] >= a) & (r["close_date"] <= b) & (r["status"] == "Filled")]
        stages = [("Applied", "applicants"), ("Screened", "screened"), ("Interviewed", "interviewed"),
                  ("Offered", "offers"), ("Hired", "offers_accepted")]
        top = f["applicants"].sum()
        return [{"stage": s, "count": int(f[c].sum()), "pct_of_applied": _r(f[c].sum() / top * 100)} for s, c in stages]

    def monthly_days_to_fill(self, job_family: str | None = None, group: str = "all") -> list[dict]:
        r = self._group(self.reqs, group)
        r = r[r["status"] == "Filled"]
        if job_family:
            r = r[r["job_family"] == job_family]
        g = r.groupby(r["close_date"].dt.to_period("M")).agg(filled=("req_id", "count"),
                                                             avg_days_to_fill=("days_to_fill", "mean"))
        g = g[(g.index >= pd.Period("2023-10", "M")) & (g.index <= pd.Period("2026-09", "M"))]
        return [{"month": str(p), "filled": int(v.filled), "avg_days_to_fill": _r(v.avg_days_to_fill)} for p, v in g.iterrows()]

    # ------------------------------------------------------------ payroll
    def payroll_summary(self, fy: int, group: str = "all") -> dict:
        a, b = fy_bounds(fy)
        p = self._group(self.payroll[(self.payroll["check_date"] >= a) & (self.payroll["check_date"] <= b)], group)
        ne = p[p["flsa"] == "Nonexempt"]
        c = self.corrections
        c = c.merge(p[["period_end", "employee_id"]].drop_duplicates(), on=["period_end", "employee_id"])
        gross = p["gross_pay"].sum()
        return {
            "fiscal_year": fy, "group": group,
            "pay_periods": int(p["period_end"].nunique()),
            "checks_issued": int(len(p)),
            "gross_pay_usd": _r(gross, 0),
            "overtime_pay_usd": _r(p["overtime_pay"].sum(), 0),
            "overtime_rate_pct": _r(ne["overtime_hours"].sum() / ne["regular_hours"].sum() * 100, 2),
            "shift_differential_usd": _r(p["shift_diff_pay"].sum(), 0),
            "other_pay_usd": _r(p["other_pay"].sum(), 0),
            "premium_pay_share_pct": _r((p["overtime_pay"] + p["shift_diff_pay"] + p["other_pay"]).sum() / gross * 100, 2),
            "off_cycle_corrections": int(len(c)),
            "corrections_per_1000_checks": _r(len(c) / len(p) * 1000, 2) if len(p) else None,
        }

    def payroll_by(self, fy: int, by: str = "dept_name", group: str = "all") -> list[dict]:
        a, b = fy_bounds(fy)
        p = self._group(self.payroll[(self.payroll["check_date"] >= a) & (self.payroll["check_date"] <= b)], group)
        g = p.groupby(by).agg(gross_pay_usd=("gross_pay", "sum"), overtime_pay_usd=("overtime_pay", "sum"),
                              overtime_hours=("overtime_hours", "sum"), regular_hours=("regular_hours", "sum"))
        ne = p[p["flsa"] == "Nonexempt"].groupby(by).agg(oh=("overtime_hours", "sum"), rh=("regular_hours", "sum"))
        g = g.join(ne)
        g["overtime_rate_pct"] = (g["oh"] / g["rh"] * 100).round(2)
        g = g.drop(columns=["oh", "rh", "overtime_hours", "regular_hours"]).reset_index()
        g[["gross_pay_usd", "overtime_pay_usd"]] = g[["gross_pay_usd", "overtime_pay_usd"]].round(0)
        g = g.sort_values("overtime_pay_usd", ascending=False)
        return _records(g)

    def payroll_by_period(self, group: str = "all") -> list[dict]:
        p = self._group(self.payroll, group)
        ne = p[p["flsa"] == "Nonexempt"]
        g = p.groupby("check_date").agg(gross=("gross_pay", "sum"), ot=("overtime_pay", "sum"),
                                        checks=("employee_id", "count"))
        r = ne.groupby("check_date").agg(oh=("overtime_hours", "sum"), rh=("regular_hours", "sum"))
        c = self.corrections.merge(p[["period_end", "employee_id", "check_date"]], on=["period_end", "employee_id"]) \
                .groupby("check_date").size()
        g = g.join(r).join(c.rename("corrections")).fillna(0)
        return [{"check_date": d.strftime("%Y-%m-%d"), "gross_pay_usd": _r(v.gross, 0), "overtime_pay_usd": _r(v.ot, 0),
                 "overtime_rate_pct": _r(v.oh / v.rh * 100, 2), "corrections": int(v.corrections),
                 "corrections_per_1000_checks": _r(v.corrections / v.checks * 1000, 2)} for d, v in g.iterrows()]

    # ------------------------------------------------------------ HR services
    def _cases_fy(self, fy, group):
        a, b = fy_bounds(fy)
        c = self.cases
        return self._group(c[(c["opened_at"] >= a) & (c["opened_at"] < b + pd.Timedelta(days=1))], group)

    def service_summary(self, fy: int, group: str = "all") -> dict:
        c = self._cases_fy(fy, group)
        closed = c[c["closed_at"].notna()]
        t1 = c[c["tier"] == 1]
        hc = self.avg_headcount(fy, group)
        return {
            "fiscal_year": fy, "group": group,
            "cases_opened": int(len(c)),
            "cases_per_100_employees": _r(len(c) / hc * 100),
            "sla_met_rate_pct": _r(closed["met_sla"].mean() * 100),
            "median_resolution_hours": _r(closed["resolution_hours"].median()),
            "first_contact_resolution_pct": _r(t1["first_contact_resolution"].mean() * 100),
            "avg_csat": _r(c["csat"].mean(), 2),
            "csat_responses": int(c["csat"].notna().sum()),
            "ai_assisted_triage_share_pct": _r((c["triage_method"] == "AI-assisted").mean() * 100),
            "median_hours_to_assign": _r(c["hours_to_assign"].median(), 2),
        }

    def service_by(self, fy: int, by: str = "category", group: str = "all") -> list[dict]:
        """HR case metrics by category, subcategory, channel, priority or triage_method."""
        c = self._cases_fy(fy, group)
        g = c.groupby(by).agg(cases=("case_id", "count"), sla_met_rate_pct=("met_sla", "mean"),
                              median_resolution_hours=("resolution_hours", "median"), avg_csat=("csat", "mean"),
                              median_hours_to_assign=("hours_to_assign", "median")).reset_index()
        g["sla_met_rate_pct"] = (g["sla_met_rate_pct"] * 100).round(1)
        g["share_pct"] = (g["cases"] / g["cases"].sum() * 100).round(1)
        return _records(g.round(2).sort_values("cases", ascending=False))

    def monthly_cases(self, group: str = "all") -> list[dict]:
        c = self._group(self.cases, group)
        c = c[c["opened_at"] < pd.Timestamp(2026, 10, 1)]
        m = c["opened_at"].dt.to_period("M")
        g = c.groupby([m, "category"]).size().unstack(fill_value=0)
        sla = c.groupby(m)["met_sla"].mean()
        assign = c.groupby(m)["hours_to_assign"].median()
        out = []
        for p, row in g.iterrows():
            d = {"month": str(p), "total": int(row.sum()), "sla_met_rate_pct": _r(sla[p] * 100),
                 "median_hours_to_assign": _r(assign[p], 2)}
            d.update({k: int(v) for k, v in row.items()})
            out.append(d)
        return out

    # ------------------------------------------------------------ compensation
    def comp_snapshot(self, fy: int, group: str = "all") -> pd.DataFrame:
        _, b = fy_bounds(fy)
        s = self.snapshot(b, group).merge(self.employees[["employee_id", "gender", "hire_date"]], on="employee_id")
        s = s.copy()
        if b < pd.Timestamp(2025, 7, 6):  # nursing ranges moved up 6% with the July 2025 market adjustment
            rn = s["job_code"].isin(["RN100", "RN200"])
            for c in ("range_min", "range_mid", "range_max"):
                s.loc[rn, c] = s.loc[rn, c] / 1.06
        s["compa_ratio"] = s["pay_rate"] / s["range_mid"]
        s["range_penetration"] = (s["pay_rate"] - s["range_min"]) / (s["range_max"] - s["range_min"])
        s["annual_pay"] = np.where(s["pay_basis"] == "Hourly", s["pay_rate"] * 2080, s["pay_rate"])
        return s

    def compensation_summary(self, fy: int, group: str = "all") -> dict:
        a, b = fy_bounds(fy)
        s = self.comp_snapshot(fy, group)
        t = self.txns.merge(self.jobs[["job_code", "is_clinical"]], left_on="to_job", right_on="job_code", how="left")
        yr = self._group(t[(t["effective_date"] >= a) & (t["effective_date"] <= b)], group)
        merit = yr[yr["txn_type"] == "Merit increase"]
        pct = (merit["new_pay"] / merit["old_pay"] - 1) * 100
        within = s.groupby(["job_code", "gender"])["annual_pay"].mean().unstack()
        within = within.dropna()
        weights = s.groupby("job_code").size().reindex(within.index)
        ratio = float((within["F"] / within["M"] * weights).sum() / weights.sum()) if len(within) else None
        return {
            "fiscal_year": fy, "group": group,
            "employees": int(len(s)),
            "avg_compa_ratio": _r(s["compa_ratio"].mean(), 3),
            "below_range_midpoint_pct": _r((s["compa_ratio"] < 1).mean() * 100),
            "merit_increases": int(len(merit)),
            "avg_merit_increase_pct": _r(pct.mean(), 2) if len(merit) else None,
            "promotions": int((yr["txn_type"] == "Promotion").sum()),
            "market_adjustments": int((yr["txn_type"] == "Market adjustment").sum()),
            "gender_pay_ratio_within_job": _r(ratio, 3),
        }

    def compensation_by(self, fy: int, by: str = "job_family", group: str = "all") -> list[dict]:
        s = self.comp_snapshot(fy, group)
        g = s.groupby(by).agg(employees=("employee_id", "count"), avg_compa_ratio=("compa_ratio", "mean"),
                              avg_range_penetration=("range_penetration", "mean"),
                              avg_annual_pay=("annual_pay", "mean")).reset_index()
        g = g[g["employees"] >= 5]
        g["avg_compa_ratio"] = g["avg_compa_ratio"].round(3)
        g["avg_range_penetration"] = (g["avg_range_penetration"] * 100).round(1)
        g["avg_annual_pay"] = g["avg_annual_pay"].round(0)
        return _records(g.sort_values("avg_compa_ratio")
                        .rename(columns={"avg_range_penetration": "avg_range_penetration_pct"}))

    def pay_compression(self, fy: int, job_code: str = "RN100") -> dict:
        """Compare recent hires (under 1 year) with experienced staff (5+ years) in one job."""
        _, b = fy_bounds(fy)
        s = self.comp_snapshot(fy)
        s = s[s["job_code"] == job_code]
        tenure = (b - s["hire_date"]).dt.days / 365.25
        new, exp = s[tenure < 1], s[tenure >= 5]
        gap = (exp["pay_rate"].mean() / new["pay_rate"].mean() - 1) * 100 if len(new) and len(exp) else None
        return {"fiscal_year": fy, "job_code": job_code, "job_title": s["job_title"].iloc[0] if len(s) else None,
                "new_hires_under_1yr": int(len(new)), "avg_rate_new": _r(new["pay_rate"].mean(), 2),
                "experienced_5yr_plus": int(len(exp)), "avg_rate_experienced": _r(exp["pay_rate"].mean(), 2),
                "experience_premium_pct": _r(gap)}

    def compa_distribution(self, fy: int, group: str = "all") -> list[dict]:
        s = self.comp_snapshot(fy, group)
        bins = [0, .85, .90, .95, 1.0, 1.05, 1.10, 1.15, 9]
        labels = ["Under 0.85", "0.85-0.90", "0.90-0.95", "0.95-1.00", "1.00-1.05", "1.05-1.10", "1.10-1.15", "1.15+"]
        cut = pd.cut(s["compa_ratio"], bins, labels=labels, right=False)
        out = cut.value_counts().reindex(labels).fillna(0)
        return [{"band": k, "employees": int(v)} for k, v in out.items()]
