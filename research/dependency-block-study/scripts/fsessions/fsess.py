"""Estimate f (share of real agent sessions that edit Python importing a package whose public API changed since the
model's cutoff) from the local Claude Code transcript store. Protocol: expansion/F_PROTOCOL.md (sha256 in
F_PROTOCOL.sha256).

Privacy: everything runs locally. The work directory (default: <tempdir>/fsessions_work) holds per-transcript records
with import lines and edited code for the synthetic scans; it is private, never published, and `clean` deletes it.
Only `analyze` writes a shareable file, and it contains aggregates only (counts, shares, intervals, public PyPI
distribution names with counts). No personal data is embedded in this script: the transcript root is derived from the
home folder and session ids to exclude are command-line arguments.

usage:
  python -I fsess.py extract --exclude-session <id> [--exclude-session <id> ...]
  python -I fsess.py versions          # PyPI release history of the resolved public distributions
  python -I fsess.py scan [--label primary|opus_cutoff]
  python -I fsess.py analyze --out <analysis/f_sessions.json>
  python -I fsess.py clean
"""
import argparse
import ast
import collections
import datetime as dt
import glob
import hashlib
import json
import os
import pickle
import random
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
import warnings
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
ROOT = HOME / ".claude" / "projects"
WORK = Path(os.environ.get("FSESS_WORK", os.path.join(tempfile.gettempdir(), "fsessions_work")))
SC = Path(os.environ.get("CUTOFFNOTES_EXE", "since_cutoff_runs/scan-venv/Scripts/since-cutoff.exe"))
SCAN_DIRS = [Path(os.environ.get("REALWORLD_DIR", "since_cutoff_runs/realworld")) / "scans",
             Path(os.environ.get("REALWORLD2_DIR", "since_cutoff_runs/realworld2")) / "scans"]
warnings.filterwarnings("ignore", category=SyntaxWarning)
PROTOCOL = Path(__file__).resolve().parent.parent / "F_PROTOCOL.md"
OPUS55_CUTOFF = "2026-06-30"
SEED = 20261001
B = 10000

EDIT_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
PATH_TOOLS = EDIT_TOOLS + ("Read",)
# X1 / X2 (protocol section 3); matched on lower-cased, back-slashed paths
X1_PREFIX = ("c:\\b\\",)
X1_SUB = ("since-cutoff-benchmark", "since-cutoff-bench", "since_cutoff_runs")
X2_SUB = ("\\<research folder>", "")
# common import-name -> distribution mismatches (protocol 4.3)
ALIASES = {"yaml": "pyyaml", "pil": "pillow", "sklearn": "scikit-learn", "cv2": "opencv-python",
           "bs4": "beautifulsoup4", "dateutil": "python-dateutil", "dotenv": "python-dotenv", "jwt": "pyjwt",
           "git": "gitpython", "google.genai": "google-genai", "attr": "attrs", "magic": "python-magic",
           "docx": "python-docx", "pptx": "python-pptx", "fitz": "pymupdf", "serial": "pyserial",
           "telegram": "python-telegram-bot", "crypto": "pycryptodome", "skimage": "scikit-image",
           "multipart": "python-multipart", "jose": "python-jose", "slugify": "python-slugify",
           "socks": "pysocks", "win32api": "pywin32", "win32com": "pywin32", "pythoncom": "pywin32",
           "googleapiclient": "google-api-python-client", "huggingface_hub": "huggingface-hub",
           "mcp": "mcp", "claude_agent_sdk": "claude-agent-sdk", "fastmcp": "fastmcp"}
# names that local folders commonly take and that some wheels ship by mistake: never a third-party import here
NOT_THIRD_PARTY = {"tests", "test", "docs", "doc", "examples", "example", "src", "scripts", "script", "benchmarks",
                   "benchmark", "utils", "util", "conftest", "setup", "app", "main", "config", "common", "lib",
                   "core", "helpers", "tools", "data", "build", "dist", "__main__"}


def norm_dist(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def low(p: str) -> str:
    return os.path.normpath(p).replace("/", "\\").lower()


# ---------------------------------------------------------------- clusters (protocol section 3)
def _strip(x: str) -> str:
    prev = None
    while prev != x:
        prev = x
        x = re.sub(r"(-pr\d+|-\d+|-wt.*|-fix.*)$", "", x)
    return x


def project_key(path: str) -> tuple[str, bool]:
    """(cluster key, is_scratch). Keys stay in memory / the private work dir only."""
    parts = low(path).split("\\")
    if len(parts) > 3 and parts[1] == "users":
        rest = parts[3:]
        is_dir = lambda i: len(rest) > i + 1  # noqa: E731  (component i is a folder, not the file itself)
        if rest[0] == "projects" and is_dir(1):
            x = rest[1]
            if x.startswith("since-cutoff") or x.startswith("sc-") or x.startswith(".sc-venv"):
                return "projects:sc-tool", False
            if x.startswith("<project>"):
                return "projects:<project>", False
            return "projects:" + _strip(x), False
        if rest[0] == "appdata" and len(rest) > 3 and rest[1] == "local" and rest[2] == "temp":
            if rest[3] == "claude" and "scratchpad" in rest:
                i = rest.index("scratchpad")
                return "scratch:" + (rest[i - 1] if i >= 1 else "?"), True
            return ("temp:" + _strip(rest[3]) if is_dir(3) else "temp:loose"), True
        if rest[0] == "oss" and is_dir(1):
            return "oss:" + _strip(rest[1]), False
        if rest[0] == "desktop" and is_dir(1):
            return "desktop:" + "/".join(rest[1:3] if is_dir(2) else rest[1:2]), False
        if is_dir(0):
            return "home:" + _strip(rest[0]), False
        return "home:loose", False
    return "other:" + "/".join(parts[:3]), False


def is_tool_key(k: str) -> bool:
    return k == "projects:sc-tool"


# ---------------------------------------------------------------- import parsing (protocol 4.2)
IMPORT_RE = re.compile(r"^\s*(from\s+[\w.]+\s+import\s+[\w., ()*]+|import\s+[\w., ]+)")


def parse_snippet(code: str):
    """Return (module ast or None, text the tool should see)."""
    code = textwrap.dedent(code.replace("\r\n", "\n"))
    for cand in (code, "def _fsess_snippet():\n" + textwrap.indent(code, "    ") + "\n    pass\n"):
        try:
            return ast.parse(cand), cand
        except (SyntaxError, ValueError):
            continue
    return None, code


def import_lines(code: str) -> list[str]:
    """Import statements of a file or snippet, unparsed one per line (dedented)."""
    tree, _ = parse_snippet(code)
    out = []
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                out.append(ast.unparse(node))
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                out.append(ast.unparse(node))
        return out
    for line in code.splitlines():
        m = IMPORT_RE.match(line)
        if m and "(" not in m.group(1) and not line.rstrip().endswith("\\"):
            s = m.group(1).strip().rstrip(",")
            try:
                ast.parse(s)
                out.append(s)
            except SyntaxError:
                pass
    return out


def modules_of(lines: list[str]) -> set[str]:
    """Dotted module candidates: 'a.b' for `import a.b`; 'a' and 'a.x' for `from a import x`."""
    mods = set()
    for s in lines:
        try:
            node = ast.parse(s).body[0]
        except Exception:
            continue
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
            for a in node.names:
                if a.name != "*":
                    mods.add(node.module + "." + a.name)
    return mods


def notebook_code(src) -> str:
    return "".join(src) if isinstance(src, list) else (src or "")


# ---------------------------------------------------------------- extract
def iter_records(f):
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except Exception:
                continue


NUMBERED = re.compile(r"^\s*(\d+)(?:\t|→)(.*)$")


def read_result_text(content, any_start=False) -> str | None:
    """File text from a Read tool_result shown as `cat -n` lines; None unless it starts at line 1."""
    if isinstance(content, list):
        content = "\n".join(x.get("text", "") for x in content if isinstance(x, dict))
    if not isinstance(content, str):
        return None
    lines, first = [], None
    for line in content.splitlines():
        m = NUMBERED.match(line)
        if m:
            if first is None:
                first = int(m.group(1))
            lines.append(m.group(2))
    return "\n".join(lines) if (first == 1 or (any_start and first is not None)) else None


def read_disk_imports(path: str) -> list[str] | None:
    """Only import statements of a file that still exists locally (protocol section 2)."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > 2_000_000:
            return None
        if path.endswith(".ipynb"):
            nb = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
            code = "\n".join(notebook_code(c.get("source")) for c in nb.get("cells", []) if c.get("cell_type") == "code")
        else:
            code = Path(path).read_text(encoding="utf-8", errors="replace")
        return import_lines(code)
    except Exception:
        return None


def extract_transcript(f: str) -> dict:
    rel = Path(f).relative_to(ROOT).parts
    top = rel[1] if "subagents" in rel else Path(f).stem
    models = collections.Counter()
    first_ts = None
    cwds, all_paths, edited_any = set(), set(), []
    pending = {}            # tool_use id -> (name, input, header candidates at call time)
    state = collections.defaultdict(dict)   # path -> {'write': lines, 'read1': lines, 'orig': lines}
    py_edits = []           # dicts: path, snippets [code], header lines, header_source, error
    views = collections.defaultdict(set)    # path -> import lines seen in any view of the file (deviation D2)
    for r in iter_records(f):
        if r.get("cwd"):
            cwds.add(low(r["cwd"]))
        m = r.get("message")
        if r.get("type") == "assistant" and isinstance(m, dict):
            mod = m.get("model")
            if mod and not mod.startswith("<"):
                models[mod] += 1
                if first_ts is None and r.get("timestamp"):
                    first_ts = r["timestamp"]
            for c in m.get("content") or []:
                if not (isinstance(c, dict) and c.get("type") == "tool_use"):
                    continue
                name, inp = c.get("name"), c.get("input") or {}
                if name not in PATH_TOOLS or not isinstance(inp, dict):
                    continue
                p = inp.get("file_path") or inp.get("notebook_path") or ""
                if not isinstance(p, str) or not p:
                    continue
                all_paths.add(low(p))
                if name in EDIT_TOOLS:
                    st = state[low(p)]
                    pending[c.get("id")] = (name, inp, p, dict(st))
                elif name == "Read":
                    pending[c.get("id")] = (name, inp, p, None)
        elif r.get("type") == "user" and isinstance(m, dict) and isinstance(m.get("content"), list):
            tur = r.get("toolUseResult")
            for c in m["content"]:
                if not (isinstance(c, dict) and c.get("type") == "tool_result"):
                    continue
                pend = pending.pop(c.get("tool_use_id"), None)
                if pend is None:
                    continue
                name, inp, p, st = pend
                err = bool(c.get("is_error"))
                lp = low(p)
                if name == "Read":
                    if err or not lp.endswith(".py"):
                        continue
                    if isinstance(tur, dict) and isinstance(tur.get("file"), dict):
                        fl = tur["file"]
                        if isinstance(fl.get("content"), str) and (fl.get("startLine") in (None, 1)):
                            state[lp]["read1"] = state[lp]["latest"] = import_lines(fl["content"])
                    else:   # subagent transcripts keep only the numbered text of the result
                        text = read_result_text(c.get("content"))
                        if text is not None:
                            state[lp]["read1"] = state[lp]["latest"] = import_lines(text)
                        part = read_result_text(c.get("content"), any_start=True)
                        if part:
                            views[lp].update(import_lines(part))
                    if state[lp].get("read1"):
                        views[lp].update(state[lp]["read1"])
                    continue
                if err:
                    continue
                edited_any.append(p)
                is_py = lp.endswith(".py") or (lp.endswith(".ipynb") and name == "NotebookEdit")
                orig = tur.get("originalFile") if isinstance(tur, dict) else None
                if name == "Write":
                    content = inp.get("content") or ""
                    snippets = [content]
                    header, hsrc = [], "write"
                    if is_py:
                        state[lp]["write"] = state[lp]["latest"] = import_lines(content)
                        views[lp].update(state[lp]["write"])
                elif name in ("Edit", "MultiEdit"):
                    if name == "Edit":
                        snippets = [inp.get("new_string") or ""]
                    else:
                        snippets = [e.get("new_string") or "" for e in inp.get("edits") or [] if isinstance(e, dict)]
                    header, hsrc = None, None
                    if is_py and isinstance(orig, str) and orig:
                        header, hsrc = import_lines(orig), "originalFile"
                        state[lp]["orig"] = state[lp]["latest"] = header
                        views[lp].update(header)
                    if header is None and st.get("latest") is not None:   # most recent full-file view
                        header = st["latest"]
                        hsrc = next(k for k in ("write", "read1", "orig") if st.get(k) is st["latest"])
                else:  # NotebookEdit
                    if (inp.get("cell_type") or "code") != "code":
                        continue
                    snippets = [notebook_code(inp.get("new_source"))]
                    header, hsrc = None, None
                if is_py:
                    py_edits.append({"path": p, "snippets": snippets, "header": header, "hsrc": hsrc})
    # disk fallback for headers (imports only)
    disk_cache = {}
    for e in py_edits:
        if e["header"] is None:
            if e["path"] not in disk_cache:
                disk_cache[e["path"]] = read_disk_imports(e["path"])
            h = disk_cache[e["path"]]
            e["header"], e["hsrc"] = (h, "disk") if h is not None else (None, "none")
    model = models.most_common(1)[0][0] if models else None
    return {"file": f, "top": top, "model": model, "first_ts": first_ts, "cwds": sorted(cwds),
            "paths": sorted(all_paths), "edited_any": edited_any, "py_edits": py_edits,
            "views": {k: sorted(v) for k, v in views.items()}}


def excluded(t: dict, ex_sessions: set[str]) -> str | None:
    if not t["model"] or not t["first_ts"]:
        return "X0_empty"
    locs = list(t["cwds"]) + list(t["paths"])
    if any(l.startswith(X1_PREFIX) or any(s in l for s in X1_SUB) for l in locs):
        return "X1_benchmark"
    if t["top"] in ex_sessions:
        return "X2a_research_session"
    if any(any(s in l for s in X2_SUB) for l in locs):
        return "X2b_research_tree"
    return None


def model_cutoffs() -> dict:
    out = subprocess.run([str(SC), "models"], capture_output=True, text=True, encoding="utf-8").stdout
    table = {}
    for line in out.splitlines():
        cols = line.split("\t")
        if len(cols) >= 3 and cols[0] == "anthropic":
            c = cols[2]
            if re.fullmatch(r"\d{4}-\d{2}", c):
                y, mo = map(int, c.split("-"))
                nxt = dt.date(y + (mo == 12), mo % 12 + 1, 1)
                c = (nxt - dt.timedelta(days=1)).isoformat()
            table[cols[1]] = c
    return table


def local_dist_map() -> dict:
    """top-level / dotted import name -> set of normalised distribution names (local data only)."""
    mp = collections.defaultdict(set)
    pys = [sys.executable, str(SC.parent / "python.exe"), "venv/Scripts/python.exe"]
    pys += glob.glob(str(HOME / "projects" / "*" / ".venv" / "Scripts" / "python.exe"))
    pys += glob.glob(str(HOME / "projects" / ".*venv*" / "Scripts" / "python.exe"))
    code = "import json,importlib.metadata as m;print(json.dumps(m.packages_distributions()))"
    for py in dict.fromkeys(pys):
        if not os.path.exists(py):
            continue
        r = subprocess.run([py, "-I", "-c", code], capture_output=True, text=True, encoding="utf-8")
        try:
            for k, v in json.loads(r.stdout).items():
                for d in v:
                    mp[k].add(norm_dist(d))
        except Exception:
            pass
    # public distributions' import names from the paper's exposure scans (deviation D1)
    for d in SCAN_DIRS:
        for f in glob.glob(str(d / "*.json")):
            try:
                data = json.loads(Path(f).read_text(encoding="utf-8"))
            except Exception:
                continue
            for item in data.get("scan") or []:
                for imp in item.get("import_names") or []:
                    mp[imp].add(norm_dist(item["name"]))
    for k, v in ALIASES.items():
        mp[k] = {norm_dist(v)}
    return mp


def resolve(mod: str, mp: dict) -> str | None:
    parts = mod.split(".")
    if mod.lower() in ALIASES:
        return norm_dist(ALIASES[mod.lower()])
    for i in range(len(parts), 0, -1):
        pre = ".".join(parts[:i])
        if pre in ALIASES:
            return norm_dist(ALIASES[pre])
        cands = mp.get(pre)
        if not cands:
            continue
        if len(cands) == 1:
            return next(iter(cands))
        for j in range(len(parts), 0, -1):    # namespace package: dist named like the dotted prefix
            want = norm_dist("-".join(parts[:j]))
            if want in cands:
                return want
        if i == 1:
            return None   # ambiguous namespace top
    return None


def cmd_extract(args):
    WORK.mkdir(parents=True, exist_ok=True)
    files = sorted(glob.glob(str(ROOT / "**" / "*.jsonl"), recursive=True))
    ex_sessions = set(args.exclude_session or [])
    cut = model_cutoffs()
    mp = local_dist_map()
    ts = []
    for i, f in enumerate(files):
        t = extract_transcript(f)
        t["exclusion"] = excluded(t, ex_sessions)
        ts.append(t)
        if i % 200 == 0:
            print("extract", i, len(files), flush=True)
    # header fallback D2: imports seen in any view of the same path anywhere in the store
    allviews = collections.defaultdict(set)
    for t in ts:
        for k, v in t["views"].items():
            allviews[k].update(v)
    for t in ts:
        for e in t["py_edits"]:
            if e["header"] is None:
                v = allviews.get(low(e["path"]))
                e["header"], e["hsrc"] = (sorted(v), "store_views") if v else ([], "none")
    # clusters
    for t in ts:
        keys = [project_key(p) for p in t["edited_any"]]
        nonscratch = collections.Counter(k for k, s in keys if not s)
        allk = collections.Counter(k for k, s in keys)
        if nonscratch:
            t["cluster"] = nonscratch.most_common(1)[0][0]
        elif allk:
            t["cluster"] = allk.most_common(1)[0][0]
        else:
            t["cluster"] = "session:" + t["top"]
        t["is_tool"] = is_tool_key(t["cluster"])
        t["py_scratch_only"] = bool(t["py_edits"]) and all(project_key(e["path"])[1] for e in t["py_edits"])
    # per-cluster path components (local-module rule)
    comps = collections.defaultdict(set)
    for t in ts:
        for p in t["edited_any"]:
            k, s = project_key(p)
            for c in low(p).split("\\"):
                comps[t["cluster"] if s else k].add(re.sub(r"\.pyi?$", "", c))
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    unresolved = collections.Counter()
    for t in ts:
        dists = {}
        for e in t["py_edits"]:
            k, s = project_key(e["path"])
            ck = t["cluster"] if s else k
            lines = list(e["header"] or [])
            for sn in e["snippets"]:
                lines += import_lines(sn)
            e["imports"] = sorted(set(lines))
            mods = modules_of(e["imports"])
            edists, unres = set(), set()
            fdir = os.path.dirname(e["path"])
            bytop = collections.defaultdict(set)
            for mod in mods:
                bytop[mod.split(".")[0]].add(mod)
            for topm, tmods in bytop.items():
                if topm in stdlib or topm.lower() in NOT_THIRD_PARTY or topm.startswith("_"):
                    continue
                if topm.lower() in comps.get(ck, set()):
                    continue
                if os.path.exists(os.path.join(fdir, topm + ".py")) or os.path.isdir(os.path.join(fdir, topm)):
                    continue
                # 'from a import x' gives 'a' and 'a.x'; namespace tops resolve only through the dotted names
                got = {d for d in (resolve(m, mp) for m in tmods) if d}
                if got:
                    edists |= got
                else:
                    unres.add(topm)
                    unresolved[topm] += 1
            e["dists"] = sorted(edists)
            e["unresolved"] = sorted(unres)
            for d in edists:
                dists[d] = True
        t["dists"] = sorted(dists)
        t["cutoff"] = cut.get(t["model"]) if t["model"] else None
        t["date"] = t["first_ts"][:10] if t["first_ts"] else None
    with open(WORK / "transcripts.pkl", "wb") as fh:
        pickle.dump(ts, fh)
    (WORK / "unresolved.pkl").write_bytes(pickle.dumps(unresolved))
    print("unresolved top modules: distinct", len(unresolved), "occurrences", sum(unresolved.values()))
    inc = [t for t in ts if not t["exclusion"]]
    print("transcripts", len(ts), "included", len(inc), "excl", collections.Counter(t["exclusion"] for t in ts))
    print("included with py edits", sum(bool(t["py_edits"]) for t in inc),
          "with resolved dists", sum(bool(t["dists"]) for t in inc))
    print("models without cutoff", collections.Counter(t["model"] for t in inc if not t["cutoff"]))


# ---------------------------------------------------------------- versions (protocol 4.4)
def pypi_json(dist: str):
    cache = WORK / "pypi" / (dist + ".json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{dist}/json", timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        slim = {"name": data["info"]["name"], "releases": {
            v: [{"t": f.get("upload_time_iso_8601"), "y": f.get("yanked", False)} for f in fs]
            for v, fs in data.get("releases", {}).items()}}
    except Exception as exc:  # noqa: BLE001
        slim = {"error": str(exc)[:200]}
    cache.write_text(json.dumps(slim), encoding="utf-8")
    time.sleep(0.05)
    return slim


def version_at(dist: str, date: str):
    from packaging.version import InvalidVersion, Version
    data = pypi_json(dist)
    if "releases" not in data:
        return None
    best = None
    for v, files in data["releases"].items():
        files = [f for f in files if f["t"] and not f["y"]]
        if not files:
            continue
        try:
            V = Version(v)
        except InvalidVersion:
            continue
        if V.is_prerelease or V.is_devrelease:
            continue
        first = min(f["t"] for f in files)[:10]
        if first <= date and (best is None or V > best[0]):
            best = (V, v)
    return best[1] if best else None


def cmd_versions(args):
    ts = pickle.loads((WORK / "transcripts.pkl").read_bytes())
    inc = [t for t in ts if not t["exclusion"] and t["dists"]]
    dists = sorted({d for t in inc for d in t["dists"]})
    print("distributions", len(dists))
    for i, d in enumerate(dists):
        pypi_json(d)
        if i % 50 == 0:
            print("pypi", i, flush=True)
    vers = {}
    for t in inc:
        for d in t["dists"]:
            vers[(d, t["date"])] = version_at(d, t["date"])
    (WORK / "versions.pkl").write_bytes(pickle.dumps(vers))
    print("missing", sum(v is None for v in vers.values()), "of", len(vers))


# ---------------------------------------------------------------- scan (protocol 4.5)
def cmd_scan(args):
    ts = pickle.loads((WORK / "transcripts.pkl").read_bytes())
    vers = pickle.loads((WORK / "versions.pkl").read_bytes())
    label = args.label
    groups = collections.defaultdict(list)
    for i, t in enumerate(ts):
        if t["exclusion"] or not t["dists"]:
            continue
        cutoff = OPUS55_CUTOFF if label == "opus_cutoff" else t["cutoff"]
        if label == "opus_cutoff" and t["cutoff"] == OPUS55_CUTOFF:
            continue   # identical to the primary scan
        groups[(cutoff, t["date"])].append(i)
    env = {k: v for k, v in os.environ.items()
           if not any(s in k.upper() for s in ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL"))}
    env.pop("CLAUDECODE", None)
    env["PYTHONUTF8"] = "1"
    outdir = WORK / "results" / label
    outdir.mkdir(parents=True, exist_ok=True)
    nfail = 0
    for gi, ((cutoff, date), idxs) in enumerate(sorted(groups.items())):
        out = outdir / f"{cutoff}_{date}.pkl"
        if out.exists():
            continue
        proj = WORK / "proj" / f"{label}_{gi}"
        if proj.exists():
            shutil.rmtree(proj)
        proj.mkdir(parents=True)
        reqs = {}
        filemap = {}   # file name -> (transcript idx, edit idx, 'h'|'e')
        parse_fail = collections.Counter()
        for i in idxs:
            t = ts[i]
            for d in t["dists"]:
                v = vers.get((d, date))
                if v:
                    reqs[d] = v
            for k, e in enumerate(t["py_edits"]):
                if not e["dists"]:
                    continue
                header = "\n".join(e["header"] or [])
                body = []
                for sn in e["snippets"]:
                    tree, text = parse_snippet(sn)
                    if tree is None:
                        parse_fail[i] += 1
                        continue
                    body.append(text)
                hname, ename = f"t{i}_{k}_h.py", f"t{i}_{k}_e.py"
                (proj / hname).write_text(header + "\n", encoding="utf-8")
                filemap[hname] = (i, k, "h")
                if body:
                    (proj / ename).write_text(header + "\n\n" + "\n\n".join(body) + "\n", encoding="utf-8")
                    filemap[ename] = (i, k, "e")
        (proj / "requirements.txt").write_text("".join(f"{d}=={v}\n" for d, v in sorted(reqs.items())),
                                               encoding="utf-8")
        t0 = time.time()
        r = subprocess.run([str(SC), "scan", str(proj), "--cutoff", cutoff, "--json",
                            "--out", str(WORK / "reports" / f"{label}_{gi}")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, stdin=subprocess.DEVNULL, timeout=3600)
        try:
            data = json.loads(r.stdout)
            ok = r.returncode in (0, 3)
        except json.JSONDecodeError:
            data, ok = {}, False
            nfail += 1
        status = {norm_dist(p["package"]): {"status": p.get("status"), "locked": p.get("locked"),
                                            "cutoff_version": p.get("cutoff_version"),
                                            "breaking": p.get("breaking_changes") or 0,
                                            "reason": p.get("reason")}
                  for p in data.get("packages") or []}
        used = []
        for u in data.get("used_apis") or []:
            files = set(os.path.basename(x) for x in (u.get("used_in") or []))
            files |= {os.path.basename(l.get("file") or "") for l in u.get("locations") or []}
            used.append({"package": norm_dist(u.get("package") or ""), "api": u.get("api"),
                         "form": u.get("form"), "files": sorted(f for f in files if f in filemap)})
        res = {"ok": ok, "exit": r.returncode, "seconds": round(time.time() - t0, 1), "status": status,
               "used": used, "filemap": filemap, "reqs": reqs, "parse_fail": dict(parse_fail),
               "warnings": len(data.get("warnings") or []), "stderr_tail": "" if ok else r.stderr[-1500:]}
        out.write_bytes(pickle.dumps(res))
        shutil.rmtree(proj, ignore_errors=True)
        print(label, gi + 1, len(groups), cutoff, len(idxs), "transcripts", len(reqs), "dists",
              "ok" if ok else f"FAIL exit {r.returncode}", res["seconds"], "s", flush=True)
    print("failures", nfail)


# ---------------------------------------------------------------- analyze (protocol 4.6-4.8)
def flags_for(ts, label, unchecked_as_changed=False):
    """Per included transcript: dict of flags. Non-scanned transcripts get False flags."""
    resdir = WORK / "results" / label
    res = {}
    for f in resdir.glob("*.pkl"):
        res[f.stem] = pickle.loads(f.read_bytes())
    prim = WORK / "results" / "primary"
    out = {}
    for i, t in enumerate(ts):
        if t["exclusion"]:
            continue
        fl = {"edit_any": bool(t["edited_any"]), "edit_py": bool(t["py_edits"]), "dists": bool(t["dists"]),
              "newer": False, "upper": False, "upper_breaking": False, "upper_new": False, "strict": False, "changed_dists": [],
              "strict_dists": [], "unchecked": False, "scanned": False}
        if t["dists"]:
            cutoff = OPUS55_CUTOFF if label == "opus_cutoff" else t["cutoff"]
            key = f"{cutoff}_{t['date']}"
            r = res.get(key)
            if r is None and label == "opus_cutoff":
                r = pickle.loads((prim / f"{cutoff}_{t['date']}.pkl").read_bytes()) if \
                    (prim / f"{cutoff}_{t['date']}.pkl").exists() else None
            if r is not None and r["ok"]:
                fl["scanned"] = True
                for d in t["dists"]:
                    st = (r["status"].get(d) or {}).get("status")
                    if st in ("changed", "unchanged", "new"):
                        fl["newer"] = True
                    if st == "changed" or (unchecked_as_changed and st in ("skipped", None)):
                        fl["upper"] = True
                        fl["changed_dists"].append(d)
                    if st == "changed" and (r["status"].get(d) or {}).get("breaking", 0) > 0:
                        fl["upper_breaking"] = True
                    if st in ("changed", "new"):
                        fl["upper_new"] = True
                    if st in ("skipped", None):
                        fl["unchecked"] = True
                hfiles = collections.defaultdict(set)
                efiles = collections.defaultdict(set)
                for u in r["used"]:
                    for fn in u["files"]:
                        ti, k, kind = r["filemap"][fn]
                        if ti != i:
                            continue
                        (hfiles if kind == "h" else efiles)[k].add((u["package"], u["api"]))
                for k, apis in efiles.items():
                    new = apis - hfiles.get(k, set())
                    if new:
                        fl["strict"] = True
                        fl["strict_dists"] += sorted({p for p, _ in new})
        out[i] = fl
    return out


def boot(units, clusters, keyfn, B=B, seed=SEED):
    """Cluster bootstrap of a share. units: list of 0/1; clusters: parallel list of keys."""
    byc = collections.defaultdict(list)
    for u, c in zip(units, clusters):
        byc[c].append(u)
    cl = list(byc.values())
    sums = [(sum(v), len(v)) for v in cl]
    rng = random.Random(seed)
    est = sum(units) / len(units) if units else float("nan")
    draws = []
    n = len(sums)
    for _ in range(B):
        s = m = 0
        for _ in range(n):
            a, b = sums[rng.randrange(n)]
            s += a
            m += b
        draws.append(s / m if m else 0.0)
    draws.sort()
    return {"k": sum(units), "n": len(units), "share": round(est, 4),
            "ci95": [round(draws[int(0.025 * B)], 4), round(draws[int(0.975 * B) - 1], 4)],
            "clusters": n}


def summarize(ts, fl, subset=lambda t: True, name=""):
    idx = [i for i in fl if subset(ts[i])]
    cl = [ts[i]["cluster"] for i in idx]
    out = {"n_transcripts": len(idx)}
    if not idx:
        return out
    for k in ("edit_any", "edit_py", "newer", "upper", "upper_breaking", "upper_new", "strict"):
        out[k] = boot([int(fl[i][k]) for i in idx], cl, None)
    py = [i for i in idx if fl[i]["edit_py"]]
    clp = [ts[i]["cluster"] for i in py]
    if py:
        out["given_edit_py"] = {k: boot([int(fl[i][k]) for i in py], clp, None) for k in ("newer", "upper", "upper_breaking", "strict")}
    ea = [i for i in idx if fl[i]["edit_any"]]
    if ea:
        out["given_edit_any"] = {k: boot([int(fl[i][k]) for i in ea], [ts[i]["cluster"] for i in ea], None)
                                 for k in ("upper", "strict")}
    sizes = collections.Counter(cl)
    out["n_clusters"] = len(sizes)
    out["largest_cluster_share"] = round(max(sizes.values()) / len(idx), 3)
    return out


def session_level(ts, fl):
    by = collections.defaultdict(lambda: collections.Counter())
    for i, f in fl.items():
        c = by[ts[i]["top"]]
        c["n"] += 1
        for k in ("edit_py", "upper", "strict"):
            c[k] = max(c[k], int(f[k]))
    n = len(by)
    return {"n_top_level_sessions": n, **{k: sum(c[k] for c in by.values()) for k in ("edit_py", "upper", "strict")},
            "subagent_transcripts_per_session_max": max(c["n"] for c in by.values())}


def cmd_analyze(args):
    ts = pickle.loads((WORK / "transcripts.pkl").read_bytes())
    sha = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    prim = flags_for(ts, "primary")
    inc = [i for i in prim]
    excl = collections.Counter(t["exclusion"] or "included" for t in ts)
    res = {"protocol": "expansion/F_PROTOCOL.md", "protocol_sha256": sha,
           "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "tool": "since-cutoff 0.5.0 (scan --cutoff, static)", "bootstrap": {"B": B, "seed": SEED, "cluster": "project"},
           "transcripts_total": len(ts), "exclusions": dict(excl)}
    # descriptive
    models = collections.Counter(ts[i]["model"] for i in inc)
    dates = sorted(ts[i]["date"] for i in inc)
    res["included"] = {"transcripts": len(inc),
                       "top_level_sessions": len({ts[i]["top"] for i in inc}),
                       "subagent_transcripts": sum("subagents" in Path(ts[i]["file"]).parts for i in inc),
                       "models": dict(models), "date_range": [dates[0], dates[-1]],
                       "dates_by_month": dict(collections.Counter(d[:7] for d in dates)),
                       "cutoffs": dict(collections.Counter(ts[i]["cutoff"] for i in inc))}
    pe = [e for i in inc for e in ts[i]["py_edits"]]
    res["edits"] = {"python_edit_calls": len(pe),
                    "header_source": dict(collections.Counter(e["hsrc"] for e in pe)),
                    "edits_with_third_party_dist": sum(bool(e["dists"]) for e in pe),
                    "edits_with_unresolved_module": sum(bool(e.get("unresolved")) for e in pe),
                    "transcripts_with_py_and_any_unresolved": sum(
                        any(e.get("unresolved") for e in ts[i]["py_edits"]) for i in inc),
                    "transcripts_with_py_but_no_resolved_dist": sum(
                        bool(ts[i]["py_edits"]) and not ts[i]["dists"] for i in inc)}
    # scan bookkeeping
    rs = [pickle.loads(f.read_bytes()) for f in (WORK / "results" / "primary").glob("*.pkl")]
    res["scans_primary"] = {"groups": len(rs), "ok": sum(r["ok"] for r in rs),
                            "seconds_total": round(sum(r["seconds"] for r in rs)),
                            "snippets_unparseable": sum(sum(r["parse_fail"].values()) for r in rs),
                            "transcripts_scanned_ok": sum(f["scanned"] for f in prim.values()),
                            "transcripts_with_dists": sum(f["dists"] for f in prim.values()),
                            "transcripts_with_unchecked_dist": sum(f["unchecked"] for f in prim.values())}
    res["scans_primary"]["edits_scanned"] = sum(bool(e["dists"]) for i in inc for e in ts[i]["py_edits"])
    res["scans_primary"]["snippets_scanned"] = sum(len(e["snippets"]) for i in inc for e in ts[i]["py_edits"]
                                                   if e["dists"])
    # estimates
    res["primary"] = summarize(ts, prim)
    res["primary_session_level"] = session_level(ts, prim)
    res["S1_without_tool_repo"] = summarize(ts, prim, lambda t: not t["is_tool"])
    prim_s2 = {i: (dict(f, **{k: False for k in ("edit_py", "newer", "upper", "upper_breaking", "upper_new", "strict")})
                   if ts[i]["py_scratch_only"] else f) for i, f in prim.items()}
    res["S2_without_scratch_only_python"] = summarize(ts, prim_s2)
    res["S3_unchecked_as_changed"] = summarize(ts, flags_for(ts, "primary", unchecked_as_changed=True))
    if (WORK / "results" / "opus_cutoff").exists():
        res["S4_opus55_cutoff_for_all"] = summarize(ts, flags_for(ts, "opus_cutoff"))
    res["S5_opus55_only"] = summarize(ts, prim, lambda t: t["model"] == "claude-opus-5-5")
    res["S1_and_S2"] = summarize(ts, prim_s2, lambda t: not t["is_tool"])
    # S6 (deviation D3): worst case for unrecovered headers - a transcript with any Python edit whose file header
    # could not be recovered (file gone, no full view in the store) and whose snippet imports nothing third-party
    # counts as f_upper = 1
    miss = {i for i in prim if any(e["hsrc"] == "none" and not e["dists"] for e in ts[i]["py_edits"])}
    prim_s6 = {i: (dict(f, upper=True) if i in miss else f) for i, f in prim.items()}
    res["S6_missing_header_as_exposed"] = summarize(ts, prim_s6)
    res["S6_missing_header_as_exposed"]["transcripts_with_missing_header_edit"] = len(miss)
    # S7 (deviation D3): complete-case rate and a missing-at-random imputation within project category
    cat = lambda i: ts[i]["cluster"].split(":")[0]  # noqa: E731
    py = [i for i in prim if prim[i]["edit_py"]]
    complete = [i for i in py if i not in miss]
    rates = {}
    for c in sorted({cat(i) for i in py}):
        cc = [i for i in complete if cat(i) == c]
        rates[c] = (sum(prim[i]["upper"] for i in cc) / len(cc)) if cc else None
    allrate = sum(prim[i]["upper"] for i in complete) / len(complete)
    imp_units = [(rates.get(cat(i)) if rates.get(cat(i)) is not None else allrate) if (i in miss and not prim[i]["upper"])
                 else float(prim[i]["upper"]) for i in prim]
    cls = [ts[i]["cluster"] for i in prim]
    imp = boot(imp_units, cls, None)
    imp["k"] = round(imp["k"], 1)
    impy = boot([u for i, u in zip(prim, imp_units) if prim[i]["edit_py"]],
                [ts[i]["cluster"] for i in prim if prim[i]["edit_py"]], None)
    impy["k"] = round(impy["k"], 1)
    res["S7_missing_header_imputed"] = {
        "complete_case_py_transcripts": len(complete),
        "complete_case_upper_given_py": boot([int(prim[i]["upper"]) for i in complete],
                                             [ts[i]["cluster"] for i in complete], None),
        "complete_case_rate_by_category": {c: (round(r, 3) if r is not None else None) for c, r in rates.items()},
        "missing_by_category": dict(collections.Counter(cat(i) for i in miss)),
        "upper_imputed": imp, "upper_imputed_given_py": impy,
        "note": "imputed rates held fixed in the bootstrap (CI too narrow)"}
    bycat = collections.defaultdict(collections.Counter)
    for i, f in prim.items():
        c = "tool_repo" if ts[i]["is_tool"] else cat(i)
        bycat[c]["n"] += 1
        bycat[c]["clusters_" + ts[i]["cluster"]] += 0
        for k in ("edit_py", "newer", "upper", "strict"):
            bycat[c][k] += int(f[k])
    res["by_project_category"] = {c: {"n": v["n"], "clusters": sum(1 for k in v if k.startswith("clusters_")),
                                      **{k: v[k] for k in ("edit_py", "newer", "upper", "strict")}}
                                  for c, v in bycat.items()}
    # which public distributions drive f_upper / f_strict (transcript counts)
    cd = collections.Counter(d for f in prim.values() for d in set(f["changed_dists"]))
    sd = collections.Counter(d for f in prim.values() for d in set(f["strict_dists"]))
    res["changed_distributions_by_transcripts"] = dict(cd.most_common(25))
    res["strict_distributions_by_transcripts"] = dict(sd.most_common(25))
    res["n_distinct_changed_distributions"] = len(cd)
    res["n_distinct_resolved_distributions"] = len({d for i in inc for d in ts[i]["dists"]})
    # break-even comparison
    be = {"benchmark_block_6_10pct": [0.06, 0.10], "real_blocks_9_30pct": [0.09, 0.30]}
    cmp = {}
    for est in ("upper", "strict"):
        p = res["primary"][est]
        cmp[est] = {rng: ("below" if p["ci95"][1] < lo else "above" if p["ci95"][0] > hi else "overlaps")
                    for rng, (lo, hi) in be.items()}
    res["breakeven_comparison"] = {"ranges": be, "primary": cmp}
    Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


def cmd_clean(args):
    shutil.rmtree(WORK, ignore_errors=True)
    print("removed", WORK)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--exclude-session", action="append")
    sub.add_parser("versions")
    s = sub.add_parser("scan")
    s.add_argument("--label", default="primary", choices=["primary", "opus_cutoff"])
    a = sub.add_parser("analyze")
    a.add_argument("--out", required=True)
    sub.add_parser("clean")
    args = ap.parse_args()
    {"extract": cmd_extract, "versions": cmd_versions, "scan": cmd_scan, "analyze": cmd_analyze,
     "clean": cmd_clean}[args.cmd](args)


if __name__ == "__main__":
    main()
