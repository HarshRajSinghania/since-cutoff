"""``since-cutoff explain API`` and the MCP tool ``explain_api`` (issue #28): everything
since-cutoff knows about one API, from the scan sync runs, with no model call and nothing
written.

The toy project and the fake PyPI are test_sync.py's: toylib 1.0 is the release at the cutoff
2025-07-31 and the project pins 2.0, in which `Client.send` lost `temperature` ([diff]),
`legacy_fetch` was removed with "Use fetch instead." in its docstring ([diff + library]) and
`toylib.helpers.Session` moved to `toylib.Session` ([diff + move checked])."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from since_cutoff import cli
from since_cutoff.cache import DiskCache
from since_cutoff.mcp_server import Tools
from since_cutoff.models import ModelRegistry
from tests import test_sync
from tests.test_ci import scan_app
from tests.test_sync import SONNET, make_app, run_block

# The fixtures of test_sync.py: the fake PyPI, and the CLI without network (``sc``).
pypi = test_sync.pypi
sc = test_sync.sc


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def explain(sc: Any, root: Path, api: str, *flags: str) -> tuple[int, str]:
    """``explain API PATH FLAGS`` in a project, which it leaves as it was (the flags after the
    path: Python 3.10's argparse takes no option between two positionals)."""
    before = snapshot(root)
    code, out = sc("explain", api, root, *flags)
    assert snapshot(root) == before  # nothing written
    return code, out


@pytest.fixture
def app(sc: Any, tmp_path: Path) -> Path:
    root = make_app(tmp_path)
    assert sc("sync", root, *SONNET, "--yes")[0] == 0
    return root


def test_a_diff_note_with_both_signatures_and_where_the_code_uses_it(sc, app) -> None:
    code, out = explain(sc, app, "Client.send")
    assert code == 0, out
    # The model and cutoff the notes were written for.
    assert "(from the notes in AGENTS.md; --model to change)" in out
    assert "## Client.send (toylib)" in out
    assert (
        "- `Client.send()` no longer accepts `temperature`; do not pass it. since-cutoff found no "
        "replacement in toylib's deprecation text. Pass `stream` to `Client.send()` by keyword. "
        "[diff]" in out
    )
    assert "Written in: AGENTS.md (from the diff)." in out
    assert (
        "Package: toylib 2.0 (2025-10-01), from pyproject.toml; compared from 1.0 (2025-01-10), "
        "the latest release 30 days before the cutoff." in out
    )
    assert "- param_removed: `toylib.Client.send(temperature=...)`: parameter `temperature`" in out
    assert "  1.0: send(self, message: str, temperature: float = 1.0, stream: bool = False)" in out
    assert "  2.0: send(self, message: str, *, stream: bool = False) -> str" in out
    assert out.count("  2.0: send(self") == 1  # both changes of one API: said once
    assert "- [diff] a static comparison of the two releases' public APIs" in out
    assert "- checked: static API diff (griffe), 1.0 vs 2.0, diff schema" in out
    assert "- runtime: not checked" in out
    assert "- main.py: old form, passes temperature to send" in out
    assert "- sub/other.py: uses this API, calls send" in out
    assert "- no example was type-checked against the pinned version" in out


def test_a_library_replacement_with_the_text_and_file_it_rests_on(sc, app) -> None:
    code, out = explain(sc, app, "legacy_fetch")
    assert code == 0, out
    assert "- `toylib.legacy_fetch` was removed; do not use it. Use `toylib.fetch` instead." in out
    assert "[diff + library]" in out
    assert '  toylib 1.0 said (toylib/helpers.py), docstring: ".. deprecated:: 1.0 Use fetch' in out
    assert (
        "- replacement `toylib.fetch` for `toylib.legacy_fetch` (library_text): toylib 1.0 "
        "toylib/helpers.py" in out
    )
    assert "- [library] the replacement is named in the library's own deprecation text" in out
    # The code does not use it: no block has it, and nothing says where it is used.
    assert "- nowhere: your code does not use this API (it imports the package)" in out
    assert "Not in a notes block yet" in out


def test_a_moved_api_with_what_the_move_kept(sc, app) -> None:
    code, out = explain(sc, app, "Session")
    assert code == 0, out
    assert (
        "- `toylib.helpers.Session` moved to `toylib.Session`: import it with `from toylib "
        "import Session`. [diff + move checked]" in out
    )
    assert "  move evidence: compared class, kept 1, of 1" in out
    assert (
        "- replacement `toylib.Session` for `toylib.helpers.Session` (move_checked): toylib 2.0 "
        "API diff: the object at `toylib.Session` keeps 1 of 1 public names of the old one" in out
    )


@pytest.mark.parametrize(
    "name", ["toylib.fetch", "fetch", "toylib.helpers.fetch", "fetch()", "TOYLIB.FETCH"]
)
def test_an_api_by_any_of_its_names(sc, app, name) -> None:
    code, out = explain(sc, app, name)
    assert code == 0 and "## toylib.fetch (toylib)" in out, out
    assert "- `toylib.fetch()` now requires `timeout`. [diff]" in out
    assert "- main.py: uses this API, calls fetch" in out


def test_an_unknown_api_lists_close_matches(sc, app) -> None:
    code, out = explain(sc, app, "fetchh")
    assert code == 1
    assert (
        "No API named 'fetchh' changed in toylib after claude-sonnet-4-5's training cutoff "
        "(2025-07-31). Close matches: toylib.fetch" in out
    )


def test_json_has_the_same_and_more(sc, app) -> None:
    code, out = explain(sc, app, "send", "--json")
    assert code == 0
    result = json.loads(out)
    assert (result["query"], result["model"], result["cutoff"]) == (
        "send",
        "claude-sonnet-4-5",
        "2025-07-31",
    )
    [found] = result["found"]
    assert found["api"] == "Client.send" and found["in_blocks"] == {"AGENTS.md": "from the diff"}
    assert found["note"]["tags"] == ["diff"] and found["note"]["line"].endswith("[diff]")
    assert [c["kind"] for c in found["changes"]] == ["param_removed", "param_keyword_only"]
    assert (
        found["changes"][0]["new_signature"]
        == "send(self, message: str, *, stream: bool = False) -> str"
    )
    forms = {(u["file"], u["form"]) for u in found["uses"]}
    assert {("main.py", "old_form"), ("sub/other.py", "uses_api")} <= forms
    assert all(u["line"] is None for u in found["uses"])  # file-level until issue #8
    code, out = explain(sc, app, "nothing.like.it", "--json")
    assert code == 1 and json.loads(out)["found"] == []


def test_another_cutoff_and_two_given_releases(sc, app) -> None:
    # A cutoff before toylib 1.0: it is compared from 0.9.
    code, out = explain(sc, app, "Client.send", "--cutoff", "2024-09")
    assert code == 0 and "compared from 0.9 (2024-06-01)" in out
    code, out = explain(sc, app, "fetch", "--package", "toylib", "--from", "1.1", "--to", "2.1")
    assert code == 0, out
    assert "Package: toylib 2.1 (2025-11-01), from as given (--to); compared from 1.1" in out
    assert "- main.py: uses this API, calls fetch" in out


def test_a_type_checked_bullet_points_to_results_json(sc, tmp_path, cache, pypi) -> None:
    root = make_app(tmp_path)
    run_block(root, scan_app(root, cache, pypi, date(2025, 7, 31)))
    assert sc("sync", root, "--yes")[0] == 0  # keeps the [type-checked] note of Client.send
    code, out = explain(sc, root, "Client.send")
    assert code == 0, out
    assert "Written in: AGENTS.md ([type-checked])." in out
    assert "its example and the type checker's verdict are in .since-cutoff/results.json" in out


def test_from_and_to_need_a_package(sc, app, capsys) -> None:
    assert cli.main(["explain", "fetch", str(app), "--from", "1.0"]) == 2
    assert "explain --from and --to need --package" in capsys.readouterr().err
    argv = ["explain", "fetch", str(app), "--package", "toylib", "--from", "2.0", "--to", "1.1"]
    assert cli.main(argv) == 1
    assert "toylib 1.1 is not newer than 2.0: there is no change to explain" in " ".join(
        capsys.readouterr().err.split()
    )


def test_explain_without_notes_uses_the_model_given(sc, tmp_path) -> None:
    root = make_app(tmp_path)
    code, out = explain(sc, root, "Client.send", *SONNET)
    assert code == 0 and "Not in a notes block" not in out and "Written in" not in out
    assert not (root / "AGENTS.md").exists()


def test_the_mcp_tool_explains_too(app, cache: DiskCache, pypi) -> None:
    registry = ModelRegistry(cache, offline=True)
    tools = Tools(cache, registry=registry, pypi=pypi, today=date(2026, 9, 1))
    out = tools.explain_api("legacy_fetch", str(app))
    assert out.startswith("# legacy_fetch\n")
    assert "For claude-sonnet-4-5's training cutoff (2025-07-31)" in out  # the notes' model
    assert "[diff + library]" in out and "toylib 1.0 toylib/helpers.py" in out
    out = tools.explain_api("send", str(app), cutoff="2025-07")
    assert "## Client.send (toylib)" in out and "- main.py: old form" in out
    with pytest.raises(Exception, match="pass `package`"):
        tools.explain_api("send", str(app), from_version="1.0")
