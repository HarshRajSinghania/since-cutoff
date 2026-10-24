"""Summarise `since-cutoff scan --json` outputs for many models into a table and a chart.

Usage: python stack_report.py SCANS_DIR [OUT_DIR] [--label TEXT]

SCANS_DIR holds one `<model>.json` per model, made with
`since-cutoff scan --model <provider:model> --json > SCANS_DIR/<model>.json` in this directory.
Writes stack.json, stack.md, ai-stack.svg and ai-stack-dark.svg to OUT_DIR (default: SCANS_DIR).
The chart's footer names the since-cutoff version and the margin the scans record; `--label`
replaces the version part (for scans made with an unreleased checkout).

Breaks and deprecations count the public changes only (since-cutoff 0.6 gives each change a
`tier`, and the scan's own counts leave the internal ones apart); stack.json also has the
counts over every change (`with_breaking_any_tier`), which is what scans made before 0.6 give.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from packaging.version import Version

HARD = {
    "removed", "moved", "param_removed", "param_required", "param_keyword_only",
    "param_positional_only", "kind_changed",
}  # fmt: skip
VENDOR = {
    "gpt": "OpenAI", "o3": "OpenAI", "claude": "Anthropic", "gemini": "Google",
    "grok": "xAI", "deepseek": "DeepSeek", "qwen": "Qwen", "kimi": "Moonshot",
    "devstral": "Mistral", "mistral": "Mistral",
}  # fmt: skip
COLORS = {
    "OpenAI": "#10a37f", "Anthropic": "#c15f3c", "Google": "#4285f4", "xAI": "#555555",
    "DeepSeek": "#4d6bfe", "Qwen": "#6f42c1", "Moonshot": "#b8860b", "Mistral": "#fa520f",
}  # fmt: skip


def vendor(model: str) -> str:
    return next((v for k, v in VENDOR.items() if model.startswith(k)), "Other")


def major(v: str) -> int:
    return Version(v).release[0]


def public(changes: list[dict]) -> list[dict]:
    """The changes to public APIs (a scan made before 0.6 has no `tier`: all of them)."""
    return [c for c in changes if c.get("tier", "public") == "public"]


def row(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    deps = d["scan"]
    seen = [r for r in deps if r.get("cutoff_version")]
    settings = d.get("settings") or {}

    def libraries_with(kinds: set[str], every_tier: bool = False) -> int:
        return sum(
            1
            for r in deps
            if any(
                c["kind"] in kinds
                for c in (r.get("changes") or [] if every_tier else public(r.get("changes") or []))
            )
        )

    model = d["model"].split("/")[-1]  # `google/gemini-2.5-pro` from openrouter's listing
    return {
        "model": model,
        "vendor": vendor(model),
        "cutoff": d["cutoff"],
        "compare_from": d.get("compare_from", d["cutoff"]),
        "cutoff_margin": settings.get("cutoff_margin", 0),
        "tool_version": settings.get("tool_version") or (d.get("tool") or "?").split()[-1],
        "libraries": len(deps),
        "did_not_exist": len(deps) - len(seen),
        "released_since": sum(1 for r in deps if r.get("cutoff_version") != r.get("locked")),
        "new_major": sum(1 for r in seen if major(r["cutoff_version"]) != major(r["locked"])),
        "with_breaking": libraries_with(HARD),
        "with_deprecations": libraries_with({"deprecated"}),
        "with_breaking_any_tier": libraries_with(HARD, every_tier=True),
        "with_deprecations_any_tier": libraries_with({"deprecated"}, every_tier=True),
        "new_majors": sorted(
            r["name"] for r in seen if major(r["cutoff_version"]) != major(r["locked"])
        ),
    }


def markdown(rows: list[dict]) -> str:
    n = rows[0]["libraries"]
    out = [
        f"| model | vendor | training cutoff | compared from releases up to | "
        f"new release since (of {n}) | did not exist yet | new major version | "
        "public API breaks | new deprecations |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['model']} | {r['vendor']} | {r['cutoff']} | {r['compare_from']} | "
            f"{r['released_since']} | {r['did_not_exist']} | {r['new_major']} | "
            f"{r['with_breaking']} | {r['with_deprecations']} |"
        )
    return "\n".join(out) + "\n"


def margin(rows: list[dict]) -> int | None:
    """The cutoff margin of the scans, when they all have the same."""
    margins = {r["cutoff_margin"] for r in rows}
    return margins.pop() if len(margins) == 1 else None


def since(rows: list[dict], short: bool = False) -> str:
    """What the counts start from: ``since 30 days before each model's training cutoff`` (a
    change made within the margin came before the cutoff), or ``after each model's ...``;
    ``short`` for the chart's subtitle, ``since 30 days before each cutoff``."""
    m = margin(rows)
    if m:
        return f"since {m} days before each " + ("cutoff" if short else "model's training cutoff")
    return "after each model's training cutoff"


def footer(rows: list[dict], label: str | None = None) -> str:
    """``static API diff, since-cutoff 0.6.0, compared from 30 days before each cutoff``."""
    tool = label or f"since-cutoff {rows[0]['tool_version']}"
    m = margin(rows)
    if m:
        return f"static API diff, {tool}, compared from {m} days before each cutoff"
    return f"static API diff, {tool}"


def svg(rows: list[dict], dark: bool = False, label: str | None = None) -> str:
    """One row per model (oldest cutoff first): bars out of the n libraries."""
    n = rows[0]["libraries"]
    W, L, R, T, ROW = 940, 250, 70, 92, 21
    H = T + ROW * len(rows) + 80
    bg, fg, sub, grid, track = (
        ("#0d1117", "#e6edf3", "#9198a1", "#21262d", "#161b22")
        if dark
        else ("#ffffff", "#1f2328", "#59636e", "#eaeef2", "#f6f8fa")
    )
    red, blue = ("#f85149", "#4493f8") if dark else ("#cf222e", "#0969da")
    span = W - L - R

    def bx(v: float) -> float:
        return L + span * v / n

    o = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        'role="img" aria-labelledby="t d" font-family="-apple-system,BlinkMacSystemFont,'
        'Segoe UI,Helvetica,Arial,sans-serif">',
        '<title id="t">What your model hasn\'t seen: the Python AI stack after each training cutoff</title>',
        f'<desc id="d">For {len(rows)} models from 8 vendors, how many of {n} widely used '
        f"Python AI libraries broke their public API or shipped a new major version {since(rows)}."
        "</desc>",
        f'<rect width="{W}" height="{H}" fill="{bg}"/>',
        f'<text x="24" y="34" font-size="20" font-weight="650" fill="{fg}">'
        "What your model hasn't seen</text>",
        f'<text x="24" y="58" font-size="13.5" fill="{sub}">Of {n} widely used Python AI/LLM '
        f"libraries (September 2026 versions), how many changed {since(rows, short=True)}</text>",
    ]
    for v in range(0, n + 1, 6):
        o.append(
            f'<line x1="{bx(v):.1f}" x2="{bx(v):.1f}" y1="{T - 8}" y2="{T + ROW * len(rows)}" stroke="{grid}"/>'
        )
        o.append(
            f'<text x="{bx(v):.1f}" y="{T - 13}" font-size="10.5" fill="{sub}" text-anchor="middle">{v}</text>'
        )
    for i, r in enumerate(rows):
        y = T + i * ROW
        mid = y + ROW / 2
        month = date.fromisoformat(r["cutoff"]).strftime("%b %Y")
        color = COLORS.get(r["vendor"], sub)
        o.append(f'<circle cx="{L - 226}" cy="{mid:.1f}" r="4" fill="{color}"/>')
        o.append(
            f'<text x="{L - 216}" y="{mid + 4:.1f}" font-size="12.5" fill="{fg}">{r["model"]}</text>'
        )
        o.append(
            f'<text x="{L - 10}" y="{mid + 4:.1f}" font-size="11.5" fill="{sub}" text-anchor="end">{month}</text>'
        )
        # Two separate bars: a new major version is not necessarily among the flagged breaks.
        o.append(
            f'<rect x="{L}" y="{y + 2}" width="{span:.1f}" height="{ROW - 4}" rx="3" fill="{track}"/>'
        )
        o.append(
            f'<rect x="{L}" y="{y + 3}" width="{bx(r["with_breaking"]) - L:.1f}" height="8" rx="2" fill="{red}"/>'
        )
        o.append(
            f'<rect x="{L}" y="{y + 12}" width="{bx(r["new_major"]) - L:.1f}" height="6" rx="2" fill="{blue}"/>'
        )
        extra = (
            f' <tspan fill="{sub}">· {r["did_not_exist"]} did not exist yet</tspan>'
            if r["did_not_exist"]
            else ""
        )
        o.append(
            f'<text x="{bx(r["with_breaking"]) + 6:.1f}" y="{mid + 4:.1f}" font-size="11.5" fill="{fg}">'
            f'<tspan fill="{red}" font-weight="600">{r["with_breaking"]}</tspan> '
            f'<tspan fill="{blue}">{r["new_major"]}</tspan>{extra}</text>'
        )
    ly = T + ROW * len(rows) + 30
    o += [
        f'<rect x="{L}" y="{ly - 10}" width="14" height="8" rx="2" fill="{red}"/>',
        f'<text x="{L + 20}" y="{ly}" font-size="12" fill="{fg}">libraries whose public API broke (names or parameters removed or changed)</text>',
        f'<rect x="{L}" y="{ly + 8}" width="14" height="6" rx="2" fill="{blue}"/>',
        f'<text x="{L + 20}" y="{ly + 16}" font-size="12" fill="{fg}">libraries now on a new major version</text>',
        f'<text x="{W - 24}" y="{ly + 32}" font-size="11" fill="{sub}" text-anchor="end">{footer(rows, label)}</text>',
        "</svg>",
    ]
    return "\n".join(o)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scans", type=Path)
    parser.add_argument("out", type=Path, nargs="?")
    parser.add_argument("--label", help="the tool in the chart's footer, e.g. 'since-cutoff 0.6'")
    args = parser.parse_args()
    out = args.out or args.scans
    scans = [p for p in args.scans.glob("*.json") if p.name != "stack.json"]  # a previous run's
    rows = sorted((row(p) for p in scans), key=lambda r: (r["cutoff"], r["model"]))
    outputs = {
        "stack.json": json.dumps(rows, indent=1),
        "stack.md": markdown(rows),
        "ai-stack.svg": svg(rows, label=args.label),
        "ai-stack-dark.svg": svg(rows, dark=True, label=args.label),
    }
    for name, text in outputs.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    print(markdown(rows))


if __name__ == "__main__":
    main()
