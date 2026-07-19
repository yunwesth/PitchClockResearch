# Pitch Clock × Reliever Fatigue — Findings Summary

_Generated 2026-07-19. Companion to `CLAUDE.md` (spec + journal). Design belongs to
Daniel; this file records what was built, decided, run, and verified._

---

## 1. Research question

Did the **2023 MLB pitch clock** change how reliever fatigue accumulates on
**consecutive-day appearances**?

- **Core estimand:** β₃ = coefficient on **Post × ConsecutiveDay** in a
  difference-in-differences with two-way fixed effects.
- **Fatigue proxies (4 outcomes):** four-seam release velocity, horizontal
  movement (`pfx_x`), vertical movement (`pfx_z`), and expected batting average
  against (`xBAA`).

---

## 2. Headline result

**No detectable effect.** β₃ is statistically insignificant for all four outcomes,
in both the primary and robustness specifications, with and without the IL filter.

### Primary spec — IL-filtered, (a) back-to-back · 18,824 appearances / 289 pitchers

| Outcome | β₃ | SE | p-value |
|---|---|---|---|
| release_speed | +0.0318 | 0.0342 | 0.354 |
| pfx_x | −0.0060 | 0.0060 | 0.315 |
| pfx_z | +0.0052 | 0.0047 | 0.266 |
| xBAA | +0.0005 | 0.0058 | 0.932 |

### Robustness — IL-filtered, (b) intensity N=3

| Outcome | β₃ | SE | p-value |
|---|---|---|---|
| release_speed | +0.0294 | 0.0245 | 0.231 |
| pfx_x | +0.0035 | 0.0038 | 0.365 |
| pfx_z | +0.0047 | 0.0031 | 0.130 |
| xBAA | −0.0016 | 0.0037 | 0.670 |

### Baseline — NO IL filter, (a) back-to-back · 33,252 appearances / 462 pitchers

| Outcome | β₃ | SE | p-value |
|---|---|---|---|
| release_speed | −0.0071 | 0.0284 | 0.803 |
| pfx_x | −0.0039 | 0.0045 | 0.392 |
| pfx_z | +0.0062 | 0.0037 | 0.092 |
| xBAA | +0.0025 | 0.0046 | 0.589 |

**Interpretation:** every β₃ p-value > 0.13. The pitch clock does not appear to
change consecutive-day fatigue accumulation on any of these proxies.

---

## 3. Data sources (all via `pybaseball` unless noted)

| Data | Source | Notes |
|---|---|---|
| Reliever roster (G, GS) | **Baseball-Reference** (`pitching_stats_bref`) | FanGraphs is Cloudflare-blocked (403); bref carries MLBAM id (`mlbID`) directly |
| Pitch-level data | **Baseball Savant** (`statcast_pitcher`) | cached to `data/statcast_raw.parquet` (all 878 combos, 721,806 pitches) |
| Injured-list stints | **MLB Stats API** (`statsapi.mlb.com/api/v1/transactions`) | keyed by MLBAM id; cached to `data/il_transactions.parquet` |

---

## 4. Sample construction (filter cascade)

```
bref pitcher-seasons 2021–2024 .............. 3,498
  GS == 0 (no starts) ....................... 1,976
  G >= 20 (per season) ......................   878   ← unbalanced panel
  IL filter (drop if hit IL that season) ....   459   ← 419 excluded
  → panel pitcher-seasons with four-seam data:  427  (289 unique pitchers)
  → appearances (regression rows): 18,824
```

- **Unbalanced panel** kept intentionally (avoids durable-veteran selection bias).
- **Observation unit = appearance** (one pitcher, one `game_date`); inclusion
  filters applied at the pitcher-season level.

---

## 5. Decisions (confirmed by Daniel)

| Item | Decision |
|---|---|
| Pitch type | **Four-seam only (`FF`)** for velocity/movement; SI/FT/FC excluded |
| ConsecutiveDay | **(a) back-to-back = primary**, **(b) intensity N=3 = robustness** |
| xBAA aggregation | in-play → xBA, strikeout → 0, BB/HBP/sac excluded; **min 3 AB**; over **all at-bats** in the outing (not just four-seam-terminated) |
| Observation unit | Appearance-level |
| Roster source | Baseball-Reference |
| IL rule | Exclude a pitcher-season with ≥1 IL **placement** (window widened to Mar 1); transfers/activations not counted |

---

## 6. Model

```
y ~ consec_day + post:consec_day | pitcher_id + season
```

- `post:consec_day` = **β₃** (core estimand)
- `| pitcher_id + season` = two-way fixed effects (post main effect absorbed by season FE)
- SE clustered on `pitcher_id` (CRV1)
- Estimated with `pyfixest.feols`

---

## 7. Verification — PASSED

Independent audit (`scratchpad/verify.py`):

| Check | Result |
|---|---|
| Filter counts (878 → 459) | reconcile exactly |
| Included/excluded pitchers | re-checked from scratch (GS/G/IL) ✓ |
| Four-seam velocity & movement | hand-recomputed from raw pitches, match to 4 decimals |
| `consec_day` | 0 mismatches over one pitcher's 56 appearances |
| `xBAA` | hand-recomputed from raw at-bats, exact match (0.3280) |
| **β₃** | re-estimated with **statsmodels** two-way FE dummies — matches `pyfixest` to 6 decimals |

The null result is not an artifact of one regression library or of a filtering bug.

---

## 8. Files

| File | Role |
|---|---|
| `reliever_list.py` | Step 1 roster (bref + IL filter) → `data/reliever_roster.parquet` |
| `il_data.py` | IL placements from MLB Stats API → `data/il_transactions.parquet` |
| `build_panel.py` | Statcast fetch (cached), four-seam filter, appearance panel, xBAA, consec vars → `data/panel.parquet` |
| `run_did.py` | DID over 4 outcomes × 2 specs → `results/did_results*.csv` |
| `event_study.py` | stub (parallel-trends, not yet implemented) |
| `results/did_results.csv` | primary (a) | `..._intensity.csv` robustness (b) |
| `results/*_noIL.csv` | baseline without IL filter |

Reproduce: `.venv/bin/python reliever_list.py && … build_panel.py && … run_did.py`
(Statcast cached, so no re-download.)

---

## 9. Caveats & open items

- **Still Daniel's to decide:** parallel-trends / event-study check (to defend the
  DID assumption), 2025 data as robustness, alternative specs (IL transfers, cutter,
  min-AB, N sensitivity for intensity).
- **Environment:** Python 3.9 requires `pyfixest==0.18.0` (see `requirements.txt`).
- **AI disclosure:** code generated with Claude Code; see `AI_USAGE.md`.
