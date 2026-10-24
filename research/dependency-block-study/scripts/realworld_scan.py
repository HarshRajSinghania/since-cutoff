"""Q3 (PROTOCOL_ADDENDUM section 5): static since-cutoff scans of real public Python repositories. No model calls,
no code from the repositories is executed (shallow clone + since-cutoff's static parser/diff only).

usage: python -I realworld_scan.py select   -> repos.json (GitHub search, first 50 with uv.lock/poetry.lock)
       python -I realworld_scan.py scan     -> scans/<owner__name>.<label>.json for each repo and cutoff
Outputs under $REALWORLD_DIR (default ./realworld); the tool executable is $CUTOFFNOTES_EXE.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(os.environ.get("REALWORLD_DIR", "realworld"))
CLONES = OUT / "clones"
SCANS = OUT / "scans"
SC = Path(os.environ.get("CUTOFFNOTES_EXE", "since-cutoff"))
QUERY = "language:Python stars:>=200 pushed:>=2026-09-01"
N = 50
CUTOFFS = [("opus-5-5", ["--model", "anthropic:claude-opus-5-5"]),
           ("cutoff-2025-07-31", ["--cutoff", "2025-07-31"])]


def gh(path: str):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def select():
    OUT.mkdir(parents=True, exist_ok=True)
    chosen, examined = [], 0
    for page in range(1, 11):
        q = QUERY.replace(" ", "+").replace(":", "%3A").replace(">", "%3E").replace("=", "%3D")
        res = gh(f"search/repositories?q={q}&sort=stars&order=desc&per_page=100&page={page}")
        if not res:
            break
        for repo in res.get("items", []):
            examined += 1
            full = repo["full_name"]
            root = gh(f"repos/{full}/contents/")
            if not isinstance(root, list):
                continue
            names = {e["name"] for e in root if e.get("type") == "file"}
            lock = "uv.lock" if "uv.lock" in names else ("poetry.lock" if "poetry.lock" in names else None)
            if lock and "pyproject.toml" in names:
                chosen.append({"full_name": full, "stars": repo["stargazers_count"], "lock": lock,
                               "default_branch": repo["default_branch"], "pushed_at": repo["pushed_at"]})
                print(len(chosen), full, lock, flush=True)
            if len(chosen) >= N + 15:   # spares for repos the tool cannot parse
                break
            time.sleep(0.3)
        if len(chosen) >= N + 15:
            break
    meta = {"query": QUERY, "sort": "stars desc", "selected_at": datetime.now(timezone.utc).isoformat(),
            "examined": examined, "rule": "root has pyproject.toml and uv.lock or poetry.lock; first 50 parsable",
            "repos": chosen}
    (OUT / "repos.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def scan():
    meta = json.loads((OUT / "repos.json").read_text(encoding="utf-8"))
    CLONES.mkdir(parents=True, exist_ok=True)
    SCANS.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if not any(s in k.upper() for s in ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL"))}
    env["GIT_TERMINAL_PROMPT"] = "0"
    ok = 0
    shard, nshards = (int(x) for x in (sys.argv[2].split("/") if len(sys.argv) > 2 else ("0", "1")))
    # sharding: repo i goes to shard i % n; the first-50-parsable rule is applied afterwards in the analysis
    for i, repo in enumerate(meta["repos"]):
        if i % nshards != shard:
            continue
        slug = repo["full_name"].replace("/", "__")
        done = [SCANS / f"{slug}.{label}.json" for label, _ in CUTOFFS]
        if all(p.exists() for p in done):
            ok += json.loads(done[0].read_text(encoding="utf-8")).get("_ok", False)
            continue
        dest = CLONES / slug
        if not dest.exists():
            r = subprocess.run(["git", "clone", "--depth", "1", "--no-tags", "-c", "core.symlinks=false",
                                f"https://github.com/{repo['full_name']}.git", str(dest)],
                               capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=900)
            if r.returncode != 0:
                print("clone failed", repo["full_name"], flush=True)
                continue
        commit = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        repo_ok = True
        for label, args in CUTOFFS:
            out_path = SCANS / f"{slug}.{label}.json"
            if out_path.exists():
                continue
            t0 = time.time()
            print("start", repo["full_name"], label, flush=True)
            so, se = out_path.with_suffix(".stdout"), out_path.with_suffix(".stderr")
            with open(so, "wb") as fo, open(se, "wb") as fe:
                proc = subprocess.Popen([str(SC), "scan", str(dest), "--json", "--out",
                                         str(OUT / "reports" / slug / label), *args],
                                        stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, env=env)
                try:
                    rc = proc.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
                    rc = None
            if rc is None:
                out_path.write_text(json.dumps({"_ok": False, "_timeout": True, "_repo": repo}), encoding="utf-8")
                print(repo["full_name"], label, "TIMEOUT", flush=True)
                repo_ok = False
                continue
            try:
                data = json.loads(so.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                data = {"_parse_error": True, "stderr_tail": se.read_text(encoding="utf-8", errors="replace")[-2000:]}
            so.unlink(missing_ok=True)

            class R: pass
            r = R(); r.returncode = rc
            data["_ok"] = r.returncode in (0, 3) and "_parse_error" not in data
            data["_exit"] = r.returncode
            data["_seconds"] = round(time.time() - t0, 1)
            data["_repo"] = repo | {"commit": commit}
            out_path.write_text(json.dumps(data), encoding="utf-8")
            repo_ok = repo_ok and data["_ok"]
            print(repo["full_name"], label, "exit", r.returncode, f"{data['_seconds']}s", flush=True)
        ok += repo_ok
    print("parsable repos:", ok)


if __name__ == "__main__":
    {"select": select, "scan": scan}[sys.argv[1]]()
