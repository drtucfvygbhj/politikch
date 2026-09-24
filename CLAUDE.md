# Politikch — rules for Claude sessions

Every change follows `GUARDRAILS.md`. In short:

1. **Review before editing (PROC-01).** Before changing any file, write the
   pre-change review from GUARDRAILS.md §11 (scope, rule map, new external
   contact, content check, risks, test plan, verdict) and wait for the owner's
   approval. Nothing is edited first.
2. **Check (PROC-02).** After editing, run `python3 scripts/check.py`. Fix every
   BLOCK. List every FLAG for the owner with what changed and why it is fine.
3. **Preview (PROC-03).** View every affected route on `localhost:8001` in at
   least EN, DE and FR, desktop and 375 px wide, before anything is committed.
4. **Sign-offs are the owner's.** Only add an `Approved-Rule: <ID> — reason`
   line to a commit message when the owner has approved that rule in the chat
   for this change. Never add one on your own judgement, and never bypass the
   pre-push hook (`--no-verify`).
5. **Never** weaken a rule, the sink baseline, the robots snapshot or the source
   registry to make a check pass, unless the owner asks for exactly that.
6. **Quiet period (POL-09).** Within 10 days of a federal ballot, don't change
   pages about the proposals on it except for corrections or privacy fixes, and
   don't start the data job by hand.
7. Legal questions go to the owner, and on to a lawyer when GUARDRAILS.md §10 says so. Never
   present a legal conclusion as settled.
