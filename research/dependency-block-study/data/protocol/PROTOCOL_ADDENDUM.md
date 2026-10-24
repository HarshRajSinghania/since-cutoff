# Protocol addendum (NAACL 2027 Industry Track): additional studies

Written 2026-10-21, **before any session of the studies below was started**. It extends the frozen protocol
`bench/PROTOCOL.md` at tag `main-freeze-2026-09-28` (public repo `since-cutoff-benchmark`, main = b64d378). Everything
not stated here is unchanged from that protocol (agent command, tools, settings, validity rules, grading, process
metrics, bootstrap seed 20261001 with 10,000 resamples, task set, stale patterns). Results already published for
`main-2026-09-28` are not re-analysed under new rules; the only new analyses on the old data are labelled
*exploratory* in section 6.

Harness: local branch `naacl-addendum` of the benchmark repository, commit 8ebb05f (adds condition H only;
`bench/config.py`, `bench/conditions.py`); harness code sha256 recorded in every run record and in `plan.meta.json`.
Configs: `configs/bench.sonnet-5-5.toml`, `configs/bench.haiku-5-5.toml` (diff against `bench/bench.toml` = the
lines listed in section 2). Results: `since_cutoff_runs\results\<study>`; agent projects
`C:\b\runs\<study>`.

(Note in this copy: sections appear in the order they were written. The GPU pilot record of the open-model study, section 10.1, is filed at the end of section 11.4, amendment 10a sits between sections 12 and 13, and in section 14 the W design (14.2) precedes the amendment 14.1. Section 14 was registered but not run, because the Claude CLI login had expired. A later section 15 registered a second open-weight study, which was started and stopped before completion; its partial runs are not analysed, and the section is not included in this copy.)

## 1. Questions

- **Q1 (model generalisation).** Do the main-run findings (same pass rate, lower cost/turns/tokens, fewer stale
  first edits with since-cutoff notes) hold for two other Claude models with the same training cutoff,
  `claude-sonnet-5-5` and `claude-haiku-5-5` (models.dev cutoff 2026-06 for all three, so the task strata, the
  cutoff-era versions and the notes are unchanged)?
- **Q2 (why notes help: placebo).** The main run's efficiency gain also appeared on post-cutoff tasks whose change
  the notes did *not* cover (exploratory, section 6). Is the gain caused by the specific change lines, or by a
  generic signal ("this project's libraries changed since your cutoff", versions named)? Condition **H** keeps the
  notes block's header, intro and per-package version lines and removes every change line.
- **Q3 (deployment context, no model calls).** How often do real public Python projects pin dependency versions
  released after a current model's cutoff, and how many API changes reach code they import / use? (static scans)
- **Q4 (static exposure vs. observed staleness).** Across libraries, does the static count of post-cutoff breaking
  changes rank libraries the way probed model behaviour does? (existing data only, if present)

## 2. Studies and their fixed settings

| study id | model | conditions | tasks | reps | sessions | seed |
|---|---|---|---|---|---|---|
| `gen-sonnet55-2026-10-21` | claude-sonnet-5-5 | A, C, H | all 24 | 3 | 216 | 20261021 |
| `gen-haiku55-2026-10-21` | claude-haiku-5-5 | A, C | all 24 | 3 | 144 | 20261022 |

Changes from the main run, all decided before any session:

1. `--model` as above; `--effort medium` kept (main run value; the `--effort low` default of the tool is not used,
   so the comparison with Opus 5.5 holds the agent setup fixed).
2. Notes: generated with the released `since-cutoff==0.4.1` (`sync --yes --scope imported --model
   anthropic:<model>`), frozen. Verified before freezing: for all 24 tasks the blocks are byte-identical to the
   frozen Opus 5.5 notes once the model name is replaced (only the model name in the header and meta line differ;
   same cutoff 2026-06-30). Manifests: Sonnet `29bccc64…`, Haiku `40ed2b9b…`.
3. Condition H (Sonnet study only): `make_header_notes.py` applied to the frozen Sonnet notes (every line starting
   with `- ` removed; mean 246 estimated tokens for the 20 non-empty blocks); manifest `38f4015f…`. For the 4 tasks
   with empty notes (oai05, pd01–pd03) A, C and H have identical CLAUDE.md.
4. `--max-budget-usd 7.5` instead of 3: Claude Code 2.1.283 does not know these two models
   (`[claude-code:unrecognized_model]`, `costBasis: unknown`) and prices them at a fallback rate that is 2.5x Opus
   5.5 list price (measured: 48,077 1-hour cache-write tokens priced $0.9618 = $20/MTok vs $8 for Opus 5.5).
   7.5 = 3 x 2.5 keeps the main run's token cap. The CLI version is not changed (pinned 2.1.283).
   The same CLI reports a 200k context window for these models (1M for Opus 5.5); auto-compaction events, if any,
   are counted and reported.
5. Cost: the harness's `cost_usd` (CLI fallback pricing) is kept for the C/A ratio as the pre-registered metric
   (a fixed price per token type, so the ratio is a weighted token ratio). In addition `list_cost_usd` is recomputed
   from each run's token usage at list prices (`analysis/recompute_cost.py`): Sonnet 5.5 $2 in / $10 out / $0.20
   cache read / $4 1-hour cache write; Haiku 5.5 $0.10 / $0.50 / $0.01 (assumed 0.1x input) / $0.20 (assumed 2x
   input), prompts under 100k tokens. The Haiku cache prices are assumptions and are reported as such.
6. Analysis contrasts (Holm family per study): Sonnet C−A, H−A, C−H; Haiku C−A.

Context7 re-run (B/D/E with a key): **not run**. `CONTEXT7_API_KEY` is not set in this environment (checked
2026-10-21) and keys are not requested or typed. The quota caveat of PROTOCOL 12.t stands and is reported.

## 3. Hypotheses and decision rules (per study; post-cutoff stratum = 17 tasks unless stated)

| id | claim | evidence required |
|---|---|---|
| G1 | notes lower cost/effort on this model | C/A ratio CI (task bootstrap, geometric mean of per-task medians) entirely below 1 for **total tokens** (primary for these studies, because CLI cost is fallback-priced); turns, wall time, CLI cost and list cost reported as secondary |
| G2 | notes raise pass rate | only if A < 90% on post-cutoff tasks (ceiling rule): Δ(C−A) CI lower > 0 and Holm p < .05 (exact sign-flip) |
| G3 | notes don't hurt | one-sided 95% lower bound of Δ(C−A) on the 7 controls ≥ −10 pp |
| G4 | fewer stale first edits | stale_in_first_edit rate lower in C than A, tested by exact sign-flip over per-task differences in stale rate (two-sided, tasks with an edit in both arms) |
| P1 | change lines matter beyond the header (Sonnet) | C/H total-token ratio CI entirely below 1, **or** stale first edit lower in C than H with sign-flip p < .05 |
| P2 | header alone gives the gain (Sonnet) | H/A total-token ratio CI entirely below 1 and C/H CI includes 1 |
| X1 | generalisation across models | G1 met in at least 2 of the 3 models (Opus 5.5 main run, Sonnet 5.5, Haiku 5.5) |
| X2 | pooled stale first edit | across the three models, per-task difference (A rate − C rate) averaged over models; exact sign-flip over the 17 post-cutoff tasks, two-sided; reported with and without the pilot-exposed ant01 and mcp01 |

Pilot exposure: every claim is reported with all tasks and with `--exclude-tasks ant01,mcp01`; a claim counts as
supported only if it holds in both (as in PROTOCOL 12.z). Anything that meets no rule is reported as inconclusive.
No pass-rate claim is made when the ceiling rule fires.

## 4. Validity, exclusion, stopping

- Validity and re-queue rules exactly as PROTOCOL section 6 (invalid runs re-queued, up to 3 attempts; `auth` and
  `usage_limit` stop the study, resumed with `run --resume`). `model_mismatch` checks the init event against the
  study model.
- Batches of at most 60 sessions (`--max-sessions 60`), 3 workers (2 if a usage-limit warning appears). After each
  batch: count invalid reasons, timeouts, budget stops (`error_max_budget_usd`), compactions, network-like commands,
  and run `python -m bench.secretscan` on the study folder.
- If the author's Claude usage limit is hit, the study stops and is resumed later; no session is discarded for that
  reason other than the invalid attempt itself.
- Order of execution: Sonnet study first, then Haiku. If time runs out, the Haiku study is reported as incomplete
  (blocks completed so far, every block has all its conditions back to back), not dropped silently.

## 5. Static studies (no model calls)

- **Q3 real-world scan.** Population: public GitHub repositories, primary language Python, ≥ 200 stars, pushed
  after 2026-09-01, with a `uv.lock` or `poetry.lock` at the root and a `pyproject.toml`, from the GitHub search API
  sorted by stars (query and date stored with the results); the first 50 that `since-cutoff` 0.5.0 can parse.
  Shallow clone (no code from the repositories is executed); `since-cutoff scan --json --model
  anthropic:claude-opus-5-5` (cutoff 2026-06, default 30-day margin) and the same with `--cutoff 2025-07-31`
  (Sonnet 4.5's cutoff, an older but still widely used model). Metrics per repo: direct dependencies, share whose
  locked version was released after the cutoff (margin applied), packages with ≥ 1 breaking public-API change, total
  breaking changes, changes in APIs the code uses (file:line matches). Reported as medians/IQR and share of repos
  with ≥ 1 used changed API. Repositories are identified only by count and aggregate in the paper (names kept in the
  raw file).
- **Q4 static vs probe.** Uses `~/projects/since-cutoff-bench` (36-library ai-stack scans for 21 models; probe runs
  for claude-haiku-4-5, claude-opus-4-6 and any complete others). Spearman correlation, per model, between a
  library's static breaking-change count (and log count) and its probed stale rate; exploratory, reported with n.

## 6. Exploratory analyses on the main-run data (labelled as such)

- Stale first edit, A vs C: run-level counts with Fisher exact test (ignores clustering) and task-level exact
  sign-flip (respects clustering).
- Efficiency by notes coverage: C/A ratios separately for the 5 covered post-cutoff tasks, the 12 uncovered ones and
  the 7 controls (computed before this addendum was written; it motivated condition H).

## 7. Addendum 2 (written 2026-10-22 ~00:15 UTC, after the Sonnet and Haiku studies, before any session below)

Motivation (stated honestly): in the Sonnet study the header-only placebo H matched C on pass rate; whether the main
run's Opus 5.5 efficiency gain comes from the change lines or from the header is the open "why" question.

| study id | model | conditions | tasks | reps | sessions | seed |
|---|---|---|---|---|---|---|
| `abl-opus55-2026-10-22` | claude-opus-5-5 | A, C, H | 17 post-cutoff tasks | 3 | 153 | 20261023 |

Settings exactly as the main run (`--effort medium`, `--max-budget-usd 3`, CLI 2.1.283, which knows this model), C =
the frozen main-run notes (`bench/notes`, manifest f7e0b283…), H = `make_header_notes.py` applied to them (manifest
3688d53d…, mean 245 est. tokens). Config `configs/bench.opus-5-5-abl.toml`. It is also a temporal replication of the
main run's C vs A (same model, 3.5 weeks later).

Rules (Holm family C−A, H−A, C−H on pass rate; ratios as in section 3):
- R1 replication: C/A total-token and cost ratio CIs entirely below 1 (as in the main run).
- P1/P2 as in section 3 (C/H CI below 1 = the change lines add efficiency beyond the header; H/A below 1 with C/H
  including 1 = the header alone gives the gain).
- Pilot-exposure sensitivity (without ant01, mcp01) as before. Batches of ≤ 60 sessions, 3 workers.

## 8. Addendum 3: task-set expansion (written 2026-10-22 ~18:45 local / 17:45 UTC, before any session below)

Motivation (stated honestly): internal reviews of the draft named "17 post-cutoff tasks in 4 libraries, all from one
author" as the main external-validity risk. This study adds tasks in three libraries that are not in the main set
(polars, streamlit, mistralai), written after the main results were known, and repeats the Opus 5.5 A/C/H design on
them. Hidden tests stay private (`since_cutoff_tasks2`, outside the public repository); task hashes
are fixed below so the tasks cannot change after the results are seen.

| study id | model | conditions | tasks | reps | sessions | seed |
|---|---|---|---|---|---|---|
| `tasks2-opus55-2026-10-22` | claude-opus-5-5 | A, C, H | 11 new tasks (8 post-cutoff, 3 pre-cutoff controls) | 3 | 99 | 20261024 |

**Tasks** (cutoff convention as in the main run: `cutoff_version` = newest release on or before 2026-06-30, margin 0;
pinned = newest release on 2026-10-22). Every task passed the four validation gates and the leak check with
`bench validate` (logs `I1/expansion/validate_tasks2_final.log`) and an independent review (separate agent, 55
alternative/wrong solutions run against the hidden tests; findings and fixes in `I1/expansion/REVIEW_tasks2.md` (copy: `addendum/REVIEW_tasks2.md`)).

| key | library (cutoff -> pinned) | kind | change |
|---|---|---|---|
| pl01 | polars 1.42.1 -> 2.0.0 | post-cutoff, silent | `DataFrame.explode` default `empty_as_null` True -> False (rows silently dropped) |
| pl02 | polars | post-cutoff, loud | `read_csv_batched` removed |
| pl03 | polars | post-cutoff, loud | `Expr.replace(default=)` removed (`replace_strict`) |
| pl04 | polars | post-cutoff, loud | `collect(streaming=True)` removed (`engine="streaming"`) |
| st01 | streamlit 1.58.0 -> 1.66.1 | post-cutoff, loud | `st.cache` removed |
| st02 | streamlit | post-cutoff, silent | `st.image(use_column_width=)` accepted but ignored |
| mi01 | mistralai 2.5.0 -> 3.3.0 | post-cutoff, loud | HTTP layer moved from httpx to httpx2 (httpx no longer installed) |
| mi02 | mistralai | post-cutoff, silent | `ocr.process(include_blocks=)` default False -> True |
| pl90 | polars (stale 0.20.31) | pre-cutoff control | `cumsum` removed in 1.0.0 (2024) |
| pl91 | polars (stale 0.20.31) | pre-cutoff control | `DataFrame.groupby` removed in 1.0.0 (2024) |
| st90 | streamlit (stale 1.53.1) | pre-cutoff control | `experimental_get/set_query_params` removed in 1.54.0 (2026-02) |

Considered and not used (premise rules as for the dropped ant06/mcp03/hf05): fastapi 0.138.2 -> 0.159.1 (behaviour
fixes where the cutoff-era idiom still passes), mistralai `fine_tuning` (removed in 3.x without a replacement),
mistralai built-in `web_search` tool in `chat.complete` (removed; replacement endpoint not verifiable offline).
Note: several changes were announced by deprecation warnings before the cutoff (pl01-pl04, st01); this is reported
as a threat to validity, as for the main set.

**Notes** (decided before any session): unchanged tool and settings, so the study is comparable with the main run -
released `since-cutoff==0.4.1`, `sync --yes --scope imported --model anthropic:claude-opus-5-5`, frozen (manifest
`6a6f666687ae58be9f18c1c45aa377b03a3a72ea5aa26dda7cf8d0171338f034`, 11 non-empty blocks, mean ~407 est. tokens).
0.4.1 shows at most five change lines per package (ranked); with these large diffs the notes cover the task's
change in **2 of 8** post-cutoff tasks (pl02, st01; harness `note_keys`). This is recorded now and the covered /
uncovered split is reported descriptively (as in section 6). H = `make_header_notes.py` on the frozen notes
(manifest `7810f8190381705b0fa225d6d6c38ca34becf6cee850bea538ad6dc4c1b18b52`, mean 237.5 est. tokens). Controls
get notes too (they import the same libraries), so A, C and H differ on every task.

**Settings** exactly as the Opus 5.5 main run and section 7 (CLI 2.1.283, `--effort medium`, `--max-budget-usd 3`,
40 turns, 900 s, same tools/permissions/env scrub, grading with pytest-socket and a dead proxy). Config
`addendum/bench.tasks2-opus55.toml` (config sha256 `2434141f…`; adds `[paths] tasks/notes/notes_header` - the
harness change is the 2-line `[paths] tasks` option in `bench/config.py`). Harness sha256 `970a81f3…`; full hashes of
every task (task.toml, repo, hidden, reference, stale) and env lock in `addendum/HASHES.tasks2.json` (generated
2026-10-22T17:30Z). Hidden-test sha256: see that file (`hidden_sha256` per task).

**Hypotheses and rules** (post-cutoff stratum = 8 tasks; task = unit; bootstrap and sign-flip as in section 3;
Holm family C−A, H−A, C−H on pass rate):
- **E1 pass rate** (primary): Δ(C−A) on the 8 post-cutoff tasks, CI lower > 0 and Holm p < .05 - only if A < 90%
  (ceiling rule; if A ≥ 90%, no pass-rate claim).
- **E2 efficiency**: C/A total-token ratio CI entirely below 1 (primary efficiency metric, as in section 7); cost,
  turns, wall time secondary.
- **E3 non-inferiority on controls**: Δ(C−A) one-sided 95% lower bound ≥ −10 pp on the 3 controls (low power with 3
  tasks; reported, and pooled with the 7 main-run controls as a secondary check).
- **E4 stale first edit**: rate lower in C than A, exact sign-flip over per-task differences (two-sided); Fisher at
  run level reported alongside (ignores clustering).
- **P1/P2 placebo** as in section 3 (C vs H, H vs A) on tokens and stale first edits.
- **Pooled secondary analysis (old + new tasks, Opus 5.5)**: 25 post-cutoff task clusters = the 17 main-run tasks
  (study `main-2026-09-28`, conditions A and C) + these 8 (A and C). Pass-rate Δ(C−A) with task bootstrap and exact
  sign-flip, C/A total-token and cost ratios (geometric mean of per-task medians, task bootstrap), stale first edit
  sign-flip; repeated with the 17 old tasks taken from the section-7 replication (`abl-opus55-2026-10-22`, A/C/H)
  instead of the main run, and with A/C/H where H exists (replication + new). Labelled secondary; reported with and
  without the pilot-exposed ant01 and mcp01. Controls pooled likewise (7 + 3) for non-inferiority.
- **Coverage split** (descriptive): covered (pl02, st01) vs uncovered (6) post-cutoff tasks, C/A and H/A ratios.

Exclusion, validity and stopping as section 4 (batches ≤ 60 sessions, 3 workers, 2 after any usage-limit warning;
secret scan after every batch; usage limit pauses and resumes the study). No task is changed or dropped after the
first session; a task found broken after the study is reported as such, with results shown with and without it.
Threat recorded now: the new tasks, references and hidden tests were written by an agent running Claude Opus 5.5
(the same model as the agent under test), reviewed by a second Opus 5.5 agent; the author has not
yet re-checked them.

## 9. Workstream B (open-model agent): preparation record (written 2026-10-22 ~19:15 local, before any download)

Not a pre-registration of hypotheses (that will be section 10, written before any B session). This section fixes
what is downloaded, from where, with sizes and hashes, so the setup is reproducible. Everything goes under
`sc_openagent\` (own venv; the shared `venv` is not touched). The GPU is not used while
`gpu.lock` exists (T1, then T2 have priority).

| item | source (exact URL) | size (bytes) | sha256 | use |
|---|---|---|---|---|
| llama.cpp b11821 CPU build | https://github.com/ggml-org/llama.cpp/releases/download/b11821/llama-b11821-bin-win-cpu-x64.zip | 24,074,923 | efb0ac7f0b06b541905ecefc98feedfd77316b9c555fb6bf6776e6c168b078f7 | CPU pilot of the adapter |
| llama.cpp b11821 CUDA 12.4 build | https://github.com/ggml-org/llama.cpp/releases/download/b11821/llama-b11821-bin-win-cuda-12.4-x64.zip | 272,324,869 | 135edd84a11bc91c423d2ee10d2395fa09e45af66dbd80fc4fe83afd4d7fab97 | GPU run (driver 596.08 = CUDA 13.2, so the 12.4 build, not 13.4) |
| CUDA 12.4 runtime DLLs | https://github.com/ggml-org/llama.cpp/releases/download/b11821/cudart-llama-bin-win-cuda-12.4-x64.zip | 391,443,627 | 8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6 | GPU run |
| Qwen2.5-Coder-1.5B-Instruct Q4_K_M (Apache-2.0) | https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf | 1,117,320,768 | cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046 | CPU pilot only (adapter logic; not a study model) |
| Qwen3-Coder-30B-A3B-Instruct Q4_K_M (Apache-2.0; repo unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF @ b17cb02d) | https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/resolve/b17cb02dd882d5b6ab62fc777ad2995f19668350/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf | 18,556,689,568 | fadc3e5f8d42bf7e894a785b05082e47daee4df26680389817e2093056f088ad | study model (MoE, 3B active; 16 GB VRAM + `--n-cpu-moe` offload to 64 GB RAM) |
| mini-swe-agent 2.4.6 (PyPI) | https://pypi.org/project/mini-swe-agent/2.4.6/ (wheel mini_swe_agent-2.4.6-py3-none-any.whl) | 115,037 | a35463c553ac825c7773b03cfa69cd44958e3af20155dcc5711fdf9e4c67cd54 | agent scaffold (bash-only), LiteLLM to the local OpenAI-compatible llama-server |

Every file is checked against the sha256 above after download; a mismatch stops the workstream. Qwen3-Coder's
training cutoff is earlier than Opus 5.5's (released 2025-07), so the cutoff-era versions and notes for this model
differ (`since-cutoff --cutoff <date>`); this is decided in section 10.

9.1 Preparation done 2026-10-22 (no GPU used): all six files downloaded and sha256-verified (every hash matches the
table). Extracted to `sc_openagent\bin\llama-cpu` and `bin\llama-cuda` (CUDA build + cudart 12.4).
Venv `sc_openagent\venv` = mini-swe-agent 2.4.6 + `mcp` 2.3.0 (litellm 1.106.2 imports `mcp` whenever
tools are passed; without it every tool-calling query fails); full freeze in `sc_openagent\requirements.lock.txt`.
Adapter `I1/scripts/openagent_run.py`: reuses the harness (stdlib) for tasks, condition CLAUDE.md text (prepended to
the task prompt and written to the project), env locks, venvs (+ `_hf_isolation.pth`) and hidden-test grading;
mini-swe-agent DefaultAgent; every agent command runs in Git Bash with an environment built from scratch (no user
variables; HOME/USERPROFILE/APPDATA/TEMP per run; `PIP_NO_INDEX=1`; HTTP(S) proxies set to the dead proxy
127.0.0.1:9, so network calls from agent commands fail - checked: curl to pypi.org rc=7); first edit of a target
file is detected by snapshotting the target files after every command (stale_in_first_edit); tokens from the
server's usage fields. Limitation recorded: no filesystem sandbox (the Claude runs had Claude Code's permission
rules); the secret scan is run on every B transcript.
CPU pilot (study `openagent-pilot-cpu-2026-10-22`, config `I1/configs/bench.openagent-pilot.toml`, Qwen2.5-Coder-1.5B
Q4_K_M on llama-server b11821 CPU, `--textbased`, step limit 12; 2 sessions pl91-C, mi02-C): the pipeline runs end to
end (agent loop, bash, grading, records, orphan cleanup); both sessions valid (LimitsExceeded) and failed - the 1.5B
model produced format errors and once overwrote README.md with the prompt; expected for a 1.5B model, it is not a
study model. Pilot records are not analysed.

## 10. Addendum 4: open-model agent replication (written 2026-10-22 ~21:50 local / 20:50 UTC, before any GPU session)

Motivation (stated honestly): every agent study so far uses Claude models in Claude Code, and the draft's main
reviewer risk is "single vendor". This study repeats the A vs C comparison with an open-weight model from another
vendor in a different, minimal agent scaffold. It was decided after all Claude results were known; the design below is
fixed before any session of it (GPU pilot included).

**Agent and model.** Qwen3-Coder-30B-A3B-Instruct (Alibaba Qwen; Apache-2.0; MoE, 3.3B active), GGUF Q4_K_M
(file and sha256 in section 9), served by llama.cpp `llama-server` b11821 (CUDA 12.4 build) on the local RTX 4090
Laptop GPU (16 GB) with MoE expert layers partly offloaded to CPU RAM (`--n-cpu-moe`), flash attention, q8_0 KV cache,
chat template from the GGUF (`--jinja`), launcher `I1/scripts/openagent_server.sh`. Sampling = the model card's
recommendation: temperature 0.7, top_p 0.8, top_k 20, repetition penalty 1.05. Context per server slot ≥ 32k tokens
(target 40,960; final value and slot count fixed in the GPU pilot, 10.1, before any study session, from the
throughput measurement only). Scaffold: mini-swe-agent 2.4.6 `DefaultAgent` with its default config and native tool
calling (one `bash` tool), through LiteLLM to the local OpenAI-compatible endpoint; if the pilot shows that tool calls
are not parsed reliably, the text-based variant (`--textbased`) is used for the whole study (decided in the pilot,
recorded in 10.1). Adapter `I1/scripts/openagent_run.py` (section 9.1; additions since: `--reps`, `--shard`,
`--wall-limit`, re-attempt of infrastructure-invalid sessions, context overflow classified as a valid failure).
Limits: 40 model calls (= the Claude runs' 40 turns), 1800 s wall time per session (local inference is slower than the
Claude API; the Claude runs had 900 s), 180 s per command. No filesystem sandbox (section 9.1); same environment scrub,
dead proxy and offline pip as 9.1. The model gets the condition's CLAUDE.md text both as the project file and
prepended to the task prompt (identical bytes in A and C apart from the notes block).

**Training cutoff.** The model card states no knowledge cutoff (checked 2026-10-22 on huggingface.co
Qwen/Qwen3-Coder-30B-A3B-Instruct). since-cutoff 0.4.1's model registry (models.dev snapshot) lists
`alibaba:qwen3-coder-30b-a3b-instruct` with knowledge cutoff **2025-04** (end of month: 2025-04-30); the model was
released 2025-07-31, which bounds the cutoff from above. We use the registry value, i.e. exactly what a user of the
tool would get with `--model alibaba:qwen3-coder-30b-a3b-instruct`. Task classification below does not depend on the
exact date within 2025-04..2025-07: every treatment change happened on or after 2025-10-17, every control change in
2024-07.

**Notes.** Unchanged tool and settings (released `since-cutoff==0.4.1`, `sync --yes --scope imported`, five change
lines per package), generated for this model's cutoff with `--model alibaba:qwen3-coder-30b-a3b-instruct`
(cutoff-era versions therefore differ from the Opus 5.5 studies: e.g. polars 1.29.0, not 1.42.1), via
`bench notes --tool since-cutoff==0.4.1` with configs `I1/configs/bench.openagent-qwen3c-main.toml` (main task set)
and `bench.openagent-qwen3c-tasks2.toml` (addendum-3 task set), then frozen:
main set manifest `e5d9b991e60d4e3c00044de011e0bc1f982ddff763289ea44990cd964d0c462f` (24 non-empty blocks, mean ~431
est. tokens), addendum-3 set manifest `9f3ff3451ccdac0009efa78f2f627c278e82db714d4b471502afd94c29eea310` (11 blocks,
mean ~404). Cutoff-era versions chosen by the tool: anthropic 0.50.0, openai 1.76.2, huggingface-hub 0.30.2, mcp 1.6.0,
langchain-core 0.3.56, pandas 2.2.3, polars 1.29.0, streamlit 1.45.0, mistralai 1.7.0. Because these diffs are larger
than for Opus 5.5 and 0.4.1 keeps five ranked lines per package, the notes cover the task's change (harness
`note_keys`) in only **6 of the 31 treatment tasks** (ant01, hf01, hf03, lc01, lc02, st01). This is recorded now;
a small or null effect is the expected outcome for the 25 uncovered tasks, and the covered/uncovered split is
reported. Hashes of configs, adapter, scripts, notes manifests and plans: `addendum/HASHES.openagent.json`.
The header-only variant H is not run (GPU time; A vs C is the question).

**Tasks** (all 35 validated tasks; strata re-assigned for a 2025-04 cutoff, not by the Opus 5.5 labels):
- **treatment, 31 tasks** = every task whose change postdates the cutoff: the 25 Opus post-cutoff tasks (ant01-05,
  oai01-03, hf01-04, mcp01/02/04/05/06, pl01-04, st01-02, mi01-02) plus the six Opus-era controls whose change also
  postdates 2025-04: pd01-03 (pandas 3.0.0, 2026-01-21), lc01-02 (langchain-core 1.0.0, 2025-10-17), st90
  (streamlit 1.54.0, 2026-02-04);
- **controls, 2 tasks**: pl90, pl91 (polars 1.0.0, 2024-07: before the cutoff);
- **other, 2 tasks, descriptive only**: oai04 (no-change control, but "no change" was verified only from openai
  2.44.0, not from the 2025-04 release 1.7x) and oai05 (pinned behind at openai 2.44.0, itself a post-cutoff release
  for this model).
Stale patterns are the tasks' existing ones (they describe the Opus-era idiom; for some tasks this model's era idiom
may differ, e.g. huggingface-hub 0.30 used `requests`, so stale rates are a lower bound; stated as a limitation).

| study id | config | tasks | conditions | reps | sessions | seed |
|---|---|---|---|---|---|---|
| `openagent-qwen3c-main-2026-10-22` | bench.openagent-qwen3c-main.toml | 24 (main set) | A, C | 3 | 144 | 20261025 |
| `openagent-qwen3c-tasks2-2026-10-22` | bench.openagent-qwen3c-tasks2.toml | 11 (addendum-3 set) | A, C | 3 | 66 | 20261026 |

Plans are written with `bench plan` (randomised A/C order within each task x rep block). Execution is **rep-major**
(all rep-1 sessions of both studies, then rep 2, then rep 3; `I1/scripts/openagent_batches.sh`, batches of 12, two
parallel slots if the pilot shows this is faster, secret scan after every batch).

**Metrics.** Pass (hidden tests, unchanged grading); stale first edit (first change of a target file contains a
stale pattern; runs without any target-file edit are excluded from this rate and counted); stale in final diff;
model calls ("turns"); total tokens (prompt + completion from the server's usage fields, summed over calls); wall time.

**Hypotheses and rules** (task = unit; 10,000 task-bootstrap resamples, seed 20261001; exact sign-flip):
- **Q1 pass rate** (primary): Δ(C−A) on the 31 treatment tasks, mean of per-task differences, 95% CI lower bound > 0
  and two-sided sign-flip p < .05; McNemar on task majorities reported alongside. **Floor rule:** if both A and C
  treatment pass rates are < 10%, no pass-rate claim is made in either direction and only the staleness/behavioural
  metrics (Q3, Q2) are reported. Ceiling rule as before (A ≥ 90%: no pass-rate claim).
- **Q2 efficiency**: C/A total-token ratio (geometric mean of per-task medians), CI entirely below 1; turns and wall
  time secondary. (Tokens here are local and free; the question is whether notes shorten the search as with Opus.)
- **Q3 stale first edit**: rate lower in C than in A, exact two-sided sign-flip over per-task differences; Fisher at
  run level alongside (ignores clustering).
- **Q4 controls**: Δ(C−A) on pl90/pl91, descriptive (two tasks; no test interpreted). "Other" strata descriptive.
- **Coverage split** (descriptive): covered vs uncovered treatment tasks by the frozen notes (harness `note_keys`).
- Comparison with the Claude studies: descriptive only (different scaffold, limits and cutoff).
- Sensitivity: without pd01 (behavioural, silent change) and with the controls-turned-treatment tasks (pd01-03,
  lc01-02, st90) removed, i.e. the 25 tasks that are post-cutoff for every model studied.

**Validity, exclusion, stopping.** A session is valid if the agent ends by submitting, by the call/time limit, by
repeated format errors, or by context overflow (the conversation outgrew the slot's context; counted as a failure
like a turn limit). An exception from the model server or adapter (connection error, server crash, adapter bug) makes
the session invalid; it is re-run, up to three attempts; the invalid attempts are kept in `runs_invalid/` and
counted. No task is changed or dropped after the first session. A session interrupted by the nightly scheduler (no
record written) is simply re-run. Secret scan after every batch; a hit stops the run until redacted. If not all three
reps are complete by 2026-10-26 23:59 local (paper deadline 10-27), the analysis uses the completed reps (complete
for every task in both conditions), and this is reported. GPU pilot (study `openagent-qwen3c-pilot-2026-10-22`, 2
tasks, not analysed) only checks the pipeline and throughput and fixes the slot count/context; it does not change
anything above.
Threat recorded now: the open model's results may be at the floor (a 3B-active model in a minimal scaffold on tasks
that need library-specific migrations); the floor rule above was set for that case.

## 11. Addendum 5: three experiments requested in internal reviews (written 2026-10-22 ~22:05 local / 21:05 UTC, before any session below)

Motivation (stated honestly): two internal reviews of the draft asked for (a) a control that separates "any concrete list of changes" from "the change lines about the
task's package", (b) a test of the cutoff anchor with a model whose cutoff differs, and (c) a real-repository case
study. All three designs, hypotheses and analyses are fixed here before any of their sessions. Common settings, unless
stated: CLI 2.1.283, `--effort medium`, `--max-budget-usd 3`, 40 turns, 900 s, tools/permissions/env scrub, grading
with pytest-socket and a dead proxy, validity and re-queue rules, batches of <= 60 sessions with 2-3 workers, secret
scan after every batch, usage limit pauses and resumes (section 4). Task = unit of analysis; bootstrap (10,000, seed
20261001) and exact sign-flip as in section 3. Harness change: condition **R** (`bench/conditions.py`, `[paths]
notes_irrelevant` in `bench/config.py`, 19 lines); harness sha256 `cd3914f1…` (recorded per run). Hash files:
`addendum/HASHES.{irr-opus55,anchor-s45-main,anchor-s45-tasks2,case-opus55}.json`. Analysis: `I1/scripts/addendum5_analysis.py`
(written after this section; it only reuses `recompute_cost.ratio_ci`, `stale_tests.signflip` and the bootstrap of
`pooled_old_new.py`, merging studies per task).

| study id | model | conditions | tasks | reps | sessions | seed | config sha256 |
|---|---|---|---|---|---|---|---|
| `irr-opus55-2026-10-22` | claude-opus-5-5 | R (x3), A (x1, drift check) | the 11 tasks of section 8 | 3 / 1 | 44 | 20261026 | `30e01dc9…` |
| `anchor-s45-main-2026-10-22` | claude-sonnet-4-5 | A, C | 9 main-set tasks (below) | 3 | 54 | 20261027 | `c6370201…` |
| `anchor-s45-tasks2-2026-10-22` | claude-sonnet-4-5 | A, C | 6 new tasks (below) | 3 | 36 | 20261028 | `afbc8368…` |
| `case-opus55-2026-10-22` | claude-opus-5-5 | A, C | 2 real-repository tasks (cs01, cs02) | 5 | 20 | 20261029 | `d694b2f7…` |

Plans written 2026-10-22 ~21:00 UTC (`plan.jsonl` sha256 prefixes 0647142c…, aeab1ee0…, 285330e8…, 01130bde…). For
`irr-opus55` the harness plan (R, A x 3 reps) was cut to A rep 1 only right after `plan` (order indices renumbered,
block order unchanged; noted in `plan.meta.json`). Total 154 sessions.

### 11.1 E-irr: length-matched irrelevant-content control (condition R)

- **R** = the frozen C block of each task (section 8 notes, manifest `6a6f6666…`) with every change line removed
  (exactly as H; header, meta line, intro, authority sentence and the task's own package/version line kept), plus ONE
  donor package section appended verbatim: true change lines that `since-cutoff==0.4.1` generated for the same model
  and cutoff (Opus 5.5, 2026-06-30) for a package the task does not use, taken from the frozen main-run notes
  (`bench/notes`, manifest `f7e0b283…`). Donor rule (`addendum/make_irrelevant_notes.py`, sha256 `d5bb896f…`): among
  the distinct donor sections whose package is not the task's library/extra requirement and whose text matches none of
  the task's note_keys, doc_keys or answer tokens, the one making the R block's length closest to C's. Result
  (manifest `4d6a7787f9f09c15e42f701de382cfbdc2924a93869ab1113d0b0c86c5297112`, mean 427 est. tokens vs C 407):
  polars tasks <- mcp 2.2.0 section (1,653 vs 1,500 bytes), mistralai tasks <- openai 3.19.2 (1,791 vs 1,796), st01 <-
  openai 3.19.2 (1,703 vs 1,745), st02/st90 <- huggingface-hub 2.0.0 (1,797 vs 1,788). Caveats fixed now: the header
  still says the lines concern "the packages this project imports", which is false for the donor section; the meta
  line's body hash no longer matches (agents do not check it); the donor packages are not installed in the task envs.
- Comparisons use the A, C and H runs of `tasks2-opus55-2026-10-22` (same tasks, notes, settings; seed 20261024)
  with the R runs of this study. R was not randomised in the same blocks as A/C/H (it runs about a day later), so a
  concurrent **A x 1 rep** per task is included as a drift check.
- Rules (8 post-cutoff tasks):
  - **I1 content matters**: C/R total-token ratio (C from tasks2, R from this study) CI entirely below 1.
  - **I2 any concrete change list gives the gain (priming)**: R/A total-token ratio CI entirely below 1 (A from
    tasks2) **and** the C/R CI includes 1.
  - Neither: inconclusive. Secondary: list cost, turns, wall time; R/H ratio (does adding irrelevant change lines to
    the header change anything); stale first edit C vs R and R vs A (sign-flip); pass rates (ceiling rule: A was 24/24,
    so no pass-rate claim unless A_new < 90%); controls (3 tasks) and all 11 tasks descriptive.
  - **Drift check**: A_new/A_old total-token ratio (A_new = this study's single rep, A_old = tasks2 median of 3) with
    a task bootstrap CI over the 11 tasks. If the CI excludes 1, I1/I2 are reported as confounded by drift and R/A_new
    is reported alongside (descriptive).

### 11.2 E-anchor: an older-cutoff model with notes anchored to its own cutoff

- **Model** `claude-sonnet-4-5` (checked 2026-10-22: Claude Code 2.1.283 accepts the id; the init event reports
  `claude-sonnet-4-5`, `apiKeySource none`; the CLI knows its price, unlike the 5.5 models). Documented cutoff:
  Anthropic's model overview lists a training-data cutoff of July 2025 (reliable knowledge cutoff January 2025);
  models.dev, which since-cutoff uses, gives 2025-07-31. The notes use the tool's default (2025-07-31), as a user
  would get.
- **Notes**: regenerated with the released `since-cutoff==0.4.1`, `sync --yes --scope imported --model
  anthropic:claude-sonnet-4-5`, frozen: main-set tasks manifest
  `d0310fc32f69937b8472a090f9be68fd7f87aa06bf181496cbc4bcac26fc8059`, new tasks
  `a0fc991454f8dfe050885b2c1875ab4e2f30d9ea7d8a3bb9d353011042c7254e` (cutoff-era versions: anthropic 0.60.0,
  huggingface-hub 0.34.3, mcp 1.12.3, openai 1.98.0, mistralai 1.9.3, polars 1.31.0, streamlit 1.47.1). Coverage of
  the task's change among the 15 sampled tasks: **2/15** (hf03, st01; harness note_keys), recorded now.
- **Tasks**: every post-cutoff task's change postdates both cutoffs (2026-06-30 > 2025-07-31). Budget <= 90 sessions =
  15 tasks x 2 conditions x 3 reps, so 15 of the 23 post-cutoff tasks without pilot exposure (17 main + 8 new, minus
  ant01, mcp01) were drawn with `random.Random(20261025).sample(sorted(tasks), 15)`: ant02, ant04, hf02, hf03, hf04,
  mcp06, oai01, oai02, oai03 (main set) and mi01, mi02, pl01, pl02, st01, st02 (new set). No controls are run, so no
  non-inferiority claim on controls is made for this model.
- `--max-budget-usd 3` kept (Sonnet 4.5's list price, $3/$15 per MTok, is below Opus 5.5's, so the token cap is
  looser). List cost recomputed at $3 in / $15 out / $0.30 cache read / $6 1-hour / $3.75 5-minute cache write.
- Rules (15 tasks; the two studies pooled as one task set, each task from exactly one study):
  - **K1 pass rate** (primary if A < 90%): Δ(C−A) task bootstrap CI lower > 0 and exact sign-flip p < .05. If A >= 90%,
    no pass-rate claim (ceiling rule).
  - **K2 efficiency**: C/A total-token ratio CI entirely below 1; list cost, turns, wall secondary.
  - **K3 stale first edit**: lower in C than A, exact sign-flip over per-task differences (two-sided); Fisher at run
    level alongside.
  - Descriptive: the same 15 tasks' Opus 5.5 C/A ratios (main / tasks2 studies) next to Sonnet 4.5's; covered vs
    uncovered split.
- Scope of the claim, fixed now: this tests whether notes anchored to *this* model's cutoff help *this* model. It does
  not compare anchors on one model (e.g. Sonnet 4.5 given the Opus-anchored notes); that arm is not run, and the
  paper must not say the anchor was ablated.

### 11.3 E-case: real-repository case study (LiteLLM)

- **Repository**: BerriAI/litellm at b6f91a221b6b (2026-10-21; the clone from the real-world scan, the only audited
  repository with old-form uses). pyproject.toml pins `mcp>=2.3.0,<3`; uv.lock locks mcp 2.3.0. The agent gets a
  subset of the real repository (193 files, 6.2 MB: README.md, AGENTS.md, pyproject.toml, uv.lock,
  tests/integration/{__init__,conftest}.py, tests/integration/mcp/, tests/integration/_support/,
  litellm/experimental_mcp_client/, litellm/proxy/_experimental/mcp_server/), not the full 14,580-file checkout
  (per-run copies and grading time). Only mcp 2.3.0 and its dependencies are installed (env lock `mcp-2.3.0`, sha256
  `ed99fefe…`); LiteLLM's own suites cannot run, and the instruction says so.
- **Audited old-form uses and what became of them** (probes 2026-10-22, mcp 2.3.0):
  - (1, 2) `from mcp.server.fastmcp import Context, FastMCP` in tests/integration/mcp/_math_server.py (the server
    the MCP e2e suite spawns): ModuleNotFoundError at 2.3.0 -> **tasks cs01 and cs02**. The same file has a second,
    unaudited break: `mcp.settings.host/port = ...` raises ValueError on MCPServer (no such fields; host/port are now
    keyword arguments of `run(...)`).
  - (3) `streamable_http_client(url, http_client=httpx.AsyncClient(...))` in tests/integration/_support/mcp.py:
    **dropped**. Probe: an `httpx.AsyncClient` still works with mcp 2.3.0's `streamable_http_client` (duck typing; a
    tool call against a local MCPServer returned the right result), so there is no failing behaviour to test; the
    audit's "affected" verdict holds for the type annotation, not for runtime behaviour.
  - (4, 5) `ClientSession.subscribe_resource/unsubscribe_resource` in tests/integration/mcp/test_interactions.py:
    **dropped**. Deprecation warning only ("use Client.listen() instead", different semantics), and the call sites
    are integration tests that need the LiteLLM proxy gateway and its database; no deterministic offline check of a
    fix exists.
- **Tasks** (private, `since_cutoff_case`; hidden tests are not published). Both start from the real
  file. cs01 (bug report: the stdio server crashes on start; keep tools/prompts/resources/options) - hidden test:
  in-process `list_tools/call_tool/list_prompts/get_prompt/list_resources/list_resource_templates/read_resource`
  (version-agnostic result parsing, MCP_ADD_OFFSET) plus a stdio JSON-RPC smoke test. cs02 (bug report: HTTP mode
  `--transport http --host --port` must serve streamable HTTP at /mcp, and `request_headers` must return the caller's
  headers) - hidden test: subprocess server on a free localhost port, raw JSON-RPC initialize + tools/call. Gates
  (`bench validate`, all PASS): original fails at 2.3.0, reference passes at 2.3.0, original (= stale) passes at
  1.28.1; cs02's extra solution "import renamed only" fails at 2.3.0. Task hashes: cs01 `b6d97bd8…`, cs02 `2695c8ce…`
  (hidden `a193e84d…`, `e8fb581e…`). The repository subset already contains `MCPServer`/`httpx2` elsewhere (it is
  mostly migrated), so the global leak tokens are allowed for these tasks (`leak_allow`); this is the realistic
  setting. The tasks were written by an Opus 5.5 agent (as in section 8) and are not yet reviewed by the author.
- **Notes**: `since-cutoff==0.4.1 sync --yes --scope imported --model anthropic:claude-opus-5-5` on the subset with
  its real uv.lock (versions_from uv.lock): one block of 34 change lines in 6 packages (cryptography, h2, hypothesis,
  mcp, mcp-types, uvicorn), ~1,530 est. tokens, manifest
  `4653c8459d0275f50afc1d658d7b65031eaf147d2d834cad397ed3d391e3b32f`. It contains the FastMCP -> MCPServer move (cs01
  covered; cs02 1 of 2 keys: the host/port change is not in it).
- **Analysis**: descriptive only (2 tasks; no task-level test is possible). Per task and condition: passing runs out
  of 5, median list cost, total tokens, turns, wall time; per-task C/A median ratio with a run-level bootstrap CI
  (10,000, seed 20261001), labelled descriptive; stale first edit counts; one transcript-level observation per task.
  Absolute list cost per session is reported.

### 11.4 Order and reporting

Order: E-irr, then E-anchor (main-set study, then new-task study), then E-case. If the usage limit or the schedule
stops a study, it resumes with `run --resume`; an incomplete study is reported as incomplete (completed blocks only).
Results go to RESULTS_FOR_PAPER.md section 0.9 with every number, its source file and its CI/test; rules met / not
met / inconclusive are stated as such. This workstream does not edit the paper.

10.1 GPU pilot record (2026-10-22 22:50-23:05 local, before any study session; nothing in section 10 changed).
GPU lock taken ("SC") at 22:49 after T1 released it. Server: `openagent_server.sh 20 40960 2` = `--n-cpu-moe 20`
(experts of the first 20 of 48 layers in CPU RAM), 2 slots x 40,960-token context, q8_0 KV, flash attention; VRAM
15.6 of 16.4 GB. Throughput (synthetic 3k-token prompt, 300 output tokens): one stream 1,177 prompt tok/s and 40
generated tok/s; two concurrent streams 29-34 generated tok/s each (~62 aggregate), so the study runs **2 slots** (two
adapter processes, `--shard 0/2`, `1/2`). Native tool calling works (no `--textbased`). Pilot sessions (study
`openagent-qwen3c-pilot-2026-10-22`, run concurrently): st01 C r1 PASS (15 calls, 56.7k tokens, 130 s) and pl91 A r1
PASS (17 calls, 70.0k tokens, 151 s); both valid (Submitted), grading, first-edit detection and records OK. Not
analysed. Both pilot agents also wrote extra test files of their own; harmless for grading (the hidden tests run from their own folder with
`--confcutdir`, so agent-written tests and conftest files are not collected, as in all studies).

## 12. Addendum 6: deployment iteration - a newer tool version on the same tasks (written 2026-10-22 ~23:15 local / 22:15 UTC, before any session below)

Motivation (stated honestly): section 8's study found that the frozen 0.4.1 notes named the task's change in only 2
of 8 new post-cutoff tasks (pl02, st01; RESULTS_FOR_PAPER 0.7/0.7.1; paper Lesson 3), because 0.4.1 shows at most
five change lines per package, does not report changed defaults (pl01, mi02) and does not report dependency switches
(mi01). This study asks whether later tool versions that act on those lessons change coverage and outcomes on the
**same** tasks, model, cutoff and harness: lesson found in evaluation -> fixed in a later version -> measured.

**Which gaps later versions close** (checked 2026-10-22 against the tool repo `~/projects/since-cutoff`, CHANGELOG
and code):
- dependency switches (`dependency_switched`, `[diff + metadata]`, listed first in `sync --scope imported`):
  **released in 0.5.0** (2026-09-28) -> mi01 (httpx -> httpx2).
- 30-day margin (compare from the latest release >= 30 days before the cutoff): **unreleased, on main** (#98,
  d3b212c). For these tasks it moves the comparison release to polars 1.41.2 (was 1.42.1) and mistralai 2.4.8 (was
  2.5.0); streamlit stays 1.58.0. It closes no task's gap here, and it **hides mi02's flip**:
  `Ocr.process(include_blocks=)` was added in 2.5.0 (False) and flipped in 3.x (True), so against 2.4.8 it is a new
  parameter, not a changed default.
- changed defaults: **in no version** (apidiff.py ignored all defaults). Added for this study as a small change on a
  NEW LOCAL branch of the tool repo, `naacl/changed-defaults`, commit **3f0144f** on top of origin/main 11e5728
  (commits by the author, no AI trailer; not pushed, not released): a flip of the literal `True`/`False` default of a
  public parameter is a change of its own (`default_changed`, diff schema 22), noted in `sync --scope imported` on
  top of the per-package budget (up to 5 APIs per package), never "old form", not probed by `run`; other default
  changes stay ignored. 8 new unit tests (`tests/test_default_changed.py`), 4 fixtures re-recorded (`--check`
  unchanged), offline suite on Python 3.13: 1,464 passed + the 2 schema-gated fixture tests passing after
  re-recording (183 passed in the affected files; 3.10: 136 passed in the touched test files), ruff/mypy clean, CHANGELOG
  + READMEs (4 languages) + how-it-works.md updated. Measured precision proxy: polars 1.41.2 -> 2.0.0 has 6 such
  flips among 205 changes (5 x `explode(empty_as_null=)`, `from_arrow(rechunk=)`), streamlit 1.58.0 -> 1.66.1 one,
  mistralai 2.4.8 -> 3.3.0 none. **Disclosed bias:** the detector was written (by an Opus 5.5 agent) after the
  evaluation showed pl01 uncovered; it is a general rule, not task-specific, but pl01 motivated it.
- per-package cap: **unchanged** in every version (`IMPORTED_APIS = 5`; `--per-package N` exists since 0.4.1; the MCP
  tool `api_changes` lists 10 per package by default since 0.2.0, which is not part of the CLAUDE.md notes).
  Descriptive probe (not used in any session): with `--per-package 10` the 3f0144f notes still do not cover pl03 or
  pl04 (their changes rank below 10th) and, by the harness regex, lose st01 (the longer merged bullet pushes
  "removed" past the regex window).
- st02 (`st.image(use_column_width=)` accepted but ignored): not detectable from a static API diff in any version.

**Condition C2** = notes from since-cutoff 3f0144f (wheel
`I1/notes/tools/3f0144f/since_cutoff-0.5.0-py3-none-any.whl`, sha256 `8d39475d…`; it reports itself as "0.5.0"
because main has not been bumped), same command as section 8 (`sync --yes --scope imported --model
anthropic:claude-opus-5-5 --target CLAUDE.md`, default settings, so the 30-day margin applies), generated with
`addendum/bench.iter-opus55-notes.toml` (sha256 `f0e3ac32…`) and frozen: `I1/notes/tasks2-opus-5-5-v2`, manifest
`d292149bae015219d698be6a3cbb38f76bb739bea8ed8f83b64ecb3d7f3c767b`, mean ~484 est. tokens (C: ~407).
**Coverage recorded before any session** (harness `note_keys`, same regexes as section 8):

| task | C (0.4.1) | C2 (3f0144f) | why |
|---|---|---|---|
| pl01 | no | **yes** | changed-default detection (new) |
| pl02 | yes | yes | |
| pl03 | no | no | `replace(default=)` ranks below the 5-API cap |
| pl04 | no | no | `collect(streaming=)` ranks below the cap |
| st01 | yes | yes | |
| st02 | no | no | silently ignored parameter: not visible to a static diff |
| mi01 | no | **yes** | dependency switch (0.5.0) |
| mi02 | no | no | flip hidden by the 30-day margin (parameter absent from 2.4.8) |
| controls pl90, pl91, st90 | no | no | pre-cutoff changes are out of scope by design |

Post-cutoff coverage 2/8 -> **4/8**. Strata for the descriptive analysis: newly covered {pl01, mi01}, covered by both
{pl02, st01}, covered by neither {pl03, pl04, st02, mi02}. C2 differs from C in more than coverage (comparison
release, wording of the newer notes, merged bullets, changelog pointers, length, the header's version and "comparing
from releases up to 2026-05-31"), so C2 vs C measures the **version**, not coverage alone; the "neither" stratum
shows the effect of the non-coverage differences.

**Study** (harness change: condition `C2` = `notes_variant "v2"`, `[paths] notes_v2`; `bench/conditions.py`,
`bench/config.py`, 19 lines; harness sha256 `0f091005…`; config `addendum/bench.iter-opus55.toml` sha256
`58ac4477…`; hashes `addendum/HASHES.iter-opus55.json`):

| study id | model | conditions | tasks | reps | sessions | seed |
|---|---|---|---|---|---|---|
| `iter-opus55-2026-10-22` | claude-opus-5-5 | C2 (x3), A (x1), C (x1) | the 11 tasks of section 8 | 3 / 1 / 1 | 55 | 20261030 |

The harness plan (C2, A, C x 3) was cut to A and C rep 1 right after `plan` (order indices renumbered, block order
unchanged; `plan.meta.json` note; plan.jsonl sha256 `f2492d9f…`). Settings exactly as section 8 (CLI 2.1.283,
`--effort medium`, `--max-budget-usd 3`, 40 turns, 900 s, tools/permissions/env scrub, grading with pytest-socket
and a dead proxy). One batch of 55 sessions, **2 workers** (another agent runs Claude sessions concurrently), secret
scan after the batch; validity, exclusion, re-queue and usage-limit rules as section 4.

**Comparators**: the A, C (and H) runs of `tasks2-opus55-2026-10-22` (same tasks, settings and C notes; 3 reps; run
2026-10-22 ~18:05-20:30 UTC). Because section 11.1 found a drift point estimate of 1.18 between days, this study adds
concurrent A x 1 and C x 1 ("A_new", "C_new").

**Hypotheses and rules** (post-cutoff stratum = 8 tasks; task = unit; ratios = geometric mean over tasks of per-task
median ratios; task bootstrap 10,000, seed 20261001; exact sign-flip; as sections 3/8/11):
- **K1 coverage**: 2/8 -> 4/8 (deterministic, recorded above; not a test).
- **K2 efficiency, primary**: C2/C total-token ratio (C = tasks2, 3 reps). Met ("no worse") if the CI upper bound
  <= 1.10 **and** the C2/A point estimate <= the C/A point estimate (0.79, A = tasks2). "Improvement shown" only if
  the C2/C CI is entirely below 1. Secondary: list cost, turns, wall; C2/A ratios with CIs; C2/H.
- **K3 stale first edit non-inferiority**: Δ(C2 − C) and Δ(C2 − A) in the per-task stale-first-edit rate (task
  bootstrap, one-sided 95% upper bound <= +10 pp); two-sided sign-flip p reported. (C and A had 0/24 on these tasks,
  so this mainly checks that C2 does not introduce stale code.)
- **K4 pass-rate non-inferiority**: Δ(C2 − A) and Δ(C2 − C), one-sided 95% lower bound >= −10 pp (task bootstrap);
  ceiling rule as section 8 (A was 24/24: no superiority claim).
- **Drift check**: A_new/A_old and C_new/C_old total-token ratios over the 11 tasks (task bootstrap). If either CI
  excludes 1, K2 is reported as confounded by drift and the concurrent C2/C_new and C2/A_new ratios (C2 median of 3
  vs a single rep) are given equal weight in the reading (descriptive, noisy).
- **Descriptive**: per-stratum (newly covered / both / neither) C2/C and C2/A ratios and pass rates; per-task
  medians; whether the agent's first edit handles the newly covered change (pl01 passes `empty_as_null`, mi01 uses
  `httpx2`); site-packages reads per session; controls (3 tasks) C2−A pass-rate non-inferiority and token ratios.
- Power is low (8 tasks; C/A was 0.79 with CI 0.68-0.92); a K2 without "improvement shown" is inconclusive, not
  evidence of no effect. The analysis script `I1/scripts/iter_analysis.py` is written after this section and only
  reuses `recompute_cost.ratio_ci`, `stale_tests.signflip` and the bootstrap of `pooled_old_new.py` /
  `addendum5_analysis.py`. Results go to RESULTS_FOR_PAPER.md section 0.10 with every number, source and CI/test.
  This workstream does not edit the paper.

## 10a. Amendment: header-only condition H for the open-model agent on the 17 original post-cutoff tasks (written 2026-10-23 ~01:05 local / 00:05 UTC, during the section-10 study and before any H session)

Why (stated honestly): an internal review named a non-Claude run on the 17 original post-cutoff tasks with A, C and
H as the most informative addition. A and C on those tasks are already in the section-10 main study
(`openagent-qwen3c-main-2026-10-22`; ~77 of 214 section-10/pilot sessions had been recorded when this was written,
and interim A/C numbers had been looked at, which is disclosed here); this amendment adds H only. Nothing in section
10 changes; the section-10 analysis stays primary for A vs C.

- **Study** `openagent-qwen3c-h-2026-10-23`: condition H x 17 tasks (ant01-05, oai01-03, hf01-04, mcp01/02/04/05/06)
  x 3 reps = 51 sessions, seed 20261028, config `I1/configs/bench.openagent-qwen3c-main-h.toml` (sha256 f4e64e50f53903c7ab18c7ebe83b13734306169700fec48353a726c42b1dbf58),
  plan sha256 9ee75bd9a588ef7114c80b99001fb947c82b17ed0afa84a9524d92ff76cefbcf. H notes = `make_header_notes.py` on the frozen section-10 main-set notes (header and per-package
  version lines kept, every change line removed): manifest
  `9328ad9a8cdb245b35058437abe3f918156e339ba491a87a3d52bd57d068c3c4`, mean ~246 est. tokens.
- Same server, flags, adapter, limits and grading as section 10/10.1. It runs **after** the section-10 studies finish
  (rep-major: all rep-1 sessions, then rep 2, then rep 3; `I1/scripts/openagent_batches_h.sh`, sha256 49e67caad726997a56729c30b9110ec313f3cffbfa53a39e165386e93ecd470a, = the
  section-10 driver with a study-list argument), so H is not randomised within blocks with A and C: a time-of-run
  confound (same server and machine; no model or software change) is accepted and reported.
- **Analysis** (`openagent_analyze.py --pairs C/A,H/A,C/H --only-tasks <17>`, sha256 1b6cd001dab12655adf583d694646f870d9095eca0d217f8cd3d810446bd2294): on the 17 tasks, pass-rate
  differences for C-A, H-A, C-H (task bootstrap CI, exact sign-flip, Holm over the three as in section 7); token,
  turn and wall-time ratios; stale first edit. **P1 (placebo):** notes act through their content if C differs from H
  in the direction C better (pass, stale first edit) or cheaper (tokens), CI/sign-flip as above. Floor rule as section
  10 (if A, C and H all < 10% pass on these 17 tasks, no pass-rate claim). Exclusion/validity/stopping as section 10.
  If the 08:17 GPU stop or T2's GPU slot prevents all three reps, completed reps are analysed and this is reported.

## 13. Addendum 7: concurrent mechanism ablation - generic instruction G, with A, C, H and R in the same blocks (written 2026-10-23 ~01:30 local / 00:30 UTC, before any session below)

Motivation (stated honestly): an internal review points out that
(a) the C-versus-R contrast of section 11.1 compared R runs made about a day after the A/C/H runs, with a concurrent A
drift estimate (A_new/A_old 1.18 [0.97, 1.43]) as large as the C/R effect, and (b) no arm tests whether a short
generic "your knowledge may be stale, check installed APIs" instruction, with no package lines, does most of the work.
This study runs A, C, H, R and a new generic-instruction arm G **concurrently** (same randomised blocks, same day,
same harness, same CLI and model) on the 11 tasks of section 8. Everything below is fixed before the first session.

**Condition G** (harness: `notes_variant "generic"`, `[paths] notes_generic`; `bench/conditions.py` +12 lines,
`bench/config.py` +7 lines; block written by `addendum/make_generic_notes.py`). The same block for every task, placed
where the notes go (after the base CLAUDE.md block); no package, version, model, cutoff date, tool name or markers:

> ## Library APIs may have changed since your training data
>
> Your knowledge of library APIs may be out of date. The versions pinned in `pyproject.toml` may have been released
> after your training data was collected, and between releases functions, classes, parameters, default values and
> import paths can be renamed, moved, changed or removed. Before using an API from an installed package, check its
> signature in the installed source (the package's files in `.venv`) or with `help()`, and write code for the version
> that is installed, not the version you remember. If a call fails with an import, attribute or argument error, or a
> deprecation warning appears, look up the installed API before trying another guess. This applies to every
> third-party package, including ones you know well. Where the installed code conflicts with what you remember,
> follow the installed code.

(Exact bytes: `addendum/notes-tasks2-generic/*.md`, 872 bytes, ~218 est. tokens, block sha256 `f1ba057e…`; frozen
manifest `e8ed48cd921e0d6743506386fc8630b60ff12fe84311c1442f07a76b63b5db66`.) Length is matched roughly to H (932-1,024
bytes, mean 237.5 est. tokens; C ~407; R ~427). Differences from H stated now: G names no package, version, model or
cutoff, carries no "according to <tool>" authority and no tags, and it contains an explicit *procedure* (check the
installed signature first), which H does not; so G vs H tests "version-specific framing" against "generic framing +
a lookup instruction", not framing alone. Note: the harness denies `python -c` (PROTOCOL 12.x), so `help()` needs a
script file; the instruction is kept as written because a practitioner's generic line would read like this.

**Other conditions**, unchanged and frozen: A (base block only); C = since-cutoff 0.4.1 notes of section 8 (manifest
`6a6f6666…`, coverage 2/8 post-cutoff: pl02, st01); H = header-only (`7810f819…`); R = section 11.1 irrelevant-content
notes (`4d6a7787…`).

**Study**: config `addendum/bench.conc-opus55.toml` (the section-12 config with conditions A, C, H, R, G and paths
notes_header / notes_irrelevant / notes_generic; sha256 `ae7e9ce6…`); harness sha256 `67eb0b65…` (recorded per run;
the harness test suite passes, 90 tests); hashes of every task, hidden test and env lock in
`addendum/HASHES.conc-opus55.json` (task hashes unchanged from section 8). Plan written 2026-10-23 ~00:20 UTC:
harness plan sha256 `ac52af34…` (kept as `plan.orig.jsonl`), rep-major plan.jsonl sha256 `a958f31e…`.

| study id | model | conditions | tasks | reps | sessions | seed |
|---|---|---|---|---|---|---|
| `conc-opus55-2026-10-23` | claude-opus-5-5 | A, C, H, R, G | the 11 tasks of section 8 (8 post-cutoff, 3 controls) | 3 | 165 | 20261031 |

Plan: harness `plan` (randomised blocks = task x rep, condition order shuffled within each block, so the five
conditions of a block run back to back on one worker). Right after `plan`, the blocks are reordered **rep-major**
(all rep-1 blocks in their shuffled order, then rep 2, then rep 3; order indices renumbered, block contents and
within-block order unchanged; noted in `plan.meta.json`) so that a stop by the 08:17 weekday scheduler leaves complete
replicates. Settings exactly as section 8 (CLI 2.1.283, `--effort medium`, `--max-budget-usd 3`, 40 turns, 900 s,
tools/permissions/env scrub, grading with pytest-socket and a dead proxy). Batches of <= 60 sessions, 3 workers (2
after any usage-limit warning), secret scan after every batch; validity, exclusion, re-queue and usage-limit rules as
section 4. No condition, task or block is changed or dropped after the first session.

**Hypotheses and rules** (post-cutoff stratum = 8 tasks; task = unit; ratios = geometric mean over tasks of per-task
median ratios; task bootstrap 10,000, seed 20261001; exact two-sided sign-flip over per-task log ratios; all
comparisons use only this study's runs, i.e. concurrent arms):
- **Primary metric**: total tokens. Secondary: list cost, turns, wall time, output tokens.
- **Pre-registered family (Holm over three tests on total tokens):**
  - **M1 content beyond generic framing**: C/G CI entirely below 1 **and** Holm-adjusted sign-flip p < .05 ->
    "supported"; CI below 1 but Holm p >= .05 -> "suggestive"; otherwise "not supported".
  - **M2 content beyond irrelevant content, concurrent (re-test of section 11.1 I1)**: C/R, same rule. The earlier R
    result counts as **confirmed** if the concurrent C/R CI is entirely below 1, **not replicated** if the CI includes
    1, **reversed** if the CI is entirely above 1 (reported with the point estimate in each case).
  - **M3 version-specific framing vs generic instruction**: G/H, two-sided; "G cheaper" / "H cheaper" only if the CI
    excludes 1 and Holm p < .05; otherwise "no difference shown".
- **Reported with CIs and unadjusted sign-flip p, not part of the family**: C/A, G/A, H/A, R/A, C/H, R/H, G/R (the
  ordering of the five arms against the agent alone).
- **Non-inferiority** (each of C, G, H, R vs A): pass rate Δ one-sided 95% lower bound >= −10 pp (task bootstrap; on
  the 8 post-cutoff tasks and, separately, on the 3 controls); stale first edit Δ one-sided 95% upper bound <= +10 pp.
  Ceiling rule as section 8: if A >= 90% on post-cutoff tasks, no pass-rate superiority claim. Known now: with 8
  tasks x 3 reps a single failing (or stale) run in an arm whose comparator has none gives a bound of about 12.5 pp and
  fails this rule; such a case is reported with the run named, as in sections 8 and 12.
- **Descriptive**: covered (pl02, st01) vs uncovered (6) split for every ratio (the key question for content is C/G
  on the uncovered tasks); per-task medians; reads of installed package sources per session (harness
  `process.site_packages_reads`, exploratory mechanism); cross-day ratios of the same condition (this study vs
  tasks2 for A, C, H; vs irr for R) to quantify drift.
- **Partial completion**: the pre-registered analysis uses every replicate that is complete (all 55 runs of the rep
  valid); if the study stops early, results on the complete replicates are reported as such (e.g. "rep 1-2, 110
  sessions"), and runs of an incomplete replicate are reported only descriptively. Power is low (8 tasks; earlier
  C/A 0.79 [0.68, 0.92]); "not supported" is inconclusive, not evidence of no effect.
- Analysis script `I1/scripts/conc_analysis.py`, written before any session (copy `addendum/conc_analysis.py`, sha256
  `a07f337c…`; smoke-tested on the earlier tasks2/irr records relabelled, where it reproduces section 11.1's C/R 0.78
  [0.64, 0.95]); it reuses `recompute_cost.ratio_ci`, `stale_tests.signflip` and `addendum5_analysis` helpers. Results go to
  RESULTS_FOR_PAPER.md section 0.11 with every number, source and CI/test. This workstream does not edit the paper.

## 14. Addendum 8: lockfile-only header L (does the cutoff/diff information matter beyond naming pinned versions?), with an optional wrong-block harm check W (written 2026-10-23 ~17:40 local / 16:40 UTC, before any session below)

Motivation (stated honestly): an internal review notes that the
pre-registered "change lines add to the header" test failed (section 13: C/H 1.04 [0.90, 1.17]) and asks whether the
header that carries the saving needs the API diff at all, or whether simply naming the project's pinned versions does
the same. It also asks what a wrong block does (harm check). This study runs a new arm **L** concurrently with A, H
and C, and (optionally, only if session budget remains after L) a separate concurrent A-versus-W study. Everything
below is fixed before the first session of any study in this section. Where this design differs from the one the internal review proposed, this design is followed: the review's L
kept the cutoff versions; this L lists ONLY the pinned versions.

**Condition L** (harness: `notes_variant "lockfile"`, `[paths] notes_lockfile`; `bench/conditions.py` +24 lines
together with W, `bench/config.py` +14 lines; block written by `addendum/make_lockfile_notes.py`, sha256
`e2dcb428…`). For each task: the project's pinned direct dependencies read from `repo/pyproject.toml`
`[project].dependencies` (exact `name==version` pins, file order; no lockfile parser, no diff, no matcher, no network,
no model). Same place as H (after the base CLAUDE.md block), same heading level, bold package lines and closing
authority sentence as H; it has **no** cutoff version, model name, cutoff date, "changed after the training cutoff"
framing, change lines, tags sentence, tool name, link, meta line or markers. Exact text (polars tasks; the other tasks
differ only in the package line(s)):

> ## Library versions pinned in this project
>
> The packages this project depends on, at the exact versions pinned in `pyproject.toml`. Where these lines conflict
> with what you remember, follow these lines.
>
> **polars 2.0.0**

The package set equals H's on every task (each task has one direct dependency, which is H's package), except ant04,
where L lists `anthropic 1.8.0` and `httpx 0.28.1` and H lists only anthropic (httpx has no post-cutoff change).
L is 218-241 bytes (~56 est. tokens) vs H 932-1,024 bytes (~238). Note: the base block already says "Dependencies are
pinned in `pyproject.toml` and already installed", so L adds the version numbers and the authority sentence only.
Frozen manifests: tasks2 `308f1d0e8bb75442810e071504a7e4c386f8f69342b03c5938af43218206a645`
(`addendum/notes-tasks2-lockfile`, copy of `I1/notes/tasks2-opus-5-5-lockfile`), original tasks
`842b4a559004150c8ab4c696eb375eeaf613577aed9585f55a9baf9f6fec12e1` (`addendum/notes-orig-lockfile`, copy of
`I1/notes/opus-5-5-lockfile`).

**Other conditions**, unchanged and frozen: A (base block only); C = since-cutoff 0.4.1 notes (tasks2 manifest
`6a6f6666…`, coverage 2/8 post-cutoff: pl02, st01); H = header-only (tasks2 `7810f819…`; original tasks `3688d53d…`,
the H notes of section 7). C is not run on the original tasks in this section.

**Studies** (harness sha256 `5a7458b23f20bb8fd40e3f33626246bee8eb293974d16af137bd0437ffc45a69` for all three, recorded
per run; harness test suite 90 passed; task, hidden-test and env-lock hashes in
`addendum/HASHES.{lockhdr-tasks2,lockhdr-orig,wrong-tasks2}.json`, task hashes unchanged from sections 7/8):

| study id | model | conditions | tasks | reps | sessions | seed | config sha256 |
|---|---|---|---|---|---|---|---|
| `lockhdr-tasks2-opus55-2026-10-23` (S1) | claude-opus-5-5 | A, C, H, L | the 11 tasks of section 8 (8 post-cutoff, 3 controls) | 3 | 132 | 20261101 | `f0c2a45b…` |
| `lockhdr-orig-opus55-2026-10-23` (S2) | claude-opus-5-5 | A, H, L | the 17 original post-cutoff tasks (ant01-05, oai01-03, hf01-04, mcp01/02/04/05/06; ant01/mcp01 pilot-exposed, planned as ordinary tasks as in section 7) | 2 | 102 | 20261102 | `bc689773…` |
| `wrong-tasks2-opus55-2026-10-23` (W, optional) | claude-opus-5-5 | A, W | the 11 tasks of section 8 | 3 | 66 | 20261103 | `6fa1b418…` |

Configs `addendum/bench.lockhdr-tasks2-opus55.toml` (= section-13 config with conditions A, C, H, L and path
notes_lockfile), `addendum/bench.lockhdr-orig-opus55.toml` (= section-7 config with conditions A, H, L, path
notes_lockfile, `pilot_tasks = []`), `addendum/bench.wrong-tasks2-opus55.toml`. Plans written 2026-10-23 16:38 UTC by
harness `plan` (randomised blocks = task x rep, condition order shuffled within each block, so all arms of a block run
back to back on one worker), then reordered **rep-major** (`addendum/reorder_rep_major.py`, sha256 `fd97245d…`;
originals kept as plan.orig.jsonl; noted in plan.meta.json): S1 plan.orig sha256 `f3fb1ab6…` -> plan.jsonl
`385c75c0…`; S2 `0737c36f…` -> `3ab2fbeb…`; W `079a2097…` -> `26b452e3…`.

**Order of sessions** (so that replicate 1 of every arm is complete first): S1 rep 1 (44), S2 rep 1 (51), S1 rep 2
(44), S2 rep 2 (51), S1 rep 3 (44); then W (66) only if the usage limit allows after S1 and S2 are complete. Each step
is one batch (<= 60 sessions, `run --resume --max-sessions <n>` in plan order), 3 workers (2 after any usage-limit
warning), secret scan after every batch. Settings exactly as sections 8/13 (CLI 2.1.283, `--effort medium`,
`--max-budget-usd 3`, 40 turns, 900 s, tools/permissions/env scrub, grading with pytest-socket and a dead proxy);
validity, exclusion, re-queue and usage-limit rules as section 4. No condition, task, block or analysis is changed or
dropped after the first session. Arms within a study are concurrent; S1 and S2 interleave on the same evening and
share no tasks, so pooling S1 and S2 per task keeps every comparison concurrent.

**Hypotheses and rules.** Primary metrics: **total tokens** (geometric mean over tasks of per-task median ratios) and
**list-price cost per solved task** (sum of list cost / number of passed sessions per arm, pooled over tasks). Both with
a task bootstrap (10,000 resamples, seed 20261001, percentile 95% CI) and an exact two-sided sign-flip test over
per-task log ratios (tokens: log ratio of per-task medians; cost per solved task: log ratio of per-task
cost / max(passes, 0.5)); the exact test is enumerated (meet-in-the-middle for n > 16; identical counts). Secondary:
list cost per session, turns, wall time, output tokens.
- **F1 (primary family; S1, 8 post-cutoff tasks; all four arms concurrent): {L/A, H/L, C/L} x {tokens, cost per
  solved task}, Holm over the 6 tests.**
- **F2 (key secondary family; pooled 25 post-cutoff tasks = S1's 8 + S2's 17, arms A, H, L): {L/A, H/L} x {tokens,
  cost per solved task}, Holm over the 4.** Run only if S2 has at least one complete replicate; reported with and
  without the pilot-exposed ant01 and mcp01 (the without-pilot version is not in the family).
- Verdict per test: "supported" = CI entirely below 1 and Holm p < .05; "suggestive" = CI below 1, Holm p >= .05;
  "no difference shown" otherwise (reverse-direction analogues reported as such).
- **Decision for the review's question (H/L), applied to F2 when it exists, otherwise to F1:**
  (i) **"cutoff-version/diff information adds"** if H/L is "supported" on either primary metric;
  (ii) **"L matches H"** if on BOTH primary metrics the 90% bootstrap CI of H/L lies inside the equivalence margin
  [0.85, 1/0.85 = 1.176] (TOST at 5% per side; margin = about half of the H/A effect, 0.73-0.86, seen so far);
  (iii) equivalence on one metric only, or neither (i) nor (ii): **inconclusive**. Power is limited (8 or 25 tasks);
  an inconclusive result is not evidence of no effect.
- **L/A** answers "do pinned versions alone save?"; **C/L** "does the full block beat naming versions?" (F1 only).
- Reported, not in a family: H/A, C/A, C/H (S1); H/A (S2, pooled); coverage split (covered = C's lines name the task's
  change: pl02, st01, ant01, ant03, hf01, hf02, hf03; descriptive); controls (3 tasks; tokens and cost per solved,
  descriptive); reads of installed package sources per session (`process.site_packages_reads`, exploratory);
  cross-day same-arm ratios vs section 13 (A, C, H on tasks2) and section 7 (A, H on the original tasks), descriptive.
- **Non-inferiority** (each of L, H, C vs A, as section 13): pass-rate difference one-sided 95% lower bound >= -10 pp
  (task bootstrap; post-cutoff tasks, and controls separately); stale-first-edit difference one-sided 95% upper bound
  <= +10 pp. Ceiling rule: if A >= 90% on post-cutoff tasks, no pass-rate superiority claim. As before, a single
  failing (or stale) run in an arm whose comparator has none can fail the 10 pp rule with 8 tasks; such runs are named.
- **Partial completion**: each study's pre-registered analysis uses its complete replicates (all planned runs of the
  rep valid); S1 must have at least replicate 1 for F1 to be reported; runs of an incomplete replicate are reported only
  descriptively; if S2 is not run or has no complete replicate, F2 is not reported and the decision uses F1.

### 14.2 Optional harm check W (run only if budget allows after S1 and S2)

**Condition W** (harness `notes_variant "wrong"`, `[paths] notes_wrong`; block written by
`addendum/make_wrong_notes.py`, sha256 `eef8f7f3…`; frozen manifest
`767ca7af4843a1f9897155ee96db7c4610dba3ac077015efeee83ab32562a5d2`, `addendum/notes-tasks2-wrong`, copy of
`I1/notes/tasks2-opus-5-5-wrong`, mean ~270 est. tokens): the task's frozen H block (C's header, meta line, intro,
tags and authority sentences, package/version line) plus ONE change line, in since-cutoff's own sentence templates and
tags, that is plausible but **false for the pinned version**: it presents the task's correct (pinned-version) API as
removed and the cutoff-era or older API as the one to use (mi01, mi02, pl01: an HTTP-layer or parameter claim that is
false). This is the block that a diff run in the wrong direction, or a stale block left after a version change, would
give for the task's API, i.e. a worst realistic case. The eleven lines were written by an agent (Claude Opus 5.5) from
each task's task.toml before any W session, and each was checked to be false against the installed package
(`C:/b/venvs`: polars 2.0.0 has `LazyFrame.collect_batches`, `Expr.replace_strict`, `collect(engine=)`,
`explode(empty_as_null=)`, `cum_sum`, `group_by` and lacks `read_csv_batched`, `collect(streaming=)`, `cumsum`,
`groupby`; streamlit 1.66.1 has `cache_data`, `query_params`, `image(width=)` and lacks `cache`,
`experimental_get_query_params`; mistralai 3.3.0 ships httpx2, not httpx, and `ocr.process` defaults to
`include_blocks=True`). Lines (exact text in the script and manifest), e.g. pl04: "`polars.LazyFrame.collect`:
parameter `engine` was removed; do not use it. Use `streaming=True` instead. [diff + library]"; st01:
"`streamlit.cache_data` was removed; do not use it. Use `streamlit.cache` instead. [diff + library]".
- Study `wrong-tasks2-opus55-2026-10-23` (table above): A and W in the same randomised blocks (its own concurrent A),
  11 tasks x 3 reps = 66 sessions, rep-major, same settings, batches and scans as above.
- Outcomes (8 post-cutoff tasks; controls separately): pass rate W vs A (difference with task bootstrap CI and exact
  sign-flip; **harm shown** if the CI is entirely below 0 and sign-flip p < .05; "no harm shown" otherwise;
  non-inferiority bound reported); stale first edit W vs A (same rules, direction reversed); total tokens and cost per
  solved task W/A (CI and sign-flip). Descriptive: per run, whether the agent followed the false line (the false API in
  its first edit or final code, from the stale-pattern detector and the final diff) and whether it recovered after
  running the tests. With A at ceiling (24/24 in earlier studies), any W failure is informative descriptively.
- If W is not run (budget), this is reported; W is never run before S1 and S2 are complete.

Analysis script `I1/scripts/lockhdr_analysis.py` (copy `addendum/lockhdr_analysis.py`, sha256 `4ac7cfc8…`), written
before any session; smoke-tested on the section-13 and section-7 records relabelled (G -> L, C -> L; output
`I1/analysis/_smoke_lockhdr.json`, not a result), where it reproduces section 13's H/A 0.73 [0.60, 0.85], C/A 0.75
[0.62, 0.90], C/G 0.80 [0.66, 0.98] and section 0.12's concurrent cost-per-solved C/A 0.77. It reuses
`recompute_cost.ratio_ci`/`load`, `addendum5_analysis` helpers, `stale_tests.signflip` and `pooled_old_new.boot_mean`.
Results go to RESULTS_FOR_PAPER.md section 0.13 with every number, source and CI/test; this workstream does not edit
the paper.

### 14.1 Amendment: aborted first launch (expired CLI login) and an auth-classifier fix (written 2026-10-23 ~17:52 local / 16:52 UTC, before any session that reached the model)

What happened. S1 was launched at 16:43:55 UTC (after commit 6782807 and tag naacl-addendum8-prereg-2026-10-23).
The Claude Code login used by the harness had expired: the refresh token's expiry (`refreshTokenExpiresAt`) was about
12:45 UTC, and at 16:44:07 UTC the CLI cleared the stored tokens. The first three sessions (pl90 A r1, pl91 L r1,
st02 H r1; and pl90 H r1, pl91 H r1 a few minutes later) ended after one synthetic turn with "Failed to authenticate:
OAuth session expired and could not be refreshed" (`result.subtype` "success", `is_error` true, 0 tokens, $0). The
harness classified them as **valid** (failed) runs, because its auth pattern matched "oauth token expired" but not this
wording and the result subtype was not an error subtype. The other 39 attempts failed before the agent started
(`python -m venv` / `pip install` exit 0xC0000142, STATUS_DLL_INIT_FAILED; transient: a venv created at 16:47 UTC
with the same command succeeded). I stopped the driver at ~16:46 UTC. **No session reached the model (total tokens 0
over all 44 records)**, so nothing about the arms was observed.

Actions (before any further session): (1) the aborted records were moved aside unchanged to
`results/lockhdr-tasks2-opus55-2026-10-23/_aborted_launch_2026-10-23T1643Z/` (runs.jsonl, runs/, logs; secret scan 0)
and the agent projects to `C:/b/runs/_aborted_lockhdr-tasks2-opus55-2026-10-23T1643Z`; the plans are unchanged and
the study restarts from its first block. (2) `bench/runner.py` (+6/-1): `AUTH_RE` also matches "failed to
authenticate|oauth session expired|authentication_failed", and a result with `is_error` true, an auth message and no
output tokens is classified invalid "auth" (re-queued; the run loop stops on "auth"). This changes only the
classification of runs that never reached the model; grading and every valid-run rule are unchanged. New harness
sha256 `15239089aa39e474dfd1cbad2095f704f6a2698c3076d6edaf2fff457b69d3a3` (all three studies; HASHES files
regenerated; plan.meta.json still records the plan-time harness `5a7458b2…`, and every run record carries the harness
it ran with). Harness tests: runner/isolation subset 32 passed after the change (the full suite, 90, passed before
it). (3) The driver (`addendum/lockhdr_driver.sh`, sha256 `184ee482…`) refuses to start a batch unless the CLI login
holds a usable token and stops if any valid record has zero tokens. Restarting needs the author to log in again
(`claude auth login`); agents must not handle credentials.
