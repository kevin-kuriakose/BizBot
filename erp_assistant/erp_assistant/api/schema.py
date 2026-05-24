import frappe

_schema_cache = {}
_installed_apps_cache = None

# Only DocTypes confirmed to exist in standard ERPNext v15
CORE_DOCTYPES = [
    "Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order",
    "Customer", "Supplier", "Item", "Stock Ledger Entry", "Stock Entry",
    "Journal Entry", "Payment Entry", "Employee", "Quotation",
    "Delivery Note", "Purchase Receipt",
]

CUSTOM_APP_DOCTYPES = {
    "logistics_transport_erp": [
        "Shipment", "Vehicle", "Driver",
    ],
    "retail_erp": [
        "Weigh Label", "Store Profile", "POS Invoice",
    ],
    "energy_erp": [
        "Power Plant", "Generation Log", "Energy Bill",
        "Fuel Receipt",
    ],
    "civic_erp": [
        "Grant", "Donor", "Fund", "Beneficiary", "Program",
    ],
    "museum_erp": [
        "Artifact", "Exhibition", "Loan", "Conservation Record",
    ],
    "proserv_erp": [
        "Client", "Engagement", "Timesheet Entry", "Fee Note",
        "Staff Profile",
    ],
    "organ_donation_erp": [
        "Donor Pledge", "Deceased Donor", "Organ Record",
        "Recipient", "Transplant Surgery",
    ],
    "vetcare_management": [
        "Patient", "Appointment",
    ],
    "healthcare": [
        "Patient", "Patient Appointment",
    ],
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
            all_doctypes.extend(dts)

    seen = set()
    deduped = []
    for dt in all_doctypes:
        if dt not in seen:
            seen.add(dt)
            deduped.append(dt)

    if focus_doctypes:
        priority = [dt for dt in focus_doctypes if dt in seen]
        rest = [dt for dt in deduped if dt not in set(priority)]
        deduped = priority + rest

    schema_lines = []
    for dt in deduped[:30]:
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
        # DocType doesn't exist in this install — skip silently
        return None

    fields = []
    for f in meta.fields:
        if f.fieldtype in _SKIP_FIELDTYPES:
            continue
        info = f"{f.fieldname} ({f.fieldtype}"
        if f.fieldtype == "Link" and f.options:
            info += f" → {f.options}"
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

    return f"TABLE `tab{doctype}`: " + ", ".join(fields)


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
