#!/usr/bin/env bash
# AexPy 0.4.3 on the seven pairs. One venv per release with aexpy + that release installed (AexPy's extractor
# imports the package in the current environment), then preprocess -w / extract / diff / report.
set -u
W=recall_eval; PY="AppData/Local/Programs/Python/Python313/python.exe"
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
OUT=$W/out/aexpy; mkdir -p $OUT $W/ax
ext() { # dist version
  local d=$1 v=$2; local whl=$(ls /c/b/wheelhouse/${d//-/_}-$v-*.whl 2>/dev/null | head -1)
  [ -z "$whl" ] && whl=$(ls /c/b/wheelhouse/$d-$v-*.whl | head -1)
  local E=$W/ax/venv-$d-$v
  [ -x $E/Scripts/python.exe ] || "$PY" -m venv $E
  $E/Scripts/python -m pip install -q aexpy==0.4.3 "$whl" --find-links /c/b/wheelhouse > $OUT/$d-$v.pip.log 2>&1 || echo "pip fail $d $v"
  mkdir -p $W/ax/whl-$d-$v && cp "$whl" $W/ax/whl-$d-$v/
  local w=$W/ax/whl-$d-$v/$(basename "$whl")
  $E/Scripts/python -m aexpy preprocess -w "$w" $OUT/$d-$v.dist.json > $OUT/$d-$v.pre.log 2>&1 || echo "preprocess fail $d $v"
  ( timeout 3600 $E/Scripts/python -m aexpy extract -j $OUT/$d-$v.dist.json $OUT/$d-$v.api.json > $OUT/$d-$v.ext.log 2>&1 ) || echo "extract fail $d $v"
  echo "done $d $v $(ls -la $OUT/$d-$v.api.json 2>/dev/null | awk '{print $5}')"
}
while read lib d o n; do
  ext $d $o; ext $d $n
  if [ -s $OUT/$d-$o.api.json ] && [ -s $OUT/$d-$n.api.json ]; then
    $W/ax/venv-$d-$n/Scripts/python -m aexpy diff $OUT/$d-$o.api.json $OUT/$d-$n.api.json $OUT/$lib.diff.json > $OUT/$lib.diff.log 2>&1 || echo "diff fail $lib"
    $W/ax/venv-$d-$n/Scripts/python -m aexpy report $OUT/$lib.diff.json $OUT/$lib.report.json > $OUT/$lib.report.log 2>&1 || echo "report fail $lib"
  fi
  echo "pair $lib finished"
done <<'LIBS'
anthropic anthropic 0.115.0 1.8.0
openai openai 2.44.0 3.19.2
huggingface-hub huggingface_hub 1.21.0 2.0.0
mcp mcp 1.28.1 2.2.0
polars polars 1.42.1 2.0.0
streamlit streamlit 1.58.0 1.66.1
mistralai mistralai 2.5.0 3.3.0
LIBS
