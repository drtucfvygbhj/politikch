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
