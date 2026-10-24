"""Q4 (exploratory): static breaking-change count vs probed stale rate per library, from since-cutoff `run` reports
in ~/projects/since-cutoff-bench/runs/<model>.json (36-library ai-stack). Spearman rho with a permutation p-value
(20,000 permutations, seed 20261021); also a package-level logistic-free check: stale rate among packages above vs
below the median static count. Writes analysis/static_vs_probe.json.
"""
import json
import math
import random
from pathlib import Path

RUNS = Path.home() / "projects" / "since-cutoff-bench" / "runs"
OUT = Path(__file__).resolve().parent.parent / "analysis" / "static_vs_probe.json"


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


def spearman(x, y, perms=20000, seed=20261021):
    rx, ry = ranks(x), ranks(y)
    rho = pearson(rx, ry)
    rnd = random.Random(seed)
    hits = 0
    ry2 = ry[:]
    for _ in range(perms):
        rnd.shuffle(ry2)
        if abs(pearson(rx, ry2)) >= abs(rho) - 1e-12:
            hits += 1
    return rho, (hits + 1) / (perms + 1)


res = {}
pooled_x, pooled_y = [], []
for f in sorted(RUNS.glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    pk = [p for p in d["packages"] if (p.get("probed") or 0) > 0]
    if not pk:
        continue
    x = [math.log1p(p["breaking_changes"] or 0) for p in pk]
    y = [(p["stale"] or 0) / p["probed"] for p in pk]
    rho, pval = spearman(x, y)
    med = sorted(x)[len(x) // 2]
    hi = [p for p, xi in zip(pk, x) if xi >= med]; lo = [p for p, xi in zip(pk, x) if xi < med]
    rate = lambda ps: sum(p["stale"] for p in ps) / max(1, sum(p["probed"] for p in ps))
    res[d["model"]] = {"cutoff": d["cutoff"], "packages_probed": len(pk), "probes": d["probes"],
                       "spearman_rho_logbreaking_vs_stale_rate": rho, "perm_p": pval,
                       "stale_rate_high_static_half": rate(hi), "stale_rate_low_static_half": rate(lo),
                       "probes_per_package_mean": sum(p["probed"] for p in pk) / len(pk)}
    pooled_x += x; pooled_y += y
if pooled_x:
    rho, pval = spearman(pooled_x, pooled_y)
    res["pooled_package_model_pairs"] = {"n": len(pooled_x), "spearman_rho": rho, "perm_p": pval,
                                         "note": "pairs are not independent across models"}
OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
print(json.dumps(res, indent=2))
