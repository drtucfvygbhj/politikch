-- Politikch analytics — D1 (SQLite) schema.
-- Apply with: wrangler d1 execute politikch-analytics --remote --file=schema.sql

-- One row per page view / action / engagement ping. Never an IP address.
-- `visitor` is a one-way hash of (daily salt, IP, user agent); the salt is
-- deleted after its day, so the same person can't be linked across days.
CREATE TABLE IF NOT EXISTS events (
  id           INTEGER PRIMARY KEY,
  ts           INTEGER NOT NULL,          -- ms since epoch
  day          TEXT    NOT NULL,          -- YYYY-MM-DD, Europe/Zurich
  hour         INTEGER NOT NULL,          -- 0–23, Europe/Zurich
  kind         TEXT    NOT NULL,          -- 'pageview' | 'event' | 'engagement'
  route        TEXT    NOT NULL,          -- e.g. '/', '/party/SVP'
  entry        INTEGER NOT NULL DEFAULT 0,-- 1 = first page view of a page load
  name         TEXT,                      -- event name (kind = 'event')
  prop         TEXT,                      -- event detail / 'lang=xx' on entry
  ref          TEXT,                      -- referring host (entry only)
  utm_source   TEXT,
  utm_medium   TEXT,
  utm_campaign TEXT,
  country      TEXT,
  region       TEXT,
  city         TEXT,
  device       TEXT,
  browser      TEXT,
  os           TEXT,
  screen       TEXT,
  lang         TEXT,                      -- site language
  blang        TEXT,                      -- browser language
  visitor      TEXT    NOT NULL,
  duration     INTEGER                    -- ms visible (kind = 'engagement')
);
-- A single index keeps D1 row-writes low (each index costs a write per insert).
CREATE INDEX IF NOT EXISTS events_day_kind_ts ON events(day, kind, ts);

-- Daily random salt for the visitor hash; each is deleted once its day is over.
CREATE TABLE IF NOT EXISTS salts (
  day  TEXT PRIMARY KEY,
  salt TEXT NOT NULL
);

-- Finished days, rolled up (kept forever, tiny).
CREATE TABLE IF NOT EXISTS daily_totals (
  day       TEXT PRIMARY KEY,
  visitors  INTEGER NOT NULL,
  visits    INTEGER NOT NULL,
  pageviews INTEGER NOT NULL,
  bounces   INTEGER NOT NULL,
  duration  INTEGER NOT NULL             -- total visible ms
);

-- Finished days, per dimension (pages, sources, countries, events, …).
CREATE TABLE IF NOT EXISTS daily_dims (
  day      TEXT    NOT NULL,
  dim      TEXT    NOT NULL,
  key      TEXT    NOT NULL,
  visitors INTEGER NOT NULL,
  hits     INTEGER NOT NULL,
  extra    INTEGER NOT NULL,
  PRIMARY KEY (day, dim, key)
);
