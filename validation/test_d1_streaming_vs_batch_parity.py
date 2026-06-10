"""GATE A (D1a): streaming honest resolver == batch resolve_honest_outcome, per touch.

Over the 9 real store days 2025-07-10 -> 2025-07-22 (the b3 multiday window), one
production plugin runtime is rolled exactly like the b3 multiday regression
(``reset()`` + reseed from the preceding processed day at each boundary; reuses
``_read_trades``/``_build_runtime``). Every runtime touch is resolved BOTH ways with
identical params (the engine constants: tp/sl/trap + DECISION_OFFSET_MINUTES):

(i)  STREAMING, as wired: ``StreamingHonestResolver`` fed from the live seams — entry
     prints from the runtime's trade ring (``StrategyRuntime.trade_price_at``), forward
     bars from each ``RuntimeUpdate.closed_bars``. A touch is registered on the first
     trade whose clock is at/after its decision instant (the resolver's caller
     contract — production registers at observation expiry, the same instant); pending
     touches whose decision lands after the day's last print are registered post-loop,
     and the day ends with ``flush(<window end>)``.
(ii) BATCH: ``resolve_honest_outcome(touch, day_bars, reference_price_at, ...)`` where
     ``day_bars`` is the day's full closed forward-bar list (the same bars the
     streaming side consumed) and ``reference_price_at`` reproduces the
     ``decision_diff_harness.py:594-616`` reference semantics over the SAME front-month
     trade prints ``_read_trades`` feeds the runtime: most recent print with
     ``ts <= as_of`` within the 30-minute bounded lookback. (The reference SQL's
     ``bid/ask > 0`` predicate is parquet row-validity; the ratified live analogue is
     the ``price > 0`` gate ``_read_trades`` already applies — D1a design.)

Direction is NOT re-derived: ``touch.direction`` is the production decision path's
authoritative direction (resolved on the merged-zone side; consumed verbatim by the
QL adapter ``engine_decision.process_single_date_engine`` and by ``resolve_outcome``).

EXACT per-touch equality asserted: drop-vs-outcome, drop reason, label, max_mfe /
max_mae (the kernel's 4dp rounding), bars_to_resolution (both sides 0-based / -1
sentinel), entry price. Non-vacuity: the window must yield nonzero resolved outcomes;
per-reason drop counts are reported.

Run:    python validation/test_d1_streaming_vs_batch_parity.py
pytest: pytest validation/test_d1_streaming_vs_batch_parity.py
"""

from __future__ import annotations

import bisect
from datetime import datetime, timedelta

import pandas as pd

from test_b3_golive_plugin_regression import DATA_DIR, TICK_SIZE, _build_runtime, _read_trades

from _b3_regression_util import (
    MULTIDAY_DAYS,
    day_extremes_ticks,
    static_reference_levels,
)

from strategy_core.constants import (
    DECISION_OFFSET_MINUTES,
    DEFAULT_SL_POINTS,
    DEFAULT_TP_POINTS,
    DEFAULT_TRAP_MFE_MIN,
)
from strategy_core.decisions.honest_entry import HonestEntryDrop, resolve_honest_outcome
from strategy_core.decisions.outcomes import OutcomeResult
from strategy_core.decisions.streaming import (
    TRADE_PRICE_LOOKBACK_MINUTES,
    StreamDrop,
    StreamingHonestResolver,
    StreamResolution,
)

FORWARD_TF = 147
_DECISION_OFFSET = timedelta(minutes=DECISION_OFFSET_MINUTES)


def _window_end_utc(day: str) -> datetime:
    return pd.Timestamp(f"{day} 18:00:00", tz="America/New_York").tz_convert("UTC").to_pydatetime()


class _ReferencePriceAt:
    """The batch reference entry query over the day's front-month prints (see module doc)."""

    def __init__(self, trades) -> None:
        self._ts = [t.event_ts_utc for t in trades]
        self._px = [t.price_ticks * TICK_SIZE for t in trades]

    def __call__(self, as_of: datetime) -> float | None:
        i = bisect.bisect_right(self._ts, as_of) - 1  # most recent ts <= as_of
        if i < 0:
            return None
        if self._ts[i] < as_of - timedelta(minutes=TRADE_PRICE_LOOKBACK_MINUTES):
            return None
        return self._px[i]


def _run_day(runtime, resolver, trades, day: str):
    """Replay one day; return (streaming events by key, touches, day forward bars)."""
    events: dict[int, StreamResolution | StreamDrop] = {}
    touches = []
    day_bars = []
    pending = []  # (decision_ts_utc, key, touch), FIFO in touch order

    def _register_due(now_ts: datetime) -> None:
        while pending and pending[0][0] <= now_ts:
            _, key, touch = pending.pop(0)
            drop = resolver.register(
                key,
                touch_bar_ts_utc=touch.bar_ts_utc,
                trading_day=touch.trading_day,
                direction=touch.direction,
            )
            if drop is not None:
                events[key] = drop

    for tr in trades:
        update = runtime.process_event(tr)
        # Register due setups BEFORE feeding this update's closed bars: a bar closing on
        # this very trade with close > decision_ts belongs to the forward window (the
        # batch bound is strict close > decision_ts, not close > registration time).
        _register_due(tr.event_ts_utc)
        for bar in update.closed_bars:
            if bar.timeframe_ticks == FORWARD_TF:
                day_bars.append(bar)
            for emitted in resolver.on_bar(bar):
                events[emitted.key] = emitted
        for touch in update.touches:
            key = len(touches)
            touches.append(touch)
            pending.append((touch.bar_ts_utc + _DECISION_OFFSET, key, touch))

    # Touches whose decision instant falls after the day's last print (e.g. inside the
    # 17:00-18:00 ET halt): register now — flatten/cutoff drop them identically to batch,
    # and the entry query semantics are unchanged (most recent print <= decision instant).
    _register_due(_window_end_utc(day))
    for emitted in resolver.flush(_window_end_utc(day)):
        events[emitted.key] = emitted
    return events, touches, day_bars


def _compare(day, key, touch, streaming, batch, ref_entry) -> list[str]:
    tag = f"{day} touch[{key}] {touch.level_type} {touch.direction} @{touch.bar_ts_utc}"
    problems = []
    if isinstance(batch, HonestEntryDrop):
        if not isinstance(streaming, StreamDrop) or streaming.reason != batch.reason:
            problems.append(f"{tag}: batch drop {batch.reason!r} vs streaming {streaming!r}")
            return problems
        if streaming.decision_ts_utc != batch.decision_ts_utc:
            problems.append(f"{tag}: decision_ts {streaming.decision_ts_utc} != {batch.decision_ts_utc}")
        if batch.reason == "no_forward" and streaming.entry_price != batch.entry_price:
            problems.append(f"{tag}: no_forward entry {streaming.entry_price} != {batch.entry_price}")
        return problems
    assert isinstance(batch, OutcomeResult)
    if batch.label == "no_resolution":
        if not isinstance(streaming, StreamDrop) or streaming.reason != "no_resolution":
            problems.append(f"{tag}: batch no_resolution vs streaming {streaming!r}")
            return problems
        if (streaming.max_mfe, streaming.max_mae, streaming.bars_to_resolution) != (
            batch.max_mfe,
            batch.max_mae,
            batch.bars_to_resolution,
        ):
            problems.append(
                f"{tag}: no_resolution extremes/bars "
                f"({streaming.max_mfe},{streaming.max_mae},{streaming.bars_to_resolution}) != "
                f"({batch.max_mfe},{batch.max_mae},{batch.bars_to_resolution})"
            )
        if streaming.entry_price != ref_entry:
            problems.append(f"{tag}: no_resolution entry {streaming.entry_price} != {ref_entry}")
        return problems
    if not isinstance(streaming, StreamResolution):
        problems.append(f"{tag}: batch {batch.label!r} vs streaming {streaming!r}")
        return problems
    got = (
        streaming.result.label,
        streaming.result.max_mfe,
        streaming.result.max_mae,
        streaming.result.bars_to_resolution,
        streaming.entry_price,
    )
    want = (batch.label, batch.max_mfe, batch.max_mae, batch.bars_to_resolution, ref_entry)
    if got != want:
        problems.append(f"{tag}: resolved mismatch {got} != {want}")
    return problems


def _run_gate():
    runtime = _build_runtime()
    resolver = StreamingHonestResolver(
        forward_timeframe_ticks=FORWARD_TF,
        tick_size=TICK_SIZE,
        tp_points=DEFAULT_TP_POINTS,
        sl_points=DEFAULT_SL_POINTS,
        trap_mfe_min=DEFAULT_TRAP_MFE_MIN,
        trade_price_at=runtime.trade_price_at,
        available_timeframes=(FORWARD_TF,),
    )
    problems: list[str] = []
    per_day = []
    totals = {"touches": 0, "resolved": 0}
    drop_counts: dict[str, int] = {}
    label_counts: dict[str, int] = {}
    prev_extremes = None
    days_run = 0

    for i, day in enumerate(MULTIDAY_DAYS):
        trades = _read_trades(day)
        if not trades:
            per_day.append((day, None))
            continue
        if i > 0 and prev_extremes is not None:
            runtime.reset()  # also clears the trade ring; resolver is empty (flushed)
            ph, pl, pday = prev_extremes
            runtime.load_prior_day_summary(pday, high_ticks=ph, low_ticks=pl)
            runtime.set_static_levels(static_reference_levels(ph, pl, TICK_SIZE))
        events, touches, day_bars = _run_day(runtime, resolver, trades, day)
        assert resolver.open_count == 0, f"{day}: {resolver.open_count} setups survived the flush"
        reference = _ReferencePriceAt(trades)
        day_stats = {"touches": len(touches), "resolved": 0, "drops": {}}
        for key, touch in enumerate(touches):
            assert key in events, f"{day} touch[{key}]: streaming produced no event"
            batch = resolve_honest_outcome(
                touch,
                day_bars,
                reference,
                tick_size=TICK_SIZE,
                tp_points=DEFAULT_TP_POINTS,
                sl_points=DEFAULT_SL_POINTS,
                trap_mfe_min=DEFAULT_TRAP_MFE_MIN,
                decision_offset_minutes=DECISION_OFFSET_MINUTES,
            )
            ref_entry = reference(touch.bar_ts_utc + _DECISION_OFFSET)
            problems.extend(_compare(day, key, touch, events[key], batch, ref_entry))
            streaming = events[key]
            if isinstance(streaming, StreamResolution):
                day_stats["resolved"] += 1
                label_counts[streaming.result.label] = (
                    label_counts.get(streaming.result.label, 0) + 1
                )
            else:
                day_stats["drops"][streaming.reason] = (
                    day_stats["drops"].get(streaming.reason, 0) + 1
                )
                drop_counts[streaming.reason] = drop_counts.get(streaming.reason, 0) + 1
        totals["touches"] += day_stats["touches"]
        totals["resolved"] += day_stats["resolved"]
        per_day.append((day, day_stats))
        prev_extremes = (*day_extremes_ticks(trades), pd.Timestamp(day).date())
        days_run += 1

    return days_run, per_day, totals, drop_counts, label_counts, problems


def test_d1_streaming_vs_batch_parity():
    import pytest

    if not DATA_DIR.exists():
        pytest.skip(f"databento store not available at {DATA_DIR}")
    days_run, per_day, totals, drop_counts, label_counts, problems = _run_gate()
    if days_run < 7:
        pytest.skip(f"need >=7 multiday days for the gate; only {days_run} resolved")
    assert not problems, "streaming-vs-batch mismatches:\n" + "\n".join(problems)
    # Non-vacuity: the window must actually exercise the resolved path.
    assert totals["resolved"] > 0, "vacuous gate: zero resolved outcomes across the window"
    assert totals["touches"] > 0, "vacuous gate: zero touches across the window"
    print(
        f"\nGATE A: {totals['touches']} touches / {totals['resolved']} resolved across "
        f"{days_run} days; drops by reason: {drop_counts}; labels: {label_counts}"
    )


if __name__ == "__main__":
    import warnings

    warnings.simplefilter("ignore")
    print("GATE A — streaming honest resolver vs batch resolve_honest_outcome\n"
          f"store = {DATA_DIR}\nparams: tp={DEFAULT_TP_POINTS} sl={DEFAULT_SL_POINTS} "
          f"trap={DEFAULT_TRAP_MFE_MIN} offset={DECISION_OFFSET_MINUTES}m tf={FORWARD_TF}t\n")
    days_run, per_day, totals, drop_counts, label_counts, problems = _run_gate()
    for day, stats in per_day:
        if stats is None:
            print(f"  {day}: NO DATA")
            continue
        print(f"  {day}: touches={stats['touches']} resolved={stats['resolved']} "
              f"drops={stats['drops']}")
    print(f"\nTOTAL: touches={totals['touches']} resolved={totals['resolved']}")
    print(f"DROPS BY REASON: {drop_counts}")
    print(f"RESOLVED LABELS: {label_counts}")
    if problems:
        print(f"\nMISMATCHES ({len(problems)}):")
        for p in problems:
            print(f"  {p}")
        print("\nVERDICT: DIVERGED")
    else:
        print("\nVERDICT: EXACT per-touch parity — streaming == batch on every touch.")
