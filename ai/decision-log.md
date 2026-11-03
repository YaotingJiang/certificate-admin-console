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

## D5 — Corrected: `npm run lint` failed on the AI-written React components

- **What happened**: during the final criteria check, `npm run lint` (eslint-config-next 16,
  React Compiler rules) reported 4 errors `react-hooks/set-state-in-effect` — the list page,
  detail page and bulk panel all called `setState` synchronously inside `useEffect` to reset
  loading/error/page state when the actor or query changed. Type-check and runtime were fine;
  this was a code-quality finding a reviewer would hit immediately.
- **Correction**: loading/error are now *derived* (`loaded.key !== requestKey`) instead of set in
  effects; the page and bulk panel are mounted with `key={actor}` so a tenant switch remounts and
  resets state; page resets happen in the search/sort handlers; the idempotency key is created
  lazily in the submit handler. `StatusBadge` moved out of `page.tsx` (non-page exports break
  `next build`). Lint and `tsc --noEmit` are clean; the full UI walkthrough was repeated after
  the change (search, empty state, sort both directions, double-click guard → one key,
  revoke with confirmation → one audit row, actor switch, 100 k-row paging "Page 2 of 5001",
  error state with backend down).
- **Commit**: "fix(ui): derive loading state, key by actor — lint clean".

## D4 — Scope: Docker Compose planned as the one startup command, then dropped for `./start.sh`

- **Plan** (ARCHITECTURE.md §6): `docker compose up --build` as the single startup command,
  local `make dev` as fallback — matching the candidate's usual Docker-first verification habit.
- **What happened**: the compose files and Dockerfiles were written, but Docker Desktop on the
  development machine could not start any container during the sitting (containers stuck in
  `Created`, `docker compose up` hanging; restarting `com.docker.vmnetd` did not help). Two
  retries cost ~10 minutes of the time box.
- **Decision** (candidate's call, in words: "if docker is not working, stop using it. It takes
  too long"): stop spending time on Docker; make the plain local path the documented one command.
  `./start.sh` creates the venv, installs both dependency sets, seeds and starts both servers.
  The Docker files stay in the repo, labelled untested in the README rather than deleted or
  claimed to work.
- **Verification**: `./start.sh` run from a clean shell; `/health` and the UI probed on 8000/3000.
- **Commit**: see `git log` entry "chore: start.sh as the one startup command".
