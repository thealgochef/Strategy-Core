"""Shared trading-day anchoring for the TIME-bar builders (Phase F).

Both the streaming and batch time builders bucket a trade by

    bucket_index = floor((ts_utc - day_boundary_utc) / interval_seconds)

where ``day_boundary_utc`` is the ABSOLUTE UTC instant the trading day opened.
Single-sourced here so the two paths cannot drift on the anchor.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from strategy_core.candles.exchange_calendar import (
    ExchangeMinuteSchedule,
    MinuteSlotStatus,
)
from strategy_core.types import SessionScheme

__all__ = [
    "HTF_ANCHOR_POLICY",
    "trading_day_start_utc",
    "logical_bucket_bounds",
    "eligible_minute_closes",
    "eligible_minute_close_count",
    "is_eligible_minute_close",
]

#: Q-40 remains open. This name pins the as-built semantics so changing the
#: anchor cannot masquerade as a parameter-only profile edit.
HTF_ANCHOR_POLICY = "trading_day_18et_elapsed_v1"

_UTC = ZoneInfo("UTC")


def trading_day_start_utc(trading_day: date, scheme: SessionScheme) -> datetime:
    """The UTC instant ``trading_day`` opens: ``scheme.trading_day_boundary``
    (18:00 for the research scheme) in the scheme timezone on the calendar day
    PRECEDING ``trading_day``.

    Anchoring buckets at this absolute instant — rather than at local wall-clock
    labels — is what makes 23- and 25-hour DST trading days bucket correctly:
    elapsed seconds since the anchor are true elapsed seconds, so the day simply
    contains fewer or more buckets. (Not DST-ambiguous itself: the 18:00 boundary
    always exists; US DST flips at 02:00.) Mirrors
    ``StrategyLevelState._trading_day_start_available`` (``runtime/levels.py``).
    """
    tz = ZoneInfo(scheme.timezone)
    local = datetime.combine(
        trading_day - timedelta(days=1), scheme.trading_day_boundary, tzinfo=tz
    )
    return local.astimezone(_UTC)


def logical_bucket_bounds(
    trading_day: date,
    bucket: int,
    interval_seconds: int,
    scheme: SessionScheme,
) -> tuple[datetime, datetime]:
    """Scheduled half-open ``[open, close)`` bounds for one elapsed-time bucket."""
    if bucket < 0:
        raise ValueError(f"bucket must be non-negative (got {bucket})")
    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds must be positive (got {interval_seconds})")
    logical_open = trading_day_start_utc(trading_day, scheme) + timedelta(
        seconds=bucket * interval_seconds
    )
    logical_close = logical_open + timedelta(seconds=interval_seconds)
    if scheme.closed_window is not None:
        tz = ZoneInfo(scheme.timezone)
        maintenance_open = datetime.combine(
            trading_day,
            scheme.closed_window[0],
            tzinfo=tz,
        ).astimezone(_UTC)
        if logical_open < maintenance_open < logical_close:
            logical_close = maintenance_open
    return logical_open, logical_close


def eligible_minute_closes(
    start_exclusive: datetime,
    end_inclusive: datetime,
    scheme: SessionScheme | ExchangeMinuteSchedule,
) -> tuple[datetime, ...]:
    """Scheduled eligible 1-minute closes in ``(start, end]``.

    The iterator uses absolute UTC minutes, matching elapsed-time bucketing across
    DST.  A minute whose half-open source bucket starts inside the configured
    maintenance window is excluded.  This is the shared source-gap clock used by
    displacement; it never invents bars for missing prints.
    """

    if isinstance(scheme, ExchangeMinuteSchedule):
        return scheme.eligible_closes(start_exclusive, end_inclusive)
    if end_inclusive < start_exclusive:
        raise ValueError("eligible-minute interval ends before it starts")
    if start_exclusive.tzinfo is None or end_inclusive.tzinfo is None:
        raise ValueError("eligible-minute bounds must be timezone-aware")
    minute = timedelta(minutes=1)
    close = start_exclusive + minute
    out: list[datetime] = []
    tz = ZoneInfo(scheme.timezone)
    while close <= end_inclusive:
        bucket_open_local = (close - minute).astimezone(tz).time().replace(tzinfo=None)
        excluded = False
        if scheme.closed_window is not None:
            start, end = scheme.closed_window
            excluded = (
                start <= bucket_open_local < end
                if start <= end
                else bucket_open_local >= start or bucket_open_local < end
            )
        if not excluded:
            out.append(close)
        close += minute
    return tuple(out)


def _closed_bucket_open(bucket_open_utc: datetime, scheme: SessionScheme) -> bool:
    if scheme.closed_window is None:
        return False
    local = bucket_open_utc.astimezone(ZoneInfo(scheme.timezone)).time().replace(tzinfo=None)
    start, end = scheme.closed_window
    return start <= local < end if start <= end else local >= start or local < end


def is_eligible_minute_close(
    start_exclusive: datetime,
    candidate_close: datetime,
    scheme: SessionScheme | ExchangeMinuteSchedule,
) -> bool:
    """Whether ``candidate_close`` is on the eligible 1m grid after ``start``.

    This is the constant-space membership counterpart to
    :func:`eligible_minute_closes`.  The grid is deliberately anchored at the
    supplied start instant, matching the historical tuple-producing helper even
    when that instant is not a wall-clock minute boundary.
    """

    if isinstance(scheme, ExchangeMinuteSchedule):
        if candidate_close <= start_exclusive:
            return False
        return scheme.slot(candidate_close).status is MinuteSlotStatus.ELIGIBLE
    if start_exclusive.tzinfo is None or candidate_close.tzinfo is None:
        raise ValueError("eligible-minute bounds must be timezone-aware")
    delta = candidate_close - start_exclusive
    minute = timedelta(minutes=1)
    if delta < minute:
        return False
    _steps, remainder = divmod(delta, minute)
    return remainder == timedelta(0) and not _closed_bucket_open(
        candidate_close - minute,
        scheme,
    )


def _ceil_minute_steps(delta: timedelta) -> int:
    steps, remainder = divmod(delta, timedelta(minutes=1))
    return steps + (remainder != timedelta(0))


def eligible_minute_close_count(
    start_exclusive: datetime,
    end_inclusive: datetime,
    scheme: SessionScheme | ExchangeMinuteSchedule,
) -> int:
    """Count eligible 1m closes in ``(start, end]`` without materializing them.

    With no maintenance window this is O(1).  With one, it visits local calendar
    days rather than elapsed minutes, preserving DST/maintenance semantics while
    keeping long displacement-window finalization bounded in practice.
    """

    if isinstance(scheme, ExchangeMinuteSchedule):
        return scheme.eligible_close_count(start_exclusive, end_inclusive)
    if end_inclusive < start_exclusive:
        raise ValueError("eligible-minute interval ends before it starts")
    if start_exclusive.tzinfo is None or end_inclusive.tzinfo is None:
        raise ValueError("eligible-minute bounds must be timezone-aware")
    minute = timedelta(minutes=1)
    total = int((end_inclusive - start_exclusive) // minute)
    if total <= 0 or scheme.closed_window is None:
        return total
    closed_start, closed_end = scheme.closed_window
    if closed_start == closed_end:
        return total

    tz = ZoneInfo(scheme.timezone)
    first_day = start_exclusive.astimezone(tz).date() - timedelta(days=1)
    last_day = end_inclusive.astimezone(tz).date() + timedelta(days=1)
    excluded = 0
    day = first_day
    while day <= last_day:
        local_start = datetime.combine(day, closed_start, tzinfo=tz)
        end_day = day if closed_start < closed_end else day + timedelta(days=1)
        local_end = datetime.combine(end_day, closed_end, tzinfo=tz)
        interval_start = local_start.astimezone(_UTC)
        interval_end = local_end.astimezone(_UTC)

        # Candidate source-bucket opens are start + j*1m for j in [0,total).
        lower = max(interval_start, start_exclusive)
        upper = min(interval_end, end_inclusive)
        if lower < upper:
            first_index = max(0, _ceil_minute_steps(lower - start_exclusive))
            end_index = min(total, _ceil_minute_steps(upper - start_exclusive))
            excluded += max(0, end_index - first_index)
        day += timedelta(days=1)
    return total - excluded
