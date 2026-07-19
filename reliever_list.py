"""
reliever_list.py — Step 1: build the eligible reliever roster.

Pitch Clock x Reliever Fatigue analysis. See CLAUDE.md for the full spec.

Confirmed filters (do NOT change without Daniel):
    - GS == 0            (no starts)
    - G  >= 20           (per season)
    - seasons 2021-2024  (2025 is robustness-only, excluded here)
    - UNBALANCED panel   (do not force a balanced panel -> avoids durable-veteran
                          selection bias)

⚠️ DATA-SOURCE CHANGE (needs Daniel's sign-off):
    The spec (CLAUDE.md Step 1) specifies FanGraphs via
    `pitching_stats(...)`. That endpoint is now behind Cloudflare bot
    protection and returns HTTP 403 for automated clients, so it is NOT usable.
    This module instead pulls the SAME fields (G, GS per pitcher-season) from
    Baseball-Reference via `pybaseball.pitching_stats_bref`, which also provides
    the MLBAM id directly (`mlbID`). The filter *intent* is unchanged; only the
    source differs.
    # TODO: confirm with Daniel that Baseball-Reference is an acceptable roster
    source, or restore FanGraphs via a Cloudflare-capable fetch.

All baseball data comes from `pybaseball`.

Coding principles enforced (CLAUDE.md sec. 6):
    - log before/after counts at every filter step
    - log missing-id rows explicitly (never drop silently)
    - do NOT invent an IL source -> placeholder no-op, logged as such
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from pybaseball import cache, pitching_stats_bref

import il_data

cache.enable()  # re-run safe: avoid re-downloading each season

# --- config -----------------------------------------------------------------
SEASONS = range(2021, 2025)     # 2021, 2022, 2023, 2024 (inclusive)
MIN_GAMES = 20                  # G >= 20 per season
DATA_DIR = Path(__file__).parent / "data"

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("reliever_list")


def get_reliever_seasons() -> pd.DataFrame:
    """Return one row per eligible (pitcher, season) from Baseball-Reference.

    pitching_stats_bref returns one MLB row per player-season (traded players are
    already combined into a single season total), so filters apply cleanly per
    pitcher-season. A pitcher can qualify in some seasons and not others — this is
    the intended UNBALANCED panel.
    """
    frames = []
    for season in SEASONS:
        df = pitching_stats_bref(season)
        df = df.copy()
        df["season"] = season
        frames.append(df)
        log.info("Baseball-Reference pitcher rows pulled (%d): %d", season, len(df))

    allp = pd.concat(frames, ignore_index=True)
    log.info("total pitcher-seasons pulled (%d-%d): %d rows",
             min(SEASONS), max(SEASONS), len(allp))

    # GS == 0 : no starting appearances
    no_starts = allp[allp["GS"] == 0].copy()
    log.info("after GS == 0: %d rows (dropped %d)", len(no_starts), len(allp) - len(no_starts))

    # G >= 20 per season
    relievers = no_starts[no_starts["G"] >= MIN_GAMES].copy()
    log.info(
        "after G >= %d: %d rows (dropped %d)",
        MIN_GAMES, len(relievers), len(no_starts) - len(relievers),
    )

    n_pitchers = relievers["mlbID"].nunique()
    log.info("eligible: %d pitcher-seasons across %d unique pitchers", len(relievers), n_pitchers)
    return relievers


def attach_mlbam_ids(relievers: pd.DataFrame) -> pd.DataFrame:
    """Baseball-Reference already carries the MLBAM id in `mlbID`.

    Rows with a missing/blank `mlbID` cannot be pulled from Statcast, so they are
    logged (count + names) and dropped — never silently (CLAUDE.md principle 4).
    """
    relievers = relievers.copy()
    # normalize blanks to NaN
    relievers["mlbID"] = relievers["mlbID"].replace("", pd.NA)

    missing = relievers[relievers["mlbID"].isna()]
    if len(missing):
        names = sorted(missing["Name"].astype(str).unique().tolist())
        log.warning(
            "missing MLBAM id for %d pitcher-season rows (%d players): %s",
            len(missing), len(names), names,
        )
    else:
        log.info("all eligible pitcher-seasons have an MLBAM id")

    matched = relievers[relievers["mlbID"].notna()].copy()
    matched["mlbam_id"] = matched["mlbID"].astype(int)
    log.info("usable pitcher-seasons with MLBAM id: %d", len(matched))
    return matched


def apply_il_filter(relievers: pd.DataFrame) -> pd.DataFrame:
    """Step 3 — IL (injured list) filter (CONFIRMED rule; source = MLB Stats API).

    Rule: exclude a pitcher-season if the pitcher hit the IL that season, where
    "hit the IL" = at least one injured-list PLACEMENT (see il_data.py). Source is
    the MLB Stats API transactions endpoint, keyed by MLBAM id, cached to
    data/il_transactions.parquet.
    """
    seasons = sorted(relievers["season"].astype(int).unique())
    flagged = il_data.il_pitcher_seasons(seasons)

    ids = pd.to_numeric(relievers["mlbID"], errors="coerce").astype("Int64")
    keys = list(zip(ids, relievers["season"].astype(int)))
    mask_hit = [(int(m), s) in flagged if pd.notna(m) else False for m, s in keys]
    n_hit = sum(mask_hit)

    kept = relievers[[not h for h in mask_hit]].copy()
    log.info(
        "IL filter: %d -> %d pitcher-seasons (excluded %d that hit the IL)",
        len(relievers), len(kept), n_hit,
    )
    return kept


def build_roster() -> pd.DataFrame:
    relievers = get_reliever_seasons()
    relievers = apply_il_filter(relievers)          # no-op for now
    roster = attach_mlbam_ids(relievers)

    # keep a lean set of columns useful downstream
    keep = ["season", "Name", "mlbam_id", "GS", "G"]
    keep = [c for c in keep if c in roster.columns]
    roster = roster[keep].rename(columns={"Name": "name"})
    return roster.sort_values(["season", "name"]).reset_index(drop=True)


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    roster = build_roster()
    out = DATA_DIR / "reliever_roster.parquet"
    roster.to_parquet(out, index=False)
    log.info("wrote %s (%d rows)", out, len(roster))
    print(roster.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
