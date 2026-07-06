# Platform Refactor — BACKLOG (open punt-list)

Companion to `PLATFORM_REFACTOR_PROGRESS.md` (the execution log) and
`PLATFORM_REFACTOR_PLAN.md` (the authoritative spec). This file is the **open punt-list**:
work deliberately deferred out of a window, grouped by tier. Items graduate out of here when
they land in PROGRESS. Doc-only; commits ride the next greenlight.

---

## Tier 1 — Pre-soak blockers (clear before any real-money soak)

- **Live reader raw-correctness audit (`DatabentoLiveSource`).** `READER_CORRECTNESS_PROOF.md`
  validated the **replay** reader (`DatabentoParquetSource`) against raw ground truth; the soak
  runs the **live** path, which is a separate code path with no equivalent raw-bytes proof yet.
  Audit the live normalize path to the same standard before trusting live numbers.
- **Counter-vs-QL equality test for the Finding-1 asymmetry reconciler.** The
  `classify_serving_only` reconciler (the deliberate `<5-interaction-print` serving asymmetry)
  needs a test asserting its counter matches QL's, owed to a fully-green W3b.

## Tier 2 — Owed for the record (low-effort)

- **02-12 W3b gate re-run, per-axis output.** The per-axis diff for the resolved 2026-02-12
  touch was captured in chat only — no committed artifact yet.
- **`Trade.side` docstring fix (`strategy_core/types.py`).** The comment has `A`/`B`
  buy/sell **backwards** relative to the ratified `BUY_AGGRESSOR_SIDE='B'`. Decode is
  byte-faithful (verified in the reader proof); this is a documentation-only correction.
- **Minor cosmetics.** `c6fc42c` parses `--pin-features` via `_parse_sessions` (works;
  cosmetic naming); `ef77885` proof note on low-touch days (timings near-neutral because
  unseeded proof days yield few touches — record the caveat).

## Tier 3 — Near-term (queued behind W3b)

- **TL live-insight surfaces UI.** Surface the serving stack's live insight as first-class UI
  panels — predictions/probabilities with gate state, level/touch context, drop reasons, and
  the prediction-journal history; today the chart markers + hover tooltip are the only surface.
- **Verify-prior-session-levels recon.** Recon TL's LIVE prior-session level seeding (rolling
  PDH/PDL + session extremes) against the canonical store for a sample of live days. The W3b
  gate proves the REPLAY path's seeding (and 02-12 showed exactly how a wrong seed silently
  changes the level set); the live path's equivalent is unproven.
- **QL Training UI (`ml_training_tab.py`).** Pin-features multiselect, RFECV decoupling,
  fold-scheme controls.
- **IFVG plugin `ifvg_smc`.** Design complete through Phase 5; open **Q-40** (4H/1H bar
  anchoring); blocked on W3b.

## Tier 4 — Deferred / roadmap

- **Block-1 out-of-regime stress audit** (2021-12-02 → 2022-03-10, ATR-normalized).
- **Stashed branch `wip/warm-context-backfill` (`114e6e4`)** — revisit or drop.
- **Parked platform sections** — S9.9, Phase-F, §3, 9.10.
- **ML strategy shortlist** — opening-drive classifier; day-type/regime overlay; meta-labeling
  on strategy A; volatility-state / barrier-geometry audit; execution micro-timing.
- **v2 IFVG** — key-level HTF roots; `freshest_wins`/`nearest_wins` priority; BE-managed label
  family; pool fallback from v1 pain-state data.
- **Early-exit fast-path (~2× gate lever; shelved).** Stop each gate day's replay at the last
  touch-relevant event (all labels/outcomes for the day complete) instead of draining to the
  session cutoff — roughly halves per-day serving wall with NO engine change. Needs its own
  completeness proof (journal identical to the full drain) before adoption. Shelved: iteration
  currently routes around full replays with narrow-days + `--resume`; it sequences AHEAD of the
  T4 rewrite below as the cheaper iteration-speed lever.
- **T4 — Serving-engine array rewrite (scaling/perf; money-path; major gated project).** The
  serving engine — not the reader — is the gate bottleneck. The vectorized reader drains a full
  day in 37s; pushing those events through the Python-object serving state machine takes
  ~26 min/day (~8,147 ev/s solo). It's also why the gate won't parallelize: the scattered
  Python-object working set blows the shared 96 MB V-Cache, so two workers on distinct days
  collapse below solo (same-file 2-workers scale to ~13k agg; different-file collapse to ~4–5k).
  Rewrite the serving hot path to arrays: Python objects → NumPy/Arrow; `list[event]` →
  struct-of-arrays; dict/attr → integer columns/enums/bitmasks; per-event callbacks → tight
  sequential loop over array rows; object retention buffer → ring-buffer arrays; diagnostic
  objects → sampled counters. Wins on both axes (faster per-worker + small enough footprint to
  actually parallelize) and benefits live serving too.
  **Constraint:** serving is stateful/sequential, so the win is a leaner sequential loop, NOT
  vectorized/parallel decisions (impossible for a state machine — unlike the reader, where decode
  was stateless).
  **Risk/scope:** this is the money-path decision engine — must produce byte-identical decisions
  and re-pass full parity + gate-and-soak. The validation burden, not the engineering, is the cost.
  **Sequencing:** behind the early-exit gate (cheaper iteration-speed lever, no engine change).
  Revisit only if full serving replays become a recurring bottleneck — iteration currently routes
  around them with narrow-days + `--resume`.
  **Baseline note (2026-07-03):** the ~8,147 ev/s / ~26 min-day figures predate the W3b
  terminalization fix. Clean completed-day spans now exist from the re-gate benches (e.g.
  12-18 = 1554 s at workers=1 for 13.48 M events ≈ 8.7 k ev/s, but measured with debug ticks
  on, inside a 2-day serial run) — a true SOLO dense-day baseline (one worker, one day, no
  co-runner, debug off) is still owed before sizing this rewrite's win.
