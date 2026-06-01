# Phase 4c — DuckDB as a parity-locked batch bar builder

Goal: keep DuckDB as research's batch bar builder, but make it **byte-identical** to the
engine's **streaming** builder on the same spec (18:00 ET boundary + a deterministic,
reader-independent order), so research-train and Trade-Lab-serve can never drift.

- DuckDB change: Claude-Quant-Lab branch `duckdb-18et-boundary` (commit 2f6aa62):
  `agents/data_infra/tick_store.py` (`build_tick_bars`, new `query_tick_events`) +
  `ml/dashboard_utility_builder.py` (`_build_bars_for_date` bounds). Decision layer NOT
  repointed; no retrain.
- Standing test: `strategy-core/validation/test_duckdb_streaming_parity.py` (pytest +
  runnable). Skips cleanly without the branch/data.

## 1. DuckDB query change (before → after)

**Before** (`build_tick_bars`):
```sql
WITH numbered AS (
  SELECT ts_event, (bid_px_00+ask_px_00)/2.0 AS mid, size,
         CAST(ROW_NUMBER() OVER (ORDER BY ts_event) - 1 AS BIGINT) AS rn      -- ties nondeterministic
  FROM (union) WHERE ts_event >= $1 AND ts_event <= $2 AND bid_px_00>0 AND ask_px_00>0 {sym}
)
SELECT (rn // N) AS bar_id, LAST(ts_event ORDER BY ts_event) AS bar_time,
       FIRST(mid ORDER BY ts_event) AS open, MAX(mid), MIN(mid),
       LAST(mid ORDER BY ts_event) AS close, SUM(size)
FROM numbered GROUP BY bar_id HAVING COUNT(*) = N ORDER BY bar_id     -- DROPS trailing partial
```
…with the window bounds passed as a **naive** `datetime(prev,23,0)`, which DuckDB cast
against the `TIMESTAMPTZ ts_event` using its session TZ (`America/Chicago`) → a 23:00-CT
window artifact. Four problems: (1) no trading-day partition, (2) `ORDER BY ts_event`
only → arbitrary tie resolution, (3) `HAVING` drops the partial, (4) naive bound → wrong TZ.

**After**:
```sql
WITH ev AS (
  SELECT ts_event, "sequence", size, bid_px_00, ask_px_00,
         (bid_px_00+ask_px_00)/2.0 AS mid,
         CAST((ts_event AT TIME ZONE 'America/New_York') + INTERVAL 6 HOUR AS DATE) AS trading_day
  FROM (union) WHERE ts_event >= $1 AND ts_event < $2 AND bid_px_00>0 AND ask_px_00>0 {sym}
),
numbered AS (
  SELECT *, CAST(ROW_NUMBER() OVER (
              PARTITION BY trading_day ORDER BY ts_event,"sequence",bid_px_00,ask_px_00,size
            ) - 1 AS BIGINT) AS rn
  FROM ev
)
SELECT trading_day, (rn // N) AS bar_index,
  FIRST(ts_event ORDER BY <order>) AS open_time, LAST(ts_event ORDER BY <order>) AS bar_time,
  FIRST(mid ORDER BY <order>) AS open, MAX(mid), MIN(mid), LAST(mid ORDER BY <order>) AS close,
  SUM(size) AS volume, COUNT(*) AS trade_count
FROM numbered GROUP BY trading_day, bar_index ORDER BY trading_day, bar_index   -- NO HAVING (keep partial)
```
Bounds are now **tz-aware UTC** `18:00 ET → UTC` (`_build_bars_for_date`). The 18:00-ET
trading day uses `ts_event AT TIME ZONE 'America/New_York' + 6h` (DST-aware), matching
`strategy_core.decisions.sessions.trading_day_for` instant-for-instant. `PARTITION BY
trading_day` resets `bar_index` at each 18:00-ET open; Sunday-evening Globex groups into
the Monday trading day.

## 2. Intrinsic tiebreak — and why `(ts_event, sequence)` is NOT enough

**Chosen order: `(ts_event, sequence, bid_px_00, ask_px_00, size)`.** Reader-independent
because every component is a field *in the data* (event time, venue matching-engine
`sequence`, the L0 book, trade size) — identical no matter how DuckDB or pandas physically
reads the parquet, unlike parquet/DataFrame row order (the source of the prior ~2.2%
open/close nondeterminism).

Why `sequence`/`ts_recv` alone fail (the make-or-break detail, measured on 2025-07-15):
- **154,289** book-valid front-month rows share a `(ts_event, sequence)`. databento emits
  a trade (`action='T'`) **plus its book consequences** (`'C'/'A'/'M'`) under one
  `sequence`, e.g. `T` with mid `22997.625` and `C` with mid `22997.750`.
- **52,828** `(ts_event, sequence)` groups have **>1 distinct mid** — whichever record is
  "last" sets the bar close, so the order is outcome-determining.
- `ts_recv` / `ts_in_delta` are **identical** for those records, so they don't break the tie.
- Appending the **mid determinants** `bid_px_00, ask_px_00` (plus `size`) makes every
  mid-differing record deterministically ordered. Residual ties (≈4,644 fully-identical
  rows) have identical `(mid, size)` → bar-irrelevant; both builders produce identical bars
  regardless of how those are ordered.

The same `order_clause` is used in DuckDB's `ROW_NUMBER`, every `FIRST/LAST`, and
`query_tick_events`' `ORDER BY` — so bucket boundaries and open/close are fully determined.

## 3. Trailing-partial handling — confirmed identical

The streaming `CandleEngine` emits the day's final `<N`-tick bucket as an `END_OF_DAY`
incomplete bar (`finalize_trading_day` / day rollover). DuckDB previously **dropped** it
(`HAVING COUNT=N`); now it **keeps** it (no HAVING) with `is_complete = trade_count==N`.
Verified: `trailing_partial(duck=1, stream=1)` on every sample day, and
`sum(trade_count) == events` (no print dropped).

## 4. Parity-test results — DuckDB-batch == engine-STREAMING, byte-for-byte

Feed the EXACT `query_tick_events` stream (composite-ordered) through the streaming
`CandleEngine`; compare every field (trading_day, bar_index, open/close ts, OHLC ticks,
volume, trade_count, is_complete, close_reason, bar_id).

| Day | kind | events | bars | trailing partial (duck/stream) | BYTE-IDENTICAL |
|---|---|---:|---:|---|---|
| 2025-07-15 | ties-heavy RTH | 11,775,272 | 80,104 | 1 / 1 | ✅ |
| 2025-07-07 | Sunday-Globex / 18:00-ET seam | 10,276,990 | 69,912 | 1 / 1 | ✅ |
| 2025-07-11 | ordinary RTH | 9,755,187 | 66,362 | 1 / 1 | ✅ |

**VERDICT: ALL BYTE-IDENTICAL** (incl. open/close, which the prior `(ts_event)`-only order
got wrong on ~2.2% of bars).

## 5. Caveat to ratify (surfaced, out of 4c scope)

The composite order is **not** databento's wire/emission order — no field captures the
sub-`sequence` record order, so the deterministic key sorts same-`sequence` records by their
resulting book + size instead. For research-batch == serving-streaming to hold in
**production**, Trade-Lab's replay/live feed must deliver events to the streaming engine in
this **same** `(ts_event, sequence, bid_px_00, ask_px_00, size)` order:
- **Replay**: a sort (it has all events) — straightforward, Trade-Lab-side.
- **Live**: events arrive in wire order; on a rare tie-straddling bar the live close could
  differ by a few ticks unless the adapter buffers same-`(ts_event,sequence)` records and
  reorders.
Cleaner long-term option: collapse each `(ts_event, sequence)` to one representative record
(the post-event book) before bucketing — makes `sequence` a true total order and is
tie-insensitive, but changes the bar definition (a retrain decision). Flagged for your call.

GATE: stop here. No decision-layer repoint, emitter fix, or retrain.
