"""Aggregate the Q3 real-world scans (PROTOCOL_ADDENDUM section 5). First 50 repositories in star order whose scans
succeeded for both cutoffs. Writes analysis/realworld_summary.json (aggregates; repo names only in the raw files).
"""
import json
import os
import statistics
from pathlib import Path

# Folder with repos.json and scans/ (set REALWORLD_DIR; default ./realworld).
RW = Path(os.environ.get("REALWORLD_DIR", "realworld"))
OUT = Path(__file__).resolve().parent.parent / "analysis" / "realworld_summary.json"
LABELS = {"opus-5-5": "2026-06-30", "cutoff-2025-07-31": "2025-07-31"}
N = 50

meta = json.loads((RW / "repos.json").read_text(encoding="utf-8"))
chosen, failed = [], []
for repo in meta["repos"]:
    slug = repo["full_name"].replace("/", "__")
    data = {}
    for label in LABELS:
        p = RW / "scans" / f"{slug}.{label}.json"
        if p.exists():
            data[label] = json.loads(p.read_text(encoding="utf-8"))
    if len(data) == len(LABELS) and all(d.get("_ok") for d in data.values()):
        chosen.append((repo, data))
    elif len(data) == len(LABELS):
        failed.append(repo["full_name"])
    if len(chosen) >= N:
        break


def q(xs):
    xs = sorted(xs)
    if not xs:
        return None
    return {"median": statistics.median(xs), "p25": xs[len(xs) // 4], "p75": xs[(3 * len(xs)) // 4],
            "mean": sum(xs) / len(xs), "max": xs[-1]}


summary = {"repos": len(chosen), "failed_parse": len(failed), "query": meta["query"],
           "selected_at": meta["selected_at"], "examined_in_search": meta["examined"], "by_cutoff": {}}
for label, cutoff in LABELS.items():
    rows = []
    for repo, data in chosen:
        d = data[label]
        direct = [p for p in d.get("scan", []) if p.get("direct")]
        dated = [p for p in direct if p.get("locked_date")]
        post = [p for p in dated if p["locked_date"] > cutoff]
        pk = d.get("packages", [])
        changed_imported = [p for p in pk if p.get("status") == "changed" and p.get("imported")]
        used = d.get("used") or {}
        rows.append({
            "direct_deps": len(direct), "direct_with_date": len(dated),
            "share_direct_locked_after_cutoff": len(post) / len(dated) if dated else 0.0,
            "direct_locked_after_cutoff": len(post),
            "deps_changed": d.get("dependencies_changed", 0),
            "imported_deps_changed": len(changed_imported),
            "breaking_changes": d.get("breaking_changes", 0),
            "breaking_in_imported": sum(p.get("breaking_changes") or 0 for p in changed_imported),
            "used_apis": used.get("apis", 0), "used_changes": used.get("changes", 0),
            "used_files": used.get("files", 0), "used_packages": len(used.get("packages", [])),
        })
    agg = {k: q([r[k] for r in rows]) for k in rows[0]} if rows else {}
    agg["repos_with_any_direct_dep_after_cutoff"] = sum(r["direct_locked_after_cutoff"] > 0 for r in rows)
    agg["repos_with_imported_breaking_change"] = sum(r["imported_deps_changed"] > 0 for r in rows)
    agg["repos_with_used_changed_api"] = sum(r["used_apis"] > 0 for r in rows)
    agg["total_used_changed_apis"] = sum(r["used_apis"] for r in rows)
    summary["by_cutoff"][f"{label} ({cutoff})"] = agg
# secondary (deviation, documented): first 50 repos in star order whose current-cutoff (opus-5-5) scan succeeded,
# regardless of the older-cutoff scan (which timed out on several large AI repositories)
sec = []
for repo in meta["repos"]:
    p = RW / "scans" / f"{repo['full_name'].replace('/', '__')}.opus-5-5.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("_ok"):
            sec.append(d)
    if len(sec) >= N:
        break
cutoff = LABELS["opus-5-5"]
rows = []
for d in sec:
    direct = [p for p in d.get("scan", []) if p.get("direct")]
    dated = [p for p in direct if p.get("locked_date")]
    post = [p for p in dated if p["locked_date"] > cutoff]
    ci = [p for p in d.get("packages", []) if p.get("status") == "changed" and p.get("imported")]
    used = d.get("used") or {}
    rows.append({"direct": len(direct), "post": len(post), "share": len(post) / len(dated) if dated else 0.0,
                 "ci": len(ci), "bi": sum(p.get("breaking_changes") or 0 for p in ci), "used": used.get("apis", 0),
                 "used_pk": used.get("packages", [])})
from collections import Counter
summary["secondary_current_cutoff_only"] = {
    "repos": len(rows), "direct_deps": q([r["direct"] for r in rows]),
    "share_direct_locked_after_cutoff": q([r["share"] for r in rows]),
    "repos_with_any_direct_dep_after_cutoff": sum(r["post"] > 0 for r in rows),
    "repos_with_imported_breaking_change": sum(r["ci"] > 0 for r in rows),
    "breaking_in_imported": q([r["bi"] for r in rows]),
    "repos_with_used_changed_api": sum(r["used"] > 0 for r in rows),
    "total_used_changed_apis": sum(r["used"] for r in rows),
    "packages_behind_used_changes": Counter(pk for r in rows for pk in r["used_pk"]).most_common(15)}
OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
