# Phase 4b-prep — vectorized emit + 18:00 ET boundary (targeted validation)

Engine `strategy_core_engine_v1`. strategy-core only; Claude-Quant-Lab and Trade-Lab
untouched. Harness: `validation/phase4b_validate.py` (reads research repo + databento
store read-only). 18:00 ET boundary confirmed locked: `RESEARCH_SESSION_SCHEME.
trading_day_boundary = 18:00`, tz `US/Eastern` (DST-aware), `bar_index` resets there.

Sample (chosen to stress the risks): **2025-07-01** (busy RTH, duplicate-ts ties,
post-18:00-ET tail), **2025-07-06** (Sunday-evening Globex / 18:00-ET seam),
**2025-07-15** (busy RTH, ties).

## (a) Emit equivalence — PASS
The per-bar `.itertuples()` + per-row `Timestamp.to_pydatetime()` emit was replaced by
a batch/vectorized emit (extract agg columns once, build `Bar`s in one comprehension).
**Same aggregation, same deterministic `(ts_event, source-seq)` order — only the emit
changed.** New vs old emit, byte-for-byte on every field (OHLC, volume, timestamps,
`bar_index`, `bar_id`, flags, close_reason):

| Day | bars | IDENTICAL |
|---|---:|---|
| 2025-07-01 | 62 526 | ✅ |
| 2025-07-06 | 1 890 | ✅ |
| 2025-07-15 | 76 154 | ✅ |

(Also guarded by the package's `tests/test_candle_parity.py` — batch == streaming, 97 tests pass.)

## (b) No-regression diff — engine (18:00 ET) vs canonical (23:00 CT), PASS
Zones are identical (session highs/lows are order-independent max/min, so
bucketing-independent). **Logic is provably unchanged**: feeding *identical* bars to
the research touch detector and `strategy_core.detect_touches` yields identical
touches (`LOGIC_UNCHANGED=True`) — so every engine-vs-canonical difference below is
attributable to the **bar inputs differing at the 18:00-ET boundary**, not to any
code change.

| Day | zones_same | logic_unchanged | canon→eng touches | matched | only_canon | only_eng | labels_same | touch-ts shift (med / max) |
|---|---|---|---|---|---|---|---|---|
| 2025-07-01 | ✅ | ✅ | 5→5 | 5 | 0 | 0 | 5/5 | 0.1s / 6.6h |
| 2025-07-06 | ✅ | ✅ | 2→1 | 1 | 1 | 0 | 1/1 | 0s / 0s |

Boundary attribution: on 07-01 the RTH touches align to 0.1s and all labels match; one
overnight level shifts 6.6h because the engine's trading day `[D-1 18:00 ET, D 18:00 ET]`
first-touches it in the prior evening, whereas research's `[D 00:00 ET, D+1 00:00 ET]`
window touches it later. On the Sunday 07-06 session the boundary window omits one of
canonical's two touches. Both are pure window/bucketing effects.

Label/level classes seen in-sample: PDH, PDL, asia_high/low, london_high/low;
labels `tradeable_reversal`, `no_resolution`. (Small sample → only these classes hit.)

## (c) Seam audit — PASS (closes the prior 23:59-ET Stage-E concern)
Independent re-derivation of the first bar of the engine trading day, from raw events:

- **2025-07-01**: td opens `2025-06-30 18:00 ET`; first event exactly at 18:00:00 ET;
  bar0 `trading_day=2025-07-01`, `bar_index=0` (reset confirmed); bar0 OHLC recomputed
  from the first 147 raw events matches the engine exactly (open/high/low/close all equal);
  close-ts = the 147th event's time → **no look-ahead**.
- **2025-07-06** (Sunday): td opens `2025-07-05 18:00 ET`; bar0 `trading_day=2025-07-06`,
  `bar_index=0`; first-147-event recompute matches; close-ts = 147th event → no look-ahead.

The prior phase-4a Stage-E outlier (a 23:59-ET touch whose window crossed midnight) was a
harness window-bound artifact; the engine's 18:00-ET day assignment + windowing is correct.

## (d) Benchmark — emit was NOT the bottleneck (premise overturned)
Profiling one busy day (2025-07-01, 9.19M book events):

| Phase | time |
|---|---:|
| prep (ts coerce + tz_convert + stable sort, 9.19M rows) | **10.40s** |
| groupby aggregation | 0.64s |
| emit (vectorized) | 0.19s |
| **engine build total** | **~11s** |
| DuckDB build (research path) | **0.37s** |

The emit is already ~0.2s; vectorizing it is correct but does **not** move the total —
the cost is the pandas prep over ~9M events/day, which the emit refactor doesn't touch
and which pandas can't bring near DuckDB's columnar speed. So the engine's batch builder
stays ~11s/day. (The live **streaming** `CandleEngine` is unaffected — it's per-event,
no batch prep.)

## VERDICT
Emit vectorization is **byte-identical** and the **18:00 ET boundary is validated**
(zones/logic unchanged, every diff boundary-attributable, seam re-derived with no
look-ahead) — but the **performance goal is not met**: the emit was never the
bottleneck, so the pandas batch builder remains ~11s/day vs DuckDB's 0.37s. **Decision
needed:** keep DuckDB as the batch bar builder (engine owns the spec + streaming builder
+ parity test), or greenlight a full numpy rewrite of the batch builder's prep +
aggregation (beyond "only the emit") to approach DuckDB speed.

GATE: stopped here. No repointing of research, the emitter, or Trade-Lab.
