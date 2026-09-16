# Community poll backend

The site is static and works with **no backend**. The one optional server-backed
feature is the **community poll** — the "how others voted" bars on present/future
initiatives, referendums and session votes.

Until you configure a backend, the poll shows an honest *"not yet connected"*
state and never invents numbers. Everything else (a visitor's own votes, the
My-profile page, party alignment) is fully on-device and needs nothing here.

## What the client sends

Only an **anonymous aggregate vote**. No account, name, cookie, or identifier.
The server stores running totals per item, never a row linking a vote to a person.
This is what the Privacy Policy (`#/privacy`) commits to — keep the backend within
that promise (no logging of IPs against votes, no per-user records).

## HTTP contract

Set `POLL_API` in [`js/config.js`](js/config.js) to the base URL (no trailing slash).
The client calls exactly two endpoints and expects JSON. CORS must allow the site
origin (GitHub Pages domain / your custom domain).

### `GET {POLL_API}/tally?type=<type>&id=<id>`
`type` is `initiative` or `session`; `id` is the item id.
Response:
```json
{ "yes": 1234, "no": 567 }
```

### `POST {POLL_API}/vote`
Body:
```json
{ "type": "initiative", "id": "vote-20260927-6880", "choice": "yes", "prev": null }
```
- `choice` is `"yes"`, `"no"`, or `null` (the visitor cleared their vote).
- `prev` is the visitor's previous choice (or `null`) so the server can move a
  changed vote (decrement `prev`, increment `choice`) without double-counting.
Response: the updated tally, same shape as `GET`.

## Reference implementation — Cloudflare Worker + KV

Free tier is enough for a poll. Create a KV namespace `POLL` and bind it, then:

```js
// worker.js
const CORS = {
  'Access-Control-Allow-Origin': '*',            // or lock to your domain
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};
const json = (o) => new Response(JSON.stringify(o), { headers: { 'Content-Type': 'application/json', ...CORS } });
const keyOf = (type, id) => `${type}:${id}`;
const clamp = (c) => (c === 'yes' || c === 'no') ? c : null;

export default {
  async fetch(req, env) {
    if (req.method === 'OPTIONS') return new Response(null, { headers: CORS });
    const url = new URL(req.url);

    if (req.method === 'GET' && url.pathname === '/tally') {
      const k = keyOf(url.searchParams.get('type'), url.searchParams.get('id'));
      const t = (await env.POLL.get(k, 'json')) || { yes: 0, no: 0 };
      return json({ yes: t.yes || 0, no: t.no || 0 });
    }

    if (req.method === 'POST' && url.pathname === '/vote') {
      const b = await req.json().catch(() => ({}));
      const type = String(b.type || ''), id = String(b.id || '');
      if (!type || !id) return json({ error: 'bad request' });
      const k = keyOf(type, id);
      const t = (await env.POLL.get(k, 'json')) || { yes: 0, no: 0 };
      const prev = clamp(b.prev), choice = clamp(b.choice);
      if (prev) t[prev] = Math.max(0, (t[prev] || 0) - 1);   // moving/clearing a vote
      if (choice) t[choice] = (t[choice] || 0) + 1;           // casting/changing a vote
      await env.POLL.put(k, JSON.stringify(t));
      return json({ yes: t.yes || 0, no: t.no || 0 });
    }
    return json({ error: 'not found' });
  },
};
```

Deploy (`wrangler deploy`), copy the Worker URL into `POLL_API`, done.

## Notes & honest limits

- **This is an unofficial straw poll.** It is client-driven, so it can be gamed
  (repeat votes from cleared storage, scripted requests). Don't present it as a
  representative survey — the UI already labels it "unofficial" with striped bars.
- If you want light abuse resistance, add per-item rate limiting keyed on a coarse,
  non-identifying signal — but do **not** start logging IPs against individual
  votes; that would break the privacy commitment. Keep only aggregate totals.
- Any provider works (Supabase RPC, a tiny serverless function + Postgres/Redis,
  etc.) as long as it honours the two-endpoint contract above.
