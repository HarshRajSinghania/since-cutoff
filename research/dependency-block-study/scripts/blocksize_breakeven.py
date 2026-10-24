"""Real-repository block sizes and the break-even share of sessions (requested in an internal review).
No model calls, no agent sessions; existing run tables plus static `since-cutoff sync --dry-run` on the scanned clones.

usage: python blocksize_breakeven.py generate [--workers 1]   -> $REALWORLD_DIR/blocks/<owner__name>.<scope>.json (raw)
       python blocksize_breakeven.py analyse                  -> <study>/analysis/blocksize_breakeven.json (aggregates only)
env:   REALWORLD_DIR (default since_cutoff_runs/realworld), CUTOFFNOTES_EXE (default the scan venv's
       since-cutoff 0.5.0, the version used for the exposure scan), RUNS_TABLES (default <study>/runs_tables).

1. Block sizes. Repositories: the 47 primary repositories of the exposure scan (scripts/realworld_analyze.py rule: first
   50 in star order whose scans succeeded for both cutoffs). For each, `since-cutoff sync <clone> --dry-run --model
   anthropic:claude-opus-5-5` (cutoff 2026-06-30), in two scopes:
     imported  --scope imported --per-package 5  (the setting of every benchmark notes manifest; primary)
     used      --scope used (the tool's default: notes only for changed APIs the code uses)
   Static only (wheels downloaded and parsed; nothing from the repositories is executed; --dry-run writes nothing).
   Per-repo timeout 1800 s (as the scan). The block is parsed from the dry-run diff (start to end marker); its token
   estimate is the benchmark manifests' rule: round(len(block_text) / 4), block_text = markers included, stripped,
   plus a newline (bench/conditions.py extract_block + note_entry). Packages = "**pkg version**" lines; change lines =
   "- " bullet lines inside the block. Runtime = wall seconds per call, run sequentially (--workers 1: parallel calls race on
   the shared tool cache on Windows, PermissionError in os.replace), tool cache as left by earlier calls in the run.
   Also from the scan JSON (opus-5-5): direct dependencies locked to a release after the cutoff (M, as
   realworld_analyze.py), to compare with the packages the block names (C2: "the diff filters N of M").
2. Break-even. Block overhead per session for a block of T est. tokens on Opus 5.5 list prices:
     O(T) = T x turns x $0.20/MTok (cache read every turn) + T x $8/MTok (one 1h cache write per session),
   turns = mean turns of C sessions (post-cutoff tasks) in each study; sensitivity: C turns on control tasks, and 24
   turns (LiteLLM case). Saving per affected session: the task-averaged mean (A - C) list-cost saving per session
   (token_breakdown.py saving_shares) in each Opus study, which already includes the benchmark block's own overhead;
   gross saving = net + benchmark-block overhead O_bench (same formula with each C session's notes_tokens and turns).
   With a share p of sessions touching a listed package, and the saving per affected session unchanged by block size,
   net = p x S_gross - O(T) (every session pays O(T)), so the break-even share is p* = O(T) / S_gross. Uncertainty:
   joint task bootstrap (10,000, seed 20261001; same draw for S and O_bench) at fixed T; reported at the real-block
   median, p75 and max and at the benchmark mean. Also the naive O(T)/S_net for comparison with the internal review's text.
"""
import json
import math
import os
import random
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

RW = Path(os.environ.get("REALWORLD_DIR", "since_cutoff_runs/realworld"))
SC = Path(os.environ.get("CUTOFFNOTES_EXE", "since_cutoff_runs/scan-venv/Scripts/since-cutoff.exe"))
RT = Path(os.environ.get("RUNS_TABLES", HERE.parent / "runs_tables"))
OUT = HERE.parent / "analysis" / "blocksize_breakeven.json"
BLOCKS = RW / "blocks"
CUTOFF = "2026-06-30"
SCOPES = {"imported": ["--scope", "imported", "--per-package", "5"], "used": ["--scope", "used"]}
TIMEOUT = 1800
START, END = "<!-- since-cutoff:start -->", "<!-- since-cutoff:end -->"
B, SEED = 10000, 20261001
P_CR, P_W1H = 0.20, 8.0  # Opus 5.5 $/MTok: cache read, 1h cache write (recompute_cost.PRICES)


def primary_repos():
    meta = json.loads((RW / "repos.json").read_text(encoding="utf-8"))
    chosen = []
    for repo in meta["repos"]:
        slug = repo["full_name"].replace("/", "__")
        data = {}
        for label in ("opus-5-5", "cutoff-2025-07-31"):
            p = RW / "scans" / f"{slug}.{label}.json"
            if p.exists():
                data[label] = json.loads(p.read_text(encoding="utf-8"))
        if len(data) == 2 and all(d.get("_ok") for d in data.values()):
            chosen.append((repo, slug, data["opus-5-5"]))
        if len(chosen) >= 50:
            break
    return chosen


def parse_block(text):
    """Block lines from the dry-run diff ('+' lines between the markers) -> (block text, number of blocks)."""
    blocks, cur = [], None
    for line in text.splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            if cur is not None and not line.startswith("+"):
                pass
            continue
        body = line[1:]
        if body.strip() == START:
            cur = [body]
        elif cur is not None:
            cur.append(body)
            if body.strip() == END:
                blocks.append("\n".join(cur).strip() + "\n"); cur = None
    return (blocks[0] if blocks else ""), len(blocks)


def block_stats(block):
    if not block:
        return {"tokens_est": 0, "chars": 0, "packages": 0, "change_lines": 0, "lines_per_package": []}
    inner = block.split("\n")
    pk, lines, per = 0, 0, []
    for ln in inner:
        if re.match(r"^\*\*[^*]+\*\*", ln):
            pk += 1; per.append(0)
        elif ln.startswith("- ") and per:
            lines += 1; per[-1] += 1
    return {"tokens_est": round(len(block) / 4), "chars": len(block), "packages": pk, "change_lines": lines,
            "lines_per_package": per}


def run_one(slug, scope):
    out_path = BLOCKS / f"{slug}.{scope}.json"
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    env = {k: v for k, v in os.environ.items()
           if not any(s in k.upper() for s in ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL"))}
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [str(SC), "sync", str(RW / "clones" / slug), "--dry-run", "--model", "anthropic:claude-opus-5-5",
           *SCOPES[scope]]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, env=env, timeout=TIMEOUT,
                           cwd=str(BLOCKS))
        rc, so, se = p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
        timeout = False
    except subprocess.TimeoutExpired as e:
        rc, so, se, timeout = None, (e.stdout or b"").decode("utf-8", "replace"), (e.stderr or b"").decode(
            "utf-8", "replace"), True
    secs = round(time.time() - t0, 1)
    block, nblocks = parse_block(so + "\n" + se)
    rec = {"slug": slug, "scope": scope, "command": ["since-cutoff", *cmd[1:2], "<clone>", *cmd[3:]], "exit": rc,
           "timeout": timeout, "seconds": secs, "n_blocks_in_diff": nblocks,
           "nothing_to_write": "--- " not in so and not block,
           "unchecked_packages": len(re.findall(r"could not be checked", so + se)),
           "block": block, **block_stats(block), "stderr_tail": se[-1500:],
           "stdout_head": "\n".join(l for l in so.splitlines() if not l.startswith("+"))[:1500]}
    rec["ok"] = (not timeout) and rc == 0
    out_path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(slug, scope, "exit", rc, f"{secs}s", rec["tokens_est"], "tok", rec["packages"], "pkgs", flush=True)
    return rec


def generate(workers):
    BLOCKS.mkdir(parents=True, exist_ok=True)
    print("tool:", subprocess.run([str(SC), "--version"], capture_output=True, text=True).stdout.strip(), flush=True)
    jobs = [(slug, scope) for _, slug, _ in primary_repos() for scope in SCOPES]
    # longest first (scan seconds), so the big repos do not end up last
    secs = {slug: d.get("_seconds", 0) for _, slug, d in primary_repos()}
    jobs.sort(key=lambda j: -secs[j[0]])
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda j: run_one(*j), jobs))


# ----------------------------------------------------------------------------------------------- analysis

def q(xs):
    xs = sorted(xs)
    if not xs:
        return None
    n = len(xs)

    def pctl(p):  # linear interpolation (numpy default)
        k = (n - 1) * p; f = math.floor(k); c = min(f + 1, n - 1)
        return xs[f] + (xs[c] - xs[f]) * (k - f)
    return {"n": n, "median": statistics.median(xs), "p25": pctl(0.25), "p75": pctl(0.75), "mean": sum(xs) / n,
            "min": xs[0], "max": xs[-1]}


def load(study):
    recs = [json.loads(l) for l in open(RT / study / "runs.jsonl", encoding="utf-8")]
    recs = [r for r in recs if r.get("valid") and not r.get("pilot")]
    seen, out = set(), []
    for r in sorted(recs, key=lambda r: (r["run_id"], r["attempt"])):
        if r["run_id"] not in seen:
            seen.add(r["run_id"]); out.append(r)
    return out


def sessions(studies, stratum="post-cutoff"):
    from recompute_cost import list_cost
    pt = defaultdict(lambda: defaultdict(list))
    for st in studies:
        for r in load(st):
            if (r["stratum"] == "post-cutoff") != (stratum == "post-cutoff") or r["condition"] not in ("A", "C"):
                continue
            res = r.get("result") or {}
            pt[r["task"]][r["condition"]].append({
                "cost": list_cost(r["agent"]["model"], res.get("usage") or {}), "turns": res.get("num_turns") or 0,
                "notes": (r.get("condition_config") or {}).get("notes_tokens") or 0})
    return {t: cs for t, cs in sorted(pt.items()) if cs.get("A") and cs.get("C")}


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def study_terms(pt, idx=None):
    tasks = list(pt)
    sel = [tasks[i] for i in idx] if idx is not None else tasks
    s_net = mean(mean(s["cost"] for s in pt[t]["A"]) - mean(s["cost"] for s in pt[t]["C"]) for t in sel)
    o_bench = mean(mean(s["notes"] * (s["turns"] * P_CR + P_W1H) / 1e6 for s in pt[t]["C"]) for t in sel)
    turns_c = mean(mean(s["turns"] for s in pt[t]["C"]) for t in sel)
    return s_net, o_bench, turns_c


def overhead(T, turns):
    return T * (turns * P_CR + P_W1H) / 1e6


def analyse():
    repos = primary_repos()
    out = {"generated_by": "scripts/blocksize_breakeven.py", "method": __doc__.split("1. Block sizes.")[1].strip(),
           "tool": "since-cutoff 0.5.0 (scan venv; the version used for the exposure scan)",
           "model": "anthropic:claude-opus-5-5", "cutoff": CUTOFF, "repos": len(repos), "block_sizes": {}}
    per_repo = {}
    for repo, slug, scan in repos:
        direct = [p for p in scan.get("scan", []) if p.get("direct")]
        post = [p for p in direct if p.get("locked_date") and p["locked_date"] > CUTOFF]
        imported_changed = [p for p in scan.get("packages", []) if p.get("status") == "changed" and p.get("imported")]
        npv = scan.get("notes_preview") or {}
        row = {"stars": repo["stars"], "direct_deps": len(direct), "direct_locked_after_cutoff": len(post),
               "imported_changed_packages_scan": len(imported_changed), "scan_seconds_cold": scan.get("_seconds"),
               "scan_notes_preview_tokens_est": round(len(npv["block"].strip() + "\n") / 4) if npv.get("block") else 0}
        for scope in SCOPES:
            p = BLOCKS / f"{slug}.{scope}.json"
            if p.exists():
                r = json.loads(p.read_text(encoding="utf-8"))
                row[scope] = {k: r[k] for k in ("ok", "exit", "timeout", "seconds", "tokens_est", "packages",
                                                "change_lines", "unchecked_packages", "n_blocks_in_diff")}
        per_repo[slug] = row
    for scope in SCOPES:
        ok = [r[scope] for r in per_repo.values() if scope in r and r[scope]["ok"]]
        fail = [s for s, r in per_repo.items() if scope not in r or not r[scope]["ok"]]
        ne = [r for r in ok if r["tokens_est"] > 0]
        out["block_sizes"][scope] = {
            "repos_ok": len(ok), "repos_failed_or_timeout": len(fail),
            "failed_detail": [{"exit": per_repo[s].get(scope, {}).get("exit"),
                               "timeout": per_repo[s].get(scope, {}).get("timeout")} for s in fail],
            "repos_with_nonempty_block": len(ne), "share_nonempty": len(ne) / len(ok) if ok else None,
            "tokens_all": q([r["tokens_est"] for r in ok]), "tokens_nonempty": q([r["tokens_est"] for r in ne]),
            "packages_all": q([r["packages"] for r in ok]), "packages_nonempty": q([r["packages"] for r in ne]),
            "change_lines_all": q([r["change_lines"] for r in ok]),
            "change_lines_nonempty": q([r["change_lines"] for r in ne]),
            "seconds": q([r["seconds"] for r in ok]),
            "repos_block_over_423_tokens": sum(r["tokens_est"] > 423 for r in ok),
            "repos_block_over_1000_tokens": sum(r["tokens_est"] > 1000 for r in ok),
            "repos_block_over_2000_tokens": sum(r["tokens_est"] > 2000 for r in ok),
            "repos_block_over_5000_tokens": sum(r["tokens_est"] > 5000 for r in ok),
            "unchecked_packages_total": sum(r["unchecked_packages"] for r in ok)}
    # consistency: used-scope sync block vs the scan's own notes preview (scope used, 2026-10-21/22)
    cmp_ = [(r["used"]["tokens_est"], r["scan_notes_preview_tokens_est"]) for r in per_repo.values()
            if r.get("used", {}).get("ok")]
    out["check_used_scope_vs_scan_preview"] = {
        "repos": len(cmp_), "identical_token_estimate": sum(a == b for a, b in cmp_),
        "both_empty": sum(a == b == 0 for a, b in cmp_),
        "abs_diff": q([abs(a - b) for a, b in cmp_])}
    # C2: post-cutoff direct pins vs packages named in the imported-scope block
    rows = [r for r in per_repo.values() if r.get("imported", {}).get("ok")]
    with_post = [r for r in rows if r["direct_locked_after_cutoff"] > 0]
    out["selection_vs_versions_only"] = {
        "note": "M = direct dependencies locked to a release after 2026-06-30 (scan JSON, realworld_analyze rule); "
                "K = packages named in the imported-scope block (may include imported packages that are not direct "
                "dependencies); a versions-only header (every post-cutoff direct pin) would name M packages",
        "repos": len(rows), "repos_with_post_cutoff_direct_pin": len(with_post),
        "M_post_cutoff_direct_pins": q([r["direct_locked_after_cutoff"] for r in with_post]),
        "K_block_packages": q([r["imported"]["packages"] for r in with_post]),
        "M_minus_K": q([r["direct_locked_after_cutoff"] - r["imported"]["packages"] for r in with_post]),
        "share_named_K_over_M": q([r["imported"]["packages"] / r["direct_locked_after_cutoff"] for r in with_post]),
        "sum_M": sum(r["direct_locked_after_cutoff"] for r in with_post),
        "sum_K": sum(r["imported"]["packages"] for r in with_post),
        "repos_K_zero_but_M_positive": sum(r["imported"]["packages"] == 0 for r in with_post),
        "used_scope_K": q([r["used"]["packages"] for r in with_post if r.get("used", {}).get("ok")])}

    # ------------------------------------------------------------------ break-even
    studies = {"main": (["main-2026-09-28"], "Opus main (17 post-cutoff tasks)"),
               "replication": (["abl-opus55-2026-10-22"], "Opus replication (17)"),
               "new_tasks": (["tasks2-opus55-2026-10-22"], "Opus new tasks (8)"),
               "pooled_main_new": (["main-2026-09-28", "tasks2-opus55-2026-10-22"], "pooled main + new (25)"),
               "pooled_repl_new": (["abl-opus55-2026-10-22", "tasks2-opus55-2026-10-22"], "pooled repl. + new (25)")}
    imp = out["block_sizes"]["imported"]
    sizes = {"benchmark_mean_423": 423}
    if imp["tokens_all"]:
        sizes.update({"real_median_all": imp["tokens_all"]["median"], "real_p75_all": imp["tokens_all"]["p75"],
                      "real_max_all": imp["tokens_all"]["max"]})
    if imp["tokens_nonempty"]:
        sizes.update({"real_median_nonempty": imp["tokens_nonempty"]["median"],
                      "real_p25_nonempty": imp["tokens_nonempty"]["p25"],
                      "real_p75_nonempty": imp["tokens_nonempty"]["p75"]})
    used = out["block_sizes"]["used"]
    if used["tokens_nonempty"]:
        sizes["real_median_nonempty_used_scope"] = used["tokens_nonempty"]["median"]
    be = out["break_even"] = {"prices_usd_per_mtok": {"cache_read": P_CR, "cache_write_1h": P_W1H},
                              "block_sizes_tokens": sizes, "studies": {}}
    ctrl_turns = {}
    for key, (sts, desc) in studies.items():
        pt = sessions(sts)
        s_net, o_bench, turns_c = study_terms(pt)
        cpt = sessions(sts, "controls")
        ctrl_turns[key] = mean(mean(s["turns"] for s in cpt[t]["C"]) for t in cpt) if cpt else None
        rnd = random.Random(SEED)
        n = len(pt)
        draws = []
        for _ in range(B):
            idx = [rnd.randrange(n) for _ in range(n)]
            draws.append(study_terms(pt, idx))
        res = {"description": desc, "tasks": n, "mean_C_turns": turns_c, "mean_C_turns_controls": ctrl_turns[key],
               "S_net_saving_per_affected_session_usd": {"value": s_net,
                                                         "ci95": pct([d[0] for d in draws])},
               "O_bench_block_overhead_usd": o_bench, "S_gross_usd": {"value": s_net + o_bench,
                                                                     "ci95": pct([d[0] + d[1] for d in draws])},
               "by_block_size": {}}
        for name, T in sizes.items():
            o = overhead(T, turns_c)
            ps = [overhead(T, d[2]) / (d[0] + d[1]) if d[0] + d[1] > 0 else float("inf") for d in draws]
            res["by_block_size"][name] = {
                "T_tokens": T, "overhead_per_session_usd": o,
                "overhead_controls_turns_usd": overhead(T, ctrl_turns[key]) if ctrl_turns[key] else None,
                "overhead_24_turns_usd": overhead(T, 24),
                "break_even_share": o / (s_net + o_bench), "break_even_share_ci95": pct(ps),
                "share_draws_never_break_even": sum(p == float("inf") or p > 1 for p in ps) / B,
                "naive_O_over_S_net": o / s_net,
                "break_even_share_controls_turns": (overhead(T, ctrl_turns[key]) / (s_net + o_bench)
                                                    if ctrl_turns[key] else None)}
        be["studies"][key] = res
        print("break-even", key, file=sys.stderr)
    # per-repo break-even under the main study's saving (gross) and turns, for the distribution over repos
    m = be["studies"]["main"]; nt = be["studies"]["new_tasks"]
    per = []
    for r in rows:
        T = r["imported"]["tokens_est"]
        if T > 0:
            per.append({"T": T, "p_main": overhead(T, m["mean_C_turns"]) / m["S_gross_usd"]["value"],
                        "p_new": overhead(T, nt["mean_C_turns"]) / nt["S_gross_usd"]["value"]})
    be["per_repo_nonempty_imported"] = {
        "repos": len(per), "break_even_share_main_saving": q([x["p_main"] for x in per]),
        "break_even_share_new_tasks_saving": q([x["p_new"] for x in per]),
        "repos_break_even_above_50pct_main": sum(x["p_main"] > 0.5 for x in per),
        "repos_break_even_above_100pct_main": sum(x["p_main"] > 1 for x in per),
        "repos_break_even_above_100pct_new": sum(x["p_new"] > 1 for x in per)}
    OUT.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    print("wrote", OUT.name)


def pct(xs):
    xs = sorted(xs)
    return [xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]]


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "generate":
        generate(int(a[a.index("--workers") + 1]) if "--workers" in a else 1)
    elif a and a[0] == "analyse":
        analyse()
    else:
        raise SystemExit(__doc__)
