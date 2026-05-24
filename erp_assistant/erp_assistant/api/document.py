import frappe
from frappe.utils import today as _today, getdate, nowdate
from erp_assistant.erp_assistant.api.ollama import call_ollama

KNOWN_DOCTYPES = [
    "Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order",
    "Customer", "Supplier", "Item", "Stock Entry", "Journal Entry",
    "Payment Entry", "Employee", "Quotation", "Delivery Note",
    "Purchase Receipt", "Weigh Label", "Store Profile", "POS Invoice",
    "Power Plant", "Generation Log", "Energy Bill", "Fuel Receipt",
    "Grant", "Donor", "Fund", "Beneficiary", "Program",
    "Artifact", "Exhibition", "Loan", "Conservation Record",
    "Client", "Engagement", "Timesheet Entry", "Fee Note",
    "Donor Pledge", "Deceased Donor", "Organ Record",
    "Recipient", "Transplant Surgery",
]

SKIP_FIELDS = {
    "naming_series", "amended_from", "amendment_date",
    "currency", "conversion_rate", "exchange_rate",
    "price_list", "price_list_currency", "plc_conversion_rate",
    "price_list_exchange_rate", "base_net_total", "base_grand_total",
    "net_total", "grand_total", "base_total", "total",
    "total_taxes_and_charges", "base_total_taxes_and_charges",
    "outstanding_amount", "advance_paid", "debit_to", "credit_to",
    "status", "docstatus", "owner", "modified_by",
    "letter_head", "tc_name", "terms",
    "selling_price_list", "buying_price_list",
    "set_warehouse", "set_from_warehouse",
}

CHILD_TABLE_FIELDS = {"items", "taxes", "payment_schedule", "advances"}

# Minimum fields needed to auto-create a missing linked record
QUICK_CREATE_FIELDS = {
    "Customer":  {"customer_name": None, "customer_type": "Individual", "customer_group": "All Customer Groups", "territory": "All Territories"},
    "Supplier":  {"supplier_name": None, "supplier_group": "All Supplier Groups", "country": "India"},
    "Item":      {"item_name": None, "item_code": None, "item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 0},
    "Employee":  {"employee_name": None, "company": None, "date_of_joining": None, "gender": "Male"},
}


def handle_write(message, history, session_data, intent):
    mode = session_data.get("mode")

    if mode == "collecting_fields":
        return _continue_collection(message, history, session_data)
    if mode == "confirm_submit":
        return _handle_submit_confirm(message, session_data)
    if mode == "collecting_items":
        return _continue_items(message, session_data)
    if mode == "confirm_create_linked":
        return _handle_linked_confirm(message, session_data)
    if mode == "collecting_linked_fields":
        return _continue_linked_collection(message, session_data)

    doctype = _identify_doctype(message, intent)
    if not doctype:
        return {
            "response": (
                "Which document would you like to create? For example:\n"
                "Sales Invoice, Purchase Order, Timesheet Entry, Donor Pledge, etc."
            ),
            "type": "clarify",
            "session_data": {},
        }

    fields = _get_askable_fields(doctype)
    if not fields:
        return _create_document(doctype, {})

    first = fields[0]
    return {
        "response": f"I'll help you create a **{doctype}**.\n\n**{first['label']}**{_field_hint(first)}:",
        "type": "write_collecting",
        "session_data": {
            "mode": "collecting_fields",
            "doctype": doctype,
            "required_fields": fields,
            "collected": {},
            "current_field_index": 0,
        },
    }


def _continue_collection(message, history, session_data):
    doctype   = session_data["doctype"]
    required  = session_data["required_fields"]
    collected = session_data["collected"]
    idx       = session_data["current_field_index"]

    current = required[idx]
    value   = message.strip()

    # Validate Link fields — check if record exists
    if current["fieldtype"] == "Link" and current["options"]:
        linked_dt = current["options"]
        exists = frappe.db.exists(linked_dt, value)
        if not exists:
            # Check if we can quick-create this type
            can_create = linked_dt in QUICK_CREATE_FIELDS
            if can_create:
                return {
                    "response": (
                        f"**{linked_dt}** `{value}` was not found in the system.\n\n"
                        f"Would you like me to **create a new {linked_dt}** called `{value}`? (yes / no)\n\n"
                        f"Or type the correct name of an existing {linked_dt}."
                    ),
                    "type": "write_collecting",
                    "session_data": {
                        "mode": "confirm_create_linked",
                        "parent_session": session_data,
                        "linked_doctype": linked_dt,
                        "linked_name": value,
                        "field_being_filled": current,
                    },
                }
            else:
                return {
                    "response": (
                        f"**{linked_dt}** `{value}` was not found.\n\n"
                        f"Please enter a valid existing {linked_dt} name, or check the {linked_dt} list first."
                    ),
                    "type": "write_collecting",
                    "session_data": session_data,
                }

    # Store value and advance
    collected[current["fieldname"]] = value
    idx += 1
    session_data["current_field_index"] = idx
    session_data["collected"] = collected

    if idx >= len(required):
        if _doctype_needs_items(doctype):
            return {
                "response": (
                    "Got it! Now let's add items.\n\n"
                    "**Item** — Enter item name/code, quantity and rate "
                    "(e.g. `soap, 2, 150`):\n"
                    "Type **done** when finished."
                ),
                "type": "write_collecting",
                "session_data": {
                    "mode": "collecting_items",
                    "doctype": doctype,
                    "collected": collected,
                    "items": [],
                },
            }
        return _create_document(doctype, collected)

    nxt = required[idx]
    return {
        "response": f"Got it. **{nxt['label']}**{_field_hint(nxt)}:",
        "type": "write_collecting",
        "session_data": session_data,
    }


def _handle_linked_confirm(message, session_data):
    """Handle yes/no for creating a missing linked record."""
    msg           = message.strip().lower()
    parent        = session_data["parent_session"]
    linked_dt     = session_data["linked_doctype"]
    linked_name   = session_data["linked_name"]
    field         = session_data["field_being_filled"]

    if any(w in msg for w in ["yes", "yeah", "y", "ok", "sure", "create", "add"]):
        # Quick-create the linked record
        result = _quick_create_linked(linked_dt, linked_name, parent.get("collected", {}))
        if result["success"]:
            # Resume parent collection with the new record
            collected  = parent["collected"]
            required   = parent["required_fields"]
            idx        = parent["current_field_index"]

            collected[field["fieldname"]] = linked_name
            idx += 1
            parent["current_field_index"] = idx
            parent["collected"] = collected

            success_msg = f"✅ **{linked_dt}** `{linked_name}` created successfully!\n\n"

            if idx >= len(required):
                doctype = parent["doctype"]
                if _doctype_needs_items(doctype):
                    return {
                        "response": success_msg + "Now let's add items. Enter item name, qty and rate (e.g. `soap, 2, 150`):\nType **done** when finished.",
                        "type": "write_collecting",
                        "session_data": {
                            "mode": "collecting_items",
                            "doctype": doctype,
                            "collected": collected,
                            "items": [],
                        },
                    }
                return _create_document(doctype, collected)

            nxt = required[idx]
            return {
                "response": success_msg + f"**{nxt['label']}**{_field_hint(nxt)}:",
                "type": "write_collecting",
                "session_data": parent,
            }
        else:
            return {
                "response": f"❌ Could not create {linked_dt}: {result['error']}\n\nPlease enter an existing {linked_dt} name.",
                "type": "write_collecting",
                "session_data": parent,
            }
    else:
        # User said no — ask them to provide a valid existing record
        return {
            "response": f"OK. Please enter the name of an existing **{linked_dt}**{_field_hint(field)}:",
            "type": "write_collecting",
            "session_data": parent,
        }


def _quick_create_linked(doctype, name, parent_collected):
    """Create a linked record with minimal required fields."""
    try:
        template = QUICK_CREATE_FIELDS.get(doctype, {})
        doc_data = {"doctype": doctype}

        for fieldname, default in template.items():
            if default is None:
                # Use the name for name fields
                if "name" in fieldname:
                    doc_data[fieldname] = name
                elif fieldname == "item_code":
                    doc_data[fieldname] = name
                elif fieldname == "date_of_joining":
                    doc_data[fieldname] = _today()
                elif fieldname == "company":
                    # Get from parent collected or first company
                    doc_data[fieldname] = (
                        parent_collected.get("company") or
                        frappe.db.get_single_value("Global Defaults", "default_company") or
                        frappe.db.get_value("Company", {}, "name")
                    )
                else:
                    doc_data[fieldname] = name
            else:
                doc_data[fieldname] = default

        doc = frappe.get_doc(doc_data)
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "name": doc.name}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _continue_linked_collection(message, session_data):
    """Placeholder for future multi-field linked record creation."""
    return _handle_linked_confirm("yes", session_data)


def _continue_items(message, session_data):
    doctype   = session_data["doctype"]
    collected = session_data["collected"]
    items     = session_data.get("items", [])

    if message.strip().lower() in ("done", "finish", "complete", "that's all", "thats all", "done."):
        if not items:
            return {
                "response": "Please add at least one item before finishing.",
                "type": "write_collecting",
                "session_data": session_data,
            }
        collected["items"] = items
        return _create_document(doctype, collected)

    parts = [p.strip().strip("'\"") for p in message.split(",")]
    item_name = parts[0] if parts else message.strip()

    # Check if item exists
    item_code = None
    if frappe.db.exists("Item", item_name):
        item_code = item_name
    else:
        # Try case-insensitive search
        found = frappe.db.get_value("Item", {"item_name": ["like", f"%{item_name}%"]}, "name")
        if found:
            item_code = found
        else:
            # Offer to create
            qty  = float(parts[1]) if len(parts) >= 2 else 1
            rate = float(parts[2]) if len(parts) >= 3 else 0
            session_data["pending_item"] = {"item_name": item_name, "qty": qty, "rate": rate}
            return {
                "response": (
                    f"**Item** `{item_name}` was not found in the Items list.\n\n"
                    f"Would you like me to **create a new Item** called `{item_name}`? (yes / no)\n\n"
                    f"Or enter the correct name of an existing item."
                ),
                "type": "write_collecting",
                "session_data": {
                    "mode": "confirm_create_item",
                    "parent_items_session": session_data,
                },
            }

    qty  = float(parts[1]) if len(parts) >= 2 else 1
    rate = float(parts[2]) if len(parts) >= 3 else 0

    items.append({
        "item_code": item_code or item_name,
        "item_name": item_name,
        "qty": qty,
        "rate": rate,
        "uom": "Nos",
    })
    session_data["items"] = items

    return {
        "response": (
            f"✅ Added: **{item_name}** (qty: {qty}, rate: ₹{rate})\n\n"
            f"Add another item, or type **done** to create the document."
        ),
        "type": "write_collecting",
        "session_data": session_data,
    }


def _handle_submit_confirm(message, session_data):
    msg      = message.lower().strip()
    doctype  = session_data.get("doctype")
    doc_name = session_data.get("doc_name")

    if any(w in msg for w in ["yes", "submit", "confirm", "ok", "sure", "yeah", "y"]):
        try:
            doc = frappe.get_doc(doctype, doc_name)
            doc.submit()
            frappe.db.commit()
            return {
                "response": f"✅ **{doctype}** `{doc_name}` submitted successfully!",
                "type": "write_success",
                "session_data": {},
            }
        except Exception as e:
            err = str(e)
            # Check if error is about a missing linked record
            if "not found" in err.lower():
                item_name = _extract_missing_name(err)
                if item_name:
                    return {
                        "response": (
                            f"❌ Cannot submit — **{item_name}** was not found.\n\n"
                            f"Would you like me to create it automatically? (yes / no)"
                        ),
                        "type": "write_error",
                        "session_data": {
                            "mode": "confirm_create_linked",
                            "parent_session": {"doctype": doctype, "doc_name": doc_name, "mode": "resubmit"},
                            "linked_doctype": "Item",
                            "linked_name": item_name,
                            "field_being_filled": {"fieldname": "item_code", "fieldtype": "Link", "options": "Item", "label": "Item"},
                        },
                    }
            return {
                "response": f"❌ Could not submit: {err}",
                "type": "write_error",
                "session_data": {},
            }
    else:
        return {
            "response": f"OK, `{doc_name}` saved as draft. You can submit it later from the {doctype} list.",
            "type": "write_success",
            "session_data": {},
        }


def _extract_missing_name(error_str):
    """Extract the missing record name from an error like 'Item soap not found'."""
    import re
    m = re.search(r'Item\s+(.+?)\s+not found', error_str, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _create_document(doctype, field_data):
    try:
        doc_data = {"doctype": doctype}
        doc_data.update(field_data)

        # Fix date fields
        date_fields = ["posting_date", "transaction_date", "due_date",
                       "from_date", "to_date", "date"]
        for df in date_fields:
            if df in doc_data:
                val = str(doc_data[df]).lower().strip()
                if val in ("today", "now", "", "none"):
                    doc_data[df] = _today()
                else:
                    try:
                        doc_data[df] = str(getdate(val))
                    except Exception:
                        doc_data[df] = _today()
            elif df in ("posting_date", "transaction_date"):
                doc_data[df] = _today()

        # Handle items list
        if "items" in doc_data and isinstance(doc_data["items"], list):
            doc_data["items"] = [
                {
                    "item_code": i.get("item_code", i.get("item_name", "")),
                    "item_name": i.get("item_name", i.get("item_code", "")),
                    "qty": i.get("qty", 1),
                    "rate": i.get("rate", 0),
                    "uom": i.get("uom", "Nos"),
                }
                for i in doc_data["items"]
            ]

        doc = frappe.get_doc(doc_data)
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True, ignore_links=True)
        frappe.db.commit()

        # Build view URL
        dt_slug = doctype.lower().replace(" ", "-")
        view_url = f"/app/{dt_slug}/{doc.name}"

        return {
            "response": (
                f"✅ **{doctype}** created successfully!\n\n"
                f"**Document ID:** `{doc.name}`\n"
                f"**View:** [{doc.name}]({view_url})\n\n"
                f"Would you like to **submit** this document? (yes / no)"
            ),
            "type": "write_success",
            "session_data": {
                "mode": "confirm_submit",
                "doctype": doctype,
                "doc_name": doc.name,
            },
        }
    except Exception as e:
        return {
            "response": f"❌ Could not create {doctype}: {str(e)}",
            "type": "write_error",
            "session_data": {},
        }


def _doctype_needs_items(doctype):
    return doctype in (
        "Sales Invoice", "Purchase Invoice", "Sales Order",
        "Purchase Order", "Delivery Note", "Purchase Receipt",
        "Quotation", "Stock Entry",
    )


def _get_askable_fields(doctype):
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        return []

    fields = []
    for f in meta.fields:
        if f.fieldtype in ("Section Break", "Column Break", "HTML",
                           "Fold", "Heading", "Tab Break", "Button", "Image"):
            continue
        if f.fieldname in SKIP_FIELDS:
            continue
        if f.fieldname in CHILD_TABLE_FIELDS:
            continue
        if f.read_only and not f.reqd:
            continue
        if f.default and not f.reqd:
            continue
        if f.reqd or f.fieldname in ("customer", "supplier", "employee",
                                      "posting_date", "transaction_date",
                                      "item_code", "qty", "rate"):
            fields.append({
                "fieldname": f.fieldname,
                "label": f.label or f.fieldname.replace("_", " ").title(),
                "fieldtype": f.fieldtype,
                "required": bool(f.reqd),
                "options": f.options or "",
                "default": f.default or "",
            })
    return fields


def _identify_doctype(message, intent):
    if intent.get("doctypes"):
        return intent["doctypes"][0]

    msg_lower = message.lower()
    for dt in KNOWN_DOCTYPES:
        if dt.lower() in msg_lower:
            return dt

    try:
        result = call_ollama([
            {
                "role": "system",
                "content": (
                    "Return ONLY the exact Frappe DocType name from this list:\n"
                    + ", ".join(KNOWN_DOCTYPES)
                    + "\nReturn ONLY the name, nothing else."
                ),
            },
            {"role": "user", "content": message},
        ])
        result = result.strip()
        if result in KNOWN_DOCTYPES:
            return result
    except Exception:
        pass
    return None


def _field_hint(field):
    ft = field.get("fieldtype", "") if isinstance(field, dict) else field.fieldtype
    opts = field.get("options", "") if isinstance(field, dict) else (field.options or "")
    if ft == "Date":
        return f" (YYYY-MM-DD, today is {_today()})"
    if ft == "Link" and opts:
        return f" (existing {opts} name)"
    if ft == "Select" and opts:
        choices = [o for o in opts.split("\n") if o][:5]
        return f" ({', '.join(choices)})"
    return ""
