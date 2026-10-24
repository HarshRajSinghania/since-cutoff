#!/usr/bin/env bash
# PROTOCOL_ADDENDUM section 14 driver: S1 rep1, S2 rep1, S1 rep2, S2 rep2, S1 rep3 (each one batch <= 60 sessions),
# validity summary + harness secret scan after every batch; stops on usage_limit/auth or no progress.
# usage: lockhdr_driver.sh [workers] [first_step]
set -u
WORKERS="${1:-3}"; FIRST="${2:-1}"
PY="$HOME/projects/since-cutoff-benchmark/.venv/Scripts/python.exe"
RUNS=since_cutoff_runs
W="research/dependency-block-study"
LOG="$RUNS/lockhdr-2026-10-23.batches.log"
cd "$HOME/projects/since-cutoff-benchmark" || exit 1
S1=lockhdr-tasks2-opus55-2026-10-23; C1=addendum/bench.lockhdr-tasks2-opus55.toml
S2=lockhdr-orig-opus55-2026-10-23;   C2=addendum/bench.lockhdr-orig-opus55.toml
login_ok() {  # the CLI login must hold a usable token (prints nothing secret)
  "$PY" -c "import json,os,sys,time; d=json.load(open(os.path.expanduser('~/.claude/.credentials.json'))).get('claudeAiOauth') or {}; ok=bool(d.get('accessToken')) and (d.get('expiresAt',0)/1000>time.time()+600 or (bool(d.get('refreshToken')) and d.get('refreshTokenExpiresAt',0)/1000>time.time()+3600)); sys.exit(0 if ok else 1)"
}
zero_valid() {  # valid records with zero tokens = a login/API failure the classifier missed
  "$PY" -c "import json,sys; n=sum(1 for l in open(sys.argv[1]+'/runs.jsonl') for r in [json.loads(l)] if r.get('valid') and not sum(((r.get('result') or {}).get('usage') or {}).get(k,0) for k in ('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens'))); print(n)" "$1"
}
step() {  # step <n> <cfg> <study> <target_valid>
  local n="$1" cfg="$2" st="$3" target="$4" res="$RUNS/results/$3" tries=0
  while :; do
    local before; before=$("$PY" "$W/scripts/validity.py" "$res" --count-valid)
    if [ "$before" -ge "$target" ]; then echo "STEP $n DONE $st valid=$before/$target" | tee -a "$LOG"; return 0; fi
    if ! login_ok; then echo "STOPPED login expired or not usable (user must run: claude auth login) $(date -u +%FT%TZ)" | tee -a "$LOG"; exit 4; fi
    tries=$((tries+1)); if [ "$tries" -gt 3 ]; then echo "STEP $n GAVE UP $st valid=$before/$target" | tee -a "$LOG"; return 3; fi
    local need=$((target-before))
    echo "BATCH START step $n $st need=$need valid=$before/$target $(date -u +%FT%TZ)" | tee -a "$LOG"
    "$PY" -m bench --config "$cfg" run "$st" --workers "$WORKERS" --resume --max-sessions "$need" >> "$LOG" 2>&1
    local rc=$?
    local after; after=$("$PY" "$W/scripts/validity.py" "$res" --count-valid)
    local summary; summary=$("$PY" "$W/scripts/validity.py" "$res")
    local scan; scan=$("$PY" -m bench.secretscan "$res" 2>&1 | tail -1)
    echo "BATCH END step $n $st rc=$rc valid=$after/$target $(date -u +%FT%TZ) | $summary | secretscan: $scan" | tee -a "$LOG"
    if echo "$summary" | grep -qE "usage_limit|auth"; then echo "STOPPED usage_limit/auth $st" | tee -a "$LOG"; exit 2; fi
    local z; z=$(zero_valid "$res"); if [ "$z" -gt 0 ]; then echo "STOPPED $z valid record(s) with zero tokens in $st (check auth/API)" | tee -a "$LOG"; exit 5; fi
    if [ "$after" -le "$before" ]; then echo "STOPPED no progress $st rc=$rc" | tee -a "$LOG"; exit 3; fi
  done
}
[ "$FIRST" -le 1 ] && { step 1 "$C1" "$S1" 44  || exit $?; }
[ "$FIRST" -le 2 ] && { step 2 "$C2" "$S2" 51  || exit $?; }
[ "$FIRST" -le 3 ] && { step 3 "$C1" "$S1" 88  || exit $?; }
[ "$FIRST" -le 4 ] && { step 4 "$C2" "$S2" 102 || exit $?; }
[ "$FIRST" -le 5 ] && { step 5 "$C1" "$S1" 132 || exit $?; }
echo "ALL STEPS DONE $(date -u +%FT%TZ)" | tee -a "$LOG"
