import httpx
import frappe

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = "YOUR_GROQ_API_KEY_HERE"
MODEL = "llama-3.3-70b-versatile"
TIMEOUT = 60.0  # Groq is fast — 60s is more than enough


def call_ollama(messages, model=MODEL):
    """
    Call Groq API and return response text.
    Drop-in replacement for the Ollama call — same interface.
    """
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {frappe.conf.get('groq_api_key', GROQ_API_KEY)}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 1024,
                    "temperature": 0.1,  # Low temp for consistent SQL
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        frappe.throw("Groq API request timed out. Please try again.")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            frappe.throw("Groq rate limit reached. Please wait a moment and try again.")
        elif e.response.status_code == 401:
            frappe.throw("Groq API key invalid. Please check your API key.")
        else:
            frappe.throw(f"Groq API error: {e.response.status_code}")
    except Exception as e:
        frappe.throw(f"Groq error: {str(e)}")


@frappe.whitelist(allow_guest=False)
def test_connection():
    """Test endpoint called by the UI."""
    try:
        result = call_ollama([
            {"role": "user", "content": "Reply with only the word: ready"}
        ])
        return {
            "status": "ok",
            "message": f"✅ Groq API connected | Model: {MODEL} | Response: {result.strip()}",
        }
    except Exception as e:
        return {"status": "error", "message": f"❌ {str(e)}"}
