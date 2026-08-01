"""IFVG v2 logical-time, anchor, and authoritative-session goldens."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from strategy_core.candles._buckets import (
    HTF_ANCHOR_POLICY,
    logical_bucket_bounds,
    trading_day_start_utc,
)
from strategy_core.candles.time_streaming import TimeBarEngine
from strategy_core.constants import IFVG_DOC_SESSION_SCHEME
from strategy_core.decisions.sessions import classify_session
from strategy_core.types import Trade

UTC = timezone.utc
ET = ZoneInfo("America/New_York")


def _utc(day: date, wall: time, *, fold: int = 0) -> datetime:
    return datetime.combine(day, wall, tzinfo=ET).replace(fold=fold).astimezone(UTC)


def test_anchor_policy_name_is_pinned() -> None:
    assert HTF_ANCHOR_POLICY == "trading_day_18et_elapsed_v1"


@pytest.mark.parametrize(
    ("trading_day", "elapsed_hours"),
    [
        (date(2026, 1, 13), 23),  # normal EST day
        (date(2026, 3, 8), 22),  # spring-forward day
        (date(2026, 11, 1), 24),  # fall-back day
    ],
)
def test_maintenance_open_caps_logical_day_and_shortens_last_bucket(
    trading_day: date,
    elapsed_hours: int,
) -> None:
    anchor = trading_day_start_utc(trading_day, IFVG_DOC_SESSION_SCHEME)
    maintenance = _utc(trading_day, time(17, 0))
    assert maintenance - anchor == timedelta(hours=elapsed_hours)

    bucket = (elapsed_hours - 1) // 4
    logical_open, logical_close = logical_bucket_bounds(
        trading_day,
        bucket,
        4 * 60 * 60,
        IFVG_DOC_SESSION_SCHEME,
    )
    assert logical_close == maintenance
    assert logical_open < logical_close
    assert logical_close - logical_open <= timedelta(hours=4)


def test_streaming_bar_preserves_print_times_and_emits_logical_bounds() -> None:
    trading_day = date(2026, 1, 13)
    first = _utc(date(2026, 1, 12), time(18, 0)) + timedelta(seconds=17)
    last = _utc(trading_day, time(16, 59, 59))
    engine = TimeBarEngine((14400,), scheme=IFVG_DOC_SESSION_SCHEME)
    bars = list(engine.process_trade(Trade(first, 100, 1)).completed)
    bars.extend(engine.process_trade(Trade(last, 110, 1)).completed)
    bars.extend(engine.finalize_trading_day())
    assert bars[0].open_ts_utc == first
    assert bars[-1].close_ts_utc == last
    assert bars[0].logical_open_ts_utc == _utc(
        date(2026, 1, 12), time(18, 0)
    )
    assert bars[-1].logical_close_ts_utc == _utc(trading_day, time(17, 0))


@pytest.mark.parametrize(
    ("local_day", "wall", "expected"),
    [
        (date(2026, 1, 12), time(16, 0), "asia"),
        (date(2026, 1, 13), time(1, 44, 59), "asia"),
        (date(2026, 1, 13), time(1, 45), "none"),
        (date(2026, 1, 13), time(2, 0), "london"),
        (date(2026, 1, 13), time(7, 0), "none"),
        (date(2026, 1, 13), time(8, 0), "ny"),
        (date(2026, 1, 13), time(14, 0), "none"),
        (date(2026, 1, 13), time(17, 30), "closed"),
    ],
)
def test_authoritative_sessions_are_end_exclusive(
    local_day: date,
    wall: time,
    expected: str,
) -> None:
    assert (
        classify_session(
            _utc(local_day, wall),
            IFVG_DOC_SESSION_SCHEME,
        ).session
        == expected
    )


def test_dst_fall_fold_both_0130_instants_are_asia() -> None:
    day = date(2026, 11, 1)
    first = _utc(day, time(1, 30), fold=0)
    second = _utc(day, time(1, 30), fold=1)
    assert second - first == timedelta(hours=1)
    assert classify_session(first, IFVG_DOC_SESSION_SCHEME).session == "asia"
    assert classify_session(second, IFVG_DOC_SESSION_SCHEME).session == "asia"
