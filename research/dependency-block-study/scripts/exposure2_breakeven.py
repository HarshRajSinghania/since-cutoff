"""Break-even share of sessions that need a changed API, at the block sizes of the random two-stratum exposure sample.

Exploratory, added 2026-10-23. It applies the overhead model of blocksize_breakeven.py (block size x (mean C turns x
cache-read price + one one-hour cache write) per session) and each study's gross saving per affected session from
analysis/blocksize_breakeven.json to the median and mean non-empty imported-scope blocks of the two strata in
analysis/exposure2.json (point estimates only; not bootstrapped).

usage: python scripts/exposure2_breakeven.py   -> writes analysis/exposure2_breakeven.json
"""
import json
from pathlib import Path

STUDY = Path(__file__).resolve().parent.parent
be = json.loads((STUDY / "analysis" / "blocksize_breakeven.json").read_text(encoding="utf-8"))["break_even"]
ex = json.loads((STUDY / "analysis" / "exposure2.json").read_text(encoding="utf-8"))["exposure"]
prices = be["prices_usd_per_mtok"]

sizes = {}
for stratum in ("G", "AI"):
    tok = ex["strata"][stratum]["block_imported_scope"]["tokens_nonempty"]
    sizes[f"{stratum}_median_nonempty"] = tok["median"]
    sizes[f"{stratum}_mean_nonempty"] = round(tok["mean"])

out = {"generated_by": "scripts/exposure2_breakeven.py", "prices_usd_per_mtok": prices, "block_sizes_tokens": sizes,
       "studies": {}}
for name, st in be["studies"].items():
    turns = st["mean_C_turns"]
    gross = st["S_gross_usd"]["value"]
    per_token = (turns * prices["cache_read"] + prices["cache_write_1h"]) / 1e6
    out["studies"][name] = {
        "mean_C_turns": turns,
        "S_gross_usd": gross,
        "by_block_size": {
            k: {"T_tokens": t, "overhead_per_session_usd": round(t * per_token, 5),
                "break_even_share": round(t * per_token / gross, 4)}
            for k, t in sizes.items()
        },
    }

(STUDY / "analysis" / "exposure2_breakeven.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
for name, st in out["studies"].items():
    print(name, {k: v["break_even_share"] for k, v in st["by_block_size"].items()})
