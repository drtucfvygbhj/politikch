#!/usr/bin/env python3
"""A tiny LOCAL, private review desk for AI-staged upkeep.

Run it after `ai_maintain.py` has staged proposals:

    python3 scripts/review_server.py      # then open http://127.0.0.1:8777

It lists every pending proposal in review/queue/ (translations + overviews),
lets you edit the text and Approve / Reject each one. Approving writes the
(edited) content into the LIVE data files:
  * translation -> data/<initiatives|sessions>-translations.json  (titles.<id>)
  * overview    -> data/overviews/<kind>/<id>.json  (reviewed: true)
and removes it from the queue. Nothing reaches the site until you approve it,
and this server is bound to 127.0.0.1 — it is only for you, not the public site.

Stdlib only. No API key, no external calls, no dependency.
"""
import http.server, json, os, socketserver, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "review", "queue")
LANGS = ["en", "de", "fr", "it", "rm"]
LEVELS = 5
PORT = int(os.environ.get("REVIEW_PORT", "8777"))


def list_queue():
    items = []
    for base, _dirs, files in os.walk(QUEUE):
        for f in sorted(files):
            if not f.endswith(".json"):
                continue
            path = os.path.join(base, f)
            try:
                data = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            data["_file"] = os.path.relpath(path, ROOT)
            items.append(data)
    items.sort(key=lambda d: (d.get("task", ""), d.get("kind", ""), d.get("id", "")))
    return items


def safe_queue_path(rel):
    """Resolve a client-supplied queue path, refusing anything outside QUEUE."""
    p = os.path.realpath(os.path.join(ROOT, rel))
    if not p.startswith(os.path.realpath(QUEUE) + os.sep) or not os.path.isfile(p):
        raise ValueError("bad path")
    return p


def apply_translation(kind, item_id, proposal):
    f = os.path.join(ROOT, f"data/{'initiatives' if kind == 'initiative' else 'sessions'}-translations.json")
    data = json.load(open(f, encoding="utf-8"))
    data.setdefault("titles", {})[item_id] = {"en": proposal["en"], "rm": proposal["rm"]}
    json.dump(data, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return os.path.relpath(f, ROOT)


def apply_overview(kind, item_id, proposal, source_url):
    d = os.path.join(ROOT, "data/overviews", kind)
    os.makedirs(d, exist_ok=True)
    out = {"generatedAt": __import__("time").strftime("%Y-%m-%d"), "model": "claude-cli",
           "reviewed": True, "sourceUrl": source_url, "lang": {}}
    for lg in LANGS:
        arr = [s.strip() for s in proposal["lang"][lg]]
        if len([s for s in arr if s]) != LEVELS:
            raise ValueError(f"{lg}: need {LEVELS} non-empty levels")
        out["lang"][lg] = arr
    path = os.path.join(d, f"{item_id}.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return os.path.relpath(path, ROOT)


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/api/queue":
            return self._send(200, json.dumps({"items": list_queue()}, ensure_ascii=False))
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            path = safe_queue_path(body["file"])
            item = json.load(open(path, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            return self._send(400, json.dumps({"error": str(e)}))

        action = urllib.parse.urlparse(self.path).path
        try:
            if action == "/api/reject":
                os.remove(path)
                return self._send(200, json.dumps({"ok": True, "removed": body["file"]}))

            proposal = body.get("proposal", item.get("proposal"))
            if action == "/api/save":
                item["proposal"] = proposal
                json.dump(item, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                return self._send(200, json.dumps({"ok": True, "saved": body["file"]}))

            if action == "/api/approve":
                # Target paths are derived from the item, never from the client.
                if item["task"] == "translation":
                    written = apply_translation(item["kind"], item["id"], proposal)
                elif item["task"] == "overview":
                    written = apply_overview(item["kind"], item["id"], proposal, item.get("sourceUrl"))
                else:
                    raise ValueError("unknown task")
                os.remove(path)
                return self._send(200, json.dumps({"ok": True, "written": written}))
        except Exception as e:  # noqa: BLE001
            return self._send(400, json.dumps({"error": str(e)}))
        self._send(404, json.dumps({"error": "unknown action"}))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Politikch — review desk (private)</title>
<style>
:root{--red:#D0021B;--ink:#1a1a1a;--mid:#6b6b6b;--border:#e5e2d9;--paper:#faf9f6}
*{box-sizing:border-box} body{font-family:system-ui,-apple-system,'DM Sans',sans-serif;margin:0;background:var(--paper);color:var(--ink)}
header{background:var(--ink);color:#fff;padding:16px 22px;display:flex;align-items:center;gap:12px}
header b{font-size:18px} .tag{font-size:11px;background:rgba(255,255,255,.15);padding:2px 8px;border-radius:20px}
main{max-width:900px;margin:0 auto;padding:22px}
.empty{color:var(--mid);padding:40px;text-align:center;border:1px dashed var(--border);border-radius:12px}
.card{background:#fff;border:1px solid var(--border);border-radius:12px;padding:18px;margin-bottom:16px}
.chd{display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap}
.pill{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;border-radius:20px;padding:2px 9px}
.pill-translation{background:rgba(59,111,176,.12);color:#2f6f8f}
.pill-overview{background:rgba(142,107,191,.14);color:#5b4a8a}
.cid{font-size:12px;color:var(--mid)} .ctitle{font-weight:600;margin:2px 0 6px}
.ref{font-size:12px;color:var(--mid);margin:4px 0 10px}
.ref a{color:var(--red)}
label{display:block;font-size:12px;font-weight:600;color:var(--mid);margin:10px 0 3px}
input,textarea{width:100%;font:inherit;font-size:14px;padding:8px 10px;border:1px solid var(--border);border-radius:8px;background:#fff}
textarea{min-height:74px;resize:vertical;line-height:1.5}
.hint{font-size:11px;color:var(--mid);margin-top:2px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.actions{display:flex;gap:8px;margin-top:14px}
button{font:inherit;font-weight:600;border-radius:8px;padding:8px 16px;cursor:pointer;border:1px solid var(--border);background:#fff}
.approve{background:#2f8f5b;border-color:#2f8f5b;color:#fff}
.reject{color:var(--red);border-color:rgba(208,2,27,.4)}
.msg{font-size:12px;color:var(--mid);margin-left:auto;align-self:center}
</style></head><body>
<header><b>Politikch review desk</b><span class="tag">private · localhost only</span></header>
<main id="app"><p class="empty">Loading…</p></main>
<script>
const app=document.getElementById('app');
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function load(){
  const {items}=await (await fetch('/api/queue')).json();
  if(!items.length){app.innerHTML='<p class="empty">Nothing to review. Run <code>python3 scripts/ai_maintain.py</code> to stage proposals.</p>';return;}
  app.innerHTML=items.map(card).join('');
  items.forEach(wire);
}
function card(it){
  const head=`<div class="chd"><span class="pill pill-${it.task}">${it.task}</span>
    <span class="cid">${esc(it.kind)} · ${esc(it.id)}</span></div>`;
  if(it.task==='translation'){
    const off=it.official||{};
    const ref=Object.keys(off).map(k=>`<b>${k.toUpperCase()}</b> ${esc(off[k])}`).join(' &nbsp;·&nbsp; ');
    return `<div class="card" data-file="${esc(it._file)}" data-task="translation">${head}
      <div class="ref">${ref}</div>
      <div class="grid">
        <div><label>English (en)</label><input data-f="en" value="${esc(it.proposal.en)}"></div>
        <div><label>Romansh (rm)</label><input data-f="rm" value="${esc(it.proposal.rm)}"></div>
      </div>${actions()}</div>`;
  }
  const langs=['en','de','fr','it','rm'];
  const boxes=langs.map(lg=>`<div><label>${lg.toUpperCase()} — 5 levels, one per line (brief → in depth)</label>
     <textarea data-lg="${lg}">${esc((it.proposal.lang[lg]||[]).join('\\n'))}</textarea></div>`).join('');
  return `<div class="card" data-file="${esc(it._file)}" data-task="overview">${head}
     <div class="ctitle">${esc(it.title||'')}</div>
     ${it.sourceUrl?`<div class="ref"><a href="${esc(it.sourceUrl)}" target="_blank" rel="noopener">official source ↗</a></div>`:''}
     ${boxes}<div class="hint">Each box must have exactly 5 non-empty lines.</div>${actions()}</div>`;
}
function actions(){return `<div class="actions">
  <button class="approve">Approve & publish</button>
  <button class="save">Save edits</button>
  <button class="reject">Reject</button>
  <span class="msg"></span></div>`;}
function collect(card){
  if(card.dataset.task==='translation'){
    return {en:card.querySelector('[data-f=en]').value.trim(), rm:card.querySelector('[data-f=rm]').value.trim()};
  }
  const lang={}; card.querySelectorAll('textarea[data-lg]').forEach(t=>{
    lang[t.dataset.lg]=t.value.split('\\n').map(s=>s.trim()).filter(Boolean);
  });
  return {lang};
}
function wire(it){
  const card=document.querySelector(`.card[data-file="${CSS.escape(it._file)}"]`);
  const msg=card.querySelector('.msg');
  const post=async(url)=>{
    msg.textContent='…';
    const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({file:it._file,proposal:collect(card)})});
    const j=await r.json();
    if(j.ok){ if(url!=='/api/save'){card.remove(); if(!document.querySelector('.card'))load();} else msg.textContent='saved'; }
    else msg.textContent='⚠ '+(j.error||'error');
  };
  card.querySelector('.approve').onclick=()=>post('/api/approve');
  card.querySelector('.save').onclick=()=>post('/api/save');
  card.querySelector('.reject').onclick=()=>{ if(confirm('Reject and discard this proposal?')) post('/api/reject'); };
}
load();
</script></body></html>"""


def main():
    os.makedirs(QUEUE, exist_ok=True)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Review desk on http://127.0.0.1:{PORT}  (private; Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")


if __name__ == "__main__":
    main()
