"""
il_data.py — Step 3 injured-list source (MLB Stats API transactions).

Pitch Clock x Reliever Fatigue analysis. See CLAUDE.md Step 3.

Source: https://statsapi.mlb.com/api/v1/transactions  (free, official, JSON, no
auth). Each transaction carries the player's MLBAM id (`person.id`) — the same id
used in the reliever roster — plus a text `description`.

Rule (CLAUDE.md confirmed): exclude a pitcher-season if the pitcher HIT the IL that
season. "Hit the IL" = a PLACEMENT: description contains "placed" + "injured list".
Transfers (15->60 day) and activations/reinstatements are NOT counted as new stints
(a placement already exists for those). The season window is widened to March 1 to
catch late-spring placements before Opening Day.

Cached to data/il_transactions.parquet so re-runs don't re-hit the API.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "data"
IL_CACHE = DATA_DIR / "il_transactions.parquet"
API = "https://statsapi.mlb.com/api/v1/transactions"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# IL-detection substrings (lowercased description must contain ALL of one group)
PLACEMENT_TERMS = ("placed", "injured list")

# season window widened to catch pre-Opening-Day (spring) placements
SEASON_MONTHS = [  # (month_start, month_end_exclusive) pulled per (year, month)
    (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10), (10, 11), (11, 12),
]

log = logging.getLogger("il_data")


def _fetch_month(year: int, month: int) -> list[dict]:
    """Fetch one month of transactions (endpoint returns the full range at once)."""
    start = f"{year}-{month:02d}-01"
    end_month = month + 1
    end_year = year
    if end_month > 12:
        end_month, end_year = 1, year + 1
    end = f"{end_year}-{end_month:02d}-01"
    r = requests.get(
        API, params={"startDate": start, "endDate": end}, headers=HEADERS, timeout=60
    )
    r.raise_for_status()
    return r.json().get("transactions", [])


def _is_placement(desc: str) -> bool:
    d = (desc or "").lower()
    return all(term in d for term in PLACEMENT_TERMS) and "activated" not in d \
        and "reinstated" not in d


def fetch_il_transactions(seasons) -> pd.DataFrame:
    """Return IL PLACEMENT transactions across `seasons` as a DataFrame
    (columns: season, mlbam_id, name, date, description). Cached to parquet."""
    seasons = list(seasons)
    if IL_CACHE.exists():
        cached = pd.read_parquet(IL_CACHE)
        have = set(cached["season"].unique())
        if set(seasons).issubset(have):
            log.info("IL transactions loaded from cache (%d rows)", len(cached))
            return cached[cached["season"].isin(seasons)].copy()
    else:
        cached = pd.DataFrame()

    rows = []
    for year in seasons:
        n_year = 0
        for m_start, _ in SEASON_MONTHS:
            for t in _fetch_month(year, m_start):
                if not _is_placement(t.get("description", "")):
                    continue
                person = t.get("person", {}) or {}
                pid = person.get("id")
                if pid is None:
                    continue
                rows.append({
                    "season": year,
                    "mlbam_id": int(pid),
                    "name": person.get("fullName"),
                    "date": t.get("date"),
                    "description": t.get("description"),
                })
                n_year += 1
        log.info("IL placements pulled for %d: %d", year, n_year)

    df = pd.DataFrame(rows).drop_duplicates()
    if not cached.empty:
        df = pd.concat([cached, df], ignore_index=True).drop_duplicates()
    DATA_DIR.mkdir(exist_ok=True)
    df.to_parquet(IL_CACHE, index=False)
    log.info("wrote %s (%d IL placement rows)", IL_CACHE, len(df))
    return df[df["season"].isin(seasons)].copy()


def il_pitcher_seasons(seasons) -> set[tuple[int, int]]:
    """Return the set of (mlbam_id, season) that hit the IL (>=1 placement)."""
    df = fetch_il_transactions(seasons)
    return set(zip(df["mlbam_id"].astype(int), df["season"].astype(int)))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    ils = il_pitcher_seasons(range(2021, 2025))
    print(f"total (player, season) IL stints 2021-2024: {len(ils)}")
