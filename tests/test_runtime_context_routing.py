"""Exact BarSpec label/kind/size routing guards."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from strategy_core.constants import RESEARCH_SESSION_SCHEME
from strategy_core.runtime.context import RuntimePlatformContext
from strategy_core.strategies.protocols import BarSpec
from strategy_core.types import Bar, BarKind, CloseReason


def _bar(seconds: int, index: int) -> Bar:
    ts = datetime(2026, 1, 5, 23, tzinfo=UTC)
    return Bar(
        timeframe_ticks=seconds,
        trading_day=date(2026, 1, 6),
        bar_index=index,
        bar_id=f"{seconds}s:2026-01-06:{index}",
        open_ts_utc=ts,
        close_ts_utc=ts,
        open_ticks=100,
        high_ticks=101,
        low_ticks=99,
        close_ticks=100,
        volume=1,
        trade_count=1,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
        kind=BarKind.TIME,
    )


def _context(specs, bars):
    return RuntimePlatformContext(
        tick_size=0.25,
        point_value=20.0,
        bar_specs=specs,
        get_current_bars=lambda: bars,
        get_closed_bars=lambda: bars,
        get_scheme=lambda: RESEARCH_SESSION_SCHEME,
    )


def test_1m_and_1h_labels_resolve_to_distinct_exact_specs() -> None:
    minute = _bar(60, 1)
    hour = _bar(3600, 2)
    context = _context(
        (
            BarSpec(BarKind.TIME, 60, "1m"),
            BarSpec(BarKind.TIME, 3600, "1H"),
        ),
        (minute, hour),
    )
    assert context.current_bar("1m") is minute
    assert context.current_bar("1H") is hour
    assert context.closed_bars("1m") == (minute,)
    assert context.closed_bars("1H") == (hour,)


def test_duplicate_empty_and_unknown_labels_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _context(
            (
                BarSpec(BarKind.TIME, 60, "same"),
                BarSpec(BarKind.TIME, 3600, "same"),
            ),
            (),
        )
    with pytest.raises(ValueError, match="non-empty"):
        _context((BarSpec(BarKind.TIME, 60, ""),), ())
    context = _context((BarSpec(BarKind.TIME, 60, "1m"),), ())
    with pytest.raises(KeyError, match="unknown"):
        context.current_bar("60m")
