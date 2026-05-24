import frappe


@frappe.whitelist()
def get_page_data():
    return {"status": "ok"}
