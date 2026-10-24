"""Exposure study 2 analysis (EXPOSURE2_PROTOCOL.md section 6). Aggregates only (no repository names) ->
<study>/analysis/exposure2.json (key "exposure"; the audit script adds key "audit").

usage: python -I analyze.py
"""
import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from math import sqrt
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
sys.path.insert(0, str(HERE))
from common import CUTOFF, N_PER_STRATUM, RW1, RW2, SEED_BOOT, canon, is_pinned, slug  # noqa: E402

OUT = STUDY / "analysis" / "exposure2.json"
B = 10000


def wilson(k, n, z=1.959964):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def pctl(xs, p):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    k = (n - 1) * p
    f = math.floor(k)
    c = min(f + 1, n - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def q(xs):
    xs = list(xs)
    if not xs:
        return None
    return {"n": len(xs), "median": statistics.median(xs), "p25": pctl(xs, .25), "p75": pctl(xs, .75),
            "mean": round(sum(xs) / len(xs), 3), "min": min(xs), "max": max(xs)}


def repo_row(data, block=None):
    scan = data.get("scan", [])
    pinned_names = {canon(e["name"]) for e in scan if is_pinned(e)}
    direct = [e for e in scan if e.get("direct") and not e.get("reason") and e.get("locked")]
    pdirect = [e for e in direct if is_pinned(e)]
    post = [e for e in pdirect if (e.get("locked_date") or "") > CUTOFF]
    pk = data.get("packages", [])
    brk = [p for p in pk if p.get("status") == "changed" and p.get("imported") and (p.get("breaking_changes") or 0) > 0]
    brk_p = [p for p in brk if canon(p["package"]) in pinned_names]
    chg_imp = [p for p in pk if p.get("status") == "changed" and p.get("imported")]
    used = data.get("used_apis") or []
    used_p = [u for u in used if canon(u["package"]) in pinned_names]
    npv = data.get("notes_preview") or {}
    row = {
        "direct": len(direct), "direct_pinned": len(pdirect), "post_pins": len(post),
        "share_post": len(post) / len(pdirect) if pdirect else 0.0,
        "P1": len(post) > 0,
        "P2": len(brk_p) > 0, "P2b": len(chg_imp) > 0, "P2c": len(brk) > 0,
        "breaking_in_imported": sum(p.get("breaking_changes") or 0 for p in brk_p),
        "imported_breaking_packages": len(brk_p),
        "P3": len(used_p) > 0, "P3_all": len(used) > 0,
        "used_apis": len(used_p), "used_changes": sum(len(u.get("changes") or []) for u in used_p),
        "used_packages": sorted({canon(u["package"]) for u in used_p}),
        "used_scope_tokens": round(len(npv["block"].strip() + "\n") / 4) if npv.get("block") else 0,
        "scan_seconds": data.get("_seconds"),
        "lockfile": data.get("version_source", "").split(",")[0].strip(),
    }
    if block is not None:
        row.update({"block_ok": bool(block.get("ok")), "block_tokens": block.get("tokens_est", 0),
                    "block_packages": block.get("packages", 0), "block_lines": block.get("change_lines", 0),
                    "block_seconds": block.get("seconds")})
    return row


def boot(rows, owners, stat, seed=SEED_BOOT, b=B):
    """Owner-cluster percentile bootstrap of stat(rows)."""
    groups = defaultdict(list)
    for r, o in zip(rows, owners):
        groups[o].append(r)
    keys = sorted(groups)
    rng = random.Random(seed)
    vals = []
    for _ in range(b):
        sample = []
        for _k in range(len(keys)):
            sample += groups[keys[rng.randrange(len(keys))]]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    vals.sort()
    return [round(pctl(vals, .025), 4), round(pctl(vals, .975), 4)]


def share(key):
    return lambda rows: sum(bool(r[key]) for r in rows) / len(rows)


def med(key, nonempty=None):
    def f(rows):
        xs = [r[key] for r in rows if (nonempty is None or r[nonempty] > 0)]
        return statistics.median(xs) if xs else None
    return f


def summarise(rows, owners, with_blocks=True):
    n = len(rows)
    out = {"n": n, "owners": len(set(owners)), "max_repos_per_owner": max(Counter(owners).values()) if owners else 0}
    for key, label in (("P1", "post_cutoff_direct_pin"), ("P2", "imports_package_with_breaking_change"),
                       ("P2b", "imports_changed_package_earlier_definition"),
                       ("P2c", "imports_breaking_incl_unpinned"), ("P3", "matcher_hit_changed_api_used"),
                       ("P3_all", "matcher_hit_incl_unpinned")):
        k = sum(bool(r[key]) for r in rows)
        out[label] = {"k": k, "share": round(k / n, 4), "wilson95": wilson(k, n),
                      "owner_cluster_boot95": boot(rows, owners, share(key))}
    out["direct_deps"] = q(r["direct"] for r in rows)
    out["direct_pinned"] = q(r["direct_pinned"] for r in rows)
    out["share_pinned_direct_locked_after_cutoff"] = q(r["share_post"] for r in rows)
    out["share_pinned_direct_locked_after_cutoff"]["median_boot95"] = boot(rows, owners, med("share_post"))
    out["post_pins_per_repo"] = q(r["post_pins"] for r in rows)
    out["breaking_in_imported"] = q(r["breaking_in_imported"] for r in rows)
    out["breaking_in_imported"]["median_boot95"] = boot(rows, owners, med("breaking_in_imported"))
    out["matched_apis_total"] = sum(r["used_apis"] for r in rows)
    out["matched_changes_total"] = sum(r["used_changes"] for r in rows)
    out["matched_apis_per_hit_repo"] = q(r["used_apis"] for r in rows if r["used_apis"])
    out["packages_behind_matches"] = Counter(p for r in rows for p in r["used_packages"]).most_common(15)
    out["used_scope_tokens_nonempty"] = q(r["used_scope_tokens"] for r in rows if r["used_scope_tokens"])
    out["used_scope_nonempty_share"] = round(sum(r["used_scope_tokens"] > 0 for r in rows) / n, 4)
    out["scan_seconds"] = q(r["scan_seconds"] for r in rows if r["scan_seconds"] is not None)
    out["version_sources"] = Counter(r["lockfile"] for r in rows).most_common()
    if with_blocks and all("block_tokens" in r for r in rows):
        ok = [r for r in rows if r["block_ok"]]
        bo = [o for r, o in zip(rows, owners) if r["block_ok"]]
        ne = [r for r in ok if r["block_tokens"] > 0]
        out["block_imported_scope"] = {
            "ok": len(ok), "failed_or_timeout": n - len(ok),
            "nonempty": {"k": len(ne), "share": round(len(ne) / len(ok), 4) if ok else None,
                         "wilson95": wilson(len(ne), len(ok)),
                         "owner_cluster_boot95": boot(ok, bo, lambda rs: sum(r["block_tokens"] > 0 for r in rs) / len(rs))},
            "tokens_all": q(r["block_tokens"] for r in ok),
            "tokens_nonempty": q(r["block_tokens"] for r in ne),
            "tokens_nonempty_median_boot95": boot(ok, bo, med("block_tokens", "block_tokens")),
            "tokens_all_median_boot95": boot(ok, bo, med("block_tokens")),
            "packages_nonempty": q(r["block_packages"] for r in ne),
            "change_lines_nonempty": q(r["block_lines"] for r in ne),
            "repos_over_423_1000_2000_5000": [sum(r["block_tokens"] > t for r in ok) for t in (423, 1000, 2000, 5000)],
            "seconds": q(r["block_seconds"] for r in ok if r["block_seconds"] is not None),
        }
    return out


def diff_boot(ra, oa, rb, ob, stat):
    """AI - G difference, independent owner-cluster resampling within each stratum."""
    def resampler(rows, owners, seed):
        groups = defaultdict(list)
        for r, o in zip(rows, owners):
            groups[o].append(r)
        keys = sorted(groups)
        rng = random.Random(seed)

        def draw():
            s = []
            for _ in keys:
                s += groups[keys[rng.randrange(len(keys))]]
            return s
        return draw
    da, db = resampler(ra, oa, SEED_BOOT), resampler(rb, ob, SEED_BOOT + 1)
    vals = sorted(stat(da()) - stat(db()) for _ in range(B))
    return {"diff": round(stat(ra) - stat(rb), 4), "boot95": [round(pctl(vals, .025), 4), round(pctl(vals, .975), 4)]}


def reason(c):
    """Failure category without repository names or paths."""
    why = c.get("why") or "eligible"
    if why.startswith("clone failed"):
        if "invalid path" in why:
            return "clone failed: path invalid on Windows"
        if "too long" in why.lower() or "unable to create file" in why:
            return "clone failed: path too long on Windows"
        return "clone failed: other"
    return why[:60]


def main():
    sel = json.loads((RW2 / "selection.json").read_text(encoding="utf-8"))
    frame = json.loads((RW2 / "frame.json").read_text(encoding="utf-8"))
    cands = [json.loads(l) for l in (RW2 / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    cands = {c["idx"]: c for c in cands}
    by_name = {c["full_name"]: c for c in cands.values()}
    prefix = sel["prefix"]
    walked = [cands[i] for i in range(prefix)]

    def rows_for(names):
        rows, owners = [], []
        for full in names:
            data = json.loads((RW2 / "scans" / f"{slug(full)}.json").read_text(encoding="utf-8"))
            bp = RW2 / "blocks" / f"{slug(full)}.imported.json"
            block = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else None
            rows.append(repo_row(data, block))
            owners.append(full.split("/")[0].lower())
        return rows, owners

    rg, og = rows_for(sel["G"])
    ra, oa = rows_for(sel["AI"])
    res = {
        "protocol": "expansion/EXPOSURE2_PROTOCOL.md",
        "protocol_sha256": hashlib.sha256((STUDY / "expansion" / "EXPOSURE2_PROTOCOL.md").read_bytes()).hexdigest(),
        "tool": "since-cutoff 0.5.0 (scan venv)", "model": "anthropic:claude-opus-5-5", "cutoff": CUTOFF,
        "frame": {"query": frame["base_query"], "enumerated_at": frame["finished"],
                  "total_count_unpartitioned": frame["total_count_unpartitioned"],
                  "sum_slice_counts": frame["sum_slice_counts"], "enumerated_union": frame["enumerated_union"],
                  "slices": len(frame["slices"]), "exclusions_before_sampling": sel["exclusions"],
                  "after_exclusions": sel["frame_after_exclusions"]},
        "walk": {"candidates_walked": prefix,
                 "stage_counts": Counter(c["stage"] for c in walked),
                 "reasons": Counter(reason(c) for c in walked).most_common(),
                 "eligible": sum(bool(c.get("eligible")) for c in walked),
                 "eligible_ai_stack": sum(bool(c.get("eligible")) and bool(c.get("ai_stack")) for c in walked),
                 "scan_timeouts": sum(bool(c.get("timeout")) for c in walked)},
        "strata_overlap": len(set(sel["G"]) & set(sel["AI"])),
        "union_size": len(set(sel["G"]) | set(sel["AI"])),
    }
    # AI share among the first eligible (G) and among all eligible scanned in the walk
    g_ai = sum(bool(by_name[n].get("ai_stack")) for n in sel["G"])
    res["ai_stack_share_in_G"] = {"k": g_ai, "n": len(sel["G"]), "share": round(g_ai / len(sel["G"]), 4),
                                  "wilson95": wilson(g_ai, len(sel["G"]))}
    res["strata"] = {"G": summarise(rg, og), "AI": summarise(ra, oa)}
    res["AI_minus_G"] = {lab: diff_boot(ra, oa, rg, og, share(k)) for k, lab in
                         (("P1", "post_cutoff_direct_pin"), ("P2", "imports_package_with_breaking_change"),
                          ("P3", "matcher_hit_changed_api_used"))}
    # G members that are not AI-stack (descriptive)
    nonai = [(r, o) for r, o, n in zip(rg, og, sel["G"]) if not by_name[n].get("ai_stack")]
    if nonai:
        res["strata"]["G_non_ai_subset"] = summarise([r for r, _ in nonai], [o for _, o in nonai], with_blocks=True)

    # timeout sensitivity (protocol 6.5): timed-out candidates in the walk before each stratum filled
    def pos_of(names):
        return max(by_name[n]["idx"] for n in names)
    tg = [c for c in walked if c.get("timeout") and c["idx"] < pos_of(sel["G"])]
    ta = [c for c in walked if c.get("timeout") and c["idx"] < pos_of(sel["AI"])]
    sens = {}
    for lab, rows, touts in (("G", rg, tg), ("AI", ra, ta)):
        n, k_t = len(rows), len(touts)
        sens[lab] = {"timeouts_before_filled": k_t}
        for key in ("P1", "P2", "P3"):
            k = sum(bool(r[key]) for r in rows)
            sens[lab][key] = {"all_exposed": round((k + k_t) / (n + k_t), 4), "none_exposed": round(k / (n + k_t), 4)}
    res["timeout_sensitivity"] = sens

    # the earlier 47 under the same definitions (descriptive comparison)
    sys.path.insert(0, str(STUDY / "scripts"))
    import os
    os.environ.setdefault("REALWORLD_DIR", str(RW1))
    from blocksize_breakeven import primary_repos
    r47, o47 = [], []
    for repo, sl, data in primary_repos():
        bp = RW1 / "blocks" / f"{sl}.imported.json"
        block = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else None
        r47.append(repo_row(data, block))
        o47.append(repo["full_name"].split("/")[0].lower())
    res["earlier_47_same_definitions"] = summarise(r47, o47)
    res["overlap_with_earlier_47"] = len({repo["full_name"] for repo, _, _ in primary_repos()}
                                         & (set(sel["G"]) | set(sel["AI"])))
    for lab, rows in (("G", rg), ("AI", ra)):
        res["strata"][lab]["stars"] = q(by_name[n]["stars"] for n in sel[lab])

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    old["exposure"] = res
    OUT.write_text(json.dumps(old, indent=1, default=lambda o: dict(o) if isinstance(o, Counter) else str(o)),
                   encoding="utf-8")
    print(json.dumps(res, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
