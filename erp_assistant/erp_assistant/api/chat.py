try:
    from bizaxl_radar.intelligence.domain_loader import (
        get_system_prompt_addition as _get_domain_ctx,
        get_domain_label as _get_domain_label,
    )
except ImportError:
    def _get_domain_ctx(): return ''
    def _get_domain_label(): return 'business'

import re
import frappe
import json
from erp_assistant.erp_assistant.api.ollama import call_ollama
from erp_assistant.erp_assistant.api.intent import classify_intent
from erp_assistant.erp_assistant.api.query import execute_query
from erp_assistant.erp_assistant.api.document import handle_write
from erp_assistant.erp_assistant.api.schema import get_schema_context
from erp_assistant.erp_assistant.api.permissions import (
    get_user_permissions, can_submit, can_create,
    get_allowed_modules, is_admin, get_role_level
)

# Frappe table name map — used to correct hallucinated names
TABLE_ALIASES = {
    "sales invoice": "tabBA Sales Invoice",
    "purchase invoice": "tabBA Purchase Invoice",
    "sales order": "tabBA Sales Order",
    "purchase order": "tabBA Purchase Order",
    "customer": "tabBA Customer",
    "supplier": "tabBA Supplier",
    "item": "tabBA Item",
    "stock entry": "tabBA Stock Entry",
    "stock ledger entry": "tabStock Ledger Entry",
    "journal entry": "tabBA Journal Entry",
    "payment entry": "tabBA Payment Entry",
    "employee": "tabEmployee",
    "quotation": "tabBA Quotation",
    "delivery note": "tabDelivery Note",
    "purchase receipt": "tabPurchase Receipt",
    "sales transactions": "tabSales Invoice",
    "salestransactions": "tabSales Invoice",
    "sales_invoices": "tabSales Invoice",
    "salesinvoices": "tabSales Invoice",
    "invoice": "tabBA Sales Invoice",
    "invoices": "tabBA Sales Invoice",
    "transactions": "tabSales Invoice",
    "purchase_invoices": "tabPurchase Invoice",
    "purchaseinvoices": "tabPurchase Invoice",
    "sales_orders": "tabSales Order",
    "purchase_orders": "tabPurchase Order",
    "customers": "tabBA Customer",
    "suppliers": "tabBA Supplier",
    "items": "tabBA Item",
    "employees": "tabEmployee",
    "payments": "tabBA Payment Entry",
}


@frappe.whitelist(allow_guest=False)
def chat(message, history=None, session_data=None, context=None):
    if not message or not message.strip():
        return {"response": "Please type a message.", "type": "error", "session_data": {}}

    history = json.loads(history) if isinstance(history, str) else (history or [])
    session_data = (
        json.loads(session_data) if isinstance(session_data, str) else (session_data or {})
    )
    page_context = json.loads(context) if isinstance(context, str) else (context or {})

    try:
        if session_data.get("mode") in ("collecting_fields", "confirm_submit", "collecting_items", "confirm_create_linked", "collecting_linked_fields", "confirm_create_item", "creating_new_item", "confirm_restart", "resubmit"):
            return handle_write(message, history, session_data, {})

        # ── Inject domain-specific AI context ──────────────────
        _domain_context = _get_domain_ctx()
        _domain_name    = _get_domain_label()

        intent = classify_intent(message, history)

        # Capability / feature questions — answer conversationally, never hit DB
        if intent.get("capability") or (intent.get("type") == "general" and not intent.get("doctypes")):
            cap_q = ("You are BizBot, an AI assistant for BizAxl ERP. "
                     "The user asks about your capabilities. Answer helpfully. "
                     "BizBot can: query ERP data, create documents, analyse trends, "
                     "read PDFs (RAG), and analyse images via AI Vision (OCR). "
                     "To upload: click the Files chip in the chat. "
                     "Question: " + message)
            try:
                cap_ans = call_ollama([{"role": "user", "content": cap_q}])
            except Exception:
                cap_ans = "Yes! Click the \uD83D\uDCCE Files chip to upload a PDF or image."
            return {"response": cap_ans, "type": "general", "session_data": session_data}


    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ERP Assistant Chat Error")
        return {
            "response": f"Error: {str(e)}",
            "type": "error",
            "session_data": {},
        }


def _extract_sql(text):
    """Extract first SELECT statement from LLM output regardless of formatting."""
    # Strip ```sql fences
    fence = re.search(r'```(?:sql)?\s*(SELECT[\s\S]+?)```', text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip().rstrip(';')

    # Bare SELECT anywhere
    bare = re.search(r'(SELECT\s[\s\S]+?)(?:;|\Z)', text, re.IGNORECASE)
    if bare:
        sql = bare.group(1).strip().rstrip(';')
        if 'FROM' in sql.upper():
            return sql

    return None


def _fix_table_names(sql):
    """Replace hallucinated table names with correct Frappe tab-prefixed names."""
    fixes = [
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Ss]ales[_]?[Ii]nvoices?[`"\']?', r'\1 `tabSales Invoice`'),
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Pp]urchase[_]?[Ii]nvoices?[`"\']?', r'\1 `tabPurchase Invoice`'),
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Ss]ales[_]?[Oo]rders?[`"\']?', r'\1 `tabSales Order`'),
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Pp]urchase[_]?[Oo]rders?[`"\']?', r'\1 `tabPurchase Order`'),
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Cc]ustomers?[`"\']?', r'\1 `tabCustomer`'),
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Ss]uppliers?[`"\']?', r'\1 `tabSupplier`'),
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Ii]tems?[`"\']?', r'\1 `tabItem`'),
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Ee]mployees?[`"\']?', r'\1 `tabEmployee`'),
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Pp]ayment[_]?[Ee]ntri(?:es|y)?[`"\']?', r'\1 `tabPayment Entry`'),
        (r'(?i)\b(FROM|JOIN)\s+`?["\']?[Ss]tock[_]?[Ee]ntri(?:es|y)?[`"\']?', r'\1 `tabStock Entry`'),
    ]
    for pattern, replacement in fixes:
        sql = re.sub(pattern, replacement, sql)
    return sql


_CLEAN_COLUMNS = {
    'tabCustomer': 'name, customer_name, customer_type, customer_group, territory, mobile_no, email_id',
    'tabSales Invoice': 'name, customer, posting_date, grand_total, outstanding_amount, status',
    'tabPurchase Invoice': 'name, supplier, posting_date, grand_total, outstanding_amount, status',
    'tabSales Order': 'name, customer, transaction_date, grand_total, status',
    'tabPurchase Order': 'name, supplier, transaction_date, grand_total, status',
    'tabItem': 'name, item_name, item_group, stock_uom, standard_rate',
    'tabEmployee': 'name, employee_name, department, designation, status',
    'tabPayment Entry': 'name, payment_type, posting_date, party, paid_amount, status',
}


def _clean_select_star(sql):
    """Replace SELECT * with specific columns for known tables."""
    if 'SELECT *' not in sql.upper():
        return sql
    for table, cols in _CLEAN_COLUMNS.items():
        pattern = re.compile(
            r'SELECT\s+\*\s+FROM\s+`?' + re.escape(table) + r'`?',
            re.IGNORECASE
        )
        sql = pattern.sub('SELECT ' + cols + ' FROM `' + table + '`', sql)
    return sql


def handle_read(message, history, intent, page_context=None):
    schema = get_schema_context(intent.get("doctypes", []))

    # Explicit table name reference in the prompt
    # Build page context hint
    context_hint = ""
    if page_context:
        route = page_context.get("route", [])
        route_str = page_context.get("route_str", "")
        if route and len(route) >= 2:
            page_type = route[0]  # e.g. "List", "Form", "Report"
            page_name = route[1]  # e.g. "Sales Invoice"
            if page_type == "List":
                context_hint = f"\nCURRENT PAGE: User is viewing the {page_name} list."
            elif page_type == "Form":
                doc_name = route[2] if len(route) > 2 else ""
                context_hint = f"\nCURRENT PAGE: User is viewing {page_name} {doc_name}."
            elif page_type == "Report":
                context_hint = f"\nCURRENT PAGE: User is on the {page_name} report."

    sql_prompt = f"""You are a MariaDB expert. Generate a SQL SELECT query for a Frappe/ERPNext database.{context_hint}

CRITICAL — Frappe table naming rules:
- ALL tables have the prefix "tab" followed by the DocType name
- Sales invoices    → `tabSales Invoice`
- Purchase invoices → `tabPurchase Invoice`
- Customers         → `tabCustomer`
- Items/products    → `tabItem`
- Stock entries     → `tabStock Entry`
- Journal entries   → `tabJournal Entry`
- Payment entries   → `tabPayment Entry`
- Sales orders      → `tabSales Order`
- Purchase orders   → `tabPurchase Order`
- Employees         → `tabEmployee`
- NEVER use table names without the "tab" prefix
- NEVER invent table names — only use tables from the schema below

OTHER RULES:
- Always include: WHERE docstatus < 2
- Backtick reserved words: `name`, `status`, `type`, `date`
- "this month": MONTH(posting_date)=MONTH(CURDATE()) AND YEAR(posting_date)=YEAR(CURDATE())
- "this year": YEAR(posting_date)=YEAR(CURDATE())
- For totals: SUM(grand_total)
- Add LIMIT 50
- NEVER use SELECT * — always select specific relevant columns only
- For customers: SELECT name, customer_name, customer_type, customer_group, territory, mobile_no, email_id
- For sales invoices: SELECT name, customer, posting_date, grand_total, outstanding_amount, `status`
- For purchase invoices: SELECT name, supplier, posting_date, grand_total, outstanding_amount, `status`
- For items: SELECT name, item_name, item_group, stock_uom, standard_rate
- For employees: SELECT name, employee_name, department, designation, `status`
- For sales orders: SELECT name, customer, transaction_date, grand_total, `status`

SCHEMA:
{schema}

Question: {message}

SQL (starting with SELECT, no explanation):"""

    raw = call_ollama([{"role": "user", "content": sql_prompt}])
    sql = _extract_sql(raw)
    if sql:
        sql = _clean_select_star(sql)

    if not sql:
        return handle_general(message, history)

    # Fix any hallucinated table names before executing
    sql = _fix_table_names(sql)

    try:
        rows, columns = execute_query(sql)
    except Exception as e:
        err_str = str(e)
        # If table still doesn't exist, surface it clearly with the SQL
        return {
            "response": (
                f"I generated a query but it failed: `{err_str}`\n\n"
                "Please try a more specific question, e.g. 'show me sales invoices this month'."
            ),
            "type": "error",
            "sql": sql,
            "session_data": {},
        }

    if not rows:
        return {
            "response": "No records found for that query. The data may not exist yet.",
            "type": "read",
            "data": [],
            "columns": [],
            "sql": sql,
            "session_data": {},
        }

    summary_prompt = f"""User asked: "{message}"
Database returned {len(rows)} rows.
Columns: {columns}
First 10 rows: {json.dumps(rows[:10], default=str)}

Write a SHORT business summary (max 80 words).
Use ₹ for currency. Bold key numbers with **number**.
Do NOT say "go to" or give navigation instructions.
End with one follow-up suggestion."""

    summary = call_ollama([
        {
            "role": "system",
            "content": "Summarise ERP query results concisely. Never give navigation instructions.",
        },
        {"role": "user", "content": summary_prompt},
    ])

    return {
        "response": summary,
        "type": "read",
        "data": rows[:50],
        "columns": columns,
        "sql": sql,
        "session_data": {},
    }




def handle_analytics(message, history, intent, page_context=None):
    """
    Handle analytics queries — multi-query comparisons, trends, summaries.
    Generates multiple SQL queries and combines results.
    """
    schema = get_schema_context(intent.get("doctypes", []))

    analytics_prompt = f"""You are a business analyst and MariaDB expert for a Frappe/ERPNext database.
The user wants an analytics summary. Generate 1-3 SQL SELECT queries to answer their question.

CRITICAL TABLE NAMES:
- Sales invoices → `tabSales Invoice`
- Purchase invoices → `tabPurchase Invoice`
- Customers → `tabCustomer`
- Items → `tabItem`
- Employees → `tabEmployee`
- Payments → `tabPayment Entry`

RULES:
- Always include WHERE docstatus < 2
- For "this month": MONTH(posting_date)=MONTH(CURDATE()) AND YEAR(posting_date)=YEAR(CURDATE())
- For "last month": MONTH(posting_date)=MONTH(CURDATE())-1 AND YEAR(posting_date)=YEAR(CURDATE())
- For "this year": YEAR(posting_date)=YEAR(CURDATE())
- For "last year": YEAR(posting_date)=YEAR(CURDATE())-1
- Use SUM(grand_total) for revenue, COUNT(*) for counts
- Separate multiple queries with --- on its own line
- Each query must be a complete valid SELECT statement

SCHEMA:
{schema}

Question: {message}

SQL queries (separated by --- if multiple):"""

    raw = call_ollama([{"role": "user", "content": analytics_prompt}])

    # Split into multiple queries
    queries = []
    for block in raw.split("---"):
        sql = _extract_sql(block.strip())
        if sql:
            sql = _clean_select_star(sql)
            sql = _fix_table_names(sql)
            queries.append(sql)

    if not queries:
        return handle_general(message, history)

    all_results = []
    all_columns = []

    for sql in queries[:3]:  # max 3 queries
        try:
            rows, cols = execute_query(sql)
            if rows:
                all_results.append({"sql": sql, "rows": rows, "columns": cols})
                all_columns = cols  # use last for display
        except Exception:
            continue

    if not all_results:
        return {
            "response": "I couldn't find data to compare. Make sure you have transactions in the system.",
            "type": "read",
            "data": [],
            "columns": [],
            "sql": queries[0] if queries else "",
            "session_data": {},
        }

    # Build combined summary
    summary_data = []
    for r in all_results:
        summary_data.extend(r["rows"][:5])

    summary_prompt = f"""User asked: "{message}"

Analytics data from {len(all_results)} queries:
{json.dumps([{{"query": r["sql"][:100], "rows": r["rows"][:3]}} for r in all_results], default=str)}

Write a concise business analytics summary (max 150 words).
- Compare numbers clearly
- Use ₹ for currency, bold key figures with **number**
- Highlight trends (up/down/flat)
- End with one actionable insight"""

    summary = call_ollama([
        {"role": "system", "content": "You are a business analyst. Summarise ERP analytics data concisely."},
        {"role": "user", "content": summary_prompt}
    ])

    # Use first result's data for the table
    first = all_results[0]
    return {
        "response": summary,
        "type": "read",
        "data": first["rows"][:50],
        "columns": first["columns"],
        "sql": " \n---\n".join(r["sql"] for r in all_results),
        "session_data": {},
    }

def handle_help(message, history):
    messages = [
        {
            "role": "system",
            "content": "You are a Frappe/ERPNext v15 expert. Answer how-to questions clearly. Max 200 words.",
        },
    ]
    for h in history[-6:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})
    return {"response": call_ollama(messages), "type": "help", "session_data": {}}


def handle_general(message, history):
    messages = [
        {
            "role": "system",
            "content": "You are an ERP assistant. Be concise. Max 150 words.",
        },
    ]
    for h in history[-6:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})
    return {"response": call_ollama(messages), "type": "general", "session_data": {}}
