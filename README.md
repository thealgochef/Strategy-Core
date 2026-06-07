# strategy-core

Shared, versioned strategy engine for zero-drift parity between **Quant-Lab** research/training and **Trade-Lab** live/replay inference.

`strategy-core` owns the strategy mechanics that must not drift: tick bars, sessions, zones, first-touch detection, feature formulas, outcome resolution, honest decision-time entry orchestration, and the versioned `strategy.json` schema/loader.

> Current status, verified 2026-06-04: **engine v3 is implemented and unit-tested**. `python -m pytest -q` passes; `python -m pytest --collect-only -q` reports **106 tests** across 8 test files. Quant-Lab imports this engine for dashboard-utility training and contract emission. Trade-Lab is still **not v3-compatible**; see [`V3_COMPATIBILITY_MATRIX.md`](V3_COMPATIBILITY_MATRIX.md) and [`MIGRATION.md`](MIGRATION.md).

---

## Install / verify

```bash
pip install -e .
pip install -e ".[dev]"      # pytest + pandas for batch candle builder tests
python -m pytest -q          # 106 tests passing as of 2026-06-04
python -m pytest --collect-only -q
```

Runtime import intent: stdlib + `numpy` + `pydantic`; pandas is loaded lazily by the batch candle builder only.

---

## Version stamps

| Stamp | Current value | Meaning |
|---|---:|---|
| `ENGINE_VERSION` | `strategy_core_engine_v3` | Structural decision/candle semantics that a model bundle binds to. A mismatch must fail closed. |
| `CONTRACT_VERSION` | `trade_lab_contract_v1` | Shape/version of `strategy.json`. The v3 engine still uses the v1 contract format plus required `engine_version`, `label_policy.decision_offset_minutes`, and optional research audit metadata. |

`load_strategy_contract(path, expected_engine_version=ENGINE_VERSION)` rejects stale bundles before they can be served.

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
  __init__.py        ENGINE_VERSION, CONTRACT_VERSION, public API re-exports
  constants.py       single source of strategy semantics and contract descriptors
  types.py           neutral Trade/Quote/Bar/Level/Zone/Touch/SessionScheme types
  candles/
    streaming.py     CandleEngine — event-at-a-time trade tick bars
    batch.py         build_tick_bars_from_frame — pandas batch builder
    _ids.py          stable bar ids
  decisions/
    sessions.py      classify_session / trading_day_for
    zones.py         build_zones
    touch.py         is_touch / detect_touches with v3 availability guard
    features.py      interaction + approach feature formulas
    outcomes.py      classify_mae_first / resolve_outcome
    honest_entry.py  decision-time outcome orchestration
  contract/
    schema.py        Pydantic StrategyContract with engine_version and research_session_experiment
    loader.py        strict fail-closed loader
validation/          retained validation notes and legacy real-data harnesses
```

---

## What is still not done

1. **Trade-Lab v3 repoint is incomplete.** Current Trade-Lab has its own contract schema without `engine_version` / `decision_offset_minutes`, Chicago session classification, exact-tick level touches, quote-mid dwell features, and level-price outcome tracking.
2. **A v3 model bundle still needs to be verified/promoted.** Quant-Lab can emit `engine_version=strategy_core_engine_v3` and `research_session_experiment`, but canonical bundle location, file presence, and checksums are intentionally deferred until the local data zip is available.
3. **Historical validation reports are not current-state docs.** Most stale v1/v2 phase reports were pruned from the working tree; retained validation notes must still be checked against current source/tests before citation.

---

## Key docs

- [`V3_COMPATIBILITY_MATRIX.md`](V3_COMPATIBILITY_MATRIX.md) — one-page Quant-Lab / Strategy-Core / Trade-Lab compatibility matrix.
- [`MIGRATION.md`](MIGRATION.md) — current migration status and remaining Trade-Lab tasks.
- [`validation/README.md`](validation/README.md) — how to interpret retained validation notes.
