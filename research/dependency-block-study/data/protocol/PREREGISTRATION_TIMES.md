# Pre-registration and first-session times (UTC)

Each study's protocol or addendum was committed and tagged in git before the study's first session. The tags are
unsigned. The main study's tag `main-freeze-2026-09-28` (commit de23b80) is in the public benchmark repository,
https://github.com/MohammadHijjawi97/since-cutoff-benchmark. The addendum tags (`naacl-addendum*`) are in a local branch
of that repository that has not been published, so their times cannot be checked externally. First-session times are
the earliest `started_at` of the study's non-pilot sessions in `runs/<study>/runs.jsonl`.

| study | pre-registration | tag and commit time | first session | last session |
|---|---|---|---|---|
| main (Opus 5.5, A-E) | PROTOCOL.md (frozen protocol) | 2026-09-28 03:24:52 | 2026-09-28 03:25:50 | 2026-09-28 09:53:33 |
| Sonnet 5.5 (A/C/H) | PROTOCOL_ADDENDUM.md sections 1-6 | 2026-10-21 21:04:09 | 2026-10-21 21:08:22 | 2026-10-21 22:55:21 |
| Haiku 5.5 (A/C) | PROTOCOL_ADDENDUM.md sections 1-6 | 2026-10-21 21:04:09 | 2026-10-21 22:57:30 | 2026-10-22 00:09:42 |
| replication (Opus 5.5, A/C/H) | PROTOCOL_ADDENDUM.md section 7 | 2026-10-22 00:12:40 | 2026-10-22 00:13:01 | 2026-10-22 01:50:03 |
| new tasks (Opus 5.5, A/C/H) | PROTOCOL_ADDENDUM.md section 8 | 2026-10-22 17:31:42 | 2026-10-22 17:32:37 | 2026-10-22 18:25:00 |
| irrelevant-content control R (Opus 5.5) | PROTOCOL_ADDENDUM.md section 11.1 | 2026-10-22 21:07:49 | 2026-10-22 21:08:38 | 2026-10-22 21:30:18 |
| older cutoff, original tasks (Sonnet 4.5, A/C) | PROTOCOL_ADDENDUM.md section 11.2 | 2026-10-22 21:07:49 | 2026-10-22 21:32:17 | 2026-10-22 22:28:46 |
| older cutoff, new tasks (Sonnet 4.5, A/C) | PROTOCOL_ADDENDUM.md section 11.2 | 2026-10-22 21:07:49 | 2026-10-22 22:30:43 | 2026-10-22 22:58:19 |
| case study (Opus 5.5, A/C) | PROTOCOL_ADDENDUM.md section 11.3 | 2026-10-22 21:07:49 | 2026-10-22 23:00:23 | 2026-10-22 23:24:27 |
| later tool version C2 (Opus 5.5) | PROTOCOL_ADDENDUM.md section 12 | 2026-10-22 22:17:28 | 2026-10-22 22:17:51 | 2026-10-22 23:02:02 |
| concurrent five-arm study (Opus 5.5, A/C/H/R/G) | PROTOCOL_ADDENDUM.md section 13 | 2026-10-23 00:02:42 | 2026-10-23 00:03:16 | 2026-10-23 01:38:26 |
| open-weight agent, A/C, original tasks (Qwen3-Coder-30B-A3B, mini-swe-agent) | PROTOCOL_ADDENDUM.md section 10 (pilot record 10.1 committed 2026-10-22 21:54:15) | 2026-10-22 20:45:54 | 2026-10-22 21:54:30 | 2026-10-23 03:16:59 |
| open-weight agent, A/C, new tasks | PROTOCOL_ADDENDUM.md section 10 | 2026-10-22 20:45:54 | 2026-10-22 23:18:57 | 2026-10-23 03:56:07 |
| open-weight agent, H, 17 original post-cutoff tasks | PROTOCOL_ADDENDUM.md section 10a | 2026-10-22 23:57:41 | 2026-10-23 01:57:53 | 2026-10-23 04:23:55 |

Section 14 (the lockfile-only header L and the wrong-block arm W) was registered but not run, because the Claude CLI
login had expired. Section 15 (a second open-weight study) was started and stopped before completion; its partial runs
are not analysed and are not in this folder.

Note: the heading of section 8 gives an approximate writing time ("~18:45 local / 17:45 UTC") that is later than the
commit that contains it (17:31:42 UTC, 18:31:42 local); the approximate time in the heading is wrong, and the commit
time is the one that counts. The heading of section 7 ("~00:15 UTC") is likewise approximate. The heading of
section 13 ("~01:30 local / 00:30 UTC") is also wrong: the plan was written at 00:01:49 UTC and the commit is
00:02:42 UTC, before the first session at 00:03:16 UTC.
For the three open-weight-agent studies the run records carry no start time; the first and last times are the
earliest and latest file times in the study's run folders (session start and end). The two A/C studies ran rep-major
in one sequence (all repetition-1 sessions of both, then repetition 2, then 3). The heading of section 10
("~21:50 local / 20:50 UTC") is approximate and a few minutes later than its commit (20:45:54 UTC). The heading of
section 10a ("~01:05 local / 00:05 UTC") is also later than its commit (23:57:41 UTC); the commit precedes the first H
session at 01:57:53 UTC. H was registered while the A/C studies were running and after interim A/C numbers had been
seen, which section 10a discloses.
