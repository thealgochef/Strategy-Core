# strategy-core

Shared, versioned strategy engine for zero-drift parity between **Quant-Lab** research/training and **Trade-Lab** live/replay inference.

`strategy-core` owns the strategy mechanics that must not drift: Databento historical/live normalization boundaries, deterministic event ordering, replay/runtime state, tick bars, sessions, zones, first-touch detection, feature formulas, outcome resolution, honest decision-time entry orchestration, and the versioned `strategy.json` schema/loader.

> Current status, verified 2026-06-08: **engine v3 plus the shared market-data runtime are implemented and unit-tested**. `uv run --python 3.14 python -m pytest -q` passes; `pytest --collect-only -q` reports **135 tests** across 18 test files. Quant-Lab imports this engine for dashboard-utility training and contract emission. Trade-Lab backend now routes replay/live runtime bars, sessions, levels, zones, and touches through a Strategy-Core adapter, but model-bundle activation/parity remains gated; see [`V3_COMPATIBILITY_MATRIX.md`](V3_COMPATIBILITY_MATRIX.md) and [`MIGRATION.md`](MIGRATION.md).

---

## Install / verify

```bash
pip install -e .
pip install -e ".[dev]"      # pytest + pandas for batch candle builder tests
pip install -e ".[databento]" # optional real Databento SDK integration
python -m pytest -q          # 135 tests passing as of 2026-06-08
python -m pytest --collect-only -q
```

Runtime import intent: stdlib + `numpy` + `pydantic`; pandas is loaded lazily by the batch candle builder only. Databento SDK imports are optional and occur only when an explicit live source is started.

---

## Version stamps

| Stamp | Current value | Meaning |
|---|---:|---|
| `PLATFORM_VERSION` | `strategy_core_platform_v1` | Structural platform (decision/candle) semantics that a model bundle binds to (the engine axis renamed at E1; per-plugin `strategy_version` is the second axis). A mismatch must fail closed. |
| `CONTRACT_VERSION` | `trade_lab_contract_v2` | Shape/version of `strategy.json`. v2 carries the two-axis binding: required `platform_version` + `strategy_version`, `label_policy.decision_offset_minutes`, and optional research audit metadata. |

`load_strategy_contract(path, expected_platform_version=PLATFORM_VERSION)` rejects stale bundles before they can be served.

---

## v3 canonical strategy semantics

These are the current engine constants and code paths, not historical validation assumptions:

| Area | v3 behavior |
|---|---|
| Bars | Production bars are **trade-price tick bars** (`BAR_PRICE_SOURCE="trade_price"`) on the NQ 0.25 grid. Default touch bar count is `147t`; streaming and batch builders are parity-tested. |
| Trade ordering | Deterministic order is `(ts_event, sequence, side_signed_price, size)` so sell sweeps are not reversed. |
| Sessions | ET-native, DST-aware. Trading-day boundary remains **18:00 ET**. Named windows: `asia` 19:00→02:45, `london` 03:00→08:00, `ny` 09:00→17:00. Gaps return `none`; there is no closed-window drop in the research scheme. |
| Levels | `PDH/PDL` come from the **full prior trading day** `[18:00, 18:00)` high/low, not the prior NY/RTH slice. Session levels are Asia/London high/low plus PDH/PDL. |
| Level availability | `available_from` is enforced in `detect_touches`: PDH/PDL from day start; Asia levels after 02:45; London levels after 08:00; merged zones use the max constituent availability. Pre-availability self-touches do not consume a zone. |
| Zones/touches | Levels within 3.0 points merge into a zone; representative price is the mean; first touch per zone per trading day; touch fires when a bar's closed `[low, high]` range intersects the zone representative. |
| Features | Interaction features use **trade prints** (`MID_PRICE_SOURCE="trade_price"`): `int_time_beyond_level`, `int_time_within_2pts`, `int_absorption_ratio`. Runtime approach subset: `app_large_trade_vol_pct`, `app_avg_trade_size`, `app_max_spread`. |
| Labels/outcomes | 3 classes: `tradeable_reversal=0`, `trap_reversal=1`, `aggressive_blowthrough=2`. MAE is checked before MFE on same-bar ambiguity. Defaults: TP 15, SL 30, trap MFE min 5. |
| Honest entry | `resolve_honest_outcome()` anchors outcome at decision time: `touch_close + DECISION_OFFSET_MINUTES` (default 5 minutes). Entry price is injected by caller as the realistic trade price at decision time. Forward bars are strictly after decision time and before cutoff. |
| Cutoffs | New entries are dropped at/after **16:40 ET** (`FLATTEN_TIME`). Forward label cutoff is **17:00 ET** (`LABEL_FORWARD_CUTOFF="17:00_US/Eastern_ny_close"`). |
| Inference gate | Contract default gate: `eligible_class=tradeable_reversal`, `eligible_session=ny`, `confidence_gate=0.70`. |

---

## Layout

```text
src/strategy_core/
  __init__.py        PLATFORM_VERSION, CONTRACT_VERSION, public API re-exports
  constants.py       single source of strategy semantics and contract descriptors
  types.py           neutral Trade/Quote/Bar/Level/Zone/Touch/SessionScheme types
  candles/
    streaming.py     CandleEngine — event-at-a-time trade tick bars
    batch.py         build_tick_bars_from_frame — pandas batch builder
    _ids.py          stable bar ids
  data/
    ordering.py      canonical `(ts_event, sequence, side_signed_price, size)` order
    databento_parquet.py  Databento-export parquet scanner/normalizer
    databento_live.py     optional/fake-tested Databento live source boundary
  decisions/
    sessions.py      classify_session / trading_day_for
    zones.py         build_zones
    touch.py         is_touch / detect_touches with v3 availability guard
    features.py      interaction + approach feature formulas
    outcomes.py      classify_mae_first / resolve_outcome
    honest_entry.py  decision-time outcome orchestration
  runtime/
    state.py         StrategyRuntime snapshots/updates for replay/live consumers
    levels.py        streaming v3 level state with availability timestamps
    replay.py        neutral replay controller over StrategyRuntime/source events
  contract/
    schema.py        Pydantic StrategyContract with platform_version/strategy_version and research_session_experiment
    loader.py        strict fail-closed loader
validation/          retained validation notes and legacy real-data harnesses
```

---

## What is still not done

1. **Trade-Lab model serving is still gated.** The backend market-data runtime now uses Strategy-Core for bars/sessions/levels/touches, but contract activation, feature-vector parity, and outcome tracking still need a verified v3 bundle path before paper/live model serving.
2. **A v3 model bundle still needs to be verified/promoted.** Quant-Lab can emit `platform_version=strategy_core_platform_v1` and `research_session_experiment`, but canonical bundle location, file presence, and checksums are intentionally deferred until a candidate bundle is selected.
3. **Historical validation reports are not current-state docs.** Retained validation notes must still be checked against current source/tests before citation.

---

## Key docs

- [`V3_COMPATIBILITY_MATRIX.md`](V3_COMPATIBILITY_MATRIX.md) — one-page Quant-Lab / Strategy-Core / Trade-Lab compatibility matrix.
- [`MIGRATION.md`](MIGRATION.md) — current migration status and remaining Trade-Lab tasks.
- [`validation/README.md`](validation/README.md) — how to interpret retained validation notes.
