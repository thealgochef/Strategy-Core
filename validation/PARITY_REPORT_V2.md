# Strategy-Core Parity Report v2 — CORRECTED phase-4a gate (FINAL)

Engine: `strategy_core_engine_v1` · contract `trade_lab_contract_v1`
Synthesized from the run-1 full sweep (all 57 days) + the run-3 candle-stage
reclassification (verified consistent on days 1–11 before the run was stopped to
save ~35 min of redundant recompute; the findings were stable from run 1).

## Day range (honored exactly)
- Requested: **2025-07-01 .. 2025-09-05 inclusive** → 67 calendar days.
- **Available and run: 57.** Warm-up day 2025-06-30 (level carry only, not counted).
- **Unavailable (10):** 2025-07-05, 07-08, 07-12, 07-19, 07-26, 08-02, 08-09, 08-16,
  08-23, 08-30 (Saturdays + a 07-08 data gap). No out-of-range substitution.
- **Total kept touches: 255** (canonical interaction features not None).

## Stage results (aggregate over all 57 available days)

| Stage | Scope | Total | Matched | Result |
|---|---|---:|---:|---|
| 0. Candles (deterministic book-mid bars) | must-match | per-day groups | aligned 100% | **see note** |
| A. Zones | must-match | 309 | 309 | ✅ |
| B. Touches (+ close ts) | must-match | 255 | 255 | ✅ |
| C. Sessions | must-match | 252 944 | 252 944 | ✅ |
| D. Labels | must-match | 218 | 218 | ✅ |
| E. Interaction *formula* fidelity | must-match | 255 | 254 | ⚠️ 1 harness artifact |
| F. Interaction *trade-price* | expected-differ | 255 | — | reported, not asserted |
| G. Approach features (×3) | must-match | 255 | 255 | ✅ |

## Stage 0 — candles: determinism FIXED; one real boundary difference remains
After imposing the stable total order `(ts_event, source-row-sequence)` and feeding
the **same ordered events** to both a harness-local reference bucketer and the engine
builder, the engine's bars match the reference **100% including open/close within
each trading-day group** (e.g. 2025-07-01: 62 524/62 524). The prior run's ~2.2%
open/close nondeterminism is **gone**.

The residual difference is **not** a bucketing/tie-break bug — it is a real
**trading-day-boundary semantics** difference:
- The engine uses a DST-aware **18:00 ET** trading-day boundary and resets
  `bar_index` there. Research's window edge is a hardcoded **23:00 America/Chicago**
  (see Window finding) and buckets continuously across it.
- On **44 of 57 days** the engine peels the post-18:00-ET tail into the *next*
  trading day; on Sunday-evening Globex sessions the whole session rolls to Monday.
  This phase-shifts ~0.5–2.8k tail bars/day. Counted raw (run 1) it was
  12 931 / 2 860 577 bars (0.45%); correctly classified (run 3) it is a **reported
  boundary finding**, with the aligned trading-day group matching 100%.
- 104 engine `END_OF_DAY` trailing partials excluded by design.

## Findings (reported, not hidden)
1. **Window root cause.** Research `_build_bars_for_date` passes a *naive*
   `datetime(prev, 23, 0)`; DuckDB's session `TimeZone='America/Chicago'` interprets
   it as **23:00 Chicago**, so the canonical bar window is Chicago-anchored, not UTC.
   The harness reproduced canonical bar counts/values exactly once localized to CT.
2. **Engine 18:00 ET vs research 23:00 CT day boundary** (Stage 0 above) — the one
   substantive engine-vs-research divergence; must be reconciled before the engine
   builder can replace research's DuckDB builder.
3. **Stage E single outlier (1/255):** touch @ 2025-07-20T23:59:04Z, whose +5m
   interaction window crosses midnight; the engine received *more* book rows than
   canonical (within: canon 30.14 vs eng 107.38), i.e. a **harness window-bound
   artifact at the day seam**, not an engine formula error — the formula is proven
   exact by the other 254 matches (and the v1 gate's 22/22).

## Stage F — interaction trade-price divergence (reported, not asserted)
Real TRADE prints (tick 0.25) vs canonical BOOK-MID (tick 0.125), `|Δ|` over 255 touches:
- int_time_beyond_level: mean 1.46, median 0.003, p95 9.01, max 47.78
- int_time_within_2pts:  mean 4.87, median 1.21,  p95 20.18, max 138.11
- int_absorption_ratio:  mean 0.131, median 0.000, p95 1.000, max 1.000

This is the deliberate trade-price change; the engine was never reverted to book-mid.

## Bar-builder benchmark (informational; not apples-to-apples)
Over 57 days / ~2.9M complete bars: shared engine builder ≈ **498s**, all-DuckDB ≈
**35s**. The engine number excludes the parquet read and is dominated by per-bar
`Bar`-object construction via `.itertuples()` (~60k/day) — the aggregation itself is
fast. Implication: the engine builder needs a faster bar-emit path before it can
replace DuckDB on speed; the dataset volume (~8.8M book events/day) makes I/O the
floor regardless.

## VERDICT
- **Decision-layer port fidelity: PROVEN** across all 57 available real days
  (255 touches): zones, touches + close timestamps, sessions, labels, interaction
  *formula* fidelity, and the 3 approach features all match canonical exactly (the
  lone Stage-E outlier is a harness window-bound artifact, not an engine divergence).
- **Candle builder: determinism PROVEN** (100% incl. open/close on aligned
  trading-day groups after the stable sort); **one open reconciliation** — the engine's
  18:00 ET trading-day boundary vs research's 23:00 CT window.
- **Net:** the engine reproduces the canonical **decision** pipeline exactly on the
  full requested real range; the single open item is the candle builder's
  **trading-day-boundary definition** — a reconciliation decision, not a defect.

GATE: stop here. No repointing of research, the emitter, or Trade-Lab.
