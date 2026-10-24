"""``sync --header-only``, ``sync --profile evaluated`` and project_changes' ``header_only``.

The benchmark's header-only arm (H, NAACL addendum) used the full block with every change line
(``- ...``) removed: the header, which ends with the instruction to follow the block, and one
line per package with its pinned version and the release it is compared from. ``--header-only``
writes that block; ``--profile evaluated`` selects the notes configuration the benchmark
measured (the imported scope, up to 5 APIs per package). No network, no model calls.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from since_cutoff import cli
from since_cutoff.apidiff import REMOVED
from since_cutoff.cache import DiskCache
from since_cutoff.mcp_server import Tools
from since_cutoff.models import ModelRegistry
from since_cutoff.notes import (
    BLOCK_END,
    BLOCK_START,
    IMPORTED_APIS,
    TAG_TYPE_CHECKED,
    body_hash,
    deps_hash,
    diff_note,
    parse_block,
    render_block,
)
from since_cutoff.sync import EXIT_OK, EXIT_OUT_OF_DATE
from tests import test_sync
from tests.test_notes_provenance import CUTOFF, change, sha
from tests.test_sync import SONNET, agents, make_app, set_pins

pypi = test_sync.pypi
sc = test_sync.sc

# The last sentence of the header, as the evaluated H arm had it (since-cutoff 0.4.1's notes
# with the change lines removed, addendum/make_header_notes.py).
H_SENTENCE = "Where these lines conflict with what you remember, follow these lines."


def h_transform(text: str) -> str:
    """addendum/make_header_notes.py: drop every line that starts with ``- ``, collapse the
    blank lines left behind."""
    kept: list[str] = []
    for line in text.splitlines():
        if line.startswith("- "):
            continue
        if line.strip() == "" and kept and kept[-1].strip() == "":
            continue
        kept.append(line)
    return "\n".join(kept).strip() + "\n"


def body_of(block: str) -> str:
    """The block's lines after the meta line, up to the end marker."""
    lines = block.splitlines()
    assert lines[0] == BLOCK_START and lines[-1] == BLOCK_END
    return "\n".join(lines[2:-1]) + "\n"


def meta_of(block: str) -> dict[str, Any]:
    parsed = parse_block(block)
    assert parsed is not None
    return parsed.meta


# ------------------------------------------------------------------- the block
GOLDEN_HEADER = """\
## Library changes after the model's training cutoff

Changed after the training cutoff of `claude-sonnet-4-5` (2025-07-31, comparing from releases up \
to 2025-07-01) in the packages this project imports, at the versions in `uv.lock`, according to \
[since-cutoff](https://github.com/MohammadHijjawi97/since-cutoff) 0.4.0. Tags: [diff] a static \
comparison of the two releases' public APIs; [library] the replacement is named in the library's \
own deprecation text and exists in the pinned version; [type-checked] an example that basedpyright \
accepts for the pinned version. No library code was run. Where these lines conflict with what you \
remember, follow these lines.

**anthropic 1.8.0** (compared from 0.60.0)

**huggingface-hub 2.0.0** (compared from 1.21.0)
"""


def two_packages() -> list[Any]:
    """A note for each of two packages (anthropic: a lost parameter; huggingface-hub: a
    removed class)."""
    anthropic = diff_note([change(param=p) for p in ("temperature", "top_p")])
    hub = diff_note(
        [
            change(
                kind=REMOVED,
                pkg="huggingface-hub",
                path="huggingface_hub.InferenceApi",
                name="InferenceApi",
                owner=None,
                param=None,
                old="1.21.0",
                new="2.0.0",
            )
        ]
    )
    return [anthropic, hub]


def test_golden_header_only_block() -> None:
    """The header-only block, byte for byte: the full block's header, one line per package, no
    change lines, and a meta line that records the choice."""
    notes = two_packages()
    options: dict[str, Any] = {
        "model": "claude-sonnet-4-5",
        "cutoff": CUTOFF,
        "version_source": "uv.lock",
        "deps": deps_hash([("anthropic", "1.8.0"), ("huggingface-hub", "2.0.0")]),
        "scope": "imported",
        "tool": "0.4.0",
    }
    block = render_block(notes, **options, header_only=True)
    meta = {
        "v": 2,
        "tool": "0.4.0",
        "model": "claude-sonnet-4-5",
        "cutoff": "2025-07-31",
        "margin": 30,
        "versions_from": "uv.lock",
        "deps": sha("anthropic==1.8.0\nhuggingface-hub==2.0.0"),
        "body": sha(GOLDEN_HEADER),
        "scope": "imported",
        "header_only": True,
    }
    meta_line = "<!-- since-cutoff:meta " + json.dumps(meta, separators=(",", ":")) + " -->"
    assert block == f"{BLOCK_START}\n{meta_line}\n{GOLDEN_HEADER}{BLOCK_END}\n"
    assert GOLDEN_HEADER.split("\n\n")[1].endswith(
        H_SENTENCE.replace("these lines.", "these\nlines.").replace("\n", " ")
    )
    # The block parses as one with two packages, no bullets, and is not taken for a hand edit.
    parsed = parse_block(block)
    assert parsed is not None and parsed.edited is False
    assert {k: (v.version, v.cutoff_version, v.bullets) for k, v in parsed.packages.items()} == {
        "anthropic": ("1.8.0", "0.60.0", []),
        "huggingface-hub": ("2.0.0", "1.21.0", []),
    }


@pytest.mark.parametrize("scope", ["used", "imported"])
def test_the_header_is_the_full_block_without_its_change_lines(scope: str) -> None:
    """What the evaluated H arm did to a full block (make_header_notes.py) gives the header-only
    block's text: only the meta line differs (``header_only``, and the hash of the body)."""
    notes = two_packages()
    options: dict[str, Any] = {
        "model": "claude-sonnet-4-5",
        "cutoff": CUTOFF,
        "version_source": "uv.lock",
        "scope": scope,
    }
    full = render_block(notes, **options)
    header = render_block(notes, **options, header_only=True)
    assert any(line.startswith("- ") for line in full.splitlines())
    assert not any(line.startswith("- ") for line in header.splitlines())
    assert body_of(header) == h_transform(body_of(full))
    assert H_SENTENCE in " ".join(body_of(header).split())
    full_meta, header_meta = meta_of(full), meta_of(header)
    assert header_meta.pop("header_only") is True and "header_only" not in full_meta
    assert header_meta.pop("body") == body_hash(body_of(header))
    full_meta.pop("body")
    assert header_meta == full_meta


def test_a_header_records_no_type_checked_apis() -> None:
    note = diff_note([change(param="temperature")])
    checked = type(note)(note.change, note.bullet, "x = 1", True, "model", (TAG_TYPE_CHECKED,))
    options: dict[str, Any] = {"model": "m", "cutoff": CUTOFF, "version_source": "uv.lock"}
    assert "checked" in meta_of(render_block([checked], **options))
    assert "checked" not in meta_of(render_block([checked], **options, header_only=True))


# -------------------------------------------------------------------- the CLI
def test_sync_header_only_writes_the_header_and_the_block_keeps_it(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    code, out = sc("sync", root, *SONNET, "--header-only", "--yes")
    assert code == EXIT_OK, out
    assert "✓ Created AGENTS.md with a header for 1 package." in out
    text = agents(root)
    block = parse_block(text)
    assert block is not None and block.edited is False
    # No --scope and no block: the packages the code imports, as the benchmark's header.
    assert block.meta["scope"] == "imported" and block.meta["header_only"] is True
    assert {k: (v.version, v.bullets) for k, v in block.packages.items()} == {"toylib": ("2.0", [])}
    assert "**toylib 2.0** (compared from 1.0)" in text
    assert not any(line.startswith("- ") for line in text.splitlines())
    assert H_SENTENCE in " ".join(text.split())

    # The next sync keeps it (the meta line is the setting), and says what the block holds.
    code, out = sc("sync", root, "--yes")
    assert code == EXIT_OK and "AGENTS.md is up to date: a header for 1 package for" in out
    assert agents(root) == text

    # --no-header-only writes the change lines again, and says so.
    code, out = sc("sync", root, "--check", "--no-header-only")
    assert code == EXIT_OUT_OF_DATE
    assert "it is the header only, without the change lines (--no-header-only)" in out
    code, out = sc("sync", root, "--no-header-only", "--yes")
    assert code == EXIT_OK
    assert "now with the change lines (it was the header only; --no-header-only)" in out
    block = parse_block(agents(root))
    assert block is not None and "header_only" not in block.meta
    assert block.meta["scope"] == "imported" and block.packages["toylib"].bullets

    # And back: the switch is said once, not as notes dropped package by package.
    code, out = sc("sync", root, "--header-only", "--yes")
    assert code == EXIT_OK and "now the header only, no change lines (--header-only)" in out
    assert "dropped" not in out
    assert agents(root) == text


def test_header_only_keeps_a_scope_given_or_written(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    assert sc("sync", root, *SONNET, "--yes")[0] == EXIT_OK  # a block for the used scope
    assert sc("sync", root, "--header-only", "--yes")[0] == EXIT_OK
    block = parse_block(agents(root))
    assert block is not None and block.meta["scope"] == "used" and block.meta["header_only"]
    assert sc("sync", root, "--scope", "imported", "--yes")[0] == EXIT_OK
    block = parse_block(agents(root))
    assert block is not None and block.meta["scope"] == "imported" and block.meta["header_only"]


def test_a_header_after_a_bump_says_the_new_version_without_note_counts(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    assert sc("sync", root, *SONNET, "--header-only", "--yes")[0] == EXIT_OK
    set_pins(root, ("toylib==2.1", "otherlib==1.0"))
    code, out = sc("sync", root, "--check")
    assert code == EXIT_OUT_OF_DATE and "toylib 2.0 in the notes, 2.1 in" in out
    code, out = sc("sync", root, "--yes")
    assert code == EXIT_OK and "Updated AGENTS.md: toylib checked again for 2.1." in out
    assert "**toylib 2.1** (compared from 1.0)" in agents(root)


def test_header_only_in_json_and_status(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    code, out = sc("sync", root, *SONNET, "--header-only", "--yes", "--json")
    assert code == EXIT_OK
    [target] = json.loads(out[out.index("{") :])["targets"]
    assert target["header_only"] is True and target["packages"] == 1 and target["notes"] == 0
    code, out = sc("status", root, "--json")
    [status] = json.loads(out[out.index("{") :])["targets"]
    assert status["header_only"] is True and status["scope"] == "imported"


def test_header_only_with_nothing_imported_writes_nothing(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    (root / "main.py").write_text("import json\n", encoding="utf-8")
    (root / "sub" / "other.py").unlink()
    code, out = sc("sync", root, *SONNET, "--header-only", "--yes")
    assert code == EXIT_OK and "AGENTS.md: no notes to write" in out
    assert not (root / "AGENTS.md").exists()


def test_profile_evaluated_is_the_imported_scope_with_five_apis_per_package(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    (root / "main.py").write_text("import toylib\n", encoding="utf-8")
    (root / "sub" / "other.py").unlink()
    code, out = sc("sync", root, *SONNET, "--profile", "evaluated", "--yes")
    assert code == EXIT_OK, out
    block = parse_block(agents(root))
    assert block is not None and block.meta["scope"] == "imported"
    assert "per_package" not in block.meta and "header_only" not in block.meta  # the defaults
    assert len(block.packages["toylib"].bullets) == IMPORTED_APIS == 5
    # The block keeps it: a later sync with no flags is up to date.
    code, out = sc("sync", root, "--check")
    assert code == EXIT_OK, out
    # The same as giving the two flags.
    code, out = sc("sync", root, "--check", "--scope", "imported", "--per-package", "5")
    assert code == EXIT_OK, out
    # With --header-only: the evaluated header-only arm (H).
    code, out = sc("sync", root, "--profile", "evaluated", "--header-only", "--yes")
    assert code == EXIT_OK and "now the header only" in out


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (
            ["--scope", "used"],
            "--profile evaluated sets --scope imported; --scope used contradicts",
        ),
        (["--per-package", "2"], "--profile evaluated sets --per-package 5; --per-package 2"),
    ],
)
def test_profile_refuses_a_contradicting_flag(tmp_path, capsys, flags, message) -> None:
    # Refused before the project is read or anything is looked up.
    root = make_app(tmp_path)
    code = cli.main(["sync", str(root), *SONNET, "--profile", "evaluated", *flags, "--yes"])
    captured = capsys.readouterr()
    assert code == 1 and captured.out == ""
    assert message in " ".join(captured.err.split())
    assert not (root / "AGENTS.md").exists()


def test_the_parser_has_the_flags_and_profiles() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["sync", "--header-only", "--profile", "evaluated"])
    assert args.header_only is True and args.profile == "evaluated"
    assert parser.parse_args(["sync", "--no-header-only"]).header_only is False
    assert parser.parse_args(["sync"]).header_only is None
    with pytest.raises(SystemExit):
        parser.parse_args(["sync", "--profile", "fastest"])
    assert cli.PROFILES == {"evaluated": {"scope": "imported", "per_package": IMPORTED_APIS}}


# -------------------------------------------------------------------- the MCP tool
@pytest.fixture
def tools(cache: DiskCache, fake_pypi: Any) -> Tools:
    registry = ModelRegistry(cache, offline=True)
    return Tools(cache, registry=registry, pypi=fake_pypi, today=date(2026, 9, 1))


def mcp_app(tmp_path: Path, code: str) -> Path:
    root = tmp_path / "app"
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "0"\ndependencies = ["toylib==2.0"]\n',
        encoding="utf-8",
    )
    (root / "main.py").write_text(code, encoding="utf-8")
    return root


def test_project_changes_header_only_is_what_sync_writes(tools: Tools, tmp_path: Path) -> None:
    root = mcp_app(tmp_path, "import toylib\n")
    out = tools.project_changes(str(root), model="claude-sonnet-4-5", header_only=True)
    assert out.startswith("## Library changes after the model's training cutoff\n\n")
    assert "in the packages this project imports, at the versions in `pyproject.toml`" in out
    assert H_SENTENCE in out
    assert out.endswith("\n\n**toylib 2.0** (compared from 1.0)\n")
    assert BLOCK_START not in out and "since-cutoff:meta" not in out
    assert not any(line.startswith("- ") for line in out.splitlines())


def test_project_changes_header_only_with_nothing_imported(tools: Tools, tmp_path: Path) -> None:
    root = mcp_app(tmp_path, "import json\n")
    out = tools.project_changes(str(root), cutoff="2025-07", header_only=True)
    # The day it compares from, as the rest of 0.6 says it, not "after the cutoff".
    assert out.startswith(
        "No package this project imports changed its API after 2025-07-01 (30 days before the "
        "cutoff). Cutoff 2025-07-31 ("
    )
    assert out.endswith("; versions from pyproject.toml.\n")
    out = tools.project_changes(str(root), cutoff="2025-07", header_only=True, cutoff_margin=0)
    assert out.startswith("No package this project imports changed its API after the cutoff. ")
