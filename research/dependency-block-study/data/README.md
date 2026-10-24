# Data of the dependency-block study

Everything here is aggregated or de-identified. Paths below are relative to `research/dependency-block-study`; the
scripts are in `../scripts`. See `../README.md` for the findings and the main commands.

## Contents

- `protocol/`: the frozen pre-registration of the main study (`PROTOCOL.md`); the addendum (`PROTOCOL_ADDENDUM.md`)
  for the Sonnet 5.5, Haiku 5.5, Opus replication and new-task studies (sections 1 to 8; section 8 registers the new
  tasks), the open-weight agent (section 9: downloads and setup; section 10: Qwen3-Coder-30B-A3B in mini-swe-agent,
  A vs C on all 35 tasks; 10.1: GPU pilot record; 10a: header-only arm H on the 17 original post-cutoff tasks), the
  four follow-up studies (sections 11 and 12: the irrelevant-content control R, the older-cutoff model, the
  real-repository case study and the later tool version C2), the concurrent five-arm study (section 13: A, C, H, R and
  the generic instruction G in the same batches) and section 14 (a lockfile-only header L with A, C and H, and an
  optional wrong-block arm W; 14.1: an aborted first launch and a harness fix; 14.2: the W design); the review of the
  11 new tasks (`REVIEW_tasks2.md`); the protocols of the detector-recall study (`RECALL_PROTOCOL.md`), the random
  exposure sample (`EXPOSURE2_PROTOCOL.md`) and the agent-session estimate of f (`F_PROTOCOL.md`); and the tag and
  first-session time of every study (`PREREGISTRATION_TIMES.md`).
  - Section 14 was registered but not run: its first launch failed before any session reached the model because the
    Claude CLI login had expired, so the report has no L or W result. Its frozen blocks (`notes/*-lockfile`,
    `notes/tasks2-opus-5-5-wrong`), driver (`scripts/lockhdr_driver.sh`) and analysis script
    (`scripts/lockhdr_analysis.py`) are included so the registration can be checked.
  - Section 15 registered a second open-weight study (the same model and tasks with a fixed adapter, and arms A, C,
    H, L and a decoy header). It was started and stopped before completion; its partial runs are not analysed, and its
    protocol section, blocks, runs and scripts are not in this folder.
- `configs/`: harness configuration of the main study (`bench.toml`), the per-study configs of the addendum, the base
  CLAUDE.md, the Context7 rules and the agent settings.
- `tasks/`: the 24 original task definitions (instruction, pinned and cutoff-era versions, stale-API patterns, note
  coverage keys). Their repositories, reference solutions and hidden tests are in the public benchmark repository,
  https://github.com/MohammadHijjawi97/since-cutoff-benchmark.
- `tasks2/`: the 11 new task definitions (polars, streamlit, mistralai) with their validation records (four gates and
  the leak check). Their repositories, reference solutions and hidden tests are not published, so that the tasks stay
  unseen.
- `case/`: the two case-study task definitions (a subset of a public repository) with their validation records. The
  repository subset, reference solutions and hidden tests are not published.
- `notes/`: every frozen block given to an agent (`opus-5-5` = main study and replication; `sonnet-5-5`, `haiku-5-5`;
  `tasks2-opus-5-5` = new tasks; `*-header` = the header-only control H; `tasks2-opus-5-5-irrelevant` = R;
  `tasks2-opus-5-5-generic` = the generic instruction G; `tasks2-opus-5-5-v2` = C2; `sonnet45-*` = notes anchored to
  the older model's cutoff; `case-opus-5-5` = case study; `qwen3c-main`, `qwen3c-tasks2` and `qwen3c-main-header` = the
  open-weight agent's notes for its 2025-04 cutoff and their header-only variant; `opus-5-5-lockfile`,
  `tasks2-opus-5-5-lockfile` and `tasks2-opus-5-5-wrong` = arms L and W of section 14, frozen but never given to an
  agent, W containing one deliberately false line per task) with their manifests.
- `runs/`: de-identified per-run tables of the eleven completed studies (`runs.jsonl` with the fields the scripts read;
  `runs.csv` with one readable row per attempt: task, condition, repetition, validity, pass, tokens by type, turns,
  wall time, stale-edit flags, exploration counts, start time). No prompts, transcripts or paths. The three
  `runs/openagent-qwen3c-*` folders also hold one slim `runs/<run_id>/record.json` per session (the layout
  `openagent_analyze.py` reads). `runs/pilot-2026-09-28` is the main study's pilot, excluded from every analysis
  except the pilot row of `token_breakdown.json`.
- `recall/`: the 154-item ground truth of the detector-recall study with sources and verification evidence
  (`gt/*.json`, built and checked by Claude Opus 5.5 sessions, no human review), the item-level match overrides
  (`adjudication.json`), the precision verdicts (`precision_manual.json`, AI-judged) and the list of changelogs read
  (`sources/SOURCES.tsv`; the texts themselves are not redistributed).
- `analysis/`: every aggregated result the report uses. The main files:
  - ratios with bootstrap CIs per study (`main_ratios_recomputed.json`, `opus_abl_ratios*.json`, `sonnet_ratios*.json`,
    `haiku_ratios*.json`, `tasks2_ratios*.json`, `pooled_*.json`), stale-edit tests (`*_stale_*.json`), the concurrent
    study (`conc_ablation*.json`), the follow-ups (`addendum5_*.json`, `iter_C2.json`) and the open-weight agent
    (`openagent_qwen3c_*.json`);
  - Table 1's raw and Holm-adjusted p values (`round22_holm.json`, `round22_holm_out.txt`) and its other numbers
    (`round5_table1.json`);
  - token types, turns decomposition and cost per solved task (`token_breakdown.json`), per-task ratios
    (`per_task_ratios.json`), exact tests (`round3_stats.json`), header-only analyses (`round6_header.json`,
    `round7_checks.json`), the post hoc coverage split and equivalence tests (`round15_coverage.json`), the analysis
    without the anthropic-SDK tasks (`robust_no_anthropic.json`), exploration counts (`exploration_mechanism.json`) and
    the Context7 counts (`context7_received.json`);
  - the break-even analyses: block sizes and break-even shares (`blocksize_breakeven.json`, `exposure2_breakeven.json`),
    the two-parameter break-even at benchmark length (`breakeven2d.json`), the header-alone break-even, size cap and
    fleet example (`round13_numbers.json`, `round9_numbers.json`), the per-context cost (`context_cost_out.txt`), the
    benchmark's CLI turns against model calls (`turns_vs_calls_out.txt`), every benchmark-length number in model calls
    (`unit_switch_check_out.txt`; the report uses its V1 rows), the unified-unit bootstrap of the net saving with K
    measured in the agent contexts (`breakeven_unified.json`, `breakeven_unified_out.txt`) and the figure data at the
    contexts' length (`breakeven2d_contexts.json`). In `matched_base_out.txt`, the rows "u needed" divide a
    per-context cost by the benchmark's K; they are superseded by `breakeven_unified_out.txt`;
  - the agent-session estimate of f (`f_sessions.json`; aggregates only);
  - detector recall and precision (`recall_eval.json`), the random exposure sample (`exposure2.json`), the earlier
    exposure scan (`realworld_summary.json`), its AI-assisted audit (`realworld_audit.csv`, one row per matched API
    with verdict and reason, not re-checked by a human; `realworld_audit_summary.json`) and the static-vs-probe
    correlation (`static_vs_probe.json`).
  - `_smoke_lockhdr.json` is not a result: it is a pipeline test of `lockhdr_analysis.py` run before section 14 on
    earlier studies with arms relabelled; no L or W session exists.

## What cannot be re-run from this folder

- The agent-session estimate of f, the per-context cost and the unified-unit bootstrap read the author's private
  Claude Code transcripts (`scripts/fsessions/fsess.py`, `scripts/context_cost.py`, `scripts/breakeven_unified.py`).
  Only their aggregate outputs are published.
- `scripts/turns_vs_calls.py`, `scripts/unit_switch_check.py` and `scripts/matched_base.py` also read the benchmark
  sessions' stream logs; those of the main study are in the benchmark repository, the later studies' are not
  published.
- The exposure scripts need the raw scans, which name repositories and are not included; their aggregated outputs and
  the first audit file are.
- The open-weight agent's run scripts and the detector runs need the benchmark harness, the task repositories, the
  released wheels and a local GPU; they document the setup.

## Notes on this copy

- Several addendum sections and script docstrings say that a study or analysis was motivated by an internal review
  of a draft. These were AI-assisted reviews and are not published; in this copy their file names were replaced by
  "an internal review". The working protocols call the single human author "the user"; this copy says "the author".
  No design, hypothesis or decision rule was changed.
- Personal folders were rewritten to relative names (for example `since_cutoff_runs/...` for the local run results
  and `research/dependency-block-study` for the study folder), one private project name reads `<project>` and one
  private folder `<research folder>`; a folder named after a flattened local path now reads
  `since-cutoff==0.5.0@3f0144f`. Em dashes in the protocols and in two ground-truth quotes were replaced by hyphens.
- Outside `protocol/`, the conference wording of the working files ("NAACL addendum") reads "addendum", and the
  private name of the study folder ("I1") reads `<study>` or "the study folder" (in code, the variable `STUDY`). Git
  tag and branch names such as `naacl-addendum-prereg-2026-10-21` are kept as they are, so they can be looked up.
- The files in `protocol/` were fixed (and some hashed) before the studies, so they keep their original wording,
  including the conference name, the folder name "I1" and phrases such as "the paper sprint". Only personal paths,
  internal-review file names and em dashes were changed, so a copy no longer hashes to its recorded value (for
  example the sha256 of `F_PROTOCOL.md` in `analysis/f_sessions.json`). A path that was only a private folder
  name reads as that name (for example `ai-research` in `F_PROTOCOL.md`).
- Scripts that take the study folder as an argument run on `data`, which has the same `analysis/` and `runs/`
  layout; `round22_holm.py` writes its text output to `analysis/`, and the scripts that cannot be re-run from here
  write theirs next to the script.
- List prices ($ per million tokens: input, output, cache read, 1-hour cache write) used for every cost: Opus 5.5
  4 / 20 / 0.20 / 8; Sonnet 5.5 2 / 10 / 0.10 / 4; Sonnet 4.5 3 / 15 / 0.30 / 6; Haiku 5.5 0.10 / 0.50 / 0.01 / 0.20
  (tier for prompts up to 100k tokens; no logged prompt exceeded 70k). Checked against
  https://platform.claude.com/docs/en/about-claude/pricing on 2026-10-24. The addendum's price table gave 0.20 for
  Sonnet 5.5 cache reads; the outputs use the list price, 0.10.
