# Phase 8 — Trade-Bar Cutover + Honest-Entry Re-Anchor (ALIGNMENT, engine v1 → v2)

## WHY + HARD GATE

**Goal.** Cut the canonical research↔engine path over to **trade-print bars** and re-anchor the
canonical **outcome** to the **decision-time entry** (the realistic price when a prediction can
actually fire), single-sourcing both into the shared `strategy_core` engine and the
`strategy.json` contract. This closes the research↔engine seam at **engine_version v2**.

**This is ALIGNMENT, not edge.** The deliverable is an aligned, cut-over platform — *not* a
retrained model and *not* an edge/PnL read.

**HARD GATE (respected, verified):**
- **No retrain** (next phase). **No edge/PnL eval** run (next phase).
- **Trade-Lab is READ-ONLY** this phase — read file:line only, zero edits.
- **HELD EXACTLY** (byte-identical): the **3 classes** (`tradeable_reversal` 0 / `trap_reversal` 1
  / `aggressive_blowthrough` 2), **tp=15**, **sl=30**, **trap_mfe_min=5**, the **MAE-first** ladder,
  and **within_band = 2.0 POINTS**. *Only* the entry anchor + the forward-window start moved.
- **Legacy kept importable** (book-mid regression mode reachable; nothing deleted).
- **All changes left UNCOMMITTED.** HEADs unchanged: **SC `4ce2e61`** (branch `main`),
  **CQL `2f6aa62`** (branch `duckdb-18et-boundary`), **Trade-Lab `2f6aa62`**.
- Env: `PYTHONPATH=src` for every CQL python call (alpha_lab shadowing). Data:
  `C:/Users/gonza/Documents/Trade-Dashboard/data/databento` (symbol NQ).

---

## PART 0 — Pinned Trade-Lab conventions (read-only) + the stale-side discovery

### The closure target (executor decision-time entry + flatten)

The canonical outcome must match the Trade-Lab **executor** convention: entry at the **market price
when the prediction fires** (= touch + interaction window 5m, *not* the level price 5 min earlier),
with **new entries rejected at/after ~15:55 ET** (flatten). This is the rule the engine v2 outcome
now mirrors.

### DISCOVERY — Trade-Lab's inference is the STALE side

Re-confirmed file:line (read-only) that Trade-Lab's live inference has **not** been repointed onto
the engine — it is the stale side on both the feature and outcome axes:

- **Cited executor file is ABSENT.** `backend/src/trade_lab/services/inference/` contains only
  `inference_engine.py` (produces a `Prediction`, no entry-price logic), `outcome_tracker.py`, and
  `features/`. There is **no `trade_executor.py`** in the current Trade-Lab working tree — the brief's
  cited `trade_executor.py:41-79` (`on_prediction`, enter-at-market-when-prediction-fires) is not
  present. The decision-time touch+5m fill is therefore confirmed against the **v2 engine/adapter
  convention**, not against a live TL executor file.
- **Outcome entry is the OLD level price.**
  `services/inference/outcome_tracker.py` `register()` still computes
  `entry_points = float(Decimal(prediction.level_price_ticks) * self._tick_size)` with the docstring
  *"Entry reference is the level's representative price … matching the training labels."* — the OLD
  `level_representative_price` anchor, **not** the honest decision-time trade price.
- **Two DWELL features still run over QUOTE-MID.**
  `services/inference/features/feature_functions.py` computes the two dwell features over **quotes at
  quote-mid** — `int_time_beyond_level` (`:170`) and `int_time_within_2pts` (`:191`) both iterate
  `_interaction_quotes` (`:134`) using `_quote_mid_points` (`:140`, lines `:164/:179/:199`) — while
  `int_absorption_ratio` (`:207`) already uses trade prints. They are **not** re-sourced to TRADE
  PRINTS at the 0.25 grid per `MID_PRICE_SOURCE="trade_price"`.

### OWNER DECISION (ratified, followed exactly)

The **`strategy_core` engine is the canonical ground truth.** Re-source all 3 interaction features to
**TRADE PRINTS** (`MID_PRICE_SOURCE="trade_price"`); re-anchor the canonical OUTCOME to the
decision-time entry (= executor convention); bump `engine_version` **v1 → v2**. The engine is **not**
bent to Trade-Lab's current quote-mid/level convention. **Trade-Lab's repoint onto engine v2 is a
DEFERRED future phase** — it is the remaining gap to full platform alignment and was **not edited**
here (Trade-Lab read-only). Mtime check confirms zero Trade-Lab inference files modified today.

---

## PART 1 — The trade-bar cutover (3 changes + cache fix), file:line

The production decision path now runs on **TRADE bars (0.25 grid)** with **TRADE-PRINT** interaction
features, instead of book-mid bars (0.125 grid) with book-mid features.

1. **Bars → trade-price, BOTH lines.**
   `CQL/src/alpha_lab/agents/data_infra/ml/dashboard_utility_builder.py` `_build_bars_for_date`:
   `price_source="trade"` on **`:351`** (the Nt/147t path) and **`:356`** (the 987t fallback);
   cutover comments + `_process_single_date` docstring updated.

2. **`tick_size` threaded; hardwired `0.125` removed from the trade path.**
   `CQL/.../ml/engine_decision.py`: `TRADE_TICK = 0.25` (`:87`) with
   `assert TRADE_TICK == DEFAULT_TICK_SIZE` (`:88`, single-sources the contract constant), threaded
   through `bars_et_to_engine` (`:108`), `detect_touches`, `resolve_outcome`, and the interaction
   features. `BOOK_MID_TICK = 0.125` (`:84`) is **retained only** for the reachable book-mid
   regression. `within_band` stays **2.0 POINTS** (a points constant, `WITHIN_BAND_PTS=2.0`, compared
   as `abs(m-level)<=2.0`, never tick-scaled — `features.py`/`touch.py` unmodified).

3. **All 3 interaction features → TRADE PRINTS.**
   `CQL/.../tick_store.py` `query_tick_feature_rows` gained keyword **`price_source`** (`:291`,
   default `"book_mid"` preserves all 3 existing callers; `"trade"` routes `price` to the front-month
   TRADE print with `action='T'` at `:346`; raises on unknown at `:309`). `engine_decision`'s
   `compute_interaction_features_engine` pulls all 3 `int_` features via
   `query_tick_feature_rows(price_source="trade")` at the 0.25 grid.

**Cache fix.** `CQL/.../ml/config.py` `MLPipelineConfig.dataset_config_hash` (`:260`) now folds
`strategy_core.constants.BAR_PRICE_SOURCE` + `LABEL_ENTRY_REFERENCE` + `ENGINE_VERSION` into the
payload (`:290-292`, no restated literals), so the dataset cache tag changed
**`89d82fb5` → `b8b2e14d`** and stale book-mid `ml_utility_*` caches are orphaned (never read).
The operator can reclaim disk via `scripts/clear_dashboard_utility_caches.py --hash 89d82fb5 --delete`
(no files deleted from the shared real-data store this phase).

---

## PART 2 — The honest-entry re-anchor (class scheme UNTOUCHED)

### Held byte-identical — only the anchor moved

The 3-class scheme and the MAE-first machinery are **unchanged**:
`SC/constants.py` `DEFAULT_TP_POINTS=15.0`, `DEFAULT_SL_POINTS=30.0`, `DEFAULT_TRAP_MFE_MIN=5.0`,
`LABEL_RESOLUTION="mae_first"`, `WITHIN_BAND_PTS=2.0`, the class strings + `{0,1,2}` encoding, and
`classify_mae_first`/`resolve_outcome` are byte-unchanged (the `git diff` on `outcomes.py` shows only
**docstring** lines moved — the function signature and body are identical). Only
`LABEL_ENTRY_REFERENCE` (a *value*) and the forward-window **start** changed.

### New constants (single-sourced)

- `SC/constants.py:236` `LABEL_ENTRY_REFERENCE` **`"level_representative_price"` → `"realistic_at_decision"`**.
- `SC/constants.py:242` `DECISION_OFFSET_MINUTES = DEFAULT_INTERACTION_WINDOW_MINUTES` (**= 5**) —
  decision fires `offset` (= the interaction window) after the touch, so the feature window
  `[touch, touch+offset]` and the label window `(touch+offset, RTH_END]` **do not overlap** (look-ahead closure).
- `SC/constants.py:249` `FLATTEN_TIME = time(15, 55)` — single-sources the executor no-entry rule.
- Both added to `constants.__all__`. `MID_PRICE_SOURCE="trade_price"` (`:95`) consistent with the
  trade-print re-source.

### engine_version = v2

`SC/__init__.py:33` `ENGINE_VERSION` **`"strategy_core_engine_v1"` → `"strategy_core_engine_v2"`**, with
a rationale comment (decision-formula change: honest-entry re-anchor + trade-print features).

### The re-anchor lives in the ADAPTER; the engine stays PURE

`SC/decisions/outcomes.py` docstrings were re-anchored to decision-time semantics, but
**`resolve_outcome` stays a pure forward-scan** with an **unchanged signature/body**: it knows nothing
about decision time, the offset, the flatten, market data, or timezones. The CQL adapter
(`engine_decision.process_single_date_engine`, `honest_entry=True`) computes, per touch:
1. `decision_ts_et = bar_ts_et + decision_offset` (`engine_decision.py:222`), `decision_offset` single-sourced from config (== `DECISION_OFFSET_MINUTES = 5`);
2. **drop** if `_at_or_after_flatten(decision_ts_et)` (15:55 ET, `:307` single-sourcing `FLATTEN_TIME`) **or** `decision_ts_et >= 16:15` rth_cutoff (`:227`) — the executor no-entry rule;
3. `entry_price = _trade_price_at(decision_ts_utc)` (`:233`) — most-recent front-month TRADE print (`action='T'`, `price>0`, book-valid, 30-min bounded lookback);
4. forward window = `bars_et[(index > decision_ts_et) & (index < 16:15)]` (`:242-243`) → `resolve_outcome(entry_points=entry_price, …, tick_size=0.25, tp=15/sl=30/trap=5, MAE-first)`.

Engine purity verified: `strategy_core` imports **no** pandas/duckdb/pytz/dateutil (the only pandas
is lazy inside `candles/batch.py`, the one documented-permitted module). Book-mid regression
(`honest_entry=False`) keeps the legacy level-price entry + post-touch window for the parity proof.

### NEW vs OLD class balance (informational only — no edge/PnL eval)

| Sample | Bars / entry | Tag | n | tradeable_reversal | trap_reversal | aggressive_blowthrough |
|---|---|---|---|---|---|---|
| OLD (2026-02-09…02-20, ~9d) | book-mid 0.125 + level-price entry | `89d82fb5` | 21 | 18 (85.7%) | 1 (4.8%) | 2 (9.5%) |
| NEW (2026-02-09…02-20, ~9d) | trade 0.25 + trade-print int\_ + decision-time honest | `b8b2e14d` | 25 | 21 (84.0%) | 2 (8.0%) | 2 (8.0%) |

Direction is as expected for an honest re-label: `tradeable_reversal` **share drops**
(85.7% → 84.0%) and the **loss classes grow** (14.3% → 16.0%). The kept-touch **count** differs
(21 vs 25) because the bar grid changed (0.125 → 0.25), shifting touch detection + the honest-entry
drop set — this is the bar+label change, not a pure relabel. A separate honest re-run on
2025-07-07…07-18 (9d, 147t trade bars) gave n=17 surviving → tradeable 15 (88.2%),
aggressive_blowthrough 2 (11.8%), trap 0, with the honest rule also **dropping** many detected touches
(e.g. 07-11: 5 touches all dropped) because their decision_ts lands at/after 15:55 flatten or has no
forward window — the executor no-entry rule, identical on both bar sets. **Small-n, informational
only; no edge/PnL eval run (gate honored).**

---

## PART 3 — Contract: field→constant map, v2 stamp, no-drift, loader binding

### Schema change (one additive, range-typed field)

`SC/contract/schema.py` `LabelPolicy` gained **`decision_offset_minutes: int = Field(gt=0, le=1440)`**,
placed right after `entry_reference` (required because `extra="forbid"` means every emitted key must
be in the schema). `entry_reference` already existed — only its **value** changed via the constant, no
schema change. No other schema fields added. The CQL emitter
(`ml/strategy_contract.py:186-187`) emits both `entry_reference = k.LABEL_ENTRY_REFERENCE` and
`decision_offset_minutes = k.DECISION_OFFSET_MINUTES` (constant-sourced).

### Field → source map (cutover-relevant entries; everything else still constant/config-sourced)

| Contract field | Source | Kind |
|---|---|---|
| `engine_version` | `strategy_core.ENGINE_VERSION` (`strategy_core_engine_v2`) | constant |
| `feature_windows.mid_price_source` | `k.MID_PRICE_SOURCE` (`trade_price`) | constant |
| `label_policy.resolution` | `k.LABEL_RESOLUTION` (`mae_first`, unchanged) | constant |
| `label_policy.entry_reference` | `k.LABEL_ENTRY_REFERENCE` (`realistic_at_decision` — NEW v2 value) | constant |
| `label_policy.decision_offset_minutes` | `k.DECISION_OFFSET_MINUTES` (=`DEFAULT_INTERACTION_WINDOW_MINUTES`=5 — NEW v2 field) | constant |
| `label_policy.tp_points / sl_points / trap_mfe_min` | config (15/30/5, unchanged) | config-allowlist |
| `feature_windows.within_band_pts` | `k.WITHIN_BAND_PTS` (2.0 points, unchanged) | constant |
| `touch_rule.bar_type` | config (147t trade-price tick bar) | config-allowlist |
| `tick_size` | config (0.25 == `DEFAULT_TICK_SIZE`) | config-allowlist |
| `provenance.dataset_config_hash` | `config.dataset_config_hash()` (`b8b2e14d` after cutover) | config-allowlist |

### No-drift coverage + loader binding (measured)

- **No-drift test PASS:** CQL `tests/agents/test_strategy_contract_nodrift.py` **9 passed** (+3 over the
  prior 6): `test_engine_version_is_v2`, `test_label_policy_honest_entry_reanchor_is_constant_sourced`
  (asserts `entry_reference == k.LABEL_ENTRY_REFERENCE == "realistic_at_decision"` **and**
  `decision_offset_minutes == k.DECISION_OFFSET_MINUTES` **and** `offset == DEFAULT_INTERACTION_WINDOW_MINUTES`
  **and** `resolution == "mae_first"` unchanged), `test_v2_bundle_loads_against_v2_and_rejects_v1`.
  Coverage guard confirmed **non-vacuous**: 53 model leaves, all covered; dropping
  `decision_offset_minutes` from its source makes the guard report it uncovered (would fail).
- **Loader validates v2 / rejects v1 (end-to-end, real emitter output):**
  `load_strategy_contract(path, expected_engine_version="strategy_core_engine_v2")` **LOADS**;
  `expected_engine_version="strategy_core_engine_v1"` **RAISES `ContractError`**. Pre-existing on-disk
  bundles under `models/` (v1 / unversioned, `entry_reference=level_representative_price`, no
  `decision_offset_minutes`) correctly **fail-close** against v2 — their re-emit/retrain under v2 is the
  **deferred** next phase.
- SC `tests/test_contract.py` **15 passed** (added `decision_offset_minutes:5` to the inline valid
  fixture). CQL contract suite (nodrift + repoint) **16 passed**.

---

## PART 4 — Decision-diff ALIGNMENT proof + regression

### Research ↔ engine streaming path: IDENTICAL (file-level)

The SC decision-diff harness (`validation/decision_diff_harness.py` + `test_decision_diff.py`, the
two untracked validation files edited — SC engine/production untouched) runs **both** sides under the
**same engine-v2 honest rule**, mirroring the production adapter `process_single_date_engine(honest_entry=True)`:
- **RESEARCH** = CQL `TickStore.build_tick_bars(price_source="trade")`;
- **TRADE-LAB** = streaming `CandleEngine` fed wire-order front-month trades.

Both apply: `decision_ts_et = touch_close + DECISION_OFFSET_MINUTES` (5m, single-sourced); **drop** if
at/after `FLATTEN_TIME` (15:55 ET) or `>= 16:15` ET; entry = realistic front-month TRADE price at the
decision instant (new `DayStreams.trade_price_at`, mirroring `engine_decision._trade_price_at`);
forward window = bars whose close (ET) ∈ `(decision_ts, 16:15]`; `resolve_outcome(MAE-first,
tp=15/sl=30/trap=5)` **held exactly**.

**Result (extended 9 days 2025-07-07…07-18; 07-13 SKIP = Sunday boundary, empty bar set): on EVERY day —**
- **levels identical; zones IDENTICAL; touches IDENTICAL** (count + level_type/ts/direction; matched=all, differing=0);
- the **6 features IDENTICAL** across both sides (trade-print interaction trio
  `int_time_beyond_level`/`int_time_within_2pts`/`int_absorption_ratio` over `action='T'` @0.25 + 3 approach features; `features_identical=True`);
- the honest **survive/drop partition IDENTICAL** (`survive_set_identical=True`);
- labels computed by the **SAME honest decision-time rule on both sides with ZERO flips**.

**VERDICT: ALIGNED.** `validation/test_decision_diff.py` **PASSES** (1 passed, ~70s, not skipped) on the
3 core days.

### Entry-def vs the Trade-Lab executor

The engine's NEW entry reference (touch + 5m decision_offset, trade price at decision_time, flatten
15:55, forward `(decision, 16:15]`) is implemented in the adapter at
`engine_decision.py:222/227/233/242-243`, single-sourcing `DECISION_OFFSET_MINUTES` (5) and
`FLATTEN_TIME` (15:55). **`entry_def_matches_executor = FALSE`** — *not* because the convention
diverges, but because the brief's cited `trade_executor.py:41-79` does **not exist** in the current
Trade-Lab tree (only `inference_engine.py` + the stale `outcome_tracker.py` are present). The
touch+5m trade-price honest fill is therefore confirmed equal to the **v2 engine/adapter** convention,
but cannot be confirmed file:line against a live TL executor here.

### Regression (independently re-run — gates green, bar parity holds, Trade-Lab untouched)

- **SC engine:** `python -m pytest -q` → **97 passed** (incl. `test_outcomes` pure forward-scan
  unchanged; `test_contract` tracks v2 symbolically; v999 negative still wrong).
- **SC gates (real NQ):** `test_production_pair_parity.py` + `test_duckdb_streaming_parity.py` +
  `test_decision_diff.py` → **3 passed** (~200s). **Bar-level production_pair_parity HOLDS** — the
  cutover does not change the bars in that gate. (6 benign `UserWarning: Discarding nonzero nanoseconds`
  from `decision_diff_harness.py:209`, not failures.)
- **CQL tick_store:** **40 passed** — `query_tick_feature_rows` default `book_mid` preserves callers;
  `trade` routes to `action='T'`; unknown raises.
- **CQL repoint parity (real NQ):** `test_decision_repoint_parity.py` → **14 passed, 1 skipped** (~241s).
  The **book-mid engine==legacy byte-exact proof is PRESERVED** via `_bookmid_bars` pinning
  `price_source='book_mid'`/`tick_size=0.125`/`honest_entry=False`; new `test_engine_trade_path_cutover`
  passes (every kept decision empirically `<15:55` and `<16:15` on real NQ). The 1 skip is
  data-conditioned (2025-07-11: no tradeable touch under the honest path), not a failure.
- **CQL contract:** nodrift **9 passed**, repoint **7 passed**.
- **Trade-Lab untouched:** zero tracked-file diffs under `services/inference/`; no inference file
  modified today (mtime check); the flagged stale files predate this phase's SC/CQL edits.
- **Engine purity:** import pulls only stdlib (incl. `zoneinfo`, already present); no
  pandas/duckdb/pytz/dateutil — verified.
- **Trade-path e2e:** `build_utility_dataset(use_engine=True)` ran end-to-end on the sample days,
  writing the new `b8b2e14d` caches with the 3 trade-print `int_` features and decision-time honest labels.

---

## CLOSING

The platform is **cut over and aligned**. Research and the engine streaming path are **single-sourced**
on **trade-print bars (0.25 grid)**, **trade-print interaction features**, and the **decision-time honest
outcome**, all bound to **`engine_version = strategy_core_engine_v2`** and a contract that **validates v2
and rejects v1**. The class scheme (3 classes / tp=15 / sl=30 / trap_mfe_min=5 / MAE-first /
within_band 2.0 pts) is **held exactly** — only the entry anchor and the forward-window start moved.

**NEXT phase (not done here, per the gate):** retrain on the honest trade-bar dataset (`b8b2e14d`) and
read the edge. **No go/no-go and no edge claim is made.**

**Remaining alignment gap (DEFERRED — Trade-Lab read-only, untouched):** Trade-Lab's own inference is the
**stale side** and its repoint onto engine v2 is a future phase — `feature_functions.py` still computes
the two DWELL features over **quote-mid** quotes (`int_time_beyond_level`/`int_time_within_2pts`; only
`int_absorption_ratio` uses trades) and `outcome_tracker.py` (`register`) still uses the **level-price**
entry rather than the decision-time touch+5m trade-price fill.

---

**HARD GATE RESPECTED:** ALIGNMENT only — no retrain, no edge/PnL eval, Trade-Lab read-only/untouched;
3 classes / tp15 / sl30 / trap5 / MAE-first / within_band 2.0pts held exactly; legacy importable; all
changes UNCOMMITTED (SC HEAD `4ce2e61`, CQL HEAD `2f6aa62` unchanged).
