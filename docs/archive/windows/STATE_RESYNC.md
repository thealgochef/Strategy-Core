# STATE RESYNC — three-repo snapshot (read-only)

Generated: 2026-07-03 02:22 -0500 · branch `platform-refactor` on all three repos · this file is UNCOMMITTED and lives at the SC root only.
Remote tips read via `git ls-remote` (no fetch — remote-tracking refs untouched). No other writes were made anywhere.

| Repo | Path | Origin |
|------|------|--------|
| SC | `C:\Users\gonza\Documents\Strategy-core` | `thealgochef/Strategy-Core` |
| TL | `C:\Users\gonza\Documents\Trade-Lab` | `thealgochef/Trade-Lab` |
| QL | `C:\Users\gonza\Documents\Claude-Quant-Lab` | `thealgochef/Quant-Lab` |

---

## 1. Per-repo git state

### SC — Strategy-core

- **Local tip:** `3a37f7593281e9b50f4382239ae12b1eb1511ea3` — `docs: W3 DOC SYNC — BACKLOG.md punt-list + PROGRESS.md through reader validation` — 2026-06-17 14:57:19 -0500
- **Pushed origin tip:** `5ac08a0b6bd6f9a6caed97c5c6c0c778f3830ff6` — `docs: DECISIONS.md — goal anchor + living decision registry (D-P-01..14)` — 2026-06-12 17:30:53 -0500
- **Ahead 4 / behind 0.** Unpushed commits (newest first):
  - `3a37f75` docs: W3 DOC SYNC — BACKLOG.md punt-list + PROGRESS.md through reader validation
  - `4b08ba1` docs: W3A-READER P4 — D-P-15 (reader vectorized pre-build under identity proof + drift net) + W3a record subsection
  - `37359ae` perf(data): W3A-READER P3c — delete the row-wise reader path on full green
  - `332ad3e` perf(data): W3A-READER P2 — vectorized DatabentoParquetSource decode; row-wise path kept until P3
- **Dirty tree** — staged: *none*; modified (3): `docs/BACKLOG.md`, `src/strategy_core/runtime/replay.py`, `tests/test_runtime_replay.py` ⚠️ (uncommitted **source** changes on the runtime replay path); untracked (21): `ARCH_STATE_RECON.md`, `D1A_SC_DIFF.txt`, `D1B_SC_DIFF.txt`, `E3_SC_DIFF.txt`, `E_SC_DIFF.txt`, `W1_SC_DIFF.txt`, `W2FIX_SC_DIFF.txt`, `W2_SC_DIFF.txt`, `W3A_READER_PROOF.log`, `W3A_READER_SC_DIFF.txt`, `W3A_SC_DIFF.txt`, `W3B_0212_DIFF.log`, `W3B_0212_RAW.log`, `algo-dev.md`, `b2_context.md`, `route_seam_report.json`, `scratch_w3a_reader_proof.py`, `scratch_w3b_0212_diff.py`, `scratch_w3b_0212_raw.py`, `scratch_w3b_0212_raw_run.out`, `scratch_w3b_0212_run.out`

### TL — Trade-Lab

- **Local tip:** `0286dc75e55453507fd2262e8064f55137dedacd` — `fix(frontend): drop chart markers older than the loaded bar window (no bars[0] pile)` — 2026-06-16 15:29:23 -0500
- **Pushed origin tip:** `5a8d28a0e1f06da5bcfa98c346b9dd811084fc50` — `style: W2 lint fixes — import order in app.py, E501 wraps in test_lifecycle_w2` — 2026-06-12 14:19:28 -0500
- **Ahead 7 / behind 0.** Unpushed commits (newest first):
  - `0286dc7` fix(frontend): drop chart markers older than the loaded bar window (no bars[0] pile)
  - `77ec617` fix(frontend): declutter chart marker annotations — inline text → hover tooltip
  - `8bdedfb` feat: Databento queue-overflow fix + warm-start broadcast throttle
  - `099a1a5` fix: W3b Finding-1 — classify_serving_only reconciles the <5-interaction-trade asymmetry
  - `d96094f` feat: W3b crash-resumable window runner + parity report
  - `fb26643` feat: W3b batch↔serving parity gate + falsification
  - `b27e2c0` chore: W3a P0 housekeeping — gitignore root recon/diff scratch artifacts
- **Dirty tree** — staged: *none*; modified (13): `.claude/scheduled_tasks.lock`, `backend/scripts/w3b/headless_replay.py`, `backend/scripts/w3b/run_window.py`, `backend/scripts/w3b/window.py`, `backend/src/trade_lab/adapters/databento.py`, `backend/src/trade_lab/api/app.py`, `backend/tests/test_live_warm_start.py`, `frontend/src/App.test.tsx`, `frontend/src/chart/overlayManager.test.ts`, `frontend/src/chart/overlayManager.ts`, `frontend/src/chart/viewModels.ts`, `frontend/src/components/TradingChart.test.tsx`, `frontend/src/components/TradingChart.tsx`; untracked (10): `BASELINE_REPORT.md`, `D1_CHARACTERIZATION.md`, `READER_CORRECTNESS_PROOF.md`, `W3B_LIVELOCK_ROOTCAUSE.md`, `backend/D1_CHARACTERIZATION.md`, `backend/W3B_FIX_TL_DIFF.txt`, `backend/package-lock.json`, `backend/tests/test_w3b_drive_terminalization.py`, `backend/tests/test_w3b_run_window_exceptions.py`, `test.md`

### QL — Claude-Quant-Lab

- **Local tip = pushed origin tip (in sync):** `098e354ff1f878e6f3d2e9e16138c9143d990ebf` — `fix(ml): guard build_utility_dataset against seedless/wrong-seed day caches` — 2026-06-17 03:58:38 -0500
- **Ahead 0 / behind 0.**
- **Dirty tree** — staged: *none*; modified: *none*; untracked (16): `.w3_new_bundle_name`, `CACHE_GUARD_QL_DIFF.txt`, `E3_QL_DIFF.txt`, `E_QL_DIFF.txt`, `QL_TRAINING_UI_RECON.md`, `QL_UI_TRAIN_GAP_RECON.md`, `W1_QL_DIFF.txt`, `W2_QL_DIFF.txt`, `W3A_PRECEDING_6_REVIEW.txt`, `W3A_QL_DIFF.txt`, `W3A_READER_QL_DIFF.txt`, `W3_CONFIG_RECON.md`, `W3_WARMER_DIFF.txt`, `scratch_w3a_p2_gate.py`, `scratch_w3b_0212_regen.out`, `scratch_w3b_0212_regen.py`
  - Note: `W3A_P1_PROOF.log`, `W3A_P2_GATE.log`, `W3A_WARM.log`, `W3A_WARM_launch.log` exist at the QL root but are **gitignored** (`.gitignore:19 *.log`), so they don't appear in `git status`. Same for TL's `W3B_TL_DIFF.txt` (`.gitignore:72 /*_DIFF.txt`).

---

## 2. SC `docs/PLATFORM_REFACTOR_PROGRESS.md`

### Status section (verbatim, lines 1486–1489 — the doc's final `### Status`; as of unpushed local tip `3a37f75`)

> ### Status
> Phases A–E3: COMPLETE. W1: COMPLETE (pushed; pins bumped; CI witnessed). W2: COMPLETE (pushed; pins held `256020c` — no consumer-facing SC change; CI ×3 green incl. SC's first run; W2-FIX + the TL lint commit `5a8d28a` recorded). Current: W3 — **W3a bundle BUILT on D-036 (`NQ_W3_20260613T055600Z`); W3b gate run over the full 73-day window = 236/236 BIT-EXACT with one RED (2026-02-12), root-caused to a None-seeded standalone-build cache the warmer skipped and RESOLVED (5-touch regen + the `098e354` seed guard); `098e354` + 6 preceding W3a commits greenlit, push pending. CAVEAT (design review): that build + gate ran on the STALE 583-line site-packages reader — bit-exact green = CONSISTENCY on a shared unvalidated reader, NOT correctness. The vectorized reader SC `37359ae` is now validated CORRECT vs raw ground truth (`READER_CORRECTNESS_PROOF.md`). IN FLIGHT: vectorized-reader redeploy + W3 bundle rebuild + W3b re-gate on it — LOCAL, push pending.** S9.9, F1–F3: PARKED behind W3 green + soak. Live model outputs remain DECORATIVE until W3's gate is green on the fresh bundle (re-gated on the validated reader).

### Record sections added after the W3A-READER subsection (line 1474)

- `#### W3a BUILD → W3b GATE → READER VALIDATION (2026-06-13 → 2026-06-17; landed LOCALLY — push pending)` (line 1478)
- `### Status` (line 1486 — quoted above)

No other sections follow.

---

## 3. Decision logs

- **SC `docs/DECISIONS.md` — entries after D-P-15: NONE.** `D-P-15 RATIFIED (2026-06-12)` (W3A-READER pre-build vectorization under identity proof + drift net) is the final entry; the file ends with the "How to add an entry" convention note.
- **QL `docs/DECISIONS.md` — entries after D-037: NONE.** `D-037: Quote Feature Rides the Gate — Stub-Exclusion Pre-Ruling Superseded` (2026-06-12) is the final entry (file ends at line 322).

---

## 4. QL model-store bundles (`models/NQ_W3_*`)

### `NQ_W3_20260613T055600Z` — dir mtime 2026-06-13 00:57:08 -0500

| File | Size (bytes) |
|------|-------------:|
| evaluation.json | 19,244 |
| metadata.json | 3,632 |
| model.cbm | 2,142,240 |
| model.cbm.sha256 | 77 |
| oos_predictions.parquet | 10,123 — **41 rows** (parquet metadata) |
| strategy.json | 3,685 |

### `NQ_W3_20260617T220752Z` — dir mtime 2026-06-17 17:08:58 -0500

| File | Size (bytes) |
|------|-------------:|
| evaluation.json | 19,066 |
| metadata.json | 3,633 |
| model.cbm | 2,140,184 |
| model.cbm.sha256 | 77 |
| oos_predictions.parquet | 10,155 — **42 rows** (parquet metadata) |
| strategy.json | 3,685 |

Note: QL root untracked file `.w3_new_bundle_name` contains exactly `NQ_W3_20260617T220752Z` — i.e., the 06-17 bundle is the IN-FLIGHT rebuild artifact referenced by the Status section.

---

## 5. Root evidence files (W3A_*/W3B_*/WARM/GATE/PROOF; mtime + first/last line)

### SC root

| File | mtime | Size |
|------|-------|-----:|
| `W3A_READER_PROOF.log` | 2026-06-12 20:17:32 -0500 | 4,646 |
| `W3A_READER_SC_DIFF.txt` | 2026-06-12 20:45:06 -0500 | 49,976 |
| `W3A_SC_DIFF.txt` | 2026-06-12 17:06:25 -0500 | 21,282 |
| `W3B_0212_DIFF.log` | 2026-06-17 02:25:14 -0500 | 18,821,407 |
| `W3B_0212_RAW.log` | 2026-06-17 02:15:33 -0500 | 19,968,857 |

- `W3A_READER_PROOF.log` — first: `W3A-READER P3a IDENTITY PROOF — row-wise vs vectorized DatabentoParquetSource` · last: `assumption: non-reader pipeline cost (~420s/day: runtime drive, labeling, features) unchanged; per-day ml_utility caches make reruns instant.`
- `W3A_READER_SC_DIFF.txt` — first: `diff --git a/docs/DECISIONS.md b/docs/DECISIONS.md` · last: `return DataQualityWarning(code=code, message=message, severity=severity, source=source, event_ts_utc=event_ts_utc, metadata=metadata)`
- `W3A_SC_DIFF.txt` — first: `diff --git a/docs/PLATFORM_REFACTOR_PROGRESS.md b/docs/PLATFORM_REFACTOR_PROGRESS.md` · last: `---`
- `W3B_0212_DIFF.log` — first: `W3b 02-12 reader diff  run=2026-06-17T02:13:07  SC HEAD=332ad3e` · last: `QUOTE ts=2026-02-12 15:55:59.979800373+00:00 bid=25044.5 ask=25045.0 bidsz=2 asksz=1 (ticks 100178/100180)`
- `W3B_0212_RAW.log` — first: `RAW scan C:\Users\gonza\Documents\Claude-Quant-Lab\data\databento\NQ\2026-02-12\mbp10.parquet` · last: `ts=2026-02-12 15:55:59.979800373+00:00 act='A' side='A' px=25045.0 size=1 seq=340224934 bid=25044.5 ask=25045.0 sym='NQH6' iid=42002475`

### TL root (+ one backend/ match)

| File | mtime | Size |
|------|-------|-----:|
| `W3B_LIVELOCK_ROOTCAUSE.md` | 2026-06-18 20:58:45 -0500 | 15,294 |
| `W3B_TL_DIFF.txt` | 2026-06-15 17:10:20 -0500 | 75,138 |
| `backend/W3B_FIX_TL_DIFF.txt` | 2026-06-15 18:59:29 -0500 | 16,482 |

- `W3B_LIVELOCK_ROOTCAUSE.md` — first: `# W3b replay _drive livelock — root-cause report` · last: (blank)
- `W3B_TL_DIFF.txt` — first: `===============================================================================` · last: `+    assert diff.green, diff.summary()`
- `backend/W3B_FIX_TL_DIFF.txt` (not at root, included for completeness) — first: `commit 099a1a53f6b1a3f3027433790317a795b84ce78e` · last: `bad = dict(s.probabilities)`

### QL root

| File | mtime | Size |
|------|-------|-----:|
| `W3A_P1_PROOF.log` | 2026-06-12 16:22:58 -0500 | 344 |
| `W3A_P2_GATE.log` | 2026-06-12 16:57:03 -0500 | 272 |
| `W3A_PRECEDING_6_REVIEW.txt` | 2026-06-17 11:37:00 -0500 | 52,501 |
| `W3A_QL_DIFF.txt` | 2026-06-12 17:06:25 -0500 | 22,083 |
| `W3A_READER_QL_DIFF.txt` | 2026-06-12 19:58:47 -0500 | 4,777 |
| `W3A_WARM.log` | 2026-06-17 17:06:34 -0500 | 18,505 |
| `W3A_WARM_launch.log` | 2026-06-12 22:19:19 -0500 | 9,447 |

- `W3A_P1_PROOF.log` — first: `=== 2022-02-15 ===` · last: `OVERALL: IDENTICAL`
- `W3A_P2_GATE.log` — first: `config hash: 7850272e; cache pre-exists: False` · last: `GATE (90 min): STOP`
- `W3A_PRECEDING_6_REVIEW.txt` — first/last: `================================================================================` (banner lines)
- `W3A_QL_DIFF.txt` — first: `diff --git a/docs/DECISIONS.md b/docs/DECISIONS.md` · last: `+        )`
- `W3A_READER_QL_DIFF.txt` — first: `commit 0a03980864874d07beb6e583848ba944175bb3fa` · last: `from alpha_lab.agents.data_infra.ml.dashboard_utility_builder import build_utility_dataset`
- `W3A_WARM.log` — first: `# 2026-06-13T02:42:07.808372+00:00 W3 cache warmer | tag=7850272e | symbol=NQ | window=73d | targets=2 | workers=2 | pid=59748` · last: `# 2026-06-17T22:06:34.524636+00:00 DONE wall=24.7min counts={'EMPTY': 14, 'OK': 43} peak_rss_gb=6.26 (day=2026-02-05) | suggested_workers: floor(20GB / 6.26GB peak) = 3 -> min(4, max(2, 3)) = 3` — note this log spans 06-13 → 06-17; its final DONE is the 06-17 re-warm that preceded the rebuild bundle.
- `W3A_WARM_launch.log` — first: `# 2026-06-13T02:49:27.782756+00:00 W3 cache warmer | tag=7850272e | symbol=NQ | window=73d | targets=70 | workers=4 | pid=62360` · last: `# 2026-06-13T03:19:19.035610+00:00 DONE wall=29.9min counts={'EMPTY': 14, 'OK': 56} peak_rss_gb=6.36 (day=2026-02-02) | suggested_workers: floor(20GB / 6.36GB peak) = 3 -> min(4, max(2, 3)) = 3`

(SC root `W1_/W2_/W2FIX_*_DIFF.txt` and QL `W3_CONFIG_RECON.md` / `W3_WARMER_DIFF.txt` etc. don't match the requested patterns; they're enumerated in §1's dirty-tree lists.)

---

## 6. SC pins (verbatim, as they stand on disk)

- **TL** `backend/pyproject.toml:18` → `"strategy-core @ git+https://github.com/thealgochef/Strategy-Core.git@256020c263a019aa8ffbb55aab804f2ebef2c1f6",`
- **QL** `pyproject.toml:36` → `"strategy-core @ git+https://github.com/thealgochef/Strategy-Core.git@256020c263a019aa8ffbb55aab804f2ebef2c1f6",`

Both pins sit at `256020c2` (the held W2 pin) — 4 SC commits behind the local SC tip and **not** pointing at the validated vectorized reader `37359ae` (consistent with the Status section's "redeploy IN FLIGHT, push pending").

---

## 7. CI (unauthenticated GitHub API; `gh` CLI not installed)

| Repo | Workflow | Last run on `platform-refactor` | Conclusion | head_sha |
|------|----------|--------------------------------|------------|----------|
| SC | `ci` (run #2) | `27446811807` | ✅ success | `5ac08a0b` = origin tip |
| TL | `backend-ci` (run #6) | `27437711555` | ✅ success | `5a8d28a0` = origin tip |
| QL | `ci` (run #5) | `27708038721` | ✅ success | `098e354f` = origin tip = local tip |

All three origin tips are CI-green. The 4 SC + 7 TL unpushed commits have, by construction, never run in CI.
