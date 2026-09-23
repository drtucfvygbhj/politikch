/* ============================================================
   Politikch analytics — Cloudflare Worker
   ------------------------------------------------------------
   POST /e            anonymous beacons from the site (no cookies, no IPs stored)
   GET  /dashboard    the private dashboard (HTTP Basic auth, DASHBOARD_PASSWORD)
   GET  /api/stats    the dashboard's data (same auth)
   cron (hourly)      roll up finished days, drop old salts + expired raw rows

   Privacy model: a visitor is counted with a one-way hash of a random daily
   salt + IP + user agent. The salt is deleted when its day ends, so nobody
   can be recognised across days, and the IP itself is never written anywhere.
   ============================================================ */
import DASHBOARD_SOURCE from './dashboard.html';

// The dashboard's script is served from /dashboard.js so the page's CSP can
// forbid inline scripts entirely.
const SCRIPT_RE = /<script>([\s\S]*?)<\/script>/;
const DASHBOARD_JS = (DASHBOARD_SOURCE.match(SCRIPT_RE) || [, ''])[1];
const DASHBOARD_HTML = DASHBOARD_SOURCE.replace(SCRIPT_RE, '<script src="/dashboard.js"></script>');
const SECURITY_HEADERS = {
  'Cache-Control': 'no-store',
  'Referrer-Policy': 'no-referrer',
  'X-Content-Type-Options': 'nosniff',
  'Strict-Transport-Security': 'max-age=31536000',
};

const TZ = 'Europe/Zurich';
const SESSION_GAP = 30 * 60 * 1000;
const MAX_BODY = 4096;
const MAX_BATCH = 5;
const EVENT_NAMES = new Set(['lang', 'search', 'vote', 'share', 'outbound', 'vote_open', 'contact', 'glossary']);
const BOT_RE = /bot|crawl|spider|slurp|headless|lighthouse|pagespeed|preview|monitor|uptime|curl|wget|python|httpclient|java\/|go-http|axios|node-fetch|facebookexternalhit|embedly|whatsapp|telegram|discord|skype|bingpreview|phantomjs|selenium|puppeteer|playwright/i;

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (url.pathname === '/e') return ingest(req, env, ctx);
    if (url.pathname === '/') return Response.redirect(url.origin + '/dashboard', 302);
    if (url.pathname === '/dashboard' || url.pathname === '/dashboard.js' || url.pathname === '/api/stats') {
      const ip = req.headers.get('CF-Connecting-IP') || '';
      if (lockedOut(ip)) {
        return new Response('Too many failed attempts. Try again later.', { status: 429, headers: { ...SECURITY_HEADERS, 'Retry-After': '900' } });
      }
      if (!authorised(req, env)) {
        if (req.headers.has('Authorization')) noteFailure(ip);
        return new Response('Authentication required', {
          status: 401,
          headers: { ...SECURITY_HEADERS, 'WWW-Authenticate': 'Basic realm="Politikch analytics", charset="UTF-8"' },
        });
      }
      if (url.pathname === '/dashboard') {
        return new Response(DASHBOARD_HTML, {
          headers: {
            ...SECURITY_HEADERS,
            'Content-Type': 'text/html; charset=utf-8',
            'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
          },
        });
      }
      if (url.pathname === '/dashboard.js') {
        return new Response(DASHBOARD_JS, { headers: { ...SECURITY_HEADERS, 'Content-Type': 'text/javascript; charset=utf-8' } });
      }
      try {
        return json(await stats(url, env));
      } catch (e) {
        return json({ error: String(e && e.message || e) }, 500);
      }
    }
    return new Response('Not found', { status: 404 });
  },

  async scheduled(_evt, env, ctx) {
    ctx.waitUntil(housekeeping(env));
  },
};

/* ---------- helpers ---------- */
const json = (o, status = 200) => new Response(JSON.stringify(o), {
  status, headers: { ...SECURITY_HEADERS, 'Content-Type': 'application/json' },
});

// Best-effort brute-force brake for the dashboard password (per isolate, in
// memory only): 10 failed attempts from one address locks it out for 15 minutes.
const failures = new Map();
const LOCK_MS = 15 * 60 * 1000, MAX_FAILS = 10;
function lockedOut(ip) {
  const f = failures.get(ip);
  if (!f) return false;
  if (Date.now() - f.since > LOCK_MS) { failures.delete(ip); return false; }
  return f.n >= MAX_FAILS;
}
function noteFailure(ip) {
  const f = failures.get(ip);
  if (!f || Date.now() - f.since > LOCK_MS) failures.set(ip, { n: 1, since: Date.now() });
  else f.n++;
  if (failures.size > 1000) failures.clear();
}

const dayFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });
const hourFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', hourCycle: 'h23' });
const zurichDay = (ms) => dayFmt.format(new Date(ms));
const zurichHour = (ms) => parseInt(hourFmt.format(new Date(ms)), 10) % 24;
function addDays(day, n) {
  const d = new Date(day + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function authorised(req, env) {
  const secret = env.DASHBOARD_PASSWORD;
  if (!secret) return false;
  const h = req.headers.get('Authorization') || '';
  if (!h.startsWith('Basic ')) return false;
  let pass = '';
  try { pass = atob(h.slice(6)).split(':').slice(1).join(':'); } catch (e) { return false; }
  const enc = new TextEncoder();
  const a = enc.encode(pass), b = enc.encode(secret);
  if (a.byteLength !== b.byteLength) { crypto.subtle.timingSafeEqual(b, b); return false; }
  return crypto.subtle.timingSafeEqual(a, b);
}

async function sha256hex(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}

let saltCache = { day: '', salt: '' };
async function dailySalt(env, day) {
  if (saltCache.day === day) return saltCache.salt;
  let row = await env.DB.prepare('SELECT salt FROM salts WHERE day = ?').bind(day).first();
  if (!row) {
    const fresh = [...crypto.getRandomValues(new Uint8Array(32))].map(b => b.toString(16).padStart(2, '0')).join('');
    await env.DB.prepare('INSERT OR IGNORE INTO salts (day, salt) VALUES (?, ?)').bind(day, fresh).run();
    row = await env.DB.prepare('SELECT salt FROM salts WHERE day = ?').bind(day).first();
  }
  saltCache = { day, salt: row.salt };
  return row.salt;
}

function parseUA(ua, touch) {
  let browser = 'Other', os = 'Other', device = 'Desktop';
  if (/Edg(e|A|iOS)?\//.test(ua)) browser = 'Edge';
  else if (/OPR\/|Opera/.test(ua)) browser = 'Opera';
  else if (/SamsungBrowser/.test(ua)) browser = 'Samsung Internet';
  else if (/Firefox\/|FxiOS/.test(ua)) browser = 'Firefox';
  else if (/DuckDuckGo/.test(ua)) browser = 'DuckDuckGo';
  else if (/CriOS|Chrome\//.test(ua)) browser = 'Chrome';
  else if (/Safari\//.test(ua)) browser = 'Safari';

  if (/iPhone|iPod/.test(ua)) os = 'iOS';
  else if (/iPad/.test(ua)) os = 'iPadOS';
  else if (/Android/.test(ua)) os = 'Android';
  else if (/Windows/.test(ua)) os = 'Windows';
  else if (/CrOS/.test(ua)) os = 'ChromeOS';
  else if (/Macintosh|Mac OS X/.test(ua)) os = touch ? 'iPadOS' : 'macOS';   // iPads report as Macs
  else if (/Linux/.test(ua)) os = 'Linux';

  if (os === 'iPadOS' || /Tablet/.test(ua) || (os === 'Android' && !/Mobile/.test(ua))) device = 'Tablet';
  else if (os === 'iOS' || /Mobi/.test(ua)) device = 'Mobile';
  return { browser, os, device };
}

function screenBucket(w) {
  if (!w) return 'Unknown';
  if (w < 576) return 'Phone (<576px)';
  if (w < 768) return 'Large phone (576–767px)';
  if (w < 1024) return 'Tablet (768–1023px)';
  if (w < 1440) return 'Laptop (1024–1439px)';
  return 'Desktop (1440px+)';
}

const str = (v, max, re) => {
  if (typeof v !== 'string') return null;
  const s = v.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, max);
  if (!s) return null;
  return re && !re.test(s) ? null : s;
};

function cleanEvent(e) {
  if (!e || typeof e !== 'object') return null;
  const kind = e.k === 'pv' ? 'pageview' : e.k === 'ev' ? 'event' : e.k === 'eng' ? 'engagement' : null;
  if (!kind) return null;
  const route = str(e.r, 160, /^\/[\w\-./%~]*$/);
  if (!route) return null;
  const out = { kind, route, entry: 0, name: null, prop: null, ref: null, utm_source: null, utm_medium: null, utm_campaign: null, duration: null };
  out.lang = str(e.l, 2, /^(en|de|fr|it|rm)$/);
  out.blang = str(e.bl, 2, /^[a-z]{2}$/);
  out.w = Number.isFinite(e.w) ? Math.max(0, Math.min(10000, Math.round(e.w))) : 0;
  out.touch = e.t === 1;
  if (kind === 'event') {
    out.name = str(e.n, 20);
    if (!out.name || !EVENT_NAMES.has(out.name)) return null;
    out.prop = str(e.p, 80);
  } else if (kind === 'engagement') {
    const d = Number(e.d);
    if (!Number.isFinite(d) || d < 1000) return null;
    out.duration = Math.min(Math.round(d), 30 * 60 * 1000);
  } else if (e.entry === 1) {
    out.entry = 1;
    out.ref = str(e.ref, 100, /^[a-z0-9.\-]+$/i);
    out.ref = out.ref && out.ref.toLowerCase().replace(/^www\./, '');
    out.utm_source = str(e.us, 60);
    out.utm_medium = str(e.um, 60);
    out.utm_campaign = str(e.uc, 60);
    const ll = str(e.ll, 2, /^(en|de|fr|it|rm)$/);
    if (ll) out.prop = 'lang=' + ll;
  }
  return out;
}

// Best-effort per-isolate flood guard.
const recent = new Map();
function flooding(visitor, now) {
  const minute = Math.floor(now / 60000);
  const k = visitor + ':' + minute;
  const n = (recent.get(k) || 0) + 1;
  recent.set(k, n);
  if (recent.size > 5000) for (const key of recent.keys()) { if (!key.endsWith(':' + minute)) recent.delete(key); }
  return n > 120;
}

/* ---------- ingest ---------- */
// Read at most `max` bytes of the body; null if it is larger.
async function readCapped(req, max) {
  const len = parseInt(req.headers.get('Content-Length') || '0', 10);
  if (len > max) return null;
  if (!req.body) return '';
  const reader = req.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > max) { reader.cancel(); return null; }
    chunks.push(value);
  }
  const buf = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) { buf.set(c, off); off += c.byteLength; }
  return new TextDecoder().decode(buf);
}

async function ingest(req, env, ctx) {
  const origin = req.headers.get('Origin') || '';
  const allowed = (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
  const okOrigin = allowed.includes(origin);
  const cors = okOrigin ? { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' } : {};
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: { ...cors, 'Access-Control-Allow-Methods': 'POST', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '86400' } });
  }
  const done = () => new Response(null, { status: 204, headers: cors });
  if (req.method !== 'POST') return new Response(null, { status: 405 });
  if (!okOrigin) return done();
  const ua = req.headers.get('User-Agent') || '';
  if (!ua || BOT_RE.test(ua)) return done();

  let body;
  try {
    const text = await readCapped(req, MAX_BODY);
    if (text == null) return done();
    body = JSON.parse(text);
  } catch (e) { return done(); }
  const list = (Array.isArray(body && body.e) ? body.e : []).slice(0, MAX_BATCH).map(cleanEvent).filter(Boolean);
  if (!list.length) return done();

  ctx.waitUntil(store(list, req, env, ua).catch(err => console.error('store failed', err)));
  return done();
}

async function store(list, req, env, ua) {
  const now = Date.now();
  const day = zurichDay(now), hour = zurichHour(now);
  const ip = req.headers.get('CF-Connecting-IP') || '';
  const salt = await dailySalt(env, day);
  const visitor = (await sha256hex(`${salt}|${ip}|${ua}`)).slice(0, 20);
  if (flooding(visitor, now)) return;
  const cf = req.cf || {};
  const country = cf.country || null;
  const region = cf.region || null;
  const city = cf.city || null;
  const stmt = env.DB.prepare(`INSERT INTO events
    (ts, day, hour, kind, route, entry, name, prop, ref, utm_source, utm_medium, utm_campaign,
     country, region, city, device, browser, os, screen, lang, blang, visitor, duration)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`);
  await env.DB.batch(list.map(e => {
    const u = parseUA(ua, e.touch);
    return stmt.bind(now, day, hour, e.kind, e.route, e.entry, e.name, e.prop, e.ref,
      e.utm_source, e.utm_medium, e.utm_campaign, country, region, city,
      u.device, u.browser, u.os, screenBucket(e.w), e.lang, e.blang, visitor, e.duration);
  }));
}

/* ---------- roll-ups ----------
   The same queries compute a finished day (stored by the cron) and today
   (computed live for the dashboard), so both always agree. */
const SESSIONS_CTE = `
  pv AS (
    SELECT visitor, ts, route, LAG(ts) OVER (PARTITION BY visitor ORDER BY ts) AS prev
    FROM events WHERE day = ?1 AND kind = 'pageview'),
  s AS (
    SELECT visitor, ts, route,
      SUM(CASE WHEN prev IS NULL OR ts - prev > ${SESSION_GAP} THEN 1 ELSE 0 END)
        OVER (PARTITION BY visitor ORDER BY ts ROWS UNBOUNDED PRECEDING) AS sn
    FROM pv)`;

const TOTALS_SQL = `
  WITH ${SESSIONS_CTE},
  v AS (SELECT visitor, sn, COUNT(*) AS n FROM s GROUP BY visitor, sn)
  SELECT COUNT(DISTINCT visitor) AS visitors, COUNT(*) AS visits,
         COALESCE(SUM(n), 0) AS pageviews, COALESCE(SUM(n = 1), 0) AS bounces,
         (SELECT COALESCE(SUM(duration), 0) FROM events WHERE day = ?1 AND kind = 'engagement') AS duration
  FROM v`;

// Every dimension query returns rows of (dim, key, visitors, hits, extra).
const DIM_SQL = [
  // Pages: views, unique visitors, total visible time.
  `SELECT 'page' AS dim, route AS key,
     COUNT(DISTINCT CASE WHEN kind = 'pageview' THEN visitor END) AS visitors,
     SUM(kind = 'pageview') AS hits,
     SUM(CASE WHEN kind = 'engagement' THEN duration ELSE 0 END) AS extra
   FROM events WHERE day = ?1 AND kind IN ('pageview', 'engagement')
   GROUP BY route HAVING SUM(kind = 'pageview') > 0`,
  // Entry and exit pages, per visit.
  `WITH ${SESSIONS_CTE},
   r AS (SELECT route,
           ROW_NUMBER() OVER (PARTITION BY visitor, sn ORDER BY ts) AS a,
           ROW_NUMBER() OVER (PARTITION BY visitor, sn ORDER BY ts DESC) AS d
         FROM s)
   SELECT 'entry' AS dim, route AS key, 0 AS visitors, SUM(a = 1) AS hits, 0 AS extra
     FROM r GROUP BY route HAVING SUM(a = 1) > 0
   UNION ALL
   SELECT 'exit', route, 0, SUM(d = 1), 0 FROM r GROUP BY route HAVING SUM(d = 1) > 0`,
  // Actions.
  `SELECT 'event' AS dim, name || char(9) || COALESCE(prop, '') AS key,
     COUNT(DISTINCT visitor) AS visitors, COUNT(*) AS hits, 0 AS extra
   FROM events WHERE day = ?1 AND kind = 'event' GROUP BY 2`,
  // Hours of the day (Zurich time).
  `SELECT 'hour' AS dim, printf('%02d', hour) AS key, COUNT(DISTINCT visitor) AS visitors, COUNT(*) AS hits, 0 AS extra
   FROM events WHERE day = ?1 AND kind = 'pageview' GROUP BY hour`,
];
// Visitor attributes, over page views. `entry` = only the landing page view.
const ATTRS = [
  ['source', "COALESCE(ref, '(direct / none)')", true],
  ['utm_source', 'utm_source', true],
  ['utm_medium', 'utm_medium', true],
  ['utm_campaign', 'utm_campaign', true],
  ['landing_lang', "substr(prop, 6)", true, "prop LIKE 'lang=%'"],
  ['country', 'country'],
  ['region', "country || ' · ' || region", false, 'region IS NOT NULL'],
  ['city', "country || ' · ' || city", false, 'city IS NOT NULL'],
  ['device', 'device'],
  ['browser', 'browser'],
  ['os', 'os'],
  ['screen', 'screen'],
  ['lang', 'lang'],
  ['blang', 'blang'],
];
for (const [dim, expr, entryOnly, extraWhere] of ATTRS) {
  DIM_SQL.push(`SELECT '${dim}' AS dim, ${expr} AS key, COUNT(DISTINCT visitor) AS visitors, COUNT(*) AS hits, 0 AS extra
    FROM events WHERE day = ?1 AND kind = 'pageview'${entryOnly ? ' AND entry = 1' : ''}
      AND (${expr}) IS NOT NULL AND (${expr}) <> ''${extraWhere ? ' AND ' + extraWhere : ''}
    GROUP BY 2`);
}

async function computeDay(env, day) {
  const res = await env.DB.batch([TOTALS_SQL, ...DIM_SQL].map(q => env.DB.prepare(q).bind(day)));
  const totals = res[0].results[0] || { visitors: 0, visits: 0, pageviews: 0, bounces: 0, duration: 0 };
  const dims = res.slice(1).flatMap(r => r.results);
  return { totals, dims };
}

async function rollUpDay(env, day) {
  const { totals, dims } = await computeDay(env, day);
  const stmts = [
    env.DB.prepare('DELETE FROM daily_dims WHERE day = ?').bind(day),
    env.DB.prepare('INSERT OR REPLACE INTO daily_totals (day, visitors, visits, pageviews, bounces, duration) VALUES (?,?,?,?,?,?)')
      .bind(day, totals.visitors, totals.visits, totals.pageviews, totals.bounces, totals.duration),
  ];
  const ins = env.DB.prepare('INSERT OR REPLACE INTO daily_dims (day, dim, key, visitors, hits, extra) VALUES (?,?,?,?,?,?)');
  for (const d of dims) stmts.push(ins.bind(day, d.dim, String(d.key), d.visitors || 0, d.hits || 0, d.extra || 0));
  for (let i = 0; i < stmts.length; i += 100) await env.DB.batch(stmts.slice(i, i + 100));
}

// Roll up every finished day not yet rolled up; drop old salts and raw rows.
async function housekeeping(env) {
  const today = zurichDay(Date.now());
  // Only look at days after the last rolled-up one, so this stays cheap.
  const last = await env.DB.prepare('SELECT MAX(day) AS d FROM daily_totals').first();
  const pending = await env.DB.prepare(
    `SELECT DISTINCT day FROM events WHERE day > ?1 AND day < ?2 ORDER BY day`
  ).bind((last && last.d) || '0000-00-00', today).all();
  for (const r of pending.results) await rollUpDay(env, r.day);
  const keep = Math.max(2, parseInt(env.RAW_RETENTION_DAYS || '7', 10) || 7);
  const cutoff = addDays(today, -keep);
  await env.DB.batch([
    env.DB.prepare('DELETE FROM salts WHERE day < ?').bind(today),
    // Only delete raw days that are safely rolled up.
    env.DB.prepare('DELETE FROM events WHERE day < ?1 AND day IN (SELECT day FROM daily_totals)').bind(cutoff),
  ]);
  saltCache = { day: '', salt: '' };
}

/* ---------- stats API ---------- */
const RANGES = { today: 0, '7d': 6, '30d': 29, '90d': 89, '12m': 364 };

async function stats(url, env) {
  await housekeeping(env);   // cheap when nothing is pending; covers a missed cron
  const now = Date.now();
  const today = zurichDay(now);
  const range = url.searchParams.get('range') || '30d';
  let from;
  if (range === 'all') {
    const first = await env.DB.prepare('SELECT MIN(day) AS d FROM daily_totals').first();
    from = (first && first.d) || today;
  } else {
    from = addDays(today, -(RANGES[range] ?? 29));
  }

  const [past, pastDims, live, todayData] = await Promise.all([
    env.DB.prepare('SELECT * FROM daily_totals WHERE day >= ? AND day < ? ORDER BY day').bind(from, today).all(),
    env.DB.prepare(`SELECT dim, key, SUM(visitors) AS visitors, SUM(hits) AS hits, SUM(extra) AS extra
                    FROM daily_dims WHERE day >= ? AND day < ? GROUP BY dim, key`).bind(from, today).all(),
    env.DB.prepare(`SELECT COUNT(DISTINCT visitor) AS visitors, COUNT(*) AS pageviews FROM events
                    WHERE day >= ? AND kind = 'pageview' AND ts > ?`).bind(addDays(today, -1), now - 30 * 60 * 1000).first(),
    computeDay(env, today),
  ]);

  const days = past.results.slice();
  days.push({ day: today, ...todayData.totals });
  const totals = days.reduce((a, d) => {
    for (const k of ['visitors', 'visits', 'pageviews', 'bounces', 'duration']) a[k] += d[k] || 0;
    return a;
  }, { visitors: 0, visits: 0, pageviews: 0, bounces: 0, duration: 0 });

  // Merge past + today per dimension.
  const merged = {};
  for (const r of [...pastDims.results, ...todayData.dims]) {
    const m = (merged[r.dim] = merged[r.dim] || {});
    const e = (m[r.key] = m[r.key] || { key: r.key, visitors: 0, hits: 0, extra: 0 });
    e.visitors += r.visitors || 0; e.hits += r.hits || 0; e.extra += r.extra || 0;
  }
  const dims = {};
  for (const [dim, m] of Object.entries(merged)) {
    dims[dim] = Object.values(m).sort((a, b) => (b.visitors - a.visitors) || (b.hits - a.hits)).slice(0, 100);
  }

  // Time series: hourly for today, else daily (the dashboard groups by month when long).
  let series;
  if (range === 'today') {
    const hours = Object.fromEntries((merged.hour ? Object.values(merged.hour) : []).map(h => [h.key, h]));
    series = Array.from({ length: 24 }, (_, h) => {
      const k = String(h).padStart(2, '0');
      return { label: k + ':00', visitors: hours[k]?.visitors || 0, pageviews: hours[k]?.hits || 0 };
    });
  } else {
    const byDay = Object.fromEntries(days.map(d => [d.day, d]));
    series = [];
    for (let d = from; d <= today; d = addDays(d, 1)) {
      series.push({ label: d, visitors: byDay[d]?.visitors || 0, pageviews: byDay[d]?.pageviews || 0, visits: byDay[d]?.visits || 0 });
    }
  }

  return { range, from, to: today, generatedAt: new Date(now).toISOString(), live, totals, series, dims };
}
