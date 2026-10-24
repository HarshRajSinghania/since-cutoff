"""For each (item, detector) the auto-matcher marked N, list reports that mention the item's names (loose), so the
adjudicator can catch matcher misses. Output: out/auto/<lib>[.tasks].miss.txt"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from candidates import gt_items, task_items, comps  # noqa: E402
from automatch import DETECTORS, NOTES, NORM, AUTO  # noqa: E402


def names(it):
    out = set()
    for p in [it.get("old_path") or ""] + list(it.get("api_names") or []):
        c = comps(p)
        if c:
            out.add(c[-1])
            if len(c) >= 2 and c[-2][:1].isupper():
                out.add(c[-2])
    out |= set(it.get("params") or [])
    return {n for n in out if len(n) >= 4 and n not in {"create", "list", "update", "delete", "retrieve", "__init__"}}


def run(lib, items, tag):
    auto = json.loads((AUTO / f"{lib}{tag}.json").read_text(encoding="utf-8"))
    rows = {t: json.loads((NORM / t / f"{lib}.json").read_text(encoding="utf-8"))
            for t in DETECTORS + NOTES if (NORM / t / f"{lib}.json").exists()}
    txt = []
    for it in items:
        ns = names(it)
        block = []
        for t, rs in rows.items():
            a = auto[it["id"]].get(t)
            if a is None or a["auto"]:
                continue
            hits = [r for r in rs if any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])",
                                                   r["path"] + " " + r["text"]) for n in ns)]
            if hits:
                block.append(f"   {t}: {len(hits)} | " + " || ".join(f"{h['rid'].split('-')[-1]} {h['kind']} {h['path'][-70:]} {h['text'][:90] if not h['path'] else (h.get('param') or '')}" for h in hits[:3]))
        if block:
            txt.append(f"{it['id']} [{it['change_type']}] {it.get('old_path')} {it.get('params') or ''}\n" + "\n".join(block))
    (AUTO / f"{lib}{tag}.miss.txt").write_text("\n".join(txt), encoding="utf-8")


if __name__ == "__main__":
    for lib in sys.argv[1:]:
        run(lib, gt_items(lib), "")
        run(lib, task_items(lib), ".tasks")
