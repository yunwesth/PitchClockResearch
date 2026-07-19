"""
run_did.py — the difference-in-differences regression (CONFIRMED spec).

Pitch Clock x Reliever Fatigue analysis. See CLAUDE.md section 4.

Main model (do NOT change — confirmed specification):

    y ~ consec_day + post:consec_day | pitcher_id + season

    - post:consec_day  == beta3  <- THE core estimand
    - | pitcher_id + season      == two-way fixed effects (gamma_i, delta_t)
    - post main effect is absorbed by season FE, so it is NOT included
    - vcov CRV1 on pitcher_id    == pitcher-level clustered SE

Robustness (Daniel: (a) primary + (b) robustness): the same model re-run with the
(b) intensity coding `consec_intensity_3` in place of `consec_day`.

Outputs:
    results/did_results.csv                 — main spec, (a) back-to-back
    results/did_results_intensity.csv       — robustness, (b) intensity
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pyfixest as pf

DATA_DIR = Path(__file__).parent / "data"
RESULTS_DIR = Path(__file__).parent / "results"
PANEL_PATH = DATA_DIR / "panel.parquet"

# All 4 outcomes now confirmed (xBAA aggregation decided: spec rule, min 3 AB).
OUTCOMES = ["release_speed", "pfx_x", "pfx_z", "xBAA"]

# (consec variable, output filename, human label)
SPECS = [
    ("consec_day", "did_results.csv", "main / (a) back-to-back"),
    ("consec_intensity_3", "did_results_intensity.csv", "robustness / (b) intensity N=3"),
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("run_did")


def _scalar(series_or_val, key):
    """pyfixest accessors return a pandas Series keyed by term; pull the term."""
    if hasattr(series_or_val, "loc"):
        return float(series_or_val.loc[key])
    return float(series_or_val)


def run_one(panel: pd.DataFrame, y: str, consec: str):
    """Fit the DID model for a single outcome + consec coding; return dict/None."""
    term = f"post:{consec}"
    usable = panel.dropna(subset=[y, consec, "post", "pitcher_id", "season"])
    if usable[y].notna().sum() == 0:
        log.warning("outcome '%s' has no usable (non-NaN) values — skipped", y)
        return None
    if usable[consec].nunique() < 2:
        log.warning("'%s': %s has no variation in sample — skipped", y, consec)
        return None

    log.info("fitting DID for '%s' ~ %s on %d appearances", y, consec, len(usable))
    model = pf.feols(
        f"{y} ~ {consec} + post:{consec} | pitcher_id + season",
        data=usable,
        vcov={"CRV1": "pitcher_id"},
    )
    model.summary()

    for m in ("coef", "se", "tstat", "pvalue"):
        if not hasattr(model, m):
            raise AttributeError(
                f"pyfixest model has no .{m}() — check installed version and adapt run_did.py"
            )

    beta3 = _scalar(model.coef(), term)
    se = _scalar(model.se(), term)
    # Standardized (SD-unit) effect: z-scoring the dependent variable is a linear
    # rescale, so beta3_sd = beta3 / SD(y) and se_sd = se / SD(y); the t-stat and
    # p-value are UNCHANGED. beta3_sd is comparable across outcomes (in SDs of y).
    sd_y = float(usable[y].std(ddof=1))
    return {
        "outcome": y,
        "consec_coding": consec,
        "n_appearances": len(usable),
        "beta3": beta3,
        "se": se,
        "t": _scalar(model.tstat(), term),
        "p_value": _scalar(model.pvalue(), term),
        "sd_y": sd_y,
        "beta3_sd": beta3 / sd_y,
        "se_sd": se / sd_y,
    }


def run_spec(panel: pd.DataFrame, consec: str, out_name: str, label: str) -> None:
    if consec not in panel.columns:
        log.warning("spec '%s': column %s not in panel — skipped", label, consec)
        return
    log.info("===== spec: %s =====", label)
    rows = []
    for y in OUTCOMES:
        if y not in panel.columns:
            log.warning("outcome '%s' not in panel columns — skipped", y)
            continue
        res = run_one(panel, y, consec)
        if res is not None:
            rows.append(res)
    if not rows:
        log.warning("spec '%s': no outcomes estimated", label)
        return
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / out_name
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    log.info("wrote %s", out)
    print(f"\n--- {label} ---")
    print(df.to_string(index=False))


def main() -> None:
    if not PANEL_PATH.exists():
        raise SystemExit(f"missing {PANEL_PATH} — run build_panel.py first")
    panel = pd.read_parquet(PANEL_PATH)
    log.info("panel: %d appearances, %d pitchers", len(panel), panel["pitcher_id"].nunique())

    for consec, out_name, label in SPECS:
        run_spec(panel, consec, out_name, label)


if __name__ == "__main__":
    main()
