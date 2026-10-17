"""``since-cutoff explain API`` and the MCP tool ``explain_api`` (issue #28): everything
since-cutoff knows about one API, from the scan ``sync`` runs, with no model call and nothing
written.

For the API as a note names it (``Client.send``, ``huggingface_hub.hf_hub_download``), or the
end of that name (``send``), or ``package.API``: the note as the block writes it (and the
bullet it shares with other APIs, when it does), which files' blocks have it, the package with
the release at the cutoff, the pinned one and where that version comes from, each change with
both signatures, the evidence behind the tag (the library's own deprecation text with the file
it is in, a replacement and its source, what a move kept, a switched dependency's
Requires-Dist), the "Runtime:" line, the changelog, every place the project's code uses it with
the form (file:line once the scan records lines, issue #8), and what the tag does not check.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from packaging.utils import canonicalize_name

from since_cutoff.apidiff import DEPENDENCY_SWITCHED, MOVED, APIChange
from since_cutoff.engine import (
    CHANGED,
    NEW,
    SKIPPED,
    Engine,
    ModelTarget,
    PackageScan,
    ScanResult,
    UsedAPI,
)
from since_cutoff.errors import PackageIndexError, SinceCutoffError
from since_cutoff.notes import (
    NEW_PACKAGE,
    SCOPE_IMPORTED,
    SCOPE_USED,
    Note,
    ParsedBlock,
    api_id,
    dependency_detail,
    diff_notes,
    rename_text,
    runtime_check,
    similar_text,
    tag_legend,
    tag_text,
)
from since_cutoff.project import Project
from since_cutoff.pypi import changelog_url
from since_cutoff.report import place_form, places, use_text
from since_cutoff.selection import FORM_LABELS, type_project

# More matches than this: their names are listed, to pick one.
MATCHES_SHOWN = 3
CLOSE_MATCHES = 6


@dataclass
class Found:
    """One API since-cutoff has a note for, with what the scan knows of it."""

    note: Note  # the note from the diff for this API alone (Note.covered: its changes)
    package: PackageScan
    used: UsedAPI | None  # where the project's code uses it; None when it does not

    @property
    def api(self) -> str:
        return self.note.api

    def names(self) -> set[str]:
        """Every name the API goes by: the note's, each public path of each change (re-exports
        too), and each of them after the package's import names."""
        c = self.note.change
        names = {self.note.api, *self.note.apis}
        for change in self.note.covered:
            names.update(p for p in (change.path, *(change.import_paths or ())) if p)
            if change.kind == DEPENDENCY_SWITCHED:
                names.update(n for n in (change.name, change.switched_to) if n)
        roots = {c.package, c.package.replace("-", "_"), *self.package.import_names}
        names.update(f"{r}.{self.note.api}" for r in roots)
        return names


@dataclass
class Lookup:
    """What a name finds: the APIs it names, else names close to it."""

    query: str
    found: list[Found] = field(default_factory=list)
    close: list[str] = field(default_factory=list)


def candidates(scan: ScanResult, package: str | None = None) -> list[Found]:
    """Every API of the scan's changed packages with a note: those the code uses first (with
    their places), then the others (each from the diff alone), then a package first released
    after the cutoff that the code imports (its ``[metadata]`` note). ``package`` keeps one."""
    wanted = canonicalize_name(package) if package else None
    out: list[Found] = []
    seen: set[str] = set()
    for u in scan.used_apis():
        if wanted is None or u.package.name == wanted:
            out.append(Found(u.note, u.package, u))
            seen.update(c.api_key for c in u.note.covered)
    for p in scan.packages:
        if p.status != CHANGED or (wanted is not None and p.name != wanted):
            continue
        rest = [c for c in p.distinct if c.api_key not in seen]
        out += [Found(n, p, None) for n in diff_notes(rest, changelog=p.changelog)]
    by_name = {p.name: p for p in scan.packages}
    for n in scan.new_package_notes():
        if wanted is None or n.change.package == wanted:
            out.append(Found(n, by_name[n.change.package], None))
    return out


def lookup(scan: ScanResult, query: str, package: str | None = None) -> Lookup:
    """The APIs ``query`` names: exactly (one of :meth:`Found.names`), else by the end of a
    name (``send`` for ``Client.send``), else either without regard to case. Call syntax is
    ignored (``Client.send()``). None found: the names closest to it."""
    q = query.strip().removesuffix("()").strip("`").strip()
    result = Lookup(query.strip())
    if not q:
        return result
    found = candidates(scan, package)
    tests: tuple[Callable[[str], bool], ...] = (
        lambda n: n == q,
        lambda n: n.endswith("." + q),
        lambda n: n.lower() == q.lower(),
        lambda n: n.lower().endswith("." + q.lower()),
    )
    for test in tests:
        hits = [f for f in found if any(test(n) for n in f.names())]
        if hits:
            result.found = hits
            return result
    apis = sorted({f.api for f in found})
    close = difflib.get_close_matches(q, apis, n=CLOSE_MATCHES, cutoff=0.5)
    inside = [a for a in apis if q.lower() in a.lower() and a not in close]
    tail = [a for a in apis if a.rsplit(".", 1)[-1].lower() == q.rsplit(".", 1)[-1].lower()]
    result.close = list(dict.fromkeys([*close, *inside, *tail]))[:CLOSE_MATCHES]
    return result


GIVEN = "as given"  # PackageScan.version_source of a version_scan


def version_scan(
    engine: Engine,
    project: Project,
    target: ModelTarget,
    package: str,
    from_version: str | None = None,
    to_version: str | None = None,
) -> ScanResult:
    """A scan of one package between two releases (``explain --package P --from A --to B``):
    ``from_version`` else the latest release by the target's comparison day, ``to_version``
    else the version the project pins, else the latest on PyPI. The project's code is still
    read for where it uses the changed APIs. SinceCutoffError when there is nothing to compare,
    PackageIndexError when it cannot be diffed."""
    name = canonicalize_name(package)
    pypi = engine.pypi
    dep = next((d for d in project.dependencies if d.key == name), None)
    to = (to_version or "").strip() or (dep.version if dep is not None else None)
    new = pypi.release(name, to) if to else pypi.latest(name)
    if from_version and from_version.strip():
        old = pypi.release(name, from_version.strip())
    else:
        found = pypi.version_at(name, target.compare_date)
        if found is None:
            raise SinceCutoffError(
                f"{name} had no release {target.compare_when} ({target.compare_date}): give "
                "the release to compare from with --from"
            )
        old = found
    if new.parsed <= old.parsed:
        raise SinceCutoffError(
            f"{name} {new.version} is not newer than {old.version}: there is no change to explain"
        )
    where = (
        f"{GIVEN} (--to)"
        if to_version
        else (dep.pinned_in or dep.source)
        if dep is not None and dep.version
        else "latest on PyPI"
    )
    scan = PackageScan(
        name,
        new.version,
        where,
        dep.direct if dep is not None else False,
        status=CHANGED,
        cutoff_version=old.version,
        cutoff_version_date=old.uploaded.date().isoformat(),
        locked_date=new.uploaded.date().isoformat(),
        changelog=changelog_url(pypi.project_urls(name)),
    )
    engine.diff_package(scan)
    if scan.status == SKIPPED:
        raise PackageIndexError(scan.reason or f"could not diff {name}")
    scan.imported = project.imports(scan.import_names) if scan.import_names else None
    typed = type_project(project, [scan], pypi, engine.store)
    return ScanResult(typed, target, [scan], name_matches=engine.settings.include_name_matches)


# ------------------------------------------------------------------ the text
def merged_bullet(scan: ScanResult, f: Found) -> Note | None:
    """The note a block writes for this API when it shares one bullet with other APIs
    (notes.diff_notes with ``merge``; a block of ``--scope imported`` for an API the code does
    not use), else None."""
    keys = {c.api_key for c in f.note.covered}
    notes = scan.scope_notes(SCOPE_USED if f.used is not None else SCOPE_IMPORTED)
    for n in notes:
        if keys & {c.api_key for c in n.covered} and len(n.apis) > 1:
            return n
    return None


def in_blocks(f: Found, blocks: Mapping[str, ParsedBlock]) -> dict[str, str]:
    """The files whose block has a bullet for this API, with how: ``"from the diff"`` (this
    note or the bullet it shares), or ``"[type-checked]"`` (written by ``run --apply``, kept by
    ``sync``: the meta line's ``checked`` names its API)."""
    out: dict[str, str] = {}
    ids = {api_id(c) for c in f.note.covered}
    for name, block in blocks.items():
        section = block.packages.get(f.note.change.package)
        if section is None:
            continue
        checked = block.meta.get("checked")
        if isinstance(checked, list) and ids & {str(i) for i in checked}:
            out[name] = "[type-checked]"
            continue
        texts = [text for text, _ in section.bullets]
        names = [f"`{a}`" for a in f.note.apis] + [f"`{a}(" for a in f.note.apis]
        if any(f.note.bullet == t or any(n in t for n in names) for t in texts):
            out[name] = "from the diff"
    return out


def _versions(scan: ScanResult, p: PackageScan) -> str:
    where = p.version_source if p.version_source.startswith(GIVEN) else scan.versions_from(p)
    if p.status == NEW:
        first = f", first released {p.first_released}" if p.first_released else ""
        return (
            f"{p.name} {p.locked} (from {where}){first}: no release by the cutoff to compare with"
        )
    pinned = f"{p.locked} ({p.locked_date})" if p.locked_date else f"{p.locked}"
    old = (
        f"{p.cutoff_version} ({p.cutoff_version_date})"
        if p.cutoff_version_date
        else str(p.cutoff_version)
    )
    return (
        f"{p.name} {pinned}, from {where}; compared from {old}, the latest release "
        f"{scan.target.compare_when}"
    )


def _change_lines(c: APIChange) -> list[str]:
    out = [f"- {c.kind}: {c.describe(versioned=False)}"]
    if c.kind == NEW_PACKAGE:
        return out
    if c.old_signature:
        out.append(f"  {c.from_version}: {c.old_signature}")
    if c.new_signature:
        out.append(f"  {c.to_version}: {c.new_signature}")
    if c.hint:
        where = f" ({c.hint_file})" if c.hint_file else ""
        how = f", {c.hint_source}" if c.hint_source else ""
        out.append(f'  {c.package} {c.from_version} said{where}{how}: "{_one(c.hint)}"')
    if c.deprecation:
        where = f" ({c.deprecation_file})" if c.deprecation_file else ""
        out.append(f'  {c.package} {c.to_version} says{where}: "{_one(c.deprecation)}"')
    if c.still_handled_text:
        out.append(
            f'  {c.to_version}\'s code that still reads it says: "{_one(c.still_handled_text)}"'
        )
    if c.kind == MOVED and c.move_evidence:
        out.append(f"  move evidence: {_evidence(c.move_evidence)}")
    if c.kind == DEPENDENCY_SWITCHED:
        out.append(f"  {dependency_detail(c)}")
    for text in (rename_text(c), similar_text(c)):
        if text:
            out.append(f"  {text}")
    return out


def _signature_heads(c: APIChange) -> tuple[str, ...]:
    return tuple(
        f"  {v}: {s}"
        for v, s in ((c.from_version, c.old_signature), (c.to_version, c.new_signature))
        if s
    )


def _evidence(e: Mapping[str, Any]) -> str:
    return ", ".join(f"{k} {v}" for k, v in e.items())


def _one(text: str, limit: int = 400) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _not_checked(note: Note) -> list[str]:
    """What the note's tag does not say was checked (Note.checks)."""
    checks = note.checks()
    out = []
    if checks["example_type_checks"] is None:
        out.append(
            "no example was type-checked against the pinned version (`since-cutoff run` does "
            "that, with a model)"
        )
    out.append("nothing of the library was run: its behaviour behind an unchanged signature")
    out.append("whether a model gets this API wrong was not measured (`since-cutoff run`)")
    return out


def explain_lines(
    scan: ScanResult, f: Found, blocks: Mapping[str, ParsedBlock] | None = None
) -> list[str]:
    """What ``explain`` prints for one API (plain text that reads as Markdown)."""
    note, p = f.note, f.package
    out = [f"## {f.api} ({p.name})", "", "Note:", f"- {note.line}"]
    merged = merged_bullet(scan, f)
    if merged is not None and merged.line != note.line:
        out += ["The block writes it in a bullet shared with other APIs:", f"- {merged.line}"]
    where = in_blocks(f, blocks or {})
    if where:
        out.append("Written in: " + "; ".join(f"{n} ({how})" for n, how in where.items()) + ".")
        if "[type-checked]" in where.values():
            out.append(
                "A [type-checked] bullet was written by `since-cutoff run --apply`: its example "
                "and the type checker's verdict are in .since-cutoff/results.json."
            )
    elif blocks:
        out.append("Not in a notes block yet: `since-cutoff sync` writes it if the code uses it.")
    out += ["", f"Package: {_versions(scan, p)}."]
    if p.changelog:
        out.append(f"Changelog: {p.changelog}")
    out += ["", "Changes:"]
    shown: set[tuple[str | None, str | None]] = set()
    for c in note.covered:
        lines = _change_lines(c)
        signatures = (c.old_signature, c.new_signature)
        if signatures in shown:  # the same API's signatures, said for its first change
            lines = [line for line in lines if not line.startswith(_signature_heads(c))]
        shown.add(signatures)
        out += lines
    out += ["", f"Evidence {tag_text(note.tag_list)}:"]
    out += [f"- {line}" for line in tag_legend(note.tag_list)]
    checks = note.checks()
    out.append(f"- checked: {checks['change']}")
    for r in note.replacements:
        replaces = f" for `{r.replaces}`" if r.replaces else ""
        out.append(f"- replacement `{r.text}`{replaces} ({r.evidence}): {r.source}")
    if note.not_confirmed:
        names = ", ".join(f"`{n}`" for n in note.not_confirmed)
        out.append(f"- similar names, not confirmed as replacements: {names}")
    out.append(f"- runtime: {runtime_check(note.covered)}")
    out += ["", "Where your code uses it:"]
    if f.used is None:
        imported = "it imports the package" if p.imported else "nor does it import the package"
        out.append(f"- nowhere: your code does not use this API ({imported})")
    else:
        for at, uses in places(f.used):
            out.append(f"- {at}: {FORM_LABELS[place_form(uses)]}, {use_text(uses)}")
    out += ["", "Not checked:"]
    out += [f"- {line}" for line in _not_checked(note)]
    return out


def lookup_lines(scan: ScanResult, result: Lookup, blocks: Mapping[str, ParsedBlock]) -> list[str]:
    """What ``explain`` prints for a lookup: each API it names (at most MATCHES_SHOWN; more
    are listed by name), or why nothing matched, with the closest names."""
    head = [
        f"# {result.query}",
        "",
        f"For {_basis(scan)}; versions from {scan.project.version_source}.",
        "",
    ]
    if not result.found:
        return [*head, no_match_text(scan, result)]
    if len(result.found) > MATCHES_SHOWN:
        names = ", ".join(f"{f.api} ({f.package.name})" for f in result.found)
        return [
            *head,
            f"{len(result.found)} APIs match '{result.query}': {names}. Give one of them.",
        ]
    out = head
    for i, f in enumerate(result.found):
        if i:
            out.append("")
        out += explain_lines(scan, f, blocks)
    return out


def no_match_text(scan: ScanResult, result: Lookup) -> str:
    """Why nothing matched, and what is close."""
    changed = [p.name for p in scan.packages if p.status in (CHANGED, NEW)]
    if not changed:
        return f"No API named '{result.query}': no dependency changed its API after {_basis(scan)}."
    close = f" Close matches: {', '.join(result.close)}." if result.close else ""
    return (
        f"No API named '{result.query}' changed in {', '.join(sorted(changed))} after "
        f"{_basis(scan)}.{close}"
    )


def _basis(scan: ScanResult) -> str:
    t = scan.target
    who = f"{t.model_id}'s training cutoff" if t.model_id else "the cutoff"
    return f"{who} ({t.cutoff.isoformat()})"


# ------------------------------------------------------------------ the JSON
def explain_json(
    scan: ScanResult, result: Lookup, blocks: Mapping[str, ParsedBlock] | None = None
) -> dict[str, Any]:
    """``explain --json``: the same as the text, for each API the name finds."""
    t = scan.target
    return {
        "query": result.query,
        "model": t.model_id or None,
        "cutoff": t.cutoff.isoformat(),
        "cutoff_margin": t.margin,
        "versions_from": scan.project.version_source,
        "found": [_found_json(scan, f, blocks or {}) for f in result.found],
        "close_matches": list(result.close),
    }


def _found_json(scan: ScanResult, f: Found, blocks: Mapping[str, ParsedBlock]) -> dict[str, Any]:
    p, note = f.package, f.note
    merged = merged_bullet(scan, f)
    return {
        "api": f.api,
        "package": p.name,
        "version": p.locked,
        "cutoff_version": p.cutoff_version,
        "versions_from": scan.versions_from(p),
        "status": p.status,
        "changelog": p.changelog,
        "note": note.to_dict() | {"line": note.line, "tag_legend": tag_legend(note.tag_list)},
        "block_bullet": merged.line if merged is not None and merged.line != note.line else None,
        "in_blocks": in_blocks(f, blocks),
        "changes": [_change_json(c) for c in note.covered],
        "runtime": runtime_check(note.covered),
        "uses": _uses_json(f.used),
        "not_checked": _not_checked(note),
    }


def _change_json(c: APIChange) -> dict[str, Any]:
    keys = (
        "id",
        "kind",
        "path",
        "parameter",
        "old_signature",
        "new_signature",
        "moved_to",
        "hint",
        "hint_source",
        "hint_file",
        "deprecation",
        "deprecation_file",
        "still_handled_at",
        "still_handled_text",
        "move_evidence",
        "library_names",
        "suggestions",
        "import_paths",
        "tier",
    )
    d = {k: getattr(c, k) for k in keys}
    d["description"] = c.describe(versioned=False)
    d["from_version"], d["to_version"] = c.from_version, c.to_version
    if c.kind == DEPENDENCY_SWITCHED:
        d["dependency"] = c.dependency
        d["dependency_detail"] = dependency_detail(c)
    return d


def _uses_json(used: UsedAPI | None) -> list[dict[str, Any]]:
    if used is None:
        return []
    return [
        {
            "file": u.file,
            "line": u.line,
            "column": u.column,
            "form": u.form,
            "what": use_text([u]),
            "match": u.how,
        }
        for u in used.uses
    ]


def blocks_of(files: Iterable[Any]) -> dict[str, ParsedBlock]:
    """The blocks of the target files (sync.TargetFile) that have one, by name."""
    return {t.name: t.block for t in files if getattr(t, "block", None) is not None}
