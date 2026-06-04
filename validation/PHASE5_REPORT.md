# Phase 5 — research-side decision-layer repoint onto the engine + literal-free, version-stamped contract (BOOK_MID)

**Why.** Bars are locked (4c–4f). Two RESEARCH-side drift surfaces remained. (1) The CQL training
pipeline ran its OWN duplicate decision code (zones/touches/labels/features) instead of the shared
`strategy_core` engine — a second copy of the strategy that can drift from the engine the runtime
trusts. (2) The contract emitter RESTATED literals (session windows, proximity bands, thresholds,
point value, class names, RTH close, `mid_price_source`) instead of sourcing them from the engine,
and emitted NO `engine_version`. Phase 5 single-sources BOTH: it repoints the training decision
layer onto the engine, and rewrites the emitter to read every structural value from
`strategy_core.constants` and stamp the engine version — **with NO strategy change yet**. The
repoint is proven against the 4a canonical answer on `book_mid` (the last point a known-good answer
exists). The trade-bar cutover + retrain is the NEXT phase.

**Scope / gate.** HARD GATE respected throughout:
- CQL `_build_bars_for_date` stays **pinned to `price_source="book_mid"`** — confirmed explicit at
  `dashboard_utility_builder.py:344` and `:349` (book-mid bars feed both the legacy and engine
  decision paths; no trade-bar flip).
- **No retrain.** No model rebuilt; `engine_version` not bumped (it stays `strategy_core_engine_v1`).
- **No Trade-Lab edit.** `C:/Users/gonza/Documents/Trade-Lab` untouched (the only `??` there is a
  pre-existing v2 test, not a phase-5 file).
- **Old CQL decision code kept importable.** `_build_zones`, `_detect_touches`,
  `_compute_interaction_features`, `_compute_approach_features` (builder) and `label_touch_event`
  (labeling) are intact and runnable for the parity diff — cleanup is a later phase.
- **No edge eval.** Parity only; no PnL / no model selection.
- All changes left **UNCOMMITTED** in both repos (4d/4e/4f convention). SC HEAD unchanged at
  `4ce2e61` (branch `main`); the SC working tree shows only `M src/strategy_core/constants.py` (the
  additive descriptor block) plus this report. CQL changes are the builder edit + the new engine
  adapter / emitter rewrite / proof script / tests, all uncommitted.

---

## PART 1 — the decision-layer repoint (book_mid)

### Which CQL call-sites now run the engine

A new adapter `C:/Users/gonza/Documents/Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/engine_decision.py`
imports and CALLS the shared engine directly (verified: the only references to the legacy CQL
decision functions in this file are docstrings/comments — never calls):

| stage | engine function (from `strategy_core`) | adapter site |
|---|---|---|
| zones | `build_zones(levels)` | `engine_decision.py:160` |
| touches | `detect_touches(bars, zones, tick_size=0.125, trading_day=…)` | `:161` |
| session eligibility | `classify_session` (reporting only — **NOT** used to gate labels) | imported `:48` |
| labels / outcome | `resolve_outcome(…, tick_size=0.125, tp=15, sl=30, trap_mfe_min=5)` | `:177` |
| interaction features | `int_time_beyond_level`, `int_time_within_2pts`, `int_absorption_ratio` | `:280–282` |
| approach features | `app_avg_trade_size`, `app_large_trade_vol_pct`, `app_max_spread` | `:347–349` |

The builder threads a `use_engine: bool = True` flag through `build_utility_dataset`
(`dashboard_utility_builder.py:63`) and `_process_single_date` (`:201`); the engine branch
(`:228–233`) dispatches to `process_single_date_engine` AFTER computing the SAME book-mid bars +
levels, then falls through to the legacy path when `use_engine=False`. Both paths consume the
identical, pinned book-mid bar/level input, so the diff isolates the decision layer alone.

### Book_mid grids (reproduced exactly from `parity_harness_v2`)

- **book-mid bars + bar decision layer (zones/touches/labels)** and **interaction features**:
  `tick_size = 0.125` (`BOOK_MID_TICK`). The book-mid grid is lossless at 0.125 (`round(price/0.125)`
  integer ticks). `detect_touches(…, 0.125)`, `resolve_outcome(…, 0.125)`, all three `int_*` at 0.125.
- **approach features (`app_*`)**: TRADE prints + L0 quotes at `tick_size = 0.25` (`TRADE_TICK`) over
  `[touch-30min, touch)`. Matches `parity_harness_v2` (`CANON_TICK=0.125`, `TRADE_TICK=0.25`).
- Interaction book rows come from a **per-date single-day** `TickStore.query_tick_feature_rows`
  (`price=(bid+ask)/2`), fed as `Trade@0.125` over `[touch_ts, touch_ts+interaction_window)`, keyed
  off the **ET-indexed touch date** (canonical `_compute_interaction_features` scope) so the 5-min
  window cannot leak next-day rows across a UTC midnight. The legacy `<5-row` drop is reproduced.
- Forward bars for `resolve_outcome` are strictly `index > touch bar` AND `< 16:15 ET` cutoff; the
  touch ts == bar close (asserted `==` in the test).

### PLUMBING-PROOF — per-day, engine vs legacy (4a canonical answer)

`scripts/decision_repoint_proof.py` builds book-mid bars+levels once, then runs BOTH the legacy CQL
decision code and the engine adapter on them and diffs every output. Expectation: **feature
max-abs-diff = 0**.

| Day | touches matched (legacy == engine) | kept feature-touches | labels match | feature max abs diff |
|---|:--:|:--:|:--:|:--:|
| 2025-07-09 | 5/5 | 3 | yes | **0.0** |
| 2025-07-10 | 5/5 | 5 | yes | **0.0** |
| 2025-07-11 | 5/5 | 1 | yes | **0.0** |
| 2025-07-14 | 5/5 | 5 | yes | **0.0** |
| 2025-07-15 | 5/5 | 1 | yes | **0.0** |

**Result: the engine path reproduces the 4a-canonical / legacy output EXACTLY on the sample.** Zones
(set) match; touches 5/5 each day (level_type, bar-close ts, direction, rep_price byte-identical);
labels match (class + max_mfe/max_mae to 1e-9); all 6 model features have max abs diff `0.0`; AND
the integrated `_process_single_date(use_engine=True)` dataset rows equal `use_engine=False`
row-for-row on the model feature columns (1e-9, NaN-aware). The 07-09 case (prior calendar day 07-08
missing from the store) exercised the day-gap path and still matched 5/5.

**Known 23:59-ET window artifact — itemized, NOT hit here.** The single documented
`parity_harness_v2` exception is the interaction window-bound artifact at a 23:59-ET
midnight-crossing touch (the harness's 5-min window crosses UTC midnight; interaction-formula was
254/255 there). Both the proof harness and the standing test GUARD for it, but none of the 5 sample
days (07-09…07-15) had a touch land in that window, so `feature_max_abs_diff` is a clean `0.0`
everywhere — no artifact triggered.

### Flagged call-site literals (single-source targets)

These legacy literals are now governed by the engine constant on the repointed path (the legacy code
still restates them, kept for the diff; cleanup is a later phase):

| legacy literal (call-site) | engine constant it maps to | how the engine path honors it |
|---|---|---|
| `_ZONE_PROXIMITY=3.0` (builder `_build_zones`) | `ZONE_PROXIMITY_PTS` | `build_zones` single-sources it; engine path passes nothing |
| within-band `abs(m-rep)<=2.0` (`_compute_interaction_features`) | `WITHIN_BAND_PTS` | `int_time_within_2pts` single-sources it |
| `level_proximity_pts` absorption band (config 0.50) | `LEVEL_PROXIMITY_PTS` (engine default) | adapter passes nothing → engine constant governs (matches) |
| `size>=10` large-trade (experiment/features.py:44, LIVE comment) | `LARGE_TRADE_THRESHOLD` | `app_large_trade_vol_pct` single-sources it |
| `{LOW->LONG, HIGH->SHORT}` (`_detect_touches`) | `DIRECTION_FROM_SIDE` | `detect_touches` single-sources it; emitter now emits it from there too |
| `dt_sec>600` max dwell gap (`_compute_interaction_features`) | `MAX_DWELL_GAP_SECONDS` | engine tempo loops single-source it |
| emitter (pre-Part-2): `_SESSION_TIMEZONE`, `_TRADING_DAY_BOUNDARY`, 3 session windows, `_ZONE_PROXIMITY_PTS`, `_WITHIN_BAND_PTS`, `_LARGE_TRADE_THRESHOLD`, `_POINT_VALUE`, `CLASS_NAMES`, `RTH_END`, `mid_price_source='top_of_book'` | the corresponding `strategy_core.constants` | ALL single-sourced in Part 2 (below) |

**Approach-feature scope.** The engine implements only the 3 RUNTIME approach features
(`app_avg_trade_size`, `app_large_trade_vol_pct`, `app_max_spread`) — exactly the 3 the model uses —
and they matched the canonical DuckDB `_compute_approach_features` EXACTLY (mirrors
`parity_harness_v2` Stage G 255/255). The other 5 `LIVE_APPROACH_FEATURES`
(`volume_acceleration`, `avg_tob_imbalance`, `volatility_recent`/`ratio`, `trade_count`) have no
engine formula yet and are NOT in the model's feature set — a future flag, not a repoint regression.

---

## PART 2 — the literal-free, version-stamped contract

The emitter `C:/Users/gonza/Documents/Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/strategy_contract.py`
was rewritten to read every STRUCTURAL value from `from strategy_core import constants as k` (plus
`CONTRACT_VERSION` / `ENGINE_VERSION` from `strategy_core`). All restated locals and inline literals
were removed; only the JSON dict KEYS (field names), session-name SELECTORS (`"asia"`/`"london"`/
`"ny_rth"`, which read window VALUES from `k.RESEARCH_SESSION_SCHEME`), the bundle filename
`"model.cbm"`, and structural booleans remain as non-value strings.

### SC constants added (additive descriptor block, `constants.py`)

17 new constants for the previously-literal descriptors, each citing its canonical-research
provenance, with `__all__` updated:
`NAN_POLICY`, `PDH_PDL_SOURCE`, `SESSION_LEVELS`, `LEVEL_AVAILABLE_FROM_GUARD`, `TOUCH_TYPE`,
`ZONE_REPRESENTATIVE_PRICE`, `TOUCH_SCOPE`, `LABEL_RESOLUTION`, `LABEL_ENTRY_REFERENCE`,
`LABEL_NO_RESOLUTION_DROPPED`, `LABEL_FORWARD_CUTOFF`, `INFERENCE_ELIGIBLE_SESSION`,
`DEFAULT_CONFIDENCE_GATE`, `MIN_BOOK_LEVEL`, `LIVE_SCHEMAS`, `REPLAY_SCHEMAS`, `DEPTH_USAGE`.
`LABEL_FORWARD_CUTOFF` is DERIVED (`f"{RTH_END:%H:%M}_{SESSION_TIMEZONE}_rth_close"` =
`"16:15_US/Eastern_rth_close"`), not a restated literal. The pre-existing constants
(`POINT_VALUE`, `ZONE_PROXIMITY_PTS`, `WITHIN_BAND_PTS`, `LARGE_TRADE_THRESHOLD`,
`MID_PRICE_SOURCE`, `DIRECTION_FROM_SIDE`, `CLASS_NAMES`, `TRADEABLE_REVERSAL`, `SESSION_TIMEZONE`,
`TRADING_DAY_BOUNDARY`, `RESEARCH_SESSION_SCHEME`) were reused, not duplicated. The SC engine source
(zones/touch/sessions/outcomes/features) was NOT touched — only `constants.py` got the additive block.

### FIELD → CONSTANT / CONFIG mapping (all 52 leaves of `StrategyContract`)

30 leaves are STRUCTURAL (engine-constant-sourced); 22 are per-run (config-sourced). `30 + 22 = 52`,
zero uncovered, zero overlap.

**Structural (engine-sourced, `k.*` / `strategy_core`):**

| field | source |
|---|---|
| `contract_version` | `CONTRACT_VERSION` |
| `engine_version` | `ENGINE_VERSION` |
| `point_value` | `POINT_VALUE[instrument]` |
| `feature_set.nan_policy` | `NAN_POLICY` |
| `class_map` | `CLASS_NAMES` |
| `session_scheme.timezone` | `SESSION_TIMEZONE` |
| `session_scheme.trading_day_boundary` | `TRADING_DAY_BOUNDARY` |
| `session_scheme.sessions` (asia/london/ny_rth) | `RESEARCH_SESSION_SCHEME.sessions` |
| `level_scheme.pdh_pdl_source` | `PDH_PDL_SOURCE` |
| `level_scheme.session_levels` | `SESSION_LEVELS` |
| `level_scheme.available_from_guard` | `LEVEL_AVAILABLE_FROM_GUARD` |
| `touch_rule.type` | `TOUCH_TYPE` |
| `touch_rule.zone_proximity_pts` | `ZONE_PROXIMITY_PTS` |
| `touch_rule.zone_representative_price` | `ZONE_REPRESENTATIVE_PRICE` |
| `touch_rule.scope` | `TOUCH_SCOPE` |
| `touch_rule.direction_from_side` | `DIRECTION_FROM_SIDE` |
| `feature_windows.within_band_pts` | `WITHIN_BAND_PTS` |
| `feature_windows.large_trade_threshold` | `LARGE_TRADE_THRESHOLD` |
| `feature_windows.mid_price_source` | `MID_PRICE_SOURCE` (`"trade_price"`) |
| `label_policy.resolution` | `LABEL_RESOLUTION` |
| `label_policy.entry_reference` | `LABEL_ENTRY_REFERENCE` |
| `label_policy.forward_cutoff` | `LABEL_FORWARD_CUTOFF` (from `RTH_END`+`SESSION_TIMEZONE`) |
| `label_policy.no_resolution_dropped` | `LABEL_NO_RESOLUTION_DROPPED` |
| `inference.eligible_class` | `TRADEABLE_REVERSAL` |
| `inference.eligible_session` | `INFERENCE_ELIGIBLE_SESSION` |
| `inference.confidence_gate` | `DEFAULT_CONFIDENCE_GATE` |
| `data_requirements.min_book_level` | `MIN_BOOK_LEVEL` |
| `data_requirements.live_schemas` | `LIVE_SCHEMAS` |
| `data_requirements.replay_schemas` | `REPLAY_SCHEMAS` |
| `data_requirements.depth_usage` | `DEPTH_USAGE` |

**Per-run (config-sourced — legitimately varies with a training run, correctly NOT forced to a constant):**

| field | source |
|---|---|
| `strategy_id` | per-run input |
| `training_mode` | `config:training_mode` |
| `supported_by_runtime` | derived from `training_mode=="dashboard_utility"` |
| `instrument` | `config:instrument` |
| `tick_size` | `config:tick_size` |
| `model.type` / `model.loss_function` | `config:model.{model_type,loss_function}` |
| `model.file` | literal bundle name `"model.cbm"` |
| `feature_set.names` / `order_is_contractual` | `config:selected_features` / always `True` |
| `feature_set.interaction_features` / `approach_features` | `selected_features` filtered by `LIVE_*_FEATURES` |
| `touch_rule.bar_type` | `config:dashboard_utility.bar_type` |
| `feature_windows.interaction_window_minutes` / `approach_window_minutes` | `config:dashboard_utility.*` |
| `feature_windows.level_proximity_pts` | `config:dashboard_utility.level_proximity_pts` |
| `label_policy.tp_points` / `sl_points` / `trap_mfe_min` | `config:dashboard_utility.*` |
| `label_policy.forward_bar_type` | `config:dashboard_utility.bar_type` |
| `provenance.dataset_config_hash` | `config.dataset_config_hash()` |
| `provenance.catboost` | `config:model.{iterations,depth,learning_rate,auto_class_weights}` |

(`level_proximity_pts` is deliberately config-sourced and documented: the engine's interaction
default `LEVEL_PROXIMITY_PTS=0.50` governs and the deployed value equals it, so there is no drift;
`within_band_pts` is the structural `WITHIN_BAND_PTS=2.0` — a different, pinned quantity.)

### engine_version stamping + the `mid_price_source -> trade_price` change

`engine_version = ENGINE_VERSION = "strategy_core_engine_v1"` is stamped on BOTH the full
(`dashboard_utility`) record and the minimal record (`strategy_contract.py:99`, `:119`).
`mid_price_source` flips from the old restated `"top_of_book"` to `k.MID_PRICE_SOURCE = "trade_price"`
(`:179`).

**Why this is correct.** The contract now DESCRIBES THE ENGINE, not the legacy book-mid training
path. The engine standardizes the 3 interaction features on the trade-print price. The deployed
book-mid model is therefore now `engine_version`-INCOMPATIBLE by design: the new `engine_version`
binding is exactly the fail-closed mechanism that makes Trade-Lab refuse the current book-mid model
until the trade-bar cutover + retrain in the NEXT phase. No retrain happens here; `engine_version`
was NOT bumped (no new mechanism added — additive descriptors only).

### No-drift test (with coverage guard) + loader validation

`C:/Users/gonza/Documents/Claude-Quant-Lab/tests/agents/test_strategy_contract_nodrift.py` — **6/6 PASS**.
- `test_every_structural_field_equals_its_engine_constant` pins each of the 30 structural leaves to
  its real `k.*` constant.
- `test_coverage_guard_no_structural_field_without_a_source` enumerates all 52 leaf fields of the
  `StrategyContract` pydantic model (via `_model_leaf_paths`, treating `class_map` and
  `session_scheme.sessions` as single leaves) and asserts each is covered by EITHER the structural
  constant-map (30) OR the per-run config allow-list (22): `52 = 30 + 22`, uncovered `[]`,
  overlap `[]`, no stale entries. Verified NON-VACUOUS — a simulated new leaf
  `inference.new_secret_gate` is correctly flagged uncovered (a future field added with a literal
  and no source WOULD trip the assertion).

**Loader validation.** The production contract (`dashboard_utility`, NQ, 0.25, 147t, 5m/30m,
tp15/sl30/trap5, 6 RFECV features) was built and loaded via
`strategy_core.contract.loader.load_strategy_contract(path, expected_engine_version=ENGINE_VERSION)`
— loads with NO `ContractError`; pydantic `extra='forbid'` accepted every key (no unknown field);
`feature_count=6`; `point_value=20.0`; labels = (`tradeable_reversal`, `trap_reversal`,
`aggressive_blowthrough`). Loading with `expected_engine_version="strategy_core_engine_v999"` raises
`ContractError` (fail-closed binding works).

---

## VERIFICATION

Three adversarial reviews plus an independent contract audit and a full regression run all pass.
**Part-1 review (engine actually called, no leakage/look-ahead):** confirmed by direct import +
grep that `engine_decision.py` only ever CALLS `strategy_core` functions (the legacy-fn references
are docstrings); tick grids correct (`0.125` book-mid bars + interaction, `0.25` approach — matches
`parity_harness_v2`); `_build_bars_for_date` still pinned `book_mid` (lines 344/349); forward bars
strictly `index>touch` AND `<16:15 ET`; interaction window uses a per-date single-day store keyed
off the ET-indexed touch date so it cannot leak across UTC midnight; the diff metrics shown
sensitive by injection (a ±250pt perturbation surfaced divergence; a corrupted label produced
exactly 1 flip) — i.e. the `0.0` is real, not vacuous. **Part-2 reviews + independent contract
audit:** a literal scan of the emitter returned NO restated structural values (`US/Eastern`,
`16:15`, `top_of_book`, `3.0`, `2.0`, `10`, `0.70`, direction/label strings — none present as
values; the lone `top_of_book` substring is inside `k.DEPTH_USAGE="top_of_book_only"`, engine-
sourced); an independent enumeration of all 52 `StrategyContract` leaves verified every structural
field EQUALS its live `strategy_core` constant (0 mismatches, 0 uncovered, 0 stale), and confirmed
the coverage guard is real and non-vacuous. **Fail-close proven on the deployed model:** the live
deployed `models/NQ_20260405_147t_5m_30m_multiclass-…/strategy.json` has NO `engine_version`
(verified: `engine_version` count = 0) and `mid_price_source=top_of_book`; loading it with
`expected_engine_version=ENGINE_VERSION` raises `ContractError` (and even without the gate it raises
`ContractError` for the missing required field) — the binding is the sole + sufficient fail-close,
and the file was NOT modified. **Regression — all green:** CQL `test_tick_store.py` 40 passed; SC
full engine suite 97 passed (the 17 new constants are purely additive — no engine test broke); SC
`tests/test_contract.py` 15 passed; SC 4e/4f gates (`test_production_pair_parity` +
`test_duckdb_streaming_parity` + `test_decision_diff`) green; new
`test_decision_repoint_parity.py` 10 passed (real Databento NQ store present, so it did NOT skip —
the engine-vs-legacy repoint was genuinely exercised on book_mid); new
`test_strategy_contract_repoint.py` 7 passed and `test_strategy_contract_nodrift.py` 6 passed (no
data dep). The only flagged items are reporting-label nuances (the Part-1 report calls some new
files "EDIT" though git shows them `??` untracked — they exist and pass) and the documented ratified
divergence; **no defect, leakage, look-ahead, accidental strategy change, or scope violation** was
found.

---

## CLOSING STATUS

> **The decision-layer repoint is PROVEN on `book_mid`** — the engine path
> (`build_zones → detect_touches → resolve_outcome → the 6 features`, at 0.125 bars/interaction and
> 0.25 approach) reproduces the 4a-canonical / legacy answer EXACTLY on the 5-day sample: zones
> match, touches 5/5 each day, labels match, all 6 model features at `max abs diff = 0.0`, and the
> integrated `_process_single_date(use_engine=True)` rows equal `use_engine=False` row-for-row. **The
> contract is LITERAL-FREE and VERSION-STAMPED** — every structural field single-sourced from
> `strategy_core.constants`, `engine_version="strategy_core_engine_v1"` stamped, `mid_price_source`
> now `trade_price`; it loads through the fail-closed loader, and the no-drift coverage guard
> enforces the property going forward. The deployed book-mid model is now `engine_version`-
> incompatible BY DESIGN (it fails the loader's engine-version fail-close). **The trade-bar cutover +
> retrain is the NEXT phase.**

**Gate (confirmed).** No trade-bar flip (`_build_bars_for_date` stays `price_source="book_mid"`,
lines 344/349); no retrain (`engine_version` not bumped); no Trade-Lab edit; no edge eval; old CQL
decision code kept importable + intact; SC engine source untouched (only the additive `constants.py`
descriptor block changed); ALL changes left UNCOMMITTED in both repos. SC HEAD unchanged at
`4ce2e61`.
