"""Precision sample (protocol section 6): up to 8 reported changes per library per detector (random.Random(20261023)
over the report list in output order), plus every line of the capped (5 per package) one-file-project blocks of
0.4.1 and C2 (margin 0). For each, text/AST evidence from both wheels (evidence.lookup) is attached for the
AI judge. Output: out/precision/sample.json and a readable sample.txt."""
import json, random, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evidence import lookup  # noqa: E402

W = Path(r"recall_eval"); NORM = W / "out" / "norm"; OUTP = W / "out" / "precision"
LIBS = ["anthropic", "openai", "huggingface-hub", "mcp", "polars", "streamlit", "mistralai"]
DISTS = {"anthropic": ("anthropic-0.115.0", "anthropic-1.8.0"), "openai": ("openai-2.44.0", "openai-3.19.2"),
         "huggingface-hub": ("huggingface_hub-1.21.0", "huggingface_hub-2.0.0"), "mcp": ("mcp-1.28.1", "mcp-2.2.0"),
         "polars": ("polars-1.42.1", "polars-2.0.0"), "streamlit": ("streamlit-1.58.0", "streamlit-1.66.1"),
         "mistralai": ("mistralai-2.5.0", "mistralai-3.3.0")}
DETECTORS = ["sc041", "scc2m0", "griffe", "aexpy"]
NOTES = ["sc041_cap5", "scc2m0_cap5"]
K = 8


def ev(lib, path):
    if not path:
        return None
    o, n = DISTS[lib]
    out = {"old": lookup(o, path), "new": lookup(n, path)}
    if lib == "mcp" and path.startswith("mcp.types") and not out["new"].get("found"):
        out["new_mcp_types"] = lookup("mcp_types-2.2.0", "mcp_types" + path[len("mcp.types"):])
    return out


def main(tools):
    OUTP.mkdir(parents=True, exist_ok=True)
    sample_path = OUTP / "sample.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8")) if sample_path.exists() else {}
    for t in tools:
        for lib in LIBS:
            p = NORM / t / f"{lib}.json"
            if not p.exists():
                continue
            rows = json.loads(p.read_text(encoding="utf-8"))
            picked = rows if (t in NOTES or len(rows) <= K) else random.Random(20261023).sample(rows, K)
            for r in picked:
                key = r["rid"]
                paths = [r["path"]] if r["path"] else [x for x in r["paths"] if "." in x][:3]
                sample[key] = {"tool": t, "lib": lib, "kind": r["kind"], "path": r["path"], "param": r.get("param"),
                               "text": r["text"], "evidence": {pp: ev(lib, re.sub(r"\(.*$", "", pp)) for pp in paths[:3]}}
    json.dump(sample, open(sample_path, "w", encoding="utf-8"), indent=1)
    lines = []
    for k, s in sample.items():
        if s["tool"] not in tools:
            continue
        lines.append(f"\n## {k} [{s['kind']}] param={s['param']}\n  {s['text'][:300]}")
        for pp, e in s["evidence"].items():
            if not e:
                continue
            for side in ("old", "new", "new_mcp_types"):
                if side in e:
                    d = e[side]
                    lines.append(f"  {side:4} {pp[-60:]}: found={d.get('found')} {d.get('kind','')} "
                                 f"params={d.get('params') or d.get('init_params') or ''} src={d.get('src','')[:80]} "
                                 f"missing={d.get('missing','')} imported={d.get('imported','')} getattr={d.get('module_getattr','')} "
                                 f"in_all={d.get('in_all','')} dec={d.get('decorators','')}"[:600])
    (OUTP / f"sample_{'_'.join(tools)}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(len([s for s in sample.values() if s["tool"] in tools]))


if __name__ == "__main__":
    main(sys.argv[1:])
