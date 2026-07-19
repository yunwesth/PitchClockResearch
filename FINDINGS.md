# Pitch Clock × Reliever Fatigue — Full Findings Report

_Generated 2026-07-19. This document is self-contained: it defines all terms,
variables, data, methods, and results needed to interpret the study without any
other file. Companion code lives alongside it (see §11)._

---

## 0. Executive summary (TL;DR)

- **Question:** Did MLB's 2023 pitch clock change how much **relief pitchers**
  fade when they pitch on **back-to-back days** (consecutive-day fatigue)?
- **Method:** Difference-in-differences (DID) with two-way fixed effects on
  appearance-level Statcast data, 2021–2024. Key coefficient **β₃ = Post ×
  ConsecutiveDay**.
- **Answer: No detectable effect.** β₃ is statistically insignificant for all four
  fatigue proxies (fastball velocity, horizontal movement, vertical movement,
  expected batting average against), in the primary spec, a robustness spec, and a
  no-injury-filter baseline. A parallel-trends (event-study) check passes, so the
  null is credible and not masking a pre-existing trend.
- **Bottom line for interpretation:** The data are consistent with the pitch clock
  having **no meaningful impact** on consecutive-day reliever fatigue as measured
  here. Estimated effects are not just insignificant but **tiny in magnitude**
  (e.g., ~0.03 mph on a ~94.8 mph fastball).

---

## 1. Background & hypothesis

The **pitch clock** was introduced in MLB in **2023**. It limits the time between
pitches (15s bases empty / 20s with runners in 2023), shortening games and reducing
rest between pitches within an outing. A plausible concern: less between-pitch
recovery could **worsen fatigue**, especially for **relief pitchers** who often
pitch on **consecutive calendar days**.

**Directional hypothesis (what a real effect would look like):** after 2023, on
consecutive-day appearances relative to non-consecutive ones, we would expect
**lower velocity**, **reduced movement**, and **worse results (higher xBAA)** —
i.e., a negative β₃ for velocity/movement and a positive β₃ for xBAA. **We do not
observe this.**

---

## 2. Glossary (baseball / Statcast terms)

| Term | Meaning |
|---|---|
| **Reliever** | A pitcher who enters mid-game, not the starter. Here: pitchers with **0 starts** in a season. |
| **Appearance / outing** | One pitcher pitching in one game (one calendar date). The unit of analysis. |
| **Four-seam fastball (`FF`)** | The most common, "straight" fastball. We restrict velocity/movement outcomes to four-seamers only, so we compare like with like. |
| **`release_speed`** | Pitch velocity at release, in **miles per hour (mph)**. |
| **`pfx_x`, `pfx_z`** | Horizontal / vertical pitch **movement**, in **feet**, from Statcast (how much the pitch deviates from a no-spin trajectory). Fatigue can flatten movement. |
| **xBA / xBAA** | *Expected* batting average (against). Statcast's `estimated_ba_using_speedangle` predicts hit probability from a batted ball's exit velocity + launch angle. **xBAA** aggregates this to a pitcher-outing: a "deserved" opponent batting average, less noisy than actual results. Ranges ~0.150–0.400; higher = pitcher did worse. |
| **AB (at-bat)** | A batter's plate appearance, excluding walks, hit-by-pitch, and sacrifices. |
| **Injured List (IL)** | Roster status for injured players. A season with any IL stint is excluded (see §5). |
| **Statcast / Baseball Savant** | MLB's pitch-tracking system and public data portal. |

---

## 3. Data sources

| Data | Source | Access | Notes |
|---|---|---|---|
| Reliever roster (games `G`, games started `GS`) | **Baseball-Reference** | `pybaseball.pitching_stats_bref(season)` | Chosen because **FanGraphs is Cloudflare-blocked (HTTP 403)**. Baseball-Reference also provides the MLBAM player id (`mlbID`) directly. |
| Pitch-level data | **Baseball Savant (Statcast)** | `pybaseball.statcast_pitcher(start, end, player_id)` | Cached locally; 721,806 pitches across 878 pitcher-seasons before filtering. |
| Injured-list stints | **MLB Stats API** | `https://statsapi.mlb.com/api/v1/transactions` | Free/official; keyed by MLBAM id. IL "placement" transactions parsed from description text. |

All player ids are **MLBAM ids**, consistent across sources.

---

## 4. Variable definitions (panel columns)

Each row of the analysis panel = one **appearance** (`pitcher_id` × `game_date`).

| Column | Definition |
|---|---|
| `pitcher_id` | MLBAM player id. |
| `game_date` | Calendar date of the appearance. |
| `season` | Year (2021–2024). |
| `release_speed` | **Mean** four-seam release velocity (mph) in that appearance. |
| `pfx_x` | Mean four-seam horizontal movement (ft) in that appearance. |
| `pfx_z` | Mean four-seam vertical movement (ft) in that appearance. |
| `n_ff_pitches` | Count of four-seam fastballs thrown that appearance. |
| `xBAA` | Expected batting average against for the outing (see §4a). `NaN` if fewer than 3 at-bats. |
| `ab_count` | Number of at-bats used in the xBAA denominator. |
| `post` | **1 if season ≥ 2023** (pitch-clock era), else 0. |
| `consec_day` | **(a) back-to-back:** 1 if the pitcher also appeared **exactly the previous calendar day**, else 0. Primary treatment intensity. |
| `consec_intensity_3` | **(b) intensity:** count of the pitcher's appearances in the **prior 3 days**. Robustness treatment intensity. |

### 4a. How `xBAA` is computed (confirmed rule)
Over **all at-bats** the reliever faced in the outing (not only four-seam-ending ones):
- **Ball in play** → add its `estimated_ba_using_speedangle` (xBA) to the numerator; count as 1 AB.
- **Strikeout** → contributes **0** to the numerator; counts as 1 AB.
- **Walk / hit-by-pitch / sacrifice** → **excluded** (not an AB).
- `xBAA = Σ(xBA) / AB`. Kept only if **AB ≥ 3** (else `NaN`).
- In-play at-bats with missing xBA, and any unclassifiable terminal event, are counted/logged and excluded (never silently dropped).

---

## 5. Sample construction (filter cascade)

```
Baseball-Reference pitcher-seasons, 2021–2024 ............ 3,498
  keep GS == 0  (no starts → reliever) .................. 1,976
  keep G  >= 20 (season workload threshold) .............   878   ← unbalanced panel
  drop pitcher-seasons that hit the IL that season ......   459   ← 419 excluded
    (→ pitcher-seasons that actually have four-seam data:  427; 289 unique pitchers)
  → appearances (regression rows) ...................... 18,824
```

- **Unbalanced panel** kept intentionally — forcing a balanced panel would bias
  toward durable veterans (survivorship/selection bias).
- **IL rule:** exclude a pitcher-season with **≥1 IL placement** that season
  (window widened to March 1 to catch spring placements). Transfers (15→60-day) and
  activations are not counted as new stints. Rationale: an injured pitcher's decline
  would confound "fatigue." COVID-IL was checked and is **not** a factor (0 rows
  among these relievers).
- **Observation unit = appearance.** Sample *inclusion* is decided per
  pitcher-season (above); the regression *rows* are appearances, because
  `consec_day` varies within a season.

---

## 6. Descriptive statistics (primary IL-filtered panel)

- **18,824 appearances**, **289 pitchers**, 2021–2024.
- Appearances by season: 2021 = 4,831 · 2022 = 4,495 · 2023 = 4,515 · 2024 = 4,983.
- `consec_day`: **3,229 back-to-back** (17.2%) vs 15,595 non-consecutive.
- `post`: 9,498 post-clock vs 9,326 pre-clock appearances.
- Four-seams per appearance: mean 7.3, median 6. xBAA at-bats: mean 3.8; xBAA is
  non-null for 16,370 appearances.

**Outcome levels (for magnitude context):**

| Outcome | Mean | SD | Note |
|---|---|---|---|
| release_speed | 94.832 mph | 2.654 | a fatigue effect of interest would be ~0.5–1+ mph |
| pfx_x | −0.345 ft | 0.679 | |
| pfx_z | 1.266 ft | 0.280 | |
| xBAA | 0.210 | 0.139 | like a .210 expected opponent average |

**Raw 2×2 "gap-of-gaps" (descriptive DID, no controls)** — mean outcome by
period × consecutive status, and the raw difference-in-differences:

_release_speed (mph):_

| | consec | non-consec |
|---|---|---|
| post (2023–24) | 95.332 | 95.141 |
| pre (2021–22) | 94.469 | 94.488 |

raw DID = (95.332−95.141) − (94.469−94.488) = **+0.210 mph**

_pfx_z (ft):_ raw DID = **+0.011** · _xBAA:_ raw DID = **+0.003**

> Note: the raw velocity DID (+0.21 mph) shrinks to **+0.03 mph and insignificant**
> once pitcher and season fixed effects are added (§8), i.e., the raw gap reflects
> *which pitchers* throw on consecutive days, not a within-pitcher clock effect.

---

## 7. Model specification

**Primary (and baseline) DID:**
```
y ~ consec_day + post:consec_day | pitcher_id + season
```
- `y` ∈ {release_speed, pfx_x, pfx_z, xBAA}, estimated separately.
- **`post:consec_day` = β₃ = the causal estimand.** It measures how the
  consecutive-day gap *changed* after the pitch clock.
- `consec_day` (main) = the consecutive-day gap in the pre-period.
- `| pitcher_id + season` = **two-way fixed effects**: `pitcher_id` absorbs
  time-invariant pitcher quality; `season` absorbs league-wide year shocks (and
  absorbs the `post` main effect, so it is not entered separately).
- **Standard errors clustered on `pitcher_id`** (CRV1), because a pitcher's
  appearances are correlated.
- Estimator: `pyfixest.feols` (Python).

**Robustness spec:** identical, replacing `consec_day` with `consec_intensity_3`.

**Coefficient sign guide:** a *fatigue* effect from the clock would be **β₃ < 0**
for velocity/movement (worse stuff) and **β₃ > 0** for xBAA (worse outcomes).

---

## 8. Results

### 8.1 Primary — IL-filtered, (a) back-to-back · N = 18,824 (xBAA N = 16,370)

| Outcome | β₃ | SE | p-value | Significant? |
|---|---|---|---|---|
| release_speed | +0.0318 | 0.0342 | 0.354 | no |
| pfx_x | −0.0060 | 0.0060 | 0.315 | no |
| pfx_z | +0.0052 | 0.0047 | 0.266 | no |
| xBAA | +0.0005 | 0.0058 | 0.932 | no |

### 8.2 Robustness — IL-filtered, (b) intensity (appearances in prior 3 days)

| Outcome | β₃ | SE | p-value | Significant? |
|---|---|---|---|---|
| release_speed | +0.0294 | 0.0245 | 0.231 | no |
| pfx_x | +0.0035 | 0.0038 | 0.365 | no |
| pfx_z | +0.0047 | 0.0031 | 0.130 | no |
| xBAA | −0.0016 | 0.0037 | 0.670 | no |

### 8.3 Baseline — NO IL filter, (a) back-to-back · N = 33,252 (462 pitchers)

| Outcome | β₃ | SE | p-value | Significant? |
|---|---|---|---|---|
| release_speed | −0.0071 | 0.0284 | 0.803 | no |
| pfx_x | −0.0039 | 0.0045 | 0.392 | no |
| pfx_z | +0.0062 | 0.0037 | 0.092 | no (marginal) |
| xBAA | +0.0025 | 0.0046 | 0.589 | no |

**How to read these:** every β₃ is insignificant (all p > 0.09; the primary spec all
p > 0.26). Signs are inconsistent across specs (e.g., velocity β₃ flips sign between
primary and baseline), which is what you expect when the true effect is ~0. The
point estimates are also **economically tiny** relative to the outcome SDs in §6.

---

## 9. Event study / parallel-trends test — PASSED

To defend the DID's key assumption (that, absent the clock, the consecutive-day gap
would have evolved in parallel), `consec_day` is interacted with **each season**,
with **2022** (last pre-clock year) as the omitted reference:
```
y ~ consec_day + consec_day:1[2021] + consec_day:1[2023] + consec_day:1[2024] | pitcher_id + season
```
Each yearly coefficient = that year's consecutive-day gap **minus 2022's**. The
**2021** coefficient is the **pre-trend test** (should be ≈0 if trends are parallel);
2023/2024 are the post-clock effects. Full table in `results/event_study.csv`.

| Outcome | 2021 coef (SE) — pre-trend | p | 2023 coef (SE) | p | 2024 coef (SE) | p |
|---|---|---|---|---|---|---|
| release_speed | +0.0646 (0.0517) | 0.212 | +0.0815 (0.0450) | 0.071 | +0.0526 (0.0451) | 0.244 |
| pfx_x | +0.0019 (0.0078) | 0.809 | −0.0046 (0.0088) | 0.599 | −0.0054 (0.0079) | 0.493 |
| pfx_z | +0.0076 (0.0060) | 0.206 | +0.0114 (0.0060) | 0.059 | +0.0073 (0.0057) | 0.202 |
| xBAA | −0.0030 (0.0083) | 0.721 | +0.0003 (0.0088) | 0.976 | −0.0023 (0.0083) | 0.785 |

**Pre-trend test PASSES:** no outcome has a significant 2021 coefficient (all
p ≥ 0.05), so the parallel-trends assumption is supported. Post-clock years are also
insignificant (closest: velocity-2023 p=0.071, pfx_z-2023 p=0.059 — both > 0.05),
consistent with the null β₃.

---

## 10. Verification — PASSED

Independent audit (`verify.py`, run 2026-07-19):

| Check | Method | Result |
|---|---|---|
| Filter counts | re-pulled bref, re-applied filters from scratch | 878 → 459 reconcile exactly |
| Roster membership | re-checked one included + one excluded pitcher (GS/G/IL) | correct |
| Four-seam outcomes | hand-averaged FF pitches for one appearance | match to 4 decimals |
| `consec_day` | walked one pitcher's 56 appearances by date gaps | 0 mismatches |
| `xBAA` | hand-computed from raw at-bats (2 field_out + 1 double) | exact match (0.3280) |
| **β₃** | re-estimated with **statsmodels** two-way FE dummies | matches `pyfixest` to 6 decimals |

The null result is not an artifact of one library or a filtering bug.

---

## 11. Files & reproduction

| File | Role |
|---|---|
| `reliever_list.py` | Step 1 roster (Baseball-Reference + IL filter) → `data/reliever_roster.parquet` |
| `il_data.py` | IL placements from MLB Stats API → `data/il_transactions.parquet` |
| `build_panel.py` | Statcast fetch (cached), four-seam filter, appearance panel, xBAA, consec vars → `data/panel.parquet` |
| `run_did.py` | DID over 4 outcomes × 2 specs → `results/did_results.csv`, `..._intensity.csv` |
| `event_study.py` | parallel-trends event study (ref 2022) → `results/event_study.csv` |
| `results/*_noIL.csv` | baseline results without the IL filter |
| `requirements.txt` | pinned deps (Python 3.9 requires `pyfixest==0.18.0`) |

**Reproduce:**
```
pip install -r requirements.txt
python reliever_list.py    # roster (+ IL filter)
python build_panel.py      # downloads Statcast on first run, then cached
python run_did.py          # primary + robustness DID
python event_study.py      # parallel-trends test
```
Data files (`data/`) are gitignored and regenerate on first run.

---

## 12. Limitations & open choices (for careful interpretation)

- **Null ≠ proof of no effect.** These data cannot rule out very small effects; they
  show no *detectable* effect at this sample size. SEs (~0.03 mph for velocity) imply
  the study could detect only effects larger than roughly a few hundredths of a mph
  at conventional power — so "no effect" is well-supported for *meaningful* fatigue,
  but a truly minuscule effect can't be excluded.
- **Fatigue proxies are indirect.** Velocity/movement/xBAA are reasonable but partial
  proxies; they don't capture injury risk, command, or pitch selection changes.
- **`consec_day` is calendar-based**, not workload-weighted (a 5-pitch outing and a
  30-pitch outing both count). The intensity spec partially addresses this.
- **IL filter is a placement-based approximation** (transfers/activations excluded);
  the no-IL baseline shows results are not sensitive to it.
- **xBAA excludes strikeout-heavy noise via the K→0 rule and min-3-AB threshold**;
  appearances with <3 AB drop out (~13% of outings).
- **2025 data** were intentionally excluded (reserved for future robustness).
- **Design decisions** (four-seam-only, appearance-level unit, back-to-back primary
  coding, xBAA rule, Baseball-Reference source, IL rule) were set deliberately and
  are documented in `CLAUDE.md`.

---

## 13. One-paragraph interpretation (drop-in)

Using appearance-level Statcast data on qualified MLB relievers (0 starts, ≥20 games,
no IL stint) from 2021–2024, we estimate a difference-in-differences with pitcher and
season fixed effects to test whether the 2023 pitch clock altered consecutive-day
fatigue. Across four fatigue proxies — four-seam velocity, horizontal and vertical
movement, and expected batting average against — the Post × ConsecutiveDay coefficient
is small and statistically insignificant in every specification (primary back-to-back,
a 3-day intensity robustness check, and a no-injury-filter baseline). An event-study
shows no differential pre-trend in 2021 and no significant post-clock shift in 2023–24.
We therefore find **no evidence that the pitch clock meaningfully changed how reliever
performance degrades on consecutive-day appearances.**
