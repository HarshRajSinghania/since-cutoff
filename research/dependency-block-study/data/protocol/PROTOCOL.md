# since-cutoff head-to-head benchmark: protocol (DRAFT, not yet tagged)

Status: draft written with the harness on 2026-09-27. It becomes the pre-registration when it is committed and tagged
together with `bench/HASHES.json` (`python -m bench hashes --write`), the frozen notes (`bench/notes/MANIFEST.json`)
and the analysis code, **before the first main-run session**. Any later change is listed under "Deviations" with its
date and reason. Source design: `since-cutoff-0.4/plan.md` section B and the benchmark report `bench.md`.

## 1. Question

On the same tasks, does Claude Code finish correctly more often, or with fewer correction attempts, less time and less
cost, with (A) its usual tools, (B) plus Context7, (C) plus since-cutoff's notes, or (D) both?

## 2. Conditions

| | CLAUDE.md (project root) | `--mcp-config` | extra `--allowedTools` |
|---|---|---|---|
| A | base block | `{"mcpServers":{}}` | – |
| B | base block + Context7 rule | context7 (stdio, `@upstash/context7-mcp` 4.1.1) | `mcp__context7` |
| C | base block + frozen since-cutoff notes | `{"mcpServers":{}}` | – |
| D | base block + rule + notes | context7 | `mcp__context7` |
| E | base block + forced Context7 rule (B-forced, added after the pilot, section 12.z) | context7 | `mcp__context7` |

- Base block: `claude_md/base.md` (pins in `pyproject.toml`, installed in `.venv`, run `pytest -q`, do not install or
  upgrade packages). Every condition has it, so having a CLAUDE.md is controlled for.
- Context7 rule, verbatim (`claude_md/context7_rule.md`): "Always use Context7 when I need library/API documentation,
  code generation, setup or configuration steps without me having to explicitly ask."
- Notes: the since-cutoff block produced by `since-cutoff==0.4.0rc1 sync --model anthropic:claude-opus-5-5
  --target CLAUDE.md` in a scratch copy of each task's `repo/` (the command template is in `bench.toml [notes]`). The
  tool gets no model credentials and never sees `hidden/`, `reference/` or `stale/`. Blocks are stored as
  `notes/<task>.md`, hashed in `notes/MANIFEST.json`, and frozen (`python -m bench notes --freeze`); runs refuse
  unfrozen or changed notes. An empty block is valid (C then equals A for that task) and is reported.
- Composition order is fixed: base, blank line, rule, blank line, notes.
- Results for C apply to 0.4.0 diff notes only, not to `run`-improved notes.

## 3. Agent setup (fixed for every session)

Command (prompt on stdin, cwd = the run's project folder):

```
<claude.exe> -p --model claude-opus-5-5 --effort medium --output-format stream-json --verbose
  --max-turns 40 --max-budget-usd 3 --permission-mode dontAsk
  --tools Bash,Read,Edit,Write,Glob,Grep,TodoWrite,Skill
  --settings <runs>/<study>/_harness/claude_settings.json
  --strict-mcp-config --mcp-config <mcp_none.json | mcp_context7.json | inline JSON, see below>
  [B, D] --allowedTools mcp__context7
  --no-session-persistence
```

- Claude Code version pinned in `bench.toml` (2.1.283); checked before a study starts and against every run's
  `system/init.claude_code_version`.
- `claude_settings.json`: exactly plan B.2 (dontAsk, `blockReadsOutsideWorkingDirectories`, allow Read/Edit/Write/
  Glob/Grep/TodoWrite/Skill and `pytest`/`python` Bash forms; deny WebFetch, WebSearch, pip, uv, curl, wget, npm,
  npx, git push).
- Environment, built from scratch (nothing inherited from the shell): Windows system variables only; `PATH` =
  `<project>\.venv\Scripts` + system folders; `VIRTUAL_ENV`; a fresh `CLAUDE_CONFIG_DIR` per run
  (`C:\b\claude-config\<study>\<run>`); `USERPROFILE`/`HOME`/`APPDATA`/`LOCALAPPDATA` in an empty per-run folder
  (`claude.isolate_home`, so no user settings, plugins, hooks, memory or dotfiles are read); `TEMP`/`TMP` per run;
  `CLAUDE_CODE_OAUTH_TOKEN` copied from the harness environment; `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`,
  `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, `DISABLE_AUTOUPDATER=1`, `ENABLE_TOOL_SEARCH=false`, `MCP_TIMEOUT=60000`,
  `PYTEST_ADDOPTS=--allow-hosts=127.0.0.1,::1`, `CLAUDE_CODE_GIT_BASH_PATH` (the Bash tool on Windows).
  Never present: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_EFFORT_LEVEL`, HTTP(S) proxies,
  `CONTEXT7_API_KEY`.
- Context7: `node.exe <npm root>\@upstash\context7-mcp\dist\index.js --transport stdio`. When `CONTEXT7_API_KEY` is
  set in the harness environment the config is passed as an inline JSON string whose server `env` holds the key,
  so the key reaches only the MCP server: it is not in the claude environment (the agent cannot print it), not in
  any file, and redacted in the recorded argv. Without a key Context7 runs anonymously (rate-limited).
- Projects live in `C:\b\runs\<study>\<run_id>`; the harness refuses to run when a `CLAUDE.md`, `AGENTS.md` or
  `CLAUDE.local.md` exists in any parent folder.
- Each project gets a fresh `.venv` built offline from the locked wheels (section 5).
- Wall-clock limit 900 s per session; on expiry the process tree is killed with `taskkill /PID <pid> /T /F`.

## 4. Tasks

Admission: `python -m bench validate` must pass for the task's current files (`tasks/<key>/VALIDATION.json`, bound to
the task sha256):
1. the unmodified repo fails the hidden tests at the pinned version;
2. `reference/` passes at the pinned version;
3. `stale/` fails at the pinned version;
4. `stale/` passes at the cutoff-era version (`stale_version`, default `cutoff_version`);
for a no-change control gate 3 is inverted to `3_stale_passes_at_pinned` (the cutoff-era solution in `stale/` passes at
the pinned version too), and for a pinned-behind task `stale/` holds the too-new solution and `stale_version` is the
newer release it was written for;
plus declared extra solutions (mcp01 `halfmigrated/` must fail at the pinned version), and the leak check: no answer
token (global list in `bench.toml [leak]` minus the task's `leak_allow`, plus the task's `answer_tokens`) in any
`repo/` file or in the instruction.

Task format (`task.toml`, schema `since-cutoff-bench/task@1`): `id, library, pinned, cutoff_version, [stale_version],
stratum, kind, timeout_s, target_files, instruction, evidence[], stale_patterns[], note_keys[], doc_keys[],
[answer_tokens[]], [leak_allow[]], [extra_requirements[]], [extra_solutions]`. Folders `repo/ hidden/ reference/ stale/`.
`task_sha256` = sha256 over `task.toml`, `repo/`, `hidden/` (CRLF normalised to LF, caches and venvs skipped).

Strata for claude-opus-5-5: post-cutoff (primary endpoint), pre-cutoff-control, no-change-control, pinned-behind.
Admitted after `bench validate` and the independent review of every task and hidden test (2026-09-27, `REVIEW.md`
in the repository root): 24 tasks.
- post-cutoff, the primary endpoint (17): ant01-ant05 (anthropic 1.8.0; cutoff era 0.115.0), oai01-oai03 (openai
  3.19.2; 2.44.0), hf01-hf04 (huggingface-hub 2.0.0; 1.21.0), mcp01, mcp02, mcp04, mcp05, mcp06 (mcp 2.2.0; 1.28.1);
- pre-cutoff controls (5): pd01-pd03 (pandas 3.0.6; `cutoff_version` 3.0.3, gate 4 at `stale_version` 2.3.2) and
  lc01, lc02 (langchain-core 1.6.5; `cutoff_version` 1.4.8, gate 4 at `stale_version` 0.3.86);
- no-change control (1): oai04 (Responses API; gate 3 inverted, see section 12);
- pinned-behind (1): oai05 (oai01 with the project pinned to openai 2.44.0; `stale/` is the 3.x answer and passes at
  3.19.2).
Dropped at the premise check, each published with the reason and a runtime probe in `bench/dropped/<key>/`: ant06
(`messages.parse(stream=True)` never worked at 0.115.0, and `messages.stream(output_format=)` is not new), mcp03 (no
realistic cutoff-era `ctx.info` call passes at 1.28.1 and fails at 2.2.0) and hf05 (huggingface-hub 1.x/2.0 still
accept the removed `hf_hub_download` arguments at run time, with a warning). `bench/candidates/hf05b`
(`list_models(direction=)`) passes the gates but is not in the pre-registered catalogue and is not admitted.
With ant06 and mcp03 dropped, the primary endpoint has 17 tasks (plan B.6 assumed 19): the sign-flip test runs over
2^17 sign patterns and the detectable effect is somewhat larger than the plan's 20-25 points.

Hidden tests stay out of any public repository until the main run is done; only their sha256 (`hidden_sha256` in
`HASHES.json`) is published with this protocol.

## 5. Environments

- Python 3.13.14 (`bench.toml [python].base`); test tooling pytest 8.4.2 and pytest-socket 0.8.1 in every venv.
- One environment per (library, version): `<library>==<version>` + test tooling (+ `extra_requirements`).
- `prepare --download` fetches wheels only (`--only-binary=:all:`) from PyPI into the wheelhouse; each environment is
  then resolved from the wheelhouse alone and frozen in `envlocks/<env_id>.json` with every wheel's sha256. Venvs are
  built with `pip install --no-index --no-deps --require-hashes` from that lock. The lock hashes are part of
  `HASHES.json`.

## 6. Grading and validity

- After the session, the project (without `.venv`, `.git`, caches) is copied into a fresh grade folder, a pristine
  venv is built from the task's pinned lock, and the hidden tests run with
  `pytest -q -p no:cacheprovider --allow-hosts=127.0.0.1,::1` plus harness-owned options
  `-c <grade>/bench_pytest.ini --rootdir <grade>/proj --confcutdir <grade>/proj/_bench_hidden --junitxml ...`, so
  the agent's pytest configuration and `conftest.py` files cannot change the hidden run. Environment: system
  variables only, then every `*KEY*`, `*TOKEN*`, `*SECRET*`, `ANTHROPIC*`, `OPENAI*`, `HF_*`, `CLAUDE*`, `CONTEXT7*`
  name removed, `HTTP(S)_PROXY=http://127.0.0.1:9`, `HOME`/`TEMP` inside the grade folder. Visible tests are also
  run with the project's own configuration and recorded, not scored.
- **A run passes** when every hidden test passes and the pins are unchanged. "Pins changed" (`lock_modified`) = any
  lock/requirements file (`bench.toml [grade].lock_files`) added, removed or changed, or any of `project.dependencies`,
  `project.optional-dependencies`, `project.requires-python`, `dependency-groups`, `build-system`, `tool.uv`,
  `tool.poetry`, `tool.pdm` changed in `pyproject.toml` (or it no longer parses). `venv_modified` (a `pip list` diff of
  the agent's venv) is recorded, not scored.
- Runs that hit `--max-turns`, `--max-budget-usd` or the wall-clock limit are graded as they stand.
- **Invalid (infrastructure) runs** are recorded, never graded, and re-queued up to 3 attempts: `spawn_failed`,
  `no_init_event`, `auth`, `usage_limit`, `api_error`, `api_retry_exhausted`, `api_retry_timeout` (killed while the
  stream ended in an API retry), `mcp_not_connected` (B/D: context7 not `connected` or `mcp_server_errors` present),
  `unexpected_mcp_servers` (A/C), `model_mismatch`, `api_key_billing` (`apiKeySource` not `none`),
  `version_mismatch`, `no_result_event` (crash), `harness_error`. `auth` and `usage_limit` stop the study; it is
  resumed with `run --resume`. A re-queued run goes to the end of the queue (it leaves its block); its record keeps
  its block id and attempt number.
- Every attempt, valid or invalid, is kept in `results/<study>/runs.jsonl` (schema `since-cutoff-bench/run@1`) with
  its `stream.jsonl`, `stderr.log`, `final.diff`, `CLAUDE.md`, `prompt.txt` and `grade.log`.

## 7. Endpoints and analysis (unchanged from plan B.6; code in `stats.py`, `report.py`)

- Unit of analysis: the task. p(t,c) = passes / valid graded runs; the first valid attempt of each planned run counts.
- Primary: Δ(C−A) = mean over post-cutoff tasks of p(t,C) − p(t,A); 95% CI by task-cluster bootstrap (10,000
  resamples, percentile, seed `bench.toml [analysis].bootstrap_seed`); p by exact sign-flip permutation over all 2^n
  sign patterns (two-sided).
- Secondary contrasts D−B, B−A, D−C; Holm across the four (primary included). C−B is reported for claim 3 only.
- Headline counts: exact McNemar on each task's majority outcome (≥ 2 of 3 passes): "fixed N tasks, broke M".
- Cost, total tokens, output tokens, turns, wall time: per-task medians; geometric-mean paired ratios with task-bootstrap
  CIs; cost per solved task = total cost / total passes (failed runs' cost counts).
- `pytest_runs`, `failing_pytest_runs`, `edits_after_first_failure`: exact Wilcoxon signed-rank on per-task medians
  (zeros dropped, average ranks for ties); ratios use a +1 offset because counts can be 0.
- Controls: non-inferiority, one-sided 95% lower bound (bootstrap) of Δ(C−A) ≥ −10 points.
- Flakiness: share of tasks with mixed outcomes across reps, per condition.
- Robustness: logistic GLMM `y ~ condition + (1|task)` fitted outside the harness (lme4 or statsmodels) from
  `runs.csv`; the harness is standard-library only.
- Process metrics from the stream (`transcript.py`): `pytest_runs` (Bash commands matching `\bpytest\b`, denied calls
  excluded), `failing_pytest_runs` (non-zero exit, or "N failed"/"N error(s)" in the output), `py_edits`,
  `edits_after_first_failure`, `stale_in_first_edit` (stale patterns on the first Edit/Write of a target file; `None`
  when never edited), `stale_in_final` (on the added lines of the final diff, CLAUDE.md excluded), `site_packages_reads`
  (Read/Grep/Glob on `.venv`/`site-packages`), `introspection_cmds`, `context7_calls`, `doc_hit` (all `doc_keys`
  found in the Context7 results), `skills`, `network_like_cmds`, `api_retries`. Stale patterns ignore Python comments.
- Pilot runs (`plan --pilot`: ant01 and mcp01 × 4 × 2) are excluded from every analysis.

## 8. Decision rules (plan B.8, applied automatically in report section (h))

| claim | evidence required |
|---|---|
| notes reduce stale-API failures on post-cutoff changes | Δ(C−A) CI lower bound > 0, Holm p < .05, and a lower `stale_in_first_edit` rate in C |
| notes add value on top of documentation access | Δ(D−B) CI lower bound > 0 |
| notes are cheaper than documentation lookups for the same success | Δ(C−B) CI within ±10 points and C/B cost-ratio CI upper bound < 1 |
| notes and Context7 complement each other | D ≥ max(B, C) on pass rate and D/B cost ratio ≤ 1 |
| notes don't hurt | non-inferiority on the controls (incl. no-change and pinned-behind tasks) |
| notes are cheaper than documentation that is looked up (E, added in 12.z before the main run) | Δ(C−E) CI within ±10 points and C/E cost-ratio CI upper bound < 1 |
| notes reduce correction attempts / time / cost | a C/A ratio CI (failing pytest runs, turns, wall time or cost) entirely below 1 |

- Ceiling: if A passes ≥ 90% of post-cutoff tasks, no pass-rate claim (the first four rows); cost, turns and
  correction attempts only.
- Low Context7 use (B call rate < 80%): a C-vs-B result compares notes with an unused tool; only a B-forced arm speaks
  to Context7's content.
- Per-task coverage decides the wording ("static-diff notes help with removed or renamed APIs" if C wins only where
  the notes covered the change).
- Anything that meets no rule is published as inconclusive.

## 9. Go / no-go after the pilot

Context7 connected in 100% of B/D pilot runs (else fix infrastructure first); B's Context7 call rate below 80% → add the
B-forced arm; median cost above about $1.5 or time above 8 minutes per session → 2 reps, stated here before the main
run; A passes every pilot run → expect the ceiling rule.

## 10. Operating procedure

```
python -m bench validate                                  # four gates + leak check for every task
python -m bench prepare --download [--install-context7]   # offline preflight (no model call)
#   the maintainer sets CLAUDE_CODE_OAUTH_TOKEN (claude setup-token) and CONTEXT7_API_KEY in the shell
python -m bench prepare --allow-calls                     # + the 6 model-call checks (about 6 short sessions)
python -m bench notes --tool since-cutoff==0.4.0rc1 --freeze
python -m bench hashes --write                            # then commit and tag: protocol, hashes, notes, code
python -m bench plan --pilot --study-id pilot-<date> --seed <N>
python -m bench run pilot-<date> --workers 2 && python -m bench report pilot-<date>
python -m bench plan --study-id main-<date> --seed <N>    # seed fixed and written here before the run
python -m bench run main-<date> --workers 3 [--resume] [--max-sessions N]
python -m bench grade main-<date>                          # only for runs made with --no-grade, or --regrade
python -m bench report main-<date>
```

Seeds: pilot `20260928`, main `20260929` (fixed 2026-09-28, after the pilot and before the main plan was written).

## 11. Known gaps

- The Claude Code sandbox does not run on native Windows: the agent's `python -c` could open sockets. Mitigated by
  the deny rules, `PYTEST_ADDOPTS=--allow-hosts`, the transcript scan (`network_like_cmds`) and grading in a pristine,
  offline venv. WSL2 with the sandbox is the stronger option.
- The anthropic tasks start with first-party documentation in every condition (bundled `/claude-api` skill); that
  stratum is reported separately and `Skill` calls are logged.
- Context7 serves default-branch documentation for these libraries (no version tags).
- `tokens_est` for notes is characters / 4.

## 12. Deviations from plan B (decided while building the harness, before any session)

- Grading adds harness-owned pytest options (`-c`, `--rootdir`, `--confcutdir`, `--junitxml`) to the plan's command so
  the agent cannot alter the hidden run through its own pytest config or `conftest.py`.
- `HOME`/`USERPROFILE`/`APPDATA` point to an empty per-run folder, and `CLAUDE_CONFIG_DIR` is per run
  (`C:\b\claude-config\<study>\<run>`), not one shared folder. Preflight check 2 confirms Claude Code runs this way;
  if it does not, set `claude.isolate_home = false` and record it here.
- `CONTEXT7_API_KEY` is passed inline in `--mcp-config` (not through the claude environment), so preflight check 3
  (no secret variables in the agent's subprocesses) holds in B and D too.
- pd01 carries `cutoff_version = 3.0.3` (Opus 5.5) and `stale_version = 2.3.2` (gate 4), stratum pre-cutoff-control.
- pd02, pd03, lc01 and lc02 (pre-cutoff controls, validated 2026-09-27) use the same versions as pd01 for pandas
  (3.0.3 is the cutoff version because 3.0.4 is yanked). For langchain-core the pin is 1.6.5, `cutoff_version` is 1.4.8
  (the highest final release on or before 2026-06-30), and `stale_version` is 0.3.86. That is the last 0.3.x release
  before the cutoff, and the removed methods are still there, deprecated. Each repo also has a `requirements.txt`
  (its non-target module that used the old API was removed in the review, see below). The langchain
  `requirements.txt` pins only the
  direct dependency, because the full dependency set includes `httpx2` (via langsmith 0.14.1), which is a global
  answer token.
- Gates by stratum (`bench/validate.py` `gates_for`). A no-change control has nothing stale, so plan B.4's gate 3
  ("stale fails at pinned") cannot apply: for oai04 it is inverted to `3_stale_passes_at_pinned` (a cutoff-era
  solution passes at both 2.44.0 and 3.19.2), which is the evidence that nothing the task needs changed. For the
  pinned-behind task (oai05) the gates are unchanged, but `stale/` is the too-new 3.x solution and `stale_version` is
  3.19.2; its `stale_patterns` flag 3.x code and its `doc_keys` flag documentation of the pinned 2.x API.
- oai02's instruction says the fix stays in `tests/fakes.py` and the pytest configuration is not changed. respx
  registers a pytest plugin that imports `httpx` at start-up, so `httpx2.alias_httpx()` only works with `-p no:respx`,
  and the grader ignores the project's pytest configuration; without that sentence such a fix would pass locally and
  fail grading.
- hf01's instruction: the prototype's TOML basic string turned `("\n\n")` into two real line breaks; the task now
  shows the literal `"\n\n"` as the benchmark report intended. No agent had run on the prototype.
- Wall-clock timeouts are valid runs (graded as they stand) unless the stream ended in an API retry.
- `leak_allow` (task.toml, `bench/tasks.py`): a task may exempt global answer tokens that are not its answer and that
  its repo must contain. Only mcp04 uses it (`MCPServer`, `mcpserver`): its repo is a server already on mcp 2.x, which
  cannot be written without the 2.x class name (mcp01's answer, protected by mcp01's own `answer_tokens`). A task's own
  `answer_tokens` always apply, and a token may not be both allowed and an answer token (schema error).
- mcp04 and mcp05 hidden tests use loopback sockets: mcp04 runs `serve_http()` in a daemon thread on a free 127.0.0.1
  port, and mcp05 runs the SDK's Streamable HTTP app under uvicorn inside the test's event loop. Both remove the
  grader's dead `HTTP(S)_PROXY` and set `NO_PROXY=127.0.0.1,localhost,::1` for the test only (monkeypatch), so the
  SDK's default httpx2 client reaches 127.0.0.1 directly. pytest-socket's `--allow-hosts=127.0.0.1,::1` still blocks
  every other host.
- mcp repos' existing library use is working 1.x-style code that still runs at 2.2.0 (`stdio_client` +
  `ClientSession` + `initialize()`, checked against a real 2.2.0 stdio server), not code that uses the changed API.
- Review (2026-09-27, by someone other than the task authors, as plan B.4 requires; details in `REVIEW.md`):
  - Existing library use in `repo/` is working code at the pinned version. Seven repos (hf02, hf03, hf04, pd02, pd03,
    lc01, lc02) had a non-target module that used the old API and was broken at the pinned version (a lure). They
    were removed (lc02's `translate.py` was rewritten to working `chat.batch(...)` use): in a post-cutoff task such a
    module shows the agent the stale answer and is exactly what used-scope notes flag, which favours C; it is not
    what bench.md 3.3 describes ("a working `summarize()`"); and the other 17 repos had none. The removed files are
    kept in `review/removed_lures/`; `tests/test_tasks_conditions.py::test_repos_hold_no_old_api_lure` enforces the
    rule.
  - The six prototypes and oai05 gained one small module of working library use (plan B.4: "each repo contains
    realistic existing use of the library"), so used-scope notes can see the changed API where a static diff can:
    ant01 `app/summaries.py` (`messages.create` without sampling parameters, bench.md 3.3's example), hf01
    `app/titles.py` (`text_generation` without a stop sequence), ant02 `app/assistant.py`, oai01 and oai05
    `app/search.py` (identical, so the pair stays matched), pd01 `app/load.py`, mcp01 `app/smoke.py` (a stdio client
    that lists the server's tools). Hidden tests do not import them. mcp01 still has no use of the renamed server
    class, which cannot be written at 2.2.0 without giving the answer.
  - hf01's hidden test counted TGI requests with a handler that crashed (JSONDecodeError, swallowed by
    huggingface_hub) on the hub's own `GET https://huggingface.co/api/agent-harnesses`; it now answers requests to
    other hosts with 404 and records only the TGI host. Same assertions, no longer dependent on that crash.
  - ant03's instruction now says the answer must not go through a tool call: strict tool use is also "structured
    outputs" in Anthropic's documentation, and the hidden test checks the JSON-output format.
  - Nine tasks declare the reviewer's alternative correct answer as `alt_review = "pass"` in `[extra_solutions]`
    (ant02, ant04, hf01, hf02, hf04, oai01, oai03, oai05, pd01), so `bench validate` keeps checking that the hidden
    tests accept an approach other than the reference's.

### 12.x Findings from the first model-call preflight (2026-09-28, Claude Code 2.1.283)

- **Inline Python is refused in every condition.** With `blockReadsOutsideWorkingDirectories`
  on, a `python -c "..."` command cannot be analysed by the permission system and is denied
  (`-p` mode cannot ask). Scripts (`python file.py`) and `pytest` run normally. All four
  conditions share this restriction; transcripts record such denials in `permission_denials`.
- **`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` forces the permission mode to `default`** (the CLI
  prints "Permission mode forced to default"). In headless mode this behaves like `dontAsk`
  for everything the settings allow-list names, which is every tool the runs use; anything
  else is denied without a prompt. The recorded argv keeps `--permission-mode dontAsk`.
- **Login mode.** Runs use the maintainer's normal Claude Code login (`apiKeySource=none`,
  model `claude-opus-5-5` confirmed) with `--setting-sources project`, so user settings,
  hooks and plugins are not loaded; the maintainer's config had no user CLAUDE.md, no hooks
  and no enabled plugins at the time (recorded in `bench prepare`).
- **Probe design.** The env probe runs `python envcheck.py` (a script written into the probe
  project) rather than `python -c`; the permissions probe runs in a project without the base
  CLAUDE.md block, because an agent that obeys "do not install packages" never exercises the
  `pip` deny rule.

### 12.y Pilot notes (2026-09-28)

The pilot (excluded from every analysis, section 8) uses notes from since-cutoff 0.4.0 with
`sync --yes --scope imported`, frozen before the pilot. With the default `used` scope, 0.4.0
wrote notes covering 4 of the 17 post-cutoff tasks, because the task repositories contain
working uses of each library but none of the changed APIs (by design, section 4); with
`--scope imported`, 5 of 17. The notes are ranked by a rule that put `ClientSession`
parameter removals ahead of the `mcp.server.fastmcp` package move and the `FastMCP` rename,
so mcp01's notes do not cover its change. since-cutoff 0.4.1 changes that ranking; the main
run's notes will be generated with the released 0.4.1 and frozen before the main run, with
the scope recorded here then. The pilot measures cost, time, turns, Context7 use and
infrastructure failures, and checks the go/no-go rules of section 9.

### 12.z Pilot outcome and decisions (2026-09-28, before the main run)

`python -m bench report pilot-2026-09-28` (the report now describes a pilot study on its own
and prints the section 9 table): 16 sessions, 16 valid, no timeouts, no lockfile or venv
changes.

| section 9 rule | pilot value | fires |
|---|---|---|
| Context7 connected in 100% of B/D runs | 8/8 | no |
| B's Context7 call rate below 80% | 2/4 (mcp01 2/2, ant01 0/2) | **yes** |
| median cost per session above $1.5 | $0.26 | no |
| median time per session above 8 minutes | 54 s | no |
| A passes every pilot run | 2/4 | no |

Decisions:

1. **B-forced arm E.** The call-rate rule fired, so the main run adds condition E: the same
   MCP config and allow rule as B, with the Context7 rule replaced by
   `claude_md/context7_forced_rule.md`, verbatim: "Before you write or change code that calls
   a third-party library, look up that library's API with Context7: call
   `resolve-library-id` for the library, then `query-docs` for the classes, functions and
   parameters you are going to use. Do this even when you think you know the API." B keeps
   Context7's own recommended rule. The pre-registered contrasts and their Holm family are
   unchanged; C−E, E−B and C−B are reported as extra, unadjusted contrasts, and the claim
   row added to section 8 uses C−E.
2. **Reps stay at 3.** Cost and time are far below the section 9 limits. The main run is
   24 tasks × 5 conditions × 3 reps = 360 sessions, run in batches (`--max-sessions`).
3. **A tool change made after seeing a pilot task.** In ant01 (anthropic 1.8.0 removed
   `temperature`, `top_k` and `top_p` from `Messages.create()`; the task needs temperature
   0), the 0.4.0 note said "`Messages.create()` no longer accepts `temperature`, `top_k` or
   `top_p`; do not pass them." Every C and D run followed it: no stale code (stale first
   edit 0/4 vs 2/4 in A and B) and no temperature at all, so the hidden test failed (C 0/2,
   D 0/2; A 0/2, B 1/2). "do not pass them" is advice the diff does not support: the
   parameters left the signature, the request field did not necessarily go away, and the
   pinned `create()` has an `extra_body` argument for request fields that are not
   parameters. since-cutoff 0.4.1 states the removal without that advice and, where the
   pinned signature has `extra_body`, says so; the rule is generic (any method with an
   `extra_body` parameter, as in every Stainless-generated SDK: anthropic, openai and
   others), not written for ant01. Because the change was made after seeing ant01's pilot
   runs, ant01 and mcp01 are **pilot-exposed**: the main report is published twice, with all
   tasks and with `--exclude-tasks ant01,mcp01`, and a claim is reported as supported only
   if it holds in both.
4. **mcp01 is at the ceiling in the pilot** (8/8 in every condition, including A, which
   reads the installed package's source). It stays in the task set; per-task results show it.

Pilot observations that are descriptive only (two tasks, excluded from every analysis):
C/A cost ratio 0.51 [0.32, 0.81] and total tokens 0.52; ant01 cost per session was A
$0.51–0.53, B $0.48–0.61, C $0.16–0.17 and D $0.10–0.18 (the reason is not analysed here).

### 12.w Main-run notes (frozen 2026-09-28, before the main plan)

Generated with the released `since-cutoff==0.4.1` (PyPI), `sync --yes --scope imported` with
the default budget of 5 APIs per package, model `anthropic:claude-opus-5-5`, target
`CLAUDE.md` (`bench.toml [notes]`); frozen, manifest sha256 `f7e0b28399773c60…`. Scope
decision: `imported`, because every task repository uses its library but, by design
(section 4), none of the changed APIs, so the default `used` scope writes notes for few
tasks; `imported` is what a user starting new work against a pinned package would run. The
tool's defaults are used as shipped and were not tuned to the tasks.

Coverage (every `note_keys` regex matches the frozen notes), post-cutoff stratum: 5 of 17 -
ant01, ant03, hf01, hf02, hf03. Partly matched: mcp01 (`FastMCP|MCPServer`, not
`ToolError`). Not covered: ant02, ant04, ant05, hf04, mcp02, mcp04, mcp05, mcp06, oai01,
oai02, oai03; the httpx → httpx2 dependency switch (ant04, hf04, oai01–03) is not a change
to the package's own public API, so a static diff of that API does not report it. mcp05's
five slots go to `ClientSession` changes because its code uses `ClientSession` (APIs the
project uses rank first), which leaves `streamablehttp_client` sixth. Empty blocks: oai05,
pd01–pd03 (no API change after the cutoff), so C equals A there. The report's per-task
coverage column carries this into the wording rule of section 8.

### 12.v Noted during the main run (infrastructure only; no outcome was looked at to decide it)

- Batch 1 (60 sessions): 60 valid, no timeouts, no API retries, Context7 connected in every
  B/D/E run with 0 errors, E called Context7 in 12 of 12 runs. Three runs of mcp04 (B, D, E)
  flagged `network_like_cmds`: each started its own server and probed `127.0.0.1:8765`; no
  host other than localhost was contacted. Runs of the same task can overlap across the 3
  workers, so an agent's own self-check could reach another run's local server on the same
  port. Grading is unaffected (hidden tests run afterwards in their own venv, and orphaned
  processes are killed at the end of each session; none were left on 8765 after the batch);
  the confound is limited to what an agent sees while checking its work, and is reported as
  a known gap rather than changed mid-run.

### 12.u Credential isolation fixed during the main run (2026-09-28, after 181 sessions)

The secret scan run on the artifacts before publication (`python -m bench.secretscan`) found the
maintainer's saved Hugging Face token in two hf04 transcripts (B r3, D r1). Cause: the claude
process received `HF_HOME` (per-run folder) and `HF_HUB_DISABLE_IMPLICIT_TOKEN=1`, but the
commands its Bash tool starts did not, so huggingface_hub 2.0 in an agent's own check script read
`~/.cache/huggingface/token` and attached it to a request sent to an in-memory `MockTransport`;
the script printed the request headers. No request left the machine in those two scripts, and
grading was not affected (it runs outside the agent with its own isolated environment). The
first 181 sessions include 40 on hf tasks during which the token was readable by the agent's
Python processes.

Changes, made before any further session: the run was stopped; every per-run venv now gets
`_hf_isolation.pth` (bench/envs.py `isolate_python`), which sets `HF_HOME`, `HF_TOKEN_PATH`,
`HF_STORED_TOKENS_PATH` and `HF_HUB_DISABLE_IMPLICIT_TOKEN` and drops `HF_TOKEN` at interpreter
start-up for every python and pytest launched from the venv, whatever environment the shell
passes (verified on the hf04 venv: without the file the token is found, with it none is; `pip
list` is unchanged, so `venv_modified` is unaffected); records made after this carry
`python_isolation`. The two transcripts were redacted in place (`<REDACTED:hf-token>`), a rescan
finds nothing, and the maintainer was asked to revoke the token. The report lists the hf-task
runs made before and after the change.

### 12.t Post-run notes (written after the main run, 2026-09-28; nothing here changes the frozen rules)

- **Context7 monthly quota.** All B/D/E sessions ran Context7 without an API key. From the
  session that started at 2026-09-28T06:25:53Z (the 215th of 360 by start time) every Context7
  call returned "Monthly quota exceeded" instead of documentation. The harness counted these as
  successful tool calls (they are not tool errors), so `context7_errors` stayed 0 and the
  between-batch checks did not catch it; it was found in the transcripts while the results page
  was written. Documentation actually received: B 14 of the 23 sessions that called Context7
  (post-cutoff 9), D 8 of 13 (post-cutoff 1), E 42 of 72 (post-cutoff 34 of 51). The
  pre-registered notes-vs-agent-alone contrasts (C-A, the efficiency claim, the controls) do not
  involve Context7 and are unaffected. Comparisons with B, D and E understate what Context7 can
  do; E especially. Exploratory, not pre-registered: on the 34 post-cutoff blocks where E
  received documentation, C and E both passed 34 of 34; session-level C/E ratios (bootstrap over
  sessions, seed 20261001): turns 0.79 [0.71, 0.89], cost 0.86 [0.69, 1.04], wall time 0.81.
  A re-run of the affected B/D/E sessions with a Context7 key is the clean fix and would be
  reported as a separate, labelled study.
- **Protocol header.** The first line of this file still says "DRAFT, not yet tagged"; the
  frozen version is the one at tag `main-freeze-2026-09-28` (created before the first main
  session), and the tag is unsigned and was local until publication.
- **Authentication as run.** Sessions used the maintainer's normal Claude Code login with the
  real user folder (`auth = "login"`, `isolate_home = false`, recorded in 12.x), not the token and
  per-run home described in section 3; this is how the saved Hugging Face token was readable
  (12.u).
- **12.u follow-up.** The hf-task sessions before and after the credential fix: 40 before (the
  first 181 sessions, harness 9227ebaf60e2) and 20 after (179 sessions, harness 90165f07c60f);
  all 60 passed.
- **Section 7 robustness check.** The mixed-model (GLMM) check was not run; with the pass-rate
  ceiling met it would not change any claim.
