frappe.provide("erp_assistant.widget");

erp_assistant.widget = {
    _dialog: null,
    _history: [],
    _session: {},
    _waiting: false,

    init: function() {
        if (document.getElementById("eca-fab")) return;
        var self = this;
        var fab = document.createElement("button");
        fab.id = "eca-fab";
        fab.title = "BizBot (BB)";
        fab.innerHTML = '<span style="font-size:13px;font-weight:800;letter-spacing:-0.5px;color:#0a1a12">BB</span>';
        fab.setAttribute("style",
            "position:fixed;bottom:24px;right:24px;width:52px;height:52px;" +
            "border-radius:50%;background:linear-gradient(135deg,#00e5a0,#00c47a);border:none;cursor:pointer;" +
            "z-index:99999;font-size:22px;box-shadow:0 4px 20px rgba(0,229,160,0.6);" +
            "display:flex;align-items:center;justify-content:center;" +
            "transition:transform 0.2s,box-shadow 0.2s;"
        );
        fab.onclick = function() { self.open(); };
        document.body.appendChild(fab);
    },

    _perms: null,

    loadPermissions: function(callback) {
        var self = this;
        frappe.call({
            method: "erp_assistant.erp_assistant.api.permissions.get_user_permissions",
            callback: function(r) {
                self._perms = r.message || {role_level:"none", can_submit:false};
                if (callback) callback(self._perms);
            },
            error: function() {
                self._perms = {role_level:"sales_user", can_submit:false};
                if (callback) callback(self._perms);
            }
        });
    },

    _perms: null,

    loadPermissions: function(callback) {
        var self = this;
        frappe.call({
            method: "erp_assistant.erp_assistant.api.permissions.get_user_permissions",
            callback: function(r) {
                self._perms = r.message || {role_level:"none", can_submit:false};
                if (callback) callback(self._perms);
            },
            error: function() {
                self._perms = {role_level:"sales_user", can_submit:false};
                if (callback) callback(self._perms);
            }
        });
    },

    open: function() {
        var self = this;
        if (!this._dialog) {
            this._dialog = new frappe.ui.Dialog({
                title: "BizBot (BB) — Your ERP Assistant",
                size: "large",
                fields: [
                    {
                        fieldtype: "HTML",
                        fieldname: "msgs",
                        options: '<div id="eca-msgs" style="height:380px;overflow-y:auto;' +
                            'background:#0f0f11;padding:12px;border-radius:8px;' +
                            'display:flex;flex-direction:column;gap:8px;' +
                            'font-family:-apple-system,sans-serif"></div>' +
                            '<div id="bb-chips" style="display:flex;gap:6px;flex-wrap:wrap;padding:8px 0 4px">' +
                            '<button class="bb-chip" data-q="Show sales invoices this month" ' +
                            'style="padding:4px 10px;border-radius:12px;border:1px solid #2a2a35;' +
                            'background:transparent;color:#888;cursor:pointer;font-size:11px">📊 Sales</button>' +
                            '<button class="bb-chip" data-q="Show overdue invoices" ' +
                            'style="padding:4px 10px;border-radius:12px;border:1px solid #2a2a35;' +
                            'background:transparent;color:#888;cursor:pointer;font-size:11px">⚠️ Overdue</button>' +
                            '<button class="bb-chip" data-q="List top 5 customers by revenue" ' +
                            'style="padding:4px 10px;border-radius:12px;border:1px solid #2a2a35;' +
                            'background:transparent;color:#888;cursor:pointer;font-size:11px">👥 Customers</button>' +
                            '<button class="bb-chip" data-q="Show pending purchase orders" ' +
                            'style="padding:4px 10px;border-radius:12px;border:1px solid #2a2a35;' +
                            'background:transparent;color:#888;cursor:pointer;font-size:11px">🛒 POs</button>' +
                            '<button class="bb-chip" data-q="Create a new sales invoice" ' +
                            'style="padding:4px 10px;border-radius:12px;border:1px solid #2a2a35;' +
                            'background:transparent;color:#888;cursor:pointer;font-size:11px">➕ Invoice</button>' +
                            '<button id="bb-pdf-btn" class="bb-chip" style="padding:4px 10px;border-radius:12px;border:1px solid #2a2a35;background:transparent;color:#888;cursor:pointer;font-size:11px">📎 PDF</button></div>'
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "message",
                        label: "",
                        placeholder: "Ask BB anything about your ERP…"
                    }
                ],
                primary_action_label: "Send ➤",
                primary_action: function(v) {
                    if (!v.message || !v.message.trim()) return;
                    var msg = v.message.trim();
                    self._dialog.set_value("message", "");
                    self.send(msg);
                }
            });

            // Style the dialog
            this._dialog.onshow = function() {
                var wrap = self._dialog.$wrapper;
                wrap.find(".modal-content").css("background", "#16161a");
                wrap.find(".modal-header").css({"background":"#1a1a1f","border-bottom":"1px solid #2a2a35"});
                wrap.find(".modal-title").css("color","#f0f0f4");
                wrap.find(".modal-footer").css({"background":"#1a1a1f","border-top":"1px solid #2a2a35"});
                wrap.find(".btn-primary").css({"background":"#00e5a0","border-color":"#00e5a0","color":"#000"});
                wrap.find("input[data-fieldname='message']").css({
                    "background":"#0f0f11","border-color":"#2a2a35","color":"#ddd"
                });
            };
        }

        this._dialog.show();

        setTimeout(function() {
            var msgs = document.getElementById("eca-msgs");
            if (!msgs) {
                // DOM not ready — retry once
                setTimeout(function() {
                    if (document.getElementById("eca-msgs") && document.getElementById("eca-msgs").children.length === 0) {
                        self.addMsg("a", "Hey! 👋 I'm **BB** — your BizBot ERP Assistant.\n\nI can help you:\n📊 **Query data** — Show sales this month\n📝 **Create documents** — Create a sales invoice\n📈 **Analytics** — Compare Q1 vs Q2 revenue\n\nHow can I help you today?");
                    }
                }, 500);
                return;
            }
            if (msgs.children.length === 0) {
                self.addMsg("a", "Hey! 👋 I'm **BB** — your BizBot ERP Assistant.\n\nI can help you:\n📊 **Query data** — Show sales this month\n📝 **Create documents** — Create a sales invoice\n📈 **Analytics** — Compare Q1 vs Q2 revenue\n\nHow can I help you today?");
            }
            document.querySelectorAll(".eca-chip, .bb-chip").forEach(function(btn) {
                btn.onclick = function() { self.send(btn.getAttribute("data-q")); };
                btn.onmouseover = function() { this.style.borderColor="#00e5a0"; this.style.color="#00e5a0"; };
                btn.onmouseout  = function() { this.style.borderColor="#2a2a35"; this.style.color="#888"; };
            });
            // Wire up PDF chip
            var pdfBtn = document.getElementById("bb-pdf-btn");
            if (pdfBtn) {
                pdfBtn.onmouseover = function() { if (!self._doc) { this.style.borderColor="#00e5a0"; this.style.color="#00e5a0"; } };
                pdfBtn.onmouseout  = function() { if (!self._doc) { this.style.borderColor="#2a2a35"; this.style.color="#888"; } };
                pdfBtn.onclick = function() {
                    if (self._doc) { self.clearPdf(); return; }
                    var fi = document.getElementById("bb-file-input");
                    if (!fi) {
                        fi = document.createElement("input");
                        fi.type = "file"; fi.id = "bb-file-input";
                        fi.accept = ".pdf,application/pdf"; fi.style.display = "none";
                        document.body.appendChild(fi);
                        fi.addEventListener("change", function(e) {
                            if (e.target.files && e.target.files[0]) self.processPdf(e.target.files[0]);
                            fi.value = "";
                        });
                    }
                    fi.click();
                };
            }
            self.loadPermissions(function(perms) {
                self._applyPermissions(perms);
            });
        }, 300);
    },
    quickSend: function(msg) {
        this.send(msg);
    },

    _linkifyDocs: function(text) {
        // Convert document IDs like ACC-SINV-2026-00001 to clickable links
        // Matches common Frappe naming patterns
        return text.replace(
            /`([A-Z][A-Z0-9]+-[A-Z]+-\d{4}-\d{5,}|[A-Z][A-Z0-9]+-\d{4}-\d{5,}|[A-Z][A-Z0-9]+-\d{5,})`/g,
            function(match, docname) {
                // Guess doctype from prefix
                var prefix = docname.split('-')[0];
                var routeMap = {
                    'ACC': 'Sales Invoice',
                    'SINV': 'Sales Invoice', 
                    'PINV': 'Purchase Invoice',
                    'SO': 'Sales Order',
                    'PO': 'Purchase Order',
                    'QUOT': 'Quotation',
                    'DN': 'Delivery Note',
                    'PR': 'Purchase Receipt',
                    'HR': 'Employee',
                    'EMP': 'Employee',
                    'CUST': 'Customer',
                    'SUPP': 'Supplier',
                };
                // Try to find in full name
                var dt = null;
                for (var k in routeMap) {
                    if (docname.indexOf(k) !== -1) { dt = routeMap[k]; break; }
                }
                if (dt) {
                    var url = '/app/' + dt.toLowerCase().replace(/ /g, '-') + '/' + encodeURIComponent(docname);
                    return '<a href="' + url + '" target="_blank" style="color:#00e5a0;text-decoration:none;border-bottom:1px solid rgba(0,229,160,0.3)">' + docname + ' ↗</a>';
                }
                return '<code style="background:rgba(255,255,255,0.07);padding:1px 4px;border-radius:3px;font-size:11px">' + docname + '</code>';
            }
        );
    },

    addMsg: function(role, text, data) {
        var msgs = document.getElementById("eca-msgs");
        if (!msgs) return;
        var isUser = role === "u";
        var d = document.createElement("div");
        d.style.cssText = "display:flex;gap:7px;" + (isUser ? "flex-direction:row-reverse;" : "");
        var t = (text||"")
            .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
            .replace(/\*\*(.*?)\*\*/g,"<strong>$1</strong>")
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" style="color:#00e5a0;text-decoration:none;border-bottom:1px solid rgba(0,229,160,0.3)">$1 \u2197</a>')
            .replace(/`([A-Z][A-Z0-9]+-[A-Z]+-\d{4}-\d{5,})`/g, function(m, dn) {
                var slug = dn.indexOf("SINV") !== -1 ? "sales-invoice" :
                           dn.indexOf("PINV") !== -1 ? "purchase-invoice" :
                           dn.indexOf("-SO-") !== -1 ? "sales-order" :
                           dn.indexOf("-PO-") !== -1 ? "purchase-order" : null;
                if (slug) return '<a href="/app/'+slug+'/'+encodeURIComponent(dn)+'" style="color:#00e5a0;text-decoration:none;border-bottom:1px solid rgba(0,229,160,0.3)">'+dn+' \u2197</a>';
                return '<code style="background:rgba(255,255,255,0.07);padding:1px 4px;border-radius:3px;font-size:11px">'+dn+'</code>';
            })
            .replace(/\n/g,"<br>");
        var bubbleStyle = isUser
            ? "max-width:80%;padding:8px 12px;border-radius:10px;font-size:12px;line-height:1.6;background:#1a3a2a;color:#ddd;border:1px solid #1e4a30;"
            : "max-width:80%;padding:8px 12px;border-radius:10px;font-size:12px;line-height:1.6;background:#1e1e26;color:#ddd;border:1px solid #2a2a35;border-left:3px solid #00e5a0;";

        var tableHtml = "";
        if (data && data.type === "read" && data.data && data.data.length) {
            var cols = data.columns;
            var rows = data.data.slice(0,10);
            var th = cols.map(function(c){return '<th style="padding:4px 8px;text-align:left;color:#666;font-size:10px;white-space:nowrap">'+c.replace(/_/g," ")+"</th>";}).join("");
            var tb = rows.map(function(r){
                return "<tr>"+cols.map(function(c){return '<td style="padding:4px 8px;font-size:10px;color:#aaa;border-top:1px solid #1a1a1f;white-space:nowrap">'+(r[c]!=null?r[c]:"")+"</td>";}).join("")+"</tr>";
            }).join("");
            tableHtml = '<div style="margin-top:8px;overflow-x:auto;border-radius:5px;border:1px solid #1a1a1f"><table style="width:100%;border-collapse:collapse"><thead><tr>'+th+'</tr></thead><tbody>'+tb+'</tbody></table></div>';
            if (data.sql) {
                tableHtml += '<div style="font-size:10px;color:#444;margin-top:4px;cursor:pointer" onclick="this.nextSibling.style.display=this.nextSibling.style.display===\'block\'?\'none\':\'block\'">🔍 View SQL</div><div style="display:none;font-size:10px;font-family:monospace;color:#555;margin-top:2px;word-break:break-all">'+data.sql.replace(/</g,"&lt;")+"</div>";
            }
        }

        d.innerHTML = '<div style="width:24px;height:24px;border-radius:50%;background:'+(isUser?'rgba(99,102,241,0.2)':'linear-gradient(135deg,#00e5a0,#00c47a)')+';display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px">'+(isUser?'<span style="font-size:11px">👤</span>':'<span style="font-size:8px;font-weight:800;color:#0a1a12">BB</span>')+'</div>' +
            '<div style="'+bubbleStyle+'">'+t+tableHtml+'</div>';
        msgs.appendChild(d);
        msgs.scrollTop = msgs.scrollHeight;
    },

    _applyPermissions: function(perms) {
        if (!perms) return;
        var role = perms.role_level;
        var chips = document.querySelectorAll(".bb-chip, .eca-chip");

        // Define which chips each role sees
        var hiddenForSalesUser = [
            "Create a new sales invoice",   // sales user can create but not submit — keep visible
            "Show pending purchase orders", // POs hidden for sales user
        ];
        var hiddenForStoreManager = [];     // store manager sees everything except...

        chips.forEach(function(btn) {
            var q = btn.getAttribute("data-q") || "";
            var hide = false;

            if (role === "sales_user") {
                // Hide PO chip, analytics chips
                if (q.toLowerCase().indexOf("purchase order") !== -1) hide = true;
            }

            if (role === "none") {
                hide = true; // hide all chips for no-role users
            }

            btn.style.display = hide ? "none" : "";
        });

        // Show role badge in dialog
        var existing = document.getElementById("bb-role-badge");
        if (existing) existing.remove();

        var roleLabels = {
            "admin": {label:"Admin", color:"#ff6b6b"},
            "store_manager": {label:"Store Manager", color:"#ffd93d"},
            "sales_user": {label:"Sales User", color:"#6bcb77"},
            "none": {label:"Limited Access", color:"#888"}
        };
        var rl = roleLabels[role] || roleLabels["none"];

        var badge = document.createElement("div");
        badge.id = "bb-role-badge";
        badge.style.cssText = "font-size:10px;padding:2px 8px;border-radius:10px;display:inline-block;margin-bottom:6px;font-weight:600;";
        badge.style.background = rl.color + "22";
        badge.style.color = rl.color;
        badge.style.border = "1px solid " + rl.color + "44";
        badge.textContent = "● " + rl.label;

        // Insert badge above the messages area
        var msgs = document.getElementById("eca-msgs");
        if (msgs) {
            msgs.insertBefore(badge, msgs.firstChild);
        } else {
            // Fallback: insert into dialog body
            var body = document.querySelector(".modal-body");
            if (body) body.insertBefore(badge, body.firstChild);
        }
    },

    _applyPermissions: function(perms) {
        if (!perms) return;
        var role = perms.role_level;
        var chips = document.querySelectorAll(".bb-chip, .eca-chip");

        // Define which chips each role sees
        var hiddenForSalesUser = [
            "Create a new sales invoice",   // sales user can create but not submit — keep visible
            "Show pending purchase orders", // POs hidden for sales user
        ];
        var hiddenForStoreManager = [];     // store manager sees everything except...

        chips.forEach(function(btn) {
            var q = btn.getAttribute("data-q") || "";
            var hide = false;

            if (role === "sales_user") {
                // Hide PO chip, analytics chips
                if (q.toLowerCase().indexOf("purchase order") !== -1) hide = true;
            }

            if (role === "none") {
                hide = true; // hide all chips for no-role users
            }

            btn.style.display = hide ? "none" : "";
        });

        // Show role badge in dialog
        var existing = document.getElementById("bb-role-badge");
        if (existing) existing.remove();

        var roleLabels = {
            "admin": {label:"Admin", color:"#ff6b6b"},
            "store_manager": {label:"Store Manager", color:"#ffd93d"},
            "sales_user": {label:"Sales User", color:"#6bcb77"},
            "none": {label:"Limited Access", color:"#888"}
        };
        var rl = roleLabels[role] || roleLabels["none"];

        var badge = document.createElement("div");
        badge.id = "bb-role-badge";
        badge.style.cssText = "font-size:10px;padding:2px 8px;border-radius:10px;display:inline-block;margin-bottom:6px;font-weight:600;";
        badge.style.background = rl.color + "22";
        badge.style.color = rl.color;
        badge.style.border = "1px solid " + rl.color + "44";
        badge.textContent = "● " + rl.label;

        var msgs = document.getElementById("eca-msgs");
        if (msgs && msgs.parentNode) {
            msgs.parentNode.insertBefore(badge, msgs);
        }
    },

    send: function(msg) {
        if (this._waiting || !msg) return;
        var self = this;
        this.addMsg("u", msg);
        this._history.push({role:"user",content:msg});
        this._waiting = true;

        var msgs = document.getElementById("eca-msgs");
        var tid = "et"+Date.now();
        var td = document.createElement("div");
        td.id = tid;
        td.style.cssText = "display:flex;gap:7px;";
        td.innerHTML = '<div style="width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,#00e5a0,#00c47a);display:flex;align-items:center;justify-content:center;flex-shrink:0"><span style="font-size:8px;font-weight:800;color:#0a1a12">BB</span></div>' +
            '<div style="padding:8px 12px;border-radius:10px;font-size:12px;background:#1e1e26;color:#555;border:1px solid #2a2a35;border-left:3px solid #00e5a0">Thinking…</div>';
        if (msgs) { msgs.appendChild(td); msgs.scrollTop = msgs.scrollHeight; }
        frappe.call({
            method: _method, args: _args, timeout: 180,
            callback: _onSuccess,
            error: function() {
                var el = document.getElementById(tid); if (el) el.remove();
                self.addMsg("a", "\u274C Error connecting to AI. Check your API key.");
                self._waiting = false;
            }
        });
    }
};

// Multiple strategies to ensure init runs after Frappe session is ready
function _ecaAutoInit() {
    if (frappe.session && frappe.session.user && frappe.session.user !== "Guest") {
        erp_assistant.widget.init();
        return true;
    }
    return false;
}

$(document).on("frappe.ready", function() { setTimeout(_ecaAutoInit, 500); });
$(document).on("page-change", function() { 
    if (!document.getElementById("eca-fab")) _ecaAutoInit(); 
});

// Persistent poll — keeps trying until FAB appears
var _ecaPoll = setInterval(function() {
    if (document.getElementById("eca-fab")) { 
        clearInterval(_ecaPoll); 
        return; 
    }
    _ecaAutoInit();
}, 2000);
setTimeout(function() { clearInterval(_ecaPoll); }, 60000);

// ── BizBot PDF RAG extension (appended after widget definition) ──────────────
erp_assistant.widget._doc = null;

erp_assistant.widget.processPdf = function(file) {
    var self = this;
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
        self.addMsg("a", "\u274C PDF too large (max 20 MB).");
        return;
    }
    self.addMsg("a", "\uD83D\uDCCE Processing **" + file.name + "**\u2026 one moment.");
    var reader = new FileReader();
    reader.onload = function(e) {
        var b64 = (e.target.result || "").split(",")[1];
        if (!b64) { self.addMsg("a", "\u274C Could not read the file."); return; }
        frappe.call({
            method: "erp_assistant.erp_assistant.api.pdf.process_pdf",
            args: { file_b64: b64, file_name: file.name },
            timeout: 120,
            callback: function(r) {
                if (r.message && r.message.doc_id) {
                    self._doc = { doc_id: r.message.doc_id, name: r.message.name };
                    var m = r.message;
                    var btn = document.getElementById("bb-pdf-btn");
                    if (btn) {
                        var sn = file.name.length > 14 ? file.name.slice(0,11) + "\u2026" : file.name;
                        btn.innerHTML = "\uD83D\uDCCE " + sn + " \u00D7";
                        btn.style.borderColor = "#00e5a0";
                        btn.style.color = "#00e5a0";
                    }
                    self.addMsg("a",
                        "\u2705 **" + file.name + "** loaded!\n\n" +
                        "\uD83D\uDCC4 ~" + m.word_count + " words \u00B7 " + m.chunk_count + " sections indexed\n\n" +
                        "Ask me anything about this document."
                    );
                }
            },
            error: function() {
                self.addMsg("a", "\u274C Failed to process PDF. Run: pip install pypdf --break-system-packages");
            }
        });
    };
    reader.readAsDataURL(file);
};

erp_assistant.widget.clearPdf = function() {
    this._doc = null;
    var btn = document.getElementById("bb-pdf-btn");
    if (btn) {
        btn.innerHTML = "\uD83D\uDCCE PDF";
        btn.style.borderColor = "#2a2a35";
        btn.style.color = "#888";
    }
    this.addMsg("a", "\uD83D\uDCCE Document removed. Back to ERP mode.");
};

// Override send() to branch into PDF RAG when a document is loaded
(function() {
    var _origSend = erp_assistant.widget.send.bind(erp_assistant.widget);
    erp_assistant.widget.send = function(msg) {
        if (!msg || this._waiting) return;
        if (!this._doc) { return _origSend(msg); }

        // PDF RAG mode
        var self = this;
        self.addMsg("u", msg);
        self._history.push({role: "user", content: msg});
        self._waiting = true;

        var msgs = document.getElementById("eca-msgs");
        var tid = "et" + Date.now();
        var td = document.createElement("div");
        td.id = tid;
        td.style.cssText = "display:flex;gap:7px;";
        td.innerHTML = '<div style="width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,#00e5a0,#00c47a);display:flex;align-items:center;justify-content:center;flex-shrink:0"><span style="font-size:8px;font-weight:800;color:#0a1a12">BB</span></div>' +
            '<div style="padding:8px 12px;border-radius:10px;font-size:12px;background:#1e1e26;color:#555;border:1px solid #2a2a35;border-left:3px solid #00e5a0">Reading document\u2026</div>';
        if (msgs) { msgs.appendChild(td); msgs.scrollTop = msgs.scrollHeight; }

        frappe.call({
            method: "erp_assistant.erp_assistant.api.pdf.ask_with_doc",
            args: { question: msg, doc_id: self._doc.doc_id, doc_name: self._doc.name },
            timeout: 180,
            callback: function(r) {
                var el = document.getElementById(tid); if (el) el.remove();
                var answer = (r.message || "I couldn\'t find an answer in the document.");
                self.addMsg("a", answer);
                self._history.push({role: "assistant", content: answer});
                self._waiting = false;
            },
            error: function() {
                var el = document.getElementById(tid); if (el) el.remove();
                self.addMsg("a", "\u274C Error reading document. Check your API key.");
                self._waiting = false;
            }
        });
    };
})();

// ── Complete send() override — handles both normal chat AND PDF RAG ──────────
erp_assistant.widget.send = function(msg) {
    if (!msg || this._waiting) return;
    var self = this;
    self.addMsg("u", msg);
    self._history.push({role: "user", content: msg});
    self._waiting = true;

    var msgs = document.getElementById("eca-msgs");
    var tid  = "et" + Date.now();
    var td   = document.createElement("div");
    td.id    = tid;
    td.style.cssText = "display:flex;gap:7px;";
    var thinkLabel = self._doc ? "Reading document\u2026" : "Thinking\u2026";
    td.innerHTML =
        '<div style="width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,#00e5a0,#00c47a);display:flex;align-items:center;justify-content:center;flex-shrink:0">' +
        '<span style="font-size:8px;font-weight:800;color:#0a1a12">BB</span></div>' +
        '<div style="padding:8px 12px;border-radius:10px;font-size:12px;background:#1e1e26;color:#555;border:1px solid #2a2a35;border-left:3px solid #00e5a0">' + thinkLabel + '</div>';
    if (msgs) { msgs.appendChild(td); msgs.scrollTop = msgs.scrollHeight; }

    var method, args, onSuccess;

    if (self._doc) {
        // ── PDF RAG mode ──────────────────────────────────────────────────────
        method = "erp_assistant.erp_assistant.api.pdf.ask_with_doc";
        args   = { question: msg, doc_id: self._doc.doc_id, doc_name: self._doc.name };
        onSuccess = function(r) {
            var el = document.getElementById(tid); if (el) el.remove();
            self.addMsg("a", r.message || "I couldn\'t find an answer in the document.");
            self._history.push({role: "assistant", content: r.message || ""});
            self._waiting = false;
        };
    } else {
        // ── Normal ERP chat mode ──────────────────────────────────────────────
        method = "erp_assistant.erp_assistant.api.chat.chat";
        args   = {
            message: msg,
            history: JSON.stringify(self._history.slice(-10)),
            session_data: JSON.stringify(self._session),
            context: JSON.stringify({
                route:     frappe.get_route     ? frappe.get_route()     : [],
                route_str: frappe.get_route_str ? frappe.get_route_str() : "",
                user:      frappe.session.user
            })
        };
        onSuccess = function(r) {
            var el = document.getElementById(tid); if (el) el.remove();
            var res = r.message;
            if (res) {
                self._session = res.session_data || {};
                self.addMsg("a", res.response || "No response.", res);
                self._history.push({role: "assistant", content: res.response || ""});
            }
            self._waiting = false;
        };
    }

    frappe.call({
        method: method, args: args, timeout: 180,
        callback: onSuccess,
        error: function() {
            var el = document.getElementById(tid); if (el) el.remove();
            self.addMsg("a", "\u274C Error. Check your Groq API key.");
            self._waiting = false;
        }
    });
};
