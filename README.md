# Certificate Admin Console

Internal admin console for a multi-tenant training platform: tenant admins list certificates,
bulk-issue them for a course, revoke them, and export CSV. Built for the Ocean AI Labs technical
assessment. Design: [ARCHITECTURE.md](ARCHITECTURE.md). AI evidence: [`ai/`](ai/).

Stack: FastAPI + SQLite (stdlib `sqlite3`, WAL) · Next.js 16 (React, TypeScript, Tailwind).

## Start (one command)

Requires `python3` ≥ 3.11 and `node` ≥ 20.

```bash
./start.sh
```

Creates a venv and installs the declared Python deps, runs `npm install`, creates the schema,
seeds the quick-start data (idempotent) and starts the backend on <http://localhost:8000>
(OpenAPI at `/docs`) and the UI on <http://localhost:3000>. Ctrl-C stops both. The SQLite file
is `backend/data/app.db`. (`make dev` is an alias.)

Verification (second command):

```bash
make verify        # A1–A5, A7 + list behaviour on a fresh temp DB (pytest)
make verify-big    # A6: 100,000 rows, two exports, list during export
cd frontend && npm run lint && npx tsc --noEmit   # frontend static checks (clean)
```

`docker-compose.yml` and the two Dockerfiles are included but **untested** — Docker Desktop on
the development machine could not start containers during the sitting, so Docker was dropped as
the startup path (see `ai/decision-log.md` D4).

## Actors

No login. Every API call carries the actor in a header; the UI has an "Acting as" selector that
sets it.

| Header | Tenant | Timezone |
|---|---|---|
| `X-Actor: alice@east.test` | East | Australia/Sydney |
| `X-Actor: bob@west.test` | West | Australia/Perth |

Missing/unknown actor → `401`. Cross-tenant resources → `404` (non-revealing).

## Quick-start demo data

Both tenants contain course **Safety 101** and learner **Alex Lee**, plus course *Data Privacy
Basics* and learners Priya Nair, Sam Chen, Jordan Kim, Maria Garcia, Tom Walsh.

Safety 101 enrollments per tenant: Alex Lee *completed*, Priya Nair *completed*, Sam Chen
*incomplete*, Jordan Kim *completed + already certified* (`<TENANT>-SEED-0001`, issued
`2026-01-10T13:30:00Z` — the A5 timestamp), Maria Garcia *completed + already certified*
(`<TENANT>-SEED-0002`, issued `2025-12-31T14:00:00Z`).

## API

```
GET  /health
GET  /api/actors                       seeded admins (for the selector)
GET  /api/me
GET  /api/courses                      tenant's courses
GET  /api/certificates?q=&sort=&dir=&page=&page_size=
     sort ∈ issued_local_date (default, desc) | learner_name | serial | course_title | status
     q matches learner name or serial (substring, case-insensitive)
GET  /api/certificates/export.csv?q=&sort=&dir=      streaming CSV, same filter/sort as the list
GET  /api/certificates/{id}            detail + audit trail
POST /api/certificates/{id}/revoke     200; audit event only on the active→revoked transition
POST /api/certificates/bulk-issue      body {"course_id": N}, header Idempotency-Key (required)
```

Errors: `{"detail": {"code": "...", "message": "..."}}`.

## Reproducing the acceptance scenarios

All of A1–A5 and A7 are automated in
[`backend/tests/test_acceptance.py`](backend/tests/test_acceptance.py) (`make verify`); A6 is
`make verify-big`. Manual equivalents against the running app (`<EAST_SAFETY_ID>` etc. come from
`curl -H "X-Actor: alice@east.test" localhost:8000/api/courses`):

**A1 Tenant isolation**
```bash
curl -s -H "X-Actor: bob@west.test" localhost:8000/api/certificates            # only WEST-… serials
curl -s -H "X-Actor: bob@west.test" localhost:8000/api/certificates/1           # 404 (East cert)
curl -s -H "X-Actor: bob@west.test" -X POST localhost:8000/api/certificates/1/revoke   # 404
# East's Safety 101 course id is in `curl -H "X-Actor: alice@east.test" localhost:8000/api/courses`
curl -s -H "X-Actor: bob@west.test" -H "Idempotency-Key: x1" -H "Content-Type: application/json" \
     -d '{"course_id": <EAST_SAFETY_ID>}' localhost:8000/api/certificates/bulk-issue       # 404, nothing written
curl -s -H "X-Actor: bob@west.test" localhost:8000/api/certificates/export.csv  # no EAST- rows
```
In the UI: switch "Acting as" to bob while on an East detail page → error `certificate_not_found`.

**A2 Retry safety** — same request, same key, sequentially and concurrently:
```bash
for i in 1 2 3 4 5; do curl -s -H "X-Actor: alice@east.test" -H "Idempotency-Key: k1" \
  -H "Content-Type: application/json" -d '{"course_id": <EAST_SAFETY_ID>}' \
  localhost:8000/api/certificates/bulk-issue & done; wait
```
All five bodies are identical (`operation_id` equal; later ones have `"replayed": true`); the list
grows by exactly 2 (Alex, Priya); each new certificate's detail shows exactly one
`certificate.issued` audit row.

**A3 Key misuse** — same key, different course:
```bash
curl -s -H "X-Actor: alice@east.test" -H "Idempotency-Key: k1" -H "Content-Type: application/json" \
     -d '{"course_id": <EAST_PRIVACY_ID>}' localhost:8000/api/certificates/bulk-issue   # 409 idempotency_key_reused
```

**A4 Learner outcomes** — the A2 response lists: Alex Lee `issued`, Priya Nair `issued`,
Sam Chen `skipped / not_completed`, Jordan Kim and Maria Garcia `skipped / already_certified`.
The UI bulk-issue panel shows the same table. A learner whose certificate was **revoked** is
reported as `skipped / certificate_revoked` and is *not* re-issued: one certificate per
enrollment, and a revocation is a deliberate admin action that bulk issue must not silently undo.

**A5 DST and local date**
```bash
curl -s -H "X-Actor: alice@east.test" "localhost:8000/api/certificates?q=SEED-0001"   # issued_at_local 2026-01-11 00:30
curl -s -H "X-Actor: bob@west.test"   "localhost:8000/api/certificates?q=SEED-0001"   # issued_at_local 2026-01-10 21:30
curl -s -H "X-Actor: alice@east.test" "localhost:8000/api/certificates/export.csv?q=SEED-0001"   # …,2026-01-11
```
Sorting by `issued_local_date` and the CSV column both use the tenant-local calendar date
(stored on the row at issuance, computed with `zoneinfo`).

**A6 Export growth**
```bash
make big-data          # = cd backend && .venv/bin/python seed.py --big EAST --rows 100000
time curl -s -H "X-Actor: alice@east.test" \
  "localhost:8000/api/certificates/export.csv?q=Lee&sort=learner_name&dir=asc" -o /tmp/e1.csv &
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Actor: alice@east.test" \
  "localhost:8000/api/certificates?q=Lee&sort=learner_name&dir=asc&page=3"   # 200 while export runs
wait
time curl -s -H "X-Actor: alice@east.test" \
  "localhost:8000/api/certificates/export.csv?q=Lee&sort=learner_name&dir=asc" -o /tmp/e2.csv
cmp /tmp/e1.csv /tmp/e2.csv && echo identical
```
The generator deliberately repeats learner names (120 distinct names over 5,000 learners) and
issue dates, so the chosen sort field has many equal keys; order is total (`sort, id`) and
therefore identical across runs. Locally the filtered export completes in ≈1 s. The generator
only appends; quick-start rows are untouched, and it refuses to run twice on the same DB.

**A7 Revocation audit**
```bash
curl -s -X POST -H "X-Actor: alice@east.test" localhost:8000/api/certificates/<ID>/revoke   # status revoked, 1 revoked audit row
curl -s -X POST -H "X-Actor: alice@east.test" localhost:8000/api/certificates/<ID>/revoke   # same, still 1
```
In the UI: detail page → Revoke → confirm; the audit trail shows a single `certificate.revoked`.

## How the hard parts work

- **Tenant isolation**: the actor's `tenant_id` is bound in every SQL statement; course lookup for
  bulk issue happens inside the write transaction before any insert, so a cross-tenant request
  rolls back having written nothing (not even the idempotency row).
- **Idempotency**: `idempotency_keys` has `PRIMARY KEY (tenant_id, key)`; the whole bulk issue is
  one `BEGIN IMMEDIATE` transaction that starts by inserting that row. Concurrent duplicates queue
  on SQLite's write lock, then find the row and replay the stored response. Same key with a
  different payload hash → 409. `certificates.enrollment_id UNIQUE` is the backstop.
- **Export**: a single ordered cursor streamed in 2,000-row chunks over its own connection; WAL
  mode lets list reads run concurrently. Sort columns are whitelisted and always tie-broken by
  `id`.
- **Revocation**: conditional `UPDATE … WHERE status='active'`; the audit row is written only when
  `rowcount == 1`.

## Known defects / limitations / unfinished

- `learner_name` and `course_title` are snapshotted on the certificate; renaming a learner or
  course does not update existing certificates (intentional, see `ai/decision-log.md` D3).
- Search is a `LIKE '%q%'` scan over the tenant's rows; fine at 100 k rows (<100 ms), would need
  FTS or a trigram index at a much larger scale.
- Idempotency keys are never expired.
- No re-issue after revocation. Bulk issue skips such learners with reason `certificate_revoked`;
  an explicit, audited "re-issue" action would be the right follow-up and is out of scope.
- The course dropdown scopes the bulk operation only; the certificate list always shows every
  certificate in the tenant (search is by learner name or serial, as the brief specifies). There
  is no course filter on the list.
- No eligibility preview before bulk issue. Enrolled learners who hold no certificate (e.g. an
  incomplete learner) are visible only in the outcome table *after* the operation runs; nothing
  in the UI lists a course's enrollments beforehand. The natural follow-up is a read-only
  preview in the bulk panel that reuses the same eligibility logic as the issue itself.
- The revoke confirmation is the browser's native `confirm()`; not a styled modal.
- `GET /api/actors` lists both tenants' admin emails so the demo selector can work; this is the
  "no login" shortcut the brief allows and would not exist in production.
- Audit trail is shown on the detail page only; there is no global audit view.
- No automated UI tests; the UI was verified manually in the browser (see decision log D2).
- Docker files are present but untested (see "Start"). `./start.sh` is the supported path.

## Time accounting

All times UTC, taken from `git log` and the native AI transcript (`ai/sessions/`), unaltered.
The AI session started at 06:33:09.

| Commit | Time | Elapsed | Content |
|---|---|---|---|
| `2fdf3f2` | 06:49:48 | +16:39 | backend API + A1–A7 tests |
| `bf96987` | 06:54:48 | +21:39 | UI, Docker files, Makefile |
| `db9a5b3` | 07:09:11 | +36:02 | README, decision log |
| `27f6511` | 07:10:51 | +37:42 | session export |
| `ecd381b` | 07:28:16 | +55:07 | `start.sh`; Docker dropped after two failed starts |
| `41031d4` | 07:37:43 | +64:34 | lint fixes found in the final criteria check (D5) |
| `b472aa5` | 07:52:05 | +78:56 | `written-answers.md` (no AI) |

The build and packaging were complete at +55 min. The final verification pass — which found the
lint errors — ran over the hour by about 10 minutes (roughly half of that spent on Docker
retries before dropping it). Section 6 was then written separately, as the brief's own schedule
places it. Nothing was backdated or squashed to fit the limit.

## AI interaction evidence and completeness declaration

- `ai/sessions/` — native Claude Code JSONL transcript(s) of every session used, including tool
  calls, file edits, commands, errors and model identifiers (as Claude Code records them).
- `ai/session-index.csv` — one row per session (UTC).
- `ai/decision-log.md` — accepted / corrected / tradeoff decisions linked to session, evidence
  and commits.
- Tool action evidence: Claude Code's JSONL includes every tool call and result, so no separate
  activity log is needed.
- Tools used: Claude Code (Claude desktop app, Code tab). Models: `claude-sonnet-5-5` for the
  initial `/scaffold` turn, `claude-fable-5-1` for everything after. No other AI tool, no inline
  autocomplete, no IDE AI features were used.
- Export limitation: none known — the JSONL is the tool's native, unedited record. Secrets: none
  were present; nothing was redacted.
- `written-answers.md` (Section 6) was written by the candidate without any AI assistance; the AI
  instruction files (`CLAUDE.md`, `AGENTS.md`) explicitly forbid AI from touching it.
