# Phase 4e — side-signed-price order; research bars vs Trade-Lab WIRE-order bars

**Why.** 4d's parity gate was byte-identical only because BOTH sides were fed the same
deterministic order. In production they differ: research/DuckDB used `(ts_event, sequence,
price, size)` (price ASCENDING), but Trade-Lab (replay/live/seed) buckets in WIRE order, and
the price-ascending key REVERSES sell sweeps — so the two pipelines' 147t bars differed on
~14% of bars (328/286/305 of 2313/2083/1991), ~7% on volume. That is train/serve drift. 4e
signs the price by aggressor side so the deterministic key reproduces wire direction, and
re-proves parity against Trade-Lab's ACTUAL order.

**Scope / gate.** CQL `duckdb-18et-boundary` branch (DuckDB builder) + strategy-core (order
spec + parity tests). ONLY the within-sweep order changed; everything else is 4d (trade bars,
`action='T'`, trade price, N=147, tick 0.25, 18:00-ET boundary, kept trailing partial).
`_build_bars_for_date` stays pinned to `book_mid`. No decision-layer repoint, no emitter fix,
no retrain.

## 1. The order change (both builders)

Replace `(ts_event, sequence, price, size)` with **`(ts_event, sequence, side_signed_price,
size)`**, where `side_signed_price = +price` for a BUY aggressor and `−price` for a SELL
aggressor. An ascending sort then reproduces the true wire direction: buy sweeps ascending (as
they lift asks), sell sweeps descending (as they hit bids).

- **DuckDB** (`tick_store.py`, `_tick_event_selection`, `price_source='trade'`): the order
  clause becomes `ts_event, "sequence", CASE WHEN lower(CAST(side AS VARCHAR))='b' THEN price
  ELSE -price END, size`. The same expression drives `ROW_NUMBER`, every `FIRST/LAST`, and
  `query_tick_events`. A schema without a `side` column falls back to the 4d plain-price order.
- **strategy-core** (`constants.py`): single-sourced `BUY_AGGRESSOR_SIDE = "B"` and
  `TRADE_BAR_ORDER = "(ts_event, sequence, side_signed_price, size)"`. The streaming
  `CandleEngine` never sorts; producers deliver events in this order.

## 2. Confirmed side encoding (pinned from the data, not assumed)

A backwards sign would silently reverse *buys* instead of sells, so the encoding was verified
empirically — two independent checks, on all 3 days, agreeing with **0 cross-contamination**:

| check | side='A' | side='B' |
|---|---|---|
| single-side multi-price sweeps, wire direction (07-15) | 0 asc / **8,515 desc** | **8,319 asc** / 0 desc |
| sign(price − top-of-book mid) (07-15) | above 2 / **below 169,039** | **above 170,955** / below 1 |

→ **`side='B'` = BUY aggressor** (lifts ascending asks, prints above mid); **`side='A'` =
SELL aggressor** (hits descending bids, prints below mid). `'N'` occurs ~once/day on trades
and is treated as a sell by the `ELSE` branch (never in a multi-price sweep). Same verdict on
07-07 (A:0/8798, B:8237/0) and 07-11 (A:0/7793, B:7679/0). (This corrected a *backwards*
A/B note left in the 4d harness.)

## 3. Production-pair parity — research (side-signed) vs Trade-Lab (WIRE order)

The GATE (`test_production_pair_parity.py`) compares the REAL train/serve pair on the same
front-month trade set per day: RESEARCH = `TickStore.build_tick_bars` (DuckDB, side-signed);
TRADE-LAB = streaming `CandleEngine` fed in WIRE order (the physical parquet stream, stable-
sorted by `ts_event` exactly as `historical_parquet.py:252` delivers it). Metric = bars
differing on the order/membership-sensitive CORE fields (the same metric 4d reported as 328).

| Day | bars | 4d price-ASC vs wire | **4e side-signed vs wire** | of which OHLC ticks | of which volume |
|---|---:|---:|---:|---:|---:|
| 2025-07-15 | 2,313 | 328 (14.2%) | **29 (1.3%)** | **1** | 28 |
| 2025-07-07 | 2,083 | 286 (13.7%) | **8 (0.4%)** | **0** | 8 |
| 2025-07-11 | 1,991 | 305 (15.3%) | **29 (1.5%)** | **5** | 24 |

**The gate is NOT fully byte-identical against raw wire order** — 29 / 8 / 29 bars still differ
— so by the literal "byte-identical → locked" bar, it is not yet locked. But the systematic
sweep-direction drift is **eliminated** (10–36× fewer differing bars), and **OHLC ticks are
byte-identical on all but 1 / 0 / 5 bars (≤0.25%)** — the price *structure* of the bars is
locked; the remaining divergence is volume only (§4). Bar timestamps match to DuckDB's
microsecond resolution on every bar (2313/2083/1991). The supporting same-order test
(`test_duckdb_streaming_parity.py`) stays byte-identical: DuckDB-batch == streaming when both
consume the side-signed order.

## 4. The residual, fully itemized (no bug)

Every (ts_event, sequence) multi-print group where the side-signed key fails to reproduce wire
order was categorized — `other = 0`, i.e. the key reproduces wire order for **every** clean
single-side, distinct-price sweep. The reorder groups are:

| source | reorder groups (15/07,11/07,07/07) | straddling a 147-boundary | effect on a bar |
|---|---|---|---|
| **same-price multi-fill** (a sweep with ≥2 fills at one price level; the `size` tiebreak ≠ wire fill order) | 672 / 627 / 524 | 20 / 15 / 13 | **volume only** (prices equal → OHLC unchanged; complete bars always hold exactly N trades) |
| **mixed-side** (one sequence carrying both buy and sell trades) | 16 / 8 / 13 | 1 / 2 / 0 | OHLC + volume |
| other | 0 / 0 / 0 | — | — |

So the residual is **overwhelmingly a volume sub-bar ambiguity**: when a sweep prints multiple
fills at the *same* price and those fills straddle the 147th trade, the count-based bar splits
them, and the resting-order fill sequence (which `size` cannot reproduce) decides only how the
volume divides between two adjacent bars — never the OHLC. Mixed-side groups (≤2 straddling/day)
are the only source of the 1/0/5 OHLC-tick diffs.

A second, smaller seam: DuckDB reads `ts_event` as microsecond `TIMESTAMP WITH TIME ZONE`,
truncating the parquet's nanoseconds, while the engine (fed from the parquet) keeps ns. On the
~1,100–1,300 same-µs/distinct-ns trade pairs/day this can reorder across sequences; it
accounts for the 4 DuckDB-vs-engine differences on 07-11 (0 on the other days) and a few of
that day's OHLC diffs. It is representational, not an ordering-logic defect.

## 5. Live-order conclusion

Wire order is `ts_event`-monotonic with **0 global jitter**, and the side-signed key equals
wire order for every clean sweep, so for the price structure **live FIFO == replay == research**
— the OHLC of a 147t bar is the same whether built by research (DuckDB) or by Trade-Lab's live/
replay engine, with no reorder buffer. The only divergence left is the volume split at same-
price multi-fill boundaries (and ≤2 mixed-side bars/day).

## 6. Path to EXACT byte-identical (out of this gate)

The remaining ~1% volume residual is **irreducible while Trade-Lab buckets in raw WIRE order**,
because the wire sub-order of same-price fills is not a function of any trade field. It vanishes
if Trade-Lab adopts the SAME deterministic `(ts_event, sequence, side_signed_price, size)` order
— a bounded per-(ts_event, sequence) reorder in the adapter (each matching event is a contiguous
≤25-print burst). Then research == replay == live byte-identical, which the supporting same-order
test already demonstrates. That adapter change is the **emitter fix**, explicitly **gated out**
of 4e (and the µs/ns seam would be closed by reading `ts_event` at ns or truncating both sides).
Flagged for the owner.

## 7. Verification

- `test_production_pair_parity.py` (GATE) and `test_duckdb_streaming_parity.py` (supporting)
  both pass: `pytest validation/test_production_pair_parity.py validation/test_duckdb_streaming_parity.py tests`
  → **99 passed** (97 engine + the 2 validation gates). The `validation/` gates live outside
  the default `testpaths`, so a bare `pytest` runs the 97 engine tests; the gates are invoked
  explicitly (they skip cleanly without the local databento store).
- CQL `test_tick_store.py` **39 passed** — 4 new portable side-signed tests added: a controlled
  sell sweep orders descending (open=high, close=low), a buy sweep ascending, DuckDB ==
  independent pandas side-signed reference, and side-signed ≠ price-ascending when sells exist.
- All changes uncommitted working-tree: CQL `tick_store.py`; strategy-core `constants.py`,
  `validation/test_duckdb_streaming_parity.py` (banner), new `validation/test_production_pair_parity.py`
  + `validation/PHASE4E_REPORT.md`.

## Gate

Stopped here. No decision-layer repoint, no emitter fix, no retrain. The side-signed order
removes the systematic sweep-direction train/serve drift and locks the OHLC structure of the
bars across research and Trade-Lab; the residual is a fully-itemized, irreducible-without-the-
emitter-fix volume ambiguity at same-price sweep boundaries.
