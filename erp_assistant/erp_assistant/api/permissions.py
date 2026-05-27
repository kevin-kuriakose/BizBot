import frappe

# ── Role definitions ──────────────────────────────────────────────────────────

ADMIN_ROLES = {"System Manager", "Administrator"}

STORE_MANAGER_ROLES = {"Store Manager", "Sales Manager", "Accounts Manager"}

SALES_USER_ROLES = {"Sales User", "Sales Person"}

# Modules each role can access
# Admin sees everything — not listed here, handled by is_admin()
STORE_MANAGER_MODULES = {
    "retail_erp", "erpnext",  # core sales modules
}

SALES_USER_MODULES = {
    "retail_erp",  # only RetailEdge
}

# DocTypes each role can CREATE
SALES_USER_ALLOWED_CREATE = {
    "Sales Invoice", "Customer", "Quotation",
    "POS Invoice", "Weigh Label",
}

STORE_MANAGER_ALLOWED_CREATE = {
    "Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order",
    "Customer", "Supplier", "Quotation", "Delivery Note",
    "Purchase Receipt", "POS Invoice", "Weigh Label", "Store Profile",
    "Payment Entry", "Stock Entry",
}

# Actions that require Store Manager or above
SUBMIT_ROLES = ADMIN_ROLES | STORE_MANAGER_ROLES


def get_user_roles():
    """Return set of current user's roles."""
    return set(frappe.get_roles(frappe.session.user))


def is_admin(roles=None):
    roles = roles or get_user_roles()
    return bool(roles & ADMIN_ROLES) or frappe.session.user == "Administrator"


def is_store_manager(roles=None):
    roles = roles or get_user_roles()
    return bool(roles & STORE_MANAGER_ROLES)


def is_sales_user(roles=None):
    roles = roles or get_user_roles()
    return bool(roles & SALES_USER_ROLES)


def can_submit(roles=None):
    roles = roles or get_user_roles()
    return bool(roles & SUBMIT_ROLES)


def can_create(doctype, roles=None):
    roles = roles or get_user_roles()
    if is_admin(roles):
        return True
    if is_store_manager(roles):
        return doctype in STORE_MANAGER_ALLOWED_CREATE
    if is_sales_user(roles):
        return doctype in SALES_USER_ALLOWED_CREATE
    return False


def get_allowed_modules(roles=None):
    """Return list of app modules this user can query."""
    roles = roles or get_user_roles()
    if is_admin(roles):
        return None  # None means all modules
    if is_store_manager(roles):
        return STORE_MANAGER_MODULES
    if is_sales_user(roles):
        return SALES_USER_MODULES
    return set()  # empty = no access


def get_role_level(roles=None):
    """Return string: admin / store_manager / sales_user / none"""
    roles = roles or get_user_roles()
    if is_admin(roles):
        return "admin"
    if is_store_manager(roles):
        return "store_manager"
    if is_sales_user(roles):
        return "sales_user"
    return "none"


@frappe.whitelist(allow_guest=False)
def get_user_permissions():
    """
    Called by frontend JS to get current user's permission level.
    Returns what chips/features to show.
    """
    roles      = get_user_roles()
    role_level = get_role_level(roles)

    return {
        "role_level":   role_level,
        "can_submit":   can_submit(roles),
        "can_create":   True if role_level != "none" else False,
        "is_admin":     is_admin(roles),
        "modules":      list(get_allowed_modules(roles)) if get_allowed_modules(roles) else "all",
        "user":         frappe.session.user,
    }
