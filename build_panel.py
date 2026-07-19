"""
build_panel.py — Steps 2, 4, 5, 6, 7: raw Statcast -> appearance-level panel.

Pitch Clock x Reliever Fatigue analysis. See CLAUDE.md for the full spec.

Pipeline:
    Step 2  fetch each (pitcher, season) via pybaseball.statcast_pitcher, CACHED,
            skip combos already downloaded.
    Step 4  keep four-seam fastballs ONLY -> pitch_type == "FF" (Daniel's decision;
            narrows the spec's FF/SI/FT; SI/FT/FC excluded). Applies to the
            velocity/movement outcomes only — xBAA uses all at-bats (see below).
    Step 5  aggregate to one row per (pitcher, game_date) = one appearance.
            CONFIRMED: observation unit = appearance-level.
    Step 6  post = (season >= 2023);
            consec_day       = (a) back-to-back indicator      [CONFIRMED primary]
            consec_intensity = (b) # appearances in trailing N days [robustness]
    Step 7  outcomes: release_speed / pfx_x / pfx_z (four-seam means) + xBAA.

All baseball data comes from `pybaseball`. Statcast is cached to avoid re-download.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from pybaseball import cache, statcast_pitcher

cache.enable()  # re-run safe: pybaseball caches raw HTTP pulls

# --- config -----------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
RAW_PATH = DATA_DIR / "statcast_raw.parquet"
PANEL_PATH = DATA_DIR / "panel.parquet"
ROSTER_PATH = DATA_DIR / "reliever_roster.parquet"

FOURSEAM = ["FF"]  # NOTE: four-seam-only per Daniel; SI/FT/FC excluded.
POST_SEASON_START = 2023  # pitch clock introduced 2023

# ConsecutiveDay (b) intensity robustness window (CLAUDE.md Step 6).
# Daniel: (a) primary + (b) robustness. N defaulted to 3 — change here if needed.
INTENSITY_WINDOW_DAYS = 3

# xBAA at-bat classification (CLAUDE.md Step 7, confirmed spec rule):
#   in-play -> estimated_ba_using_speedangle ; strikeout -> 0 ; BB/HBP/sac -> not an AB
MIN_AB_FOR_XBAA = 3  # Daniel: keep appearance's xBAA only if AB >= 3
EXCLUDE_FROM_AB = {
    "walk", "intent_walk", "hit_by_pitch",
    "sac_fly", "sac_bunt", "sac_fly_double_play", "catcher_interf",
}
STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}
BIP_EVENTS = {  # balls in play that count as at-bats
    "single", "double", "triple", "home_run",
    "field_out", "grounded_into_double_play", "double_play", "triple_play",
    "force_out", "fielders_choice", "fielders_choice_out", "field_error",
}

# minimum columns to retain from Statcast (spec Step 2)
MIN_COLS = [
    "game_date", "pitcher", "player_name", "pitch_type", "release_speed",
    "pfx_x", "pfx_z", "events", "description", "estimated_ba_using_speedangle",
    "at_bat_number", "inning",
]

# season -> (start, end) date windows for statcast_pitcher pulls
SEASON_WINDOWS = {
    2021: ("2021-04-01", "2021-10-05"),
    2022: ("2022-04-07", "2022-10-05"),
    2023: ("2023-03-30", "2023-10-01"),
    2024: ("2024-03-28", "2024-09-30"),
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("build_panel")


# --- Step 2: fetch raw Statcast, cached, skip already-fetched combos ---------
def _load_existing_raw() -> pd.DataFrame:
    if RAW_PATH.exists():
        return pd.read_parquet(RAW_PATH)
    return pd.DataFrame(columns=MIN_COLS + ["season"])


def fetch_statcast(roster: pd.DataFrame) -> pd.DataFrame:
    """Download pitch-level Statcast for each (pitcher, season) in the roster.

    Skips any (mlbam_id, season) combo already present in statcast_raw.parquet.
    Appends new combos and re-writes the cache.
    """
    raw = _load_existing_raw()
    have = set()
    if not raw.empty:
        have = set(zip(raw["pitcher"].astype(int), raw["season"].astype(int)))

    combos = (
        roster[["mlbam_id", "season"]]
        .dropna()
        .astype({"mlbam_id": int, "season": int})
        .drop_duplicates()
        .itertuples(index=False)
    )

    new_frames = []
    n_fetched = n_skipped = n_empty = 0
    for mlbam_id, season in combos:
        if (mlbam_id, season) in have:
            n_skipped += 1
            continue
        if season not in SEASON_WINDOWS:
            log.warning("no date window for season %s — skipping pitcher %s", season, mlbam_id)
            continue
        start, end = SEASON_WINDOWS[season]
        df = statcast_pitcher(start, end, player_id=mlbam_id)
        if df is None or df.empty:
            n_empty += 1
            log.info("no pitches returned for pitcher %s season %s", mlbam_id, season)
            continue
        df = df[[c for c in MIN_COLS if c in df.columns]].copy()
        df["season"] = season
        new_frames.append(df)
        n_fetched += 1

    log.info(
        "statcast fetch: %d combos fetched, %d skipped (cached), %d empty",
        n_fetched, n_skipped, n_empty,
    )

    if new_frames:
        raw = pd.concat([raw, *new_frames], ignore_index=True)
        DATA_DIR.mkdir(exist_ok=True)
        raw.to_parquet(RAW_PATH, index=False)
        log.info("wrote %s (%d pitch rows total)", RAW_PATH, len(raw))

    # IMPORTANT: the cache may hold MORE (pitcher, season) combos than the current
    # roster (e.g. the roster was later trimmed by the IL filter). Restrict the raw
    # pitches to exactly the roster combos so the panel matches the roster.
    roster_combos = set(
        zip(
            roster["mlbam_id"].dropna().astype(int),
            roster["season"].astype(int),
        )
    )
    n_before = len(raw)
    raw = raw[[
        (int(p), int(s)) in roster_combos
        for p, s in zip(raw["pitcher"], raw["season"])
    ]].copy()
    log.info(
        "restricted raw to roster combos: %d -> %d pitch rows (%d roster combos)",
        n_before, len(raw), len(roster_combos),
    )
    return raw


# --- Step 4: four-seam only (velocity/movement outcomes) --------------------
def filter_fourseam(raw: pd.DataFrame) -> pd.DataFrame:
    before = len(raw)
    ff = raw[raw["pitch_type"].isin(FOURSEAM)].copy()
    log.info(
        "four-seam (FF) filter: %d -> %d pitch rows (dropped %d non-FF)",
        before, len(ff), before - len(ff),
    )
    return ff


# --- Step 7: xBAA per appearance (CONFIRMED spec rule, min 3 AB) -------------
def compute_xbaa(raw: pd.DataFrame) -> pd.DataFrame:
    """xBAA per (pitcher, game_date), computed over ALL at-bats in the outing.

    Rule (CLAUDE.md Step 7, confirmed): in-play -> estimated_ba_using_speedangle,
    strikeout -> 0, BB/HBP/sacrifice -> excluded from AB. xBAA = sum(xBA)/AB, kept
    only if AB >= MIN_AB_FOR_XBAA.

    Scope (CONFIRMED by Daniel 2026-07-19): xBAA is computed over EVERY at-bat in
    the appearance, NOT just at-bats ending on a four-seam. Rationale: xBAA is an
    outing-level batting result, and the spec's xBAA section does not restrict by
    pitch type (unlike the velocity/movement outcomes, which stay four-seam-only).

    Never-silent-drop (principle 4): in-play AB with NaN xBA and any unclassified
    terminal event are counted and logged, not silently dropped.
    """
    raw = raw.copy()
    raw["game_date"] = pd.to_datetime(raw["game_date"])

    # terminal pitch of each plate appearance carries a non-null `events`
    term = raw[raw["events"].notna() & (raw["events"].astype(str) != "")].copy()

    n_nan_bip = 0
    unclassified = {}

    def _row_contrib(ev: str, xba: float):
        """Return (is_ab, xba_contribution) or (False, None) if not an AB."""
        nonlocal n_nan_bip
        if ev in EXCLUDE_FROM_AB:
            return (False, None)
        if ev in STRIKEOUT_EVENTS:
            return (True, 0.0)
        if ev in BIP_EVENTS:
            if pd.isna(xba):
                n_nan_bip += 1
                return (False, None)  # counted+logged, excluded from AB
            return (True, float(xba))
        unclassified[ev] = unclassified.get(ev, 0) + 1
        return (False, None)

    contribs = term.apply(
        lambda r: _row_contrib(r["events"], r["estimated_ba_using_speedangle"]),
        axis=1, result_type="expand",
    )
    term["is_ab"] = contribs[0].astype(bool)
    term["xba_contrib"] = contribs[1]

    if n_nan_bip:
        log.info("xBAA: %d in-play at-bats had NaN xBA — excluded from AB and logged", n_nan_bip)
    if unclassified:
        log.info("xBAA: unclassified terminal events (excluded, logged): %s", unclassified)

    ab = term[term["is_ab"]]
    grouped = ab.groupby(["pitcher", "game_date"])
    xbaa = grouped.agg(
        xBAA_num=("xba_contrib", "sum"),
        ab_count=("xba_contrib", "size"),
    ).reset_index()
    xbaa["xBAA"] = xbaa["xBAA_num"] / xbaa["ab_count"]

    # apply the minimum-AB threshold (below-threshold appearances -> NaN xBAA)
    below = (xbaa["ab_count"] < MIN_AB_FOR_XBAA).sum()
    xbaa.loc[xbaa["ab_count"] < MIN_AB_FOR_XBAA, "xBAA"] = np.nan
    log.info(
        "xBAA computed for %d appearances (%d set NaN for AB < %d)",
        len(xbaa), int(below), MIN_AB_FOR_XBAA,
    )
    return xbaa[["pitcher", "game_date", "xBAA", "ab_count"]]


# --- Step 6 helper: (b) intensity robustness variable -----------------------
def add_intensity(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    """consec_intensity_<window> = # of the pitcher's PRIOR appearances within
    `window` days before this appearance (workload entering the outing).
    This is the (b) robustness coding of ConsecutiveDay."""
    col = f"consec_intensity_{window}"

    def per_pitcher(g: pd.DataFrame) -> pd.DataFrame:
        dates = g["game_date"].to_numpy()
        counts = []
        for d in dates:
            lo = d - np.timedelta64(window, "D")
            counts.append(int(((dates >= lo) & (dates < d)).sum()))
        g[col] = counts
        return g

    return panel.groupby("pitcher_id", group_keys=False).apply(per_pitcher)


# --- Step 5+6+7: aggregate to appearance level ------------------------------
def build_appearance_panel(ff: pd.DataFrame, raw_all: pd.DataFrame) -> pd.DataFrame:
    """One row per (pitcher, game_date) = one appearance.

    CONFIRMED: observation unit = appearance-level. Sample INCLUSION is decided at
    pitcher-season level upstream (reliever_list.py). The appearance universe is
    defined by four-seam presence (velocity/movement outcomes); xBAA is attached
    where computable (>= MIN_AB_FOR_XBAA at-bats), else NaN.
    """
    ff = ff.copy()
    ff["game_date"] = pd.to_datetime(ff["game_date"])

    # log NaN counts on FF outcome columns before aggregating (never drop silently)
    for col in ["release_speed", "pfx_x", "pfx_z"]:
        n_nan = ff[col].isna().sum()
        if n_nan:
            log.info("NaN in %s: %d of %d FF pitches (excluded from that mean)", col, n_nan, len(ff))

    grouped = ff.groupby(["pitcher", "game_date"], sort=True)
    panel = grouped.agg(
        player_name=("player_name", "first"),
        release_speed=("release_speed", "mean"),
        pfx_x=("pfx_x", "mean"),
        pfx_z=("pfx_z", "mean"),
        n_ff_pitches=("release_speed", "size"),
    ).reset_index()

    # attach xBAA (computed over all at-bats in the same appearance)
    xbaa = compute_xbaa(raw_all)
    panel = panel.merge(xbaa, on=["pitcher", "game_date"], how="left")

    panel["season"] = panel["game_date"].dt.year
    panel = panel.rename(columns={"pitcher": "pitcher_id"})

    # Step 6: post indicator (post main effect absorbed by season FE in run_did)
    panel["post"] = (panel["season"] >= POST_SEASON_START).astype(int)

    # Step 6: ConsecutiveDay (a) back-to-back — CONFIRMED primary coding.
    panel = panel.sort_values(["pitcher_id", "game_date"])
    days_since_prev = panel.groupby("pitcher_id")["game_date"].diff().dt.days
    panel["consec_day"] = (days_since_prev == 1).astype(int)
    # first appearance of a pitcher has no predecessor -> 0 (not consecutive)

    # Step 6: ConsecutiveDay (b) intensity — robustness coding.
    panel = add_intensity(panel, INTENSITY_WINDOW_DAYS)

    panel = panel.reset_index(drop=True)
    log.info(
        "panel built: %d appearances, %d pitchers, seasons %s",
        len(panel), panel["pitcher_id"].nunique(), sorted(panel["season"].unique()),
    )
    log.info(
        "consec_day==1 (back-to-back): %d (%.1f%%); xBAA non-null: %d",
        int(panel["consec_day"].sum()),
        100 * panel["consec_day"].mean() if len(panel) else 0.0,
        int(panel["xBAA"].notna().sum()),
    )
    return panel


def main() -> None:
    if not ROSTER_PATH.exists():
        raise SystemExit(f"missing {ROSTER_PATH} — run reliever_list.py first")
    roster = pd.read_parquet(ROSTER_PATH)
    log.info("roster: %d pitcher-seasons", len(roster))

    raw = fetch_statcast(roster)
    if raw.empty:
        raise SystemExit("no Statcast rows fetched — nothing to build")

    ff = filter_fourseam(raw)
    panel = build_appearance_panel(ff, raw)

    DATA_DIR.mkdir(exist_ok=True)
    panel.to_parquet(PANEL_PATH, index=False)
    log.info("wrote %s (%d rows)", PANEL_PATH, len(panel))
    print(panel.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
