# ARCH_STATE_RECON — architecture-reviewer handoff

> **Regenerated 2026-07-25.** Read-only reconnaissance. Every fact below was read out of the
> three working trees, the GitHub REST API, the local store, or a live `python` probe in this
> session — nothing is carried over from prior reports or from an assistant's memory. This file
> **replaces** the previous `ARCH_STATE_RECON.md` (mtime 2026-06-15 18:29, 62,786 bytes,
> generated when SC HEAD was `4b08ba1` and both pins were at `256020c`).
>
> **Repos.** SC `C:\Users\gonza\Documents\Strategy-core` (pkg `src/strategy_core/`) ·
> TL `C:\Users\gonza\Documents\Trade-Lab` (backend under `backend/`) ·
> QL `C:\Users\gonza\Documents\Claude-Quant-Lab` (remote is named `Quant-Lab`).
>
> **Method.** `git ls-remote` for origin tips (no fetch — remote-tracking refs untouched);
> `git status --porcelain=v2 --branch` for ahead/behind; GitHub REST
> `/repos/{owner}/{repo}/actions/runs` for CI; filesystem walk for the store and bundles;
> `python -c` import probe for the environment. No tracked file was modified, staged, or
> committed. This file is the only write, and it is untracked.

---

## 1 — REPOS

All three repos are on branch **`platform-refactor`**, all three are **exactly in sync with
origin (+0 / −0)**, and all three have **zero tracked modifications** — every dirty entry is
untracked (`??`). No stashes in any repo.

| | SC (Strategy-Core) | TL (Trade-Lab) | QL (Quant-Lab) |
|---|---|---|---|
| local tip | `9d49353` | `14ed624` | `5ab6da9` |
| origin/platform-refactor | `9d49353` | `14ed624` | `5ab6da9` |
| ahead / behind | **+0 / −0** | **+0 / −0** | **+0 / −0** |
| tracked modifications | none | none | none |
| origin/main | `fd53e06` | `a191202` | `5a096a1` |

**Tips in full:**

| Repo | SHA | Subject | Date |
|---|---|---|---|
| SC | `9d4935346bf42c5d19916e05dbe21dd67c46875c` | `docs: INGEST window close record - schema-diff verdict, D-P-17 deviation, identity results, conversion counts, honest-naming ruling, verify 7-confirmed/6-refuted (INGEST P5)` | 2026-07-11 03:50:11 −0500 |
| TL | `14ed624ece07af65937190e681322c68801b3e5b` | `feat: add readme` | 2026-07-15 23:03:38 −0500 |
| QL | `5ab6da99953f72c5431b8bc1cfd0e039d3d132aa` | `fix(tests): schema_problems fixtures built with explicit arrow types - portable across pandas 3/pyarrow 25 cold installs (INGEST greenlight CI fix)` | 2026-07-11 13:10:06 −0500 |

> **Note on the TL tip.** `14ed624` (2026-07-15; 4 files, +239/−82: `README.md`,
> `backend/.env.example`, `backend/README.md`, `.claude/scheduled_tasks.lock`) sits **after** the
> INGEST pin chore and **is not covered by any window record in PROGRESS**. It is the only
> commit in any of the three repos that no window record accounts for.

### Dirty files by name (all untracked)

**SC — 45 entries, repo root only:**
`ARCH_STATE_RECON.md` (this file) · `COCKPITFIX_GREENLIGHT_REPORT.txt` ·
`COCKPIT_GREENLIGHT_REPORT.txt` · `COCKPIT_SC_DIFF.txt` · `D1A_SC_DIFF.txt` · `D1B_SC_DIFF.txt` ·
`E3_SC_DIFF.txt` · `ENVFIX_REPORT.txt` · `EXEC_GREENLIGHT_REPORT.txt` · `EXEC_SC_DIFF.txt` ·
`E_SC_DIFF.txt` · `INGEST_GREENLIGHT_REPORT.txt` · `INGEST_SC_DIFF.txt` · `LAND_SC_DIFF.txt` ·
`PRESETS_GREENLIGHT_REPORT.txt` · `PRESETS_SC_DIFF.txt` · `PROPSIM_GREENLIGHT_REPORT.txt` ·
`PROPSIM_SC_DIFF.txt` · `QLUI_SC_DIFF.txt` · `REPORT_GREENLIGHT_REPORT.txt` ·
`REPORT_SC_DIFF.txt` · `SEED_GREENLIGHT_REPORT.txt` · `SEED_SC_DIFF.txt` · `STATE_RESYNC.md` ·
`W1_SC_DIFF.txt` · `W2FIX_SC_DIFF.txt` · `W2_SC_DIFF.txt` · `W3A_READER_PROOF.log` ·
`W3A_READER_SC_DIFF.txt` · `W3A_SC_DIFF.txt` · `W3B_0212_DIFF.log` · `W3B_0212_RAW.log` ·
`WARMFIX_GREENLIGHT_REPORT.txt` · `_ingest_sc_suite.out` · `_ingest_sc_suite2.out` ·
`_ingest_sc_suite_final.out` · `algo-dev.md` · `b2_context.md` · `route_seam_report.json` ·
`scratch_w3a_reader_proof.py` · `scratch_w3b_0212_diff.py` · `scratch_w3b_0212_raw.py` ·
`scratch_w3b_0212_raw_run.out` · `scratch_w3b_0212_run.out`

**TL — 23 entries:**
`BASELINE_REPORT.md` · `COCKPIT_STATES.md` · `D1_CHARACTERIZATION.md` · `LAND_TL_DIFF_v2.txt` ·
`PLUGIN_SDK_RECON.md` · `READER_CORRECTNESS_PROOF.md` · `READER_PIN_RECON.md` ·
`REPORT_RECON.md` · `SEED_PARITY_RECON.md` · `W3B_LIVELOCK_ROOTCAUSE.md` · `WARM_PERF_RECON.md` ·
`WEDGE_CAPTURE.md` · `backend/D1_CHARACTERIZATION.md` · `backend/W3B_FIX_TL_DIFF.txt` ·
`backend/_ingest_tl_suite_final.out` · `backend/package-lock.json` · `ql_ci_logs.zip` ·
`ql_exec_ci_logs.zip` · `scratch_seed_parity.py` · `scratch_seed_parity_results.json` ·
`test.md` · `tl_ci_logs.zip` · `tl_exec_ci_logs.zip`

**QL — 34 entries, repo root only:**
`.w3_new_bundle_name` · `CACHE_GUARD_QL_DIFF.txt` · `E3_QL_DIFF.txt` · `E_QL_DIFF.txt` ·
`INGEST_QL_DIFF.txt` · `LAND_QL_DIFF.txt` · `PRESETS_QL_DIFF.txt` · `PROPSIM_BASELINE.md` ·
`PROPSIM_QL_DIFF.txt` · `QLUI_QL_DIFF.txt` · `QL_TRAINING_UI_RECON.md` ·
`QL_UI_TRAIN_GAP_RECON.md` · `SEED_QL_DIFF.txt` · `W1_QL_DIFF.txt` · `W2_QL_DIFF.txt` ·
`W3A_PRECEDING_6_REVIEW.txt` · `W3A_QL_DIFF.txt` · `W3A_READER_QL_DIFF.txt` ·
`W3_CONFIG_RECON.md` · `W3_WARMER_DIFF.txt` · `_ingest_ql_suite.out` ·
`_ingest_ql_suite_final.out` · `_p4a_run.out` · `_p4b_run.out` · `_p4c_run.out` ·
`_p5_conversion.out` · `route_seam_report_ingest.json` · `scratch_ingest_identity.py` ·
`scratch_ingest_p4b.py` · `scratch_qlui_acceptance.py` · `scratch_w3a_p2_gate.py` ·
`scratch_w3b_0212_regen.out` · `scratch_w3b_0212_regen.py`

### Latest CI runs (GitHub REST API, read 2026-07-25)

| Repo | workflow | run id | # | head_sha | branch / event | conclusion | created |
|---|---|---|---|---|---|---|---|
| SC | `ci` | **29162591811** | 13 | `9d4935346bf42c5d19916e05dbe21dd67c46875c` (= tip) | platform-refactor / push | **success** | 2026-07-11T17:58:33Z |
| TL | `backend-ci` | **29470434376** | 15 | `14ed624ece07af65937190e681322c68801b3e5b` (= tip) | platform-refactor / push | **success** | 2026-07-16T04:03:48Z |
| QL | `ci` | **29162951541** | 13 | `5ab6da99953f72c5431b8bc1cfd0e039d3d132aa` (= tip) | platform-refactor / push | **success** | 2026-07-11T18:10:11Z |

Immediately prior runs, for the INGEST-land picture:

| Repo | run id | # | head | conclusion |
|---|---|---|---|---|
| TL | 29162631478 | 14 | `3466aff` (pin chore → `9d49353`) | success |
| QL | 29162655755 | 12 | `3b470d3` (pin chore → `9d49353`) | **failure** |
| SC | 29136911173 | 12 | `1a58aa8` (PRESETS) | success |
| QL | 29136917345 | 11 | `49c2f22` (PRESETS) | success |

**Every current tip is CI-green.** The one red in recent history is QL #12 on the pin chore
`3b470d3` — fixed by the tip commit `5ab6da9` (`schema_problems` fixtures rebuilt with explicit
Arrow types, portable across pandas 3 / pyarrow 25 cold installs). **None of the five INGEST-era
run ids (SC #13, TL #14, TL #15, QL #12, QL #13) appear anywhere in PROGRESS** — see §3.3.

### Pin lines (verbatim)

`Trade-Lab/backend/pyproject.toml:18`
```
  "strategy-core @ git+https://github.com/thealgochef/Strategy-Core.git@9d4935346bf42c5d19916e05dbe21dd67c46875c",
```

`Claude-Quant-Lab/pyproject.toml:36`
```
    "strategy-core @ git+https://github.com/thealgochef/Strategy-Core.git@9d4935346bf42c5d19916e05dbe21dd67c46875c",
```

Both consumers pin **SC `9d49353`, which is SC's current tip** — consistent, current, and
CI-witnessed by cold install on both consumers' fresh runners.

---

## 2 — RULINGS

### SC `docs/DECISIONS.md` — plan-era / §9 list

Recorded under *"Plan-era rulings (full text in PLAN §9; status here is living)"*:

| id | status | ruling |
|---|---|---|
| 9.1 | RATIFIED | Plugin Protocol + registry-time assertion. |
| 9.2 | RATIFIED | In-package strategy registry. |
| 9.3 | RATIFIED | Two-axis versioning. |
| 9.4 | **PARKED** | Time bars are Phase F. |
| 9.5 | RATIFIED | Keep `strategy_core` name + `strategies/<id>/` layout. |
| 9.6 | RATIFIED | SHA-pin SC in QL (declared-not-enforced; QL cold-install debt named). |
| 9.7 | RATIFIED | TL local contract deleted. |
| 9.8 | RATIFIED | Barrier protocol; TL outcome tracker retired. |
| 9.9 | **PARKED** | Parameterized session set; behind W3 green + soak (D-P-10). |
| 9.10 | RATIFIED | Quote accessor. |
| §3-CORRECTION | RATIFIED | Direction stays platform (generic); the side→direction MAP is plugin-owned wire vocabulary. Enforced W1 P2c/P4c: constant removed, plugin ships lowercase `{"low":"long","high":"short"}`, emitter sources it verbatim. **Supersedes / OVERTURNS the D-E3-e "cosmetic" classification.** |

> The 9.6 status line still reads *"declared-not-enforced; QL cold-install debt named"*, while
> the `Current state` note (PROGRESS:33) records **9.6 ENFORCED — witnessed 2026-06-10** and the
> debt CLOSED. The DECISIONS one-liner is the stale half of that pair.

### SC `docs/DECISIONS.md` — every D-P id (one-line ruling)

| id | status | one-line ruling |
|---|---|---|
| **D-P-01** | RATIFIED | Tracer-dye: zero rehab of pre-convergence models; acceptance only on a FRESH model through the converged pipeline. |
| **D-P-02** | RATIFIED | Legacy QL artifacts untrusted, never tested against — deletion, not repair. |
| **D-P-03** | RATIFIED | L1-consumption invariant: research/replay consume ONLY the L1 projection (trades + TOB-change-deduped quotes) of the store parquets through ONE canonical SC reader; the historical API exists solely for the warm-start slice. |
| **D-P-04** | RATIFIED | Flatten by NY futures close daily; `FLATTEN_TIME` 16:40 ET, anchored to the decision's OWN trading day. |
| **D-P-05** | RATIFIED | F6/F7 research-causality fixes ride the convergence; future training-data change accepted. |
| **D-P-06** | RATIFIED | Warm-start: at startup AND reconnect, feed the trading day's events from 18:00 ET before going real-time; Chicago seed retired. |
| **D-P-07** | RATIFIED | Prediction journaling: append-only predictions/outcomes/drops surviving restarts. |
| **D-P-08** | RATIFIED | Repo privacy flip deferred indefinitely; tokens land and prove green in CI BEFORE any flip. |
| **D-P-09** | RATIFIED | `platform-refactor` is never squash-merged (pinned-SHA orphan risk). |
| **D-P-10** | RATIFIED | S9.9 and Phase F are PARKED behind the W-plan (W1 → W2 → W3 → live + soak). |
| **D-P-11** | RATIFIED (2026-06-12) | Verification-of-completion discipline: (a) a claim of completion is never evidence — only a verified artifact is; (b) window-close gates run against the COMMITTED tree, never the working tree; (c) any unreviewed mid-greenlight commit is stop-and-report first. |
| **D-P-12** | RATIFIED (2026-06-12) | Soak pre-registration: 7 trading days, Day 0 supervised and uncounted; 5 gating SYSTEM criteria; MODEL criteria recorded but never gating; serving-path fix RESTARTS the clock, environmental outage EXTENDS it. |
| **D-P-13** | RATIFIED (2026-06-12) | W3 proof-bundle training configuration = QL `D-036` verbatim; `D-037` supersedes the stub-exclusion pre-ruling (`app_max_spread` rides the W3b gate). |
| **D-P-14** | RATIFIED (2026-06-12) | Reader-cost ruling: the W3 build runs ONCE overnight at measured cost (24.1 h projection); `src/strategy_core` frozen through W3 + soak; a READER-PERF window scheduled post-soak. |
| **D-P-15** | RATIFIED (2026-06-12) | W3A-READER: D-P-14's freeze SUPERSEDED for one component — `DatabentoParquetSource` decode vectorized pre-build under a full-day event-by-event IDENTITY PROOF (5,218,914 + 10,720,798 events identical, ns-exact) plus the full drift net; the row-wise path deleted only on full green. |
| **D-P-16** | RATIFIED (2026-07-03) | W3b READER ADOPTION on the reduced-coverage re-gate: the vectorized reader is THE reader for research, serving and the gate; the pre-vectorization reader RETIRED; bundle `NQ_W3_20260617T220752Z` supersedes `NQ_W3_20260613T055600Z`; 35 of 73 days re-gated, the other 38 accepted risk bounded by the correctness proof + stress-weighted batch≡stream greens. |
| **D-P-17** | **ADOPTED IN-WINDOW (2026-07-11)** | INGEST: action-bearing TOB schemas emit trades — `_decode_batch` classifies `action∈{T,TRADE}` rows as Trade events for `is_tob` schemas (mbp-1/cmbp-1/tbbo) when the file carries an `action` column, exactly the mbp-10 rule; bbo/cbbo keep quotes-only. AMENDS the D-P-15 proof-contract line (vacuous until now — no mbp1/bbo/tbbo parquet existed in any store). **Explicitly flagged as a scope deviation, taken in-window.** |

> **Status-label asymmetry worth the reviewer's attention:** D-P-01…D-P-16 are `RATIFIED`;
> **D-P-17 alone is `ADOPTED IN-WINDOW`** — the only ruling in the registry that has not been
> through an owner ratification pass, and it is a behavioral change to the canonical reader that
> both consumers now pin and execute.

### QL `docs/DECISIONS.md` — last 6 ids

| id | date | one-line ruling |
|---|---|---|
| **D-033** | 2026-06-04 | Trade-Lab is NOT v3-compatible yet — do not call a v3 dashboard-utility bundle Trade-Lab-ready until TL is repointed to SC's contract loader, sessions, touch/zone rules, feature formulas and honest-entry orchestration, then verified by end-to-end parity. |
| **D-034** | 2026-06-04 | Current docs are indexed (`docs/README.md` is the index); stale historical reports pruned from the working tree, recoverable from git history. |
| **D-035** | 2026-06-05 | Training saves are gated (`save_trained_model()` blocks failed quality gates by default; overrides explicit + recorded) and reports must preserve OOS slices (gated OOS diagnostics, session-filtered metrics, purge metadata, optional `oos_predictions.parquet`). |
| **D-036** | 2026-06-12 | The W3 training configuration in full: `dashboard_utility` / `all_to_ny` / `147t` / NQ tick 0.25; window 2025-11-21→2026-02-13; purged walk-forward TRAIN=40 TEST=5 STEP=5 PURGE=2 MIN_TRAIN_EVENTS=30; tp=15 sl=15 trap_mfe_min=5 iw=5 aw=15, approach features on; 5 PINNED features, RFECV off; CatBoost 1000 / depth 6 / lr 0.03 / Balanced / seed 42 MultiClass; quality NOT a save gate. Its status line still records the W3a compute stop-gate (*"The TRAIN DID NOT RUN"*). |
| **D-037** | 2026-06-12 | `app_max_spread` STAYS in the pinned W3 feature set — the `quotes_in_window` stub is the SC `PlatformContext` accessor only; the feature deliberately rides the W3b parity gate. |
| **D-038** | **2026-07-10** | `oos_predictions.parquet` gains four per-row columns **on FRESH saves only**: `max_mfe_pts` / `max_mae_pts` (threaded verbatim from the engine `OutcomeResult`, never recomputed), `entry_price` (the honest decision-time fill), `resolution_type` (tradeable_reversal→tp_hit; trap/blowthrough→sl_hit). **Existing bundles are NOT retrofitted**; consumers must degrade to realized-only with a stated reason. Warm caches predating `entry_price` — including the ratified D-036 `ml_utility_7850272e` fleet — yield NaN until a day is rebuilt (the cache tag hashes config, not row schema, so caches are deliberately not invalidated). |

> Layering check: SC DECISIONS states *"Quant-Lab's docs/DECISIONS.md is repo-local research
> lore; cross-repo rulings live HERE"*, and D-P-13 imports D-036/D-037 by reference. That holds.
> D-038 is the only QL ruling with a pending cross-repo consumer (the TL Performance-page preset
> follow-up) and it is not mirrored in SC.

---

## 3 — PROGRESS

Canonical file: **SC `docs/PLATFORM_REFACTOR_PROGRESS.md`** — 2,375 lines, 252,535 bytes,
mtime 2026-07-11 03:49:59, i.e. **unchanged since the INGEST close commit `9d49353`**.

### 3.1 The two current-window pointers, verbatim — and they disagree

**(a) `## Current state` → the `- **Current:**` bullet (PROGRESS:30), verbatim opening:**

> - **Current:** **PROP-SIM** — the barrier-options walker: eval pass-probability from equity paths, TopStep 50K as preset one; QL-side (`alpha_lab.propsim` pure module + CLI, model selection is the first consumer; TL Performance-page presets are a later follow-up) + the OOS-writer per-row outcome columns (max_mfe_pts / max_mae_pts / entry_price / resolution_type on fresh saves); SC receives doc-ops only. (Prior windows QL-UI-PARITY → SEED → WARM-FIX → REPORT → EXEC → COCKPIT → COCKPIT-FIX are ALL GREENLIT + PUSHED — see the POST-E3 records and the pushed annotations; ENV-FIX executed, its QL commit `f247046` rides the PROP-SIM greenlight.) […]

**(b) `### Status` block (PROGRESS:1498–1501), verbatim and complete:**

> ### Status
> Phases A–E3: COMPLETE. W1: COMPLETE (pushed; pins bumped; CI witnessed). W2: COMPLETE (pushed; pins held `256020c` — no consumer-facing SC change; CI ×3 green incl. SC's first run; W2-FIX + the TL lint commit `5a8d28a` recorded). W3: COMPLETE (pushed at the W3b-land greenlight; CI witnessed below) — **W3a bundle REBUILT on the validated vectorized reader (`NQ_W3_20260617T220752Z`, D-036 config); W3b DONE on REDUCED, stress-weighted coverage (D-P-16): batch≡serving HARD-GREEN — 30-day journal base 92/92 + dense 7-day set 29/29 at BOTH workers=2 and 4 (per-day rows identical) + 2-day bench 8/8; 0 mismatches on every axis in every run; watchdog silent; 12-18 (the prior wedge — a harness/runtime terminalization livelock, fixed at both layers + regression-tested: TL `_drive`/`run_window`, SC `f9a1f63`) and 02-12 (the prior stale-cache RED — seeded regen + QL `098e354` guard) both GREEN; the earlier full-73-day 236/236 run stands as STALE-READER CONSISTENCY evidence only. Reader ADOPTED as THE reader (D-P-16); pins at `f9a1f63`.** Current: **QL-UI-PARITY** (QL-only; UI-wiring to train the D-036 bundle from the Workbench — the TL visibility half of worklist item 2 was delivered by the W3b land: markers/warm-up/viewport, per the deleted BACKLOG entry rationale). S9.9, F1–F3: PARKED behind W3 green + soak. Live model outputs remain DECORATIVE pending the serving-side soak (D-P-12 pre-registration) — the W3b gate is banked; the soak is not.
>
> **CI witness (W3b-land greenlight, 2026-07-06):** SC `ci` / TL `backend-ci` / QL `ci` on the pushed tips — the TL and QL runs cold-install `strategy-core` resolving the NEW pin `f9a1f63` (the pin-resolution witness the land self-verify deferred). SC ci run 28813805822 (#3) success · TL backend-ci run 28813819792 (#7) success · QL ci run 28813836317 (#6) success — all on the pushed greenlight tips (SC 0f7599b · TL 923b29a · QL 3f451bd); TL/QL cold-installed strategy-core @ f9a1f63 on fresh runners (the deferred pin-resolution witness, banked).

**Three staleness facts follow from those two quotes:**

1. `### Status` says **Current: QL-UI-PARITY** and **pins at `f9a1f63`**. Both are wrong now —
   six windows have closed since, and the pins are two bumps further on, at `9d49353`.
2. `## Current state` says **Current: PROP-SIM**. Also wrong — PRESETS and INGEST closed after it.
3. **Neither pointer names INGEST**, which is the actual last window and the state of the tips.
   The only accurate current-window markers are the `Current window:` lines buried inside the
   doc-op records (PROGRESS:2008 "PROP-SIM"; PROGRESS:2254 "INGEST").

### 3.2 Every window / phase record header in order, with close state

Phase-era records (`###`, all inside "Phases A–E3: COMPLETE", all pushed):

| line | header | state |
|---|---|---|
| 90 | Phase A — additional deviations / clarifications | PUSHED |
| 119 | Phase B — B2 PART 1 deviations | PUSHED |
| 155 | Phase B — B2 PART 2 deviations | PUSHED |
| 198 | Phase B — B3 PRE-FLIP soak coverage (PREP only) | PUSHED |
| 262 | Phase B — B3 deviations (the FLIP + DELETE — irreversible) | PUSHED |
| 316 | Phase B — S-B3a deviations (fold-collapse + dedup-into-plugin) | PUSHED |
| 404 | Post-Phase-B tidy — S-B3b deviations | PUSHED |
| 437 | Phase C — C1+C2 deviations + decision 9.6 implementation | PUSHED |
| 542 | Phase D — D1a deviations (streaming honest resolver, DARK) | PUSHED |
| 622 | Phase D — D2 deviations (shadow-engine deletion + guard) | PUSHED |
| 666 | Phase D — D1b deviations (flip + delete) | PUSHED |
| 792 | Phase E — E1/E2 deviations (two-axis versioning + registry router gate) | PUSHED |
| 902 | Phase E — E3 deviations (envelope/section split, contract v3) | PUSHED |

POST-E3 section (PROGRESS:1429 onward) — the W-plan and the window records:

| line | header | close state |
|---|---|---|
| 1431 | Audit record | — (record) |
| 1436 | Ratified rulings (owner; FINAL unless superseded) | — (record) |
| 1448 | The W-plan | — (record) |
| 1454 | **W1 record** (2026-06-12) | **PUSHED** — greenlit after full three-repo hunk review; pins bumped |
| 1459 | **W2 record** (2026-06-12) | **PUSHED** — header self-annotates `[GREENLIT + PUSHED 2026-06-12: pins HELD at 256020c; CI green ×3 …]` |
| 1469 | **W3a record** (2026-06-12) | header says LOCAL / NOT pushed, **TRAIN NOT LAUNCHED (P2 compute stop-gate fired)** — SUPERSEDED by the W3b land |
| 1474 | **W3A-READER** (2026-06-12) | header says **BUILD NOT LAUNCHED** — SUPERSEDED (build ran; D-P-15/16 discharged) |
| 1478 | **W3a BUILD → W3b GATE → READER VALIDATION** (2026-06-13→17) | header says LOCAL / push pending — SUPERSEDED by 1486 |
| 1486 | **W3b CLOSE** — vectorized-reader adoption on the reduced-coverage re-gate [D-P-16] | **PUSHED** at the 2026-07-06 W3b-land greenlight |
| 1498 | Status | — (block; stale, see §3.1) |
| 1503 | **QL-UI-PARITY** (2026-07-06, QL-only) | **PUSHED** — header annotated `[GREENLIT + PUSHED 2026-07-06 …]`; owed CI ids PAID inline (QL 28817637012 #7 · SC 28817731288 #4) |
| 1512 | SEED-PARITY recon (2026-07-06) | doc-op (read-only recon; verification half of `verify-prior-session-levels` CLOSED) |
| 1520 | **SEED** — dashboard replays get the training-parity PDH/PDL seed (2026-07-06, cross-repo) | **PUSHED** — SC `1650327` · TL `c92f13b` · QL `75f83dc`; CI ×3 with pin resolution witnessed (28839878234 / 28839902876 / 28839925480) |
| 1538 | Live post-drain wedge — root cause banked (2026-07-07) | doc-op (opens WARM-FIX) |
| 1573 | **WARM-FIX** (2026-07-08, TL window) | header says **CLOSED — LOCAL, not pushed**; superseded by 1634 → **PUSHED** |
| 1634 | WARM-FIX pushed annotation (2026-07-10) | **PUSHED** (SC ci 29073067597 · TL backend-ci 29077742228 · QL ci 29077759730) |
| 1644 | **REPORT** — performance surface (2026-07-10, TL window) | header says CLOSED — local `8e54ad1`, not pushed; superseded by 1704 → **PUSHED** |
| 1704 | REPORT pushed annotation (2026-07-10) | **PUSHED** |
| 1715 | **EXEC** — paper execution layer (2026-07-10, cross-repo) | header says CLOSED — LOCAL, not pushed; superseded by 1827 → **PUSHED** |
| 1827 | EXEC pushed annotation (2026-07-10) | **PUSHED** (SC ci 29101442670 #9 · TL backend-ci 29101483167 #11 · QL ci 29101530109 #9) |
| 1846 | **COCKPIT** — trader-facing UI pass (2026-07-10, TL window + SC doc-ops) | header says CLOSED — LOCAL, not pushed; superseded by 1951 → **PUSHED** |
| 1951 | COCKPIT pushed annotation + **COCKPIT-FIX** close + **ENV-FIX** record (2026-07-10) | COCKPIT **PUSHED** (TL `b23cc57`, backend-ci 29109919564 #12 · SC `0e86cb5`, ci 29109952671 #10) · COCKPIT-FIX **PUSHED** (TL `67e03e4`, backend-ci 29121846588 #13) · ENV-FIX executed, QL `f247046` recorded as *"COMMITTED NOT PUSHED — it rides THIS window's (PROP-SIM) greenlight"* |
| 2014 | **PROP-SIM** — the barrier-options walker (2026-07-10, QL window + SC doc-ops) | header says CLOSED — LOCAL, not pushed; superseded by 2107 → **PUSHED** |
| 2107 | PROP-SIM pushed annotation + PRESETS ratified parameters (2026-07-10) | **PUSHED** (SC ci 29134311915 #11 · QL ci 29134318835 #10) |
| 2159 | **PRESETS** — remaining eval rulesets + two trail mechanics (2026-07-10, QL window + SC doc-ops) | header says CLOSED — LOCAL, not pushed; **PUSHED annotation appended in-section** at 2233–2239 (SC `1a58aa8` ci 29136911173 #12 · QL `49c2f22` ci 29136917345 #11) — *"Both CI ids banked here; no debt outstanding."* |
| 2243 | Databento batch download — provenance (2026-07-11, INGEST P0 doc-op) | doc-op |
| 2262 | **INGEST** — batch MBP-1 download → first-class store days (2026-07-11) | header says **"CLOSED — LOCAL, not pushed"**, body says *"Pins UNCHANGED at `3d4193e` ×2 locally; **bump owed at greenlight**"* — **CONTRADICTED BY GIT: the window IS pushed, both pins ARE at `9d49353`, CI is green ×3.** No pushed annotation exists. |

**Verified ENV-FIX state:** QL `f247046` (`fix(acceptance): live Strategy-Core sys.path becomes
opt-in (ENV-FIX)`, 2026-07-10) is an **ancestor of QL `platform-refactor`, which equals
`origin/platform-refactor`** — so it is pushed, exactly as the PROP-SIM greenlight intended.
The "COMMITTED NOT PUSHED" line at PROGRESS:1991 is discharged in fact but never annotated.

### 3.3 Debts found in the text

| # | debt, as written | line | actual state (verified this session) |
|---|---|---|---|
| 1 | *"CI witness: the greenlight `ci`/`backend-ci` runs on the pushed tips (**ids at the next doc op** — PAID: the SEED greenlight runs on tips containing the land, ids in the SEED close record)"* | 33 | **PAID** — self-annotated. |
| 2 | *"SC receives exactly two doc commits this window (`4540578` open — **the owed W3b CI witness ids** — and this close record)"* | 1508 | **PAID** — the W3b CI witness block is at 1501. |
| 3 | *"SC `60650bb` (window-open doc-op: recon verdict banked + **owed QL-UI-PARITY CI ids**)"* | 1524 | **PAID** — ids in the 1503 header annotation. |
| 4 | PROP-SIM annotation: *"TL untouched — no run owed. Both CI ids re-witnessed via the REST API at this doc-op (run/head/conclusion match)."* | 2118 | **PAID / no debt.** |
| 5 | PRESETS annotation: *"Pins unchanged at `3d4193e` ×2 … TL untouched — no run owed. **Both CI ids banked here; no debt outstanding.**"* | 2238 | **PAID / no debt.** |
| 6 | **INGEST:** *"Pins UNCHANGED at `3d4193e` ×2 locally; **bump owed at greenlight** — D-P-17 + the boundary fallback are consumer-facing SC code (9.6 convention)."* | 2270 | **DONE IN GIT, UNRECORDED.** Pins are at `9d49353` in both consumers (TL `3466aff`, QL `3b470d3`). |
| 7 | **INGEST:** *"**NOT pushed (work-order FULL STOP).** Pins: **bump owed at greenlight** (consumer-facing SC: D-P-17 + boundary fallback); **TL/QL runs owed at greenlight** witness the new pin."* | 2373–2375 | **DONE IN GIT, UNRECORDED.** SC ci 29162591811 #13 · TL backend-ci 29162631478 #14 · QL ci 29162655755 #12 (**failure**) → 29162951541 #13 (success). |
| 8 | **NAMED DEBT (not fixed):** *"QL dashboard `replay_client.py` (+ legacy backtest scripts) are mbp10-hardcoded — mbp1-era days are invisible to the QL dashboard replay surface. Off this window's critical path; **owed to a future window**."* | 2356–2358 | **OPEN.** 119 mbp1-only store days (2026-02-23 → 2026-07-10) are unreachable from the QL dashboard replay. |

**Net: one genuinely open engineering debt (#8) and one unpaid doc debt (#6 + #7 — the INGEST
pushed annotation).** The doc debt is *why* every current-window pointer is stale: the INGEST P0
doc-op paid PRESETS's annotation, and no window has opened since to pay INGEST's.

---

## 4 — STORE

`C:\Users\gonza\Documents\Claude-Quant-Lab\data\databento\NQ`

| metric | value |
|---|---|
| day directories | **431** |
| date range | **2021-12-02 … 2026-07-10** |
| total files (recursive) | 1,912 |
| total size | **224,573,425,756 bytes = 209.15 GB** |

### Per-era file counts

| era file | days | date range | size |
|---|---|---|---|
| `mbp10.parquet` | **310** | 2021-12-02 … 2026-02-22 | **167.95 GB** |
| `mbp1.parquet` | **156** | 2026-01-11 … 2026-07-10 | **40.57 GB** |
| **both present (overlap)** | **37** | 2026-01-11 … 2026-02-22 | — |
| mbp1-only (post-gap, new era) | **119** | 2026-02-23 … 2026-07-10 | — |
| **neither** | **2** | `2025-11-20`, `2026-02-14` | — |

The 37 overlap days: 2026-01-11, -12, -13, -14, -15, -16, -18, -19, -20, -21, -22, -23, -25,
-26, -27, -28, -29, -30; 2026-02-01, -02, -03, -04, -05, -06, -08, -09, -10, -11, -12, -13,
-15, -16, -17, -18, -19, -20, -22. This is exactly the D-P-17 / INGEST identity-gate surface.

The two "neither" days: `2025-11-20` is **completely empty** (0 items — the day D-036 names as
"an empty day dir [that] self-skips at date discovery"); `2026-02-14` holds one non-era file,
`ohlcv_1m_20260214_20260224.parquet`.

### Derived cache / ancillary files in the same tree

| file | days | note |
|---|---|---|
| `ml_features.parquet` | 307 | legacy feature cache |
| `ml_utility_dab124ca.parquet` | 185 | |
| `ml_utility_d8e239c7.parquet` | 185 | engine-v3 sessions/availability hash |
| `ml_utility_3d2f8466.parquet` | 178 | |
| `ml_features_3154bd96.parquet` | 120 | |
| `ml_features_a4e50187.parquet` | 119 | |
| `ml_utility_960ba73b.parquet` | 89 | |
| `ml_utility_0607f6c8.parquet` | 87 | |
| `ohlcv_1m_session.parquet` | 69 | |
| **`ml_utility_7850272e.parquet`** | **60** | **the ratified D-036 cache fleet** |
| `ml_utility_89d82fb5.parquet` | 16 | |
| `ml_utility_3d60f9a9.parquet` | 9 | |
| `ml_utility_b8b2e14d.parquet` | 9 | |
| `ohlcv_1m.parquet` | 8 | |
| `ml_utility_7850272e.STALE_BACKUP_16h48.parquet` | 1 | the 02-12 stale-cache artifact (D-P-16) |
| `trades_*.parquet` / `ohlcv_1m_*_*.parquet` | 4 | one-off windows |

> **Relevant to any retrain:** the D-036 fleet is **60 days**, and the D-036 window
> (2025-11-21 → 2026-02-13) lies entirely inside the mbp-10 era. Per D-038 those caches predate
> `entry_price` and are **deliberately not invalidated** — the cache tag hashes config, not row
> schema. A fresh D-036 train on the warm fleet therefore yields NaN `entry_price`.

---

## 5 — MODELS (QL `models/`)

**21 bundle directories.** `data/models/` and `data/models_archive/` both exist but contain
**0** bundle dirs. `models_qlui_acceptance_tmp/` — the QL-UI-PARITY acceptance bundle recorded as
"kept pending review adjudication" — **no longer exists on disk**.

| bundle | mtime | oos rows | MFE/MAE cols | platform / contract version |
|---|---|---|---|---|
| NQ_20260224_210453 | 2026-02-24 21:07 | — | — | *(no strategy.json)* |
| NQ_20260224_211141 | 2026-02-24 21:16 | — | — | *(no strategy.json)* |
| NQ_20260404_053924 | 2026-04-04 13:53 | — | — | *(no strategy.json)* |
| NQ_20260404_120558 | 2026-04-04 13:37 | — | — | *(no strategy.json)* |
| NQ_20260404_185203 | 2026-04-04 18:54 | — | — | *(no strategy.json)* |
| NQ_20260404_230538 | 2026-04-04 23:07 | — | — | *(no strategy.json)* |
| NQ_20260404_230908 | 2026-04-04 23:09 | — | — | *(no strategy.json)* |
| NQ_20260405_015538 | 2026-04-05 01:57 | — | — | *(no strategy.json)* |
| NQ_20260405_147t_5m_15m_multiclass-250602-260220 | 2026-04-05 01:00 | — | — | *(no strategy.json)* |
| NQ_20260405_147t_5m_250602-260220 | 2026-04-05 00:20 | — | — | *(no strategy.json)* |
| NQ_20260405_147t_5m_30m_multiclass-250602-260220 | 2026-04-05 00:28 | — | — | *(no strategy.json)* |
| NQ_20260405_147t_5m_30m_multiclass-…-iterations800_depth4 | 2026-06-10 17:49 | — | — | `?` / `trade_lab_contract_v1` |
| NQ_20260405_extrema_rebound_crossing_10p | 2026-04-05 11:25 | — | — | *(no strategy.json)* |
| NQ_20260427_183527 | 2026-06-07 20:56 | — | — | *(no strategy.json)* |
| NQ_20260602_184719 | 2026-06-10 17:49 | — | — | `strategy_core_engine_v1` / `trade_lab_contract_v1` |
| NQ_20260602_232808 | 2026-06-10 17:49 | — | — | `strategy_core_engine_v2` / `trade_lab_contract_v1` |
| NQ_20260603_233847 | 2026-06-10 19:59 | — | — | `strategy_core_platform_v1` / `trade_lab_contract_v3` |
| NQ_20260604_012623 | 2026-06-10 19:59 | — | — | `strategy_core_platform_v1` / `trade_lab_contract_v3` |
| NQ_20260604_015413 | 2026-06-10 19:59 | — | — | `strategy_core_platform_v1` / `trade_lab_contract_v3` |
| **NQ_W3_20260613T055600Z** | 2026-06-13 00:57 | **41** | **NO** | `strategy_core_platform_v1` / `trade_lab_contract_v3` |
| **NQ_W3_20260617T220752Z** | 2026-06-17 17:08 | **42** | **NO** | `strategy_core_platform_v1` / `trade_lab_contract_v3` |

**Only 2 of 21 bundles carry `oos_predictions.parquet` at all** — the two W3 bundles. Their
schemas are identical, 13 columns each:

```
fold, timestamp, session, binary_true_tradeable, label_encoded, label,
pred_label_encoded, pred_label, prob_tradeable_reversal,
gate_0_70_runtime_sessions, gate_0_70_ny, prob_trap_reversal,
prob_aggressive_blowthrough
```

**No bundle in the store carries the D-038 columns** (`max_mfe_pts`, `max_mae_pts`,
`entry_price`, `resolution_type`). That is consistent with D-038's own text — *"Existing bundles
are NOT retrofitted"* — and it means **no FRESH save has occurred since D-038 landed on
2026-07-10.** The PROP-SIM walker, whose entire premise is per-trade excursions, therefore has
**zero bundles it can run at full fidelity**; on both W3 bundles it must degrade to
realized-only with a stated reason.

The three `NQ_20260603/0604_*` bundles carry 6 files each — `strategy.json` plus
`strategy.json.pre_v2.bak` and `strategy.json.pre_v3.bak`, the E-window and E3-window in-place
contract migrations. The `NQ_W3_*` bundles carry 6 files including `model.cbm.sha256`.

**Per D-P-16 the current W3 artifact is `NQ_W3_20260617T220752Z`** (42 OOS rows, 2,140,184-byte
`model.cbm`); `NQ_W3_20260613T055600Z` is the superseded stale-reader bundle, still on disk.

---

## 6 — EVIDENCE (untracked report / log files at the three repo roots)

Root level only. "first line" is the literal first line of the file.

### SC root

| file | mtime | bytes | first line |
|---|---|---|---|
| `ARCH_STATE_RECON.md` | 2026-06-15 18:29 → **replaced by this file** | 62,786 | `# ARCH_STATE_RECON — Platform architecture: current state vs. ratified target` |
| `STATE_RESYNC.md` | 2026-07-03 02:23 | 13,715 | `# STATE RESYNC — three-repo snapshot (read-only)` |
| `WARMFIX_GREENLIGHT_REPORT.txt` | 2026-07-10 01:14 | 8,869 | `WARM-FIX GREENLIGHT REPORT` |
| `REPORT_GREENLIGHT_REPORT.txt` | 2026-07-10 02:49 | 2,466 | `REPORT GREENLIGHT REPORT — 2026-07-10` |
| `EXEC_GREENLIGHT_REPORT.txt` | 2026-07-10 09:55 | 3,940 | `EXEC GREENLIGHT REPORT — 2026-07-10` |
| `COCKPIT_GREENLIGHT_REPORT.txt` | 2026-07-10 12:10 | 3,046 | `COCKPIT GREENLIGHT REPORT — 2026-07-10` |
| `COCKPITFIX_GREENLIGHT_REPORT.txt` | 2026-07-10 15:36 | 5,612 | `COCKPIT-FIX GREENLIGHT REPORT` |
| `ENVFIX_REPORT.txt` | 2026-07-10 15:39 | 6,370 | `ENV-FIX REPORT — close the two READER_PIN_RECON risks` |
| `PROPSIM_GREENLIGHT_REPORT.txt` | 2026-07-10 20:18 | 3,718 | `PROP-SIM GREENLIGHT REPORT` |
| `PRESETS_GREENLIGHT_REPORT.txt` | 2026-07-10 21:50 | 3,908 | `PRESETS GREENLIGHT REPORT` |
| **`INGEST_GREENLIGHT_REPORT.txt`** | **2026-07-11 13:15** | 7,233 | `INGEST GREENLIGHT REPORT` |
| `SEED_GREENLIGHT_REPORT.txt` | 2026-07-06 23:00 | 4,265 | `SEED GREENLIGHT REPORT — verified 2026-07-07 (idempotent verify pass; execution occurred in the prior session)` |
| `W3A_READER_PROOF.log` | 2026-06-12 20:17 | 4,646 | `W3A-READER P3a IDENTITY PROOF — row-wise vs vectorized DatabentoParquetSource` |
| `W3B_0212_DIFF.log` | 2026-06-17 02:25 | 18,821,407 | `W3b 02-12 reader diff  run=2026-06-17T02:13:07  SC HEAD=332ad3e` |
| `W3B_0212_RAW.log` | 2026-06-17 02:15 | 19,968,857 | `RAW scan …\NQ\2026-02-12\mbp10.parquet` |
| `_ingest_sc_suite.out` / `_suite2.out` / `_suite_final.out` | 2026-07-11 02:48 / 03:04 / 03:47 | 1,454 / 1,500 / 1,500 | pytest progress dots |
| `algo-dev.md` | 2026-06-04 01:39 | 4,596 | `AlgoDev, I want you to do a full onboarding/deep-analysis pass before we start development.` |
| `b2_context.md` | 2026-06-08 21:50 | 89,381 | `# B2 design-review context bundle  (DISPOSABLE — do not commit)` |
| `route_seam_report.json` | 2026-06-12 15:34 | 5,116 | `{` |
| per-window `*_SC_DIFF.txt` ×17 | 2026-06-10 … 2026-07-11 | 5.6 KB – 115 KB | `diff --git …` / `commit …` |
| `scratch_w3a_reader_proof.py`, `scratch_w3b_0212_diff.py`, `scratch_w3b_0212_raw.py` (+2 `.out`) | 2026-06-12 … 2026-06-17 | 4 KB – 20 MB | docstring / run header |

**`INGEST_GREENLIGHT_REPORT.txt` (2026-07-11 13:15) is the newest artifact in the SC root and
post-dates the SC tip commit (03:50) — it is the greenlight receipt for the push whose
annotation PROGRESS still owes.**

### TL root

| file | mtime | bytes | first line |
|---|---|---|---|
| `test.md` | 2026-06-08 22:22 | 12,684 | `Phase B · Step B2 — PART 1 of 2: the plugin SEAM (production construction stays OFF).` |
| `BASELINE_REPORT.md` | 2026-06-09 16:53 | 112,423 | `# BASELINE REPORT — Strategy-Core / Quant-Lab / Trade-Lab` |
| `D1_CHARACTERIZATION.md` | 2026-06-10 01:07 | 2,927 | `# D1 CHARACTERIZATION — old tracker vs dark honest resolver (GATE B)` |
| `READER_CORRECTNESS_PROOF.md` | 2026-06-17 14:00 | 16,266 | ``# Reader Correctness Proof — vectorized `DatabentoParquetSource` @ strategy-core `37359ae` `` |
| `W3B_LIVELOCK_ROOTCAUSE.md` | 2026-06-18 20:58 | 15,294 | `` # W3b replay `_drive` livelock — root-cause report `` |
| `LAND_TL_DIFF_v2.txt` | 2026-07-06 13:13 | 176,604 | `diff --git a/.gitignore b/.gitignore` |
| `PLUGIN_SDK_RECON.md` | 2026-07-06 17:23 | 136,572 | `# PLUGIN_SDK_RECON — plugin SDK surface inventory for the second-strategy window` |
| `SEED_PARITY_RECON.md` | 2026-07-06 18:32 | 67,520 | `# SEED_PARITY_RECON — does the TL dashboard replay seed prior-day PDH/PDL identically to QL training's carry?` |
| `WARM_PERF_RECON.md` | 2026-07-07 20:57 | 22,830 | `# WARM_PERF_RECON — where the live warm-start's time goes, and what a schema-scoped fetch changes` |
| `WEDGE_CAPTURE.md` | 2026-07-07 22:09 | 27,055 | `# WEDGE_CAPTURE — live-feed post-drain wedge: state capture + instrumented repro` |
| `REPORT_RECON.md` | 2026-07-10 01:36 | 7,729 | `# REPORT window — P1 recon (read-only, pre-build)` |
| `COCKPIT_STATES.md` | 2026-07-10 11:30 | 5,112 | `# COCKPIT — states description of the strip and cards` |
| `READER_PIN_RECON.md` | 2026-07-10 14:48 | 20,715 | `# READER-PIN RECON — do QL and TL consume the adopted vectorized reader everywhere?` |
| `scratch_seed_parity.py` / `…_results.json` | 2026-07-06 18:26 / 18:30 | 11,616 / 11,962 | docstring / `[` |
| `tl_ci_logs.zip`, `ql_ci_logs.zip` | 2026-07-06 22:45 | 21,183 / 30,868 | *(binary)* |
| `tl_exec_ci_logs.zip`, `ql_exec_ci_logs.zip` | 2026-07-10 09:54 / 09:55 | 21,246 / 30,920 | *(binary)* |

**Gitignored** (present on disk, invisible to `git status`):
`INGEST_TL_DIFF.txt` (2026-07-11 03:36, 3,004 B, `diff --git a/backend/src/trade_lab/adapters/replay_catalog.py …`) ·
`scratch_seed_parity_run.log` (2026-07-06 18:30, 2,086 B, `store: 310 available dates 2021-12-02..2026-02-22`) ·
`W3_ISOLATE_1223.log` (2026-06-18 18:06, 175 B, a python module-resolution error).

> Note that log's first line — `310 available dates 2021-12-02..2026-02-22` — that is the
> **pre-INGEST** store. The store is now 431 day dirs running to 2026-07-10.

### QL root

| file | mtime | bytes | first line |
|---|---|---|---|
| `W3_CONFIG_RECON.md` | 2026-06-12 15:01 | 16,003 | `# W3-CONFIG RECON — store inventory + current training/label/feature defaults` |
| `QL_TRAINING_UI_RECON.md` | 2026-06-15 19:43 | 17,086 | `` # RECON — QL training config: UI surface vs. the D-036 arg set (cache tag `7850272e`) `` |
| `QL_UI_TRAIN_GAP_RECON.md` | 2026-06-15 20:46 | 11,062 | `# RECON — UI training: what already exists vs. what's needed to reproduce the CLI D-036 bundle` |
| `W3A_PRECEDING_6_REVIEW.txt` | 2026-06-17 11:37 | 52,501 | `================================================================================` |
| `PROPSIM_BASELINE.md` | 2026-07-10 20:55 | 23,290 | `# PROP-SIM BASELINE — walker evidence run (P3; evidence, not a gate)` |
| `route_seam_report_ingest.json` | 2026-07-11 03:00 | 3,790 | `{` |
| `_p4a_run.out` | 2026-07-11 02:57 | 2,621 | `INGEST P4a OVERLAP IDENTITY — original mbp10.parquet vs converted mbp1.parquet` |
| `_p4b_run.out` | 2026-07-11 03:00 | 598 | `cache_tag=7850272e  (D-036 expectation: 7850272e)` |
| `_p4c_run.out` | 2026-07-11 03:00 | 3,901 | `{` |
| `_p5_conversion.out` | 2026-07-11 03:28 | 10,649 | `=== ingest_databento_batch 2026-07-11T08:02:22+00:00 \| input=…GLBX-20260711-EEDSMFU845.zip …` |
| `_ingest_ql_suite.out` / `_final.out` | 2026-07-11 03:06 / 03:38 | 4,601 / 4,601 | `============================= test session starts ====…` |
| `scratch_ingest_identity.py` | 2026-07-11 02:40 | 11,355 | `"""INGEST P4a OVERLAP IDENTITY: original mbp10.parquet vs converted mbp1.parquet.` |
| `scratch_ingest_p4b.py` | 2026-07-11 02:20 | 2,629 | `"""INGEST P4b FRESH-DAY BUILD: one post-gap day through the QL per-day D-036 build.` |
| `scratch_qlui_acceptance.py` | 2026-07-06 13:59 | 13,532 | `"""QL-UI-PARITY P5 acceptance (headless).` |
| `scratch_w3a_p2_gate.py` | 2026-06-12 16:59 | 3,241 | `"""W3a P2 compute stop-gate: one full pipeline day under the P3 config.` |
| `scratch_w3b_0212_regen.py` / `.out` | 2026-06-17 03:07 / 03:55 | 4,522 / 2,114 | docstring / `cache_tag=7850272e  symbol=NQ  window=73d` |
| `.w3_new_bundle_name` | 2026-06-17 17:07 | 23 | *(23-byte marker)* |
| per-window `*_QL_DIFF.txt` ×12 | 2026-06-10 … 2026-07-11 | 503 B – 112 KB | `diff --git …` / `commit …` |

**Gitignored logs at the QL root** — these are the run receipts PROGRESS cites as deliverables:

| file | mtime | bytes | first line |
|---|---|---|---|
| **`INGEST.log`** | 2026-07-11 03:28 | 15,549 | `=== ingest_databento_batch 2026-07-11T07:15:09+00:00 \| input=…\Temp\claude\…` |
| **`INGEST_IDENTITY.log`** | 2026-07-11 02:57 | 2,551 | `INGEST P4a OVERLAP IDENTITY — original mbp10.parquet vs converted mbp1.parquet` |
| `QLUI_ACCEPTANCE.log` | 2026-07-06 14:14 | 29,518 | `2026-07-06 14:11:04,904 INFO qlui_acceptance: QL HEAD: 0b4a2e8c1316c498fabb98669fe93dce8cb092af (tracked tree clean)` |
| `W3_TRAIN.log` | 2026-06-13 00:57 | 4,604 | catboost/pandas warning header |
| `W3_REBUILD_RUN.log` / `RUN2` / `RUN3` | 2026-06-17 16:12 / 16:39 / 17:06 | 2,535 / 577 / 7,901 | `# …W3 cache warmer \| tag=7850272e \| symbol=NQ \| window=73d \| targets=72/57/57 \| workers=3/2/4` |
| `W3_RETRAIN_RUN.log` | 2026-06-17 17:08 | 4,561 | `…ml_training_tab.py:840: UserWarning: Discarding nonzero nanoseconds…` |
| `W3A_WARM.log` / `W3A_WARM_launch.log` | 2026-06-17 17:06 / 2026-06-12 22:19 | 18,505 / 9,447 | warmer headers (`targets=2 workers=2` / `targets=70 workers=4`) |
| `W3A_P1_PROOF.log` | 2026-06-12 16:22 | 344 | `=== 2022-02-15 ===` |
| `W3A_P2_GATE.log` | 2026-06-12 16:57 | 272 | `config hash: 7850272e; cache pre-exists: False` |

**No `*PREREG*` file and no `*SELECTION*` file exists at any of the three roots** — see §7.

---

## 7 — IN-FLIGHT: RECENT-TRAIN-A

Searched all three working trees (root + 2 levels, plus a targeted `docs/` check) **and**
`git log --all` across every ref in all three repos.

| artifact | exists? |
|---|---|
| QL `docs/RECENT_TRAIN_PREREG.md` | **NO** — `Test-Path` returns False |
| `RECENT_TRAIN_SELECTION.md` (any repo, any path) | **NO** |
| `RTA_*` diffs (any repo, any path) | **NO** |
| Any `RECENT_TRAIN*` / `RTA_*` / `*PREREG*` path in git history (`--all`) | **NO** — zero hits in all three repos |

QL `docs/` contains exactly three files: `DECISIONS.md` (2026-07-10 18:29),
`ML_TRAINING_WORKBENCH.md` (2026-07-10 18:29), `README.md` (2026-06-07 20:56).

**Plainly, per part:**

| RECENT-TRAIN-A part | evidence of completion |
|---|---|
| **P0 — prereg** | **NONE.** The pre-registration document does not exist in any working tree or in any commit on any ref. |
| **P2 — builds** | **NONE attributable to RECENT-TRAIN-A.** No new `ml_utility_*` cache tag appeared; the newest fleets on disk are the D-036 `7850272e` (60 days) and the older `dab124ca` / `d8e239c7` / `3d2f8466` fleets. The only 2026-07 store activity is the INGEST conversion (156 `mbp1.parquet` days). |
| **P3 — scoring** | **NONE.** No scoring artifact, no `RECENT_TRAIN_SELECTION.md`, no new `oos_predictions.parquet` anywhere. |
| **P4 — finalist** | **NONE.** No bundle in `models/` has an mtime later than **2026-06-17 17:08** (`NQ_W3_20260617T220752Z`). Nothing was trained or saved in July at all. |

**Verdict: RECENT-TRAIN-A has not started.** Not one of its four parts has left a trace on disk
or in git. The newest model artifact in the platform is 38 days older than the newest commit.

Related in-flight state to hold alongside that:

- **D-038 (2026-07-10) has no beneficiary yet.** It adds four per-row OOS columns *on fresh
  saves only*; there have been no fresh saves, so PROP-SIM's walker runs realized-only on both
  W3 bundles.
- **The D-036 warm caches cannot supply `entry_price`** even if a train ran today — D-038 says
  so explicitly and declines to invalidate them.
- **119 store days (2026-02-23 → 2026-07-10) are new since the last train**, lie entirely
  outside the D-036 window, and are — per the INGEST named debt — invisible to the QL dashboard
  replay surface.

---

## 8 — ENVIRONMENT

One shared system interpreter — **no virtualenv exists in any of the three repos**
(`Get-ChildItem -Directory` matching `venv|\.venv|env$` returns nothing in SC, TL, TL/backend,
or QL).

```
PYTHON     = C:\Users\gonza\AppData\Local\Programs\Python\Python313\python.exe  (3.13.1150.1013)
PYTHONPATH = <unset>          ← no sys.path hack in play
```

### `python -c "import strategy_core"` — resolved path, from both consumer working dirs

| cwd | `strategy_core.__file__` | verdict |
|---|---|---|
| `C:\Users\gonza\Documents\Trade-Lab` | `C:\Users\gonza\Documents\Strategy-core\src\strategy_core\__init__.py` | **EDITABLE checkout** |
| `C:\Users\gonza\Documents\Trade-Lab\backend` | `C:\Users\gonza\Documents\Strategy-core\src\strategy_core\__init__.py` | **EDITABLE checkout** |
| `C:\Users\gonza\Documents\Claude-Quant-Lab` | `C:\Users\gonza\Documents\Strategy-core\src\strategy_core\__init__.py` | **EDITABLE checkout** |

Distribution metadata is unambiguous:

```
dist version    = 0.1.0
direct_url.json = {"dir_info": {"editable": true}, "url": "file:///C:/Users/gonza/Documents/Strategy-core"}
```

**Not site-packages.** This is the ENV-FIX state (PROGRESS:1981–1991) holding: *local runtime =
the SC working tree ALWAYS; the git pin stays enforced by CI cold-installs only.* Both
consumers' CI runs did cold-install and resolve `9d49353` on fresh runners (§1), so the pin is
enforced where it is meant to be and bypassed where it is meant to be.

> **Consequence the reviewer must carry:** because the local install is editable and SC's working
> tree is clean at `9d49353` (= the pin), local and CI currently agree **by coincidence of a
> clean tree**, not by construction. Any uncommitted SC edit silently changes what TL and QL
> execute locally while CI keeps testing `9d49353`.

### Vectorized-reader probe

Module under test: `strategy_core.data.databento_parquet` →
`C:\Users\gonza\Documents\Strategy-core\src\strategy_core\data\databento_parquet.py`
(`DatabentoParquetSource` at line 228).

```
decode members  = ['_decode_batch', '_decode_batches', 'batch_size']
row-wise marks  = <none>          (searched: itertuples, iterrows, _decode_row, _row_to_event)
vector marks    = ['_DecodedBatch', 'to_numpy(', 'np.flatnonzero', 'pc.cast']
D-P-17 marker   = True            (action∈{T,TRADE} classification for is_tob schemas present)
READER VERDICT  = VECTORIZED
```

Identical result from both consumer cwds. The `_DecodedBatch` dataclass carries numpy arrays
(`is_quote`, `ts_sort`, `seq`, `ssp`, `size`, `price_ticks`, `bid_ticks`, `ask_ticks`,
`bid_size`, `ask_size`); decode runs through `pyarrow.compute` + numpy over record batches. The
two residual `for row in …` occurrences in the module are a warning-emission loop over
`np.flatnonzero(trade_warn | quote_warn)` (line 949) and a side-value list comprehension
(line 985) — **not** row-wise decode. The D-P-15 row-wise path is gone.

**So: the adopted vectorized reader (D-P-16) carrying the D-P-17 trade classification is what
both consumers execute locally, and it is the same code the pin `9d49353` resolves to in CI.**

---

## 9 — STATE IN ONE SCREEN

1. **Three repos, one branch, all clean-and-synced, all CI-green, both pins on the SC tip
   `9d49353`.** There is no divergence anywhere in git — the most consistent state of the whole
   refactor.
2. **The docs lag the code by exactly one window.** INGEST landed, pushed, bumped both pins and
   went green ×3, and PROGRESS still reads *"CLOSED — LOCAL, not pushed … bump owed at
   greenlight."* Both current-window pointers are stale (`## Current state` → PROP-SIM,
   `### Status` → QL-UI-PARITY), and `### Status` still names pins at `f9a1f63`, two bumps
   behind. **One doc-op pays all of it.**
3. **D-P-17 is the one unratified ruling** — `ADOPTED IN-WINDOW`, a behavior change to the
   canonical reader, taken as an admitted scope deviation, now serving both consumers.
4. **The store nearly doubled its recent coverage and the models did not follow.** 431 day dirs
   / 209.15 GB; 119 brand-new mbp-1-only days (2026-02-23 → 2026-07-10) that no model, no cache
   fleet and no QL dashboard replay has ever touched. The newest bundle is from 2026-06-17.
5. **RECENT-TRAIN-A has not begun** — no prereg, no builds, no scoring, no finalist (§7).
6. **D-038's OOS columns exist in code and in no artifact.** Zero bundles carry MFE/MAE, so the
   PROP-SIM walker — the thing D-038 was written for — is degraded on every bundle it can see.
7. **The soak is still the open gate.** Per `### Status`: *"Live model outputs remain DECORATIVE
   pending the serving-side soak (D-P-12 pre-registration) — the W3b gate is banked; the soak is
   not."* Nothing in git, the store or the bundles indicates a soak day has been run.
8. **One open engineering debt:** QL `replay_client.py` + legacy backtest scripts are
   mbp10-hardcoded, so 119 store days are invisible to the QL dashboard replay (PROGRESS:2356).
9. **One unaccounted commit:** TL `14ed624` (`feat: add readme`, 2026-07-15) belongs to no window
   record.

---

*Generated read-only 2026-07-25. No tracked file modified, staged, or committed.*
