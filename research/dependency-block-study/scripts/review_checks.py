"""Post hoc and descriptive statistics added after the reviews (2026-10-22): sign-flip tests on per-task log ratios,
t intervals, task-paired differences between studies, power (smallest detectable ratio), the post hoc combined Opus
estimate, the header's share of the token saving, bills per session, Sonnet cost per solved task, exact lower bounds
for zero control failures, and a repository-clustered bootstrap of the audit precision.

usage: python -I review_checks.py <I1 dir> <runs dir>   (runs dir = the supplement's runs/ or I1/runs_tables)
"""
import csv, itertools, json, math, random, statistics, sys
from collections import defaultdict
from pathlib import Path

I1 = Path(sys.argv[1])
sys.path.insert(0, str(I1 / "scripts"))
from recompute_cost import load, metrics  # noqa

RUNS = Path(sys.argv[2])
S = {
    "main": RUNS / "main-2026-09-28",
    "repl": RUNS / "abl-opus55-2026-10-22",
    "sonnet": RUNS / "gen-sonnet55-2026-10-21",
    "haiku": RUNS / "gen-haiku55-2026-10-21",
    "new": RUNS / "tasks2-opus55-2026-10-22",
}
PILOT = {"ant01", "mcp01"}


def logratios(name, metric, treat="C", ctrl="A", excl=()):
    d = S[name]
    pt = defaultdict(lambda: defaultdict(list))
    for r in load(d):
        if r["stratum"] != "post-cutoff" or r["task"] in excl:
            continue
        pt[r["task"]][r["condition"]].append(metrics(r, d)[metric])
    out = {}
    for t, cs in pt.items():
        if cs.get(treat) and cs.get(ctrl):
            out[t] = math.log(statistics.median(cs[treat]) / statistics.median(cs[ctrl]))
    return out


def boot(xs, B=10000, seed=20261001):
    rnd = random.Random(seed)
    bs = sorted(sum(rnd.choice(xs) for _ in xs) / len(xs) for _ in range(B))
    return bs[int(0.025 * B)], bs[int(0.975 * B) - 1]


def signflip(xs):
    xs = [x for x in xs if x != 0]
    n = len(xs); obs = abs(sum(xs))
    if n > 20:
        rnd = random.Random(1); k = 200000
        c = sum(1 for _ in range(k) if abs(sum(x if rnd.random() < .5 else -x for x in xs)) >= obs - 1e-12)
        return c / k
    c = sum(1 for s in itertools.product([1, -1], repeat=n) if abs(sum(a * b for a, b in zip(s, xs))) >= obs - 1e-12)
    return c / 2 ** n


def tci(xs):
    n = len(xs); m = sum(xs) / n; sd = statistics.stdev(xs); se = sd / math.sqrt(n)
    tcrit = {7: 2.365, 8: 2.306, 16: 2.120, 24: 2.064, 22: 2.074}.get(n - 1, 2.0)
    return math.exp(m - tcrit * se), math.exp(m + tcrit * se), se


def show(label, xs):
    m = sum(xs) / len(xs); lo, hi = boot(xs); tl, th, se = tci(xs)
    print(f"{label}: ratio {math.exp(m):.3f} boot [{math.exp(lo):.3f},{math.exp(hi):.3f}] t [{tl:.3f},{th:.3f}] se {se:.3f} signflip p {signflip(xs):.4f} n {len(xs)}")


for metric in ("total_tokens", "list_cost_usd"):
    print("==", metric)
    L = {k: logratios(k, metric) for k in S}
    for k in S:
        show(k, list(L[k].values()))
    for small in ("sonnet", "haiku"):
        common = sorted(set(L["main"]) & set(L[small]))
        show(f"interaction main/{small}", [L["main"][t] - L[small][t] for t in common])
    common = sorted(set(L["main"]) & set(L["repl"]))
    show("main/repl", [L["main"][t] - L["repl"][t] for t in common])
    comb = [(L["main"][t] + L["repl"][t]) / 2 for t in common] + list(L["new"].values())
    show("combined opus (post hoc)", comb)
    show("pool main+new", list(L["main"].values()) + list(L["new"].values()))
    show("pool repl+new", list(L["repl"].values()) + list(L["new"].values()))

# MDE: 80% power, alpha .05 two-sided, normal approx: exp(-(1.96+0.84)*se)
for k in ("sonnet", "haiku"):
    xs = list(logratios(k, "total_tokens").values())
    se = statistics.stdev(xs) / math.sqrt(len(xs))
    print(k, "MDE tokens ratio", round(math.exp(-(1.96 + 0.8416) * se), 3), "se", round(se, 3))

# covered new tasks: per-task token ratios
L = logratios("new", "total_tokens")
print("new covered", {t: round(math.exp(L[t]), 3) for t in ("pl02", "st01")})

# share reproduced by H, contemporaneous pool (repl + new)
for excl in ((), tuple(PILOT)):
    for metric in ("total_tokens",):
        h = {**logratios("repl", metric, "H", "A", excl), **logratios("new", metric, "H", "A", excl)}
        c = {**logratios("repl", metric, "C", "A", excl), **logratios("new", metric, "C", "A", excl)}
        ts = sorted(set(h) & set(c))
        share = sum(h[t] for t in ts) / sum(c[t] for t in ts)
        print("H share", metric, "excl" if excl else "all", round(share, 2))

# Absolute: bill per session
for k, n in (("main", 72), ("repl", 51), ("new", 33)):
    d = S[k]; tot = defaultdict(float); cnt = defaultdict(int)
    for r in load(d):
        m = metrics(r, d); tot[r["condition"]] += m["list_cost_usd"]; cnt[r["condition"]] += 1
    print(k, {c: (round(tot[c], 2), cnt[c], round(tot[c] / cnt[c], 3)) for c in sorted(tot)})

# Sonnet cost per solved post-cutoff task
d = S["sonnet"]; tot = defaultdict(float); ps = defaultdict(int)
for r in load(d):
    if r["stratum"] != "post-cutoff":
        continue
    m = metrics(r, d); tot[r["condition"]] += m["list_cost_usd"]; ps[r["condition"]] += m["passed"]
print("sonnet cost/solved", {c: round(tot[c] / ps[c], 3) for c in tot})

# Exact lower bounds, zero failures
for n in (21, 9, 30):
    print("exact lower bound n", n, round(0.05 ** (1 / n), 3))

# Audit precision, repository-clustered bootstrap
rows = list(csv.DictReader(open(I1 / "analysis" / "realworld_audit.csv", encoding="utf-8")))
by = defaultdict(lambda: [0, 0])
for r in rows:
    by[r["repository"]][0] += r["verdict"] == "TP"; by[r["repository"]][1] += 1
reps = list(by.values()); rnd = random.Random(20261001); bs = []
for _ in range(10000):
    s = [rnd.choice(reps) for _ in reps]; bs.append(sum(a for a, _ in s) / sum(b for _, b in s))
bs.sort()
print("audit precision", sum(a for a, _ in reps) / sum(b for _, b in reps), "cluster boot", bs[250], bs[9749], "repos", len(reps))

# Main-study cost ratio at the Bonferroni level for the four-metric efficiency rule (98.75% percentile CI)
xs = list(logratios("main", "list_cost_usd").values())
rnd = random.Random(20261001); B = 10000
bs = sorted(math.exp(sum(rnd.choice(xs) for _ in xs) / len(xs)) for _ in range(B))
print("main cost 98.75% CI", round(bs[int(0.00625 * B)], 3), round(bs[int(0.99375 * B) - 1], 3))
