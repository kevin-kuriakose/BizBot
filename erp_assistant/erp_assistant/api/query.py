import frappe
import decimal
import datetime

BLOCKED_KEYWORDS = frozenset([
    "DROP ", "DELETE ", "TRUNCATE ", "ALTER ", "CREATE TABLE",
    "INSERT INTO", "UPDATE ", "GRANT ", "REVOKE ", "EXECUTE ",
    "INTO OUTFILE", "LOAD DATA", "SHOW TABLES", "SHOW DATABASES",
])


def execute_query(sql):
    """
    Execute a SELECT query safely.
    Returns (rows: list[dict], columns: list[str])
    Raises frappe.ValidationError on unsafe queries.
    """
    sql = _clean_sql(sql)
    sql_upper = sql.upper()

    for keyword in BLOCKED_KEYWORDS:
        if keyword in sql_upper:
            frappe.throw(f"Query contains blocked keyword: {keyword.strip()}")

    if not sql_upper.lstrip().startswith("SELECT"):
        frappe.throw("Only SELECT queries are permitted")

    # Enforce result cap
    if "LIMIT" not in sql_upper:
        sql = sql.rstrip(";") + " LIMIT 100"

    try:
        result = frappe.db.sql(sql, as_dict=True)
    except Exception as e:
        frappe.throw(f"Query execution error: {str(e)}")

    if not result:
        return [], []

    columns = list(result[0].keys())
    rows = [_serialize_row(dict(row)) for row in result]
    return rows, columns


def _clean_sql(sql):
    """Strip markdown fences and trailing semicolons."""
    sql = sql.strip()
    # Strip ```sql ... ``` or ``` ... ```
    if sql.startswith("```"):
        lines = sql.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        sql = "\n".join(lines).strip()
    return sql.rstrip(";")


def _serialize_row(row):
    """Convert non-JSON-serializable types to strings."""
    out = {}
    for k, v in row.items():
        if isinstance(v, decimal.Decimal):
            out[k] = float(v)
        elif isinstance(v, (datetime.date, datetime.datetime)):
            out[k] = str(v)
        elif v is None:
            out[k] = ""
        else:
            out[k] = v
    return out
