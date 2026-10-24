# Recall and precision of the breaking-change detector against documented changes (offline)

Written 2026-10-23 ~19:25 UTC, **before any detector was run on the version pairs below and before the ground truth was
built**. At writing time the only tool output seen for these pairs is what the paper and `RESULTS_FOR_PAPER.md` already
report (the frozen blocks' task coverage, 7 of 25 tasks; one frozen anthropic block read while locating the notes
files). Requested in an internal review: "The breaking-change detector
has no recall evaluation"; "How does the detector compare with `griffe check` on the same release pairs?"; "What
fraction ... would the five-line cap drop?". No model sessions, no GPU, no paper edits.

## 1. Questions

- **R1 (detector recall).** Of the breaking or behavioural public-API changes that the libraries' own changelogs,
  release notes and migration guides document between the cutoff-era release and the pinned release, what share does
  each tool report?
- **R2 (recall by change type).** Removal, rename/move, signature, default change, behaviour-only, dependency switch.
- **R3 (precision).** Of the changes each tool reports, what share is real (and what share is breaking for code
  written against the old release)?
- **R4 (the cap).** What does `--scope imported --per-package 5` (the setting of every benchmark block) do to the
  recall of what actually reaches the notes, compared with the uncapped detector and with `--per-package 10`?

All analyses are descriptive; the one paired test (section 7) is exploratory.

## 2. Version pairs (verified from the task files)

The seven libraries with post-cutoff tasks (`bench/tasks/*/task.toml` on branch `naacl-addendum`,
`since_cutoff_tasks2\*/task.toml`), cutoff-era release -> pinned release:

| library | cutoff-era | pinned | tasks |
|---|---|---|---|
| anthropic | 0.115.0 | 1.8.0 | ant01-05 |
| openai | 2.44.0 | 3.19.2 | oai01-03 |
| huggingface-hub | 1.21.0 | 2.0.0 | hf01-04 |
| mcp | 1.28.1 | 2.2.0 | mcp01, 02, 04, 05, 06 |
| polars | 1.42.1 | 2.0.0 | pl01-04 |
| streamlit | 1.58.0 | 1.66.1 | st01-02 |
| mistralai | 2.5.0 | 3.3.0 | mi01-02 |

(pydantic-ai is not in the benchmark. Controls -- langchain-core, pandas, the oai04/oai05 controls and pl90/91/st90 --
are out of scope.) Wheels: `C:\b\wheelhouse` (the benchmark's wheelhouse; same files the tasks were validated on).

## 3. Ground truth (GT)

**Sources (official only), fetched 2026-10-23 and archived with sha256 under `expansion/recall/sources/`:**
GitHub release notes of every non-pre-release in (cutoff-era, pinned] (GitHub REST API, `repos/<org>/<repo>/releases`);
`CHANGELOG.md` (anthropic, openai); migration guides: anthropic `MIGRATION.md`, openai `httpx2.md`, mcp
`docs/migration.md`, polars `docs/source/releases/upgrade/2.md`, mistralai `MIGRATION.md` (v2 -> v3 part);
streamlit's documentation release notes (`streamlit/docs` `content/develop/quick-references/release-notes/2026.md`,
versions 1.59-1.66.1). Every GT item records its source URL (release page or file URL with anchor).

**Eligible item.** A documented change within the range that (a) is labelled breaking, a removal, a rename/move, "no
longer", a changed default or a changed behaviour (or appears in a migration guide's v-next section), and (b) concerns
the package's public **Python** API: an importable module/class/function/method/attribute/field, a parameter, a
default, a return type or runtime behaviour of such an object, or a dependency whose types or exceptions reach user
code (e.g. httpx -> httpx2). Excluded: additions, pure deprecations that still work at the pinned version, Python-
version drops, CLI-only or REST/server-only changes with no Python API effect, docs, internal refactors, bug fixes
that only restore documented behaviour, and statements naming no specific API element ("removed deprecated APIs").
Excluded candidates are counted by reason.

**Unit.** One item per API element (module/class/function/method/attribute). Several parameters of the same callable
changed in the same way form one item (detected if a tool reports at least one of them; partial vs full recorded);
distinct objects in one changelog line are separate items. Sync/async twins of the same method count as one item.

**Change type (one per item, the first that applies):** *dependency switch* (a dependency replaced, visible in user
code); *rename/move* (object reachable under a new name or path, old one gone); *removal* (object gone without a
same-object successor); *signature* (parameter removed/renamed/now required/keyword-only, accepted type narrowed,
property -> method, sync -> async); *default change* (a parameter's default value changed); *behaviour-only* (same
signature, different runtime behaviour: exceptions, outputs, wire format).

**Verification.** Each candidate is checked against the two wheels by text inspection of the extracted sources
(grep/AST, not griffe or any evaluated tool): the old form must exist at the cutoff-era release and the documented
change must be present at the pinned release. Items that fail (change already in the cutoff-era release, reverted, or
not present) are excluded with a reason. Verification is done by Claude Opus 5.5 (this agent), single pass, no human:
**AI-verified**.

**Sampling.** If a pair has more than 30 verified eligible items, 30 are drawn uniformly at random
(`random.Random(20261023).sample` over items sorted by id); otherwise all are used. Pooled estimates are therefore
over a stratified sample; per-library recall is also reported, and a macro-average over libraries.

**Task-change set (secondary).** The 25 post-cutoff task changes (one per task, from the task files' evidence) are
evaluated separately, whether or not they are in the sample.

**Blinding.** The GT file (`expansion/recall/ground_truth.json`) is completed and its sha256 recorded in
`analysis/recall_eval.json` before any tool is run on the pairs. Items are not added or removed after tool output is
seen; adjudication errors found later are corrected only with a logged reason (section 8).

## 4. Tools and configurations

1. **since-cutoff 0.4.1** (git tag v0.4.1, installed from source in `recall_eval\venv041` with the
   study venv's exact dependency versions, griffe 2.3.0). *Detector* = every change of the pair in `scan --json`
   output (all kinds, including new deprecations), uncapped. *Notes* = the block of `sync --scope imported
   --per-package 5` for a one-file project importing the package (the benchmark setting; checked byte-equal to the
   frozen benchmark block apart from model name and hashes), plus `--per-package 10` and the uncapped detector.
2. **since-cutoff C2** = commit 3f0144f on local branch `naacl/changed-defaults` (worktree `sc-naacl-c2`; dependency-
   switch detection from released 0.5.0 plus changed-default detection), installed from source in `venvc2`, same
   settings.
3. **griffe check** (griffe 2.4.1, latest on PyPI on 2026-10-23, `venvgriffe`): for each pair a throwaway git repo
   with the old wheel's top-level package(s) committed and tagged `old`, then the new one tagged `new`; `griffe check
   <pkg> -s . -a old -b new -f oneline` (default loading options). Structured results from the same comparison via
   `griffe.find_breaking_changes` (what `griffe check` calls); the CLI line count must equal the API count. All
   breakage kinds count as reported, including changed defaults and attribute values.
4. **AexPy** 0.4.3 (`pip install aexpy`, `venvaexpy`): `preprocess -w` on each wheel, `extract` in an environment that
   has that release and its dependencies installed from the wheelhouse/PyPI (AexPy imports the package), `diff`. Reported
   = entries with rank Low, Medium or High (breaking ranks). If extraction fails for a release, the pair is "not run"
   with the error recorded; nothing is substituted.

Each tool's report list for a pair is frozen to `recall_eval\out\<tool>\<lib>.json` before matching.

## 5. Matching (detected yes/no per GT item and tool)

A tool **detects** a GT item if at least one reported change (a) refers to the item's API element (same object path,
a public alias/re-export of it, a sync/async twin, or a containing module/class whose removal or move it reports --
flagged `via_container`), and (b) is kind-consistent: removal and rename/move <- a removal, move or rename report;
signature <- a report on the same parameter(s) (removed, renamed, required, kind, type) or on the callable's removal;
default change <- a changed-default report on that parameter; dependency switch <- a report naming the switch, or a
report on a public signature/attribute whose type moved from the old dependency to the new one (flagged `indirect`);
behaviour-only <- a report on the same element whose content states the behaviour change (e.g. a deprecation
message describing it). Candidates are proposed by a script (identifier match of the item's API names against report
paths/messages) and adjudicated by Claude Opus 5.5 (**AI-judged**), with a one-line rationale per decision. Secondary
outcomes recorded: whether the report names the replacement; exact-path vs via-container (sensitivity: exact-only
recall).

**Reaches the notes:** the same rule applied to the lines of the capped block (5 per package), and of the
`--per-package 10` block.

## 6. Precision

Per tool, a random sample of up to 8 reported changes per library (seed 20261023; all if fewer), i.e. up to 56 per
tool; plus **every** line of the seven capped blocks of 0.4.1 and of C2. Each sampled report is judged against the two
releases' extracted sources (and the changelog where useful) by Claude Opus 5.5, **AI-judged**, single pass:
*accurate* (the stated change exists between the two releases, and the old object is not still reachable at the same
path through a re-export, `__getattr__`, inheritance or `**kwargs`) and *breaking* (code written for the old release
that uses that element through a public path fails or behaves differently at the pinned release). Lenient precision
= accurate; strict precision = accurate and breaking.

## 7. Statistics

Proportions with Wilson 95% intervals: recall overall (pooled items), per library, macro-average over libraries
(no CI), by change type; notes-level recall at cap 5 and cap 10; precision (lenient, strict). Pooled intervals treat
items as independent (they are clustered by library; per-library numbers are shown). Exploratory: exact McNemar test
on discordant GT items for since-cutoff 0.4.1 vs griffe check and 0.4.1 vs C2 (detector level).

## 8. Outputs and deviations

Scripts: `expansion/recall/`. Raw tool outputs and work trees: `recall_eval\`. Results:
`analysis/recall_eval.json` (aggregates, every GT item with its source URL and per-tool decision, precision
judgements). Summary for the paper: `RESULTS_FOR_PAPER.md` section 0.15. Any deviation from this protocol is listed
in section 0.15 under "Deviations" with its reason.
