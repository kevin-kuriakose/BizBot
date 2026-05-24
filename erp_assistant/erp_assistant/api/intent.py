from erp_assistant.erp_assistant.api.ollama import call_ollama

# Strong signals for SQL data queries
READ_KEYWORDS = frozenset([
    "show", "list", "get", "find", "what", "how many", "total",
    "summary", "report", "give me", "tell me", "fetch", "display",
    "how much", "which", "who", "when", "where", "count", "average",
    "top", "best", "worst", "compare", "vs", "versus", "trend",
    "balance", "outstanding", "overdue", "pending", "sales", "revenue",
    "invoice", "invoices", "orders", "stock", "inventory", "customers",
    "suppliers", "employees", "payments", "purchases",
])

# Strong signals for document creation
WRITE_KEYWORDS = frozenset([
    "create", "make", "add", "new", "submit", "file", "register",
    "insert", "post", "record", "book", "generate", "raise", "draft",
    "log a", "open a",
])

# Navigation/how-to — only triggers if NO data words present
HELP_PHRASES = [
    "how do i", "how to", "where can i find", "what is the",
    "explain", "help me understand", "guide me", "show me how",
    "what fields are", "required for", "navigate to",
]

KNOWN_DOCTYPES = [
    "Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order",
    "Customer", "Supplier", "Item", "Stock Entry", "Journal Entry",
    "Payment Entry", "Employee", "Quotation", "Delivery Note",
    "Purchase Receipt", "Weigh Label", "Store Profile", "POS Invoice",
    "Power Plant", "Generation Log", "Energy Bill", "Fuel Receipt",
    "Grant", "Donor", "Fund", "Beneficiary", "Program",
    "Artifact", "Exhibition", "Loan", "Conservation Record",
    "Client", "Engagement", "Timesheet Entry", "Fee Note", "Staff Profile",
    "Donor Pledge", "Deceased Donor", "Organ Record",
    "Recipient", "Transplant Surgery",
]

_DOCTYPE_LOWER = {dt.lower(): dt for dt in KNOWN_DOCTYPES}


def classify_intent(message, history=None):
    msg_lower = message.lower()

    mentioned = [dt for lower_dt, dt in _DOCTYPE_LOWER.items()
                 if lower_dt in msg_lower]

    read_score  = sum(1 for kw in READ_KEYWORDS  if kw in msg_lower)
    write_score = sum(1 for kw in WRITE_KEYWORDS if kw in msg_lower)

    # Write wins only with a clear write keyword and either:
    # - no competing read keywords, OR
    # - a specific doctype mentioned
    if write_score > 0 and (read_score == 0 or mentioned):
        # Safeguard: "show me new invoices" has write kw "new" but is a read
        # If read_score >= write_score and no strong write verb, treat as read
        strong_write = any(kw in msg_lower for kw in [
            "create", "make", "submit", "register", "file", "draft",
            "insert", "post", "book", "raise",
        ])
        if strong_write:
            return {"type": "write", "doctypes": mentioned}

    # Read: any read keyword present
    if read_score > 0:
        return {"type": "read", "doctypes": mentioned}

    # Help: only if it's a how-to question with no data words
    if any(phrase in msg_lower for phrase in HELP_PHRASES):
        return {"type": "help", "doctypes": mentioned}

    # Doctype mentioned without verb — probably a read
    if mentioned:
        return {"type": "read", "doctypes": mentioned}

    # True ambiguity — ask the LLM (last resort)
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
