"""Compact Y/N matrix of the auto-matcher (review aid)."""
import json, sys
from pathlib import Path
from candidates import gt_items, task_items
AUTO = Path(r"recall_eval\out\auto")
COLS = ["sc041", "scc2m0", "scc2", "griffe", "aexpy", "sc041_cap5", "sc041_cap10", "scc2m0_cap5", "scc2_cap5", "sc041_frozen", "scc2_frozen"]
for lib in sys.argv[1:]:
    for tag, items in (("", gt_items(lib)), (".tasks", task_items(lib))):
        a = json.loads((AUTO / f"{lib}{tag}.json").read_text(encoding="utf-8"))
        print(f"== {lib}{tag}  cols: " + " ".join(c.replace("sc041", "41").replace("scc2m0", "m0").replace("scc2", "c2").replace("_cap", "k").replace("_frozen", "F").replace("griffe", "gr").replace("aexpy", "ax") for c in COLS))
        for it in items:
            cells = []
            for c in COLS:
                v = a[it["id"]].get(c)
                cells.append("." if v is None else (v["level"] if v["auto"] else "-"))
            print(f"{it['id']:8} {it['change_type'][:6]:6} {' '.join(f'{x:>3}' for x in cells)}  {(it.get('old_path') or '')[-55:]}")
