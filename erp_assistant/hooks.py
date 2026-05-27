app_name = "erp_assistant"
app_title = "ERP Assistant"
app_publisher = "BizAxl"
app_description = "AI-powered ERP Assistant using local Ollama LLM"
app_email = "dev@bizaxl.com"
app_license = "MIT"
app_version = "0.0.1"

required_apps = ["frappe", "bizaxl_erp"]

app_include_css = "/assets/erp_assistant/css/erp_assistant.css"
app_include_js = "/assets/erp_assistant/js/erp_assistant.js"

doc_events = {}

scheduler_events = {
    "daily": [],
    "weekly": [],
}

fixtures = []

override_doctype_class = {}


website_context = {}
boot_session = "erp_assistant.erp_assistant.boot.boot_session"
