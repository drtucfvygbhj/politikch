/* ============================================================
   Highlight toolbar — appears only while text on the page is highlighted,
   with "Define" (js/glossary.js) and "Report" (js/report.js).
   On every device it sits just below the highlighted text, so it doesn't
   cover the phone's own copy/paste menu, which opens above it.

   Never shown for text in form fields, dialogs, the menu, or on maps and
   charts (anything marked data-no-select-tools, and every <svg>). Nothing
   about the highlighted text leaves the browser: Report opens a draft in the
   visitor's own email app, which they may send or not.
   ============================================================ */
import { openDefinition, closeDefinition, loadGlossary } from './glossary.js?v=20260925a';
import { openReport } from './report.js?v=20260925a';

let C = null;                       // context from app.js: { t, escapeAttr }
let bar = null;
let current = null;                 // { text, rect } of the highlight the bar belongs to
let timer = 0;
let pressing = false;               // a toolbar button is being pressed: keep the bar

const DEFINE_MAX_CHARS = 60, DEFINE_MAX_WORDS = 4, REPORT_MAX_CHARS = 300;
const EXCLUDE = 'input, textarea, select, button, [contenteditable=""], [contenteditable="true"], svg, '
  + '[data-no-select-tools], .sel-tools, .def-pop, .contact-overlay, .gloss-tip, #n-nav, .n-mast, .search-results';


function escapeAttr(s) { return C.escapeAttr(s); }

export function initSelectTools(ctx) {
  C = ctx;
  document.addEventListener('selectionchange', () => {
    if (pressing) return;
    // Hide while the highlight is still being dragged; show once it settles.
    hide();
    clearTimeout(timer);
    timer = setTimeout(update, matchMedia('(pointer: coarse)').matches ? 450 : 220);
  });
  window.addEventListener('scroll', () => { if (bar && !bar.hidden) position(); }, { passive: true });
  window.addEventListener('resize', () => { if (bar && !bar.hidden) position(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
}

function excluded(node) {
  const el = node && (node.nodeType === 1 ? node : node.parentElement);
  return !el || !!el.closest(EXCLUDE);
}

function selectionInfo() {
  const sel = window.getSelection && window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
  const text = sel.toString().replace(/\s+/g, ' ').trim();
  if (!text) return null;
  if (excluded(sel.anchorNode) || excluded(sel.focusNode)) return null;
  const range = sel.getRangeAt(0);
  const rects = [...range.getClientRects()].filter(r => r.width || r.height);
  if (!rects.length) return null;
  return { text, range, last: rects[rects.length - 1], box: range.getBoundingClientRect() };
}

function canDefine(text) {
  return text.length <= DEFINE_MAX_CHARS && text.split(' ').length <= DEFINE_MAX_WORDS;
}

function ensureBar() {
  if (bar) return bar;
  bar = document.createElement('div');
  bar.className = 'sel-tools';
  bar.setAttribute('role', 'toolbar');
  bar.hidden = true;
  document.body.appendChild(bar);
  // Keep the highlight (and the bar) while a button is pressed: a tap can
  // clear the phone's selection before the click arrives.
  bar.addEventListener('pointerdown', (e) => { pressing = true; e.preventDefault(); });
  bar.addEventListener('mousedown', (e) => e.preventDefault());
  document.addEventListener('pointerup', () => { setTimeout(() => { pressing = false; }, 400); }, true);
  bar.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-act]');
    pressing = false;
    if (!b || !current) return;
    const { text, box } = current;
    hide();
    if (b.dataset.act === 'define') openDefinition(text, box, null);
    else openReport({ type: 'word', quote: text.slice(0, REPORT_MAX_CHARS) });
  });
  return bar;
}

function update() {
  const info = selectionInfo();
  if (!info) { hide(); return; }
  const define = canDefine(info.text);
  if (define) loadGlossary();                    // ready by the time it's clicked
  closeDefinition();
  ensureBar();
  bar.setAttribute('aria-label', C.t('sel.toolbar'));
  bar.innerHTML =
    (define ? `<button type="button" data-act="define"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A1.5 1.5 0 015.5 4H11v16H5.5A1.5 1.5 0 014 18.5z"/><path d="M20 5.5A1.5 1.5 0 0018.5 4H13v16h5.5a1.5 1.5 0 001.5-1.5z"/></svg><span>${escapeAttr(C.t('sel.define'))}</span></button>` : '') +
    `<button type="button" data-act="report"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/></svg><span>${escapeAttr(C.t('sel.report'))}</span></button>`;
  current = { text: info.text, range: info.range, box: info.box };
  bar.hidden = false;
  position();
}

// Just below the end of the highlight (clear of the phone's selection
// handles), flipped above when there is no room below.
function position() {
  if (!bar || !current) return;
  const rects = [...current.range.getClientRects()].filter(r => r.width || r.height);
  if (!rects.length) { hide(); return; }
  const last = rects[rects.length - 1];
  current.box = current.range.getBoundingClientRect();
  const coarse = matchMedia('(pointer: coarse)').matches;
  const gap = coarse ? 26 : 8;
  const w = bar.offsetWidth, h = bar.offsetHeight;
  let left = (coarse ? current.box.left + current.box.width / 2 : last.right) - w / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
  let top = last.bottom + gap;
  if (top + h > window.innerHeight - 8) top = rects[0].top - gap - h;
  if (top < 8 || last.bottom < 0 || rects[0].top > window.innerHeight) { bar.style.visibility = 'hidden'; return; }
  bar.style.visibility = '';
  bar.style.left = Math.round(left) + 'px';
  bar.style.top = Math.round(top) + 'px';
}

function hide() {
  if (bar) bar.hidden = true;
}
