"""Sources the running Python cannot parse (apidiff._check_parsed, Engine._finish).

numpy 2.5.4's ``__init__.pyi:737`` (PEP 695) and numpy 2.3.1's ``__init__.pyi:801`` (PEP 646):
Python 3.10 cannot parse either, and the scan said "no breaking changes" of numpy. Most tests
pretend to be Python 3.10 (conftest.pretend_python), whatever Python runs them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

from since_cutoff import apidiff
from since_cutoff.apidiff import (
    REMOVED,
    UNREAD_NEXT_TO,
    UNREAD_SIBLING,
    UNREAD_SYNTAX,
    UNREAD_UNPARSED,
    APIChange,
    UnparsedSources,
    _needs_python,
    _requires_floor,
    diff_sources_with_unread,
    unread_text,
)
from since_cutoff.cache import DiskCache
from since_cutoff.engine import CHANGED, SKIPPED, Engine, PackageScan, Sibling, _unparsed_sibling
from since_cutoff.project import load_project
from since_cutoff.pypi import SourceTree
from since_cutoff.report import fail_reason, to_json
from tests.conftest import FakePyPI, pretend_python, write_tree
from tests.test_engine import make_engine, make_project

NUMPY_TYPE_LINE = "type _Falsy = L[False, 0] | bool_[L[False]]"
NUMPY_STAR_LINE = '_1NShapeT = TypeVar("_1NShapeT", bound=tuple[L[1], *tuple[L[1], ...]])'
NEWER = sys.version_info >= (3, 12)  # parses ``type X = int`` itself


def _typed_stub(tmp_path: Path) -> tuple[Path, Path]:
    old = write_tree(tmp_path / "old", {"tp/__init__.py": "def f(a, b): ...\n"})
    new = write_tree(
        tmp_path / "new",
        {
            "tp/__init__.py": "def f(a): ...\n",
            "tp/__init__.pyi": "type X = int\n\ndef f(a) -> X: ...\n",
        },
    )
    return old, new


# ------------------------------------------------------------ what blocks a package
def test_a_stub_the_running_python_cannot_parse_is_not_checked(tmp_path, older_python) -> None:
    """The top-level stub is where griffe gives up on the whole package: the diff raises,
    naming the release and the Python that can parse it, instead of finding no changes."""
    old, new = _typed_stub(tmp_path)
    with pytest.raises(UnparsedSources) as raised:
        diff_sources_with_unread("tp", "1.0", old, "2.5.4", new, ["tp"])
    assert str(raised.value) == (
        "Python 3.10 cannot parse tp 2.5.4's sources; run since-cutoff with Python 3.12 or later "
        "to check it"
    )


@pytest.mark.skipif(NEWER, reason="this Python parses PEP 695 type statements")
def test_a_pep_695_stub_on_an_older_python_is_not_checked(tmp_path) -> None:
    old, new = _typed_stub(tmp_path)
    with pytest.raises(UnparsedSources, match=r"run since-cutoff with Python 3\.12 or later"):
        diff_sources_with_unread("tp", "1.0", old, "2.5.4", new, ["tp"])


def test_both_releases_are_named_without_loading_the_pinned_one(
    tmp_path, older_python, monkeypatch
) -> None:
    """numpy 2.3.1 and 2.5.4 on Python 3.10: the comparison release fails first. The pinned
    one's top-level files and its Requires-Python say which Python parses both; loading all of
    it for that took numpy 3.3 s on every run."""
    _, new = _typed_stub(tmp_path)
    old = write_tree(tmp_path / "older", {"tp/__init__.py": "type X = int\n"})
    loads: list[Path] = []
    load = apidiff.load_api

    def counted(name: str, root: Path, *args: Any, **kwargs: Any) -> Any:
        loads.append(root)
        return load(name, root, *args, **kwargs)

    monkeypatch.setattr(apidiff, "load_api", counted)
    with pytest.raises(UnparsedSources, match=r"^Python 3\.10 cannot parse tp 2\.3\.1's and "):
        diff_sources_with_unread("tp", "2.3.1", old, "2.5.4", new, ["tp"])
    assert loads == [old]
    # The pinned release parses here, but it requires Python 3.13: that is the one named.
    plain = write_tree(tmp_path / "plain", {"tp/__init__.py": "def f(a): ...\n"})
    with pytest.raises(UnparsedSources) as raised:
        diff_sources_with_unread(
            "tp", "2.3.1", old, "2.5.4", plain, ["tp"], new_requires_python=">=3.13"
        )
    assert str(raised.value) == (
        "Python 3.10 cannot parse tp 2.3.1's sources; run since-cutoff with Python 3.13 or later "
        "to check it"
    )


def test_a_public_module_in_newer_syntax_is_not_checked(tmp_path, older_python) -> None:
    old = write_tree(tmp_path / "old", {"tp/__init__.py": "", "tp/gen.py": "def g(x): ...\n"})
    new = write_tree(tmp_path / "new", {"tp/__init__.py": "", "tp/gen.py": "def g[T](x: T): ...\n"})
    with pytest.raises(UnparsedSources, match=r"^Python 3\.10 cannot parse tp 2\.0's sources"):
        diff_sources_with_unread("tp", "1.0", old, "2.0", new, ["tp"])


def test_a_private_module_a_public_name_leads_to_is_not_checked(tmp_path, older_python) -> None:
    """scikit-learn 1.9.1 on Python 3.10: ``sklearn/linear_model/_logistic.py`` has
    ``coefs_paths[0, :, *best_index, :]``, and ``LogisticRegression`` is defined there. The
    diff reported 103 changes and none of LogisticRegression's five, under a warning about a
    "private module"."""
    old = write_tree(
        tmp_path / "old",
        {
            "sk/__init__.py": "from sk._logistic import LogisticRegression\n",
            "sk/_logistic.py": "class LogisticRegression:\n    def __init__(self, multi_class=None): ...\n",
        },
    )
    new = write_tree(
        tmp_path / "new",
        {
            "sk/__init__.py": "from sk._logistic import LogisticRegression\n",
            "sk/_logistic.py": (
                "# fails: invalid syntax\nx = paths[0, :, *best_index, :]\n\n"
                "class LogisticRegression:\n    def __init__(self): ...\n"
            ),
        },
    )
    with pytest.raises(UnparsedSources, match=r"run since-cutoff with Python 3\.11 or later"):
        diff_sources_with_unread("sk", "1.7.0", old, "1.9.1", new, ["sk"])


def test_a_private_module_in_newer_syntax_is_counted_and_said_once(tmp_path, older_python):
    """A private module no public name leads to, which griffe drops with a debug log: the rest
    is compared, and the unread entries say which modules were left out and which Python reads
    them."""
    old = write_tree(tmp_path / "old", {"tp/__init__.py": "def f(a, b): ...\n"})
    new = write_tree(
        tmp_path / "new",
        {
            "tp/__init__.py": "def f(a): ...\n",
            "tp/_core/__init__.py": "",
            "tp/_core/gen.py": "def g[T](x: T) -> T: ...\n",
            "tp/_core/more.py": "type Y = str\n",
        },
    )
    changes, unread = diff_sources_with_unread("tp", "1.0", old, "2.0", new, ["tp"])
    assert [(c["kind"], c["path"], c["parameter"]) for c in changes] == [
        ("param_removed", "tp.f", "b")
    ]
    assert unread == [f"tp._core.gen{UNREAD_SYNTAX}3.12", f"tp._core.more{UNREAD_SYNTAX}3.12"]
    assert unread_text("tp", "2.0", "1.0", unread) == (
        "tp 2.0: 2 private modules (tp._core.gen and tp._core.more) use syntax that Python 3.10 "
        "cannot parse, so changes in them are not reported; run since-cutoff with Python 3.12 or "
        "later to check them"
    )


# ------------------------------------------------------- what is no newer syntax
PY2_LEGACY = {
    "except": "try:\n    pass\nexcept ValueError, e:\n    print 'oops', e\n",
    "star call": 'def show(rows):\n    print "row", f(a, *rest)\n',
    "print": 'print "hi"\n',
}


@pytest.mark.parametrize("legacy", sorted(PY2_LEGACY))
@pytest.mark.parametrize("running", [(3, 10), (3, 13)])
def test_a_public_python_2_module_does_not_skip_the_package(
    tmp_path, monkeypatch, legacy: str, running: tuple[int, int]
) -> None:
    """``except ValueError, e:`` read as PEP 758 and ``f(a, *rest)`` as PEP 646: the package
    was skipped, with "run since-cutoff with Python 3.14" (on 3.13, and 3.11 on 3.10, for a
    module no Python parses). It is compared as before, with the module left out and said."""
    pretend_python(monkeypatch, running, fails=())  # no Python 3 parses them: a real error
    files = {"tp/__init__.py": "def f(a, b): ...\n", "tp/legacy.py": PY2_LEGACY[legacy]}
    old = write_tree(tmp_path / "old", files)
    new = write_tree(tmp_path / "new", {**files, "tp/__init__.py": "def f(a): ...\n"})
    changes, unread = diff_sources_with_unread(
        "tp", "1.0", old, "2.0", new, ["tp"], new_requires_python=">=3.8"
    )
    assert [c["parameter"] for c in changes] == ["b"]
    shown = f"{running[0]}.{running[1]}"
    assert unread == [f"tp.legacy{UNREAD_UNPARSED}{shown}"]
    assert unread_text("tp", "2.0", "1.0", unread) == (
        f"tp 2.0: 1 module (tp.legacy) could not be parsed by Python {shown}, so changes in it "
        "are not reported"
    )


# ------------------------------------------------------------- which Python can
def _error(tmp_path: Path, source: str, line: int = 1, message: str = "invalid syntax") -> Any:
    file = tmp_path / "m.py"
    file.write_text(source, encoding="utf-8")
    text = source.splitlines()[line - 1] + "\n"
    return SyntaxError(message, (str(file), line, 1, text))


@pytest.mark.parametrize(
    ("source", "message", "running", "version"),
    [
        (NUMPY_TYPE_LINE, "invalid syntax", (3, 10), (3, 12)),
        (NUMPY_TYPE_LINE, "invalid syntax", (3, 12), None),  # it parses that: something else
        (NUMPY_STAR_LINE, "invalid syntax", (3, 10), (3, 11)),
        ("class Array(Generic[*Shape]): ...", "invalid syntax", (3, 10), (3, 11)),
        # A formatted subscript fails on its first line.
        ("class G(Generic[\n    *Ts\n]): ...", "invalid syntax", (3, 10), (3, 11)),
        (
            "def h(x: tuple[\n    int,\n    *Ts,\n]) -> None: ...",
            "invalid syntax",
            (3, 10),
            (3, 11),
        ),
        ("x = coefs_paths[0, :, *best_index, :]", "invalid syntax", (3, 10), (3, 11)),
        ("def call(*args: *Ts) -> None: ...", "invalid syntax", (3, 10), (3, 11)),
        ("def first[T](xs: list[T]) -> T: ...", "invalid syntax", (3, 10), (3, 12)),
        ("class Box[T = int]: ...", "invalid syntax", (3, 12), (3, 13)),
        ("except* ValueError:", "invalid syntax", (3, 10), (3, 11)),
        ('x = f"{d["k"]}"', "f-string: unmatched '['", (3, 10), (3, 12)),
        (
            "x = f\"{'\\n'.join(a)}\"",
            "f-string expression part cannot include a backslash",
            (3, 10),
            (3, 12),
        ),
        ('x = f"""{a # c\n}"""', "f-string expression part cannot include '#'", (3, 11), (3, 12)),
        ('x = f"{a +\n b}"', "unterminated string literal (detected at line 1)", (3, 10), (3, 12)),
        ("except ValueError, TypeError:", "invalid syntax", (3, 13), (3, 14)),
        ('x = t"hello {name}"', "invalid syntax", (3, 13), (3, 14)),
        ('x = rt"a" + Tr"b"', "invalid syntax", (3, 10), (3, 14)),
        # Python 2 and templates: no Python parses them.
        ("except ValueError, e:", "invalid syntax", (3, 10), None),
        ("except ValueError, e:", "invalid syntax", (3, 13), None),
        ('print "row", f(a, *rest)', "Missing parentheses", (3, 10), None),
        ('print "a t"', "Missing parentheses", (3, 13), None),
        ('print "row", rows[i * n]', "Missing parentheses", (3, 10), None),
        ("x = [*a, *b] + [", "invalid syntax", (3, 10), None),
        ('print "hi"', "Missing parentheses", (3, 10), None),
        ("{{ cookiecutter.name }} = 1", "invalid syntax", (3, 10), None),
    ],
)
def test_which_python_parses_a_statement(
    tmp_path, monkeypatch, source: str, message: str, running: tuple[int, int], version: Any
) -> None:
    monkeypatch.setattr(apidiff, "_running", lambda: running)
    assert _needs_python(_error(tmp_path, source, message=message)) == version


@pytest.mark.parametrize(
    ("requires", "running", "floor"),
    [
        (">=3.12", (3, 10), (3, 12)),
        (">=3.11.2", (3, 11), None),  # 3.11.4 installs it
        (">=3.8", (3, 13), None),
        (">=3.14", (3, 13), (3, 14)),
        ("<3.9", (3, 10), None),  # no later Python either: no floor
        ("not a specifier", (3, 10), None),
        (None, (3, 10), None),
    ],
)
def test_the_python_a_release_requires(
    monkeypatch, requires: str | None, running: tuple[int, int], floor: Any
) -> None:
    monkeypatch.setattr(apidiff, "_running", lambda: running)
    assert _requires_floor(requires) == floor


def test_the_line_an_error_names_is_read_when_its_file_is_not(monkeypatch) -> None:
    monkeypatch.setattr(apidiff, "_running", lambda: (3, 10))
    error = SyntaxError("invalid syntax", (None, 1, 1, NUMPY_TYPE_LINE + "\n"))
    assert _needs_python(error) == (3, 12)


def test_a_top_level_module_no_python_parses_is_named_with_its_error(tmp_path) -> None:
    """Python 2 code in a release's ``__init__.py``: nothing is loaded, and no Python can be
    named, so the reason says where the parse failed."""
    old = write_tree(tmp_path / "old", {"tp/__init__.py": "def f(a, b): ...\n"})
    new = write_tree(tmp_path / "new", {"tp/__init__.py": 'print "hi"\n'})
    with pytest.raises(UnparsedSources) as raised:
        diff_sources_with_unread("tp", "1.0", old, "2.0", new, ["tp"])
    running = apidiff.running_python()
    assert str(raised.value).startswith(
        f"tp 2.0's tp could not be parsed by Python {running} (tp/__init__.py, line 1: "
    )
    assert str(raised.value).endswith("), so since-cutoff could not check tp")


def test_a_release_that_excludes_this_python_is_newer_syntax(tmp_path, monkeypatch) -> None:
    """tstring-util 2.1 requires Python 3.14: whatever its line shows, a module of it that
    Python 3.13 cannot parse is newer syntax; a Python 2 line in a release that allows the
    running Python is not."""
    monkeypatch.setattr(apidiff, "_running", lambda: (3, 13))
    legacy = _error(tmp_path, 'print "hi"')
    assert _needs_python(legacy, ">=3.14") == (3, 14)
    assert _needs_python(legacy, ">=3.8") is None
    monkeypatch.setattr(apidiff, "_running", lambda: (3, 10))
    assert _needs_python(_error(tmp_path, NUMPY_TYPE_LINE), ">=3.11") == (3, 12)


NEWER_FORMS = {
    # sphinx-autodoc-typehints 3.17's ``_render/value.py:37``
    "backslash": (
        "# fails: f-string expression part cannot include a backslash\nx = f\"{'\\n'.join(a)}\"\n",
        (3, 10),
        "3.12",
    ),
    # its ``_resolve/typed_dict.py:79``
    "split star": (
        "# fails: invalid syntax\nT = Annotated[\n    int,\n    *metadata,\n]\n",
        (3, 10),
        "3.11",
    ),
    "t-string": ('# fails: invalid syntax\nx = t"hello {name}"\n', (3, 13), "3.14"),
}


@pytest.mark.parametrize("form", sorted(NEWER_FORMS))
def test_a_public_module_in_syntax_seen_beyond_its_line_is_not_checked(
    tmp_path, monkeypatch, form: str
) -> None:
    """The line griffe's SyntaxError names showed nothing newer: ``pkg.api`` was "removed", and
    that diff was cached for every Python."""
    code, running, needed = NEWER_FORMS[form]
    pretend_python(monkeypatch, running, fails=())
    old = write_tree(
        tmp_path / "old",
        {"pkg/__init__.py": "", "pkg/api.py": "def connect(host, timeout=None): ...\n"},
    )
    new = write_tree(
        tmp_path / "new", {"pkg/__init__.py": "", "pkg/api.py": f"{code}\ndef connect(host): ...\n"}
    )
    with pytest.raises(UnparsedSources, match=rf"with Python {re.escape(needed)} or later"):
        diff_sources_with_unread("pkg", "1.0", old, "2.0", new, ["pkg"])


# ------------------------------------------------- a distribution read next to it
def test_a_star_imported_distribution_this_python_cannot_parse_only_leaves_its_names_out(
    tmp_path, older_python
) -> None:
    """scikit-learn and matplotlib on Python 3.10: ``from numpy import *`` reads numpy 2.3.1
    and 2.5.4 next to them, and numpy's stub made both "not checked", blaming their own
    sources. The package is compared; the names it takes from there are said not to be, from
    the release that could not be read (numpy 2.3.1, next to scikit-learn 1.7.0; the 2.2.6 the
    project pins parses)."""
    newer = write_tree(
        tmp_path / "ext-1.4", {"extdist/__init__.py": "type Alias = int\n\ndef h(): ...\n"}
    )
    plain = write_tree(tmp_path / "ext-1.2", {"extdist/__init__.py": "def h(): ...\n"})
    old = write_tree(
        tmp_path / "old",
        {"pkg/__init__.py": "def g(): ...\n", "pkg/compat.py": "from extdist import *\n"},
    )
    new = write_tree(
        tmp_path / "new", {"pkg/__init__.py": "", "pkg/compat.py": "from extdist import *\n"}
    )
    changes, unread = diff_sources_with_unread(
        "pkg", "1.0", old, "2.0", new, ["pkg"], old_roots=[newer], new_roots=[plain]
    )
    assert [(c["kind"], c["path"]) for c in changes] == [(REMOVED, "pkg.g")]
    assert unread == [f"{UNREAD_SIBLING}extdist{UNREAD_NEXT_TO}1.0{UNREAD_SYNTAX}3.12"]
    assert unread_text("pkg", "2.0", "1.0", unread) == ""  # the re-export warning's
    scan = PackageScan("pkg", "2.0", "pinned", True, cutoff_version="1.0")
    read = [
        [Sibling("extdist", "extdist", ("pkg.compat",), "extdist>=1", version=v)]
        for v in ("1.4", "1.2")
    ]
    _unparsed_sibling(scan, unread[0], (read[0], read[1]))
    assert scan.reexported == {
        "pkg.compat": (
            "extdist 1.4, whose sources Python 3.10 cannot parse: run since-cutoff with Python "
            "3.12 or later to read them"
        )
    }


# ----------------------------------------------------------------- the engine
def _typed_pypi(cache: DiskCache, root: Path, *, legacy: bool = False) -> FakePyPI:
    """tp 1.0 and 2.5.4, whose ``__init__.pyi`` has a PEP 695 ``type`` statement (numpy 2.5's
    does): Python 3.10 and 3.11 cannot parse it. With ``legacy``, 2.5.4 parses, and ships a
    module of Python 2 code."""
    old = write_tree(root / "tp-1.0", {"tp/__init__.py": "def f(a, b): ...\n"})
    files = {"tp/__init__.py": "def f(a): ...\n"}
    if legacy:
        files["tp/legacy.py"] = 'print "hi"\n'
    else:
        files["tp/__init__.pyi"] = "type X = int\ndef f(a) -> X: ...\n"
    new = write_tree(root / "tp-2.5.4", files)
    return FakePyPI(
        cache,
        {"tp": [("1.0", "2025-01-10"), ("2.5.4", "2025-10-01")]},
        {
            ("tp", "1.0"): SourceTree("tp", "1.0", old, ("tp",)),
            ("tp", "2.5.4"): SourceTree("tp", "2.5.4", new, ("tp",)),
        },
    )


def test_a_package_the_running_python_cannot_parse_could_not_be_checked(
    tmp_path, cache, scripted, older_python
):
    """numpy 2.5.4 on Python 3.10: the diff logged "cannot load numpy" at DEBUG and the scan
    said no breaking changes. The package is SKIPPED, its reason naming the Python that can
    parse it (once: not again as a warning), nothing is cached, and --fail-on fails."""
    engine = make_engine(cache, _typed_pypi(cache, tmp_path), scripted)
    project = load_project(make_project(tmp_path, '"tp==2.5.4"', "import tp\ntp.f(1)\n"))
    scan = engine.scan(project, engine.resolve_target())
    pkg = scan.package("tp")
    reason = (
        "Python 3.10 cannot parse tp 2.5.4's sources; run since-cutoff with Python 3.12 or later "
        "to check it"
    )
    assert (pkg.status, pkg.reason, pkg.changes, pkg.unparsed) == (SKIPPED, reason, [], True)
    assert not any("cannot parse" in w for w in scan.warnings)
    for key in (Engine._diff_key(pkg), Engine._unread_key(pkg)):
        assert cache.get("diffs", key) is None  # no empty diff cached
        assert cache.get("diffs", Engine._python_key(key)) is None
    assert to_json(scan)["dependencies_skipped"] == 1
    assert fail_reason(scan, {"used"}) == (
        "--fail-on: tp could not be checked: Python 3.10 cannot parse its sources (see its "
        "reason above)"
    )
    assert fail_reason(scan, set()) is None
    # A diff a newer Python cached is served, without parsing anything.
    gone = APIChange("tp", "1.0", "2.5.4", REMOVED, "tp.g", "g", tier="public")
    cache.set("diffs", Engine._diff_key(pkg), [gone.to_dict()])
    again = make_engine(cache, _typed_pypi(cache, tmp_path), scripted).scan(
        project, engine.resolve_target()
    )
    assert again.package("tp").status == CHANGED
    assert [c.path for c in again.package("tp").changes] == ["tp.g"]


def test_a_diff_with_a_module_left_out_is_cached_for_its_python_only(
    tmp_path, cache, scripted, monkeypatch
):
    """A diff that left out a module the running Python could not parse was stored under the
    key every Python reads: a newer one was served what an older one could not read."""
    pretend_python(monkeypatch, (3, 13), fails=())
    pypi = _typed_pypi(cache, tmp_path, legacy=True)
    project = load_project(make_project(tmp_path, '"tp==2.5.4"', "import tp\ntp.f(1)\n"))
    engine = make_engine(cache, pypi, scripted)
    scan = engine.scan(project, engine.resolve_target())
    pkg = scan.package("tp")
    assert pkg.status == CHANGED and pkg.unread == [f"tp.legacy{UNREAD_UNPARSED}3.13"]
    key = Engine._diff_key(pkg)
    assert cache.get("diffs", key) is None
    assert cache.get("diffs", Engine._python_key(key)) is not None
    # The same Python is served it; another one diffs again.
    diffs: list[str] = []
    diff = apidiff.diff_sources_with_unread

    def counted(*args: Any, **kwargs: Any) -> Any:
        diffs.append(kwargs.get("package") or args[0])
        return diff(*args, **kwargs)

    monkeypatch.setattr("since_cutoff.engine.diff_sources_with_unread", counted)
    again = make_engine(cache, pypi, scripted).scan(project, engine.resolve_target())
    assert diffs == [] and again.package("tp").unread == pkg.unread
    monkeypatch.setattr(apidiff, "_running", lambda: (3, 14))
    newer = make_engine(cache, pypi, scripted).scan(project, engine.resolve_target())
    assert diffs == ["tp"] and newer.package("tp").unread == [f"tp.legacy{UNREAD_UNPARSED}3.14"]


@pytest.mark.skipif(sys.version_info >= (3, 14), reason="this Python parses t-strings")
def test_a_package_a_worker_process_cannot_parse_could_not_be_checked(tmp_path, cache, scripted):
    """Two packages diff in worker processes, where no test can pretend: a t-string (PEP 750),
    which no Python before 3.14 parses, makes one SKIPPED and leaves the other checked. Without
    its own ``except``, the worker's error read "API diff failed: ..."."""
    tp_old = write_tree(tmp_path / "tp-1.0", {"tp/__init__.py": "def f(a, b): ...\n"})
    tp_new = write_tree(
        tmp_path / "tp-2.0",
        {"tp/__init__.py": "def f(a): ...\n", "tp/api.py": 'GREETING = t"hello {name}"\n'},
    )
    ok_old = write_tree(tmp_path / "ok-1.0", {"ok/__init__.py": "def g(a, b): ...\n"})
    ok_new = write_tree(tmp_path / "ok-2.0", {"ok/__init__.py": "def g(a): ...\n"})
    pypi = FakePyPI(
        cache,
        {name: [("1.0", "2025-01-10"), ("2.0", "2025-10-01")] for name in ("tp", "ok")},
        {
            ("tp", "1.0"): SourceTree("tp", "1.0", tp_old, ("tp",)),
            ("tp", "2.0"): SourceTree("tp", "2.0", tp_new, ("tp",)),
            ("ok", "1.0"): SourceTree("ok", "1.0", ok_old, ("ok",)),
            ("ok", "2.0"): SourceTree("ok", "2.0", ok_new, ("ok",)),
        },
    )
    engine = make_engine(cache, pypi, scripted)
    project = load_project(
        make_project(tmp_path, '"tp==2.0", "ok==2.0"', "import tp, ok\ntp.f(1)\nok.g(1)\n")
    )
    scan = engine.scan(project, engine.resolve_target())
    tp, ok = scan.package("tp"), scan.package("ok")
    assert (tp.status, tp.unparsed) == (SKIPPED, True)
    assert tp.reason is not None and "run since-cutoff with Python 3.14 or later" in tp.reason
    assert ok.status == CHANGED and [c.parameter for c in ok.changes] == ["b"]


# ----------------------------------------------------- receivers (selection.type_project)
FRAMES_V1 = {
    "frames/__init__.py": "from frames.core import Frame, read_csv\n",
    "frames/core.py": (
        "from __future__ import annotations\n\n\nclass Frame:\n"
        "    def applymap(self, func: object) -> Frame:\n        return self\n\n\n"
        "def read_csv(path: str) -> Frame:\n    return Frame()\n"
    ),
}
FRAMES_V2 = {
    "frames/__init__.py": "from frames.core import Frame, read_csv\n",
    # A line of newer syntax for the Python 3.10 of the test (numpy 2.5's PEP 695 ``type``).
    "frames/__init__.pyi": (
        "# fails: invalid syntax\nPATH = str\n\n"
        "from frames.core import Frame as Frame, read_csv as read_csv\n"
    ),
    "frames/core.py": (
        "from __future__ import annotations\n\n\nclass Frame:\n"
        "    def map(self, func: object) -> Frame:\n        return self\n\n\n"
        "def read_csv(path: str) -> Frame:\n    return Frame()\n"
    ),
}
FRAMES_APP = "import frames as fr\n\ndf = fr.read_csv('a.csv')\ndf.applymap(str)\n"


def _frames(tmp_path: Path, cache: DiskCache) -> tuple[FakePyPI, Path]:
    trees = {
        ("frames", v): SourceTree(
            "frames", v, write_tree(tmp_path / f"frames-{v}", files), ("frames",)
        )
        for v, files in (("1.0", FRAMES_V1), ("2.0", FRAMES_V2))
    }
    pypi = FakePyPI(cache, {"frames": [("1.0", "2025-01-10"), ("2.0", "2025-10-01")]}, trees)
    root = write_tree(
        tmp_path / "app", {"requirements.txt": "frames==2.0\n", "main.py": FRAMES_APP}
    )
    return pypi, root


def test_a_receiver_map_an_older_python_made_is_not_served_to_a_newer_one(
    tmp_path, cache, scripted
) -> None:
    """numpy 2.5.4: a scan on Python 3.10 cached an empty receiver map (its stub did not parse),
    and the same scan on 3.13 with that cache then missed ``x.resize(...)`` on an ndarray."""
    pypi, root = _frames(tmp_path, cache)
    project = load_project(root)
    with pytest.MonkeyPatch.context() as mp:
        older_one = (sys.version_info[0], sys.version_info[1] - 1)  # than the one running
        pretend_python(mp, older_one, fails=())
        engine = make_engine(cache, pypi, scripted)
        older = engine.scan(project, engine.resolve_target())
        assert older.package("frames").status == SKIPPED
    engine = make_engine(cache, pypi, scripted)
    scan = engine.scan(project, engine.resolve_target())
    assert scan.package("frames").status == CHANGED
    assert [u.note.api for u in scan.used_apis()] == ["Frame.applymap"]
