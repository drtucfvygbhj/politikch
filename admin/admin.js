/* Politikch admin — front end. Talks only to admin/server.py on this machine.
   All text from files is inserted with textContent (never as HTML). */
(function () {
  'use strict';
  const TOKEN = document.querySelector('meta[name="admin-token"]').content;
  const PREVIEW = document.querySelector('meta[name="admin-preview"]').content;   // the site copy the preview shows
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const LANGS = ['en', 'de', 'fr', 'it', 'rm'];
  const SLIDERS = [   // [key, label, step, unit, group]
    ['left', 'Left column', 0.25, '', 'sliders'], ['centre', 'Centre column', 0.25, '', 'sliders'], ['right', 'Right column', 0.25, '', 'sliders'],
    ['gutter', 'Space beside the column lines', 1, 'px', 'sliders'], ['sectionGap', 'Space between sections', 1, 'px', 'sliders'],
    ['maxWidth', 'Page width', 10, 'px', 'sliders'], ['rule', 'Section line thickness', 1, 'px', 'sliders'], ['baseSize', 'Base text size', 1, 'px', 'sliders'],
    ['mastPad', 'Size of the title section', 1, 'px', 'title-sliders'], ['titleSize', 'Title text size', 1, 'px', 'title-sliders'],
    ['titleScaleY', 'Title height', 1, '%', 'title-sliders'], ['titleScaleX', 'Title width', 1, '%', 'title-sliders'],
  ];
  const DEFAULTS = { design: '1.1', fonts: { headline: 'playfair', body: 'dmsans' },
    layout: { left: 1, centre: 2, right: 1, gutter: 26, sectionGap: 32, maxWidth: 1320, rule: 2, baseSize: 15, mastPad: 18, titleSize: 58, titleScaleX: 100, titleScaleY: 100 },
    live: { ballotDays: 28, deadlineDays: 7 }, rotation: { canton: 9, explainer: 12 } };
  const STACKS = { playfair: "'Playfair Display', Georgia, serif", dmsans: "'DM Sans', system-ui, sans-serif",
    serif: "Charter, 'Iowan Old Style', Georgia, serif", sans: 'system-ui, -apple-system, Helvetica, Arial, sans-serif' };
  let S = null, ST = null, IMG = { library: {}, assign: {} }, PUB = {}, H = { undo: null, redo: null, undoCount: 0, redoCount: 0 };

  function el(tag, attrs, kids) {
    const e = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === undefined || v === null || v === false) return;
      if (k === 'text') e.textContent = v;
      else if (k === 'class') e.className = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    });
    (kids || []).forEach(c => e.append(c));
    return e;
  }
  function flash(msg, bad) {
    const f = $('#flash');
    f.textContent = msg; f.classList.toggle('bad', !!bad); f.hidden = false;
    clearTimeout(flash.t); flash.t = setTimeout(() => { f.hidden = true; }, bad ? 9000 : 4500);
  }
  async function api(path, body) {
    const opts = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Admin-Token': TOKEN }, body: JSON.stringify(body) };
    const r = await fetch(path, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
    return j;
  }
  const clone = o => JSON.parse(JSON.stringify(o));

  /* ---------- tabs ---------- */
  $$('.tabs button').forEach(b => b.addEventListener('click', () => {
    $$('.tabs button').forEach(x => x.classList.toggle('on', x === b));
    $$('.panel').forEach(p => p.classList.toggle('on', p.id === 'tab-' + b.dataset.tab));
    if (b.dataset.tab === 'design') { sizePreview(); if ($('#preview').src === 'about:blank') reloadPreview(); }
  }));

  /* ---------- overview ---------- */
  function renderOverview() {
    const m = ST.maintenance;
    $('#ov-maint').replaceChildren(
      el('p', { class: 'big ' + (m.on ? 'pill-warn' : 'pill-ok'), text: m.on ? 'On — the site shows the notice page' : 'Off — the site is live' }),
      el('pre', { class: 'pre', text: m.text || '(no MAINTENANCE_MODE file)' }),
      el('p', { class: 'meta', text: 'Switched only by you, by creating or deleting MAINTENANCE_MODE (SEC-10).' }));
    const b = ST.nextBallot;
    $('#ov-ballot').replaceChildren(
      el('p', { class: 'big', text: b.date ? b.date : 'None scheduled' }),
      el('p', { class: 'meta', text: b.date ? `${b.count} proposal(s) · in ${b.days} day(s)` : '' }),
      el('p', { class: b.quiet ? 'pill-warn' : 'meta', text: b.quiet ? 'Quiet period: only corrections, privacy fixes and the automatic data refresh on the vote pages (POL-09).' : 'Not in the quiet period.' }));
    $('#ov-session').replaceChildren(ST.session
      ? el('div', {}, [el('p', { class: 'big pill-ok', text: 'In session' }), el('p', { class: 'meta', text: `${ST.session.name} · ${ST.session.start} – ${ST.session.end}` })])
      : el('p', { class: 'big', text: 'Not sitting' }));
    $('#ov-fresh').replaceChildren(
      el('tr', {}, [el('th', { text: 'File' }), el('th', { text: 'Fetched' }), el('th', { text: 'Age' })]),
      ...ST.freshness.map(f => el('tr', {}, [el('td', { class: 'mono', text: f.file }), el('td', { text: f.when }),
        el('td', { class: f.days === null ? '' : f.days > 8 ? 'pill-warn' : 'pill-ok', text: f.days === null ? '?' : f.days + ' d' })])));
    $('#ov-changed').replaceChildren(...(ST.changed.length ? ST.changed.map(l => el('li', { text: l })) : [el('li', { text: 'Nothing changed.' })]));
    $('#ov-trans').textContent = ST.translations || '';
  }

  /* ---------- design ---------- */
  const form = $('#design-form');
  function buildDesignForm() {
    ['headline', 'body'].forEach(n => {
      const sel = form.elements[n];
      sel.replaceChildren(...Object.entries(ST.fonts).map(([k, label]) => el('option', { value: k, text: label })));
    });
    ['sliders', 'title-sliders'].forEach(group => $('#' + group).replaceChildren(...SLIDERS.filter(x => x[4] === group).map(([k, label, step, unit]) => {
      const [lo, hi] = ST.limits[k];
      const out = el('output', { name: k + 'Out' });
      const input = el('input', { type: 'range', name: k, min: lo, max: hi, step, 'aria-label': label, oninput: () => { out.textContent = input.value + unit; schematic(); } });
      return el('label', { class: 'range' }, [el('span', { text: label }), input, out]);
    })));
    form.elements.headline.addEventListener('change', specimens);
    form.elements.body.addEventListener('change', specimens);
  }
  function fillDesign(s) {
    form.querySelector(`input[name="design"][value="${s.design === '1.0' ? '1.0' : '1.1'}"]`).checked = true;
    form.elements.headline.value = s.fonts.headline; form.elements.body.value = s.fonts.body;
    SLIDERS.forEach(([k, , , unit]) => { const v = s.layout[k] ?? DEFAULTS.layout[k]; form.elements[k].value = v; form.elements[k + 'Out'].textContent = v + unit; });
    form.elements.ballotDays.value = s.live.ballotDays; form.elements.deadlineDays.value = s.live.deadlineDays;
    form.elements.canton.value = s.rotation.canton; form.elements.explainer.value = s.rotation.explainer;
    specimens(); schematic();
  }
  function specimens() {
    $('#spec-head').style.fontFamily = STACKS[form.elements.headline.value];
    $('#spec-body').style.fontFamily = STACKS[form.elements.body.value];
  }
  function schematic() {
    const f = form.elements;
    const sc = $('#schematic');
    sc.style.gridTemplateColumns = `${f.left.value}fr ${f.centre.value}fr ${f.right.value}fr`;
    sc.style.gap = Math.round(f.gutter.value / 4) + 'px';
    $$('i', sc).forEach(i => { i.style.borderTopWidth = f.rule.value + 'px'; });
    const mt = $('#title-schematic');
    mt.style.paddingBlock = Math.round(f.mastPad.value / 2) + 'px';
    const name = $('span', mt);
    name.style.fontSize = Math.round(f.titleSize.value / 2) + 'px';
    name.style.transform = `scale(${f.titleScaleX.value / 100}, ${f.titleScaleY.value / 100})`;
    const bad = Number(f.centre.value) < Math.max(Number(f.left.value), Number(f.right.value));
    $('#ratio-warn').hidden = !bad;
  }
  function readDesign() {
    const f = form.elements;
    const s = clone(S);
    s.design = form.querySelector('input[name="design"]:checked').value;
    s.fonts = { headline: f.headline.value, body: f.body.value };
    s.layout = {};
    SLIDERS.forEach(([k]) => { s.layout[k] = Number(f[k].value); });
    s.live = { ballotDays: Number(f.ballotDays.value), deadlineDays: Number(f.deadlineDays.value) };
    s.rotation = { canton: Number(f.canton.value), explainer: Number(f.explainer.value) };
    return s;
  }
  async function saveSettings(s, msg, label) {
    const j = await api('/api/settings', Object.assign({}, s, { _label: label || 'Design settings' }));
    S = j.settings; fillDesign(S); renderLinks(); reloadPreview(); refreshStatus();
    flash(msg || 'Saved to js/site-settings.js. It goes live when you commit and push.');
  }
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try { await saveSettings(readDesign()); } catch (err) { flash(err.message, true); }
  });
  /* ---------- undo / redo (every change made here, except adding or deleting a photo) ---------- */
  function renderHistory() {
    $('#h-undo').disabled = !H.undo; $('#h-redo').disabled = !H.redo;
    $('#h-undo').title = H.undo ? 'Undo: ' + H.undo : 'Nothing to undo';
    $('#h-redo').title = H.redo ? 'Redo: ' + H.redo : 'Nothing to redo';
    $('#h-state').textContent = H.undo ? `Last change: ${H.undo}` : 'Nothing to undo.';
  }
  async function historyStep(dir) {
    try {
      const j = await api('/api/history/' + dir, {});
      S = j.settings; IMG = j.images || IMG; H = j.history || H;
      fillDesign(S); renderLinks(); renderImages(); reloadPreview(); await refreshStatus();
      flash((dir === 'undo' ? 'Undone: ' : 'Redone: ') + j.label);
    } catch (err) { flash(err.message, true); }
  }
  $('#h-undo').addEventListener('click', () => historyStep('undo'));
  $('#h-redo').addEventListener('click', () => historyStep('redo'));
  // Cmd/Ctrl+Z and Shift+Cmd/Ctrl+Z (or Ctrl+Y), except while typing in a field.
  document.addEventListener('keydown', (e) => {
    if (!(e.metaKey || e.ctrlKey) || e.target.closest('input, textarea, select, [contenteditable]')) return;
    const k = e.key.toLowerCase();
    if (k === 'z' && !e.shiftKey && H.undo) { e.preventDefault(); historyStep('undo'); }
    else if (((k === 'z' && e.shiftKey) || k === 'y') && H.redo) { e.preventDefault(); historyStep('redo'); }
  });
  $('#defaults').addEventListener('click', () => { const s = clone(S); Object.assign(s, clone(DEFAULTS)); fillDesign(s); flash('Form reset to the defaults — press "Save & preview" to apply.'); });

  // The preview reloads where it was (page and language), as reported by its helper.
  const view = { hash: '#/', lang: 'en' };
  function reloadPreview() {
    const hash = /^#\/[\w\/%.-]*$/.test(view.hash) ? view.hash : '#/';
    const lang = LANGS.includes(view.lang) ? view.lang : 'en';
    $('#preview').src = `${PREVIEW}/?lang=${lang}&_=${Date.now()}${hash}`;
  }
  $('#reload').addEventListener('click', reloadPreview);
  // Desktop is drawn at a real 1400 px and scaled down to fit; the phone view is 375 px, unscaled.
  let previewWidth = 1400;
  function sizePreview() {
    const wrap = $('.frame-wrap'), fr = $('#preview');
    const scale = previewWidth > wrap.clientWidth ? wrap.clientWidth / previewWidth : 1;
    fr.style.width = previewWidth + 'px';
    fr.style.height = Math.round(wrap.clientHeight / scale) + 'px';
    fr.style.transform = scale < 1 ? `scale(${scale})` : 'none';
  }
  $$('.preview-bar button[data-w]').forEach(b => b.addEventListener('click', () => {
    $$('.preview-bar button[data-w]').forEach(x => x.classList.toggle('on', x === b));
    previewWidth = b.dataset.w === '375px' ? 375 : 1400;
    sizePreview();
  }));
  window.addEventListener('resize', sizePreview);

  /* ---------- edit modes in the preview: text and positioning ----------
     The preview (another port) carries admin/preview-agent.js; it reports clicks
     here with postMessage. Messages from anywhere else are ignored. */
  let editMode = null, firstPick = null;
  const tellPreview = (msg) => { const w = $('#preview').contentWindow; if (w) w.postMessage(msg, PREVIEW); };
  const HINTS = { text: 'Click any text in the preview to edit it.', position: 'Click a block, then the block to swap it with.' };
  function setMode(m) {
    editMode = editMode === m ? null : m;
    firstPick = null;
    $('#mode-text').setAttribute('aria-pressed', editMode === 'text' ? 'true' : 'false');
    $('#mode-pos').setAttribute('aria-pressed', editMode === 'position' ? 'true' : 'false');
    $('#mode-hint').textContent = HINTS[editMode] || 'Switch on a mode, then click in the preview.';
    if (editMode !== 'text') $('#editor').hidden = true;
    tellPreview({ type: 'mode', mode: editMode });
  }
  $('#mode-text').addEventListener('click', () => setMode('text'));
  $('#mode-pos').addEventListener('click', () => setMode('position'));
  window.addEventListener('message', (e) => {
    if (e.origin !== PREVIEW || e.source !== $('#preview').contentWindow || !e.data || typeof e.data !== 'object') return;
    const d = e.data;
    if (typeof d.hash === 'string') view.hash = d.hash || '#/';
    if (LANGS.includes(d.lang)) view.lang = d.lang;
    if (d.type === 'ready') { firstPick = null; tellPreview({ type: 'mode', mode: editMode }); }
    if (d.type === 'pick-text' && editMode === 'text') openEditor(String(d.text || ''), view.lang);
    if (d.type === 'pick-pos' && editMode === 'position') pickBlock(String(d.id || ''), d.arrangement);
  });

  // Positioning: the first click marks a block, the second swaps the two (any
  // columns). Saved as the full order in js/site-settings.js ("positions").
  const blockName = (id) => id.startsWith('story:') ? 'story ' + id.slice(6) : id;
  async function pickBlock(id, arr) {
    if (!id) return;
    if (!firstPick) { firstPick = id; $('#mode-hint').textContent = `Marked "${blockName(id)}" — now click the block to swap it with.`; return; }
    if (firstPick === id) { firstPick = null; tellPreview({ type: 'clear' }); $('#mode-hint').textContent = HINTS.position; return; }
    const a = { l: [...(arr && arr.l || [])], c: [...(arr && arr.c || [])], r: [...(arr && arr.r || [])] };
    const where = (x) => { for (const k of ['l', 'c', 'r']) { const i = a[k].indexOf(x); if (i >= 0) return [k, i]; } return null; };
    const p1 = where(firstPick), p2 = where(id);
    const first = firstPick;
    firstPick = null;
    if (!p1 || !p2) { flash('Could not find both blocks — click them again.', true); tellPreview({ type: 'clear' }); return; }
    a[p1[0]][p1[1]] = id; a[p2[0]][p2[1]] = first;
    const s = clone(S); s.positions = a;
    try {
      await saveSettings(s, `Swapped "${blockName(first)}" and "${blockName(id)}". It goes live with "Make changes live".`, `Swapped ${blockName(first)} and ${blockName(id)}`);
      $('#mode-hint').textContent = HINTS.position;
    } catch (err) { flash(err.message, true); }
  }
  $('#pos-reset').addEventListener('click', async () => {
    if (!S.positions) return flash('The front page already uses the standard order.');
    const s = clone(S); delete s.positions;
    try { await saveSettings(s, 'Front page back to the standard order.', 'Positions reset'); } catch (err) { flash(err.message, true); }
  });

  // Text: find where the clicked text comes from, then edit it in all languages.
  const LANG_NAMES = { en: 'English', de: 'German', fr: 'French', it: 'Italian', rm: 'Romansh' };
  async function openEditor(text, lang) {
    const box = $('#editor');
    box.hidden = false;
    box.replaceChildren(el('div', { class: 'k', text: 'Edit text' }), el('p', { class: 'meta', text: 'Looking it up…' }));
    let cands = [];
    try { cands = (await api('/api/text/find', { text, lang })).candidates; } catch (err) { box.replaceChildren(el('p', { class: 'blocked', text: err.message })); return; }
    const head = [el('div', { class: 'k', text: 'Edit text' }), el('div', { class: 'quote', text: text.length > 300 ? text.slice(0, 300) + '…' : text })];
    if (!cands.length) {
      box.replaceChildren(...head, el('p', { class: 'meta', text: 'Not found in the interface text or our editorial files. It is data (official or fetched texts, figures, names — they stay as the source publishes them), or it is put together from several pieces: click a smaller part of it.' }),
        el('div', { class: 'actions' }, [el('button', { type: 'button', text: 'Close', onclick: () => { box.hidden = true; } })]));
      return;
    }
    const form = el('form', {});
    const pick = (c) => {
      const fields = LANGS.filter(l => l in c.values).map(l => {
        const v = c.values[l] || '';
        return el('label', { class: 'field' }, [document.createTextNode(LANG_NAMES[l] + (l === lang ? ' (shown in the preview)' : '')),
          el('textarea', { name: l, rows: String(Math.min(10, Math.max(2, Math.ceil(v.length / 70)))), disabled: !!c.locked }, [document.createTextNode(v)])]);
      });
      const notes = [el('p', { class: 'meta', text: `${c.file} · ${c.label}` })];
      if (c.locked) notes.push(el('p', { class: 'blocked', text: c.locked }));
      else notes.push(el('p', { class: 'meta', text: 'Change every language together. Keep {placeholders} as they are. Saving changes the file here only; "Publish text" runs the checks (neutral wording, privacy text, legal pages) and asks for your sign-off.' }));
      form.replaceChildren(...notes, ...fields, el('div', { class: 'actions' }, [
        el('button', { type: 'submit', class: 'primary', text: 'Save text', disabled: !!c.locked }),
        el('button', { type: 'button', text: 'Cancel', onclick: () => { box.hidden = true; } })]));
      form.onsubmit = async (ev) => {
        ev.preventDefault();
        const values = {};
        LANGS.filter(l => l in c.values).forEach(l => { values[l] = form.elements[l].value; });
        try {
          const j = await api('/api/text/save', { file: c.file, path: c.path, values });
          H = j.history || H; renderHistory();
          box.hidden = true; reloadPreview(); await refreshStatus();
          flash(`Saved in ${c.file}. It goes live with "Publish text".`);
        } catch (err) { flash(err.message, true); }
      };
    };
    const list = cands.length > 1 ? el('div', { class: 'cands' }, [el('p', { class: 'meta', text: 'This text matches several entries — pick the one you mean:' }),
      ...cands.map((c, n) => el('label', {}, [el('input', { type: 'radio', name: 'cand', checked: n === 0, onchange: () => pick(c) }),
        document.createTextNode(` ${c.label} — “${(c.values[lang] || '').slice(0, 80)}”`)]))]) : null;
    box.replaceChildren(...head, ...(list ? [list] : []), form);
    pick(cands[0]);
  }

  /* ---------- images ---------- */
  const up = $('#upload-form');
  let processed = null;
  $('#alt-fields').replaceChildren(el('div', { class: 'alt-grid' }, LANGS.map(l =>
    el('label', { class: 'field' }, [document.createTextNode(`Alt text (${l.toUpperCase()}) — what the photo shows`), el('input', { type: 'text', name: 'alt-' + l, maxlength: 250 })]))));

  function blobToDataURL(blob) {
    return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(blob); });
  }
  /* Metadata: list what the original file carries (so you can see what is being
     left behind), and check that the new WebP files carry none. */
  function tiffTags(dv, start) {
    const out = [];
    const le = dv.getUint16(start) === 0x4949;
    const u16 = (o) => dv.getUint16(start + o, le), u32 = (o) => dv.getUint32(start + o, le);
    const ascii = (o, n) => { let s = ''; for (let i = 0; i < n - 1 && start + o + i < dv.byteLength; i++) s += String.fromCharCode(dv.getUint8(start + o + i)); return s.trim(); };
    const readIfd = (off, names) => {
      const found = {};
      if (off <= 0 || start + off + 2 > dv.byteLength) return found;
      const n = u16(off);
      for (let i = 0; i < n && start + off + 2 + i * 12 + 12 <= dv.byteLength; i++) {
        const e = off + 2 + i * 12, tag = u16(e), type = u16(e + 2), count = u32(e + 4);
        if (type === 2) found[tag] = ascii(count <= 4 ? e + 8 : u32(e + 8), count);
        else found[tag] = u32(e + 8);
      }
      return found;
    };
    const ifd0 = readIfd(u32(4));
    const cam = [ifd0[0x010F], ifd0[0x0110]].filter(x => typeof x === 'string' && x).join(' ');
    if (cam) out.push('camera: ' + cam);
    if (typeof ifd0[0x0131] === 'string' && ifd0[0x0131]) out.push('software: ' + ifd0[0x0131]);
    if (typeof ifd0[0x013B] === 'string' && ifd0[0x013B]) out.push('author: ' + ifd0[0x013B]);
    if (typeof ifd0[0x8298] === 'string' && ifd0[0x8298]) out.push('copyright note');
    const exif = ifd0[0x8769] ? readIfd(ifd0[0x8769]) : {};
    const when = exif[0x9003] || ifd0[0x0132];
    if (typeof when === 'string' && when) out.push('date taken: ' + when);
    if (exif[0xA431]) out.push('camera serial number');
    if (typeof exif[0xA434] === 'string' && exif[0xA434]) out.push('lens: ' + exif[0xA434]);
    if (ifd0[0x8825]) { const gps = readIfd(ifd0[0x8825]); out.push(gps[2] || gps[4] ? 'GPS location' : 'GPS data'); }
    if (!out.length) out.push('EXIF data');
    return out;
  }
  async function inspectMetadata(file) {
    const buf = await file.arrayBuffer();
    const dv = new DataView(buf), u8 = new Uint8Array(buf);
    const found = [];
    const bytes = new TextDecoder('latin1');                  // one character per byte (markers are ASCII)
    const str = (o, n) => bytes.decode(u8.subarray(o, o + n));
    try {
      if (dv.getUint16(0) === 0xFFD8) {                       // JPEG: walk the segments
        let o = 2;
        while (o + 4 <= dv.byteLength && dv.getUint8(o) === 0xFF) {
          const m = dv.getUint8(o + 1), len = dv.getUint16(o + 2);
          if (m === 0xDA || m === 0xD9) break;
          if (m === 0xE1 && str(o + 4, 6) === 'Exif\0\0') found.push(...tiffTags(dv, o + 10));
          else if (m === 0xE1 && str(o + 4, 28).startsWith('http://ns.adobe.com/xap/1.0/')) found.push('XMP data (may include author, location, editing history)');
          else if (m === 0xED) found.push('IPTC data (captions, names, places)');
          else if (m === 0xE2 && str(o + 4, 11) === 'ICC_PROFILE') found.push('colour profile');
          else if (m === 0xFE) found.push('comment');
          o += 2 + len;
        }
      } else if (u8[0] === 0x89 && str(1, 3) === 'PNG') {     // PNG: walk the chunks
        let o = 8;
        while (o + 8 <= dv.byteLength) {
          const len = dv.getUint32(o), type = str(o + 4, 4);
          if (type === 'eXIf') found.push(...tiffTags(dv, o + 8));
          else if (['tEXt', 'iTXt', 'zTXt'].includes(type)) found.push('text notes');
          else if (type === 'iCCP') found.push('colour profile');
          if (type === 'IEND') break;
          o += 12 + len;
        }
      } else {                                               // HEIC and others: look for the markers
        const text = str(0, Math.min(u8.length, 2000000));
        const ex = text.indexOf('Exif\0\0');
        if (ex >= 0) found.push(...tiffTags(dv, ex + 6));
        if (text.includes('x:xmpmeta')) found.push('XMP data (may include author, location, editing history)');
      }
    } catch (e) { found.push('metadata that could not be read'); }
    return [...new Set(found)];
  }
  // Take the metadata chunks out of a WebP (data: URL): EXIF, XMP and the ICC
  // colour profile the browser adds (it can name the display). The VP8X header
  // flags for them are cleared and the RIFF size fixed. Pixels are untouched.
  function stripWebp(dataUrl) {
    const bin = atob(dataUrl.split(',')[1]);
    const keep = [];
    for (let o = 12; o + 8 <= bin.length;) {
      const tag = bin.slice(o, o + 4);
      const size = (bin.charCodeAt(o + 4) | (bin.charCodeAt(o + 5) << 8) | (bin.charCodeAt(o + 6) << 16) | (bin.charCodeAt(o + 7) << 24)) >>> 0;
      let chunk = bin.slice(o, o + 8 + size + (size & 1));
      if (tag === 'VP8X') chunk = chunk.slice(0, 8) + String.fromCharCode(chunk.charCodeAt(8) & ~0x2C) + chunk.slice(9);
      if (!['EXIF', 'XMP ', 'ICCP'].includes(tag)) keep.push(chunk);
      o += 8 + size + (size & 1);
    }
    const body = 'WEBP' + keep.join('');
    const n = body.length;
    const riff = 'RIFF' + String.fromCharCode(n & 255, (n >> 8) & 255, (n >> 16) & 255, (n >>> 24) & 255) + body;
    return 'data:image/webp;base64,' + btoa(riff);
  }
  // Chunks of a WebP (data: URL) that would carry metadata.
  function webpMetadata(dataUrl) {
    const bin = atob(dataUrl.split(',')[1]);
    const bad = [];
    for (let o = 12; o + 8 <= bin.length;) {
      const tag = bin.slice(o, o + 4);
      const size = bin.charCodeAt(o + 4) | (bin.charCodeAt(o + 5) << 8) | (bin.charCodeAt(o + 6) << 16) | (bin.charCodeAt(o + 7) << 24);
      if (['EXIF', 'XMP ', 'ICCP'].includes(tag)) bad.push(tag.trim());
      o += 8 + size + (size & 1);
    }
    return bad;
  }
  function showMetadata(found) {
    const box = $('#up-meta');
    box.hidden = false;
    box.replaceChildren(
      el('p', { class: 'meta', text: found.length ? 'Found in the original file and left behind:' : 'No metadata found in the original file.' }),
      ...(found.length ? [el('ul', { class: 'metalist' }, found.map(f => el('li', { text: f })))] : []),
      el('p', { class: 'ok', text: 'Checked: the new WebP files carry no metadata (no EXIF, XMP or colour profile).' }));
  }

  async function processImage(file) {
    const found = await inspectMetadata(file);
    const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const ratio = 3 / 2;
    let sw = bmp.width, sh = bmp.height, sx = 0, sy = 0;
    if (sw / sh > ratio) { sw = Math.round(sh * ratio); sx = Math.round((bmp.width - sw) / 2); }
    else { sh = Math.round(sw / ratio); sy = Math.round((bmp.height - sh) / 2); }
    const make = async (w, cap) => {
      const c = document.createElement('canvas');
      c.width = Math.min(w, sw); c.height = Math.round(c.width / ratio);
      c.getContext('2d').drawImage(bmp, sx, sy, sw, sh, 0, 0, c.width, c.height);
      for (const q of [0.82, 0.72, 0.6]) {
        const blob = await new Promise(r => c.toBlob(r, 'image/webp', q));
        if (!blob || blob.type !== 'image/webp') throw new Error('This browser cannot save WebP. Use Chrome, Edge or Firefox.');
        if (blob.size <= cap) return stripWebp(await blobToDataURL(blob));
      }
      throw new Error('The photo is still too large after compression.');
    };
    const pv = $('#up-preview');
    pv.getContext('2d').drawImage(bmp, sx, sy, sw, sh, 0, 0, pv.width, pv.height);
    pv.hidden = false;
    const out = { w1600: await make(1600, 1400000), w800: await make(800, 560000), small: sw < 1200 };
    const left = [...webpMetadata(out.w1600), ...webpMetadata(out.w800)];
    if (left.length) throw new Error('The new files still carry metadata (' + left.join(', ') + ') — they are not saved.');
    showMetadata(found);
    return out;
  }
  up.elements.file.addEventListener('change', async () => {
    processed = null;
    $('#up-meta').hidden = true;
    const file = up.elements.file.files[0];
    if (!file) return;
    try {
      processed = await processImage(file);
      flash(processed.small ? 'Photo ready — note: it is under 1200 px wide and may look soft on large screens.' : 'Photo ready. Fill in the alt text and credit, then add it.');
    } catch (err) { flash(err.message, true); }
  });
  up.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!processed) return flash('Choose a photo first.', true);
    const alt = {};
    LANGS.forEach(l => { alt[l] = up.elements['alt-' + l].value; });
    const btn = up.querySelector('button[type=submit]');
    btn.disabled = true;
    try {
      const j = await api('/api/images', { w1600: processed.w1600, w800: processed.w800, alt, credit: up.elements.credit.value,
        licence: up.elements.licence.value, confirm: up.elements.confirm.checked });
      IMG = j.images; processed = null; up.reset(); $('#up-preview').hidden = true; $('#up-meta').hidden = true;
      await refreshStatus(); renderImages(); reloadPreview(); flash('Added to the library as ' + j.id + ' — visible in the Design preview; public after "Publish images".');
    } catch (err) { flash(err.message, true); } finally { btn.disabled = false; }
  });

  function renderImages() {
    const lib = IMG.library || {};
    const reg = ST.register || {};
    const ids = Object.keys(lib).sort();
    $('#library').replaceChildren(...(ids.length ? ids.map(id => imageCard(id, lib[id], reg[id] || {})) : [el('p', { class: 'meta', text: 'No photos yet. Until there are, the front page shows neutral placeholders.' })]));
    const assign = IMG.assign || {};
    $('#assign').replaceChildren(el('tr', {}, [el('th', { text: 'Vote' }), el('th', { text: 'Photo' })]),
      ...ST.votes.map(v => el('tr', {}, [el('td', {}, [el('b', { text: v.title }), el('div', { class: 'meta', text: `${v.date} · ${v.id}` })]),
        el('td', {}, [el('select', { 'data-vote': v.id, 'aria-label': 'Photo for ' + v.title }, [el('option', { value: '', text: 'Automatic' }),
          ...ids.map(id => el('option', { value: id, text: id + ' — ' + (lib[id].alt.en || ''), selected: assign[v.id] === id }))])])])));
  }
  function imageCard(id, e, r) {
    const fields = LANGS.map(l => el('label', { class: 'field' }, [document.createTextNode('Alt ' + l.toUpperCase()), el('input', { type: 'text', name: 'alt-' + l, value: e.alt[l] || '', maxlength: 250 })]));
    const credit = el('input', { type: 'text', name: 'credit', value: e.credit || '', maxlength: 120 });
    const licence = el('input', { type: 'text', name: 'licence', value: r.licence || '', maxlength: 200 });
    const f = el('form', { class: 'card' }, [
      el('img', { src: '/images/' + e.w800, alt: e.alt.en || '' }),
      el('div', {}, [el('b', { text: id }), document.createTextNode(' · added ' + (r.added || '?'))]),
      el('p', { class: (ST.imageMeta || {})[id] && ST.imageMeta[id].length ? 'blocked' : 'meta', text: (ST.imageMeta || {})[id] && ST.imageMeta[id].length ? 'Carries metadata: ' + ST.imageMeta[id].join(', ') : 'No metadata in the files.' }),
      ...fields, el('label', { class: 'field' }, [document.createTextNode('Credit'), credit]), el('label', { class: 'field' }, [document.createTextNode('Licence'), licence]),
      el('div', { class: 'actions' }, [el('button', { type: 'submit', text: 'Save text' }), el('button', { type: 'button', text: 'Delete', onclick: async () => {
        if (!confirm('Delete ' + id + ' from the library and from disk?')) return;
        try { const j = await api('/api/images/delete', { id }); IMG = j.images; await refreshStatus(); renderImages(); reloadPreview(); flash('Deleted ' + id + '.'); } catch (err) { flash(err.message, true); }
      } })])]);
    f.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const alt = {}; LANGS.forEach(l => { alt[l] = f.elements['alt-' + l].value; });
      try { const j = await api('/api/images/update', { id, alt, credit: credit.value, licence: licence.value }); IMG = j.images; await refreshStatus(); flash('Saved.'); } catch (err) { flash(err.message, true); }
    });
    return f;
  }
  $('#save-assign').addEventListener('click', async () => {
    const assign = {};
    $$('#assign select').forEach(sel => { if (sel.value) assign[sel.dataset.vote] = sel.value; });
    try { const j = await api('/api/images/assign', { assign }); IMG = j.images; await refreshStatus(); reloadPreview(); flash('Photo assignments saved. They go public with "Publish images".'); }
    catch (err) { flash(err.message, true); }
  });

  /* ---------- vote links ---------- */
  // Every proposal Parliament has voted on (or may have): upcoming, decided,
  // pending. Title matches are only suggestions — nothing is linked until you
  // choose it and save (POL-03: check each one against parlament.ch).
  const curiaUrl = (n) => `https://www.parlament.ch/de/ratsbetrieb/suche-curia-vista/geschaeft?AffairId=${encodeURIComponent(n)}`;
  const STATUS_LABEL = { upcoming: 'Upcoming', adopted: 'Adopted', rejected: 'Rejected', pending: 'Pending' };
  function renderLinks() {
    const links = S.parliamentLinks || {};
    const votes = ST.linkVotes || [];
    const linked = votes.filter(v => links[v.id]).length;
    $('#links-count').textContent = `${linked} of ${votes.length} proposals linked.`;
    $('#links').replaceChildren(...votes.map(v => {
      const cur = links[v.id];
      const name = 'link-' + v.id;
      const opts = [el('label', { class: 'cand' }, [el('input', { type: 'radio', name, value: '', checked: !cur }), document.createTextNode(' No link (the graphic is left out)')])];
      const cands = v.candidates.slice();
      if (cur && !cands.some(c => c.session === cur.session && c.vote === cur.vote)) cands.unshift({ session: cur.session, vote: cur.vote, title: '(current link)', date: '', tally: null });
      if (!v.candidates.length) opts.push(el('p', { class: 'meta', text: 'No matching final vote in the session data (it may be older than the data, or not voted yet).' }));
      cands.forEach(c => opts.push(el('label', { class: 'cand' + (c.score === 1 ? ' exact' : '') }, [
        el('input', { type: 'radio', name, value: c.session + ':' + c.vote, 'data-score': String(c.score ?? ''), checked: !!cur && cur.session === c.session && cur.vote === c.vote }),
        document.createTextNode(` ${c.title}`), el('div', { class: 'meta' }, [
          document.createTextNode(`${c.score === 1 ? 'exact title match' : c.score ? 'partial match (' + Math.round(c.score * 100) + '%)' : ''} · session ${c.session} · vote ${c.vote} · ${c.date || ''}` +
            (c.tally ? ` · ${c.tally.yes} yes, ${c.tally.no} no, ${c.tally.abstain} abstained` : '')),
          ...(c.business ? [document.createTextNode(' · '), el('a', { href: curiaUrl(c.business), target: '_blank', rel: 'noopener noreferrer', text: 'check on parlament.ch ↗' })] : [])])])));
      return el('div', { class: 'link-vote' + (cur ? ' is-linked' : '') }, [el('p', { class: 'vote-h', text: v.title }),
        el('p', { class: 'meta', text: `${STATUS_LABEL[v.status] || v.status} · ${v.date || 'no ballot date yet'} · ${v.type} · ${v.id}` }), ...opts]);
    }));
  }
  // Pre-select the exact title match wherever a proposal has no link yet. It
  // only fills the form: nothing changes until you check them and press Save.
  $('#links-exact').addEventListener('click', () => {
    let n = 0;
    (ST.linkVotes || []).forEach(v => {
      const box = document.querySelectorAll(`input[name="link-${CSS.escape(v.id)}"]`);
      const none = [...box].find(r => r.value === '');
      const exact = [...box].filter(r => r.dataset.score === '1');
      if (none && none.checked && exact.length === 1) { exact[0].checked = true; n++; }
    });
    flash(n ? `${n} exact matches selected — check each on parlament.ch, then Save links.` : 'No unlinked proposal has a single exact match.');
  });
  $('#save-links').addEventListener('click', async () => {
    const s = clone(S);
    s.parliamentLinks = {};
    (ST.linkVotes || []).forEach(v => {
      const r = document.querySelector(`input[name="link-${CSS.escape(v.id)}"]:checked`);
      if (r && r.value) { const [session, vote] = r.value.split(':').map(Number); s.parliamentLinks[v.id] = { session, vote }; }
    });
    Object.entries(S.parliamentLinks || {}).forEach(([k, val]) => { if (!(ST.linkVotes || []).some(v => v.id === k)) s.parliamentLinks[k] = val; });
    try { await saveSettings(s, 'Vote links saved.', 'Vote links'); } catch (err) { flash(err.message, true); }
  });

  /* ---------- publish (two separate buttons) ---------- */
  const PUB_TEXT = {
    settings: { kicker: 'Make changes live', title: 'Publish the design settings', what: 'Only js/site-settings.js is committed and pushed — design version, fonts, sizes, live rules, rotation and vote links.' },
    images: { kicker: 'Publish images', title: 'Publish the photos', what: 'Only images/ and js/site-images.js are committed and pushed — the photos, their licence record, alt text and which vote each one goes with.' },
    text: { kicker: 'Publish text', title: 'Publish the text edits', what: 'Only the text files edited here are committed and pushed: data/i18n.json, data/parties.json, data/cantons.json, data/donor-descriptions.json, data/legal.json.' },
  };
  function renderPubState() {
    $$('.pub-state').forEach(el => {
      const files = (PUB[el.dataset.kind] || {}).pending || [];
      el.classList.toggle('pending', files.length > 0);
      el.textContent = files.length ? `Not live yet: ${files.join(', ')}` : 'Everything here is live.';
    });
  }
  let pubKind = null, pubData = null;
  async function openPublish(kind) {
    pubKind = kind; pubData = null;
    $('#pub-kicker').textContent = PUB_TEXT[kind].kicker;
    $('#pub-title').textContent = PUB_TEXT[kind].title;
    $('#pub-go').hidden = true;
    $('#pub-body').replaceChildren(el('p', { class: 'meta', text: 'Checking against GitHub and running the guardrail checks…' }));
    $('#pub').hidden = false;
    try {
      pubData = await api('/api/publish/preview', { kind });
    } catch (err) {
      $('#pub-body').replaceChildren(el('p', { class: 'blocked', text: err.message }));
      return;
    }
    const body = [el('p', { text: PUB_TEXT[kind].what }), el('div', { class: 'k mt', text: 'Files' }),
      el('ul', { class: 'plain mono' }, pubData.files.map(f => el('li', { text: f })))];
    if (pubData.blocks.length) {
      body.push(el('p', { class: 'blocked', text: 'The checks found something that must be fixed first — nothing can be published:' }),
        el('ul', { class: 'plain' }, pubData.blocks.map(([r, m]) => el('li', { text: r + ': ' + m }))));
    } else {
      const rules = Object.keys(pubData.flags).sort();
      body.push(el('div', { class: 'k mt', text: 'Sign-offs' }));
      if (!rules.length) body.push(el('p', { class: 'ok', text: 'The checks passed with nothing to sign off.' }));
      rules.forEach(r => body.push(el('label', { class: 'reason' }, [el('b', { text: r }), document.createTextNode(' — ' + pubData.flags[r].join(' · ')),
        el('input', { type: 'text', name: 'reason-' + r, maxlength: 300, placeholder: 'Your reason (becomes the Approved-Rule line)' })])));
      body.push(el('label', { class: 'check' }, [el('input', { type: 'checkbox', name: 'previewed' }),
        document.createTextNode(' I have looked at the change in the preview in English, German and French, on desktop and phone width (PROC-03).')]));
      $('#pub-go').hidden = false;
    }
    body.push(el('details', {}, [el('summary', { text: 'Full check output' }), el('pre', { class: 'pre', text: pubData.output })]));
    $('#pub-body').replaceChildren(...body);
  }
  $$('[data-publish]').forEach(b => b.addEventListener('click', () => openPublish(b.dataset.publish)));
  $('#pub-cancel').addEventListener('click', () => { $('#pub').hidden = true; });
  $('#pub-go').addEventListener('click', async (e) => {
    const b = e.currentTarget;
    const reasons = {};
    Object.keys(pubData.flags).forEach(r => { reasons[r] = $('#pub-body').querySelector(`input[name="reason-${CSS.escape(r)}"]`).value; });
    const previewed = $('#pub-body').querySelector('input[name="previewed"]').checked;
    b.disabled = true; b.textContent = 'Publishing…';
    try {
      const j = await api('/api/publish', { kind: pubKind, reasons, previewed });
      $('#pub-body').replaceChildren(el('p', { class: 'ok', text: `Published as commit ${j.commit}. GitHub deploys it in about a minute.` }),
        el('p', { class: 'meta', text: 'While MAINTENANCE_MODE exists, the public site still shows only the notice page.' }),
        el('details', {}, [el('summary', { text: 'Push output' }), el('pre', { class: 'pre', text: j.output })]));
      $('#pub-go').hidden = true;
      await refreshStatus();
    } catch (err) { flash(err.message, true); }
    finally { b.disabled = false; b.textContent = 'Publish now'; }
  });

  /* ---------- checks ---------- */
  $('#run-checks').addEventListener('click', async (e) => {
    const b = e.currentTarget; b.disabled = true; b.textContent = 'Running…';
    try {
      const j = await api('/api/check', {});
      $('#check-out').replaceChildren(...Object.entries(j).map(([name, r]) => el('div', { class: 'mod' }, [
        el('div', { class: 'k', text: name + (r.code === 0 ? ' · passed' : ' · exit code ' + r.code) }), el('pre', { class: 'pre', text: r.output })])));
    } catch (err) { flash(err.message, true); } finally { b.disabled = false; b.textContent = 'Run checks'; }
  });

  /* ---------- boot ---------- */
  async function refreshStatus() {
    const j = await api('/api/state');
    ST = j.status; PUB = j.publish || {}; H = j.history || H;
    if (!S) S = j.settings;
    renderOverview(); renderPubState(); renderHistory();
  }
  (async () => {
    try {
      const j = await api('/api/state');
      S = j.settings; ST = j.status; IMG = j.images || IMG; PUB = j.publish || {}; H = j.history || H;
      buildDesignForm(); fillDesign(S); renderOverview(); renderImages(); renderLinks(); renderPubState(); renderHistory();
    } catch (err) { flash('Could not load: ' + err.message, true); }
  })();
})();
