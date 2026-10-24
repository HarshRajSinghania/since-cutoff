"""Strict, rule-based proposal of detected yes/no per GT item and tool (protocol section 5), reviewed afterwards by
the AI adjudicator (adjudication.json overrides it). Writes out/auto/<lib>[.tasks].json and a compact review text.

Element match levels: E (a report path's Owner.name tail equals the item's, or the full path is equal), P (the report
is about one of the item's parameters on the same callable/class: same Owner.name tail and report param in params, or
report path == item Owner.name + "." + param), C (the report path is a containing module/class of the item path, at
least two components). Kind consistency per change type follows the protocol. dependency_switch: a report of kind
dependency_switched (the tools that have it), or a notes line saying the package "requires `httpx2`". behaviour_only:
never auto-yes (adjudicated by hand). Notes lines: the line must name the item's object (Owner.name or last name) in
backticks, plus one of the item's params for parameter items; default changes need the word "default".
"""
import json, re, sys
from pathlib import Path

W = Path(r"recall_eval"); NORM = W / "out" / "norm"; AUTO = W / "out" / "auto"
sys.path.insert(0, str(Path(__file__).parent))
from candidates import gt_items, task_items, comps  # noqa: E402

DETECTORS = ["sc041", "scc2m0", "scc2", "griffe", "aexpy"]
NOTES = ["sc041_cap5", "sc041_cap10", "scc2m0_cap5", "scc2m0_cap10", "scc2_cap5", "sc041_frozen", "scc2_frozen"]
REMOVAL_KINDS = {"removed", "moved", "OBJECT_REMOVED", "kind_changed", "OBJECT_CHANGED_KIND",
                 "RemoveFunction", "RemoveClass", "RemoveAttribute", "RemoveAlias", "RemoveModule", "RemoveMethod",
                 "RemoveInstanceAttribute", "RemoveExternalAlias"}
PARAM_KINDS = {"param_removed", "param_required", "param_keyword_only", "param_positional_only",
               "PARAMETER_REMOVED", "PARAMETER_CHANGED_KIND", "PARAMETER_CHANGED_REQUIRED", "PARAMETER_ADDED_REQUIRED",
               "PARAMETER_MOVED", "RemoveParameter", "ChangeParameterOptional", "AddRequiredParameter",
               "ReorderParameter", "ChangeParameterType", "MoveParameter", "AddParameter",
               "RemoveOptionalParameter", "RemoveRequiredParameter", "RemoveVarKeyword", "RemoveVarPositional",
               "RemoveParameterDefault", "AddRequiredParameter"}
SIG_EXTRA = {"RETURN_CHANGED_TYPE", "kind_changed", "OBJECT_CHANGED_KIND", "ChangeReturnType", "ATTRIBUTE_CHANGED_TYPE",
             "ChangeAttributeType"}
TYPE_KINDS = {"ChangeParameterType", "ChangeAttributeType", "ChangeReturnType", "RemoveBaseClass",
              "RETURN_CHANGED_TYPE", "ATTRIBUTE_CHANGED_TYPE", "CLASS_REMOVED_BASE"}
DEFAULT_KINDS = {"default_changed", "PARAMETER_CHANGED_DEFAULT", "ChangeParameterDefault"}  # AexPy: ChangeParameterDefault


def tail(cs, n=2):
    return list(cs[-n:]) if len(cs) >= n else list(cs)


def same_side(a, b):
    """A beta mirror and its GA twin are different APIs (`resources.beta...` vs `resources...`)."""
    return ("beta" in a) == ("beta" in b)


def cls_tail(c):
    """Owner.name when the owner is a class (capitalised), else the last name only."""
    if len(c) >= 2 and c[-2][:1].isupper():
        return c[-2:]
    return c[-1:]


ACCESSORS = {("Series", "cat"): "CatNameSpace", ("Expr", "cat"): "ExprCatNameSpace",
             ("Series", "arr"): "ArrayNameSpace", ("Expr", "arr"): "ExprArrayNameSpace",
             ("Series", "list"): "ListNameSpace", ("Expr", "list"): "ExprListNameSpace",
             ("Series", "str"): "StringNameSpace", ("Expr", "str"): "ExprStringNameSpace",
             ("Series", "dt"): "DateTimeNameSpace", ("Expr", "dt"): "ExprDateTimeNameSpace",
             ("Series", "struct"): "StructNameSpace", ("Expr", "struct"): "ExprStructNameSpace"}


def accessor_form(g):
    """polars `Series.cat.get_categories` -> `CatNameSpace.get_categories` (the namespace class)."""
    for i in range(len(g) - 1):
        if (g[i], g[i + 1]) in ACCESSORS:
            return g[:i] + [ACCESSORS[(g[i], g[i + 1])]] + g[i + 2:]
    return g


def same_tail(rc, g):
    if len(g) >= 2 and len(rc) >= 2 and tail(rc) == tail(g):
        return True
    # module-level function/constant re-exported from a submodule: same package, same name, both owners modules
    # (only for a top-level path `pkg.name`, so that `mcp.client.experimental` does not match `mcp.server.lowlevel.experimental`)
    return (len(g) == 2 and len(rc) >= 2 and rc[0] == g[0] and rc[-1] == g[-1] and rc[-2][:1].islower())


def mod_ok(rc, g):
    """The report's module path must extend the item's module path (re-exports from a parent package), so that an
    incidental import of the same class name in an unrelated module does not count."""
    def mod(c):
        for i, x in enumerate(c):
            if x[:1].isupper():
                return c[:i]
        return c[:-1]
    gm, rm = mod(g), mod(rc)
    return rm[:len(gm)] == gm


def element(item, r):
    paths = [item.get("old_path") or ""] + list(item.get("api_names") or [])
    gcs = [accessor_form(comps(p)) for p in paths if p]
    params = set(item.get("params") or [])
    best = None
    for rp in r["paths"]:
        rc = comps(rp)
        if not rc:
            continue
        for g in gcs:
            if not g or not same_side(rc, g):
                continue
            if r.get("param") and r["param"] in params and len(g) >= 2 and (same_tail(rc, g) or (
                    g[-2][:1].isupper() and cls_tail(rc) == cls_tail(g) and mod_ok(rc, g))):
                return "P"
            if len(rc) >= 3 and rc[-1] in params and (same_tail(rc[:-1], g) or (
                    g[-1][:1].isupper() and rc[-2] == g[-1] and mod_ok(rc[:-1], g))):
                return "P"
            if rc == g or same_tail(rc, g) or (
                    len(g) >= 2 and g[-1][:1].isupper() and rc[-1] == g[-1] and mod_ok(rc, g)) or (
                    len(g) >= 3 and g[-2][:1].isupper() and len(rc) >= 2 and cls_tail(rc) == cls_tail(g) and mod_ok(rc, g)):
                best = "E"
            elif best is None and 2 <= len(rc) < len(g) and g[:len(rc)] == rc:
                best = "C"
    return best


def consistent(ct, level, kind, has_params):
    if ct in ("removal", "rename_move"):
        return (level in ("E", "C") and kind in REMOVAL_KINDS) or (level == "P" and kind in REMOVAL_KINDS | PARAM_KINDS)
    if ct == "signature":
        if level == "P":
            return kind in PARAM_KINDS | SIG_EXTRA | REMOVAL_KINDS
        if level == "E":
            return kind in REMOVAL_KINDS | SIG_EXTRA or (not has_params and kind in PARAM_KINDS)
        if level == "C":
            return kind in REMOVAL_KINDS
    if ct == "default_change":
        return level == "P" and kind in DEFAULT_KINDS
    return False


def note_names(item):
    out = set()
    for p in [item.get("old_path") or ""] + list(item.get("api_names") or []):
        c = comps(p)
        if c:
            out.add(".".join(c[-2:] if len(c) >= 2 else c))  # Owner.name (class or module owner)
            if c[-1][:1].isupper():
                out.add(c[-1])  # a class may be named bare
    return {n for n in out if len(n) >= 3}


def decide(item, lib, rows, is_notes):
    ct = item["change_type"]
    hits = []
    for r in rows:
        if ct == "dependency_switch":
            if r["kind"] == "dependency_switched" or (is_notes and re.search(r"requires `httpx2`", r["text"])):
                hits.append(("D", r))
            elif (not is_notes and r["kind"] in TYPE_KINDS and "httpx2" in r["text"]
                  and re.search(r"(?<![\w])httpx\.", r["text"]) and not re.search(r"(^|\.)_", r["path"])):
                hits.append(("I", r))  # indirect: a public signature/attribute type moved from httpx to httpx2
            continue
        if is_notes:
            t = r["text"]
            ticks = re.findall(r"`([^`]+)`", t)
            named = any(re.search(r"(^|\.)" + re.escape(n) + r"(\(\))?$", tk) for tk in ticks for n in note_names(item))
            member = any(re.search(r"(^|\.)" + re.escape(n) + r"\." + re.escape(p) + r"$", tk) for tk in ticks
                         for n in note_names(item) for p in (item.get("params") or []))
            ok = named or member
            if ok and not member and item.get("params"):
                ok = any(p in ticks or any(tk.startswith(p + "=") for tk in ticks) for p in item["params"])
            if ok and ct == "default_change":
                ok = "default" in t
            if ok and ct == "behaviour_only":
                ok = False
            if ok:
                hits.append(("N", r))
            elif ct in ("removal", "rename_move", "signature") and re.search(r"\b(moved|removed)\b", t):
                # the line names a containing package/module/class as moved or removed (same rule as level C)
                gpaths = [comps(p) for p in [item.get("old_path") or ""] + list(item.get("api_names") or []) if p]
                for tk in ticks:
                    tc = comps(re.sub(r"\(\)$", "", tk))
                    if len(tc) >= 2 and any(len(g) > len(tc) and g[:len(tc)] == tc for g in gpaths):
                        hits.append(("NC", r))
                        break
            continue
        lv = element(item, r)
        if lv and consistent(ct, lv, r["kind"], bool(item.get("params"))):
            hits.append((lv, r))
    order = {"D": 0, "N": 0, "P": 0, "E": 1, "C": 2, "NC": 2, "I": 3}
    hits.sort(key=lambda h: order[h[0]])
    return hits


def run(lib, items, tag):
    out, txt, rows = {}, [], {}
    for t in DETECTORS + NOTES:
        p = NORM / t / f"{lib}.json"
        rows[t] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    for it in items:
        out[it["id"]] = {}
        line = [f"{it['id']} [{it['change_type']}] {it.get('old_path')} {it.get('params') or ''} :: {it['description'][:110]}"]
        for t in DETECTORS + NOTES:
            if rows[t] is None:
                out[it["id"]][t] = None
                continue
            hits = decide(it, lib, rows[t], t in NOTES)
            out[it["id"]][t] = {"auto": bool(hits), "level": hits[0][0] if hits else None,
                                "rids": [h[1]["rid"] for h in hits[:8]], "n_hits": len(hits),
                                "params_hit": sorted({h[1].get("param") for h in hits if h[1].get("param")})}
            if hits:
                h = hits[0][1]
                line.append(f"   {t}: Y{hits[0][0]} x{len(hits)} {h['rid'].split('-')[-1]} {h['kind']} | {h['text'][:110]}")
        if len(line) == 1:
            line[0] += "   [no auto match]"
        txt.append("\n".join(line))
    AUTO.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(AUTO / f"{lib}{tag}.json", "w", encoding="utf-8"), indent=0)
    (AUTO / f"{lib}{tag}.txt").write_text("\n".join(txt), encoding="utf-8")


if __name__ == "__main__":
    for lib in sys.argv[1:]:
        run(lib, gt_items(lib), "")
        run(lib, task_items(lib), ".tasks")
