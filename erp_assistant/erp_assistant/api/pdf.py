"""
BizBot PDF RAG backend.
process_pdf  — extract, chunk, index a PDF into Redis (4-hour session)
ask_with_doc — keyword-based retrieval + Groq answer
"""
from __future__ import annotations
import httpx
import frappe, base64, hashlib, json, re, math, io
from typing import List


# ── TEXT EXTRACTION ───────────────────────────────────────────────────────────

def _extract_text(pdf_bytes: bytes) -> str:
    for lib in ("pypdf", "PyPDF2"):
        try:
            mod = __import__(lib)
            Reader = getattr(mod, "PdfReader")
            reader = Reader(io.BytesIO(pdf_bytes))
            return "\n\n".join(
                (p.extract_text() or "").strip()
                for p in reader.pages
                if (p.extract_text() or "").strip()
            )
        except ImportError:
            continue
        except Exception as e:
            frappe.throw(f"PDF read error: {e}")
    frappe.throw(
        "pypdf not installed. Run: pip install pypdf --break-system-packages"
    )


# ── CHUNKING ──────────────────────────────────────────────────────────────────

def _chunk(text: str, size: int = 380, overlap: int = 40) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], []
    for para in paras:
        words = para.split()
        if len(buf) + len(words) <= size:
            buf.extend(words)
        else:
            if buf:
                chunks.append(" ".join(buf))
            if len(words) > size:
                for i in range(0, len(words), size - overlap):
                    c = words[i : i + size]
                    if c:
                        chunks.append(" ".join(c))
                buf = words[-(overlap):]
            else:
                buf = words
    if buf:
        chunks.append(" ".join(buf))
    return [c for c in chunks if len(c.split()) > 15]


# ── KEYWORD RETRIEVAL ─────────────────────────────────────────────────────────

_STOP = {
    "the","a","an","is","are","was","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","may","might","to",
    "of","in","on","at","by","for","with","and","but","or","not","this",
    "that","it","its","i","we","you","he","she","they","what","how","why",
    "which","who","about","from","up","if","as","so","then","than","too",
}

def _score(chunk: str, qtoks: set) -> float:
    wtoks = set(re.findall(r"\b\w+\b", chunk.lower())) - _STOP
    hits  = len(qtoks & wtoks)
    if not hits:
        return 0.0
    density = hits / max(len(wtoks), 1)
    phrase  = sum(1 for t in qtoks if t in chunk.lower())
    return hits * 2 + phrase * 1.5 + density * 8

def _top_chunks(chunks: List[str], query: str, n: int = 4) -> List[str]:
    qtoks = set(re.findall(r"\b\w+\b", query.lower())) - _STOP or             set(re.findall(r"\b\w+\b", query.lower()))
    scored = sorted(enumerate(chunks), key=lambda x: -_score(x[1], qtoks))
    top_idx = sorted(i for i, _ in scored[:n])
    return [chunks[i] for i in top_idx]


# ── CACHE HELPERS ─────────────────────────────────────────────────────────────

def _cache_key(doc_id: str) -> str:
    return f"bizbot_doc_{frappe.session.user}_{doc_id}"


# ── WHITELISTED ENDPOINTS ─────────────────────────────────────────────────────

@frappe.whitelist()
def process_pdf(file_b64: str, file_name: str) -> dict:
    """Extract, chunk, and cache a PDF. Returns doc_id."""
    try:
        pdf_bytes = base64.b64decode(file_b64)
    except Exception:
        frappe.throw("Invalid base64 data.")

    text = _extract_text(pdf_bytes)
    if not text or len(text.split()) < 30:
        frappe.throw(
            "Could not extract readable text — the PDF may be image-based or encrypted."
        )

    chunks = _chunk(text)
    doc_id  = hashlib.md5(pdf_bytes).hexdigest()[:16]

    frappe.cache().set_value(
        _cache_key(doc_id),
        json.dumps({
            "name":        file_name,
            "chunks":      chunks,
            "word_count":  len(text.split()),
        }),
        expires_in_sec=14400,   # 4-hour session
    )

    return {
        "doc_id":      doc_id,
        "name":        file_name,
        "word_count":  len(text.split()),
        "chunk_count": len(chunks),
    }


@frappe.whitelist()
def ask_with_doc(question: str, doc_id: str, doc_name: str = "") -> str:
    """Answer a question using RAG over a cached PDF."""
    cached = frappe.cache().get_value(_cache_key(doc_id))
    if not cached:
        return (
            "The document session has expired (4-hour limit). "
            "Please re-upload the PDF and ask again."
        )

    data   = json.loads(cached)
    chunks = data.get("chunks", [])
    name   = data.get("name", doc_name or "document")

    if not chunks:
        return "No content could be retrieved from the cached document."

    context   = "\n---\n".join(_top_chunks(chunks, question))
    word_count = data.get("word_count", "?")

    system = f"""You are BizBot, an intelligent document analyst for BizAxl ERP.
Answer the user's question using ONLY the document excerpts below.

DOCUMENT: {name}  ({word_count} words)

RELEVANT EXCERPTS:
===
{context}
===

RULES:
- Base your answer strictly on the excerpts above
- If the answer is not in the excerpts, say "I couldn't find that in the document"
- Be concise and quote specific figures, names, or dates where relevant
- Format key values clearly (bold with **text**)"""

    from erp_assistant.erp_assistant.api.ollama import call_ollama
    try:
        return call_ollama([
            {"role": "system",  "content": system},
            {"role": "user",    "content": question},
        ])
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "BizBot PDF RAG")
        return f"Error processing your question against the document: {e}"

@frappe.whitelist()
def ask_with_image(question: str, image_b64: str, file_name: str = "") -> str:
    key = frappe.conf.get("radar_groq_api_key") or frappe.conf.get("groq_api_key")
    if not key:
        return "Set groq_api_key in site_config to enable image analysis."

    head = image_b64[:12]
    if head.startswith("iVBORw0KGgo"):
        mime = "image/png"
    elif head.startswith("/9j"):
        mime = "image/jpeg"
    elif head.startswith("R0lGOD"):
        mime = "image/gif"
    elif head.startswith("UklGR"):
        mime = "image/webp"
    else:
        mime = "image/jpeg"

    fn = (' named "' + file_name + '"') if file_name else ""
    system = (
        "You are BizBot, a business document analyst for BizAxl ERP. "
        "The user uploaded an image" + fn + ". "
        "If it is a document (invoice, bill, receipt, order): extract key fields, "
        "amounts, dates, parties, and line items in a structured format. "
        "Use INR for Indian currency. Be concise and specific."
    )

    models = [
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.2-11b-vision-preview",
        "llama-3.2-90b-vision-preview",
    ]
    last_err = "No vision model responded."
    for model in models:
        try:
            with httpx.Client(timeout=45) as c:
                r = c.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": [
                                {"type": "image_url", "image_url": {"url": "data:" + mime + ";base64," + image_b64}},
                                {"type": "text", "text": question}
                            ]}
                        ],
                        "max_tokens": 1200,
                        "temperature": 0.1,
                    }
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
                err = ""
                try:
                    err = r.json().get("error", {}).get("message", "")
                except Exception:
                    err = r.text[:200]
                last_err = model + ": " + err
                if "model" not in err.lower() and "not found" not in err.lower():
                    return "Error from Groq (" + model + "): " + err
        except Exception as e:
            last_err = model + " exception: " + str(e)[:100]
            frappe.log_error(last_err, "BizBot Vision")
    return "Could not analyse image. " + last_err

@frappe.whitelist()
def create_invoice_from_image(image_b64: str, file_name: str = '') -> dict:
    key = frappe.conf.get('radar_groq_api_key') or frappe.conf.get('groq_api_key')
    if not key:
        return {'error': 'Set groq_api_key in site_config.'}
    head = image_b64[:12]
    mime = 'image/png' if head.startswith('iVBORw0KGgo') else 'image/jpeg'
    tmpl = '{"items":[{"name":"item name","qty":1,"rate":0.0}],"customer":"","notes":""}'
    prompt = ('Extract ALL line items from this invoice/bill image. '
              'Return ONLY valid JSON matching this format: ' + tmpl +
              ' Use numbers only for qty/rate. No currency symbols.')
    models = ['meta-llama/llama-4-scout-17b-16e-instruct',
              'llama-3.2-11b-vision-preview',
              'llama-3.2-90b-vision-preview']
    raw = None
    for model in models:
        try:
            with httpx.Client(timeout=45) as c:
                resp = c.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                    json={'model': model, 'max_tokens': 800, 'temperature': 0.0,
                          'messages': [{'role': 'user', 'content': [
                              {'type': 'image_url', 'image_url': {'url': 'data:' + mime + ';base64,' + image_b64}},
                              {'type': 'text', 'text': prompt}]}]})
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content']
                    break
                frappe.log_error(resp.text[:200], 'invoice_from_image ' + model)
        except Exception as ex:
            frappe.log_error(str(ex), 'invoice_from_image ' + model)
    if not raw:
        return {'error': 'Vision model did not respond. Check Error Log.'}
    import re as _re
    m = _re.search(r'\{[\s\S]+\}', raw)
    if not m:
        return {'error': 'Could not parse vision response: ' + raw[:200]}
    try:
        data = json.loads(m.group())
    except Exception:
        return {'error': 'JSON parse error: ' + raw[:200]}
    items = data.get('items', [])
    if not items:
        return {'error': 'No line items found in image.'}
    sinv = frappe.new_doc('BA Sales Invoice')
    _cos = frappe.db.get_all('BA Company', limit=1)
    sinv.company = _cos[0].name if _cos else ''
    sinv.posting_date = frappe.utils.nowdate()
    sinv.due_date     = frappe.utils.add_days(frappe.utils.nowdate(), 30)
    cname = (data.get('customer') or '').strip()
    if cname and frappe.db.exists('BA Customer', cname):
        sinv.customer = cname
    else:
        first = frappe.db.get_all('BA Customer', limit=1)
        sinv.customer = first[0].name if first else ''
    # Tax template — find whichever template DocType exists on this site
    for _tmpl_dt in ['BA Sales Taxes and Charges Template',
                     'Sales Taxes and Charges Template']:
        try:
            _tmpls = frappe.db.get_all(_tmpl_dt, limit=1)
            if _tmpls:
                sinv.taxes_and_charges = _tmpls[0].name
            break
        except Exception:
            pass
    all_items = frappe.db.get_all('BA Item', fields=['name','item_name'], limit=500)
    for it in items:
        iname = str(it.get('name', 'Item')).strip()
        code = next((r.name for r in all_items if iname.lower() in (r.item_name or '').lower()), iname)
        sinv.append('items', {
            'item_code': iname,
            'qty':       float(it.get('qty') or 1),
            'rate':      float(it.get('rate') or 0),
        })
    if data.get('notes'):
        sinv.remarks = str(data['notes'])[:500]
    try:
        sinv.insert(ignore_permissions=True)
        frappe.db.commit()
        return {'ok': True, 'name': sinv.name,
                'url': '/app/ba-sales-invoice/' + sinv.name,
                'total': sinv.grand_total,
                'item_count': len(sinv.items),
                'customer': sinv.customer}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), 'create_invoice_from_image')
        return {'error': 'Save failed: ' + str(e)[:200]}
