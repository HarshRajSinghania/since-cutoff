---
title: What your coding model doesn't know about your dependencies
description: Measuring which pinned library APIs a coding model gets wrong because they changed after its training cutoff, and writing short AGENTS.md notes about them.
---

**English** · [Español](es/index.md) · [Français](fr/index.md)

*Mohammad Hijjawi · September 2026, updated October 2026 · [since-cutoff on GitHub](https://github.com/MohammadHijjawi97/since-cutoff)*

<p align="center"><img src="img/hero.svg" width="640" alt="Your coding model learned your libraries before they changed. Claude Opus 4.6 on one sample project, measured with since-cutoff 0.1.0: on 7 of 16 probed API changes it used a name or parameter that has since been removed; with the notes, 5% to 65% of 20 held-out tasks were correct. Try it: uvx since-cutoff scan (no model calls, no API key)."></p>

**since-cutoff** is an open-source command-line tool and MCP server for Python projects written
with coding agents. `scan` shows where your code uses a dependency API that changed after the
model's training cutoff, with a note for each stated from the API diff (the version you pin
against the comparison release, the latest one published at least 30 days before the cutoff);
`sync` writes the notes into AGENTS.md or CLAUDE.md and keeps them in step with your lockfile;
`status`, pre-commit hooks and a GitHub Action tell you when they fall behind; the MCP server
lets an agent ask what changed in a library before it writes code. Only the optional `run` calls
a model: it measures which of the changes the model gets wrong and whether the notes help. Each
note is tagged with what was checked: stated from the API diff, or written by the model and kept
only if its example type-checks against your version.

```bash
# the changed APIs your code uses, with a note for each (no model calls, no API key)
uvx since-cutoff scan

# write the notes into AGENTS.md and keep them current (no model calls)
uvx since-cutoff sync

# optional: measure which of the changes your model gets wrong, and test the notes (calls it;
# --with adds the basedpyright type checker, which only run needs)
uvx --with basedpyright since-cutoff run
```

`pip install since-cutoff` installs everything but `run`'s type checker;
`pip install "since-cutoff[run]"` adds it (basedpyright, with the Node.js it brings).

[Source and documentation on GitHub](https://github.com/MohammadHijjawi97/since-cutoff) ·
[PyPI](https://pypi.org/project/since-cutoff/) ·
[How it works, in detail](https://github.com/MohammadHijjawi97/since-cutoff/blob/main/docs/how-it-works.md) ·
[Troubleshooting](troubleshooting.md)

## What it does, as of 0.6

- **Which release it compares from.** For each dependency, the comparison release is the
  latest one published at least 30 days before the model's training cutoff
  (`--cutoff-margin DAYS`; `0` compares from the cutoff itself, as before 0.6). A model knows
  the last weeks before its cutoff least: llama-index-core 0.13.0, which removed
  `ReActAgent.from_tools` and `FunctionCallingAgent`, was uploaded the day before Claude Sonnet
  4.5's cutoff, and comparing from the cutoff hid both removals; with the margin, a project
  that pins 0.14.25 and calls both is told about both. The model line, the reports and the
  notes block give both dates ("training cutoff 2025-07-31, comparing from releases up to
  2025-07-01"), the dependency tables head the column "compared from", and the scan says what
  the changes came after: "Your code uses 2 APIs that changed after 2025-07-01, 30 days before
  claude-sonnet-4-5's training cutoff (2025-07-31)".
- **Where your code uses a changed API.** Imports and calls, and since 0.6 method calls on
  objects whose class the file never names: the receiver is typed from the pinned release's own
  annotations, so `df = pd.read_csv(...)` is a `DataFrame` and `df.groupby(...).count()` a
  `DataFrameGroupBy.count`, and `llm.predict(q)` on a `ChatOpenAI` is langchain-core's
  `BaseChatModel.predict`. A change to an inherited method is matched under the public classes
  that inherit it (`DataFrame.fillna` for `NDFrame.fillna`). A use found by the method's name
  alone is left out unless you pass `--include-name-matches`, and the scan says how many it
  left out.
- **What the diff sees.** Removed and moved names, removed or newly required parameters,
  keyword-only and positional-only changes, new deprecation markers (PEP 702's `@deprecated`
  too, also when a library imports it through a compatibility module) and dependency switches
  (`httpx` to `httpx2`). New in 0.6: parameters removed behind `**kwargs: Unpack[SomeTypedDict]`
  (pandas 3.0's `read_csv` takes its keywords that way, and lost `delim_whitespace`,
  `date_parser`, `infer_datetime_format`, `keep_date_col` and `verbose`), and names a module
  takes from another distribution with `from x import *` (mcp's `mcp.types` comes from
  mcp-types, which renamed every field to snake_case).
- **Public and internal changes.** Each change is public (the package's top level exports it,
  a module names it in `__all__`, re-exports it or documents it) or internal. The counts give
  the internal ones apart, as "+N internal", and `scan --internal` lists them; the notes cover
  only the APIs your code uses.
- **What the notes say.** The replacement the library's own deprecation text names, in its
  words, tagged `[diff + library]` (httpx 0.28: "Use `proxy` or `mounts` instead of
  `proxies`"). The text is looked for where libraries put it: a `.. deprecated::` directive, a
  parameter's docstring entry, a `warnings.warn` message, and for a removed method with no
  text of its own, its class's (llama-index-core's `ReActAgent.from_tools`: "Use
  `llama_index.core.agent.workflow.ReActAgent` instead."). Where the text names none, the note
  links the package's migration guide, changelog or releases page for the changes since the
  comparison release. Quotes keep the library's code intact. Bullets that say the same of
  several APIs of one package are merged into one. A dependency first released after the
  cutoff, or within the margin before it, gets one `[metadata]` note with its first release
  date and summary.
- **What it says it could not see.** A module the pinned release ships compiled, without a
  `.py` source or a `.pyi` stub; a distribution a module re-exports that could not be
  downloaded; a class whose attributes a base class in another package may set; sources in a
  syntax the Python running since-cutoff cannot parse (numpy 2.5.4's stub on Python 3.10: the
  package could not be checked, and the scan names the Python that can). The scan, the report
  and the MCP tools warn about each, instead of reporting removals that may not be real or no
  changes at all. A metapackage such as llama-index, with no API of its own, is named as one,
  with the parts that were checked and those that were not. When PyPI cannot be reached, a
  release list cached more than 12 hours earlier is used, and the scan says from which day it
  is.
- **Where the notes go.** AGENTS.md, CLAUDE.md, or both: with both files and a CLAUDE.md that
  does not import AGENTS.md (`@AGENTS.md`), `sync` writes the block to both, because Claude
  Code reads only CLAUDE.md and Codex, Cursor and Copilot read AGENTS.md; it says how to keep
  one copy.
- **For scripts and agents.** `since-cutoff sync --json` (with `--yes`, `--check` or
  `--dry-run`), `since-cutoff models --json`, and `models --makers` for the model makers' own
  listings without gateways and resellers. The MCP server has two prompts, `check_project` and
  `before_upgrade`. Without `--model`, Gemini CLI's model is read from `GEMINI_MODEL` or
  `.gemini/settings.json`.
- **Install, start-up and cache.** basedpyright, which only `run` uses, is the `[run]` extra.
  A plain install measured about 73 MB of packages in a fresh virtual environment (about 254 MB
  with `[run]`), and `since-cutoff --help` starts in about 100 ms (both measured on Windows,
  Python 3.13). `since-cutoff cache info` shows the cache by kind, `cache clear --sources`,
  `--diffs` or `--pypi` clears one kind, and `SINCE_CUTOFF_CACHE_MAX_MB` caps the extracted
  sources (2048 by default).

It is still Python only, and the notes still come from a static diff of two releases: they say
what changed, not what the model knows. Behaviour changes behind an unchanged signature are not
seen.

The rest of this page is the story behind it and the first measurements, made with since-cutoff
0.1.0 in September 2026. More recent measurements: [What your model hasn't seen](ai-stack.md)
(36 libraries, 21 models, no model calls, re-run with 0.6) and
[the coding-agent benchmark](benchmark.md) (360 Claude Code sessions, with 0.4.1's notes).

---

Every coding model has a training cutoff. Your lockfile doesn't. When a library changes its
public API after the cutoff, a model that learned the old version keeps writing the old calls,
and nothing in the prompt tells it otherwise.

I wanted a number for that instead of an anecdote: **for one real project, which of the exact
dependency versions it pins does the model get wrong, and does a short note fix it?**
[since-cutoff](https://github.com/MohammadHijjawi97/since-cutoff) is the tool I built to answer it.

## The setup

The sample project ([`examples/agent-app`](https://github.com/MohammadHijjawi97/since-cutoff/tree/main/examples/agent-app))
is a small agent app with nine dependencies. Six are pinned to current releases (anthropic
1.8.0, openai 3.19.2, huggingface-hub 2.0.0, langchain-core 1.6.5, langgraph 1.2.12 and
pydantic 2.13.5); three are unpinned (fastapi, requests and httpx), so the tool uses their
latest release.

Two models were tested: **Claude Haiku 4.5** (training cutoff February 2025) and **Claude Opus 4.6**
(May 2025). Tasks and notes were written by Claude Opus 4.6.

## How it measures

1. **What changed.** For each dependency, take the comparison release, the latest release
   published at least 30 days before the model's training cutoff (by default; the 0.1.0 runs
   below took the newest release on or before the cutoff), and diff its public API against the
   pinned version, statically (griffe, no code imported). That finds removed and moved objects,
   removed or newly required parameters, keyword/positional-only changes and new deprecation
   markers. For this project and Claude Haiku 4.5's cutoff, 7 of the 9 dependencies changed;
   the 0.6 diff, comparing from 29 January 2025, flags 344 breaking changes and 48 new
   deprecations in public APIs, and 168 changes to internal ones.
2. **Tasks that need the change.** For the highest-ranked changes, a task writer produces short,
   realistic coding tasks that require the changed functionality but never name the changed
   identifier or its replacement. One task is the probe; two are held out.
3. **Answers with nothing to look things up in.** The model gets the task and the pinned version
   number, and no tools, no web, no project files.
4. **Scoring by a type checker, twice.** The answer is type-checked with basedpyright against the
   comparison release (step 1) and against the pinned version, each in an isolated environment
   with that version's own dependencies. Only API-knowledge errors count (unknown names, imports
   and parameters, missing arguments, arity), never type-strictness complaints.
   - **stale**: valid for the comparison release, invalid for the pinned one
   - **wrong**: invalid, and not explained by the version change
   - **deprecated**: valid, but uses an API marked `@deprecated` in the pinned version
5. **Write and test notes.** For each failure, a one-line note is written for AGENTS.md. A note
   written by the model is kept only if its example type-checks against the pinned version and
   every API it recommends appears in that example; otherwise the note is a plain statement of
   the change taken from the API diff. Then the held-out tasks are answered again, without and
   with the notes, and compared pair by pair.

No generated code is ever executed.

## Results

These runs were made with since-cutoff 0.1.0, on the one project above.

| | Claude Haiku 4.5 | Claude Opus 4.6 |
|---|---|---|
| training cutoff | Feb 2025 | May 2025 |
| API changes probed | 20 | 16 |
| **stale** / wrong / deprecated / correct | **5** / 1 / 2 / 12 | **7** / 0 / 3 / 6 |
| libraries with stale use | 3 of 5 probed | 2 of 4 probed |
| notes written (with an example that type-checks) | 8 (7), about 391 tokens | 10 (7), about 437 tokens |
| **held-out correct, without -> with notes** | **14% -> 57%** (14 pairs) | **5% -> 65%** (20 pairs) |
| previously-correct APIs after notes | 6/6 still correct | 6/6 still correct |

In this sample the stronger model was not safer. Opus 4.6 has a later cutoff and still wrote
stale code more often: `anthropic.HUMAN_PROMPT` with `client.completions`,
`hf_hub_download(force_filename=...)`, `resume_download=...`.

More stale code from the Haiku run, each valid for the comparison release and rejected by the
type checker for the pinned one:

- `client.messages.create(..., temperature=...)`: removed in anthropic 1.8, which raises
  `TypeError` for it
- `hf_hub_download(..., resume_download=True)`, `local_dir_use_symlinks=...` and `proxies=...`:
  no longer in the signature since huggingface-hub 1.0; 2.0 still accepts them at run time,
  ignores them and warns
- `client.beta.vector_stores`: an openai 1.x API that 3.x moved to `client.vector_stores`

### Does a note fix it?

since-cutoff wrote **8 notes, about 391 tokens**, 7 of them with an example that type-checks (one
fell back to a plain statement from the API diff). For example:

```markdown
**anthropic 1.8.0**
- `temperature=...` was removed from `messages.create()` in anthropic 1.8.0. Omit the `temperature` parameter entirely; there is no replacement.

**openai 3.19.2**
- `client.beta.vector_stores` is removed in openai 3.19.2. Use `client.vector_stores` instead.
```

On the held-out tasks for the changes it got wrong, the model was correct on **14% without the
notes and 57% with them** (14 paired tasks from 7 API changes). The run card also says "4 of 7
changes fixed, 95% CI 25-84%". That is 0.1.0's count, which also counted a change as fixed when a
held-out answer was already right without the notes, and the interval belongs to that count, not
to the two rates. The six APIs it already got right were still right with the notes in its
context.

## What these numbers do and don't say

- **Small sample.** Two models, one project, 16-20 probes each. It is a demonstration of a
  method, not a benchmark. The confidence interval is wide because the sample is small.
- **A sample of changes, not all of them.** Probes are ranked (APIs the project's own code uses
  first, hard breaks before soft ones); the task writer also skips internals.
- **What a type checker can see.** Wrong names, parameters, arity and PEP 702 deprecations.
  Behaviour changes behind an unchanged signature are invisible.
- **Held-out tasks are paraphrases of the same change,** so the before/after measures whether a
  note fixes *that* change, not general ability.
- **"The comparison release" is a date rule.** In these 0.1.0 runs it was the newest release on
  or before the cutoff. Models know the weeks right before their cutoff poorly, so real
  staleness can begin earlier; since 0.6 it is the latest release published at least 30 days
  before the model's training cutoff (by default).

## Why I care about this

This grew out of a paper I co-authored for EMNLP 2026 on *temporal isolation*: using a model's
training cutoff as a natural experiment for what it knows. Library releases are the same
experiment with a very practical payoff: the answer is a list of lines to put in AGENTS.md.

## Try it

```bash
# the changed APIs your code uses, with a note for each (no model calls)
uvx since-cutoff scan

# write the notes into AGENTS.md and keep them current (no model calls)
uvx since-cutoff sync

# optional: measure which of the changes your model gets wrong, and test the notes (calls it;
# --with adds the basedpyright type checker, which only run needs)
uvx --with basedpyright since-cutoff run
```

`run` works with Claude Code (as a plugin), Anthropic, OpenAI, OpenRouter, DeepSeek, Ollama and
any OpenAI-compatible server; `scan`, `sync` and `status` need only the model's cutoff.
`since-cutoff status` (offline), `sync --check`, the
[pre-commit hooks](https://github.com/MohammadHijjawi97/since-cutoff#pre-commit) and a
[GitHub Action](https://github.com/MohammadHijjawi97/since-cutoff#github-action) tell you when
the notes fall behind; `since-cutoff mcp` lets any MCP client (Claude Code, Codex, Cursor, VS
Code, Gemini CLI) look up a library's changes before writing code. It is Python-only for now;
TypeScript is next. Feedback on the method is very welcome in the
[issues](https://github.com/MohammadHijjawi97/since-cutoff/issues), and results from your own
projects in [Share your results](https://github.com/MohammadHijjawi97/since-cutoff/discussions/6).
If you would like to contribute code, the
[good first issues](https://github.com/MohammadHijjawi97/since-cutoff/labels/good%20first%20issue)
are a good place to start.
