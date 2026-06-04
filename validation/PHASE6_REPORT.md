# PHASE 6 REPORT — Edge-Eval Readiness Scout (INVENTORY ONLY)

**GOAL:** Determine, against the existing CQL + Strategy-core + Trade-Lab infrastructure, (a) which trained model is best and best-aligned with the locked engine / trade-price / 6-feature direction, (b) whether we are retrain-ready on the agreed engine feature space, (c) the state of the Databento NQ data coverage, and (d) whether the next-phase **anchored monthly walk-forward edge eval** can run on existing infra or what must be built first.

**HARD GATE — this was an inventory-only scout.** Nothing was built. Nothing was trained. No backtests/training were run. No production/source code was edited. No git commits. All findings come from read-only operations (Read / Grep / Glob / `ls` / JSON inspection). Every EXISTS / PARTIAL claim is cited with concrete `file:line` evidence.

The single deliverable created is **this file** (`C:/Users/gonza/Documents/Strategy-core/validation/PHASE6_REPORT.md`).

---

## 1. MODEL INVENTORY

Three candidate bundles live under `C:/Users/gonza/Documents/Claude-Quant-Lab/models/`. All three carry `model.cbm + metadata.json + evaluation.json`; **only the `iterations800_depth4` bundle additionally carries `strategy.json`** — i.e. it is the only one bound to the runtime contract (confirmed: `ls` of the three dirs shows `strategy.json` present only in `...iter800_depth4/`).

| # | Dir (short) | Artifacts | Features | OOS f1 / precision@0.70 gate / coverage | trade_utility (exp_15_30 / PF / n) | WF folds (train/test/gap) |
|---|-------------|-----------|----------|------------------------------------------|------------------------------------|---------------------------|
| 1 | `147t_5m_15m` | model.cbm + metadata + eval (**no strategy.json**) | **17** (3 int_* + 14 app_*, incl `app_price_velocity_15m`, `app_volatility_full`, `app_depth_concentration`) | f1 **0.9230** / prec **0.9508** @ cov 0.717 | **11.43** / 5.806 / 618 | 30 / 7 / 1 (non-exp), 33 folds |
| 2 | `147t_5m_30m` | model.cbm + metadata + eval (**no strategy.json**) | **13** (3 int_* + 10 app_*, incl `app_volume_acceleration`, `app_avg_top5_depth`) | f1 **0.9257** / prec **0.9478** @ cov 0.702 | **11.83** / **6.593** / 610 | 30 / 7 / 1 (non-exp), 33 folds |
| 3 | `147t_5m_30m_iter800_depth4` **(PRODUCTION)** | model.cbm + metadata + eval + **strategy.json** | **6** RFECV (contractual order) | f1 **0.9133** / prec **0.9432** @ cov **0.746** | **11.71** / 6.333 / 574 | 40 / 5 / 2 (non-exp), 44 folds |

**Evidence (file:line):**
- Bundle #1: `models/.../147t_5m_15m.../evaluation.json:2-27` (OOS), `:332-334` (gate), `:264-269` (trade_utility), `:419-420` (folds); `.../metadata.json:2-20` (17 features). Provenance caveat: `metadata.json` reports `rfecv_enabled:false` while `evaluation.full_config.model` reports `rfecv_enabled:true` (`evaluation.json:425-431`) — stale metadata field; the 17 selected features confirm RFECV ran.
- Bundle #2: `models/.../147t_5m_30m.../evaluation.json:2-27`, `:328-330` (gate), `:264-269` (trade_utility — highest PF 6.593), `:419-420` (folds); `.../metadata.json:2-16` (13 features). Same stale `rfecv_enabled` metadata caveat (`evaluation.json:421-431`).
- Bundle #3 (PRODUCTION): `models/.../iterations800_depth4/evaluation.json:2-27` (OOS), `:399-401` (gate, prec 0.9432 @ cov 0.746), `:341-346` (trade_utility), `:365-369` (true 3-class balance tradeable 710 / trap 78 / blowthrough 58), `:486-491` (44 folds, train40/test5/gap2), `:444-448` (calibration well-behaved). `.../metadata.json:2-9, :10-17, :23-32`. `.../strategy.json:15-34` (the 6 features in contractual order — **verified directly this run**), `:36-40` (class_map), `:91-100` (label_policy mae_first tp15/sl30/trap_mfe5), `:101-105` (confidence_gate 0.70 / eligible tradeable_reversal / ny_rth), `:74,84-85` (147t / 5m / 30m), `:119-126` (catboost iter800 depth4).

### Which is best — and best aligned?

**Best = #3, `NQ_20260405_147t_5m_30m_multiclass-250602-260220-iterations800_depth4` (the stated PRODUCTION model).**

- **Alignment is decisive.** It is the **only** bundle with a `strategy.json` runtime contract, and that contract literally encodes the agreed direction: `feature_set.names` is **exactly** the 6 RFECV features in contractual order — `int_time_beyond_level, int_time_within_2pts, int_absorption_ratio, app_large_trade_vol_pct, app_avg_trade_size, app_max_spread` (`strategy.json:15-34`, re-verified this run); 3-class map (`:36-40`); gate 0.70 + tradeable_reversal + ny_rth (`:101-105`); mae_first tp15/sl30/trap_mfe5 (`:91-100`). The other two carry **no contract** and bind to **broader, non-6** feature sets (17 and 13) that the runtime does not accept — #1 even uses a 15-minute approach window vs the contract's 30m.
- **Performance is a near-tie, so alignment breaks it.** At the 0.70 gate, tradeable_reversal precision is 0.9432 (#3) / 0.9478 (#2) / 0.9508 (#1); headline OOS f1 0.913 / 0.926 / 0.923; expectancy_15_30 11.71 / 11.83 / 11.43 pts; PF 6.33 / 6.59 / 5.81 — all within each other's precision CI. #3 buys essentially the same edge with **6 features** (lower variance, the locked RFECV set) **and the highest gate coverage (0.746)**, while being the only bundle on the trade-price / engine direction. Net: #3 is the right model.

### Retrain-ready on the agreed engine feature space? — YES (one literal to flip)

All inputs to reproduce a #3-style bundle exist and are wired (engine → dataset → trainer → contract emit):
- **Engine (shared, importable):** `strategy_core` exposes `build_zones` (`zones.py:23`) → `detect_touches` (`touch.py:49`) → `resolve_outcome` (`outcomes.py:111`) → `classify_session` (`sessions.py:69`) + the 6 features (`features.py:59-64` and `:68/103/130/168/194/206`; exported `__init__.py:41-54`); `ENGINE_VERSION="strategy_core_engine_v1"` (`__init__.py:25`).
- **Dataset:** `dashboard_utility_builder.build_utility_dataset(..., use_engine=True)` default (`dashboard_utility_builder.py:57-64, :228`), feeding `engine_decision.py:35-54,149-177`.
- **Trainer:** `ExtremaModelTrainer` (CatBoost + RFECV) `model_trainer.py:36-46,145-164`; `WalkForwardConfig` `config.py:119-137`.
- **Emitter (phase-5, literal-free + engine_version-stamped):** `strategy_contract.build_strategy_contract` (`strategy_contract.py:39,99,119`); `mid_price_source` tracks the engine constant `MID_PRICE_SOURCE="trade_price"` (`strategy_contract.py:179` + `strategy_core/constants.py:95`).
- **Driver + data:** `scripts/train_dashboard_model.py:73-271`; 225 usable Databento NQ sessions in range (room to extend).

**Retrain gaps (none are hard blockers for retrain itself):**
1. **The trade-bar pin (resolvable, by design).** `_build_bars_for_date` is still hard-pinned to `price_source="book_mid"` at `dashboard_utility_builder.py:344` AND `:349` (fallback 987t branch), with the intentional comment at `:340-342` (verified this run) stating the pin is deliberate so phase-4d does not silently repoint the decision layer. Engine/contract ground truth is now `trade_price` (`strategy_core/constants.py:36,95`). The feature/decision path already runs on the engine (`use_engine=True`), but the **bars** fed to it are still book-mid. This is the **next-phase trade-bar cutover**, not a missing input.
2. **Provenance cosmetic (not a gap):** `metadata.rfecv_enabled` is stale on #1/#2 (`false`) vs `evaluation.full_config.model` (`true`). Worth standardizing the emitter; does not block retrain.
3. **Data (informational):** training used 224 sessions (2025-06-02..2026-02-20); the store holds ~225 usable in range and ~310+ across full history — ample headroom to extend the train range / run the edge eval. No data gap blocks retrain.

---

## 2. DATA COVERAGE (2025-06-01 .. 2026-02-22)

**Continuous? NO.** 225 sessions have a non-empty `mbp10.parquet` in range (>96% of expected CME weekday sessions) but there are **3 true weekday gaps** with no holiday explanation. Healthy, but not strictly continuous — the walk-forward fold population must account for 3 missing trading days.

**Per-month session counts:**

| Month | Sessions |
|-------|----------|
| 2025-06 | 25 |
| 2025-07 | 26 |
| 2025-08 | 26 |
| 2025-09 | 26 |
| 2025-10 | 27 |
| 2025-11 | 23 |
| 2025-12 | 27 |
| 2026-01 | 26 |
| 2026-02 | 19 (range ends 2026-02-22) |
| **Total** | **225** |

**Calendar note:** counts follow the **CME futures** calendar, not NYSE — 38 Sunday-evening Globex opens are present, so per-month counts run ~24-27 (higher than NYSE's ~21-22). All 8 US holidays in range HAVE data (CME abbreviated sessions): Juneteenth, July 4, Labor Day, Thanksgiving, Christmas (113,522 rows — shortened), New Year, MLK, Presidents Day. The lone Saturday `2026-02-14` (ohlcv-only, no mbp10) is non-trading and not counted.

**The 3 gaps (weekday, no holiday):**
1. `2025-07-08` (Tue) — no session dir at all.
2. `2025-11-14` (Fri) — no session dir at all.
3. `2025-11-20` (Thu) — dir EXISTS but is EMPTY (no `mbp10.parquet`). Most likely re-fetchable.

**Integrity:** 225/227 in-range dirs have a non-empty `mbp10.parquet` (0 zero-byte files; min 6.32 MB = Christmas, max ~2.0 GB). Remediation for the 3 gaps: re-pull mbp-10 NQ front-month for those dates via the existing `databento_historical` adapter — trivial (~minutes each); none fall on a holiday, so they are genuine fetch omissions, not closures.

Store root: `C:/Users/gonza/Documents/Trade-Dashboard/data/databento/NQ`.

---

## 3. INVENTORY TABLE (items 1–8)

| # | Item | Status | Build estimate |
|---|------|--------|----------------|
| 1 | **Data coverage** 2025-06..2026-02 | **PARTIAL** — 225 usable sessions, NOT continuous: 3 weekday gaps (`2025-07-08`, `2025-11-14`, `2025-11-20` empty) | Re-pull 3 dates via `databento_historical` adapter — ~minutes each |
| 2 | **Train orchestration** (date-range → engine dataset `use_engine=True` → CatBoost → phase-5 contract emit) | **PARTIAL** — full capability exists as composable functions; **no headless/CLI entrypoint** (only Streamlit `render_ml_training_tab`); single-shot (one bundle per run), no multi-fold outer loop | ~80–150 line argparse wrapper looping the 3 existing functions + a fold loop |
| 3 | **Purged/embargoed walk-forward** reachable from CQL | **PARTIAL** — working purged anchored/rolling WF (produced the production model); **no true symmetric embargo**, purge is train-side-only heuristic, not label-horizon-exact to 16:15 RTH cutoff | Reuse as-is for purge; ~0.5–1 day to add label-horizon-exact purge + test-side embargo |
| 4 | **Batch inference** (score OOS touch set → 3-class probs → apply 0.70 gate, in batch) | **PARTIAL** — every constituent exists (one-row-per-touch matrix, batch `predict_proba`, gate logic, constants) but **not assembled** into one OOS-gate function; gate lives only as per-event live code in Trade-Lab; OOS matrix lacks a session column | ~30–60 lines / half a day to assemble + add session column |
| 5 | **PnL / backtest harness** (net expectancy: hit rate, avg win/loss, net PnL, max DD) | **PARTIAL** — full PnL/expectancy/DD/CSV harness EXISTS (`run_backtest.py` + `analyze_backtest.py` + `analyze_trailing_dd.py`) but runs the **LEGACY** `dashboard.engine` pipeline + 3-feature model + 15/15 TP/SL — **NOT** strategy_core engine + production tp15/sl30 6-feature model. Trade-Lab replay emits **signals/outcomes only, no $PnL** | ~1–2 days to repoint signal-gen onto strategy_core engine + production contract; reporting layer reusable as-is |
| 6 | **Entry timing** (look-ahead-safe post-window entry) + **NQ costs** | **PARTIAL** — (a) ENTRY: safe window-close entry exists **only** in streaming/audit path (`trade_executor.py:41-79`, `audit_lookahead.py`), **not** in the research/label path (labels enter at touch-level price at touch instant — entry/feature-availability mismatch). (b) COSTS: **EXISTS** — NQ cost model fully populated | (a) ~0.5 day to port window-close entry into the engine/label/WF path; (b) none — costs reusable |
| 7 | **Cutover readiness** (is the ONLY change book_mid→trade + thread tick_size 0.25?) | **PARTIAL** — NOT minimal: 2 stated changes are necessary but **not sufficient**. (i) flip `price_source` at **two** lines `:344` & `:349`; (ii) collapse `BOOK_MID_TICK=0.125`→0.25 at ~5 engine_decision call-sites; **(iii) un-stated**: re-source the 3 interaction features from **trade prints** (today hardcoded book-mid in `tick_store.query_tick_feature_rows:322-324`) — the deferred "touch-seam drift". Then retrain + parity re-verify | ~0.5–1 day code (4+ edits) + separate retrain/parity |
| 8 | **Vol-regime classifier** (HMM?) for per-fold regime tagging | **PARTIAL** — a heuristic `classify_regime` EXISTS (`monitoring/regime.py:61`), **not** an HMM (0 hmm/GMM matches in CQL); needs caller-supplied EMA/KAMA/ATR/ADX inputs that the WF pipeline does not produce; zero references in `data_infra/ml` | ~0.5–1 day to wrap a per-fold tagger; **RECOMMEND SKIP** for v1 (use a plain ATR-ratio split if a regime cut is wanted) |

**Key file:line evidence (per row):**
- **#2:** `scripts/ml_training_tab.py:939` (build call), `:1110` (train), `:1327`/`:606-625` (save → `build_strategy_contract`); `dashboard_utility_builder.py:57-64,:228`; orchestration only behind Streamlit `st.button` gates (`ml_training_tab.py:914,1056,1326`, `dashboard.py:1196`). `scripts/train_dashboard_model.py` is a separate legacy 3-feature path (no engine, no contract).
- **#3:** `walk_forward.py:37-139` (rolling + expanding, gap_delta); `config.py:119-140`; `ml_training_tab.py:159-433` (integration), `:258-277` (train-side label purge, one-directional heuristic, `n_purged_total`); production `evaluation.json` confirms train40/test5/gap2, 44/44 folds, `n_purged_total=0`. Import gotcha: `alpha_lab.agents` importable **only** with `PYTHONPATH=src` (bare `import alpha_lab` shadows to the Trade-Dashboard package lacking `.agents`).
- **#4:** `dashboard_utility_builder.py:267-294` (one row/touch + 6 feats); `experiment/diagnostics.py:1056-1085` (batch multiclass `predict_proba` → top3_predictions.parquet); gate is per-event in `trade-lab .../inference/inference_engine.py:171-182`; constants `strategy_core/constants.py:238-239`.
- **#5:** `scripts/run_backtest.py:30-42` (legacy `dashboard.engine` import), `:50` (3-feature .cbm), `:581-650`/`:670-701`/`:1040-1077` (win rate/PnL/DD/monthly/CSV); `analyze_backtest.py:218-241` (net expectancy, breakeven); `analyze_trailing_dd.py:50-103`; Trade-Lab `services/replay.py:451-486`, `runtime.py:339-358,509-533`, `inference/outcome_tracker.py:193-213` (Outcome = MFE/MAE pts, no $PnL); grep `pnl|expectancy|drawdown|TradeExecutor` in trade_lab backend → none.
- **#6:** `trade_executor.py:41-79` (entry = market-at-window-close); `audit_lookahead.py:159-177,596-656` (TEST 4 asserts entry==market not level); `strategy_core/constants.py:226` (`LABEL_ENTRY_REFERENCE="level_representative_price"`), `decisions/outcomes.py:111-181` (entry=level rep price, scan from touch+1, no window offset); COSTS: `agents/execution/cost_model.py:22-32,35-81`, `config/instruments.yaml:8-13` (NQ round-turn ~7.78, point_value 20).
- **#7:** `dashboard_utility_builder.py:343-344` & `:348-349` (book_mid pin, **verified this run** incl intentional comment `:340-342`); `engine_decision.py:67-69,108-111,161,184,258,270-282` (BOOK_MID_TICK 0.125 hardwired); `tick_store.py:322-324` (`query_tick_feature_rows` hardcodes book-mid, no price_source param); `strategy_core/features.py:1-23`, `constants.py:86-95`; `parity_harness_v2.py:823-846` (book@0.125 vs trades@0.25 are different values).
- **#8:** `monitoring/regime.py:61,76-80,89-149` (heuristic, no state model); `core/enums.py:115-119`; `monitoring/agent.py:209-241`; grep `hmm|GaussianMixture|hmmlearn` → 0 in CQL.

---

## 4. CLOSING ONE-PARAGRAPH READ — Can we run the anchored monthly walk-forward edge eval on existing infra?

**Not yet on existing infra — the decision/scoring half is ready, but the money half is not.** The locked engine, the purged/anchored walk-forward, the dataset builder, the trainer, the contract emitter, the production 6-feature model, the NQ cost model, and ~225 sessions of clean data all EXIST and are wired (and they already produced the production bundle), so we can build datasets, retrain, and score OOS touches to 3-class probabilities. **What blocks the edge eval, in priority order, is: (1) a PnL/expectancy/drawdown harness on the engine path — the existing harness (`run_backtest.py` + `analyze_backtest.py` + `analyze_trailing_dd.py`) has all the reporting (hit rate, avg win/loss, net PnL, max DD, monthly + cost-adjusted expectancy) but runs the LEGACY `dashboard.engine` + 3-feature model + 15/15 TP/SL, so it must be repointed onto strategy_core + the production tp15/sl30 6-feature contract (~1–2 days); (2) a look-ahead-safe entry rule plumbed into the research/label path — a safe window-close (touch+5min) market entry exists only in the streaming/audit code, while training labels still enter at the touch-level price at the touch instant, so MFE/MAE for the eval must be resolved from an entry at/after window close (~0.5 day; the cost model itself is reusable as-is, just convert points→$ at ×20); (3) a headless, foldable orchestration driver + a batch OOS-gate function — both are trivial assembly of existing pieces (~80–150 lines and ~30–60 lines respectively) but neither exists outside Streamlit/per-event-live code today; and (4) the trade-bar cutover (book_mid→trade at two lines, collapse BOOK_MID_TICK→0.25, re-source interaction features from trade prints) plus retrain, which is the agreed next-phase change and is required for a faithful trade-price eval.** Regime tagging (item 8) is optional and recommended skipped for v1. Net verdict: **NO-GO on existing infra as-is; GO after building the engine-path PnL/expectancy harness + look-ahead-safe entry, wrapping the headless orchestrator + batch gate, and performing the trade-bar cutover/retrain — roughly 3–5 focused days of glue (no novel research), since every underlying capability already exists.**
