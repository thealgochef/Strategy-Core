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

- **TL warm-up thread.** The viewport fix `ddcfdc0` broke warm-up replay; warm-up **and**
  full marker-history visibility are both dark and need restoring.
- **D1b — flip TL dashboard to `StreamingHonestResolver`, retire `OutcomeTracker`.** Prompt
  delivered; pending execution.
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
