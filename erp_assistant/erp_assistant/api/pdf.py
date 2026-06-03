"""
BizBot PDF RAG backend.
process_pdf  — extract, chunk, index a PDF into Redis (4-hour session)
ask_with_doc — keyword-based retrieval + Groq answer
"""
from __future__ import annotations
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
