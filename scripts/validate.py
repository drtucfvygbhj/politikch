#!/usr/bin/env python3
"""Validate Politikch data files.

Run locally with:  python3 scripts/validate.py
                    python3 scripts/validate.py --ticker DIR   # only the session ticker files in DIR
Exits non-zero (and prints what's wrong) if any check fails, so it can
gate merges in CI.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

LANGS = ["en", "de", "fr", "it", "rm"]
errors = []


def load(name):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errors.append(f"{name}: invalid JSON — {e}")
        return None


def check_parties(data):
    if not data:
        return
    parties = data.get("parties", {})
    nc = sum(p.get("ncSeats", 0) for p in parties.values())
    cs = sum(p.get("csSeats", 0) for p in parties.values())
    if nc != 200:
        errors.append(f"parties.json: National Council seats sum to {nc}, expected 200")
    if cs != 46:
        errors.append(f"parties.json: Council of States seats sum to {cs}, expected 46")
    for key, p in parties.items():
        for field in ("name", "abbr", "color", "spectrum", "website"):
            if field not in p:
                errors.append(f"parties.json: {key} missing '{field}'")
        if "en" not in p.get("name", {}):
            errors.append(f"parties.json: {key} name missing English label")
        sp = p.get("spectrum", {})
        for axis in ("x", "y"):
            v = sp.get(axis)
            if not isinstance(v, (int, float)) or not (0 <= v <= 100):
                errors.append(f"parties.json: {key} spectrum.{axis} must be 0–100")


def check_cantons(data):
    if not data:
        return
    cantons = data.get("cantons", {})
    if len(cantons) != 26:
        errors.append(f"cantons.json: expected 26 cantons, found {len(cantons)}")
    seats = sum(c.get("seats", 0) for c in cantons.values())
    if seats != 200:
        errors.append(f"cantons.json: National Council seats sum to {seats}, expected 200")
    for code, c in cantons.items():
        for field in ("name", "capital", "pop", "area", "seats", "language", "desc"):
            if field not in c:
                errors.append(f"cantons.json: {code} missing '{field}'")


def check_initiatives(data):
    if not data:
        return
    for i, init in enumerate(data.get("initiatives", [])):
        label = init.get("id", f"index {i}")
        if init.get("type") not in ("initiative", "referendum"):
            errors.append(f"initiatives.json: {label} has invalid type '{init.get('type')}'")
        if init.get("status") not in ("adopted", "rejected", "pending", "collecting", "upcoming"):
            errors.append(f"initiatives.json: {label} has invalid status '{init.get('status')}'")
        for field in ("title", "desc", "date", "url"):
            if field not in init:
                errors.append(f"initiatives.json: {label} missing '{field}'")
        if "en" not in init.get("title", {}):
            errors.append(f"initiatives.json: {label} title missing English text")
        par = init.get("parliament")
        if par is not None:
            if not re.fullmatch(r"\d{2}\.\d{3}", str(par.get("business", ""))):
                errors.append(f"initiatives.json: {label} parliament.business must look like 24.092")
            if par.get("form") not in (None, "mandatory", "optional", "initiative", "counter", "tiebreak"):
                errors.append(f"initiatives.json: {label} parliament.form invalid")
            if par.get("position") not in (None, "accept", "reject", "none", "counter", "initiative"):
                errors.append(f"initiatives.json: {label} parliament.position invalid")
            for k in ("ncFor", "ncAgainst"):
                if k in par and (not isinstance(par[k], int) or par[k] < 0):
                    errors.append(f"initiatives.json: {label} parliament.{k} must be a non-negative integer")
            link = par.get("link")
            if link is not None and not (isinstance(link.get("session"), int) and isinstance(link.get("vote"), int)):
                errors.append(f"initiatives.json: {label} parliament.link must hold integer session and vote")


def check_financing(data, parties_data, initiatives_data):
    if not data:
        return  # financing.json is optional: absent means "show the placeholder"
    known_parties = set((parties_data or {}).get("parties", {}).keys())
    known_initiatives = {i.get("id") for i in (initiatives_data or {}).get("initiatives", [])}

    for key, entry in data.get("parties", {}).items():
        if key not in known_parties:
            errors.append(f"financing.json: party '{key}' not found in parties.json")
        for field in ("totalRevenue", "monetaryDonations", "nonMonetaryDonations"):
            v = entry.get(field)
            if not isinstance(v, (int, float)) or v < 0:
                errors.append(f"financing.json: party {key}.{field} must be a non-negative number")

    for key, sides in data.get("initiatives", {}).items():
        if key not in known_initiatives:
            errors.append(f"financing.json: initiative '{key}' not found in initiatives.json")
        for side in ("pro", "contra"):
            v = (sides.get(side) or {}).get("totalRevenue")
            if not isinstance(v, (int, float)) or v < 0:
                errors.append(f"financing.json: initiative {key}.{side}.totalRevenue must be a non-negative number")

    # GUARDRAILS.md PRIV-08: a private person's donation reveals a political
    # opinion, so an individual donor is only ever "Private individual" — the
    # data must carry no name or place for them.
    lists = [(f"parties.{k}", e.get("largeDonors")) for k, e in data.get("parties", {}).items()]
    lists += [(f"initiatives.{k}.{s}", (sides.get(s) or {}).get("largeDonors"))
              for k, sides in data.get("initiatives", {}).items() for s in ("pro", "contra")]
    for where, donors in lists:
        for d in donors or []:
            if d.get("type") != "organization" and ({"name", "location"} & d.keys()):
                errors.append(f"financing.json: {where} has a private individual with a name or place (PRIV-08)")


def check_sessions(index, parties_data):
    # sessions-index.json + data/sessions/<id>.json are optional: absent means
    # the Sessions page shows its honest "not fetched yet" empty state.
    if not index:
        return
    known_parties = set((parties_data or {}).get("parties", {}).keys())
    seasons = {"spring", "summer", "autumn", "winter", "special"}
    check_fetched("sessions-index.json", index)
    for i, s in enumerate(index.get("sessions", [])):
        label = s.get("id", f"index {i}")
        for field in ("id", "season", "year", "start"):
            if field not in s:
                errors.append(f"sessions-index.json: session {label} missing '{field}'")
        if s.get("season") not in seasons:
            errors.append(f"sessions-index.json: session {label} has invalid season '{s.get('season')}'")
        # Validate the per-session votes file if present.
        path = DATA / "sessions" / f"{s.get('id')}.json"
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            votes = doc.get("votes", [])
        except Exception as e:  # noqa: BLE001
            errors.append(f"sessions/{s.get('id')}.json: invalid JSON — {e}")
            continue
        check_fetched(f"sessions/{s.get('id')}.json", doc)
        for v in votes:
            tally = v.get("tally", {})
            for k in ("yes", "no", "abstain"):
                if not isinstance(tally.get(k), int) or tally.get(k) < 0:
                    errors.append(f"sessions/{s.get('id')}.json: vote {v.get('id')} tally.{k} must be a non-negative integer")
            if not v.get("title"):
                errors.append(f"sessions/{s.get('id')}.json: vote {v.get('id')} has no title")
            for pk in (v.get("byParty") or {}):
                if pk not in known_parties:
                    errors.append(f"sessions/{s.get('id')}.json: vote {v.get('id')} references unknown party '{pk}'")
            # A federal decree on a popular initiative: its Yes adopts Parliament's
            # recommendation. The direction is "reject", "accept" or explicitly
            # unknown (null) — never guessed.
            dec = v.get("initiativeDecree")
            if dec is not None and (not isinstance(dec, dict) or dec.get("recommend") not in ("reject", "accept", None)):
                errors.append(f"sessions/{s.get('id')}.json: vote {v.get('id')} initiativeDecree.recommend must be reject, accept or null")
            m = v.get("meaning")
            if m is not None and not (isinstance(m, dict) and all(isinstance(m.get(k, ""), str) for k in ("yes", "no"))):
                errors.append(f"sessions/{s.get('id')}.json: vote {v.get('id')} meaning must hold yes/no texts")
            title_de = ((v.get("title") or {}).get("de") or "").lower()
            if "meaning" in v and "volksinitiative" in title_de and "gegenentwurf" not in title_de \
                    and "gegenvorschlag" not in title_de and dec is None:
                errors.append(f"sessions/{s.get('id')}.json: vote {v.get('id')} is a decree on a popular initiative but has no initiativeDecree")


# SRC-12: parlament.ch's terms require the date and time of download next to
# the data, so every file from its web service records it (date, time, zone).
FETCHED_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z)$")


def check_fetched(where, doc):
    at = ((doc or {}).get("_meta") or {}).get("fetchedAt")
    if not isinstance(at, str) or not FETCHED_RE.match(at):
        errors.append(f"{where}: _meta.fetchedAt must hold the date and time of download with its time zone (SRC-12)")


# ---- Session ticker files (data/sessions/days/, published from the ticker-data branch) ----
# The ticker's legal limits are enforced here, on every file, before it is
# committed (session-ticker.yml) and again before it is deployed (deploy.yml):
#   SRC-12 download time · SRC-13 no speech text · POL-15 no computed outcome ·
#   PRIV-13 group tallies only, no individual votes or person identifiers ·
#   council of States votes are out of scope (owner decision 2026-10-05).
TICKER_ROLES = {"Mit-M", "Mit-F", "P-M", "P-F", "1VP-M", "1VP-F", "2VP-M", "2VP-F", "BR-M", "BR-F",
                "BPR-M", "BPR-F", "VPBR-M", "VPBR-F", "BK-M", "BK-F", "other"}
TICKER_FORBIDDEN_KEYS = {"text", "speech", "speeches_text", "transcript", "personnumber", "person", "firstname",
                         "lastname", "decision", "voters", "members", "member", "passed", "outcome", "result",
                         "adopted", "rejected", "photo", "image", "url", "link"}
RESIDENCE = re.compile(r"(?i)wohnhaft|domicili|residente|von [A-ZÄÖÜ][a-zäöü]+ \(")
HHMM = re.compile(r"^\d{2}:\d{2}$")
OFFICIAL_LANGS = {"de", "fr", "it"}


def check_ticker(folder, known_parties):
    folder = Path(folder)
    if not folder.exists():
        return
    def err(where, msg):
        errors.append(f"ticker {where}: {msg}")

    def keys(where, obj, allowed, required=()):
        if not isinstance(obj, dict):
            err(where, "must be an object")
            return False
        extra = set(obj) - set(allowed)
        if extra:
            err(where, f"unexpected field(s) {sorted(extra)}")
        for k in required:
            if k not in obj:
                err(where, f"missing '{k}'")
        return True

    def text(where, v, cap, optional=False):
        if v is None and optional:
            return
        if not isinstance(v, str) or not v.strip():
            err(where, "must be text")
        elif len(v) > cap:
            err(where, f"longer than {cap} characters ({len(v)}) — speech text is never stored (SRC-13)")
        elif MARKUP.search(v):
            err(where, f"looks like markup/script — {v[:60]!r}")

    def langs(where, v, cap):
        if keys(where, v, OFFICIAL_LANGS):
            for lg, t in v.items():
                text(f"{where}.{lg}", t, cap)

    def counts(where, v):
        if keys(where, v, ("yes", "no", "abstain"), ("yes", "no", "abstain")):
            for k, n in v.items():
                if not isinstance(n, int) or n < 0 or n > 200:
                    err(f"{where}.{k}", "must be a whole number from 0 to 200")

    def walk_forbidden(where, node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.lower() in TICKER_FORBIDDEN_KEYS and not (where.endswith("]") and k == "text" and ".decisions[" in where):
                    err(f"{where}.{k}", "field not allowed in ticker data (SRC-13 / PRIV-13 / POL-15)")
                walk_forbidden(f"{where}.{k}", v)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk_forbidden(f"{where}[{i}]", v)

    for path in sorted(folder.glob("*.json")):
        name = path.name
        try:
            doc = json.loads(path.read_text("utf-8"))
        except Exception as e:  # noqa: BLE001
            err(name, f"invalid JSON — {e}")
            continue
        walk_forbidden(name, {k: v for k, v in doc.items() if k != "_meta"})
        if name == "index.json":
            keys(name, doc, ("_meta", "days"), ("_meta", "days"))
            for i, day in enumerate(doc.get("days") or []):
                w = f"{name}.days[{i}]"
                if keys(w, day, ("date", "session", "fetchedAt", "counts", "decisions"), ("date", "fetchedAt")):
                    check_fetched(w, {"_meta": {"fetchedAt": day.get("fetchedAt")}})
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", name):
            err(name, "unexpected file in the ticker folder")
            continue
        keys(name, doc, ("_meta", "date", "session", "councils", "decisions"), ("_meta", "date", "session", "councils"))
        check_fetched(f"ticker {name}", doc)
        keys(f"{name}._meta", doc.get("_meta"), ("license", "licenseUrl", "attribution", "commercialReuse",
                                                  "source", "fetchedAt", "probe"))
        if doc.get("date") != name[:-5]:
            err(name, "date doesn't match the file name")
        sess = doc.get("session")
        if keys(f"{name}.session", sess, ("id", "season", "year"), ("id", "season", "year")):
            if not isinstance(sess.get("id"), int) or sess.get("season") not in {"spring", "summer", "autumn", "winter", "special"}:
                err(f"{name}.session", "invalid id or season")
        councils = doc.get("councils") or {}
        keys(f"{name}.councils", councils, ("N", "S", "V"))
        for c, body in councils.items():
            w = f"{name}.councils.{c}"
            # National Council votes only; the Council of States and the United
            # Federal Assembly have no vote list in the ticker (owner decision).
            allowed = ("meetings", "agenda", "speeches", "votes") if c == "N" else ("meetings", "agenda", "speeches")
            if not keys(w, body, allowed):
                continue
            for i, m in enumerate(body.get("meetings") or []):
                if keys(f"{w}.meetings[{i}]", m, ("id", "begin"), ("id",)) and m.get("begin") is not None \
                        and not HHMM.match(str(m["begin"])):
                    err(f"{w}.meetings[{i}].begin", "must be HH:MM")
            for i, a in enumerate(body.get("agenda") or []):
                wa = f"{w}.agenda[{i}]"
                if not keys(wa, a, ("subject", "meeting", "items"), ("subject", "items")):
                    continue
                for j, it in enumerate(a.get("items") or []):
                    wi = f"{wa}.items[{j}]"
                    if keys(wi, it, ("business", "businessId", "title", "note"), ("business", "title")):
                        text(f"{wi}.business", it.get("business"), 20)
                        langs(f"{wi}.title", it.get("title"), 1000)
                        text(f"{wi}.note", it.get("note"), 200, optional=True)
            for i, sp in enumerate(body.get("speeches") or []):
                ws = f"{w}.speeches[{i}]"
                # SRC-13 / PRIV-13: exactly who spoke, in what role, when — nothing else.
                if not keys(ws, sp, ("subject", "start", "end", "name", "role", "group", "canton"),
                            ("subject", "start", "end", "name", "role", "group", "canton")):
                    continue
                text(f"{ws}.name", sp.get("name"), 80)
                if sp.get("role") not in TICKER_ROLES:
                    err(f"{ws}.role", f"unknown role {sp.get('role')!r}")
                if sp.get("group") is not None and sp["group"] not in known_parties:
                    err(f"{ws}.group", f"unknown party {sp['group']!r}")
                if sp.get("canton") is not None and not re.fullmatch(r"[A-Z]{2}", str(sp["canton"])):
                    err(f"{ws}.canton", "must be a canton code")
                for k in ("start", "end"):
                    if sp.get(k) is not None and not HHMM.match(str(sp[k])):
                        err(f"{ws}.{k}", "must be HH:MM")
            for i, v in enumerate(body.get("votes") or []):
                wv = f"{w}.votes[{i}]"
                # POL-15: no outcome field; PRIV-13: tallies by group only.
                if not keys(wv, v, ("id", "time", "business", "businessId", "bill", "billTitle", "subject",
                                    "meaning", "tally", "byParty"), ("id", "tally", "byParty", "meaning")):
                    continue
                if not isinstance(v.get("id"), int):
                    err(f"{wv}.id", "must be a number")
                if v.get("time") is not None and not HHMM.match(str(v["time"])):
                    err(f"{wv}.time", "must be HH:MM")
                text(f"{wv}.subject", v.get("subject"), 200, optional=True)
                if keys(f"{wv}.meaning", v.get("meaning"), ("yes", "no"), ("yes", "no")):
                    for k in ("yes", "no"):
                        m = v["meaning"].get(k)
                        if not isinstance(m, str) or len(m) > 300 or MARKUP.search(m):
                            err(f"{wv}.meaning.{k}", "must be plain official text (≤ 300 characters)")
                if v.get("billTitle"):
                    langs(f"{wv}.billTitle", v["billTitle"], 1000)
                counts(f"{wv}.tally", v.get("tally"))
                if isinstance(v.get("byParty"), dict):
                    for pk, pv in v["byParty"].items():
                        if pk not in known_parties:
                            err(f"{wv}.byParty", f"unknown party {pk!r}")
                        counts(f"{wv}.byParty.{pk}", pv)
                else:
                    err(f"{wv}.byParty", "must be an object")
        for i, dcs in enumerate(doc.get("decisions") or []):
            wd = f"{name}.decisions[{i}]"
            if not keys(wd, dcs, ("council", "business", "businessId", "bill", "text"), ("council", "business", "text")):
                continue
            if dcs.get("council") not in ("N", "S"):
                err(f"{wd}.council", "must be N or S")
            langs(f"{wd}.text", dcs.get("text"), 120)
            for t in (dcs.get("text") or {}).values():
                if isinstance(t, str) and RESIDENCE.search(t):
                    err(f"{wd}.text", "reads like an election naming private persons — only standard decisions (PRIV-13)")


def check_parliament_links(initiatives_data):
    """Every automatic link points at a final vote that exists."""
    for init in (initiatives_data or {}).get("initiatives", []):
        link = (init.get("parliament") or {}).get("link")
        if not link:
            continue
        path = DATA / "sessions" / f"{link.get('session')}.json"
        try:
            ids = {v.get("id") for v in json.loads(path.read_text(encoding="utf-8")).get("votes", [])}
        except Exception:  # noqa: BLE001
            ids = set()
        if link.get("vote") not in ids:
            errors.append(f"initiatives.json: {init.get('id')} links to final vote {link.get('vote')} not found in sessions/{link.get('session')}.json")


def check_i18n(data):
    if not data:
        return
    for lang in LANGS:
        if lang not in data:
            errors.append(f"i18n.json: missing language '{lang}'")
    base = set(data.get("en", {}).keys())
    for lang in LANGS:
        if lang == "en" or lang not in data:
            continue
        diff = base ^ set(data[lang].keys())
        if diff:
            errors.append(f"i18n.json: '{lang}' key mismatch vs 'en': {sorted(diff)}")


# Upstream-derived files: written by the weekly fetch job from third-party
# sources (VoteInfo, LINDAS, Swissvotes, parlament.ch, EFK, BFS, DeepL) and
# published without human review. The site escapes this text, but anything that
# looks like markup or a script URL is a sign an upstream source changed or was
# tampered with — fail loudly here, before the job commits and deploys it.
UPSTREAM_FILES = [
    "initiatives.json", "financing.json", "canton-data.json",
    "sessions-index.json", "mt.json",
]
UPSTREAM_GLOBS = ["sessions/*.json", "overviews/*/*.json"]
MARKUP = re.compile(r"<\s*[a-zA-Z!/?]|javascript\s*:|\bon[a-z]+\s*=", re.I)
MAX_TEXT = 20000   # longest legitimate text today is a brochure argument (~4k)


def check_upstream_text():
    files = [DATA / f for f in UPSTREAM_FILES]
    for g in UPSTREAM_GLOBS:
        files.extend(sorted(DATA.glob(g)))

    def walk(node, where):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]")
        elif isinstance(node, str):
            if MARKUP.search(node):
                errors.append(f"{where}: looks like markup/script — {node[:80]!r}")
            elif len(node) > MAX_TEXT:
                errors.append(f"{where}: unexpectedly long text ({len(node)} chars)")

    for path in files:
        if path.exists():
            walk(json.loads(path.read_text(encoding="utf-8")), path.relative_to(DATA).as_posix())


def check_all_languages():
    # Editorial and composed texts must exist in every site language, so no page
    # quietly falls back to another language (official DE/FR/IT texts and their
    # machine translations are handled separately).
    def need(obj, where):
        if not isinstance(obj, dict):
            errors.append(f"{where} must be a per-language object")
            return
        missing = [l for l in LANGS if not (obj.get(l) or "").strip()]
        if missing:
            errors.append(f"{where} is missing {missing}")
    parties = (load("parties.json") or {}).get("parties", {})
    for k, pa in parties.items():
        need(pa.get("name"), f"parties.json: {k}.name")
        need(pa.get("desc"), f"parties.json: {k}.desc")
        for i, pos in enumerate(pa.get("positions") or []):
            need(pos.get("stance"), f"parties.json: {k}.positions[{i}].stance")
    for code, c in ((load("cantons.json") or {}).get("cantons", {})).items():
        for f in ("name", "capital", "language", "desc"):
            need(c.get(f), f"cantons.json: {code}.{f}")
    for slug, dd in ((load("donor-descriptions.json") or {}).get("donors", {})).items():
        need(dd.get("desc"), f"donor-descriptions.json: {slug}.desc")
    for it in ((load("initiatives.json") or {}).get("initiatives", [])):
        for f in ("desc", "date"):
            need(it.get(f), f"initiatives.json: {it.get('id')}.{f}")


def check_argument_text():
    # Official arguments must be clean verbatim text: no page furniture (vote
    # tables, footnotes, navigation, badge links) and never one side alone.
    sys.path.insert(0, str(ROOT / "scripts"))
    from fetch_arguments import FURNITURE, BADGE_LINK  # same rules as the fetcher
    for path in sorted((DATA / "overviews").rglob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        rel = path.relative_to(DATA).as_posix()
        for lang, block in (d.get("lang") or {}).items():
            if bool(block.get("pros")) != bool(block.get("cons")):
                errors.append(f"{rel}: {lang} has only one side (POL-01)")
            for side in ("pros", "cons"):
                for i, para in enumerate(block.get(side) or []):
                    if FURNITURE.search(para) or BADGE_LINK.search(para):
                        errors.append(f"{rel}: {lang}.{side}[{i}] contains page layout, not argument text")


def check_mt_args(data):
    # GUARDRAILS.md POL-01: a machine-translated argument set always carries both
    # sides; one side must never be published translated on its own.
    for iid, by_lang in (data or {}).get("args", {}).items():
        if not isinstance(by_lang, dict):
            errors.append(f"mt.json: args.{iid} must map language -> {{pros, cons}}")
            continue
        for tl, e in by_lang.items():
            if tl not in ("en", "it"):
                errors.append(f"mt.json: args.{iid}.{tl} is not a supported target language")
            if not (isinstance(e, dict) and e.get("pros") and e.get("cons")):
                errors.append(f"mt.json: args.{iid}.{tl} must have both pros and cons (POL-01)")


def main():
    if "--ticker" in sys.argv[1:]:
        i = sys.argv.index("--ticker")
        folder = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        check_ticker(folder, set(((load("parties.json") or {}).get("parties") or {}).keys()))
        if errors:
            print("Ticker validation FAILED:\n")
            for e in errors:
                print(f"  ✗ {e}")
            sys.exit(1)
        print("Ticker data checks passed ✓")
        return
    parties_data = load("parties.json")
    initiatives_data = load("initiatives.json")
    check_parties(parties_data)
    check_cantons(load("cantons.json"))
    check_initiatives(initiatives_data)
    check_i18n(load("i18n.json"))
    check_all_languages()
    check_argument_text()

    financing_path = DATA / "financing.json"
    if financing_path.exists():
        check_financing(load("financing.json"), parties_data, initiatives_data)

    if (DATA / "sessions-index.json").exists():
        check_sessions(load("sessions-index.json"), parties_data)
        check_parliament_links(initiatives_data)

    if (DATA / "mt.json").exists():
        check_mt_args(load("mt.json"))

    check_upstream_text()
    # Local replays of the ticker (data/sessions/days/ is git-ignored on main).
    check_ticker(DATA / "sessions" / "days", set(((parties_data or {}).get("parties") or {}).keys()))

    if errors:
        print("Validation FAILED:\n")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    print("All data checks passed ✓")


if __name__ == "__main__":
    main()
