"""Propose candidate tool reports for each GT item (identifier match), for AI adjudication.

Levels: E = a report path ends with the item's Owner.name (or equals a GT path); C = the report's path is a
containing module/class of a GT path; P = report parameter is one of the item's params on a callable of the same
name; T = the item's name or one of its params occurs in the report text. Output: out/cand/<lib>.txt (for reading)
and out/cand/<lib>.json.
"""
import json, re, sys
from pathlib import Path

W = Path(r"recall_eval"); NORM = W / "out" / "norm"; CAND = W / "out" / "cand"
GT = Path(r"research/dependency-block-study\expansion\recall\gt")
TOOLS = ["sc041", "scc2m0", "scc2", "griffe", "aexpy", "sc041_cap5", "sc041_cap10", "scc2m0_cap5", "scc2m0_cap10",
         "scc2_cap5", "sc041_frozen", "scc2_frozen"]
CAP = 5


def comps(p):
    p = re.sub(r"\(.*$", "", p or "").replace(":", ".").replace("/", ".")
    return [c for c in p.split(".") if c]


def gt_items(lib):
    d = json.loads((GT / f"{lib}.json").read_text(encoding="utf-8"))
    cands = {c["id"]: c for c in d["candidates"]}
    ver = {v["id"]: v for v in d["verification"]}
    items = []
    for i in d["sample"]:
        c = dict(cands[i]); c["change_type"] = ver[i]["change_type"]; items.append(c)
    return items


def task_items(lib):
    d = json.loads((GT / "_tasks.json").read_text(encoding="utf-8"))
    return [dict(x, api_names=[x["old_path"]], new_path=None) for x in d["items"] if x["library"] == lib]


def match(item, r, notes):
    paths = [item.get("old_path") or ""] + list(item.get("api_names") or [])
    if item.get("new_path"):
        paths.append(item["new_path"])
    gcs = [comps(p) for p in paths if p]
    names = {g[-1] for g in gcs if g}
    params = set(item.get("params") or [])
    if notes:
        ticks = " ".join(r["paths"]) + " " + r["text"]
        hits = [n for n in names | params if len(n) >= 3 and re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", ticks)]
        return ("T", hits) if hits else None
    best = None
    for rp in r["paths"]:
        rc = comps(rp)
        if not rc:
            continue
        for g in gcs:
            if not g:
                continue
            if rc == g or (len(g) >= 2 and len(rc) >= 2 and rc[-2:] == g[-2:]):
                return ("E", rp)
            if len(rc) < len(g) and g[:len(rc)] == rc and len(rc) >= 2:
                best = best or ("C", rp)
            if r.get("param") and r["param"] in params and rc[-1] == g[-1]:
                return ("P", rp)
    if best:
        return best
    hits = [n for n in names | params if len(n) >= 4 and re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", r["text"])]
    if hits and (not params or set(hits) & params or len(hits) == len(names | params)):
        return ("T", hits)
    return None


def run(lib, items, tag):
    reports = {}
    for t in TOOLS:
        p = NORM / t / f"{lib}.json"
        reports[t] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    lines, out = [], {}
    order = {"E": 0, "P": 1, "C": 2, "T": 3}
    for it in items:
        lines.append(f"\n### {it['id']} [{it['change_type']}] {it.get('old_path')} params={it.get('params')} new={it.get('new_path')}\n    {it['description']}")
        out[it["id"]] = {}
        for t, rows in reports.items():
            if rows is None:
                lines.append(f"  {t}: (no output)"); continue
            hits = []
            for r in rows:
                m = match(it, r, t.endswith(("cap5", "cap10", "frozen")))
                if m:
                    hits.append((order[m[0]], m[0], r))
            hits.sort(key=lambda h: h[0])
            out[it["id"]][t] = [{"level": lv, "rid": r["rid"], "text": r["text"][:300]} for _, lv, r in hits]
            if hits:
                lines.append(f"  {t}: {len(hits)} cand")
                for _, lv, r in hits[:CAP]:
                    lines.append(f"    {lv} {r['rid'].split('-')[-1]} {r['text'][:230]}")
            else:
                lines.append(f"  {t}: -")
    CAND.mkdir(parents=True, exist_ok=True)
    (CAND / f"{lib}{tag}.txt").write_text("\n".join(lines), encoding="utf-8")
    json.dump(out, open(CAND / f"{lib}{tag}.json", "w", encoding="utf-8"), indent=0)


if __name__ == "__main__":
    for lib in sys.argv[1:]:
        run(lib, gt_items(lib), "")
        run(lib, task_items(lib), ".tasks")
