import frappe
from frappe.utils import today as _today, getdate
from erp_assistant.erp_assistant.api.ollama import call_ollama
from erp_assistant.erp_assistant.api.permissions import can_submit, get_role_level

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

QUICK_CREATE_FIELDS = {
    "Customer": {
        "customer_name": None,
        "customer_type": "Individual",
        "customer_group": "All Customer Groups",
        "territory": "All Territories"
    },
    "Supplier": {
        "supplier_name": None,
        "supplier_group": "All Supplier Groups",
        "country": "India"
    },
    "Employee": {
        "employee_name": None,
        "company": None,
        "date_of_joining": None,
        "gender": "Male"
    },
}

# Fields to collect when creating a new Item
ITEM_CREATION_FIELDS = [
    {"fieldname": "item_name",   "label": "Item Name",   "fieldtype": "Data",   "hint": ""},
    {"fieldname": "item_group",  "label": "Item Group",  "fieldtype": "Link",   "hint": " (e.g. Products, Services, Raw Materials, All Item Groups)"},
    {"fieldname": "stock_uom",   "label": "Unit of Measure", "fieldtype": "Data", "hint": " (e.g. Nos, Kg, Litre, Box, Metre)"},
    {"fieldname": "standard_rate", "label": "Standard Rate", "fieldtype": "Currency", "hint": " (default selling price per unit)"},
    {"fieldname": "description", "label": "Description", "fieldtype": "Text",   "hint": " (optional, press Enter to skip)"},
]

# Redo keywords
REDO_KEYWORDS = {"redo", "change", "wrong", "mistake", "back", "oops", "fix", "edit", "modify", "update", "incorrect"}
RESTART_KEYWORDS = {"restart", "start over", "start again", "reset", "begin again", "cancel", "abort"}


def handle_write(message, history, session_data, intent):
    mode = session_data.get("mode")

    # ── Redo / restart detection ─────────────────────────────────
    msg_lower = message.lower().strip()

    if mode in ("collecting_fields", "collecting_items") and any(k in msg_lower for k in RESTART_KEYWORDS):
        return {
            "response": (
                f"OK, starting over! I'll keep the info you already entered.\n\n"
                f"Previously collected: {_summarise_collected(session_data)}\n\n"
                f"Type **keep** to reuse everything, or tell me what to change, "
                f"or type **fresh** to start completely from scratch."
            ),
            "type": "write_collecting",
            "session_data": {
                "mode": "confirm_restart",
                "previous_session": session_data,
            },
        }

    if mode == "confirm_restart":
        return _handle_restart_confirm(message, session_data)

    if mode in ("collecting_fields",) and any(k in msg_lower for k in REDO_KEYWORDS):
        return _handle_redo(message, session_data)

    # ── Normal routing ───────────────────────────────────────────
    if mode == "collecting_fields":
        return _continue_collection(message, history, session_data)
    if mode == "confirm_submit":
        return _handle_submit_confirm(message, session_data)
    if mode == "collecting_items":
        return _continue_items(message, session_data)
    if mode == "confirm_create_linked":
        return _handle_linked_confirm(message, session_data)
    if mode == "creating_new_item":
        return _continue_item_creation(message, session_data)
    if mode == "confirm_create_item":
        return _handle_item_creation_confirm(message, session_data)

    # ── New document ─────────────────────────────────────────────
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
        "response": (
            f"I'll help you create a **{doctype}**.\n\n"
            f"💡 _Tip: At any point say **'change [field]'** to correct a previous answer, "
            f"or **'start over'** to restart._\n\n"
            f"**{first['label']}**{_field_hint(first)}:"
        ),
        "type": "write_collecting",
        "session_data": {
            "mode": "collecting_fields",
            "doctype": doctype,
            "required_fields": fields,
            "collected": {},
            "current_field_index": 0,
        },
    }


# ── Redo helpers ─────────────────────────────────────────────────────────────

def _summarise_collected(session_data):
    collected = session_data.get("collected", {})
    if not collected:
        return "nothing yet"
    return ", ".join(f"**{k}**: {v}" for k, v in collected.items())


def _handle_redo(message, session_data):
    """Let user change a previously entered field."""
    msg_lower = message.lower()
    collected = session_data.get("collected", {})
    required = session_data.get("required_fields", [])

    # Find which field they want to change
    target_field = None
    target_idx = None
    for i, f in enumerate(required):
        if f["fieldname"] in msg_lower or f["label"].lower() in msg_lower:
            target_field = f
            target_idx = i
            break

    if not target_field:
        # Show what's been collected and ask which to change
        summary = _summarise_collected(session_data)
        return {
            "response": (
                f"Which field would you like to change?\n\n"
                f"Currently entered: {summary}\n\n"
                f"Say **'change [field name]'** e.g. 'change customer' or 'change date'"
            ),
            "type": "write_collecting",
            "session_data": session_data,
        }

    # Remove the field from collected and go back to it
    collected.pop(target_field["fieldname"], None)
    session_data["collected"] = collected
    session_data["current_field_index"] = target_idx

    return {
        "response": f"Sure! Let's redo **{target_field['label']}**{_field_hint(target_field)}:",
        "type": "write_collecting",
        "session_data": session_data,
    }


def _handle_restart_confirm(message, session_data):
    msg_lower = message.lower().strip()
    prev = session_data.get("previous_session", {})

    if "fresh" in msg_lower:
        # Complete restart
        doctype = prev.get("doctype")
        fields = _get_askable_fields(doctype)
        first = fields[0] if fields else None
        return {
            "response": f"Starting fresh! **{first['label']}**{_field_hint(first)}:" if first else "OK, starting over.",
            "type": "write_collecting",
            "session_data": {
                "mode": "collecting_fields",
                "doctype": doctype,
                "required_fields": fields,
                "collected": {},
                "current_field_index": 0,
            },
        }
    elif "keep" in msg_lower:
        # Resume from where we left off
        return {
            "response": (
                f"Resuming with your previous answers: {_summarise_collected(prev)}\n\n"
                f"What would you like to change? Or say **done** to continue."
            ),
            "type": "write_collecting",
            "session_data": prev,
        }
    else:
        # They said what to change
        return _handle_redo(message, prev)


# ── Field collection ──────────────────────────────────────────────────────────

def _continue_collection(message, history, session_data):
    doctype   = session_data["doctype"]
    required  = session_data["required_fields"]
    collected = session_data["collected"]
    idx       = session_data["current_field_index"]
    current   = required[idx]
    value     = message.strip()

    # Validate Link fields
    if current["fieldtype"] == "Link" and current["options"]:
        linked_dt = current["options"]
        exists = frappe.db.exists(linked_dt, value)
        if not exists:
            can_create = linked_dt in QUICK_CREATE_FIELDS
            if can_create:
                return {
                    "response": (
                        f"**{linked_dt}** `{value}` was not found.\n\n"
                        f"Would you like me to **create a new {linked_dt}** called `{value}`? (yes / no)\n\n"
                        f"Or type the name of an existing {linked_dt}."
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
                        f"Please enter a valid existing {linked_dt} name."
                    ),
                    "type": "write_collecting",
                    "session_data": session_data,
                }

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
                    "Type **done** when finished adding items."
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


# ── Item collection ───────────────────────────────────────────────────────────

def _continue_items(message, session_data):
    doctype   = session_data["doctype"]
    collected = session_data["collected"]
    items     = session_data.get("items", [])
    msg       = message.strip()
    msg_lower = msg.lower()

    # Done
    if msg_lower in ("done", "finish", "complete", "that's all", "thats all", "done.", "done!"):
        if not items:
            return {
                "response": "Please add at least one item before finishing.",
                "type": "write_collecting",
                "session_data": session_data,
            }
        collected["items"] = items
        return _create_document(doctype, collected)

    # Redo last item
    if msg_lower in ("undo", "remove last", "delete last"):
        if items:
            removed = items.pop()
            session_data["items"] = items
            item_list = "\n".join([f"- {i['item_name']} (qty: {i['qty']}, rate: ₹{i['rate']})" for i in items])
            return {
                "response": (
                    f"Removed **{removed['item_name']}**.\n\n"
                    + (f"Current items:\n{item_list}\n\n" if items else "No items yet.\n\n")
                    + "Add another item or type **done**."
                ),
                "type": "write_collecting",
                "session_data": session_data,
            }

    # Parse item entry
    parts = [p.strip().strip("'\"") for p in msg.split(",")]
    item_name = parts[0] if parts else msg

    qty  = 1.0
    rate = 0.0
    if len(parts) >= 2:
        try: qty = float(parts[1])
        except: pass
    if len(parts) >= 3:
        try: rate = float(parts[2])
        except: pass

    # Check if item exists
    item_code = None
    if frappe.db.exists("Item", item_name):
        item_code = item_name
    else:
        found = frappe.db.get_value("Item", {"item_name": ["like", f"%{item_name}%"]}, ["name", "item_name", "standard_rate"], as_dict=True)
        if found:
            item_code = found.name
            if rate == 0 and found.standard_rate:
                rate = found.standard_rate
        else:
            # Item not found — offer to create it
            return {
                "response": (
                    f"**Item** `{item_name}` was not found in the Items master.\n\n"
                    f"Would you like me to **create a new Item** called `{item_name}`? (yes / no)\n\n"
                    f"If yes, I'll collect the item details before adding it to the invoice.\n"
                    f"Or enter the correct name of an existing item."
                ),
                "type": "write_collecting",
                "session_data": {
                    "mode": "confirm_create_item",
                    "item_name": item_name,
                    "qty": qty,
                    "rate": rate,
                    "parent_items_session": session_data,
                },
            }

    items.append({
        "item_code": item_code or item_name,
        "item_name": item_name,
        "qty": qty,
        "rate": rate,
        "uom": "Nos",
    })
    session_data["items"] = items

    item_list = "\n".join([f"- {i['item_name']} (qty: {i['qty']}, ₹{i['rate']})" for i in items])
    return {
        "response": (
            f"✅ Added: **{item_name}** (qty: {qty}, rate: ₹{rate})\n\n"
            f"**Items so far:**\n{item_list}\n\n"
            f"Add another item, type **undo** to remove last, or **done** to create the document."
        ),
        "type": "write_collecting",
        "session_data": session_data,
    }


# ── Item creation flow ────────────────────────────────────────────────────────

def _handle_item_creation_confirm(message, session_data):
    msg_lower = message.strip().lower()
    item_name = session_data["item_name"]
    qty       = session_data["qty"]
    rate      = session_data["rate"]
    parent    = session_data["parent_items_session"]

    if any(w in msg_lower for w in ["yes", "yeah", "y", "ok", "sure", "create", "add"]):
        # Start collecting item details
        first = ITEM_CREATION_FIELDS[0]
        return {
            "response": (
                f"Great! Let's set up the new item **{item_name}**.\n\n"
                f"**{first['label']}**{first['hint']}:\n"
                f"_(Press Enter or type 'skip' for optional fields)_"
            ),
            "type": "write_collecting",
            "session_data": {
                "mode": "creating_new_item",
                "new_item_name": item_name,
                "new_item_qty": qty,
                "new_item_rate": rate,
                "item_fields": ITEM_CREATION_FIELDS,
                "item_collected": {"item_code": item_name},
                "item_field_index": 0,
                "parent_items_session": parent,
            },
        }
    else:
        # User said no — ask for existing item
        return {
            "response": "OK. Please enter the name of an existing item (or a different item name):",
            "type": "write_collecting",
            "session_data": parent,
        }


def _continue_item_creation(message, session_data):
    """Collect item fields one by one then create the Item record."""
    fields      = session_data["item_fields"]
    collected   = session_data["item_collected"]
    idx         = session_data["item_field_index"]
    item_name   = session_data["new_item_name"]
    qty         = session_data["new_item_qty"]
    rate        = session_data["new_item_rate"]
    parent      = session_data["parent_items_session"]

    current = fields[idx]
    value   = message.strip()

    # Handle skip for optional fields
    if value.lower() in ("skip", "", "none", "-"):
        value = None
    
    if value:
        collected[current["fieldname"]] = value
        # If they gave us a rate, use it for the invoice too
        if current["fieldname"] == "standard_rate":
            try:
                rate = float(value)
                session_data["new_item_rate"] = rate
            except:
                pass

    idx += 1
    session_data["item_field_index"] = idx
    session_data["item_collected"] = collected

    # All fields collected — create the item
    if idx >= len(fields):
        result = _create_item_record(collected, item_name)
        if result["success"]:
            # Add the new item to the invoice items list
            items = parent.get("items", [])
            items.append({
                "item_code": result["item_code"],
                "item_name": item_name,
                "qty": qty,
                "rate": rate or float(collected.get("standard_rate", 0) or 0),
                "uom": collected.get("stock_uom", "Nos"),
            })
            parent["items"] = items

            item_list = "\n".join([f"- {i['item_name']} (qty: {i['qty']}, ₹{i['rate']})" for i in items])
            return {
                "response": (
                    f"✅ Item **{item_name}** created successfully!\n\n"
                    f"**Items so far:**\n{item_list}\n\n"
                    f"Add another item or type **done** to create the document."
                ),
                "type": "write_collecting",
                "session_data": parent,
            }
        else:
            return {
                "response": (
                    f"❌ Could not create item: {result['error']}\n\n"
                    "Please try a different item name or check the details."
                ),
                "type": "write_error",
                "session_data": parent,
            }

    # Ask next field
    nxt = fields[idx]
    return {
        "response": f"**{nxt['label']}**{nxt['hint']}:",
        "type": "write_collecting",
        "session_data": session_data,
    }


def _create_item_record(collected, item_name):
    """Create a new Item in the Items master."""
    try:
        item_code = collected.get("item_code", item_name)

        # Check if item_group exists, fallback to "All Item Groups"
        item_group = collected.get("item_group", "All Item Groups")
        if not frappe.db.exists("Item Group", item_group):
            item_group = "All Item Groups"

        doc_data = {
            "doctype": "Item",
            "item_code": item_code,
            "item_name": collected.get("item_name", item_name),
            "item_group": item_group,
            "stock_uom": collected.get("stock_uom", "Nos"),
            "is_stock_item": 0,
            "description": collected.get("description", ""),
        }

        if collected.get("standard_rate"):
            try:
                doc_data["standard_rate"] = float(collected["standard_rate"])
            except:
                pass

        doc = frappe.get_doc(doc_data)
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return {"success": True, "item_code": doc.name}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Linked record creation ────────────────────────────────────────────────────

def _handle_linked_confirm(message, session_data):
    msg_lower     = message.strip().lower()
    parent        = session_data["parent_session"]
    linked_dt     = session_data["linked_doctype"]
    linked_name   = session_data["linked_name"]
    field         = session_data["field_being_filled"]

    if any(w in msg_lower for w in ["yes", "yeah", "y", "ok", "sure", "create", "add"]):
        result = _quick_create_linked(linked_dt, linked_name, parent.get("collected", {}))
        if result["success"]:
            collected = parent["collected"]
            required  = parent["required_fields"]
            idx       = parent["current_field_index"]

            collected[field["fieldname"]] = linked_name
            idx += 1
            parent["current_field_index"] = idx
            parent["collected"] = collected

            success_msg = f"✅ **{linked_dt}** `{linked_name}` created!\n\n"

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
        return {
            "response": f"OK. Please enter the name of an existing **{linked_dt}**{_field_hint(field)}:",
            "type": "write_collecting",
            "session_data": parent,
        }


def _quick_create_linked(doctype, name, parent_collected):
    try:
        template = QUICK_CREATE_FIELDS.get(doctype, {})
        doc_data = {"doctype": doctype}
        for fieldname, default in template.items():
            if default is None:
                if "name" in fieldname:
                    doc_data[fieldname] = name
                elif fieldname == "item_code":
                    doc_data[fieldname] = name
                elif fieldname == "date_of_joining":
                    doc_data[fieldname] = _today()
                elif fieldname == "company":
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


# ── Submit confirmation ───────────────────────────────────────────────────────


def _notify_manager_for_submit(doctype, doc_name):
    """Send a Frappe notification to Store Managers and Admins to review."""
    try:
        import frappe
        # Find users with Store Manager or System Manager role
        managers = frappe.db.sql("""
            SELECT DISTINCT u.name, u.full_name
            FROM `tabUser` u
            JOIN `tabHas Role` r ON r.parent = u.name
            WHERE r.role IN ('Store Manager', 'Sales Manager', 'System Manager')
            AND u.enabled = 1
            AND u.name != 'Administrator'
            AND u.name != %s
        """, frappe.session.user, as_dict=True)

        dt_slug  = doctype.lower().replace(" ", "-")
        view_url = f"/app/{dt_slug}/{doc_name}"
        submitter = frappe.get_value("User", frappe.session.user, "full_name") or frappe.session.user

        for manager in managers:
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": f"Review & Submit Request: {doctype} {doc_name}",
                "email_content": (
                    f"<p><b>{submitter}</b> has created <b>{doctype}</b> "
                    f"<a href='{view_url}'>{doc_name}</a> and requires your approval to submit.</p>"
                    f"<p><a href='{view_url}'>Click here to review</a></p>"
                ),
                "for_user": manager.name,
                "type": "Alert",
                "document_type": doctype,
                "document_name": doc_name,
            }).insert(ignore_permissions=True)

        frappe.db.commit()
    except Exception as e:
        frappe.log_error(str(e), "BizBot Submit Notification Error")


def _handle_submit_confirm(message, session_data):
    msg      = message.lower().strip()
    doctype  = session_data.get("doctype")
    doc_name = session_data.get("doc_name")

    if any(w in msg for w in ["yes", "submit", "confirm", "ok", "sure", "yeah", "y"]):
        # Permission check
        if not can_submit():
            role = get_role_level().replace("_", " ").title()
            _notify_manager_for_submit(doctype, doc_name)
            return {
                "response": (
                    "Your role (" + role + ") cannot submit documents.\n\n"
                    "**" + str(doctype) + "** `" + str(doc_name) + "` saved as draft.\n\n"
                    "Your Store Manager has been notified to review and submit it."
                ),
                "type": "write_success",
                "session_data": {},
            }
        # Permission check
        # Permission check
        if not can_submit():
            role = get_role_level().replace("_", " ").title()
            _notify_manager_for_submit(doctype, doc_name)
            return {
                "response": (
                    "Your role (" + role + ") cannot submit documents.\n\n"
                    "**" + (doctype or "") + "** `" + (doc_name or "") + "` saved as draft.\n\n"
                    "Your Store Manager has been notified to review and submit it."
                ),
                "type": "write_success",
                "session_data": {},
            }
        try:
            doc = frappe.get_doc(doctype, doc_name)
            doc.submit()
            frappe.db.commit()
            dt_slug  = doctype.lower().replace(" ", "-")
            view_url = f"/app/{dt_slug}/{doc_name}"
            return {
                "response": (
                    f"✅ **{doctype}** [`{doc_name}` ↗]({view_url}) submitted successfully!"
                ),
                "type": "write_success",
                "session_data": {},
            }
        except Exception as e:
            err = str(e)
            if "not found" in err.lower():
                item_name = _extract_missing_name(err)
                if item_name:
                    return {
                        "response": (
                            f"❌ Cannot submit — **{item_name}** was not found in Items master.\n\n"
                            f"Would you like me to create it? (yes / no)"
                        ),
                        "type": "write_error",
                        "session_data": {
                            "mode": "confirm_create_item",
                            "item_name": item_name,
                            "qty": 1,
                            "rate": 0,
                            "parent_items_session": {
                                "mode": "resubmit",
                                "doctype": doctype,
                                "doc_name": doc_name,
                                "items": [],
                                "collected": {},
                            },
                        },
                    }
            return {
                "response": f"❌ Could not submit: {err}",
                "type": "write_error",
                "session_data": {},
            }
    else:
        dt_slug  = doctype.lower().replace(" ", "-")
        view_url = f"/app/{dt_slug}/{doc_name}"
        return {
            "response": (
                f"OK, saved as draft. View it here: [`{doc_name}` ↗]({view_url})"
            ),
            "type": "write_success",
            "session_data": {},
        }


def _extract_missing_name(error_str):
    import re
    m = re.search(r'Item\s+(.+?)\s+not found', error_str, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


# ── Document creation ─────────────────────────────────────────────────────────

def _create_document(doctype, field_data):
    try:
        doc_data = {"doctype": doctype}
        doc_data.update(field_data)

        # Fix date fields
        for df in ["posting_date", "transaction_date", "due_date", "from_date", "to_date", "date"]:
            if df in doc_data:
                val = str(doc_data[df]).lower().strip()
                if val in ("today", "now", "", "none"):
                    doc_data[df] = _today()
                else:
                    try:
                        doc_data[df] = str(getdate(val))
                    except:
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

        dt_slug  = doctype.lower().replace(" ", "-")
        view_url = f"/app/{dt_slug}/{doc.name}"

        return {
            "response": (
                f"✅ **{doctype}** created!\n\n"
                f"**Document ID:** [`{doc.name}` ↗]({view_url})\n\n"
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _doctype_needs_items(doctype):
    return doctype in (
        "Sales Invoice", "Purchase Invoice", "Sales Order",
        "Purchase Order", "Delivery Note", "Purchase Receipt",
        "Quotation", "Stock Entry",
    )


def _get_askable_fields(doctype):
    try:
        meta = frappe.get_meta(doctype)
    except:
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
    except:
        pass
    return None


def _field_hint(field):
    ft   = field.get("fieldtype", "") if isinstance(field, dict) else field.fieldtype
    opts = field.get("options", "")   if isinstance(field, dict) else (field.options or "")
    if ft == "Date":
        return f" (YYYY-MM-DD, today is {_today()})"
    if ft == "Link" and opts:
        return f" (existing {opts} name)"
    if ft == "Select" and opts:
        choices = [o for o in opts.split("\n") if o][:5]
        return f" ({', '.join(choices)})"
    return ""
