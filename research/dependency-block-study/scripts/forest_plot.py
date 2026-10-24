"""Per-task forest plot of C/A total tokens (Opus 5.5, 25 post-cutoff tasks) -> paper/figures/forest_tasks.pdf.

usage: python forest_plot.py [--data ../analysis/per_task_ratios.json] [--out ../paper/figures/forest_tasks.pdf]
Reads analysis/per_task_ratios.json (scripts/per_task_ratios.py; run it first). One row per task: combined C/A ratio of
geometric means (original tasks: main run and replication, stratified by study; new tasks: one study) with a 95% Welch t
interval over reps; small grey dots = the single-study estimates. Colour + marker shape encode notes coverage (Okabe-Ito
blue filled circle = notes name the task's change, orange open square = they do not), so the figure also reads in
greyscale; a dagger marks the pilot-exposed tasks. Diamonds: geometric mean over tasks with a 95% task bootstrap CI.
Log x axis. Single ACL column (3.03 in), 7 pt text (compact rows since 2026-10-23), vector PDF with embedded TrueType fonts.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FixedLocator, NullLocator  # noqa: E402

BLUE, ORANGE, GREY, BLACK = "#0072B2", "#E69F00", "0.55", "0.15"
HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE.parent / "analysis" / "per_task_ratios.json"))
    ap.add_argument("--out", default=str(HERE.parent / "paper" / "figures" / "forest_tasks.pdf"))
    ap.add_argument("--preview", default=None, help="optional PNG path for a raster preview")
    ap.add_argument("--row", type=float, default=0.098, help="row height in inches (0.125 before 2026-10-23)")
    ap.add_argument("--font", type=float, default=7.0, help="font size in pt (8 before 2026-10-23)")
    args = ap.parse_args()
    d = json.loads(Path(args.data).read_text(encoding="utf-8"))
    tasks = {t: v for t, v in d["tasks"].items() if v["task_set"] in ("original", "new")}

    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                         "font.size": args.font, "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "mathtext.fontset": "stix"})
    rows = []  # (kind, label, payload)
    for tset, title in (("original", "Original tasks (main + replication)"), ("new", "New tasks (one study)")):
        sel = sorted((t for t, v in tasks.items() if v["task_set"] == tset), key=lambda t: tasks[t]["combined"]["gm_ratio"])
        rows.append(("header", title, None))
        rows += [("task", t, tasks[t]) for t in sel]
    rows.append(("header", "Geometric mean over tasks", None))
    for g, lab in (("covered", "Covered"), ("uncovered", "Not covered"), ("all", "All")):
        s = d["summaries"][g]["gm_of_combined_gm_ratio"]
        rows.append(("summary", f"{lab} ({s['tasks']})", s))

    n = len(rows)
    fig, ax = plt.subplots(figsize=(3.03, args.row * n + 0.5))
    ax.set_xscale("log")
    lo_lim, hi_lim = 0.15, 3.3
    ax.axvline(1.0, color="0.35", lw=0.7, ls="--", zorder=1)
    ylabels, yticks = [], []
    for i, (kind, label, p) in enumerate(rows):
        y = n - 1 - i
        if kind == "header":
            ax.text(lo_lim * 1.03, y, label, fontsize=args.font, fontweight="bold", va="center", ha="left")
            continue
        if kind == "task":
            c = p["combined"]
            col, mk, mfc = (BLUE, "o", BLUE) if p["covered"] else (ORANGE, "s", "white")
            lo, hi = c["ci95_welch_t"]
            ax.plot([max(lo, lo_lim), min(hi, hi_lim)], [y, y], color=col, lw=0.9, zorder=2, solid_capstyle="butt")
            for side, v in (("<", lo), (">", hi)):
                if (side == "<" and v < lo_lim) or (side == ">" and v > hi_lim):
                    ax.plot(lo_lim if side == "<" else hi_lim, y, marker=side, ms=2.6, color=col, zorder=2)
            if len(p["per_study"]) > 1:
                for s in p["per_study"].values():
                    ax.plot(s["gm_ratio"], y, "o", ms=1.6, color=GREY, zorder=3)
            ax.plot(c["gm_ratio"], y, mk, ms=3.3, color=col, mfc=mfc, mew=0.9, zorder=4)
            ylabels.append(label + ("$^\\dagger$" if p["pilot_exposed"] else ""))
        else:
            r, lo, hi = p["ratio"], p["lo"], p["hi"]
            ax.fill([lo, r, hi, r], [y, y + 0.32, y, y - 0.32], color=BLACK, lw=0, zorder=4)
            ylabels.append(label)
        yticks.append(y)
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=args.font)
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_xlim(lo_lim, hi_lim)
    ax.xaxis.set_major_locator(FixedLocator([0.25, 0.5, 1, 2]))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels(["0.25", "0.5", "1", "2"])
    ax.tick_params(axis="x", labelsize=8, length=2)
    ax.tick_params(axis="y", length=0, pad=2)
    ax.set_xlabel("C/A total tokens (log scale)", fontsize=args.font, labelpad=2)
    ax.grid(axis="x", color="0.92", lw=0.5, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    handles = [Line2D([], [], marker="o", color=BLUE, mfc=BLUE, ms=3.3, lw=0.9, label="covered"),
               Line2D([], [], marker="s", color=ORANGE, mfc="white", ms=3.3, mew=0.9, lw=0.9, label="not covered"),
               Line2D([], [], marker="o", color=GREY, ms=1.6, lw=0, label="per study")]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.35, 1.0), ncol=3, fontsize=args.font, frameon=False,
              handlelength=1.4, columnspacing=0.8, handletextpad=0.4, borderaxespad=0.1)
    fig.tight_layout(pad=0.2)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="pdf")
    if args.preview:
        fig.savefig(args.preview, dpi=220)
    print("wrote", out.name)


if __name__ == "__main__":
    main()
