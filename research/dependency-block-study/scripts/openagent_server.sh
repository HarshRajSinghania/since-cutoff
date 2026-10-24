#!/usr/bin/env bash
# Workstream B (PROTOCOL_ADDENDUM section 10): llama-server b11821 (CUDA 12.4) with Qwen3-Coder-30B-A3B-Instruct Q4_K_M.
# usage: bash openagent_server.sh [N_CPU_MOE=24] [CTX_PER_SLOT=40960] [NSLOTS=2]
# Sampling = the model card's recommendation (temp 0.7, top_p 0.8, top_k 20, repetition penalty 1.05);
# the adapter also sends temperature 0.7. Runs in the foreground; log to sc_openagent\logs.
NCMOE="${1:-24}"; CTX="${2:-40960}"; NP="${3:-2}"
D=sc_openagent
exec "$D/bin/llama-cuda/llama-server.exe" \
  -m "$D/downloads/qwen30b/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf" \
  --host 127.0.0.1 --port 8090 --alias qwen3-coder --jinja \
  -c $((CTX * NP)) -np "$NP" -ngl 99 --n-cpu-moe "$NCMOE" -fa on -ctk q8_0 -ctv q8_0 \
  --temp 0.7 --top-p 0.8 --top-k 20 --repeat-penalty 1.05 --metrics --no-webui
