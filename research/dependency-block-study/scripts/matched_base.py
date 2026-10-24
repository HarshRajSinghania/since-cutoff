"""Break-even comparisons on matched bases (round 21, verifier rows 1-3, Reviewer A W3).

Every comparison of a measured f with a break-even uses the same contexts on both sides: either all agent contexts
(f_strict 0.84%, f_upper 6.96%; mean 45.26 model calls) or Python-editing contexts (f_strict 2.14%, f_upper 17.74%;
mean 81.55 calls). For each base: c, f* at u = 0 and at the control-task point estimate u = 6.63%, c/K, the u at
which the block pays at the measured f, the size cap b_max at u = 0, and the 1,000-context fleet example at u = 0.
Also re-derives the third audit's snippet split (row d of Reviewer A) from the second-audit files if present.

usage: python -I scripts/matched_base.py   ->   prints; also written to scripts/matched_base_out.txt
Inputs: analysis/f_sessions.json (f), scripts/context_cost_out.txt values (mean calls per context, as printed by
context_cost.py), analysis/exposure2_breakeven.json (s for main, replication, new tasks), analysis/breakeven2d.json
(K, u point estimate), recompute_cost.PRICES (Opus 5.5 cache read / 1-hour write).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
I1 = HERE.parent
OUT = HERE / "matched_base_out.txt"
sys.path.insert(0, str(HERE))
from recompute_cost import PRICES  # noqa: E402

P_R, P_W = PRICES["claude-opus-5-5"][2] / 1e6, PRICES["claude-opus-5-5"][3] / 1e6
B = 704
fs = json.loads((I1 / "analysis" / "f_sessions.json").read_text(encoding="utf-8"))["primary"]
eb = json.loads((I1 / "analysis" / "exposure2_breakeven.json").read_text(encoding="utf-8"))["studies"]
b2 = json.loads((I1 / "analysis" / "breakeven2d.json").read_text(encoding="utf-8"))
K = b2["K_control_A_mean_cost_usd"]
U_PT = b2["u_range_from_controls"]["cost"]["u_point"]
S = {k: eb[k]["S_gross_usd"] for k in ("main", "replication", "new_tasks")}
T_CTX = {"all contexts": 45.26, "Python-editing contexts": 81.55, "benchmark (16.6 CLI turns)": 16.647058823529413}
F = {"all contexts": (fs["strict"]["share"], fs["upper"]["share"]),
     "Python-editing contexts": (fs["given_edit_py"]["strict"]["share"], fs["given_edit_py"]["upper"]["share"])}


def fstar(c, s, u):
    return max(0.0, min(1.0, (c - u * K) / (s - u * K)))


def u_needed(c, s, f):
    return (c - f * s) / (K * (1 - f))


lines = [f"matched_base.py: b = {B} tokens, K = ${K}, u point estimate (control cost) = {U_PT}, s = {S}"]
for base, t in T_CTX.items():
    per_tok = t * P_R + P_W
    c = B * per_tok
    lines.append(f"\n[{base}] t = {t:.2f}: c = ${c:.5f}; c/K = {c / K:.4f}")
    lines.append(f"  f* (main s): u = 0 {fstar(c, S['main'], 0):.4f}; u = point {fstar(c, S['main'], U_PT):.4f}; "
                 f"u = -0.037 {fstar(c, S['main'], -0.037):.4f}")
    lines.append(f"  b_max at u = 0 (tokens per unit f): main {S['main'] / per_tok:.0f}, replication "
                 f"{S['replication'] / per_tok:.0f}, new tasks {S['new_tasks'] / per_tok:.0f}")
    if base in F:
        for name, f in zip(("f_strict", "f_upper"), F[base]):
            lines.append(f"  {name} = {f:.4f}: u needed (main s) {u_needed(c, S['main'], f):.4f}; b_max at u = 0 "
                         f"{f * S['main'] / per_tok:.0f} tokens; fleet of 1,000 contexts/day at u = 0: pays "
                         f"${1000 * c:.2f}, saves ${1000 * f * S['main']:.2f}, net ${1000 * (f * S['main'] - c):.2f}")
    if base.startswith("all"):
        # pooled-range check: 704 tokens with the main saving .. 1,320 tokens with the new-task saving
        lo = fstar(c, S["main"], 0)
        hi = fstar(1320 * per_tok, S["new_tasks"], 0)
        lines.append(f"  u = 0 range over sizes and savings (704/main .. 1320/new tasks): {lo:.4f} .. {hi:.4f}")

# second audit snippets (Reviewer A, row d): counts only
aud = Path("since_cutoff_runs/realworld2/audit")
if (aud / "verdicts.json").exists() and (aud / "runtime_results.json").exists():
    v = json.loads((aud / "verdicts.json").read_text(encoding="utf-8"))
    r = json.loads((aud / "runtime_results.json").read_text(encoding="utf-8"))
    tp = sum(1 for k in r if (v.get(k) or {}).get("verdict") == "TP")
    ok_tp = sum(1 for k in r if (v.get(k) or {}).get("verdict") == "TP" and r[k].get("outcome") == "ok")
    fp = sum(1 for k in r if str((v.get(k) or {}).get("verdict", "")).startswith("FP"))
    ok_fp = sum(1 for k in r if str((v.get(k) or {}).get("verdict", "")).startswith("FP") and r[k].get("outcome") == "ok")
    lines.append(f"\nsecond audit snippets: {len(r)} run; on true uses {tp} ({ok_tp} ran cleanly); on false positives "
                 f"{fp} ({ok_fp} ran cleanly)")
txt = "\n".join(lines)
print(txt)
OUT.write_text(txt + "\n", encoding="utf-8")
