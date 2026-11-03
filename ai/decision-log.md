# AI decision log

All decisions below come from Claude Code session `2ed64df3-23e8-40d9-a214-02d5e8aafa6b`
(export: `ai/sessions/2ed64df3-23e8-40d9-a214-02d5e8aafa6b.jsonl`). Times are UTC.

## D1 — Accepted: single `BEGIN IMMEDIATE` transaction as the idempotency mechanism (A2/A3)

- **AI suggestion** (ARCHITECTURE.md, "Data flow"): run the whole bulk-issue inside one SQLite
  `BEGIN IMMEDIATE` transaction that starts by inserting the `(tenant_id, key)` row. Concurrent
  duplicates block on the write lock (busy_timeout 30 s); when they acquire it the key row already
  exists, so they replay the stored `response_json`. No `in_progress` polling loop, no background
  reconciliation.
- **Why accepted**: SQLite has a single writer anyway, so serialising on the lock costs nothing
  extra and removes a whole class of partial-state bugs. The `enrollment_id UNIQUE` constraint is
  the backstop if the logic ever regresses.
- **Verification**: `backend/tests/test_acceptance.py::test_a2_a4_bulk_issue_outcomes_and_retry_safety`
  fires 8 concurrent identical requests from separate clients and asserts identical bodies,
  exactly 2 new certificates and exactly 2 `certificate.issued` audit rows for the operation id.
  `test_a3_key_reuse_with_different_payload` asserts 409 and an unchanged first result.
- **Commit**: `2fdf3f2` (feat: certificate API …).

## D2 — Corrected: AI's `db.py` broke under uvicorn although the tests passed

- **What happened**: the first `db.py` opened connections with the sqlite3 default
  `check_same_thread=True`. The pytest suite (Starlette `TestClient`) passed 6/6. When the real
  app was driven from the browser, every request 500'd with
  `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`
  raised from the `get_db` dependency's `conn.close()` — FastAPI runs a sync dependency's setup
  and teardown on different threadpool workers under uvicorn. The UI showed "Failed to fetch" and
  the browser console showed CORS errors (the 500 had no CORS headers), which initially pointed
  the wrong way.
- **Correction**: `check_same_thread=False` on `sqlite3.connect` (each connection is still used by
  one request at a time), restart, re-run the suite (6/6) and the browser flow (bulk issue →
  issued 2 / skipped 3, list refreshed).
- **Lesson recorded**: `TestClient` is not a substitute for exercising the real server; the
  browser verification step was kept in the plan for exactly this reason.
- **Commit**: `bf96987` (feat: admin console UI … — the db.py fix landed in that commit).

- A second, smaller correction in the same pass: Next.js 16 refused `crypto.randomUUID()` inside a
  `useState` initializer during prerender ("unstable value in a Client Component"). Moved key
  generation into the actor `useEffect` / change handler; the key is still created once per
  logical attempt and reused on retry.

## D3 — Tradeoff: denormalise `learner_name` / `course_title` onto `certificates`

- **Options**: (a) normalised joins at read time; (b) snapshot the names on the certificate row.
- **Chosen**: (b). List, search, sort and the 100 k-row CSV export become single-table,
  index-backed queries (`(tenant_id, issued_local_date, id)`, `(tenant_id, learner_name, id)`),
  and the certificate records what was printed on it at issuance, which is arguably the correct
  semantics for a certificate.
- **Cost accepted**: renaming a learner or course does not update existing certificates. Noted
  in README "Known defects / limitations".
- **Verification**: `-m big` test — 100 000 generated rows, filtered export twice in well under
  the 60 s budget (≈1 s each locally), byte-identical output, list request succeeds mid-export.
- **Commit**: `2fdf3f2`.

## D4 — Scope: Docker Compose as the one startup command, local `make dev` as fallback

- The brief wants one documented command that installs declared deps, seeds and starts
  everything. `docker compose up --build` does all three reproducibly; a local `make dev` is kept
  for machines without Docker. Both are in the Makefile and README. Decided in ARCHITECTURE.md
  §6 before implementation.
