#!/usr/bin/env sh
# One command: install declared dependencies, seed demo data, start backend (8000) + frontend (3000).
# Requires python3 >= 3.11 and node >= 20. Ctrl-C stops both.
set -eu
cd "$(dirname "$0")"

[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install -q -r backend/requirements.txt
( cd backend && .venv/bin/python seed.py )
( cd frontend && npm install --no-audit --no-fund --silent )

( cd backend && exec .venv/bin/uvicorn main:app --port 8000 ) &
BACK=$!
( cd frontend && exec npm run dev ) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' INT TERM EXIT

echo "backend  -> http://localhost:8000   (docs: /docs)"
echo "frontend -> http://localhost:3000"
wait
