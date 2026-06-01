# Migration handoff — repointing both repos onto strategy-core

The shared engine (this package) is **done and tested**. This file is the staged
plan for the remaining spec phases (4–8): repointing Claude-Quant-Lab (research)
and Trade-Lab (runtime) onto it, plus the cross-repo parity proof. These phases
touch a live serving path with money on it and require running both repos' full
suites against real data, so they are **not applied here** — they are specified,
ordered, and anchored so they can be executed deliberately and verified.

Status legend: ✅ done · ▶ next · ⏳ later

| Phase | What | Status |
|---|---|---|
| 1 | Scaffold `strategy-core` (package, types, constants, contract schema) | ✅ |
| 2 | Lift candle layer (batch + streaming + parity test) | ✅ |
| 3 | Extract decision layer from training path (+ tests) | ✅ |
| 4a | **Parity gate** — decision-layer fidelity vs canonical on real data (pre-retrain) | ✅ |
| 4 | Repoint research **training** onto the engine | ▶ |
| 5 | Fix the contract **emitter** (emit from engine constants) | ▶ |
| 6 | Repoint **Trade-Lab** onto the engine | ▶ |
| 7 | End-to-end **parity** proof (one model + one data slice) | ▶ |
| 8 | Absorb remaining research duplicates (experiment / live-dashboard) | ⏳ |

---

## ⚠️ Retrain gate (must happen in phase 4, before phase 6 can serve anything)

The engine standardizes interaction features on **trade price** (ratified). The
deployed model was trained on a **top-of-book mid** (`tick_store.py:264`,
`dashboard_utility_builder.py:488`). They are incompatible.

So phase 4 is not just "wire an adapter" — it is **retrain the model under this
engine**: repoint research dataset construction onto `strategy_core`, rebuild the
training set (interaction features now trade-price), retrain CatBoost, and emit a
new bundle stamped `engine_version = strategy_core_engine_v1`. Trade-Lab's
`engine_version` fail-close (phase 6) will refuse the old bundle — by design.

If, on reflection, the strategy should stay on TOB-mid instead, that is a one-line
change (`MID_PRICE_SOURCE = "top_of_book"`) plus reworking the three interaction
features to consume a top-of-book book-event stream (mid + event size), and then
**no** retrain is needed because the deployed model already encodes TOB-mid. That
reversal was offered and declined; this plan assumes trade-price + retrain.

---

## Phase 4 — repoint research training

Goal: the training set is produced by `strategy_core`, not the in-repo duplicates.

1. Write an adapter `DataFrame/DuckDB row → engine neutral types` (Trade/Quote/Bar/Level).
   - bars (`tick_store.build_tick_bars` / `build_bars_from_ticks`) → `strategy_core.types.Bar`
     (or benchmark `build_tick_bars_from_frame`, see open decision below).
   - levels (`_compute_levels_for_date`, builder:347-376) → `list[Level]`.
   - interaction-window ticks (`query_tick_feature_rows`) → `list[Trade]` of **trade prints**
     (NOT the book-mid rows — that is the strategy change; apply the `< 5`-tick drop here).
2. Replace the in-repo functions with engine calls:
   | Research callsite | → engine |
   |---|---|
   | `_build_zones` (builder:382-411) | `decisions.zones.build_zones` |
   | `_detect_touches` (builder:414-440) | `decisions.touch.detect_touches` |
   | `_slice_session`/session consts (builder:332-344, 44-51) | `decisions.sessions.classify_session` |
   | `_compute_interaction_features` (builder:446-538) | `decisions.features.int_*` |
   | approach features (`experiment/features.py`) | `decisions.features.app_*` |
   | `label_touch_event` (labeling:44-108) | `decisions.outcomes.resolve_outcome` |
3. **Golden assertion:** capture the *current* training output (touches, feature
   matrix, labels) as golden vectors BEFORE the swap; after the swap, assert the
   non-feature columns (touches, sessions, labels) are byte-identical and the
   interaction features change **only** in the expected trade-price direction
   (everything else — approach features, labels — unchanged).

## Phase 5 — fix the contract emitter

`strategy_contract.py` (research) currently restates literals it should import.

1. Import `StrategyContract` from `strategy_core.contract.schema` (delete the
   duplicate dict-building where possible; at minimum validate the emitted dict
   against the shared schema before writing).
2. Emit every field from engine constants — delete `_SESSION_TIMEZONE`,
   `_TRADING_DAY_BOUNDARY`, the session-time constants, `_ZONE_PROXIMITY_PTS`,
   `_WITHIN_BAND_PTS`, `_LARGE_TRADE_THRESHOLD` (strategy_contract.py:52-59) and read
   `strategy_core.constants` instead. (These are the "restated literals" the audit
   flagged.)
3. Stamp `engine_version = strategy_core.ENGINE_VERSION`.
4. Set `feature_windows.mid_price_source = strategy_core.constants.MID_PRICE_SOURCE`
   (`"trade_price"`). Note: this is now *correct by construction* rather than a
   hand-maintained label.

## Phase 6 — repoint Trade-Lab

The bigger lift; this is the serving path. Each item has its current Trade-Lab anchor.

1. **Build a zone layer.** Trade-Lab has none (`domain/levels.py` works on individual
   levels, exact-tick). Add zone construction via `strategy_core.build_zones` fed by
   Trade-Lab's level objects.
2. **Swap sessions to ET.** Replace `domain/sessions.py` Chicago classifier
   (`CT`, `classify_session` :35-52) with `strategy_core.classify_session`
   (RESEARCH_SESSION_SCHEME). This also re-parameterizes the **candle** trading-day
   calendar — feed `CandleEngine(scheme=RESEARCH_SESSION_SCHEME)` (or pass the
   contract's `session_scheme`). The CT 16:00–18:00 closed-window drop disappears
   (research keeps those trades).
3. **Swap touch to bar-intersect-on-zones, per-zone-per-day.** Replace the exact-tick
   detector (`domain/levels.py:245-274`) with `strategy_core.detect_touches` fed by
   *closing candles*. Drop the `(day, session, kind)` first-touch key in favor of
   per-zone-per-day (the `Zone.touched` flag).
4. **Route features through the engine.** Replace `feature_functions.py:170-239`
   (the quote-mid interaction features) with `strategy_core.decisions.features.int_*`
   fed by **trade** events (trade-price). Keep `app_*` via the engine. This removes
   the quote-mid path.
5. **Route outcomes through the engine.** Have `outcome_tracker.py` call
   `strategy_core.classify_mae_first` for the per-bar ladder (its `_classify`
   :160-191 already matches; this just single-sources it). The streaming tracker's
   `forced` (RTH cutoff) branch maps to `classify_mae_first(..., forced=True)`.
6. **Fail-close on `engine_version`.** In `services/model_registry.py`, call
   `load_strategy_contract(path, expected_engine_version=strategy_core.ENGINE_VERSION)`
   and reject bundles that don't match — extending the existing fail-closed
   `contract_id` validation.
7. Remove the now-dead bespoke exact-tick / Chicago / per-session machinery.

## Phase 7 — end-to-end parity proof (the real test)

Take **one** trained bundle (retrained under the engine, phase 4) and **one** slice
of raw data. Run research-training and Trade-Lab over it and assert:

- **identical touch population** (same zones, same first-touch bars),
- **identical feature vectors** (every column, every touch),
- **identical outcome labels**.

Resolve the open parity items while doing this — they are the most likely sources of
a mismatch:

- **Touch timestamp open vs close** — confirm which bar timestamp the research index
  carries and align `detect_touches` (currently `close_ts_utc`).
- **Bar-price tick alignment** — confirm OHLC are tick-aligned end to end.
- **Absorption `size`** — confirm the retrained dataset and the engine sum the same
  size source.

## Phase 8 — absorb remaining duplicates (later)

Migrate the research `experiment/` and `dashboard/engine/` paths onto the shared
engine to kill the remaining internal duplication. Not on the critical path; do
after the training↔serving path is proven.

---

## Phase 4a parity gate — RESULT

Run `validation/parity_harness.py` (additive, imports both repos read-only) over 5
real NQ days. **PORT FIDELITY PROVEN**: zones, sessions, touches+timestamps, labels,
interaction-formula-fidelity, and the 3 approach features all 100% match canonical;
the interaction trade-price divergence is reported, not asserted. Independently
re-derived. Report: `validation/_out/PARITY_REPORT.md`. This gate clears phases 4–6
of the decision-layer-fidelity risk; phase 7 (full end-to-end parity) still runs
after the retrain because it must use a model actually trained under this engine.

## Open decisions for the human

1. **Candle builder: numpy/pandas vs DuckDB (spec §7) — BENCHMARKED.** On one real
   day, canonical DuckDB tick-bar build is ~26× faster than a naive numpy/pandas
   rebuild (0.34s vs 9.0s; parquet I/O dominates). Bars agree on count, close
   timestamps, high/low, and volume; only `open`/`close` *mid* differ on ~2.2% of
   bars, from DuckDB's non-deterministic tie-break on duplicate `ts_event` — which
   does **not** affect touches/labels (they use order-independent high/low).
   **Decision:** keep research on DuckDB as the verified-equivalent fast path; the
   engine owns the bar spec + parity test. If a numpy fast path is ever wanted, first
   add a deterministic secondary sort key (e.g. `ORDER BY ts_event, rn`) to the
   canonical builder so `open`/`close` become well-defined, then mirror it in numpy.
2. **Trade-price retrain** (the retrain gate above) — assumed yes.
3. **Touch timestamp / absorption size / tick alignment — RESOLVED in 4a:** touch ts
   = bar CLOSE (engine matches); absorption size canonical = book-event size (engine
   trade-size is the deliberate change); book mids lie exactly on the 0.125 grid
   (engine integer-tick `Bar` is lossless).

## How this package was built

The engine was authored by a hand-written foundation (`types.py`, `constants.py`,
`__init__.py`, `pyproject.toml`) plus a multi-agent workflow that ported each
candle/decision/contract module from the canonical sources and adversarially
reviewed each for drift. The workflow script is kept at `.wf/build_strategy_core.js`
for reproducibility.
