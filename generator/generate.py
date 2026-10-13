"""Generate three fiscal years of fictional HR data for Cedar Fork Health.

Usage:  python -m generator.generate            (writes data/hr.db and data/csv/)

The simulation is seeded, so every run produces the same company. Story beats are
planted on purpose so the metrics have something to say:

  * FY25 Q2  - a regional competitor recruits nurses; RN turnover and time to fill spike
  * Jul 2025 - a 6% market adjustment for nurses; RN turnover falls afterwards
  * Feb 2025 - a payroll system upgrade; payroll inquiries and off-cycle corrections spike
  * Oct 2025 - an AI triage assistant and virtual agent launch in the HR service center
  * Oct 2025 - a new ambulatory clinic opens, adding growth hiring
  * Vacancies drive overtime: open requisitions in a job family push its overtime up
"""

from __future__ import annotations

import csv
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from generator import catalog as C

SEED = 20260930
START = date(2023, 10, 1)
END = date(2026, 9, 30)
TARGET_TURNOVER = 0.183  # calibrated so realized turnover lands near 20% after retirements and story beats
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

MARKET_ADJ_DATE = date(2025, 7, 6)
MERIT_DATES = {date(2024, 10, 6): 0.0, date(2025, 10, 5): 0.5}  # extra merit points by cycle
UPGRADE_START, UPGRADE_END = date(2025, 2, 1), date(2025, 3, 31)
SERVICE_LAUNCH = date(2025, 10, 1)
CLINIC_OPEN = date(2025, 10, 1)

rng = np.random.default_rng(SEED)
JOBS = {j[0]: j for j in C.JOBS}
DEPTS = {d[0]: d for d in C.DEPARTMENTS}


# ---------------------------------------------------------------- helpers
def fiscal_year(d: date) -> int:
    return d.year + 1 if d.month >= 10 else d.year


def months():
    y, m = START.year, START.month
    while date(y, m, 1) <= END:
        first = date(y, m, 1)
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        yield first, nxt - timedelta(days=1)
        y, m = nxt.year, nxt.month


def pick(options, weights=None):
    if weights is None:
        return options[rng.integers(len(options))]
    w = np.asarray(weights, dtype=float)
    return options[rng.choice(len(options), p=w / w.sum())]


def pick_weighted(pairs):
    return pick([p[0] for p in pairs], [p[1] for p in pairs])


def rand_day(a: date, b: date) -> date:
    return a + timedelta(days=int(rng.integers(0, (b - a).days + 1)))


DEPT_WEIGHTS = {"D101": .30, "D102": .15, "D103": .17, "D104": .10, "D105": .13, "D106": .07, "D107": .08,
                "D301": .60, "D302": .40, "D303": .45}


def pick_dept(job_code: str) -> str:
    depts = JOBS[job_code][11]
    return pick(depts, [DEPT_WEIGHTS.get(d, 0.2) for d in depts])


def pick_location(dept_id: str) -> str:
    rule = DEPTS[dept_id][4]
    if rule == "flagship":
        return "LOC01"
    if rule == "clinics":
        return "LOC04"
    if rule == "corporate":
        return "LOC05"
    if rule == "any":
        return pick(["LOC01", "LOC02", "LOC03", "LOC04"], [.45, .2, .15, .2])
    return pick(["LOC01", "LOC02", "LOC03"], [.55, .25, .20])


def pick_fte(job_code: str) -> float:
    if JOBS[job_code][2] in ("Nursing", "Patient Care Support"):
        return float(pick([1.0, 0.9, 0.6, 0.5], [.68, .12, .14, .06]))
    return float(pick([1.0, 0.8, 0.5], [.88, .07, .05]))


def pick_shift(job_code: str, dept_id: str) -> str:
    j = JOBS[job_code]
    if j[6] == "Hourly" and DEPTS[dept_id][4] in ("hospital", "flagship") and j[5] == 1 or job_code in ("EV100", "SC100"):
        return pick_weighted(C.SHIFTS)
    return "Day"


def pay_for_position(job_code: str, position: float, on: date) -> float:
    j = JOBS[job_code]
    lo, hi = j[7], j[8]
    if job_code in ("RN100", "RN200") and on >= MARKET_ADJ_DATE:
        lo, hi = lo * 1.06, hi * 1.06
    rate = lo + max(0.0, min(1.0, position)) * (hi - lo)
    return round(rate, 2) if j[6] == "Hourly" else round(rate / 100) * 100


# ---------------------------------------------------------------- model objects
@dataclass
class Segment:
    start: date
    end: date | None
    job_code: str
    dept_id: str
    location_id: str
    fte: float
    pay_rate: float


@dataclass
class Employee:
    employee_id: str
    first_name: str
    last_name: str
    gender: str
    birth_year: int
    hire_date: date
    source: str
    req_id: str | None
    shift: str
    segments: list = field(default_factory=list)
    term_date: date | None = None
    term_type: str | None = None
    term_reason: str | None = None
    rating: int = 3

    @property
    def seg(self) -> Segment:
        return self.segments[-1]

    def active_on(self, d: date) -> bool:
        return self.hire_date <= d and (self.term_date is None or self.term_date >= d)


employees: list[Employee] = []
transactions: list[dict] = []
requisitions: list[dict] = []
_next_emp = [10001]
_next_req = [50001]


def new_employee(job_code, dept_id, location_id, hire_date, source, req_id, position, age=None) -> Employee:
    family = JOBS[job_code][2]
    gender = "F" if rng.random() < C.FEMALE_SHARE[family] else "M"
    first = pick(C.FIRST_NAMES_F if gender == "F" else C.FIRST_NAMES_M)
    last = pick(C.LAST_NAMES)
    if age is None:
        age = int(np.clip(rng.normal(32 if JOBS[job_code][3] < 12 else 41, 8), 19, 64))
    e = Employee(f"E{_next_emp[0]}", first, last, gender, hire_date.year - age, hire_date, source, req_id,
                 pick_shift(job_code, dept_id))
    _next_emp[0] += 1
    e.segments.append(Segment(hire_date, None, job_code, dept_id, location_id, pick_fte(job_code),
                              pay_for_position(job_code, position, hire_date)))
    e.rating = int(pick([1, 2, 3, 4, 5], [.03, .10, .55, .25, .07]))
    employees.append(e)
    if hire_date >= START:
        transactions.append(dict(employee_id=e.employee_id, effective_date=hire_date, txn_type="Hire",
                                 from_job=None, to_job=job_code, from_dept=None, to_dept=dept_id,
                                 old_pay=None, new_pay=e.seg.pay_rate, reason=source))
    return e


def change(e: Employee, eff: date, txn_type: str, reason: str, job_code=None, dept_id=None, pay=None):
    s = e.seg
    eff = max(eff, s.start + timedelta(days=1))  # effective dates must move forward
    s.end = eff - timedelta(days=1)
    job = job_code or s.job_code
    dept = dept_id or s.dept_id
    loc = s.location_id if dept == s.dept_id else pick_location(dept)
    new = Segment(eff, e.term_date if e.term_date and e.term_date >= eff else None, job, dept, loc, s.fte,
                  pay if pay is not None else s.pay_rate)
    e.segments.append(new)
    transactions.append(dict(employee_id=e.employee_id, effective_date=eff, txn_type=txn_type,
                             from_job=s.job_code, to_job=job, from_dept=s.dept_id, to_dept=dept,
                             old_pay=s.pay_rate, new_pay=new.pay_rate, reason=reason))


# ---------------------------------------------------------------- recruiting
def ttf_multiplier(job_code: str, open_date: date) -> float:
    if job_code in ("RN100", "RN200"):
        if date(2024, 12, 1) <= open_date < date(2025, 7, 1):
            return 1.40
        if open_date >= date(2025, 10, 1):
            return 0.85
    return 1.0


def accept_rate(job_code: str, d: date) -> float:
    if job_code in ("RN100", "RN200", "LP100"):
        if date(2024, 12, 1) <= d < date(2025, 7, 1):
            return 0.64
        if d >= date(2025, 7, 1):
            return 0.83
    return 0.80


def open_req(job_code: str, dept_id: str, location_id: str, open_date: date, req_type: str):
    j = JOBS[job_code]
    req_id = f"R{_next_req[0]}"
    _next_req[0] += 1
    mean_days = j[13] * ttf_multiplier(job_code, open_date)
    ttf = max(7, int(round(mean_days * rng.lognormal(-0.1, 0.45))))
    apps_mean = j[12] * (0.75 if job_code in ("RN100", "RN200") and fiscal_year(open_date) == 2025 else 1.0)
    applicants = max(1, int(rng.poisson(apps_mean)))
    screened = max(1, int(rng.binomial(applicants, 0.55)))
    interviewed = max(1, int(rng.binomial(screened, 0.45)))
    cancelled = rng.random() < 0.06
    status, close_date, hire_date, hired = "Open", None, None, None
    offers = accepted = 0
    source = None
    if cancelled:
        close_date = open_date + timedelta(days=int(rng.integers(20, 90)))
        status = "Cancelled" if close_date <= END else "Open"
        if status == "Open":
            close_date = None
        offers = int(rng.binomial(interviewed, 0.1))
    else:
        accept_date = open_date + timedelta(days=ttf)
        p = accept_rate(job_code, accept_date)
        offers = 1 + int(rng.geometric(p) - 1)
        if accept_date <= END:
            status, close_date, accepted = "Filled", accept_date, 1
            hire_date = accept_date + timedelta(days=14)
            interviewed = max(interviewed, offers)
            screened = max(screened, interviewed)
            applicants = max(applicants, screened)
            sources = dict(C.SOURCES)
            if job_code in ("RN100", "RN200") and accept_date >= date(2025, 7, 1):
                sources["Employee referral"] = 0.30
            source = pick_weighted(list(sources.items()))
            nurse_boost = job_code == "RN100" and hire_date >= MARKET_ADJ_DATE
            position = float(np.clip(rng.normal(0.36 if nurse_boost else 0.24, 0.08), 0.0, 0.7))
            e = new_employee(job_code, dept_id, location_id, hire_date, source, req_id, position)
            hired = e.employee_id
        else:
            offers = 0
    requisitions.append(dict(req_id=req_id, job_code=job_code, dept_id=dept_id, location_id=location_id,
                             req_type=req_type, open_date=open_date, close_date=close_date, status=status,
                             applicants=applicants, screened=screened, interviewed=interviewed, offers=offers,
                             offers_accepted=accepted, source_of_hire=source, hired_employee_id=hired,
                             hire_date=hire_date))


# ---------------------------------------------------------------- simulation
def seed_population(n=4925):
    shares = np.array([j[9] for j in C.JOBS])
    shares = shares / shares.sum()
    counts = np.round(shares * n).astype(int)
    counts[0] += n - counts.sum()
    for (job_code, *_), k in zip(C.JOBS, counts):
        for _ in range(k):
            dept = pick_dept(job_code)
            age = int(np.clip(rng.normal(41, 11), 21, 68))
            tenure = float(min(rng.exponential(6.5), age - 20))
            hire = START - timedelta(days=int(tenure * 365.25) + 1)
            position = float(np.clip(0.28 + tenure / 20 * 0.6 + rng.normal(0, 0.10), 0.02, 0.98))
            e = new_employee(job_code, dept, pick_location(dept), hire, pick_weighted(C.SOURCES), None, position,
                             age=age - int(tenure))
            # back-date the pay so it reflects today's position in range
            e.segments[0].pay_rate = pay_for_position(job_code, position, START)
    # vacancies already open on day one
    for _ in range(230):
        job_code = pick([j[0] for j in C.JOBS], shares * np.array([j[10] for j in C.JOBS]))
        dept = pick_dept(job_code)
        open_req(job_code, dept, pick_location(dept), START - timedelta(days=int(rng.integers(1, 75))), "Backfill")


def hazard_multiplier(job_code: str, d: date) -> float:
    if job_code in ("RN100", "RN200"):
        if date(2025, 1, 1) <= d < date(2025, 7, 1):
            return 1.75
        if d >= date(2025, 8, 1):
            return 0.72
    return 1.0


def tenure_multiplier(years: float) -> float:
    if years < 0.25:
        return 2.3
    if years < 1:
        return 1.6
    if years < 3:
        return 1.05
    if years < 10:
        return 0.85
    return 0.6


def simulate():
    seed_population()
    monthly_target = 1 - (1 - TARGET_TURNOVER) ** (1 / 12)
    for m_start, m_end in months():
        active = [e for e in employees if e.hire_date < m_start and e.term_date is None]
        base = np.array([JOBS[e.seg.job_code][10] * tenure_multiplier((m_start - e.hire_date).days / 365.25)
                         for e in active])
        monthly = 1 - (1 - base) ** (1 / 12)
        monthly *= monthly_target * len(active) / monthly.sum()
        ages = np.array([m_start.year - e.birth_year for e in active])
        monthly += np.where(ages >= 62, 0.006, 0.0)
        mult = np.array([hazard_multiplier(e.seg.job_code, m_start) for e in active])
        terms = rng.random(len(active)) < monthly * mult
        for e, t, age in zip(active, terms, ages):
            if not t:
                continue
            e.term_date = rand_day(m_start, m_end)
            tenure = (e.term_date - e.hire_date).days / 365.25
            invol_p = 0.45 if tenure < 0.25 else 0.17
            if rng.random() < invol_p:
                e.term_type = "Involuntary"
                e.term_reason = "Failed introductory period" if tenure < 0.25 and rng.random() < .6 \
                    else pick_weighted(C.INVOLUNTARY_REASONS[:-2] + C.INVOLUNTARY_REASONS[-1:])
            else:
                e.term_type = "Voluntary"
                if age >= 62 and rng.random() < 0.6:
                    e.term_reason = "Retirement"
                elif e.seg.job_code in ("RN100", "RN200") and hazard_multiplier(e.seg.job_code, m_start) > 1 \
                        and rng.random() < 0.5:
                    e.term_reason = "Better pay elsewhere"
                else:
                    e.term_reason = pick_weighted([r for r in C.VOLUNTARY_REASONS if r[0] != "Retirement"])
            e.seg.end = e.term_date
            transactions.append(dict(employee_id=e.employee_id, effective_date=e.term_date, txn_type="Termination",
                                     from_job=e.seg.job_code, to_job=None, from_dept=e.seg.dept_id, to_dept=None,
                                     old_pay=e.seg.pay_rate, new_pay=None,
                                     reason=f"{e.term_type}: {e.term_reason}"))
            if rng.random() < 0.97:
                od = max(START, e.term_date - timedelta(days=int(rng.integers(0, 21))))
                open_req(e.seg.job_code, e.seg.dept_id, e.seg.location_id, od, "Backfill")

        # growth hiring, plus the new ambulatory clinic
        growth = int(rng.poisson(6))
        if CLINIC_OPEN <= m_start < date(2026, 1, 1):
            growth += 40
        for _ in range(growth):
            if CLINIC_OPEN <= m_start < date(2026, 1, 1) and rng.random() < 0.88:
                job_code = pick(["MA100", "RN100", "AP100", "MD100", "PA100", "LP100"], [.30, .24, .12, .08, .16, .10])
                dept = pick(["D301", "D302"], [.6, .4]) if job_code != "PA100" else "D404"
                loc = "LOC04"
            else:
                job_code = pick([j[0] for j in C.JOBS], [j[9] for j in C.JOBS])
                dept = pick_dept(job_code)
                loc = pick_location(dept)
            open_req(job_code, dept, loc, rand_day(m_start, m_end), "Growth")

        # market adjustment for nurses
        if m_start <= MARKET_ADJ_DATE <= m_end:
            for e in employees:
                if e.active_on(MARKET_ADJ_DATE) and e.seg.job_code in ("RN100", "RN200") and e.seg.start < MARKET_ADJ_DATE:
                    change(e, MARKET_ADJ_DATE, "Market adjustment", "Nursing market adjustment (6%)",
                           pay=round(e.seg.pay_rate * 1.06, 2))

        # annual merit
        for mdate, extra in MERIT_DATES.items():
            if m_start <= mdate <= m_end:
                pct = {1: 0.0, 2: 1.5, 3: 3.0, 4: 4.0, 5: 5.5}
                for e in employees:
                    if not e.active_on(mdate) or (mdate - e.hire_date).days < 90:
                        continue
                    e.rating = int(pick([1, 2, 3, 4, 5], [.03, .10, .55, .25, .07]))
                    p = 0.0 if e.rating == 1 else max(0.0, pct[e.rating] + extra + rng.normal(0, 0.3))
                    if p == 0:
                        continue
                    pay = e.seg.pay_rate * (1 + p / 100)
                    pay = round(pay, 2) if JOBS[e.seg.job_code][6] == "Hourly" else round(pay / 100) * 100
                    change(e, mdate, "Merit increase", f"FY{fiscal_year(mdate) % 100} merit, rating {e.rating}", pay=pay)

        # promotions and transfers
        for e in active:
            if e.term_date is not None:
                continue
            tenure = (m_start - e.hire_date).days / 365.25
            nxt = C.PROMOTION_PATHS.get(e.seg.job_code)
            if nxt and tenure > 1 and rng.random() < 0.0045:
                j = JOBS[nxt]
                old = e.seg.pay_rate
                if JOBS[e.seg.job_code][6] == "Hourly" and j[6] == "Salary":
                    old = old * 2080
                elif JOBS[e.seg.job_code][6] == "Salary" and j[6] == "Hourly":
                    old = old / 2080
                pay = max(old * 1.08, pay_for_position(nxt, 0.08, m_start))
                pay = round(pay, 2) if j[6] == "Hourly" else round(pay / 100) * 100
                dept = e.seg.dept_id if e.seg.dept_id in j[11] else pick_dept(nxt)
                change(e, rand_day(m_start, m_end), "Promotion", f"Promoted to {j[1]}", job_code=nxt,
                       dept_id=dept, pay=pay)
            elif rng.random() < 0.003 and len(JOBS[e.seg.job_code][11]) > 1:
                dept = pick([d for d in JOBS[e.seg.job_code][11] if d != e.seg.dept_id])
                change(e, rand_day(m_start, m_end), "Transfer", f"Transfer to {DEPTS[dept][1]}", dept_id=dept)


# ---------------------------------------------------------------- payroll
OT_BASE = {"RN100": 6, "RN200": 5, "PC100": 4, "RT100": 4, "RD100": 3, "LB100": 3, "ST100": 4, "LP100": 3,
           "PH200": 2, "EV100": 3, "FS100": 2, "SC100": 4, "PA100": 1.5, "MA100": 1, "CD100": .5, "AD100": .5}
SHIFT_DIFF = {"Day": 0.0, "Evening": 2.50, "Night": 4.50}


def vacancy_by_family():
    """Month-end vacancy rate per job family: open requisitions / (headcount + open requisitions)."""
    out = {}
    for m_start, m_end in months():
        hc, vac = {}, {}
        for e in employees:
            if e.active_on(m_end):
                s = next((s for s in reversed(e.segments) if s.start <= m_end), e.seg)
                fam = JOBS[s.job_code][2]
                hc[fam] = hc.get(fam, 0) + 1
        for r in requisitions:
            if r["open_date"] <= m_end and (r["hire_date"] is None or r["hire_date"] > m_end) \
                    and (r["status"] != "Cancelled" or r["close_date"] > m_end):
                fam = JOBS[r["job_code"]][2]
                vac[fam] = vac.get(fam, 0) + 1
        out[(m_start.year, m_start.month)] = {f: vac.get(f, 0) / (hc.get(f, 0) + vac.get(f, 0) or 1)
                                              for f in set(hc) | set(vac)}
    return out


def build_payroll():
    vac = vacancy_by_family()
    rows, corrections = [], []
    period_end = date(2023, 10, 14)
    sign_on = {e.employee_id: e for e in employees
               if e.seg is not None and e.segments[0].job_code == "RN100" and e.hire_date >= date(2025, 1, 1)}
    while period_end <= END:
        period_start = period_end - timedelta(days=13)
        check_date = period_end + timedelta(days=6)
        v = vac.get((period_end.year, period_end.month), {})
        upgrade = UPGRADE_START <= check_date <= UPGRADE_END
        checks = 0
        for e in employees:
            if e.hire_date > period_end or (e.term_date is not None and e.term_date < period_start):
                continue
            s = next((s for s in reversed(e.segments) if s.start <= period_end), None)
            if s is None:
                continue
            first = max(period_start, e.hire_date)
            last = min(period_end, e.term_date or period_end)
            frac = ((last - first).days + 1) / 14
            j = JOBS[s.job_code]
            hourly = j[6] == "Hourly"
            reg_h = round(80 * s.fte * frac, 2)
            ot_h = 0.0
            if j[4] == "Nonexempt":
                lam = OT_BASE.get(s.job_code, 1) * (1 + 9 * v.get(j[2], 0.05)) * frac
                if s.dept_id in C.CLINIC_DEPTS:
                    lam *= 0.3  # clinics run business hours
                if rng.random() < 0.55:
                    ot_h = round(float(rng.gamma(0.9, lam / 0.9 / 0.55)), 2)
            if hourly:
                reg_pay = s.pay_rate * reg_h
                ot_pay = s.pay_rate * 1.5 * ot_h
            else:
                reg_pay = s.pay_rate / 26 * s.fte * frac
                ot_pay = 0.0
            diff = SHIFT_DIFF[e.shift] * (reg_h + ot_h) if hourly else 0.0
            other = 0.0
            if e.employee_id in sign_on:
                if first == e.hire_date:
                    other += 3750
                six = e.hire_date + timedelta(days=182)
                if period_start <= six <= period_end:
                    other += 3750
            gross = reg_pay + ot_pay + diff + other
            rows.append((period_end.isoformat(), check_date.isoformat(), e.employee_id, s.dept_id, s.job_code,
                         reg_h, ot_h, round(reg_pay, 2), round(ot_pay, 2), round(diff, 2), round(other, 2),
                         round(gross, 2)))
            checks += 1
            if rng.random() < (0.022 if upgrade else 0.004):
                reason = pick(["Missed hours", "Shift differential error", "Retro pay", "Deduction error",
                               "Late timecard approval"],
                              [.25, .25, .15, .2, .15] if upgrade else [.35, .1, .2, .1, .25])
                corrections.append((period_end.isoformat(), e.employee_id, reason,
                                    round(float(rng.lognormal(5.0, 0.8)), 2)))
        period_end += timedelta(days=14)
    return rows, corrections


# ---------------------------------------------------------------- HR service center
def build_cases():
    cases = []
    n = 900001
    hires_by_month, terms_by_month = {}, {}
    for e in employees:
        if e.hire_date >= START:
            k = (e.hire_date.year, e.hire_date.month)
            hires_by_month.setdefault(k, []).append(e)
        if e.term_date:
            k = (e.term_date.year, e.term_date.month)
            terms_by_month.setdefault(k, []).append(e)
    for m_start, m_end in months():
        active = [e for e in employees if e.active_on(m_end)]
        fy = fiscal_year(m_start)
        launched = m_start >= SERVICE_LAUNCH
        upgrade = UPGRADE_START <= m_start <= UPGRADE_END
        for cat, sub, rate, median_h, tier in C.CASE_TYPES:
            pool = active
            if cat == "Onboarding":
                pool = hires_by_month.get((m_start.year, m_start.month), [])
                lam = 0.45 * len(pool)
            elif cat == "Offboarding":
                pool = terms_by_month.get((m_start.year, m_start.month), [])
                lam = 0.40 * len(pool)
            else:
                lam = rate / 1000 * len(active)
            if cat == "Benefits" and m_start.month == 11:
                lam *= 3.4
            if cat == "Benefits" and m_start.month == 12:
                lam *= 1.6
            if sub == "Direct deposit or tax form" and m_start.month == 1:
                lam *= 3.0
            if sub == "Direct deposit or tax form" and m_start.month == 2:
                lam *= 1.8
            if cat == "Payroll" and upgrade:
                lam *= 2.3
            if launched and tier == 1:
                lam *= 0.86  # virtual agent answers some questions before a case is opened
            if not pool:
                continue
            for _ in range(int(rng.poisson(lam))):
                e = pool[rng.integers(len(pool))]
                day = rand_day(m_start, m_end)
                opened = datetime(day.year, day.month, day.day, int(rng.integers(7, 19)), int(rng.integers(0, 60)))
                priority = pick(["P1", "P2", "P3"], [.30, .50, .20] if cat == "Employee relations" else [.10, .45, .45])
                sla = {"P1": 24, "P2": 72, "P3": 120}[priority]
                mult = 1.0
                if launched and tier == 1:
                    mult *= 0.70
                if upgrade and cat == "Payroll":
                    mult *= 1.8
                if priority == "P1":
                    mult *= 0.55
                hours = round(float(median_h * mult * rng.lognormal(0, 0.75)), 1)
                closed = opened + timedelta(hours=hours)
                if closed.date() > END:
                    closed, hours = None, None
                if launched:
                    channel = pick(["Phone", "Email", "Portal", "Virtual agent"], [.28, .20, .27, .25])
                else:
                    channel = pick(["Phone", "Email", "Portal", "Chat"], [.42, .30, .23, .05])
                fcr_p = (0.75 if channel == "Virtual agent" else 0.60) if launched else 0.50
                fcr = int(tier == 1 and rng.random() < fcr_p)
                triage = "AI-assisted" if launched and rng.random() < 0.88 else "Manual"
                assign_h = round(float((0.3 if triage == "AI-assisted" else 5.5) * rng.lognormal(0, 0.6)), 2)
                met = None if hours is None else int(hours <= sla)
                csat = None
                if hours is not None and rng.random() < 0.28:
                    mu = 4.05 + (0.15 if launched else 0) - (0.6 if not met else 0) - (0.35 if upgrade and cat == "Payroll" else 0)
                    csat = int(np.clip(round(rng.normal(mu, 0.8)), 1, 5))
                cases.append((f"HC{n}", e.employee_id, opened.isoformat(sep=" "),
                              closed.isoformat(sep=" ") if closed else None, cat, sub, channel, priority, tier,
                              sla, hours, met, fcr, triage, assign_h, csat))
                n += 1
    return cases


# ---------------------------------------------------------------- write out
SCHEMA = """
CREATE TABLE locations (location_id TEXT PRIMARY KEY, location_name TEXT, location_type TEXT);
CREATE TABLE departments (dept_id TEXT PRIMARY KEY, dept_name TEXT, division TEXT, is_clinical INTEGER);
CREATE TABLE jobs (job_code TEXT PRIMARY KEY, job_title TEXT, job_family TEXT, grade INTEGER, flsa TEXT,
  is_clinical INTEGER, pay_basis TEXT, range_min REAL, range_mid REAL, range_max REAL);
CREATE TABLE employees (employee_id TEXT PRIMARY KEY, first_name TEXT, last_name TEXT, email TEXT, gender TEXT,
  birth_year INTEGER, hire_date TEXT, term_date TEXT, term_type TEXT, term_reason TEXT, status TEXT,
  job_code TEXT, dept_id TEXT, location_id TEXT, fte REAL, shift TEXT, pay_rate REAL, annual_base_pay REAL,
  performance_rating INTEGER, source_of_hire TEXT, req_id TEXT);
CREATE TABLE job_history (employee_id TEXT, start_date TEXT, end_date TEXT, job_code TEXT, dept_id TEXT,
  location_id TEXT, fte REAL, pay_rate REAL);
CREATE TABLE transactions (txn_id TEXT PRIMARY KEY, employee_id TEXT, effective_date TEXT, txn_type TEXT,
  from_job TEXT, to_job TEXT, from_dept TEXT, to_dept TEXT, old_pay REAL, new_pay REAL, reason TEXT);
CREATE TABLE requisitions (req_id TEXT PRIMARY KEY, job_code TEXT, dept_id TEXT, location_id TEXT, req_type TEXT,
  open_date TEXT, close_date TEXT, status TEXT, days_to_fill INTEGER, applicants INTEGER, screened INTEGER,
  interviewed INTEGER, offers INTEGER, offers_accepted INTEGER, source_of_hire TEXT, hired_employee_id TEXT,
  hire_date TEXT);
CREATE TABLE payroll (period_end TEXT, check_date TEXT, employee_id TEXT, dept_id TEXT, job_code TEXT,
  regular_hours REAL, overtime_hours REAL, regular_pay REAL, overtime_pay REAL, shift_diff_pay REAL,
  other_pay REAL, gross_pay REAL);
CREATE TABLE payroll_corrections (period_end TEXT, employee_id TEXT, reason TEXT, amount REAL);
CREATE TABLE hr_cases (case_id TEXT PRIMARY KEY, employee_id TEXT, opened_at TEXT, closed_at TEXT, category TEXT,
  subcategory TEXT, channel TEXT, priority TEXT, tier INTEGER, sla_hours INTEGER, resolution_hours REAL,
  met_sla INTEGER, first_contact_resolution INTEGER, triage_method TEXT, hours_to_assign REAL, csat INTEGER);
CREATE INDEX ix_hist ON job_history(employee_id, start_date);
CREATE INDEX ix_pay ON payroll(period_end, dept_id);
CREATE INDEX ix_txn ON transactions(txn_type, effective_date);
CREATE INDEX ix_case ON hr_cases(opened_at);
"""


def iso(d):
    return d.isoformat() if d else None


def write(db_path: Path, csv_dir: Path):
    payroll, corrections = build_payroll()
    cases = build_cases()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO locations VALUES (?,?,?)", C.LOCATIONS)
    con.executemany("INSERT INTO departments VALUES (?,?,?,?)", [d[:4] for d in C.DEPARTMENTS])
    con.executemany("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [(j[0], j[1], j[2], j[3], j[4], j[5], j[6],
                      *(round(x * (1.06 if j[0] in ("RN100", "RN200") else 1), 2) for x in (j[7], (j[7] + j[8]) / 2, j[8])))
                     for j in C.JOBS])
    emp_rows, hist_rows = [], []
    for e in employees:
        s = e.seg
        status = "Terminated" if e.term_date else ("Pending start" if e.hire_date > END else "Active")
        annual = s.pay_rate * 2080 * s.fte if JOBS[s.job_code][6] == "Hourly" else s.pay_rate * s.fte
        emp_rows.append((e.employee_id, e.first_name, e.last_name,
                         f"{e.first_name.lower()}.{e.last_name.lower()}{e.employee_id[1:]}@{C.EMAIL_DOMAIN}",
                         e.gender, e.birth_year, iso(e.hire_date), iso(e.term_date), e.term_type, e.term_reason,
                         status, s.job_code, s.dept_id, s.location_id, s.fte, e.shift, s.pay_rate, round(annual, 2),
                         e.rating, e.source, e.req_id))
        for seg in e.segments:
            hist_rows.append((e.employee_id, iso(seg.start), iso(seg.end), seg.job_code, seg.dept_id,
                              seg.location_id, seg.fte, seg.pay_rate))
    con.executemany(f"INSERT INTO employees VALUES ({','.join('?' * 21)})", emp_rows)
    con.executemany("INSERT INTO job_history VALUES (?,?,?,?,?,?,?,?)", hist_rows)
    txns = sorted(transactions, key=lambda t: (t["effective_date"], t["employee_id"]))
    con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [(f"T{i:07d}", t["employee_id"], iso(t["effective_date"]), t["txn_type"], t["from_job"],
                      t["to_job"], t["from_dept"], t["to_dept"], t["old_pay"], t["new_pay"], t["reason"])
                     for i, t in enumerate(txns, 1)])
    con.executemany(f"INSERT INTO requisitions VALUES ({','.join('?' * 17)})",
                    [(r["req_id"], r["job_code"], r["dept_id"], r["location_id"], r["req_type"], iso(r["open_date"]),
                      iso(r["close_date"]), r["status"],
                      (r["close_date"] - r["open_date"]).days if r["status"] == "Filled" else None,
                      r["applicants"], r["screened"], r["interviewed"], r["offers"], r["offers_accepted"],
                      r["source_of_hire"], r["hired_employee_id"], iso(r["hire_date"])) for r in requisitions])
    con.executemany("INSERT INTO payroll VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", payroll)
    con.executemany("INSERT INTO payroll_corrections VALUES (?,?,?,?)", corrections)
    con.executemany(f"INSERT INTO hr_cases VALUES ({','.join('?' * 16)})", cases)
    con.commit()

    csv_dir.mkdir(parents=True, exist_ok=True)
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cur = con.execute(f"SELECT * FROM {table}")
        with open(csv_dir / f"{table}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([c[0] for c in cur.description])
            w.writerows(cur)
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    return counts


def main():
    simulate()
    counts = write(DATA_DIR / "hr.db", DATA_DIR / "csv")
    for t, n in counts.items():
        print(f"{t:<22}{n:>9,}")


if __name__ == "__main__":
    main()
