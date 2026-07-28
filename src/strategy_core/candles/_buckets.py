"""Shared trading-day anchoring for the TIME-bar builders (Phase F).

Both the streaming and batch time builders bucket a trade by

    bucket_index = floor((ts_utc - day_boundary_utc) / interval_seconds)

where ``day_boundary_utc`` is the ABSOLUTE UTC instant the trading day opened.
Single-sourced here so the two paths cannot drift on the anchor.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from strategy_core.types import SessionScheme

__all__ = ["trading_day_start_utc"]

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
