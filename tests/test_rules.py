"""Path-scoped rule files (issue #16): ``sync --target claude-rules`` (``cursor-rules``,
``copilot-instructions``) writes one file per changed package, whose front matter names the
files that use it, with the same block, markers and hash as AGENTS.md's; ``status``, ``sync
--check`` and ``unapply`` handle them, and a file since-cutoff did not write is left alone.

The toy project and the fake PyPI are test_sync.py's: toylib 2.0 changed after the cutoff
2025-07-31, and main.py and sub/other.py use it. No network, and no model is called."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from since_cutoff import cli
from since_cutoff.notes import BLOCK_START, parse_block
from since_cutoff.rules import (
    FORMATS,
    front_hash,
    glob_of,
    split_front,
    with_rule,
    without_rule,
)
from since_cutoff.sync import EXIT_EDITED, EXIT_OK, EXIT_OUT_OF_DATE
from tests import test_sync
from tests.test_sync import MINE, SONNET, make_app, set_pins, write

# The fixtures of test_sync.py: the fake PyPI, and the CLI without network (``sc``).
pypi = test_sync.pypi
sc = test_sync.sc

CLAUDE = ".claude/rules/since-cutoff-toylib.md"
CURSOR = ".cursor/rules/since-cutoff-toylib.mdc"
COPILOT = ".github/instructions/since-cutoff-toylib.instructions.md"
FILES = {"claude-rules": CLAUDE, "cursor-rules": CURSOR, "copilot-instructions": COPILOT}


def read(root: Path, name: str) -> str:
    return (root / name).read_bytes().decode("utf-8")


def put(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write(path, text)


def errors(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str]:
    """The CLI's exit code and what it printed to stderr, in one line (with ``sc``'s fakes)."""
    code = cli.main([str(a) for a in argv])
    return code, " ".join(capsys.readouterr().err.split())


def rules(sc: Any, root: Path, target: str = "claude-rules", *flags: str) -> str:
    code, out = sc("sync", root, *SONNET, "--yes", "--target", target, *flags)
    assert code == EXIT_OK, out
    return read(root, FILES[target])


# ------------------------------------------------------------------ writing
def test_claude_rules_name_the_files_that_use_the_package(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    code, out = sc("sync", root, *SONNET, "--yes", "--target", "claude-rules")
    assert code == EXIT_OK, out
    assert f"+++ {CLAUDE} (since-cutoff sync)" in out
    assert f"✓ Created {CLAUDE} with 2 notes." in out
    text = read(root, CLAUDE)
    front, rest = split_front(text)
    assert front == '---\npaths:\n  - "main.py"\n  - "sub/other.py"\n---\n'
    assert rest.startswith(BLOCK_START + "\n")
    block = parse_block(text)
    assert block is not None and block.edited is False
    assert set(block.packages) == {"toylib"} and block.packages["toylib"].version == "2.0"
    assert block.meta["paths"] == ["main.py", "sub/other.py"]
    assert block.meta["front"] == front_hash(front)
    # The notes are where the agent loads them only for those files: AGENTS.md is not written.
    assert not (root / "AGENTS.md").exists() and not (root / "CLAUDE.md").exists()


def test_cursor_and_copilot_front_matter_as_their_docs_give_it(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    cursor = rules(sc, root, "cursor-rules")
    assert split_front(cursor)[0] == (
        "---\n"
        "description: \"toylib 2.0: library changes after the model's training cutoff "
        '(since-cutoff)"\n'
        "globs: main.py, sub/other.py\n"
        "alwaysApply: false\n"
        "---\n"
    )
    copilot = rules(sc, root, "copilot-instructions")
    assert split_front(copilot)[0] == '---\napplyTo: "main.py,sub/other.py"\n---\n'
    # The same notes in each: the block after the front matter differs only in its meta line.
    for text in (cursor, copilot):
        block = parse_block(text)
        assert block is not None and len(block.packages["toylib"].bullets) == 2


def test_the_rule_formats_are_the_ones_the_cli_names() -> None:
    """``cli.RULE_TARGETS`` is a copy, so that --help does not import notes."""
    assert tuple(FORMATS) == cli.RULE_TARGETS


def test_imported_scope_rules_apply_to_every_file_that_imports_the_package(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    (root / "plain.py").write_text("import toylib\n", encoding="utf-8")
    text = rules(sc, root, "claude-rules", "--scope", "imported")
    block = parse_block(text)
    assert block is not None and block.meta["scope"] == "imported"
    assert block.meta["paths"] == ["main.py", "plain.py", "sub/other.py"]
    # Used scope: only the files that use a changed API.
    assert parse_block(rules(sc, root, "cursor-rules")).meta["paths"] == [  # type: ignore[union-attr]
        "main.py",
        "sub/other.py",
    ]


def test_globs_match_each_file_and_nothing_breaks_the_front_matter() -> None:
    assert glob_of("app/main.py") == "app/main.py"
    assert glob_of("a [draft]/b,c.py") == "a??draft?/b?c.py"
    assert glob_of('we"ird#{x}*.py') == "we?ird??x??.py"
    assert glob_of("@scope/x.py") == "?scope/x.py"
    assert glob_of("café/ü.py") == "café/ü.py"
    claude = FORMATS["claude-rules"].front_matter(['x "y".py'], "toylib", "2.0")
    assert claude == '---\npaths:\n  - "x??y?.py"\n---\n'
    # No file known: a rule that applies everywhere.
    assert FORMATS["claude-rules"].front_matter([], "toylib", "2.0") == ""
    assert "alwaysApply: true" in FORMATS["cursor-rules"].front_matter([], "toylib", "2.0")
    assert FORMATS["copilot-instructions"].front_matter([], "toylib", "2.0") == (
        '---\napplyTo: "**"\n---\n'
    )


def test_with_and_without_rule_keep_text_of_ones_own() -> None:
    front = '---\napplyTo: "a.py"\n---\n'
    block = f"{BLOCK_START}\nnotes\n<!-- since-cutoff:end -->\n"
    text, action = with_rule(None, front, block, "x.md")
    assert (text, action) == (front + block, "created")
    assert without_rule(text, "x.md") is None  # nothing of the user's: the file goes
    mine = text + "\nMy own line.\n"
    new, action = with_rule(mine, '---\napplyTo: "b.py"\n---\n', block, "x.md")
    assert action == "updated" and new.endswith("My own line.\n") and 'applyTo: "b.py"' in new
    assert without_rule(mine, "x.md") == front + "My own line.\n"
    crlf = text.replace("\n", "\r\n")
    assert with_rule(crlf, front, block, "x.md")[0] == crlf


# ---------------------------------------------------------- keeping in step
def test_a_second_sync_leaves_the_rule_files_alone_and_writes_no_agents_md(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    before = rules(sc, root)
    stamp = (root / CLAUDE).stat().st_mtime_ns
    code, out = sc("sync", root)  # no --target: the rule files are where the notes are
    assert code == EXIT_OK, out
    assert f"{CLAUDE} is up to date: 2 notes for claude-sonnet-4-5 (cutoff 2025-07-31)" in out
    assert f"(from the notes in {CLAUDE}; --model to change)" in out
    assert read(root, CLAUDE) == before and (root / CLAUDE).stat().st_mtime_ns == stamp
    assert not (root / "AGENTS.md").exists()
    assert sc("sync", root, "--check")[0] == EXIT_OK
    assert sc("status", root)[0] == EXIT_OK


def test_a_file_that_starts_using_the_package_is_added_to_the_globs(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    rules(sc, root, "cursor-rules")
    (root / "sub" / "more.py").write_text("from toylib import fetch\nfetch('u')\n", "utf-8")
    code, out = sc("sync", root, "--check")
    assert code == EXIT_OUT_OF_DATE, out
    assert f"{CURSOR} is out of date: the files it is loaded for would change (1 added)." in out
    code, out = sc("sync", root, "--yes")
    assert code == EXIT_OK and f"✓ Updated {CURSOR}: now loaded for 3 files (1 added)." in out
    assert "globs: main.py, sub/more.py, sub/other.py\n" in read(root, CURSOR)
    assert sc("sync", root, "--check")[0] == EXIT_OK


def test_status_and_check_see_a_bumped_package_in_a_rule_file(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    rules(sc, root, "copilot-instructions")
    set_pins(root, ("toylib==2.1", "otherlib==1.0"))
    code, out = sc("status", root)
    assert code == EXIT_OUT_OF_DATE, out
    assert f"{COPILOT}: notes for claude-sonnet-4-5 (cutoff 2025-07-31)" in out
    code, out = sc("status", root, "--json")
    [target] = json.loads(out)["targets"]
    assert target["file"] == COPILOT and target["state"] == "out_of_date"
    assert sc("sync", root, "--check")[0] == EXIT_OUT_OF_DATE
    code, out = sc("sync", root, "--yes")
    assert code == EXIT_OK and f"✓ Updated {COPILOT}: toylib checked again for 2.1" in out
    assert "toylib 2.1: library" not in read(root, COPILOT)  # Copilot's has no description
    assert parse_block(read(root, COPILOT)).packages["toylib"].version == "2.1"  # type: ignore[union-attr]


@pytest.mark.parametrize("target", list(FILES))
def test_a_hand_edit_of_the_front_matter_or_the_notes_shows(sc, tmp_path, target) -> None:
    root = make_app(tmp_path)
    name = FILES[target]
    text = rules(sc, root, target)
    for edited in (
        text.replace("main.py", "everything.py", 1),
        text.replace("do not pass it.", "do not pass it, ever."),
    ):
        write(root / name, edited)
        code, out = sc("sync", root, "--check")
        assert code == EXIT_EDITED, out
        assert f"The since-cutoff block in {name} was edited by hand" in out
        code, out = sc("status", root)
        assert "edited by hand since since-cutoff wrote it" in out
        assert read(root, name) == edited
    code, out = sc("sync", root, "--yes", "--force")
    assert code == EXIT_OK and "replaced the text edited by hand" in out
    assert read(root, name) == text


def test_a_package_with_no_notes_left_loses_its_file(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    rules(sc, root)
    set_pins(root, ("toylib==1.0", "otherlib==1.0"))
    code, out = sc("sync", root, "--check")
    assert code == EXIT_OUT_OF_DATE
    assert f"{CLAUDE} is out of date: toylib 1.0 in pyproject.toml is the latest release" in out
    code, out = sc("sync", root, "--yes")
    assert code == EXIT_OK, out
    assert (
        f"✓ Removed {CLAUDE}: toylib dropped (1.0 is the latest release 30 days before the "
        "cutoff)." in out
    )
    assert not (root / CLAUDE).exists()
    code, out = sc("sync", root, "--target", "claude-rules")
    assert code == EXIT_OK
    assert ".claude/rules: no notes to write; your code uses none of the APIs" in out


def test_text_of_ones_own_in_a_rule_file_stays_when_its_notes_go(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    text = rules(sc, root) + "\nAlso: prefer fetch.\n"
    write(root / CLAUDE, text)
    set_pins(root, ("otherlib==1.0",))
    code, out = sc("sync", root, "--yes")
    assert code == EXIT_OK, out
    assert f"✓ Removed the notes block from {CLAUDE}: toylib dropped" in out
    assert read(root, CLAUDE) == split_front(text)[0] + "Also: prefer fetch.\n"


# ------------------------------------------------------------ the user's own
def test_a_rule_file_since_cutoff_did_not_write_is_never_touched(sc, tmp_path, capsys) -> None:
    root = make_app(tmp_path)
    put(root / CLAUDE, "# My notes on toylib\n")
    put(root / ".claude" / "rules" / "style.md", "Use tabs.\n")
    code, err = errors(capsys, "sync", root, *SONNET, "--yes", "--target", "claude-rules")
    assert code == 1
    assert (
        "since-cutoff-toylib.md exists and has no since-cutoff block, so since-cutoff leaves it "
        "alone; rename or remove it, then run again" in err
    )
    assert read(root, CLAUDE) == "# My notes on toylib\n"
    assert sc("unapply", root)[0] == EXIT_OK
    assert read(root, CLAUDE) == "# My notes on toylib\n"
    assert read(root, ".claude/rules/style.md") == "Use tabs.\n"


def test_unapply_removes_the_rule_files_and_nothing_else(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    put(root / ".cursor" / "rules" / "style.mdc", "---\nalwaysApply: true\n---\nTabs.\n")
    rules(sc, root, "claude-rules")
    rules(sc, root, "cursor-rules")
    code, out = sc("unapply", root, "--target", "cursor-rules")
    assert code == EXIT_OK and f"removed the since-cutoff block from {CURSOR}" in out
    assert not (root / CURSOR).exists() and (root / CLAUDE).exists()
    write(root / "AGENTS.md", MINE)
    code, out = sc("sync", root, *SONNET, "--yes", "--target", "AGENTS.md")
    assert code == EXIT_OK
    code, out = sc("unapply", root)
    assert code == EXIT_OK
    assert f"removed the since-cutoff block from AGENTS.md, {CLAUDE}" in out
    assert not (root / CLAUDE).exists() and read(root, "AGENTS.md") == MINE
    assert read(root, ".cursor/rules/style.mdc") == "---\nalwaysApply: true\n---\nTabs.\n"
    assert sc("unapply", root)[1].strip() == "no since-cutoff block found"


def test_sync_says_when_agents_md_keeps_a_second_copy(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    code, _ = sc("sync", root, *SONNET, "--yes")
    assert code == EXIT_OK and (root / "AGENTS.md").exists()
    code, out = sc("sync", root, *SONNET, "--yes", "--target", "claude-rules")
    assert code == EXIT_OK
    assert (
        "AGENTS.md still has a notes block, which agents load on every request: `since-cutoff "
        "unapply --target AGENTS.md` removes it." in " ".join(out.split())
    )
    # Both are kept in step from then on.
    assert sc("sync", root, "--check")[0] == EXIT_OK


def test_run_leaves_the_rule_files_to_sync(sc, tmp_path, capsys) -> None:
    root = make_app(tmp_path)
    code, err = errors(capsys, "run", root, "--apply", "--target", "cursor-rules")
    assert code == 2
    assert "run `since-cutoff sync --target cursor-rules`" in err
    assert not (root / ".cursor").exists()
