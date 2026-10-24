#!/usr/bin/env bash
# Workstream B (PROTOCOL_ADDENDUM section 10): run the two Qwen3-Coder studies rep-major in resumable batches,
# NSLOTS adapter processes in parallel (one per llama-server slot), secret scan after every batch.
# Requires a running llama-server on 127.0.0.1:8090 (scripts/openagent_server.sh). Safe to re-run: finished
# sessions (record.json present) are skipped by the adapter.
# usage: bash openagent_batches.sh <date-suffix> [NSLOTS=2] [REPS="1 2 3"] [BATCH=12] ["cfg:study ..."]
set -u
SUFFIX="${1:?date suffix, e.g. 2026-10-22}"
NSLOTS="${2:-2}"
REPS="${3:-1 2 3}"
BATCH="${4:-12}"
I1="research/dependency-block-study"
BENCH="$HOME/projects/since-cutoff-benchmark"
PY=sc_openagent/venv/Scripts/python.exe
LOG="since_cutoff_runs/openagent-qwen3c-$SUFFIX.batches.log"
RESULTS=since_cutoff_runs/results
STUDIES=("main:openagent-qwen3c-main-$SUFFIX" "tasks2:openagent-qwen3c-tasks2-$SUFFIX")
# section 10a: optional 5th argument = space-separated "<config suffix>:<study id>" list (e.g. "main-h:openagent-qwen3c-h-2026-10-23")
if [ -n "${5:-}" ]; then read -r -a STUDIES <<< "$5"; LOG="since_cutoff_runs/${STUDIES[0]#*:}.batches.log"; fi

pending() {  # $1 config $2 study $3 rep -> number of pending sessions
  "$PY" - "$RESULTS/$2" "$3" <<'EOF'
import json, sys
from pathlib import Path
d, rep = Path(sys.argv[1]), int(sys.argv[2])
plan = [json.loads(l) for l in (d / "plan.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
done = set()
for p in (d / "runs").glob("*/record.json"):
    r = json.loads(p.read_text(encoding="utf-8"))
    if r.get("valid") or int(r.get("attempt", 1)) >= 3:
        done.add(p.parent.name)
print(sum(1 for e in plan if int(e["rep"]) == rep and e["run_id"] not in done))
EOF
}

echo "$(date -Is) start suffix=$SUFFIX slots=$NSLOTS reps=$REPS batch=$BATCH" >> "$LOG"
for rep in $REPS; do
  for entry in "${STUDIES[@]}"; do
    cfgname="${entry%%:*}"; study="${entry#*:}"
    cfg="$I1/configs/bench.openagent-qwen3c-$cfgname.toml"
    while true; do
      n=$(pending "$cfg" "$study" "$rep")
      [ "$n" -gt 0 ] || break
      if ! curl -s -m 5 http://127.0.0.1:8090/health | grep -q ok; then
        echo "$(date -Is) llama-server not healthy; stopping" >> "$LOG"; exit 3
      fi
      echo "$(date -Is) $study rep $rep: $n pending; batch of up to $BATCH" >> "$LOG"
      per=$(( (BATCH + NSLOTS - 1) / NSLOTS ))
      a1=$(ls -d "$RESULTS/$study"/runs/*/ "$RESULTS/$study"/runs_invalid/*/ 2>/dev/null | wc -l)
      pids=()
      for ((i = 0; i < NSLOTS; i++)); do
        "$PY" "$I1/scripts/openagent_run.py" --config "$cfg" --study-id "$study" \
          --api-base http://127.0.0.1:8090/v1 --model-name openai/qwen3-coder \
          --reps "$rep" --shard "$i/$NSLOTS" --max-sessions "$per" --wall-limit 1800 >> "$LOG" 2>&1 &
        pids+=($!)
      done
      for p in "${pids[@]}"; do wait "$p"; done
      (cd "$BENCH" && .venv/Scripts/python.exe -m bench.secretscan "$RESULTS/$study") >> "$LOG" 2>&1
      rc=$?
      echo "$(date -Is) secretscan rc=$rc ($study)" >> "$LOG"
      if [ "$rc" -ne 0 ]; then echo "$(date -Is) secret scan found something: STOP (redact before resuming)" >> "$LOG"; exit 4; fi
      a2=$(ls -d "$RESULTS/$study"/runs/*/ "$RESULTS/$study"/runs_invalid/*/ 2>/dev/null | wc -l)
      if [ "$a2" -le "${a1:-0}" ]; then echo "$(date -Is) no session recorded in this batch: STOP" >> "$LOG"; exit 5; fi
    done
  done
done
echo "$(date -Is) all requested reps done" >> "$LOG"
