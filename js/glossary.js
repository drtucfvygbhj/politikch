/* ============================================================
   Glossary — the "Define" pop-up and the #/glossary page.
   Terms live in data/glossary.json: institutions and procedures only
   (no parties, people or ideology words — GUARDRAILS POL-04/06).
   Definitions are written by the editor; an entry without one is listed
   as "explanation coming". The 15 older explanations stay in i18n.json
   (`gloss.*`) and an entry points to them with `definitionKey`.

   Looking a word up happens entirely in the browser: the highlighted text
   is never sent anywhere and never counted (PRIV-01/05).
   ============================================================ */

let C = null;                       // context from app.js: { t, state, escapeAttr, openReport }
export function configureGlossary(ctx) { C = ctx; }

const LANGS = ['en', 'de', 'fr', 'it'];
// Romansh has no glossary text of its own yet: German, with the language chip.
const textLang = () => (C.state.lang === 'rm' ? 'de' : C.state.lang);
const t = (k) => C.t(k);
function escapeAttr(s) { return C.escapeAttr(s); }
function tf(k, vars) {
  let s = t(k);
  Object.keys(vars).forEach(a => { s = s.split('{' + a + '}').join(String(vars[a])); });
  return s;
}

let glossaryPromise = null;
let terms = [];
const byId = new Map();
let index = null;                   // lang -> Map(normalised form -> [ids]); '*stem' maps too

export function loadGlossary() {
  if (!glossaryPromise) {
    glossaryPromise = fetch('data/glossary.json?v=20260925a')
      .then(r => (r.ok ? r.json() : { terms: [] }))
      .catch(() => ({ terms: [] }))
      .then(d => {
        terms = Array.isArray(d.terms) ? d.terms : [];
        terms.forEach(e => byId.set(e.id, e));
        index = buildIndex();
        return terms;
      });
  }
  return glossaryPromise;
}

/* ---- matching ---- */

export function normalise(s) {
  return String(s || '')
    .normalize('NFC')
    .replace(/[‘’ʼ]/g, "'")
    .replace(/[­​]/g, '')                      // soft hyphens, zero-width spaces
    .replace(/[‐-―]/g, '-')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^[\s"'«»„“”‚‘()[\]{}.,;:!?¿¡…*/-]+|[\s"'«»„“”‚‘()[\]{}.,;:!?¿¡…*/-]+$/g, '')
    .toLowerCase();
}

// One common ending stripped from each word, so plurals and case endings find
// their entry (Volksinitiativen → volksinitiativ ← Volksinitiative; initiatives
// populaires ↔ initiative populaire). Both sides are stemmed the same way;
// nothing fuzzier than that.
const ENDINGS = {
  en: ['es', 's'],
  de: ['ern', 'en', 'er', 'es', 'e', 'n', 's'],
  fr: ['es', 'x', 's', 'e'],
  it: ['i', 'e', 'a', 'o'],
};
function stemWord(w, lang) {
  for (const end of ENDINGS[lang] || []) {
    if (w.endsWith(end) && w.length - end.length >= 4) return w.slice(0, -end.length);
  }
  return w;
}
function stem(form, lang) {
  return form.split(' ').map(w => stemWord(w, lang)).join(' ');
}

function formsOf(e, lang) {
  const out = [];
  const hw = e.headword && e.headword[lang];
  if (hw) out.push(hw);
  ((e.forms && e.forms[lang]) || []).forEach(f => out.push(f));
  return out;
}

function buildIndex() {
  const idx = {};
  LANGS.forEach(lang => {
    const exact = new Map(), stems = new Map();
    const add = (m, k, id) => { if (!k) return; const a = m.get(k) || []; if (!a.includes(id)) a.push(id); m.set(k, a); };
    terms.forEach(e => {
      formsOf(e, lang).concat((e.alsoMatches && e.alsoMatches[lang]) || []).forEach(f => {
        const n = normalise(f);
        add(exact, n, e.id);
        add(stems, stem(n, lang), e.id);
      });
    });
    idx[lang] = { exact, stems };
  });
  return idx;
}

// The entries a highlighted text could mean: exact forms in the reading
// language, then in the other languages, then the same with one ending
// stripped from each word.
export function lookup(text) {
  const q = normalise(text);
  if (!q || !index) return [];
  const order = [textLang()].concat(LANGS.filter(l => l !== textLang()));
  const tries = [
    (lang) => index[lang].exact.get(q),
    (lang) => index[lang].exact.get(stem(q, lang)),     // Kantone → kanton = Kanton
    (lang) => index[lang].stems.get(stem(q, lang)),
  ];
  for (const get of tries) {
    for (const lang of order) {
      const ids = get(lang);
      if (ids && ids.length) return ids.map(id => byId.get(id)).filter(Boolean);
    }
  }
  return [];
}

/* ---- text of an entry ---- */

function headword(e) { return (e.headword && (e.headword[textLang()] || e.headword.en)) || e.id; }
function definition(e) {
  if (e.definitionKey) {
    const k = 'gloss.' + e.definitionKey;
    const s = t(k);
    return s === k ? '' : s;
  }
  return (e.definition && e.definition[textLang()]) || '';
}
// Shown in another language than the page's (Romansh → German): a fixed chip.
const RM_CHIP = ' <span class="ai-ov-langchip">DE</span>';
function fallbackChip(e) {
  return C.state.lang === 'rm' && !e.definitionKey ? RM_CHIP : '';
}
function sourceOf(e) {
  const s = e.source;
  if (!s || !s.url) return null;
  const url = s.url.split('{lang}').join(textLang());
  if (!/^https:\/\//.test(url)) return null;
  return { url, label: (s.label && (s.label[textLang()] || s.label.en)) || url };
}
function alsoCalled(e) {
  const hw = normalise(headword(e));
  const seen = new Set([hw]);
  const out = [];
  ((e.forms && e.forms[textLang()]) || []).forEach(f => {
    const n = normalise(f);
    if (!seen.has(n)) { seen.add(n); out.push(f); }
  });
  return out;
}

/* ---- the pop-up ---- */

let pop = null, popTrigger = null;

export function closeDefinition() {
  if (!pop) return;
  pop.remove();
  pop = null;
  document.removeEventListener('keydown', onPopKey, true);
  document.removeEventListener('mousedown', onPopOutside, true);
  if (popTrigger && popTrigger.focus && document.contains(popTrigger)) popTrigger.focus();
  popTrigger = null;
}
function onPopKey(e) { if (e.key === 'Escape') { e.stopPropagation(); closeDefinition(); } }
function onPopOutside(e) { if (pop && !pop.contains(e.target) && !e.target.closest('.sel-tools')) closeDefinition(); }

// Show the pop-up for a highlighted text. `rect` is where the text sits on screen.
export function openDefinition(text, rect, trigger) {
  return loadGlossary().then(() => {
    const found = lookup(text);
    if (found.length === 1) render(entryHTML(found[0]));
    else if (found.length > 1) render(whichHTML(found));
    else render(noneHTML(text));
    place(rect);
    popTrigger = trigger || null;
    wire(text);
  });
}

function shell(inner) {
  return `<button type="button" class="def-close" aria-label="${escapeAttr(t('def.close'))}">×</button>` + inner;
}

function entryHTML(e) {
  const def = definition(e);
  const src = sourceOf(e);
  const also = alsoCalled(e);
  const related = (e.related || []).map(id => byId.get(id)).filter(Boolean);
  let h = `<p class="def-kicker">${escapeAttr(t('def.kicker'))}</p>`;
  h += `<h2 class="def-term" id="def-h">${escapeAttr(headword(e))}</h2>`;
  if (also.length) h += `<p class="def-also">${escapeAttr(t('def.alsoCalled'))}: ${escapeAttr(also.join(' · '))}</p>`;
  h += def
    ? '<p class="def-text">' + escapeAttr(def) + fallbackChip(e) + '</p>'
    : `<p class="def-text def-pending">${escapeAttr(t('def.pending'))}</p>`;
  if (related.length) {
    h += `<p class="def-rel"><span>${escapeAttr(t('def.related'))}:</span> ` +
      related.map(r => `<button type="button" class="def-chip" data-def-id="${escapeAttr(r.id)}">${escapeAttr(headword(r))}</button>`).join('') + '</p>';
  }
  if (src) h += `<p class="def-src">${escapeAttr(t('def.source'))}: <a href="${escapeAttr(src.url)}" target="_blank" rel="noopener noreferrer">${escapeAttr(src.label)}</a></p>`;
  h += '<p class="def-foot">';
  if (def) h += `<span>${escapeAttr(t('def.label'))} · <a href="#/page/methodology">${escapeAttr(t('footer.method'))}</a></span>`;
  h += `<a href="#/glossary" class="def-all">${escapeAttr(t('def.all'))}</a></p>`;
  return h;
}

function whichHTML(list) {
  return `<p class="def-kicker">${escapeAttr(t('def.kicker'))}</p><h2 class="def-term" id="def-h">${escapeAttr(t('def.which'))}</h2>` +
    '<ul class="def-which">' + list.map(e => `<li><button type="button" class="def-chip" data-def-id="${escapeAttr(e.id)}">${escapeAttr(headword(e))}</button></li>`).join('') + '</ul>';
}

function noneHTML(text) {
  const shown = normalise(text) ? String(text).trim().slice(0, 60) : '';
  let h = `<p class="def-kicker">${escapeAttr(t('def.kicker'))}</p>`;
  h += `<h2 class="def-term def-term-none" id="def-h">${escapeAttr(tf('def.none', { term: shown }))}</h2>`;
  h += `<div class="def-actions"><button type="button" class="def-btn" data-def-search>${escapeAttr(t('def.search'))}</button>`;
  h += `<button type="button" class="def-btn def-btn-main" data-def-suggest>${escapeAttr(t('def.suggest'))}</button>`;
  h += `</div><p class="def-foot"><a href="#/glossary" class="def-all">${escapeAttr(t('def.all'))}</a></p>`;
  return h;
}

function render(inner) {
  if (!pop) {
    pop = document.createElement('div');
    pop.className = 'def-pop';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-labelledby', 'def-h');
    document.body.appendChild(pop);
    document.addEventListener('keydown', onPopKey, true);
    document.addEventListener('mousedown', onPopOutside, true);
  }
  pop.innerHTML = shell(inner);
}

// Desktop: next to the highlighted text. Phones: a sheet along the bottom (CSS).
function place(rect) {
  if (!pop) return;
  pop.style.left = pop.style.top = '';
  if (window.matchMedia('(max-width: 640px)').matches || !rect) return;
  const w = pop.offsetWidth, h = pop.offsetHeight, gap = 12;
  let left = rect.left + rect.width / 2 - w / 2;
  left = Math.max(12, Math.min(left, window.innerWidth - w - 12));
  let top = rect.bottom + gap;
  if (top + h > window.innerHeight - 12) top = Math.max(12, rect.top - gap - h);
  pop.style.left = Math.round(left) + 'px';
  pop.style.top = Math.round(top) + 'px';
}

function wire(text) {
  if (!pop) return;
  pop.querySelector('.def-close').addEventListener('click', closeDefinition);
  pop.querySelectorAll('[data-def-id]').forEach(b => b.addEventListener('click', () => {
    const e = byId.get(b.dataset.defId);
    if (!e) return;
    const r = pop.getBoundingClientRect();
    render(entryHTML(e));
    place({ left: r.left, width: r.width, top: r.top, bottom: r.top });
    wire(text);
    pop.querySelector('.def-close').focus();
  }));
  pop.querySelectorAll('a[href^="#/"]').forEach(a => a.addEventListener('click', () => closeDefinition()));
  pop.querySelector('[data-def-search]')?.addEventListener('click', () => {
    const input = document.getElementById('site-search');
    closeDefinition();
    if (!input) return;
    input.value = String(text).trim().slice(0, 60);
    input.focus();
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  pop.querySelector('[data-def-suggest]')?.addEventListener('click', () => {
    closeDefinition();
    C.openReport({ type: 'definition', quote: text });
  });
  setTimeout(() => pop && pop.querySelector('.def-close').focus({ preventScroll: true }), 0);
}

/* ---- #/glossary ---- */

const CATEGORIES = ['institutions', 'parliament', 'votes', 'elections', 'federalism', 'finance'];

export function renderGlossaryPage() {
  const titleEl = document.getElementById('glossary-title');
  const leadEl = document.getElementById('glossary-lead');
  const host = document.getElementById('glossary-content');
  if (!titleEl || !host) return;
  titleEl.textContent = t('glossary.title');
  if (leadEl) leadEl.textContent = t('glossary.lead');
  loadGlossary().then(() => {
    const locale = { en: 'en-CH', de: 'de-CH', fr: 'fr-CH', it: 'it-CH' }[textLang()];
    host.innerHTML =
      `<label class="gl-search-label" for="gl-search">${escapeAttr(t('glossary.search'))}</label>` +
      `<input type="search" id="gl-search" class="init-search gl-search" autocomplete="off" placeholder="${escapeAttr(t('glossary.search'))}">` +
      '<div id="gl-list"></div>';
    const list = host.querySelector('#gl-list');
    const draw = (q) => {
      const nq = normalise(q);
      const hit = (e) => !nq || formsOf(e, textLang()).concat(formsOf(e, 'en')).some(f => normalise(f).includes(nq));
      const html = CATEGORIES.map(cat => {
        const items = terms.filter(e => e.category === cat && hit(e))
          .sort((a, b) => headword(a).localeCompare(headword(b), locale));
        if (!items.length) return '';
        return `<section class="gl-cat"><h2 class="info-h">${escapeAttr(t('glossary.cat.' + cat))}</h2><dl class="gl-dl">` +
          items.map(e => {
            const def = definition(e);
            const src = sourceOf(e);
            return `<div class="gl-item" id="gl-${escapeAttr(e.id)}"><dt>${escapeAttr(headword(e))}</dt><dd>` +
              (def ? escapeAttr(def) + fallbackChip(e) : `<span class="def-pending">${escapeAttr(t('glossary.pendingShort'))}</span>`) +
              (src ? ` <a class="gl-src" href="${escapeAttr(src.url)}" target="_blank" rel="noopener noreferrer">${escapeAttr(src.label)}</a>` : '') +
              '</dd></div>';
          }).join('') + '</dl></section>';
      }).join('');
      list.innerHTML = html || `<p class="init-empty">${escapeAttr(t('glossary.empty'))}</p>`;
    };
    draw('');
    host.querySelector('#gl-search').addEventListener('input', (e) => draw(e.target.value));
  });
}
