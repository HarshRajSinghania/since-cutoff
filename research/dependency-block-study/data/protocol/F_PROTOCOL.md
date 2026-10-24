# Estimating f from the author's own Claude Code sessions: protocol

Written 2026-10-24, **before any import was extracted, any package was mapped or diffed, and before any value of f
existed.** Done before writing this file: a structural census of the transcript store (number of JSONL files: 1,845, of
which 1,812 are subagent transcripts; models per transcript; first/last assistant date per top-level session; counts
of Edit/Write/MultiEdit/NotebookEdit calls on `.py`/`.ipynb` files by coarse path category: tool repository,
temp/scratch, other home folders, benchmark, research; whether edited files still exist on disk; which tool-result
fields are present). No file content, prompt, import or package was looked at. The sha256 of this file is recorded in
`F_PROTOCOL.sha256`, in `analysis/f_sessions.json` and in RESULTS_FOR_PAPER.md section 0.18. The I1 folder is not a
git repository; the author should commit/tag this file before relying on it as a registration.

Not pre-registered in the strict sense: one analyst, the data already exist, and the census above was seen. Treat the
result as a **descriptive, single-developer estimate**.

## 1. Question

The paper's break-even (section 5; RESULTS 0.14.2) says the notes block pays for itself when a share f of sessions
needs a changed API: f* about 6-10% at the benchmark block size, 9-30% at real block sizes. Reviewers asked for real
session evidence. We estimate f from the author's own local Claude Code transcripts, locally, aggregates only.

## 2. Data and privacy

- Input: `~/.claude/projects/**/*.jsonl` (top-level session transcripts and `subagents/agent-*.jsonl`).
- Everything runs locally. Outputs (`analysis/f_sessions.json`, RESULTS 0.18) hold **aggregates only**: counts,
  shares, intervals, and counts of public PyPI distributions by name. No project names, paths, session ids, code,
  prompts or file contents in any output. Cluster keys are kept in memory only.
- Scripts (`expansion/fsessions/`) embed no personal data: the transcript root is derived from the home folder, and
  session ids to exclude are passed on the command line.
- Network: only (a) PyPI JSON metadata for **public distributions** chosen by the local mapping in 4.3 (never a name
  that is not an installed distribution or in the fixed alias table), and (b) the since-cutoff tool's own wheel
  downloads from PyPI for those distributions. Edited code never leaves the machine; synthetic scan folders are
  written to a temporary directory and deleted after the run.
- Local files: an edited file that still exists on disk is read only to extract its import statements (4.2, last
  fallback). Nothing else in any repository is read.

## 3. Units, exclusions, clusters

**Unit = one agent transcript** (a top-level session or one subagent run). Each is a separate model context that would
receive the notes block once (the block's cost model in the paper is per session/context), so it is the natural unit
for f. Secondary: the top-level session with its subagents pooled (reported, few units).

Exclusion rules, applied in order (counts reported for each):
- **X0 empty**: no assistant message with a real model id (e.g. only `<synthetic>`), or no timestamp.
- **X1 benchmark harness / runs**: the transcript's `cwd`, or any file path given to Edit/Write/MultiEdit/NotebookEdit/
  Read, lies under `C:\b\`, or contains `since-cutoff-benchmark`, `since-cutoff-bench` or `since_cutoff_runs`.
- **X2 research agents**: (a) every transcript of the top-level session(s) passed with `--exclude-session` (the session
  that runs this paper's research and its subagents, including this analysis); (b) any transcript whose `cwd` or any
  path as in X1 lies under the research trees `<research folder>` or `` (the paper sprint's research
  folders).
- Nothing else is excluded. Sessions that edit nothing (planning, review, e-mail, research reading, scheduled tasks)
  stay in the denominator: every session would pay for the block.

Development of the since-cutoff tool itself (`projects\since-cutoff*`, `projects\sc-*` worktrees) is real product work
and stays in the primary analysis; a **sensitivity analysis drops it** (S1), because the tool is the paper's own
system and its sessions are numerous.

**Cluster = project.** Each edited path maps to a project key: `projects\<X>` -> family of X (`since-cutoff*`/`sc-*` ->
one key; `<project>*` -> one key; else X); `oss\<X>` and other folders directly under home -> X with trailing
`-pr<N>`, `-<N>`, `-wt*`, `-fix*` removed; `Temp\claude\...\scratchpad` files -> the transcript's modal non-scratch
project if any, else one key per top-level session; other `Temp\<X>` -> `temp:<X>`; anything else -> its first three
path components. A transcript's cluster is the modal project of the files it edits (any file type); a transcript that
edits nothing is clustered with its top-level session (`session:<id>`). Keys are never written out.

## 4. Measurements per transcript

### 4.1 Model, cutoff, date
Model = most frequent `message.model` over assistant messages (ignoring `<synthetic>`). Cutoff = the tool's
`since-cutoff models` table (0.5.0, the exposure-scan version); a month-only cutoff means the month's last day
(as the paper: Opus 5.5 -> 2026-06-30). Session date = UTC date of the first assistant message.

### 4.2 Python edits and their imports
Edits = tool calls `Edit`, `MultiEdit`, `Write` on `*.py`, and `NotebookEdit` on `*.ipynb` code cells. Python written by
Bash (heredocs, `python -c`) is **not** counted (limitation; biases f down).
For each edited file, the imports in force are the union of the import statements found in:
(1) the edited code itself (Write content; Edit/MultiEdit `new_string`; notebook `new_source`), and
(2) the file's header at edit time, from the first available of: the Edit tool result's `originalFile`; the latest
earlier Write content of the same path in the transcript; an earlier Read result of the path that starts at line 1;
an earlier Edit `originalFile` of the same path; the file on disk now, if it exists (import statements only).
Imports are parsed with `ast` (fallback: line regex `^\s*(from|import)\s`), keeping absolute imports' dotted names.

### 4.3 Third-party distributions
A top-level module is dropped if it is in `sys.stdlib_module_names`, `__future__`, or **local**: a name equal to a
path component of any edited file of the same project, or a sibling `<name>.py`/`<name>/` next to the edited file or at
the project root on disk. Remaining modules map to PyPI distributions through `importlib.metadata.
packages_distributions()` collected from the local Python environments (system Python plus venvs found under
`~/projects/*/` and the since-cutoff scan venv), plus a fixed alias table for common mismatches (e.g. `yaml` ->
PyYAML, `PIL` -> pillow, `sklearn` -> scikit-learn, `cv2` -> opencv-python, `bs4` -> beautifulsoup4, `dateutil` ->
python-dateutil, `dotenv` -> python-dotenv, `jwt` -> PyJWT, `git` -> GitPython, `google.genai` -> google-genai).
For namespace tops (several candidate distributions) the distribution whose normalised name equals the dotted module
prefix is used. Modules that map to nothing are counted as **unresolved** (reported; treated as not changed).

### 4.4 Version in use (approximation, stated)
There is no record of the installed version at session time. **Primary:** the version in use is the **latest final
(non-pre-release, non-yanked) release uploaded on or before the session date** (what a fresh install that day
resolves to). This tends to overstate recency, and so exposure, for projects that pin older versions. No sensitivity
with lockfiles is attempted (most edited projects no longer exist locally, and today's lockfile is not the lockfile at
session time); this is a stated limitation.

### 4.5 Changed API (the tool's own diff)
For each transcript with at least one resolved third-party distribution, a synthetic project is written to a temp
folder: `requirements.txt` with `<dist>==<version in use>` for each distribution, and for each edited file two Python
files: `h_<i>.py` = the file's import header only, and `e_<i>.py` = the same header plus the edited code (Edit
snippets dedented; if still not parseable, wrapped as the body of a function; Write content as is). The tool runs
statically: `since-cutoff scan <dir> --cutoff <model cutoff> --json` (0.5.0; wheels parsed with griffe, nothing
executed). From its report:
- a distribution is **changed** if its `status` is `changed` (public API changed between the release current at the
  cutoff and the version in use; this is the exposure definition of the paper's 4.1/0.16 scans);
- **newer** if the version in use was released after the cutoff (changed or not);
- a changed API is **touched by the edit** if the report's `used_apis` lists it as used in an `e_<i>.py` file and it is
  not used in the matching `h_<i>.py` (so unchanged header imports do not count).
Distributions the tool cannot check (too large, no wheel, errors) are counted as **unchecked** and treated as not
changed in the primary estimate; the S3 sensitivity treats every unchecked imported distribution as changed.

### 4.6 Estimands
Over included transcripts (denominator N):
- `share_edit_any`: edits any file; `share_edit_py`: edits Python (4.2).
- `f_newer`: edits a Python file importing a distribution with a release after the cutoff (in use at the session).
- **`f_upper`**: edits a Python file importing a distribution whose public API changed between the cutoff and the
  version in use (the checklist's "edited a file importing a package the block names", imported scope).
- **`f_strict`**: the edited code itself uses a changed API symbol (tool matcher, 4.5).
Also the same three shares conditional on editing Python.

### 4.7 Intervals and comparison
95% percentile bootstrap, **clustered by project** (resample clusters with replacement; 10,000 draws; seed 20261001).
Also reported: number of clusters, the largest cluster's share of transcripts, and the estimates at the top-level
session level. Comparison: f_upper and f_strict against the paper's break-even shares (6-10% at the benchmark block,
9-30% at real blocks; RESULTS 0.14.2 and paper section 5): reported as below / inside / above, with the CI.

### 4.8 Sensitivity analyses (all reported)
- S1: without the since-cutoff tool's own repository.
- S2: without temp/scratch-only Python edits (files under the temp folder).
- S3: unchecked imported distributions treated as changed.
- S4: every transcript assigned Opus 5.5's cutoff (2026-06-30), the paper's model, whatever model it ran.
- S5: Opus 5.5 transcripts only.

## 5. Caveats to report
Single developer, own sessions, heavy subagent use, period 2026-05 to 2026-10 (mostly late Sept-Oct 2026); selection
(the author builds a tool about dependency drift and contributes to AI-library repositories, so exposure may be higher
than typical); version-in-use approximation; Bash-written Python not counted; Edit snippets may be unparseable (share
reported); the matcher's recall is incomplete (RESULTS 0.15) so f_strict is a lower bound of "edits touching a
changed API"; f_upper is an upper bound of "sessions needing a changed API".
