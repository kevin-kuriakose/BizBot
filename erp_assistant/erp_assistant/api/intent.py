from erp_assistant.erp_assistant.api.ollama import call_ollama

READ_KEYWORDS = frozenset([
    "show", "list", "get", "find", "what", "how many", "total",
    "summary", "report", "give me", "tell me", "fetch", "display",
    "how much", "which", "who", "when", "where", "count", "average",
    "top", "best", "worst", "compare", "vs", "versus", "trend",
    "balance", "outstanding", "overdue", "pending", "sales", "revenue",
    "invoice", "invoices", "orders", "stock", "inventory", "customers",
    "suppliers", "employees", "payments", "purchases",
])

WRITE_KEYWORDS = frozenset([
    "create", "make", "add", "new", "submit", "file", "register",
    "insert", "post", "record", "book", "generate", "raise", "draft",
    "log a", "open a",
])

HELP_PHRASES = [
    "how do i", "how to", "where can i find", "what is the",
    "explain", "help me understand", "guide me", "show me how",
    "what fields are", "required for", "navigate to",
]

KNOWN_DOCTYPES = [
    "BA Sales Invoice", "BA Purchase Invoice", "BA Sales Order",
    "BA Purchase Order", "BA Customer", "BA Supplier", "BA Item",
    "BA Stock Entry", "BA Journal Entry", "BA Payment Entry",
    "BA Employee", "BA Quotation", "BA Account", "BA Cost Center",
    "BA Lead", "BA Opportunity", "BA Project", "BA Task", "BA Timesheet",
    "BA Asset", "BA POS Invoice", "BA Salary Slip", "BA Payroll Entry",
    "BA Leave Application", "BA Attendance", "BA Expense Claim",
    "Weigh Label", "Store Profile", "Cashier Shift",
    "Power Plant", "Generation Log", "Energy Bill",
    "Grant", "Donor", "Fund", "Beneficiary",
    "Artifact", "Exhibition", "Loan",
    "Client", "Engagement", "Fee Note",
    "Donor Pledge", "Deceased Donor", "Organ Record", "Recipient",
]

_DOCTYPE_LOWER = {dt.lower(): dt for dt in KNOWN_DOCTYPES}


def classify_intent(message, history=None):
    msg_lower = message.lower()
    mentioned = [dt for lower_dt, dt in _DOCTYPE_LOWER.items() if lower_dt in msg_lower]
    read_score = sum(1 for kw in READ_KEYWORDS if kw in msg_lower)
    write_score = sum(1 for kw in WRITE_KEYWORDS if kw in msg_lower)

    if write_score > 0 and (read_score == 0 or mentioned):
        strong_write = any(kw in msg_lower for kw in [
            "create", "make", "submit", "register", "file", "draft",
            "insert", "post", "book", "raise",
        ])
        if strong_write:
            return {"type": "write", "doctypes": mentioned}

    if read_score > 0:
        return {"type": "read", "doctypes": mentioned}

    if any(phrase in msg_lower for phrase in HELP_PHRASES):
        return {"type": "help", "doctypes": mentioned}

    if mentioned:
        return {"type": "read", "doctypes": mentioned}

    return _llm_classify(message, mentioned)


def _llm_classify(message, mentioned_doctypes):
    try:
        prompt = f"""Classify this ERP system message into ONE word only.

read   = asking for data, reports, numbers, lists, summaries
write  = creating, submitting, registering a document
help   = asking how to do something in the software
general = everything else

Message: {message}

Reply with exactly one word (read, write, help, or general):"""

        result = call_ollama([{"role": "user", "content": prompt}]).strip().lower()
        for t in ("write", "help", "general", "read"):
            if t in result:
                return {"type": t, "doctypes": mentioned_doctypes}
        return {"type": "read", "doctypes": mentioned_doctypes}
    except Exception:
        return {"type": "read", "doctypes": mentioned_doctypes}
