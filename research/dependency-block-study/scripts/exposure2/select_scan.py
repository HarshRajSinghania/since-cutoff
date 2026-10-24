"""Exposure study 2 driver (EXPOSURE2_PROTOCOL.md sections 2-5). Read-only GitHub API (`gh api`), shallow sparse
clones, static `since-cutoff` scans. Nothing from the repositories is executed.

usage: python -I select_scan.py methodcheck        sparse vs full clone on 3 of the earlier 47 (protocol E2)
       python -I select_scan.py run [--workers 4]  walk the seeded permutation until both strata are full
       python -I select_scan.py blocks              sync --dry-run (imported scope) for the included repositories
       python -I select_scan.py status
Raw outputs under $REALWORLD2_DIR: candidates.jsonl, clones/, scans/, blocks/, cache/w<i>/.
"""
import json
import random
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (AI_EXACT, AI_PREFIX, AUTHOR_OWNER, CLONE_TIMEOUT, CUTOFF, LOCKFILES, MAX_SIZE_KB, MODEL,
                    N_PER_STRATUM, RW1, RW2, SC, SCAN_TIMEOUT, SEED_ORDER, SPARSE, canon, clean_env, is_ai,
                    is_pinned, slug)

CLONES, SCANS, BLOCKS, CACHE = RW2 / "clones", RW2 / "scans", RW2 / "blocks", RW2 / "cache"
CAND = RW2 / "candidates.jsonl"
_lock = threading.Lock()
_tl = threading.local()
_worker_ids = iter(range(1000))


def log(*a):
    s = datetime.now().strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    with _lock, open(RW2 / "run.log", "a", encoding="utf-8") as f:
        f.write(s + "\n")


def worker_cache():
    if not hasattr(_tl, "wid"):
        with _lock:
            _tl.wid = next(_worker_ids)
    d = CACHE / f"w{_tl.wid}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def gh(path):
    for attempt in range(5):
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            return json.loads(r.stdout)
        if "404" in r.stderr or "Not Found" in r.stderr or "empty" in r.stderr.lower():
            return None
        if "rate limit" in r.stderr.lower() or "403" in r.stderr:
            log("rate limit; sleeping 120 s")
            time.sleep(120)
            continue
        time.sleep(5 * (attempt + 1))
    return None


def permutation():
    meta = json.loads((RW2 / "frame.json").read_text(encoding="utf-8"))
    frame = meta["repos"]
    excl = {"fork": 0, "archived": 0, "template": 0, "author": 0, "size": 0}
    keep = []
    for r in frame:
        if r["fork"]:
            excl["fork"] += 1
        elif r["archived"]:
            excl["archived"] += 1
        elif r.get("is_template"):
            excl["template"] += 1
        elif r["owner"] == AUTHOR_OWNER:
            excl["author"] += 1
        elif r["size_kb"] > MAX_SIZE_KB:
            excl["size"] += 1
        else:
            keep.append(r)
    keep.sort(key=lambda r: r["full_name"].lower())
    random.Random(SEED_ORDER).shuffle(keep)
    return keep, excl, meta


def clone(full, dest, sparse=True):
    env = clean_env()
    if dest.exists():
        return True, "exists"
    args = ["git", "clone", "--depth", "1", "--no-tags", "-c", "core.symlinks=false"]
    if sparse:
        args += ["--filter=blob:none", "--sparse"]
    try:
        r = subprocess.run(args + [f"https://github.com/{full}.git", str(dest)], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL, timeout=CLONE_TIMEOUT)
        if r.returncode != 0:
            return False, r.stderr[-400:]
        if sparse:
            r = subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", "--no-cone", *SPARSE],
                               capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
                               timeout=CLONE_TIMEOUT)
            if r.returncode != 0:
                return False, "sparse: " + r.stderr[-400:]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "timeout"


def run_tool(args, timeout, cache, cwd=None):
    env = clean_env({"SINCE_CUTOFF_CACHE": str(cache)})
    t0 = time.time()
    proc = subprocess.Popen([str(SC), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, env=env, cwd=cwd)
    try:
        so, se = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        so, se = proc.communicate()
        rc = None
    return rc, so.decode("utf-8", "replace"), se.decode("utf-8", "replace"), round(time.time() - t0, 1)


def scan(dest, out_path, cache):
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    rc, so, se, secs = run_tool(["scan", str(dest), "--json", "--model", MODEL], SCAN_TIMEOUT, cache)
    if rc is None:
        data = {"_ok": False, "_timeout": True}
    else:
        try:
            data = json.loads(so)
        except json.JSONDecodeError:
            data = {"_parse_error": True}
        data["_ok"] = rc in (0, 3) and "_parse_error" not in data
        data["_timeout"] = False
    data["_exit"], data["_seconds"], data["_stderr_tail"] = rc, secs, se[-1500:]
    out_path.write_text(json.dumps(data), encoding="utf-8")
    return data


DEPFILE_RE = re.compile(r"(pyproject\.toml|requirements.*\.txt|.*\.lock|Pipfile|pylock.*\.toml)$", re.I)


def mentions_ai(dest):
    """Necessary condition for AI-stack: a name on the list appears in a dependency file (incl. lockfiles)."""
    pat = re.compile(r"(?<![a-z0-9-])(" + "|".join(re.escape(n) for n in sorted(AI_EXACT, key=len, reverse=True))
                     + "|" + "|".join(re.escape(p) + r"[a-z0-9-]+" for p in AI_PREFIX) + r")(?![a-z0-9])")
    for p in dest.rglob("*"):
        if p.is_file() and DEPFILE_RE.match(p.name) and ".git" not in p.parts:
            try:
                text = re.sub(r"[-_.]+", "-", p.read_text(encoding="utf-8", errors="replace").lower())
            except OSError:
                continue
            if pat.search(text):
                return True
    return False


def classify(data):
    direct = [e for e in data.get("scan", []) if e.get("direct") and not e.get("reason")]
    checked = [e for e in direct if e.get("locked")]
    pinned = [e for e in checked if is_pinned(e)]
    e4 = bool(pinned) and len(pinned) >= 0.5 * len(checked)
    ai_pk = sorted({canon(e["name"]) for e in data.get("scan", []) if e.get("direct") and e.get("imported")
                    and is_ai(e["name"])})
    return {"e4": e4, "direct_checked": len(checked), "direct_pinned": len(pinned), "ai_stack": bool(ai_pk),
            "ai_packages": ai_pk}


def process(idx, repo, precheck):
    full = repo["full_name"]
    rec = {"idx": idx, "full_name": full, "owner": repo["owner"], "id": repo["id"], "stars": repo["stars"]}
    root = gh(f"repos/{full}/contents/")
    if not isinstance(root, list):
        rec.update(stage="e1", eligible=False, why="root listing failed/empty")
        return rec
    files = {e["name"] for e in root if e.get("type") == "file"}
    dirs = {e["name"] for e in root if e.get("type") == "dir"}
    locks = sorted(f for f in files if f in LOCKFILES or re.fullmatch(r"pylock\..*\.toml", f))
    reqs = sorted(f for f in files if re.fullmatch(r"requirements.*\.txt", f, re.I))
    rec.update(lockfiles=locks, requirements_files=len(reqs), requirements_dir="requirements" in dirs)
    if not (locks or reqs or "requirements" in dirs):
        rec.update(stage="e1", eligible=False, why="no pin source at root")
        return rec
    dest = CLONES / slug(full)
    ok, err = clone(full, dest)
    if not ok:
        rec.update(stage="e2", eligible=False, why="clone failed: " + err[:200])
        return rec
    if precheck and not mentions_ai(dest):
        rec.update(stage="precheck", eligible=None, why="G full; no AI name in dependency files", ai_stack=False)
        return rec
    data = scan(dest, SCANS / f"{slug(full)}.json", worker_cache())
    rec["scan_seconds"] = data.get("_seconds")
    if data.get("_timeout"):
        rec.update(stage="e3", eligible=False, why="scan timeout", timeout=True)
        return rec
    if not data.get("_ok"):
        rec.update(stage="e3", eligible=False, why=f"scan exit {data.get('_exit')}")
        return rec
    c = classify(data)
    rec.update(c)
    rec.update(stage="done", eligible=c["e4"], why="" if c["e4"] else "E4 fewer than half of direct deps pinned")
    return rec


def load_records():
    recs = {}
    if CAND.exists():
        for line in CAND.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            recs[r["idx"]] = r
    return recs


def selection(recs, n_total):
    """First 100 eligible (G) and first 100 eligible AI-stack (AI) within the completed prefix."""
    G, A = [], []
    prefix = 0
    for i in range(n_total):
        if i not in recs:
            break
        prefix = i + 1
        r = recs[i]
        if r.get("eligible"):
            if len(G) < N_PER_STRATUM:
                G.append(i)
            if r.get("ai_stack") and len(A) < N_PER_STRATUM:
                A.append(i)
        if len(G) >= N_PER_STRATUM and len(A) >= N_PER_STRATUM:
            break
    return G, A, prefix


def run(workers):
    for d in (CLONES, SCANS, BLOCKS, CACHE):
        d.mkdir(parents=True, exist_ok=True)
    perm, excl, meta = permutation()
    log("frame", meta["enumerated_union"], "after exclusions", len(perm), excl)
    recs = load_records()
    pending = {}
    i = 0
    with ThreadPoolExecutor(workers) as ex:
        while True:
            G, A, prefix = selection(recs, len(perm))
            if len(G) >= N_PER_STRATUM and len(A) >= N_PER_STRATUM:
                break
            g_full = len(G) >= N_PER_STRATUM
            while len(pending) < workers and i < len(perm):
                if i not in recs:
                    pending[ex.submit(process, i, perm[i], g_full)] = i
                i += 1
            if not pending:
                if i >= len(perm):
                    log("frame exhausted")
                    break
                continue
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for f in done:
                idx = pending.pop(f)
                try:
                    r = f.result()
                except Exception as e:  # noqa: BLE001
                    r = {"idx": idx, "full_name": perm[idx]["full_name"], "stage": "error", "eligible": False,
                         "why": repr(e)[:300]}
                recs[idx] = r
                with _lock, open(CAND, "a", encoding="utf-8") as fo:
                    fo.write(json.dumps(r) + "\n")
                G, A, prefix = selection(recs, len(perm))
                log(f"#{idx} {r['stage']} elig={r.get('eligible')} ai={r.get('ai_stack')} "
                    f"{r.get('scan_seconds', '')}s | G={len(G)} AI={len(A)} prefix={prefix} {r.get('why', '')[:80]}")
        for f in pending:  # let in-flight jobs finish and record them
            pass
    G, A, prefix = selection(recs, len(perm))
    sel = {"G": [recs[i]["full_name"] for i in G], "AI": [recs[i]["full_name"] for i in A], "prefix": prefix,
           "exclusions": excl, "frame_after_exclusions": len(perm), "finished": datetime.now(timezone.utc).isoformat()}
    (RW2 / "selection.json").write_text(json.dumps(sel, indent=1), encoding="utf-8")
    log("selection written", len(G), len(A), "prefix", prefix)


# ------------------------------------------------------------------------------------------------ blocks

def blocks(workers):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from blocksize_breakeven import parse_block, block_stats  # same parser as 0.14
    sel = json.loads((RW2 / "selection.json").read_text(encoding="utf-8"))
    names = sorted(set(sel["G"]) | set(sel["AI"]))
    BLOCKS.mkdir(parents=True, exist_ok=True)

    def one(full):
        out = BLOCKS / f"{slug(full)}.imported.json"
        if out.exists():
            return
        rc, so, se, secs = run_tool(["sync", str(CLONES / slug(full)), "--dry-run", "--model", MODEL, "--scope",
                                     "imported", "--per-package", "5"], SCAN_TIMEOUT, worker_cache(), cwd=str(BLOCKS))
        block, nblocks = parse_block(so + "\n" + se)
        rec = {"exit": rc, "timeout": rc is None, "seconds": secs, "n_blocks_in_diff": nblocks, "block": block,
               **block_stats(block), "unchecked_packages": len(re.findall(r"could not be checked", so + se)),
               "stderr_tail": se[-1500:], "ok": rc == 0}
        out.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        log("block", full, rc, secs, rec["tokens_est"])

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, names))


# ------------------------------------------------------------------------------------------------ method check

def methodcheck():
    """Protocol E2: scan sparse clones of 3 earlier repositories and compare with the earlier full-clone scans."""
    picks = ["openai/openai-python", "BerriAI/litellm", "python-poetry/poetry"]
    out = {}
    d = RW2 / "methodcheck"
    d.mkdir(parents=True, exist_ok=True)
    for full in picks:
        # a full shallow clone and a sparse shallow clone of the same HEAD, scanned with the same tool and cache
        fc, sp = d / (slug(full) + ".full"), d / (slug(full) + ".sparse")
        ok1, _ = clone(full, fc, sparse=False)
        ok2, _ = clone(full, sp, sparse=True)
        h = [subprocess.run(["git", "-C", str(x), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
             for x in (fc, sp)]
        full_clone = fc
        cache = CACHE / "methodcheck"
        res = {}
        for label, path in (("full", full_clone), ("sparse", sp)):
            rc, so, se, secs = run_tool(["scan", str(path), "--json", "--model", MODEL], SCAN_TIMEOUT, cache)
            j = json.loads(so)
            res[label] = {k: j.get(k) for k in ("dependencies_total", "dependencies_checked", "dependencies_changed",
                                                "breaking_changes", "deprecations")}
            res[label]["used"] = {k: v for k, v in (j.get("used") or {}).items() if k != "packages"}
            res[label]["used_apis"] = sorted((u["package"], u["api"], len(u["used_in"])) for u in j.get("used_apis") or [])
            res[label]["imported"] = sorted(p["package"] for p in j.get("packages", []) if p.get("imported"))
        res["same_commit"] = h[0] == h[1]
        res["identical"] = res["full"] == res["sparse"]
        out[full] = res
        log("methodcheck", full, "identical" if res["identical"] else "DIFFERENT")
    (d / "methodcheck.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


def status():
    perm, excl, meta = permutation()
    recs = load_records()
    G, A, prefix = selection(recs, len(perm))
    from collections import Counter
    print("records", len(recs), "G", len(G), "AI", len(A), "prefix", prefix)
    print(Counter(r["stage"] for r in recs.values()))
    print(Counter(r.get("why", "")[:40] for r in recs.values()).most_common(12))


if __name__ == "__main__":
    cmd = sys.argv[1]
    w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
    if cmd == "run":
        run(w)
    elif cmd == "blocks":
        blocks(w)
    elif cmd == "methodcheck":
        methodcheck()
    else:
        status()
