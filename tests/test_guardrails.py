import json

import pytest

from agent.guardrails import MAX_ROWS, GuardrailError, run_readonly_sql
from agent.tools import TOOL_DEFINITIONS, dispatch_tool


@pytest.mark.parametrize("sql", [
    "DELETE FROM employees",
    "UPDATE employees SET pay_rate = 0",
    "INSERT INTO jobs VALUES ('X','X','X',1,'X',0,'X',1,1,1)",
    "DROP TABLE payroll",
    "SELECT 1; DROP TABLE payroll",
    "ATTACH DATABASE 'x.db' AS x",
    "PRAGMA writable_schema = 1",
    "WITH x AS (SELECT 1) DELETE FROM employees",
])
def test_writes_and_ddl_refused(sql):
    with pytest.raises(GuardrailError):
        run_readonly_sql(sql)


@pytest.mark.parametrize("sql", [
    "SELECT first_name FROM employees",
    "SELECT * FROM employees",
    "SELECT email FROM employees WHERE employee_id = 'E10001'",
    "SELECT COUNT(*) FROM employees WHERE last_name = 'Smith'",
    "SELECT employee_id FROM employees ORDER BY birth_year",
])
def test_pii_columns_blocked(sql):
    with pytest.raises(GuardrailError, match="PII"):
        run_readonly_sql(sql)


def test_allowed_query_and_row_cap():
    out = run_readonly_sql("SELECT employee_id, job_code FROM employees")
    assert out["row_count"] == MAX_ROWS and out["truncated"] is True
    agg = run_readonly_sql("SELECT job_code, COUNT(*) FROM employees GROUP BY job_code")
    assert agg["truncated"] is False and agg["row_count"] > 10


def test_dispatch_never_raises_and_flags_errors():
    payload, is_error = dispatch_tool("run_sql", {"sql": "DELETE FROM employees"})
    assert is_error and "error" in json.loads(payload)
    payload, is_error = dispatch_tool("enterprise_summary", {"fiscal_year": 2031})
    assert is_error
    payload, is_error = dispatch_tool("no_such_tool", {})
    assert is_error


def test_schema_hides_pii():
    payload, _ = dispatch_tool("describe_schema", {})
    cols = json.loads(payload)["tables"]["employees"]
    assert "first_name" not in cols and "email" not in cols and "employee_id" in cols


def test_every_tool_has_valid_schema():
    names = [t["name"] for t in TOOL_DEFINITIONS]
    assert len(names) == len(set(names))
    for t in TOOL_DEFINITIONS:
        assert t["description"] and t["input_schema"]["type"] == "object"
        for r in t["input_schema"]["required"]:
            assert r in t["input_schema"]["properties"]
