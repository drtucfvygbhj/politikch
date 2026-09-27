/* Politikch admin — helper for the preview (127.0.0.1:8003 only).
   Served by admin/server.py's preview port and added to the page there; it is
   never part of the published site. It talks only to the admin page that
   embeds the preview (its origin comes from this script's own URL) and only
   while an edit mode is switched on there:
     • "text": a click reports the text under the pointer, so the admin can
       find where it comes from and open it for editing;
     • "position": a click reports the front-page block (data-pos) under the
       pointer, plus the current order of all blocks, so the admin can swap two.
   Nothing here writes anything; saving happens in the admin. */
const ADMIN = `http://127.0.0.1:${new URL(import.meta.url).searchParams.get('admin')}`;
let mode = null;
let hovered = null;
let picked = null;

const send = (msg) => { if (window.parent !== window) window.parent.postMessage(msg, ADMIN); };
const lang = () => document.documentElement.lang || 'en';

function outline(el, on, colour) {
  if (!el) return;
  el.style.outline = on ? `2px solid ${colour}` : '';
  el.style.outlineOffset = on ? '2px' : '';
  el.style.cursor = on ? 'pointer' : '';
}

// The element whose own text is under the pointer: the innermost element with
// visible text of its own, not a wrapper around several texts.
function textElement(target) {
  let el = target instanceof Element ? target : target.parentElement;
  while (el && el !== document.body) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (own) return el;
    if (!el.children.length && (el.innerText || '').trim()) return el;
    if (el.matches('section, article, .n-col, .n-stick, .n-band, #n-flow, main, header, footer, nav')) return null;
    el = el.parentElement;
  }
  return null;
}

// Current order of the front-page blocks: column → block ids, top to bottom.
function arrangement() {
  const out = { l: [], c: [], r: [] };
  document.querySelectorAll('#n-flow .n-col').forEach(col => {
    const k = col.classList.contains('n-col-l') ? 'l' : col.classList.contains('n-col-c') ? 'c' : 'r';
    col.querySelectorAll('[data-pos]').forEach(b => { if (!out[k].includes(b.dataset.pos)) out[k].push(b.dataset.pos); });
  });
  return out;
}
const blockEls = (id) => [...document.querySelectorAll('[data-pos]')].filter(b => b.dataset.pos === id);

function target(e) {
  if (mode === 'text') return textElement(e.target);
  if (mode === 'position') { const b = e.target.closest && e.target.closest('#n-flow [data-pos]'); return b; }
  return null;
}

document.addEventListener('pointerover', (e) => {
  if (!mode) return;
  const el = target(e);
  if (el === hovered) return;
  if (hovered && !(picked && blockEls(picked).includes(hovered))) outline(hovered, false);
  hovered = el;
  if (el) outline(el, true, mode === 'text' ? '#1f6feb' : '#7A1C2A');
}, true);

document.addEventListener('click', (e) => {
  if (!mode) return;
  e.preventDefault();
  e.stopPropagation();
  const el = target(e);
  if (!el) return;
  if (mode === 'text') {
    send({ type: 'pick-text', text: (el.innerText || el.textContent || '').trim().slice(0, 4000), lang: lang(), hash: location.hash });
  } else {
    const id = el.dataset.pos;
    blockEls(id).forEach(b => outline(b, true, '#7A1C2A'));
    picked = id;
    send({ type: 'pick-pos', id, arrangement: arrangement(), hash: location.hash, lang: lang() });
  }
}, true);

window.addEventListener('message', (e) => {
  if (e.origin !== ADMIN || !e.data || typeof e.data !== 'object') return;
  if (e.data.type === 'mode') {
    mode = ['text', 'position'].includes(e.data.mode) ? e.data.mode : null;
    if (hovered) outline(hovered, false);
    document.querySelectorAll('[data-pos]').forEach(b => outline(b, false));
    hovered = null; picked = null;
  }
  if (e.data.type === 'clear') {
    document.querySelectorAll('[data-pos]').forEach(b => outline(b, false));
    picked = null;
  }
});

// Tell the admin the preview is (re)loaded, so it can switch the mode back on.
send({ type: 'ready', hash: location.hash, lang: lang() });
window.addEventListener('hashchange', () => send({ type: 'nav', hash: location.hash, lang: lang() }));
