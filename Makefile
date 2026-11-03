.PHONY: up dev verify verify-big big-data

## One command: build images, install declared deps, seed demo data, start backend (8000) + frontend (3000)
up:
	docker compose up --build

## Local fallback without Docker (needs python3 >= 3.11 and node >= 20)
dev:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python seed.py
	cd frontend && npm install
	(cd backend && .venv/bin/uvicorn main:app --port 8000) & (cd frontend && npm run dev); wait

## Acceptance scenarios A1-A5, A7 + list behaviour (fresh temp DB each run)
verify:
	cd backend && .venv/bin/python -m pytest -q

## A6: generates 100,000 East rows on a temp DB, exports twice, lists during export
verify-big:
	cd backend && .venv/bin/python -m pytest -q -m big -s

## Append 100,000 generated East certificates to the running app's DB (quick-start rows untouched)
big-data:
	cd backend && .venv/bin/python seed.py --big EAST --rows 100000
