# BizBot (BB) — AI-Powered ERP Assistant for Frappe/ERPNext

![BizBot](https://img.shields.io/badge/BizBot-BB-00e5a0?style=for-the-badge)
![Frappe](https://img.shields.io/badge/Frappe-v15-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

BizBot is an AI-powered conversational assistant that lives inside your Frappe/ERPNext instance. It appears as a floating **BB** button on every page of your ERP — click it and chat with your data in plain English.

No separate tools. No switching tabs. No training required.

---

## What BizBot Can Do

### 📊 Query Your ERP Data
Ask questions in plain English and get instant answers with data tables:
- *"Show me sales invoices this month"*
- *"List top 5 customers by revenue"*
- *"Show all overdue invoices"*
- *"What is our current stock summary?"*
- *"How many organ donor pledges were registered this quarter?"*

### 📝 Create Documents Conversationally
BizBot guides you through document creation step by step:
- *"Create a new sales invoice"* → BB asks for customer, date, items one by one
- *"Register a new donor pledge"*
- *"Create a purchase order for supplier X"*
- *"File a new timesheet entry"*

If a customer, item, or linked record doesn't exist, BB offers to create it inline without breaking your flow.

### 📈 Analytics & Comparisons
- *"Compare this month vs last month sales"*
- *"How did we do this year vs last year?"*
- *"What is our best selling item?"*
- *"Show grant utilization vs budget"*

### 🔗 Clickable Document Links
Every document ID in the chat (e.g. `ACC-SINV-2026-00001`) is a clickable link that opens directly in ERPNext — no searching, no copying IDs.

### 🌐 Context Aware
BizBot knows which page you're on. If you're viewing the Sales Invoice list and ask "show me these", it knows what you mean.

### ⚡ Powered by Groq + Llama 3.3 70B
Responses in 1–3 seconds. Far faster and more accurate than local models.

### 🔒 Privacy First
Only your database schema (table/field names) is sent to the AI — never your actual data. Query results are processed entirely on your server.

---

## Supported Modules

BizBot works across **all installed Frappe/ERPNext modules** including:

| App | Key DocTypes |
|-----|-------------|
| ERPNext (Core) | Sales Invoice, Purchase Invoice, Sales Order, Purchase Order, Customer, Supplier, Item, Employee, Payment Entry, Journal Entry |
| RetailEdge | Weigh Label, Store Profile, POS Invoice |
| EnergyEdge | Power Plant, Generation Log, Energy Bill, Fuel Receipt |
| CivicEdge | Grant, Donor, Fund, Beneficiary, Program |
| MuseumEdge | Artifact, Exhibition, Loan, Conservation Record |
| ProEdge | Client, Engagement, Timesheet Entry, Fee Note |
| LifeEdge | Donor Pledge, Deceased Donor, Organ Record, Recipient, Transplant Surgery |

---

## Requirements

- Frappe/ERPNext **v15**
- Python **3.10+**
- A **Groq API key** — free tier available at [console.groq.com](https://console.groq.com/keys)
  - Free tier: 14,400 requests/day, 30 requests/minute
  - No credit card required for free tier

---

## Installation

### Step 1 — Get the app

```bash
cd ~/frappe-bench
bench get-app https://github.com/kevin-kuriakose/BizBot.git
```

### Step 2 — Install on your site

```bash
bench --site yoursite.local install-app erp_assistant
```

### Step 3 — Set your Groq API key

```bash
bench --site yoursite.local set-config groq_api_key YOUR_GROQ_API_KEY
```

Get your free Groq API key at: https://console.groq.com/keys

### Step 4 — Migrate and restart

```bash
bench --site yoursite.local migrate
bench restart
```

### Step 5 — Access BizBot

Open your ERPNext site. You will see a green **BB** button in the bottom-right corner of every page. Click it to start chatting.

---

## Usage Examples

Once installed, click the **BB** button on any page and try:
Show me sales invoices this month
List all customers
Show overdue invoices
Create a new sales invoice
Compare this month vs last month revenue
What is our best selling item?
How many active employees do we have?
Create a purchase order for supplier Tata Group

---

## Architecture
Browser (Frappe Desk)
↓  frappe.call()
erp_assistant/api/chat.py        ← Main router
↓
intent.py                        ← Classifies: read / write / analytics / help
↓
┌─────────────┬──────────────┬─────────────────┐
│ handle_read │ handle_write │ handle_analytics │
│ (SQL gen)   │ (doc create) │ (multi-query)    │
└─────────────┴──────────────┴─────────────────┘
↓
ollama.py → Groq API (Llama 3.3 70B)
↓
query.py → MariaDB (frappe.db.sql)
↓
Response → Chat UI (Frappe Dialog)

---

## File Structure
erp_assistant/
├── erp_assistant/
│   ├── api/
│   │   ├── chat.py          # Main chat endpoint & handlers
│   │   ├── ollama.py        # Groq API client
│   │   ├── intent.py        # Intent classifier
│   │   ├── query.py         # Safe SQL executor
│   │   ├── schema.py        # DocType schema extractor
│   │   └── document.py      # Document creation handler
│   └── page/
│       └── erp_chat/        # Dedicated chat page (optional)
├── public/
│   ├── js/erp_assistant.js  # Floating BB widget (injected on all pages)
│   └── css/erp_assistant.css
└── hooks.py                 # Frappe hooks

---

## Configuration

### Changing the AI Model

BizBot uses `llama-3.3-70b-versatile` by default. To use a different Groq model:

```python
# Edit: erp_assistant/erp_assistant/api/ollama.py
MODEL = "llama-3.3-70b-versatile"  # Change this line
```

Available Groq models (as of 2026):
- `llama-3.3-70b-versatile` ← recommended
- `llama-3.1-70b-versatile`
- `mixtral-8x7b-32768` (faster, longer context)
- `gemma2-9b-it` (fastest, smaller)

---

## Changing the API Key

If you need to update or replace your Groq API key:

### Option 1 — Using bench (recommended)

```bash
bench --site yoursite.local set-config groq_api_key YOUR_NEW_API_KEY
bench restart
```

No code changes needed. The key is stored in your site's `site_config.json`.

### Option 2 — Directly in site_config.json

```bash
# File location: ~/frappe-bench/sites/yoursite.local/site_config.json
# Add or update this line:
{
  "groq_api_key": "YOUR_NEW_API_KEY"
}
```

Then restart bench:
```bash
bench restart
```

### Option 3 — Hardcode in code (not recommended for production)

```python
# Edit: erp_assistant/erp_assistant/api/ollama.py
GROQ_API_KEY = "your_key_here"
```

Then reinstall and restart:
```bash
pip install -e apps/erp_assistant
bench restart
```

### Getting a new Groq API key

1. Go to https://console.groq.com/keys
2. Click **Create API Key**
3. Copy the key (starts with `gsk_...`)
4. Apply using Option 1 above

---

## Troubleshooting

**BB button not appearing**
- Hard refresh: Ctrl+Shift+R
- Make sure you're logged in (not guest)
- Run: `bench --site yoursite.local clear-cache && bench restart`

**"Groq rate limit reached"**
- Free tier limit: 30 requests/minute
- Wait 60 seconds and try again
- Upgrade to Groq paid tier for higher limits

**"Groq API key not configured"**
- Run: `bench --site yoursite.local set-config groq_api_key YOUR_KEY`

**No records found for queries**
- Your ERPNext database may be empty — add some test data first
- Try more specific queries: "show me all customers" instead of "show me data"

**Document creation errors**
- Ensure the linked records exist (Customer, Item, etc.)
- BizBot will offer to create missing records automatically

---

## Contributing

Pull requests welcome. For major changes, open an issue first.

---

## License

MIT License — free to use, modify, and distribute.

---

## Built By

**BizAxl** — Built for modern ERP teams who want to talk to their data.

> *"If you can describe what you want in plain English, you can use the ERP."*
