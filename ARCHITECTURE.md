# ARCHITECTURE — Certificate Admin Console

Single source of truth for the Ocean AI Labs take-home (1-hour sitting).
Classification: **(A) standard web application** — no LLM/agent decomposition. Plain layered architecture.

## 0. Hard constraints pulled from the brief

| Constraint | Decision |
|---|---|
| Backend Go/Python/Node + SQLite/MySQL/Postgres | **FastAPI + SQLite (stdlib `sqlite3`, WAL mode)** — already scaffolded |
| Frontend Vue 3 / React | **Next.js 15 App Router (React, TS, Tailwind)** — already scaffolded |
| One startup command | `docker compose up --build` (installs deps, seeds demo data, starts both). Fallback: `make dev` (local venv + npm) |
| Actor identification, no login | Header `X-Actor: alice@east.test` → admin → tenant. Unknown → 401 |
| No prod auth / cloud / notifications | Out of scope. No extra features |
| Section 6 `written-answers.md` | **Candidate-only. AI never reads, drafts, edits, or polishes it.** Recorded in `CLAUDE.md`/`AGENTS.md` |
| AI evidence | `ai/sessions/` (Claude Code JSONL from `~/.claude/projects/`), `ai/session-index.csv`, `ai/decision-log.md`, completeness declaration in README |

Note: Section 7 of the brief sums to 180 min; you said 1 hour — the budget below assumes **60 min of build time**.

## 1. Data model (SQLite, `backend/schema.sql`)

```
tenants          id, code (EAST|WEST), name, timezone (Australia/Sydney | Australia/Perth)
admins           id, tenant_id, email UNIQUE
learners         id, tenant_id, name
courses          id, tenant_id, title
enrollments      id, tenant_id, learner_id, course_id, completed_at_utc NULL
                 UNIQUE(learner_id, course_id)
certificates     id, tenant_id, enrollment_id UNIQUE, learner_id, course_id,
                 learner_name, course_title            -- snapshot at issuance (no joins for list/sort/export)
                 serial UNIQUE, status ('active'|'revoked'),
                 issued_at_utc, issued_local_date (YYYY-MM-DD, tenant tz, computed at write),
                 revoked_at_utc NULL
                 INDEX (tenant_id, issued_local_date, id), (tenant_id, learner_name, id), (tenant_id, serial)
audit_events     id, tenant_id, actor_id, action ('certificate.issued'|'certificate.revoked'),
                 certificate_id, operation_id NULL, created_at_utc
                 INDEX (certificate_id)
idempotency_keys tenant_id, key, request_hash, status ('in_progress'|'done'),
                 response_json NULL, created_at_utc
                 PRIMARY KEY (tenant_id, key)
```

Invariants enforced by the DB, not just code:
- `certificates.enrollment_id UNIQUE` → at most one certificate per enrollment (A2/A4 safety net).
- `idempotency_keys PK (tenant_id, key)` → one logical operation per key per tenant (A2/A3).
- All tables carry `tenant_id`; every query is `WHERE tenant_id = :actor_tenant` (A1).

## 2. Data flow

```
 Browser (Next.js)                               FastAPI                              SQLite (WAL)
 ───────────────                                 ───────                              ────────────
 actor selector ──X-Actor header──▶ deps.get_actor() ──▶ admins ⨝ tenants ──▶ Actor{tenant_id, tz}
                                         │
 list page  ──GET /api/certificates──▶ routers.certificates ─▶ services.certificates.query()
   q,sort,dir,page                       │                      whitelist sort col + ", id ASC"
                                         │                      LIKE on learner_name/serial ──▶ SELECT … LIMIT/OFFSET
                                         ◀── {items,total,page,page_size}  (issued_at_local formatted via zoneinfo)
 export btn ──GET …/export.csv──▶ StreamingResponse(csv_rows())  opens its OWN connection
   same q,sort,dir                       │   inside the generator thread, fetchmany(2000) ──▶ SELECT … ORDER BY sort,id
                                         │                                                   (no OFFSET; single cursor)
 bulk issue ──POST /bulk-issue──▶ services.issuance.bulk_issue()
   {course_id} + Idempotency-Key         │   BEGIN IMMEDIATE  (serialises writers; busy_timeout 30s)
                                         │   INSERT idempotency_keys  ─ conflict? ─▶ hash≠ → 409 | done → replay response
                                         │   course ∈ tenant? else 404 (nothing written)
                                         │   for each enrollment in course: completed? certified? → issued/skipped
                                         │   INSERT certificate + INSERT audit(issued) per issuance
                                         │   UPDATE idempotency_keys SET done, response_json
                                         │   COMMIT
 detail page ──GET /api/certificates/{id}──▶ cert WHERE id AND tenant_id → 404 if other tenant
 revoke   ──POST …/{id}/revoke──▶ BEGIN IMMEDIATE; UPDATE … SET revoked WHERE id AND tenant_id AND status='active'
                                         │   rowcount==1 → INSERT audit(revoked); rowcount==0 → no audit (A7 repeat)
                                         │   COMMIT → return detail
```

## 3. Component breakdown (separation of concerns)

### Backend `backend/` (flat package, run from `backend/`)
| File | Responsibility |
|---|---|
| `main.py` | FastAPI app, CORS (`http://localhost:3000`), router mounting, `/health`, startup: ensure schema + seed if empty |
| `config.py` | `DB_PATH`, CORS origins (pydantic-settings) |
| `db.py` | `connect()` per request: WAL, `busy_timeout=30000`, `foreign_keys=ON`, `row_factory=Row`, `isolation_level=None`; `write_txn()` ctx-manager issuing `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK` |
| `schema.sql` | DDL above |
| `seed.py` | `python seed.py` quick-start dataset (idempotent); `python seed.py --big EAST --rows 100000` generator (batched executemany, deliberately repeated names/dates for equal sort keys). Big mode never touches quick-start rows |
| `deps.py` | `get_actor(X-Actor)` → `Actor(id, email, tenant_id, tenant_code, tz)`; 401 on unknown |
| `tz.py` | `utc_to_local(iso, tz) -> (local_date, 'YYYY-MM-DD HH:MM')` via `zoneinfo` |
| `schemas.py` | Pydantic response/request models, error shape `{detail:{code,message}}` |
| `routers/actors.py` | `GET /api/actors` (seeded admins for selector), `GET /api/me` |
| `routers/courses.py` | `GET /api/courses` (tenant-scoped) |
| `routers/certificates.py` | list / export.csv / detail / revoke / bulk-issue — HTTP only, delegates |
| `services/certificates.py` | query builder (search, whitelisted sort + id tiebreak, pagination), detail+audit, revoke, CSV row iterator |
| `services/issuance.py` | bulk issue with idempotency + per-learner outcomes |
| `tests/test_acceptance.py` | A1–A7 via `TestClient` on a temp DB; A2 concurrency with `ThreadPoolExecutor`; A6 marked `big` |
| `Dockerfile` | python:3.12-slim, `pip install -r requirements.txt`, CMD `python seed.py && uvicorn main:app --host 0.0.0.0` |

### API surface
```
GET  /health
GET  /api/actors                         -> [{email, tenant_code}]
GET  /api/me                             -> {email, tenant:{code,name,timezone}}
GET  /api/courses                        -> [{id,title}]
GET  /api/certificates?q&sort&dir&page&page_size
     sort ∈ issued_local_date(default desc)|learner_name|serial|course_title|status ; always + ", id ASC"
     -> {items:[{id,serial,learner_name,course_title,status,issued_at_utc,issued_at_local,issued_local_date}], total, page, page_size}
GET  /api/certificates/export.csv?q&sort&dir   -> text/csv stream: learner_name,course_title,serial,issued_local_date
GET  /api/certificates/{id}              -> detail + audit:[{action,actor_email,created_at_utc,operation_id}]
POST /api/certificates/{id}/revoke       -> detail (200 even if already revoked; audit only on transition)
POST /api/certificates/bulk-issue  {course_id}  header Idempotency-Key (required, 400 if missing)
     -> {operation_id, replayed:bool, summary:{issued,skipped,failed},
         results:[{learner_id,learner_name,outcome:'issued'|'skipped'|'failed',reason,serial}]}
     409 on same key + different payload
```

### Frontend `frontend/src/`
| File | Responsibility |
|---|---|
| `lib/api.ts` | `fetch` wrapper: base URL from `NEXT_PUBLIC_API_URL`, attaches `X-Actor` from localStorage, normalises errors |
| `lib/actor.tsx` | `ActorProvider` + selector (persists choice; reloads data on change) |
| `app/page.tsx` | Certificate list: search input, sortable headers, pagination, **loading / empty / error** states, Export CSV (fetch→blob→download with same q/sort/dir), Bulk-issue panel |
| `components/BulkIssuePanel.tsx` | course select; idempotency key generated once per attempt and reused on retry; button disabled while pending; status + per-learner outcome table |
| `app/certificates/[id]/page.tsx` | detail fields (serial, course, learner, tenant-local issue date, status), Revoke with `confirm()`, audit list |

No extra client libs. Tailwind only for layout.

### Root
```
fastapi-app/                 (rename to cert-admin-console at git init — optional)
├── ARCHITECTURE.md  CLAUDE.md  AGENTS.md  README.md
├── docker-compose.yml   Makefile (dev / verify / verify-big / big-data)
├── backend/   frontend/
├── ai/sessions/  ai/session-index.csv  ai/decision-log.md
└── written-answers.md       ← candidate-only, AI-excluded
```

## 4. Acceptance scenario → mechanism

| ID | Mechanism | Verified by |
|---|---|---|
| A1 Tenant isolation | `tenant_id` from actor on every query; detail/course lookup scoped → 404; bulk-issue course check happens inside txn **before** any insert, so rejection writes nothing | test: bob hits East cert id → 404; bob bulk-issues East course → 404, cert/audit counts unchanged |
| A2 Retry safety | `BEGIN IMMEDIATE` + PK on `(tenant_id,key)`: concurrent duplicates block on the write lock, then replay stored `response_json`; `enrollment_id UNIQUE` as backstop | test: 5 threads same key → identical bodies, certs = eligible count, audit = certs |
| A3 Key misuse | `request_hash = sha256(canonical json)` compared on key hit → 409, first result untouched | test |
| A4 Outcomes | eligibility = `completed_at_utc IS NOT NULL AND no certificate for enrollment`; skip reasons `not_completed` / `already_certified`; per-row try/except → `failed` | test on seeded Safety 101 |
| A5 DST / local date | `issued_local_date` computed with `zoneinfo` at write; display string computed at read; sort/CSV use `issued_local_date` | seed both tenants with `2026-01-10T13:30:00Z`; assert `2026-01-11 00:30` (East) / `2026-01-10 21:30` (West) |
| A6 Export growth | streaming CSV, own connection per generator, `fetchmany`, index on `(tenant_id, issued_local_date, id)`, deterministic `ORDER BY sort, id`; WAL lets list reads proceed during export | `make verify-big`: generate 100k, export twice with q+sort, diff identical, each < 60 s, list call succeeds mid-export |
| A7 Revocation audit | conditional `UPDATE … AND status='active'`; audit only when `rowcount == 1` | test: revoke twice → 1 audit row |

## 5. Time budget (60 min build)

| Min | Work | Commit |
|---|---|---|
| 0–5 | `git init`, `CLAUDE.md`/`AGENTS.md` (incl. Section-6 exclusion), `schema.sql`, `db.py`, `seed.py` quick-start | `chore: scaffold + schema + seed` |
| 5–22 | backend: deps, tz, services, routers, bulk-issue idempotency, streaming export | `feat: certificate API A1–A7` |
| 22–35 | frontend: actor selector, list (states/sort/search/paging/export), bulk panel, detail+revoke | `feat: admin console UI` |
| 35–45 | `tests/test_acceptance.py` A1–A5, A7 + `--big` generator + A6 script; fix defects | `test: acceptance A1–A7` |
| 45–53 | Dockerfiles, compose, Makefile, README (startup, headers, repro steps, 100k, known defects) | `docs: README + startup` |
| 53–60 | copy Claude Code JSONL → `ai/sessions/`, `session-index.csv`, `decision-log.md`, completeness declaration, final commit | `docs: AI evidence` |
| after | **You alone**: `written-answers.md` | your commit |

Cut order if over time: (1) Docker → `make dev` only, (2) sort on status/course_title, (3) audit list in UI (keep in API).

## 6. Open decisions for you
1. Startup command: `docker compose up --build` (your Docker-first preference) with `make dev` fallback — **default**, or local-only to save ~5 min?
2. Repo folder name stays `fastapi-app` or rename to `cert-admin-console`?
