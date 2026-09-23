# Politikch analytics (Cloudflare Worker)

The site's own anonymous, cookie-free visit statistics and a private dashboard.
Runs entirely on Cloudflare's free plan (Workers + D1). Not part of the static
site: the Pages deploy only publishes its allowlist, so this folder never goes live.

- **Site side:** [`js/analytics.js`](../js/analytics.js), switched on by
  `ANALYTICS_API` in [`js/config.js`](../js/config.js) (empty = off).
- **Worker:** [`src/index.js`](src/index.js): `POST /e` (beacons),
  `GET /dashboard` + `GET /api/stats` (password-protected), hourly cron.
- **Database:** [`schema.sql`](schema.sql) (D1 / SQLite, EU jurisdiction).

## Privacy model
No cookies and no device storage (except the visitor's own opt-out flag, set
by the switch on the Privacy page or `?analytics=off`). Global Privacy Control
and Do Not Track are honoured. **Never send a vote choice or any other
political opinion** — that is sensitive personal data and would need explicit
consent; the `vote` action carries only the item kind. The IP address is never stored: a visitor is a one-way hash of
a random **daily** salt + IP + user agent, and each salt is deleted when its
day ends, so nobody can be recognised across days. Raw rows are deleted after
`RAW_RETENTION_DAYS` (7); anonymous daily totals are kept. Keep the Privacy
page (`privacy.*analytics*` keys in `data/i18n.json`) in line with any change.

## First-time setup
Run from this folder, with Wrangler installed and logged in (`wrangler login`):

```bash
wrangler d1 create politikch-analytics --jurisdiction eu --binding DB --update-config
wrangler d1 execute politikch-analytics --remote --file=schema.sql
wrangler secret put DASHBOARD_PASSWORD
wrangler deploy
```

Then open `https://<worker>.workers.dev/dashboard` (any username, your password;
10 wrong attempts lock that address out for 15 minutes).

To switch the site on: set `ANALYTICS_API` in `js/config.js` to the Worker's
origin (no trailing slash), add that origin to `connect-src` in the
Content-Security-Policy in `index.html`, and push.

## Everyday
- **Redeploy after editing:** `wrangler deploy`
- **Change the password:** `wrangler secret put DASHBOARD_PASSWORD`
- **Allowed site origins:** `ALLOWED_ORIGINS` in `wrangler.jsonc` (beacons
  from anywhere else are dropped)
- **Live logs:** `wrangler tail`
- **Exclude your own visits:** open the site once per browser with `?analytics=off`

## Tracked actions
`lang`, `search`, `vote`, `share`, `outbound`, `vote_open`, `contact`,
`glossary`. To add one: add the name to `EVENT_NAMES` in `src/index.js`, a
label in `EVENT_LABELS` in `src/dashboard.html`, and call `track(name, detail)`
from the site.

## Free-plan limits
Workers: about 100,000 requests a day. D1: daily limits on rows read and written.
Each page view is one request and roughly two row-writes. If a limit is hit,
that day's beacons fail silently; the website is unaffected. A free account
with no payment method cannot be charged.

## Local testing
Add a `d1_databases` entry with any `database_id` to a copy of `wrangler.jsonc`,
put `DASHBOARD_PASSWORD=…` in `.dev.vars`, then:
```bash
wrangler d1 execute politikch-analytics --local --file=schema.sql
wrangler dev
```
