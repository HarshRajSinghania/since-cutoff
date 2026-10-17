"""Path-scoped rule files (issue #16): the notes in files that a coding agent loads only while
it works on the files they are about, instead of one block in AGENTS.md / CLAUDE.md that every
agent loads on every request.

``sync --target claude-rules`` (``cursor-rules``, ``copilot-instructions``) writes one file per
changed package, ``since-cutoff-<package>`` in the agent's rules folder, whose front matter
names the files it applies to (:func:`globs_for`): a file at the project's root that uses the
package's changed APIs as itself, and for the others the Python files of their folder and its
subfolders (``app/api/**/*.py``), so that a file added there later loads the notes too and the
list stays short however many files use the package (from the scan's locations; for a block of
``--scope imported``, and for a package first released after the cutoff, the files that import
the package; files git ignores are left out, :func:`ignored`). The file's text after the front
matter is a notes block like AGENTS.md's, with the same markers, meta line and hash, so that
``status``, ``sync --check`` and ``unapply`` handle it; the meta line also records a hash of
the front matter (``front``), so that a hand edit of it shows too. Only files of that name with
the markers, inside the project, are since-cutoff's: a file there without them is the user's,
and is never written or removed, nor is one reached through a link to a folder or file outside
the project (a rules folder shared between projects).

Each format is as its agent documents it (checked 2026-10):

=========================  =================================================================
``claude-rules``           Claude Code: ``.claude/rules/*.md`` with ``paths:`` (a YAML list of
                           globs), loaded when Claude reads or edits a matching file
                           (https://code.claude.com/docs/en/memory#path-specific-rules); VS
                           Code's Copilot Chat reads it too
``cursor-rules``           Cursor: ``.cursor/rules/*.mdc`` with ``globs:`` (comma-separated)
                           and ``alwaysApply: false``, "Auto-attached when a matching file is
                           in context" (https://cursor.com/docs/rules)
``copilot-instructions``   GitHub Copilot: ``.github/instructions/*.instructions.md`` with
                           ``applyTo:`` (comma-separated globs), read at the repository's root
                           by Copilot Chat in VS Code, Visual Studio, JetBrains, Eclipse and
                           Xcode, Copilot CLI, cloud agent and code review
                           (https://docs.github.com/en/copilot/reference/
                           custom-instructions-support)
=========================  =================================================================

VS Code matches a glob that does not start with ``**/`` as ``**/<glob>``, against the whole
path: there, ``main.py`` also loads the rule for ``other/main.py``.

Windsurf (now Devin Desktop: ``.devin/rules``, ``.windsurf/rules``) documents a rule with one
glob and not how to give several, and Codex no path scoping at all (it reads the AGENTS.md
files on the way to the folder it starts in), so neither has a format here.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from since_cutoff.notes import (
    NotesFileError,
    _hash,
    _read,
    _write,
    has_markers,
    with_block,
    without_block,
)

PREFIX = "since-cutoff-"
# The meta line's key for a rule file's hash of its front matter.
FRONT_KEY = "front"
BOM = "﻿"  # the byte order mark some editors put first in a file
# A package's name as since-cutoff writes it (packaging's canonicalize_name).
_PACKAGE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# More globs than this, and a rule's folders are named by their top-level folder (globs_for).
MAX_GLOBS = 20


@dataclass(frozen=True)
class RuleFormat:
    """One agent's path-scoped rule files."""

    name: str  # as --target takes it
    folder: str  # relative to the project, with "/"
    suffix: str  # what each file's name ends with
    agent: str
    docs: str

    def path(self, root: Path, package: str) -> Path:
        """``.claude/rules/since-cutoff-toylib.md``."""
        return root / self.folder / f"{PREFIX}{package}{self.suffix}"

    def package_of(self, path: Path) -> str | None:
        """The package a file of this format is for (from its name, whatever its case), or
        None when it is not one since-cutoff names: ``since-cutoff-toylib.instructions.md``
        in .claude/rules is no package's ``.md``."""
        name = path.name.lower()
        if not (name.startswith(PREFIX) and name.endswith(self.suffix)):
            return None
        package = name[len(PREFIX) : len(name) - len(self.suffix)]
        return package if _PACKAGE.fullmatch(package) else None

    def files(self, root: Path) -> list[Path]:
        """The files since-cutoff wrote here: named for a package, with since-cutoff markers,
        and inside the project (:func:`outside`: not through a link to a shared folder)."""
        folder = root / self.folder
        if not folder.is_dir() or outside(root, folder):
            return []
        found = [
            p
            for p in folder.iterdir()
            if p.is_file()
            and self.package_of(p) is not None
            and not outside(root, p)
            and has_markers(p)
        ]
        return sorted(found, key=lambda p: p.name)

    def front_matter(self, paths: Sequence[str], package: str, version: str) -> str:
        """The front matter for a file about ``package`` ``version`` that applies to ``paths``
        (files relative to the project, with "/"; :func:`globs_for` makes the globs); with no
        paths, one that applies always."""
        globs = globs_for(paths)
        if self.name == CLAUDE_RULES:
            if not globs:
                return ""  # a rule without `paths` loads in every session
            listed = "".join(f'  - "{g}"\n' for g in globs)
            return f"---\npaths:\n{listed}---\n"
        if self.name == CURSOR_RULES:
            # Cursor's "auto-attached" rule: globs, and no description (that is for a rule the
            # agent pulls in by itself).
            if not globs:
                return "---\nalwaysApply: true\n---\n"
            return f"---\nglobs: {', '.join(globs)}\nalwaysApply: false\n---\n"
        # VS Code reads the description to load the file on demand; GitHub reads applyTo.
        description = f"{package} {version}: API changes after the model's training cutoff"
        apply = ",".join(globs) if globs else "**"
        return f'---\ndescription: "{_quoted(description)}"\napplyTo: "{apply}"\n---\n'

    def globs_in(self, front: str) -> list[str]:
        """The globs a front matter of this format names ([] for one that applies always)."""
        if self.name == CLAUDE_RULES:
            return re.findall(r'(?m)^  - "(.*)"\r?$', front)
        key = "globs" if self.name == CURSOR_RULES else "applyTo"
        m = re.search(rf'(?m)^{key}: "?(.*?)"?\r?$', front)
        if m is None:
            return []
        globs = [g.strip() for g in m.group(1).split(",") if g.strip()]
        return [] if globs == ["**"] else globs


CLAUDE_RULES = "claude-rules"
CURSOR_RULES = "cursor-rules"
COPILOT_INSTRUCTIONS = "copilot-instructions"
FORMATS: dict[str, RuleFormat] = {
    f.name: f
    for f in (
        RuleFormat(
            CLAUDE_RULES,
            ".claude/rules",
            ".md",
            "Claude Code",
            "https://code.claude.com/docs/en/memory#path-specific-rules",
        ),
        RuleFormat(
            CURSOR_RULES,
            ".cursor/rules",
            ".mdc",
            "Cursor",
            "https://cursor.com/docs/rules",
        ),
        RuleFormat(
            COPILOT_INSTRUCTIONS,
            ".github/instructions",
            ".instructions.md",
            "GitHub Copilot",
            "https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/"
            "add-repository-instructions",
        ),
    )
}


def rule_format(target: str | None) -> RuleFormat | None:
    """The format ``--target`` names (``cursor-rules``), or None for a file."""
    return FORMATS.get((target or "").strip().lower()) if target else None


def format_of(root: Path, path: Path) -> RuleFormat | None:
    """The format of a file since-cutoff writes (by its folder and name), or None."""
    for f in FORMATS.values():
        if path.parent == root / f.folder and f.package_of(path) is not None:
            return f
    return None


def present(root: Path) -> list[RuleFormat]:
    """The formats that have files since-cutoff wrote in the project, in FORMATS' order."""
    return [f for f in FORMATS.values() if f.files(root)]


# ------------------------------------------------------------------ the globs
# A character a glob reads as syntax (or YAML, or a list's comma), or a space: it stands as
# ``?``, which matches any one character, that one included.
_PLAIN = re.compile(r"[\w./+=~@-]")


def glob_of(path: str) -> str:
    """A glob that matches the file or folder ``path`` (relative, with "/"): the path, with
    each character outside letters, digits and ``._-/+=~@`` as ``?`` (one character, that one
    included), and so the first one unless it is a letter, a digit, ``_`` or ``.``. A file
    named ``a [draft].py`` is matched by ``a??draft?.py``, which may match a file next to it
    whose name differs only there: the rule loads for it too, which costs a few tokens. A
    character beyond the Basic Multilingual Plane that is not a letter or a digit (an emoji)
    is ``*``, as the JavaScript glob engines' ``?`` matches half of one only."""
    chars = [
        c if _PLAIN.fullmatch(c) else "*" if ord(c) > 0xFFFF and i else "?"
        for i, c in enumerate(path)
    ]
    if chars and not (chars[0].isalnum() or chars[0] in "_."):
        chars[0] = "?"
    return re.sub(r"\*{2,}", "*", "".join(chars))


def globs_for(files: Iterable[str]) -> list[str]:
    """The globs a rule file names for ``files`` (relative to the project, with "/"), sorted:
    a file at the project's root as itself (``main.py``), and for the others the Python files
    of their folder and its subfolders (``app/api/**/*.py``; a folder inside another one listed
    is left out), so that a file added next to them later loads the notes too, and the list
    stays short however many files use the package. More than :data:`MAX_GLOBS`: each folder
    by its top-level folder (``app/**/*.py``); still more, [] (the rule applies always)."""
    names = sorted(set(files))
    top = [glob_of(f) for f in names if "/" not in f]
    folders = _outermost({f.rsplit("/", 1)[0] for f in names if "/" in f})
    globs = sorted({*top, *(f"{glob_of(d)}/**/*.py" for d in folders)})
    if len(globs) <= MAX_GLOBS:
        return globs
    tops = {d.split("/", 1)[0] for d in folders}
    globs = sorted({*top, *(f"{glob_of(d)}/**/*.py" for d in tops)})
    return globs if len(globs) <= MAX_GLOBS else []


def _outermost(folders: set[str]) -> list[str]:
    """The folders that are not inside another one of them."""
    return sorted(
        d for d in folders if not any(d.startswith(other + "/") for other in folders if other != d)
    )


def _quoted(text: str) -> str:
    """Text for a double-quoted YAML string."""
    return text.replace("\\", "/").replace('"', "'")


# ------------------------------------------------------------- front matter
def front_hash(front: str) -> str:
    return _hash(front.replace("\r\n", "\n"))


def split_front(text: str) -> tuple[str, str]:
    """A file's front matter (``---`` lines at its very start, line breaks as they are; ""
    when it has none) and the rest of the text; a byte order mark before them is in neither
    (:func:`with_rule` and :func:`without_rule` keep it first)."""
    text = text.removeprefix(BOM)
    m = re.match(r"---\r?\n(?:.*?\r?\n)??---[ \t]*(?:\r?\n|\Z)", text, re.S)
    if m is None:
        return "", text
    return text[: m.end()], text[m.end() :]


def front_edited(text: str, meta: dict[str, object]) -> bool:
    """Whether a rule file's front matter is not the one since-cutoff wrote (its meta line's
    ``front`` hash). A block whose meta line has no such hash was not written for a rule file
    (``run --apply`` writes none there): nothing to tell."""
    if FRONT_KEY not in meta:
        return False
    front, _ = split_front(text)
    return meta.get(FRONT_KEY) != front_hash(front)


def with_rule(text: str | None, front: str, block: str, name: str) -> tuple[str, str]:
    """The text of a rule file with ``front`` as its front matter and ``block`` as its notes
    block, and what that does ("created", "updated"). Text of its own after the block stays,
    and so does a byte order mark at its start."""
    if text is None:
        return front + block, "created"
    nl = "\r\n" if "\r\n" in text else "\n"
    bom = BOM if text.startswith(BOM) else ""
    _, rest = split_front(text)
    body, action = with_block(rest, block, name)
    return bom + front.replace("\n", nl) + body, "updated" if action == "updated" else action


def without_rule(text: str, name: str) -> str | None:
    """A rule file's text without its notes block: None when nothing else is left (the file
    goes), else the rest with its front matter; the text unchanged when it has no block."""
    bom = BOM if text.startswith(BOM) else ""
    front, rest = split_front(text)
    body = without_block(rest, name)
    if body is None:
        return text
    if not body.strip():
        return None
    return bom + front + body


# ------------------------------------------------------------------ the files
def outside(root: Path, path: Path) -> str | None:
    """Why since-cutoff does not write or remove ``path`` (a rule file or its folder): it is
    reached through a link to a place outside the project (a rules folder shared between
    projects: each would take the others' files for its own), or it is a hard link (another
    name of a file that may be elsewhere). None when neither."""
    try:
        base, real = root.resolve(), path.resolve()
    except (OSError, RuntimeError) as exc:
        return f"cannot be resolved ({exc})"
    if real != base and base not in real.parents:
        return f"is a link to {real}, outside the project"
    try:
        if path.is_file() and path.stat().st_nlink > 1:
            return "is a hard link, which may be a file of another project"
    except OSError:
        pass
    return None


def check_ours(root: Path, path: Path) -> None:
    """Refuse a file at a rule file's path that since-cutoff may not write: one reached
    through a link outside the project (:func:`outside`), one that is not UTF-8 text, and one
    since-cutoff did not write (no markers)."""
    for p in (path.parent, path):
        why = outside(root, p)
        if why:
            name = p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p)
            raise NotesFileError(
                f"{name} {why}: since-cutoff writes rule files only inside the project, so it "
                "leaves it alone"
            )
    if not path.exists():
        return
    try:
        _read(path)
    except UnicodeDecodeError as exc:
        raise NotesFileError(f"{path.name} is not UTF-8 text: {exc}") from exc
    except OSError as exc:
        raise NotesFileError(f"cannot read {path}: {exc}") from exc
    if not has_markers(path):
        raise NotesFileError(
            f"{path.name} exists and has no since-cutoff block, so since-cutoff leaves it "
            "alone; rename or remove it, then run again"
        )


def remove_rule(path: Path) -> bool:
    """``unapply`` for a rule file: the file goes when it holds nothing but since-cutoff's
    front matter and block, else only the block goes. False when it has no block."""
    try:
        text = _read(path)
    except FileNotFoundError:
        return False
    except (OSError, UnicodeDecodeError) as exc:
        raise NotesFileError(f"cannot read {path}: {exc}") from exc
    new = without_rule(text, path.name)
    if new == text:
        return False
    if new is None:
        delete(path)
    else:
        _write(path, new)
    return True


def write_rule(path: Path, text: str) -> None:
    """Write a rule file, and its folder (NotesFileError when that fails)."""
    _write(path, text)


def delete(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise NotesFileError(f"cannot remove {path}: {exc}") from exc


# ------------------------------------------------------------------- git
def _git(root: Path, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    """``git -C root ...`` (no fsmonitor hook runs); OSError or SubprocessError when git is
    not there or does not answer."""
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        input=stdin,
        capture_output=True,
        timeout=60,
        check=False,
    )


def repo_root(root: Path) -> Path | None:
    """The root of the git work tree the project is in, or None: not in one, git is not
    installed, or the work tree ignores the project's folder (it is not part of that
    repository)."""
    if not any((p / ".git").exists() for p in (root, *root.parents)):
        return None
    try:
        found = _git(root, "rev-parse", "--show-toplevel")
        if found.returncode != 0:
            return None
        top = Path(found.stdout.decode("utf-8", "surrogateescape").strip()).resolve()
        here = root.resolve()
        if top != here and top in here.parents:
            rel = here.relative_to(top).as_posix()
            if _git(top, "check-ignore", "-q", "--", rel).returncode == 0:
                return None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return top


def ignored(root: Path, files: Sequence[str]) -> set[str]:
    """Of ``files`` (relative to the project, with "/"), those git ignores (.gitignore,
    .git/info/exclude, the global excludes; a tracked file is never ignored), so that a
    committed rule file does not name a local file nobody else has, and ``sync --check`` on a
    clean checkout does not fail over it. None outside a git work tree (:func:`repo_root`)."""
    if not files or repo_root(root) is None:
        return set()
    try:
        found = _git(
            root,
            "check-ignore",
            "-z",
            "--stdin",
            stdin="\0".join(files).encode("utf-8", "surrogateescape"),
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if found.returncode not in (0, 1):  # 1: none of them is ignored
        return set()
    return {p for p in found.stdout.decode("utf-8", "surrogateescape").split("\0") if p}


def root_warning(root: Path, rule: RuleFormat) -> str | None:
    """What to say when the project is a folder of a git repository and the format's agent
    reads its folder at the repository's root only (GitHub's ``.github/instructions``)."""
    if rule.name != COPILOT_INSTRUCTIONS:
        return None
    top = repo_root(root)
    if top is None or top == root.resolve():
        return None
    return (
        f"GitHub reads {rule.folder} at the repository's root ({top.as_posix()}) only, so "
        f"Copilot does not read the files written here in {rule.folder}; VS Code reads them "
        "when this folder is the workspace"
    )


def rules_tip(root: Path, formats: Iterable[RuleFormat]) -> str | None:
    """What to say when the notes go to rule files and AGENTS.md or CLAUDE.md still has a
    block: agents load that one on every request, the rule files only where they apply."""
    if not list(formats):
        return None
    left = [n for n in ("AGENTS.md", "CLAUDE.md") if has_markers(root / n)]
    if not left:
        return None
    files = " and ".join(left)
    which = "it" if len(left) == 1 else "them"
    commands = " and ".join(f"`since-cutoff unapply --target {n}`" for n in left)
    return (
        f"{files} still {'has' if len(left) == 1 else 'have'} a notes block, which agents load "
        f"on every request: {commands} {'removes' if len(left) == 1 else 'remove'} {which}"
    )
