"""Neutral value types shared by the engine.

These are deliberately minimal and dependency-free (stdlib only): the engine must
never import pandas, duckdb, or either repo's domain objects. Each repo adapts its
own representation (a DuckDB row, a Databento event, a runtime ``TradeEvent``) into
these plain dataclasses at the IO boundary.

Prices are carried as integer **ticks** (matching Trade-Lab's candle engine and the
exact-integer arithmetic that keeps bar aggregation lossless). Decision-layer
formulas compare in **points** (``ticks * tick_size``); the ``*_points`` helpers do
that conversion so callers never sprinkle ``tick_size`` math around.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum

__all__ = [
    "Side",
    "Direction",
    "CloseReason",
    "Trade",
    "Quote",
    "Bar",
    "Level",
    "Zone",
    "Touch",
    "SessionWindow",
    "SessionScheme",
    "SessionInfo",
]


class Side(StrEnum):
    """Which side of price a level sits on. ``StrEnum`` so ``Side.LOW == "LOW"``."""

    HIGH = "HIGH"
    LOW = "LOW"


class Direction(StrEnum):
    """Trade direction implied by the touched side (low -> long, high -> short)."""

    LONG = "LONG"
    SHORT = "SHORT"


class CloseReason(StrEnum):
    """Why a bar closed. Mirrors Trade-Lab ``CandleCloseReason`` exactly."""

    COMPLETE = "complete"
    END_OF_DAY = "end_of_day"


@dataclass(frozen=True, slots=True)
class Trade:
    """A single print. ``price_ticks`` is the trade price in integer tick units."""

    event_ts_utc: datetime
    price_ticks: int
    size: int
    #: Aggressor side if known ('A' = buy/ask-lift, 'B' = sell/bid-hit). Unused by
    #: the three interaction features; carried for approach order-flow features.
    side: str | None = None

    def price_points(self, tick_size: float) -> float:
        return self.price_ticks * tick_size


@dataclass(frozen=True, slots=True)
class Quote:
    """Top-of-book (L0/L1) quote. Deeper book levels are intentionally absent."""

    event_ts_utc: datetime
    bid_price_ticks: int
    ask_price_ticks: int
    bid_size: int = 0
    ask_size: int = 0

    def mid_points(self, tick_size: float) -> float:
        return (self.bid_price_ticks + self.ask_price_ticks) / 2 * tick_size

    def spread_points(self, tick_size: float) -> float:
        return (self.ask_price_ticks - self.bid_price_ticks) * tick_size


@dataclass(frozen=True, slots=True)
class Bar:
    """An aggregated tick/time/volume bar. Prices in integer ticks.

    Field layout mirrors Trade-Lab's ``Candle`` so the promoted candle builders
    can emit this type unchanged.
    """

    timeframe_ticks: int
    trading_day: date
    bar_index: int
    bar_id: str
    open_ts_utc: datetime
    close_ts_utc: datetime
    open_ticks: int
    high_ticks: int
    low_ticks: int
    close_ticks: int
    volume: int
    trade_count: int
    is_complete: bool
    is_partial: bool
    close_reason: CloseReason | None = None

    def high_points(self, tick_size: float) -> float:
        return self.high_ticks * tick_size

    def low_points(self, tick_size: float) -> float:
        return self.low_ticks * tick_size

    def close_points(self, tick_size: float) -> float:
        return self.close_ticks * tick_size


@dataclass(frozen=True, slots=True)
class Level:
    """A single key level (PDH/PDL/session high/low) in points.

    ``available_from`` is the UTC instant at/after which this level may first be
    touched — its defining session's CLOSE (engine v3 look-ahead guard): PDH/PDL from
    the trading-day start (prior 18:00 ET); asia_high/low from the Asia close (02:45
    ET); london_high/low from the London close (08:00 ET). ``None`` means UNGATED
    (the legacy/book-mid regression path, which reproduces the pre-v3 no-guard
    behavior); the production research path always supplies it.
    """

    name: str
    price: float
    side: Side
    available_from: datetime | None = None


@dataclass(slots=True)
class Zone:
    """A merged cluster of nearby levels.

    ``representative_price`` is the mean of the constituent level prices (the
    canonical training rule). ``touched`` is mutable first-touch state and is the
    only mutable field on any engine type; first-touch scope tracking flips it.

    ``available_from`` is the UTC instant at/after which this zone may first be
    touched (engine v3 look-ahead guard) — the MAX of its constituent levels'
    ``available_from`` (a merged level isn't real until its latest-closing session has
    closed). ``None`` means UNGATED (all constituents ungated, i.e. the legacy/book-mid
    path). ``detect_touches`` skips a zone on any bar that closes before this instant.
    """

    representative_price: float
    names: tuple[str, ...]
    side: Side
    touched: bool = False
    available_from: datetime | None = None


@dataclass(frozen=True, slots=True)
class Touch:
    """A detected first-touch event: a bar's range straddled a zone's price."""

    bar_ts_utc: datetime
    representative_price: float
    direction: Direction
    level_type: str
    trading_day: date


@dataclass(frozen=True, slots=True)
class SessionWindow:
    """A named intraday session window in the scheme's local timezone.

    ``[start, end)`` half-open. ``crosses_midnight`` marks windows whose ``end`` is
    on the next calendar day (e.g. Asia 18:00 -> 01:00).
    """

    start: time
    end: time
    crosses_midnight: bool = False

    def contains(self, t: time) -> bool:
        if self.crosses_midnight:
            return t >= self.start or t < self.end
        return self.start <= t < self.end


@dataclass(frozen=True, slots=True)
class SessionScheme:
    """The full session/trading-day calendar the engine is parameterized by.

    Carries everything the contract's ``session_scheme`` describes, so a parameter
    change (different timezone, boundary, or windows) is config-only.

    * ``timezone`` -- IANA tz name (e.g. ``US/Eastern``).
    * ``trading_day_boundary`` -- at/after this local wall-clock time a trade rolls
      into the *next* calendar day's trading day (CME 18:00 rollover).
    * ``sessions`` -- named windows used by ``classify_session`` and level slicing.
    * ``closed_window`` -- optional ``[start, end)`` local window whose trades are
      dropped from bar building (e.g. a maintenance halt). ``None`` for the
      canonical research scheme, which drops nothing.
    """

    timezone: str
    trading_day_boundary: time
    sessions: Mapping[str, SessionWindow]
    closed_window: tuple[time, time] | None = None


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Result of classifying a timestamp: its trading day and session name.

    ``trading_day`` is ``None`` only when the timestamp falls in ``closed_window``
    (no trading day). ``session`` is the matched window name, or ``"none"`` for
    times inside a trading day but outside every named window (e.g. the v3 ET
    08:00-09:00 london->ny gap).
    """

    trading_day: date | None
    session: str
    local_ts: datetime
