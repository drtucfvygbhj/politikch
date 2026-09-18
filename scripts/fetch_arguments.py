#!/usr/bin/env python3
"""Fetch official pro/con vote arguments from the Federal Council brochure.

This is the build-time replacement for the AI-generated "overview" flow (the
review desk). Instead of an LLM writing a summary that a human must approve, we
extract the **official** text of the Federal Council's voting brochure
("Erläuterungen des Bundesrates" / Abstimmungsbüechli) verbatim, so nothing is
fabricated and nothing needs editorial sign-off.

Source & limits (see the `brochure-arguments-source` memo / politikch-api skill):
- The brochure PDFs are hosted per vote by Swissvotes:
  https://swissvotes.ch/vote/<anr>.00/brochure-{de,fr}.pdf
- Swissvotes carries **DE and FR only** (no IT/RM) and lags the newest ballots.
  Missing languages fall back on the site (a language chip); missing votes get
  no file and the page keeps its honest "being prepared" placeholder.
- The brochure is one multi-item PDF per ballot date. Each vorlage has separate,
  consistently-headed pages we group into sections:
    * summary  — "In Kürze" / "L'essentiel en bref"
    * pros     — "Argumente Initiativkomitee|Referendumskomitee"
                 / "Arguments du comité d'initiative|référendaire"
    * cons     — "Argumente Bundesrat und Parlament"
                 / "Arguments du Conseil fédéral et du Parlement"
  A section is identified for a given vote by its "<Ordinal> Vorlage: <title>"
  subtitle, matched to the vote's German title by token overlap.

Output: data/overviews/initiative/<id>.json (single reading level, no `reviewed`
gate), shape:
  {
    "generatedAt": "YYYY-MM-DD",
    "source": "Federal Council voting explanations (Erläuterungen) … Art. 5 URG",
    "sourceUrl": {"de": "…brochure-de.pdf", "fr": "…brochure-fr.pdf"},
    "lang": {
      "de": {"pros": ["…"], "cons": ["…"]},
      "fr": {"pros": ["…"], "cons": ["…"]}
    }
  }
Neutral framing stays the initiative's own title/desc already on the page; only
the official pro (committee) and con (Federal Council & Parliament) arguments are
added here. EN/RM (and IT when no local PDF is supplied) fall back on-site.

Needs pymupdf (see scripts/requirements-arguments.txt); runs offline / in CI,
never in the browser. Honesty rule: if a section can't be found, it is omitted
rather than guessed — never fabricate political argument text.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_DIR = DATA / "overviews" / "initiative"

SWISSVOTES_CSV = "https://swissvotes.ch/page/dataset/swissvotes_dataset.csv"
# Swissvotes vote pages/assets use a two-decimal id, e.g. anr 688 -> 688.00.
BROCHURE_URL = "https://swissvotes.ch/vote/{anr}/brochure-{lang}.pdf"
# The official brochure covers DE/FR/IT; Swissvotes hosts DE/FR only, so IT
# (and RM/EN) come, if at all, from a locally-supplied official PDF (--pdf-dir).
BROCHURE_LANGS = ("de", "fr")

# Argument-section running headers per language. Only the two argument sections
# are extracted — they are the official pro/con. The neutral framing is the
# initiative's own title/description already on the page, so no fragile
# "In Kürze" summary parsing (its pages carry no distinguishing heading).
SECTION_HEADERS = {
    "de": {
        "pros": r"Argumente\s+(?:Initiativkomitee|Referendumskomitee)",
        "cons": r"Argumente\s+Bundesrat\s+und\s+Parlament",
    },
    "fr": {  # "du" is present in some editions (2022) and dropped in others (2026)
        "pros": r"Arguments\s+(?:du\s+)?[Cc]omit[ée]\s+(?:d[’']initiative|r[ée]f[ée]rendaire)",
        "cons": r"Arguments\s+(?:du\s+)?Conseil\s+f[ée]d[ée]ral\s+et\s+(?:du\s+)?Parlement",
    },
    "it": {
        "pros": r"Argoment[io]\s+(?:del\s+)?[Cc]omitato\s+(?:d[’']iniziativa|referendario)",
        "cons": r"Argoment[io]\s+(?:del\s+)?Consiglio\s+federale\s+e\s+(?:del\s+)?Parlamento",
    },
}
# Subtitle that names which vorlage a section belongs to.
VORLAGE_SUBTITLE = {
    "de": r"(?:Erste|Zweite|Dritte|Vierte|F[üu]nfte|Sechste|Siebte|Achte)\s+Vorlage\s*:",
    "fr": r"(?:Premier|Deuxi[èe]me|Troisi[èe]me|Quatri[èe]me|Cinqui[èe]me|Sixi[èe]me|"
          r"Septi[èe]me|Huiti[èe]me)\s+objet\s*:",
    "it": r"(?:Primo|Secondo|Terzo|Quarto|Quinto|Sesto|Settimo|Ottavo)\s+"
          r"(?:oggetto|progetto)\s*:",
}
# Attribution line the brochure prints on the committee (pro) spread — kept out
# of the extracted argument body (we surface authorship in the UI instead).
ATTRIB_LINE = re.compile(
    r"(Der Text auf dieser Doppelseite stammt.*?verantwortlich\.|"
    r"Le texte de cette double page émane.*?responsable\.|"
    r"Le comité d[’']initiative est seul responsable.*?ci-dessus\.|"
    r"Il testo di questa doppia pagina proviene.*?responsabile\.|"
    r"Il comitato d[’']iniziativa è il solo responsabile.*?sopra\.)",
    re.S)

_TITLE_STOP = {"und", "der", "die", "das", "für", "den", "des", "eine", "einen",
               "von", "zur", "zum", "mit", "vom", "über", "auf", "initiative",
               "volksinitiative", "bundesgesetz", "änderung", "referendum"}


def http_get(url, retries=6):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.read()
        except Exception as e:  # noqa: BLE001 — transient proxy/network errors
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def norm_tokens(text):
    text = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", " ", (text or "").lower())
    text = re.sub(r"[«»'\"“”’()–—\-.,!?:;]", " ", text)
    return {w for w in text.split() if len(w) > 3 and w not in _TITLE_STOP}


# ---------------------------------------------------------------------------
# Swissvotes: vote (date + German title) -> anr (vote number for the PDF URL)
# ---------------------------------------------------------------------------
def load_swissvotes_index():
    """Return {dateIso: [{anr, tokens}]} from the Swissvotes dataset."""
    print("Fetching Swissvotes dataset (anr lookup)...")
    try:
        raw = http_get(SWISSVOTES_CSV).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"  ! Swissvotes fetch failed ({e})", file=sys.stderr)
        return {}
    if not raw.lstrip().lower().startswith(tuple("anr")) and ";" not in raw[:200]:
        print("  ! Swissvotes did not return the CSV (blocked?)", file=sys.stderr)
        return {}
    reader = csv.DictReader(io.StringIO(raw), delimiter=";")
    by_date = {}
    anr_key = None
    for row in reader:
        if anr_key is None:
            anr_key = next((k for k in row if k and "anr" in k.lower()), None)
        anr = (row.get(anr_key) or "").strip() if anr_key else ""
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", (row.get("datum") or "").strip())
        if not anr or not m:
            continue
        date_iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        title = row.get("titel_off_d") or row.get("titel_kurz_d") or ""
        by_date.setdefault(date_iso, []).append(
            {"anr": anr, "tokens": norm_tokens(title)})
    print(f"  indexed {sum(len(v) for v in by_date.values())} Swissvotes ballots")
    return by_date


def anr_for_vote(item, sv_index):
    cands = sv_index.get(item.get("voteDate"), [])
    itok = norm_tokens((item.get("title") or {}).get("de", ""))
    best, best_score = None, 0.0
    for r in cands:
        if not r["tokens"] or not itok:
            continue
        score = len(r["tokens"] & itok) / min(len(r["tokens"]), len(itok))
        if score > best_score:
            best, best_score = r, score
    return (best["anr"], best_score) if best and best_score >= 0.5 else (None, 0.0)


# ---------------------------------------------------------------------------
# Brochure PDF -> per-vorlage {summary, pros, cons} sections (verbatim)
# ---------------------------------------------------------------------------
# Structural headers that END an argument section, so a con section can't run on
# into the next vorlage's material (Abstimmungstext / Im Detail / In Kürze).
BOUNDARY_HEADERS = {
    "de": r"Abstimmungstext|Im\s+Detail|In\s+K[üu]rze",
    "fr": r"Texte\s+soumis\s+au\s+vote|En\s+d[ée]tail|L[’']?essentiel\s+en\s+bref",
    "it": r"Testo\s+in\s+votazione|Nei\s+dettagli|In\s+breve",
}


def brochure_sections(pdf_bytes, lang):
    """Parse a brochure PDF into [{kind, subtitle, tokens, text}] argument sections.

    Each vorlage is laid out as In Kürze / Im Detail / Argumente Initiativkomitee
    (pro) / Argumente Bundesrat und Parlament (con) / Abstimmungstext. Some
    editions repeat the "<Ordinal> Vorlage: <title>" subtitle on the argument
    page, others only on the Im-Detail pages — so we carry the current vorlage as
    a *running context* and bound each argument section by the next structural
    header. Requires pymupdf.
    """
    import pymupdf  # imported lazily so --help works without the dep

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    headers = SECTION_HEADERS[lang]
    ctx_rx = re.compile(VORLAGE_SUBTITLE[lang] + r"\s+([^\d]{3,70})", re.I)
    bound_rx = re.compile(BOUNDARY_HEADERS[lang], re.I)
    arg_starts = []       # (page_index, kind, ctx_title)
    boundaries = set()    # page indices that end a section
    ctx_title = ""
    for i, pg in enumerate(doc):
        flat = " ".join(pg.get_text().split())
        cm = ctx_rx.search(flat)
        if cm:
            ctx_title = " ".join(cm.group(1).split())[:70]
        has_pro = re.search(headers["pros"], flat, re.I)
        has_con = re.search(headers["cons"], flat, re.I)
        # A page listing both argument headers next to page numbers is the TOC.
        is_toc = bool(has_pro and has_con)
        matched_kind = None
        if not is_toc and len(flat) > 250:
            for kind, hrx in headers.items():
                m = re.search(hrx, flat, re.I)
                # A real section page has the header NOT immediately followed by a
                # page number (that pattern is a table-of-contents line).
                if m and not re.match(r"\s*\d", flat[m.end():m.end() + 4]):
                    matched_kind = kind
                    break
        if matched_kind:
            arg_starts.append((i, matched_kind, ctx_title))
        elif bound_rx.search(flat) and len(flat) > 120:
            boundaries.add(i)
    cut_pages = sorted({s[0] for s in arg_starts} | boundaries | {len(doc)})
    sections = []
    for page_i, kind, subtitle in arg_starts:
        end = next((c for c in cut_pages if c > page_i), len(doc))
        body = "\n".join((doc[p].get_text() or "") for p in range(page_i, end))
        sections.append({
            "kind": kind,
            "subtitle": subtitle.strip(" :–-"),
            "tokens": norm_tokens(subtitle),
            "text": _clean_section(body, lang, kind),
        })
    doc.close()
    return sections


def _clean_section(body, lang, kind):
    """Verbatim text of a section: drop page numbers, header, subtitle, chrome."""
    # Remove the header phrase and everything before it on the first line.
    hrx = SECTION_HEADERS[lang][kind]
    body = re.sub(r"^.*?" + hrx, "", body, count=1, flags=re.S | re.I)
    body = re.sub(VORLAGE_SUBTITLE[lang], "", body, flags=re.I)
    body = ATTRIB_LINE.sub("", body)
    # Rejoin words split by a soft hyphen at a line break (e.g. "Eigen­\n
    # verantwortung" -> "Eigenverantwortung"); the soft hyphen always marks a
    # split word, so this is safe (unlike ambiguous real hyphens, left as-is).
    body = re.sub(r"­\s*", "", body)
    # Split into paragraphs, drop bare page numbers / bullet glyphs.
    paras = []
    for chunk in re.split(r"\n\s*\n", body):
        line = re.sub(r"[•·­]", "", chunk)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or re.fullmatch(r"\d{1,3}", line):
            continue
        line = re.sub(r"^\d{1,3}\s+", "", line)  # leading printed page number
        if len(line) < 3:
            continue
        paras.append(line)
    return paras


def match_section(sections, item, kind):
    """Pick the section of `kind` whose vorlage best matches the vote's title.

    Uses raw token-overlap and takes the single clear winner. A brochure has only
    a handful of vorlagen, and the right one shares the distinctive short name
    (e.g. "Ernährungsinitiative"), so the highest overlap is reliable. Ties and
    zero-overlap-with-alternatives are skipped rather than guessed (never
    fabricate an association).
    """
    itok = norm_tokens((item.get("title") or {}).get("de", "")) \
        | norm_tokens((item.get("title") or {}).get("fr", ""))
    cands = sorted(((len(s["tokens"] & itok), s)
                    for s in sections if s["kind"] == kind and s["tokens"]),
                   key=lambda x: x[0], reverse=True)
    if not cands:
        return None
    if len(cands) == 1:                     # sole candidate of this kind
        return cands[0][1]
    if cands[0][0] == 0:                     # nothing matches — don't guess
        return None
    if cands[0][0] > cands[1][0]:            # a single clear winner
        return cands[0][1]
    return None                              # ambiguous tie — skip


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
# All official-brochure languages we can render natively. DE/FR come from
# Swissvotes automatically; IT only if an official PDF is supplied via --pdf-dir
# (Swissvotes has no IT). EN/RM are never in the brochure and fall back on-site.
LANGS_ALL = ("de", "fr", "it")


def anr_path(anr):
    """Swissvotes id for the URL: CSV anr 688 -> '688.00', 550.1 -> '550.10'."""
    try:
        return f"{float(anr):.2f}"
    except (TypeError, ValueError):
        return str(anr)


def _load_local_pdf(pdf_dir, date_iso, lang):
    """Official brochure a maintainer dropped in, named <YYYYMMDD>-<lang>.pdf.

    One file per ballot date covers every vorlage on that date. Used mainly to
    add native Italian, which Swissvotes doesn't host.
    """
    if not pdf_dir or not date_iso:
        return None
    ymd = date_iso.replace("-", "")
    for name in (f"{ymd}-{lang}.pdf", f"{ymd}_{lang}.pdf"):
        p = Path(pdf_dir) / name
        if p.exists():
            data = p.read_bytes()
            return data if data[:4] == b"%PDF" else None
    return None


def build_for_item(item, sv_index, brochure_cache, pdf_dir=None):
    anr, score = anr_for_vote(item, sv_index)
    date_iso = item.get("voteDate")
    out_lang, source_url = {}, {}
    for lang in LANGS_ALL:
        pdf, url = None, None
        local = _load_local_pdf(pdf_dir, date_iso, lang)
        if local:                                   # official PDF supplied locally
            pdf, url = local, item.get("url")
        elif anr and lang in BROCHURE_LANGS:        # Swissvotes-hosted official PDF
            key = (anr, lang)
            if key not in brochure_cache:
                u = BROCHURE_URL.format(anr=anr_path(anr), lang=lang)
                try:
                    data = http_get(u)
                    brochure_cache[key] = data if data[:4] == b"%PDF" else None
                except Exception:  # noqa: BLE001
                    brochure_cache[key] = None
            pdf = brochure_cache[key]
            url = BROCHURE_URL.format(anr=anr_path(anr), lang=lang)
        if not pdf:
            continue
        try:
            sections = brochure_sections(pdf, lang)
        except Exception as e:  # noqa: BLE001
            print(f"    ! parse failed ({lang}) for {item['id']}: {e}",
                  file=sys.stderr)
            continue
        block = {}
        for kind in ("pros", "cons"):
            sec = match_section(sections, item, kind)
            if sec and sec["text"]:
                block[kind] = sec["text"]
        if block.get("pros") or block.get("cons"):
            out_lang[lang] = block
            if url:
                source_url[lang] = url
    if not out_lang:
        return None, ("no brochure/section found" if anr else "no Swissvotes match")
    return {
        "generatedAt": date.today().isoformat(),
        "source": "Federal Council voting explanations (Erläuterungen des "
                  "Bundesrates), Federal Chancellery — official text under Art. 5 URG",
        "sourceUrl": source_url,
        "lang": out_lang,
    }, f"ok (anr {anr}, {'+'.join(out_lang)}, score {score:.2f})"


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N eligible initiatives")
    ap.add_argument("--only", default="",
                    help="process a single initiative id (e.g. vote-20220613-6570)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing output files")
    ap.add_argument("--out", default=str(OUT_DIR), help="output directory")
    ap.add_argument("--pdf-dir", default=str(DATA / "brochures"),
                    help="folder with official brochure PDFs named "
                         "<YYYYMMDD>-<lang>.pdf (e.g. add native IT here); "
                         "these override/extend the Swissvotes-hosted DE/FR")
    args = ap.parse_args(argv)
    pdf_dir = args.pdf_dir if Path(args.pdf_dir).is_dir() else None

    data = json.loads((DATA / "initiatives.json").read_text("utf-8"))
    items = data["initiatives"] if isinstance(data, dict) else data
    # Only votes that reached (or are scheduled for) a ballot have a brochure.
    eligible = [it for it in items
                if it.get("type") == "initiative" and it.get("voteDate")]
    if args.only:
        eligible = [it for it in eligible if it["id"] == args.only]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    sv_index = load_swissvotes_index()
    if not sv_index and not pdf_dir:
        print("No Swissvotes index and no --pdf-dir — nothing to source from.",
              file=sys.stderr)
        return 0  # never break CI on a flaky source

    cache = {}
    wrote = skipped = 0
    for it in eligible:
        dest = out_dir / f"{it['id']}.json"
        if dest.exists() and not args.force:
            skipped += 1
            continue
        result, why = build_for_item(it, sv_index, cache, pdf_dir)
        title = (it.get("title") or {}).get("de", it["id"])[:50]
        if result:
            dest.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                            "utf-8")
            wrote += 1
            print(f"  ✓ {it['id']}  {why}  [{title}]")
        else:
            print(f"  – {it['id']}  skip: {why}  [{title}]")
        if args.limit and wrote >= args.limit:
            break
    print(f"\nDone. wrote={wrote} skipped(existing)={skipped} "
          f"eligible={len(eligible)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
