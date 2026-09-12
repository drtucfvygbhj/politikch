import { MAP_PATHS } from './map-data.js';
import { configureShare, wireShares, mountShare } from './share.js';

/* ============================================================
   State
   ============================================================ */
const state = {
  lang: 'en',
  data: { parties: {}, cantons: {}, initiatives: [], i18n: {}, financing: { parties: {}, initiatives: {} } },
  tab: 'upcoming',
  partyTab: 'upcoming',
  search: ''
};

// Which vote statuses belong to each lifecycle tab, in process (chronological)
// order. The data file is already ordered so that filtering preserves the
// intended within-tab order (upcoming soonest-first, collecting by nearest
// deadline, decided newest-first).
const TAB_STATUSES = {
  collecting: ['collecting'],
  pending: ['pending'],
  upcoming: ['upcoming'],
  decided: ['adopted', 'rejected']
};
// Tabs whose items carry a real ballot date are grouped under a date heading.
const GROUPED_TABS = new Set(['upcoming', 'decided']);

const SUPPORTED_LANGS = ['en', 'de', 'fr', 'it', 'rm'];

/* ============================================================
   Icons — a small set of line symbols drawn in the site's own
   colour (currentColor), replacing decorative emoji so every
   glyph follows one monochrome, on-brand scheme.
   ============================================================ */
const ICONS = {
  pen: '<path d="M4 20l4-1L19 8l-3-3L5 16z"/><path d="M14 7l3 3"/>',
  institution: '<path d="M3 21h18"/><path d="M4 10l8-6 8 6"/><path d="M6 10v9M10 10v9M14 10v9M18 10v9"/>',
  calendar: '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 9.5h16M8 3v4M16 3v4"/>',
  ballot: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 12l3 3 5-6"/>',
  coins: '<circle cx="12" cy="12" r="8"/><path d="M9.5 8.5h4.5M9.5 12h3.5M11.2 8.5v7"/>',
  buildings: '<path d="M3 21h18"/><path d="M5 21V9h6v12"/><path d="M11 21V4h8v17"/><path d="M14 8h2M14 12h2M14 16h2"/>',
  spring: '<path d="M12 21v-8"/><path d="M12 13c0-3-2-5-5.5-5 0 3.3 2.2 5 5.5 5z"/><path d="M12 11c0-3 2-5 5.5-5 0 3.3-2.2 5-5.5 5z"/>',
  summer: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8"/>',
  autumn: '<path d="M5 19c8 1.5 14-4.5 14-14C10 6.5 4 12 5 19z"/><path d="M6 18l6.5-6.5"/>',
  winter: '<path d="M12 2v20M3.3 7l17.4 10M20.7 7L3.3 17"/><path d="M12 6l-2.2-2.2M12 6l2.2-2.2M12 18l-2.2 2.2M12 18l2.2 2.2"/>',
  star: '<path d="M12 3l2.5 5.6L20 9.3l-4 4 1 5.7-5-2.8-5 2.8 1-5.7-4-4 5.5-.7z"/>',
  hemicycle: '<path d="M3 18a9 9 0 0118 0"/><circle cx="6.5" cy="13.5" r="1.1"/><circle cx="12" cy="11" r="1.1"/><circle cx="17.5" cy="13.5" r="1.1"/>',
  chamberCS: '<path d="M5 18a7 7 0 0114 0"/><circle cx="9" cy="13" r="1.1"/><circle cx="15" cy="13" r="1.1"/>',
  chamberUFA: '<path d="M3 15a9 9 0 0118 0"/><path d="M6.5 18a5.5 5.5 0 0111 0"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
  scale: '<path d="M12 3v16M6 19h12"/><path d="M6 6l-3 6h6zM18 6l-3 6h6z"/><path d="M6 6h12"/>',
};
function icon(name, cls) {
  return `<svg class="icon${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ''}</svg>`;
}
const SEASON_ICON = { spring: 'spring', summer: 'summer', autumn: 'autumn', winter: 'winter', special: 'star' };

/* ============================================================
   Data loading
   ============================================================ */
async function loadData() {
  const [parties, cantons, initiatives, council, i18n] = await Promise.all([
    fetch('data/parties.json').then(r => r.json()),
    fetch('data/cantons.json').then(r => r.json()),
    fetch('data/initiatives.json').then(r => r.json()),
    fetch('data/council.json').then(r => r.json()),
    fetch('data/i18n.json').then(r => r.json())
  ]);
  state.data.parties = parties.parties;
  state.data.cantons = cantons.cantons;
  state.data.initiatives = initiatives.initiatives;
  state.data.council = council;
  state.data.i18n = i18n;

  // Optional: fetched at build time from the official EFK register (see
  // scripts/fetch_financing.py). Missing file or fetch failure just means
  // no live figures yet — pages fall back to the "see official register" copy.
  try {
    const financing = await fetch('data/financing.json').then(r => r.ok ? r.json() : null);
    if (financing) state.data.financing = financing;
  } catch (e) { /* keep the empty default; placeholders will show */ }

  // Optional: per-canton facts fetched at build time from official BFS
  // open data (see scripts/fetch_cantons.py). Missing/failed just means the
  // canton sections keep their "data coming from …" placeholders.
  try {
    const cantonData = await fetch('data/canton-data.json').then(r => r.ok ? r.json() : null);
    if (cantonData) state.data.cantonData = cantonData;
  } catch (e) { /* keep placeholders */ }

  // Optional: unofficial English titles for initiatives whose official name is
  // only registered in a national language (data/initiatives-translations.json).
  try {
    const it = await fetch('data/initiatives-translations.json').then(r => r.ok ? r.json() : null);
    state.data.initTrans = (it && it.titles) || {};
  } catch (e) { state.data.initTrans = {}; }

  // Optional: editorial descriptions + name-variant aliases for organisation
  // donors (data/donor-descriptions.json). Missing just means donor pages show
  // a neutral factual note and variant spellings aren't merged.
  try {
    const di = await fetch('data/donor-descriptions.json').then(r => r.ok ? r.json() : null);
    state.data.donorInfo = di || { donors: {} };
  } catch (e) { state.data.donorInfo = { donors: {} }; }
}

/* ============================================================
   i18n helpers
   ============================================================ */
function t(key) {
  const dict = state.data.i18n[state.lang] || state.data.i18n.en || {};
  return dict[key] ?? state.data.i18n.en?.[key] ?? key;
}
function localized(obj) {
  if (!obj) return '';
  return obj[state.lang] || obj.en || Object.values(obj)[0] || '';
}

/* ============================================================
   Share specs — build the link-agnostic descriptions the share
   module (js/share.js) redraws onto a branded canvas. Built lazily
   at click time so the current language and live data are used.
   ============================================================ */
const SHARE_CTX = () => ({ origin: location.origin });

// Party seats as ordered legend/seat data (left→right by spectrum position, as
// the on-page hemicycles are ordered). Used for chamber and delegation charts.
function seatSpecFromSeats(seatData) {
  return Object.entries(seatData)
    .filter(([, n]) => n > 0)
    .sort((a, b) => (state.data.parties[a[0]]?.spectrum?.x ?? 50) - (state.data.parties[b[0]]?.spectrum?.x ?? 50))
    .map(([k, n]) => ({ label: state.data.parties[k]?.abbr || k, color: state.data.parties[k]?.color || '#999', seats: n }));
}
// Home-page chamber seat totals derived live from the party data.
function chamberSeats(which) {
  const key = which === 'nc' ? 'ncSeats' : 'csSeats';
  const o = {};
  Object.entries(state.data.parties).forEach(([k, p]) => { if (p[key]) o[k] = p[key]; });
  return o;
}
// Pie share spec from aggregated donor slices ({slug,name,amount}). tailSum is
// the merged "other donors" remainder, if any.
function pieSpecFromDonors(agg, title, route, totalLabel) {
  const slices = agg.slice(0, FIN_MAX_SLICES).map((d, i) => ({
    label: d.name, value: d.amount, valueText: formatCHF(d.amount), color: finColor(i),
  }));
  const tail = agg.slice(FIN_MAX_SLICES).reduce((s, d) => s + d.amount, 0);
  if (tail > 0) slices.push({ label: t('financing.moreDonors'), value: tail, valueText: formatCHF(tail), color: FIN_OTHER_COLOR });
  const total = agg.reduce((s, d) => s + d.amount, 0);
  const tl = totalLabel || t('financing.total');
  return {
    kind: 'pie', title, route, subtitle: `${tl} · ${formatCHF(total)}`,
    slices, totalText: formatCHF(total), totalLabel: tl,
  };
}
// Two-axis spectrum spec from the party set (+ optional endorser highlighting
// and coalition midpoint, matching voteScaleHTML).
function spectrumSpec(title, route, opts) {
  opts = opts || {};
  const on = opts.onKeys ? new Set(opts.onKeys) : null;
  const dots = Object.entries(state.data.parties)
    .filter(([, p]) => p.spectrum)
    .map(([k, p]) => ({
      label: p.abbr || k, x: p.spectrum.x, y: p.spectrum.y,
      color: p.color, on: on ? on.has(k) : true,
    }));
  const spec = {
    kind: 'spectrum', title, route, dots,
    axes: { left: t('spec.axisLeft'), right: t('spec.axisRight'), top: t('spec.axisTop'), bottom: t('spec.axisBottom') },
  };
  if (opts.marker) spec.marker = opts.marker;
  return spec;
}
// Federal Council arc: the seven members as party-coloured discs.
function shareCouncilSpec() {
  const members = (state.data.council && state.data.council.members) || [];
  const byParty = {};
  members.forEach(m => { byParty[m.party] = (byParty[m.party] || 0) + 1; });
  return {
    kind: 'arc', title: t('council.title'), subtitle: t('council.sub'),
    total: members.length, seats: seatSpecFromSeats(byParty),
  };
}
// The current hash route as a plain "view[/id]" path, for linking a shared
// graph back to the page it lives on (used by graphs without their own route).
function currentRoute() {
  const r = parseHash();
  if (!r || !r.view) return '';
  return r.id != null ? `${r.view}/${r.id}` : r.view;
}
// Plain-text title for a session vote (unofficial translation, else official).
function plainVoteTitle(v) {
  return voteTransTitle(v) || (v.title && (v.title[state.lang] || v.title.de || v.title.fr || v.title.it || v.title.en)) || ('#' + v.businessNumber);
}
// Vote-hemicycle share spec from a session vote's per-party Yes/No/abstain.
function voteHemiSpec(vote) {
  const parties = state.data.parties;
  const ordered = Object.keys(vote.byParty)
    .filter(k => parties[k])
    .sort((a, b) => (parties[a]?.spectrum?.x ?? 50) - (parties[b]?.spectrum?.x ?? 50));
  let y = 0, n = 0, ab = 0;
  const groups = ordered.map(k => {
    const g = vote.byParty[k];
    y += g.yes || 0; n += g.no || 0; ab += g.abstain || 0;
    return { label: parties[k].abbr || k, color: parties[k].color || '#999', yes: g.yes || 0, no: g.no || 0, abstain: g.abstain || 0 };
  });
  return { kind: 'voteHemicycle', title: plainVoteTitle(vote), route: currentRoute(), groups, tallies: { yes: y, no: n, abstain: ab } };
}
// Attach a share button to a chart card, resolving its spec lazily.
function shareChart(host, getSpec) {
  if (host) mountShare(host, getSpec, SHARE_CTX());
}

/* ============================================================
   Financing (from data/financing.json, fetched at build time
   from the official EFK register — see scripts/fetch_financing.py)
   ============================================================ */
const CHF_LOCALES = { en: 'en-CH', de: 'de-CH', fr: 'fr-CH', it: 'it-CH', rm: 'rm-CH' };
function formatCHF(n) {
  const locale = CHF_LOCALES[state.lang] || 'en-CH';
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n || 0) + ' CHF';
}

function renderFinancingSource() {
  const meta = state.data.financing._meta;
  const date = meta?.fetchedAt ? meta.fetchedAt.slice(0, 10) : '';
  return `<p class="detail-source">${t('financing.source').replace('{date}', date)}</p>`;
}

/* ---- Donor identity ------------------------------------------------------
   The EFK register spells the same donor several ways (e.g. "economiesuisse",
   "Economiesuisse", "economiesuisse Verband der Schweizer Unternehmen"). We
   merge those to one canonical donor via the alias table in
   data/donor-descriptions.json, so a donor's page and its search entry gather
   every contribution. Only organisations get a page; individuals are shown as
   plain text (privacy). */
function slugify(s) {
  return normStr(s).replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'x';
}
function donorCanonName(name) {
  return String(name || '').replace(/\s*\([^()]*\)\s*$/, '').replace(/\s+/g, ' ').trim();
}
function donorMaps() {
  if (state._donorMaps) return state._donorMaps;
  const alias = new Map();   // normalised name variant -> canonical slug
  const meta = new Map();    // slug -> {name, desc, url, aliases}
  const donors = (state.data.donorInfo && state.data.donorInfo.donors) || {};
  Object.entries(donors).forEach(([slug, info]) => {
    meta.set(slug, info);
    alias.set(normStr(donorCanonName(info.name || slug)), slug);
    (info.aliases || []).forEach(a => alias.set(normStr(donorCanonName(a)), slug));
  });
  state._donorMaps = { alias, meta };
  return state._donorMaps;
}
function donorSlug(rawName) {
  const key = normStr(donorCanonName(rawName));
  return donorMaps().alias.get(key) || slugify(donorCanonName(rawName));
}
function donorDisplayName(rawName) {
  const m = donorMaps().meta.get(donorSlug(rawName));
  return (m && m.name) || donorCanonName(rawName);
}

/* ---- Pie chart ---------------------------------------------------------- */
const FIN_PALETTE = ['#3b6fb0', '#e07a3f', '#4c9a6b', '#c94f6d', '#8e6bbf', '#d4a63c', '#5aa7c4', '#b5654a', '#6b8e3a', '#c76fa8', '#4f9d9d', '#9c8459'];
const FIN_OTHER_COLOR = '#c2bcae';
function finColor(i) { return FIN_PALETTE[i % FIN_PALETTE.length]; }

// slices: [{key,label,value,color}] with value>0. Returns a pie SVG; each slice
// carries data-donor=key so it cross-highlights with the matching list row.
function renderPie(slices) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  if (!(total > 0)) return '';
  const cx = 60, cy = 60, r = 56;
  const aria = escapeAttr(t('financing.chartLabel'));
  if (slices.length === 1) {
    const s = slices[0];
    return `<svg class="fin-pie" viewBox="0 0 120 120" role="img" aria-label="${aria}">`
      + `<circle class="fin-slice" data-donor="${escapeAttr(s.key)}" cx="${cx}" cy="${cy}" r="${r}" fill="${s.color}">`
      + `<title>${escapeAttr(s.label)} · ${formatCHF(s.value)}</title></circle></svg>`;
  }
  let a0 = -Math.PI / 2;
  const pt = (a) => [(cx + r * Math.cos(a)).toFixed(2), (cy + r * Math.sin(a)).toFixed(2)];
  const paths = slices.map(s => {
    const a1 = a0 + (s.value / total) * 2 * Math.PI;
    const large = (a1 - a0) > Math.PI ? 1 : 0;
    const [x0, y0] = pt(a0), [x1, y1] = pt(a1);
    a0 = a1;
    return `<path class="fin-slice" data-donor="${escapeAttr(s.key)}" d="M${cx} ${cy} L${x0} ${y0} A${r} ${r} 0 ${large} 1 ${x1} ${y1} Z" fill="${s.color}">`
      + `<title>${escapeAttr(s.label)} · ${formatCHF(s.value)}</title></path>`;
  }).join('');
  return `<svg class="fin-pie" viewBox="0 0 120 120" role="img" aria-label="${aria}">${paths}</svg>`;
}

// Merge a side's disclosed donors into one entry per canonical donor.
function aggregateDonors(donors) {
  const map = new Map();
  (donors || []).forEach(d => {
    const slug = donorSlug(d.name);
    const e = map.get(slug) || { slug, name: donorDisplayName(d.name), type: d.type, amount: 0 };
    e.amount += d.amount || 0;
    if (d.type === 'organization') e.type = 'organization';
    map.set(slug, e);
  });
  return [...map.values()].sort((a, b) => b.amount - a.amount);
}

// A pie + a highlight-linked donor list. opts: {heading, total, actors}.
const FIN_MAX_SLICES = 8;
function financingBlockHTML(donors, opts) {
  opts = opts || {};
  const head = opts.heading
    ? `<div class="fin-head"><span class="fin-head-label">${opts.heading}</span>`
      + (opts.total != null ? `<span class="fin-head-total">${formatCHF(opts.total)}</span>` : '')
      + `</div>`
      + (opts.actors != null ? `<div class="fin-sub">${opts.actors} · ${t('financing.actorsReporting')}</div>` : '')
    : '';
  const agg = aggregateDonors(donors);
  if (!agg.length) {
    return `<div class="fin-block">${head}<p class="fin-none">${t('financing.noDonors')}</p></div>`;
  }
  const OTHERS = '__others__';
  const slices = agg.slice(0, FIN_MAX_SLICES).map((d, i) => ({ key: d.slug, label: d.name, value: d.amount, color: finColor(i) }));
  const tailSum = agg.slice(FIN_MAX_SLICES).reduce((s, d) => s + d.amount, 0);
  if (tailSum > 0) slices.push({ key: OTHERS, label: t('financing.moreDonors'), value: tailSum, color: FIN_OTHER_COLOR });
  const rows = agg.map((d, i) => {
    const inPie = i < FIN_MAX_SLICES;
    const key = inPie ? d.slug : OTHERS;
    const color = inPie ? finColor(i) : FIN_OTHER_COLOR;
    const name = d.type === 'organization'
      ? `<a href="#/donor/${encodeURIComponent(d.slug)}" class="fin-name">${escapeAttr(d.name)}</a>`
      : `<span class="fin-name">${escapeAttr(d.name)}</span>`;
    return `<div class="fin-row" data-donor="${escapeAttr(key)}" tabindex="0">`
      + `<span class="fin-dot" style="background:${color}"></span>${name}`
      + `<span class="fin-amt">${formatCHF(d.amount)}</span></div>`;
  }).join('');
  const shareAttr = opts.shareTitle
    ? ` data-share="${escapeAttr(JSON.stringify(pieSpecFromDonors(agg, opts.shareTitle, opts.shareRoute)))}"`
    : '';
  return `<div class="fin-block"${shareAttr}>${head}`
    + `<div class="fin-chartwrap">${renderPie(slices)}</div>`
    + `<div class="fin-rows">${rows}</div></div>`;
}

// Attach cross-highlighting (slice <-> row) to every financing block in a container.
function wireFinancingHighlights(container) {
  if (!container) return;
  container.querySelectorAll('.fin-block').forEach(b => wireCrossHighlight(b, 'data-donor'));
}

/* ---- Donor index + donor pages ------------------------------------------
   Every disclosed contribution, gathered per canonical donor across parties
   and both sides of every vote. Powers the donor pages and search. */
function buildDonorIndex() {
  if (state._donorIndex) return state._donorIndex;
  const idx = new Map();
  const add = (d, recip) => {
    if (!d || !d.amount) return;
    const slug = donorSlug(d.name);
    const e = idx.get(slug) || { slug, name: donorDisplayName(d.name), type: d.type, locations: new Set(), total: 0, contributions: [] };
    if (d.type === 'organization') e.type = 'organization';
    if (d.location) e.locations.add(d.location);
    e.total += d.amount;
    e.contributions.push({ kind: recip.kind, id: recip.id, side: recip.side, amount: d.amount, date: d.date });
    idx.set(slug, e);
  };
  const fin = state.data.financing || {};
  Object.entries(fin.parties || {}).forEach(([pk, f]) =>
    (f.largeDonors || []).forEach(d => add(d, { kind: 'party', id: pk, side: 'party' })));
  Object.entries(fin.initiatives || {}).forEach(([ik, sides]) =>
    ['pro', 'contra'].forEach(side => ((sides[side] || {}).largeDonors || []).forEach(d => add(d, { kind: 'vote', id: ik, side }))));
  state._donorIndex = idx;
  return idx;
}
function recipientName(kind, id) {
  if (kind === 'party') { const p = state.data.parties[id]; return p ? (p.abbr || localized(p.name)) : id; }
  const init = (state.data.initiatives || []).find(i => i.id === id);
  return init ? localized(init.title) : id;
}
function recipientRoute(kind, id) { return kind === 'party' ? `party/${id}` : `initiative/${id}`; }
function sideLabel(side) {
  return side === 'pro' ? t('financing.pro') : side === 'contra' ? t('financing.contra') : t('donor.side.party');
}

function renderDonorPage(slug) {
  const entry = buildDonorIndex().get(slug);
  const titleEl = document.getElementById('donor-title');
  const subEl = document.getElementById('donor-sub');
  const bodyEl = document.getElementById('donor-content');
  if (!titleEl || !bodyEl) return;
  if (!entry) { navigate(''); return; }
  const meta = donorMaps().meta.get(slug);
  const lang = state.lang;
  titleEl.textContent = (meta && meta.name) || entry.name;
  // Dedupe locations, dropping the postal-code prefix the register sometimes adds.
  const locs = [...new Set([...entry.locations].map(l => l.replace(/^\d{4}\s+/, '').trim()))].join(', ');
  subEl.textContent = t('donor.type.org') + (locs ? ' · ' + t('donor.location') + ' ' + locs : '');
  const desc = (meta && meta.desc && (meta.desc[lang] || meta.desc.de || meta.desc.en)) || t('donor.neutralDesc');

  // Aggregate this donor's contributions by recipient + side.
  const byRecip = new Map();
  entry.contributions.forEach(c => {
    const key = `${c.kind}:${c.id}:${c.side}`;
    const e = byRecip.get(key) || { key, kind: c.kind, id: c.id, side: c.side, amount: 0 };
    e.amount += c.amount; byRecip.set(key, e);
  });
  const recips = [...byRecip.values()].sort((a, b) => b.amount - a.amount);
  const OTHERS = '__others__';
  const slices = recips.slice(0, FIN_MAX_SLICES).map((r, i) => ({ key: r.key, label: recipientName(r.kind, r.id), value: r.amount, color: finColor(i) }));
  const tail = recips.slice(FIN_MAX_SLICES).reduce((s, r) => s + r.amount, 0);
  if (tail > 0) slices.push({ key: OTHERS, label: t('financing.moreDonors'), value: tail, color: FIN_OTHER_COLOR });
  const rows = recips.map((r, i) => {
    const inPie = i < FIN_MAX_SLICES;
    const key = inPie ? r.key : OTHERS;
    const color = inPie ? finColor(i) : FIN_OTHER_COLOR;
    return `<div class="fin-row" data-donor="${escapeAttr(key)}" tabindex="0">`
      + `<span class="fin-dot" style="background:${color}"></span>`
      + `<a class="fin-name" href="#/${recipientRoute(r.kind, r.id)}">${escapeAttr(recipientName(r.kind, r.id))}</a>`
      + `<span class="fin-side fin-side-${r.side}">${sideLabel(r.side)}</span>`
      + `<span class="fin-amt">${formatCHF(r.amount)}</span></div>`;
  }).join('');

  bodyEl.innerHTML =
    `<p class="donor-desc">${escapeAttr(desc)}</p>`
    + `<p class="info-updated">${t('donor.editorial')}</p>`
    + `<div class="donor-stats"><div class="stat-box"><div class="big">${formatCHF(entry.total)}</div>`
    + `<div class="lbl">${t('donor.total')}</div></div></div>`
    + `<h3 class="canton-section-title">${t('donor.contributionsTitle')}</h3>`
    + `<div class="fin-block donor-fin" data-share="${escapeAttr(JSON.stringify({
        kind: 'pie',
        title: `${titleEl.textContent} — ${t('donor.contributionsTitle')}`,
        route: `donor/${slug}`,
        subtitle: `${t('donor.total')} · ${formatCHF(entry.total)}`,
        slices: slices.map(s => ({ label: s.label, value: s.value, valueText: formatCHF(s.value), color: s.color })),
        totalText: formatCHF(entry.total), totalLabel: t('donor.total'),
      }))}"><div class="fin-chartwrap">${renderPie(slices)}</div>`
    + `<div class="fin-rows fin-rows-side">${rows}</div></div>`
    + renderFinancingSource()
    + `<div class="donor-links">`
    + (meta && meta.url ? `<a class="resource-link" href="${escapeAttr(meta.url)}" target="_blank" rel="noopener noreferrer">${t('donor.website')} <span class="arrow">↗</span></a>` : '')
    + `<a class="resource-link" href="https://politikfinanzierung.efk.admin.ch" target="_blank" rel="noopener noreferrer">${t('donor.register')} <span class="arrow">↗</span></a>`
    + `</div>`;
  wireFinancingHighlights(bodyEl);
  wireShares(bodyEl, SHARE_CTX());
}

function applyStaticTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.innerHTML = t(el.getAttribute('data-i18n'));
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph')));
  });
  document.querySelectorAll('[data-i18n-aria]').forEach(el => {
    el.setAttribute('aria-label', t(el.getAttribute('data-i18n-aria')));
  });
  document.documentElement.lang = state.lang;
}

function setLang(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) lang = 'en';
  state.lang = lang;
  try { localStorage.setItem('politikch-lang', lang); } catch (e) { /* ignore */ }
  document.querySelectorAll('.lang-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === lang);
    b.setAttribute('aria-pressed', b.dataset.lang === lang ? 'true' : 'false');
  });
  applyStaticTranslations();
  renderFederalCouncil();
  renderInitiatives();
  // Re-render an open subpage so its content follows the language
  const route = parseHash();
  if (route.view === 'canton') renderCantonPage(route.id);
  if (route.view === 'party') renderPartyPage(route.id);
  if (route.view === 'initiative') renderInitiativePage(route.id);
  if (route.view === 'sessions') renderSessionsPage();
  if (route.view === 'session') renderSessionPage(route.id);
  if (route.view === 'votes') renderVotesPage();
  if (route.view === 'page') renderInfoPage(route.id);
  if (route.view === 'donor') renderDonorPage(decodeURIComponent(route.id));
  refreshGlossaryLabels();
}

/* ============================================================
   Hemicycle
   ============================================================ */
function renderHemicycle(containerId, seatData, totalSeats) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  const cx = 200, cy = 190, rInner = 62;

  // Reference geometry is tuned for a 200-seat chamber. Smaller chambers get
  // fewer rows and a smaller radius so seat spacing stays consistent instead
  // of stretching a handful of seats across the full arc.
  const refSeats = 200, rowsRef = 6, rOuterRef = 178;
  const seatCount = Object.values(seatData).reduce((a, b) => a + b, 0);
  const fill = Math.min(1, seatCount / refSeats);
  const rows = Math.max(1, Math.round(rowsRef * Math.sqrt(fill)));
  const rOuter = Math.sqrt(rInner * rInner + (rOuterRef * rOuterRef - rInner * rInner) * fill);

  // Parties ordered left-to-right by political position (spectrum.x)
  const orderedParties = Object.entries(seatData)
    .sort((a, b) => (state.data.parties[a[0]]?.spectrum?.x ?? 50) - (state.data.parties[b[0]]?.spectrum?.x ?? 50));

  const rowRadii = [];
  for (let r = 0; r < rows; r++) rowRadii.push(rows === 1 ? rOuter : rInner + (rOuter - rInner) * (r / (rows - 1)));
  const totalLen = rowRadii.reduce((s, r) => s + r, 0);
  const rowWeights = rowRadii.map(r => r / totalLen);

  // Give each party a share of every row (proportional to row length), so a
  // party's seats form one radial wedge instead of being siloed in one row.
  const perPartyRowCounts = orderedParties.map(([, n]) => {
    const counts = rowWeights.map(w => Math.round(w * n));
    let drift = n - counts.reduce((a, b) => a + b, 0);
    let ri = counts.length - 1;
    while (drift !== 0) {
      counts[ri] += drift > 0 ? 1 : -1;
      drift += drift > 0 ? -1 : 1;
      ri = (ri - 1 + counts.length) % counts.length;
    }
    return counts;
  });

  const rowSeatLists = rowRadii.map((_, row) => {
    const list = [];
    orderedParties.forEach(([key], p) => {
      const color = state.data.parties[key]?.color || '#999';
      for (let i = 0; i < perPartyRowCounts[p][row]; i++) list.push({ party: key, color });
    });
    return list;
  });

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 400 205');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${totalSeats} seats by party`);

  rowRadii.forEach((radius, row) => {
    const list = rowSeatLists[row];
    const count = list.length;
    for (let i = 0; i < count; i++) {
      const angle = Math.PI + (count === 1 ? 0.5 : i / (count - 1)) * Math.PI;
      const x = cx + radius * Math.cos(angle);
      const y = cy + radius * Math.sin(angle);
      const s = list[i];
      const circle = document.createElementNS(svgNS, 'circle');
      circle.setAttribute('cx', x.toFixed(1));
      circle.setAttribute('cy', y.toFixed(1));
      circle.setAttribute('r', '4.6');
      circle.setAttribute('fill', s.color);
      circle.setAttribute('opacity', '0.92');
      circle.setAttribute('tabindex', '0');
      circle.setAttribute('role', 'button');
      circle.setAttribute('data-party', s.party);
      circle.style.cursor = 'pointer';
      circle.style.transition = 'r 0.15s, opacity 0.15s';
      const label = `${state.data.parties[s.party]?.abbr || s.party}`;
      circle.setAttribute('aria-label', label);
      const enter = () => { circle.setAttribute('r', '6.6'); circle.setAttribute('opacity', '1'); };
      const leave = () => { circle.setAttribute('r', '4.6'); circle.setAttribute('opacity', '0.92'); };
      circle.addEventListener('mouseenter', enter);
      circle.addEventListener('mouseleave', leave);
      circle.addEventListener('focus', enter);
      circle.addEventListener('blur', leave);
      circle.addEventListener('click', () => navigate(`party/${s.party}`));
      circle.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`party/${s.party}`); } });
      svg.appendChild(circle);
    }
  });

  container.appendChild(svg);
  const total = document.createElement('div');
  total.className = 'hemicycle-total';
  total.innerHTML = `<div class="num">${totalSeats}</div><div class="lbl">seats</div>`;
  container.appendChild(total);
}

function renderLegend(containerId, seatData) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  const total = Object.values(seatData).reduce((a, b) => a + b, 0) || 1;
  Object.entries(seatData)
    .sort((a, b) => (state.data.parties[a[0]]?.spectrum?.x ?? 50) - (state.data.parties[b[0]]?.spectrum?.x ?? 50))
    .forEach(([key, seats]) => {
      const p = state.data.parties[key];
      if (!p) return;
      const pct = Math.round(seats / total * 100);
      const item = document.createElement('button');
      item.className = 'legend-item';
      item.type = 'button';
      item.setAttribute('data-party', key);
      // The percentage sits between the abbreviation and the seat count and
      // expands into view when the party (or one of its seats) is highlighted.
      item.innerHTML = `<span class="legend-dot" style="background:${p.color}"></span>`
        + `<span>${p.abbr}</span>`
        + `<span class="legend-pct">${pct}%</span>`
        + `<span class="legend-seats">${seats}</span>`;
      item.addEventListener('click', () => navigate(`party/${key}`));
      container.appendChild(item);
    });
  // Seats + legend share one highlight scope (their common chamber card).
  wireCrossHighlight(container.closest('.chamber-card'));
}

/* ============================================================
   Federal Council (7-member executive)
   ============================================================ */
// Two initials for a seat disc, Unicode-safe (handles "Élisabeth …" etc.).
function initialsOf(name) {
  return name.split(/\s+/).filter(Boolean).map(w => [...w][0]).slice(0, 2).join('');
}
// Fill a "{year}"-style placeholder in a translated string.
function fillYear(str, value) { return String(str).replace('{year}', value); }

// A shallow 7-seat arc that echoes the parliament hemicycles, plus a labelled
// list of the seven councillors (name, party, canton), the President marked.
// Composition comes from data/council.json (sourced from admin.ch), so it is
// factual and attributed rather than invented.
function renderFederalCouncil() {
  const wrap = document.getElementById('federal-council');
  const listEl = document.getElementById('council-members');
  if (!wrap || !listEl || !state.data.council) return;
  const meta = state.data.council._meta || {};
  const year = meta.presidencyYear || '';
  const members = state.data.council.members || [];
  const parties = state.data.parties;
  const posX = (m) => parties[m.party]?.spectrum?.x ?? 50;

  // Arc seats ordered left→right by party position, like the chambers.
  const arc = members.slice().sort((a, b) => posX(a) - posX(b));
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 400 190');
  svg.setAttribute('class', 'council-arc');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', t('council.title'));
  const cx = 200, cy = 168, radius = 130, n = arc.length;
  arc.forEach((m, i) => {
    const angle = Math.PI + (n === 1 ? 0.5 : i / (n - 1)) * Math.PI;
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    const p = parties[m.party] || {};
    const isPres = m.role === 'president';
    const r = isPres ? 17 : 15;
    const g = document.createElementNS(svgNS, 'g');
    g.setAttribute('class', 'council-seat' + (isPres ? ' is-president' : ''));
    g.setAttribute('tabindex', '0');
    g.setAttribute('role', 'button');
    g.setAttribute('aria-label', `${m.name} — ${p.abbr || m.party}` + (isPres ? ` · ${fillYear(t('council.president'), year)}` : ''));
    g.style.cursor = 'pointer';
    if (isPres) {
      const ring = document.createElementNS(svgNS, 'circle');
      ring.setAttribute('cx', x.toFixed(1)); ring.setAttribute('cy', y.toFixed(1));
      ring.setAttribute('r', (r + 4).toFixed(1)); ring.setAttribute('class', 'council-pres-ring');
      g.appendChild(ring);
    }
    const c = document.createElementNS(svgNS, 'circle');
    c.setAttribute('cx', x.toFixed(1)); c.setAttribute('cy', y.toFixed(1)); c.setAttribute('r', r);
    c.setAttribute('fill', p.color || '#999'); c.setAttribute('class', 'council-seat-circle');
    g.appendChild(c);
    const tx = document.createElementNS(svgNS, 'text');
    tx.setAttribute('x', x.toFixed(1)); tx.setAttribute('y', y.toFixed(1));
    tx.setAttribute('text-anchor', 'middle'); tx.setAttribute('dominant-baseline', 'central');
    tx.setAttribute('class', 'council-seat-initials'); tx.textContent = initialsOf(m.name);
    g.appendChild(tx);
    if (isPres) {
      const star = document.createElementNS(svgNS, 'text');
      star.setAttribute('x', x.toFixed(1)); star.setAttribute('y', (y - r - 6).toFixed(1));
      star.setAttribute('text-anchor', 'middle'); star.setAttribute('class', 'council-star');
      star.textContent = '★';
      g.appendChild(star);
    }
    const title = document.createElementNS(svgNS, 'title');
    title.textContent = `${m.name} (${p.abbr || m.party})`;
    g.appendChild(title);
    const go = () => navigate('party/' + m.party);
    g.addEventListener('click', go);
    g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    svg.appendChild(g);
  });
  wrap.innerHTML = '';
  wrap.appendChild(svg);

  // List: President first, then Vice-President, then the rest by seniority.
  const rank = (m) => m.role === 'president' ? 0 : m.role === 'vice' ? 1 : 2;
  const ordered = members.slice().sort((a, b) => rank(a) - rank(b) || a.since - b.since);
  listEl.innerHTML = ordered.map(m => {
    const p = parties[m.party] || {};
    const cantonName = (state.data.cantons[m.canton] || {}).name || m.canton;
    let badge = '';
    if (m.role === 'president') badge = `<span class="council-badge council-badge-pres">${fillYear(t('council.president'), year)}</span>`;
    else if (m.role === 'vice') badge = `<span class="council-badge">${fillYear(t('council.vice'), year)}</span>`;
    return `<button type="button" class="council-member" data-party="${m.party}" aria-label="${m.name}, ${p.abbr || m.party}">
      <span class="council-dot" style="background:${p.color || '#999'}"></span>
      <span class="council-member-text">
        <span class="council-name">${m.name}${badge}</span>
        <span class="council-meta">${p.abbr || m.party} · ${cantonName} · ${fillYear(t('council.since'), m.since)}</span>
      </span>
    </button>`;
  }).join('');
  listEl.querySelectorAll('.council-member[data-party]').forEach(b => {
    b.addEventListener('click', () => navigate('party/' + b.dataset.party));
  });
}

/* ============================================================
   Spectrum chart
   ============================================================ */
function renderSpectrum() {
  const chart = document.getElementById('spectrum-chart');
  chart.querySelectorAll('.party-dot').forEach(d => d.remove());
  Object.entries(state.data.parties).forEach(([key, party]) => {
    if (!party.spectrum) return;
    const dot = document.createElement('button');
    dot.className = 'party-dot';
    dot.type = 'button';
    // x maps directly; y is inverted (0 = progressive at bottom, 100 = traditional at top)
    dot.style.left = party.spectrum.x + '%';
    dot.style.top = (100 - party.spectrum.y) + '%';
    dot.setAttribute('aria-label', localized(party.name));
    dot.innerHTML = `
      <span class="party-dot-circle" style="background:${party.color}">${key.slice(0, 3)}</span>
      <span class="party-dot-label">${party.abbr}</span>`;
    dot.addEventListener('click', () => navigate(`party/${key}`));
    chart.appendChild(dot);
  });
}

/* ============================================================
   Initiatives (with filter + search)
   ============================================================ */
// Days-left countdown chip for signature-gathering items (from their deadline).
function daysLeftChip(init) {
  if (init.status !== 'collecting' || !init.deadline) return '';
  const days = Math.ceil((new Date(init.deadline + 'T00:00:00') - new Date()) / 86400000);
  const label = days >= 0 ? t('vote.daysLeft').replace('{n}', days) : t('vote.closed');
  return `<span class="initiative-daysleft">${label}</span>`;
}

// Short words describing where a coalition sits, from its average position:
// x = economic left↔right, y = social progressive(low)↔traditional(high).
function leaningWords(avgX, avgY) {
  let econ;
  if (avgX < 38) econ = 'left';
  else if (avgX < 46) econ = 'centreLeft';
  else if (avgX <= 54) econ = 'centre';
  else if (avgX <= 62) econ = 'centreRight';
  else econ = 'right';
  const parts = [t('lean.' + econ)];
  if (avgY > 62) parts.push(t('lean.conservative'));
  else if (avgY < 38) parts.push(t('lean.progressive'));
  return parts.join(', ');
}

// Political scale for one vote: the parties that endorse it (recommended Yes),
// listed above a mini spectrum where endorsers show in colour and everyone else
// is greyed out ("no say"). A marker at the endorsers' average position (both
// axes) carries short words describing that coalition's leaning. Same axes as
// the home-page "Where the parties stand". With opts.interactive the party dots
// are clickable and reveal their initials on hover.
function voteScaleHTML(init, opts) {
  opts = opts || {};
  const recs = init.recommendations || {};
  const parties = Object.entries(state.data.parties);
  const endorsers = parties.filter(([k]) => recs[k] === 'yes');

  const clickable = opts.interactive;
  const chips = endorsers.length
    ? `<span class="endorse-label">${t('vote.endorsedBy')}</span>` +
      endorsers.map(([key, p]) => clickable
        ? `<button type="button" class="endorse-chip endorse-chip-btn" data-party="${key}" style="background:${p.color}">${p.abbr}</button>`
        : `<span class="endorse-chip" style="background:${p.color}">${p.abbr}</span>`).join('')
    : `<span class="endorse-none">${t('vote.noEndorsements')}</span>`;

  const dots = parties.map(([key, p]) => {
    if (!p.spectrum) return '';
    const on = endorsers.some(([, ep]) => ep === p);
    const cx = p.spectrum.x, cy = 100 - p.spectrum.y;
    const circle = on
      ? `<circle cx="${cx}" cy="${cy}" r="6.5" fill="${p.color}"></circle>`
      : `<circle cx="${cx}" cy="${cy}" r="5.5" class="ms-off"></circle>`;
    if (!clickable) {
      return `<g>${circle}<title>${p.abbr}</title></g>`;
    }
    return `<g class="ms-dot" data-party="${key}" role="button" tabindex="0" aria-label="${p.abbr}">
      ${circle}
      <text class="ms-initials" x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="central">${key.slice(0, 3)}</text>
      <title>${p.abbr}</title></g>`;
  }).join('');

  // Endorsers' midpoint: a solid marker at the average position on both axes,
  // with a leader line routed out to the nearest side and a label sitting a
  // short gap beyond the line's tip so the two never overlap.
  let marker = '';
  const avgX = endorsers.length ? endorsers.reduce((s, [, p]) => s + p.spectrum.x, 0) / endorsers.length : 50;
  const avgY = endorsers.length ? endorsers.reduce((s, [, p]) => s + p.spectrum.y, 0) / endorsers.length : 50;
  if (endorsers.length) {
    const mx = +avgX.toFixed(1), my = +(100 - avgY).toFixed(1);
    const left = avgX < 50;                 // nearest border (left/right)
    const labelX = left ? -10 : 110;        // label sits outside that border…
    const lineEndX = left ? -3 : 103;       // …with the leader line stopping short of it
    const labelY = 1;                       // routed to the top, clear of the axis labels
    marker = `
      <line class="ms-lead" x1="${mx}" y1="${my}" x2="${lineEndX}" y2="${labelY}"></line>
      <circle class="ms-mid-core" cx="${mx}" cy="${my}" r="2.6"></circle>
      <text class="ms-callout" x="${labelX}" y="${labelY}" text-anchor="${left ? 'end' : 'start'}">${leaningWords(avgX, avgY)}</text>`;
  }

  const cls = 'vote-scale' + (opts.large ? ' vote-scale-lg' : '') + (clickable ? ' vote-scale-interactive' : '');
  let shareAttr = '';
  if (opts.share) {
    const spec = spectrumSpec(opts.share.title, opts.share.route, {
      onKeys: endorsers.map(([k]) => k),
      marker: endorsers.length ? { x: avgX, y: 100 - avgY, label: leaningWords(avgX, avgY) } : null,
    });
    shareAttr = ` data-share="${escapeAttr(JSON.stringify(spec))}"`;
  }
  // viewBox padded on every side so the axis labels and endorsers' callout sit
  // outside the 0–100 plot, clear of the axis lines; the plot itself is centred.
  return `
    <div class="${cls}" data-scale${shareAttr}>
      <div class="vote-endorsers">${chips}</div>
      <div class="scale-row">
        <svg class="mini-spectrum" viewBox="-32 -14 164 138" role="img" aria-label="${t('vote.endorsedBy')}">
          <line class="ms-axis" x1="0" y1="50" x2="100" y2="50"></line>
          <line class="ms-axis" x1="50" y1="0" x2="50" y2="100"></line>
          <text class="ms-lbl" x="-5" y="51" text-anchor="end">${t('spec.axisLeft')}</text>
          <text class="ms-lbl" x="105" y="51" text-anchor="start">${t('spec.axisRight')}</text>
          <text class="ms-lbl" x="50" y="-6" text-anchor="middle">${t('spec.axisTop')}</text>
          <text class="ms-lbl" x="50" y="108" text-anchor="middle">${t('spec.axisBottom')}</text>
          ${dots}
          ${marker}
        </svg>
      </div>
    </div>`;
}

// ---- Floating "political priorities" tooltip for the position scales ----
// A pointer-following panel over the mini spectrum and the home "Where the
// parties stand" chart. Over open plot area it ranks example political
// priorities by how well they match the cursor's spot on the economic (x) /
// social (y) grid — items re-order and drop off the list as the pointer moves.
// Over an axis line it instead names that axis and bolds the direction arrow
// the pointer is travelling along.
function clampNum(v, a, b) { return Math.max(a, Math.min(b, v)); }

// Example priorities anchored on the grid: x = economic (0 left … 100 right),
// y = social (0 progressive … 100 traditional). Editorial illustration only.
const PRIORITIES = [
  { key: 'prio.redistribution', x: 8,  y: 45 },
  { key: 'prio.publicServices', x: 15, y: 52 },
  { key: 'prio.workersRights',  x: 18, y: 38 },
  { key: 'prio.freeMarket',     x: 90, y: 52 },
  { key: 'prio.lowTax',         x: 85, y: 58 },
  { key: 'prio.deregulation',   x: 80, y: 62 },
  { key: 'prio.climate',        x: 32, y: 15 },
  { key: 'prio.openness',       x: 35, y: 20 },
  { key: 'prio.equality',       x: 25, y: 12 },
  { key: 'prio.tradition',      x: 62, y: 90 },
  { key: 'prio.sovereignty',    x: 72, y: 85 },
  { key: 'prio.security',       x: 68, y: 82 },
];
const PRIO_SIGMA = 34;      // relevance falloff (grid units)
const PRIO_CUTOFF = 0.14;   // below this a priority drops off the list
const PRIO_MAX = 5;         // most priorities shown at once
const PRIO_ROW_H = 24;      // row height / travel step (px)
const AXIS_BAND = 7;        // how close to a centre line counts as "on the axis"
const AXIS_DEADZONE = 1.4;  // grid units of travel needed to flip the bold arrow (anti-flicker)
const PARTY_SUPPRESS_R = 8; // within this many grid units of a party dot, defer to that dot

let plotTip = null;
let plotTipRows = null;     // Map<key, rowElement>
let lastX = 50, lastY = 50; // previous cursor grid position (for travel direction)
// Axis-direction hysteresis: the bold arrow only flips after the pointer has
// travelled AXIS_DEADZONE past the point where it was last committed, so small
// jitter while sliding along an axis doesn't make the highlighted word flicker.
let axisKindPrev = null, axisAnchor = 50, axisDir = 0;

// True when the pointer sits on or beside any party dot, so the scale tooltip
// should step aside and let the party's own hover (initials / label) show.
function nearPartyDot(cx, cy) {
  const parties = state.data.parties || {};
  for (const key in parties) {
    const sp = parties[key].spectrum;
    if (!sp) continue;
    const ddx = sp.x - cx, ddy = sp.y - cy;
    if (ddx * ddx + ddy * ddy <= PARTY_SUPPRESS_R * PARTY_SUPPRESS_R) return true;
  }
  return false;
}

function buildPlotTip() {
  if (plotTip) return plotTip;
  plotTip = document.createElement('div');
  plotTip.className = 'plot-tip';
  plotTip.setAttribute('aria-hidden', 'true'); // purely visual pointer aid; dots stay keyboard-navigable
  plotTip.innerHTML =
    '<div class="plot-tip-head"></div>' +
    '<div class="plot-tip-prio"></div>' +
    '<div class="plot-tip-axis"></div>';
  document.body.appendChild(plotTip);
  plotTipRows = new Map();
  const body = plotTip.querySelector('.plot-tip-prio');
  PRIORITIES.forEach(p => {
    const row = document.createElement('div');
    row.className = 'plot-tip-row';
    row.innerHTML = '<span class="plot-tip-dot"></span><span class="plot-tip-lbl"></span>';
    body.appendChild(row);
    plotTipRows.set(p.key, row);
  });
  return plotTip;
}

function plotCoords(plot, e) {
  const rect = plot.getBoundingClientRect();
  if (plot.classList.contains('mini-spectrum')) {
    const vb = plot.viewBox.baseVal;
    const vbx = vb.x + (e.clientX - rect.left) / rect.width * vb.width;
    const vby = vb.y + (e.clientY - rect.top) / rect.height * vb.height;
    return { x: vbx, y: 100 - vby, inBounds: vbx >= 0 && vbx <= 100 && vby >= 0 && vby <= 100 };
  }
  const px = (e.clientX - rect.left) / rect.width * 100;
  const py = (e.clientY - rect.top) / rect.height * 100;
  return { x: px, y: 100 - py, inBounds: px >= 0 && px <= 100 && py >= 0 && py <= 100 };
}

function priorityScore(p, cx, cy) {
  const dx = p.x - cx, dy = p.y - cy;
  return Math.exp(-(dx * dx + dy * dy) / (2 * PRIO_SIGMA * PRIO_SIGMA));
}

function renderPriorities(cx, cy) {
  plotTip.classList.remove('axis-mode');
  plotTip.querySelector('.plot-tip-head').textContent = t('scale.prioritiesTitle');
  const ranked = PRIORITIES
    .map(p => ({ p, s: priorityScore(p, cx, cy) }))
    .filter(o => o.s >= PRIO_CUTOFF)
    .sort((a, b) => b.s - a.s)
    .slice(0, PRIO_MAX);
  const shown = new Set();
  ranked.forEach((o, i) => {
    const row = plotTipRows.get(o.p.key);
    shown.add(o.p.key);
    row.querySelector('.plot-tip-lbl').textContent = t(o.p.key);
    row.style.transform = 'translateY(' + (i * PRIO_ROW_H) + 'px)';
    row.style.opacity = clampNum(0.5 + o.s, 0.5, 1).toFixed(2);
    row.classList.add('show');
  });
  plotTipRows.forEach((row, key) => {
    if (!shown.has(key)) { row.classList.remove('show'); row.style.opacity = '0'; }
  });
  plotTip.querySelector('.plot-tip-prio').style.height = (ranked.length * PRIO_ROW_H) + 'px';
}

function renderAxis(kind, dir) {
  plotTip.classList.add('axis-mode');
  const head = plotTip.querySelector('.plot-tip-head');
  const axis = plotTip.querySelector('.plot-tip-axis');
  if (kind === 'econ') {
    head.textContent = t('axis.econ');
    axis.innerHTML =
      '<span class="axis-dir' + (dir < 0 ? ' bold' : '') + '">&larr; ' + t('axis.econLeft') + '</span>' +
      '<span class="axis-dir' + (dir > 0 ? ' bold' : '') + '">' + t('axis.econRight') + ' &rarr;</span>';
  } else {
    head.textContent = t('axis.social');
    axis.innerHTML =
      '<span class="axis-dir' + (dir > 0 ? ' bold' : '') + '">&uarr; ' + t('axis.socialTop') + '</span>' +
      '<span class="axis-dir' + (dir < 0 ? ' bold' : '') + '">&darr; ' + t('axis.socialBottom') + '</span>';
  }
}

function positionPlotTip(e) {
  const pad = 16;
  const w = plotTip.offsetWidth, h = plotTip.offsetHeight;
  let x = e.clientX + pad, y = e.clientY + pad;
  if (x + w > window.innerWidth - 8) x = e.clientX - pad - w;
  if (y + h > window.innerHeight - 8) y = e.clientY - pad - h;
  plotTip.style.left = Math.max(8, x) + 'px';
  plotTip.style.top = Math.max(8, y) + 'px';
}

function hidePlotTip() {
  if (plotTip) plotTip.classList.remove('visible');
}

function updatePlotTip(plot, e) {
  buildPlotTip();
  const c = plotCoords(plot, e);
  if (!c.inBounds) { hidePlotTip(); return; }
  const cx = clampNum(c.x, 0, 100), cy = clampNum(c.y, 0, 100);
  const mvx = cx - lastX, mvy = cy - lastY;      // genuine per-event movement
  lastX = cx; lastY = cy;

  // A party circle nearby wins: hide the scale tooltip so its own hover shows.
  if (nearPartyDot(cx, cy)) { axisKindPrev = null; hidePlotTip(); return; }

  const nearH = Math.abs(cy - 50) < AXIS_BAND;   // on the economic (horizontal) line
  const nearV = Math.abs(cx - 50) < AXIS_BAND;   // on the social (vertical) line
  let mode = 'prio';
  // At the crosshair centre, stay on the axis already in use; otherwise pick the
  // axis the pointer is travelling along most.
  if (nearH && nearV) mode = axisKindPrev || (Math.abs(mvx) >= Math.abs(mvy) ? 'econ' : 'social');
  else if (nearH) mode = 'econ';
  else if (nearV) mode = 'social';

  if (mode === 'econ' || mode === 'social') {
    const pos = mode === 'econ' ? cx : cy;
    if (mode !== axisKindPrev) { axisKindPrev = mode; axisAnchor = pos; axisDir = 0; }
    const delta = pos - axisAnchor;
    if (delta >= AXIS_DEADZONE) { axisDir = 1; axisAnchor = pos; }
    else if (delta <= -AXIS_DEADZONE) { axisDir = -1; axisAnchor = pos; }
    renderAxis(mode, axisDir);
  } else {
    axisKindPrev = null;
    renderPriorities(cx, cy);
  }
  plotTip.classList.add('visible');
  positionPlotTip(e);
}

function initScaleReadouts() {
  document.addEventListener('mousemove', (e) => {
    const target = e.target;
    const plot = target && target.closest && target.closest('.mini-spectrum, #spectrum-chart');
    if (plot) updatePlotTip(plot, e);
    else hidePlotTip();
  });
  window.addEventListener('scroll', hidePlotTip, { passive: true });
  window.addEventListener('blur', hidePlotTip);
}

/* ============================================================
   Glossary help markers ("?" with a hover/focus explanation)
   ============================================================ */
function escapeAttr(s) {
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Inline "?" marker for a Swiss-politics term; `term` maps to a `gloss.<term>`
// definition. Safe to drop next to any label in static HTML or rendered markup.
function termHelp(term) {
  const def = t('gloss.' + term);
  return `<button type="button" class="term-help" data-term="${term}" aria-label="${escapeAttr(def)}">?</button>`;
}

let glossTip = null;
function positionGlossTip(el) {
  const r = el.getBoundingClientRect();
  const w = glossTip.offsetWidth, h = glossTip.offsetHeight, gap = 8;
  let left = r.left + r.width / 2 - w / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
  let top = r.bottom + gap;
  if (top + h > window.innerHeight - 8) top = r.top - gap - h; // flip above if no room below
  glossTip.style.left = Math.round(left) + 'px';
  glossTip.style.top = Math.round(Math.max(8, top)) + 'px';
}
function showGlossTip(el) {
  if (!glossTip) {
    glossTip = document.createElement('div');
    glossTip.className = 'gloss-tip';
    glossTip.setAttribute('role', 'tooltip');
    document.body.appendChild(glossTip);
  }
  // A glossary marker carries a term; other tooltip triggers (e.g. the
  // "unofficial translation" badge) carry the text directly in data-tip.
  glossTip.textContent = el.dataset.tip ? el.dataset.tip : t('gloss.' + el.dataset.term);
  glossTip.classList.add('visible');
  positionGlossTip(el);
}
function hideGlossTip() { if (glossTip) glossTip.classList.remove('visible'); }

// Keep every marker's accessible name in sync with the current language.
function refreshGlossaryLabels() {
  document.querySelectorAll('.term-help[data-term]').forEach(b => {
    b.setAttribute('aria-label', t('gloss.' + b.dataset.term));
  });
}

function initGlossary() {
  // Delegated so it also covers markers added by later renders.
  document.addEventListener('mouseover', (e) => {
    const m = e.target.closest && e.target.closest('.term-help, .unofficial-badge');
    if (m) showGlossTip(m);
  });
  document.addEventListener('mouseout', (e) => {
    const m = e.target.closest && e.target.closest('.term-help, .unofficial-badge');
    if (m && (!e.relatedTarget || !m.contains(e.relatedTarget))) hideGlossTip();
  });
  document.addEventListener('focusin', (e) => {
    const m = e.target.closest && e.target.closest('.term-help, .unofficial-badge');
    if (m) showGlossTip(m);
  });
  document.addEventListener('focusout', (e) => {
    const m = e.target.closest && e.target.closest('.term-help, .unofficial-badge');
    if (m) hideGlossTip();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideGlossTip(); });
  document.addEventListener('click', (e) => {
    // On touch/click, toggle rather than navigate.
    const m = e.target.closest && e.target.closest('.term-help, .unofficial-badge');
    if (m) { e.preventDefault(); glossTip && glossTip.classList.contains('visible') ? hideGlossTip() : showGlossTip(m); }
  });
  window.addEventListener('scroll', hideGlossTip, { passive: true });
  refreshGlossaryLabels();
}

/* ============================================================
   Site-wide search (parties, cantons, votes, municipalities)
   ============================================================ */
function normStr(s) {
  return (s == null ? '' : String(s)).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}
const SEARCH_TYPE_ORDER = { canton: 0, party: 1, vote: 2, donor: 3, session: 4, city: 5 };
// Per-section cap so no one kind floods the suggestion list; sections are shown
// with headers in the order above.
const SEARCH_TYPE_CAP = { canton: 4, party: 4, vote: 4, donor: 5, session: 3, city: 5 };
let muniSearchItems = null; // lazily-loaded municipality entries

// Build the always-available items (parties, cantons, votes) from loaded data.
function coreSearchItems() {
  const items = [];
  Object.entries(state.data.parties || {}).forEach(([key, p]) => {
    const names = Object.values(p.name || {}).join(' ');
    items.push({ type: 'party', label: localized(p.name) || p.abbr, sub: p.abbr,
      route: `party/${key}`, hay: normStr(`${p.abbr} ${names}`) });
  });
  Object.entries(state.data.cantons || {}).forEach(([code, c]) => {
    items.push({ type: 'canton', label: c.name, sub: `${code} · ${c.capital || ''}`,
      route: `canton/${code}`, hay: normStr(`${c.name} ${code} ${c.capital || ''}`) });
  });
  (state.data.initiatives || []).forEach(it => {
    const title = initTitlePlain(it);
    const allTitles = Object.values(it.title || {}).join(' ') + ' ' + (initEnTitle(it) || '');
    items.push({ type: 'vote', label: title, sub: t('type.' + it.type),
      route: `initiative/${it.id}`, hay: normStr(`${title} ${allTitles}`) });
  });
  return items;
}

// Organisation donors for the site search (individuals are omitted for privacy).
function donorSearchItems() {
  const out = [];
  buildDonorIndex().forEach(e => {
    if (e.type !== 'organization') return;
    const loc = ([...e.locations][0] || '').replace(/^\d{4}\s+/, '').trim();
    out.push({ type: 'donor', label: e.name, amount: e.total,
      sub: t('donor.type.org') + (loc ? ' · ' + loc : ''),
      route: `donor/${e.slug}`, hay: normStr(e.name) });
  });
  return out;
}

// Session entries for the site search, built from the (lazy) sessions index.
// Rebuilt on each query rather than cached, so labels follow the language.
function sessionSearchItems() {
  const sessions = (state.data.sessionsIndex && state.data.sessionsIndex.sessions) || [];
  return sessions.map(s => ({
    type: 'session', label: sessionName(s), sub: formatSessionDates(s.start, s.end),
    route: `session/${s.id}`, hay: normStr(`${sessionName(s)} ${s.year} ${s.abbr || ''}`),
  }));
}

function loadMuniSearchItems() {
  if (muniSearchItems) return Promise.resolve(muniSearchItems);
  return fetch('data/municipalities-index.json').then(r => r.ok ? r.json() : null).then(d => {
    const rows = (d && d.m) || [];
    muniSearchItems = rows.map(m => ({
      type: 'city', label: m.n, pop: m.p || 0,
      sub: (state.data.cantons[m.c] || {}).name || m.c,
      route: `canton/${m.c}`, hay: normStr(m.n),
    }));
    return muniSearchItems;
  }).catch(() => { muniSearchItems = []; return muniSearchItems; });
}

// Rank matches: prefix beats word-start beats substring; then, within a kind,
// larger cities / shorter labels first. Results are grouped by kind and each
// section is capped (SEARCH_TYPE_CAP) so no one kind floods the list, then
// returned flat in section order for rendering + keyboard navigation.
function rankSearch(items, q) {
  const nq = normStr(q);
  const scored = [];
  for (const it of items) {
    const i = it.hay.indexOf(nq);
    if (i < 0) continue;
    const score = i === 0 ? 0 : (/\s/.test(it.hay[i - 1]) ? 1 : 2);
    scored.push({ it, score });
  }
  scored.sort((a, b) =>
    a.score - b.score ||
    (b.it.pop || 0) - (a.it.pop || 0) ||
    (b.it.amount || 0) - (a.it.amount || 0) ||
    a.it.label.length - b.it.label.length);
  const counts = {};
  const bySection = {};
  for (const s of scored) {
    const ty = s.it.type;
    counts[ty] = (counts[ty] || 0) + 1;
    if (counts[ty] > (SEARCH_TYPE_CAP[ty] || 4)) continue;
    (bySection[ty] = bySection[ty] || []).push(s.it);
  }
  const out = [];
  Object.keys(SEARCH_TYPE_ORDER)
    .sort((a, b) => SEARCH_TYPE_ORDER[a] - SEARCH_TYPE_ORDER[b])
    .forEach(ty => { if (bySection[ty]) out.push(...bySection[ty]); });
  return out;
}

function setupSearch() {
  const input = document.getElementById('site-search');
  const box = document.getElementById('search-results');
  if (!input || !box) return;
  let results = [], active = -1;

  const close = () => {
    box.hidden = true; box.innerHTML = ''; results = []; active = -1;
    input.setAttribute('aria-expanded', 'false');
  };
  const go = (it) => { close(); input.value = ''; input.blur(); navigate(it.route); };

  const render = () => {
    box.innerHTML = '';
    if (!results.length) {
      const empty = document.createElement('div');
      empty.className = 'search-empty';
      empty.textContent = t('search.noResults');
      box.appendChild(empty);
    } else {
      let lastType = null;
      results.forEach((it, i) => {
        // A section header whenever the kind changes — visually separating groups.
        if (it.type !== lastType) {
          lastType = it.type;
          const h = document.createElement('div');
          h.className = 'search-section';
          h.setAttribute('role', 'presentation');
          h.textContent = t('search.type.' + it.type);
          box.appendChild(h);
        }
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'search-result';
        b.setAttribute('role', 'option');
        b.setAttribute('aria-selected', i === active ? 'true' : 'false');
        if (i === active) b.classList.add('active');
        const main = document.createElement('span');
        main.className = 'search-result-main';
        const lab = document.createElement('span');
        lab.className = 'search-result-label';
        lab.textContent = it.label;
        const sub = document.createElement('span');
        sub.className = 'search-result-sub';
        sub.textContent = it.sub || '';
        main.appendChild(lab); main.appendChild(sub);
        b.appendChild(main);
        b.addEventListener('mousedown', (e) => { e.preventDefault(); go(it); });
        box.appendChild(b);
      });
    }
    box.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  };

  const query = () => {
    const q = input.value.trim();
    if (q.length < 1) { close(); return; }
    const run = () => {
      const items = coreSearchItems().concat(donorSearchItems(), sessionSearchItems(), muniSearchItems || []);
      results = rankSearch(items, q); active = -1; render();
    };
    // Pull in municipalities + the sessions index on first use, then re-run.
    Promise.all([
      muniSearchItems ? null : loadMuniSearchItems(),
      state.data.sessionsIndex ? null : ensureSessionsIndex(),
    ]).then(run);
  };

  input.addEventListener('input', query);
  input.addEventListener('focus', () => { if (input.value.trim()) query(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { close(); input.blur(); return; }
    if (box.hidden || !results.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); active = (active + 1) % results.length; render(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = (active - 1 + results.length) % results.length; render(); }
    else if (e.key === 'Enter') { e.preventDefault(); go(results[active >= 0 ? active : 0]); }
  });
  input.addEventListener('blur', () => setTimeout(close, 120));
}

function makeVoteCard(init, opts) {
  opts = opts || {};
  const card = document.createElement('button');
  card.className = 'initiative-card';
  card.type = 'button';
  const desc = localized(init.desc);
  const shortDesc = desc.length > 130 ? desc.slice(0, 130).trimEnd() + '…' : desc;
  const dateHTML = opts.hideDate ? '' : `<span class="initiative-date">${localized(init.date)}</span>`;
  card.innerHTML = `
    <span class="initiative-type type-${init.type}">${t('type.' + init.type)}</span>
    <span class="initiative-title" style="display:block">${initTitleHTML(init, false)}</span>
    <span class="initiative-desc" style="display:block">${shortDesc}</span>
    <span class="initiative-meta">
      ${dateHTML}
      <span class="initiative-status-group">
        ${daysLeftChip(init)}
        <span class="initiative-status status-${init.status}">${t('status.' + init.status)}</span>
      </span>
    </span>
    ${voteScaleHTML(init)}
    <span class="initiative-link">${t('init.readMore')} →</span>`;
  card.addEventListener('click', () => navigate(`initiative/${init.id}`));
  return card;
}

// Filter the vote list to one lifecycle tab (and an optional search query).
function votesForTab(tab, query) {
  const statuses = TAB_STATUSES[tab] || [];
  const q = (query || '').trim().toLowerCase();
  return state.data.initiatives.filter(init => {
    if (!statuses.includes(init.status)) return false;
    if (!q) return true;
    return (localized(init.title) + ' ' + localized(init.desc)).toLowerCase().includes(q);
  });
}

// Render vote cards into a container, either flat or grouped by ballot date
// (a date heading, a vertical gap, then that date's cards).
function renderVotes(container, items, grouped, emptyMsg) {
  container.innerHTML = '';
  if (!items.length) {
    container.innerHTML = `<div class="init-empty">${emptyMsg}</div>`;
    return;
  }
  if (!grouped) {
    const grid = document.createElement('div');
    grid.className = 'initiatives-grid';
    items.forEach(init => grid.appendChild(makeVoteCard(init)));
    container.appendChild(grid);
    return;
  }
  const order = [];
  const groups = {};
  items.forEach(it => {
    const key = localized(it.date);
    if (!groups[key]) { groups[key] = []; order.push(key); }
    groups[key].push(it);
  });
  order.forEach(key => {
    const wrap = document.createElement('div');
    wrap.className = 'vote-date-group';
    const h = document.createElement('h3');
    h.className = 'vote-date-heading';
    h.textContent = key;
    wrap.appendChild(h);
    const grid = document.createElement('div');
    grid.className = 'initiatives-grid';
    groups[key].forEach(init => grid.appendChild(makeVoteCard(init, { hideDate: true })));
    wrap.appendChild(grid);
    container.appendChild(wrap);
  });
}

function updateProcessGraphic(tab) {
  document.querySelectorAll('#vote-process .vote-process-step').forEach(step => {
    step.classList.toggle('active', step.dataset.stage === tab);
  });
  const desc = document.getElementById('vote-process-desc');
  if (desc) desc.textContent = t('process.desc.' + tab);
}

function renderInitiatives() {
  const container = document.getElementById('initiatives-grid');
  if (!container) return;
  const items = votesForTab(state.tab, state.search);
  const emptyMsg = state.search.trim() ? t('init.none') : t('init.emptyTab');
  renderVotes(container, items, GROUPED_TABS.has(state.tab), emptyMsg);
  updateProcessGraphic(state.tab);
}

/* ============================================================
   Initiative page
   ============================================================ */
function renderInitiativePage(id) {
  const init = state.data.initiatives.find(i => i.id === id);
  if (!init) { navigate(''); return; }

  const badge = document.getElementById('initiative-type-badge');
  badge.className = 'party-abbr';
  badge.style.background = init.type === 'initiative' ? 'var(--red)' : '#0064C8';
  badge.innerHTML = `<span>${t('type.' + init.type)}</span>${termHelp(init.type)}`;
  // Title text only; the "unofficial translation" badge sits on its own line
  // beneath the title and above the date/status line.
  document.getElementById('initiative-title').textContent = initTitlePlain(init);
  document.getElementById('initiative-badge-line').innerHTML = initEnTitle(init) ? unofficialBadge() : '';
  document.getElementById('initiative-date').textContent = localized(init.date);

  // Signature-gathering initiatives get a "where to sign" callout pointing to
  // the official Federal Chancellery page where signature sheets are published.
  const signBlock = init.status === 'collecting' && init.url ? `
    <div class="init-sign">
      <h4 class="canton-section-title" style="font-size:16px;margin-top:0">${t('init.sign')}</h4>
      <p>${t('init.signDesc')}</p>
      <a class="resource-link" href="${init.url}" target="_blank" rel="noopener noreferrer">${t('init.signLink')} <span class="arrow">↗</span></a>
    </div>` : '';

  const fillFin = (fkey) => t(fkey).replace('{name}', initTitlePlain(init));
  const content = document.getElementById('initiative-content');
  content.innerHTML = `
    <div class="detail-top">
      <div class="detail-top-left">
        <p class="canton-intro" style="margin-bottom:24px">${localized(init.desc)}</p>
        <div class="detail-facts">
          <div class="detail-fact"><strong>${t('modal.status')}</strong><span>${t('status.' + init.status)}</span></div>
          <div class="detail-fact"><strong>${t('modal.date')}</strong><span>${localized(init.date)}</span></div>
          ${init.outcome ? `<div class="detail-fact"><strong>${t('modal.outcome')}</strong><span>${localized(init.outcome)}</span></div>` : ''}
          ${init.author ? `<div class="detail-fact"><strong>${t('modal.author')}</strong><span>${init.author}</span></div>` : ''}
        </div>
        <p class="detail-source">${t('modal.source')}</p>
        <a class="resource-link resource-link-compact" href="${init.url}" target="_blank" rel="noopener noreferrer">${t('modal.official')} <span class="arrow">↗</span></a>
        ${signBlock}
      </div>
      <div class="detail-top-right">
        <h3 class="canton-section-title" style="margin-top:0">${t('init.scaleTitle')}</h3>
        ${voteScaleHTML(init, { large: true, interactive: true, share: { title: `${t('init.scaleTitle')} — ${initTitlePlain(init)}`, route: `initiative/${id}` } })}
      </div>
    </div>
    <h3 class="canton-section-title" style="margin-top:48px">${t('rec.title')}${termHelp('parole')}</h3>
    ${recommendationColumnsHTML(init)}
    <h3 class="canton-section-title" style="margin-top:48px">${t('init.financing.title')}</h3>
    ${renderInitiativeFinancing(id, fillFin)}`;

  // Party dots on the detail scale are clickable and reveal their initials on hover.
  content.querySelectorAll('.ms-dot[data-party]').forEach(g => {
    const key = g.dataset.party;
    g.addEventListener('click', () => navigate('party/' + key));
    g.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('party/' + key); }
    });
  });
  // The "endorsed by" chips and the recommendation-column chips are clickable.
  content.querySelectorAll('.endorse-chip-btn[data-party], .rec-chip[data-party]').forEach(btn => {
    btn.addEventListener('click', () => navigate('party/' + btn.dataset.party));
  });
  wireFinancingHighlights(content);
  wireShares(content, SHARE_CTX());
}

// Party voting recommendations (Parolen) for one vote, split into three
// columns — recommends Yes / recommends No / no recommendation (free vote).
// Data is stored per vote in initiatives.json by the build-time fetcher (from
// Swissvotes); a vote whose parties haven't decided yet shows an honest
// "not announced" note instead of an empty graph. This is additive — the
// position spectrum above it is unchanged.
function recommendationColumnsHTML(init) {
  const recs = init.recommendations || {};
  const keys = Object.keys(recs).filter(k => state.data.parties[k]);
  if (!keys.length) {
    return `<div class="rec-pending">
      <span class="rec-pending-icon" aria-hidden="true">${icon('ballot')}</span>
      <p>${t('rec.pending')}</p>
    </div>`;
  }
  // Order each column left-to-right by economic position, like the legend.
  const byX = (a, b) => (state.data.parties[a]?.spectrum?.x ?? 50) - (state.data.parties[b]?.spectrum?.x ?? 50);
  const chip = (key) => {
    const p = state.data.parties[key];
    return `<button type="button" class="rec-chip" data-party="${key}" style="background:${p.color}" aria-label="${localized(p.name)}">${p.abbr}</button>`;
  };
  const col = (stance) => {
    const members = keys.filter(k => recs[k] === stance).sort(byX);
    const chips = members.length
      ? members.map(chip).join('')
      : `<span class="rec-empty">${t('rec.none')}</span>`;
    return `<div class="rec-col rec-col-${stance}">
      <div class="rec-col-head">
        <span class="rec-col-title">${t('rec.' + stance)}${stance === 'free' ? termHelp('stimmfreigabe') : ''}</span>
        <span class="rec-count">${members.length}</span>
      </div>
      <div class="rec-chips">${chips}</div>
    </div>`;
  };
  return `
    <div class="rec-columns">
      ${col('yes')}
      ${col('no')}
      ${col('free')}
    </div>
    <p class="rec-source">${t('rec.source')}</p>`;
}

function renderInitiativeFinancing(id, fillFin) {
  const sides = state.data.financing.initiatives[id];
  if (!sides) {
    return `
      <div class="empty-state"><div class="empty-state-icon" aria-hidden="true">${icon('coins')}</div><p>${fillFin('init.financing.desc')}</p></div>
      <div style="margin-top:16px">
        <a class="resource-link" href="https://politikfinanzierung.efk.admin.ch" target="_blank" rel="noopener noreferrer">${t('init.financing.link')} <span class="arrow">↗</span></a>
      </div>`;
  }
  const sideBlock = (sideKey, labelKey) => financingBlockHTML(sides[sideKey].largeDonors, {
    heading: t(labelKey),
    total: sides[sideKey].totalRevenue,
    actors: sides[sideKey].actorCount,
    shareTitle: `${t(labelKey)} — ${t('init.financing.title')}`,
    shareRoute: `initiative/${id}`,
  });
  return `
    <div class="canton-grid fin-grid" style="margin-top:8px">
      ${sideBlock('pro', 'financing.pro')}
      ${sideBlock('contra', 'financing.contra')}
    </div>
    ${renderFinancingSource()}
    <div style="margin-top:16px">
      <a class="resource-link" href="https://politikfinanzierung.efk.admin.ch" target="_blank" rel="noopener noreferrer">${t('init.financing.link')} <span class="arrow">↗</span></a>
    </div>`;
}

/* ============================================================
   Map
   ============================================================ */
function buildMap() {
  const svg = document.getElementById('swiss-map');
  const tooltip = document.getElementById('map-tooltip');
  const NS = 'http://www.w3.org/2000/svg';

  Object.entries(MAP_PATHS).forEach(([code, geo]) => {
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', geo.d);
    path.setAttribute('id', code);
    path.setAttribute('tabindex', '0');
    path.setAttribute('role', 'button');
    const name = () => state.data.cantons[code]?.name || code;
    path.setAttribute('aria-label', name());

    const showTip = e => {
      tooltip.textContent = name();
      tooltip.style.opacity = '1';
      const x = (e.clientX ?? window.innerWidth / 2);
      const y = (e.clientY ?? window.innerHeight / 2);
      tooltip.style.left = (x - tooltip.offsetWidth / 2) + 'px';
      tooltip.style.top = (y - tooltip.offsetHeight - 14) + 'px';
    };
    path.addEventListener('mousemove', showTip);
    path.addEventListener('mouseleave', () => { tooltip.style.opacity = '0'; });
    path.addEventListener('focus', () => {
      const rect = path.getBoundingClientRect();
      tooltip.textContent = name();
      tooltip.style.opacity = '1';
      tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
      tooltip.style.top = (rect.top - tooltip.offsetHeight - 8) + 'px';
    });
    path.addEventListener('blur', () => { tooltip.style.opacity = '0'; });
    path.addEventListener('click', () => navigate(`canton/${code}`));
    path.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`canton/${code}`); }
    });
    svg.appendChild(path);

    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', geo.c[0]);
    label.setAttribute('y', geo.c[1]);
    label.setAttribute('class', 'map-label');
    label.textContent = code;
    svg.appendChild(label);
  });
}

/* ============================================================
   Canton page
   ============================================================ */
function renderCantonPage(code) {
  const c = state.data.cantons[code];
  if (!c) { navigate(''); return; }

  document.getElementById('canton-title').textContent = c.name;
  document.getElementById('canton-capital').textContent = `${t('canton.capital')}: ${c.capital}`;
  document.getElementById('canton-emblem').textContent = code;

  document.getElementById('canton-stats').innerHTML = `
    <div class="canton-stat"><div class="canton-stat-val">${c.pop}</div><div class="canton-stat-label">${t('canton.stat.pop')}</div></div>
    <div class="canton-stat"><div class="canton-stat-val">${c.area}</div><div class="canton-stat-label">${t('canton.stat.area')}</div></div>
    <div class="canton-stat"><div class="canton-stat-val">${c.seats}</div><div class="canton-stat-label">${t('canton.stat.seats')}</div></div>
    <div class="canton-stat"><div class="canton-stat-val">${c.joined}</div><div class="canton-stat-label">${t('canton.stat.joined')}</div></div>`;

  const fill = (key) => t(key).replace('{name}', c.name);
  const cd = (state.data.cantonData && state.data.cantonData.cantons) ? state.data.cantonData.cantons[code] : null;
  const meta = (state.data.cantonData && state.data.cantonData._meta) || {};
  const emptyBox = (icon, key) =>
    `<div class="empty-state"><div class="empty-state-icon" aria-hidden="true">${icon}</div><p>${fill(key)}</p></div>`;

  const electionsBody = cantonNCHTML(cd, c) || emptyBox(icon('ballot'), 'canton.empty.elections');
  const muniBody = cantonMuniHTML(cd, meta) || emptyBox(icon('buildings'), 'canton.empty.municipalities');

  document.getElementById('canton-content').innerHTML = `
    <p class="canton-intro">${c.desc}</p>
    <div class="canton-grid">
      <div>
        <h3 class="canton-section-title">${t('canton.elections')}${termHelp('nationalCouncil')}</h3>
        ${electionsBody}
      </div>
      <div>
        <h3 class="canton-section-title">${t('canton.municipalities')}${termHelp('canton')}</h3>
        <div id="canton-muni-body">${muniBody}</div>
      </div>
    </div>
    <p class="canton-sources">${t('canton.sources')}</p>`;

  renderCantonSeats(cd);
  const cncRoot = document.querySelector('#canton-content .cnc');
  wireCrossHighlight(cncRoot);
  wirePartyNav(cncRoot);
  renderCantonMap(cd, code);
}

// Cross-highlight within a container: hovering (or focusing) any element that
// carries a data-party highlights every element of that party inside `root` and
// dims the rest. Used by the canton "Elections & results" block (seats + bar +
// list) and each home-page chamber (seats + legend). Idempotent per element.
function wireCrossHighlight(root, attr) {
  if (!root || root.dataset.xhlWired) return;
  root.dataset.xhlWired = '1';
  attr = attr || 'data-party';
  const sel = `[${attr}]`;
  const set = (key) => {
    root.classList.toggle('is-dim', key != null);
    root.querySelectorAll(sel).forEach(el => {
      el.classList.toggle('hl', key != null && el.getAttribute(attr) === key);
    });
  };
  const from = (e) => {
    const el = e.target && e.target.closest && e.target.closest(sel);
    set(el ? el.getAttribute(attr) : null);
  };
  root.addEventListener('mouseover', from);
  root.addEventListener('mouseleave', () => set(null));
  root.addEventListener('focusin', from);
  root.addEventListener('focusout', () => set(null));
}

// Make every [data-party] element inside `root` navigate to that party's page
// (click or Enter/Space), but only when the value is a real party key — so
// keyless entries (e.g. small canton lists stored by name) stay inert.
function wirePartyNav(root) {
  if (!root || root.dataset.pnavWired) return;
  root.dataset.pnavWired = '1';
  const keyAt = (e) => {
    const el = e.target && e.target.closest && e.target.closest('[data-party]');
    const key = el && el.getAttribute('data-party');
    return (key && state.data.parties[key]) ? key : null;
  };
  root.addEventListener('click', (e) => { const k = keyAt(e); if (k) navigate('party/' + k); });
  root.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const k = keyAt(e); if (k) { e.preventDefault(); navigate('party/' + k); }
  });
}

// "Elections & results": the canton's National Council delegation from the last
// federal election (party strengths, seats, change), from data/canton-data.json.
function cantonNCHTML(cd, c) {
  const nc = cd && cd.nc;
  if (!nc || !nc.parties || !nc.parties.length) return '';
  const prev = nc.year - 4;
  const colorFor = (p) => (p.key && state.data.parties[p.key]) ? state.data.parties[p.key].color : '#9aa0a6';
  const nameFor = (p) => (p.key && state.data.parties[p.key]) ? state.data.parties[p.key].abbr : localized(p.name);
  // Stable per-party id shared by the seats, the bar and the list, so hovering
  // any one representation can highlight the party across all three.
  const idFor = (p) => p.key || localized(p.name);
  // A party is a link only when it maps to a real party page.
  const clickable = (p) => !!(p.key && state.data.parties[p.key]);

  // Seat-distribution bar: widths are the exact share of the canton's seats each
  // party won (so they sum to 100% and match the hemicycle and the table), left
  // → right by political position. Parties that won no seats are omitted.
  const spectrumX = (p) => (p.key && state.data.parties[p.key] && state.data.parties[p.key].spectrum
    && state.data.parties[p.key].spectrum.x != null) ? state.data.parties[p.key].spectrum.x : 50;
  const barParties = nc.parties.filter(p => p.seats > 0).sort((a, b) => spectrumX(a) - spectrumX(b));
  const bar = barParties.map(p => {
    const w = (p.seats / nc.totalSeats * 100).toFixed(3);
    return `<span class="cnc-seg${clickable(p) ? ' is-clickable' : ''}" data-party="${idFor(p)}" style="width:${w}%;background:${colorFor(p)}" title="${escapeAttr(nameFor(p))} · ${p.seats}/${nc.totalSeats}"></span>`;
  }).join('');

  const seatParties = nc.parties.filter(p => p.seats > 0).sort((a, b) => b.seats - a.seats);
  const rows = seatParties.map(p => {
    const d = p.delta;
    const delta = d == null ? '<span class="cnc-delta"></span>'
      : `<span class="cnc-delta ${d > 0 ? 'up' : d < 0 ? 'down' : ''}">${d > 0 ? '▲' : d < 0 ? '▼' : '–'} ${Math.abs(d).toFixed(1)}</span>`;
    const canClick = clickable(p);
    const attrs = canClick ? ` role="button" tabindex="0" aria-label="${escapeAttr(nameFor(p))}"` : '';
    return `<div class="cnc-row${canClick ? ' is-clickable' : ''}" data-party="${idFor(p)}"${attrs}>
      <span class="cnc-dot" style="background:${colorFor(p)}"></span>
      <span class="cnc-name">${nameFor(p)}</span>
      <span class="cnc-seats">${p.seats}</span>
      <span class="cnc-strength">${p.strength != null ? p.strength.toFixed(1) + '%' : '—'}</span>
      ${delta}
    </div>`;
  }).join('');

  const heading = t('canton.nc.heading').replace('{year}', nc.year);
  const note = nc.totalSeats === 1
    ? `<p class="cnc-note">${t('canton.nc.singleSeat').replace('{name}', c.name)}</p>` : '';
  return `<div class="cnc">
    <div class="cnc-head">${heading} · <strong>${nc.totalSeats}</strong> ${t('canton.stat.seats')}</div>
    <div class="hemicycle canton-hemicycle" id="canton-nc-hemicycle"></div>
    ${bar ? `<div class="cnc-bar" role="img" aria-label="${heading}">${bar}</div>` : ''}
    <div class="cnc-row cnc-legend">
      <span class="cnc-dot"></span>
      <span class="cnc-name">${t('canton.nc.party')}</span>
      <span class="cnc-seats">${t('canton.nc.seats')}</span>
      <span class="cnc-strength">${t('canton.nc.share')}</span>
      <span class="cnc-delta">${t('canton.nc.change').replace('{year}', prev)}</span>
    </div>
    ${rows}
    ${note}
  </div>`;
}

// Municipality map for the canton: a baked, pre-projected SVG (one file per
// canton under data/municipalities/) whose polygons reveal name + population on
// hover. Purely informational — it navigates nowhere. Loaded lazily; on any
// failure the municipality count already in place stays as the fallback.
let muniTip = null;
function ensureMuniTip() {
  if (muniTip) return muniTip;
  muniTip = document.createElement('div');
  muniTip.className = 'muni-tip';
  document.body.appendChild(muniTip);
  return muniTip;
}
function muniTipHTML(m) {
  const pop = m.pop != null ? Number(m.pop).toLocaleString('de-CH') : null;
  return `<strong>${escapeAttr(m.name)}</strong>`
    + (m.capital ? `<span class="muni-tip-badge">${t('canton.map.capital')}</span>` : '')
    + (pop ? `<div class="muni-tip-row">${t('canton.map.pop')}: <b>${pop}</b></div>` : '')
    + (m.km2 != null ? `<div class="muni-tip-row">${m.km2} km²</div>` : '');
}
function showMuniTipAt(m, x, y) {
  const tip = ensureMuniTip();
  tip.innerHTML = muniTipHTML(m);
  tip.style.opacity = '1';
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let left = x - w / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
  let top = y - h - 12;
  if (top < 8) top = y + 16;
  tip.style.left = Math.round(left) + 'px';
  tip.style.top = Math.round(top) + 'px';
}
function hideMuniTip() { if (muniTip) muniTip.style.opacity = '0'; }

function renderCantonMap(cd, code) {
  const host = document.getElementById('canton-muni-body');
  if (!host) return;
  fetch(`data/municipalities/${code}.json`).then(r => r.ok ? r.json() : null).then(map => {
    if (!map || !map.municipalities || !map.municipalities.length) return; // keep the count fallback
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${map.w} ${map.h}`);
    svg.setAttribute('class', 'muni-map');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', t('canton.map.hint'));
    map.municipalities.forEach(m => {
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', m.d);
      path.setAttribute('class', 'muni' + (m.capital ? ' muni-capital' : ''));
      path.setAttribute('tabindex', '0');
      path.setAttribute('role', 'img');
      const popTxt = m.pop != null ? `, ${t('canton.map.pop')} ${Number(m.pop).toLocaleString('de-CH')}` : '';
      path.setAttribute('aria-label', m.name + popTxt);
      // Note: do NOT re-order the node on hover — mutating the hovered element
      // suppresses the follow-up mousemove and breaks the tooltip.
      path.addEventListener('mousemove', e => showMuniTipAt(m, e.clientX, e.clientY));
      path.addEventListener('mouseleave', hideMuniTip);
      path.addEventListener('focus', () => { const r = path.getBoundingClientRect(); showMuniTipAt(m, r.left + r.width / 2, r.top); });
      path.addEventListener('blur', hideMuniTip);
      svg.appendChild(path);
    });
    const wrap = document.createElement('div');
    wrap.className = 'muni-map-wrap';
    wrap.appendChild(svg);

    // Zoom + pan controls (wheel / drag, plus +/−/reset buttons).
    const zoom = setupMuniZoom(svg, map.w, map.h);
    const controls = document.createElement('div');
    controls.className = 'muni-map-controls';
    const mkBtn = (label, txt, fn) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'muni-zoom-btn';
      b.textContent = txt;
      b.setAttribute('aria-label', label);
      b.addEventListener('click', fn);
      return b;
    };
    controls.appendChild(mkBtn(t('canton.map.zoomIn'), '+', () => zoom.step(1)));
    controls.appendChild(mkBtn(t('canton.map.zoomOut'), '−', () => zoom.step(-1)));
    controls.appendChild(mkBtn(t('canton.map.zoomReset'), '⤡', () => zoom.reset()));
    wrap.appendChild(controls);

    const cap = document.createElement('div');
    cap.className = 'muni-map-caption';
    cap.textContent = t('canton.muni.single').replace('{m}', map.municipalities.length);
    wrap.appendChild(cap);
    host.innerHTML = '';
    host.appendChild(wrap);
  }).catch(() => { /* keep the count fallback */ });
}

// Pan + zoom for a municipality-map SVG by driving its viewBox. Zoom via wheel
// (toward the cursor) or the +/−/reset buttons; pan by dragging. Never zooms out
// past the full canton or pans outside it. Returns { step, reset }.
function setupMuniZoom(svg, bw, bh) {
  const KMAX = 9;
  let k = 1, x = 0, y = 0;
  const apply = () => {
    x = Math.max(0, Math.min(bw - bw / k, x));
    y = Math.max(0, Math.min(bh - bh / k, y));
    svg.setAttribute('viewBox', `${x.toFixed(1)} ${y.toFixed(1)} ${(bw / k).toFixed(1)} ${(bh / k).toFixed(1)}`);
  };
  const zoomTo = (sx, sy, nk) => {
    nk = Math.max(1, Math.min(KMAX, nk));
    const ratio = k / nk;                 // keep (sx,sy) under the cursor fixed
    x = sx - (sx - x) * ratio;
    y = sy - (sy - y) * ratio;
    k = nk;
    apply();
  };
  const toSvg = (clientX, clientY) => {
    const r = svg.getBoundingClientRect();
    return [x + (clientX - r.left) / r.width * (bw / k),
            y + (clientY - r.top) / r.height * (bh / k)];
  };
  svg.addEventListener('wheel', (e) => {
    e.preventDefault();
    const [sx, sy] = toSvg(e.clientX, e.clientY);
    zoomTo(sx, sy, k * (e.deltaY < 0 ? 1.08 : 1 / 1.08)); // gentle per-notch zoom
  }, { passive: false });

  let dragging = false, lastX = 0, lastY = 0;
  svg.addEventListener('pointerdown', (e) => {
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    svg.classList.add('grabbing');
    try { svg.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
  });
  svg.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const r = svg.getBoundingClientRect();
    x -= (e.clientX - lastX) / r.width * (bw / k);
    y -= (e.clientY - lastY) / r.height * (bh / k);
    lastX = e.clientX; lastY = e.clientY;
    apply();
    hideMuniTip();
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false;
    svg.classList.remove('grabbing');
    try { svg.releasePointerCapture(e.pointerId); } catch (_) { /* noop */ }
  };
  svg.addEventListener('pointerup', end);
  svg.addEventListener('pointercancel', end);
  svg.addEventListener('lostpointercapture', () => { dragging = false; svg.classList.remove('grabbing'); });

  apply();
  return {
    step: (dir) => zoomTo(x + bw / k / 2, y + bh / k / 2, k * (dir > 0 ? 1.3 : 1 / 1.3)),
    reset: () => { k = 1; x = 0; y = 0; apply(); },
  };
}

// Populate the canton NC seat hemicycle (same graphic as the home page's
// chambers), keyed by party. Called after canton-content innerHTML is set.
function renderCantonSeats(cd) {
  if (!cd || !cd.nc || !cd.nc.parties) return;
  const container = document.getElementById('canton-nc-hemicycle');
  if (!container) return;
  const seatData = {};
  cd.nc.parties.filter(p => p.seats > 0)
    .forEach(p => { seatData[p.key || localized(p.name)] = p.seats; });
  if (Object.keys(seatData).length) {
    renderHemicycle('canton-nc-hemicycle', seatData, cd.nc.totalSeats);
    const cantonName = document.getElementById('canton-title')?.textContent || '';
    shareChart(container.closest('.cnc'), () => ({
      kind: 'hemicycle',
      title: `${cantonName} — ${t('canton.elections')}`,
      subtitle: t('canton.nc.heading').replace('{year}', cd.nc.year),
      total: cd.nc.totalSeats,
      seats: seatSpecFromSeats(seatData),
    }));
  }
}

// "Municipalities": count of political municipalities (and districts) in the
// canton, from the official federal register in data/canton-data.json.
function cantonMuniHTML(cd, meta) {
  if (!cd || cd.municipalities == null) return '';
  const d = cd.districts || 0;
  const summary = d > 1
    ? t('canton.muni.summary').replace('{m}', cd.municipalities).replace('{d}', d)
    : t('canton.muni.single').replace('{m}', cd.municipalities);
  const year = (meta.municipalitySnapshot || '').slice(0, 4);
  const asOf = year ? `<div class="canton-muni-asof">${t('canton.asOf').replace('{date}', year)}</div>` : '';
  return `<div class="canton-muni">
    <div class="canton-muni-num">${cd.municipalities}</div>
    <div class="canton-muni-text">${summary}</div>
    ${asOf}
  </div>`;
}

/* ============================================================
   Party page
   ============================================================ */
function renderPartyPage(key) {
  const p = state.data.parties[key];
  if (!p) { navigate(''); return; }

  const hero = document.getElementById('party-hero');
  hero.style.background = `linear-gradient(135deg, ${p.color}22 0%, var(--white) 100%)`;
  const badge = document.getElementById('party-abbr-badge');
  badge.style.background = p.color;
  badge.textContent = p.abbr;
  document.getElementById('party-name-large').textContent = localized(p.name);
  document.getElementById('party-desc-large').textContent = localized(p.desc);

  const posGrid = document.getElementById('party-positions');
  posGrid.innerHTML = '';
  (p.positions || []).forEach(pos => {
    const card = document.createElement('div');
    card.className = 'position-card';
    const barLabel = `${t('party.positionLevel')}: ${pos.level}%`;
    card.innerHTML = `
      <div class="position-topic">${t('topic.' + pos.topic)}</div>
      <div class="position-stance">${localized(pos.stance)}</div>
      <div class="position-bar" role="img" aria-label="${barLabel}"><div class="position-bar-fill" style="width:0%;background:${p.color}"></div></div>`;
    posGrid.appendChild(card);
    // animate bar after paint
    requestAnimationFrame(() => {
      card.querySelector('.position-bar-fill').style.width = pos.level + '%';
    });
  });

  const fillFin = (fkey) => t(fkey).replace('{name}', localized(p.name));
  document.getElementById('party-extra').innerHTML = `
    <div>
      <h3 class="canton-section-title">${t('party.rep')}</h3>
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <div class="stat-box"><div class="big" style="color:${p.color}">${p.ncSeats}</div><div class="lbl">${t('party.nc')}</div></div>
        <div class="stat-box"><div class="big" style="color:${p.color}">${p.csSeats}</div><div class="lbl">${t('party.cs')}</div></div>
      </div>
    </div>
    <div>
      <h3 class="canton-section-title">${t('party.resources')}</h3>
      <div style="display:flex;flex-direction:column;gap:12px">
        <a class="resource-link" href="${p.website}" target="_blank" rel="noopener noreferrer">${t('party.website')} <span class="arrow">↗</span></a>
        <a class="resource-link" href="https://www.parlament.ch/en/organe/groups" target="_blank" rel="noopener noreferrer">${t('party.group')} <span class="arrow">↗</span></a>
      </div>
      <p style="margin-top:20px;font-size:12px;color:var(--mid);line-height:1.6">${t('party.disclaimer')}</p>
    </div>
    <div style="grid-column:1/-1">
      <h3 class="canton-section-title">${t('party.financing.title')}</h3>
      ${renderPartyFinancing(key, p, fillFin)}
    </div>
    <div style="grid-column:1/-1">
      <h3 class="canton-section-title">${t('party.votesTitle')}</h3>
      <p style="margin:-8px 0 16px;font-size:13px;color:var(--mid);line-height:1.6">${t('party.votesDesc')}</p>
      <div class="init-filters" role="tablist" aria-label="Vote stage" id="party-vote-tabs">
        <button class="filter-btn" role="tab" data-ptab="collecting" aria-selected="false" data-i18n="init.tabCollecting">Gathering signatures</button>
        <button class="filter-btn" role="tab" data-ptab="pending" aria-selected="false" data-i18n="init.tabPending">Pending</button>
        <button class="filter-btn active" role="tab" data-ptab="upcoming" aria-selected="true" data-i18n="init.tabUpcoming">Voting next</button>
        <button class="filter-btn" role="tab" data-ptab="decided" aria-selected="false" data-i18n="init.tabVoted">Voted on</button>
      </div>
      <div class="votes-list" id="party-vote-grid" style="margin-top:24px"></div>
    </div>`;

  state.partyTab = 'upcoming';
  document.querySelectorAll('#party-vote-tabs [data-ptab]').forEach(btn => {
    btn.addEventListener('click', () => { state.partyTab = btn.dataset.ptab; renderPartyVotes(key); });
  });
  wireFinancingHighlights(document.getElementById('party-extra'));
  wireShares(document.getElementById('party-extra'), SHARE_CTX());
  applyStaticTranslations();
  renderPartyVotes(key);
}

// Votes this party recommended a Yes on, grouped into the same lifecycle tabs.
function renderPartyVotes(key) {
  const grid = document.getElementById('party-vote-grid');
  if (!grid) return;
  const tab = state.partyTab || 'upcoming';
  document.querySelectorAll('#party-vote-tabs [data-ptab]').forEach(b => {
    const on = b.dataset.ptab === tab;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  const items = votesForTab(tab).filter(i => i.recommendations && i.recommendations[key] === 'yes');
  renderVotes(grid, items, GROUPED_TABS.has(tab), t('party.votesNone'));
}

function renderPartyFinancing(key, p, fillFin) {
  const f = state.data.financing.parties[key];
  if (!f) {
    return `
      <div class="empty-state"><div class="empty-state-icon" aria-hidden="true">${icon('coins')}</div><p>${fillFin('party.financing.desc')}</p></div>
      <div style="margin-top:16px">
        <a class="resource-link" href="https://politikfinanzierung.efk.admin.ch" target="_blank" rel="noopener noreferrer">${t('party.financing.link')} <span class="arrow">↗</span></a>
      </div>`;
  }
  return `
    <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:20px">
      <div class="stat-box"><div class="big" style="color:${p.color}">${formatCHF(f.totalRevenue)}</div><div class="lbl">${t('financing.total')} (${f.year})</div></div>
    </div>
    <div class="detail-facts">
      <div class="detail-fact"><strong>${t('financing.monetary')}</strong><span>${formatCHF(f.monetaryDonations)}</span></div>
      <div class="detail-fact"><strong>${t('financing.nonMonetary')}</strong><span>${formatCHF(f.nonMonetaryDonations)}</span></div>
      <div class="detail-fact"><strong>${t('financing.events')}</strong><span>${formatCHF(f.events)}</span></div>
      <div class="detail-fact"><strong>${t('financing.sales')}</strong><span>${formatCHF(f.sales)}</span></div>
      <div class="detail-fact"><strong>${t('financing.membershipFees')}</strong><span>${formatCHF(f.membershipFees)}</span></div>
      <div class="detail-fact"><strong>${t('financing.mandateFees')}</strong><span>${formatCHF(f.mandateFees)}</span></div>
    </div>
    <h4 class="canton-section-title" style="font-size:16px;margin-top:24px">${t('financing.topDonors')}</h4>
    ${financingBlockHTML(f.largeDonors, { shareTitle: `${t('financing.topDonors')} — ${p.abbr || localized(p.name)}`, shareRoute: `party/${key}` })}
    ${renderFinancingSource()}
    <div style="margin-top:16px">
      <a class="resource-link" href="https://politikfinanzierung.efk.admin.ch" target="_blank" rel="noopener noreferrer">${t('party.financing.link')} <span class="arrow">↗</span></a>
    </div>`;
}

/* ============================================================
   Federal Assembly sessions
   Index: data/sessions-index.json (session list + metadata).
   Detail: data/sessions/<id>.json (that session's final votes).
   Both fetched at build time from the parliament.ch OData web
   service (scripts/fetch_sessions.py) and loaded lazily.
   ============================================================ */
// The Federal Assembly's own YouTube channel. Politikch only ever *links* to
// it — recordings stay on the parliament's channel, never re-hosted here.
const PARL_YOUTUBE = 'https://www.youtube.com/@ParlCH';
// German season terms match the channel's own video titles, so a channel-scoped
// search on them reliably surfaces a given session's recordings.
const SEASON_QUERY = { spring: 'Frühjahrssession', summer: 'Sommersession', autumn: 'Herbstsession', winter: 'Wintersession', special: 'Sondersession' };

let sessionsIndexPromise = null;
let sessionTransPromise = null;
const sessionFileCache = {};
// Per-session vote filter state (topic + search), keyed by session id.

function ensureSessionsIndex() {
  if (sessionsIndexPromise) return sessionsIndexPromise;
  sessionsIndexPromise = fetch('data/sessions-index.json')
    .then(r => r.ok ? r.json() : null)
    .then(d => { state.data.sessionsIndex = d || { sessions: [] }; return state.data.sessionsIndex; })
    .catch(() => { state.data.sessionsIndex = { sessions: [] }; return state.data.sessionsIndex; });
  return sessionsIndexPromise;
}
// Unofficial English act-title translations (data/sessions-translations.json),
// kept separate from the official per-session files. Only used for the English UI.
function ensureSessionTranslations() {
  if (sessionTransPromise) return sessionTransPromise;
  sessionTransPromise = fetch('data/sessions-translations.json')
    .then(r => r.ok ? r.json() : null)
    .then(d => { state.data.sessionTrans = (d && d.titles) || {}; return state.data.sessionTrans; })
    .catch(() => { state.data.sessionTrans = {}; return state.data.sessionTrans; });
  return sessionTransPromise;
}
// The unofficial translation of a vote's title for the current language, if we
// have one (only EN and RM — the languages with no official Swiss act title).
// The file may store a plain string (English-only legacy) or {en,rm} per id.
function voteTransTitle(v) {
  const e = state.data.sessionTrans && state.data.sessionTrans[String(v.id)];
  if (!e) return null;
  return (typeof e === 'string') ? (state.lang === 'en' ? e : null) : (e[state.lang] || null);
}
function ensureSessionFile(id) {
  if (sessionFileCache[id]) return sessionFileCache[id];
  sessionFileCache[id] = fetch(`data/sessions/${id}.json`)
    .then(r => r.ok ? r.json() : null)
    .catch(() => null);
  return sessionFileCache[id];
}

function sessionName(s) { return `${t('session.' + s.season)} ${s.year}`; }

function formatSessionDates(start, end) {
  const locale = CHF_LOCALES[state.lang] || 'en-CH';
  const s = new Date(start + 'T00:00:00');
  const full = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', year: 'numeric' });
  if (!end) return full.format(s);
  const e = new Date(end + 'T00:00:00');
  if (s.getMonth() === e.getMonth() && s.getFullYear() === e.getFullYear()) {
    return `${new Intl.DateTimeFormat(locale, { day: 'numeric' }).format(s)}–${full.format(e)}`;
  }
  return `${full.format(s)} – ${full.format(e)}`;
}

function sessionVotesLabel(n) {
  if (!n) return '';
  return n === 1 ? t('session.finalVotesOne') : t('session.finalVotes').replace('{n}', n);
}
function youtubeSessionSearch(s) {
  const q = `${SEASON_QUERY[s.season] || ''} ${s.year}`.trim();
  return `${PARL_YOUTUBE}/search?query=${encodeURIComponent(q)}`;
}
function businessUrl(v) {
  const lp = ({ en: 'en', de: 'de', fr: 'fr', it: 'it' })[state.lang] || 'en';
  return `https://www.parlament.ch/${lp}/ratsbetrieb/suche-curia-vista/geschaeft?AffairId=${v.businessNumber}`;
}
// Act title. Swiss acts have official titles only in DE/FR/IT. In DE/FR/IT the
// official title is shown as-is. In English we show our UNOFFICIAL translation
// (marked with an "unofficial" badge that explains itself on hover/focus); if no
// translation exists yet we fall back to the official original with a language chip.
function voteTitleHTML(v) {
  const title = v.title || {};
  const en = voteTransTitle(v);
  if (en) {
    return `<span class="svote-title-text">${en}</span>${unofficialBadge()}`;
  }
  const cur = title[state.lang];
  if (cur) return `<span class="svote-title-text">${cur}</span>`;
  const order = ['de', 'fr', 'it'];
  const lang = order.find(l => title[l]) || Object.keys(title)[0];
  const text = title[lang] || v.business || '';
  return `<span class="svote-title-text">${text}</span>` +
    `<abbr class="svote-lang" title="${escapeAttr(t('session.titleLangNote'))}">${(lang || '').toUpperCase()}</abbr>`;
}
function voteTitlePlain(v) {
  const title = v.title || {};
  return voteTransTitle(v) || title[state.lang] || title.de || title.fr || title.it || v.business || '';
}

// A small "unofficial translation" badge whose full explanation shows on
// hover/focus (native tooltip). Shared by session votes and initiatives — it
// replaces the former sessions popup. `interactive` adds keyboard focus; pass
// false inside a <button> (a focusable child there would be invalid markup).
function unofficialBadge(interactive) {
  const focus = interactive === false ? '' : ' tabindex="0" role="note"';
  const tip = escapeAttr(t('session.unofficialTip'));
  return `<span class="unofficial-badge"${focus} data-tip="${tip}" aria-label="${tip}">${t('session.unofficial')}</span>`;
}

// Initiative title: in English, prefer our unofficial translation (+ badge)
// where the official name is only in a national language; otherwise the
// localized official title. `interactive` false for use inside a card button.
function initEnTitle(init) {
  const e = state.data.initTrans && state.data.initTrans[init.id];
  if (!e) return null;
  return (typeof e === 'string') ? (state.lang === 'en' ? e : null) : (e[state.lang] || null);
}
function initTitleHTML(init, interactive) {
  const en = initEnTitle(init);
  if (en) return `<span class="init-title-text">${en}</span>${unofficialBadge(interactive)}`;
  return `<span class="init-title-text">${localized(init.title)}</span>`;
}
function initTitlePlain(init) { return initEnTitle(init) || localized(init.title); }

/* ---- Sessions list page (#/sessions) ---- */
function renderSessionsPage() {
  const intro = document.getElementById('sessions-page-intro');
  const grid = document.getElementById('sessions-page-grid');
  if (!intro || !grid) return;

  intro.innerHTML = `
    <p class="canton-intro" style="margin-bottom:28px">${t('session.desc')}</p>
    <div class="chamber-types">
      <div class="chamber-type">
        <span class="chamber-type-icon">${icon('hemicycle')}</span>
        <div><h4>${t('session.nc')}</h4><p>${t('session.ncDesc')}</p></div>
      </div>
      <div class="chamber-type">
        <span class="chamber-type-icon">${icon('chamberCS')}</span>
        <div><h4>${t('session.cs')}</h4><p>${t('session.csDesc')}</p></div>
      </div>
      <div class="chamber-type">
        <span class="chamber-type-icon">${icon('chamberUFA')}</span>
        <div><h4>${t('session.ufa')}</h4><p>${t('session.ufaDesc')}</p></div>
      </div>
    </div>
    <p class="session-chamber-note">${t('session.chambersDesc')}</p>
    <button type="button" class="votes-open-btn" id="votes-open-btn">${icon('search')}<span>${t('votes.open')}</span></button>`;
  const openBtn = document.getElementById('votes-open-btn');
  if (openBtn) openBtn.addEventListener('click', () => navigate('votes'));

  ensureSessionsIndex().then(data => {
    const sessions = (data && data.sessions) || [];
    grid.innerHTML = '';
    if (!sessions.length) {
      grid.innerHTML = `<div class="init-empty">${t('session.empty')}</div>`;
      return;
    }
    // Group into one row per year (newest year first; within a year, earliest
    // session on the left so the row reads as a chronological timeline).
    const byYear = new Map();
    sessions.forEach(s => { if (!byYear.has(s.year)) byYear.set(s.year, []); byYear.get(s.year).push(s); });
    [...byYear.keys()].sort((a, b) => b - a).forEach(year => {
      const block = document.createElement('div');
      block.className = 'session-year';
      const label = document.createElement('div');
      label.className = 'session-year-label';
      label.textContent = year;
      block.appendChild(label);
      const row = document.createElement('div');
      row.className = 'session-year-row';
      byYear.get(year).slice().sort((a, b) => a.start.localeCompare(b.start))
        .forEach(s => row.appendChild(makeSessionCard(s)));
      block.appendChild(row);
      grid.appendChild(block);
    });
  });
}

function makeSessionCard(s) {
  const card = document.createElement('button');
  card.className = 'session-card';
  card.type = 'button';
  const votes = s.voteCount || 0;
  const meta = votes
    ? `<span class="session-card-votes">${sessionVotesLabel(votes)}</span>`
    : `<span class="session-card-votes session-card-votes-muted">${t('session.' + s.season)}</span>`;
  card.innerHTML = `
    <span class="session-card-emblem" aria-hidden="true">${icon(SEASON_ICON[s.season] || 'star')}</span>
    <span class="session-card-body">
      <span class="session-card-name">${sessionName(s)}</span>
      <span class="session-card-dates">${formatSessionDates(s.start, s.end)}</span>
      <span class="session-card-meta">${meta}</span>
    </span>
    <span class="session-card-arrow" aria-hidden="true">→</span>`;
  card.setAttribute('aria-label', `${sessionName(s)} — ${sessionVotesLabel(votes) || t('session.' + s.season)}`);
  card.addEventListener('click', () => navigate('session/' + s.id));
  return card;
}

/* ---- One final-vote block (collapsed head + expandable details) ---- */
function sessionVoteHTML(v) {
  const cast = v.tally.yes + v.tally.no + v.tally.abstain;
  const pct = (n) => cast ? (n / cast * 100).toFixed(1) : 0;
  const seg = (kind, n) => n > 0 ? `<span class="svote-seg svote-seg-${kind}" style="width:${pct(n)}%"></span>` : '';
  const resultCls = v.passed ? 'yes' : 'no';
  const resultTxt = v.passed ? t('session.passed') : t('session.rejected');
  const tallyAria = `${t('session.yes')} ${v.tally.yes}, ${t('session.no')} ${v.tally.no}, ${t('session.abstain')} ${v.tally.abstain}`;

  const topicChips = (v.topics || []).map(tk =>
    `<span class="svote-topic">${t('session.topic.' + tk)}</span>`).join('');
  const typeChip = v.btype ? `<span class="svote-btype">${t('session.btype.' + v.btype)}</span>` : '';

  return `<div class="svote" data-vote="${v.id}">
    <div class="svote-head">
      <a class="svote-num" href="${businessUrl(v)}" target="_blank" rel="noopener noreferrer">${v.business || ''}</a>
      <span class="svote-title">${voteTitleHTML(v)}</span>
      <span class="svote-result svote-result-${resultCls}">${resultTxt}</span>
    </div>
    <div class="svote-tally" role="img" aria-label="${tallyAria}">
      ${seg('yes', v.tally.yes)}${seg('no', v.tally.no)}${seg('abs', v.tally.abstain)}
    </div>
    <div class="svote-counts">
      <span class="svote-c svote-c-yes">${t('session.yes')} ${v.tally.yes}</span>
      <span class="svote-c svote-c-no">${t('session.no')} ${v.tally.no}</span>
      ${v.tally.abstain ? `<span class="svote-c svote-c-abs">${t('session.abstain')} ${v.tally.abstain}</span>` : ''}
    </div>
    <details class="svote-details">
      <summary>${t('session.details')}</summary>
      <div class="svote-detail-body">
        <div class="svote-meaning">
          <h4>${t('session.meaningTitle')}</h4>
          <p>${t('session.meaningBody')}</p>
          <div class="svote-tags">
            ${topicChips ? `<div class="svote-tagrow"><span class="svote-taglbl">${t('session.topicsLabel')}</span><span class="svote-tagvals">${topicChips}</span></div>` : ''}
            ${typeChip ? `<div class="svote-tagrow"><span class="svote-taglbl">${t('session.typeLabel')}</span><span class="svote-tagvals">${typeChip}</span></div>` : ''}
          </div>
          <a class="resource-link resource-link-compact" href="${businessUrl(v)}" target="_blank" rel="noopener noreferrer">${t('session.officialDossier')} <span class="arrow">↗</span></a>
          <div class="svote-leaning">
            <h4>${t('leaning.title')}</h4>
            <p class="svote-leaning-desc">${t('leaning.desc')}</p>
            ${voteLeaningHTML(v)}
          </div>
        </div>
        <div class="svote-graphic">
          <h4>${t('session.graphicTitle')}</h4>
          <div class="svote-hemi" data-hemi></div>
          <div class="svote-hemi-legend">
            <span class="svh-key svh-key-yes">${t('session.legendYes')}</span>
            <span class="svh-key svh-key-no">${t('session.legendNo')}</span>
            <span class="svh-key svh-key-abs">${t('session.legendAbstain')}</span>
          </div>
          <h4 style="margin-top:22px">${t('session.byPartyTitle')}</h4>
          <div class="svote-party-grid">${votePartyRowsHTML(v)}</div>
        </div>
      </div>
    </details>
  </div>`;
}

function votePartyRowsHTML(v) {
  const groups = Object.keys(v.byParty)
    .filter(k => state.data.parties[k])
    .sort((a, b) => (state.data.parties[a]?.spectrum?.x ?? 50) - (state.data.parties[b]?.spectrum?.x ?? 50));
  return groups.map(k => {
    const p = state.data.parties[k];
    const g = v.byParty[k];
    const gc = g.yes + g.no + g.abstain;
    const gp = (n) => gc ? (n / gc * 100).toFixed(1) : 0;
    return `<div class="svote-prow is-clickable" data-party="${k}" role="button" tabindex="0" aria-label="${escapeAttr(localized(p.name) || p.abbr)}">
      <span class="svote-pdot" style="background:${p.color}"></span>
      <span class="svote-pabbr">${p.abbr}</span>
      <span class="svote-pbar" role="img" aria-label="${p.abbr}: ${t('session.yes')} ${g.yes}, ${t('session.no')} ${g.no}, ${t('session.abstain')} ${g.abstain}">
        ${g.yes > 0 ? `<span class="svote-seg svote-seg-yes" style="width:${gp(g.yes)}%"></span>` : ''}
        ${g.no > 0 ? `<span class="svote-seg svote-seg-no" style="width:${gp(g.no)}%"></span>` : ''}
        ${g.abstain > 0 ? `<span class="svote-seg svote-seg-abs" style="width:${gp(g.abstain)}%"></span>` : ''}
      </span>
      <span class="svote-pcounts">
        <span class="pc pc-yes">${g.yes}</span><span class="pc pc-no">${g.no}</span><span class="pc pc-abs">${g.abstain}</span>
      </span>
    </div>`;
  }).join('');
}

// The vote's "leaning": the average political position of the members who voted
// Yes, each placed at their party's spectrum position and weighted by that
// party's Yes count. Used for the leaning graph and the "by leaning" ordering.
function voteLeaning(v) {
  const parties = state.data.parties;
  let sx = 0, sy = 0, w = 0;
  for (const k in (v.byParty || {})) {
    const p = parties[k];
    if (!p || !p.spectrum) continue;
    const yes = v.byParty[k].yes || 0;
    sx += p.spectrum.x * yes; sy += p.spectrum.y * yes; w += yes;
  }
  return w ? { x: sx / w, y: sy / w } : null;
}

// How close a vote was: the Yes/No margin. diff is the raw gap; pct is the gap
// as a share of Yes+No (0 = tied, 1 = unanimous). Smaller = closer.
function voteMargin(v) {
  const y = v.tally.yes, n = v.tally.no, cast = y + n;
  return { diff: Math.abs(y - n), pct: cast ? Math.abs(y - n) / cast : 1 };
}

// Mini 2-D spectrum for one vote: each party dot filled if its members mostly
// voted Yes, greyed otherwise, with a marker at the Yes-coalition's weighted
// position and short words describing that leaning (same chart as the votes).
function voteLeaningHTML(v) {
  const lean = voteLeaning(v);
  if (!lean) return `<p class="rec-source">${t('leaning.none')}</p>`;
  const parties = Object.entries(state.data.parties);
  const dots = parties.map(([key, p]) => {
    if (!p.spectrum) return '';
    const g = (v.byParty || {})[key];
    const on = g && g.yes > g.no;
    const cx = p.spectrum.x, cy = 100 - p.spectrum.y;
    return on
      ? `<g><circle cx="${cx}" cy="${cy}" r="6" fill="${p.color}"></circle><title>${p.abbr}</title></g>`
      : `<g><circle cx="${cx}" cy="${cy}" r="5" class="ms-off"></circle><title>${p.abbr}</title></g>`;
  }).join('');
  const mx = +lean.x.toFixed(1), my = +(100 - lean.y).toFixed(1);
  const left = lean.x < 50;
  const labelX = left ? -10 : 110, lineEndX = left ? -3 : 103, labelY = 1;
  const marker = `
    <line class="ms-lead" x1="${mx}" y1="${my}" x2="${lineEndX}" y2="${labelY}"></line>
    <circle class="ms-mid-core" cx="${mx}" cy="${my}" r="2.8"></circle>
    <text class="ms-callout" x="${labelX}" y="${labelY}" text-anchor="${left ? 'end' : 'start'}">${leaningWords(lean.x, lean.y)}</text>`;
  return `<div class="vote-scale">
    <div class="scale-row">
      <svg class="mini-spectrum" viewBox="-32 -14 164 138" role="img" aria-label="${escapeAttr(t('leaning.title'))}">
        <line class="ms-axis" x1="0" y1="50" x2="100" y2="50"></line>
        <line class="ms-axis" x1="50" y1="0" x2="50" y2="100"></line>
        <text class="ms-lbl" x="-5" y="51" text-anchor="end">${t('spec.axisLeft')}</text>
        <text class="ms-lbl" x="105" y="51" text-anchor="start">${t('spec.axisRight')}</text>
        <text class="ms-lbl" x="50" y="-6" text-anchor="middle">${t('spec.axisTop')}</text>
        <text class="ms-lbl" x="50" y="108" text-anchor="middle">${t('spec.axisBottom')}</text>
        ${dots}${marker}
      </svg>
    </div>
  </div>`;
}

// A hemicycle where each seat is a National Council member, ordered left→right
// by party position: filled = Yes, hollow = No, small grey = abstained/absent.
// Shows at a glance how the vote split across the political spectrum.
function renderVoteHemicycle(container, byParty) {
  const parties = state.data.parties;
  const ordered = Object.keys(byParty)
    .filter(k => parties[k])
    .sort((a, b) => (parties[a]?.spectrum?.x ?? 50) - (parties[b]?.spectrum?.x ?? 50));
  // Flatten into an ordered seat list (party colour + decision), grouped so a
  // party's Yes seats sit next to its No/abstain seats.
  const seats = [];
  ordered.forEach(k => {
    const g = byParty[k], color = parties[k].color;
    for (let i = 0; i < g.yes; i++) seats.push({ color, d: 'yes', party: k });
    for (let i = 0; i < g.no; i++) seats.push({ color, d: 'no', party: k });
    for (let i = 0; i < g.abstain; i++) seats.push({ color, d: 'abs', party: k });
  });
  const total = seats.length;
  if (!total) return;

  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 400 210');
  svg.setAttribute('class', 'vote-hemicycle');
  svg.setAttribute('role', 'img');
  const cx = 200, cy = 196, rInner = 66, rOuter = 188;
  const rows = 7;
  const rowRadii = [];
  for (let r = 0; r < rows; r++) rowRadii.push(rInner + (rOuter - rInner) * (r / (rows - 1)));
  const totalLen = rowRadii.reduce((s, r) => s + r, 0);
  // Seats per row proportional to arc length; distribute the ordered list across
  // rows so the left→right ordering is preserved radially.
  const perRow = rowRadii.map(r => Math.max(1, Math.round(total * r / totalLen)));
  let drift = total - perRow.reduce((a, b) => a + b, 0), ri = perRow.length - 1;
  while (drift !== 0) { perRow[ri] += drift > 0 ? 1 : -1; drift += drift > 0 ? -1 : 1; ri = (ri - 1 + perRow.length) % perRow.length; }

  let idx = 0;
  rowRadii.forEach((radius, row) => {
    const count = perRow[row];
    for (let i = 0; i < count && idx < total; i++) {
      const angle = Math.PI + (count === 1 ? 0.5 : i / (count - 1)) * Math.PI;
      const x = cx + radius * Math.cos(angle);
      const y = cy + radius * Math.sin(angle);
      const s = seats[idx++];
      if (s.d === 'abs') {
        // Abstained / absent: a dot with hatch lines in the party's own colour.
        const g = document.createElementNS(NS, 'g');
        g.setAttribute('data-party', s.party);
        const ring = document.createElementNS(NS, 'circle');
        ring.setAttribute('cx', x.toFixed(1)); ring.setAttribute('cy', y.toFixed(1));
        ring.setAttribute('r', '4'); ring.setAttribute('fill', '#ffffff');
        ring.setAttribute('stroke', s.color); ring.setAttribute('stroke-width', '0.9');
        g.appendChild(ring);
        [-1.4, 1.4].forEach(dy => {
          const half = Math.sqrt(Math.max(0, 3.4 * 3.4 - dy * dy));
          const ln = document.createElementNS(NS, 'line');
          ln.setAttribute('x1', (x - half).toFixed(1)); ln.setAttribute('y1', (y + dy).toFixed(1));
          ln.setAttribute('x2', (x + half).toFixed(1)); ln.setAttribute('y2', (y + dy).toFixed(1));
          ln.setAttribute('stroke', s.color); ln.setAttribute('stroke-width', '0.9');
          g.appendChild(ln);
        });
        svg.appendChild(g);
        continue;
      }
      const c = document.createElementNS(NS, 'circle');
      c.setAttribute('cx', x.toFixed(1)); c.setAttribute('cy', y.toFixed(1));
      c.setAttribute('data-party', s.party);
      if (s.d === 'yes') { c.setAttribute('r', '4.4'); c.setAttribute('fill', s.color); }
      else { c.setAttribute('r', '4.2'); c.setAttribute('fill', '#ffffff'); c.setAttribute('stroke', s.color); c.setAttribute('stroke-width', '1.6'); }
      svg.appendChild(c);
    }
  });
  container.innerHTML = '';
  container.appendChild(svg);
}

/* ---- Shared votes explorer (used by the session page and the votes page) ----
   Renders search + topic + "by leaning" + "closest" filters over a set of votes
   and lists the matching vote cards (each expandable). */

// Wire each rendered vote card so its hemicycle draws lazily on first open, with
// cross-highlight + party navigation on the graphic.
function wireVoteCards(host, votes) {
  host.querySelectorAll('.svote').forEach(el => {
    const details = el.querySelector('.svote-details');
    const holder = el.querySelector('[data-hemi]');
    const id = +el.dataset.vote;
    const vote = votes.find(v => String(v.id) === String(id));
    if (!details || !vote) return;
    details.addEventListener('toggle', () => {
      if (details.open && holder && !holder.dataset.done) {
        holder.dataset.done = '1';
        renderVoteHemicycle(holder, vote.byParty);
        const g = el.querySelector('.svote-graphic');
        wireCrossHighlight(g);
        wirePartyNav(g);
        mountShare(g, () => voteHemiSpec(vote), SHARE_CTX());
      }
    });
  });
}

function mountVotesExplorer(hostEl, votes) {
  // Three independent controls that all compose:
  //  • topic   — subset by thematic tag
  //  • result  — dropdown: closest / widest margin (sorts) or adopted / not
  //              adopted (subset)
  //  • leaning — click a spectrum point to rank by distance to it
  const st = { q: '', topic: '', result: '', target: null };
  const topics = [...new Set(votes.flatMap(v => v.topics || []))]
    .map(k => ({ k, label: t('session.topic.' + k) }))
    .sort((a, b) => a.label.localeCompare(b.label));

  hostEl.innerHTML = `
    <div class="votes-controls">
      <div class="session-search-wrap">
        <span class="session-search-icon">${icon('search')}</span>
        <input type="search" class="session-search" data-x-search autocomplete="off"
          placeholder="${escapeAttr(t('votes.searchPh'))}" aria-label="${escapeAttr(t('votes.searchPh'))}">
      </div>
      <select class="session-topic-select" data-x-topic aria-label="${escapeAttr(t('session.filterTopic'))}">
        <option value="">${t('session.filterAll')}</option>
        ${topics.map(o => `<option value="${o.k}">${o.label}</option>`).join('')}
      </select>
      <select class="session-topic-select" data-x-result aria-label="${escapeAttr(t('explore.resultAny'))}">
        <option value="">${t('explore.resultAny')}</option>
        <option value="close">${t('explore.closest')}</option>
        <option value="wide">${t('explore.widest')}</option>
        <option value="adopted">${t('explore.adopted')}</option>
        <option value="rejected">${t('explore.notAdopted')}</option>
      </select>
      <button type="button" class="votes-fbtn" data-x-lean aria-pressed="false">${icon('target')}<span>${t('explore.leaning')}</span></button>
      <button type="button" class="votes-clear" data-x-clear hidden>${t('explore.clear')}</button>
      <span class="session-vote-count" data-x-count></span>
    </div>
    <div data-x-list></div>`;

  const q1 = (s) => hostEl.querySelector(s);
  const listHost = q1('[data-x-list]');
  const countEl = q1('[data-x-count]');
  const leanBtn = q1('[data-x-lean]');
  const clearBtn = q1('[data-x-clear]');
  const searchEl = q1('[data-x-search]');
  const topicEl = q1('[data-x-topic]');
  const resultEl = q1('[data-x-result]');

  const dist = (v) => { const l = voteLeaning(v); return l ? (l.x - st.target.x) ** 2 + (l.y - st.target.y) ** 2 : Infinity; };
  const byDate = (a, b) => (b.voteEnd || '').localeCompare(a.voteEnd || '');

  const filtered = () => {
    let out = votes.slice();
    if (st.topic) out = out.filter(v => (v.topics || []).includes(st.topic));
    if (st.result === 'adopted') out = out.filter(v => v.passed);
    else if (st.result === 'rejected') out = out.filter(v => !v.passed);
    const q = st.q.trim().toLowerCase();
    if (q) out = out.filter(v => (voteTitlePlain(v) + ' ' + (v.business || '')).toLowerCase().includes(q));
    // Ordering: a chosen margin sort is primary (with leaning as tiebreaker when
    // also active); otherwise leaning if a point is set; otherwise by date.
    const leanTie = (a, b) => st.target ? dist(a) - dist(b) : byDate(a, b);
    if (st.result === 'close') out.sort((a, b) => voteMargin(a).diff - voteMargin(b).diff || leanTie(a, b));
    else if (st.result === 'wide') out.sort((a, b) => voteMargin(b).diff - voteMargin(a).diff || leanTie(a, b));
    else if (st.target) out.sort((a, b) => dist(a) - dist(b) || byDate(a, b));
    else out.sort(byDate);
    return out;
  };

  const render = () => {
    const out = filtered();
    countEl.textContent = t('session.showing').replace('{n}', out.length).replace('{total}', votes.length);
    leanBtn.classList.toggle('active', !!st.target);
    leanBtn.setAttribute('aria-pressed', st.target ? 'true' : 'false');
    clearBtn.hidden = !(st.q || st.topic || st.result || st.target);
    if (!out.length) { listHost.innerHTML = `<div class="init-empty">${t('session.noMatch')}</div>`; return; }
    listHost.innerHTML = `<div class="svote-list">${out.map(sessionVoteHTML).join('')}</div>`;
    wireVoteCards(listHost, out);
  };

  searchEl.addEventListener('input', () => { st.q = searchEl.value; render(); });
  topicEl.addEventListener('change', () => { st.topic = topicEl.value; render(); });
  resultEl.addEventListener('change', () => { st.result = resultEl.value; render(); });
  leanBtn.addEventListener('click', () => {
    if (st.target) { st.target = null; render(); return; }
    openLeaningPicker(leanBtn, (pt) => { st.target = pt; render(); });
  });
  clearBtn.addEventListener('click', () => {
    st.q = ''; st.topic = ''; st.result = ''; st.target = null;
    searchEl.value = ''; topicEl.value = ''; resultEl.value = ''; render();
  });

  render();
}

/* ---- "Filter by leaning" popup: an interactive spectrum; clicking a point
   ranks the votes by how close their result sits to it. ---- */
let leanPicker = null;
function closeLeaningPicker() {
  if (leanPicker) { leanPicker.remove(); leanPicker = null; }
  document.removeEventListener('click', leanOutside, true);
  document.removeEventListener('keydown', leanEsc);
}
function leanOutside(e) { if (leanPicker && !leanPicker.contains(e.target)) closeLeaningPicker(); }
function leanEsc(e) { if (e.key === 'Escape') closeLeaningPicker(); }
function openLeaningPicker(anchor, onPick) {
  closeLeaningPicker();
  const dots = Object.values(state.data.parties).filter(p => p.spectrum).map(p =>
    `<circle cx="${p.spectrum.x}" cy="${100 - p.spectrum.y}" r="4.5" fill="${p.color}" opacity="0.55"><title>${p.abbr}</title></circle>`).join('');
  const el = document.createElement('div');
  el.className = 'lean-picker';
  el.innerHTML = `
    <div class="lean-picker-hint">${t('explore.leaningHint')}</div>
    <svg class="mini-spectrum lean-picker-svg" viewBox="-16 -16 132 132" role="img" aria-label="${escapeAttr(t('explore.leaning'))}">
      <line class="ms-axis" x1="0" y1="50" x2="100" y2="50"></line>
      <line class="ms-axis" x1="50" y1="0" x2="50" y2="100"></line>
      <text class="ms-lbl" x="-5" y="51" text-anchor="end">${t('spec.axisLeft')}</text>
      <text class="ms-lbl" x="105" y="51" text-anchor="start">${t('spec.axisRight')}</text>
      <text class="ms-lbl" x="50" y="-7" text-anchor="middle">${t('spec.axisTop')}</text>
      <text class="ms-lbl" x="50" y="109" text-anchor="middle">${t('spec.axisBottom')}</text>
      ${dots}
    </svg>`;
  document.body.appendChild(el);
  leanPicker = el;
  const svg = el.querySelector('svg');
  svg.addEventListener('click', (e) => {
    const rect = svg.getBoundingClientRect();
    const vb = svg.viewBox.baseVal;
    const vx = vb.x + (e.clientX - rect.left) / rect.width * vb.width;
    const vy = vb.y + (e.clientY - rect.top) / rect.height * vb.height;
    onPick({ x: Math.max(0, Math.min(100, vx)), y: Math.max(0, Math.min(100, 100 - vy)) });
    closeLeaningPicker();
  });
  const r = anchor.getBoundingClientRect();
  el.style.left = Math.max(8, Math.min(r.left, window.innerWidth - el.offsetWidth - 8)) + 'px';
  el.style.top = (r.bottom + 8) + 'px';
  setTimeout(() => document.addEventListener('click', leanOutside, true), 0);
  document.addEventListener('keydown', leanEsc);
}

function renderSessionPage(id) {
  ensureSessionsIndex().then(index => {
    const s = ((index && index.sessions) || []).find(x => String(x.id) === String(id));
    if (!s) { navigate('sessions'); return; }
    const meta = (index && index._meta) || {};
    const fetched = meta.fetchedAt ? meta.fetchedAt.slice(0, 10) : '';

    document.getElementById('session-emblem').innerHTML = icon(SEASON_ICON[s.season] || 'star');
    document.getElementById('session-title').textContent = sessionName(s);
    const lp = s.legislativePeriod ? ` · ${t('session.legislativePeriod').replace('{n}', s.legislativePeriod)}` : '';
    document.getElementById('session-dates').textContent = formatSessionDates(s.start, s.end) + lp;

    const content = document.getElementById('session-content');
    content.innerHTML = `
      <div class="session-watch">
        <div class="session-watch-text">
          <h3 class="canton-section-title" style="margin-top:0">${t('session.watchTitle')}</h3>
          <p class="canton-intro" style="margin-bottom:20px">${t('session.watchDesc')}</p>
          <div class="session-watch-links">
            <a class="resource-link" href="${youtubeSessionSearch(s)}" target="_blank" rel="noopener noreferrer">${t('session.watchSearch')} <span class="arrow">↗</span></a>
            <a class="resource-link" href="${PARL_YOUTUBE}" target="_blank" rel="noopener noreferrer">${t('session.watchChannel')} <span class="arrow">↗</span></a>
          </div>
        </div>
      </div>
      <h3 class="canton-section-title" style="margin-top:44px">${t('session.votesTitle')}${termHelp('finalVote')}</h3>
      <p class="session-votes-desc">${t('session.votesDesc')}</p>
      <p class="session-chamber-note">${t('session.chamberNote')}</p>
      <div id="session-votes-region"></div>
      <p class="detail-source" style="margin-top:28px">${t('session.source').replace('{date}', fetched)}</p>`;

    const region = document.getElementById('session-votes-region');
    Promise.all([ensureSessionFile(s.id), ensureSessionTranslations()]).then(([file]) => {
      const votes = (file && file.votes) || [];
      if (!votes.length) {
        region.innerHTML = `<div class="empty-state"><div class="empty-state-icon" aria-hidden="true">${icon('ballot')}</div><p>${t('session.noVotes')}</p></div>`;
        return;
      }
      mountVotesExplorer(region, votes);
    });
  });
}

/* ---- Votes page (#/votes): every recorded final vote, searchable ---- */
function renderVotesPage() {
  const intro = document.getElementById('votes-page-intro');
  const region = document.getElementById('votes-page-region');
  if (!intro || !region) return;
  intro.innerHTML = `<p class="canton-intro" style="margin-bottom:24px">${t('votes.desc')}</p>`;
  region.innerHTML = `<div class="init-empty">${t('votes.loading')}</div>`;

  // Load the index, then every per-session file, then flatten into one list.
  ensureSessionsIndex().then(index => {
    const sessions = ((index && index.sessions) || []).filter(s => (s.voteCount || 0) > 0);
    return Promise.all([
      ensureSessionTranslations(),
      ...sessions.map(s => ensureSessionFile(s.id).then(f => ({ s, f }))),
    ]);
  }).then(results => {
    const files = results.slice(1);
    const votes = [];
    files.forEach(({ f }) => { (f && f.votes || []).forEach(v => votes.push(v)); });
    if (!votes.length) {
      region.innerHTML = `<div class="init-empty">${t('session.empty')}</div>`;
      return;
    }
    mountVotesExplorer(region, votes);
  });
}

/* ============================================================
   Router (hash-based, shareable URLs)
   ============================================================ */
/* ============================================================
   Info / legal pages (privacy, legal notice, sources, about, …)
   Content lives in data/legal.json (trusted first-party HTML);
   Romansh falls back to German. Loaded once, on demand.
   ============================================================ */
const INFO_SLUGS = ['about', 'methodology', 'sources', 'privacy', 'legal', 'contact'];
let legalPromise = null;
function loadLegal() {
  if (!legalPromise) {
    legalPromise = fetch('data/legal.json').then(r => (r.ok ? r.json() : null)).catch(() => null);
  }
  return legalPromise;
}

function renderInfoPage(slug) {
  const titleEl = document.getElementById('info-title');
  const contentEl = document.getElementById('info-content');
  const navEl = document.getElementById('info-nav');
  if (!titleEl || !contentEl) return;
  loadLegal().then(data => {
    const page = data && data.pages && data.pages[slug];
    if (!page) {
      titleEl.textContent = '';
      contentEl.innerHTML = `<p>${t('search.noResults')}</p>`;
      if (navEl) navEl.innerHTML = '';
      return;
    }
    const lang = state.lang;
    const pick = (obj) => (obj && (obj[lang] || obj.de || obj.en)) || '';
    const contact = (data._meta && data._meta.contactEmail) || '';
    const contactHtml = contact.includes('@')
      ? `<a href="mailto:${encodeURIComponent(contact)}">${escapeAttr(contact)}</a>`
      : escapeAttr(contact);

    titleEl.textContent = pick(page.title);
    // Romansh pages fall back to German; note that so it isn't mistaken for an oversight.
    const rmNote = (lang === 'rm' && !(page.body && page.body.rm))
      ? '<p class="info-updated">Questa pagina è disponibla per tudestg.</p>' : '';
    contentEl.innerHTML = rmNote + pick(page.body).split('{{contact}}').join(contactHtml);

    if (navEl) {
      navEl.innerHTML = INFO_SLUGS
        .filter(s => s !== slug && data.pages[s])
        .map(s => `<a href="#/page/${s}">${escapeAttr(pick(data.pages[s].title))}</a>`)
        .join('');
    }
  });
}

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [view, id] = raw.split('/');
  return { view: view || 'home', id: id || null };
}

function navigate(path) {
  location.hash = path ? `#/${path}` : '#/';
}

function showView(name) {
  document.getElementById('home-content').style.display = name === 'home' ? 'block' : 'none';
  document.getElementById('canton-page').classList.toggle('active', name === 'canton');
  document.getElementById('party-page').classList.toggle('active', name === 'party');
  document.getElementById('initiative-page').classList.toggle('active', name === 'initiative');
  document.getElementById('sessions-page').classList.toggle('active', name === 'sessions');
  document.getElementById('session-page').classList.toggle('active', name === 'session');
  document.getElementById('votes-page').classList.toggle('active', name === 'votes');
  document.getElementById('info-page').classList.toggle('active', name === 'info');
  document.getElementById('donor-page').classList.toggle('active', name === 'donor');
}

function handleRoute() {
  const { view, id } = parseHash();
  if (view === 'canton' && id) {
    renderCantonPage(id);
    showView('canton');
  } else if (view === 'party' && id) {
    renderPartyPage(id);
    showView('party');
  } else if (view === 'initiative' && id) {
    renderInitiativePage(id);
    showView('initiative');
  } else if (view === 'session' && id) {
    renderSessionPage(id);
    showView('session');
  } else if (view === 'sessions') {
    renderSessionsPage();
    showView('sessions');
  } else if (view === 'votes') {
    renderVotesPage();
    showView('votes');
  } else if (view === 'page' && id) {
    renderInfoPage(id);
    showView('info');
  } else if (view === 'donor' && id) {
    renderDonorPage(decodeURIComponent(id));
    showView('donor');
  } else {
    showView('home');
  }
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function scrollToSection(id) {
  if (parseHash().view !== 'home') {
    navigate('');
    // wait for home to show
    setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }), 60);
  } else {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  }
  closeMobileMenu();
}

/* ============================================================
   Scroll reveal
   ============================================================ */
function initScrollReveal() {
  if (!('IntersectionObserver' in window)) {
    document.querySelectorAll('.reveal').forEach(el => el.classList.add('visible'));
    return;
  }
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); } });
  }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });
  document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
}

/* ============================================================
   Mobile menu
   ============================================================ */
function closeMobileMenu() { document.getElementById('navbar').classList.remove('menu-open'); }

/* ============================================================
   Wire up events
   ============================================================ */
function bindEvents() {
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.addEventListener('click', () => setLang(btn.dataset.lang));
  });
  document.querySelectorAll('[data-scroll]').forEach(el => {
    el.addEventListener('click', () => scrollToSection(el.dataset.scroll));
  });
  document.querySelectorAll('[data-home]').forEach(el => {
    el.addEventListener('click', (e) => { e.preventDefault(); navigate(''); });
  });
  document.querySelectorAll('[data-nav]').forEach(el => {
    el.addEventListener('click', (e) => { e.preventDefault(); navigate(el.dataset.nav); closeMobileMenu(); });
  });

  const toggle = document.getElementById('nav-toggle');
  toggle.addEventListener('click', () => document.getElementById('navbar').classList.toggle('menu-open'));

  // Votes lifecycle tabs + search
  document.querySelectorAll('#initiatives .filter-btn[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.tab = btn.dataset.tab;
      document.querySelectorAll('#initiatives .filter-btn[data-tab]').forEach(b => {
        b.classList.toggle('active', b === btn);
        b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
      });
      renderInitiatives();
    });
  });
  const search = document.getElementById('init-search');
  search.addEventListener('input', () => { state.search = search.value; renderInitiatives(); });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMobileMenu();
  });

  initScaleReadouts();
  initGlossary();
  setupSearch();

  // Nav shrink on scroll
  window.addEventListener('scroll', () => {
    document.getElementById('navbar').classList.toggle('scrolled', window.scrollY > 20);
  });

  // Routing
  window.addEventListener('hashchange', handleRoute);
}

/* ============================================================
   Boot
   ============================================================ */
async function init() {
  configureShare({ t, lang: () => state.lang });
  try {
    await loadData();
  } catch (err) {
    document.getElementById('load-error').style.display = 'block';
    console.error('Failed to load data', err);
    return;
  }

  // Language: saved → browser → en
  let lang = 'en';
  try { lang = localStorage.getItem('politikch-lang') || navigator.language?.slice(0, 2) || 'en'; } catch (e) {}
  if (!SUPPORTED_LANGS.includes(lang)) lang = 'en';
  state.lang = lang;

  buildMap();
  applyStaticTranslations();
  document.querySelectorAll('.lang-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === lang);
    b.setAttribute('aria-pressed', b.dataset.lang === lang ? 'true' : 'false');
  });

  const ncSeats = {};
  const csSeats = {};
  Object.entries(state.data.parties).forEach(([k, p]) => {
    if (p.ncSeats) ncSeats[k] = p.ncSeats;
    if (p.csSeats) csSeats[k] = p.csSeats;
  });

  renderHemicycle('nc-hemicycle', ncSeats, 200);
  renderLegend('nc-legend', ncSeats);
  renderHemicycle('cs-hemicycle', csSeats, 46);
  renderLegend('cs-legend', csSeats);
  renderFederalCouncil();
  renderSpectrum();
  // Share buttons on the home-page graphs (mounted once; specs read live data).
  shareChart(document.getElementById('nc-hemicycle').closest('.chamber-card'), () => ({
    kind: 'hemicycle', title: t('parl.nc'), subtitle: t('parl.ncsub'), total: 200,
    seats: seatSpecFromSeats(chamberSeats('nc')),
  }));
  shareChart(document.getElementById('cs-hemicycle').closest('.chamber-card'), () => ({
    kind: 'hemicycle', title: t('parl.cs'), subtitle: t('parl.cssub'), total: 46,
    seats: seatSpecFromSeats(chamberSeats('cs')),
  }));
  shareChart(document.querySelector('.council-card'), () => shareCouncilSpec());
  shareChart(document.getElementById('spectrum-chart'), () => spectrumSpec(t('spec.title'), '', {}));
  renderInitiatives();
  initScrollReveal();
  bindEvents();
  handleRoute();
}

document.addEventListener('DOMContentLoaded', init);
