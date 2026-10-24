"""Build the paper's figure(s) from the aggregated analysis JSON.

Usage (from the paper folder):  python make_figures.py [--analysis ../analysis] [--out figures]

Figure 2, Appendix D (figures/ratios.pdf): treatment/control ratios (geometric mean over the
post-cutoff tasks (17 per original study, 8 for the new tasks) of per-task median ratios, 95% task-cluster bootstrap CI)
for total tokens and list-price cost, per study. Filled markers: notes vs.
agent alone (C/A). Open markers: header-only control vs. agent alone (H/A).

Colours are from the Okabe-Ito palette (colour-blind safe); markers differ in
shape and fill as well, so the figure also reads in greyscale.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

STUDIES = [
    # (label, file)
    ("Opus, main", "main_ratios_recomputed.json"),
    ("Opus, repl.", "opus_abl_ratios.json"),
    ("Sonnet 5.5", "sonnet_ratios.json"),
    ("Haiku 5.5", "haiku_ratios.json"),
    ("Opus, new tasks", "tasks2_ratios.json"),
]
METRICS = [("total_tokens", "Total tokens"), ("list_cost_usd", "Cost (list price)")]
BLUE, ORANGE = "#0072B2", "#E69F00"


def load(analysis: Path):
    rows = []
    for label, fname in STUDIES:
        d = json.loads((analysis / fname).read_text(encoding="utf-8"))
        post = d["ratios"]["post-cutoff"]
        rows.append((label, post.get("C/A"), post.get("H/A")))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", default=str(Path(__file__).resolve().parent.parent / "analysis"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "figures"))
    args = ap.parse_args()
    rows = load(Path(args.analysis))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "font.size": 8,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "pdf.fonttype": 42,
    })
    fig, axes = plt.subplots(1, 2, figsize=(3.0, 2.55), sharey=True)
    n = len(rows)
    for ax, (key, title) in zip(axes, METRICS):
        ax.set_axisbelow(True)
        ax.axvline(1.0, color="0.35", lw=0.8, ls="--", zorder=2)
        for i, (label, ca, ha) in enumerate(rows):
            y = n - 1 - i
            if ca is not None:
                r = ca[key]
                ax.errorbar(r["ratio"], y + 0.13, xerr=[[r["ratio"] - r["lo"]], [r["hi"] - r["ratio"]]],
                            fmt="o", ms=3.4, color=BLUE, mfc=BLUE, lw=0.9, capsize=1.5)
            if ha is not None:
                r = ha[key]
                ax.errorbar(r["ratio"], y - 0.17, xerr=[[r["ratio"] - r["lo"]], [r["hi"] - r["ratio"]]],
                            fmt="s", ms=3.0, color=ORANGE, mfc="white", mew=0.9, lw=0.9, capsize=1.5)
        ax.set_title(title, fontsize=8, pad=3)
        ax.set_xlim(0.55, 1.4)
        ax.set_xticks([0.6, 0.8, 1.0, 1.2])
        ax.tick_params(axis="both", labelsize=8, length=2)
        ax.grid(axis="x", color="0.92", lw=0.5, zorder=0)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_yticks(range(n))
    axes[0].set_yticklabels([r[0] for r in rows][::-1])
    axes[0].set_ylim(-0.6, n - 0.4)
    fig.supxlabel("ratio to agent alone (A); < 1 is cheaper", fontsize=8, y=0.02)
    handles = [
        plt.Line2D([], [], marker="o", ls="", color=BLUE, ms=3.4, label="notes (C/A)"),
        plt.Line2D([], [], marker="s", ls="", color=ORANGE, mfc="white", ms=3.0, label="header only (H/A)"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False, fontsize=8,
               bbox_to_anchor=(0.58, 1.02), handletextpad=0.2, columnspacing=1.0)
    fig.subplots_adjust(left=0.27, right=0.98, top=0.82, bottom=0.2, wspace=0.16)
    fig.savefig(out / "ratios.pdf")
    print("wrote", out / "ratios.pdf")
    breakeven2d(Path(args.analysis), out)


def breakeven2d(analysis: Path, out: Path) -> None:
    """Figure, Appendix D (figures/breakeven2d.pdf). Round 22: one unit (model calls) and a matched base. Break-even
    share f* of agent contexts against the block's effect u on the other contexts, at the contexts' mean length
    (45.3 model calls) with K measured from their logged usage (analysis/breakeven2d_contexts.json, from
    scripts/breakeven2d_contexts.py). Dotted vertical: u = 0. Dashed horizontal: one author's f_strict and f_upper over
    all agent contexts (the same base). The control-task 95% range of u (-3.6% to +15.6%) covers the whole axis, which
    the caption states instead of shading. Earlier versions (rounds 13-21) drew benchmark-length curves (16.6 CLI
    turns, K = $0.17) against a Python-editing f; those are retired."""
    d = json.loads((analysis / "breakeven2d_contexts.json").read_text(encoding="utf-8"))
    fm = d["f_measured_all_contexts"]
    curves = [  # (curve key, label, colour, line style)
        ("main|G_median_nonempty", "704 tokens, main saving", BLUE, "-"),
        ("main|AI_median_nonempty", "1,025 tokens, main saving", "#D55E00", "--"),
        ("new_tasks|AI_mean_nonempty", "1,320 tokens, new-task saving", ORANGE, ":"),
    ]
    fig, ax = plt.subplots(figsize=(3.0, 2.1))
    ax.axvline(0, color="0.35", lw=0.6, ls=(0, (1, 1)), zorder=1)
    for f, lab in ((fm["upper"], r"$f_{\mathrm{upper}}$"), (fm["strict"], r"$f_{\mathrm{strict}}$")):
        ax.axhline(100 * f, color="0.35", lw=0.7, ls="--", zorder=1)
        ax.text(-1.97, 100 * f + 1.0, lab, ha="left", va="bottom", fontsize=8, color="0.25")
    for key, label, colour, ls in curves:
        pts = d["curves"][key]["contexts"]["f_star_curve"]
        ax.plot([100 * u for u, _ in pts], [100 * f for _, f in pts], color=colour, ls=ls, lw=1.4, label=label,
                zorder=3)
    ax.set_xlim(-2, 1)
    ax.set_ylim(0, 100)
    ax.set_xlabel("$u$: saving on other contexts (%; < 0 more expensive)", fontsize=8)
    ax.set_ylabel("break-even $f^{*}$ (% of contexts)", fontsize=8)
    ax.tick_params(axis="both", labelsize=8, length=2)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 1.0), frameon=False, fontsize=7, handlelength=2.2,
              borderaxespad=0.2)
    fig.subplots_adjust(left=0.15, right=0.98, top=0.97, bottom=0.2)
    fig.savefig(out / "breakeven2d.pdf")
    print("wrote", out / "breakeven2d.pdf")


if __name__ == "__main__":
    main()
