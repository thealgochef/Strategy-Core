# Migration handoff — Strategy-Core v3

Updated: 2026-06-08. This is the current migration state, replacing the older v1/v2 phase plan. Historical details remain in `validation/PHASE*.md`; treat those as audit trail, not current-state docs.

## Status legend

✅ done · ▶ next · ⏳ later / deferred · ⚠️ blocked / incompatible

| Workstream | Current status | Evidence / notes |
|---|---|---|
| Strategy-Core package scaffold, types, constants, contract schema | ✅ | `src/strategy_core/` is importable; `ENGINE_VERSION=strategy_core_engine_v3`; `CONTRACT_VERSION=trade_lab_contract_v1`. |
| Candle layer | ✅ | Streaming + batch trade tick bars exist; tests cover parity and session behavior. |
| Decision layer | ✅ | Zones, touches, sessions, features, outcomes, and honest-entry orchestration live in `strategy_core.decisions`. |
| Contract loader fail-close | ✅ | `load_strategy_contract(..., expected_engine_version=...)` rejects engine mismatches. |
| Quant-Lab dashboard-utility training repoint | ✅ | Production builder calls `engine_decision.process_single_date_engine()`; contract emitter pulls constants/version stamps from Strategy-Core. |
| Strategy-Core v3 semantics | ✅ | Sessions re-clocked, full-prior-day PDH/PDL, availability guard enforced, 16:40/17:00 cutoffs, `eligible_session=ny`. |
| Strategy-Core Databento/replay/runtime package | ✅ | `strategy_core.data` owns deterministic ordering plus parquet/live normalization boundaries; `strategy_core.runtime` owns neutral replay/runtime snapshots/updates. |
| Strategy-Core tests | ✅ | Verified 2026-06-08: `uv run --python 3.14 python -m pytest -q` passes; collect-only count is 135. Also passes under Trade-Lab Python 3.13 via `PYTHONPATH`. |
| Trade-Lab market-data runtime repoint | ✅ | Trade-Lab `ApplicationRuntime` now routes bars/sessions/levels/zones/touches through `StrategyCoreService`; backend acceptance tests prove direct Strategy-Core touch output matches Trade-Lab DTO/observation output. |
| Trade-Lab model-contract / feature / outcome compatibility | ⚠️ | Model activation, contract fail-close, feature-vector parity, and decision-time outcome tracking still need a verified v3 bundle path. Do not serve v3 bundles there yet. |
| Canonical v3 model/data bundle verification | ⏳ | Deferred until local data/model zip is available; verify file presence and checksums later. |

---

## Current v3 truth

The canonical strategy state is documented in [`README.md`](README.md) and summarized in [`V3_COMPATIBILITY_MATRIX.md`](V3_COMPATIBILITY_MATRIX.md). The most important v3 differences from old docs are:

1. **Engine stamp:** `strategy_core_engine_v3`, not v1/v2.
2. **Sessions:** ET-native `asia` 19:00→02:45, `london` 03:00→08:00, `ny` 09:00→17:00; 18:00 ET trading-day boundary.
3. **Level source:** PDH/PDL = full prior trading-day high/low, not prior NY/RTH high/low.
4. **Availability guard:** session levels cannot be touched before their defining session closes.
5. **Entry/outcome:** realistic decision-time entry at `touch_close + 5m`; forward labels start after decision time.
6. **Cutoffs:** no new decision at/after 16:40 ET; forward cutoff 17:00 ET.
7. **Feature price source:** trade-print interaction features on the 0.25 trade grid.

---

## Trade-Lab repoint — remaining required engineering work

The Trade-Lab market-data runtime repoint is complete enough for backend replay/live market-data tests. The remaining work is model-serving parity and bundle activation. Each item needs tests before paper/live use.

1. **Fail-close bundle activation.**
   - In model registry activation/discovery, load `strategy.json` through `strategy_core.load_strategy_contract(path, expected_engine_version=strategy_core.ENGINE_VERSION)`.
   - Reject stale v1/v2/unversioned bundles with a path-free error.

2. **Retire or quarantine stale local strategy semantics.**
   - `domain/candles.py`, `domain/sessions.py`, and `domain/levels.py` remain as compatibility DTO/test helpers in some paths; do not use them as the authoritative runtime strategy engine.
   - New runtime code must route through `StrategyCoreService` / `strategy_core.runtime`.

3. **Replace feature computation.**
   - Route `int_time_beyond_level`, `int_time_within_2pts`, and `int_absorption_ratio` through Strategy-Core trade-print formulas, not quote-mid dwell for the two time features.
   - Keep only contract-declared features and preserve contractual order.

4. **Replace outcome tracking.**
   - Use the v3 decision-time entry convention: decision timestamp is prediction availability (`touch + decision_offset_minutes`); entry price is the current executable trade/market price at that instant; forward scan starts strictly after that instant.
   - Use `strategy_core.resolve_honest_outcome()` or the same orchestration with injected runtime price accessors.

5. **Parity proof before activation.**
   - Take one v3-trained bundle and one raw-data slice.
   - Assert identical zones, touches, feature vectors, predictions/gate decisions, and outcome labels between Quant-Lab batch path and Trade-Lab replay path.
   - Only after this passes should paper serving be considered. Live use requires separate explicit approval.

---

## Deferred data/model-bundle work

When the local data zip is available:

1. Verify incoming archive path, size, and checksum if provided.
2. Inspect zip structure before extracting.
3. Import into the Quant-Lab/Trade-Lab expected local data layout.
4. Identify the canonical v3 model-bundle location.
5. Verify each bundle has `model.cbm`, `metadata.json`, `evaluation.json`, `strategy.json`, and `model.cbm.sha256` if expected.
6. Validate `strategy.json` against `strategy_core_engine_v3` and compute/check file hashes.

Do **not** infer bundle validity from names or old reports.
