"""Tests for the honest decision-time orchestration (``decisions/honest_entry.py``).

``resolve_honest_outcome`` is the single relocated orchestration (Phase 8.1): it
computes decision_ts = touch close + offset, drops at/after flatten or the RTH
cutoff, looks up the injected decision-time entry price, slices the post-decision
forward window, and calls the pure ``resolve_outcome``. These tests are PURE and
SYNTHETIC — no store, no pandas, fixed tz-aware UTC timestamps — and cover the
traded path plus all four drop arms (flatten / cutoff / no_fill / no_forward).

The cutoff arm is exercised in isolation by passing a ``flatten_time`` LATER than
``rth_end`` (in production flatten 16:40 < cutoff 17:00, so flatten always fires
first); this is a legitimate pure unit check of the cutoff comparison.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from strategy_core.constants import (
    FLATTEN_TIME,
    RTH_END,
    TRADEABLE_REVERSAL,
)
from strategy_core.decisions.honest_entry import (
    HonestEntryDrop,
    resolve_honest_outcome,
)
from strategy_core.decisions.outcomes import OutcomeResult
from strategy_core.types import Bar, CloseReason, Direction, Touch

TICK_SIZE = 0.25
TP_POINTS = 15.0
SL_POINTS = 30.0
TRAP_MFE_MIN = 5.0

_ET = ZoneInfo("US/Eastern")
#: A fixed summer trading day (EDT = UTC-4, never DST-ambiguous at these times).
_TRADING_DAY = date(2025, 7, 15)


def _et(hh: int, mm: int, ss: int = 0) -> datetime:
    """A UTC instant for ``hh:mm:ss`` ET on the fixed trading day."""
    return datetime(2025, 7, 15, hh, mm, ss, tzinfo=_ET).astimezone(timezone.utc)


def _touch(close_utc: datetime, direction: Direction = Direction.LONG) -> Touch:
    return Touch(
        bar_ts_utc=close_utc,
        representative_price=100.0,
        direction=direction,
        level_type="PDH",
        trading_day=_TRADING_DAY,
    )


def _bar(close_utc: datetime, *, high_pts: float, low_pts: float, index: int = 0) -> Bar:
    return Bar(
        timeframe_ticks=0,
        trading_day=_TRADING_DAY,
        bar_index=index,
        bar_id=f"bar-{index}",
        open_ts_utc=close_utc,
        close_ts_utc=close_utc,
        open_ticks=round(low_pts / TICK_SIZE),
        high_ticks=round(high_pts / TICK_SIZE),
        low_ticks=round(low_pts / TICK_SIZE),
        close_ticks=round(low_pts / TICK_SIZE),
        volume=1,
        trade_count=1,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
    )


def _resolve(touch, day_bars, *, price, **over):
    """Call the orchestration with the standard label policy; ``price`` is the
    injected fill (a constant accessor) or ``None`` for the no-fill arm."""
    return resolve_honest_outcome(
        touch,
        day_bars,
        (lambda _ts: price),
        tick_size=TICK_SIZE,
        tp_points=TP_POINTS,
        sl_points=SL_POINTS,
        trap_mfe_min=TRAP_MFE_MIN,
        **over,
    )


# ── traded path ──────────────────────────────────────────────────────────────
def test_traded_long_resolves_tradeable_reversal():
    """A 10:00 ET LONG touch: decision at 10:05 ET, entry 100.0, a forward bar that
    runs +TP (high 116) before any stop -> tradeable_reversal, MFE 16, MAE 0."""
    touch_close = _et(10, 0)
    decision = touch_close + timedelta(minutes=5)  # 10:05 ET
    # one bar AFTER the decision, inside RTH: high 116 (MFE 16 >= tp), low 100 (MAE 0)
    fwd = _bar(decision + timedelta(minutes=1), high_pts=116.0, low_pts=100.0)
    # a pre-decision bar (must be EXCLUDED by the strict > decision bound)
    pre = _bar(touch_close, high_pts=130.0, low_pts=70.0, index=99)

    out = _resolve(_touch(touch_close), [pre, fwd], price=100.0)

    assert isinstance(out, OutcomeResult)
    assert out.label == TRADEABLE_REVERSAL
    assert out.max_mfe == 16.0
    assert out.max_mae == 0.0


# ── drop arms ────────────────────────────────────────────────────────────────
def test_flatten_drop():
    """A touch at 16:36 ET -> decision 16:41 ET is at/after FLATTEN_TIME (16:40) ->
    flatten drop, regardless of any fill/forward."""
    touch_close = _et(16, 36)
    fwd = _bar(touch_close + timedelta(minutes=6), high_pts=200.0, low_pts=50.0)

    out = _resolve(_touch(touch_close), [fwd], price=100.0)

    assert isinstance(out, HonestEntryDrop)
    assert out.reason == "flatten"
    assert out.decision_ts_utc == touch_close + timedelta(minutes=5)


def test_cutoff_drop():
    """A touch whose decision is at/after the forward cutoff (17:00) but BEFORE a
    (synthetically) later flatten -> cutoff drop. Pass flatten_time=23:00 so the
    flatten arm does not pre-empt the cutoff comparison."""
    touch_close = _et(16, 56)  # decision 17:01 ET >= 17:00 cutoff
    fwd = _bar(touch_close + timedelta(minutes=10), high_pts=200.0, low_pts=50.0)

    out = _resolve(_touch(touch_close), [fwd], price=100.0, flatten_time=time(23, 0))

    assert isinstance(out, HonestEntryDrop)
    assert out.reason == "cutoff"


def test_no_fill_drop():
    """The injected trade_price_at returns None at the decision instant -> no_fill."""
    touch_close = _et(10, 0)
    fwd = _bar(touch_close + timedelta(minutes=6), high_pts=200.0, low_pts=50.0)

    out = _resolve(_touch(touch_close), [fwd], price=None)

    assert isinstance(out, HonestEntryDrop)
    assert out.reason == "no_fill"
    assert out.entry_price is None


def test_no_forward_drop():
    """A fill exists but NO bar closes in (decision, rth_cutoff) -> no_forward; the
    resolved fill is carried on the drop."""
    touch_close = _et(10, 0)
    # the only bar closes BEFORE the decision (excluded by the strict > bound)
    pre = _bar(touch_close, high_pts=200.0, low_pts=50.0)

    out = _resolve(_touch(touch_close), [pre], price=123.5)

    assert isinstance(out, HonestEntryDrop)
    assert out.reason == "no_forward"
    assert out.entry_price == 123.5


# ── boundary: a decision EXACTLY at flatten is dropped (non-strict >=) ────────
def test_flatten_boundary_is_non_strict():
    """decision_ts exactly at FLATTEN_TIME (16:40 ET) drops (``t >= flatten``)."""
    touch_close = _et(16, 35)  # decision exactly 16:40 ET
    fwd = _bar(touch_close + timedelta(minutes=6), high_pts=200.0, low_pts=50.0)

    out = _resolve(_touch(touch_close), [fwd], price=100.0)

    assert isinstance(out, HonestEntryDrop)
    assert out.reason == "flatten"


# ── W1 P2a: flatten is trading-day anchored, not a bare wall-clock compare ────
def test_evening_touch_of_next_trading_day_is_not_flattened():
    """A 20:00 ET touch belongs to the NEXT trading day (rolls at 18:00 ET); its
    decision must NOT drop at the prior session's flatten and resolves against its
    OWN trading day's cutoff (~21h away)."""
    touch_close = datetime(2025, 7, 14, 20, 0, tzinfo=_ET).astimezone(timezone.utc)
    fwd = _bar(touch_close + timedelta(minutes=6), high_pts=116.0, low_pts=100.0)

    out = _resolve(_touch(touch_close), [fwd], price=100.0)

    assert isinstance(out, OutcomeResult)
    assert out.label == TRADEABLE_REVERSAL


def test_evening_decision_still_drops_at_its_own_days_flatten():
    """The same-trading-day 16:40 anchor still applies: a decision landing at/after
    16:40 ET ON the touch's trading day drops as flatten."""
    touch_close = _et(16, 36)  # decision 16:41 ET on 2025-07-15 >= 16:40 that day
    fwd = _bar(touch_close + timedelta(minutes=6), high_pts=200.0, low_pts=50.0)

    out = _resolve(_touch(touch_close), [fwd], price=100.0)

    assert isinstance(out, HonestEntryDrop)
    assert out.reason == "flatten"


# ── defaults are single-sourced from the engine constants ────────────────────
def test_defaults_pull_from_constants():
    """With no override, a touch right before the flatten survives; one at the
    flatten drops — proving the default flatten_time is the engine constant."""
    just_before = _et(16, 34, 59)  # decision 16:39:59 < 16:40 -> survives the flatten
    fwd = _bar(just_before + timedelta(minutes=6), high_pts=116.0, low_pts=100.0)
    out = _resolve(_touch(just_before), [fwd], price=100.0)
    assert isinstance(out, OutcomeResult)
    assert FLATTEN_TIME == time(16, 40)
    assert RTH_END == time(17, 0)
