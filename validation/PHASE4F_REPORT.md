# Phase 4f — us/ns ordering seam fix + decision-layer diff of the 4e bar residual

**Why.** 4e locked the OHLC *structure* of the production 147t trade-price tick bars (research
DuckDB side-signed vs Trade-Lab streaming WIRE order), leaving a ~1% residual: same-price
VOLUME sub-splits plus a handful of mixed-side OHLC bars and a DuckDB us/ns truncation seam.
4f does two things. **Part 1** fixes the one cheap *real* defect — the us/ns ordering seam in
the DuckDB trade-bar reader. **Part 2** runs the engine decision pipeline on BOTH bar sets as a
*measurement instrument* to answer the only question that matters: does the residual change any
DECISION output (levels, zones, touches, labels, features)?

**Scope / gate.** HARD GATE respected throughout: **no decision-layer repoint** of either repo;
**no emitter fix** (Trade-Lab `historical_parquet.py` still buckets in raw wire order — it does
NOT adopt the deterministic key); **no retrain**; CQL `_build_bars_for_date` stays **pinned to
`price_source="book_mid"`**. All changes left **UNCOMMITTED** (4d/4e convention). CQL HEAD still
`2f6aa62` (branch `duckdb-18et-boundary`); SC HEAD still `4ce2e61` (branch `main`). Stopped at
the verdict — the fix below is *measured*, not *implemented*.

---

## PART 1 — the us/ns ordering seam fix (CQL `tick_store.py`, trade path only)

**Root cause.** The parquet `ts_event` column is `timestamp[ns, tz=UTC]`. DuckDB `read_parquet`
materializes it as `TIMESTAMP WITH TIME ZONE`, which is inherently **microsecond** and cannot
hold tz-aware nanoseconds — so the sub-microsecond part is truncated. When two trades share the
same microsecond but carry distinct nanoseconds and straddle a 147-trade bar boundary, the
DuckDB order can disagree with the engine's nanosecond-resolution wire order. On 07-11 this
reordered exactly 4 bars (this was the "second, smaller seam" §4 of the 4e report).

**What changed (ordering-only, trade path only).** In
`C:/Users/gonza/Documents/Claude-Quant-Lab/src/alpha_lab/agents/data_infra/tick_store.py`:

- New `TickStore._ns_keyed_relation`: reads only the trade columns of the registered parquet(s)
  via pyarrow and appends a BIGINT `ts_event_ns = cast(cast(ts_event, ts[ns,UTC]), int64())`
  (the double-cast normalizes us OR ns inputs to the true parquet nanosecond), concats
  multi-date, registers it as a DuckDB relation, and caches it by path-set.
- In `_tick_event_selection`, **for `price_source=='trade'` ONLY**: the union swaps to the
  ns-keyed relation, `ts_order_key='ts_event_ns'`, and both the side-signed and the no-side
  `order_clause`s now **LEAD with `ts_event_ns`** instead of `ts_event`. `ROW_NUMBER` and every
  `FIRST/LAST` reference `{order_clause}`, so the ns tie-break leads everywhere.
- **Output `ts_event` is unchanged.** `open_time`/`bar_time` still come from `FIRST/LAST(ts_event …)`
  (us `TIMESTAMPTZ`); the 18:00-ET `_SQL_TRADING_DAY` cast and the `[start,end)` window still use
  the unchanged us `ts_event`. `ts_event_ns` never leaks into `build_tick_bars` /
  `query_tick_events` output (still exactly `[ts_event, price, size]`).
- **`book_mid` is byte-unchanged** — it bypasses the ns relation and uses the plain
  `read_parquet` view. A no-files fallback restores the 4e us ordering for in-memory-only views.

### Gate numbers — BEFORE → AFTER (research side-signed vs Trade-Lab wire)

| Day | bars | bars-diff vs wire | OHLC ticks | volume | `duck_vs_engine_signed` |
|---|---:|---:|---:|---:|---:|
| 2025-07-15 | 2,313 | 29 → **29** | 1 → **1** | 28 → **28** | 0 → **0** (no seam this day) |
| 2025-07-07 | 2,083 | 8 → **8** | 0 → **0** | 8 → **8** | 0 → **0** (no seam this day) |
| 2025-07-11 | 1,991 | 29 → **25** | 5 → **5** | 24 → **20** | **4 → 0** (seam closed) |

**The us/ns seam is VOLUME-ONLY.** Closing it on 07-11 dropped `duck_vs_engine_signed` 4 → 0 and
`bars-diff` 29 → 25 — *exactly the 4 seam bars* — and those 4 were *all volume diffs*:
`volume` 24 → 20 while **OHLC ticks stayed 5 → 5**. The fix produces **0 OHLC change** on every
day (07-15 stays 1, 07-07 stays 0, 07-11 stays 5).

**This refines the 4e report.** 4e §4 said the us/ns seam accounted for "a few of that day's
OHLC diffs." That is **incorrect**: the seam caused *no* OHLC diffs at all — it was purely a
volume reorder. The residual OHLC diffs (1/0/5) are the **mixed-side aggressor residual**, not
the seam. 07-15 and 07-07 had `duck_vs_engine_signed=0` before the fix (no same-us/distinct-ns
trade ties straddling a boundary), so they are byte-unchanged. The seam-attributable diffs on
07-11 are **gone**.

---

## PART 2 — decision-layer diff (engine pipeline as a measurement instrument)

**Setup.** New harness `validation/decision_diff_harness.py` builds BOTH 147t trade-price bar
sets on the same front-month trade set per day:

- **RESEARCH** = CQL `TickStore.build_tick_bars(price_source='trade')` (DuckDB side-signed).
- **TRADE-LAB** = streaming `CandleEngine(scheme=RESEARCH_SESSION_SCHEME, tf=(147,))` fed the
  physical stream stable-sorted by `ts_event` (the verbatim gate `_read_phys` / wire path ==
  `historical_parquet.py:252`), finalized for the partial.

The FULL engine pipeline then runs on EACH bar set: engine-native levels (asia/london H/L from
this day's bars bucketed by `classify_session(close)`; PDH/PDL from the prior NY-RTH day built
with the SAME pipeline, walking back past weekends/holidays) → `build_zones` → `detect_touches`
(tick=0.25) → `classify_session` (ny_rth eligibility) → `resolve_outcome` (forward bars strictly
after the touch bar, truncated 16:15 ET, MAE-first, tp=15/sl=30/trap_mfe_min=5) → the 6 features
(windows anchored at the touch close **floored to us**, neutralizing the us/ns seam; the feature
streams read bar-set-INDEPENDENT DuckDB trade/quote data).

### Per-day decision diff (research bars vs trade-lab bars)

| Day | levels | zones | touches (R/TL · matched/diff) | labels | features (max abs diff) | ny_rth touches |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| 2025-07-09 | identical | identical | 5/5 · 5/0 | identical | identical (0.0) | 1 |
| 2025-07-10 | identical | identical | 5/5 · 5/0 | identical | identical (0.0) | 1 |
| 2025-07-11 | identical | identical | 5/5 · 5/0 | identical | identical (0.0) | 0 |
| 2025-07-14 | identical | identical | 5/5 · 5/0 | identical | identical (0.0) | 1 |
| 2025-07-15 | identical | identical | 5/5 · 5/0 | identical | identical (0.0) | 0 |
| 2025-07-16 | identical | identical | 5/5 · 5/0 | identical | identical (0.0) | 0 |
| 2025-07-17 | identical | identical | 5/5 · 5/0 | identical | identical (0.0) | 0 |
| 2025-07-18 | identical | identical | 5/5 · 5/0 | identical | identical (0.0) | 0 |
| 2025-07-07 | identical | identical | 6/6 · 6/0 | identical | identical (0.0) | 1 |

**Days run: 9** (the 3 core days 07-07/07-11/07-15 plus an `--extended` run 07-09…07-18). 07-08
and 07-12 are missing from the store; 07-13 (Sunday) skips cleanly — its window
`[07-12 18:00 ET, 07-13 18:00 ET)` has 0 front-month trades.

**Result: zero decision divergence on every day.**
- **Levels identical every day**, including PDH/PDL — and each pipeline derives PDH/PDL from
  ITS OWN prior-day bars, yet both independently produced the same values (e.g. 07-11 both =
  23090.0/22901.25 from 07-10; 07-07 both walked back past 07-06 Sunday and missing 07-05 to
  the 07-04 July-4 half-day NY-RTH = 22945.5/22888.0). **The residual does NOT propagate through
  the PDH/PDL carry.**
- **Zones identical every day** (e.g. 07-11: 6 zones, byte-identical names/sides/rep prices).
- **Touches identical every day**: per-day matched == research == trade-lab count (5 or 6),
  `differing=0` — the touch KEY sets (level_type, direction, under-us touch ts, rep_price) are
  byte-identical between the two bar sets.
- **No label flips on any day (0/9).**
- **No feature diffs above epsilon**: `features_identical=True` every day, max abs diff = 0.0 <
  1e-6 across all 6 features on every matched touch.

**Why the residual is fully absorbed.** The decision layer reads only `high_ticks`/`low_ticks`/
`close_ticks` (never volume) for levels/zones/touches/labels, so the same-price VOLUME sub-split
residual is invisible to it by construction. Feature windows read bar-set-INDEPENDENT DuckDB
trade/quote streams anchored at the touch close floored to us. On every tested day the few
mixed-side OHLC-differing bars (1/0/5) never coincided with a session-extreme bar, a
zone-straddling first-touch bar, or shifted any touch anchor across a us boundary — so the
residual is absorbed before any decision output. **There is no differing decision to trace back
to a residual source: there are none.**

---

## VERIFICATION

Three independent reviews plus regression. **Adversarial correctness review (Part 1):**
`ts_event_ns` independently proved bit-exact to native parquet ns over ~11M rows (total abs diff
= 0); forcing the pre-fix us fallback (`_ns_keyed_relation → None`) reproduced the reported 07-11
BEFORE exactly (`gate29, ohlc5, vol24, duck_vs_signed4`), confirming the fix drops gate 29→25 /
vol 24→20 with OHLC unchanged — i.e. the seam is **volume-only**, corroborating the refinement of
the 4e claim; output `ts_event` confirmed to stay us with no ns leak; `book_mid` confirmed
byte-unchanged and pinned. **Adversarial review (Part 2):** all imports/call-signatures match the
real `strategy_core` source; the two bar sets confirmed to genuinely DIFFER on 07-11 (25/5/20,
non-vacuous); diff metrics shown **sensitive by injection** (a ±250pt bar perturbation surfaced
levels/zones/touches divergence; a corrupted matched label produced exactly 1 detected flip).
**Independent re-derivation:** a separate script (not importing the harness) rebuilt both 07-11
bar sets, re-derived levels/zones/touches, and matched every Part-2 07-11 number exactly
(levels identical, 6/6 zones, 5/5 touches, 0 differing). **Issues found:** only minor, benign,
fully-disclosed observations — (a) `main()`'s verdict triggers on `any_touch_diff>0` while the
standing test tolerates `≤1` (immaterial: measured reality is 0); (b) the 07-07 PDH/PDL walk-back
lands on the 07-04 half-day rather than the task's expected ~07-03, but BOTH pipelines agree
exactly so it does not affect the diff; (c) the harness keeps all touches (strictly more
conservative for diffing). **No defects, leakage, look-ahead, or verdict-logic errors.**
**Regression:** CQL `test_tick_store.py` **40 passed**; SC engine **97 passed**; SC gates
(`test_production_pair_parity` + `test_duckdb_streaming_parity`) **2 passed**; new
`validation/test_decision_diff.py` **PASSES** (and green together with both 4e gates: 3 passed).
**All green.**

---

## VERDICT

> **LOCKED-ENOUGH (→ repoint + retrain).** The decision outputs are **identical on all 9 tested
> days** — 0/9 label flips, touch KEY sets byte-identical (differing=0 every day), feature max
> abs diff = 0.0 (< 1e-6), and levels/zones identical including the independently-derived PDH/PDL
> carry. The 4e/4f bar residual (same-price volume sub-splits + ≤5 mixed-side OHLC bars/day) is
> **measured-immaterial**: it never reaches a decision output. **Do NOT implement the emitter
> reorder.** The us/ns fix (Part 1) is a real, in-scope, volume-only correction and is the only
> change warranted.

The verdict is based strictly on the measured Part-2 outputs (no differing decision exists to
attribute to the emitter residual), so **EMITTER-FIX-WARRANTED is not triggered**.

---

## Gate

Stopped at the verdict. **No decision-layer repoint** of either repo, **no emitter fix**
(`historical_parquet.py` still buckets in raw wire order), **no retrain**; CQL
`_build_bars_for_date` remains pinned to `price_source="book_mid"`. CQL HEAD unchanged at
`2f6aa62`; SC HEAD unchanged at `4ce2e61`; `git diff` of `src/strategy_core/decisions` and
`candles` is empty. All changes UNCOMMITTED: CQL `tick_store.py` (Part 1); two new SC files
`validation/decision_diff_harness.py` + `validation/test_decision_diff.py` (Part 2) and this
report.
