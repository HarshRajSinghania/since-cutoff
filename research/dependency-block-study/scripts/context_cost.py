"""Per-context block cost: model API calls per context (main sessions vs subagent runs), whether subagent contexts
carry the memory-file channel that delivers CLAUDE.md, and c / f* recomputed per context (round 20, reviewer: 1,281 of
the 1,308 contexts behind f are subagent runs, while c uses a benchmark session's 16.6 turns).

usage: python -I scripts/context_cost.py [<study dir>]   ->   prints aggregates; also written to scripts/context_cost_out.txt

Privacy: reads the local Claude Code transcript store (~/.claude/projects/**/*.jsonl) and prints COUNTS ONLY. No
transcript content, prompt, path, project name or session id is printed or written. Deterministic: files are read in
sorted order and only records stamped before the f run (analysis/f_sessions.json "generated") are used, so later
activity in the store does not change the output except the store-total and X0 counts on line 2.

Context set (as expansion/fsessions/fsess.py, protocol expansion/F_PROTOCOL.md section 3): one context = one .jsonl
transcript (a top-level session or one subagents/agent-*.jsonl run). Exclusions X0 (no real model turn), X1 (benchmark
harness / runs paths) and X2b (research-tree paths) are fsess.py's rules verbatim. X2a (the research session(s) passed to
fsess.py by id on the command line) cannot be replayed without the ids, so it is replaced by its documented effect:
every transcript of a top-level session any of whose transcripts meets X2b is excluded. The script checks the result
against f_sessions.json (included, top-level sessions, subagent transcripts, models) and prints whether they match.

API calls per context = distinct message ids of assistant records with a real model id (not '<synthetic>', not API
error records); Claude Code writes one record per content block, so records are de-duplicated by message id.

Cost (paper Sec. 5 and scripts/round13_numbers.py): c = b (t p_r + p_w), b = 704 tokens (random-sample median
non-empty block), p_r / p_w = Opus 5.5 cache-read / 1-hour cache-write list price from scripts/recompute_cost.py,
t = mean API calls per context (c is linear in t, so the mean gives the expected cost per context).
f* = (c - uK) / (s - uK) with s and K from analysis/exposure2_breakeven.json and analysis/breakeven2d.json.
"""
import collections
import datetime as dt
import glob
import json
import os
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from recompute_cost import PRICES  # noqa: E402

STUDY = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE.parent
STORE = Path(os.path.expanduser("~")) / ".claude" / "projects"
OUT = HERE / "context_cost_out.txt"

# fsess.py exclusion constants, verbatim
PATH_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit", "Read")
EDIT_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
X1_PREFIX = ("c:\\b\\",)
X1_SUB = ("since-cutoff-benchmark", "since-cutoff-bench", "since_cutoff_runs")
X2_SUB = ("\\<research folder>", "ai-research")
BUILTIN_AGENTS = {"general-purpose", "Explore", "Plan", "claude-code-guide", "statusline-setup", "fork"}

BLOCK = 704
P_R, P_W = PRICES["claude-opus-5-5"][2], PRICES["claude-opus-5-5"][3]   # $/MTok cache read, 1h cache write


def low(p):
    return os.path.normpath(p).replace("/", "\\").lower()


def ts_of(r):
    t = r.get("timestamp")
    if not isinstance(t, str):
        return None
    try:
        return dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


def has_claude_marker(s):
    return "claudeMd" in s or ("Contents of" in s and "CLAUDE.md" in s)


def scan(f, cutoff):
    rel = Path(f).relative_to(STORE).parts
    sub = "subagents" in rel
    top = rel[1] if sub else Path(f).stem
    first_ts, models, cwds, paths = None, collections.Counter(), set(), set()
    msg_ids, pre_api = set(), True
    first_span = {"claude_marker": False, "memory_channel": False, "memory_types": set()}
    py_edit = False
    pending = {}
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = ts_of(r)
            if t is not None and t >= cutoff:
                continue
            if r.get("cwd"):
                cwds.add(low(r["cwd"]))
            typ = r.get("type")
            m = r.get("message")
            if typ == "assistant" and isinstance(m, dict):
                mod = m.get("model")
                if mod and not mod.startswith("<"):
                    models[mod] += 1
                    if first_ts is None and r.get("timestamp"):
                        first_ts = r["timestamp"]
                    if not r.get("isApiErrorMessage"):
                        msg_ids.add(m.get("id") or r.get("requestId") or r.get("uuid"))
                        pre_api = False
                for c in m.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in PATH_TOOLS:
                        inp = c.get("input") or {}
                        p = inp.get("file_path") or inp.get("notebook_path") if isinstance(inp, dict) else None
                        if isinstance(p, str) and p:
                            paths.add(low(p))
                            if c.get("name") in EDIT_TOOLS:
                                pending[c.get("id")] = (c.get("name"), inp, low(p))
                continue
            if typ == "user" and isinstance(m, dict) and isinstance(m.get("content"), list):
                for c in m["content"]:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        pe = pending.pop(c.get("tool_use_id"), None)
                        if pe and not c.get("is_error"):
                            name, inp, lp = pe
                            if lp.endswith(".py") and name != "NotebookEdit":
                                py_edit = True
                            elif lp.endswith(".ipynb") and name == "NotebookEdit" and \
                                    (inp.get("cell_type") or "code") == "code":
                                py_edit = True
            if pre_api:   # everything recorded before the context's first model API call
                if typ in ("user", "system") and has_claude_marker(line):
                    first_span["claude_marker"] = True
                if typ == "attachment":
                    a = r.get("attachment") or {}
                    if a.get("type") == "instructions":
                        first_span["memory_channel"] = True
                        for it in a.get("files") or []:
                            if isinstance(it, dict):
                                first_span["memory_types"].add(str(it.get("type")))
                    if has_claude_marker(line):
                        first_span["claude_marker"] = True
    agent_type = None
    if sub:
        meta = Path(f[:-len(".jsonl")] + ".meta.json")
        try:
            at = json.loads(meta.read_text(encoding="utf-8")).get("agentType")
            agent_type = at if at in BUILTIN_AGENTS else "other (custom)"
        except Exception:
            agent_type = "no meta file"
    return {"sub": sub, "top": top, "first_ts": first_ts, "model": models.most_common(1)[0][0] if models else None,
            "locs": list(cwds) + list(paths), "calls": len(msg_ids), "py_edit": py_edit, "agent_type": agent_type,
            **first_span}


def x1(t):
    return any(l.startswith(X1_PREFIX) or any(s in l for s in X1_SUB) for l in t["locs"])


def x2b(t):
    return any(any(s in l for s in X2_SUB) for l in t["locs"])


def dist(v):
    v = sorted(v)
    if not v:
        return {"n": 0}
    p90 = v[min(len(v) - 1, int(round(0.9 * (len(v) - 1))))]   # nearest-rank on (n-1), deterministic
    return {"n": len(v), "median": statistics.median(v), "mean": round(statistics.mean(v), 2), "p90": p90,
            "min": v[0], "max": v[-1]}


def c_of(t, b=BLOCK):
    return b * (t * P_R + P_W) / 1e6


def f_star(c, s, uK):
    if uK >= c:
        return 0.0
    return min(1.0, (c - uK) / (s - uK))


def main():
    fs = json.loads((STUDY / "analysis" / "f_sessions.json").read_text(encoding="utf-8"))
    ex = json.loads((STUDY / "analysis" / "exposure2_breakeven.json").read_text(encoding="utf-8"))
    b2 = json.loads((STUDY / "analysis" / "breakeven2d.json").read_text(encoding="utf-8"))
    cutoff = dt.datetime.fromisoformat(fs["generated"])
    files = sorted(glob.glob(str(STORE / "**" / "*.jsonl"), recursive=True))
    ts = [scan(f, cutoff) for f in files]
    excl = collections.Counter()
    for t in ts:
        t["x"] = ("X0_empty_or_after_f_run" if not t["model"] or not t["first_ts"] else "X1_benchmark" if x1(t)
                  else "X2b" if x2b(t) else None)
    research_tops = {t["top"] for t in ts if t["x"] == "X2b"}
    for t in ts:
        if t["x"] is None and t["top"] in research_tops:
            t["x"] = "X2a_session_of_research_transcript"
        if t["x"] == "X2b":
            t["x"] = "X2a_session_of_research_transcript"
        excl[t["x"] or "included"] += 1
    inc = [t for t in ts if t["x"] is None]
    main_c = [t for t in inc if not t["sub"]]
    sub_c = [t for t in inc if t["sub"]]
    L = []
    say = L.append
    say("context_cost.py: aggregates only (counts); records before the f run, " + fs["generated"])
    say(f"transcripts in store: {len(ts)}; exclusions: {dict(sorted(excl.items()))}")
    chk = {"included": (len(inc), fs["included"]["transcripts"]),
           "top_level_sessions": (len({t['top'] for t in inc}), fs["included"]["top_level_sessions"]),
           "subagent_transcripts": (len(sub_c), fs["included"]["subagent_transcripts"]),
           "models": (dict(collections.Counter(t["model"] for t in inc)), fs["included"]["models"])}
    say("check against analysis/f_sessions.json (this script, fsess.py): " +
        "; ".join(f"{k} {a} vs {b} {'MATCH' if a == b else 'DIFF'}" for k, (a, b) in chk.items()))
    say(f"main-session contexts n = {len(main_c)}; subagent contexts n = {len(sub_c)}")
    say("")
    say("1. Model API calls per context (distinct assistant message ids)")
    D = {"main": dist([t["calls"] for t in main_c]), "subagent": dist([t["calls"] for t in sub_c]),
         "all (as f counted)": dist([t["calls"] for t in inc]),
         "Python-editing contexts (edit_py, the paper's 2-18% base)": dist([t["calls"] for t in inc if t["py_edit"]])}
    for k, v in D.items():
        say(f"   {k}: {v}")
    bytype = collections.defaultdict(list)
    for t in sub_c:
        bytype[t["agent_type"]].append(t["calls"])
    for k in sorted(bytype):
        say(f"   subagent type {k}: {dist(bytype[k])}")
    say("")
    say("2. Memory-file channel in the context before its first API call")
    for name, grp in (("main", main_c), ("subagent", sub_c)):
        n = len(grp)
        k1 = sum(t["claude_marker"] for t in grp)
        k2 = sum(t["memory_channel"] for t in grp)
        types = collections.Counter(x for t in grp for x in t["memory_types"])
        say(f"   {name}: literal CLAUDE.md marker ('claudeMd' or 'Contents of'+'CLAUDE.md') {k1}/{n}; "
            f"'instructions' attachment (the channel that injects CLAUDE.md / memory files) {k2}/{n}; "
            f"file types in it: {dict(types)}")
    for k in sorted(bytype):
        grp = [t for t in sub_c if t["agent_type"] == k]
        say(f"   subagent type {k}: instructions attachment {sum(t['memory_channel'] for t in grp)}/{len(grp)}")
    say("")
    say("3. Python-editing share (fsess.py edit_py rule) by context kind; f_upper / f_strict cannot be split from")
    say("   f_sessions.json (per-transcript scan flags were deleted with the private work folder)")
    ep_m, ep_s = sum(t["py_edit"] for t in main_c), sum(t["py_edit"] for t in sub_c)
    say(f"   edit_py: main {ep_m}/{len(main_c)} = {ep_m / len(main_c):.3f}; subagent {ep_s}/{len(sub_c)} = "
        f"{ep_s / len(sub_c):.3f}; all {ep_m + ep_s}/{len(inc)} (f_sessions.json: {fs['primary']['edit_py']['k']})")
    sl = fs["primary_session_level"]
    up, st = fs["primary"]["upper"]["k"], fs["primary"]["strict"]["k"]
    nm, ns = len(main_c), len(sub_c)
    say(f"   session level (top session pooled with its subagents, f_sessions.json): upper {sl['upper']}/"
        f"{sl['n_top_level_sessions']} = {sl['upper'] / sl['n_top_level_sessions']:.3f}, strict {sl['strict']}/"
        f"{sl['n_top_level_sessions']} = {sl['strict'] / sl['n_top_level_sessions']:.3f}")
    say(f"   bounds (each main transcript is in its own top session): f_upper main <= {sl['upper']}/{nm} = "
        f"{sl['upper'] / nm:.3f}, subagent in [{(up - sl['upper']) / ns:.3f}, {up / ns:.3f}]; f_strict main <= "
        f"{sl['strict']}/{nm} = {sl['strict'] / nm:.3f}, subagent in [{(st - sl['strict']) / ns:.4f}, {st / ns:.4f}]")
    say("")
    s_main = ex["studies"]["main"]["S_gross_usd"]
    s_new = ex["studies"]["new_tasks"]["S_gross_usd"]
    t_bench_main = ex["studies"]["main"]["mean_C_turns"]
    t_bench_new = ex["studies"]["new_tasks"]["mean_C_turns"]
    b_hi = ex["block_sizes_tokens"]["AI_mean_nonempty"]
    K = b2["K_control_A_mean_cost_usd"]
    uc = b2["u_range_from_controls"]["cost"]
    us = {"u = 0 (reference)": 0.0, f"u = {uc['u_ci_low']} (cost CI low)": uc["u_ci_low"],
          f"u = {uc['u_point']} (cost point)": uc["u_point"]}
    say(f"4. Cost per context: c = b (t p_r + p_w), b = {BLOCK}, p_r = ${P_R}/MTok, p_w = ${P_W}/MTok "
        f"(recompute_cost.py, Opus 5.5); s = ${s_main:.4f} (main), K = ${K}")
    rows = [("benchmark session (paper)", t_bench_main), ("main session, mean", D["main"]["mean"]),
            ("main session, median", D["main"]["median"]), ("subagent context, mean", D["subagent"]["mean"]),
            ("subagent context, median", D["subagent"]["median"]),
            ("pooled per context as f counted, mean", D["all (as f counted)"]["mean"]),
            ("Python-editing context, mean", D["Python-editing contexts (edit_py, the paper's 2-18% base)"]["mean"]),
            ("floor: one cache write, t = 0", 0)]
    for name, t in rows:
        c = c_of(t)
        fst = "; ".join(f"{k}: f* = {f_star(c, s_main, u * K):.4f}" for k, u in us.items())
        say(f"   {name}: t = {t}, c = ${c:.5f}; {fst}; pays at every f once u >= c/K = {c / K:.4f}")
    n_top = len({t["top"] for t in inc})
    c_top = sum(c_of(t["calls"]) for t in inc) / n_top
    say(f"   per top-level session incl. its subagents (every context loads the block; {len(inc)} contexts / {n_top} "
        f"sessions = {len(inc) / n_top:.1f}): c = ${c_top:.4f} = {c_top / s_main:.2f} x s, so at a single-context "
        f"saving s the block never pays per session (f* = {f_star(c_top, s_main, 0.0):.2f}, capped) unless the "
        f"saving also scales with the number of contexts")
    say("")
    say(f"5. The paper's u = 0 range '9-30%' re-evaluated: low end = main saving, {BLOCK} tokens; high end = new-task "
        f"saving ${s_new:.4f}, {b_hi} tokens (AI-stack mean)")
    for name, t_lo, t_hi in (("paper (benchmark turns)", t_bench_main, t_bench_new),
                             ("main session, mean", D["main"]["mean"], D["main"]["mean"]),
                             ("subagent context, mean", D["subagent"]["mean"], D["subagent"]["mean"]),
                             ("pooled per context, mean", D["all (as f counted)"]["mean"], D["all (as f counted)"]["mean"])):
        lo = f_star(c_of(t_lo), s_main, 0.0)
        hi = f_star(c_of(t_hi, b_hi), s_new, 0.0)
        say(f"   {name}: {lo:.4f} to {hi:.4f}")
    text = "\n".join(L) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
