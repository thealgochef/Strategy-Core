# PHASE 7 REPORT — Honest-Edge Audit (IDEALIZED vs +5m-ENTRY+COSTS) — NUMBERS ONLY

**GOAL.** The production model's reported edge — `expectancy_15_30 ≈ 11.71 pts`, `PF ≈ 6.33`, `prec@0.70 ≈ 0.943` over **574** OOS gated trades on a 44-fold walk-forward — is **IDEALIZED**. The training label enters the trade at the **level price** at the **touch instant** with **zero costs**, but the decision itself depends on the **post-touch 5-minute interaction features** (`int_time_beyond_level`, `int_time_within_2pts`, `int_absorption_ratio`), which do not exist until **touch + 5 minutes**. So the label path cannot be traded — by the time the model can fire, the price has moved. This phase measures the **honest** edge: a realistic **+5-minute entry** at the market price, with **slippage and commissions**, on exactly the touches the production serve gate would have taken. We then place that honest number **side-by-side** with the idealized number to quantify how much of the reported edge was idealized entry + zero costs.

**HARD GATE (obeyed).**
- **`_build_bars_for_date` stays `price_source="book_mid"` — NOT flipped.** We are auditing the **existing book-mid model**, not the future trade-bar cutover. Verified untouched at `dashboard_utility_builder.py:344` and `:349`.
- **No new / different model trained.** We **reproduced** the existing walk-forward eval with the **SAME spec** (same 6 features, same HPs, same fold scheme) to recover the OOS gated touches. Changing features / HPs / fold-scheme was NOT done.
- **Trade-Lab untouched.** No Trade-Lab file was read-for-write or modified.
- **All changes left UNCOMMITTED.** Only new files were created: the harness `scripts/honest_edge_audit.py` and the artifacts under `data/experiment/honest_edge/`.
- **NO GO/NO-GO declared.** This report **stops at the numbers**. Whether the edge is "profitable," and whether the trade-bar cutover is worth doing, is the **OWNER's call.**

**ARTIFACTS.**
- Harness: `C:/Users/gonza/Documents/Claude-Quant-Lab/scripts/honest_edge_audit.py`
- Full-range enriched parquet: `C:/Users/gonza/Documents/Claude-Quant-Lab/data/experiment/honest_edge/enriched.parquet`
- Full-range results: `C:/Users/gonza/Documents/Claude-Quant-Lab/data/experiment/honest_edge/results.json`
- Validation-subset artifacts: `.../honest_edge/val_enriched.parquet`, `.../honest_edge/val_results.json`

---

## 1. HARNESS DESIGN + EVERY STATED ASSUMPTION

The harness reuses the production engine and metric path end-to-end (no re-implementation of the edge math): `strategy_core` via `engine_decision.process_single_date_engine` for signal generation; `WalkForwardSplitter` + `ExtremaModelTrainer` (CatBoost+RFECV) + `ModelEvaluator` for the reproduction; and `compute_utility_metrics` (imported **by path** from `scripts/ml_training_tab.py`) for the idealized expectancy. Costs come from `config/instruments.yaml`. Imports run under `PYTHONPATH=src` (the `alpha_lab` shadowing gotcha is honored).

**Pipeline (three steps).**
1. **Enrich (STEP 1).** For each session in range, build **book-mid 147t bars** (`price_source="book_mid"`, UNCHANGED), run the engine (`build_zones → detect_touches → resolve_outcome → classify_session`) to produce each touch's row: the 6 contract features, `label_encoded`, the **idealized** `max_mfe`/`max_mae` (from level entry), plus a precomputed **honest** signed `honest_gross_pts` (the +5m realistic outcome) for **every** touch. Appended per-date to the parquet; already-present dates are skipped but prior-day session H/L level state is always re-warmed so a resumed chunk starts with correct levels.
2. **Reproduce the 44-fold walk-forward (STEP 2).** Rolling `train=40 / test=5 / gap=2` (`expanding=False`), RFECV run **once** on the full feature set, then per-fold `CatBoost(iterations=800, depth=4, MultiClass, auto_class_weights=Balanced, random_seed=42)`. Predict only on `split.test_indices` → OOS-only probabilities. Label-purge buffer `max(5, forward_window//500) = 10 min`, identical to production.
3. **Gate + metrics (STEP 3).** Idealized block via the production confusion-matrix + `compute_utility_metrics`; honest + baseline blocks via the precomputed honest outcomes filtered by the respective gate.

**EVERY STATED ASSUMPTION (explicit):**

| # | Assumption | Value / rule |
|---|------------|--------------|
| A1 | **Signal generation** | `strategy_core` ENGINE on **book-mid 147t** bars (`process_single_date_engine`; `BOOK_MID_TICK=0.125`). No legacy `dashboard.engine`. |
| A2 | **Entry rule (honest)** | `entry_ts = touch-bar close (ET) + interaction_window (5 min)` — exactly when the 3 interaction features (and thus the prediction) first exist. Entry **price = front-month book-mid** `(bid_px_00+ask_px_00)/2`, most-recent quote with `ts_event <= entry_ts` (bounded 30-min lookback). The honest fill is on the **same book-mid surface** the model and its bars live on. Entry is **never** the level price, **never** a future price. |
| A3 | **Entry slippage** | 1 tick = 0.25 pt **adverse** in the entry fill (long pays mid+0.25; short sells mid−0.25). |
| A4 | **Exit slippage** | 1 tick = 0.25 pt **adverse** in the exit fill (TP / SL / cutoff). `honest_gross_pts` is signed and already includes **both** entry and exit slippage → every TP resolves to **+14.75**, every SL to **−30.25**. |
| A5 | **Cost scheme (no double-count)** | Slippage (1 tick/side = 0.5 pt = **$10** round-turn) is modeled **directly in the fills**. Commission = `(exchange_nfa 2.14 + broker 0.50) × 2 = $5.28` RT, subtracted only from the **$** P&L (`commission_pts = 5.28/20 = 0.264`). **Total adverse RT = $15.28.** (Cross-check: `instruments.yaml` NQ `total_round_turn=7.78` bundles only 0.5-tick/side; per the prompt's adverse-fill spec we model a **full 1 tick/side**, hence the larger figure.) |
| A6 | **Points → $** | `point_value = 20.0`, `tick_size = 0.25`. |
| A7 | **Flatten** | **15:55 ET** — if `entry_ts (touch+5m)` is at/after 15:55, `traded=False` (matches `trade_executor.on_prediction`). |
| A8 | **Cutoff / mark** | **16:15 ET** — forward scan covers book-mid bars with `close_ts ∈ (entry_ts, 16:15 ET]`; if neither TP+15 nor SL−30 is hit, exit at last bar close ≤ cutoff (`exit_reason='cutoff'`, mark-to-market). |
| A9 | **Bracket resolution** | TP **+15** / SL **−30**, **MAE-first** (adverse side checked before favorable each bar), bracketed from the **REAL +5m entry** — matching `resolve_outcome`/`classify_mae_first`. |
| A10 | **Idealized gate** | `argmax predicted class == tradeable_reversal` (`raw_pred==0`) — the exact `(eval_y = label_encoded==0, eval_pred = raw_pred==0)` confusion matrix `ml_training_tab` feeds to `compute_utility_metrics`. (This is **argmax**, NOT prob≥0.70.) |
| A11 | **Honest / production serve gate** | `prob_reversal >= 0.70` **AND** `session(event_ts) == ny_rth` **AND** `eligible_class = tradeable_reversal` (per `strategy.json`). |
| A12 | **Baseline gate** | Drops the prob/class gate; keeps **only** `ny_rth`. Same +5m entry, same TP/SL/MAE-first, same costs — only the gate differs, so it is apples-to-apples vs the gated honest block. |
| A13 | **Walk-forward** | `train=40 / test=5 / gap=2`, **ROLLING** (`expanding=False`); RFECV once; CatBoost `800/depth4/MultiClass/Balanced/seed42`; purge `max(5, fw//500)=10 min`; predict on `test_indices` only. |

**Look-ahead guards (audited).** (1) Honest entry price uses only quotes with `ts_event <= touch+5m`. (2) Forward scan is strictly `bars.index > entry_ts`. (3) Idealized labels use forward bars strictly after the touch bar, end-capped at 16:15. (4) The gate uses only fold-**test** predictions from models trained on **purged** train rows. (5) +5m entry is causally consistent — that is exactly when the prediction becomes available.

---

## 2. THE ANCHOR — did IDEALIZED reproduce ~11.71 / ~574 trades?

**Sanity question:** before comparing honest vs idealized, do we measure the *same trades* the production model reported?

**ANSWER: NO — the anchor did NOT reproduce.** This is flagged as a **BLOCKING** finding; the honest numbers below are therefore **NOT certified apples-to-apples** against the published 11.71.

| Metric | Production target (`evaluation.json`) | This run (reproduced) | Δ |
|--------|---------------------------------------|-----------------------|---|
| Idealized expectancy_15_30 | **11.71 pts** | **12.51 pts** | +0.80 pts (+6.9%) |
| Profit factor | **6.333** | **8.54** | +2.21 |
| n_simulated_trades (gated) | **574** | **452** | −122 (−21.3%) |
| Confusion (tp / fp) | 532 / 42 | 427 / 25 | — |
| Precision | 0.927 | 0.945 | +0.018 |

Both confusion matrices are **internally consistent** with their reported metrics — `(427×15 − 25×30)/452 = 12.51`, `PF = (427×15)/(25×30) = 8.54`; production `(532×15 − 42×30)/574 = 11.708 → 11.71`, `PF = 7980/1260 = 6.333`. So the gap is a **genuinely different (smaller) trade population**, not an arithmetic or mechanism error.

**ROOT CAUSE — data-side, not harness-side (fully diagnosed):**
- The reproduction runs on a **smaller touch population**. Full-range enriched = **654** touches vs production `full_dataset_class_balance` = **846**. By class: `tradeable_reversal` **554 vs 710** (−22%), `trap_reversal` **42 vs 78** (−46%), `aggressive_blowthrough` **58 vs 58** (**exact match**). OOS touches **541 vs 708**; idealized-gated **452 vs 574**.
- The **harness is faithful.** Running the *actual* production builder `build_utility_dataset(use_engine=True)` on the *exact* production `dates_used` list (incl. the Sunday 2025-06-08) reproduces the per-date touch counts **bit-for-bit** (2,3,1,6,5,4,3,5,3,2 → 34 on the first 11-date window; and 0 touches on 2025-06-08, same as the harness). The walk-forward spec (44 folds confirmed), RFECV-on, CatBoost HPs, and the `compute_utility_metrics` path are all correct and unchanged.
- **Conclusion:** the **current** Databento NQ store yields ~23% fewer reversal/trap touches than the snapshot present when the production `evaluation.json` (11.71/574) was generated — consistent with the store having been **re-curated** since (the multi-instrument contamination cleanup noted in `databento-nq-store`). The exact **574-trade** set is **not recoverable from the current store**; recovering it would require the original store snapshot.

**Implication:** the honest and baseline numbers below are computed on a **faithfully-reproduced but DIFFERENT (smaller)** trade set than the published 11.71 idealized set. The **qualitative** finding is unaffected; the **quantitative** honest-vs-11.71 comparison is **unanchored**.

---

## 3. PART 3 — IDEALIZED vs HONEST SIDE-BY-SIDE (the headline gap)

**Coverage: FULL RANGE.** STEP 1 enriched the full `2025-06-02 .. 2026-02-22` span (last available session **2026-02-20**): **184** trading dates that yield touches (226 store sessions scanned; the 42 non-yielding are Sundays/holidays/thin sessions producing 0 touches when built from the current store — verified the production builder reproduces those 0-touch days bit-for-bit). **654** total enriched touches. STEP 2+3 ran a **complete 44-fold** rolling walk-forward (all 44 folds valid; matches production `n_total_folds=44`) → **541** OOS test touches, of which **51** are `ny_rth`, **22** pass the 0.70+ny_rth gate, **19** honestly traded. This is a **COMPLETE run of the full range** — NOT a partial. (The shortfall vs production 846/708 is the data-store difference diagnosed in §2.)

### The headline gap (per-trade, on the reproduced OOS gated set)

| | Idealized | Honest (+5m entry + costs) | Gap |
|---|-----------|----------------------------|-----|
| Per-trade expectancy | **+12.51 pts** | **−4.461 pts** net (**−4.197** gross) | **−16.97 pts** swing (net) |
| Profit factor | **8.54** | **0.653** net (0.670 gross) | edge inverts |
| In $ | ≈ +$250/trade | **−$89.23/trade** net | — |

**The +5m honest entry turns the idealized clean-reversal edge NEGATIVE.** Roughly half of the gated touches the idealized label scores as clean reversals become **−30 stop-outs** once you enter 5 minutes late. (Caveat from §2: the +12.51 is the *reproduced* idealized number on the smaller set, not the published +11.71 — so this is the honest-vs-idealized gap *on the reproduced population*, not a certified honest-vs-11.71 comparison.)

### Full honest gated block (`prob_reversal≥0.70` AND `ny_rth`, +5m book-mid entry + costs)

| Field | Value |
|-------|-------|
| n gated | 22 (3 rejected: flatten / no-quote / no-forward-bar) |
| n traded | **19** |
| Hit rate | **0.579** (11 TP / 8 SL) |
| Avg win | **+14.75 pts** |
| Avg loss | **−30.25 pts** |
| Expectancy (gross) | **−4.197 pts** |
| Expectancy (net) | **−4.461 pts** = **−$89.23 / trade** |
| Profit factor (gross / net) | **0.670 / 0.653** |
| Total gross PnL | **−$1,595.00** |
| Total net PnL | **−$1,695.32** |
| Max drawdown (net equity, ordered by event_ts) | **$2,151.40** |

### BASELINE — ALL eligible `ny_rth` OOS touches, NO model gate (same honest +5m entry + costs)

| Field | Value |
|-------|-------|
| n traded | **48** |
| Hit rate | **0.6875** (33 TP / 15 SL) |
| Avg win / loss | **+14.75 / −30.25 pts** |
| Expectancy (gross) | **+0.6875 pts** |
| Expectancy (net) | **+0.4235 pts** = **+$8.47 / trade** |
| Profit factor (gross / net) | **1.073 / 1.044** |
| Total net PnL | **+$406.56** |
| Max drawdown | **$2,502.80** |

**Does gating add value, net?** On this reproduced set, **NO** — the unfiltered `ny_rth` baseline is **barely net-positive** (**+$8.47/trade**, PF 1.044), while the **0.70 model gate SELECTS a WORSE honest subset** (**−$89.23/trade**, PF 0.653). I.e. the 0.70 gate underperforms even the no-gate `ny_rth` baseline on this set. (State as measured; no verdict.)

### Per-fold table (consistency + counts)

Across all 44 folds, **16 folds** had ≥1 honestly-traded gated touch (19 trades total). Wins land at exactly **+14.75** gross (1-tick-slipped TP), losses at exactly **−30.25** gross (1-tick-slipped SL); **8 of 19** gated trades stopped out.

| Fold | n | Hit | Net exp (pts) | | Fold | n | Hit | Net exp (pts) |
|------|---|-----|---------------|---|------|---|-----|---------------|
| 0  | 1 | 1.00 | +14.486 | | 17 | 1 | 1.00 | +14.486 |
| 1  | 1 | 0.00 | −30.514 | | 18 | 2 | 0.50 | −8.014 |
| 3  | 1 | 1.00 | +14.486 | | 26 | 1 | 0.00 | −30.514 |
| 4  | 1 | 0.00 | −30.514 | | 29 | 3 | 1.00 | +14.486 |
| 5  | 1 | 0.00 | −30.514 | | 36 | 1 | 1.00 | +14.486 |
| 6  | 1 | 0.00 | −30.514 | | 37 | 1 | 0.00 | −30.514 |
| 7  | 1 | 1.00 | +14.486 | | 41 | 1 | 0.00 | −30.514 |
| 13 | 1 | 1.00 | +14.486 | | (fold 11) | 0 | — | — |
| 14 | 1 | 1.00 | +14.486 | | | | | |

The idealized per-fold precision mirrors the production `fold_metrics` shape (most folds 0.9–1.0 precision), but on the reduced touch set.

### Validation subset (labeled partial, sanity only — `2025-12-15 .. 2026-02-20`)

48 dates / 173 touches → 5 WF folds → 69 OOS test touches (8 `ny_rth`). Idealized **14.18 pts** / PF 27.0 / n=55 (tp=54, fp=1; `(54×15−1×30)/55=14.18`). Honest gated **n=2** (one +14.75, one −30.25) → exp_net **−8.014 pts** = −$160.28/trade. Baseline n=8, hit 0.875, exp_net **+8.861 pts**, +$1,417.76. The subset confirms the pipeline computes all three blocks correctly and the honest mechanics (TP=+14.75, SL=−30.25) are exact; `ny_rth` touches are sparse (~8/69 OOS ≈ 0.116, consistent with production `rth_fraction ≈ 0.18`), so the gated honest n is tiny on a subset — a data-coverage property, not a defect.

---

## 4. VERIFICATION SUMMARY

**Anchor (BLOCKING, disclosed).** Idealized reproduced **12.51 pts / PF 8.54 / n=452**, NOT the production **11.71 / 6.333 / 574**. Independently re-checked against `results.json`, the enriched parquet, `compute_utility_metrics`, and the production `evaluation.json` (target self-consistent: tp=532/fp=42 → 11.708→11.71, PF 6.333, 44 folds, train40/test5/gap2/expanding=false, CatBoost iter800/depth4/MultiClass/Balanced/RFECV, 6 features match). Root cause confirmed **data-side**: current store has 654 touches (554/42/58) vs production 846 (710/78/58); `aggressive_blowthrough` matches exactly (58=58), reversal/trap are ~22–46% short. The fold scheme, model spec, and metric path are all correct — only the touch population differs. Author correctly set `idealized_reproduced_1171 = false`; honest numbers are **not** presented as apples-to-apples vs 11.71.

**Look-ahead.** Adversarial + empirical audit of all five required checks — **NONE found.** (1) Entry `= touch-close + 5m` exactly; entry price = book-mid from a quote with `ts_event <= entry_ts`. An independently re-fetched quote for a real traded row gave mid 21231.75 → +0.25 long slip = 21232.0 (the stored entry), while the mid **5 min later** (21239.0) differs — proving no future quote leaks. (2) Forward scan strictly `> entry_ts`, `<= 16:15`; MAE-first; **every** TP = +14.75 and **every** SL = −30.25 (entry slippage cancels in the bracket-relative outcome — no double count; short-side sign correct). (3) Gate uses fold-**test** predictions only; 44 folds (0..43), 0 duplicate touches across test sets, 0 test-window overlaps, probs sum to 1.0, `raw_pred==0 ≡ argmax==0`; purge buffer `max(5, 5000/500)=10 min` applied as `train_ts <= test_start − 10m` — a touch is never scored by a model trained on it. (4) 0 traded rows at/after 15:55 (flatten) or 16:15 (cutoff); unresolved → mark-to-market. (5) Costs: 1 tick/side ($10 RT) in fills, commission $5.28 RT in $/net only (`commission_pts=0.264`), ×20 — no double counting. Two **immaterial** notes only: the honest forward scan selects bars by *close* timestamp (same bar convention as the production labeler — inherent granularity, not directional look-ahead); and a `<16:15` vs `<=16:15` boundary one-bar difference (only 1 of 371 traded rows hit `cutoff`).

**Fidelity.** Harness signal-gen uses the `strategy_core` engine via `process_single_date_engine` (NO legacy `dashboard.engine` import — grep clean); idealized mechanism mirrors `ml_training_tab.py:301-304` and calls the SAME `compute_utility_metrics`; gate matches `strategy.json` (0.70 / tradeable_reversal / ny_rth 09:30–16:15); book-mid pin intact (`price_source=book_mid`, `BOOK_MID_TICK=0.125`); reproduction is a faithful twin of `run_walk_forward_training` (no new/different model). Enriched base rows verified **bit-exact** vs `build_utility_dataset(use_engine=True)` on overlapping touches (6 features + `label_encoded` + `max_mfe`/`max_mae` to 1e-6). Baseline is apples-to-apples (same `_honest_block`, same costs, only the gate differs).

**Regression.** Strategy-core engine suite **97 passed** (0.47s). CQL phase 4–5 standing tests **56 passed** (185.51s, exit 0). Scope sweep clean: CQL tracked diffs are only the pre-existing phase 4–6 working tree; the audit added only **new/untracked** files (`scripts/honest_edge_audit.py`, `data/experiment/honest_edge/*`). `_build_bars_for_date` still `book_mid`. SC and Trade-Lab git status unchanged from the opening snapshot. Nothing staged, nothing committed.

---

## 5. CLOSING

The numbers are presented. On the reproduced full-range OOS set, the **idealized** edge of **+12.51 pts/trade** (which itself reproduced the production *mechanism* but at **452** trades, not the published **574**, because the current store yields a smaller touch population than the 11.71 snapshot) collapses under a realistic **+5-minute book-mid entry with slippage and commissions** to a **honest net −4.461 pts (−$89.23)/trade**, PF 0.653, on 19 gated trades — while the unfiltered `ny_rth` baseline sits at a barely-positive **+0.4235 pts (+$8.47)/trade**. The idealized anchor did **not** reproduce ~11.71, so these honest figures are **not certified apples-to-apples** against the production-reported edge. **Whether this honest edge is acceptable, and whether the trade-bar cutover is worth doing, is the OWNER's call. This report declares no GO/NO-GO and makes no "profitable" determination.**
