# Exposure study 2 (random sample, two strata): pre-registered protocol

Written 2026-10-23 (~19:20 UTC), **before the sampling frame was enumerated, before any repository was selected,
cloned or scanned, and before any result of this study existed.** The only GitHub call made before writing this file
was one search count to size the frame (`language:Python stars:>=200 pushed:>=2026-07-25` reported 15,738
repositories). The file's sha256 is recorded in `analysis/exposure2.json` and in RESULTS_FOR_PAPER.md section 0.16;
the I1 folder is not a git repository, so the author should commit/tag this file before relying on it as a
registration (it must be byte-identical to that sha256).

No model sessions, no GPU, no paper edits. Offline static analysis plus read-only GitHub API calls through `gh api`.

## 1. Why (concerns from internal reviews)

The exposure evidence in the paper (§6, Appendix G; RESULTS 4.1, 0.14) rests on 47 repositories that are the
*most-starred* Python repositories with a uv/Poetry lockfile pushed after 2026-09-01. Internal reviews objected that
(i) n = 47 is small, (ii) the set is clustered (top-starred, heavy on AI tooling, several repositories per
organisation possible), and (iii) the matcher's recall is unknown and its precision rests on one audit dominated by
two repositories (35 of 53 matches). This study draws a **random** sample from a defined frame, in two strata, with
repository-clustered intervals, and audits a random sample of matcher hits, including whether each hit would break at
runtime.

## 2. Sampling frame

- **Frame F**: public, non-fork, non-archived GitHub repositories returned by the search
  `language:Python stars:>=200 pushed:>=2026-07-25 archived:false` (pushed within the 90 days before 2026-10-23),
  enumerated completely through the search API (`gh api search/repositories`, read-only). Because one search returns
  at most 1,000 results, the query is partitioned by star ranges (and, if a single range still exceeds 1,000, by
  creation-date ranges) until every slice is ≤ 1,000; the union is de-duplicated by repository id. The enumeration
  timestamp, the per-slice `total_count`s and the number enumerated are recorded; a gap between the sum of slice
  counts and the enumerated union (search-index inconsistency) is reported, not corrected.
- Repositories marked `is_template`, repositories of the tool's author (owner `MohammadHijjawi97`) and repositories
  with GitHub `size` > 2,000,000 KB are excluded from F before sampling (counts reported).
- **Order**: F sorted by lower-cased `full_name`, then shuffled with `random.Random(20261023)`. All selection below
  walks this one permutation; nothing else (stars, topic, language share) influences selection.

## 3. Eligibility (checked in permutation order)

E1. **Pin source at the root** (contents API, read-only): the root has `uv.lock`, `poetry.lock`, `pdm.lock`,
    `pylock.toml` / `pylock.*.toml` or `Pipfile.lock`, **or** at least one `requirements*.txt` (or a `requirements/`
    directory).
E2. **Clone**: `git clone --depth 1 --no-tags --filter=blob:none --sparse -c core.symlinks=false`, sparse checkout
    (non-cone) of only the files the scan reads: `*.py*` (the tool's source glob is `rglob("*.py*")`), `*.toml`,
    `*.lock`, `requirements*.txt`, `requirements/*.txt`, `Pipfile`, `Pipfile.lock`, `.python-version`, `/*.md`.
    Clone timeout 600 s. A clone failure makes the repository ineligible (counted).
    *Method check (pre-registered, reported)*: on 3 repositories of the earlier 47, the scan of a sparse clone must
    give the same JSON counts as the scan of the earlier full clone (same tool, same cutoff); otherwise the full
    shallow clone (`--depth 1`) is used for every repository.
E3. **Scan succeeds**: `since-cutoff 0.5.0 scan <clone> --json --model anthropic:claude-opus-5-5` (cutoff
    2026-06-30, the exposure-scan version in `since_cutoff_runs\scan-venv`), exit 0 or 3 and parsable
    JSON, per-repository timeout **1,200 s**. A timeout, another exit code (e.g. no dependency it can check) or
    unparsable output makes the repository ineligible; timeouts are counted separately (see 6.5).
E4. **Pinned project**: at least one direct PyPI dependency the tool checked, and at least half of the checked direct
    dependencies take their version from a lockfile, an exact pin or an environment, i.e. per-package
    `version_source` not starting with `latest on PyPI` and not `unpinned` (the tool resolves unpinned dependencies to
    PyPI's latest release, which is not a pin).

Nothing from the repositories is executed (no setup.py, no scripts, no imports of repository code); the tool parses
lockfiles/requirements and the code statically and downloads/parses released wheels.

## 4. Strata and target sizes (target n = 200, 100 per stratum)

- **Stratum G (general Python)**: the first **100** eligible repositories in permutation order, regardless of what
  they depend on. G is a simple random sample of eligible repositories in F (it contains AI repositories at their
  natural rate, so G's shares estimate the frame's eligible population directly).
- **Stratum AI (AI/LLM stack)**: the first **100** eligible repositories in permutation order that are *AI-stack*:
  at least one **direct** dependency that the scan marks `imported` is on the fixed list below (canonicalised
  names; `*` = prefix family). AI is a simple random sample of eligible AI-stack repositories.
  AI list: openai, anthropic, google-genai, google-generativeai, google-cloud-aiplatform, google-adk, mistralai,
  cohere, groq, together, fireworks-ai, litellm, ollama, vllm, llama-cpp-python, langchain, langchain-\*, langgraph,
  langgraph-\*, langsmith, llama-index, llama-index-\*, transformers, sentence-transformers, huggingface-hub,
  datasets, tokenizers, tiktoken, peft, trl, accelerate, diffusers, mcp, fastmcp, pydantic-ai, pydantic-ai-slim,
  instructor, dspy, dspy-ai, crewai, smolagents, autogen-agentchat, autogen-core, pyautogen, ag2, openai-agents,
  claude-agent-sdk, agno, haystack-ai, semantic-kernel, guidance, outlines, chromadb, qdrant-client, pinecone,
  pinecone-client, weaviate-client, pymilvus, lancedb, mem0ai, letta, browser-use.
- The strata overlap (AI-stack repositories among the first 100 eligible are members of both). Per-stratum results
  use each stratum's 100; the union is used only for the audit pool and is reported with its size. After G is full,
  later candidates are scanned only if their dependency files (pyproject/requirements/lockfiles/Pipfile) mention a
  name on the AI list (a necessary condition for AI-stack; it saves scans and does not change the definition).
- If F runs out before a stratum reaches 100, the stratum is reported with the n reached (no other frame is used).
- Overlap with the earlier 47 repositories is counted and reported; they are not excluded.

## 5. Scans (per included repository)

- Exposure: the scan JSON of E3 (cutoff 2026-06-30).
- Block size, imported scope: `since-cutoff sync <clone> --dry-run --model anthropic:claude-opus-5-5 --scope imported
  --per-package 5` (the setting of every benchmark notes manifest; as in 0.14), timeout 1,200 s; block parsed from the
  dry-run diff exactly as `scripts/blocksize_breakeven.py` (`parse_block`, `block_stats`; tokens = round(len/4)).
  Used scope: the scan's own `notes_preview` token estimate (0.14 showed it equals the used-scope block in 47/47).
- Up to 4 workers in parallel, each with its own tool cache (`SINCE_CUTOFF_CACHE`), to avoid the shared-cache race
  seen in 0.14. Environment variables whose names contain TOKEN/KEY/SECRET/PASSWORD/CREDENTIAL are removed from the
  tool's environment.

## 6. Outcomes (per repository, at cutoff 2026-06-30) and estimators

"Pinned" = per-package `version_source` not starting with `latest on PyPI` and not `unpinned`.

- **P1 (primary) post-cutoff pin**: ≥ 1 pinned direct dependency whose locked release is dated after the cutoff
  (`locked_date > 2026-06-30`; includes packages first released after the cutoff).
- **P2 (primary) imported breaking package**: ≥ 1 pinned package (direct or transitive) with `status = changed`,
  `imported = true` and `breaking_changes > 0`. Secondary P2b: the earlier definition (`status = changed`,
  `imported`), and P2c with unpinned packages included (what the tool would report).
- **P3 (primary) matcher hit**: ≥ 1 entry in `used_apis` whose package is pinned (the code uses a changed API by the
  tool's static matcher). Secondary: number of matched APIs and of changes per repository.
- **P4 block sizes (imported scope)**: share with a non-empty block; tokens median [IQR] (linear interpolation),
  mean, max over all repositories and over non-empty ones; packages and change lines in non-empty blocks; share above
  423 / 1,000 / 2,000 tokens; used-scope tokens (notes_preview) likewise.
- Also: direct dependencies per repository; share of pinned direct dependencies locked after the cutoff (median
  [IQR]); breaking changes in imported packages per repository; share of AI-stack repositories within G (and among all
  eligible repositories screened).
- **Intervals**: every share and median gets a **cluster bootstrap** 95% percentile CI, 10,000 resamples, seed
  20261023, resampling **GitHub owners** (organisations/users; repositories of the same owner move together; with
  one repository per owner this is the ordinary repository bootstrap). Wilson 95% intervals are reported alongside
  shares. Strata are analysed separately; differences AI − G are bootstrapped jointly (independent resampling within
  each stratum; overlapping repositories are resampled independently in each, so the difference CI is approximate,
  stated as such).
- **6.5 Timeouts**: reported per stratum; sensitivity bounds for P1–P3 recomputed as if every timed-out repository
  that would otherwise have entered the stratum (in permutation order, within the walk) were exposed / unexposed.
- **Comparison with the earlier 47** (descriptive): the same outcomes recomputed with these definitions on the 47.

## 7. Matcher audit (AI-judged) and runtime check

- **Pool**: every `used_apis` entry with a pinned package in the union G ∪ AI (one entry = one matched API in one
  repository, as the scan lists it). **Sample**: 60 entries, `random.Random(20261024).sample` of the pool sorted by
  (repository, package, api); all entries if the pool has ≤ 60.
- **Judge**: the AI assistant (Claude Opus 5.5 in Claude Code) reads the matched files in the clone and both releases'
  sources (the tool's download cache, or the wheel from PyPI), and labels, as in the first audit
  (`scripts/realworld_audit.py`): verdict TP / FP-resolution / FP-diff; for TP, affected yes / handled / no. Labels
  are reported as **AI-judged** (no human re-check in this study).
- **Runtime check** (TP only): class **breaks** (raises at import, attribute access or call binding), **warns**
  (DeprecationWarning/FutureWarning only), or **runs**. Where feasible, a minimal snippet written by the judge - never
  repository code - runs in an isolated virtual environment containing only the pinned release (from PyPI) of the
  package and its dependencies: it performs the import/attribute access the code performs, or binds the code's call
  form to the API's signature (`inspect.signature(...).bind(...)` with placeholder values for the arguments the code
  passes), with warnings captured. Otherwise the class is a static judgement, flagged as such. Unless a TP is labelled
  affected = yes, the expected class is runs; a sample of those is still checked by snippet where cheap.
- **Estimates**: precision = TP / audited, with a **repository-cluster bootstrap** CI (resample repositories among
  the audited entries, with all their audited entries; 10,000, seed 20261023) and Wilson; FP types; share of
  audited entries that break / warn at runtime (same CIs); audited repositories with ≥ 1 TP and with ≥ 1 runtime
  break; tool `old_form` label accuracy.
- Recall is **not** estimated (it would need ground truth of all changed-API uses); this is stated as a limitation.

## 8. Outputs

Scripts `expansion/exposure2/` (frame, select+scan driver, analysis, audit, runtime check). Raw data (with repository
names) only under `since_cutoff_runs\realworld2\`. `analysis/exposure2.json`: aggregates only, no
repository names. RESULTS_FOR_PAPER.md section 0.16 with the numbers and suggested paper sentences. Deviations from
this protocol, if any, are listed there under "Deviations".
