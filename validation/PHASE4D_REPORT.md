# Phase 4d — Trade-price tick bars; DuckDB == streaming parity re-proven

**Decision (ratified):** production bars are **TRADE-PRICE TICK BARS** — a "tick" is a
*trade* (databento `action='T'`), not a book event. This supersedes the phase-4c book-mid
bars that parity was first proven on. All of 4c's machinery is reused unchanged: the 18:00-ET
trading-day boundary, the deterministic reader-independent order, the kept trailing partial,
and the standing parity test. The book-mid path is kept reachable (`price_source='book_mid'`)
for comparison and the documented reversal path.

**Scope / gate:** changes live only on the CQL `duckdb-18et-boundary` branch (the DuckDB
builder) and in strategy-core (engine bar spec + constants + the parity test). The decision
layer is **not** repointed, the emitter is **not** changed, and **no retrain** is performed.
`TickStore.query_tick_feature_rows` (the decision-layer feature stream) is deliberately
untouched — 4d switches only the **bar** definition.

Because `build_tick_bars` now *defaults* to `price_source='trade'`, its one decision-layer
caller — `_build_bars_for_date` in `ml/dashboard_utility_builder.py` — is **explicitly pinned
to `price_source='book_mid'`** so the decision/dashboard pipeline keeps producing exactly the
phase-4c bars it was built/trained on. This keeps 4d **side-effect-free downstream**: the
trade-bar default applies only to the production-bar consumers that opt in (the parity test,
research/Trade-Lab tooling that asks for production bars). Flipping that caller to `'trade'` is
the explicit, reviewed **phase-7 retrain** cutover, not a silent default flip. (Both the
adversarial review and the completeness critic independently flagged the un-pinned default as
an implicit decision-layer repoint; pinning resolves it.)

**Status:** all changes are uncommitted working-tree edits (CQL `tick_store.py`,
`ml/dashboard_utility_builder.py`, `tests/agents/test_tick_store.py` on branch
`duckdb-18et-boundary`; strategy-core `constants.py`, `validation/test_duckdb_streaming_parity.py`,
plus new `validation/PHASE4D_REPORT.md` + `validation/phase4d_liveorder.py` on `main`). Nothing
is committed yet.

## 1. Bar-spec change (applied identically in both builders)

| | phase-4c (book-mid) | **phase-4d (trade-price)** |
|---|---|---|
| a "tick" is | any book-valid event | a **trade** (`action='T'`) |
| bar price | `(bid_px_00 + ask_px_00) / 2` | the **trade `price`** |
| price grid / `tick_size` | 0.125 (mids land on half-ticks) | **0.25** (NQ trade grid) |
| volume | Σ event size | Σ trade size |
| a bar closes on | the Nth event | the **Nth trade** (default **N = 147**) |
| deterministic order | `(ts_event, sequence, bid_px_00, ask_px_00, size)` | **`(ts_event, sequence, price, size)`** |
| trading-day boundary | 18:00 ET (DST-aware) + `bar_index` reset | unchanged |
| trailing partial | kept (END_OF_DAY) | unchanged |

**Trade prints are lossless at `tick_size=0.25`:** over a full 18:00-ET day the off-grid
trade count is **0** on every sample day (`|price/0.25 − round(price/0.25)| < 1e-9` for all
trades), so the engine's integer-tick `Bar` representation is exact — the same losslessness
book mids had on the 0.125 grid.

**The streaming `CandleEngine` needs no logic change.** It already accepts only `Trade`
events and closes a bar at `trade_count == N`, building OHLC from whatever `price_ticks` it is
fed (`candles/streaming.py`). The 4c book-mid parity test merely fed it book mids as synthetic
"trades"; 4d feeds it real trades. `DEFAULT_TICK_SIZE` was already `0.25` (the NQ trade grid);
the only `0.125` left in the engine path was the parity test's local constant, now reverted to
`0.25`. New single-sourced constants: `BAR_PRICE_SOURCE = "trade_price"`, `DEFAULT_TICK_COUNT
= 147` (distinct from `MID_PRICE_SOURCE`, which governs the interaction *features*, not the
bars).

**DuckDB builder** (`tick_store.py`): `build_tick_bars` / `query_tick_events` /
`_tick_event_selection` gained a `price_source` argument defaulting to `"trade"`. For trades
it filters `lower(CAST(action AS VARCHAR)) = 't'` (a trades-only file with no `action` column
is already all trades), prices OHLC from the trade `price`, and orders by `(ts_event,
sequence, price, size)`. Everything else (18:00-ET `PARTITION BY trading_day`, no-`HAVING`
kept partial, half-open `[start, end)`, front-month filter) is the 4c code path.

## 2. Trade-bar tie surface (vs book-mid's 52,828/day)

A `(ts_event, sequence)` is not a total order: databento emits multiple records under one
sequence. For **trades** those are the prints of one matching event — a sweep that lifts/hits
successive levels. Measured per 18:00-ET day (front-month):

| Day | trades | multi-price `(ts,seq)` groups | book-mid was | non-monotonic sweeps | max prints/seq |
|---|---:|---:|---:|---:|---:|
| 2025-07-15 | 339,997 | 16,903 | 52,828 | 0 | 16 |
| 2025-07-07 | 306,103 | 17,109 | 52,828 | 2 | 25 |
| 2025-07-11 | 292,586 | 15,531 | 52,828 | 1 | 17 |

The multi-price surface is ~3× smaller than book-mid's, and — the important property — the
prints within a sweep are **price-monotonic** (only 0–2 non-monotonic groups/day, vs book-mid
where the 52,828 groups mixed a `T` with its `C`/`A`/`M` book consequences at *non-monotonic*
mids). So `price` is a faithful, reader-independent ordering field for trades, and any residual
fully-identical tie is bar-irrelevant.

## 3. Trailing partial — unchanged, confirmed

DuckDB keeps the day's final `<N`-trade bucket (no `HAVING`) as an `is_complete=False` bar;
the streaming engine emits it via `finalize_trading_day` as `END_OF_DAY`. Both produce exactly
**1** trailing partial per day, and `Σ trade_count == trades` (no print dropped).

## 4. Parity — DuckDB-batch == engine-STREAMING, byte-for-byte

Feed the EXACT `query_tick_events` trade stream (composite-ordered) through the streaming
`CandleEngine`; compare every Bar field (trading_day, bar_index, open/close ts, OHLC ticks,
volume, trade_count, is_complete, close_reason, bar_id).

| Day | kind | trades (events) | bars (147t) | trailing partial (duck/stream) | BYTE-IDENTICAL |
|---|---|---:|---:|---|---|
| 2025-07-15 | ties-heavy RTH | 339,997 | 2,313 | 1 / 1 | ✅ |
| 2025-07-07 | Sunday-Globex / 18:00-ET seam | 306,103 | 2,083 | 1 / 1 | ✅ |
| 2025-07-11 | ordinary RTH | 292,586 | 1,991 | 1 / 1 | ✅ |

**VERDICT: ALL BYTE-IDENTICAL.** Trade-bar cadence is visible vs the old book-event count: the
same days produced **80,104 / 69,912 / 66,362** book-mid bars in 4c — trade bars are ~35×
coarser (trades are ~3% of book events: e.g. 2025-07-15 had A=4,828,779 C=4,784,886 M=1,821,610
**T=339,997**).

Regression: strategy-core unit suite **97 passed**; CQL `test_tick_store.py` **35 passed** —
27 pre-existing plus **8 new** portable trade-bar tests (added in 4d): trade bars vs an
independent pandas bucketer (byte-equal, **no local-store dependency**), `action='T'`
filtering, the `book_mid` path counting all book events, `query_tick_events` columns/filter,
the no-`action`-column all-trades fallback, and the missing-`price` / unknown-source /
missing-`sequence` raises. (The standing DuckDB↔streaming byte-parity test above needs the
local databento store; these unit tests give the trade-bar SQL portable CI coverage — closing
the review's coverage-gap note.)

## 5. Live-order finding (closes the 4c §5 caveat for trade bars)

4c §5 flagged that the composite order is **not** databento wire order, so for production
parity Trade-Lab's live/replay feed must deliver events in the same order. For trade bars the
picture is now precise (`validation/phase4d_liveorder.py`):

1. **No global arrival jitter.** The wire/emission order is already **ts_event-monotonic** —
   `0` ts_event inversions on every day — so bucketing in arrival order vs ts_event order
   produces identical bars (`TE == PHYS`, 0 differing bars). No large reorder window is needed.

2. **The only divergence is within a matching event, and it is the composite key's
   price-ASCENDING tiebreak reversing *descending* (sell) sweeps.** On 2025-07-15 the 16,903
   multi-price sweeps split **8,336 ascending (buy)** / **8,530 descending (sell)** / **0
   non-monotonic**. The composite key sorts price ascending, so it reproduces wire order for
   buy sweeps but **reverses** sell sweeps. Where a reversed sweep straddles a 147-trade bucket
   boundary, membership/open/close shift: **composite vs raw-wire differs on 328/2,313 bars
   (≈14%)**, of which **172 (≈7%)** differ on `volume` (i.e. the bucket boundary moved).
   high/low/volume/trade_count are order-free *within* a bucket; only boundary-straddling
   sweeps matter.

3. **The required reorder is bounded and trivial.** Each matching event's prints are a
   **contiguous** monotonic wire burst (`0` non-contiguous groups), ≤ ~25 prints. So a live
   adapter that buffers one `(ts_event, sequence)` burst and emits it price-ascending
   reproduces the composite order exactly → **live == replay**. This is far cheaper than the
   book-mid case (which had to buffer across `T` + `C`/`A`/`M` records with non-monotonic mids,
   52,828 mixed groups/day). Replay, having all events, just sorts.

**What Trade-Lab actually does today (code-level).** All three Trade-Lab bar paths bucket in
**wire / `ts_event`-stable order**, never the research composite: replay does a single stable
`sorted(..., key=event_ts_utc)` (`adapters/historical_parquet.py:252`); live is pure FIFO wire
delivery (`adapters/databento.py:239` → `services/live.py:226`); the warm-up seed builder does
`sort_values('ts_event', kind='stable')` (`services/seed.py:84`); and `CandleEngine` itself
never reorders (`domain/candles.py:123`). So Trade-Lab is internally consistent (replay == live
== seed == wire) and chronologically faithful — and since wire order is `ts_event`-monotonic
with `0` jitter, its bars equal the raw-wire bars. The aggressor `side` is carried end-to-end
into `TradeEvent.side` (`historical_parquet.py:285`, `databento.py:344`) but is consumed only by
the decision-layer `MarketContextBuffer`, **never for bucketing**. So the divergence is precisely
*research-DuckDB-composite (price-ASC)* vs *Trade-Lab-wire*; it is the **research** order that
reorders (reverses sell sweeps), not Trade-Lab.

**Answer to "does live wire order reproduce `(ts_event, sequence, price)` with no reordering?"**
— **No.** ~half of sweeps are descending and the ascending-`price` composite key reverses them,
so the composite order is *not* what Trade-Lab's replay/live/seed produce; on ~14% of 147t bars
(7% on volume) the research-composite bars and the Trade-Lab-wire bars differ. The reorder that
would close the gap is a single contiguous matching-event burst (or the side-signed-price order
below). **The DuckDB↔streaming parity gate itself is unaffected** — it is byte-identical only
because *both* of its sides consume the composite order; it does not exercise the live path.

**Recommended spec refinement (flagged, out of 4d's gate — it changes the bars).** The
databento aggressor **`side`** is fully populated on trades (A=170,956 / B=169,041, 0 `N` on
2025-07-15) and is single-valued within all but **32 / 24 / 19** multi-price sweeps per day
(2025-07-15 / 07-07 / 07-11; out of ~16–17k). A deterministic **side-signed-price** order —
`(ts_event, sequence, +price if side='A' else −price, size)` — would reproduce *chronological
wire order* directly (ascending for buys, descending for sells) down to the ~20–32 mixed-side
groups/day, while staying reader-independent (every key field is in the data). Adopted in
**both** the DuckDB builder *and* the engine spec — and matching Trade-Lab's already-chronological
wire order — it would make research == replay == live with no reorder buffer at all, the cleanest
resolution. It changes the sell-sweep boundary bars, so it needs a re-prove and carries retrain
implications → owner's call, the same way the 4c §5 caveat was flagged.

## Gate

Stopped here. No decision-layer repoint, no emitter fix, no retrain. The bar definition is
switched in both builders, parity is re-proven byte-for-byte on trade bars, and the live-order
caveat is quantified and (for the parity gate) closed.
