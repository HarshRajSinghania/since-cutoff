#!/usr/bin/env bash
# Run a study in batches of <= 60 sessions (PROTOCOL_ADDENDUM section 4). After each batch: validity summary and the
# harness secret scan. Stops when the plan is complete, when a batch makes no progress, or when the harness reports
# auth/usage_limit (it stops itself; the summary shows it).
# usage: run_batches.sh <config.toml> <study_id> [workers]
set -u
CFG="$1"; STUDY="$2"; WORKERS="${3:-3}"
# Environment: PY (python with the harness installed), RUNS_DIR (folder for results), BENCH_DIR (benchmark repo).
PY="${PY:-python}"
RES="${RUNS_DIR:?set RUNS_DIR}/results/$STUDY"
LOG="$RUNS_DIR/$STUDY.batches.log"
W="$(cd "$(dirname "$0")/.." && pwd)"
cd "${BENCH_DIR:?set BENCH_DIR}" || exit 1
planned=$(wc -l < "$RES/plan.jsonl")
for b in $(seq 1 12); do
  before=$("$PY" "$W/scripts/validity.py" "$RES" --count-valid)
  if [ "$before" -ge "$planned" ]; then echo "BATCHES DONE $STUDY valid=$before/$planned" | tee -a "$LOG"; break; fi
  echo "BATCH START $STUDY #$b valid=$before/$planned $(date -u +%FT%TZ)" | tee -a "$LOG"
  "$PY" -m bench --config "$CFG" run "$STUDY" --workers "$WORKERS" --resume --max-sessions 60 >> "$LOG" 2>&1
  rc=$?
  after=$("$PY" "$W/scripts/validity.py" "$RES" --count-valid)
  summary=$("$PY" "$W/scripts/validity.py" "$RES")
  scan=$("$PY" -m bench.secretscan "$RES" 2>&1 | tail -1)
  echo "BATCH END $STUDY #$b rc=$rc valid=$after/$planned | $summary | secretscan: $scan" | tee -a "$LOG"
  if echo "$summary" | grep -qE "usage_limit|auth"; then echo "STOPPED usage_limit/auth $STUDY" | tee -a "$LOG"; exit 2; fi
  if [ "$after" -le "$before" ]; then echo "STOPPED no progress $STUDY rc=$rc" | tee -a "$LOG"; exit 3; fi
done
