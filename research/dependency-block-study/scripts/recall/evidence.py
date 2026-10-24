"""Text/AST evidence for judging a reported change (no import of the analysed packages, no API-diff tool).

lookup(dist_dir, dotted_path) -> dict: which module file holds the path, whether the final object is defined there
(def/class/assignment/annotated field), imported/re-exported there, listed in __all__, or covered by a module
__getattr__; for a callable, its parameter list with defaults.
"""
import ast, os, re, sys
from pathlib import Path

W = Path(r"recall_eval\wheels")


def _exists(p):
    # case-sensitive existence check (Windows file systems are case-insensitive)
    try:
        return p.name in os.listdir(p.parent) and _exists_dir(p.parent)
    except OSError:
        return False


def _exists_dir(d):
    if d == W or W not in d.parents:
        return True
    return d.name in os.listdir(d.parent) and _exists_dir(d.parent)


def _module_file(root, comps):
    for k in range(len(comps), 0, -1):
        base = root.joinpath(*comps[:k])
        for f in (base.parent / (base.name + ".py"), base / "__init__.py", base.parent / (base.name + ".pyi"), base / "__init__.pyi"):
            if _exists(f):
                return f, comps[k:]
    return None, comps


def _params(fn):
    a = fn.args
    out = []
    pos = a.posonlyargs + a.args
    defs = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    for p, d in zip(pos, defs):
        out.append(p.arg + ("=" + ast.unparse(d)[:40] if d is not None else ""))
    if a.vararg:
        out.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        out.append("*")
    for p, d in zip(a.kwonlyargs, a.kw_defaults):
        out.append(p.arg + ("=" + ast.unparse(d)[:40] if d is not None else ""))
    if a.kwarg:
        out.append("**" + a.kwarg.arg)
    return out


def _find(body, name):
    hits = []
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name:
            hits.append(n)
        elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            hits.append(n)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
            hits.append(n)
        elif isinstance(n, (ast.If, ast.Try)):
            hits += _find(n.body + getattr(n, "orelse", []) + [x for h in getattr(n, "handlers", []) for x in h.body], name)
    return hits


def lookup(dist, path, depth=0):
    root = W / dist
    comps = re.sub(r"\(.*$", "", path).split(".")
    f, rest = _module_file(root, comps)
    if f is None:
        return {"module_file": None, "found": False}
    src = f.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    res = {"module_file": str(f.relative_to(W)), "rest": rest}
    if not rest:
        res.update(found=True, kind="module"); return res
    body, node = tree.body, None
    for i, name in enumerate(rest):
        hits = _find(body, name)
        if not hits:
            # imported / re-exported?
            imp = [ast.unparse(n)[:150] for n in ast.walk(tree) if isinstance(n, (ast.ImportFrom, ast.Import))
                   and any((a.asname or a.name).split(".")[-1] == name for a in n.names)] if i == 0 else []
            ga = any(isinstance(n, ast.FunctionDef) and n.name == "__getattr__" for n in tree.body) if i == 0 else False
            in_all = bool(re.search(r"__all__[^\]]*['\"]" + re.escape(name) + r"['\"]", src, re.S)) if i == 0 else False
            res.update(found=False, missing=name, imported=imp[:2], module_getattr=ga, in_all=in_all)
            if i == 0 and depth < 3:
                for n in ast.walk(tree):
                    if isinstance(n, ast.ImportFrom) and any((a.asname or a.name) == name for a in n.names):
                        a = [a for a in n.names if (a.asname or a.name) == name][0]
                        modparts = str(f.relative_to(root).with_suffix("")).replace(os.sep, ".").split(".")
                        if modparts[-1] == "__init__":
                            modparts = modparts[:-1]
                        if n.level:
                            base = modparts[: len(modparts) - n.level + 1] if f.name.startswith("__init__") else modparts[: len(modparts) - n.level]
                            target = ".".join(base + ([n.module] if n.module else []))
                        else:
                            target = n.module or ""
                        sub = lookup(dist, target + "." + a.name + ("." + ".".join(rest[1:]) if rest[1:] else ""), depth + 1)
                        sub["via_reexport_from"] = res["module_file"]
                        return sub
            if node is not None and isinstance(node, ast.ClassDef):
                res["class_bases"] = [ast.unparse(b) for b in node.bases]
            return res
        node = hits[0]
        body = getattr(node, "body", [])
    res.update(found=True, kind=type(node).__name__, line=node.lineno)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        res["params"] = _params(node)
        res["decorators"] = [ast.unparse(d)[:60] for d in node.decorator_list]
    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
        res["src"] = ast.unparse(node)[:160]
    elif isinstance(node, ast.ClassDef):
        res["bases"] = [ast.unparse(b)[:60] for b in node.bases]
        init = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"]
        if init:
            res["init_params"] = _params(init[0])
    return res


if __name__ == "__main__":
    import json
    print(json.dumps(lookup(sys.argv[1], sys.argv[2]), indent=0))
