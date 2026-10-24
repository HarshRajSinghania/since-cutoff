"""Exposure study 2, runtime check of audited true positives (EXPOSURE2_PROTOCOL.md section 7).

Each snippet is written by the judge (never repository code). It runs in an isolated virtual environment that contains
only the pinned release of the package (from PyPI) and its dependencies, with all warnings recorded. Snippets import
the API / access the attribute the code uses, or bind the code's call form to the API's signature.

usage: python -I runtime_check.py   reads $REALWORLD2_DIR/audit/snippets.json
         [{"i": <sample index>, "install": ["pkg==1.2.3", ...], "code": "..."}]
       -> $REALWORLD2_DIR/audit/runtime_results.json {"<i>": {"outcome": "ok|error", "error": ..., "warnings": [...]}}
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RW2, clean_env  # noqa: E402

AUD = RW2 / "audit"
VENVS = AUD / "venvs"

RUNNER = r'''
import json, sys, warnings
code = open(sys.argv[1], encoding="utf-8").read()
res = {"outcome": "ok", "error": None, "warnings": []}
with warnings.catch_warnings(record=True) as W:
    warnings.simplefilter("always")
    try:
        exec(compile(code, "<snippet>", "exec"), {"__name__": "__snippet__"})
    except BaseException as e:
        res["outcome"] = "error"
        res["error"] = f"{type(e).__name__}: {str(e)[:400]}"
    res["warnings"] = [f"{w.category.__name__}: {str(w.message)[:300]}" for w in W
                       if issubclass(w.category, (DeprecationWarning, FutureWarning, PendingDeprecationWarning, UserWarning))]
print("@@RESULT@@" + json.dumps(res))
'''


def venv_for(install):
    key = hashlib.sha256(" ".join(sorted(install)).encode()).hexdigest()[:12]
    d = VENVS / key
    py = d / "Scripts" / "python.exe"
    if not py.exists():
        subprocess.run([sys.executable, "-m", "venv", str(d)], check=True, capture_output=True)
        r = subprocess.run([str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                            "--only-binary=:all:", *install], capture_output=True, text=True, env=clean_env(),
                           timeout=1800)
        if r.returncode != 0:
            return None, r.stderr[-800:]
    return py, None


def main():
    specs = json.loads((AUD / "snippets.json").read_text(encoding="utf-8"))
    out_p = AUD / "runtime_results.json"
    results = json.loads(out_p.read_text(encoding="utf-8")) if out_p.exists() else {}
    VENVS.mkdir(parents=True, exist_ok=True)
    runner = AUD / "_runner.py"
    runner.write_text(RUNNER, encoding="utf-8")
    for s in specs:
        k = str(s["i"])
        if k in results and results[k].get("code") == s["code"]:
            continue
        py, err = venv_for(s["install"])
        if py is None:
            results[k] = {"outcome": "install_failed", "error": err, "install": s["install"], "code": s["code"]}
            print(k, "install failed", flush=True)
            continue
        with tempfile.TemporaryDirectory() as td:
            code_p = Path(td) / "snippet.py"
            code_p.write_text(s["code"], encoding="utf-8")
            try:
                r = subprocess.run([str(py), "-I", str(runner), str(code_p)], capture_output=True, text=True,
                                   cwd=td, env=clean_env(), timeout=300)
                line = next((l for l in r.stdout.splitlines() if l.startswith("@@RESULT@@")), None)
                res = json.loads(line[10:]) if line else {"outcome": "crash", "error": r.stderr[-500:]}
            except subprocess.TimeoutExpired:
                res = {"outcome": "timeout"}
        res.update(install=s["install"], code=s["code"])
        results[k] = res
        print(k, res["outcome"], res.get("error"), len(res.get("warnings", [])), flush=True)
        out_p.write_text(json.dumps(results, indent=1), encoding="utf-8")
    out_p.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
