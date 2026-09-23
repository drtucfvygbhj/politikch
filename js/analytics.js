/* ============================================================
   Anonymous, cookie-free visit statistics
   ------------------------------------------------------------
   Sends page views and a few named actions to the site's own statistics
   service (analytics-worker/, a Cloudflare Worker). No cookies, nothing
   stored on the device, no IP address kept server-side — see the Privacy page
   and analytics-worker/README.md.

   Off when ANALYTICS_API (js/config.js) is empty, on localhost, for automated
   browsers, when the browser sends a Global Privacy Control or Do Not Track
   signal, and for anyone who opts out — with the switch on the Privacy page or
   by opening the site once with ?analytics=off (?analytics=on undoes it; the
   choice is remembered in this browser only).
   ============================================================ */
import { ANALYTICS_API } from './config.js?v=20260923b';

const OFF_KEY = 'politikch-analytics-off';

// Read the landing address now: app.js strips ?lang= from it during boot.
const landing = (() => {
  try { return new URLSearchParams(location.search); } catch (e) { return new URLSearchParams(); }
})();

function optedOut() {
  try {
    const flag = landing.get('analytics');
    if (flag === 'off') localStorage.setItem(OFF_KEY, '1');
    if (flag === 'on') localStorage.removeItem(OFF_KEY);
    // Drop the parameter from the address once applied, so a copied/shared
    // link doesn't silently opt out whoever opens it (as app.js does for ?lang=).
    if (flag !== null) {
      const url = new URL(location.href);
      url.searchParams.delete('analytics');
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    }
    return localStorage.getItem(OFF_KEY) === '1';
  } catch (e) { return false; }
}

// The browser's own privacy signals count as an objection.
const privacySignal = navigator.globalPrivacyControl === true
  || navigator.doNotTrack === '1' || window.doNotTrack === '1';

const available = !!ANALYTICS_API
  && !/^(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)$/.test(location.hostname)
  && location.protocol === 'https:'
  && !navigator.webdriver;
let optOut = optedOut();
let enabled = available && !privacySignal && !optOut;

/** State for the Privacy page's switch: 'unavailable' | 'signal' | 'off' | 'on'. */
export function analyticsState() {
  if (!ANALYTICS_API) return 'unavailable';
  if (privacySignal) return 'signal';
  return optOut ? 'off' : 'on';
}

/** Opt this browser out of (or back into) the statistics. */
export function setAnalyticsOptOut(off) {
  try { off ? localStorage.setItem(OFF_KEY, '1') : localStorage.removeItem(OFF_KEY); } catch (e) { /* ignore */ }
  optOut = !!off;
  enabled = available && !privacySignal && !optOut;
}

let current = null;        // route of the page being shown
let first = true;          // next page view is the landing one
let visibleSince = 0;      // performance.now() when the page last became visible
let visibleMs = 0;         // visible time accumulated on the current page

function send(events) {
  if (!enabled || !events.length) return;
  const body = JSON.stringify({ e: events });
  const url = ANALYTICS_API + '/e';
  try {
    if (navigator.sendBeacon && navigator.sendBeacon(url, new Blob([body], { type: 'text/plain' }))) return;
  } catch (e) { /* fall through */ }
  try {
    fetch(url, { method: 'POST', body, keepalive: true, headers: { 'Content-Type': 'text/plain' }, credentials: 'omit' }).catch(() => {});
  } catch (e) { /* ignore */ }
}

// Visible time on the current page since the last flush, as an event (or null).
function takeEngagement() {
  if (!current) return null;
  if (visibleSince) { visibleMs += performance.now() - visibleSince; visibleSince = document.visibilityState === 'visible' ? performance.now() : 0; }
  const d = Math.round(visibleMs);
  visibleMs = 0;
  return d >= 1000 ? { k: 'eng', r: current, d } : null;
}

function refHost() {
  try {
    if (!document.referrer) return '';
    const h = new URL(document.referrer).hostname;
    return h === location.hostname ? '' : h;
  } catch (e) { return ''; }
}

/** Record a page view. `route` is the hash path, e.g. '/party/SVP' ('/' for home). */
export function trackPageview(route, lang) {
  if (!enabled || route === current) return;
  const events = [];
  const eng = takeEngagement();
  if (eng) events.push(eng);
  current = route;
  visibleMs = 0;
  visibleSince = document.visibilityState === 'visible' ? performance.now() : 0;
  const pv = {
    k: 'pv', r: route, l: lang,
    w: (window.screen && screen.width) || 0,
    t: navigator.maxTouchPoints > 1 ? 1 : 0,
    bl: (navigator.language || '').slice(0, 2).toLowerCase(),
  };
  if (first) {
    first = false;
    pv.entry = 1;
    pv.ref = refHost();
    pv.us = landing.get('utm_source') || undefined;
    pv.um = landing.get('utm_medium') || undefined;
    pv.uc = landing.get('utm_campaign') || undefined;
    pv.ll = landing.get('lang') || undefined;
  }
  events.push(pv);
  send(events);
}

/** Record a named action (see EVENT_NAMES in analytics-worker/src/index.js). */
export function track(name, prop) {
  if (!enabled) return;
  send([{ k: 'ev', n: name, p: prop == null ? undefined : String(prop).slice(0, 80), r: current || '/' }]);
}

if (available) {   // listeners stay cheap no-ops while opted out (send() checks `enabled`)
  // Flush visible time when the tab is hidden or closed; resume when shown.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      const eng = takeEngagement();
      visibleSince = 0;
      if (eng) send([eng]);
    } else if (!visibleSince) {
      visibleSince = performance.now();
    }
  });
  // Clicks through to other websites (official sources, parties, …).
  document.addEventListener('click', (e) => {
    const a = e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    try {
      const u = new URL(a.href, location.href);
      if ((u.protocol === 'http:' || u.protocol === 'https:') && u.hostname !== location.hostname) {
        track('outbound', u.hostname.replace(/^www\./, ''));
      }
    } catch (err) { /* ignore */ }
  }, true);
}
