# Independent review of the 11 tasks2 tasks (2026-10-22, before any session)

Reviewer: a separate Claude Opus 5.5 agent with no part in writing the tasks. It changed no task files. It ran 55
alternative-correct and plausible-wrong solutions against the hidden tests in the prebuilt venvs, using the grading
flags (`-p no:cacheprovider --allow-hosts=127.0.0.1,::1`).
Its solution folders and proposed tests are in the session scratchpad `review/`; they are not kept.

## Verdicts and what was applied

| task | verdict | finding | applied fix |
|---|---|---|---|
| pl01 | OK | NOTE: stale_pattern `[^)]*` matches correct code with nested parens (`explode(pl.col("tags"), empty_as_null=True)`) | pattern allows one nesting level |
| pl02 | fix needed | BLOCKER: batching never checked; `pl.read_csv` whole file + one progress call passed | added `largest_frame` fixture + `test_reads_in_batches_of_at_most_batch_size` (>= 3 progress steps, each <= batch_size; no materialised frame > 1000 rows) |
| pl03 | OK | – | – |
| pl04 | fix needed | BLOCKER: plain `collect()` runs on the streaming engine in polars 2.0 (collect docstring, `lazyframe/frame.py:2101-2104`; POLARS_VERBOSE confirms), `pl.StreamingEngine()`, `with pl.Config(engine_affinity=...)`, sinks were rejected; env-var teardown broke module-level affinity | engine resolved at call time via `_select_engine(...).plan_engine`; "auto" counts as streaming on polars >= 2; collect_batches/sink_* wrapped; env teardown removed |
| st01 | OK | SHOULD: "Streamlit's caching" only checked through test order (`functools.lru_cache` failed by accident) | added `test_cache_is_streamlits` |
| st02 | OK | NOTE: `width=10_000` (clamped) would be rejected; unlikely | none |
| mi01 | OK | – (SDK hooks, wrapping transport, Client subclass all pass; per-client id / no log / ignored transport fail) | – |
| mi02 | OK | SHOULD: stub returned pages out of order (trap unrelated to the API change); stale_pattern nesting false positive | stub pages in index order; pattern allows one nesting level |
| pl90 | OK | – | – |
| pl91 | OK | – | – |
| st90 | OK | SHOULD: "always written back" not checked on first load (on_change-only solution passed) | test asserts `region == "all"` in the URL for missing/invalid input |

## Premises

The reviewer checked every claimed change in the installed site-packages of both versions:
- pl01: `frame.py:9471` (1.42.1) vs `frame.py:9539` (2.0.0).
- pl02: `read_csv_batched` is deprecated at `io/csv/functions.py:768` and removed in 2.0.
- pl03: `expr.py:12438` vs `expr.py:11451`.
- pl04: `lazyframe/frame.py:2069`.
- st01: `__init__.py:287`.
- st02: `image.py:199-202` vs `image.py:190`.
- st90: `__init__.py:291` (1.53.1).
- mi01: METADATA requires httpx2; `client/sdk.py:8` does `import httpx2 as httpx`.
- mi02: `client/ocr.py:34` vs `client/ocr.py:35`.
- pl90 and pl91: the removed APIs exist in 0.20.31 and are absent in 1.42.1 and 2.0.0.

No answer token appears in any repo or instruction. No repo contains old-API code an agent could copy.

## Notes for the paper

- Several changes were announced before the cutoff: the pl01 DeprecationWarning names the fix, and pl02, pl03, pl04
  and st01 remove long-deprecated APIs whose error messages name the replacement. This is a threat to validity.
- Because of the polars 2.0 default engine, pl04 effectively tests "do not pass the removed `streaming=` argument".
- After the fixes, `bench validate` passes all 11 tasks on all four gates and the leak check
  (`validate_tasks2_final.log`).
