/* Session ticker (#/ticker/<date>): what the Federal Assembly has on the day's
   programme, who has spoken on each item, how the National Council voted and
   what the councils decided — from data/sessions/days/, which the session
   ticker job fetches from parlament.ch every 20 minutes while Parliament sits.

   Rules this page is held to (GUARDRAILS.md; check.py enforces them on this file):
   * POL-14 — never called live: the official data runs 1–2 hours behind the
     chamber, and the page always shows that, the download time (SRC-12), the
     credit and "not an official publication" ('ticker.delay', 'ticker.fetched',
     'ticker.credit', 'ticker.notOfficial').
   * POL-15 — no outcome worked out from a tally (the spending brake needs 101
     votes; a tie is decided by the president). Tallies and the official meaning
     of Yes and No are shown; a decision only from the councils' own records.
   * POL-16 — every item, speaker, vote and decision, in the order the source
     gives: no selection, highlights or re-sorting.
   * PRIV-13 — tallies by parliamentary group only; speakers by name, role,
     group, canton and time. No speech text (SRC-13): the data has none.
   Everything from the data is escaped (SEC-01). */

let C = null;
const REFRESH_MS = 5 * 60 * 1000;
const YES = '#534AB7', NO = '#0F6E56';
const COUNCIL_KEYS = { N: 'parl.nc', S: 'parl.cs', V: 'session.ufa' };

export function configureTicker(ctx) { C = ctx; }

function t(k) { return C.t(k); }
function tf(k, vars) {
  let s = C.t(k);
  Object.keys(vars).forEach(a => { s = s.split('{' + a + '}').join(String(vars[a])); });
  return s;
}
function escapeAttr(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function plural(base, n) { return tf(base + (n === 1 ? '.one' : '.many'), { n }); }

/* ---- data ---- */
let indexCache = null, indexAt = 0;
const dayCache = {};

// The ticker files change during a sitting day, so they are revalidated with
// the server rather than taken from the browser cache (same origin only).
export function loadTickerIndex(force) {
  if (!force && indexCache && Date.now() - indexAt < 60000) return indexCache;
  indexAt = Date.now();
  indexCache = fetch('data/sessions/days/index.json', { cache: 'no-cache' })
    .then(r => r.ok ? r.json() : null)
    .catch(() => null);
  return indexCache;
}
function loadDay(date, force) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date || '')) return Promise.resolve(null);
  if (!force && dayCache[date]) return dayCache[date];
  dayCache[date] = fetch(`data/sessions/days/${date}.json`, { cache: 'no-cache' })
    .then(r => r.ok ? r.json() : null)
    .catch(() => null);
  return dayCache[date];
}

// Today's date in Switzerland (or, on a local preview only, ?today=YYYY-MM-DD).
export function tickerToday() {
  const dev = C.devToday && C.devToday();
  if (dev) return `${dev.getFullYear()}-${String(dev.getMonth() + 1).padStart(2, '0')}-${String(dev.getDate()).padStart(2, '0')}`;
  const p = {};
  new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Zurich', year: 'numeric', month: '2-digit', day: '2-digit' })
    .formatToParts(new Date()).forEach(x => { p[x.type] = x.value; });
  return `${p.year}-${p.month}-${p.day}`;
}

/* ---- labels ---- */
function party(k) { return (C.state.data.parties || {})[k] || null; }
function groupLabel(k) { const p = party(k); return p ? (p.abbr || k) : k; }
function titleOf(title) {
  // Official titles exist in DE/FR/IT only; other languages show one of those.
  const tt = title || {};
  const lang = tt[C.state.lang] ? C.state.lang : (tt.de ? 'de' : tt.fr ? 'fr' : 'it');
  return { text: tt[lang] || '', lang };
}
function titleHTML(title) {
  const x = titleOf(title);
  return `<span lang="${escapeAttr(x.lang)}">${escapeAttr(x.text)}</span>` +
    (x.lang !== C.state.lang ? ` <span class="tk-lang">${escapeAttr(x.lang.toUpperCase())}</span>` : '');
}
function businessUrl(id) {
  const lp = ({ en: 'en', de: 'de', fr: 'fr', it: 'it' })[C.state.lang] || 'de';
  return 'https://www.parlament.ch/' + lp + '/ratsbetrieb/suche-curia-vista/geschaeft?AffairId=' + encodeURIComponent(id);
}
function dayLabel(date) { return C.formatLongDate(new Date(date + 'T00:00:00')); }

/* ---- the page ---- */
let shownDate = null, timer = null;

export function renderTickerPage(date) {
  shownDate = date || null;
  const content = document.getElementById('ticker-content');
  if (!content) return;
  document.getElementById('ticker-title').textContent = t('ticker.title');
  loadTickerIndex().then(index => {
    const days = (index && index.days) || [];
    let want = shownDate;
    if (!want) {
      // No date in the address: today's file, else the most recent day on file.
      const today = tickerToday();
      days.forEach(d => { if (d.date <= today) want = d.date; });
    }
    return loadDay(want).then(day => draw(content, index, days, want, day));
  });
  if (!timer) {
    timer = setInterval(() => {
      if (document.visibilityState !== 'visible' || !document.getElementById('ticker-page')?.classList.contains('active')) return;
      refresh();
    }, REFRESH_MS);
  }
}

function refresh() {
  const content = document.getElementById('ticker-content');
  const before = content && content.dataset.fetched;
  loadTickerIndex(true).then(index => {
    const days = (index && index.days) || [];
    const want = content.dataset.date;
    loadDay(want, true).then(day => {
      if (!day || day._meta.fetchedAt === before) return;
      // Keep the items a reader has opened.
      const open = new Set();
      content.querySelectorAll('details[open][data-k]').forEach(d => open.add(d.dataset.k));
      draw(content, index, days, want, day);
      content.querySelectorAll('details[data-k]').forEach(d => { if (open.has(d.dataset.k)) d.open = true; });
    });
  });
}

function draw(content, index, days, date, day) {
  content.dataset.date = date || '';
  content.dataset.fetched = (day && day._meta && day._meta.fetchedAt) || '';
  const sub = document.getElementById('ticker-sub');
  sub.textContent = day ? C.sessionName(day.session) + ' · ' + dayLabel(day.date) : t('ticker.title');

  let html = `<p class="tk-note">${escapeAttr(t('ticker.delay'))}</p>`;
  if (day) html += `<p class="tk-fetched">${escapeAttr(tf('ticker.fetched', { fetched: C.formatFetched(day._meta.fetchedAt) }))}</p>`;

  // Sitting days of the same session, in date order.
  const same = [];
  days.forEach(d => { if (day && d.session && d.session.id === day.session.id) same.push(d); });
  if (same.length > 1) {
    html += `<div class="tk-days" role="navigation" aria-label="${escapeAttr(t('ticker.days'))}">` + same.map(d =>
      `<a href="#/ticker/${escapeAttr(d.date)}" aria-current="${escapeAttr(d.date === date ? 'page' : 'false')}">${escapeAttr(dayLabel(d.date))}</a>`).join('') + '</div>';
  }

  if (!day) {
    html += `<p class="tk-empty">${escapeAttr(t('ticker.noData'))}</p>`;
  } else {
    ['N', 'S', 'V'].forEach(c => { if (day.councils[c]) html += councilHTML(c, day.councils[c], day.decisions || []); });
  }
  html += `<p class="detail-source">${escapeAttr(t('ticker.credit'))} ${escapeAttr(t('ticker.notOfficial'))}</p>`;
  content.innerHTML = html;
}

function councilHTML(c, body, decisions) {
  const speeches = body.speeches || [];
  const votes = body.votes || [];
  // Speeches, votes and decisions grouped under their agenda item (no reordering).
  const bySubject = {};
  speeches.forEach(s => { (bySubject[s.subject] = bySubject[s.subject] || []).push(s); });
  const votesByBusiness = {}, decByBusiness = {};
  votes.forEach(v => { (votesByBusiness[v.business] = votesByBusiness[v.business] || []).push(v); });
  decisions.forEach(d => { if (d.council === c) (decByBusiness[d.business] = decByBusiness[d.business] || []).push(d); });
  const placedVotes = new Set(), placedDec = new Set(), placedSubjects = new Set();

  let latest = null;
  speeches.forEach(s => { if (s.start && (!latest || s.start >= latest.start)) latest = s; });

  let html = `<div class="tk-council"><h2 class="canton-section-title">${escapeAttr(t(COUNCIL_KEYS[c]))}</h2>`;
  const begins = [];
  (body.meetings || []).forEach(m => { if (m.begin) begins.push(m.begin); });
  if (begins.length) html += `<p class="tk-meta">${escapeAttr(tf('ticker.sittings', { times: begins.join(', ') }))}</p>`;
  if (latest) {
    let item = null;
    (body.agenda || []).forEach(a => { if (a.subject === latest.subject && a.items && a.items[0]) item = a.items[0]; });
    html += `<p class="tk-latest">${escapeAttr(tf('ticker.latest', { time: latest.start, item: item ? item.business + ' ' + titleOf(item.title).text : '' }))}</p>`;
  }
  if (c === 'S') html += `<p class="tk-meta">${escapeAttr(t('ticker.noVotesCS'))}</p>`;

  html += `<h3 class="tk-h">${escapeAttr(t('ticker.agenda'))}</h3><ol class="tk-agenda">`;
  (body.agenda || []).forEach(a => {
    placedSubjects.add(a.subject);
    const sp = bySubject[a.subject] || [];
    const vs = [], ds = [];
    (a.items || []).forEach(it => {
      (votesByBusiness[it.business] || []).forEach(v => { if (!placedVotes.has(v.id)) { placedVotes.add(v.id); vs.push(v); } });
      (decByBusiness[it.business] || []).forEach(d => { if (!placedDec.has(d)) { placedDec.add(d); ds.push(d); } });
    });
    html += `<li class="tk-item">` + itemHTML(c, a, sp, vs, ds) + '</li>';
  });
  html += '</ol>';

  // Anything the source didn't attach to an agenda item, so nothing is left out.
  const restS = [], restV = [], restD = [];
  speeches.forEach(s => { if (!placedSubjects.has(s.subject)) restS.push(s); });
  votes.forEach(v => { if (!placedVotes.has(v.id)) restV.push(v); });
  decisions.forEach(d => { if (d.council === c && !placedDec.has(d)) restD.push(d); });
  if (restS.length || restV.length || restD.length) {
    html += `<h3 class="tk-h">${escapeAttr(t('ticker.other'))}</h3><div class="tk-item">` +
      itemHTML(c, { subject: 'other-' + c, items: [] }, restS, restV, restD) + '</div>';
  }
  return html + '</div>';
}

function itemHTML(c, a, sp, vs, ds) {
  let head = '';
  (a.items || []).forEach(it => {
    head += `<div class="tk-biz"><a class="tk-num" href="${escapeAttr(businessUrl(it.businessId))}" target="_blank" rel="noopener noreferrer">${escapeAttr(it.business)}</a> ` +
      titleHTML(it.title) + (it.note ? ` <span class="tk-notes">${escapeAttr(it.note)}</span>` : '') + '</div>';
  });
  let status = sp.length
    ? tf('ticker.debatedAt', { from: sp[0].start || '', to: sp[sp.length - 1].end || sp[sp.length - 1].start || '', n: sp.length })
    : t('ticker.notYet');
  if (vs.length) status += ' · ' + plural('ticker.votes', vs.length);
  let html = head + `<p class="tk-meta">${escapeAttr(status)}</p>`;
  ds.forEach(d => {
    // Several drafts of one business each get their own decision: name the draft.
    const label = ds.length > 1 && d.bill ? tf('ticker.decisionDraft', { n: d.bill }) : t('ticker.decisionH');
    // titleHTML escapes the official text itself.
    html += `<p class="tk-dec"><b>${escapeAttr(label)}:</b> ` + titleHTML(d.text) + '</p>';
  });
  if (!sp.length && !vs.length) return html;
  html += `<details class="tk-more" data-k="${escapeAttr(c + ':' + a.subject)}"><summary>${escapeAttr(t('ticker.details'))}</summary>`;
  if (vs.length) html += `<h4 class="tk-h4">${escapeAttr(t('ticker.votesH'))}</h4>` + vs.map(voteHTML).join('');
  if (sp.length) {
    html += `<h4 class="tk-h4">${escapeAttr(t('ticker.speakersH'))}</h4><ul class="tk-speakers">` + sp.map(s => {
      const bits = [];
      if (s.role !== 'Mit-M' && s.role !== 'Mit-F' && s.role !== 'other') bits.push(t('ticker.role.' + s.role));
      if (s.group) bits.push(groupLabel(s.group));
      if (s.canton) bits.push(s.canton);
      return `<li><span class="tk-time">${escapeAttr((s.start || '') + (s.end ? '–' + s.end : ''))}</span> ` +
        `<span class="tk-name">${escapeAttr(s.name)}</span>` + (bits.length ? ` <span class="tk-who">${escapeAttr(bits.join(' · '))}</span>` : '') + '</li>';
    }).join('') + '</ul>';
  }
  return html + '</details>';
}

// One National Council vote: what was voted on, what Yes and No meant (official
// text, side by side), the tally and the tally by parliamentary group. No outcome.
function voteHTML(v) {
  const tl = v.tally || {};
  const y = tl.yes || 0, n = tl.no || 0, ab = tl.abstain || 0;
  const what = [v.subject, v.bill && v.billTitle ? titleOf(v.billTitle).text : ''];
  let html = `<div class="tk-vote"><p class="tk-vh"><span class="tk-time">${escapeAttr(v.time || '')}</span> ` +
    escapeAttr(what[0] || what[1] || v.business) + '</p>';
  if (what[0] && what[1]) html += `<p class="tk-meta">${escapeAttr(what[1])}</p>`;
  html += `<div class="tk-bar" role="img" aria-label="${escapeAttr(y + ' ' + t('news.tally.yes') + ', ' + n + ' ' + t('news.tally.no') + ', ' + ab + ' ' + t('news.tally.abst'))}">` +
    `<span style="flex:${escapeAttr(y)};background:${escapeAttr(YES)}"></span><span style="flex:${escapeAttr(n)};background:${escapeAttr(NO)}"></span>` +
    `<span style="flex:${escapeAttr(ab)};background:#d6d3ca"></span></div>` +
    `<p class="tk-tally"><b style="color:${escapeAttr(YES)}">${escapeAttr(y)}</b> ${escapeAttr(t('news.tally.yes'))} · ` +
    `<b style="color:${escapeAttr(NO)}">${escapeAttr(n)}</b> ${escapeAttr(t('news.tally.no'))} · <b>${escapeAttr(ab)}</b> ${escapeAttr(t('news.tally.abst'))}</p>`;
  const m = v.meaning || {};
  if (m.yes || m.no) {
    html += '<dl class="tk-meaning">' +
      `<div><dt>${escapeAttr(t('ticker.meaningYes'))}</dt><dd>${escapeAttr(m.yes || '—')}</dd></div>` +
      `<div><dt>${escapeAttr(t('ticker.meaningNo'))}</dt><dd>${escapeAttr(m.no || '—')}</dd></div></dl>`;
  }
  const groups = Object.keys(v.byParty || {});
  if (groups.length) {
    html += `<details class="tk-groups"><summary>${escapeAttr(t('ticker.byGroup'))}</summary><table class="tk-gt"><thead><tr><th></th>` +
      `<th>${escapeAttr(t('news.tally.yes'))}</th><th>${escapeAttr(t('news.tally.no'))}</th><th>${escapeAttr(t('news.tally.abst'))}</th></tr></thead><tbody>` +
      groups.map(g => { const b = v.byParty[g]; return `<tr><th>${escapeAttr(groupLabel(g))}</th><td>${escapeAttr(b.yes)}</td><td>${escapeAttr(b.no)}</td><td>${escapeAttr(b.abstain)}</td></tr>`; }).join('') +
      '</tbody></table></details>';
  }
  return html + '</div>';
}
