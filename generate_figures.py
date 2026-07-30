"""
Generate research figures from the DID / event-study results.
Reads: results/did_results.csv, results/did_results_intensity.csv,
       results/event_study.csv, data/panel.parquet
Writes: results/figures/*.png (300 dpi, static, for paper/slides)
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

FIG_DIR = Path("results/figures")
FIG_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.edgecolor": "#c3c2b7",
    "axes.labelcolor": "#0b0b0b",
    "text.color": "#0b0b0b",
    "xtick.color": "#52514e",
    "ytick.color": "#52514e",
    "axes.grid": True,
    "grid.color": "#e1e0d9",
    "grid.linewidth": 0.6,
    "figure.facecolor": "#fcfcfb",
    "axes.facecolor": "#fcfcfb",
    "savefig.facecolor": "#fcfcfb",
})

# fixed categorical color per outcome (order = palette slot order)
OUTCOME_COLOR = {
    "release_speed": "#2a78d6",   # blue
    "pfx_x":         "#1baf7a",   # aqua
    "pfx_z":         "#eda100",   # yellow
    "xBAA":          "#4a3aa7",   # violet
}
OUTCOME_LABEL = {
    "release_speed": "Release velocity (mph)",
    "pfx_x": "Horizontal movement (ft)",
    "pfx_z": "Vertical movement (ft)",
    "xBAA": "xBAA",
}
OUTCOME_ORDER = ["release_speed", "pfx_x", "pfx_z", "xBAA"]
Z95 = 1.96

# ---------------------------------------------------------------- #
# Fig 1/2: coefficient (dot-whisker) plots for beta3, each spec
# ---------------------------------------------------------------- #
def coef_plot(csv_path, title, out_name):
    df = pd.read_csv(csv_path).set_index("outcome").loc[OUTCOME_ORDER]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ypos = range(len(df))[::-1]
    for y, outcome in zip(ypos, OUTCOME_ORDER):
        row = df.loc[outcome]
        color = OUTCOME_COLOR[outcome]
        lo, hi = row.beta3 - Z95 * row.se, row.beta3 + Z95 * row.se
        ax.plot([lo, hi], [y, y], color=color, lw=2, solid_capstyle="round")
        ax.plot(row.beta3, y, "o", color=color, ms=8, zorder=3,
                 markeredgecolor="#fcfcfb", markeredgewidth=1.2)
        sig = "" if row.p_value >= 0.10 else ("*" if row.p_value >= 0.05 else "**")
        ax.annotate(f"{row.beta3:+.3f}{sig}  (p={row.p_value:.2f})",
                    xy=(hi, y), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=9.5, color="#52514e")
    ax.axvline(0, color="#898781", lw=1, zorder=1)
    ax.set_yticks(list(ypos))
    ax.set_yticklabels([OUTCOME_LABEL[o] for o in OUTCOME_ORDER])
    ax.set_xlabel(r"$\beta_3$ (Post $\times$ ConsecutiveDay), 95% CI")
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", wrap=True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(left=False)
    xmin, xmax = ax.get_xlim()
    ax.set_xlim(xmin, xmax + 0.35 * (xmax - xmin))  # room for annotation text
    fig.tight_layout()
    fig.savefig(FIG_DIR / out_name, dpi=300)
    plt.close(fig)
    print(f"wrote {FIG_DIR / out_name}")

coef_plot("results/did_results.csv",
          "Pitch clock × consecutive-day fatigue: back-to-back spec (a)",
          "fig1_coef_beta3_primary.png")
coef_plot("results/did_results_intensity.csv",
          "Pitch clock × consecutive-day fatigue: 3-day intensity spec (b, robustness)",
          "fig2_coef_beta3_intensity.png")

# ---------------------------------------------------------------- #
# Fig 3: event study, small multiples, 2021 (pre) / 2022 (ref) / 2023 / 2024
# ---------------------------------------------------------------- #
es = pd.read_csv("results/event_study.csv")
# NOTE: the "consec_day" base term (is_reference row) is the RAW 2022-level
# consec-day gap, not a zero-by-construction omitted-category coefficient --
# the other years' coefficients are already differences from that base
# (coef_year = gap_year - gap_2022). For the event-study plot the reference
# year is therefore normalized to 0 (no CI, it's a fixed point), and the
# other years are plotted as their (already-relative) coefficients directly.
fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True)
for ax, outcome in zip(axes.flat, OUTCOME_ORDER):
    d = es[es.outcome == outcome].sort_values("year").copy()
    d.loc[d.is_reference, ["coef", "se"]] = 0.0
    color = OUTCOME_COLOR[outcome]
    lo = d.coef - Z95 * d.se
    hi = d.coef + Z95 * d.se
    non_ref = ~d.is_reference
    ax.fill_between(d.year[non_ref], lo[non_ref], hi[non_ref], color=color, alpha=0.15, linewidth=0)
    ax.plot(d.year, d.coef, "-o", color=color, ms=6, lw=2)
    ref = d[d.is_reference]
    ax.plot(ref.year, ref.coef, "o", color="#898781", ms=7, zorder=4)
    ax.axhline(0, color="#898781", lw=1)
    ax.axvline(2022.5, color="#c3c2b7", lw=1, ls="--")
    ax.set_title(OUTCOME_LABEL[outcome], loc="left", fontsize=11, fontweight="bold")
    ax.set_xticks(d.year)
    ax.spines[["top", "right"]].set_visible(False)
ax.set_xlabel = None
fig.text(0.5, 0.965, "Event study: consecutive-day fatigue effect by season (ref. = 2022)",
          ha="center", fontsize=13, fontweight="bold")
fig.text(0.5, 0.005,
          "Dashed line = pitch-clock introduction (2023). Gray dot = reference year (2022, normalized to 0). "
          "Other points = consec-day gap relative to 2022. Shaded band = 95% CI.",
          ha="center", fontsize=9, color="#52514e")
fig.tight_layout(rect=[0, 0.02, 1, 0.95])
fig.savefig(FIG_DIR / "fig3_event_study.png", dpi=300)
plt.close(fig)
print(f"wrote {FIG_DIR / 'fig3_event_study.png'}")

# ---------------------------------------------------------------- #
# Fig 4: descriptive raw trends -- mean outcome by season x consec_day
# ---------------------------------------------------------------- #
panel = pd.read_parquet("data/panel.parquet")
fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True)
for ax, outcome in zip(axes.flat, OUTCOME_ORDER):
    g = panel.groupby(["season", "consec_day"])[outcome].mean().reset_index()
    for cd, label, ls in [(0, "Not consecutive day", "-"), (1, "Consecutive day (b2b)", "--")]:
        sub = g[g.consec_day == cd].sort_values("season")
        color = OUTCOME_COLOR[outcome] if cd == 1 else "#898781"
        ax.plot(sub.season, sub[outcome], ls, marker="o", ms=6, lw=2,
                 color=color, label=label)
    ax.axvline(2022.5, color="#c3c2b7", lw=1, ls=":")
    ax.set_title(OUTCOME_LABEL[outcome], loc="left", fontsize=11, fontweight="bold")
    ax.set_xticks(sorted(panel.season.unique()))
    ax.spines[["top", "right"]].set_visible(False)
handles, labels = axes.flat[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper right", frameon=False, fontsize=9,
           bbox_to_anchor=(0.98, 0.98))
fig.text(0.5, 0.965, "Raw appearance-level means by season: consecutive-day vs. not",
          ha="center", fontsize=13, fontweight="bold")
fig.text(0.5, 0.005, "Dotted line = pitch-clock introduction (2023). Descriptive only (no FE/covariates).",
          ha="center", fontsize=9, color="#52514e")
fig.tight_layout(rect=[0, 0.02, 1, 0.95])
fig.savefig(FIG_DIR / "fig4_raw_trends.png", dpi=300)
plt.close(fig)
print(f"wrote {FIG_DIR / 'fig4_raw_trends.png'}")

print("done.")
