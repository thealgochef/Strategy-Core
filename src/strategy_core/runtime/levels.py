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
    """Maintain PDH/PDL and session high/low levels under Strategy-Core v3 sessions.

    Defaults reproduce the historical surface byte-for-byte (asia/london ranges
    only, no prior-session levels) — the touch-serving path is untouched.
    Opt-in parameterization (9.9-lite, IFVG window):

    * ``session_range_names`` — which scheme sessions get intraday H/L tracking
      (e.g. ``("asia", "london", "ny")`` adds ``ny_high``/``ny_low``, available
      from the NY close per the existing session-close rule).
    * ``emit_prior_session_levels`` — sessions whose COMPLETED prior-day ranges
      are additionally emitted as ``prev_<session>_high/low``, available from
      the trading-day start (the PDH/PDL instant) — the intraday-usable form of
      a session liquidity pool. Banked organically at the day roll; the explicit
      :meth:`load_prior_session_range` seed stays authoritative (W1 P2b rule).
    """

    def __init__(
        self,
        *,
        scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
        tick_size: float = DEFAULT_TICK_SIZE,
        session_range_names: tuple[str, ...] = ("asia", "london"),
        emit_prior_session_levels: tuple[str, ...] = (),
    ) -> None:
        for name in session_range_names:
            if name not in scheme.sessions:
                raise ValueError(f"session_range_names entry {name!r} not in scheme sessions")
        for name in emit_prior_session_levels:
            if name not in session_range_names:
                raise ValueError(
                    f"emit_prior_session_levels entry {name!r} not tracked by "
                    f"session_range_names {session_range_names!r}"
                )
        self._scheme = scheme
        self._tick_size = tick_size
        self._session_range_names = session_range_names
        self._emit_prior_sessions = emit_prior_session_levels
        self._trading_day = None
        self._day_high: int | None = None
        self._day_low: int | None = None
        self._summaries: dict[object, _DaySummary] = {}
        self._session_summaries: dict[tuple[object, str], _DaySummary] = {}
        self._ranges = {name: _Range() for name in session_range_names}
        self._static_levels: tuple[Level, ...] = ()

    def reset(self) -> None:
        self._trading_day = None
        self._day_high = None
        self._day_low = None
        self._ranges = {name: _Range() for name in self._session_range_names}

    def set_static_levels(self, levels: tuple[Level, ...]) -> None:
        self._static_levels = levels

    def load_prior_day_summary(self, trading_day, *, high_ticks: int, low_ticks: int) -> None:
        if high_ticks < low_ticks:
            raise ValueError("high_ticks must be >= low_ticks")
        self._summaries[trading_day] = _DaySummary(high_ticks, low_ticks)

    def load_prior_session_range(
        self, trading_day, session: str, *, high_ticks: int, low_ticks: int
    ) -> None:
        """Seed a completed prior day's SESSION extremes (the per-day-replay twin
        of the organic day-roll banking; mirrors :meth:`load_prior_day_summary`)."""
        if high_ticks < low_ticks:
            raise ValueError("high_ticks must be >= low_ticks")
        if session not in self._session_range_names:
            raise ValueError(f"session {session!r} not tracked by this state")
        self._session_summaries[(trading_day, session)] = _DaySummary(high_ticks, low_ticks)

    def process_trade(self, trade: Trade) -> tuple[Level, ...]:
        info = classify_session(trade.event_ts_utc, self._scheme)
        if info.trading_day is None:
            return self.levels()
        if self._trading_day != info.trading_day:
            # W1 P2b: bank the completed day's extremes BEFORE resetting so pdh/pdl
            # emit organically on multi-day streams. An explicit load_prior_day_summary
            # for the same day stays authoritative (the external seed is never
            # overwritten by the organic roll; a later explicit load overwrites).
            if (
                self._trading_day is not None
                and self._day_high is not None
                and self._day_low is not None
                and self._trading_day not in self._summaries
            ):
                self._summaries[self._trading_day] = _DaySummary(self._day_high, self._day_low)
            if self._trading_day is not None:
                # Bank completed per-session ranges under the same seed-stays-
                # authoritative rule as the day summary.
                for name, rng in self._ranges.items():
                    key = (self._trading_day, name)
                    if rng.high_ticks is not None and rng.low_ticks is not None and key not in self._session_summaries:
                        self._session_summaries[key] = _DaySummary(rng.high_ticks, rng.low_ticks)
            self._trading_day = info.trading_day
            self._day_high = None
            self._day_low = None
            self._ranges = {name: _Range() for name in self._session_range_names}
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
        for session_name in self._session_range_names:
            rng = self._ranges[session_name]
            available_from = self._session_close_available(session_name)
            if rng.high_ticks is not None:
                levels.append(Level(f"{session_name}_high", rng.high_ticks * self._tick_size, Side.HIGH, available_from))
            if rng.low_ticks is not None:
                levels.append(Level(f"{session_name}_low", rng.low_ticks * self._tick_size, Side.LOW, available_from))
        for session_name in self._emit_prior_sessions:
            prior = max(
                (day for (day, name) in self._session_summaries if name == session_name and day < self._trading_day),
                default=None,
            )
            if prior is None:
                continue
            summary = self._session_summaries[(prior, session_name)]
            available_from = self._trading_day_start_available()
            levels.append(Level(f"prev_{session_name}_high", summary.high_ticks * self._tick_size, Side.HIGH, available_from))
            levels.append(Level(f"prev_{session_name}_low", summary.low_ticks * self._tick_size, Side.LOW, available_from))
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
