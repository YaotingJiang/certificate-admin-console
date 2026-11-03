.PHONY: dev verify verify-big big-data

## One command: install declared deps, seed demo data, start backend (8000) + frontend (3000)
dev:
	./start.sh

## Acceptance scenarios A1-A5, A7 + list behaviour (fresh temp DB each run)
verify:
	cd backend && .venv/bin/python -m pytest -q

## A6: generates 100,000 East rows on a temp DB, exports twice, lists during export
verify-big:
	cd backend && .venv/bin/python -m pytest -q -m big -s

## Append 100,000 generated East certificates to the running app's DB (quick-start rows untouched)
big-data:
	cd backend && .venv/bin/python seed.py --big EAST --rows 100000
