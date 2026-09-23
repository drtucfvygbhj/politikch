/* ============================================================
   Site configuration
   ============================================================
   POLL_API — base URL of the community-poll backend (see BACKEND.md).

   The community poll ("how others voted") is the ONLY part of the site that
   talks to a server. It transmits an anonymous vote choice (no account, no
   identifier) and reads back aggregate counts. Leave POLL_API empty and the
   poll shows a clearly-labelled "not yet connected" state — everything else
   (your own votes, your profile, party alignment) stays fully on-device and
   the site remains a static, backend-free deployment.

   To turn the poll on: deploy the reference backend in BACKEND.md, then set
   POLL_API to its base URL, e.g. 'https://your-worker.example.workers.dev'.
   No trailing slash. */
export const POLL_API = '';

/* ANALYTICS_API — base URL of the site's own anonymous statistics service
   (analytics-worker/, a Cloudflare Worker). No trailing slash.

   Empty = statistics off: js/analytics.js sends nothing, and the Privacy page
   leaves out its statistics section (so it never describes processing that
   isn't happening). Set it to the Worker's address to switch statistics on —
   and add that same origin to connect-src in index.html's
   Content-Security-Policy, or the browser will block the beacons. */
export const ANALYTICS_API = 'https://politikch-analytics.soft-hill-f9fb.workers.dev';

/* PAID_PRODUCT_LIVE — whether the planned paid analysis product is shown.

   While false, nothing on the site offers or advertises a paid product: the
   Subscribe page and its footer link are hidden (#/subscribe goes home), and
   the About and Privacy pages leave out their sections about it. That keeps
   the site a free information service until the product actually exists —
   an offer of a paid service brings the Impressum duty (UWG Art. 3(1)(s):
   operator's real name and postal address) and needs its own privacy terms.
   Flip to true only when the product launches and those are in place. */
export const PAID_PRODUCT_LIVE = false;
