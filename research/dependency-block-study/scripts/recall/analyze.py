"""Aggregate recall / precision (protocol section 7) -> <study>/analysis/recall_eval.json.

Inputs: gt/*.json (frozen ground truth), out/auto/*.json (rule-based proposals), adjudication.json (AI overrides),
out/precision/judged.json (AI-judged precision), out/norm/* (report counts), the frozen notes manifests."""
import hashlib, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from candidates import gt_items, task_items  # noqa: E402

W = Path(r"recall_eval"); OUT = W / "out"
STUDY = HERE.parent.parent
LIBS = ["anthropic", "openai", "huggingface-hub", "mcp", "polars", "streamlit", "mistralai"]
DET = ["sc041", "scc2m0", "scc2", "griffe", "aexpy"]
NOTES = ["sc041_cap5", "sc041_cap10", "scc2m0_cap5", "scc2m0_cap10", "scc2_cap5", "sc041_frozen", "scc2_frozen"]
TYPES = ["removal", "rename_move", "signature", "default_change", "behaviour_only", "dependency_switch"]
NAMES = {"sc041": "since-cutoff 0.4.1", "scc2m0": "since-cutoff C2 (3f0144f), same pair (--cutoff-margin 0)",
         "scc2": "since-cutoff C2 as deployed (30-day cutoff margin: compares from an earlier release)",
         "griffe": "griffe check 2.4.1", "aexpy": "AexPy 0.4.3 (rank >= Low)"}


def wilson(k, n, z=1.959964):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(k / n, 4), round(max(0, c - h), 4), round(min(1, c + h), 4)]


def prop(k, n):
    return {"k": k, "n": n, "p_ci": wilson(k, n)}


def mcnemar(a, b):
    """exact two-sided McNemar on paired booleans"""
    b10 = sum(1 for x, y in zip(a, b) if x and not y)
    b01 = sum(1 for x, y in zip(a, b) if y and not x)
    n = b10 + b01
    if n == 0:
        return {"a_only": 0, "b_only": 0, "p": 1.0}
    k = min(b10, b01)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"a_only": b10, "b_only": b01, "p": round(p, 6)}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_decisions(tag):
    adj = json.loads((HERE / "adjudication.json").read_text(encoding="utf-8"))["overrides"]
    ov = {(o["item"], o["tool"]): o for o in adj}
    rows = []
    for lib in LIBS:
        items = gt_items(lib) if tag == "" else task_items(lib)
        auto = json.loads((OUT / "auto" / f"{lib}{tag}.json").read_text(encoding="utf-8"))
        for it in items:
            rec = {"id": it["id"], "library": lib, "change_type": it["change_type"], "description": it["description"],
                   "old_path": it.get("old_path"), "params": it.get("params")}
            if tag == "":
                rec.update(source_url=it.get("source_url"), documented_in=it.get("documented_in"))
            for t in DET + NOTES:
                a = auto[it["id"]].get(t)
                if a is None:
                    rec[t] = None
                    continue
                d = {"detected": a["auto"], "level": a["level"]}
                o = ov.get((it["id"], t))
                if o:
                    if "detected" in o:
                        d["detected"] = o["detected"]
                        d["level"] = o.get("level", d["level"] if o["detected"] else None)
                    if o.get("inaccurate"):
                        d["inaccurate"] = True
                    d["adjudication"] = o["why"]
                rec[t] = d
            rows.append(rec)
    return rows


def recall_block(rows, tool, filt=lambda r: True, exact=False, accurate=False):
    sel = [r for r in rows if filt(r) and r.get(tool) is not None]
    def hit(r):
        d = r[tool]
        if not d["detected"]:
            return False
        if exact and d["level"] == "C":
            return False
        if accurate and d.get("inaccurate"):
            return False
        return True
    return prop(sum(hit(r) for r in sel), len(sel))


def main():
    rows = load_decisions("")
    trows = load_decisions(".tasks")
    res = {"description": "Recall of documented breaking/behavioural public-API changes and precision of reported changes, "
                          "for since-cutoff 0.4.1, since-cutoff C2 (3f0144f), griffe check and AexPy on the benchmark's 7 "
                          "library version pairs. Offline; ground truth from official changelogs/release notes/migration "
                          "guides, verified against the wheels; matching and precision AI-judged (Claude Opus 5.5), no human.",
           "protocol": {"file": "expansion/RECALL_PROTOCOL.md", "sha256": sha(HERE.parent / "RECALL_PROTOCOL.md")},
           "ground_truth": {"files": {p.name: sha(p) for p in sorted((HERE / "gt").glob("*.json"))},
                            "frozen_record": (HERE / "gt" / "GT_SHA256SUMS.txt").read_text(encoding="utf-8")},
           "tools": NAMES}
    # GT composition
    comp = {}
    for lib in LIBS:
        g = json.loads((HERE / "gt" / f"{lib}.json").read_text(encoding="utf-8"))
        ver = {v["id"]: v for v in g["verification"]}
        comp[lib] = {"pair": f"{g['from']} -> {g['to']}", "candidates": len(g["candidates"]),
                     "excluded_by_reason": g.get("excluded_counts") or dict(Counter(e["reason"] for e in g["excluded"])),
                     "verified_checked": len(g["verification"]),
                     "failed_verification": dict(Counter(v["status"] for v in g["verification"] if v["status"] != "verified")),
                     "sample": len(g["sample"]),
                     "sample_by_type": dict(Counter(ver[i]["change_type"] for i in g["sample"]))}
    res["ground_truth"]["composition"] = comp
    res["ground_truth"]["n_items"] = len(rows)
    res["ground_truth"]["by_type"] = dict(Counter(r["change_type"] for r in rows))
    # report volume
    summ = json.loads((OUT / "norm" / "summary.json").read_text(encoding="utf-8"))
    res["reports_per_pair"] = {t: {lib: summ.get(f"{t}/{lib}") for lib in LIBS} for t in DET + NOTES}
    # recall
    rec = {}
    for t in DET:
        rr = {"overall": recall_block(rows, t),
              "overall_exact_path_only": recall_block(rows, t, exact=True),
              "overall_accurate_match_only": recall_block(rows, t, accurate=True),
              "static_visible_types (excl. behaviour_only)": recall_block(rows, t, lambda r: r["change_type"] != "behaviour_only"),
              "by_library": {lib: recall_block(rows, t, lambda r, l=lib: r["library"] == l) for lib in LIBS},
              "by_type": {ty: recall_block(rows, t, lambda r, y=ty: r["change_type"] == y) for ty in TYPES}}
        libs = [v["p_ci"][0] for v in rr["by_library"].values() if v["n"]]
        rr["macro_average_over_libraries"] = round(sum(libs) / len(libs), 4) if libs else None
        rr["by_library_excluding_tool_not_run"] = None
        rec[t] = rr
    res["recall_detector"] = rec
    # notes-level recall (what reaches the block)
    nrec = {}
    for t in NOTES:
        nrec[t] = {"overall": recall_block(rows, t),
                   "by_library": {lib: recall_block(rows, t, lambda r, l=lib: r["library"] == l) for lib in LIBS},
                   "by_type": {ty: recall_block(rows, t, lambda r, y=ty: r["change_type"] == y) for ty in TYPES}}
    res["recall_notes"] = nrec
    # cap effect: of the items the detector found, how many reach the capped block
    cap = {}
    for det, c5, c10 in (("sc041", "sc041_cap5", "sc041_cap10"), ("scc2m0", "scc2m0_cap5", "scc2m0_cap10")):
        found = [r for r in rows if r[det]["detected"]]
        cap[det] = {"detector_recall": recall_block(rows, det), "cap10_recall": recall_block(rows, c10),
                    "cap5_recall": recall_block(rows, c5),
                    "of_detected_reaching_cap5": prop(sum(r[c5]["detected"] for r in found), len(found)),
                    "of_detected_reaching_cap10": prop(sum(r[c10]["detected"] for r in found), len(found)),
                    "notes_only_hits_not_detected": sum(1 for r in rows if r[c5]["detected"] and not r[det]["detected"])}
    # share of detector reports whose API is named in the capped block (one-file project)
    share = {}
    for det, c5 in (("sc041", "sc041_cap5"), ("scc2m0", "scc2m0_cap5")):
        per = {}
        for lib in LIBS:
            reps = json.loads((OUT / "norm" / det / f"{lib}.json").read_text(encoding="utf-8"))
            lines = json.loads((OUT / "norm" / c5 / f"{lib}.json").read_text(encoding="utf-8"))
            ticks = set()
            for l in lines:
                for tk in re.findall(r"`([^`]+)`", l["text"]):
                    ticks.add(re.sub(r"\(\)$", "", tk))
            named = 0
            for r in reps:
                cand = {r["path"]} | set(r["paths"])
                short = {".".join(p.split(".")[-2:]) for p in cand}
                if cand & ticks or short & ticks:
                    named += 1
            per[lib] = {"reports": len(reps), "named_in_cap5_block": named, "block_lines": len(lines)}
        tot_r = sum(v["reports"] for v in per.values()); tot_n = sum(v["named_in_cap5_block"] for v in per.values())
        share[det] = {"per_library": per, "total_reports": tot_r, "named_in_block": tot_n,
                      "share_named": round(tot_n / tot_r, 4) if tot_r else None}
    cap["share_of_detector_reports_named_in_cap5_block"] = share
    res["cap_effect"] = cap
    # paired comparisons (exploratory)
    def vec(t):
        return [bool(r[t] and r[t]["detected"]) for r in rows]
    pairs = {}
    for a, b in (("sc041", "griffe"), ("sc041", "scc2m0"), ("scc2m0", "griffe"), ("sc041", "aexpy"), ("griffe", "aexpy"),
                 ("scc2m0", "aexpy")):
        if all(r.get(a) is not None and r.get(b) is not None for r in rows):
            pairs[f"{a}_vs_{b}"] = mcnemar(vec(a), vec(b))
        else:
            ok = [r for r in rows if r.get(a) is not None and r.get(b) is not None]
            pairs[f"{a}_vs_{b}"] = dict(mcnemar([bool(r[a]["detected"]) for r in ok], [bool(r[b]["detected"]) for r in ok]), n=len(ok))
    res["paired_mcnemar_exploratory"] = pairs
    union = [any(r[t] and r[t]["detected"] for t in ("sc041", "scc2m0", "griffe", "aexpy")) for r in rows]
    res["union_of_detectors_recall"] = prop(sum(union), len(rows))
    res["missed_by_all_detectors_by_type"] = dict(Counter(r["change_type"] for r, u in zip(rows, union) if not u))
    # task-change set
    man = {}
    for folder, key in (("sonnet-5-5", "sc041"), ("tasks2-opus-5-5", "sc041"), ("tasks2-opus-5-5-v2", "scc2")):
        m = json.loads((STUDY / "notes" / folder / "MANIFEST.json").read_text(encoding="utf-8"))
        for k, v in m["tasks"].items():
            man.setdefault(key, {})[k] = v["covered"]
    tasks = []
    for r in trows:
        tasks.append({"task": r["id"], "library": r["library"], "change_type": r["change_type"],
                      **{t: (r[t]["detected"] if r[t] else None) for t in DET},
                      "sc041_cap5_one_file_project": r["sc041_cap5"]["detected"],
                      "scc2m0_cap5_one_file_project": r["scc2m0_cap5"]["detected"],
                      "frozen_block_covered_0.4.1 (manifest note_keys)": man["sc041"].get(r["id"]),
                      "frozen_block_covered_C2 (manifest, tasks2 only)": man.get("scc2", {}).get(r["id"])})
    tsum = {t: prop(sum(bool(x[t]) for x in tasks if x[t] is not None), sum(1 for x in tasks if x[t] is not None)) for t in DET}
    tsum["frozen_block_0.4.1"] = prop(sum(bool(x["frozen_block_covered_0.4.1 (manifest note_keys)"]) for x in tasks), len(tasks))
    t2 = [x for x in tasks if x["frozen_block_covered_C2 (manifest, tasks2 only)"] is not None]
    tsum["frozen_block_C2_tasks2"] = prop(sum(bool(x["frozen_block_covered_C2 (manifest, tasks2 only)"]) for x in t2), len(t2))
    tsum["sc041_cap5_one_file_project"] = prop(sum(bool(x["sc041_cap5_one_file_project"]) for x in tasks), len(tasks))
    tsum["scc2m0_cap5_one_file_project"] = prop(sum(bool(x["scc2m0_cap5_one_file_project"]) for x in tasks), len(tasks))
    det_not_frozen = [x["task"] for x in tasks if x["sc041"] and not x["frozen_block_covered_0.4.1 (manifest note_keys)"]]
    res["task_changes"] = {"per_task": tasks, "summary": tsum,
                           "detected_by_0.4.1_but_not_in_frozen_block": det_not_frozen}
    # precision
    jud = json.loads((OUT / "precision" / "judged.json").read_text(encoding="utf-8"))
    prec = {}
    for t in DET + ["sc041_cap5", "scc2m0_cap5"]:
        js = [v for v in jud.values() if v["tool"] == t]
        if not js:
            prec[t] = None
            continue
        prec[t] = {"lenient_accurate": prop(sum(bool(v["accurate"]) for v in js), len(js)),
                   "strict_accurate_and_breaking": prop(sum(bool(v["accurate"] and v["breaking"]) for v in js), len(js)),
                   "by_library": {lib: {"n": sum(1 for v in js if v["lib"] == lib),
                                        "accurate": sum(1 for v in js if v["lib"] == lib and v["accurate"]),
                                        "breaking": sum(1 for v in js if v["lib"] == lib and v["accurate"] and v["breaking"])}
                                  for lib in LIBS},
                   "inaccurate_examples": [f"{v['path']} ({v['kind']}): {v['why']}" for v in js if not v["accurate"]][:10],
                   "not_breaking_reasons": dict(Counter((v["kind"]) for v in js if v["accurate"] and not v["breaking"]))}
    res["precision"] = prec
    res["items"] = rows
    res["task_items"] = trows
    (STUDY / "analysis" / "recall_eval.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    # console summary
    for t in DET:
        print(t, rec[t]["overall"], "static", rec[t]["static_visible_types (excl. behaviour_only)"]["p_ci"],
              {ty: (v["k"], v["n"]) for ty, v in rec[t]["by_type"].items()})
    for t in NOTES:
        print(t, nrec[t]["overall"])
    print(json.dumps(cap, indent=0)[:1500])
    print(pairs)
    print(json.dumps(tsum))
    for t, v in prec.items():
        if v:
            print("prec", t, v["lenient_accurate"], v["strict_accurate_and_breaking"])


if __name__ == "__main__":
    main()
