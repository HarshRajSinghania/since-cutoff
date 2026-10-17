"""Path-scoped rule files (issue #16): the notes in files that a coding agent loads only while
it works on the files they are about, instead of one block in AGENTS.md / CLAUDE.md that every
agent loads on every request.

``sync --target claude-rules`` (``cursor-rules``, ``copilot-instructions``) writes one file per
changed package, ``since-cutoff-<package>`` in the agent's rules folder, whose front matter
names the files that use the package's changed APIs (from the scan's locations; for a block of
``--scope imported``, and for a package first released after the cutoff, the files that import
the package). The file's text after the front matter is a notes block like AGENTS.md's, with
the same markers, meta line and hash, so that ``status``, ``sync --check`` and ``unapply``
handle it; the meta line also records the files (``paths``) and a hash of the front matter
(``front``), so that a hand edit of it shows too. Only files of that name with the markers are
since-cutoff's: a file there without them is the user's, and is never written or removed.

Each format is as its agent documents it (checked 2026-10):

=========================  =================================================================
``claude-rules``           Claude Code: ``.claude/rules/*.md`` with ``paths:`` (a YAML list of
                           globs), loaded when Claude reads or edits a matching file
                           (https://code.claude.com/docs/en/memory#path-specific-rules)
``cursor-rules``           Cursor: ``.cursor/rules/*.mdc`` with ``globs:`` (comma-separated)
                           and ``alwaysApply: false``, "Apply to Specific Files"
                           (https://cursor.com/docs/context/rules)
``copilot-instructions``   GitHub Copilot: ``.github/instructions/*.instructions.md`` with
                           ``applyTo:`` (comma-separated globs), read by Copilot cloud agent
                           and code review (https://docs.github.com/en/copilot/how-tos/
                           configure-custom-instructions/add-repository-instructions)
=========================  =================================================================

Windsurf documents one glob per rule file, and Codex no path scoping at all (it reads the
AGENTS.md files on the way to the folder it starts in), so neither has a format here.
"""

from __future__ import annotations

import re
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
# The meta line's keys for a rule file: the files its front matter names, and its hash.
PATHS_KEY = "paths"
FRONT_KEY = "front"


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
        """The package a file of this format is for (from its name), or None when it is not
        one since-cutoff names."""
        name = path.name
        if not (name.startswith(PREFIX) and name.endswith(self.suffix)):
            return None
        package = name[len(PREFIX) : len(name) - len(self.suffix)]
        return package if re.fullmatch(r"[a-z0-9][a-z0-9._-]*", package) else None

    def files(self, root: Path) -> list[Path]:
        """The files since-cutoff wrote here: named for a package, with since-cutoff markers."""
        folder = root / self.folder
        if not folder.is_dir():
            return []
        found = [
            p
            for p in folder.iterdir()
            if p.is_file() and self.package_of(p) is not None and has_markers(p)
        ]
        return sorted(found, key=lambda p: p.name)

    def front_matter(self, paths: Sequence[str], package: str, version: str) -> str:
        """The front matter for a file about ``package`` ``version`` that applies to ``paths``
        (files relative to the project, with "/"); with no paths, one that applies always."""
        globs = [glob_of(p) for p in paths]
        if self.name == CLAUDE_RULES:
            if not globs:
                return ""  # a rule without `paths` loads in every session
            listed = "".join(f'  - "{g}"\n' for g in globs)
            return f"---\npaths:\n{listed}---\n"
        if self.name == CURSOR_RULES:
            description = (
                f"{package} {version}: library changes after the model's training cutoff "
                "(since-cutoff)"
            )
            scope = (
                f"globs: {', '.join(globs)}\nalwaysApply: false" if globs else "alwaysApply: true"
            )
            return f'---\ndescription: "{_quoted(description)}"\n{scope}\n---\n'
        apply = ",".join(globs) if globs else "**"
        return f'---\napplyTo: "{apply}"\n---\n'


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
            "https://cursor.com/docs/context/rules",
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


# A character a glob reads as syntax (or YAML, or a list's comma), or a space: it stands as
# ``?``, which matches any one character, that one included.
_PLAIN = re.compile(r"[\w./+=~@-]")


def glob_of(path: str) -> str:
    """A glob that matches the file ``path`` (relative, with "/"): the path, with each
    character outside letters, digits and ``._-/+=~@`` as ``?`` (one character, that one
    included), and so the first one unless it is a letter, a digit, ``_`` or ``.``. A file named
    ``a [draft].py`` is matched by ``a??draft?.py``, which may match a file next to it whose
    name differs only there: the rule loads for it too, which costs a few tokens."""
    chars = [c if _PLAIN.fullmatch(c) else "?" for c in path]
    if chars and not (chars[0].isalnum() or chars[0] in "_."):
        chars[0] = "?"
    return "".join(chars)


def _quoted(text: str) -> str:
    """Text for a double-quoted YAML string."""
    return text.replace("\\", "/").replace('"', "'")


def front_hash(front: str) -> str:
    return _hash(front.replace("\r\n", "\n"))


def split_front(text: str) -> tuple[str, str]:
    """A file's front matter (``---`` lines at its very start, line breaks as they are; ""
    when it has none) and the rest of the text."""
    m = re.match(r"---\r?\n(?:.*?\r?\n)??---[ \t]*(?:\r?\n|\Z)", text, re.S)
    if m is None:
        return "", text
    return text[: m.end()], text[m.end() :]


def front_edited(text: str, meta: dict[str, object]) -> bool:
    """Whether a rule file's front matter is not the one since-cutoff wrote (its meta line's
    ``front`` hash)."""
    front, _ = split_front(text)
    return meta.get(FRONT_KEY) != front_hash(front)


def with_rule(text: str | None, front: str, block: str, name: str) -> tuple[str, str]:
    """The text of a rule file with ``front`` as its front matter and ``block`` as its notes
    block, and what that does ("created", "updated"). Text of its own after the block stays."""
    if text is None:
        return front + block, "created"
    nl = "\r\n" if "\r\n" in text else "\n"
    _, rest = split_front(text)
    body, action = with_block(rest, block, name)
    return front.replace("\n", nl) + body, "updated" if action == "updated" else action


def without_rule(text: str, name: str) -> str | None:
    """A rule file's text without its notes block: None when nothing else is left (the file
    goes), else the rest with its front matter; the text unchanged when it has no block."""
    front, rest = split_front(text)
    body = without_block(rest, name)
    if body is None:
        return text
    if not body.strip():
        return None
    return front + body


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


def check_ours(path: Path) -> None:
    """Refuse a file at a rule file's path that since-cutoff did not write (no markers)."""
    if path.exists() and not has_markers(path):
        raise NotesFileError(
            f"{path.name} exists and has no since-cutoff block, so since-cutoff leaves it "
            "alone; rename or remove it, then run again"
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
