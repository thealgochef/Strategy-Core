"""Honest decision-time outcome ORCHESTRATION (engine v2).

This is the ONE place the honest-entry decision MEANING lives. Phase 8 put this
orchestration inline in TWO copies outside the engine — the production CQL adapter
``engine_decision.process_single_date_engine`` (honest_entry=True) and the mirrored
SC ``validation/decision_diff_harness.py`` — with the decision rule hand-copied in
each. This module hoists that rule into ``strategy_core`` as a single PURE function;
the two callers become thin injectors that only wire in their data accessors.

The honest decision-time rule (UNCHANGED — relocated byte-for-byte from the two
copies; this is a pure relocation, not a behavior change):

  1. decision_ts = touch bar close + ``decision_offset_minutes`` (== the interaction
     feature window, so the feature window [touch, touch+offset] and the label window
     (decision, RTH_END] never overlap — the look-ahead closure).
  2. DROP (flatten) if decision_ts in ET is at/after ``flatten_time`` (``t >= flatten``,
     non-strict), matching the executor's no-entry rule (``_at_or_after_flatten``).
  3. DROP (cutoff) if decision_ts is at/after the touch-date ``rth_end`` cutoff
     (``decision_ts >= rth_cutoff``, non-strict).
  4. entry_price = ``trade_price_at(decision_ts_utc)`` — the INJECTED realistic
     front-month TRADE-print point query at the decision instant. DROP (no_fill) if
     ``None``.
  5. forward bars = the day's bars whose close is STRICTLY AFTER decision_ts AND
     STRICTLY BEFORE the rth_end cutoff (``close > decision_ts`` and
     ``close < rth_cutoff``). DROP (no_forward) if empty.
  6. call the EXISTING ``resolve_outcome(entry_points=entry_price, direction,
     forward_bars, tick_size, tp/sl/trap)`` — the PURE forward-scan, body unchanged.

PURE + bar-representation-agnostic + I/O only via the injected ``trade_price_at``
callable: stdlib + ``zoneinfo`` (the ET conversion the engine already uses for
sessions) + ``strategy_core`` types/constants only — NO pandas/duckdb/pytz. The
comparisons reproduce the two copies EXACTLY: timezone-aware instant comparisons
(equivalent to the copies' ET-index comparisons), the flatten/cutoff non-strict
``>=``, and the strict ``>``/``<`` forward-window bounds.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from strategy_core.constants import (
    DECISION_OFFSET_MINUTES,
    FLATTEN_TIME,
    RTH_END,
    SESSION_TIMEZONE,
)
from strategy_core.decisions.outcomes import OutcomeResult, resolve_outcome
from strategy_core.types import Bar, Touch

__all__ = ["HonestEntryDrop", "resolve_honest_outcome"]


@dataclass(frozen=True, slots=True)
class HonestEntryDrop:
    """A touch that yields NO tradeable outcome under the honest decision-time rule.

    The discriminated DROP arm of ``resolve_honest_outcome``. ``reason`` is one of:

    * ``"flatten"``  — decision_ts in ET is at/after ``flatten_time``.
    * ``"cutoff"``   — decision_ts is at/after the touch-date ``rth_end`` cutoff.
    * ``"no_fill"``  — ``trade_price_at`` returned ``None`` at the decision instant.
    * ``"no_forward"`` — no day bar closes in (decision_ts, rth_cutoff).

    ``decision_ts_utc`` is carried for the callers' golden/diff bookkeeping;
    ``entry_price`` is the resolved fill when known (``no_forward``), else ``None``.
    """

    reason: str
    decision_ts_utc: datetime
    entry_price: float | None = None


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
    """The honest decision-time outcome for one touch (the single orchestration).

    PURE + I/O only via ``trade_price_at``. Returns an ``OutcomeResult`` when the
    touch is tradeable, or a ``HonestEntryDrop`` (with ``reason`` flatten / cutoff /
    no_fill / no_forward) when it is not. The body reproduces the Phase-8 inline
    orchestration in ``engine_decision.process_single_date_engine`` (honest_entry=True)
    and ``decision_diff_harness.run_pipeline`` EXACTLY.

    Args:
        touch: The detected first-touch event. ``touch.bar_ts_utc`` is the bar close
            (the decision anchor); ``touch.trading_day`` anchors the rth_end cutoff.
        day_bars: The FULL day's engine bars (the forward window is sliced from these
            by close-instant; the touch bar and pre-decision bars are excluded by the
            strict ``> decision_ts`` bound). Bar representation is agnostic — only
            ``close_ts_utc`` and the high/low ticks (read by ``resolve_outcome``) are
            used.
        trade_price_at: Injected accessor — the realistic front-month TRADE price at
            (or just before) a UTC decision instant (the CQL ``_trade_price_at`` /
            harness ``DayStreams.price_at``, 30-min bounded lookback). Returns ``None``
            when no qualifying print exists.
        tick_size: Points per tick, threaded to ``resolve_outcome``.
        tp_points / sl_points / trap_mfe_min: The label policy, threaded unchanged to
            ``resolve_outcome``.
        decision_offset_minutes: Minutes after the touch close the decision fires
            (default the engine constant == the interaction window).
        flatten_time: ET wall-clock ON ``touch.trading_day`` at/after which a
            decision is never traded (same-day anchored, like the cutoff).
        rth_end: ET wall-clock RTH cutoff (forward-window upper bound + cutoff drop).
        timezone: IANA tz for the ET conversions (default the engine session tz).

    Returns:
        ``OutcomeResult`` (traded) or ``HonestEntryDrop`` (reason flatten / cutoff /
        no_fill / no_forward).
    """
    tz = ZoneInfo(timezone)

    # (a) decision instant = touch close + decision_offset (== interaction window).
    decision_ts_utc = touch.bar_ts_utc + timedelta(minutes=decision_offset_minutes)

    # The touch-date forward cutoff (ET) = the ny-session close (engine v3: rth_end ==
    # 17:00 ET; was 16:15). touch.trading_day is the processing date the cutoff is
    # built from; 17:00 ET is never DST-ambiguous (DST flips at 02:00 ET).
    rth_cutoff_et = datetime.combine(touch.trading_day, rth_end, tzinfo=tz)
    # W1 P2a: flatten is anchored to the SAME trading day as the cutoff (an absolute
    # instant, not a bare wall-clock compare), so evening touches — which belong to
    # the NEXT trading day whose cutoff is ~21h away — are no longer embargoed by a
    # time-of-day comparison against the prior session's flatten.
    flatten_cutoff_et = datetime.combine(touch.trading_day, flatten_time, tzinfo=tz)

    # (b) executor no-entry rule: drop a decision at/after the flatten (non-strict,
    # ``t >= flatten``) or at/after the RTH cutoff (non-strict, ``>= cutoff``). Both
    # compares are on absolute instants anchored to ``touch.trading_day``.
    if decision_ts_utc >= flatten_cutoff_et:
        return HonestEntryDrop(reason="flatten", decision_ts_utc=decision_ts_utc)
    if decision_ts_utc >= rth_cutoff_et:
        return HonestEntryDrop(reason="cutoff", decision_ts_utc=decision_ts_utc)

    # (c) entry = realistic front-month TRADE price at the decision instant (injected
    # point query). DROP no_fill if there is no qualifying print.
    entry_price = trade_price_at(decision_ts_utc)
    if entry_price is None:
        return HonestEntryDrop(reason="no_fill", decision_ts_utc=decision_ts_utc)

    # (d) forward window: bars whose close is strictly AFTER the decision AND strictly
    # BEFORE the RTH cutoff (matches ``index > decision_ts_et & index < rth_cutoff``).
    forward = [
        bar
        for bar in day_bars
        if bar.close_ts_utc > decision_ts_utc and bar.close_ts_utc < rth_cutoff_et
    ]
    if not forward:
        return HonestEntryDrop(
            reason="no_forward",
            decision_ts_utc=decision_ts_utc,
            entry_price=float(entry_price),
        )

    # (e) the EXISTING pure forward-scan — body unchanged.
    return resolve_outcome(
        entry_points=float(entry_price),
        direction=touch.direction,
        forward_bars=forward,
        tick_size=tick_size,
        tp_points=tp_points,
        sl_points=sl_points,
        trap_mfe_min=trap_mfe_min,
    )
