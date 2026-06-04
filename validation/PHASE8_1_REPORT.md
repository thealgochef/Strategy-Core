# Phase 8.1 — Honest-Entry Orchestration Relocation

## 1. Why + the pure-relocation GATE

Phase 8 left the honest-entry decision MEANING (decision_ts = touch +
`DECISION_OFFSET_MINUTES`; flatten/cutoff DROP; entry-price lookup at the decision
instant; forward-window selection; `resolve_outcome` call) inline in **two copies**
outside the engine: the production CQL adapter
`engine_decision.process_single_date_engine` (honest_entry=True) and a hand-copied
MIRROR in the SC `validation/decision_diff_harness.py`. Two copies of the decision
rule outside the engine (and a deferred Trade-Lab repoint would make a third). This
phase hoists that rule into `strategy_core` as ONE pure function; the two existing
copies become thin callers that only INJECT data accessors.

**HARD GATE (held):** this is a PURE RELOCATION.

- BYTE-IDENTICAL to Phase 8 output — **YES**.
- No behavior / constant / threshold / class / semantics change.
- No `engine_version` bump — stays `strategy_core_engine_v2`.
- `resolve_outcome` body UNCHANGED (pure forward-scan byte-unchanged).
- No Trade-Lab edit.
- `strategy_core` stays dependency-pure (stdlib + `zoneinfo`; no pandas/duckdb/pytz).
- All changes left UNCOMMITTED.

## 2. The new engine function

**Location:** `src/strategy_core/decisions/honest_entry.py`

```python
def resolve_honest_outcome(
    touch: Touch,
    day_bars: Sequence[Bar],
    trade_price_at: Callable[[datetime], float | None],
    *,
    tick_size: float,
    tp_points: float,
    sl_points: float,
    trap_mfe_min: float,
    decision_offset_minutes: int = DECISION_OFFSET_MINUTES,
    flatten_time: time = FLATTEN_TIME,
    rth_end: time = RTH_END,
    timezone: str = SESSION_TIMEZONE,
) -> OutcomeResult | HonestEntryDrop:
```

Exported from `strategy_core.decisions.__init__` and re-exported from the package
`strategy_core.__init__` (`resolve_honest_outcome` + `HonestEntryDrop`).

**Body (relocated verbatim):** `decision_ts = touch.bar_ts_utc + decision_offset`;
DROP `flatten` if decision_ts ET time `>= flatten_time` (non-strict); DROP `cutoff`
if `decision_ts >= touch.trading_day` rth_end cutoff (non-strict); `entry =
trade_price_at(decision_ts_utc)`, DROP `no_fill` if `None`; forward = day bars with
`close_ts_utc` strictly `> decision_ts` AND strictly `< rth_cutoff`, DROP `no_forward`
if empty; else the UNCHANGED `resolve_outcome(...)`. The DROP arm is the discriminated
`HonestEntryDrop(reason, decision_ts_utc, entry_price)`.

**Injected I/O — exactly one callable:** `trade_price_at` (the realistic front-month
TRADE-print point query at the UTC decision instant; 30-min bounded lookback). Plus the
full day's `day_bars` (the engine slices the forward window itself). Everything else is
pure (stdlib `datetime`/`zoneinfo` + `strategy_core` types/constants). Defaults are
single-sourced from `strategy_core.constants`
(`DECISION_OFFSET_MINUTES`/`FLATTEN_TIME`/`RTH_END`/`SESSION_TIMEZONE`).

## 3. The two deletions (now thin callers)

**CQL** `engine_decision.process_single_date_engine` (honest_entry=True): deleted the
entire inline orchestration — `decision_ts_et = bar_ts_et + Timedelta(offset)`, the
`_at_or_after_flatten(decision_ts_et) or decision_ts_et >= rth_cutoff` drop, the
`_trade_price_at(...)` entry lookup + None-skip, and the
`forward = bars_et[(index > decision_ts_et) & (index < rth_cutoff)]` selection.
Replaced by a single `resolve_honest_outcome(...)` call injecting `_trade_price_for`
(closure over `_trade_price_at`) + the full day's bars; `HonestEntryDrop -> continue`.
Also DELETED the now-dead `_at_or_after_flatten` helper + its `FLATTEN_TIME` import (the
flatten rule is now single-sourced in the engine). The honest_entry=False book-mid
level-entry regression branch was PRESERVED inline (used by
`test_decision_repoint_parity`); `_trade_price_at` kept as the injected accessor.

**SC** `validation/decision_diff_harness.py` `run_pipeline`: DELETED both mirror helpers
(`_forward_bars`, `_at_or_after_flatten`) and the inline honest-label block (decision_ts
computation, flatten/cutoff drop, `price_at` fill + None-drop, `_forward_bars` call +
empty-drop, `resolve_outcome`). Replaced by a single `resolve_honest_outcome(...)` call
injecting `price_at` (`DayStreams.trade_price_at`) + the pipeline's `day_bars`; the
engine's discriminated reasons are mapped back to the harness taxonomy
(flatten/cutoff -> `flatten_or_cutoff`, no_fill -> `no_fill`, no_forward ->
`empty_forward`). Removed the now-unused `resolve_outcome` import (`FLATTEN_TIME` import
kept for `main()`'s banner).

## 4. Golden-equivalence

**BYTE_IDENTICAL = YES.** Golden captured BEFORE the CQL refactor (verbatim inline
Phase-8 loop) -> `golden.json`; AFTER capture routed through `resolve_honest_outcome`
-> `engine.json`; compared field-by-field. **14 touches** across the 3 core days
(2025-07-15 / 2025-07-07 / 2025-07-11): 12 dropped (all reason `flatten`), 2 traded.
ZERO fields differed across touch_bar_ts, rep_price, direction, level_type, decision_ts,
drop, reason, entry_price, fwd_first/fwd_last/fwd_count, label, label_encoded, max_mfe,
max_mae. Identical md5 on both files. The cutoff/no_fill/no_forward arms (not exercised
by the real golden) are covered by the synthetic engine unit tests.

**3-core-day decision-diff smoke: PASS.**
`validation/test_decision_diff.py::test_decision_diff_research_vs_tradelab` passed on the
3 core days through the refactored harness — levels/zones identical, <=1 touch diff,
identical honest survive/drop partition, 0 label flips, features below eps (matching
Phase 8).

## 5. Regression (fast gate only)

- **SC engine suite:** 104 passed (97 prior + 7 new `resolve_honest_outcome` unit tests
  in `tests/test_honest_entry.py`: traded-long, flatten-drop, cutoff-drop, no_fill-drop,
  no_forward-drop, non-strict flatten boundary at exactly 15:55, defaults-from-constants).
- **SC decision-diff smoke:** 1 passed (3 core days).
- **CQL book-mid repoint-parity:** `test_decision_repoint_parity` 14 passed, 1 skipped —
  honest_entry=False book-mid regression branch + trade-path cutover still match.

No extended multi-day sweep / full real-data re-sweep was run, per the fast-verification
gate.

## 6. Confirm

- `ENGINE_VERSION == strategy_core_engine_v2` (verified at import; NOT bumped).
- `strategy_core` dependency-PURE: importing the package + `honest_entry` + `outcomes`
  loads ZERO of {pandas, duckdb, pytz, numpy}; `honest_entry.py` imports only
  `__future__`/`collections.abc`/`dataclasses`/`datetime`/`zoneinfo`/`strategy_core`.
- `resolve_outcome` (and `classify_mae_first`) executable bodies are AST-identical to SC
  HEAD `4ce2e61` (docstring-stripped AST compares equal); the `outcomes.py` diff vs HEAD
  is pre-existing v2 docstring prose only — no code change.
- Both repos at expected HEADs (SC=4ce2e61, CQL=2f6aa62); all changes UNCOMMITTED;
  Trade-Lab untouched.

---

The honest-entry rule now has **ONE** source in the engine
(`resolve_honest_outcome`); the two former copies are thin injectors that only wire in
the `trade_price_at` accessor + day bars. The deferred Trade-Lab repoint will be a thin
third caller. **No behavior change.**
