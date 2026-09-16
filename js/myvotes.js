/* ============================================================
   My votes — personal, on-device voting + optional community poll
   ============================================================
   Two clearly-separated things live here:

   1. Your own vote. Stored only in localStorage on this device (never sent
      anywhere). Powers the "My profile" page (participation, priorities,
      party alignment). This is what makes the site's voting feature work with
      no backend at all.

   2. The community poll. OPTIONAL. When a backend is configured (js/config.js
      → POLL_API) an anonymous choice — no account, no identifier — is sent so
      the site can show how others voted on present/future items and on session
      votes. Until a backend is set, the poll shows an honest "not connected"
      state; it never invents numbers.

   Everything a visitor sees must make the official/unofficial distinction
   obvious: official results use solid bars, community polls use striped bars
   and carry an "unofficial poll" label. */

import { POLL_API } from './config.js?v=20260916f';

let t = (k) => k;
let esc = (s) => String(s);

export function configureVotes(deps) {
  if (deps.t) t = deps.t;
  if (deps.escapeAttr) esc = deps.escapeAttr;
}

/* ---- Storage ------------------------------------------------------------ */
const STORE_KEY = 'politikch-votes';
const STORE_VER = 1;

function readStore() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return { v: STORE_VER, initiatives: {}, sessions: {} };
    const d = JSON.parse(raw);
    d.initiatives = d.initiatives || {};
    d.sessions = d.sessions || {};
    return d;
  } catch (e) {
    return { v: STORE_VER, initiatives: {}, sessions: {} };
  }
}
function writeStore(d) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(d)); } catch (e) { /* ignore */ }
}
function bucket(kind) { return kind === 'session' ? 'sessions' : 'initiatives'; }

export function getVote(kind, id) {
  const e = readStore()[bucket(kind)][id];
  return e ? e.c : null;
}
export function getAllVotes() { return readStore(); }

// Set (or clear, when choice is null) the user's vote. `meta` may carry, for a
// session vote, { parties: {SVP:'yes',…}, topics:[…] } so the profile can score
// alignment without re-fetching the session file.
export function setVote(kind, id, choice, meta) {
  const d = readStore();
  const b = d[bucket(kind)];
  if (choice == null) {
    delete b[id];
  } else {
    b[id] = Object.assign({}, b[id], { c: choice, t: Date.now() });
    if (meta && meta.parties) b[id].p = meta.parties;
    if (meta && meta.topics) b[id].topics = meta.topics;
  }
  writeStore(d);
  document.dispatchEvent(new CustomEvent('politikch:votechange', { detail: { kind, id, choice } }));
}

// What the poll server currently believes this device voted, kept in a SEPARATE
// map so it survives clearing the vote (so a clear can still be decremented).
const PUSHED_KEY = 'politikch-votes-pushed';
function readPushed() { try { return JSON.parse(localStorage.getItem(PUSHED_KEY) || '{}') || {}; } catch (e) { return {}; } }
function getPushed(kind, id) { const p = readPushed(); const k = kind + '/' + id; return (k in p) ? p[k] : null; }
function setPushed(kind, id, choice) {
  const p = readPushed(); const k = kind + '/' + id;
  if (choice == null) delete p[k]; else p[k] = choice;
  try { localStorage.setItem(PUSHED_KEY, JSON.stringify(p)); } catch (e) { /* ignore */ }
}

export function countVotes() {
  const d = readStore();
  return Object.keys(d.initiatives).length + Object.keys(d.sessions).length;
}

/* ---- Community poll client ---------------------------------------------- */
export function pollEnabled() { return !!POLL_API; }

async function fetchJSON(url, opts) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 6000);
  try {
    const r = await fetch(url, Object.assign({ signal: ctrl.signal }, opts));
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  } finally { clearTimeout(timer); }
}
async function getTally(kind, id) {
  if (!POLL_API) return null;
  return fetchJSON(`${POLL_API}/tally?type=${encodeURIComponent(kind)}&id=${encodeURIComponent(id)}`);
}
async function castPoll(kind, id, choice, prev, keepalive) {
  if (!POLL_API) return null;
  return fetchJSON(`${POLL_API}/vote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: kind, id, choice, prev: prev || null }),
    keepalive: !!keepalive,
  });
}

/* ---- Vote widget -------------------------------------------------------- */
// Choices are Yes / No for both initiatives and session votes, so alignment
// scoring is uniform. opts.poll marks an item as poll-eligible (present/future
// initiative, or any session vote). opts.meta carries session party majorities.
export function voteWidgetHTML(kind, id, opts) {
  opts = opts || {};
  const poll = opts.poll ? '1' : '';
  const meta = opts.meta ? esc(JSON.stringify(opts.meta)) : '';
  return `<div class="vote-widget" data-vk="${esc(kind)}" data-vi="${esc(id)}" data-poll="${poll}"${meta ? ` data-meta="${meta}"` : ''}></div>`;
}

function choiceLabel(c) { return c === 'yes' ? t('mine.yes') : t('mine.no'); }

function pollBarsHTML(tally) {
  const yes = (tally && tally.yes) || 0;
  const no = (tally && tally.no) || 0;
  const total = yes + no;
  const py = total ? Math.round(yes / total * 100) : 0;
  const pn = total ? 100 - py : 0;
  const nfmt = new Intl.NumberFormat();
  return `
    <div class="poll-block" role="img" aria-label="${esc(t('mine.pollAria').replace('{yes}', py).replace('{no}', pn))}">
      <div class="poll-head">
        <span class="poll-tag">${t('mine.pollTag')}</span>
        <span class="poll-total">${total ? t('mine.pollCount').replace('{n}', nfmt.format(total)) : t('mine.pollEmpty')}</span>
      </div>
      <div class="poll-bar">
        <span class="poll-seg poll-seg-yes" style="width:${py}%"></span>
        <span class="poll-seg poll-seg-no" style="width:${pn}%"></span>
      </div>
      <div class="poll-legend">
        <span class="poll-k poll-k-yes">${t('mine.yes')} ${py}%</span>
        <span class="poll-k poll-k-no">${t('mine.no')} ${pn}%</span>
      </div>
    </div>`;
}

function renderWidget(el) {
  const kind = el.dataset.vk;
  const id = el.dataset.vi;
  const isPoll = el.dataset.poll === '1';
  const choice = getVote(kind, id);
  const voted = choice === 'yes' || choice === 'no';

  const btn = (c) => `<button type="button" class="vote-btn vote-btn-${c}${choice === c ? ' active' : ''}" data-choice="${c}" aria-pressed="${choice === c ? 'true' : 'false'}">${choiceLabel(c)}</button>`;

  let html = `
    <div class="vote-widget-head">
      <span class="vote-widget-label">${t('mine.castLabel')}</span>
      <span class="unofficial-chip" title="${esc(t('mine.unofficialHint'))}">${t('mine.unofficialChip')}</span>
    </div>
    <div class="vote-choices" role="group" aria-label="${esc(t('mine.castLabel'))}">
      ${btn('yes')}${btn('no')}
    </div>`;

  if (voted) {
    html += `<div class="vote-you">${t('mine.youVoted').replace('{choice}', `<strong>${choiceLabel(choice)}</strong>`)} · <button type="button" class="vote-clear" data-clear>${t('mine.clear')}</button></div>`;
  }
  if (isPoll) {
    html += `<div class="poll-slot" data-poll-slot>${
      pollEnabled()
        ? `<div class="poll-loading">${t('mine.pollLoading')}</div>`
        : `<div class="poll-offline">${t('mine.pollOffline')}</div>`
    }</div>`;
  }
  el.innerHTML = html;

  el.querySelectorAll('.vote-btn').forEach(b => {
    b.addEventListener('click', () => onPick(el, b.dataset.choice));
  });
  const clr = el.querySelector('[data-clear]');
  if (clr) clr.addEventListener('click', () => onPick(el, null));

  if (isPoll && pollEnabled()) loadPoll(el);
}

function metaOf(el) {
  if (!el.dataset.meta) return null;
  try { return JSON.parse(el.dataset.meta); } catch (e) { return null; }
}

function onPick(el, choice) {
  const kind = el.dataset.vk;
  const id = el.dataset.vi;
  const current = getVote(kind, id);
  const next = (choice === current) ? null : choice; // click the active choice to undo
  setVote(kind, id, next, metaOf(el));
  renderWidget(el); // the visitor's own choice updates instantly, on-device
  // The community poll is NOT contacted on every click. We debounce and send
  // only the NET settled result, so spamming yes/no/yes/no still costs the
  // server at most one write once the visitor stops.
  if (el.dataset.poll === '1' && pollEnabled()) scheduleSync(kind, id);
}

/* ---- Debounced, coalesced poll sync ------------------------------------- */
const SYNC_DEBOUNCE_MS = 5000;   // wait this long after the last click
const MIN_SYNC_GAP_MS = 10000;   // and never sync one item more often than this
const _syncTimers = {};
const _lastSyncAt = {};
function scheduleSync(kind, id) {
  const key = kind + '/' + id;
  if (_syncTimers[key]) clearTimeout(_syncTimers[key]);
  const sinceLast = Date.now() - (_lastSyncAt[key] || 0);
  const wait = Math.max(SYNC_DEBOUNCE_MS, MIN_SYNC_GAP_MS - sinceLast);
  _syncTimers[key] = setTimeout(() => flushSync(kind, id), wait);
}
function flushSync(kind, id, keepalive) {
  const key = kind + '/' + id;
  if (_syncTimers[key]) { clearTimeout(_syncTimers[key]); delete _syncTimers[key]; }
  const current = getVote(kind, id);      // null if the item was cleared
  const pushed = getPushed(kind, id);
  if (current === pushed) return;         // nothing new to tell the server
  _lastSyncAt[key] = Date.now();
  castPoll(kind, id, current, pushed, keepalive).then(tally => {
    setPushed(kind, id, current);
    if (tally) { _tallyCache[key] = { at: Date.now(), tally }; paintPollByKey(key, tally); }
  });
}
// Flush everything still pending when the page is hidden/closed, using
// keepalive so the final write survives navigation.
function flushAllPending(keepalive) {
  Object.keys(_syncTimers).forEach(key => {
    const [kind, id] = key.split('/');
    flushSync(kind, id, keepalive);
  });
}
if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => flushAllPending(true));
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flushAllPending(true); });
}

/* ---- Poll reads (cached briefly so re-renders don't refetch) ------------ */
const _tallyCache = {};
const TALLY_TTL_MS = 60000;
async function loadPoll(el) {
  const slot = el.querySelector('[data-poll-slot]');
  if (!slot) return;
  const key = el.dataset.vk + '/' + el.dataset.vi;
  const cached = _tallyCache[key];
  if (cached && Date.now() - cached.at < TALLY_TTL_MS) { paintPoll(el, cached.tally); return; }
  const tally = await getTally(el.dataset.vk, el.dataset.vi);
  if (tally) { _tallyCache[key] = { at: Date.now(), tally }; paintPoll(el, tally); }
  else slot.innerHTML = `<div class="poll-offline">${t('mine.pollUnavailable')}</div>`;
}
function paintPoll(el, tally) {
  const slot = el.querySelector('[data-poll-slot]');
  if (slot) slot.innerHTML = pollBarsHTML(tally);
}
function paintPollByKey(key, tally) {
  document.querySelectorAll('.vote-widget').forEach(el => {
    if (el.dataset.vk + '/' + el.dataset.vi === key) paintPoll(el, tally);
  });
}

// Hydrate every .vote-widget under root.
export function wireVoteWidgets(root) {
  (root || document).querySelectorAll('.vote-widget').forEach(el => {
    if (el.dataset.wired) return;
    el.dataset.wired = '1';
    renderWidget(el);
  });
}
