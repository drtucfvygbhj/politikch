/* ============================================================
   Share controls + branded image generation for every graph.

   Zero-dependency (see politikch-conventions): each graph is REDRAWN from its
   data onto a <canvas>, rather than rasterising the live SVG/DOM, so the
   exported photo is crisp at any resolution, uses the site fonts, and renders
   identically across browsers. Every shareable graph exposes a share button
   that offers: save the image (PNG), copy the link, the native device share
   sheet (with the image file where supported), and direct X / Facebook /
   WhatsApp / LinkedIn targets.

   app.js drives this module declaratively: after rendering a graph it sets a
   JSON `data-share` spec on the graph's card and calls wireShares(root, ctx).
   The spec is link-agnostic; the link is built from ctx + the current origin.
   ============================================================ */
import { track } from './analytics.js?v=20260925a';

// The site's own domain per interface language (branding text baked into the
// image). RM shares the German-language domain. See the project spec.
const LANG_DOMAIN = {
  en: 'politicsch.ch',
  fr: 'politiquech.ch',
  it: 'politicach.ch',
  de: 'politikch.ch',
  rm: 'politikch.ch',
};

const RED = '#D0021B';
const INK = '#1a1a1a';
const MUTED = '#6b7076';
const HAIR = '#e3e0d8';
const CARD_BG = '#ffffff';
const OTHER = '#c2bcae';

// Translator + number formatter injected by app.js so this module stays
// decoupled from app internals. Safe fallbacks keep it working standalone.
let _t = (k) => k;
let _lang = () => 'en';
export function configureShare({ t, lang } = {}) {
  if (typeof t === 'function') _t = t;
  if (typeof lang === 'function') _lang = lang;
}

/* ---- Fonts --------------------------------------------------------------
   Canvas text only uses a web font once it is actually loaded, so make sure
   the weights we draw with are ready before rendering. */
let fontsReady = null;
function ensureFonts() {
  if (fontsReady) return fontsReady;
  const faces = [
    '300 16px "DM Sans"', '400 16px "DM Sans"', '500 16px "DM Sans"',
    '600 16px "DM Sans"', '700 16px "DM Sans"', '700 34px "Playfair Display"',
  ];
  const load = (document.fonts && document.fonts.load)
    ? Promise.all(faces.map(f => document.fonts.load(f).catch(() => {})))
    : Promise.resolve();
  fontsReady = load.then(() => document.fonts && document.fonts.ready).catch(() => {});
  return fontsReady;
}

/* ---- Small canvas helpers ---------------------------------------------- */
function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// The Politikch mark: a red rounded square carrying a white Swiss cross,
// matching the site's CSS logo proportions (arm 0.5, thickness 0.125).
function drawLogo(ctx, x, y, size) {
  roundRect(ctx, x, y, size, size, size * 0.16);
  ctx.fillStyle = RED;
  ctx.fill();
  ctx.fillStyle = '#fff';
  const arm = size * 0.5, thick = size * 0.14;
  const cx = x + size / 2, cy = y + size / 2;
  ctx.fillRect(cx - arm / 2, cy - thick / 2, arm, thick);
  ctx.fillRect(cx - thick / 2, cy - arm / 2, thick, arm);
}

function truncate(ctx, text, maxWidth) {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let s = text;
  while (s.length > 1 && ctx.measureText(s + '…').width > maxWidth) s = s.slice(0, -1);
  return s + '…';
}

// Word-wrap `text` to `maxWidth`, returning the lines (at most maxLines, last
// line ellipsised if it overflows).
function wrapLines(ctx, text, maxWidth, maxLines) {
  const words = String(text).split(/\s+/);
  const lines = [];
  let cur = '';
  for (const w of words) {
    const trial = cur ? cur + ' ' + w : w;
    if (ctx.measureText(trial).width > maxWidth && cur) {
      lines.push(cur);
      cur = w;
      if (maxLines && lines.length === maxLines - 1) break;
    } else {
      cur = trial;
    }
  }
  if (cur) lines.push(cur);
  if (maxLines && lines.length > maxLines) lines.length = maxLines;
  if (maxLines && lines.length === maxLines) lines[maxLines - 1] = truncate(ctx, lines[maxLines - 1], maxWidth);
  return lines;
}

const CARD_W = 1200;
const PAD = 64;
const SCALE = 2; // backing-store multiplier for crisp export

/* ============================================================
   Card scaffold — header (logo + wordmark), title, and footer
   (language-specific domain URL + mark). Painters fill the middle.
   ============================================================ */
function newCard(height) {
  const canvas = document.createElement('canvas');
  canvas.width = CARD_W * SCALE;
  canvas.height = height * SCALE;
  const ctx = canvas.getContext('2d');
  ctx.scale(SCALE, SCALE);
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = CARD_BG;
  ctx.fillRect(0, 0, CARD_W, height);
  // A restrained top rule in the Swiss red.
  ctx.fillStyle = RED;
  ctx.fillRect(0, 0, CARD_W, 6);
  return { canvas, ctx, w: CARD_W, h: height };
}

function drawHeader(ctx) {
  const y = 44;
  drawLogo(ctx, PAD, y, 44);
  ctx.fillStyle = INK;
  ctx.font = '700 34px "Playfair Display", Georgia, serif';
  ctx.textBaseline = 'middle';
  ctx.fillText('Politikch', PAD + 44 + 16, y + 24);
  ctx.textBaseline = 'alphabetic';
  return y + 44 + 24; // baseline y for content start
}

function drawTitle(ctx, spec, top) {
  ctx.fillStyle = INK;
  // Match the site's section titles exactly: Playfair Display 700, tight
  // tracking; only the size differs.
  ctx.font = '700 40px "Playfair Display", Georgia, serif';
  ctx.letterSpacing = '-1px';
  ctx.textBaseline = 'alphabetic';
  const lines = wrapLines(ctx, spec.title || '', CARD_W - PAD * 2, 2);
  let y = top + 46;
  lines.forEach(l => { ctx.fillText(l, PAD, y); y += 46; });
  ctx.letterSpacing = '0px';
  if (spec.subtitle) {
    ctx.fillStyle = MUTED;
    ctx.font = '300 20px "DM Sans", system-ui, sans-serif';
    const sub = wrapLines(ctx, spec.subtitle, CARD_W - PAD * 2, 2);
    y += 4;
    sub.forEach(l => { ctx.fillText(l, PAD, y); y += 27; });
  }
  return y + 10;
}

// The attribution block, rendered INTO the bitmap so it travels with every
// shared/downloaded image and cannot be removed by hiding a DOM node:
//   • the data's official source caption (spec.source), driven by the data,
//   • the Politikch logo + the language's own domain, and the graph's own hash
//     route where present, so the image says where it came from,
//   • a restrained "independent · non-partisan" mark.
// This is source attribution only — deliberately plain, never styled as a
// sponsor/ad placement.
function drawFooter(ctx, h, spec) {
  const lang = spec.lang;
  const y = h - 74;
  // Source caption above the divider (the figures' official source).
  if (spec.source) {
    ctx.fillStyle = MUTED;
    ctx.font = '400 16px "DM Sans", system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(truncate(ctx, spec.source, CARD_W - PAD * 2), PAD, y - 12);
  }
  ctx.strokeStyle = HAIR;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD, y);
  ctx.lineTo(CARD_W - PAD, y);
  ctx.stroke();
  // Left: small mark + the language's own domain (red), then the graph's hash
  // route (muted) so the image points back to the exact page.
  drawLogo(ctx, PAD, y + 16, 26);
  const domain = LANG_DOMAIN[lang] || LANG_DOMAIN.en;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  ctx.fillStyle = RED;
  ctx.font = '700 24px "DM Sans", system-ui, sans-serif';
  const dx = PAD + 26 + 12;
  ctx.fillText(domain, dx, y + 30);
  const route = spec.route;
  if (route) {
    const dw = ctx.measureText(domain).width;
    ctx.fillStyle = MUTED;
    ctx.font = '400 18px "DM Sans", system-ui, sans-serif';
    ctx.fillText(truncate(ctx, '/#/' + route, 360), dx + dw + 10, y + 30);
  }
  // Right: independent · non-partisan mark (kept distinct from the source line).
  ctx.textAlign = 'right';
  ctx.fillStyle = MUTED;
  ctx.font = '400 16px "DM Sans", system-ui, sans-serif';
  const note = _t('share.imageNote');
  ctx.fillText(note && note !== 'share.imageNote' ? note : 'Independent · non-partisan', CARD_W - PAD, y + 30);
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
}

// Colour dot + label + value legend, laid out in up to two columns.
function drawLegend(ctx, items, x, top, colW, rowH) {
  let cy = top;
  let col = 0;
  const startTop = top;
  items.forEach((it, i) => {
    const cx = x + col * colW;
    ctx.fillStyle = it.color;
    ctx.beginPath();
    ctx.arc(cx + 6, cy - 5, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = INK;
    ctx.font = '500 17px "DM Sans", system-ui, sans-serif';
    const valText = it.valueText || '';
    ctx.textAlign = 'right';
    const valW = valText ? ctx.measureText(valText).width : 0;
    ctx.textAlign = 'left';
    const nameMax = colW - 22 - (valW ? valW + 14 : 0);
    ctx.fillText(truncate(ctx, it.label, nameMax), cx + 20, cy);
    if (valText) {
      ctx.fillStyle = MUTED;
      ctx.textAlign = 'right';
      ctx.fillText(valText, cx + colW - 16, cy);
      ctx.textAlign = 'left';
    }
    cy += rowH;
  });
  return cy;
}

/* ============================================================
   Painters — one per graph family
   ============================================================ */

// PIE: a full pie (like the site's), white separators between sections, and a
// leader line from every slice out to a label carrying the section's name,
// value and percent (explicit project requirement).
function paintPie(spec) {
  const slices = (spec.slices || []).filter(s => s.value > 0);
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const rows = Math.max(slices.length, 1);
  const h = Math.max(720, 300 + rows * 34 + 120) + 40;
  const card = newCard(h);
  const ctx = card.ctx;
  const hEnd = drawHeader(ctx);
  const contentTop = drawTitle(ctx, spec, hEnd);

  const areaTop = contentTop + 10;
  const areaBottom = h - 90;
  const cx = CARD_W / 2;
  const cy = (areaTop + areaBottom) / 2;
  const r = Math.min(160, (areaBottom - areaTop) / 2 - 40);

  // Slices (full pie)
  let a0 = -Math.PI / 2;
  const mids = [];
  const bounds = [];
  slices.forEach(s => {
    const a1 = a0 + (s.value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, a0, a1);
    ctx.closePath();
    ctx.fillStyle = s.color;
    ctx.fill();
    mids.push({ s, mid: (a0 + a1) / 2, frac: s.value / total });
    bounds.push(a0);
    a0 = a1;
  });
  // Thin white separators between slices, like the site's pie (stroke #fff).
  if (slices.length > 1) {
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    bounds.forEach(a => {
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(a) * (r + 0.5), cy + Math.sin(a) * (r + 0.5));
      ctx.stroke();
    });
  }

  // Leader-lined labels: split into left/right columns by slice mid-angle, then
  // de-clutter vertically within each column so labels never overlap. Each
  // column's horizontal leader ends at colX; the text begins just past it.
  const colX = { right: cx + r + 55, left: cx - r - 55 };
  const cols = { left: [], right: [] };
  mids.forEach(m => {
    const side = Math.cos(m.mid) >= 0 ? 'right' : 'left';
    cols[side].push(m);
  });
  const pct = (f) => Math.round(f * 100) + '%';
  ctx.font = '500 16px "DM Sans", system-ui, sans-serif';
  const lineH = 40;
  ['left', 'right'].forEach(side => {
    const arr = cols[side].sort((a, b) => Math.sin(a.mid) - Math.sin(b.mid));
    // desired y from angle, then spread apart
    arr.forEach(m => { m.y = cy + Math.sin(m.mid) * (r + 26); });
    for (let i = 1; i < arr.length; i++) {
      if (arr[i].y - arr[i - 1].y < lineH) arr[i].y = arr[i - 1].y + lineH;
    }
    // clamp within area, then push up if overflowing bottom
    const minY = areaTop + 12, maxY = areaBottom - 12;
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i].y > maxY) arr[i].y = maxY - (arr.length - 1 - i) * lineH;
    }
    for (let i = 1; i < arr.length; i++) {
      if (arr[i].y - arr[i - 1].y < lineH) arr[i].y = arr[i - 1].y + lineH;
    }
    if (arr.length) arr[0].y = Math.max(arr[0].y, minY);

    arr.forEach(m => {
      const sign = side === 'right' ? 1 : -1;
      // Start on the slice's rim, kink at a fixed x just OUTSIDE the pie, then
      // run horizontally to the label column. Because the kink and the label
      // both sit outside the pie, no leader ever crosses into it; because the
      // rim points and the label rows share the same angular order and converge
      // on one vertical channel per side, the leaders fan out without crossing.
      const startX = cx + Math.cos(m.mid) * (r + 2);
      const startY = cy + Math.sin(m.mid) * (r + 2);
      const kinkX = cx + sign * (r + 26);
      const endX = colX[side];
      ctx.strokeStyle = m.s.color;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(kinkX, m.y);
      ctx.lineTo(endX, m.y);
      ctx.stroke();
      // colour tick
      ctx.fillStyle = m.s.color;
      ctx.beginPath();
      ctx.arc(endX + (side === 'right' ? 6 : -6), m.y, 4, 0, Math.PI * 2);
      ctx.fill();
      // label text: name + value + percent
      ctx.textAlign = side === 'right' ? 'left' : 'right';
      const tx = side === 'right' ? endX + 16 : endX - 16;
      const maxTextW = side === 'right' ? (CARD_W - PAD - tx) : (tx - PAD);
      ctx.fillStyle = INK;
      ctx.font = '600 17px "DM Sans", system-ui, sans-serif';
      ctx.fillText(truncate(ctx, m.s.label, maxTextW), tx, m.y - 4);
      ctx.fillStyle = MUTED;
      ctx.font = '400 15px "DM Sans", system-ui, sans-serif';
      const detail = (m.s.valueText ? m.s.valueText + ' · ' : '') + pct(m.frac);
      ctx.fillText(truncate(ctx, detail, maxTextW), tx, m.y + 15);
    });
  });
  ctx.textAlign = 'left';

  drawFooter(ctx, h, spec);
  return card.canvas;
}

// BARS: horizontal bars, one per row (label · bar · value). A row either has
// one colour or `segments` (a stacked bar, e.g. a donor split by receiving
// party), with an optional colour legend above the bars.
function paintBars(spec) {
  const rows = (spec.rows || []).filter(r => r.value > 0);
  const legend = spec.legend || [];
  const rowH = 46;
  const legendRows = Math.ceil(legend.length / 5);
  const h = Math.max(640, 330 + legendRows * 30 + rows.length * rowH + 110);
  const card = newCard(h);
  const ctx = card.ctx;
  const hEnd = drawHeader(ctx);
  let y = drawTitle(ctx, spec, hEnd) + 10;

  if (legend.length) {
    const colW = (CARD_W - PAD * 2) / 5;
    legend.forEach((it, i) => {
      const lx = PAD + (i % 5) * colW, ly = y + Math.floor(i / 5) * 30;
      ctx.fillStyle = it.color;
      ctx.beginPath(); ctx.arc(lx + 7, ly - 6, 7, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = INK;
      ctx.font = '600 17px "DM Sans", system-ui, sans-serif';
      ctx.fillText(truncate(ctx, it.label, colW - 30), lx + 22, y + Math.floor(i / 5) * 30);
    });
    y += legendRows * 30 + 14;
  }

  const labelW = 300, valueW = 190;
  const barX = PAD + labelW + 16;
  const barW = CARD_W - PAD - valueW - 16 - barX;
  const max = Math.max(...rows.map(r => r.value), 1);
  rows.forEach((r, i) => {
    const cy = y + i * rowH + rowH / 2;
    ctx.fillStyle = INK;
    ctx.font = '600 18px "DM Sans", system-ui, sans-serif';
    ctx.textBaseline = 'middle';
    ctx.fillText(truncate(ctx, r.label, labelW), PAD, cy);
    // track
    ctx.fillStyle = '#f5f0e8';
    roundRect(ctx, barX, cy - 10, barW, 20, 5); ctx.fill();
    const segs = r.segments && r.segments.length ? r.segments : [{ value: r.value, color: r.color }];
    let x = barX;
    segs.forEach(sg => {
      const w = Math.max(3, sg.value / max * barW);
      ctx.fillStyle = sg.color;
      roundRect(ctx, x, cy - 10, w, 20, 4); ctx.fill();
      x += w + 2;
    });
    ctx.fillStyle = MUTED;
    ctx.font = '500 17px "DM Sans", system-ui, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(r.valueText || String(r.value), CARD_W - PAD, cy);
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
  });

  drawFooter(ctx, h, spec);
  return card.canvas;
}

// Shared arc/hemicycle seat layout, returning seat {x,y,color}. Mirrors the
// site's hemicycle so the shared image resembles the page.
function layoutSeats(seatList, cx, cy, rInner, rOuter, rows) {
  const rowRadii = [];
  for (let r = 0; r < rows; r++) rowRadii.push(rows === 1 ? rOuter : rInner + (rOuter - rInner) * (r / (rows - 1)));
  const totalLen = rowRadii.reduce((s, r) => s + r, 0);
  const total = seatList.length;
  const perRow = rowRadii.map(r => Math.max(1, Math.round(total * r / totalLen)));
  let drift = total - perRow.reduce((a, b) => a + b, 0), ri = perRow.length - 1;
  while (drift !== 0) { perRow[ri] += drift > 0 ? 1 : -1; drift += drift > 0 ? -1 : 1; ri = (ri - 1 + perRow.length) % perRow.length; }
  const out = [];
  let idx = 0;
  rowRadii.forEach((radius, row) => {
    const count = perRow[row];
    for (let i = 0; i < count && idx < total; i++) {
      const ang = Math.PI + (count === 1 ? 0.5 : i / (count - 1)) * Math.PI;
      out.push({ x: cx + radius * Math.cos(ang), y: cy + radius * Math.sin(ang), seat: seatList[idx++] });
    }
  });
  return out;
}

// HEMICYCLE / ARC: parliamentary seats coloured by party, with a legend of
// parties (seats + share). Used for National Council, Council of States, the
// Federal Council arc, and canton delegations.
function paintHemicycle(spec) {
  const groups = (spec.seats || []).filter(g => g.seats > 0);
  const total = groups.reduce((s, g) => s + g.seats, 0) || 1;
  const legendRows = Math.ceil(groups.length / 2);
  const h = Math.max(760, 340 + 260 + legendRows * 34 + 60) + 40;
  const card = newCard(h);
  const ctx = card.ctx;
  const hEnd = drawHeader(ctx);
  const contentTop = drawTitle(ctx, spec, hEnd);

  const seatList = [];
  groups.forEach(g => { for (let i = 0; i < g.seats; i++) seatList.push(g.color); });
  const arcTop = contentTop + 20;
  const cx = CARD_W / 2;
  const rOuter = Math.min(300, (CARD_W - PAD * 2) / 2 - 20);
  const rInner = rOuter * 0.34;
  const cy = arcTop + rOuter + 6;
  const rows = spec.arc ? 1 : Math.max(3, Math.round(6 * Math.sqrt(Math.min(1, total / 200))) || 3);
  const dotR = spec.arc ? 18 : Math.max(5, Math.min(9, 520 / total + 4));
  const seats = layoutSeats(seatList.map(c => ({ color: c })), cx, cy, rInner, rOuter, rows);
  seats.forEach(s => {
    ctx.beginPath();
    ctx.arc(s.x, s.y, dotR, 0, Math.PI * 2);
    ctx.fillStyle = s.seat.color;
    ctx.fill();
  });
  // Big total in the arc's mouth — Playfair Display 700, matching the site's
  // hemicycle total figure.
  ctx.fillStyle = INK;
  ctx.textAlign = 'center';
  ctx.font = '700 46px "Playfair Display", Georgia, serif';
  ctx.fillText(String(spec.total != null ? spec.total : total), cx, cy - 14);
  ctx.fillStyle = MUTED;
  ctx.font = '400 17px "DM Sans", system-ui, sans-serif';
  if (spec.totalLabel) ctx.fillText(spec.totalLabel, cx, cy + 12);
  ctx.textAlign = 'left';

  // Legend (two columns), ordered as given (left→right political order).
  const items = groups.map(g => ({
    label: g.label, color: g.color,
    valueText: g.seats + ' · ' + Math.round(g.seats / total * 100) + '%',
  }));
  const legTop = cy + 60;
  const colW = (CARD_W - PAD * 2) / 2;
  const half = Math.ceil(items.length / 2);
  drawLegend(ctx, items.slice(0, half), PAD, legTop, colW, 34);
  drawLegend(ctx, items.slice(half), PAD + colW, legTop, colW, 34);

  drawFooter(ctx, h, spec);
  return card.canvas;
}

// VOTE HEMICYCLE: one final vote — seats coloured by party, filled = Yes,
// ringed = No, hatched = abstain/absent — with a Yes/No/Abstain tally.
function paintVoteHemicycle(spec) {
  const groups = (spec.groups || []);
  const seatList = [];
  groups.forEach(g => {
    for (let i = 0; i < (g.yes || 0); i++) seatList.push({ color: g.color, d: 'yes' });
    for (let i = 0; i < (g.no || 0); i++) seatList.push({ color: g.color, d: 'no' });
    for (let i = 0; i < (g.abstain || 0); i++) seatList.push({ color: g.color, d: 'abs' });
  });
  const total = seatList.length || 1;
  const tal = spec.tallies || { yes: 0, no: 0, abstain: 0 };
  const legendRows = Math.ceil(groups.length / 2);
  const h = Math.max(780, 360 + 260 + 60 + legendRows * 34 + 60) + 40;
  const card = newCard(h);
  const ctx = card.ctx;
  const hEnd = drawHeader(ctx);
  const contentTop = drawTitle(ctx, spec, hEnd);

  const arcTop = contentTop + 16;
  const cx = CARD_W / 2;
  const rOuter = Math.min(290, (CARD_W - PAD * 2) / 2 - 20);
  const rInner = rOuter * 0.34;
  const cy = arcTop + rOuter + 6;
  const dotR = Math.max(5, Math.min(8, 520 / total + 4));
  const seats = layoutSeats(seatList, cx, cy, rInner, rOuter, 7);
  seats.forEach(({ x, y, seat }) => {
    ctx.beginPath();
    ctx.arc(x, y, dotR, 0, Math.PI * 2);
    if (seat.d === 'yes') { ctx.fillStyle = seat.color; ctx.fill(); }
    else if (seat.d === 'no') {
      ctx.fillStyle = '#fff'; ctx.fill();
      ctx.lineWidth = 2; ctx.strokeStyle = seat.color; ctx.stroke();
    } else {
      ctx.fillStyle = '#fff'; ctx.fill();
      ctx.lineWidth = 1.2; ctx.strokeStyle = seat.color; ctx.stroke();
    }
  });

  // Tally chips (Yes / No / Abstain) centred under the arc.
  const chips = [
    { k: 'yes', v: tal.yes, c: '#3d7a4b' },
    { k: 'no', v: tal.no, c: RED },
    { k: 'abstain', v: tal.abstain, c: MUTED },
  ];
  ctx.font = '600 18px "DM Sans", system-ui, sans-serif';
  const chipLabels = chips.map(c => `${_t('share.vote.' + c.k)}: ${c.v}`);
  const chipW = chipLabels.map(l => ctx.measureText(l).width + 40);
  const gap = 16;
  let totalW = chipW.reduce((a, b) => a + b, 0) + gap * (chips.length - 1);
  let x = cx - totalW / 2;
  const chipY = cy + 30;
  chips.forEach((c, i) => {
    roundRect(ctx, x, chipY, chipW[i], 36, 18);
    ctx.fillStyle = c.c + '22';
    ctx.fill();
    ctx.fillStyle = c.c;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(chipLabels[i], x + chipW[i] / 2, chipY + 19);
    x += chipW[i] + gap;
  });
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';

  const items = groups.filter(g => (g.yes + g.no + g.abstain) > 0).map(g => ({
    label: g.label, color: g.color,
    valueText: `${g.yes}·${g.no}·${g.abstain}`,
  }));
  const legTop = chipY + 78;
  const colW = (CARD_W - PAD * 2) / 2;
  const half = Math.ceil(items.length / 2);
  drawLegend(ctx, items.slice(0, half), PAD, legTop, colW, 34);
  drawLegend(ctx, items.slice(half), PAD + colW, legTop, colW, 34);

  drawFooter(ctx, h, spec);
  return card.canvas;
}

// SPECTRUM: the two-axis political-landscape scatter (home "Where the parties
// stand", and a vote's endorsement scale). Dots may be highlighted (on) or
// greyed (off); an optional marker shows a coalition's average position.
function paintSpectrum(spec) {
  const dots = spec.dots || [];
  const h = 940;
  const card = newCard(h);
  const ctx = card.ctx;
  const hEnd = drawHeader(ctx);
  const contentTop = drawTitle(ctx, spec, hEnd);

  // Every share image is light (all-white card), so the spectrum plot is drawn
  // on white with a hairline frame regardless of where it appears on the site.
  const panel = '#ffffff';
  const frame = HAIR;
  const axisCol = 'rgba(0,0,0,0.10)';
  const axisLabel = MUTED;
  const ringCol = '#ffffff';

  const size = Math.min(560, h - contentTop - 150);
  const plotX = (CARD_W - size) / 2;
  const plotY = contentTop + 30;
  const axes = spec.axes || {};
  // Plot panel (rounded, like .spectrum-chart-inner)
  roundRect(ctx, plotX, plotY, size, size, 14);
  ctx.fillStyle = panel;
  ctx.fill();
  ctx.strokeStyle = frame;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // Centre axes
  ctx.strokeStyle = axisCol;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(plotX, plotY + size / 2); ctx.lineTo(plotX + size, plotY + size / 2);
  ctx.moveTo(plotX + size / 2, plotY); ctx.lineTo(plotX + size / 2, plotY + size);
  ctx.stroke();
  // Axis labels — uppercase + tracking, like .axis-label
  ctx.fillStyle = axisLabel;
  ctx.font = '600 14px "DM Sans", system-ui, sans-serif';
  ctx.letterSpacing = '1.5px';
  ctx.textBaseline = 'middle';
  const up = (s) => String(s || '').toUpperCase();
  ctx.textAlign = 'left';
  if (axes.left) ctx.fillText(up(axes.left), plotX + 14, plotY + size / 2 - 16);
  ctx.textAlign = 'right';
  if (axes.right) ctx.fillText(up(axes.right), plotX + size - 14, plotY + size / 2 - 16);
  ctx.textAlign = 'center';
  if (axes.top) ctx.fillText(up(axes.top), plotX + size / 2, plotY + 18);
  if (axes.bottom) ctx.fillText(up(axes.bottom), plotX + size / 2, plotY + size - 18);
  ctx.letterSpacing = '0px';
  ctx.textBaseline = 'alphabetic';

  const px = (v) => plotX + (v / 100) * size;
  const py = (v) => plotY + ((100 - v) / 100) * size; // y already given as top=high
  // Optional average marker + leader to a callout
  if (spec.marker) {
    const mx = px(spec.marker.x), my = plotY + (spec.marker.y / 100) * size;
    const mCol = INK;
    ctx.strokeStyle = mCol;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(mx, my);
    const left = spec.marker.x < 50;
    ctx.lineTo(left ? plotX + 6 : plotX + size - 6, plotY + 18);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = mCol;
    ctx.beginPath();
    ctx.arc(mx, my, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = '700 15px "DM Sans", system-ui, sans-serif';
    ctx.textAlign = left ? 'left' : 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText(spec.marker.label, left ? plotX + 12 : plotX + size - 12, plotY + 18);
    ctx.textBaseline = 'alphabetic';
  }
  // Party dots — sized to the site's .party-dot-circle (≈8% of the plot), with a
  // white ring + soft shadow and white initials inside. Greyed dots (non-
  // endorsers) sit underneath the coloured ones.
  const rOn = size * 0.042;
  const rOff = size * 0.034;
  const order = dots.slice().sort((a, b) => (a.on === b.on) ? 0 : (a.on ? 1 : -1));
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  order.forEach(d => {
    const x = px(d.x), y = py(d.y);
    const on = d.on !== false;
    const rr = on ? rOn : rOff;
    if (on) { ctx.shadowColor = 'rgba(0,0,0,0.30)'; ctx.shadowBlur = 12; ctx.shadowOffsetY = 4; }
    ctx.beginPath();
    ctx.arc(x, y, rr, 0, Math.PI * 2);
    ctx.fillStyle = on ? (d.color || RED) : '#d9d6ce';
    ctx.fill();
    ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
    // white ring
    ctx.lineWidth = 2;
    ctx.strokeStyle = on ? ringCol : 'rgba(0,0,0,0.06)';
    ctx.stroke();
    ctx.fillStyle = on ? '#fff' : '#8b8f93';
    ctx.font = `700 ${Math.round(rr * 0.82)}px "DM Sans", system-ui, sans-serif`;
    ctx.fillText((d.label || '').slice(0, 3).toUpperCase(), x, y + rr * 0.06);
  });
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';

  drawFooter(ctx, h, spec);
  return card.canvas;
}

const PAINTERS = {
  pie: paintPie,
  bars: paintBars,
  hemicycle: paintHemicycle,
  arc: (s) => paintHemicycle(Object.assign({ arc: true }, s)),
  voteHemicycle: paintVoteHemicycle,
  spectrum: paintSpectrum,
};

async function renderCard(spec) {
  await ensureFonts();
  const painter = PAINTERS[spec.kind];
  if (!painter) return null;
  return painter(spec);
}

function canvasToBlob(canvas) {
  return new Promise(res => {
    if (canvas.toBlob) canvas.toBlob(res, 'image/png');
    else res(dataURLToBlob(canvas.toDataURL('image/png')));
  });
}
function dataURLToBlob(url) {
  const [head, b64] = url.split(',');
  const mime = /:(.*?);/.exec(head)[1];
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

/* ============================================================
   Share menu (button + popover) and targets
   ============================================================ */
function shareLink(spec, ctx) {
  const origin = (ctx && ctx.origin) || location.origin;
  const route = spec.route != null ? spec.route : (ctx && ctx.route) || '';
  return origin + '/' + (route ? '#/' + route : '');
}
function shareText(spec, ctx) {
  const title = spec.title || 'Politikch';
  return title + ' — ' + shareLink(spec, ctx);
}
function slugForFile(spec) {
  return (spec.title || 'politikch').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'politikch';
}

function icon(name) {
  const p = {
    image: '<path d="M4 5h16v14H4z" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="9" cy="10" r="1.6" fill="currentColor"/><path d="M5 17l4-4 3 3 3-4 4 5" fill="none" stroke="currentColor" stroke-width="1.7"/>',
    link: '<path d="M9 15l6-6M10 6l1-1a4 4 0 015.7 5.7l-1 1M14 18l-1 1A4 4 0 017.3 13.3l1-1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    share: '<circle cx="6" cy="12" r="2.3" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="18" cy="6" r="2.3" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="18" cy="18" r="2.3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M8 11l8-4M8 13l8 4" stroke="currentColor" stroke-width="1.7"/>',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${p[name] || ''}</svg>`;
}

const SOCIALS = [
  { key: 'x', label: 'X', url: (u, txt) => `https://twitter.com/intent/tweet?text=${encodeURIComponent(txt)}&url=${encodeURIComponent(u)}` },
  { key: 'facebook', label: 'Facebook', url: (u) => `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(u)}` },
  { key: 'whatsapp', label: 'WhatsApp', url: (u, txt) => `https://wa.me/?text=${encodeURIComponent(txt + ' ' + u)}` },
  { key: 'linkedin', label: 'LinkedIn', url: (u) => `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(u)}` },
];

let openMenu = null;
function closeMenu() {
  if (!openMenu) return;
  const { menu, btn } = openMenu;
  menu.remove();
  btn.setAttribute('aria-expanded', 'false');
  document.removeEventListener('keydown', openMenu.onKey, true);
  document.removeEventListener('click', openMenu.onDoc, true);
  openMenu = null;
}

async function saveImage(spec) {
  track('share', 'image');
  const canvas = await renderCard(spec);
  if (!canvas) return;
  // A data: URL keeps the download working under the site's strict CSP
  // (which does not allow blob: URLs).
  const a = document.createElement('a');
  a.href = canvas.toDataURL('image/png');
  a.download = slugForFile(spec) + '-politikch.png';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function nativeShare(spec, ctx) {
  track('share', 'device');
  const url = shareLink(spec, ctx);
  const text = spec.title || 'Politikch';
  try {
    const canvas = await renderCard(spec);
    const blob = canvas && await canvasToBlob(canvas);
    const file = blob && new File([blob], slugForFile(spec) + '-politikch.png', { type: 'image/png' });
    if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
      await navigator.share({ files: [file], title: text, text, url });
      return;
    }
    if (navigator.share) { await navigator.share({ title: text, text, url }); return; }
  } catch (e) { /* user cancelled or unsupported */ }
}

function menuItem(labelHtml, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'share-menu-item';
  b.setAttribute('role', 'menuitem');
  b.innerHTML = labelHtml;
  b.addEventListener('click', onClick);
  return b;
}

function toggleMenu(btn, spec, ctx) {
  if (openMenu && openMenu.btn === btn) { closeMenu(); return; }
  closeMenu();
  const menu = document.createElement('div');
  menu.className = 'share-menu';
  menu.setAttribute('role', 'menu');
  menu.setAttribute('aria-label', _t('share.menuLabel'));

  const items = [];
  items.push(menuItem(icon('image') + `<span>${_t('share.saveImage')}</span>`, async () => {
    closeMenu(); await saveImage(spec, ctx);
  }));
  const linkItem = menuItem(icon('link') + `<span>${_t('share.copyLink')}</span>`, async () => {
    const url = shareLink(spec, ctx);
    track('share', 'link');
    try {
      await navigator.clipboard.writeText(url);
      linkItem.querySelector('span').textContent = _t('share.copied');
      setTimeout(closeMenu, 700);
    } catch (e) {
      window.prompt(_t('share.copyLink'), url);
      closeMenu();
    }
  });
  items.push(linkItem);
  if (navigator.share) {
    items.push(menuItem(icon('share') + `<span>${_t('share.nativeShare')}</span>`, async () => {
      closeMenu(); await nativeShare(spec, ctx);
    }));
  }
  const sep = document.createElement('div');
  sep.className = 'share-menu-sep';
  menu.append(...items, sep);
  SOCIALS.forEach(s => {
    menu.appendChild(menuItem(`<span class="share-soc share-soc-${s.key}" aria-hidden="true">${s.label[0]}</span><span>${s.label}</span>`, () => {
      const u = shareLink(spec, ctx);
      track('share', s.key);
      window.open(s.url(u, shareText(spec, ctx)), '_blank', 'noopener,noreferrer');
      closeMenu();
    }));
  });

  // Share-terms note (usage request, not a technical guarantee): attribution is
  // baked into the exported image; we ask users not to crop it out and to credit
  // the site's link when sharing publicly.
  const terms = document.createElement('p');
  terms.className = 'share-terms';
  terms.textContent = _t('share.terms');
  menu.appendChild(terms);

  document.body.appendChild(menu);
  const r = btn.getBoundingClientRect();
  const mw = menu.offsetWidth;
  let left = r.right - mw + window.scrollX;
  if (left < 8) left = 8;
  menu.style.top = (r.bottom + 6 + window.scrollY) + 'px';
  menu.style.left = left + 'px';
  btn.setAttribute('aria-expanded', 'true');

  const menuItems = [...menu.querySelectorAll('.share-menu-item')];
  let focusIdx = 0;
  menuItems[0] && menuItems[0].focus();
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); closeMenu(); btn.focus(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); focusIdx = (focusIdx + 1) % menuItems.length; menuItems[focusIdx].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); focusIdx = (focusIdx - 1 + menuItems.length) % menuItems.length; menuItems[focusIdx].focus(); }
  };
  const onDoc = (e) => { if (!menu.contains(e.target) && e.target !== btn) closeMenu(); };
  document.addEventListener('keydown', onKey, true);
  document.addEventListener('click', onDoc, true);
  menu.addEventListener('focusin', () => { focusIdx = menuItems.indexOf(document.activeElement); });
  openMenu = { menu, btn, onKey, onDoc };
}

// Build a share button that resolves its spec lazily (so language and live data
// are always current at click time). getSpec() must return a spec object.
export function mountShare(host, getSpec, ctx) {
  if (!host || host.querySelector(':scope > .share-btn')) return;
  host.classList.add('share-host');
  // The absolutely-positioned button needs a positioned host — but only set it
  // when the host is static, so we never override an element that already relies
  // on position:absolute/relative for its own layout (e.g. the spectrum plot).
  if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'share-btn';
  btn.setAttribute('aria-haspopup', 'menu');
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('data-i18n-aria', 'share.button');
  btn.setAttribute('aria-label', _t('share.button'));
  btn.innerHTML = icon('share');
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const spec = getSpec();
    if (!spec) return;
    spec.lang = spec.lang || _lang();
    toggleMenu(btn, spec, ctx || {});
  });
  host.appendChild(btn);
  return btn;
}

// Declarative wiring: every element carrying a JSON `data-share` spec inside
// `root` gets a share button. ctx supplies link context ({origin, route}).
export function wireShares(root, ctx) {
  if (!root) return;
  root.querySelectorAll('[data-share]').forEach(el => {
    let spec;
    try { spec = JSON.parse(el.getAttribute('data-share')); } catch (e) { return; }
    if (!spec || !spec.kind) return;
    el.classList.add('share-host');
    mountShare(el, () => { spec.lang = _lang(); return spec; }, ctx || {});
  });
}
