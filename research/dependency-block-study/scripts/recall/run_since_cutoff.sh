#!/usr/bin/env bash
# Runs since-cutoff (0.4.1 = venv041, C2 = venvc2) on one-file projects, one per library.
# scan --json (detector, uncapped) and sync --dry-run --scope imported --per-package 5 / 10 (notes).
# Usage: run_since_cutoff.sh <tag: 041|c2|c2m0> [library]  (c2m0 = C2 with --cutoff-margin 0: the same version pair as 0.4.1)
set -u
# mistralai is a namespace package: the project imports mistralai.client (as the benchmark repos do), since a bare
# `import mistralai` matches none of its import names and gives an empty block.
TAG=$1; W=recall_eval
EXTRA=""
case $TAG in 041) PY=$W/venv041/Scripts/python.exe;; c2) PY=$W/venvc2/Scripts/python.exe;; c2m0) PY=$W/venvc2/Scripts/python.exe; EXTRA="--cutoff-margin 0";; esac
export SINCE_CUTOFF_CACHE=$W/cache_${TAG%m0} PYTHONIOENCODING=utf-8 NO_COLOR=1
OUT=$W/out/sc$TAG; mkdir -p $OUT
while read lib ver mod; do
  if [ -n "${2:-}" ] && [ "$lib" != "$2" ]; then continue; fi
  P=$W/proj/$TAG/$lib; rm -rf $P; mkdir -p $P
  printf '[project]\nname = "recall-%s"\nversion = "0.0.0"\nrequires-python = ">=3.13"\ndependencies = ["%s==%s"]\n' "$lib" "$lib" "$ver" > $P/pyproject.toml
  printf 'import %s\n' "$mod" > $P/main.py
  ( cd $P && $PY -m since_cutoff scan . --cutoff 2026-06-30 $EXTRA --json > $OUT/$lib.scan.json 2> $OUT/$lib.scan.err; echo "scan $lib exit $?" )
  for n in 5 10; do
    ( cd $P && $PY -m since_cutoff sync . --cutoff 2026-06-30 $EXTRA --scope imported --per-package $n --target CLAUDE.md --dry-run > $OUT/$lib.sync$n.txt 2> $OUT/$lib.sync$n.err; echo "sync$n $lib exit $?" )
  done
done <<'LIBS'
anthropic 1.8.0 anthropic
openai 3.19.2 openai
huggingface-hub 2.0.0 huggingface_hub
mcp 2.2.0 mcp
polars 2.0.0 polars
streamlit 1.66.1 streamlit
mistralai 3.3.0 mistralai.client
LIBS
