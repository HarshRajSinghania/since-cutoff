"""Exposure study 2, matcher audit (EXPOSURE2_PROTOCOL.md section 7). AI-judged.

usage: python -I audit.py sample      -> $REALWORLD2_DIR/audit/worklist.json (60 hits with full details; raw, has names)
       python -I audit.py summarise   -> <study>/analysis/exposure2.json key "audit" (aggregates only)
Verdicts: $REALWORLD2_DIR/audit/verdicts.json, {"<sample index>": {"verdict": "TP|FP-resolution|FP-diff",
  "affected": "yes|handled|no|", "runtime": "breaks|warns|runs|", "runtime_basis": "snippet|static|",
  "reason": "..."}}; runtime snippet results: $REALWORLD2_DIR/audit/runtime_results.json (runtime_check.py).
"""
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
sys.path.insert(0, str(HERE))
from common import RW2, SEED_AUDIT, SEED_BOOT, canon, is_pinned, slug  # noqa: E402
from analyze import pctl, wilson  # noqa: E402

AUD = RW2 / "audit"
OUT = STUDY / "analysis" / "exposure2.json"
N_AUDIT = 60
B = 10000


def pool():
    sel = json.loads((RW2 / "selection.json").read_text(encoding="utf-8"))
    union = sorted(set(sel["G"]) | set(sel["AI"]))
    items = []
    for full in union:
        data = json.loads((RW2 / "scans" / f"{slug(full)}.json").read_text(encoding="utf-8"))
        pinned = {canon(e["name"]) for e in data.get("scan", []) if is_pinned(e)}
        details = {}
        for e in data.get("scan", []):
            for c in e.get("changes") or []:
                details.setdefault((canon(e["name"]), c.get("path"), c.get("kind"), c.get("parameter")), c)
        for u in data.get("used_apis") or []:
            if canon(u["package"]) not in pinned:
                continue
            ch = []
            for c in u.get("changes") or []:
                d = details.get((canon(u["package"]), u["api"], c.get("kind"), c.get("parameter"))) or {}
                ch.append({"kind": c.get("kind"), "parameter": c.get("parameter"), "form": c.get("form"),
                           "old_signature": d.get("old_signature"), "new_signature": d.get("new_signature"),
                           "hint": d.get("hint"), "moved_to": d.get("moved_to"), "deprecation": d.get("deprecation")})
            items.append({"repository": full, "in_G": full in sel["G"], "in_AI": full in sel["AI"],
                          "package": u["package"], "cutoff_version": u["cutoff_version"], "locked": u["locked"],
                          "api": u["api"], "display": u.get("display"), "tool_form": u.get("form"),
                          "match": u.get("match"), "changes": ch, "used_in": u.get("used_in"),
                          "locations": u.get("locations"), "replacement": u.get("replacement")})
    items.sort(key=lambda r: (r["repository"].lower(), r["package"], r["api"]))
    return items


def sample():
    AUD.mkdir(parents=True, exist_ok=True)
    items = pool()
    idx = sorted(random.Random(SEED_AUDIT).sample(range(len(items)), min(N_AUDIT, len(items))))
    work = [{"i": k, **items[j]} for k, j in enumerate(idx)]
    (AUD / "worklist.json").write_text(json.dumps({"pool": len(items), "pool_repos": len({r["repository"] for r in items}),
                                                   "sampled": work}, indent=1), encoding="utf-8")
    print("pool", len(items), "sampled", len(work), "repos in sample", len({w["repository"] for w in work}))


def cluster_boot(entries, stat):
    groups = defaultdict(list)
    for e in entries:
        groups[e["repository"]].append(e)
    keys = sorted(groups)
    rng = random.Random(SEED_BOOT)
    vals = []
    for _ in range(B):
        s = []
        for _k in keys:
            s += groups[keys[rng.randrange(len(keys))]]
        vals.append(stat(s))
    vals.sort()
    return [round(pctl(vals, .025), 4), round(pctl(vals, .975), 4)]


def prop(k, n, entries, pred):
    return {"k": k, "n": n, "share": round(k / n, 4) if n else None, "wilson95": wilson(k, n),
            "repo_cluster_boot95": cluster_boot(entries, lambda s: sum(pred(e) for e in s) / len(s))}


def summarise():
    w = json.loads((AUD / "worklist.json").read_text(encoding="utf-8"))
    v = json.loads((AUD / "verdicts.json").read_text(encoding="utf-8"))
    rt = json.loads((AUD / "runtime_results.json").read_text(encoding="utf-8")) if (AUD / "runtime_results.json").exists() else {}
    es = []
    for item in w["sampled"]:
        lab = v[str(item["i"])]
        es.append({**item, **lab})
    n = len(es)
    tp = [e for e in es if e["verdict"] == "TP"]
    is_tp = lambda e: e["verdict"] == "TP"  # noqa: E731
    repos = sorted({e["repository"] for e in es})
    per_repo = Counter(e["repository"] for e in es)
    out = {
        "label": "AI-judged (Claude Opus 5.5 in Claude Code; no human re-check)",
        "pool_hits": w["pool"], "pool_repos": w["pool_repos"], "audited": n, "audited_repos": len(repos),
        "max_audited_hits_per_repo": max(per_repo.values()),
        "audited_hits_per_repo": sorted(per_repo.values(), reverse=True),
        "stratum_membership": {"G_only": sum(e["in_G"] and not e["in_AI"] for e in es),
                               "AI_only": sum(e["in_AI"] and not e["in_G"] for e in es),
                               "both": sum(e["in_G"] and e["in_AI"] for e in es)},
        "precision": prop(len(tp), n, es, is_tp),
        "verdicts": Counter(e["verdict"] for e in es),
        "tp_affected": Counter(e.get("affected") for e in tp),
        "runtime_over_audited": {c: prop(sum(e.get("runtime") == c for e in es), n, es,
                                         (lambda c: lambda e: e.get("runtime") == c)(c))
                                 for c in ("breaks", "warns", "runs")},
        "runtime_basis_tp": Counter(e.get("runtime_basis") for e in tp),
        "runtime_snippets_run": len(rt),
        "runtime_snippet_outcomes": Counter(r.get("outcome") for r in rt.values()),
        "repos_with_tp": sum(any(is_tp(e) for e in es if e["repository"] == r) for r in repos),
        "repos_with_runtime_break": sum(any(e.get("runtime") == "breaks" for e in es if e["repository"] == r)
                                        for r in repos),
        "repos_with_old_form_use": sum(any(e.get("affected") == "yes" for e in es if e["repository"] == r)
                                       for r in repos),
        "tool_old_form_labels": sum(e["tool_form"] == "old_form" for e in es),
        "old_form_labels_correct": sum(e["tool_form"] == "old_form" and e.get("affected") == "yes" for e in es),
        "packages_in_sample": Counter(canon(e["package"]) for e in es).most_common(),
        # sensitivity (exploratory): drop the repository with the most audited hits; repository-weighted mean
        "precision_excluding_largest_cluster": (lambda rest: {"k": sum(is_tp(e) for e in rest), "n": len(rest),
                                                              "share": round(sum(is_tp(e) for e in rest) / len(rest), 4),
                                                              "wilson95": wilson(sum(is_tp(e) for e in rest), len(rest))})(
            [e for e in es if e["repository"] != per_repo.most_common(1)[0][0]]),
        "precision_repo_weighted_mean": round(sum(sum(is_tp(e) for e in es if e["repository"] == r) / per_repo[r]
                                                  for r in repos) / len(repos), 4),
        "breaks_zero_of_n_upper95_rule_of_three": round(3 / n, 4),
        "change_kinds_in_sample": Counter(c["kind"] for e in es for c in e["changes"]).most_common(),
    }
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    old["audit"] = out
    OUT.write_text(json.dumps(old, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    {"sample": sample, "summarise": summarise}[sys.argv[1]]()
