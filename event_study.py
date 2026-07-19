"""
event_study.py — parallel-trends / event-study robustness (CLAUDE.md sec. 5).

Pitch Clock x Reliever Fatigue analysis.

Instead of a single Post x ConsecutiveDay term, interact `consec_day` with each
SEASON, using 2022 (the last pre-clock season) as the reference/omitted year:

    y ~ consec_day + consec_day:1[2021] + consec_day:1[2023] + consec_day:1[2024]
        | pitcher_id + season      (SE clustered on pitcher_id)

Reading the coefficients (each = the consec-day gap in that year MINUS the 2022 gap):
    - 2021  -> PRE-TREND TEST. Should be ~0 / insignificant if parallel trends hold.
    - 2023  -> post-clock effect, year 1.
    - 2024  -> post-clock effect, year 2.
    (The base `consec_day` term = the consec-day gap in the 2022 reference year.)

Uses the (a) back-to-back coding (primary). Outputs results/event_study.csv.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pyfixest as pf

DATA_DIR = Path(__file__).parent / "data"
RESULTS_DIR = Path(__file__).parent / "results"
PANEL_PATH = DATA_DIR / "panel.parquet"

OUTCOMES = ["release_speed", "pfx_x", "pfx_z", "xBAA"]
REF_YEAR = 2022                      # omitted reference (last pre-clock season)
EVENT_YEARS = [2021, 2023, 2024]     # coefficients estimated relative to REF_YEAR

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("event_study")


def _scalar(s, key):
    return float(s.loc[key]) if hasattr(s, "loc") else float(s)


def build_interactions(panel: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Add consec_day x 1[season==year] columns for each non-reference year."""
    panel = panel.copy()
    terms = []
    for yr in EVENT_YEARS:
        col = f"consec_x_{yr}"
        panel[col] = panel["consec_day"] * (panel["season"] == yr).astype(int)
        terms.append(col)
    return panel, terms


def run_event_study(panel: pd.DataFrame, y: str, terms: list[str]):
    usable = panel.dropna(subset=[y, "consec_day", "season", "pitcher_id"])
    if usable[y].notna().sum() == 0:
        log.warning("outcome '%s' has no usable values — skipped", y)
        return []
    rhs = " + ".join(["consec_day"] + terms)
    log.info("event study for '%s' on %d appearances (ref year %d)", y, len(usable), REF_YEAR)
    model = pf.feols(
        f"{y} ~ {rhs} | pitcher_id + season",
        data=usable,
        vcov={"CRV1": "pitcher_id"},
    )
    model.summary()

    rows = []
    # base term = reference-year (2022) consec-day gap
    label_map = {"consec_day": REF_YEAR}
    label_map.update({f"consec_x_{yr}": yr for yr in EVENT_YEARS})
    for term, yr in label_map.items():
        rows.append({
            "outcome": y,
            "year": yr,
            "relative_to_ref": (yr - REF_YEAR),
            "is_reference": (yr == REF_YEAR),
            "is_pretrend_test": (yr < REF_YEAR),
            "coef": _scalar(model.coef(), term),
            "se": _scalar(model.se(), term),
            "p_value": _scalar(model.pvalue(), term),
        })
    return rows


def main() -> None:
    if not PANEL_PATH.exists():
        raise SystemExit(f"missing {PANEL_PATH} — run build_panel.py first")
    panel = pd.read_parquet(PANEL_PATH)
    log.info("panel: %d appearances, seasons %s", len(panel), sorted(panel["season"].unique()))

    panel, terms = build_interactions(panel)

    all_rows = []
    for y in OUTCOMES:
        if y not in panel.columns:
            log.warning("outcome '%s' not in panel — skipped", y)
            continue
        all_rows.extend(run_event_study(panel, y, terms))

    if not all_rows:
        raise SystemExit("no event-study estimates produced")

    df = pd.DataFrame(all_rows)
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "event_study.csv"
    df.to_csv(out, index=False)
    log.info("wrote %s", out)

    # readable summary, highlighting the 2021 pre-trend test
    print("\n=== EVENT STUDY (consec_day gap by year, ref = 2022) ===")
    show = df.copy()
    show["coef"] = show["coef"].round(4)
    show["se"] = show["se"].round(4)
    show["p_value"] = show["p_value"].round(3)
    print(show[["outcome", "year", "coef", "se", "p_value", "is_pretrend_test"]].to_string(index=False))
    pre = df[df["is_pretrend_test"]]
    bad = pre[pre["p_value"] < 0.05]
    print("\nPre-trend test (2021 vs 2022 reference):")
    if len(bad) == 0:
        print("  PASS — no outcome shows a significant 2021 pre-trend (all p >= 0.05).")
    else:
        print("  FLAG — significant 2021 pre-trend for:", bad["outcome"].tolist())


if __name__ == "__main__":
    main()
