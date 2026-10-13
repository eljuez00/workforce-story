"""The generated company must match its brief: about 5,000 employees and about 20% turnover."""

import sqlite3

import pytest

from evals import ground_truth as gt
from metrics.core import FISCAL_YEARS, HRMetrics

DB = gt.DB


@pytest.fixture(scope="module")
def m():
    return HRMetrics()


@pytest.mark.parametrize("fy", FISCAL_YEARS)
def test_headcount_near_5000(fy):
    assert 4750 <= gt.headcount_end(fy) <= 5400


def test_average_turnover_near_20pct():
    rates = [gt.turnover_rate(fy) for fy in FISCAL_YEARS]
    assert 19.0 <= sum(rates) / len(rates) <= 21.5
    assert all(16 <= r <= 24 for r in rates)


def test_story_beats_present(m):
    nursing = {r["month"]: r["annualized_turnover_pct"] for r in m.monthly_turnover("Nursing")}
    spring_2025 = [nursing[k] for k in ("2025-03", "2025-04", "2025-05")]
    fy26 = [v for k, v in nursing.items() if k >= "2025-10"]
    assert min(spring_2025) > max(sorted(fy26)[:6])  # the spike is real and then recedes
    assert m.service_summary(2026)["median_hours_to_assign"] < m.service_summary(2025)["median_hours_to_assign"] / 5
    assert m.payroll_summary(2025)["corrections_per_1000_checks"] > m.payroll_summary(2024)["corrections_per_1000_checks"]


def test_referential_integrity():
    con = sqlite3.connect(DB)
    q = lambda s: con.execute(s).fetchone()[0]
    assert q("SELECT COUNT(*) FROM employees WHERE job_code NOT IN (SELECT job_code FROM jobs)") == 0
    assert q("SELECT COUNT(*) FROM job_history WHERE employee_id NOT IN (SELECT employee_id FROM employees)") == 0
    assert q("SELECT COUNT(*) FROM payroll WHERE employee_id NOT IN (SELECT employee_id FROM employees)") == 0
    assert q("SELECT COUNT(*) FROM requisitions WHERE status='Filled' AND hired_employee_id IS NULL") == 0
    assert q("SELECT COUNT(*) FROM employees WHERE term_date < hire_date") == 0
    # effective-dated history: no overlapping segments per employee
    assert q("""SELECT COUNT(*) FROM job_history a JOIN job_history b ON a.employee_id = b.employee_id
                AND a.rowid < b.rowid AND a.start_date <= COALESCE(b.end_date, '9999') AND b.start_date <= COALESCE(a.end_date, '9999')""") == 0
    con.close()


def test_all_names_are_fictional_domain():
    con = sqlite3.connect(DB)
    assert con.execute("SELECT COUNT(*) FROM employees WHERE email NOT LIKE '%@cedarforkhealth.example'").fetchone()[0] == 0
    con.close()
