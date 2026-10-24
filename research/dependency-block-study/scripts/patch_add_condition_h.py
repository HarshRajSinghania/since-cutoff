"""Add the header-only placebo condition H to the benchmark harness (NAACL addendum, PROTOCOL_ADDENDUM.md).

H = base block + the since-cutoff notes block with every change line removed (marker, meta line, heading, intro
paragraph and the per-package "**pkg X** (Y at the cutoff)" lines are kept). Notes come from a separate frozen
manifest in `paths.notes_header` (default: <notes_dir>-header). Run once from anywhere.
"""
from pathlib import Path

ROOT = Path.home() / "projects" / "since-cutoff-benchmark" / "bench"


def sub(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (path, old[:60])
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


cfgp = ROOT / "config.py"
sub(cfgp, '''    @property
    def notes_dir(self) -> Path:
        return self.p("notes") if "notes" in self.raw["paths"] else BENCH_DIR / "notes"
''', '''    @property
    def notes_dir(self) -> Path:
        return self.p("notes") if "notes" in self.raw["paths"] else BENCH_DIR / "notes"

    @property
    def notes_header_dir(self) -> Path:
        """Header-only notes for the placebo condition H (NAACL addendum)."""
        if "notes_header" in self.raw["paths"]:
            return self.p("notes_header")
        return self.notes_dir.parent / (self.notes_dir.name + "-header")
''')

cp = ROOT / "conditions.py"
sub(cp, '''    forced: bool = False  # E: the CLAUDE.md rule tells the agent to look the API up before writing code
''', '''    forced: bool = False  # E: the CLAUDE.md rule tells the agent to look the API up before writing code
    notes_variant: str = ""  # H: "header" = header-only notes (placebo, NAACL addendum)
''')
sub(cp, '''    "E": Condition("E", context7=True, notes=False, forced=True),
}''', '''    "E": Condition("E", context7=True, notes=False, forced=True),
    # NAACL addendum (PROTOCOL_ADDENDUM.md): header-only notes, every change line removed (placebo for C)
    "H": Condition("H", context7=False, notes=True, notes_variant="header"),
}''')
sub(cp, '''def claude_md(cfg: Config, task: Task, cond: Condition, manifest: dict[str, Any] | None) -> str:
    notes = notes_for(cfg, task, manifest) if cond.notes else None
''', '''def header_manifest(cfg: Config) -> dict[str, Any] | None:
    path = cfg.notes_header_dir / "MANIFEST.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def claude_md(cfg: Config, task: Task, cond: Condition, manifest: dict[str, Any] | None) -> str:
    if cond.notes_variant == "header":
        notes = notes_for(cfg, task, header_manifest(cfg), notes_dir=cfg.notes_header_dir)
    else:
        notes = notes_for(cfg, task, manifest) if cond.notes else None
''')
sub(cp, '''def notes_for(cfg: Config, task: Task, manifest: dict[str, Any] | None, *, require_frozen: bool = True) -> str:''',
    '''def notes_for(cfg: Config, task: Task, manifest: dict[str, Any] | None, *, require_frozen: bool = True,
              notes_dir: Path | None = None) -> str:''')
sub(cp, '''    path = cfg.notes_dir / entry["file"]
    data = path.read_bytes() if path.exists() else b""''', '''    path = (notes_dir or cfg.notes_dir) / entry["file"]
    data = path.read_bytes() if path.exists() else b""''')
sub(cp, '''    notes_entry = ((manifest or {}).get("tasks") or {}).get(task.key) if cond.notes else None
    return {''', '''    if cond.notes_variant == "header":
        manifest = header_manifest(cfg)
    notes_entry = ((manifest or {}).get("tasks") or {}).get(task.key) if cond.notes else None
    return {''')
print("patched")
