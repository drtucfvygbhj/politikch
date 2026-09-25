/* ============================================================
   Politikch 1.1 — the news-style design.
   Masthead, menu with sub-categories, the "Live" row, the three-column
   front page and the footer. Everything shown is computed from the data
   files; every ordering and "live" rule is written down here and in the
   admin tool (admin/). Design 1.0 (the original) stays in app.js/styles.css,
   frozen. Which one visitors get is set in js/site-settings.js.
   ============================================================ */
import { MAP_PATHS } from './map-data.js?v=20260925a';

let C = null;                          // context from app.js (state, t, helpers)
export function configureNews(ctx) { C = ctx; }
export function newsActive() { return document.documentElement.getAttribute('data-design') === '1.1'; }
const SETTINGS = () => window.PCH_SETTINGS || {};

const YES = '#534AB7', NO = '#0F6E56';   // purple = yes / for, green = no / against
const ABST = '#ffffff', ABSENT = '#e6e4dd', NONE_BG = '#b4b2a9';
const LOCALES = { en: 'en-CH', de: 'de-CH', fr: 'fr-CH', it: 'it-CH', rm: 'de-CH' };
const RM_DAYS = ['dumengia', 'glindesdi', 'mardi', 'mesemna', 'gievgia', 'venderdi', 'sonda'];

/* ---- small helpers ---- */
function escapeAttr(s) {
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function t(k) { return C.t(k); }
function tf(k, vars) {
  let s = C.t(k);
  Object.keys(vars).forEach(a => { s = s.split('{' + a + '}').join(String(vars[a])); });
  return s;
}
const lang = () => C.state.lang;
const D = () => C.state.data;
function todayDate() { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), d.getDate()); }
function isoToday() { const d = todayDate(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
function dayDiff(iso) { return Math.round((new Date(iso + 'T00:00:00') - todayDate()) / 864e5); }
function longDate(iso) { return C.formatLongDate(new Date(iso + 'T00:00:00')); }
function shortDate(iso) {
  const d = new Date(iso + 'T00:00:00');
  if (lang() === 'rm') return `${d.getDate()}.${d.getMonth() + 1}.`;
  return new Intl.DateTimeFormat(LOCALES[lang()], { day: 'numeric', month: 'short' }).format(d);
}
function money(x) {
  const n = new Intl.NumberFormat(LOCALES[lang()], { notation: 'compact', maximumSignificantDigits: 3 }).format(x || 0);
  return 'CHF ' + n;
}
function num(x) { return new Intl.NumberFormat(LOCALES[lang()], { maximumFractionDigits: 1 }).format(x); }
function inDays(n) { return n <= 0 ? t('news.days.today') : n === 1 ? t('news.days.one') : tf('news.days.many', { n }); }
function daysLeft(n) { return n <= 0 ? t('news.left.today') : n === 1 ? t('news.left.one') : tf('news.left.many', { n }); }
function liveDot(on) {
  return on ? `<span class="n-live" role="img" aria-label="${escapeAttr(t('news.live'))}"></span>` : '';
}

/* ---- parties ---- */
function party(k) { return D().parties[k]; }
function pShort(k) {
  const p = party(k); if (!p) return k;
  const parts = String(p.abbr || k).split('/');
  return (['fr', 'it'].includes(lang()) && parts[1]) ? parts[1] : parts[0];
}
function pName(k) { const p = party(k); return p ? C.localized(p.name) : k; }
function pColor(k) { const p = party(k); return p ? p.color : NONE_BG; }
function partyOrder() {   // left to right, as on the spectrum
  return Object.keys(D().parties).sort((a, b) => (party(a).spectrum?.x ?? 50) - (party(b).spectrum?.x ?? 50));
}
function partiesBySeats() {
  return Object.keys(D().parties).sort((a, b) => (party(b).ncSeats || 0) - (party(a).ncSeats || 0));
}

/* ---- votes, sessions, live rules ---- */
function fundingOf(i) {
  const f = D().financing?.initiatives?.[i.id];
  return f ? ((f.pro?.totalRevenue || 0) + (f.contra?.totalRevenue || 0)) : 0;
}
function upcoming() { return D().initiatives.filter(i => i.status === 'upcoming' && i.voteDate && dayDiff(i.voteDate) >= 0); }
// The next ballot and its proposals, ordered by total declared campaign funding
// (for + against), then by id (the official order on the ballot).
function nextBallot() {
  const u = upcoming();
  if (!u.length) return null;
  const date = u.map(i => i.voteDate).sort()[0];
  const items = u.filter(i => i.voteDate === date).sort((a, b) => (fundingOf(b) - fundingOf(a)) || (a.id < b.id ? -1 : 1));
  return { date, items };
}
function collecting() {
  return D().initiatives.filter(i => i.status === 'collecting' && i.deadline && dayDiff(i.deadline) >= 0)
    .sort((a, b) => (a.deadline < b.deadline ? -1 : 1));
}
function decided() {
  return D().initiatives.filter(i => (i.status === 'adopted' || i.status === 'rejected') && /^vote-\d{8}/.test(i.id))
    .sort((a, b) => (a.id < b.id ? 1 : -1));
}
function voteDateOf(id) { const m = /^vote-(\d{4})(\d\d)(\d\d)/.exec(id); return m ? `${m[1]}-${m[2]}-${m[3]}` : null; }
function currentSession(sessions) { const d = isoToday(); return sessions.find(s => s.start <= d && d <= s.end) || null; }

function liveState(sessions) {
  const L = SETTINGS().live || {};
  const ballotDays = Number(L.ballotDays ?? 28), deadlineDays = Number(L.deadlineDays ?? 7);
  const nb = nextBallot();
  const ballotLive = !!nb && dayDiff(nb.date) <= ballotDays;
  return {
    upcoming: ballotLive,
    results: D().initiatives.some(i => i.voteDate && dayDiff(i.voteDate) === 0),
    sessions: !!currentSession(sessions),
    collecting: collecting().some(i => dayDiff(i.deadline) <= deadlineDays),
    money: ballotLive && nb.items.some(i => fundingOf(i) > 0),
  };
}

/* ============================================================
   Masthead, menu, live row, footer
   ============================================================ */
let chromeMounted = false;
let sessionsCache = [];

export function mountNewsChrome() {
  if (chromeMounted) return;
  chromeMounted = true;
  // The search box (and its results list) moves from the 1.0 bar into the masthead.
  const search = document.querySelector('#navbar .nav-search');
  const slot = document.getElementById('n-search');
  if (search && slot) slot.appendChild(search);
  // Language buttons live in re-rendered markup, so they are delegated.
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.n-lang');
    if (!b) return;
    e.preventDefault();
    if (b.dataset.lang !== lang()) { C.track('lang', b.dataset.lang); C.setLang(b.dataset.lang); }
  });
  const btn = document.getElementById('n-menu-btn');
  const nav = document.getElementById('n-nav');
  btn.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  // Close the phone menu after choosing something, and on Escape.
  nav.addEventListener('click', (e) => { if (e.target.closest('a')) { nav.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); } });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { nav.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); if (document.activeElement && nav.contains(document.activeElement)) document.activeElement.blur(); }
  });
  wireTooltips();
  fitTitle();
  window.addEventListener('resize', fitTitle);
  if (document.fonts) document.fonts.ready.then(fitTitle);
}

// The nameplate can be stretched in the admin (--n-titleSX / --n-titleSY). A CSS
// transform doesn't change the layout box, so the extra width is added back as a
// margin to keep the name centred and clear of the tagline.
function fitTitle() {
  const txt = document.querySelector('.n-name-text');
  if (!txt) return;
  const sx = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--n-titleSX')) || 1;
  txt.style.marginRight = '0px';
  txt.style.marginRight = ((sx - 1) * txt.offsetWidth) + 'px';
}

function menuModel(L) {
  const cantons = Object.keys(D().cantons).sort((a, b) => C.localized(D().cantons[a].name).localeCompare(C.localized(D().cantons[b].name), LOCALES[lang()]));
  return [
    { title: t('nav.initiatives'), items: [
      [t('news.m.upcoming'), '#/ballots/upcoming', L.upcoming],
      [t('news.m.results'), '#/ballots/decided', L.results],
      [t('status.collecting'), '#/ballots/collecting', L.collecting],
      [t('init.tabPending'), '#/ballots/pending', false],
      [t('news.m.money'), '#/financing/votes', L.money],
    ] },
    { title: t('nav.parliament'), items: [
      [t('parl.title'), '#/assembly/nc', false],
      [t('parl.nc'), '#/assembly/nc', false],
      [t('parl.cs'), '#/assembly/cs', false],
      [t('council.title'), '#/assembly/fc', false],
      [t('spec.title'), '#/assembly/spectrum', false],
      [t('nav.sessions'), '#/sessions', L.sessions],
      [t('votes.title'), '#/votes', false],
    ] },
    { title: t('nav.parties'), items: [[t('spec.title'), '#/assembly/spectrum', false]].concat(partiesBySeats().map(k => [pName(k), '#/party/' + k, false])) },
    { title: t('nav.cantons'), items: [[t('news.cs.pageTitle'), '#/cantons', false]].concat(cantons.map(c => [C.localized(D().cantons[c].name), '#/canton/' + c, false])) },
    { title: t('nav.financing'), items: [
      [t('news.m.partyFin'), '#/financing', false],
      [t('news.m.voteFin'), '#/financing/votes', L.money],
    ] },
    { title: t('footer.about'), items: [
      [t('footer.about'), '#/about'], [t('footer.method'), '#/page/methodology'], [t('footer.sources'), '#/page/sources'],
      [t('footer.reuse'), '#/page/reuse'], [t('footer.privacy'), '#/privacy'], [t('footer.legal'), '#/page/legal'],
      [t('footer.contact'), '#/page/contact'], [t('footer.feedback'), '#/page/feedback'], [t('nav.profile'), '#/profile'],
    ] },
  ];
}

function linkHTML(item, cls) {
  const [label, href, live, scroll] = item;
  const attrs = scroll ? ` data-scroll="${escapeAttr(scroll)}"` : '';
  return `<a class="${escapeAttr(cls || '')}" href="${escapeAttr(href)}"` + attrs + `>${escapeAttr(label)}` + liveDot(live) + '</a>';
}

function langButtons() {
  return ['en', 'de', 'fr', 'it', 'rm'].map(l =>
    `<button type="button" class="n-lang${escapeAttr(l === lang() ? ' on' : '')}" data-lang="${escapeAttr(l)}" aria-pressed="${escapeAttr(l === lang() ? 'true' : 'false')}">${escapeAttr(l.toUpperCase())}</button>`).join('');
}

export async function renderNewsChrome() {
  const idx = await C.ensureSessionsIndex();
  sessionsCache = (idx && idx.sessions) || [];
  const L = liveState(sessionsCache);
  const model = menuModel(L);

  // Date line
  const now = todayDate();
  const weekday = lang() === 'rm' ? RM_DAYS[now.getDay()] : new Intl.DateTimeFormat(LOCALES[lang()], { weekday: 'long' }).format(now);
  const fetched = D().initMeta && D().initMeta.fetchedAt ? new Date(D().initMeta.fetchedAt) : null;
  let line = weekday.charAt(0).toUpperCase() + weekday.slice(1) + ', ' + C.formatLongDate(now);
  if (fetched && !isNaN(fetched)) line += ' · ' + tf('news.updated', { date: C.formatLongDate(fetched) });
  document.getElementById('n-date').textContent = line;
  document.getElementById('n-langs').innerHTML = langButtons();
  document.getElementById('n-tag').textContent = t('news.tagline');
  document.getElementById('n-menu-btn').textContent = t('news.menu');
  document.getElementById('n-acct-t').textContent = t('nav.profile');

  // Menu: categories with their sub-categories (shown on hover / focus)
  document.getElementById('n-menu').innerHTML = model.map((cat, n) => {
    const live = cat.items.some(it => it[2]);
    const size = cat.items.length > 12 ? ' wide' : cat.items.length > 7 ? ' mid' : '';
    return `<li class="n-top"><a class="n-cat" href="${escapeAttr(cat.items[0][1])}" aria-haspopup="true" aria-controls="n-sub-${escapeAttr(n)}">${escapeAttr(cat.title)}` + liveDot(live) + '</a>' +
      `<div class="n-sub${escapeAttr(size)}" id="n-sub-${escapeAttr(n)}"><div class="n-sub-h">${escapeAttr(cat.title)}</div><ul>` +
      cat.items.map(it => '<li>' + linkHTML(it) + '</li>').join('') + '</ul></div></li>';
  }).join('');

  renderTicker(L);
  renderFooter(model);
}

function renderTicker(L) {
  const host = document.getElementById('n-ticker');
  const items = [];
  const nb = nextBallot();
  if (nb && L.upcoming) {
    nb.items.forEach(i => items.push([t('news.tick.vote'), shortDate(i.voteDate) + ' · ' + inDays(dayDiff(i.voteDate)), C.initTitlePlain(i), '#/initiative/' + i.id]));
  }
  const cur = currentSession(sessionsCache);
  if (cur) {
    const week = Math.floor((todayDate() - new Date(cur.start + 'T00:00:00')) / 6048e5) + 1;
    const weeks = Math.max(1, Math.ceil(((new Date(cur.end + 'T00:00:00') - new Date(cur.start + 'T00:00:00')) / 864e5 + 1) / 7));
    items.push([t('nav.parliament'), C.sessionName(cur) + ' · ' + t('news.tick.sitting'),
      tf('news.now.week', { w: week, total: weeks, date: shortDate(cur.end) }), '#/session/' + cur.id]);
  }
  if (nb && L.money) {
    const total = nb.items.reduce((s, i) => s + fundingOf(i), 0);
    items.push([t('news.m.money'), tf('news.tick.ballot', { date: shortDate(nb.date) }), tf('news.tick.declared', { amount: money(total) }), '#/financing/votes']);
  }
  collecting().forEach(i => items.push([t('status.collecting'), daysLeft(dayDiff(i.deadline)), C.initTitlePlain(i), '#/initiative/' + i.id]));

  if (!items.length) { host.hidden = true; return; }
  host.hidden = false;
  const row = (tab) => items.map(([a, b, c, href]) =>
    `<a class="n-ti" href="${escapeAttr(href)}" tabindex="${escapeAttr(tab)}"><b>${escapeAttr(a)}</b> <span>${escapeAttr(b)}</span> ${escapeAttr(c)}</a>`).join('');
  const chars = items.reduce((s, it) => s + it[0].length + it[1].length + it[2].length, 0);
  const secs = Math.max(30, Math.round(chars * 7 / 45));        // about 45 px per second
  host.innerHTML = `<span class="n-tl">${escapeAttr(t('news.live'))}<span class="n-live" aria-hidden="true"></span></span>` +
    `<div class="n-tv"><div class="n-tt" style="animation-duration:${escapeAttr(secs)}s">` + row(0) +
    '<span class="n-dup" aria-hidden="true">' + row(-1) + '</span></div></div>';
}

function renderFooter(model) {
  const host = document.getElementById('news-footer');
  const cols = model.filter((c, n) => n !== 3).map(cat =>
    `<div><h5>${escapeAttr(cat.title)}` + liveDot(cat.items.some(it => it[2])) + '</h5><ul>' +
    cat.items.map(it => '<li>' + linkHTML(it) + '</li>').join('') + '</ul></div>').join('');
  const cantons = model[3];
  host.innerHTML = '<div class="n-wrap"><div class="n-fgrid">' +
    `<div class="n-fabout"><a class="n-fname" href="#/"><span class="n-cross" aria-hidden="true"></span>Politikch</a><p>${escapeAttr(t('footer.disclaimer'))}</p></div>` +
    cols + '</div>' +
    `<div class="n-fcantons"><h5>${escapeAttr(cantons.title)}</h5><ul>` + cantons.items.map(it => '<li>' + linkHTML(it) + '</li>').join('') + '</ul></div>' +
    `<div class="n-fbase"><span>${escapeAttr(t('news.copy'))}</span><span class="n-langs">` + langButtons() + '</span></div></div>';
}

/* ============================================================
   Front page
   ============================================================ */
function hemicycle(dots, rows, label) {
  // dots: [{ fill, k, tip }] — seats fill left to right, row by row from the front.
  const n = dots.length;
  const R = rows === 1 ? 70 : 100, r0 = rows === 1 ? 70 : 38;
  const radii = [];
  for (let i = 0; i < rows; i++) radii.push(r0 + (R - r0) * i / Math.max(rows - 1, 1));
  const sum = radii.reduce((a, b) => a + b, 0);
  const per = radii.map(r => Math.round(n * r / sum));
  per[per.length - 1] += n - per.reduce((a, b) => a + b, 0);
  const pts = [];
  radii.forEach((r, ri) => { for (let j = 0; j < per[ri]; j++) pts.push([Math.PI - Math.PI * (per[ri] > 1 ? j / (per[ri] - 1) : 0.5), r]); });
  pts.sort((a, b) => (b[0] - a[0]) || (a[1] - b[1]));
  const rad = rows > 1 ? Math.min(6.2, (R - r0) / (rows - 1) * 0.42) : 13;
  const vb = rows > 1 ? '0 0 220 118' : '25 20 170 100';
  return `<svg class="n-chart" viewBox="${escapeAttr(vb)}" role="img" aria-label="${escapeAttr(label)}">` +
    pts.map(([a, r], i) => {
      const d = dots[i]; if (!d) return '';
      const stroke = d.fill === ABST ? ' stroke="#8a877e" stroke-width="0.8"' : '';
      return `<circle cx="${escapeAttr((110 + r * Math.cos(a)).toFixed(1))}" cy="${escapeAttr((108 - r * Math.sin(a)).toFixed(1))}" r="${escapeAttr(rad.toFixed(1))}" fill="${escapeAttr(d.fill)}" data-k="${escapeAttr(d.k)}" data-ntip="${escapeAttr(d.tip)}"` + stroke + '/>';
    }).join('') + '</svg>';
}

function legend(pairs) {   // [key, colour, label, href?]
  return '<div class="n-legend">' + pairs.map(([k, c, label, href]) => href
    ? `<a href="${escapeAttr(href)}" data-k="${escapeAttr(k)}"><i style="background:${escapeAttr(c)}"></i>${escapeAttr(label)}</a>`
    : `<span tabindex="0" data-k="${escapeAttr(k)}"><i style="background:${escapeAttr(c)}"></i>${escapeAttr(label)}</span>`).join('') + '</div>';
}

// Title of a session final vote, with the same unofficial / machine-translation
// labelling as the session pages (POL-13). Badges are non-focusable here because
// the title sits inside a link.
function sessionVoteTitle(v) {
  const title = v.title || {};
  if (title[lang()]) return escapeAttr(title[lang()]);
  const tr = C.voteTransTitle(v);
  if (tr) return escapeAttr(tr) + C.unofficialBadge(false);
  const mt = C.mtVoteTitle(v);
  if (mt) return escapeAttr(mt) + C.mtBadge(false);
  const l = ['de', 'fr', 'it'].find(x => title[x]);
  return escapeAttr(l ? title[l] : (v.business || '')) + (l ? ` <abbr class="svote-lang" title="${escapeAttr(t('session.titleLangNote'))}">${escapeAttr(l.toUpperCase())}</abbr>` : '');
}

/* ---- centre: one story per proposal on the next ballot ---- */
function storyImage(i, n) {
  const img = window.PCH_IMAGES || {};
  const lib = img.library || {};
  let id = (img.assign || {})[i.id];
  const ids = Object.keys(lib).sort();
  if (!lib[id] && ids.length) id = ids[n % ids.length];     // default: the library in turn
  const e = lib[id];
  if (!e) {
    return `<figure class="n-photo${escapeAttr(n === 0 ? ' lead' : '')}"><a href="#/initiative/${escapeAttr(i.id)}" class="n-ph" aria-hidden="true" tabindex="-1"><span class="n-cross"></span></a></figure>`;
  }
  const alt = (e.alt && (e.alt[lang()] || e.alt.en)) || '';
  return `<figure class="n-photo${escapeAttr(n === 0 ? ' lead' : '')}"><a href="#/initiative/${escapeAttr(i.id)}" tabindex="-1">` +
    `<img src="images/${escapeAttr(e.w800)}" srcset="images/${escapeAttr(e.w800)} 800w, images/${escapeAttr(e.w1600)} 1600w" sizes="(max-width: 900px) 100vw, 50vw" alt="${escapeAttr(alt)}" loading="${escapeAttr(n === 0 ? 'eager' : 'lazy')}"></a>` +
    `<figcaption>${escapeAttr(e.credit || '')}</figcaption></figure>`;
}

function moneyFig(i) {
  const f = D().financing?.initiatives?.[i.id];
  const head = `<div class="n-k">${escapeAttr(t('news.m.money'))}</div>`;
  if (!f || !(f.pro || f.contra)) return '<div class="n-fig">' + head + `<p class="n-empty">${escapeAttr(t('news.money.none'))}</p></div>`;
  const p = f.pro || {}, c = f.contra || {};
  const pv = p.totalRevenue || 0, cv = c.totalRevenue || 0;
  const side = (s) => {
    const a = s.actorCount || 0, d = (s.largeDonors || []).length;
    return tf(a === 1 ? 'news.money.actor1' : 'news.money.actors', { n: a }) + ' · ' + tf(d === 1 ? 'news.money.donation1' : 'news.money.donations', { n: d });
  };
  return '<div class="n-fig" data-hl>' + head +
    `<h4 class="n-ft">${escapeAttr(tf('news.money.h', { amount: money(pv + cv) }))}</h4>` +
    `<div class="n-split"><div data-k="for"><span class="n-lbl" style="color:${escapeAttr(YES)}">${escapeAttr(t('news.for'))}</span><span class="n-big">${escapeAttr(money(pv))}</span></div>` +
    `<div data-k="against" class="n-right"><span class="n-lbl" style="color:${escapeAttr(NO)}">${escapeAttr(t('news.against'))}</span><span class="n-big">${escapeAttr(money(cv))}</span></div></div>` +
    `<a class="n-bar tall" href="#/initiative/${escapeAttr(i.id)}"><span data-k="for" data-ntip="${escapeAttr(t('news.for') + ': ' + money(pv))}" style="flex:${escapeAttr(pv)};background:${escapeAttr(YES)}"></span>` +
    `<span data-k="against" data-ntip="${escapeAttr(t('news.against') + ': ' + money(cv))}" style="flex:${escapeAttr(cv)};background:${escapeAttr(NO)}"></span></a>` +
    `<div class="n-split n-meta"><span data-k="for">${escapeAttr(side(p))}</span><span data-k="against">${escapeAttr(side(c))}</span></div>` +
    `<p class="n-src">${escapeAttr(t('news.money.src'))}</p></div>`;
}

function recsFig(i) {
  const rec = i.recommendations || {};
  const head = `<div class="n-k">${escapeAttr(t('news.rec.k'))}</div>`;
  if (!Object.keys(rec).length) return '<div class="n-fig">' + head + `<p class="n-empty">${escapeAttr(t('news.rec.empty'))}</p></div>`;
  const groups = { yes: [], no: [], none: [] };
  partyOrder().forEach(k => groups[rec[k] === 'yes' || rec[k] === 'no' ? rec[k] : 'none'].push(k));
  const seats = {};
  Object.keys(groups).forEach(g => { seats[g] = groups[g].reduce((s, k) => s + (party(k).ncSeats || 0), 0); });
  const segs = [['yes', t('news.yes'), YES], ['no', t('news.no'), NO], ['none', t('news.rec.none'), '']].filter(s => seats[s[0]]);
  const bar = segs.map(([g, label, col]) =>
    `<span class="${escapeAttr(g === 'none' ? 'n-none' : '')}" data-k="r-${escapeAttr(g)}" data-ntip="${escapeAttr(tf('news.rec.tip', { label, n: seats[g] }))}" style="flex:${escapeAttr(seats[g])};${escapeAttr(col ? 'background:' + col : '')}">${escapeAttr(label + ' · ' + seats[g])}</span>`).join('');
  const names = segs.map(([g]) => `<span class="n-grp" style="flex:${escapeAttr(seats[g])}">` +
    groups[g].map(k => `<a href="#/party/${escapeAttr(k)}" data-k="r-${escapeAttr(g)}" data-ntip="${escapeAttr(pName(k) + ' · ' + tf('news.seats', { n: party(k).ncSeats || 0 }))}">${escapeAttr(pShort(k))}</a>`).join(' ') + '</span>').join('');
  const zero = [];
  if (!seats.yes) zero.push(t('news.rec.noYes'));
  if (!seats.no) zero.push(t('news.rec.noNo'));
  return '<div class="n-fig" data-hl>' + head + `<h4 class="n-ft">${escapeAttr(t('news.rec.h'))}</h4>` +
    '<div class="n-bar tall labelled">' + bar + '</div><div class="n-names n-meta">' + names + '</div>' +
    (zero.length ? `<p class="n-meta">${escapeAttr(zero.join(' · '))}</p>` : '') +
    `<p class="n-src">${escapeAttr(t('news.rec.src'))}</p></div>`;
}

function parlFig(i, files) {
  const link = (SETTINGS().parliamentLinks || {})[i.id];
  const file = link && files[link.session];
  const v = file && (file.votes || []).find(x => x.id === link.vote);
  if (!v) return '';
  const by = v.byParty || {};
  // byParty holds parliamentary-group counts (e.g. the SVP group includes Lega, EDU and MCG members).
  const groups = Object.keys(by).sort((a, b) => (party(a)?.spectrum?.x ?? 50) - (party(b)?.spectrum?.x ?? 50));
  const dots = [];
  groups.forEach(g => {
    const b = by[g];
    const tip = tf('news.parl.group', { party: party(g) ? pShort(g) : g, y: b.yes || 0, n: b.no || 0, a: b.abstain || 0 });
    for (let x = 0; x < (b.yes || 0); x++) dots.push({ fill: YES, k: `g-${g} v-yes`, tip });
    for (let x = 0; x < (b.abstain || 0); x++) dots.push({ fill: ABST, k: `g-${g} v-abstain`, tip });
    for (let x = 0; x < (b.no || 0); x++) dots.push({ fill: NO, k: `g-${g} v-no`, tip });
  });
  const absent = Math.max(0, 200 - dots.length);
  for (let x = 0; x < absent; x++) dots.push({ fill: ABSENT, k: 'v-absent', tip: tf('news.parl.absentTip', { n: absent }) });
  const tly = v.tally || {};
  const initiative = i.type === 'initiative';
  return '<div class="n-fig" data-hl>' + `<div class="n-k">${escapeAttr(t('news.parl.k'))}</div>` +
    `<h4 class="n-ft">${escapeAttr(t(initiative ? 'news.parl.hInit' : 'news.parl.hAct'))}</h4>` +
    '<div class="n-parl"><div>' + hemicycle(dots.slice(0, 200), 8, t('news.parl.hInit')) + '</div><div>' +
    `<div class="n-tally"><span data-k="v-yes"><b style="color:${escapeAttr(YES)}">${escapeAttr(tly.yes || 0)}</b> ${escapeAttr(t('news.tally.yes'))}</span>` +
    `<span data-k="v-no"><b style="color:${escapeAttr(NO)}">${escapeAttr(tly.no || 0)}</b> ${escapeAttr(t('news.tally.no'))}</span>` +
    `<span data-k="v-abstain"><b>${escapeAttr(tly.abstain || 0)}</b> ${escapeAttr(t('news.tally.abst'))}</span></div>` +
    legend([['v-yes', YES, t('news.yes')], ['v-no', NO, t('news.no')], ['v-abstain', '#fff;box-shadow:inset 0 0 0 1px #8a877e', t('news.tally.abst')], ['v-absent', ABSENT, t('news.absent')]]) +
    `<p class="n-note">${escapeAttr(t(initiative ? 'news.parl.noteInit' : 'news.parl.noteAct'))}</p></div></div>` +
    `<p class="n-src">${escapeAttr(tf('news.parl.src', { date: longDate(v.voteEnd) }))}</p></div>`;
}

function stories(nb, files) {
  if (!nb) return [];
  const out = [];
  nb.items.forEach((i, n) => {
    const d = dayDiff(i.voteDate);
    const kind = t(i.type === 'initiative' ? 'type.initiative' : 'type.referendum');
    out.push(`<article class="n-blk n-story${escapeAttr(n === 0 ? ' lead' : '')}"><div class="n-kicker">${escapeAttr(t('news.tick.vote') + ' · ' + longDate(i.voteDate) + ' · ' + inDays(d))} <span class="n-dim">· ${escapeAttr(kind)}</span></div>` +
      `<h2 class="n-hl${escapeAttr(C.initTitlePlain(i).length > 70 ? ' long' : '')}"><a href="#/initiative/${escapeAttr(i.id)}">` + C.initTitleHTML(i, false) + '</a></h2>' + storyImage(i, n) + '</article>');
    out.push('<div class="n-blk n-part">' + moneyFig(i) + '</div>');
    out.push('<div class="n-blk n-part">' + recsFig(i) + '</div>');
    out.push('<div class="n-blk n-part end">' + parlFig(i, files) +
      `<a class="n-more" href="#/initiative/${escapeAttr(i.id)}">${escapeAttr(t('news.more'))}</a></div>`);
  });
  out.push(`<p class="n-blk n-rule-note">${escapeAttr(t('news.order'))} <a href="#/page/methodology">${escapeAttr(t('news.orderLink'))}</a></p>`);
  return out;
}

/* ---- left column: what is happening now ---- */
function leftBlocks(files, last) {
  const out = [];
  const cur = currentSession(sessionsCache);
  if (cur) {
    const start = new Date(cur.start + 'T00:00:00'), end = new Date(cur.end + 'T00:00:00');
    const total = Math.round((end - start) / 864e5) + 1;
    const done = Math.min(total, Math.max(1, Math.round((todayDate() - start) / 864e5) + 1));
    const week = Math.floor((done - 1) / 7) + 1, weeks = Math.max(1, Math.ceil(total / 7));
    out.push(`<section class="n-blk n-mod"><div class="n-k">${escapeAttr(t('news.now.k'))}</div>` +
      `<h3 class="n-mh"><a href="#/session/${escapeAttr(cur.id)}">${escapeAttr(C.sessionName(cur))}</a>` + liveDot(true) + '</h3>' +
      `<div class="n-bar"><span style="flex:${escapeAttr(done)};background:var(--n-ink)"></span><span style="flex:${escapeAttr(total - done)};background:var(--n-rule-c)"></span></div>` +
      `<p class="n-meta">${escapeAttr(shortDate(cur.start) + ' – ' + shortDate(cur.end) + ' · ' + tf('news.now.week', { w: week, total: weeks, date: shortDate(cur.end) }))}</p></section>`);
  }

  if (last && files[last.id]) {
    const votes = (files[last.id].votes || []).slice()
      .sort((a, b) => Math.abs((a.tally?.yes || 0) - (a.tally?.no || 0)) - Math.abs((b.tally?.yes || 0) - (b.tally?.no || 0)));
    const rows = votes.slice(0, 5).map(v => {
      const y = v.tally?.yes || 0, n = v.tally?.no || 0;
      return `<li class="n-row" data-href="#/session/${escapeAttr(last.id)}"><h4 class="n-clamp"><a href="#/session/${escapeAttr(last.id)}">` + sessionVoteTitle(v) + '</a></h4>' +
        `<div class="n-bar"><span style="flex:${escapeAttr(y)};background:${escapeAttr(YES)}" data-ntip="${escapeAttr(y + ' ' + t('news.tally.yes'))}"></span><span style="flex:${escapeAttr(n)};background:${escapeAttr(NO)}" data-ntip="${escapeAttr(n + ' ' + t('news.tally.no'))}"></span></div>` +
        `<p class="n-meta">${escapeAttr(t('parl.nc') + ' · ' + y + '–' + n + ' · ' + t(v.passed ? 'status.adopted' : 'status.rejected') + ' · ' + shortDate(v.voteEnd))}</p></li>`;
    }).join('');
    out.push(`<section class="n-blk n-mod"><div class="n-k">${escapeAttr(t('news.fv.k'))}</div>` +
      `<p class="n-meta">${escapeAttr(tf('news.fv.meta', { session: C.sessionName(last), n: votes.length }))}</p><ul class="n-list">` + rows + '</ul>' +
      `<a class="n-more" href="#/session/${escapeAttr(last.id)}">${escapeAttr(tf('news.fv.all', { n: votes.length }))}</a></section>`);
  }

  const coll = collecting();
  if (coll.length) {
    out.push(`<section class="n-blk n-mod"><div class="n-k">${escapeAttr(t('news.sig.k'))}</div><p class="n-meta">${escapeAttr(t('news.sig.meta'))}</p><ul class="n-list">` +
      coll.slice(0, 5).map(i => `<li class="n-row" data-href="#/initiative/${escapeAttr(i.id)}"><h4><a href="#/initiative/${escapeAttr(i.id)}">` + C.initTitleHTML(i, false) + '</a></h4>' +
        `<p class="n-meta">${escapeAttr(tf('news.sig.row', { date: longDate(i.deadline), left: daysLeft(dayDiff(i.deadline)) }))}</p></li>`).join('') +
      `</ul><a class="n-more" href="#/ballots/collecting">${escapeAttr(tf('news.sig.all', { n: coll.length }))}</a></section>`);
  }

  const dec = decided().slice(0, 5);
  if (dec.length) {
    out.push(`<section class="n-blk n-mod"><div class="n-k">${escapeAttr(t('news.res.k'))}</div><ul class="n-list">` +
      dec.map(i => {
        const m = /([\d.]+)% (yes|no)/.exec((i.outcome && i.outcome.en) || '');
        const yes = m ? (m[2] === 'yes' ? Number(m[1]) : 100 - Number(m[1])) : null;
        const bar = yes === null ? '' : `<div class="n-bar"><span style="flex:${escapeAttr(yes.toFixed(1))};background:${escapeAttr(YES)}" data-ntip="${escapeAttr(num(yes) + '% ' + t('news.tally.yes'))}"></span><span style="flex:${escapeAttr((100 - yes).toFixed(1))};background:${escapeAttr(NO)}" data-ntip="${escapeAttr(num(100 - yes) + '% ' + t('news.tally.no'))}"></span></div>`;
        const date = voteDateOf(i.id);
        return `<li class="n-row" data-href="#/initiative/${escapeAttr(i.id)}"><h4 class="n-clamp"><a href="#/initiative/${escapeAttr(i.id)}">` + C.initTitleHTML(i, false) + '</a></h4>' + bar +
          `<p class="n-meta">${escapeAttr(C.localized(i.outcome) + (date ? ' · ' + longDate(date) : ''))}</p></li>`;
      }).join('') + `</ul><a class="n-more" href="#/ballots/decided">${escapeAttr(t('news.res.all'))}</a></section>`);
  }

  const dates = [];
  const byDate = {};
  upcoming().forEach(i => { byDate[i.voteDate] = (byDate[i.voteDate] || 0) + 1; });
  Object.keys(byDate).forEach(d => dates.push([d, byDate[d] === 1 ? t('news.dates.vote1') : tf('news.dates.vote', { n: byDate[d] }), '#/ballots/upcoming']));
  if (cur) dates.push([cur.end, tf('news.dates.sessionEnd', { session: C.sessionName(cur) }), '#/session/' + cur.id]);
  coll.slice(0, 2).forEach(i => dates.push([i.deadline, t('news.dates.deadline'), '#/initiative/' + i.id]));
  dates.sort((a, b) => (a[0] < b[0] ? -1 : 1));
  if (dates.length) {
    out.push(`<section class="n-blk n-mod"><div class="n-k">${escapeAttr(t('news.dates.k'))}</div><ul class="n-dates">` +
      dates.slice(0, 7).map(([d, label, href]) => `<li><a href="${escapeAttr(href)}"><b>${escapeAttr(shortDate(d))}</b><span>${escapeAttr(label)}</span></a></li>`).join('') + '</ul></section>');
  }
  return out;
}

/* ---- right column: the lasting picture ---- */
function chamberDots(key, chamber) {
  const out = [];
  partyOrder().forEach(k => {
    const n = party(k)[key] || 0;
    for (let x = 0; x < n; x++) out.push({ fill: pColor(k), k: 'p-' + k, tip: pName(k) + ' · ' + tf('news.seats', { n }) + ' · ' + chamber });
  });
  return out;
}

function rightBlocks() {
  const out = [];
  const order = partyOrder();
  const leg = (key) => legend(order.filter(k => party(k)[key]).map(k => ['p-' + k, pColor(k), pShort(k) + ' ' + party(k)[key], '#/party/' + k]));
  out.push(`<section class="n-blk n-mod" id="news-assembly" data-hl><div class="n-k">${escapeAttr(t('parl.label'))}</div>` +
    `<h3 class="n-mh n-cs-h"><span>${escapeAttr(t('parl.nc') + ' · ' + tf('news.seats', { n: 200 }))}</span><a class="n-cs-more" href="#/assembly/nc">${escapeAttr(t('news.cs.detail'))}</a></h3>` + hemicycle(chamberDots('ncSeats', t('parl.nc')), 8, t('parl.nc')) + leg('ncSeats') +
    `<h3 class="n-mh n-mt">${escapeAttr(t('parl.cs') + ' · ' + tf('news.seats', { n: 46 }))}</h3>` + hemicycle(chamberDots('csSeats', t('parl.cs')), 4, t('parl.cs')) + leg('csSeats') +
    `<p class="n-src">${escapeAttr(t('share.src.parliament'))}</p></section>`);

  const members = (D().council && D().council.members) || [];
  if (members.length) {
    const arc = members.map((m, n) => [m, n]).sort((a, b) => (party(a[0].party)?.spectrum?.x ?? 50) - (party(b[0].party)?.spectrum?.x ?? 50));
    const pres = members.find(m => m.role === 'president');
    const counts = {};
    members.forEach(m => { counts[m.party] = (counts[m.party] || 0) + 1; });
    out.push(`<section class="n-blk n-mod" id="news-council" data-hl><div class="n-k">${escapeAttr(t('council.title'))}</div>` +
      `<h3 class="n-mh n-cs-h"><span>${escapeAttr(pres ? tf('news.fc.h', { name: pres.name }) : t('council.sub'))}</span><a class="n-cs-more" href="#/assembly/fc">${escapeAttr(t('news.cs.detail'))}</a></h3>` +
      hemicycle(arc.map(([m, n]) => ({ fill: pColor(m.party), k: `m-${n} p-${m.party}`, tip: m.name + ' · ' + pShort(m.party) })), 1, t('council.title')) +
      legend(order.filter(k => counts[k]).map(k => ['p-' + k, pColor(k), pShort(k) + ' ' + counts[k], '#/party/' + k])) +
      '<ul class="n-plain">' + members.map((m, n) => `<li data-k="m-${escapeAttr(n)} p-${escapeAttr(m.party)}" tabindex="0"><i style="background:${escapeAttr(pColor(m.party))}"></i>${escapeAttr(m.name)}<span>${escapeAttr(pShort(m.party) + (m.role === 'president' ? ' · ' + t('news.president') : ''))}</span></li>`).join('') +
      `</ul><p class="n-src">${escapeAttr(t('council.source'))}</p></section>`);
  }

  out.push(`<section class="n-blk n-mod" id="news-spectrum" data-hl><div class="n-k">${escapeAttr(t('spec.title'))}</div>` +
    `<h3 class="n-mh n-cs-h"><span>${escapeAttr(t('news.sp.h'))}</span><a class="n-cs-more" href="#/assembly/spectrum">${escapeAttr(t('news.cs.detail'))}</a></h3>` +
    spectrumSVG({}) +
    `<p class="n-src">${escapeAttr(t('news.sp.src'))} · <a href="#/page/methodology">${escapeAttr(t('footer.method'))}</a></p></section>`);

  const fp = D().financing?.parties || {};
  const pf = Object.keys(fp).filter(k => party(k) && fp[k].totalRevenue).sort((a, b) => fp[b].totalRevenue - fp[a].totalRevenue);
  if (pf.length) {
    const max = fp[pf[0]].totalRevenue;
    const year = Math.max(...pf.map(k => fp[k].year || 0));
    out.push(`<section class="n-blk n-mod" data-hl><div class="n-k">${escapeAttr(tf('news.pf.k', { year }))}</div><h3 class="n-mh"><a href="#/financing">${escapeAttr(t('news.pf.h'))}</a></h3><ul class="n-hbars">` +
      pf.map(k => `<li><a href="#/party/${escapeAttr(k)}" data-k="p-${escapeAttr(k)}" data-ntip="${escapeAttr(pName(k) + ' · ' + money(fp[k].totalRevenue))}"><span class="n">${escapeAttr(pShort(k))}</span>` +
        `<span class="b"><i style="width:${escapeAttr((fp[k].totalRevenue / max * 100).toFixed(1))}%;background:${escapeAttr(pColor(k))}"></i></span><span class="v">${escapeAttr(money(fp[k].totalRevenue))}</span></a></li>`).join('') +
      `</ul><p class="n-src">${escapeAttr(t('news.pf.src'))}</p></section>`);
  }

  // Canton spotlight: rotates; the map and the first canton are drawn here, the rotator fills later ones.
  const bounds = mapBounds();
  out.push(`<section class="n-blk n-mod n-rot" id="n-canton" data-hl><div class="n-k">${escapeAttr(t('news.cs.k'))}</div><div class="n-tbar" aria-hidden="true"><i></i><b class="n-pz"></b></div>` +
    `<h3 class="n-mh n-cs-h"><a id="n-c-name" href="#/"></a><a class="n-cs-more" id="n-c-detail" href="#/cantons">${escapeAttr(t('news.cs.detail'))}</a></h3>` +
    `<svg class="n-chart n-map" viewBox="${escapeAttr(bounds)}" role="group" aria-label="${escapeAttr(t('nav.cantons'))}">` +
    Object.keys(MAP_PATHS).map(c => `<path d="${escapeAttr(MAP_PATHS[c].d)}" data-c="${escapeAttr(c)}" data-ntip="${escapeAttr(C.localized(D().cantons[c]?.name) || c)}" tabindex="0" role="button" aria-label="${escapeAttr(C.localized(D().cantons[c]?.name) || c)}"/>`).join('') +
    '</svg><p class="n-meta" id="n-c-meta"></p><div class="n-bar tall" id="n-c-bar"></div><ul class="n-cleg" id="n-c-leg"></ul>' +
    `<p class="n-src" id="n-c-src"></p></section>`);

  out.push(`<section class="n-blk n-mod n-rot" id="n-expl"><div class="n-k">${escapeAttr(t('news.ex.k'))}</div><div class="n-tbar" aria-hidden="true"><i></i><b class="n-pz"></b></div>` +
    '<h3 class="n-mh" id="n-e-title"></h3><p class="n-body" id="n-e-body"></p><p class="n-src" id="n-e-count"></p></section>');
  return out;
}

/* Party spectrum: traditional at the top, as on the rest of the site; all dots
   the same size. Labels are placed one by one in the first free spot around
   their dot, so they never overlap each other or another party's dot.
   opts.you = {x, y} adds the visitor's own position (profile page). */
function spectrumSVG(opts) {
  const order = partyOrder();
  const X = v => 20 + v * 1.8, Y = v => 180 - v * 1.6;
  const pts = order.map(k => { const sp = party(k).spectrum || { x: 50, y: 50 }; return { k, x: X(sp.x), y: Y(sp.y), label: pShort(k) }; });
  const boxes = [];
  const hit = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
  const dotsBox = pts.map(p => ({ x0: p.x - 6.5, x1: p.x + 6.5, y0: p.y - 6.5, y1: p.y + 6.5 }));
  if (opts.you) dotsBox.push({ x0: X(opts.you.x) - 9, x1: X(opts.you.x) + 9, y0: Y(opts.you.y) - 9, y1: Y(opts.you.y) + 9 });
  const place = (p) => {
    const w = p.label.length * 4.6 + 2, h = 8;
    const cands = [[9, 3, 'start'], [-9, 3, 'end'], [0, -9, 'middle'], [0, 15, 'middle'], [8, -6, 'start'], [8, 12, 'start'],
      [-8, -6, 'end'], [-8, 12, 'end'], [14, 3, 'start'], [-14, 3, 'end'], [0, -17, 'middle'], [0, 23, 'middle']];
    let best = null, bestScore = Infinity;
    cands.forEach(([dx, dy, a]) => {
      const tx = p.x + dx, ty = p.y + dy;
      const x0 = a === 'start' ? tx : a === 'end' ? tx - w : tx - w / 2;
      const b = { x0, x1: x0 + w, y0: ty - h + 1, y1: ty + 2 };
      let score = 0;
      boxes.forEach(o => { if (hit(b, o)) score += 10; });
      dotsBox.forEach((o, i) => { if (pts[i] !== p && hit(b, o)) score += 10; });
      if (b.x0 < 2 || b.x1 > 218 || b.y0 < 2 || b.y1 > 198) score += 5;
      if (score < bestScore) { bestScore = score; best = { tx, ty, a, b }; }
    });
    boxes.push(best.b);
    return best;
  };
  const marks = pts.map(p => {
    const L = place(p);
    return `<a href="#/party/${escapeAttr(p.k)}" data-k="p-${escapeAttr(p.k)}" data-ntip="${escapeAttr(pName(p.k))}"><circle cx="${escapeAttr(p.x.toFixed(0))}" cy="${escapeAttr(p.y.toFixed(0))}" r="6" fill="${escapeAttr(pColor(p.k))}"/>` +
      `<text x="${escapeAttr(L.tx.toFixed(0))}" y="${escapeAttr(L.ty.toFixed(0))}" text-anchor="${escapeAttr(L.a)}" class="n-sl">${escapeAttr(p.label)}</text></a>`;
  }).join('');
  const you = opts.you
    ? `<g class="n-you"><circle cx="${escapeAttr(X(opts.you.x).toFixed(1))}" cy="${escapeAttr(Y(opts.you.y).toFixed(1))}" r="7" fill="#161616" stroke="#fff" stroke-width="2"/>` +
      `<text x="${escapeAttr(X(opts.you.x).toFixed(1))}" y="${escapeAttr((Y(opts.you.y) - 11).toFixed(1))}" text-anchor="middle" class="n-sl n-you-l">${escapeAttr(t('profile.you'))}</text></g>`
    : '';
  return `<svg class="n-chart n-spec${escapeAttr(opts.big ? ' big' : '')}" viewBox="0 0 220 200" role="group" aria-label="${escapeAttr(opts.aria || t('spec.title'))}"><line x1="110" y1="14" x2="110" y2="186" class="n-ax"/><line x1="14" y1="100" x2="206" y2="100" class="n-ax"/>` +
    `<text x="16" y="96" class="n-al">${escapeAttr(t('spec.axisLeft'))}</text><text x="204" y="96" class="n-al" text-anchor="end">${escapeAttr(t('spec.axisRight'))}</text>` +
    `<text x="114" y="20" class="n-al">${escapeAttr(t('spec.axisTop'))}</text><text x="114" y="194" class="n-al">${escapeAttr(t('spec.axisBottom'))}</text>` + marks + you + '</svg>';
}

/* Canton initials for the big map. The stylised shapes overlap in a few places
   (Basel, Appenzell), so labels are placed largest canton first; a label that
   would collide moves to the nearest free spot and gets a thin leader line. */
function cantonLabels() {
  const area = d => {
    const n = (d.match(/-?\d+(\.\d+)?/g) || []).map(Number);
    let a = 0;
    for (let i = 0; i + 3 < n.length + 2; i += 2) { const j = (i + 2) % n.length; a += n[i] * n[j + 1] - n[j] * n[i + 1]; }
    return Math.abs(a / 2);
  };
  const codes = Object.keys(MAP_PATHS).filter(c => MAP_PATHS[c].c).sort((a, b) => area(MAP_PATHS[b].d) - area(MAP_PATHS[a].d));
  const placed = [];
  const hit = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
  const offsets = [[0, 0], [0, -14], [0, 14], [18, 0], [-18, 0], [18, -12], [-18, -12], [18, 12], [-18, 12], [0, -26], [0, 26], [30, 0], [-30, 0]];
  return codes.map(c => {
    const [cx, cy] = MAP_PATHS[c].c;
    let pos = offsets[0], box = null;
    for (const o of offsets) {
      const b = { x0: cx + o[0] - 10, x1: cx + o[0] + 10, y0: cy + o[1] - 7, y1: cy + o[1] + 6 };
      if (!placed.some(p => hit(b, p))) { pos = o; box = b; break; }
    }
    if (!box) box = { x0: cx - 10, x1: cx + 10, y0: cy - 7, y1: cy + 6 };
    placed.push(box);
    const tx = cx + pos[0], ty = cy + pos[1];
    const lead = (pos[0] || pos[1]) ? `<line class="n-ml-l" x1="${escapeAttr(cx)}" y1="${escapeAttr(cy)}" x2="${escapeAttr(tx)}" y2="${escapeAttr(ty - 3)}"/>` : '';
    return lead + `<text class="n-ml" data-c="${escapeAttr(c)}" x="${escapeAttr(tx)}" y="${escapeAttr(ty + 4)}" text-anchor="middle">${escapeAttr(c)}</text>`;
  }).join('');
}

let boundsCache = null;
function mapBounds() {
  if (boundsCache) return boundsCache;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  Object.values(MAP_PATHS).forEach(p => {
    const n = (p.d.match(/-?\d+(\.\d+)?/g) || []).map(Number);
    for (let i = 0; i + 1 < n.length; i += 2) { x0 = Math.min(x0, n[i]); x1 = Math.max(x1, n[i]); y0 = Math.min(y0, n[i + 1]); y1 = Math.max(y1, n[i + 1]); }
  });
  boundsCache = `${x0 - 5} ${y0 - 5} ${x1 - x0 + 10} ${y1 - y0 + 10}`;
  return boundsCache;
}

const EXPLAINERS = [
  ['init.label', 'directDemocracy'], ['type.initiative', 'initiative'], ['type.referendum', 'referendum'],
  ['news.ex.doubleMajority', 'doubleMajority'], ['news.ex.parole', 'parole'], ['news.ex.stimmfreigabe', 'stimmfreigabe'],
  ['status.collecting', 'collecting'], ['parl.label', 'federalAssembly'], ['parl.nc', 'nationalCouncil'],
  ['parl.cs', 'councilOfStates'], ['council.title', 'federalCouncil'], ['news.ex.president', 'president'],
  ['nav.sessions', 'session'], ['session.votesTitle', 'finalVote'], ['nav.cantons', 'canton'],
];

/* ---- render + behaviour ---- */
let homeToken = 0;
export async function renderNewsHome() {
  const host = document.getElementById('home-news');
  if (!host) return;
  const token = ++homeToken;
  const idx = await C.ensureSessionsIndex();
  await C.ensureSessionTranslations();
  sessionsCache = (idx && idx.sessions) || [];
  const d = isoToday();
  const last = sessionsCache.find(s => s.voteCount > 0 && s.end <= d) || sessionsCache.find(s => s.voteCount > 0) || null;
  const nb = nextBallot();
  const links = SETTINGS().parliamentLinks || {};
  const want = new Set();
  if (last) want.add(last.id);
  if (nb) nb.items.forEach(i => { if (links[i.id]) want.add(links[i.id].session); });
  const files = {};
  await Promise.all([...want].map(id => C.ensureSessionFile(id).then(f => { files[id] = f; })));
  if (token !== homeToken) return;          // a newer render (e.g. language change) took over

  const left = leftBlocks(files, last), centre = stories(nb, files), right = rightBlocks();
  host.innerHTML = '<div class="n-wrap"><div class="n-flow" id="n-flow"><div class="n-band"><div class="n-col n-col-l">' + left.join('') +
    '</div><div class="n-col n-col-c">' + centre.join('') + '</div><div class="n-col n-col-r">' + right.join('') + '</div></div></div></div>';
  wireHighlights(host);
  wireRows(host);
  startRotators();
  layout();
  if (!layoutWired) {
    layoutWired = true;
    let tmr; window.addEventListener('resize', () => { clearTimeout(tmr); tmr = setTimeout(layout, 120); });
    if (document.fonts) document.fonts.ready.then(layout);
  }
}

// Hovering (or focusing) anything with data-k lights up everything in the same
// section that shares its first key; the rest dims — as on the 1.0 charts.
function wireHighlights(root) {
  root.querySelectorAll('[data-hl]').forEach(scope => {
    const on = key => {
      scope.classList.add('is-dim');
      scope.querySelectorAll('[data-k]').forEach(el => el.classList.toggle('hl', el.dataset.k.split(' ').includes(key)));
    };
    const off = () => { scope.classList.remove('is-dim'); scope.querySelectorAll('[data-k].hl').forEach(el => el.classList.remove('hl')); };
    const from = e => { const el = e.target.closest('[data-k]'); if (el && scope.contains(el)) on(el.dataset.k.split(' ')[0]); else off(); };
    scope.addEventListener('pointerover', from);
    scope.addEventListener('focusin', from);
    scope.addEventListener('pointerleave', off);
    scope.addEventListener('focusout', off);
  });
}

// A whole list row opens its page, like the title link inside it.
function wireRows(root) {
  root.addEventListener('click', (e) => {
    const row = e.target.closest('.n-row[data-href]');
    if (!row || e.target.closest('a, button, [tabindex]')) return;
    location.hash = row.dataset.href;
  });
}

function wireTooltips() {
  const tip = document.createElement('div');
  tip.id = 'n-tip'; tip.setAttribute('role', 'tooltip');
  document.body.appendChild(tip);
  const show = (el, x, y) => {
    tip.textContent = el.dataset.ntip; tip.classList.add('on');
    tip.style.left = Math.min(x + 14, window.innerWidth - tip.offsetWidth - 8) + 'px';
    tip.style.top = (y + 16) + 'px';
  };
  document.addEventListener('pointermove', (e) => {
    const el = e.target.closest && e.target.closest('[data-ntip]');
    if (el) show(el, e.clientX, e.clientY); else tip.classList.remove('on');
  });
  document.addEventListener('focusin', (e) => {
    const el = e.target.closest && e.target.closest('[data-ntip]');
    if (el) { const r = el.getBoundingClientRect(); show(el, r.left, r.bottom - 8); } else tip.classList.remove('on');
  });
  window.addEventListener('scroll', () => tip.classList.remove('on'), { passive: true });
}

/* Flowing columns. The centre column is the anchor: it always keeps its own
   place and width, so a story and its graphics never jump to another column.
   A side column that is shorter simply stops. Once the centre ends, whatever
   is left of the side columns continues below it, the two sharing the full
   width (or one side alone taking all of it). */
let layoutWired = false;
function layout() {
  const flow = document.getElementById('n-flow');
  if (!flow || flow.offsetParent === null) return;           // not on screen (another page is open)
  const blocks = { l: [], c: [], r: [] };
  flow.querySelectorAll('.n-col').forEach(col => {
    const k = col.classList.contains('n-col-l') ? 'l' : col.classList.contains('n-col-c') ? 'c' : 'r';
    blocks[k].push(...col.children);
  });
  const lay = SETTINGS().layout || {};
  const W = { l: Number(lay.left) || 1, c: Number(lay.centre) || 2, r: Number(lay.right) || 1 };
  flow.innerHTML = '';
  // In the three-column band no column may get narrower than its graphics need
  // (sides 170 px, centre 380 px of content), whatever the admin sliders say.
  const MIN = { l: 'calc(170px + var(--n-gutter))', c: 'calc(380px + 2 * var(--n-gutter))', r: 'calc(170px + var(--n-gutter))' };
  const makeBand = (keys, weights) => {
    const band = document.createElement('div'); band.className = 'n-band';
    band.style.gridTemplateColumns = keys.map(k => `minmax(${keys.length === 3 ? MIN[k] : '0'},${weights[k]}fr)`).join(' ');
    const cols = {};
    keys.forEach(k => { const c = document.createElement('div'); c.className = 'n-col n-col-' + k; cols[k] = c; band.appendChild(c); });
    flow.appendChild(band);
    return cols;
  };
  if (window.innerWidth <= 900) {
    const cols = makeBand(['c'], { c: 1 });
    cols.c.parentElement.classList.add('one');
    ['c', 'l', 'r'].forEach(k => blocks[k].forEach(b => cols.c.appendChild(b)));
    return;
  }
  // Band 1: the three columns side by side.
  const cols = makeBand(['l', 'c', 'r'], W);
  ['l', 'c', 'r'].forEach(k => blocks[k].forEach(b => cols[k].appendChild(b)));
  const top = cols.c.parentElement.getBoundingClientRect().top;
  const lastBottom = k => { const b = cols[k].lastElementChild; return b ? b.getBoundingClientRect().bottom - top : 0; };
  const H = lastBottom('c');
  // Side blocks that start below the end of the centre move into the next band.
  const rest = { l: [], r: [] };
  ['l', 'r'].forEach(k => { rest[k] = [...cols[k].children].filter(b => b.getBoundingClientRect().top - top >= H); });
  let active = ['l', 'r'].filter(k => rest[k].length);
  while (active.length) {
    rest.l.concat(rest.r).forEach(b => b.remove());
    const band = makeBand(active, { l: W.l, r: W.r });
    active.forEach(k => { rest[k].forEach(b => band[k].appendChild(b)); band[k].classList.add('wide'); });
    if (active.length === 1) break;
    const t2 = band[active[0]].parentElement.getBoundingClientRect().top;
    const h = k => { const b = band[k].lastElementChild; return b ? b.getBoundingClientRect().bottom - t2 : 0; };
    const shortest = h('l') <= h('r') ? 'l' : 'r', other = shortest === 'l' ? 'r' : 'l';
    const H2 = h(shortest);
    rest[shortest] = [];
    rest[other] = [...band[other].children].filter(b => b.getBoundingClientRect().top - t2 >= H2);
    active = rest[other].length ? [other] : [];
  }
}
export function relayoutNews() { layout(); }

/* Rotating panels (canton spotlight, explainer) with a timer bar. Paused while
   hovered or focused; a canton clicked on the map stays until the visitor clicks
   elsewhere or scrolls the panel out of view. */
let rotators = [];
function stopRotators(group) { rotators.filter(r => r.group === group).forEach(r => r.stop()); rotators = rotators.filter(r => r.group !== group); }
function rotator(el, n, render, ms, start, group) {
  let i = start % n, t0 = 0, last = performance.now(), hover = false, focus = false, pinned = false;
  const fill = el.querySelector('.n-tbar i'), pz = el.querySelector('.n-tbar .n-pz');
  const paused = () => hover || focus || pinned;
  render(i, false);
  const id = setInterval(() => {
    const now = performance.now(), dt = now - last; last = now;
    if (document.hidden || el.offsetParent === null) return;   // tab in the background or another page open
    if (!paused()) { t0 += dt; if (t0 >= ms) { t0 = 0; i = (i + 1) % n; render(i, true); } }
    const p = Math.min(t0 / ms, 1) * 100;
    fill.style.width = p + '%'; pz.style.left = p + '%';
    el.classList.toggle('paused', paused());
  }, 40);
  el.addEventListener('pointerenter', () => { hover = true; });
  el.addEventListener('pointerleave', () => { hover = false; });
  el.addEventListener('focusin', () => { focus = true; });
  el.addEventListener('focusout', () => { focus = false; });
  const io = new IntersectionObserver(es => es.forEach(e => { if (!e.isIntersecting) { pinned = false; hover = false; } }));
  io.observe(el);
  const r = { group: group || 'home', pin(j) { i = j; t0 = 0; pinned = true; render(j, true); }, unpin() { pinned = false; }, stop() { clearInterval(id); io.disconnect(); } };
  rotators.push(r);
  return r;
}
function fade(el) { el.classList.remove('n-fade'); void el.offsetWidth; el.classList.add('n-fade'); }

let outsideWired = false, cantonRot = null;
function startRotators() {
  stopRotators('home');
  const rot = SETTINGS().rotation || {};
  const cantonMs = Math.max(4, Number(rot.canton) || 9) * 1000, explMs = Math.max(4, Number(rot.explainer) || 12) * 1000;
  const cEl = document.getElementById('n-canton');
  const cd = (D().cantonData && D().cantonData.cantons) || {};
  const codes = Object.keys(D().cantons).filter(c => cd[c] && cd[c].nc).sort();
  const dayOfYear = Math.floor((todayDate() - new Date(todayDate().getFullYear(), 0, 0)) / 864e5);
  if (cEl && codes.length) {
    cEl.querySelector('#n-c-src').textContent = tf('news.cs.src', { s: Math.round(cantonMs / 1000) });
    cantonRot = rotator(cEl, codes.length, (j, anim) => {
      const code = codes[j], nc = cd[code].nc;
      const a = cEl.querySelector('#n-c-name');
      a.textContent = C.localized(D().cantons[code].name); a.href = '#/canton/' + code;
      cEl.querySelector('#n-c-detail').href = '#/cantons/' + code;
      cEl.querySelectorAll('.n-map path').forEach(p => p.classList.toggle('on', p.dataset.c === code));
      cEl.querySelector('#n-c-meta').textContent = tf(nc.totalSeats === 1 ? 'news.cs.meta1' : 'news.cs.meta', { year: nc.year, n: nc.totalSeats });
      const ps = (nc.parties || []).filter(p => p.strength);
      cEl.querySelector('#n-c-bar').innerHTML = ps.map(p => `<span data-k="c-${escapeAttr(p.key)}" data-ntip="${escapeAttr(C.localized(p.name) + ' · ' + num(p.strength) + '%')}" style="flex:${escapeAttr(p.strength)};background:${escapeAttr(pColor(p.key))}"></span>`).join('');
      cEl.querySelector('#n-c-leg').innerHTML = ps.slice(0, 5).map(p => `<li data-k="c-${escapeAttr(p.key)}"><i style="background:${escapeAttr(pColor(p.key))}"></i>${escapeAttr(C.localized(p.name))}<span>${escapeAttr(num(p.strength))}%</span></li>`).join('');
      if (anim) ['#n-c-name', '#n-c-meta', '#n-c-bar', '#n-c-leg'].forEach(s => fade(cEl.querySelector(s)));
    }, cantonMs, dayOfYear);
    cEl.querySelectorAll('.n-map path').forEach(p => {
      const pick = (e) => { e.stopPropagation(); const j = codes.indexOf(p.dataset.c); if (j >= 0) cantonRot.pin(j); };
      p.addEventListener('click', pick);
      p.addEventListener('dblclick', () => { location.hash = '#/canton/' + p.dataset.c; });
      p.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(e); } });
    });
    if (!outsideWired) {
      outsideWired = true;
      document.addEventListener('click', (e) => { const el = document.getElementById('n-canton'); if (cantonRot && el && !el.contains(e.target)) cantonRot.unpin(); });
    }
  }
  const eEl = document.getElementById('n-expl');
  if (eEl) {
    rotator(eEl, EXPLAINERS.length, (j, anim) => {
      eEl.querySelector('#n-e-title').textContent = t(EXPLAINERS[j][0]);
      eEl.querySelector('#n-e-body').textContent = t('gloss.' + EXPLAINERS[j][1]);
      eEl.querySelector('#n-e-count').textContent = tf('news.ex.count', { i: j + 1, n: EXPLAINERS.length, s: Math.round(explMs / 1000) });
      if (anim) ['#n-e-title', '#n-e-body'].forEach(s => fade(eEl.querySelector(s)));
    }, explMs, dayOfYear);
  }
}

/* ============================================================
   Canton spotlight page (#/cantons/<code>): the spotlight graphic in big,
   with the facts and the full 2023 National Council result of the canton
   on show. Same rotation and pausing as on the front page; a click keeps a
   canton, a double click opens its canton page.
   ============================================================ */
let spotRot = null, spotOutsideWired = false;
export function renderSpotlightPage(startCode) {
  const host = document.getElementById('spotlight-content');
  if (!host) return;
  stopRotators('spot');
  const cd = (D().cantonData && D().cantonData.cantons) || {};
  const codes = Object.keys(D().cantons).filter(c => cd[c] && cd[c].nc).sort();
  if (!codes.length) { host.textContent = ''; return; }
  const rot = SETTINGS().rotation || {};
  const ms = Math.max(4, Number(rot.canton) || 9) * 1000;
  let start = codes.indexOf(String(startCode || '').toUpperCase());
  if (start < 0) start = Math.floor((todayDate() - new Date(todayDate().getFullYear(), 0, 0)) / 864e5) % codes.length;

  host.innerHTML = '<div class="n-spot n-rot" id="n-spot" data-hl>' +
    `<div class="n-spot-map"><svg class="n-chart n-map" viewBox="${escapeAttr(mapBounds())}" role="group" aria-label="${escapeAttr(t('nav.cantons'))}">` +
    Object.keys(MAP_PATHS).map(c => `<path d="${escapeAttr(MAP_PATHS[c].d)}" data-c="${escapeAttr(c)}" data-ntip="${escapeAttr(C.localized(D().cantons[c]?.name) || c)}" tabindex="0" role="button" aria-label="${escapeAttr(C.localized(D().cantons[c]?.name) || c)}"/>`).join('') +
    cantonLabels() +
    `</svg><p class="n-src">${escapeAttr(t('news.cs.hint'))}</p></div>` +
    `<div class="n-spot-side"><div class="n-k">${escapeAttr(t('news.cs.k'))}</div><div class="n-tbar" aria-hidden="true"><i></i><b class="n-pz"></b></div>` +
    '<h2 class="n-spot-name"><a id="s-name" href="#/"></a></h2><p class="n-meta" id="s-sub"></p><dl class="n-facts" id="s-facts"></dl>' +
    '<h3 class="n-mh" id="s-nch"></h3><div class="n-bar tall" id="s-bar"></div><table class="n-ptable" id="s-table"></table>' +
    `<a class="n-more" id="s-more" href="#/">${escapeAttr(t('news.cs.more'))}</a><p class="n-src" id="s-src"></p></div></div>`;
  wireHighlights(host);
  const el = document.getElementById('n-spot');
  const sign = d => (d > 0 ? '▲ ' : d < 0 ? '▼ ' : '– ') + num(Math.abs(d));
  spotRot = rotator(el, codes.length, (j, anim) => {
    const code = codes[j], c = D().cantons[code], data = cd[code], nc = data.nc;
    const name = C.localized(c.name);
    const a = el.querySelector('#s-name'); a.textContent = name; a.href = '#/canton/' + code;
    el.querySelector('#s-more').href = '#/canton/' + code;
    el.querySelectorAll('.n-map path, .n-map .n-ml').forEach(p => p.classList.toggle('on', p.dataset.c === code));
    el.querySelector('#s-sub').textContent = t('canton.capital') + ': ' + C.localized(c.capital);
    const facts = [
      [t('canton.stat.pop'), C.formatInt(c.pop)],
      [t('canton.stat.area'), C.formatInt(c.area) + ' km²'],
      [t('canton.stat.lang'), C.localized(c.language)],
      [t('canton.stat.joined'), c.joined],
      [t('canton.stat.seats'), nc.totalSeats],
      [t('canton.municipalities'), data.districts ? tf('canton.muni.summary', { m: data.municipalities, d: data.districts }) : tf('canton.muni.single', { m: data.municipalities })],
    ].filter(f => f[1] !== undefined && f[1] !== null && f[1] !== '');
    el.querySelector('#s-facts').innerHTML = facts.map(([k, v]) => `<div><dt>${escapeAttr(k)}</dt><dd>${escapeAttr(v)}</dd></div>`).join('');
    el.querySelector('#s-nch').textContent = tf(nc.totalSeats === 1 ? 'news.cs.meta1' : 'news.cs.meta', { year: nc.year, n: nc.totalSeats });
    const ps = (nc.parties || []).filter(p => p.strength).sort((x, y) => y.strength - x.strength);
    el.querySelector('#s-bar').innerHTML = ps.map(p => `<span data-k="c-${escapeAttr(p.key)}" data-ntip="${escapeAttr(C.localized(p.name) + ' · ' + num(p.strength) + '%')}" style="flex:${escapeAttr(p.strength)};background:${escapeAttr(pColor(p.key))}"></span>`).join('');
    el.querySelector('#s-table').innerHTML =
      `<tr><th>${escapeAttr(t('canton.nc.party'))}</th><th>${escapeAttr(t('canton.nc.share'))}</th><th>${escapeAttr(t('canton.nc.seats'))}</th><th>${escapeAttr(tf('canton.nc.change', { year: nc.year - 4 }))}</th></tr>` +
      ps.map(p => `<tr data-k="c-${escapeAttr(p.key)}" tabindex="0"><td><i style="background:${escapeAttr(pColor(p.key))}"></i>${escapeAttr(C.localized(p.name))}</td><td>${escapeAttr(num(p.strength))}%</td><td>${escapeAttr(p.seats || 0)}</td>` +
        `<td class="${escapeAttr(p.delta > 0 ? 'up' : p.delta < 0 ? 'down' : '')}">${escapeAttr(p.delta == null ? '' : sign(p.delta))}</td></tr>`).join('');
    el.querySelector('#s-src').textContent = t('share.src.canton');
    if (anim) ['#s-name', '#s-sub', '#s-facts', '#s-bar', '#s-table'].forEach(q => fade(el.querySelector(q)));
    if (location.hash.startsWith('#/cantons')) { try { history.replaceState(history.state, '', '#/cantons/' + code); } catch (e) { /* ignore */ } }
  }, ms, start, 'spot');
  el.querySelectorAll('.n-map path').forEach(p => {
    const pick = (e) => { e.stopPropagation(); const j = codes.indexOf(p.dataset.c); if (j >= 0) spotRot.pin(j); };
    p.addEventListener('click', pick);
    p.addEventListener('dblclick', () => { location.hash = '#/canton/' + p.dataset.c; });
    p.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(e); } });
  });
  if (!spotOutsideWired) {
    spotOutsideWired = true;
    document.addEventListener('click', (e) => { const s = document.getElementById('n-spot'); if (spotRot && s && !s.contains(e.target)) spotRot.unpin(); });
  }
}

/* ============================================================
   Parliament and parties (#/assembly/<section>): the four graphics of the
   front page's right column in big, with the figures behind them.
   Reached from "See in detail" and from the Parliament / Parties menus.
   ============================================================ */
export function renderAssemblyPage(section) {
  const host = document.getElementById('assembly-content');
  if (!host) return;
  const order = partyOrder();
  const seatRows = (key, total) => partiesBySeats().filter(k => party(k)[key]).map(k =>
    `<tr data-k="p-${escapeAttr(k)}"><td><i style="background:${escapeAttr(pColor(k))}"></i><a href="#/party/${escapeAttr(k)}">${escapeAttr(pName(k))}</a></td>` +
    `<td>${escapeAttr(pShort(k))}</td><td>${escapeAttr(party(k)[key])}</td><td>${escapeAttr(num(party(k)[key] / total * 100))}%</td></tr>`).join('');
  const seatTable = (key, total) => `<table class="n-ptable"><tr><th>${escapeAttr(t('canton.nc.party'))}</th><th></th><th>${escapeAttr(t('canton.nc.seats'))}</th><th>${escapeAttr(t('news.asm.seatShare'))}</th></tr>` + seatRows(key, total) + '</table>';
  const leg = (key) => legend(order.filter(k => party(k)[key]).map(k => ['p-' + k, pColor(k), pShort(k) + ' ' + party(k)[key], '#/party/' + k]));

  const members = (D().council && D().council.members) || [];
  const year = (D().council && D().council._meta && D().council._meta.presidencyYear) || '';
  const arc = members.map((m, n) => [m, n]).sort((a, b) => (party(a[0].party)?.spectrum?.x ?? 50) - (party(b[0].party)?.spectrum?.x ?? 50));
  const counts = {};
  members.forEach(m => { counts[m.party] = (counts[m.party] || 0) + 1; });
  const role = m => m.role === 'president' ? tf('council.president', { year }) : m.role === 'vice' ? tf('council.vice', { year }) : '';

  const sectionHTML = (id, kicker, title, graphic, side) =>
    `<section class="n-asm" id="asm-${escapeAttr(id)}" data-hl><div class="n-asm-g"><div class="n-k">${escapeAttr(kicker)}</div><h2 class="n-asm-h">${escapeAttr(title)}</h2>` + graphic + '</div><div class="n-asm-side">' + side + '</div></section>';

  host.innerHTML =
    sectionHTML('spectrum', t('nav.parties'), t('spec.title'), spectrumSVG({ big: true }),
      `<p class="n-body">${escapeAttr(t('spec.desc'))}</p><p class="n-src">${escapeAttr(t('news.sp.src'))} · <a href="#/page/methodology">${escapeAttr(t('footer.method'))}</a></p>` +
      `<table class="n-ptable"><tr><th>${escapeAttr(t('canton.nc.party'))}</th><th>${escapeAttr(t('parl.nc'))}</th><th>${escapeAttr(t('parl.cs'))}</th></tr>` +
      partiesBySeats().map(k => `<tr data-k="p-${escapeAttr(k)}"><td><i style="background:${escapeAttr(pColor(k))}"></i><a href="#/party/${escapeAttr(k)}">${escapeAttr(pName(k))}</a></td><td>${escapeAttr(party(k).ncSeats || 0)}</td><td>${escapeAttr(party(k).csSeats || 0)}</td></tr>`).join('') + '</table>') +
    sectionHTML('nc', t('parl.label'), t('parl.nc') + ' · ' + tf('news.seats', { n: 200 }),
      hemicycle(chamberDots('ncSeats', t('parl.nc')), 8, t('parl.nc')) + leg('ncSeats'),
      `<p class="n-body">${escapeAttr(t('gloss.nationalCouncil'))}</p>` + seatTable('ncSeats', 200) + `<p class="n-src">${escapeAttr(t('share.src.parliament'))}</p>`) +
    sectionHTML('cs', t('parl.label'), t('parl.cs') + ' · ' + tf('news.seats', { n: 46 }),
      hemicycle(chamberDots('csSeats', t('parl.cs')), 4, t('parl.cs')) + leg('csSeats'),
      `<p class="n-body">${escapeAttr(t('gloss.councilOfStates'))}</p>` + seatTable('csSeats', 46) + `<p class="n-src">${escapeAttr(t('share.src.parliament'))}</p>`) +
    sectionHTML('fc', t('council.label'), t('council.title'),
      '<div class="n-asm-fc">' + hemicycle(arc.map(([m, n]) => ({ fill: pColor(m.party), k: `m-${n} p-${m.party}`, tip: m.name + ' · ' + pShort(m.party) })), 1, t('council.title')) + '</div>' +
      legend(order.filter(k => counts[k]).map(k => ['p-' + k, pColor(k), pShort(k) + ' ' + counts[k], '#/party/' + k])),
      `<p class="n-body">${escapeAttr(t('gloss.federalCouncil'))}</p><ul class="n-plain">` +
      members.map((m, n) => `<li data-k="m-${escapeAttr(n)} p-${escapeAttr(m.party)}" tabindex="0"><i style="background:${escapeAttr(pColor(m.party))}"></i>${escapeAttr(m.name)}` +
        `<span>${escapeAttr([pShort(m.party), role(m), m.since ? tf('council.since', { year: m.since }) : ''].filter(Boolean).join(' · '))}</span></li>`).join('') +
      `</ul><p class="n-body n-mt">${escapeAttr(t('gloss.president'))}</p><p class="n-src">${escapeAttr(t('council.source'))}</p>`);
  wireHighlights(host);
  const target = document.getElementById('asm-' + (['spectrum', 'nc', 'cs', 'fc'].includes(section) ? section : 'spectrum'));
  if (target && section) setTimeout(() => target.scrollIntoView({ block: 'start' }), 80);
}

/* ============================================================
   My profile in the 1.1 look: the same on-device calculation as before
   (computeMyLeaning in app.js), nothing leaves the device.
   ============================================================ */
export function renderNewsProfile() {
  const el = document.getElementById('profile-content');
  if (!el) return;
  const d = C.computeMyLeaning();
  const min = C.profileMin;
  if (!d.count) {
    el.innerHTML = `<div class="n-prof"><p class="n-lead">${escapeAttr(t('profile.empty'))}</p>` +
      `<p class="n-meta">${escapeAttr(tf('profile.graphNeedMore', { min, n: 0 }))}</p>` +
      `<p><a class="n-more" href="#/sessions">${escapeAttr(t('profile.emptySessions'))} →</a> &nbsp; <a class="n-more" href="#/ballots/upcoming">${escapeAttr(t('profile.emptyVotes'))} →</a></p></div>`;
    return;
  }
  const closest = d.partyRanking[0];
  const ready = d.sessN >= min;
  const stat = (n, label) => `<div><b>${escapeAttr(n)}</b><span>${escapeAttr(label)}</span></div>`;
  const align = d.partyRanking.length
    ? '<ul class="n-hbars">' + d.partyRanking.map(r => `<li><a href="#/party/${escapeAttr(r.key)}" data-k="p-${escapeAttr(r.key)}" data-ntip="${escapeAttr(pName(r.key) + ' · ' + r.pct + '%')}"><span class="n">${escapeAttr(pShort(r.key))}</span>` +
      `<span class="b"><i style="width:${escapeAttr(r.pct)}%;background:${escapeAttr(pColor(r.key))}"></i></span><span class="v">${escapeAttr(r.pct)}%</span></a></li>`).join('') + '</ul>'
    : `<p class="n-meta">${escapeAttr(t('profile.alignNeedMore'))}</p>`;
  const charts = ready
    ? '<div class="n-prof-grid">' +
      `<section class="n-mod" data-hl><div class="n-k">${escapeAttr(t('profile.alignTitle'))}</div>` +
      (closest ? `<h3 class="n-mh">${escapeAttr(tf('profile.closest', { party: pShort(closest.key), pct: closest.pct }))}</h3>` : '') +
      `<p class="n-meta">${escapeAttr(t('profile.alignNote'))}</p>` + align + '</section>' +
      `<section class="n-mod" data-hl><div class="n-k">${escapeAttr(t('profile.spectrumTitle'))}</div>` + spectrumSVG({ you: d.point, aria: t('profile.spectrumAria') }) +
      `<p class="n-meta">${escapeAttr(t(d.point ? 'profile.spectrumDesc' : 'profile.spectrumNeedMore'))}</p></section></div>`
    : `<section class="n-mod"><div class="n-k">${escapeAttr(t('profile.alignTitle'))}</div><p class="n-meta">${escapeAttr(tf('profile.graphNeedMore', { min, n: d.sessN }))}</p>` +
      `<a class="n-more" href="#/sessions">${escapeAttr(t('profile.enrichBrowse'))} →</a></section>`;
  const topics = d.topics.length
    ? '<ul class="n-plain">' + d.topics.map(x => `<li>${escapeAttr(t('session.topic.' + x.k))}<span>${escapeAttr(x.n)}</span></li>`).join('') + '</ul>'
    : `<p class="n-meta">${escapeAttr(t('profile.topicsEmpty'))}</p>`;
  el.innerHTML = `<div class="n-prof"><p class="n-lead">${escapeAttr(t('profile.lead'))}</p><p class="n-meta">${escapeAttr(t('profile.privacyNote'))}</p>` +
    '<div class="n-stats">' + stat(d.count, t('profile.statTotal')) + stat(d.sessN, t('profile.statSessions')) + stat(d.yesN + ' / ' + d.noN, t('profile.statYesNo')) + stat(d.initN, t('profile.statInitiatives')) + '</div>' +
    charts +
    `<section class="n-mod"><div class="n-k">${escapeAttr(t('profile.priorTitle'))}</div><p class="n-meta">${escapeAttr(t('profile.priorDesc'))}</p>` + topics + '</section>' +
    `<section class="n-mod"><div class="n-k">${escapeAttr(t('profile.enrichTitle'))}</div><p class="n-meta">${escapeAttr(t('profile.enrichDesc'))} <a href="#/sessions">${escapeAttr(t('profile.enrichBrowse'))} →</a></p>` +
    '<div class="enrich-list" id="profile-enrich"></div></section></div>';
  wireHighlights(el);
  C.wireVoteWidgets(el);
  C.fillProfileEnrich();
}
