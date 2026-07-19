# CLAUDE.md — Pitch Clock × Reliever Fatigue Analysis

> Claude Code가 이 프로젝트에서 따라야 할 지시서.
> **확정된 부분만 구현**하고, `⚠️ DECISION NEEDED`는 임의로 정하지 말고 `# TODO`로 남긴 뒤 Daniel에게 물어본다.
> 이 연구의 **설계(design)는 Daniel의 것**이다. Claude Code의 역할은 구현·디버깅·검증이지, 설계 결정을 대신 내리는 것이 아니다.

---

## 0. Research Question

Does the 2023 MLB pitch clock change how reliever fatigue accumulates on **consecutive-day appearances**?
Fatigue proxies: **release velocity, pitch movement, xBAA**.
핵심 추정량: **β₃ (Post × ConsecutiveDay)**.

---

## 1. 최종 산출물

1. `data/statcast_raw.parquet` — 캐싱된 원본 Statcast pitch 데이터
2. `build_panel.py` → `data/panel.parquet` (appearance-level 분석용 데이터)
3. `run_did.py` → 회귀 4개 실행
4. `results/did_results.csv` — outcome별 β₃, SE, t, p-value
5. 필터 단계마다 before/after 카운트 로그

---

## 2. 환경 세팅

```bash
pip install pybaseball pandas numpy pyarrow pyfixest
```

- `pybaseball` → Statcast(Baseball Savant) + FanGraphs
- `pyfixest` → two-way fixed effects + clustered SE
- `pyarrow` → parquet 캐싱 (Statcast는 데이터가 크므로 필수)

```python
from pybaseball import cache
cache.enable()   # 재실행 시 재다운로드 방지
```

---

## 3. 데이터 파이프라인

### Step 1 — 자격 있는 reliever 명단 (FanGraphs)

전체 리그 pitch를 통째로 받지 말 것. "누구를 볼지" 먼저 정하고, 그 투수 것만 Statcast에서 받는다.

```python
from pybaseball import pitching_stats, playerid_reverse_lookup

fg = pitching_stats(2021, 2024, qual=0)
relievers = fg[(fg["GS"] == 0) & (fg["G"] >= 20)].copy()
ids = playerid_reverse_lookup(relievers["IDfg"].tolist(), key_type="fangraphs")
```

**필터 (확정):**
- `GS == 0` (선발 등판 없음)
- 시즌당 `G >= 20`
- 해당 시즌 IL 없음 → Step 3
- 대상 시즌: 2021–2024 (2025는 robustness 전용, 지금은 제외)
- **balanced panel로 만들지 말 것** — durable veteran 쪽 selection bias 발생. unbalanced 유지.
- ID 매칭 실패 건수는 반드시 로그로 출력.

### Step 2 — 해당 투수 Statcast pitch 수집

```python
from pybaseball import statcast_pitcher
df = statcast_pitcher("2021-04-01", "2021-10-05", player_id=<mlbam_id>)
```

- pitcher × season 조합마다 받아 concat → 캐싱, 이미 받은 조합은 skip
- 최소 컬럼: `game_date, pitcher, player_name, pitch_type, release_speed, pfx_x, pfx_z, events, description, estimated_ba_using_speedangle, at_bat_number, inning`

### Step 3 — IL(부상) 필터 ⚠️ DECISION NEEDED

- 규칙(확정): 해당 시즌 IL에 오른 pitcher-season 제외.
- 문제: pybaseball / Retrosheet / Lahman에 깨끗한 IL 데이터 없음.
- `# TODO`: IL 소스 확정 필요. 정해지기 전까지 **자리만 만들어 두고 임의 대체 필터 넣지 말 것.**

### Step 4 — 직구만 (확정)

- fastball 계열만: `["FF", "SI", "FT"]`
- `FC`(cutter) 포함 여부는 `# TODO` (기본 제외)
- arm-slot 차이는 pitcher FE가 흡수하므로 여기선 무시.

### Step 5 — appearance 단위 집계

- 한 등판 = 같은 `game_date`의 같은 pitcher 모든 pitch.
- 회귀 관측 단위(observation) = **pitcher-appearance**
- 표본 포함 여부는 pitcher-season 단위로 판단 (Step 1~3)
- ⚠️ DECISION NEEDED: 노트엔 "pitcher-season as unit"이라 적혀 있으나, ConsecutiveDay가 시즌 내에서 변하므로 회귀 행은 appearance-level이어야 함. 멘토 확인 필요.

### Step 6 — 핵심 변수

```python
panel["post"] = (panel["season"] >= 2023).astype(int)
```

**`ConsecutiveDay` ⚠️ DECISION NEEDED:**
- 개념: "이 등판이 직전 등판 다음날인가?"
- 후보: (a) 직전 등판과 정확히 1일 차이=1 (back-to-back) / (b) 최근 N일 내 등판 횟수(intensity)
- `# TODO`: (a) vs (b) 확정 필요. 임시로 (a) 구현 시 "임시" 주석 명시.
- 구현: 투수별 `game_date` 정렬 → `diff()`로 직전 등판 일수 계산.

### Step 7 — Outcome 집계

| Outcome | 방법 | 상태 |
|---|---|---|
| `release_speed` | 등판 fastball 평균 구속 | 확정 |
| `pfx_x` | 등판 fastball 평균 수평 무브먼트 | 확정 |
| `pfx_z` | 등판 fastball 평균 수직 무브먼트 | 확정 |
| `xBAA` | 아래 | ⚠️ DECISION NEEDED |

**xBAA ⚠️ DECISION NEEDED:**
- `estimated_ba_using_speedangle`는 인플레이 타구 1개당 xBA.
- 등판 단위 집계 규칙: 인플레이 → xBA / 삼진 → 0 / 볼넷·HBP → at-bat 제외 / `xBAA = Σ(xBA) / AB수`
- `# TODO`: 삼진·볼넷 처리, 최소 타석 기준 확정 필요.

---

## 4. 회귀분석 (`run_did.py`) — 확정

```python
import pyfixest as pf

outcomes = ["release_speed", "pfx_x", "pfx_z", "xBAA"]
results = {}

for y in outcomes:
    model = pf.feols(
        f"{y} ~ consec_day + post:consec_day | pitcher_id + season",
        data=panel,
        vcov={"CRV1": "pitcher_id"},   # pitcher-level clustered SE
    )
    results[y] = model
    print(f"===== {y} =====")
    model.summary()
```

**식 해설 (반드시 준수):**
- `post:consec_day` = **β₃ ← 핵심 추정량**
- `| pitcher_id + season` = two-way fixed effects (γ_i, δ_t)
- `post` 주효과는 season FE에 흡수되므로 따로 넣지 않음
- `vcov={"CRV1": "pitcher_id"}` = clustered SE

**결과표:**
```python
import pandas as pd
rows = []
for y, m in results.items():
    rows.append({
        "outcome": y,
        "beta3":   m.coef()["post:consec_day"],
        "se":      m.se()["post:consec_day"],
        "t":       m.tstat()["post:consec_day"],
        "p_value": m.pvalue()["post:consec_day"],
    })
pd.DataFrame(rows).to_csv("results/did_results.csv", index=False)
```
- ⚠️ 설치된 `pyfixest` 버전의 실제 메서드명(`coef()`/`pvalue()` 등)을 확인하고 맞출 것.

---

## 5. Robustness (지금은 스텁만)

- **Parallel trends** ⚠️: pre-clock(2021–22) 추세 평행성 검증. event-study 형태 고려 → `event_study.py` 스텁만.
- **2025 데이터**: robustness 전용, 메인 회귀 제외.
- **Robustness 명세 목록** ⚠️ DECISION NEEDED: 대안 명세(필터 변경, cutter 포함, 최소 타석 등) 확정 필요.

---

## 6. 코딩 원칙 (반드시 준수)

1. **확정 안 된 결정을 임의로 채우지 말 것.** `⚠️ DECISION NEEDED`는 `# TODO` + 질문.
2. **필터 단계마다 before/after 카운트 출력** (몇 명→몇 명, 몇 등판 제외).
3. **Statcast 데이터 반드시 캐싱**, 재실행 시 재다운로드 금지.
4. **ID 매칭 실패·결측치(NaN)를 조용히 버리지 말고 개수 로그로 남길 것.**
5. 데이터 출처 불확실하면 지어내지 말고 "확인 필요"로 표시.
6. **AI 사용 기록**: 이 저장소에서 생성/수정한 스크립트는 논문 제출 시 Materials and Methods / Acknowledgments에 AI 도구 사용을 disclosure해야 한다. 주요 생성 코드는 `AI_USAGE.md`에 한 줄씩 기록해 둘 것.

> 검증 원칙: Claude Code가 짠 코드라도 **Daniel이 이해·설명·방어할 수 있어야** 최종 채택한다. 결과는 작은 표본으로 sanity check 후 신뢰한다.

---

## 부록 — 확정 vs 미확정

**확정:** DID + two-way FE(pitcher+season) + pitcher-clustered SE / reliever 필터(GS=0, G≥20, 2021–2024, unbalanced) / fastball-only(FF/SI/FT) / outcome 4개 / β₃=Post×ConsecutiveDay

**미확정(⚠️):** IL 소스 · 관측 단위(appearance-level 확인) · ConsecutiveDay 코딩 · xBAA 집계 · cutter 포함 · robustness 목록

<!-- PROGRESS:START -->
## Progress log

### Current state
FULL RUN COMPLETE on real 2021–2024 data. Pipeline
`reliever_list.py` → `build_panel.py` → `run_did.py` all ran end-to-end.
- Primary (IL-filtered, roster 459 pitcher-seasons): panel **18,824 appearances /
  289 pitchers**; results in `results/did_results.csv` (a, back-to-back) and
  `results/did_results_intensity.csv` (b, intensity N=3).
- Baseline (no IL filter, 878 seasons): 33,252 appearances / 462 pitchers, saved to
  `results/did_results_noIL.csv` + `..._intensity_noIL.csv`.
- **Finding: β₃ is NOT significant for any of the 4 outcomes in any spec**
  (all p > 0.13; primary-spec p: velo .35, pfx_x .32, pfx_z .27, xBAA .93). i.e. no
  detectable change in consecutive-day fatigue accumulation post-pitch-clock.
- Statcast fully cached in `data/statcast_raw.parquet` (all 878 combos, 721,806
  pitch rows), so re-runs need no download.

### Codebase map (resume here WITHOUT re-reading source or re-querying data)
Run everything with the venv python: `/Users/yunwesth/PitchClockResearch/.venv/bin/python`.
Pipeline order: `reliever_list.py` → `build_panel.py` → `run_did.py`.

- **`reliever_list.py`** — Step 1 roster. Source = `pitching_stats_bref(season)` for
  2021–2024; filters `GS==0 & G>=20`; `mlbID` is carried through as `mlbam_id`;
  IL filter = `apply_il_filter()` NO-OP placeholder. Writes
  `data/reliever_roster.parquet` (cols: season, name, mlbam_id, GS, G). ~878 rows.
- **`build_panel.py`** — Steps 2/4/5/6/7. `fetch_statcast(roster)` pulls
  `statcast_pitcher` per (mlbam_id, season), CACHED to `data/statcast_raw.parquet`,
  skips already-fetched combos. `filter_fourseam` keeps `pitch_type=="FF"` only.
  `compute_xbaa(raw)` = xBAA over ALL at-bats (K→0, BB/HBP/sac excluded via
  `EXCLUDE_FROM_AB`/`STRIKEOUT_EVENTS`/`BIP_EVENTS`, min 3 AB via `MIN_AB_FOR_XBAA`).
  `add_intensity` builds `consec_intensity_3` (window = `INTENSITY_WINDOW_DAYS`).
  `build_appearance_panel(ff, raw)` writes `data/panel.parquet`.
- **`run_did.py`** — `pf.feols("{y} ~ {consec} + post:{consec} | pitcher_id + season",
  vcov={"CRV1":"pitcher_id"})`; β₃ = `post:{consec}` term. Loops `SPECS`:
  main (`consec_day`) → `results/did_results.csv`, robustness (`consec_intensity_3`)
  → `results/did_results_intensity.csv`. Outcomes list = `OUTCOMES` (4).
- **`event_study.py`** — stub (NotImplementedError). **`AI_USAGE.md`** — disclosure log.

**panel.parquet schema:** pitcher_id, game_date, player_name, release_speed, pfx_x,
pfx_z, n_ff_pitches, xBAA, ab_count, season, post, consec_day, consec_intensity_3.
Row = one (pitcher, game_date) appearance. `post = season>=2023`.

### Decisions RESOLVED by Daniel (2026-07-19)
- ConsecutiveDay: **(a) back-to-back = primary**, **(b) intensity N=3 = robustness**.
- xBAA: spec rule (K→0, BB/HBP/sac excluded, in-play→xBA), **min 3 AB** per appearance.
- Observation unit: **appearance-level** (confirmed).
- Roster source: **Baseball-Reference** (confirmed; FanGraphs Cloudflare-blocked).
- Cutter: excluded (four-seam-only stands).
- xBAA pitch scope: **ALL at-bats in the outing** (not just four-seam-terminated).

- IL source: **MLB Stats API transactions** (`il_data.py`), keyed by MLBAM id.
  "Hit the IL" = >=1 injured-list PLACEMENT in-season (window widened to Mar 1).
  Effect: roster **878 → 459** pitcher-seasons (419 excluded; COVID-IL not a factor,
  0 rows among roster). Transfers/activations not counted; refine in `il_data.py`.

### Still open (Daniel)
- **Robustness list** — beyond (b) intensity: parallel-trends event study, 2025
  data, alt filters (not yet specified).

### Verification — PASSED (2026-07-19)
Independent audit (scratchpad `verify.py`): filter counts reconcile (878→459);
included/excluded pitchers re-checked; four-seam velocity, consec_day (0 mismatches
over 56 appts), and xBAA hand-recomputed from raw pitches all match the panel;
β₃ re-estimated with **statsmodels** two-way FE dummies matches pyfixest to 6
decimals for release_speed/pfx_z/xBAA. Numbers confirmed correct.

### Next steps
- [ ] Daniel to review the null result; decide on robustness specs (parallel-trends
      event study, 2025 data, alt filters, IL transfers, N sensitivity for (b)).

### Gotchas / blockers
- Only Python 3.9.6 on this machine → **pyfixest must be <0.19** (0.18.0 pinned);
  newer pyfixest uses `str | bool` syntax that fails to import on 3.9.
- **FanGraphs is Cloudflare-blocked** (403 "Just a moment…") on both the legacy
  `leaders-legacy.aspx` and the JSON API → plain `requests`/pybaseball can't reach
  it. Worked around by sourcing the roster from Baseball-Reference
  (`pitching_stats_bref`), which also carries `mlbID` directly. Statcast
  (`statcast_pitcher`, Baseball Savant) works fine and is cached.
- Env: `.venv/` (gitignore-worthy). Deps in `requirements.txt`.

### Session history (newest first)
#### 2026-07-19 — Standardized dependent variables (SD-unit β₃)
- `run_did.py` + `event_study.py` now report `beta3_sd`/`coef_sd`, `se_sd`, `sd_y`
  (β/SD(y)); p-values unchanged (linear rescale). Verified: re-estimating on
  z-scored y equals analytic β/SD exactly. All standardized primary β₃ < 0.02 SD.
- FINDINGS.md §8.1 + §0 updated with SD-unit effect sizes. Pushed to GitHub.

#### 2026-07-19 — Event study / parallel-trends (ref 2022) — implemented + PASSED
- `event_study.py`: consec_day interacted with each season, 2022 reference; writes
  `results/event_study.csv`. Pre-trend test (2021) PASSES for all 4 outcomes
  (p: velo .21, pfx_x .81, pfx_z .21, xBAA .72; none <.05). Post years also n.s.
- Also pushed repo to GitHub (public): github.com/yunwesth/PitchClockResearch
  (code + results only; .venv/ and data/ gitignored). NOTE: event_study.py +
  event_study.csv + FINDINGS event-study section not yet pushed — needs a commit.

#### 2026-07-19 — Full real-data run complete (primary + baseline)
- Downloaded all 878 pitcher-seasons of Statcast (721,806 pitch rows, cached).
- Fixed `fetch_statcast` bug: it returned the whole cache, not the roster subset —
  now restricts raw to roster (mlbam_id, season) combos so the IL filter actually
  shrinks the panel.
- Primary IL-filtered run: 18,824 appearances / 289 pitchers. Baseline no-IL:
  33,252 / 462 (saved to `*_noIL.csv`).
- Result: β₃ non-significant across all 4 outcomes and both consec codings (all
  p>0.13). No detectable pitch-clock effect on consecutive-day fatigue.

#### 2026-07-19 — Build IL filter (MLB Stats API) + wire into roster
- New `il_data.py`: pulls transactions from statsapi.mlb.com, detects IL
  placements ("placed"+"injured list"), caches `data/il_transactions.parquet`
  (14,154 placement rows 2021–24, minor-league included but harmless).
- Wired `reliever_list.apply_il_filter` to drop pitcher-seasons with >=1 placement.
- Verified: roster 878 → **459** pitcher-seasons (419 excluded), 305 pitchers;
  0 COVID rows among roster. NOTE: re-run roster+panel+DID after the in-flight
  full download finishes (Statcast cache will already hold all 878).

#### 2026-07-19 — Wire in Daniel's 4 decisions (xBAA, consec coding, unit, source)
- `build_panel.py`: implemented real **xBAA** (spec rule, min 3 AB) computed over
  all at-bats in the outing; added **(b) intensity** var `consec_intensity_3`;
  upgraded consec_day (a) and appearance-unit comments from TEMP → CONFIRMED.
- `run_did.py`: now runs 4 outcomes across 2 specs (main (a) → `did_results.csv`,
  robustness (b) → `did_results_intensity.csv`).
- Sample-verified (Díaz, Pressly ×2022–23, 170 appearances): xBAA on 159 appts
  (11 set NaN for AB<3), both specs produce β₃/SE/t/p for all 4 outcomes.

#### 2026-07-19 — Fix FanGraphs 403 blocker (source swap to Baseball-Reference)
- Diagnosed the 403 as Cloudflare bot protection (not a dead URL); confirmed it
  hits both `leaders-legacy.aspx` and the FanGraphs JSON API.
- Rewrote `reliever_list.py` to source the roster from
  `pybaseball.pitching_stats_bref` (loops 2021–2024, filters GS==0 & G>=20, uses
  built-in `mlbID`). Flagged the source swap in the module header for Daniel.
- Verified: 3498 pitcher-seasons → 1976 (GS==0) → 878 (G>=20), 480 unique
  pitchers, all with MLBAM ids; wrote `data/reliever_roster.parquet`.
#### 2026-07-19 — Build confirmed pipeline skeleton + sanity check
- Wrote `reliever_list.py` (Step 1: GS==0 & G>=20, unbalanced, ID lookup, filter
  logging, IL no-op placeholder), `build_panel.py` (Steps 2/4/5/6/7: cached
  statcast fetch, **four-seam FF-only per Daniel**, appearance aggregation,
  post/consec_day TEMP back-to-back, xBAA stub), `run_did.py` (two-way FE DID via
  pyfixest, pitcher-clustered CRV1, results CSV), `event_study.py` stub,
  `AI_USAGE.md`, `requirements.txt`.
- Set up `.venv` (py3.9); pinned pyfixest 0.18.0 (0.40 fails on 3.9).
- Verified pyfixest API: `pf.feols` + `.coef()/.se()/.tstat()/.pvalue()`, term
  `post:consec_day` extractable.
- Sanity check (Díaz 621242, Pressly 519151 × 2022–2023): FF filter 2668→855,
  170 appearances, post var 110/60, consec_day var 137/33 (19.4% back-to-back),
  caching confirmed (2nd run skipped all combos), xBAA correctly skipped as stub,
  DID ran all 3 confirmed outcomes.
- Hit FanGraphs 403 on Step 1 roster build — flagged, not worked around.
<!-- PROGRESS:END -->

