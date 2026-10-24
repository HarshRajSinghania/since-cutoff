"""Evidence pre-check for the precision sample; the AI judge (Claude Opus 5.5) reviews every item the pre-check does
not settle, and spot-checks settled ones; manual verdicts in precision_manual.json override. AI-judged throughout.

accurate: the stated change exists between the two releases (removal: old object found, new not found and not
re-exported / served by a module __getattr__; parameter: present in the old signature and absent (or changed as
stated) in the new one, with no **kwargs absorbing it; default: the default text differs).
breaking: accurate, on a public path (no `_private` segment), and of a kind that breaks or changes old code
(deprecations and pure additions are not breaking).
"""
import json, re, sys
from pathlib import Path

W = Path(r"recall_eval"); OUTP = W / "out" / "precision"
HERE = Path(__file__).parent
REMOVAL = {"removed", "OBJECT_REMOVED", "RemoveAlias", "RemoveAttribute", "RemoveClass", "RemoveFunction", "RemoveMethod",
           "RemoveModule", "RemoveInstanceAttribute", "RemoveExternalAlias"}
PARAM_GONE = {"param_removed", "PARAMETER_REMOVED", "RemoveOptionalParameter", "RemoveRequiredParameter"}
DEFAULT = {"default_changed", "PARAMETER_CHANGED_DEFAULT", "ChangeParameterDefault"}


def pname(p):
    return re.sub(r"=.*$", "", p).lstrip("*")


def private(path):
    return any(c.startswith("_") and not (c.startswith("__") and c.endswith("__")) for c in path.split("."))


def precheck(s):
    k, path, param = s["kind"], s["path"] or "", s.get("param")
    evs = [e for e in s["evidence"].values() if e]
    if not evs or s["tool"].endswith(("_cap5", "_cap10")):
        return None, "manual"
    e = evs[0]
    old, new = e["old"], e.get("new_mcp_types") if (e.get("new_mcp_types") or {}).get("found") else e["new"]
    if k in REMOVAL:
        if not old.get("found"):
            return None, "old object not found by lookup"
        if new.get("found") or new.get("imported") or new.get("in_all") or new.get("module_getattr"):
            return False if new.get("found") else None, "still present/re-exported/getattr in new"
        return True, "old found, new absent"
    if k in PARAM_GONE and param:
        op = [pname(x) for x in old.get("params") or old.get("init_params") or []]
        np_ = [pname(x) for x in new.get("params") or new.get("init_params") or []]
        if not old.get("found") or not new.get("found"):
            return None, "callable not found by lookup"
        if param in op and param not in np_:
            if any(x.startswith("**") for x in (new.get("params") or [])) and not any(x.startswith("**") for x in (old.get("params") or [])):
                return None, "new has **kwargs"
            return True, "param in old, absent in new"
        if param in np_:
            return False, "param still in new signature"
        return None, "param not in old signature by lookup"
    if k in DEFAULT and param:
        od = {pname(x): x for x in old.get("params") or []}
        nd = {pname(x): x for x in new.get("params") or []}
        if param in od and param in nd:
            return (od[param] != nd[param]), f"{od[param]} -> {nd[param]}"
        return None, "param not found"
    return None, "manual"


def main():
    sample = json.loads((OUTP / "sample.json").read_text(encoding="utf-8"))
    manual_p = HERE / "precision_manual.json"
    manual = json.loads(manual_p.read_text(encoding="utf-8")) if manual_p.exists() else {}
    res, todo = {}, []
    for rid, s in sample.items():
        acc, why = precheck(s)
        m = manual.get(rid)
        if m:
            acc_f, brk, why_f, src = m["accurate"], m["breaking"], m["why"], "manual"
        elif acc is not None:
            acc_f, src, why_f = acc, "precheck", why
            brk = bool(acc) and not private(s["path"] or "") and s["kind"] not in {"deprecated"}
        else:
            todo.append(rid)
            continue
        res[rid] = {"tool": s["tool"], "lib": s["lib"], "kind": s["kind"], "path": s["path"], "accurate": acc_f,
                    "breaking": brk, "why": why_f, "source": src}
    json.dump(res, open(OUTP / "judged.json", "w", encoding="utf-8"), indent=1)
    lines = []
    for rid in todo:
        s = sample[rid]
        lines.append(f"\n## {rid} [{s['kind']}] param={s['param']}\n  {s['text'][:420]}")
        for pp, e in s["evidence"].items():
            if not e:
                continue
            for side in ("old", "new", "new_mcp_types"):
                if side in e:
                    d = e[side]
                    lines.append(f"  {side:4} {pp[-60:]}: found={d.get('found')} {d.get('kind','')} params={str(d.get('params') or d.get('init_params') or '')[:300]} src={d.get('src','')[:80]} missing={d.get('missing','')} imp={d.get('imported','')} ga={d.get('module_getattr','')} all={d.get('in_all','')} dec={str(d.get('decorators',''))[:120]}")
    (OUTP / "todo.txt").write_text("\n".join(lines), encoding="utf-8")
    print("judged", len(res), "todo", len(todo))


if __name__ == "__main__":
    main()
