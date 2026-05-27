import frappe

_schema_cache = {}
_installed_apps_cache = None

CORE_DOCTYPES = [
    "BA Sales Invoice", "BA Purchase Invoice", "BA Sales Order",
    "BA Purchase Order", "BA Customer", "BA Supplier", "BA Item",
    "BA Stock Ledger Entry", "BA Stock Entry", "BA Journal Entry",
    "BA Payment Entry", "BA Employee", "BA Quotation", "BA Account",
    "BA Cost Center",
]

CUSTOM_APP_DOCTYPES = {
    "bizaxl_stock": ["BA Item", "BA Warehouse", "BA Stock Entry", "BA Item Price", "BA Batch"],
    "bizaxl_hr": ["BA Employee", "BA Department", "BA Designation", "BA Leave Application", "BA Attendance", "BA Expense Claim"],
    "bizaxl_payroll": ["BA Salary Slip", "BA Payroll Entry", "BA Salary Structure", "BA Salary Component"],
    "bizaxl_projects": ["BA Project", "BA Task", "BA Timesheet"],
    "bizaxl_crm": ["BA Lead", "BA Opportunity", "BA Campaign"],
    "bizaxl_assets": ["BA Asset", "BA Asset Movement", "BA Asset Maintenance"],
    "bizaxl_pos": ["BA POS Invoice", "BA POS Profile", "BA POS Closing Entry"],
    "retail_erp": ["Weigh Label", "Store Profile", "Cashier Shift"],
    "energy_erp": ["Power Plant", "Generation Log", "Energy Bill", "Fuel Receipt"],
    "civic_erp": ["Grant", "Donor", "Fund", "Beneficiary", "Program"],
    "museum_erp": ["Artifact", "Exhibition", "Loan", "Conservation Record"],
    "proserv_erp": ["Client", "Engagement", "Timesheet Entry", "Fee Note"],
    "organ_donation_erp": ["Donor Pledge", "Deceased Donor", "Organ Record", "Recipient", "Transplant Surgery"],
}

_SKIP_FIELDTYPES = frozenset([
    "Section Break", "Column Break", "HTML", "Fold",
    "Heading", "Tab Break", "Button", "Image",
])


def _get_installed_apps():
    global _installed_apps_cache
    if _installed_apps_cache is None:
        try:
            _installed_apps_cache = set(frappe.get_installed_apps())
        except Exception:
            _installed_apps_cache = set()
    return _installed_apps_cache


def get_schema_context(focus_doctypes=None):
    global _schema_cache
    installed = _get_installed_apps()

    all_doctypes = list(CORE_DOCTYPES)
    for app_name, dts in CUSTOM_APP_DOCTYPES.items():
        if app_name in installed:
            for dt in dts:
                if dt not in all_doctypes:
                    all_doctypes.append(dt)

    if focus_doctypes:
        priority = [dt for dt in focus_doctypes if dt in all_doctypes]
        rest = [dt for dt in all_doctypes if dt not in set(priority)]
        all_doctypes = priority + rest

    schema_lines = []
    for dt in all_doctypes[:30]:
        if dt in _schema_cache:
            schema_lines.append(_schema_cache[dt])
            continue
        line = _build_schema_line(dt)
        if line:
            _schema_cache[dt] = line
            schema_lines.append(line)

    return "\n".join(schema_lines)


def _build_schema_line(doctype):
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        return None

    fields = []
    for f in meta.fields:
        if f.fieldtype in _SKIP_FIELDTYPES:
            continue
        info = f"{f.fieldname} ({f.fieldtype}"
        if f.fieldtype == "Link" and f.options:
            info += f" -> {f.options}"
        elif f.fieldtype == "Select" and f.options:
            opts = [o for o in f.options.split("\n") if o][:4]
            info += f": {', '.join(opts)}"
        if f.reqd:
            info += ", required"
        info += ")"
        fields.append(info)
        if len(fields) >= 25:
            break

    if not fields:
        return None

    table_name = f"tabBA {doctype[3:]}" if doctype.startswith("BA ") else f"tab{doctype}"
    return f"TABLE `{table_name}`: " + ", ".join(fields)


def get_doctype_fields(doctype):
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        return []

    fields = []
    for f in meta.fields:
        if f.fieldtype in _SKIP_FIELDTYPES:
            continue
        if f.fieldname in ("naming_series", "amended_from"):
            continue
        if f.read_only and not f.reqd:
            continue
        fields.append({
            "fieldname": f.fieldname,
            "label": f.label or f.fieldname.replace("_", " ").title(),
            "fieldtype": f.fieldtype,
            "required": bool(f.reqd),
            "options": f.options or "",
            "default": f.default or "",
        })
    return fields


def clear_schema_cache():
    global _schema_cache, _installed_apps_cache
    _schema_cache = {}
    _installed_apps_cache = None
