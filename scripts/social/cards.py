"""Card builders: one function per post type, each returning a Post in one language.

A Post holds the HTML of each carousel page (rendered to PNG by render.py), the
caption, and the link. Every value from data/ goes through escape() before it is
placed in the HTML (the same rule as SEC-01 on the site). All fixed wording comes
from strings.json; official texts come from data/ word for word.

Rules these builders keep (GUARDRAILS.md): every proposal of a ballot in the same
post (POL-01); outcomes only as the official data states them, never worked out
from a percentage (POL-15 spirit); Parliament's votes in the official order with
no selection (POL-16); group tallies only (PRIV-13); Parliament data credited
with its download time (SRC-12); machine translations badged (POL-13); every card
shows the language's own domain and the "not an official government site" line.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from html import escape

import sitedata as sd
from sitedata import S, fill

TIER = {"correction": 0, "results": 5, "runup": 4, "initiatives": 3, "parliament": 2, "explained": 1}
ARROW = ('<span class="arrow"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" '
         'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
         '<path d="M5 12h14M13 6l6 6-6 6"></path></svg></span>')


def e(v):
    return escape(str(v), quote=True)


@dataclass
class Post:
    type: str
    key: str                  # what the post is about (cooldowns, dedup)
    section: str
    lang: str
    route: str                # the site route the post links to
    caption: str
    pages: list = field(default_factory=list)
    x: bool = False           # 16:9 image for X instead of an Instagram carousel

    @property
    def url(self):
        return S(self.lang)["domain"] + ("/#/" + self.route if self.route else "")


# ---------------------------------------------------------------- frame
def ladder(tier, lang):
    bars = "".join(f'<i class="{"" if i <= tier else "off"}" style="height:{9 + 7 * i}px"></i>' for i in range(1, 6))
    return f'<span class="ladder" role="img" aria-label="{e(fill(S(lang)["prioAria"], n=tier))}">{bars}</span>'


def frame(lang, section, body, src, page=1, total=1, x=False):
    s = S(lang)
    tier = TIER[section]
    right = f'<span class="stamp">{e(s["correction"]["stamp"])}</span>' if tier == 0 else ladder(tier, lang)
    cta = e(fill(s["moreOn"], domain=s["domain"])) + ("" if x else "<br>" + e(s["linkInBio"]))
    if total > 1 and page < total:
        pager = (f'<div class="pager" role="img" aria-label="{e(fill(s["pageAria"], n=page, total=total))}">'
                 f'<span class="pg">{page} / {total}</span>{ARROW}</div>')
    elif total > 1:
        pager = f'<div class="pager"><span class="endcta">{cta}</span><span class="pg">{page} / {total}</span></div>'
    else:
        pager = f'<div class="pager"><span class="endcta">{cta}</span></div>'
    return (f'<div class="card{" x" if x else ""}" lang="{lang}">'
            f'<div class="band t{tier}"><div class="sec">{e(s["sec"][section])}</div>{right}</div>'
            f'<div class="body">{body}</div>'
            f'<div class="foot"><div><div class="brand">Politikch</div>'
            f'<div class="dom">{e(s["domain"])} · {e(s["disclaimer"])}</div>'
            f'<div class="src">{e(src)}</div></div>{pager}</div></div>')


def paginate(lang, section, bodies, src, x=False):
    return [frame(lang, section, b, src, i + 1, len(bodies), x) for i, b in enumerate(bodies)]


def src_line(lang, *keys, asof=None, fetched=None, extra=""):
    s = S(lang)
    names = [s["src"][k] for k in keys if s["src"].get(k)]
    label = s["source"] if len(names) == 1 else s["sources"]
    out = f"{label}: " + "; ".join(names) if lang != "fr" else f"{label} : " + " ; ".join(names)
    if fetched:
        out += f" · {s['downloaded']} {fetched}"
    elif asof:
        out += f" · {s['asOf']}" + {"fr": " : ", "en": " "}.get(lang, ": ") + asof
    if extra:
        out += " · " + extra
    return out


def data_date():
    """The date the weekly data job downloaded the vote data (initiatives.json)."""
    return sd.date_num(dt.date.fromisoformat(sd.site()["initiatives"]["_meta"]["fetchedAt"][:10]))


def badge(kind, lang):
    if kind == "mt":
        return '<span class="mt">DeepL</span>'
    if kind == "unofficial":
        return f'<span class="mt">{e({"de": "inoffiziell", "fr": "non officiel", "it": "non ufficiale", "en": "unofficial"}[lang])}</span>'
    return ""


def title_html(v, lang, size, short=False):
    t, b = (sd.short_name if short else sd.vote_title)(v, lang)
    return f'<div class="vt" style="font-size:{size}px">{e(t)}{badge(b, lang)}</div>'


def type_label(v, lang):
    return S(lang)["type"].get(sd.vote_form(v), S(lang)["type"]["referendum"])


def bar(yes, height=48):
    no = round(100 - yes, 1)
    return (f'<div class="bar" style="height:{height}px" role="img" aria-label="{yes}/{no}">'
            f'<div class="yes" style="width:{yes}%"></div><div class="no" style="width:{no}%"></div>'
            f'<div class="mid"></div></div>')


def pct_row(yes, lang, size=24):
    s = S(lang)
    return (f'<div class="pct" style="font-size:{size}px"><span class="cy">{e(sd.pct(yes, lang))} {e(s["yes"].lower() if lang == "fr" else s["yes"])}</span>'
            f'<span class="cn">{e(sd.pct(round(100 - yes, 1), lang))} {e(s["no"].lower() if lang == "fr" else s["no"])}</span></div>')


def caption(lang, key, url, **kw):
    s = S(lang)
    return (fill(s["caption"][key], **kw) + "\n\n" + fill(s["caption"]["link"], url=url)
            + f"\n\nPolitikch · {s['disclaimer']}")


# ---------------------------------------------------------------- 1 Results
def results(votes, lang):
    """1.1: overview of every proposal of a ballot day, then one page per proposal."""
    s, d = S(lang), sd.vote_date(votes[0])
    src = src_line(lang, "voteinfo", asof=sd.date_num(d + dt.timedelta(days=1)))
    rows, compact = [], len(votes) > 2
    for v in votes:
        label, yes = sd.outcome(v, lang)
        rows.append(f'<div class="rule" style="display:flex;flex-direction:column;gap:{10 if compact else 14}px;padding-top:{18 if compact else 26}px">'
                    f'<div><span class="chip">{e(type_label(v, lang))}</span></div>'
                    f'{title_html(v, lang, 32 if compact else 44, short=True)}'
                    f'<div style="font-size:{24 if compact else 30}px;font-weight:600">{e(label)}</div>'
                    f'{bar(yes, 38 if compact else 52)}{pct_row(yes, lang, 21 if compact else 26)}</div>')
    bodies = []
    for i in range(0, len(rows), 4):
        bodies.append(f'<div class="kicker">{e(fill(s["results"]["kicker"], date=sd.date_long(d, lang)))}</div>'
                      f'<h1 class="h" style="font-size:{60 if compact else 72}px">{e(s["results"]["title"])}</h1>' + "".join(rows[i:i + 4]))
    for n, v in enumerate(votes, 1):
        label, yes = sd.outcome(v, lang)
        bodies.append(f'<div class="kicker">{e(fill(s["results"]["proposalOf"], n=n, total=len(votes)))} · {e(type_label(v, lang))}</div>'
                      f'{title_html(v, lang, 46)}'
                      f'<div class="rule" style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:24px">'
                      f'<div style="padding-top:24px"><div class="big cy" style="font-size:128px">{e(sd.pct(yes, lang))}</div><div class="lbl cy" style="margin-top:10px">{e(s["yes"])}</div></div>'
                      f'<div style="padding-top:24px;text-align:right"><div class="big cn" style="font-size:128px">{e(sd.pct(round(100 - yes, 1), lang))}</div><div class="lbl cn" style="margin-top:10px">{e(s["no"])}</div></div></div>'
                      f'{bar(yes, 56)}<div style="font-size:36px;font-weight:600">{e(label)}</div>')
    route = "ballots/decided"
    return Post("results", f"results:{d}", "results", lang, route,
                caption(lang, "results", f"{s['domain']}/#/{route}", date=sd.date_long(d, lang)),
                paginate(lang, "results", bodies, src))


def results_x(votes, lang):
    """1.1 for X: one 16:9 image with every proposal."""
    s, d = S(lang), sd.vote_date(votes[0])
    rows = ""
    for v in votes[:4]:
        label, yes = sd.outcome(v, lang)
        rows += (f'<div class="rule" style="display:flex;flex-direction:column;gap:9px;padding-top:14px">'
                 f'{title_html(v, lang, 30 if len(votes) < 3 else 24, short=True)}'
                 f'<div style="font-size:21px;font-weight:600">{e(label)}</div>{bar(yes, 34)}{pct_row(yes, lang, 19)}</div>')
    body = (f'<div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:56px;height:100%">'
            f'<div style="display:flex;flex-direction:column;gap:18px"><div class="kicker">{e(fill(s["results"]["kicker"], date=sd.date_long(d, lang)))}</div>'
            f'<h1 class="h" style="font-size:64px">{e(s["results"]["title"])}</h1></div>'
            f'<div style="display:flex;flex-direction:column;gap:16px;justify-content:center">{rows}</div></div>')
    route = "ballots/decided"
    src = src_line(lang, "voteinfo", asof=sd.date_num(d + dt.timedelta(days=1)))
    return Post("results_x", f"results:{d}", "results", lang, route,
                caption(lang, "results", f"{s['domain']}/#/{route}", date=sd.date_long(d, lang)),
                [frame(lang, "results", body, src, x=True)], x=True)


# ---------------------------------------------------------------- 2 Ballot run-up
def _ballot_rows(votes, lang, size=27):
    s = S(lang)
    out = ""
    for n, v in enumerate(votes, 1):
        maj = sd.needs_cantons(v)
        chip = f'<span class="maj">{e(s["majorityBoth"] if maj else s["majorityPeople"])}</span>' if maj is not None else ""
        out += (f'<div class="rule" style="display:flex;gap:20px;padding:18px 0"><div class="num" style="font-size:44px;width:46px">{n}</div>'
                f'<div style="display:flex;flex-direction:column;gap:10px"><div style="display:flex;gap:8px;flex-wrap:wrap">'
                f'<span class="chip">{e(type_label(v, lang))}</span>{chip}</div>{title_html(v, lang, size)}</div></div>')
    return out


def runup_overview(ballot, votes, lang, sunday=False):
    """2.1 + 2.3: what is on the ballot, then one fact page per proposal."""
    s = S(lang)
    kicker = s["runup"]["thisSunday"] if sunday else fill(s["runup"]["inWeeks"], n=6)
    bodies = [f'<div class="kicker">{e(kicker)}</div>'
              f'<h1 class="h" style="font-size:64px">{e(fill(s["runup"]["title"], date=sd.date_short(ballot, lang)))}</h1>'
              f'<div>{_ballot_rows(votes, lang, 27 if len(votes) <= 4 else 22)}</div>']
    for n, v in enumerate(votes, 1):
        p = v.get("parliament") or {}
        facts = ""
        maj = sd.needs_cantons(v)
        if maj is not None:
            facts += (f'<div class="rule" style="padding:18px 0;display:flex;flex-direction:column;gap:8px"><div class="lbl">{e(s["runup"]["required"])}</div>'
                      f'<div style="font-size:32px;font-weight:600">{e((s["majorityBoth"] if maj else s["majorityPeople"]).capitalize())}</div></div>')
        rec = sd.parliament_rec(v)
        if rec:
            facts += (f'<div class="rule" style="padding:18px 0;display:flex;flex-direction:column;gap:10px"><div class="lbl">{e(s["runup"]["parlRecommends"])}</div>'
                      f'<div><span class="pill {rec}" style="font-size:24px">{e(s[rec])}</span></div></div>')
        if p.get("ncFor") is not None:
            facts += (f'<div class="rule" style="padding:18px 0;display:flex;flex-direction:column;gap:8px"><div class="lbl">{e(s["runup"]["ncFinal"])}</div>'
                      f'<div style="font-size:32px;font-weight:600"><span class="cy">{p["ncFor"]} {e(s["yes"])}</span> · <span class="cn">{p["ncAgainst"]} {e(s["no"])}</span></div></div>')
        bodies.append(f'<div class="kicker">{e(fill(s["runup"]["proposal"], n=n))} · {e(type_label(v, lang))}</div>'
                      f'{title_html(v, lang, 46)}<div style="margin-top:auto">{facts}</div>')
    route = "ballots/upcoming"
    src = src_line(lang, "chancellery", "swissvotes", asof=data_date())
    return Post("runup_overview", f"runup:{ballot}:{'sunday' if sunday else 'w6'}", "runup", lang, route,
                caption(lang, "runupOverview", f"{s['domain']}/#/{route}", date=sd.date_long(ballot, lang)),
                paginate(lang, "runup", bodies, src))


def runup_recs(ballot, votes, lang):
    """2.4: Parliament's recommendation for every proposal, then the parties' grid."""
    s = S(lang)
    rows = ""
    for n, v in enumerate(votes, 1):
        rec, p = sd.parliament_rec(v), v.get("parliament") or {}
        pill = f'<span class="pill {rec}">{e(s[rec])}</span>' if rec else '<span class="pill abs">–</span>'
        nc = f'<div class="lbl" style="margin-top:8px;text-align:right">{e(s["runup"]["nc"])} {p["ncFor"]} : {p["ncAgainst"]}</div>' if p.get("ncFor") is not None else ""
        rows += (f'<div class="rule" style="display:grid;grid-template-columns:44px minmax(0, 1fr) 210px;gap:18px;align-items:center;padding:18px 0">'
                 f'<div class="num" style="font-size:42px">{n}</div>{title_html(v, lang, 24)}<div style="text-align:right">{pill}{nc}</div></div>')
    p1 = (f'<div class="kicker">{e(fill(s["runup"]["recsKicker"], date=sd.date_long(ballot, lang)))}</div>'
          f'<h1 class="h" style="font-size:58px">{e(s["runup"]["recsTitle"])}</h1><div>{rows}</div>')
    cols = len(votes)
    head = f'<div class="lbl">{e(s["runup"]["proposalCol"])}</div>' + "".join(f'<div class="num" style="font-size:36px;text-align:center">{n}</div>' for n in range(1, cols + 1))
    grid = f'<div style="display:grid;grid-template-columns:200px repeat({cols}, minmax(0, 1fr));gap:6px;align-items:center">{head}'
    for key in sd.parties_by_seats():
        grid += f'<div style="display:flex;align-items:center;gap:12px;font-size:23px;font-weight:600"><span class="dot" style="background:{e(sd.party_color(key))}"></span>{e(sd.party_short(key, lang))}</div>'
        for v in votes:
            r = (v.get("recommendations") or {}).get(key)
            cls, lbl = ({"yes": ("yes", s["yes"]), "no": ("no", s["no"])}).get(r, ("", "–"))
            style = "color:#fff" if cls else "background:#F6F4F0;color:#7D7A72"
            grid += f'<div class="cell {cls}" style="{style}">{e(lbl)}</div>'
    grid += "</div>"
    p2 = (f'<div class="kicker">{e(s["runup"]["partiesKicker"])}</div>'
          f'<h1 class="h" style="font-size:54px">{e(s["runup"]["partiesTitle"])}</h1>{grid}'
          f'<p class="p muted" style="margin-top:auto;font-size:19px">{e(s["runup"]["partiesNote"])}</p>')
    route = "ballots/upcoming"
    src = src_line(lang, "swissvotes", asof=data_date())
    return Post("runup_recs", f"runup:{ballot}:recs", "runup", lang, route,
                caption(lang, "runupRecs", f"{s['domain']}/#/{route}", date=sd.date_long(ballot, lang)),
                paginate(lang, "runup", [p1, p2], src))


def runup_args(ballot, votes, lang):
    """2.5: one page per proposal; the first sentence of every argument, both sides alike."""
    s = S(lang)
    bodies, any_mt = [], False
    for n, v in enumerate(votes, 1):
        a = sd.arguments(v["id"], lang)
        head = (f'<div class="kicker">{e(fill(s["runup"]["argsKicker"], n=n, type=type_label(v, lang)))}</div>'
                f'{title_html(v, lang, 44)}')
        if not a or not a["pros"] or not a["cons"]:
            bodies.append(head + f'<p class="p" style="font-size:28px;margin-top:40px">{e(fill(s["runup"]["argsMissing"], domain=s["domain"]))}</p>')
            continue
        any_mt = any_mt or a["mt"]
        def side(items, who, cls, label):
            out = (f'<div style="display:flex;flex-direction:column;gap:16px;padding:22px 24px 26px;background:#F6F4F0;border-top:10px solid {"#534AB7" if cls == "cy" else "#0F6E56"}">'
                   f'<div class="lbl {cls}">{e(label)}</div><div style="font-size:23px;font-weight:600">{e(s["runup"]["sides"].get(who, ""))}</div>')
            for k, txt in enumerate(items, 1):
                out += (f'<div class="rule" style="display:flex;flex-direction:column;gap:8px;padding-top:14px"><div class="num {cls}" style="font-size:28px">{k}</div>'
                        f'<div style="font-size:{23 if len(items) < 4 else 19}px;line-height:1.4">{e(sd.first_sentence(txt))} …{badge("mt", lang) if a["mt"] else ""}</div></div>')
            return out + "</div>"
        sides = a["sides"]
        bodies.append(head + f'<div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:20px">'
                      f'{side(a["pros"], sides.get("pros"), "cy", s["for"])}{side(a["cons"], sides.get("cons"), "cn", s["against"])}</div>'
                      f'<p class="p" style="margin-top:auto;font-size:20px">{e(fill(s["runup"]["argsNote"], domain=s["domain"]))}</p>')
    route = "ballots/upcoming"
    src = src_line(lang, "explanations", extra=s["mtNote"] if any_mt else "")
    return Post("runup_args", f"runup:{ballot}:args", "runup", lang, route,
                caption(lang, "runupArgs", f"{s['domain']}/#/{route}", date=sd.date_long(ballot, lang)),
                paginate(lang, "runup", bodies, src))


def runup_money(ballot, votes, lang):
    """2.6: declared campaign money for every proposal on one scale, then one page each."""
    s, fin = S(lang), sd.site()["financing"]
    data = [(v, (fin.get("initiatives") or {}).get(v["id"])) for v in votes]
    top = max([max(f["pro"]["totalRevenue"], f["contra"]["totalRevenue"]) for _, f in data if f] or [1]) or 1
    def line(label, cls, amount, width_of):
        return (f'<div style="display:grid;grid-template-columns:150px minmax(0, 1fr) 190px;gap:14px;align-items:center;font-size:19px;font-weight:600">'
                f'<span class="{cls}">{e(label)}</span><span class="trk"><span class="{"yes" if cls == "cy" else "no"}" style="width:{amount / width_of * 100:.1f}%"></span></span>'
                f'<span class="{cls}" style="text-align:right;font-weight:600">{e(sd.chf(amount, lang))}</span></div>')
    rows = ""
    for n, (v, f) in enumerate(data, 1):
        rows += f'<div class="rule" style="display:flex;flex-direction:column;gap:10px;padding:16px 0"><div class="vt" style="font-size:22px">{n} · {e(sd.vote_title(v, lang)[0])}</div>'
        rows += (line(s["for"], "cy", f["pro"]["totalRevenue"], top) + line(s["against"], "cn", f["contra"]["totalRevenue"], top)) if f \
            else f'<div class="p muted">{e(s["runup"]["noMoney"])}</div>'
        rows += "</div>"
    bodies = [f'<div class="kicker">{e(s["runup"]["moneyKicker"])}</div><h1 class="h" style="font-size:54px">{e(s["runup"]["moneyTitle"])}</h1>'
              f'<div>{rows}</div><div class="muted" style="margin-top:auto;font-size:18px">{e(s["runup"]["sameScale"])}</div>']
    asof = sd.date_num(dt.date.fromisoformat(fin["_meta"]["fetchedAt"][:10]))
    for n, (v, f) in enumerate(data, 1):
        if not f:
            continue
        m = max(f["pro"]["totalRevenue"], f["contra"]["totalRevenue"]) or 1
        def big(side, cls, label):
            c = f[side]["actorCount"]
            act = s["runup"]["actor"] if c == 1 else fill(s["runup"]["actors"], n=c)
            return (f'<div class="rule" style="display:flex;flex-direction:column;gap:14px;padding-top:22px">'
                    f'<div style="display:flex;justify-content:space-between"><div class="lbl {cls}">{e(label)}</div><div class="muted" style="font-size:20px;font-weight:600">{e(act)}</div></div>'
                    f'<div class="big {cls}" style="font-size:70px">{e(sd.chf(f[side]["totalRevenue"], lang))}</div>'
                    f'<div class="trk" style="height:56px"><span class="{"yes" if cls == "cy" else "no"}" style="width:{f[side]["totalRevenue"] / m * 100:.1f}%"></span></div></div>')
        bodies.append(f'<div class="kicker">{e(fill(s["runup"]["moneyKickerOne"], n=n))}</div>{title_html(v, lang, 42)}'
                      f'{big("pro", "cy", s["for"])}{big("contra", "cn", s["against"])}'
                      f'<p class="p" style="margin-top:auto;font-size:20px">{e(fill(s["runup"]["moneyNote"], date=asof))}</p>')
    route = "financing/votes"
    src = src_line(lang, "sfao", fetched=sd.fetched(fin["_meta"]["fetchedAt"], lang))
    return Post("runup_money", f"runup:{ballot}:money", "runup", lang, route,
                caption(lang, "runupMoney", f"{s['domain']}/#/{route}", date=sd.date_long(ballot, lang)),
                paginate(lang, "runup", bodies, src))


# ---------------------------------------------------------------- 3 Initiatives & referendums
def spotlight(v, on_date, lang):
    """3.1: every collecting initiative or referendum, when 100 days of its period remain."""
    s, deadline = S(lang), dt.date.fromisoformat(v["deadline"])
    is_ref = v.get("type") != "initiative"
    # Initiatives: 18 months to collect; optional referendums: 100 days.
    start = deadline - dt.timedelta(days=100) if is_ref else _months_before(deadline, 18)
    days_left = (deadline - on_date).days
    span = (deadline - start).days or 1
    done = max(0, min(100, (on_date - start).days / span * 100))
    p1 = (f'<div style="display:flex;align-items:center;gap:26px"><div class="big" style="font-size:160px;color:#7A1C2A">{days_left}</div>'
          f'<div class="kicker" style="font-size:28px;line-height:1.3">{e(s["initiatives"]["daysLeft"])}</div></div>'
          f'<div style="display:flex;gap:10px;flex-wrap:wrap"><span class="chip">{e(s["initiatives"]["spotlight"])}</span><span class="chip">{e(type_label(v, lang))}</span></div>'
          f'{title_html(v, lang, 46)}')
    sigs = 50000 if is_ref else 100000
    p2 = (f'<div class="kicker">{e(sd.short_name(v, lang)[0])} · {e(s["initiatives"]["spotlight"])}</div>'
          f'<div style="display:flex;flex-direction:column;gap:14px"><div class="lbl">{e(s["initiatives"]["period"]) if not is_ref else ""}</div>'
          f'<div style="position:relative;height:48px;background:#F6F4F0;border-radius:3px"><div style="height:48px;width:{done:.1f}%;background:#7A1C2A;border-radius:3px 0 0 3px"></div>'
          f'<div style="position:absolute;left:{done:.1f}%;top:-10px;bottom:-10px;width:4px;background:#161616"></div></div>'
          f'<div style="display:flex;justify-content:space-between;font-size:22px;font-weight:600"><span>{sd.date_num(start)}</span>'
          f'<span style="color:#7A1C2A">{e(fill(s["initiatives"]["today"], n=days_left))}</span><span>{sd.date_num(deadline)}</span></div></div>'
          f'<div class="rule" style="display:flex;flex-direction:column;gap:8px;padding-top:22px"><div class="lbl">{e(s["initiatives"]["required"])}</div>'
          f'<div style="font-size:32px;font-weight:600">{e(fill(s["initiatives"]["signatures"], n=sd.num(sigs, lang)))}</div></div>'
          f'<p class="p" style="margin-top:auto;font-size:21px">{e(s["initiatives"]["fairness"])}</p>')
    route = f"initiative/{v['id']}"
    src = src_line(lang, "lindas", asof=sd.date_num(on_date))
    return Post("spotlight", f"spotlight:{v['id']}", "initiatives", lang, route,
                caption(lang, "spotlight", f"{s['domain']}/#/{route}", title=sd.short_name(v, lang)[0]),
                paginate(lang, "initiatives", [p1, p2], src))


def _months_before(d, months):
    y, m = divmod(d.month - 1 - months, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return dt.date(year, month, day)


def pipeline(on_date, lang):
    """3.4: how many proposals are collecting, handed in, or scheduled (first Friday of the month)."""
    s = S(lang)
    votes = sd.site()["votes"].values()
    counts = [sum(1 for v in votes if v["status"] == st) for st in ("collecting", "pending", "upcoming")]
    rows = ""
    for n, (name, desc) in zip(counts, s["initiatives"]["stages"]):
        dots = "".join('<i style="display:block;width:22px;height:22px;border-radius:50%;background:#7A1C2A"></i>' for _ in range(n))
        rows += (f'<div class="rule" style="display:flex;align-items:center;gap:28px;padding:24px 0"><div class="big" style="font-size:110px;width:150px;color:#7A1C2A">{n}</div>'
                 f'<div style="flex:1"><div style="font-size:31px;font-weight:600">{e(name)}</div><div class="p muted" style="margin-top:6px">{e(desc)}</div>'
                 f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:14px" aria-hidden="true">{dots}</div></div></div>')
    body = (f'<div class="kicker">{e(fill(s["initiatives"]["pipelineKicker"], month=s["months"][on_date.month - 1]))}</div>'
            f'<h1 class="h" style="font-size:60px">{e(s["initiatives"]["pipelineTitle"])}</h1><div>{rows}</div>')
    route = "ballots/collecting"
    src = src_line(lang, "lindas", asof=sd.date_num(on_date))
    return Post("pipeline", f"pipeline:{on_date:%Y-%m}", "initiatives", lang, route,
                caption(lang, "pipeline", f"{s['domain']}/#/{route}"), [frame(lang, "initiatives", body, src)])


# ---------------------------------------------------------------- 4 Parliament
def session_name(sess, lang):
    return f'{S(lang)["parliament"]["seasons"].get(sess["season"], "")} {sess["year"]}'


def bill_title(v, lang):
    """(title, badge) of a final vote. English: DeepL (badged)."""
    if lang == "en":
        t = sd.mt_title(v["id"])
        return (t, "mt") if t else (v["title"]["de"], None)
    return v["title"].get(lang) or v["title"]["de"], None


def session_summary(sess, lang, per_page=6):
    """4.2: every final vote of a session, in the official order."""
    s, data = S(lang), sd.session(sess["id"])
    votes = data["votes"]
    P = s["parliament"]
    cover = (f'<div class="kicker">{e(session_name(sess, lang))} · {sd.date_num(dt.date.fromisoformat(sess["start"]))} – {sd.date_num(dt.date.fromisoformat(sess["end"]))}</div>'
             f'<div style="display:flex;align-items:flex-end;gap:30px"><div class="big" style="font-size:240px">{len(votes)}</div>'
             f'<h1 class="h" style="font-size:60px;padding-bottom:28px">{e(P["finalVotes"])}</h1></div>'
             f'<div class="rule" style="padding-top:22px"><p class="p" style="font-size:25px">{e(P["summaryText"])}</p></div>'
             f'<p class="p muted" style="margin-top:auto;font-size:21px">{e(fill(P["summaryNext"], n=len(votes)))}</p>')
    bodies, any_mt = [cover], False
    for i in range(0, len(votes), per_page):
        chunk = votes[i:i + per_page]
        rows = ""
        for v in chunk:
            t, b = bill_title(v, lang)
            any_mt = any_mt or b == "mt"
            ta = v["tally"]
            rows += (f'<div style="display:grid;grid-template-columns:90px minmax(0, 1fr) 160px;gap:16px;align-items:start;padding:16px 0;border-bottom:1px solid #DCDAD3">'
                     f'<span class="muted" style="font-size:17px;font-weight:600;padding-top:3px">{e(v["business"])}</span>'
                     f'<span style="font-size:22px;font-weight:500;line-height:1.3">{e(t)}{badge(b, lang)}</span>'
                     f'<span class="ct" style="font-size:21px">{ta["yes"]} · {ta["no"]} · {ta["abstain"]}</span></div>')
        bodies.append(f'<div class="kicker">{e(fill(P["finalRange"], a=i + 1, b=i + len(chunk), n=len(votes)))}</div>'
                      f'<div style="display:grid;grid-template-columns:90px minmax(0, 1fr) 160px;gap:16px;font-size:15px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:#5F5E5A;border-bottom:2px solid #161616;padding-bottom:8px">'
                      f'<span>{e(P["colItem"])}</span><span>{e(P["colBill"])}</span><span style="text-align:right">{e(P["colCounts"])}</span></div><div>{rows}</div>')
    route = f"session/{sess['id']}"
    src = src_line(lang, "parliament", fetched=sd.fetched(data["_meta"]["fetchedAt"], lang), extra=s["mtNote"] if any_mt else "")
    return Post("session_summary", f"session:{sess['id']}", "parliament", lang, route,
                caption(lang, "sessionSummary", f"{s['domain']}/#/{route}", session=session_name(sess, lang), n=len(votes)),
                paginate(lang, "parliament", bodies, src))


def daily_votes(day, lang, per_page=8):
    """4.1: every National Council vote of a sitting day, complete and in the official order (POL-16)."""
    s, P = S(lang), S(lang)["parliament"]
    nc = day["councils"]["N"]
    votes = nc["votes"]
    d = dt.date.fromisoformat(day["date"])
    items = len({(v["business"], v.get("bill")) for v in votes})
    sittings = " · ".join(m["begin"] for m in nc.get("meetings", []))
    cover = (f'<div class="kicker">{e(session_name(day["session"], lang))} · {e(sd.weekday_date(d, lang))}</div>'
             f'<div style="display:flex;align-items:flex-end;gap:30px"><div class="big" style="font-size:240px">{len(votes)}</div>'
             f'<h1 class="h" style="font-size:54px;padding-bottom:28px">{e(P["votesInNc"])}</h1></div>'
             f'<div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:24px">'
             f'<div class="rule" style="padding-top:20px"><div class="big" style="font-size:72px">{items}</div><div style="font-size:24px;font-weight:600">{e(P["items"])}</div></div>'
             f'<div class="rule" style="padding-top:20px"><div class="big" style="font-size:72px">{len(nc.get("meetings", []))}</div><div style="font-size:24px;font-weight:600">{e(P["sittings"])} · {e(sittings)}</div></div></div>'
             f'<p class="p" style="margin-top:auto;font-size:22px">{e(fill(P["dailyNext"], n=len(votes)))}</p>')
    bodies = [cover]
    for i in range(0, len(votes), per_page):
        chunk, groups, rows = votes[i:i + per_page], [], ""
        for v in chunk:
            k = (v["business"], v.get("bill"))
            if not groups or groups[-1][0] != k:
                groups.append((k, v, []))
            groups[-1][2].append(v)
        for (bus, bill), first, vs in groups:
            title = (first.get("billTitle") or {}).get(lang) or (first.get("billTitle") or {}).get("de") or ""
            rows += (f'<div style="display:flex;flex-direction:column;gap:4px;padding-bottom:12px;border-bottom:1px solid #DCDAD3">'
                     f'<div class="muted" style="font-size:16px;font-weight:600">{e(bus)}{" · " + str(bill) if bill else ""}</div>'
                     f'<div style="font-size:21px;font-weight:600;line-height:1.3">{e(title)}</div>')
            for v in vs:
                t = v["tally"]
                tot = (t["yes"] + t["no"] + t["abstain"]) or 1
                rows += (f'<div class="vr"><span class="muted" style="font-weight:600">{e(v["time"])}</span><span>{e(v.get("subject", ""))}</span>'
                         f'<span class="stk"><span class="yes" style="width:{t["yes"] / tot * 100:.2f}%"></span><span class="no" style="width:{t["no"] / tot * 100:.2f}%"></span>'
                         f'<span class="abs" style="width:{t["abstain"] / tot * 100:.2f}%"></span></span><span class="ct">{t["yes"]} · {t["no"]} · {t["abstain"]}</span></div>')
            rows += "</div>"
        bodies.append(f'<div class="kicker">{e(fill(P["votesRange"], date=sd.date_long(d, lang), a=i + 1, b=i + len(chunk), n=len(votes)))}</div>'
                      f'<div class="vr lbl" style="border-bottom:2px solid #161616"><span>{e(P["colTime"])}</span><span>{e(P["colSubject"])}</span><span></span><span style="text-align:right">{e(P["colCounts"])}</span></div>'
                      f'{rows}<div class="muted" style="margin-top:auto;font-size:17px">{e(P["subjectNote"])}</div>')
    route = f"ticker/{day['date']}"
    src = src_line(lang, "parliament", fetched=sd.fetched(day["_meta"]["fetchedAt"], lang))
    return Post("daily_votes", f"daily:{day['date']}", "parliament", lang, route,
                caption(lang, "dailyVotes", f"{s['domain']}/#/{route}", date=sd.date_long(d, lang), n=len(votes)),
                paginate(lang, "parliament", bodies, src))


def seats_changed(changes, lang):
    """4.3: only when National Council seats change. changes = {party: (before, after)}."""
    s, P = S(lang), S(lang)["parliament"]
    parties = sd.site()["parties"]["parties"]
    order = ["GPS", "SP", "GLP", "EVP", "MITTE", "FDP", "MCG", "LEGA", "EDU", "SVP"]
    order = [k for k in order if k in parties] + [k for k in parties if k not in order]
    dots = _hemicycle([(k, parties[k].get("ncSeats", 0)) for k in order])
    lines = " · ".join(f"{sd.party_short(k, lang)} {b} → {a}" for k, (b, a) in changes.items())
    legend = "".join(f'<div style="display:flex;align-items:center;gap:10px;font-size:22px;font-weight:600"><span class="dot" style="background:{e(sd.party_color(k))};width:18px;height:18px"></span>{e(sd.party_short(k, lang))} {parties[k].get("ncSeats", 0)}</div>' for k in order)
    body = (f'<div class="kicker">{e(P["seatsKicker"])}</div><h1 class="h" style="font-size:58px">{e(P["seatsTitle"])}</h1>'
            f'<div style="font-size:28px;font-weight:600">{e(lines)}</div>'
            f'<div style="position:relative;width:936px;height:470px">{dots}<div style="position:absolute;left:0;right:0;top:380px;text-align:center" class="big"><span style="font-size:72px">200</span></div></div>'
            f'<div style="display:grid;grid-template-columns:repeat(5, minmax(0, 1fr));gap:12px 18px">{legend}</div>')
    route = "assembly/nc"
    src = src_line(lang, "fso2023", asof=sd.date_num(dt.date.today()))
    return Post("seats", f"seats:{dt.date.today()}", "parliament", lang, route,
                caption(lang, "seats", f"{s['domain']}/#/{route}"), [frame(lang, "parliament", body, src)])


def _hemicycle(counts, rows_n=8, r0=190, r1=450, cx=468, cy=452):
    import math
    total = sum(n for _, n in counts)
    radii = [r0 + i * (r1 - r0) / (rows_n - 1) for i in range(rows_n)]
    per = [round(total * r / sum(radii)) for r in radii]
    per[-1] += total - sum(per)
    seats = sorted(((math.pi * j / max(1, n - 1), cx - r * math.cos(math.pi * j / max(1, n - 1)), cy - r * math.sin(math.pi * j / max(1, n - 1)))
                    for r, n in zip(radii, per) for j in range(n)))
    colours = [sd.party_color(k) for k, n in counts for _ in range(n)]
    return "".join(f'<span style="position:absolute;width:24px;height:24px;border-radius:50%;left:{x - 12:.1f}px;top:{y - 12:.1f}px;background:{e(c)}"></span>'
                   for (_, x, y), c in zip(seats, colours))


# ---------------------------------------------------------------- 5 Explained (evergreen)
def final_vote(sess, v, n, total, lang):
    """E1: one final vote of the last session, in turn (the official order)."""
    s, X = S(lang), S(lang)["explained"]
    t, b = bill_title(v, lang)
    ta = v["tally"]
    groups = ""
    for key in sd.parties_by_seats():
        g = (v.get("byParty") or {}).get(key)
        if not g:
            continue
        tot = (g["yes"] + g["no"] + g["abstain"]) or 1
        groups += (f'<div style="display:grid;grid-template-columns:130px minmax(0, 1fr) 150px;gap:16px;align-items:center;font-size:21px">'
                   f'<span style="font-weight:600">{e(sd.party_short(key, lang))}</span><span class="stk" style="height:22px"><span class="yes" style="width:{g["yes"] / tot * 100:.2f}%"></span>'
                   f'<span class="no" style="width:{g["no"] / tot * 100:.2f}%"></span><span class="abs" style="width:{g["abstain"] / tot * 100:.2f}%"></span></span>'
                   f'<span class="ct">{g["yes"]} · {g["no"]} · {g["abstain"]}</span></div>')
    body = (f'<div style="display:flex;justify-content:space-between;align-items:baseline"><div class="kicker">{e(fill(X["fvKicker"], session=session_name(sess, lang), n=n, total=total))}</div>'
            f'<div class="muted" style="font-size:20px;font-weight:600">{e(v["business"])}</div></div>'
            f'<h1 class="h" style="font-size:46px;line-height:1.12">{e(t)}{badge(b, lang)}</h1>'
            f'<div class="rule" style="display:flex;gap:56px;align-items:flex-end;padding-top:18px">'
            f'<div><div class="big cy" style="font-size:96px">{ta["yes"]}</div><div class="lbl cy">{e(s["yes"])}</div></div>'
            f'<div><div class="big cn" style="font-size:96px">{ta["no"]}</div><div class="lbl cn">{e(s["no"])}</div></div>'
            f'<div><div class="big" style="font-size:96px;color:#7D7A72">{ta["abstain"]}</div><div class="lbl">{e(s["abstain"])}</div></div></div>'
            f'<div style="display:flex;flex-direction:column;gap:10px"><div class="lbl">{e(X["byGroup"])}</div>{groups}</div>')
    route = f"session/{sess['id']}"
    src = src_line(lang, "parliament", fetched=sd.fetched(sd.session(sess["id"])["_meta"]["fetchedAt"], lang), extra=s["mtNote"] if b == "mt" else "")
    return Post("final_vote", f"finalvote:{v['id']}", "explained", lang, route,
                caption(lang, "finalVote", f"{s['domain']}/#/{route}", title=t), [frame(lang, "explained", body, src)])


def how_double_majority(lang):
    """E2 'How it works': the double majority — the editor's glossary text, then a diagram."""
    s, X = S(lang), S(lang)["explained"]
    term = next(t for t in sd.site()["glossary"]["terms"] if t["id"] == "doubleMajority")
    dm = X["dm"]
    p1 = (f'<div class="kicker" style="margin-top:60px">{e(X["howKicker"])}</div><h1 class="h" style="font-size:96px">{e(dm["title"])}</h1>'
          f'<div style="font-size:40px;line-height:1.4;font-weight:500;border-left:10px solid #161616;padding-left:34px">{e(sd.gloss_text(term, lang))}</div>')
    tiles = "".join('<i style="display:block;height:48px;width:30px;border-radius:2px;background:#161616"></i>' for _ in range(20)) + \
        "".join('<i style="display:block;height:48px;width:15px;border-radius:2px;background:#7D7A72"></i>' for _ in range(6))
    p2 = (f'<div class="kicker">{e(dm["title"])}</div>'
          f'<div style="display:flex;flex-direction:column;gap:16px;padding:26px 0;border-top:2px solid #161616"><div style="font-size:36px;font-weight:600">{e(dm["people"])}</div>'
          f'<div style="position:relative;height:48px;background:#F6F4F0;border-radius:2px"><div style="height:48px;width:54%;background:#161616;border-radius:2px"></div>'
          f'<div style="position:absolute;left:50%;top:-8px;bottom:-8px;width:3px;background:#7A1C2A"></div></div><div class="p muted" style="font-size:25px">{e(dm["peopleDesc"])}</div></div>'
          f'<div class="big" style="font-size:60px;text-align:center;color:#7A1C2A" aria-hidden="true">+</div>'
          f'<div style="display:flex;flex-direction:column;gap:16px;padding:26px 0;border-top:2px solid #161616"><div style="font-size:36px;font-weight:600">{e(dm["cantons"])}</div>'
          f'<div style="display:flex;gap:6px;align-items:flex-end" role="img" aria-label="20 + 6">{tiles}</div><div class="p muted" style="font-size:25px">{e(dm["cantonsDesc"])}</div></div>'
          f'<p class="p" style="margin-top:auto;font-size:23px">{e(dm["applies"])}</p>')
    route = "glossary"
    pages = [frame(lang, "explained", p1, s["src"]["glossary"], 1, 2), frame(lang, "explained", p2, src_line(lang, "constitution"), 2, 2)]
    return Post("how", "how:doubleMajority", "explained", lang, route,
                caption(lang, "how", f"{s['domain']}/#/{route}", title=dm["title"]), pages)


def party(key, lang):
    """E3: a party in figures — seats only, no positions."""
    s, X = S(lang), S(lang)["explained"]
    p = sd.site()["parties"]["parties"][key]
    nc, cs = p.get("ncSeats", 0), p.get("csSeats", 0)
    cells = "".join(f'<i style="display:block;height:28px;border-radius:2px;background:{e(p["color"]) if i < nc else "#E7E4DD"}"></i>' for i in range(200))
    body = (f'<div style="display:flex;align-items:center;gap:16px"><span class="dot" style="width:28px;height:28px;background:{e(p["color"])}"></span>'
            f'<div class="kicker" style="color:#161616">{e(fill(X["partyKicker"], abbr=sd.party_short(key, lang)))}</div></div>'
            f'<h1 class="h" style="font-size:76px">{e(p["name"][lang])}</h1>'
            f'<div class="rule" style="display:flex;flex-direction:column;gap:14px;padding-top:22px"><div class="lbl">{e(X["nc"])}</div>'
            f'<div style="display:flex;align-items:baseline;gap:16px"><span class="big" style="font-size:124px">{nc}</span><span class="muted" style="font-size:28px;font-weight:600">{e(fill(X["ofSeats"], n=200))}</span></div>'
            f'<div style="display:grid;grid-template-columns:repeat(20, minmax(0, 1fr));gap:5px">{cells}</div></div>'
            f'<div class="rule" style="display:flex;flex-direction:column;gap:10px;padding-top:22px"><div class="lbl">{e(X["cs"])}</div>'
            f'<div style="display:flex;align-items:baseline;gap:12px"><span class="big" style="font-size:90px">{cs}</span><span class="muted" style="font-size:28px;font-weight:600">{e(fill(X["of"], n=46))}</span></div></div>'
            f'<p class="p muted" style="margin-top:auto;font-size:21px">{e(X["partyNote"])}</p>')
    route = f"party/{key}"
    return Post("party", f"party:{key}", "explained", lang, route,
                caption(lang, "party", f"{s['domain']}/#/{route}", name=p["name"][lang]),
                [frame(lang, "explained", body, src_line(lang, "fso2023", "parliament"))])


def glossary(term, lang):
    """E4: one glossary term, in the editor's own words."""
    s, X = S(lang), S(lang)["explained"]
    terms = {t["id"]: t for t in sd.site()["glossary"]["terms"]}
    related = [terms[r]["headword"][lang] for r in term.get("related", []) if r in terms and sd.gloss_text(terms[r], lang)][:2]
    rel = "".join(f'<span style="padding:8px 16px;border:2px solid #DCDAD3;border-radius:4px;font-size:24px;font-weight:600">{e(r)}</span>' for r in related)
    head = term["headword"][lang]
    body = (f'<div class="kicker" style="margin-top:60px">{e(fill(X["glossaryKicker"], category=X["categories"].get(term.get("category"), "")))}</div>'
            f'<h1 class="h" style="font-size:{104 if len(head) < 18 else 76}px">{e(head[0].upper() + head[1:])}</h1>'
            f'<div style="font-size:40px;line-height:1.4;font-weight:500;border-left:10px solid #161616;padding-left:34px">{e(sd.gloss_text(term, lang))}</div>'
            + (f'<div style="display:flex;gap:14px;align-items:center;margin-top:auto"><b class="lbl" style="color:#161616">{e(X["seeAlso"])}</b>{rel}</div>' if rel else ""))
    route = "glossary"
    return Post("glossary", f"glossary:{term['id']}", "explained", lang, route,
                caption(lang, "glossary", f"{s['domain']}/#/{route}", term=head),
                [frame(lang, "explained", body, s["src"]["glossary"])])


def canton(code, n, lang):
    """E5: a canton profile — map and facts, then the 2023 National Council result."""
    s, X = S(lang), S(lang)["explained"]
    c = sd.site()["cantons"]["cantons"][code]
    paths = sd.map_paths()
    svg = "".join(f'<path d="{e(d)}" fill="{"#7A1C2A" if k == code else "#E7E4DD"}" stroke="#fff" stroke-width="2.5" stroke-linejoin="round"></path>'
                  for k, d in sorted(paths.items(), key=lambda kv: kv[0] == code))
    facts = [(X["capital"], c["capital"][lang]), (X["joined"], c["joined"]), (X["language"], c["language"][lang]),
             (X["population"], sd.num(c["pop"], lang)), (X["area"], f'{sd.num(c["area"], lang)} km²'), (X["ncSeats"], c["seats"])]
    grid = "".join(f'<div><div class="lbl">{e(a)}</div><div style="font-size:32px;font-weight:600">{e(b)}</div></div>' for a, b in facts)
    p1 = (f'<div class="kicker">{e(fill(X["cantonKicker"], n=n))}</div><h1 class="h" style="font-size:104px">{e(c["name"][lang])}</h1>'
          f'<svg viewBox="140 60 660 410" width="936" height="480" role="img" aria-label="{e(c["name"][lang])}">{svg}</svg>'
          f'<div style="display:grid;grid-template-columns:repeat(3, minmax(0, 1fr));gap:18px 24px;border-top:2px solid #161616;padding-top:18px">{grid}</div>')
    nc = sd.site()["cantonData"]["cantons"][code]["nc"]
    known = [p for p in nc["parties"] if p.get("key") and p.get("strength") is not None]
    other = round(sum(p.get("strength") or 0 for p in nc["parties"] if not p.get("key")), 1)
    rows = known + ([{"key": None, "strength": other, "seats": 0}] if other else [])
    top = max(p["strength"] for p in rows) or 1
    lines = "".join(
        f'<div style="display:grid;grid-template-columns:180px minmax(0, 1fr) 170px;gap:16px;align-items:center;font-size:22px;padding:9px 0;border-bottom:1px solid #DCDAD3">'
        f'<span style="font-weight:600">{e(sd.party_short(p["key"], lang) if p["key"] else X["others"])}</span>'
        f'<span class="trk" style="height:26px"><span style="width:{p["strength"] / top * 100:.1f}%;background:{e(sd.party_color(p["key"]) if p["key"] else "#B9B5AC")}"></span></span>'
        f'<span class="ct">{e(sd.pct(p["strength"], lang))} ({p["seats"]})</span></div>' for p in rows)
    p2 = (f'<div class="kicker">{e(fill(X["cantonKicker"], n=n))} · {e(c["name"][lang])}</div><h1 class="h" style="font-size:58px">{e(X["cantonElection"])}</h1>'
          f'<div class="lbl" style="display:grid;grid-template-columns:180px minmax(0, 1fr) 170px;gap:16px;border-bottom:2px solid #161616;padding-bottom:8px">'
          f'<span>{e(X["partyCol"])}</span><span>{e(X["shareCol"])}</span><span style="text-align:right">{e(X["seatsCol"])}</span></div><div>{lines}</div>'
          f'<div class="muted" style="margin-top:auto;font-size:20px">{e(fill(X["seatsNote"], n=nc["totalSeats"]))}</div>')
    route = f"canton/{code}"
    return Post("canton", f"canton:{code}", "explained", lang, route,
                caption(lang, "canton", f"{s['domain']}/#/{route}", name=c["name"][lang]),
                [frame(lang, "explained", p1, src_line(lang, "cantonData"), 1, 2), frame(lang, "explained", p2, src_line(lang, "fso2023"), 2, 2)])


def history(day, votes, years, lang):
    """E6: what Switzerland voted on, on this date — every proposal of that day."""
    s, X = S(lang), S(lang)["explained"]
    kicker = fill(X["historyKicker1"] if years == 1 else X["historyKicker"], n=years, date=sd.date_long(day, lang))
    title = X["historyTitle1"] if len(votes) == 1 else fill(X["historyTitle"], n=len(votes))
    rows = ""
    for v in votes[:4]:
        label, yes = sd.outcome(v, lang)
        rows += (f'<div class="rule" style="display:flex;flex-direction:column;gap:12px;padding-top:22px">{title_html(v, lang, 32 if len(votes) < 3 else 26)}'
                 f'<div style="font-size:26px;font-weight:600">{e(label)}</div>{bar(yes, 46)}{pct_row(yes, lang, 23)}</div>')
    body = (f'<div class="big" style="font-size:190px;color:#E7E4DD;line-height:.8" aria-hidden="true">{day.year}</div>'
            f'<div class="kicker">{e(kicker)}</div><h1 class="h" style="font-size:58px">{e(title)}</h1>{rows}')
    route = "ballots/decided"
    return Post("history", f"history:{day}", "explained", lang, route,
                caption(lang, "history", f"{s['domain']}/#/{route}", date=sd.date_long(day, lang)),
                [frame(lang, "explained", body, src_line(lang, "voteinfo"))])


# ---------------------------------------------------------------- Correction
def correction(info, lang):
    """A correction of an earlier post. info = {'date': 'YYYY-MM-DD', 'wrong': {lang: …}, 'right': {lang: …}, 'source': …}."""
    s, C = S(lang), S(lang)["correction"]
    d = dt.date.fromisoformat(info["date"])
    body = (f'<div class="kicker">{e(fill(C["kicker"], date=sd.date_long(d, lang)))}</div><h1 class="h" style="font-size:72px">{e(C["title"])}</h1>'
            f'<div style="display:flex;flex-direction:column;gap:10px"><div class="lbl">{e(C["was"])}</div>'
            f'<div style="font-size:36px;line-height:1.3;color:#5F5E5A;text-decoration:line-through;text-decoration-thickness:3px">{e(info["wrong"][lang])}</div></div>'
            f'<div style="display:flex;flex-direction:column;gap:10px;border-left:10px solid #161616;padding-left:28px"><div class="lbl" style="color:#161616">{e(C["is"])}</div>'
            f'<div style="font-size:42px;line-height:1.25;font-weight:600">{e(info["right"][lang])}</div></div>'
            f'<p class="p" style="margin-top:auto">{e(C["note"])}</p>')
    route = ""
    return Post("correction", f"correction:{info['date']}", "correction", lang, route,
                caption(lang, "correction", s["domain"], date=sd.date_long(d, lang)),
                [frame(lang, "correction", body, fill(C["src"], src=info.get("source", "")))])
