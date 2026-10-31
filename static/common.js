const $ = s => document.querySelector(s);
async function api(path, opt = {}) {
  const r = await fetch(path, {method: opt.method || (opt.body ? "POST" : "GET"), headers: {"Content-Type": "application/json"}, body: opt.body ? JSON.stringify(opt.body) : undefined, credentials: "same-origin"});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Something went wrong (" + r.status + ")");
  return d;
}
async function loadNotice(role) { const n = await api("/api/notice/" + role); $("#notice-text").textContent = n.text; $("#notice-ver").textContent = "Notice version " + n.version; }
function add(parent, tag, text, cls) { const e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; parent.appendChild(e); return e; }
