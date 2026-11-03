#!/usr/bin/env sh
# Copies the native Claude Code transcript(s) for this project into ai/sessions/.
# Re-run after the final AI session has ended so the export includes its last turns.
set -eu
cd "$(dirname "$0")"
SRC="$HOME/.claude/projects/-Users-jyt-Desktop"
mkdir -p sessions
for id in 2ed64df3-23e8-40d9-a214-02d5e8aafa6b; do
  cp "$SRC/$id.jsonl" "sessions/$id.jsonl"
  echo "copied $id.jsonl ($(wc -c < "sessions/$id.jsonl") bytes)"
done
