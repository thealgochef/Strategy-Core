"""Streaming Strategy-Core level state for display and touch-zone construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from strategy_core.constants import DEFAULT_TICK_SIZE, RESEARCH_SESSION_SCHEME
from strategy_core.decisions.sessions import classify_session
from strategy_core.decisions.zones import build_zones
from strategy_core.types import Level, SessionScheme, Side, Trade, Zone

__all__ = ["StrategyLevelState"]


@dataclass(slots=True)
class _Range:
    high_ticks: int | None = None
    low_ticks: int | None = None

    def update(self, price_ticks: int) -> bool:
        changed = False
        if self.high_ticks is None or price_ticks > self.high_ticks:
            self.high_ticks = price_ticks
            changed = True
        if self.low_ticks is None or price_ticks < self.low_ticks:
            self.low_ticks = price_ticks
            changed = True
        return changed


@dataclass(frozen=True, slots=True)
class _DaySummary:
    high_ticks: int
    low_ticks: int


class StrategyLevelState:
    """Maintain PDH/PDL and Asia/London high/low under Strategy-Core v3 sessions."""

    def __init__(self, *, scheme: SessionScheme = RESEARCH_SESSION_SCHEME, tick_size: float = DEFAULT_TICK_SIZE) -> None:
        self._scheme = scheme
        self._tick_size = tick_size
        self._trading_day = None
        self._day_high: int | None = None
        self._day_low: int | None = None
        self._summaries: dict[object, _DaySummary] = {}
        self._ranges = {"asia": _Range(), "london": _Range()}
        self._static_levels: tuple[Level, ...] = ()

    def reset(self) -> None:
        self._trading_day = None
        self._day_high = None
        self._day_low = None
        self._ranges = {"asia": _Range(), "london": _Range()}

    def set_static_levels(self, levels: tuple[Level, ...]) -> None:
        self._static_levels = levels

    def load_prior_day_summary(self, trading_day, *, high_ticks: int, low_ticks: int) -> None:
        if high_ticks < low_ticks:
            raise ValueError("high_ticks must be >= low_ticks")
        self._summaries[trading_day] = _DaySummary(high_ticks, low_ticks)

    def process_trade(self, trade: Trade) -> tuple[Level, ...]:
        info = classify_session(trade.event_ts_utc, self._scheme)
        if info.trading_day is None:
            return self.levels()
        if self._trading_day != info.trading_day:
            self._trading_day = info.trading_day
            self._day_high = None
            self._day_low = None
            self._ranges = {"asia": _Range(), "london": _Range()}
        self._day_high = trade.price_ticks if self._day_high is None else max(self._day_high, trade.price_ticks)
        self._day_low = trade.price_ticks if self._day_low is None else min(self._day_low, trade.price_ticks)
        if info.session in self._ranges:
            self._ranges[info.session].update(trade.price_ticks)
        return self.levels()

    def levels(self) -> tuple[Level, ...]:
        if self._trading_day is None:
            return self._static_levels
        levels: list[Level] = list(self._static_levels)
        prior = max((day for day in self._summaries if day < self._trading_day), default=None)
        if prior is not None:
            summary = self._summaries[prior]
            levels.append(Level("pdh", summary.high_ticks * self._tick_size, Side.HIGH, self._trading_day_start_available()))
            levels.append(Level("pdl", summary.low_ticks * self._tick_size, Side.LOW, self._trading_day_start_available()))
        for session_name in ("asia", "london"):
            rng = self._ranges[session_name]
            available_from = self._session_close_available(session_name)
            if rng.high_ticks is not None:
                levels.append(Level(f"{session_name}_high", rng.high_ticks * self._tick_size, Side.HIGH, available_from))
            if rng.low_ticks is not None:
                levels.append(Level(f"{session_name}_low", rng.low_ticks * self._tick_size, Side.LOW, available_from))
        return tuple(levels)

    def zones(self) -> list[Zone]:
        return build_zones(list(self.levels()))

    def _trading_day_start_available(self) -> datetime:
        tz = ZoneInfo(self._scheme.timezone)
        local_date = self._trading_day - timedelta(days=1)  # type: ignore[operator]
        local_dt = datetime.combine(local_date, self._scheme.trading_day_boundary, tzinfo=tz)
        return local_dt.astimezone(ZoneInfo("UTC"))

    def _session_close_available(self, session_name: str) -> datetime:
        tz = ZoneInfo(self._scheme.timezone)
        window = self._scheme.sessions[session_name]
        local_date = self._trading_day  # type: ignore[assignment]
        # Asia crosses midnight and closes on the trading-day date; London also closes on it.
        local_dt = datetime.combine(local_date, window.end, tzinfo=tz)  # type: ignore[arg-type]
        return local_dt.astimezone(ZoneInfo("UTC"))
