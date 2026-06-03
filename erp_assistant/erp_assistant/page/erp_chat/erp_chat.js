frappe.pages['erp-chat'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'ERP Assistant',
        single_column: true,
    });
    new ERPChatApp(wrapper, page);
};

class ERPChatApp {
    constructor(wrapper, page) {
        this.wrapper = wrapper;
        this.page = page;
        this.history = [];
        this.sessionData = {};
        this.pdfContext = null;
        this.pdfFilename = "";
        this.render();
        this.bindEvents();
    }

    render() {
        $(this.wrapper).find('.page-content').html(`
<style>
#erp-chat-root {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 120px);
    background: #0f0f11;
    border-radius: 12px;
    overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    border: 1px solid rgba(255,255,255,0.07);
    margin: -15px 0 0 0;
}

/* ── Header ── */
.eca-header {
    padding: 14px 20px;
    background: #16161a;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}
.eca-header-icon {
    width: 36px; height: 36px;
    border-radius: 10px;
    background: rgba(0,229,160,0.12);
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
    flex-shrink: 0;
}
.eca-header-title { font-size: 15px; font-weight: 600; color: #f0f0f4; }
.eca-header-sub   { font-size: 11px; color: #50505f; margin-top: 1px; }
.eca-status {
    margin-left: auto;
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; color: #50505f;
}
.eca-status-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #00e5a0;
    box-shadow: 0 0 5px #00e5a0;
}

/* ── Messages ── */
#eca-messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 14px;
}
#eca-messages::-webkit-scrollbar { width: 3px; }
#eca-messages::-webkit-scrollbar-thumb { background: #2a2a35; border-radius: 4px; }

.eca-msg {
    display: flex;
    gap: 10px;
    animation: ecaFadeIn 0.18s ease;
}
@keyframes ecaFadeIn {
    from { opacity: 0; transform: translateY(5px); }
    to   { opacity: 1; transform: translateY(0); }
}
.eca-msg.user { flex-direction: row-reverse; }

.eca-avatar {
    width: 30px; height: 30px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px;
    flex-shrink: 0;
    margin-top: 2px;
}
.eca-msg.assistant .eca-avatar { background: rgba(0,229,160,0.12); }
.eca-msg.user      .eca-avatar { background: rgba(99,102,241,0.15); }

.eca-bubble {
    max-width: 72%;
    padding: 11px 15px;
    border-radius: 12px;
    font-size: 13px;
    line-height: 1.65;
    word-break: break-word;
}
.eca-msg.assistant .eca-bubble {
    background: #1c1c22;
    color: #dddde8;
    border: 1px solid rgba(255,255,255,0.06);
    border-top-left-radius: 3px;
}
.eca-msg.user .eca-bubble {
    background: rgba(99,102,241,0.18);
    color: #dddde8;
    border: 1px solid rgba(99,102,241,0.25);
    border-top-right-radius: 3px;
}
.eca-bubble strong { color: #f0f0f4; }
.eca-bubble code {
    background: rgba(255,255,255,0.08);
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 12px;
    font-family: 'Fira Code', monospace;
}

/* ── Data table ── */
.eca-table-wrap {
    margin-top: 10px;
    overflow-x: auto;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.07);
}
.eca-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    min-width: 400px;
}
.eca-table th {
    background: rgba(255,255,255,0.05);
    padding: 7px 12px;
    text-align: left;
    color: #80809a;
    font-weight: 500;
    white-space: nowrap;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.eca-table td {
    padding: 7px 12px;
    color: #b0b0c4;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    white-space: nowrap;
}
.eca-table tr:last-child td { border-bottom: none; }
.eca-table tr:hover td { background: rgba(255,255,255,0.02); }
.eca-table-footer {
    font-size: 11px;
    color: #50505f;
    margin-top: 5px;
    text-align: right;
}

/* ── SQL toggle ── */
.eca-sql-toggle {
    margin-top: 8px;
    font-size: 11px;
    color: #50505f;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    user-select: none;
}
.eca-sql-toggle:hover { color: #9090a8; }
.eca-sql-block {
    display: none;
    margin-top: 6px;
    background: #111116;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 6px;
    padding: 10px 12px;
    font-size: 11px;
    font-family: 'Fira Code', monospace;
    color: #7070a0;
    white-space: pre-wrap;
    word-break: break-all;
}

/* ── Typing indicator ── */
.eca-typing {
    display: flex; gap: 4px;
    padding: 11px 15px;
    background: #1c1c22;
    border-radius: 12px;
    border-top-left-radius: 3px;
    border: 1px solid rgba(255,255,255,0.06);
    width: fit-content;
}
.eca-typing span {
    width: 5px; height: 5px;
    background: #00e5a0;
    border-radius: 50%;
    animation: ecaBounce 1.1s infinite;
    opacity: 0.5;
}
.eca-typing span:nth-child(2) { animation-delay: 0.18s; }
.eca-typing span:nth-child(3) { animation-delay: 0.36s; }
@keyframes ecaBounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
    40%            { transform: translateY(-5px); opacity: 1; }
}

/* ── Quick prompts ── */
.eca-quick {
    padding: 0 20px 10px;
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    flex-shrink: 0;
}
.eca-qbtn {
    padding: 5px 11px;
    border-radius: 20px;
    font-size: 11px;
    border: 1px solid rgba(255,255,255,0.09);
    background: transparent;
    color: #80809a;
    cursor: pointer;
    transition: all 0.12s;
    font-family: inherit;
    white-space: nowrap;
}
.eca-qbtn:hover {
    border-color: #00e5a0;
    color: #00e5a0;
    background: rgba(0,229,160,0.07);
}

/* ── Input area ── */
.eca-input-area {
    padding: 12px 16px;
    background: #16161a;
    border-top: 1px solid rgba(255,255,255,0.07);
    display: flex;
    gap: 9px;
    align-items: flex-end;
    flex-shrink: 0;
}
#eca-input {
    flex: 1;
    background: #1e1e26;
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 10px;
    color: #dddde8;
    font-family: inherit;
    font-size: 13px;
    padding: 9px 13px;
    resize: none;
    outline: none;
    max-height: 110px;
    line-height: 1.5;
    transition: border-color 0.12s;
}
#eca-input:focus { border-color: rgba(0,229,160,0.5); }
#eca-input::placeholder { color: #404050; }
#eca-send {
    width: 38px; height: 38px;
    border-radius: 10px;
    background: #00e5a0;
    border: none;
    color: #0a1a12;
    font-size: 15px;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.12s;
    flex-shrink: 0;
}
#eca-send:hover:not(:disabled) { background: #00ffb3; transform: scale(1.04); }
#eca-send:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }

/* ── Error state ── */
.eca-error .eca-bubble {
    border-color: rgba(255,100,100,0.25);
    color: #ff8080;
}

/* ── PDF attach ── */
.eca-attach-btn{width:38px;height:38px;border-radius:10px;background:rgba(255,255,255,0.07);border:none;color:#a0a0b0;font-size:17px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.12s;flex-shrink:0}
.eca-attach-btn:hover{background:rgba(255,255,255,0.12);color:#f0f0f4}
.eca-pdf-bar{padding:6px 16px;background:rgba(0,229,160,0.08);border-top:1px solid rgba(0,229,160,0.15);display:flex;align-items:center;gap:8px;font-size:12px;color:#00e5a0}
.eca-pdf-bar span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.eca-pdf-clear{background:none;border:none;color:#50505f;cursor:pointer;font-size:15px;padding:0 2px;line-height:1}
.eca-pdf-clear:hover{color:#ff8080}

</style>

<div id="erp-chat-root">

    <div class="eca-header">
        <div class="eca-header-icon">🤖</div>
        <div>
            <div class="eca-header-title">ERP Assistant</div>
            <div class="eca-header-sub">Powered by qwen2.5:3b · Local AI · No data leaves your server</div>
        </div>
        <div class="eca-status">
            <div class="eca-status-dot"></div>
            <span id="eca-status-text">Online</span>
        </div>
    </div>

    <div id="eca-messages">
        <div class="eca-msg assistant">
            <div class="eca-avatar">🤖</div>
            <div class="eca-bubble">
                Hello! I'm your ERP Assistant. I can help you:<br><br>
                📊 <strong>Query data</strong> — "What are total sales this month?"<br>
                📝 <strong>Create documents</strong> — "Create a new sales invoice"<br>
                📈 <strong>Analytics</strong> — "Compare Q1 vs Q2 revenue"<br>
                ❓ <strong>Navigate</strong> — "How do I create a POS entry?"<br><br>
                What would you like to know?
            </div>
        </div>
    </div>

    <div class="eca-quick">
        <button class="eca-qbtn" data-msg="What are total sales this month?">📊 Monthly Sales</button>
        <button class="eca-qbtn" data-msg="Show me all overdue invoices">⚠️ Overdue Invoices</button>
        <button class="eca-qbtn" data-msg="List top 5 customers by revenue this year">👥 Top Customers</button>
        <button class="eca-qbtn" data-msg="What is our current stock summary?">📦 Stock Summary</button>
        <button class="eca-qbtn" data-msg="Create a new sales invoice">➕ New Invoice</button>
        <button class="eca-qbtn" data-msg="Show all pending purchase orders">🛒 Pending POs</button>
    </div>

    <div class="eca-pdf-bar" id="eca-pdf-bar" style="display:none"><span id="eca-pdf-name">📄 </span><button class="eca-pdf-clear" id="eca-pdf-clear" title="Remove PDF">✕</button></div>
    <input type="file" id="eca-pdf-input" accept=".pdf" style="display:none">
    <div class="eca-input-area">
        <textarea id="eca-input" rows="1"
            placeholder="Ask anything about your ERP data…"></textarea>
        <button id="eca-attach" class="eca-attach-btn" title="Attach PDF">📎</button>
        <button id="eca-send" title="Send (Enter)">➤</button>
    </div>

</div>`);
    }

    bindEvents() {
        const input = document.getElementById('eca-input');
        const sendBtn = document.getElementById('eca-send');

        // Send on Enter (Shift+Enter = newline)
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.send();
            }
        });

        // Auto-resize textarea
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 110) + 'px';
        });

        // Send button
        sendBtn.addEventListener('click', () => this.send());

        // PDF attach / clear
        document.getElementById('eca-attach').addEventListener('click', () => document.getElementById('eca-pdf-input').click());
        document.getElementById('eca-pdf-input').addEventListener('change', (e) => { if (e.target.files[0]) this.loadPdf(e.target.files[0]); e.target.value = ''; });
        document.getElementById('eca-pdf-clear').addEventListener('click', () => this.clearPdf());

        // Quick prompt buttons
        document.querySelectorAll('.eca-qbtn').forEach(btn => {
            btn.addEventListener('click', () => {
                input.value = btn.dataset.msg;
                input.dispatchEvent(new Event('input'));
                this.send();
            });
        });
    }

    async send() {
        const input = document.getElementById('eca-input');
        const message = input.value.trim();
        if (!message) return;

        input.value = '';
        input.style.height = 'auto';

        this.addMessage('user', message);
        this.history.push({ role: 'user', content: message });

        const sendBtn = document.getElementById('eca-send');
        sendBtn.disabled = true;
        this.setStatus('Thinking…', false);

        const typingId = this.addTyping();

        try {
            const result = await frappe.call(this.pdfContext ? {
                method: 'erp_assistant.erp_assistant.api.pdf.chat_with_pdf',
                args: { message, pdf_text: this.pdfContext, history: JSON.stringify(this.history.slice(-8)), pdf_filename: this.pdfFilename },
            } : {
                method: 'erp_assistant.erp_assistant.api.chat.chat',
                args: { message: message, history: JSON.stringify(this.history.slice(-12)), session_data: JSON.stringify(this.sessionData) },
            });

            this.removeTyping(typingId);

            const resp = result.message;
            if (resp) {
                this.sessionData = resp.session_data || {};
                const text = resp.response || 'No response received.';
                this.addMessage('assistant', text, resp);
                this.history.push({ role: 'assistant', content: text });
            }
        } catch (err) {
            this.removeTyping(typingId);
            this.addMessage('assistant',
                '❌ Connection error. Make sure Ollama is running: <code>ollama serve</code>',
                { type: 'error' });
            console.error('ERP Assistant error:', err);
        } finally {
            sendBtn.disabled = false;
            this.setStatus('Online', true);
            input.focus();
        }
    }

    addMessage(role, text, data) {
        const container = document.getElementById('eca-messages');
        const div = document.createElement('div');
        div.className = `eca-msg ${role}`;
        if (data?.type === 'error') div.classList.add('eca-error');

        const avatar = role === 'assistant' ? '🤖' : '👤';
        let html = `<div class="eca-avatar">${avatar}</div>
                    <div class="eca-bubble">${this.formatText(text)}`;

        // Append data table for read responses
        if (data?.type === 'read' && data.data?.length > 0) {
            html += this.buildTable(data.data, data.columns, data.sql);
        }

        html += `</div>`;
        div.innerHTML = html;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    formatText(text) {
        if (!text) return '';
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    buildTable(rows, columns, sql) {
        if (!rows || !rows.length || !columns) return '';

        const headers = columns.map(c =>
            `<th>${c.replace(/_/g, ' ')}</th>`
        ).join('');

        const bodyRows = rows.slice(0, 20).map(row =>
            `<tr>${columns.map(c => {
                const val = row[c] ?? '';
                // Format numbers with commas, prefix ₹ for amount/total cols
                const colLower = c.toLowerCase();
                const isAmount = ['total','amount','balance','outstanding','value',
                    'grand_total','base_grand_total','net_total'].some(k => colLower.includes(k));
                if (isAmount && typeof val === 'number') {
                    return `<td>₹${val.toLocaleString('en-IN', {maximumFractionDigits: 2})}</td>`;
                }
                return `<td>${val}</td>`;
            }).join('')}</tr>`
        ).join('');

        const footer = rows.length > 20
            ? `<div class="eca-table-footer">Showing 20 of ${rows.length} rows</div>`
            : '';

        const sqlBlock = sql ? `
            <div class="eca-sql-toggle" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='block'?'none':'block'">
                🔍 View SQL
            </div>
            <div class="eca-sql-block">${sql.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
        ` : '';

        return `
            <div class="eca-table-wrap">
                <table class="eca-table">
                    <thead><tr>${headers}</tr></thead>
                    <tbody>${bodyRows}</tbody>
                </table>
            </div>
            ${footer}
            ${sqlBlock}
        `;
    }

    addTyping() {
        const container = document.getElementById('eca-messages');
        const id = 'typing-' + Date.now();
        const div = document.createElement('div');
        div.className = 'eca-msg assistant';
        div.id = id;
        div.innerHTML = `
            <div class="eca-avatar">🤖</div>
            <div class="eca-typing">
                <span></span><span></span><span></span>
            </div>`;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        return id;
    }

    removeTyping(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    setStatus(text, online) {
        const dot = document.querySelector('.eca-status-dot');
        const label = document.getElementById('eca-status-text');
        if (dot) dot.style.background = online ? '#00e5a0' : '#f0a500';
        if (dot) dot.style.boxShadow = online ? '0 0 5px #00e5a0' : '0 0 5px #f0a500';
        if (label) label.textContent = text;
    }
    async loadPdf(file) {
        const bar = document.getElementById('eca-pdf-bar');
        const nameEl = document.getElementById('eca-pdf-name');
        nameEl.textContent = '📄 Uploading ' + file.name + '…';
        bar.style.display = 'flex';
        this.setStatus('Reading PDF…', false);
        try {
            // upload to Frappe
            const fd = new FormData();
            fd.append('file', file); fd.append('is_private', '0');
            const up = await fetch('/api/method/upload_file', {
                method: 'POST', body: fd,
                headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token },
            });
            const upData = await up.json();
            if (!upData.message?.file_url) throw new Error('Upload failed');

            // extract text
            nameEl.textContent = '📄 Extracting ' + file.name + '…';
            const ext = await frappe.call({
                method: 'erp_assistant.erp_assistant.api.pdf.extract_pdf_text',
                args: { file_url: upData.message.file_url },
            });
            const { text, pages, characters } = ext.message;
            this.pdfContext = text;
            this.pdfFilename = file.name;
            this.history = [];
            nameEl.textContent = '📄 ' + file.name + ' (' + pages + ' pages)';

            // auto-summarise
            this.setStatus('Summarising…', false);
            const sum = await frappe.call({
                method: 'erp_assistant.erp_assistant.api.pdf.summarise_pdf',
                args: { pdf_text: text, pdf_filename: file.name },
            });
            this.addMessage('assistant',
                '📄 **' + file.name + '** loaded — ' + pages + ' pages, ' + characters.toLocaleString() + ' characters.\n\n' + sum.message.summary,
                { type: 'pdf_read' }
            );
        } catch (err) {
            bar.style.display = 'none';
            this.pdfContext = null;
            this.addMessage('assistant', '❌ Could not read PDF: ' + (err.message || err), { type: 'error' });
        } finally {
            this.setStatus('Online', true);
        }
    }

    clearPdf() {
        this.pdfContext = null; this.pdfFilename = ''; this.history = [];
        document.getElementById('eca-pdf-bar').style.display = 'none';
        this.addMessage('assistant', '📄 PDF removed. Back to normal ERP mode.', {});
    }

}
