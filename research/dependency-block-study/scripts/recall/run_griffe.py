"""griffe check on the seven version pairs.

1) CLI: a throwaway git repo per library (old wheel's package dirs committed + tagged `old`, then the new ones tagged
   `new`), `griffe check <pkg> -s . -a old -b new -f oneline`; stdout saved.
2) API: griffe.load() of each extracted wheel + griffe.find_breaking_changes(old, new) (what `griffe check` calls);
   structured results saved to out/griffe/<lib>.json. The CLI line count is compared with the API count.
"""
import json, shutil, subprocess, sys, os
from pathlib import Path
import griffe

W = Path(r"recall_eval")
PAIRS = [  # lib, import name, old dist dir(s), new dist dir(s)
    ("anthropic", "anthropic", ["anthropic-0.115.0"], ["anthropic-1.8.0"]),
    ("openai", "openai", ["openai-2.44.0"], ["openai-3.19.2"]),
    ("huggingface-hub", "huggingface_hub", ["huggingface_hub-1.21.0"], ["huggingface_hub-2.0.0"]),
    ("mcp", "mcp", ["mcp-1.28.1"], ["mcp-2.2.0", "mcp_types-2.2.0"]),
    ("polars", "polars", ["polars-1.42.1"], ["polars-2.0.0"]),
    ("streamlit", "streamlit", ["streamlit-1.58.0"], ["streamlit-1.66.1"]),
    ("mistralai", "mistralai", ["mistralai-2.5.0"], ["mistralai-3.3.0"]),
]
GRIFFE = str(W / "venvgriffe" / "Scripts" / "griffe.exe")
out = W / "out" / "griffe"; out.mkdir(parents=True, exist_ok=True)


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def copy_pkgs(dists, dest):
    for d in dists:
        for p in (W / "wheels" / d).iterdir():
            if p.is_dir() and not p.name.endswith((".dist-info", ".data")):
                shutil.copytree(p, dest / p.name)


for lib, mod, old, new in PAIRS:
    if len(sys.argv) > 1 and lib not in sys.argv[1:]:
        continue
    # API
    def load(dists):
        return griffe.load(mod, search_paths=[str(W / "wheels" / d) for d in dists], resolve_aliases=False,
                           allow_inspection=True)
    o, n = load(old), load(new)
    br = list(griffe.find_breaking_changes(o, n))
    rows = []
    for b in br:
        rows.append({"path": b.obj.path, "kind": b.kind.name, "kind_text": b.kind.value,
                     "old": str(b.old_value)[:300], "new": str(b.new_value)[:300],
                     "oneline": b.explain(style=griffe.ExplanationStyle.ONE_LINE)[:600]})
    # CLI
    repo = W / "griffe_repos" / lib
    if repo.exists():
        shutil.rmtree(repo, ignore_errors=True)
    repo.mkdir(parents=True)
    git(repo, "init", "-q"); git(repo, "config", "user.email", "x@x"); git(repo, "config", "user.name", "x")
    git(repo, "config", "core.autocrlf", "false")
    copy_pkgs(old, repo); git(repo, "add", "-A"); git(repo, "commit", "-qm", "old"); git(repo, "tag", "old")
    for p in repo.iterdir():
        if p.name != ".git":
            shutil.rmtree(p)
    copy_pkgs(new, repo); git(repo, "add", "-A"); git(repo, "commit", "-qm", "new"); git(repo, "tag", "new")
    cp = subprocess.run([GRIFFE, "check", mod, "-s", ".", "-a", "old", "-b", "new", "-f", "oneline", "--no-color"],
                        cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    (out / f"{lib}.cli.txt").write_text(cp.stdout, encoding="utf-8")
    (out / f"{lib}.cli.err").write_text(cp.stderr, encoding="utf-8")
    cli_lines = [l for l in (cp.stdout + cp.stderr).splitlines() if l.strip()]  # griffe check prints breakages to stderr
    json.dump({"library": lib, "griffe": griffe.__version__ if hasattr(griffe, "__version__") else "2.4.1",
               "n_api": len(rows), "n_cli_lines": len(cli_lines), "cli_exit": cp.returncode, "changes": rows},
              open(out / f"{lib}.json", "w", encoding="utf-8"), indent=1)
    print(lib, "api", len(rows), "cli", len(cli_lines), "exit", cp.returncode, flush=True)
