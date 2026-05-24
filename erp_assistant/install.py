import frappe


def after_install():
    """Run after app installation."""
    frappe.clear_cache()
    print("✅ ERP Assistant installed successfully")
    print("   Make sure Ollama is running: ollama serve &")
    print("   Model: qwen2.5:3b")
