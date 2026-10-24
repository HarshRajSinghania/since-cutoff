"""Exposure study 2 (expansion/EXPOSURE2_PROTOCOL.md section 2): enumerate the sampling frame through the GitHub
search API (read-only `gh api`), partitioned by star ranges (then creation dates) so each slice has <= 1,000 results.

usage: python -I frame.py   -> $REALWORLD2_DIR/frame.json (repository names; raw, not for the paper)
"""
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUT = Path(os.environ.get("REALWORLD2_DIR", "since_cutoff_runs/realworld2"))
BASE = "language:Python pushed:>=2026-07-25 archived:false"
MIN_STARS = 200
SLEEP = 2.2  # search API: 30 requests / minute
LOG = OUT / "frame.log"


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def search(q, page=1, per_page=100):
    for attempt in range(8):
        time.sleep(SLEEP)
        r = subprocess.run(["gh", "api", "-X", "GET", "search/repositories", "-f", f"q={q}", "-f",
                            f"per_page={per_page}", "-f", f"page={page}", "-f", "sort=stars", "-f", "order=desc"],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            return json.loads(r.stdout)
        log("search error, retry", attempt, q, page, r.stderr[:300])
        time.sleep(30 * (attempt + 1))
    raise RuntimeError(f"search failed: {q} page {page}")


def count(q):
    return search(q, per_page=1)["total_count"]


def slices():
    """Yield (query, total_count) slices with total_count <= 1000."""
    # star upper bound: find the max stars
    top = search(f"{BASE} stars:>={MIN_STARS}", per_page=1)["items"][0]["stargazers_count"]
    stack = [(MIN_STARS, top + 1)]
    while stack:
        lo, hi = stack.pop()
        q = f"{BASE} stars:{lo}..{hi}"
        n = count(q)
        log("slice", q, n)
        if n <= 1000:
            if n:
                yield q, n
        elif hi > lo:
            mid = (lo + hi) // 2
            stack += [(mid + 1, hi), (lo, mid)]
        else:  # one star value with > 1000 repos: split by creation date
            yield from date_slices(q, date(2008, 1, 1), date(2026, 10, 24))


def date_slices(q, a, b):
    n = count(f"{q} created:{a.isoformat()}..{b.isoformat()}")
    log("dslice", q, a, b, n)
    if n <= 1000 or (b - a).days <= 1:
        if n:
            yield f"{q} created:{a.isoformat()}..{b.isoformat()}", n
        return
    m = a + (b - a) / 2
    yield from date_slices(q, a, m)
    yield from date_slices(q, m + timedelta(days=1), b)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    total_query = f"{BASE} stars:>={MIN_STARS}"
    total = count(total_query)
    repos, slice_meta = {}, []
    for q, n in slices():
        got = 0
        for page in range(1, (min(n, 1000) - 1) // 100 + 2):
            res = search(q, page=page)
            for it in res.get("items", []):
                got += 1
                repos[it["id"]] = {"id": it["id"], "full_name": it["full_name"], "owner": it["owner"]["login"],
                                   "stars": it["stargazers_count"], "fork": it["fork"], "archived": it["archived"],
                                   "is_template": it.get("is_template", False), "size_kb": it["size"],
                                   "pushed_at": it["pushed_at"], "created_at": it["created_at"],
                                   "default_branch": it["default_branch"], "language": it["language"]}
            if len(res.get("items", [])) < 100:
                break
        slice_meta.append({"query": q, "total_count": n, "enumerated": got})
        log("enumerated", q, got, "of", n, "union", len(repos))
    meta = {"base_query": total_query, "started": started, "finished": datetime.now(timezone.utc).isoformat(),
            "total_count_unpartitioned": total, "sum_slice_counts": sum(s["total_count"] for s in slice_meta),
            "enumerated_union": len(repos), "slices": slice_meta, "repos": sorted(repos.values(),
                                                                                   key=lambda r: r["full_name"].lower())}
    (OUT / "frame.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    log("done", total, meta["sum_slice_counts"], len(repos))


if __name__ == "__main__":
    main()
