"""Build app/data/metrics.json for the web app from the shared metric definitions.

Usage:  python -m metrics.build
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from generator.catalog import COMPANY
from metrics.core import DEFINITIONS, FISCAL_YEARS, GROUPS, HRMetrics

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "metrics.json"
PEOPLE = {"all": "employees", "clinical": "clinical staff", "nonclinical": "non-clinical staff"}
GROUP_LABEL = {"all": "the system", "clinical": "clinical staff", "nonclinical": "non-clinical staff"}


def pct_change(new, old):
    return None if not old else round((new - old) / old * 100, 1)


def money(x):
    return f"${x / 1e6:,.1f} million" if x >= 1e6 else f"${x:,.0f}"


def narratives(s: dict, prev: dict | None, fy: int, group: str) -> dict:
    """Plain-language headlines written from the numbers, so the story updates with the data."""
    e, r, t, p, v, c = (s["enterprise"], s["retention"], s["recruiting"], s["payroll"], s["service"], s["compensation"])
    who = GROUP_LABEL[group]
    out = {}

    d_hc = e["headcount_end"] - e["headcount_start"]
    out["enterprise"] = {
        "headline": f"{e['headcount_end']:,} people on the payroll, {e['hires']:,} hired and {e['terminations']:,} gone in FY{fy % 100}.",
        "body": (f"Headcount for {who} {'grew' if d_hc > 0 else 'shrank' if d_hc < 0 else 'held flat'} by {abs(d_hc):,} "
                 f"over the year. Replacing roughly one in five people every year is the defining fact of this "
                 f"workforce: turnover was {e['turnover_rate_pct']}%, and gross payroll reached {money(e['gross_payroll_usd'])}."),
    }

    nurse_peak = s.get("nursing_peak")
    body = (f"Voluntary turnover was {r['voluntary_turnover_rate_pct']}%. {r['early_turnover_share_pct']}% of everyone who "
            f"left had been here less than a year, so the first twelve months are where retention is won or lost. "
            f"The most common reason for leaving was “{r['top_voluntary_reason'].lower()}.”")
    if nurse_peak:
        body += (f" Nursing turnover peaked at an annualized {nurse_peak['annualized_turnover_pct']}% in "
                 f"{datetime.strptime(nurse_peak['month'], '%Y-%m').strftime('%B %Y')}.")
    out["retention"] = {"headline": f"Turnover ran at {r['turnover_rate_pct']}%"
                        + (f", {'up' if r['turnover_rate_pct'] > prev['retention']['turnover_rate_pct'] else 'down'} from "
                           f"{prev['retention']['turnover_rate_pct']}% the year before." if prev else "."),
                        "body": body}

    out["talent"] = {
        "headline": f"It took {t['avg_days_to_fill']} days on average to fill a role.",
        "body": (f"Recruiters filled {t['requisitions_filled']:,} requisitions and closed the year with "
                 f"{t['open_requisitions_at_year_end']:,} still open, a {t['vacancy_rate_pct']}% vacancy rate. "
                 f"{t['offer_acceptance_rate_pct']}% of offers were accepted"
                 + (f", compared with {prev['recruiting']['offer_acceptance_rate_pct']}% in FY{(fy - 1) % 100}." if prev else ".")),
    }

    out["payroll"] = {
        "headline": f"Overtime was {p['overtime_rate_pct']}% of regular hours, costing {money(p['overtime_pay_usd'])}.",
        "body": (f"Every open position becomes someone else's extra shift. Across {p['pay_periods']} pay periods and "
                 f"{p['checks_issued']:,} checks, premium pay (overtime, shift differentials and bonuses) made up "
                 f"{p['premium_pay_share_pct']}% of gross pay. Payroll issued {p['off_cycle_corrections']:,} off-cycle "
                 f"corrections, {p['corrections_per_1000_checks']} per thousand checks."),
    }

    out["services"] = {
        "headline": f"The HR service center handled {v['cases_opened']:,} cases and met SLA on {v['sla_met_rate_pct']}%.",
        "body": (f"That is {v['cases_per_100_employees']} cases for every 100 employees. The median case was resolved in "
                 f"{v['median_resolution_hours']} hours, {v['first_contact_resolution_pct']}% of tier 1 cases were "
                 f"resolved on first contact, and satisfaction averaged {v['avg_csat']} out of 5."
                 + (f" {v['ai_assisted_triage_share_pct']}% of cases were triaged with AI assistance, and the median time "
                    f"to route a case to the right team was {round(v['median_hours_to_assign'] * 60)} minutes."
                    if v["ai_assisted_triage_share_pct"] else
                    f" Every case was triaged by hand, and the median time to route a case was "
                    f"{v['median_hours_to_assign']} hours.")),
    }

    comp_body = (f"{c['below_range_midpoint_pct']}% of {PEOPLE[group]} are paid below their range midpoint. "
                 f"Within the same job, women earn {round(c['gender_pay_ratio_within_job'] * 100, 1)} cents for every dollar men earn.")
    if c["merit_increases"]:
        comp_body = f"The merit cycle averaged {c['avg_merit_increase_pct']}% across {c['merit_increases']:,} increases. " + comp_body
    if c["market_adjustments"]:
        comp_body += f" {c['market_adjustments']:,} nurses received a 6% market adjustment in July 2025."
    out["compensation"] = {"headline": f"The average employee is paid at {c['avg_compa_ratio']} of their range midpoint.",
                           "body": comp_body}
    return out


def build(m: HRMetrics | None = None) -> dict:
    m = m or HRMetrics()
    slices = {}
    for group in GROUPS:
        nursing = m.monthly_turnover("Nursing", group) if group != "nonclinical" else []
        prev = None
        for fy in FISCAL_YEARS:
            s = {
                "enterprise": m.enterprise_summary(fy, group),
                "retention": m.retention_summary(fy, group),
                "recruiting": m.recruiting_summary(fy, group),
                "payroll": m.payroll_summary(fy, group),
                "service": m.service_summary(fy, group),
                "compensation": m.compensation_summary(fy, group),
                "turnover_by_family": m.turnover_by(fy, "job_family", group),
                "turnover_by_tenure": m.turnover_by(fy, "tenure_band", group),
                "turnover_by_reason": m.turnover_by(fy, "term_reason", group)[:8],
                "recruiting_by_family": m.recruiting_by(fy, "job_family", group),
                "funnel": m.recruiting_funnel(fy, group),
                "sources": m.recruiting_by(fy, "source_of_hire", group),
                "payroll_by_dept": m.payroll_by(fy, "dept_name", group),
                "service_by_category": m.service_by(fy, "category", group),
                "service_by_channel": m.service_by(fy, "channel", group),
                "service_by_triage": m.service_by(fy, "triage_method", group),
                "comp_by_family": m.compensation_by(fy, "job_family", group),
                "compa_distribution": m.compa_distribution(fy, group),
            }
            in_year = [x for x in nursing if x["month"][:4] in (str(fy - 1), str(fy))
                       and (x["month"] >= f"{fy - 1}-10") and (x["month"] <= f"{fy}-09") and x["annualized_turnover_pct"]]
            s["nursing_peak"] = max(in_year, key=lambda x: x["annualized_turnover_pct"]) if in_year else None
            if group == "all":
                s["compression"] = m.pay_compression(fy, "RN100")
            s["story"] = narratives(s, prev, fy, group)
            slices.setdefault(str(fy), {})[group] = s
            prev = s
    series = {group: {
        "headcount": m.headcount_trend(group),
        "turnover_all": m.monthly_turnover(None, group),
        "turnover_nursing": m.monthly_turnover("Nursing", group) if group != "nonclinical" else [],
        "days_to_fill_all": m.monthly_days_to_fill(None, group),
        "days_to_fill_nursing": m.monthly_days_to_fill("Nursing", group) if group != "nonclinical" else [],
        "payroll": m.payroll_by_period(group),
        "cases": m.monthly_cases(group),
    } for group in GROUPS}
    return {
        "meta": {"company": COMPANY, "employees_target": 5000, "turnover_target_pct": 20,
                 "fiscal_years": list(FISCAL_YEARS), "fiscal_year_note": "Fiscal years run October to September.",
                 "as_of": "2026-09-30", "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                 "definitions": DEFINITIONS,
                 "events": [
                     {"date": "2025-01", "label": "Competitor recruits nurses"},
                     {"date": "2025-02", "label": "Payroll system upgrade"},
                     {"date": "2025-07", "label": "Nursing market adjustment"},
                     {"date": "2025-10", "label": "AI triage and new clinic launch"},
                 ]},
        "slices": slices,
        "series": series,
    }


def main():
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":"), default=str, allow_nan=False))
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:,.0f} KB)")


if __name__ == "__main__":
    main()
