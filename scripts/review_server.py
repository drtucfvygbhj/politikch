#!/usr/bin/env python3
"""Politikch — private local review desk.

Everything the maintainer needs, in one localhost page:
  * a **Run maintenance** button that triggers all Claude processes (translations
    + vote overviews) — no need to run anything from the terminal;
  * a **review queue** to approve / edit / reject each staged proposal;
  * a **history** of every run and every change, navigable down to the exact
    text approved for an item months ago;
  * automatic handover to an **official** title if one is published upstream
    after we generated an unofficial one, with a notification here.

Bound to 127.0.0.1 — it is only for you, never the public site. Stdlib only,
no API key, no external calls of its own (the Run button shells out to the local
`claude` CLI via scripts/ai_maintain.py, which uses your Claude login).

    python3 scripts/review_server.py    # → http://127.0.0.1:8777
"""
import http.server, json, os, signal, socketserver, subprocess, sys, threading, time, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_maintain  # same folder — for backlog counts + the usage file path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "review", "queue")
HISTORY_DIR = os.path.join(ROOT, "review", "history")
LOG = os.path.join(HISTORY_DIR, "log.jsonl")
DISMISSED = os.path.join(HISTORY_DIR, "dismissed.json")
USAGE_FILE = ai_maintain.USAGE_FILE
LANGS = ["en", "de", "fr", "it", "rm"]
LEVELS = 5
PORT = int(os.environ.get("REVIEW_PORT", "8777"))

# Background maintenance run (so completed items pop up live and it's stoppable).
RUN = {"proc": None, "thread": None, "lines": [], "running": False, "started": None, "args": None}


# ---------------------------------------------------------------- io helpers
def write_json_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def append_event(ev):
    ev.setdefault("ts", now())
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")


def read_events():
    if not os.path.isfile(LOG):
        return []
    out = []
    for line in open(LOG, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def read_dismissed():
    try:
        return set(json.load(open(DISMISSED, encoding="utf-8")))
    except Exception:
        return set()


def write_dismissed(s):
    write_json_atomic(DISMISSED, sorted(s))


# ---------------------------------------------------------------- queue + data
def list_queue():
    items = []
    for base, _d, files in os.walk(QUEUE):
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
    p = os.path.realpath(os.path.join(ROOT, rel))
    if not p.startswith(os.path.realpath(QUEUE) + os.sep) or not os.path.isfile(p):
        raise ValueError("bad path")
    return p


def trans_path(kind):
    return os.path.join(ROOT, f"data/{'initiatives' if kind == 'initiative' else 'sessions'}-translations.json")


def existing_titles(kind):
    try:
        return json.load(open(trans_path(kind), encoding="utf-8")).get("titles", {})
    except Exception:
        return {}


def apply_translation(kind, item_id, proposal):
    f = trans_path(kind)
    data = json.load(open(f, encoding="utf-8"))
    entry = {}
    if proposal.get("en"):
        entry["en"] = proposal["en"]
    if proposal.get("rm"):
        entry["rm"] = proposal["rm"]
    data.setdefault("titles", {})[item_id] = entry
    write_json_atomic(f, data)
    return os.path.relpath(f, ROOT)


def apply_overview(kind, item_id, proposal, source_url):
    out = {"generatedAt": time.strftime("%Y-%m-%d"), "model": "claude-cli",
           "reviewed": True, "sourceUrl": source_url, "lang": {}}
    for lg in LANGS:
        arr = [s.strip() for s in proposal["lang"][lg]]
        if len([s for s in arr if s]) != LEVELS:
            raise ValueError(f"{lg}: need {LEVELS} non-empty levels")
        out["lang"][lg] = arr
    path = os.path.join(ROOT, "data/overviews", kind, f"{item_id}.json")
    write_json_atomic(path, out)
    return os.path.relpath(path, ROOT)


# ---------------------------------------------------------------- data sources (for reconcile)
def load_initiatives():
    d = json.load(open(os.path.join(ROOT, "data/initiatives.json"), encoding="utf-8"))
    return d if isinstance(d, list) else d.get("initiatives", [])


def load_session_votes():
    import glob
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/sessions/*.json"))):
        try:
            for v in json.load(open(f, encoding="utf-8")).get("votes", []):
                out.append(v)
        except Exception:
            pass
    return out


def reconcile():
    """If an OFFICIAL title in a language now exists upstream, drop our unofficial
    translation for that language (the site already prefers official) and record a
    supersede notification. Idempotent: once removed, it isn't reported again."""
    actions = []

    def handle(kind, item_id, title_obj):
        f = trans_path(kind)
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            return
        entry = data.get("titles", {}).get(item_id)
        if not isinstance(entry, dict):
            return
        changed = False
        for lg in ("en", "rm"):
            official = (title_obj or {}).get(lg)
            if official and entry.get(lg):
                replaced = entry.pop(lg)
                changed = True
                actions.append({"kind": kind, "id": item_id, "lang": lg,
                                "official": official, "replaced": replaced})
        if changed:
            if entry:
                data["titles"][item_id] = entry
            else:
                data["titles"].pop(item_id, None)
            write_json_atomic(f, data)

    for it in load_initiatives():
        handle("initiative", it["id"], it.get("title"))
    for v in load_session_votes():
        handle("session", str(v["id"]), v.get("title"))

    for a in actions:
        append_event({"type": "supersede", "task": "translation", **a})
    return actions


def notifications():
    dismissed = read_dismissed()
    out = []
    for ev in read_events():
        if ev.get("type") != "supersede":
            continue
        eid = f"{ev['ts']}|{ev['kind']}/{ev['id']}|{ev['lang']}"
        if eid not in dismissed:
            out.append({**ev, "eid": eid})
    out.reverse()
    return out


# ---------------------------------------------------------------- run trigger (background + stoppable)
def _reader(proc, args):
    for line in iter(proc.stdout.readline, ""):
        RUN["lines"].append(line.rstrip("\n"))
        del RUN["lines"][:-500]
    try:
        proc.stdout.close()
    except Exception:
        pass
    rc = proc.wait()
    RUN["running"] = False
    try:
        reconcile()
    except Exception:
        pass
    staged = sum(1 for _b, _d, fs in os.walk(QUEUE) for f in fs if f.endswith(".json"))
    append_event({"type": "run", "task": args.get("task"), "dryRun": bool(args.get("dryRun")),
                  "stopped": args.get("stopped", False), "ok": rc == 0, "stagedTotal": staged,
                  "tail": "\n".join(RUN["lines"][-12:])})


def start_run(task, max_items, dry_run):
    if RUN["running"]:
        return False
    cmd = [sys.executable, "-u", os.path.join(ROOT, "scripts", "ai_maintain.py"), "--task", task]
    if max_items:
        cmd += ["--max", str(max_items)]
    if dry_run:
        cmd += ["--dry-run"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            cwd=ROOT, start_new_session=True, bufsize=1)
    RUN.update(proc=proc, running=True, started=now(), lines=[],
               args={"task": task, "dryRun": dry_run})
    t = threading.Thread(target=_reader, args=(proc, RUN["args"]), daemon=True)
    RUN["thread"] = t
    t.start()
    return True


def stop_run():
    proc = RUN.get("proc")
    if proc and RUN["running"]:
        RUN["args"]["stopped"] = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(0.3)
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
        RUN["running"] = False
        return True
    return False


_backlog_cache = {"at": 0, "tr": None, "ov": None}


def backlog_counts():
    # Scanning every session file is a bit heavy; cache for a few seconds so
    # the 2s status poll during a run stays cheap.
    if time.time() - _backlog_cache["at"] > 8:
        try:
            _backlog_cache.update(at=time.time(),
                                  tr=len(ai_maintain.translation_tasks()),
                                  ov=len(ai_maintain.overview_tasks()))
        except Exception:
            _backlog_cache.update(at=time.time(), tr=None, ov=None)
    return _backlog_cache["tr"], _backlog_cache["ov"]


def usage_stats():
    try:
        u = json.load(open(USAGE_FILE, encoding="utf-8"))
    except Exception:
        u = {}
    def avg(task):
        t = u.get(task) or {}
        return (t.get("cost", 0.0) / t["items"]) if t.get("items") else None
    tr_avg, ov_avg = avg("translation"), avg("overview")
    tr_left, ov_left = backlog_counts()
    est = None
    if tr_avg is not None and ov_avg is not None and tr_left is not None:
        est = tr_left * tr_avg + ov_left * ov_avg
    return {"perTask": u, "trAvg": tr_avg, "ovAvg": ov_avg,
            "trLeft": tr_left, "ovLeft": ov_left, "estBacklogUsd": est}


# ---------------------------------------------------------------- HTTP
class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "") or u.path.startswith("/index"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/queue":
            return self._send(200, json.dumps({"items": list_queue(), "notifications": notifications()}, ensure_ascii=False))
        if u.path == "/api/history":
            evs = list(reversed(read_events()))
            item = q.get("item", [None])[0]
            if item:
                evs = [e for e in evs if f"{e.get('kind')}/{e.get('id')}" == item]
            return self._send(200, json.dumps({"events": evs[:500]}, ensure_ascii=False))
        if u.path == "/api/run/status":
            return self._send(200, json.dumps({"running": RUN["running"], "started": RUN["started"],
                                               "lines": RUN["lines"][-30:]}, ensure_ascii=False))
        if u.path == "/api/usage":
            return self._send(200, json.dumps(usage_stats(), ensure_ascii=False))
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:  # noqa: BLE001
            return self._send(400, json.dumps({"error": str(e)}))

        try:
            if u.path == "/api/run":
                started = start_run(body.get("task", "all"), int(body.get("max", 0) or 0), bool(body.get("dryRun")))
                if not started:
                    return self._send(409, json.dumps({"error": "a run is already in progress"}))
                return self._send(200, json.dumps({"started": True}))

            if u.path == "/api/run/stop":
                return self._send(200, json.dumps({"stopped": stop_run()}))

            if u.path == "/api/reconcile":
                return self._send(200, json.dumps({"actions": reconcile()}, ensure_ascii=False))

            if u.path == "/api/dismiss":
                d = read_dismissed(); d.add(body["eid"]); write_dismissed(d)
                return self._send(200, json.dumps({"ok": True}))

            # queue actions need a staged file
            path = safe_queue_path(body["file"])
            item = json.load(open(path, encoding="utf-8"))
            title = item.get("title") or (item.get("official", {}) or {}).get("de") or item["id"]
            proposal = body.get("proposal", item.get("proposal"))

            if u.path == "/api/save":
                item["proposal"] = proposal
                write_json_atomic(path, item)
                return self._send(200, json.dumps({"ok": True}))

            if u.path == "/api/reject":
                os.remove(path)
                append_event({"type": "reject", "task": item["task"], "kind": item["kind"],
                              "id": item["id"], "title": title})
                return self._send(200, json.dumps({"ok": True}))

            if u.path == "/api/approve":
                if item["task"] == "translation":
                    written = apply_translation(item["kind"], item["id"], proposal)
                elif item["task"] == "overview":
                    written = apply_overview(item["kind"], item["id"], proposal, item.get("sourceUrl"))
                else:
                    raise ValueError("unknown task")
                os.remove(path)
                append_event({"type": "approve", "task": item["task"], "kind": item["kind"],
                              "id": item["id"], "title": title, "snapshot": proposal, "written": written})
                return self._send(200, json.dumps({"ok": True, "written": written}))
        except Exception as e:  # noqa: BLE001
            return self._send(400, json.dumps({"error": str(e)}))
        self._send(404, json.dumps({"error": "unknown action"}))


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Politikch — review desk (private)</title>
<style>
:root{--red:#D0021B;--ink:#1a1a1a;--mid:#6b6b6b;--border:#e5e2d9;--paper:#faf9f6}
*{box-sizing:border-box} body{font-family:system-ui,-apple-system,'DM Sans',sans-serif;margin:0;background:var(--paper);color:var(--ink)}
header{background:var(--ink);color:#fff;padding:14px 22px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
header b{font-size:18px}.tag{font-size:11px;background:rgba(255,255,255,.15);padding:2px 8px;border-radius:20px}
.run{margin-left:auto;display:flex;gap:8px;align-items:center}
select,.run input{font:inherit;font-size:13px}
.btn{font:inherit;font-weight:600;border-radius:8px;padding:7px 14px;cursor:pointer;border:1px solid var(--border);background:#fff}
.btn-run{background:var(--red);border-color:var(--red);color:#fff}
.btn-run:disabled{opacity:.6;cursor:default}
.tabs{display:flex;gap:4px;background:#fff;border-bottom:1px solid var(--border);padding:0 22px}
.tab{padding:12px 16px;cursor:pointer;border-bottom:2px solid transparent;color:var(--mid);font-weight:600}
.tab.active{color:var(--ink);border-bottom-color:var(--red)}
main{max-width:940px;margin:0 auto;padding:20px}
.empty{color:var(--mid);padding:40px;text-align:center;border:1px dashed var(--border);border-radius:12px}
.note{background:#fff8e6;border:1px solid #e6cf7a;border-radius:10px;padding:10px 14px;margin-bottom:10px;font-size:13px;display:flex;gap:10px;align-items:flex-start}
.note b{color:#7a5a00}.note .x{margin-left:auto;cursor:pointer;color:var(--mid);border:none;background:none;font-size:16px}
.card{background:#fff;border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.chd{display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap}
.pill{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;border-radius:20px;padding:2px 9px}
.pill-translation{background:rgba(59,111,176,.12);color:#2f6f8f}.pill-overview{background:rgba(142,107,191,.14);color:#5b4a8a}
.pill-approve{background:rgba(47,143,91,.14);color:#2f6f4b}.pill-reject{background:rgba(208,2,27,.10);color:var(--red)}
.pill-run{background:rgba(0,0,0,.06);color:var(--mid)}.pill-supersede{background:#fff2cc;color:#7a5a00}
.cid{font-size:12px;color:var(--mid)}.ctitle{font-weight:600;margin:2px 0 6px}.ts{font-size:11px;color:var(--mid)}
.ref{font-size:12px;color:var(--mid);margin:4px 0 10px}.ref a{color:var(--red)}
label{display:block;font-size:12px;font-weight:600;color:var(--mid);margin:10px 0 3px}
input.t,textarea{width:100%;font:inherit;font-size:14px;padding:8px 10px;border:1px solid var(--border);border-radius:8px;background:#fff}
textarea{min-height:70px;resize:vertical;line-height:1.5}
.hint{font-size:11px;color:var(--mid);margin-top:2px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.actions{display:flex;gap:8px;margin-top:12px}.approve{background:#2f8f5b;border-color:#2f8f5b;color:#fff}.reject{color:var(--red)}
.msg{font-size:12px;color:var(--mid);margin-left:auto;align-self:center}
.snap{background:var(--paper);border:1px solid var(--border);border-radius:8px;padding:10px;font-size:13px;white-space:pre-wrap;margin-top:6px}
.hfilter{display:flex;gap:8px;margin-bottom:12px}.hfilter input{flex:1}
.small{font-size:12px;color:var(--mid)}
.pbar{max-width:940px;margin:12px auto 0;padding:0 22px}
.runbox{background:#101010;color:#d6e5c8;border-radius:10px;padding:10px 14px;font:12px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;max-height:150px;overflow:auto}
.ubox{background:#fff;border:1px solid var(--border);border-radius:12px;padding:14px 16px;display:flex;gap:20px;flex-wrap:wrap;align-items:center}
.umetric b{font-size:20px}.umetric{font-size:12px;color:var(--mid)}
.ubar{height:10px;border-radius:6px;background:var(--paper);border:1px solid var(--border);overflow:hidden;min-width:120px}
.ubar span{display:block;height:100%}
</style></head><body>
<header><b>Politikch review desk</b><span class="tag">private · localhost only</span>
  <span class="run">
    <select id="task"><option value="all">All</option><option value="translation">Translations</option><option value="overview">Overviews</option></select>
    <input id="max" type="number" min="0" placeholder="max" title="max items this run (blank = as many as your limit allows)" style="width:64px;padding:6px 8px;border-radius:8px;border:1px solid var(--border)">
    <label class="small" style="display:flex;gap:4px;align-items:center;margin:0;color:#fff"><input type="checkbox" id="dry"> dry-run</label>
    <button class="btn btn-run" id="run">▶ Run maintenance</button>
    <button class="btn" id="stop" style="display:none;background:#7a1020;color:#fff;border-color:#7a1020">■ Stop</button>
  </span>
</header>
<div class="tabs"><div class="tab active" data-tab="review">Review queue</div><div class="tab" data-tab="history">History</div></div>
<div id="runbar" class="pbar" style="display:none"></div>
<div id="usage" class="pbar"></div>
<main id="main"><p class="empty">Loading…</p></main>
<script>
const main=document.getElementById('main');
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let TAB='review';
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===t));TAB=t.dataset.tab;render();});
document.getElementById('run').onclick=runNow;
document.getElementById('stop').onclick=async()=>{
  document.getElementById('stop').disabled=true;
  await fetch('/api/run/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
};

let POLL=null;
function setRunning(on){
  document.getElementById('run').style.display=on?'none':'';
  document.getElementById('stop').style.display=on?'':'none';
  document.getElementById('stop').disabled=false;
}
async function runNow(){
  try{
    const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({task:document.getElementById('task').value,max:parseInt(document.getElementById('max').value||'0',10)||0,dryRun:document.getElementById('dry').checked})});
    const j=await r.json();
    if(j.error){ alert(j.error); return; }
  }catch(e){ alert('Could not start: '+e); return; }
  startPolling();
}
function startPolling(){ setRunning(true); if(POLL) clearInterval(POLL); POLL=setInterval(pollStatus,2000); pollStatus(); }
async function pollStatus(){
  let s; try{ s=await (await fetch('/api/run/status')).json(); }catch(e){ return; }
  const bar=document.getElementById('runbar'); bar.style.display='block';
  const last=(s.lines||[]).slice(-8).join('\n');
  bar.innerHTML=`<div class="runbox"><b>${s.running?'● Running — completed items appear below as they finish':'✓ Run finished'}</b>\n${esc(last)}</div>`;
  setRunning(s.running);
  if(TAB==='review') await renderReview();      // staged items pop up live
  await renderUsage();
  if(!s.running && POLL){ clearInterval(POLL); POLL=null; }
}
async function renderUsage(){
  let u; try{ u=await (await fetch('/api/usage')).json(); }catch(e){ return; }
  const box=document.getElementById('usage');
  const money=v=>v==null?'—':('$'+v.toFixed(v<0.01?4:3));
  const per=v=>(v&&v>0)?Math.floor(1/v):null;
  const maxAvg=Math.max(u.trAvg||0,u.ovAvg||0,0.0001);
  const bar=(v,c)=>`<div class="ubar"><span style="width:${Math.min(100,Math.round((v||0)/maxAvg*100))}%;background:${c}"></span></div>`;
  const est=u.estBacklogUsd;
  box.innerHTML=`<div class="ubox">
    <div class="umetric">avg / translation<br><b>${money(u.trAvg)}</b> ${bar(u.trAvg,'#2f6f8f')}</div>
    <div class="umetric">avg / overview<br><b>${money(u.ovAvg)}</b> ${bar(u.ovAvg,'#5b4a8a')}</div>
    <div class="umetric">still to generate<br><b>${u.trLeft==null?'—':u.trLeft}</b> translations · <b>${u.ovLeft==null?'—':u.ovLeft}</b> overviews</div>
    <div class="umetric">est. to finish backlog<br><b>${money(est)}</b>${est!=null?` <span class="small">(usage-cost proxy)</span>`:''}</div>
    ${u.trAvg?`<div class="umetric">per $1 of usage<br><b>~${per(u.trAvg)||'—'}</b> translations${u.ovAvg?` · <b>~${per(u.ovAvg)||'—'}</b> overviews`:''}</div>`:'<div class="umetric small">Run once to measure average costs.</div>'}
  </div>`;
}
async function render(){ TAB==='review'?renderReview():renderHistory(); renderUsage(); }

async function renderReview(){
  const {items,notifications}=await (await fetch('/api/queue')).json();
  let html=(notifications||[]).map(n=>`<div class="note" data-eid="${esc(n.eid)}"><div><b>Official title adopted</b> — ${esc(n.kind)} ${esc(n.id)} (${esc(n.lang).toUpperCase()}). The official version is now shown; our generated one was retired.<div class="small">official: ${esc(n.official)}</div></div><button class="x" title="dismiss">×</button></div>`).join('');
  if(!items.length){ html+='<p class="empty">Queue is empty. Click <b>Run maintenance</b> above to generate proposals.</p>'; }
  else html+=items.map(card).join('');
  main.innerHTML=html;
  document.querySelectorAll('.note .x').forEach(x=>x.onclick=async()=>{await fetch('/api/dismiss',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({eid:x.closest('.note').dataset.eid})});x.closest('.note').remove();});
  items.forEach(wire);
}
function card(it){
  const head=`<div class="chd"><span class="pill pill-${it.task}">${it.task}</span><span class="cid">${esc(it.kind)} · ${esc(it.id)}</span></div>`;
  if(it.task==='translation'){
    const off=it.official||{}; const ref=Object.keys(off).map(k=>`<b>${k.toUpperCase()}</b> ${esc(off[k])}`).join(' &nbsp;·&nbsp; ');
    return `<div class="card" data-file="${esc(it._file)}" data-task="translation">${head}<div class="ref">${ref}</div>
      <div class="grid"><div><label>English (en)</label><input class="t" data-f="en" value="${esc(it.proposal.en)}"></div>
      <div><label>Romansh (rm)</label><input class="t" data-f="rm" value="${esc(it.proposal.rm)}"></div></div>${actions()}</div>`;
  }
  const boxes=['en','de','fr','it','rm'].map(lg=>`<div><label>${lg.toUpperCase()} — 5 levels, one per line</label><textarea data-lg="${lg}">${esc((it.proposal.lang[lg]||[]).join('\n'))}</textarea></div>`).join('');
  return `<div class="card" data-file="${esc(it._file)}" data-task="overview">${head}<div class="ctitle">${esc(it.title||'')}</div>
    ${it.sourceUrl?`<div class="ref"><a href="${esc(it.sourceUrl)}" target="_blank" rel="noopener">official source ↗</a></div>`:''}
    ${boxes}<div class="hint">Each box needs exactly 5 non-empty lines.</div>${actions()}</div>`;
}
function actions(){return `<div class="actions"><button class="btn approve">Approve & publish</button><button class="btn save">Save edits</button><button class="btn reject">Reject</button><span class="msg"></span></div>`;}
function collect(c){
  if(c.dataset.task==='translation') return {en:c.querySelector('[data-f=en]').value.trim(),rm:c.querySelector('[data-f=rm]').value.trim()};
  const lang={}; c.querySelectorAll('textarea[data-lg]').forEach(t=>lang[t.dataset.lg]=t.value.split('\n').map(s=>s.trim()).filter(Boolean)); return {lang};
}
function wire(it){
  const c=document.querySelector(`.card[data-file="${CSS.escape(it._file)}"]`); const msg=c.querySelector('.msg');
  const post=async u=>{ msg.textContent='…';
    const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file:it._file,proposal:collect(c)})});
    const j=await r.json();
    if(j.ok){ if(u==='/api/save') msg.textContent='saved'; else {c.remove(); if(!document.querySelector('.card'))renderReview();} } else msg.textContent='⚠ '+(j.error||'error'); };
  c.querySelector('.approve').onclick=()=>post('/api/approve');
  c.querySelector('.save').onclick=()=>post('/api/save');
  c.querySelector('.reject').onclick=()=>{ if(confirm('Reject and discard this proposal?')) post('/api/reject'); };
}

let HFILTER='';
async function renderHistory(){
  const {events}=await (await fetch('/api/history')).json();
  const bar=`<div class="hfilter"><input class="t" id="hf" placeholder="filter by id or title…" value="${esc(HFILTER)}"><span class="small" style="align-self:center">${events.length} event(s)</span></div>`;
  const list=events.filter(e=>{ if(!HFILTER) return true; const s=(e.id+' '+(e.title||'')+' '+(e.task||'')).toLowerCase(); return s.includes(HFILTER.toLowerCase()); });
  main.innerHTML=bar+(list.length?list.map(hcard).join(''):'<p class="empty">No matching history yet.</p>');
  const hf=document.getElementById('hf'); hf.oninput=()=>{HFILTER=hf.value; const p=hf.selectionStart; renderHistory().then(()=>{const n=document.getElementById('hf'); if(n){n.focus(); n.setSelectionRange(p,p);} });};
  document.querySelectorAll('[data-item]').forEach(a=>a.onclick=e=>{e.preventDefault(); HFILTER=a.dataset.item; renderHistory();});
}
function hcard(e){
  const when=`<span class="ts">${esc((e.ts||'').replace('T',' '))}</span>`;
  if(e.type==='run') return `<div class="card"><div class="chd"><span class="pill pill-run">run</span>${when}</div><div class="small">task: ${esc(e.task)} · ${e.dryRun?'dry-run · ':''}${e.ok?'ok':'issue'} · ${e.stagedTotal} staged after</div><div class="snap">${esc(e.tail||'')}</div></div>`;
  if(e.type==='supersede') return `<div class="card"><div class="chd"><span class="pill pill-supersede">official adopted</span><span class="cid"><a href="#" data-item="${esc(e.kind+'/'+e.id)}">${esc(e.kind)} · ${esc(e.id)}</a> · ${esc(e.lang).toUpperCase()}</span>${when}</div><div class="small">official now: ${esc(e.official)}</div><div class="small">retired ours: ${esc(e.replaced)}</div></div>`;
  const pill=e.type==='approve'?'pill-approve':'pill-reject';
  let snap='';
  if(e.type==='approve'&&e.snapshot){ snap = e.task==='translation'
      ? `<div class="snap">EN: ${esc(e.snapshot.en||'—')}\nRM: ${esc(e.snapshot.rm||'—')}</div>`
      : `<div class="snap">${['en','de','fr','it','rm'].map(lg=>lg.toUpperCase()+':\n  '+((e.snapshot.lang&&e.snapshot.lang[lg])||[]).join('\n  ')).join('\n\n')}</div>`; }
  return `<div class="card"><div class="chd"><span class="pill ${pill}">${esc(e.type)}</span><span class="pill pill-${e.task}">${esc(e.task)}</span><span class="cid"><a href="#" data-item="${esc(e.kind+'/'+e.id)}">${esc(e.kind)} · ${esc(e.id)}</a></span>${when}</div><div class="ctitle">${esc(e.title||'')}</div>${snap}</div>`;
}
render();
fetch('/api/run/status').then(r=>r.json()).then(s=>{ if(s.running) startPolling(); }).catch(()=>{});
</script></body></html>"""


def main():
    os.makedirs(QUEUE, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    reconcile()  # catch any official titles that appeared since last time
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Review desk on http://127.0.0.1:{PORT}  (private; Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")


if __name__ == "__main__":
    main()
