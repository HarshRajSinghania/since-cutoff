#!/usr/bin/env bash
# AexPy retry for mistralai: it is a namespace package (no mistralai/__init__.py), so preprocess finds no top-level
# module (topModules = [], 0 entries extracted). Re-run preprocess with the top-level module given explicitly
# (-m mistralai.client, the module the benchmark repos import), then extract / diff / report as for the other pairs.
set -u
W=recall_eval; OUT=$W/out/aexpy; export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
mv -f $OUT/mistralai.diff.json $OUT/mistralai.diff.EMPTY-first-attempt.json 2>/dev/null
for v in 2.5.0 3.3.0; do
  E=$W/ax/venv-mistralai-$v; w=$(ls $W/ax/whl-mistralai-$v/*.whl)
  $E/Scripts/python -m aexpy preprocess -w "$w" -m mistralai.client $OUT/mistralai-$v.m.dist.json > $OUT/mistralai-$v.m.pre.log 2>&1 || echo "preprocess fail $v"
  ( timeout 3600 $E/Scripts/python -m aexpy extract -j $OUT/mistralai-$v.m.dist.json $OUT/mistralai-$v.m.api.json > $OUT/mistralai-$v.m.ext.log 2>&1 ) || echo "extract fail $v"
  echo "done $v"
done
$W/ax/venv-mistralai-3.3.0/Scripts/python -m aexpy diff $OUT/mistralai-2.5.0.m.api.json $OUT/mistralai-3.3.0.m.api.json $OUT/mistralai.diff.json > $OUT/mistralai.diff.log 2>&1 || echo "diff fail"
echo "pair mistralai finished"
