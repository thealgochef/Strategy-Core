# strategy-core

A shared, versioned strategy **engine** for zero-drift parity between
**Claude-Quant-Lab** (research / model training, batch over parquet) and
**Trade-Lab** (live + replay inference, streaming).

The research lab is a *strategy factory*: you configure a strategy there and it
trains an ML model. Whatever strategy produced a given model, Trade-Lab must then
execute **exactly the same** — zero drift. This package is the single
implementation both repos import (the candle layer, the decision layer, and the
contract schema), so a strategy configured in research executes identically in
Trade-Lab, while research stays free to vary the strategy via config.

> Status: **engine package complete and tested (97 passing tests).** Repointing
> the two repos onto it (the live migration) is staged but not yet applied — see
> [`MIGRATION.md`](MIGRATION.md).

---

## Install

```bash
pip install -e .            # runtime: numpy + pydantic
pip install -e ".[dev]"     # adds pytest + pandas (batch builder & parity test)
python -m pytest            # 97 passed
```

The base import pulls **only numpy + pydantic + stdlib**. pandas is loaded lazily
and only when the batch candle builder is actually called — so the streaming
runtime never pays for it.

## Layout

```
src/strategy_core/
  __init__.py        ENGINE_VERSION, CONTRACT_VERSION, public API re-exports
  types.py           neutral Trade/Quote/Bar/Level/Zone/Touch/SessionScheme (stdlib only)
  constants.py       single source of every magic value + the canonical ET session scheme
  candles/
    streaming.py     CandleEngine — event-at-a-time tick bars (promoted from Trade-Lab)
    batch.py         build_tick_bars_from_frame — vectorized (pandas), parity-locked to streaming
    _ids.py          make_bar_id
  decisions/         pure, scalar, config-driven — no pandas, no IO
    zones.py         build_zones
    touch.py         is_touch + detect_touches (first-touch-per-zone)
    sessions.py      classify_session / trading_day_for (ET)
    features.py      the interaction + approach feature formulas
    outcomes.py      classify_mae_first + resolve_outcome (MAE-first)
  contract/
    schema.py        Pydantic StrategyContract (+ engine_version)
    loader.py        strict, fail-closed loader
tests/               candle parity + golden per-module unit tests
```

## Two version stamps

| Stamp | Meaning | When it changes |
|---|---|---|
| `ENGINE_VERSION` = `strategy_core_engine_v1` | The **structural** version of the engine. A model binds to the engine version that produced its features/labels. | Only when a genuinely new *mechanism* is added (new touch rule, feature family, label scheme). **Never** for a parameter change. |
| `CONTRACT_VERSION` = `trade_lab_contract_v1` | The version of the `strategy.json` *format* (schema). | When the contract schema shape changes. |

A prediction is only meaningful under its own engine version + config. The contract
carries `engine_version`; `load_strategy_contract(path, expected_engine_version=ENGINE_VERSION)`
**fail-closes** when they don't match — this is the hook Trade-Lab uses to refuse a
model whose engine it cannot reproduce.

## Two kinds of flexibility

- **Parameter** changes (bar size, zone width, sessions, tp/sl, feature windows) are
  **config-only** and instant — carried by the contract, read by the engine.
- **Structural** changes (a new mechanism) are **one engine change + an
  `ENGINE_VERSION` bump** — rare, and drift-proof because it's one change in one place.

---

## ⚠️ The `mid_price_source` decision — read before training or repointing

The interaction features (`int_time_beyond_level`, `int_time_within_2pts`,
`int_absorption_ratio`) in this engine use the **trade print price** over the trade
stream. `constants.MID_PRICE_SOURCE == "trade_price"`.

This is a **deliberate strategy standardization** (ratified by the strategy owner),
and it **diverges from the legacy training path**, which actually computed these
features over a **top-of-book mid**:

> `query_tick_feature_rows` selects `price = (bid_px_00 + ask_px_00) / 2.0` over
> *book* events (`tick_store.py:264,287`), so the builder's `mid = ticks["price"]`
> (`dashboard_utility_builder.py:488`) is a book mid, not a trade print. The `mid`
> variable name was the tell. (The earlier audit and the spec's "trade price"
> reading were both fooled by that variable.)

**Consequence:** the currently-deployed model was trained on TOB-mid features and is
**NOT compatible** with this engine. Any model served under `strategy_core_engine_v1`
**must be retrained** with the research path repointed onto this engine (so its
interaction features are trade-price). The `engine_version` fail-close is exactly
what stops Trade-Lab from silently serving the old model under the new feature
definition. See [`MIGRATION.md`](MIGRATION.md) §"Retrain gate".

The three *approach* features (`app_large_trade_vol_pct`, `app_avg_trade_size`,
`app_max_spread`) are unchanged from the canonical DuckDB aggregates — already
trade/L0-based — so they carry over without a retrain concern of their own.

---

## What is canonical (preserved exactly)

Everything else is ported byte-for-byte from the research **training** path
(`dashboard_utility_builder.py` + `dashboard_utility_labeling.py`), which is the
reference behavior because it is literally the code that produced the model's
labels and features:

- **Zones** — merge levels within `3.0` pts (compared against the *last* level in the
  open group, so chains can exceed 3.0 total); representative price = mean; side by
  strict majority (ties → LOW). (`build_zones`)
- **Touch** — closed-interval `bar_low <= zone_rep <= bar_high`, first-touch-per-zone
  via the `touched` flag, low→LONG / high→SHORT. (`detect_touches`)
- **Sessions (ET)** — asia 18:00→01:00 (crosses midnight), london 01:00→08:00,
  ny_rth 09:30→16:15; 18:00 ET trading-day rollover (`>=`); the 08:00–09:30 and
  16:15–18:00 ET gaps classify as `none`. (`classify_session`)
- **Outcomes** — MAE checked **first** each bar, so a bar breaching both stop and
  target resolves to the **loss**; trap vs blowthrough split at `trap_mfe_min`.
  (`classify_mae_first`, `resolve_outcome`)
- **Candles** — close at `trade_count == N`; per-(timeframe, trading-day) bar index;
  day-rollover freezes the open bar `END_OF_DAY`. Two builders (streaming + batch)
  are **parity-locked** by `tests/test_candle_parity.py`. Now parameterized by
  `SessionScheme` (ET by default) instead of hardcoded Chicago.

Single-sourced magic values (no more "restated literals" in the emitter):
`ZONE_PROXIMITY_PTS=3.0`, `WITHIN_BAND_PTS=2.0`, `LARGE_TRADE_THRESHOLD=10`,
`LEVEL_PROXIMITY_PTS=0.5`, the ET session windows, the 18:00 boundary, the 16:15
cutoff — all in `constants.py`, read by both the engine and (after repointing) the
contract emitter.

## Open parity items (resolve during the cross-repo parity pass, phase 7)

These are documented in the relevant module docstrings and do **not** affect the
package's internal correctness; they are train-vs-serve boundary questions:

1. **Touch timestamp: bar open vs close.** Canonical stamps the touch with the bar's
   *index* timestamp; this engine uses `bar.close_ts_utc`. The choice shifts the
   feature window anchor by one bar. (`decisions/touch.py`)
2. **Tick-aligned bar prices.** Touch/outcome math compares `ticks * tick_size`;
   exact only if bar highs/lows are integer multiples of `tick_size` (true for
   trade-derived OHLC, worth confirming for any non-tick source). (`touch.py`, `outcomes.py`)
3. **Absorption `size` source.** Under the trade-price decision the engine sums
   *trade* size; confirm the retrained dataset uses the same. (`features.py`)
4. **`< 5`-tick interaction-window drop.** A dataset-construction filter; lives in
   the adapter, not the pure formulas. (`features.py`)

## Testing

```bash
python -m pytest            # 97 passed in ~0.5s
```

`tests/test_candle_parity.py` is the keystone: it feeds one deterministic trade
stream (crossing the 18:00 ET boundary) through both candle builders and asserts
the `Bar` lists are field-for-field identical — under both the ET research scheme
and the CT reference scheme.
