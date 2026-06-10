"""Neutral Strategy-Core streaming runtime state."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from strategy_core.candles.streaming import CandleEngine
from strategy_core.constants import DEFAULT_TICK_SIZE, RESEARCH_SESSION_SCHEME
from strategy_core.data.events import DataQualityWarning, safe_text
from strategy_core.decisions.sessions import classify_session
from strategy_core.decisions.streaming import TRADE_PRICE_LOOKBACK_MINUTES
from strategy_core.runtime.context import RuntimePlatformContext, point_value_for_symbol
from strategy_core.types import Bar, Quote, SessionScheme, Touch, Trade, Zone, Level

if TYPE_CHECKING:
    # Annotation-only (under `from __future__ import annotations`): importing the plugin
    # protocol here would NOT execute at runtime, so a bare `import strategy_core` still
    # imports nothing from the strategies package and the registry stays empty until a
    # runtime is constructed — at which point the touch_reversal plugin is auto-attached
    # (B3: the plugin is the sole path; the `plugin` param is optional only to allow a
    # caller to inject a specific plugin, else the default is attached).
    from strategy_core.strategies.protocols import StrategyPlugin

__all__ = ["FeedStatus", "RuntimeSnapshot", "RuntimeUpdate", "StrategyRuntime"]


def _dt(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _bar(bar: Bar) -> dict[str, Any]:
    return {
        "timeframe_ticks": bar.timeframe_ticks,
        "trading_day": bar.trading_day.isoformat(),
        "bar_index": bar.bar_index,
        "bar_id": bar.bar_id,
        "open_ts_utc": bar.open_ts_utc.isoformat(),
        "close_ts_utc": bar.close_ts_utc.isoformat(),
        "open_ticks": bar.open_ticks,
        "high_ticks": bar.high_ticks,
        "low_ticks": bar.low_ticks,
        "close_ticks": bar.close_ticks,
        "volume": bar.volume,
        "trade_count": bar.trade_count,
        "is_complete": bar.is_complete,
        "is_partial": bar.is_partial,
        "close_reason": None if bar.close_reason is None else bar.close_reason.value,
    }


def _level(level: Level) -> dict[str, Any]:
    return {
        "name": level.name,
        "price": level.price,
        "side": level.side.value,
        "available_from": _dt(level.available_from),
    }


def _zone(zone: Zone) -> dict[str, Any]:
    return {
        "representative_price": zone.representative_price,
        "names": list(zone.names),
        "side": zone.side.value,
        "touched": zone.touched,
        "available_from": _dt(zone.available_from),
    }


def _touch(touch: Touch) -> dict[str, Any]:
    return {
        "bar_ts_utc": touch.bar_ts_utc.isoformat(),
        "representative_price": touch.representative_price,
        "direction": touch.direction.value,
        "level_type": touch.level_type,
        "trading_day": touch.trading_day.isoformat(),
    }


def _quote(quote: Quote | None) -> dict[str, Any] | None:
    if quote is None:
        return None
    return {
        "event_ts_utc": quote.event_ts_utc.isoformat(),
        "bid_price_ticks": quote.bid_price_ticks,
        "ask_price_ticks": quote.ask_price_ticks,
        "bid_size": quote.bid_size,
        "ask_size": quote.ask_size,
    }


def _warning(warning: DataQualityWarning) -> dict[str, Any]:
    return warning.to_dict()


@dataclass(frozen=True, slots=True)
class FeedStatus:
    state: str
    mode: str
    requested_symbol: str | None = None
    schema: str | None = None
    last_event_ts_utc: datetime | None = None
    last_message: str = ""
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "mode": self.mode,
            "requested_symbol": self.requested_symbol,
            "schema": self.schema,
            "last_event_ts_utc": _dt(self.last_event_ts_utc),
            "last_message": safe_text(self.last_message) or "",
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RuntimeUpdate:
    feed_status: FeedStatus | None = None
    warnings: tuple[DataQualityWarning, ...] = ()
    current_bars: tuple[Bar, ...] = ()
    closed_bars: tuple[Bar, ...] = ()
    levels: tuple[Level, ...] = ()
    zones: tuple[Zone, ...] = ()
    touches: tuple[Touch, ...] = ()
    last_quote: Quote | None = None

    def has_deltas(self) -> bool:
        return any((self.feed_status is not None, self.warnings, self.current_bars, self.closed_bars, self.levels, self.zones, self.touches, self.last_quote is not None))

    def to_dict(self) -> dict[str, Any]:
        return {
            "feed_status": None if self.feed_status is None else self.feed_status.to_dict(),
            "warnings": [_warning(item) for item in self.warnings],
            "current_bars": [_bar(item) for item in self.current_bars],
            "closed_bars": [_bar(item) for item in self.closed_bars],
            "levels": [_level(item) for item in self.levels],
            "zones": [_zone(item) for item in self.zones],
            "touches": [_touch(item) for item in self.touches],
            "last_quote": _quote(self.last_quote),
        }


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    current_bars: tuple[Bar, ...]
    recent_closed_bars: tuple[Bar, ...]
    levels: tuple[Level, ...]
    zones: tuple[Zone, ...]
    touches: tuple[Touch, ...]
    warnings: tuple[DataQualityWarning, ...]
    feed_status: FeedStatus
    last_quote: Quote | None
    session: str | None
    trading_day: date | None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_bars": [_bar(item) for item in self.current_bars],
            "recent_closed_bars": [_bar(item) for item in self.recent_closed_bars],
            "levels": [_level(item) for item in self.levels],
            "zones": [_zone(item) for item in self.zones],
            "touches": [_touch(item) for item in self.touches],
            "warnings": [_warning(item) for item in self.warnings],
            "feed_status": self.feed_status.to_dict(),
            "last_quote": _quote(self.last_quote),
            "session": self.session,
            "trading_day": None if self.trading_day is None else self.trading_day.isoformat(),
            "metadata": dict(self.metadata),
        }


class StrategyRuntime:
    """Event-at-a-time Strategy-Core runtime for replay/live market data."""

    def __init__(
        self,
        *,
        timeframes: tuple[int, ...] = (147, 987, 2000),
        decision_timeframe: int | None = None,
        requested_symbol: str | None = None,
        scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
        tick_size: float = DEFAULT_TICK_SIZE,
        recent_closed_bar_limit: int = 500,
        warning_limit: int = 100,
        plugin: StrategyPlugin | None = None,
        strategy_section: Any | None = None,
    ) -> None:
        self.requested_symbol = requested_symbol
        self.tick_size = tick_size
        self.scheme = scheme
        # B3: the touch strategy runs ONLY through the plugin — the hardwired None path is
        # gone, so ``self._plugin`` must ALWAYS be present. A runtime constructed without an
        # explicit plugin auto-attaches the registered ``touch_reversal`` plugin (+ its
        # default section), per PLAN §7 B3 ("plugin defaults to the registered touch plugin").
        # The default section uses RESEARCH_SESSION_SCHEME; a non-default scheme MUST supply
        # its own plugin+section so the plugin's level state (the SOLE level fold since
        # S-B3a) cannot silently diverge from the scheme the runtime classifies sessions
        # and builds candles with (fail-loud rather than wrong).
        if plugin is None:
            if scheme != RESEARCH_SESSION_SCHEME:
                raise ValueError(
                    "StrategyRuntime auto-attaches the default touch_reversal plugin "
                    "(RESEARCH_SESSION_SCHEME); pass an explicit plugin + strategy_section "
                    "to run a non-default session scheme."
                )
            from strategy_core.runtime.wiring import touch_reversal_kwargs

            _defaults = touch_reversal_kwargs()
            plugin = _defaults["plugin"]
            if strategy_section is None:
                strategy_section = _defaults["strategy_section"]
        self._plugin = plugin
        self.candles = CandleEngine(timeframes, scheme=scheme)
        self.decision_timeframe = decision_timeframe or min(timeframes)
        self._recent_closed_bar_limit = recent_closed_bar_limit
        self._warning_limit = warning_limit
        self._recent_closed_bars: list[Bar] = []
        self._warnings: list[DataQualityWarning] = []
        self._last_quote: Quote | None = None
        self._last_event_ts_utc: datetime | None = None
        self._touches: list[Touch] = []
        self._metadata: dict[str, Any] = {}
        # D1a trade ring: (ts_utc, price_points) prints backing trade_price_at — the honest
        # decision-time fill query. Retention is 2x the query lookback so a query slightly
        # behind the feed clock still sees its FULL 30-minute window; the exact 30-minute
        # bound is enforced at query time, never by eviction.
        self._trade_ring: deque[tuple[datetime, float]] = deque()
        self._trade_ring_retention = timedelta(minutes=2 * TRADE_PRICE_LOOKBACK_MINUTES)
        self._feed_status = FeedStatus(state="disconnected", mode="idle", requested_symbol=requested_symbol, last_message="Market-data feed is not started.")
        # The platform context the plugin reads. Backed by live accessors so
        # closed_bars/current_bar/session_at reflect current runtime state across reset().
        self._ctx = RuntimePlatformContext(
            tick_size=tick_size,
            point_value=point_value_for_symbol(requested_symbol),
            get_candles=lambda: self.candles,
            get_closed_bars=lambda: self._recent_closed_bars,
            get_scheme=lambda: self.scheme,
            get_trade_price=self.trade_price_at,
        )
        # The plugin is mandatory now (auto-attached above when not supplied); configure it
        # from the default or supplied section.
        if strategy_section is not None:
            self._plugin.configure(strategy_section, self._ctx)

    def reset(self, *, requested_symbol: str | None = None) -> RuntimeUpdate:
        if requested_symbol is not None:
            self.requested_symbol = requested_symbol
        self.candles = CandleEngine(self.candles.timeframes, scheme=self.scheme)
        # S-B3a: the plugin owns the level state AND the first-touch dedup; its reset
        # clears both (the runtime keeps no level/dedup state of its own).
        self._plugin.reset()
        self._recent_closed_bars.clear()
        self._warnings.clear()
        self._touches.clear()
        self._trade_ring.clear()
        self._last_quote = None
        self._last_event_ts_utc = None
        self._metadata.clear()
        self._feed_status = FeedStatus(state="disconnected", mode="idle", requested_symbol=self.requested_symbol, last_message="runtime reset")
        return RuntimeUpdate(feed_status=self._feed_status)

    def set_static_levels(self, levels: tuple[Level, ...]) -> None:
        # S-B3a: written through to the plugin's level state — the sole level fold.
        self._plugin.set_static_levels(levels)

    def load_prior_day_summary(self, trading_day: date, *, high_ticks: int, low_ticks: int) -> None:
        # S-B3a: written through to the plugin's level state — the sole level fold.
        self._plugin.load_prior_day_summary(trading_day, high_ticks=high_ticks, low_ticks=low_ticks)

    def record_warning(self, warning: DataQualityWarning) -> RuntimeUpdate:
        self._warnings.append(warning)
        if len(self._warnings) > self._warning_limit:
            del self._warnings[: len(self._warnings) - self._warning_limit]
        self._feed_status = FeedStatus(state="degraded", mode=self._feed_status.mode, requested_symbol=self.requested_symbol, last_event_ts_utc=warning.event_ts_utc or self._last_event_ts_utc, last_message=warning.message)
        return RuntimeUpdate(feed_status=self._feed_status, warnings=(warning,))

    def process_event(self, event: Trade | Quote | DataQualityWarning) -> RuntimeUpdate:
        if isinstance(event, DataQualityWarning):
            return self.record_warning(event)
        if isinstance(event, Quote):
            return self._process_quote(event)
        if isinstance(event, Trade):
            return self._process_trade(event)
        raise TypeError(f"unsupported runtime event type: {type(event).__name__}")

    def snapshot(self) -> RuntimeSnapshot:
        candle_update = self.candles.snapshot_update(())
        session, trading_day = self._session_state()
        # S-B3a: levels and zones are read back from the plugin — the sole owner of the
        # level fold and the first-touch dedup that pre-marks the display zones.
        return RuntimeSnapshot(
            current_bars=candle_update.current,
            recent_closed_bars=tuple(self._recent_closed_bars),
            levels=self._plugin.current_levels(),
            zones=self._plugin.snapshot_zones(trading_day),
            touches=tuple(self._touches),
            warnings=tuple(self._warnings),
            feed_status=self._feed_status,
            last_quote=self._last_quote,
            session=session,
            trading_day=trading_day,
            metadata=MappingProxyType(dict(self._metadata)),
        )

    def _process_quote(self, quote: Quote) -> RuntimeUpdate:
        self._last_quote = quote
        self._last_event_ts_utc = quote.event_ts_utc
        self._feed_status = FeedStatus(state="replaying", mode="runtime", requested_symbol=self.requested_symbol, last_event_ts_utc=quote.event_ts_utc, last_message="quote processed")
        return RuntimeUpdate(feed_status=self._feed_status, last_quote=quote)

    def trade_price_at(self, ts_utc: datetime) -> float | None:
        """The realistic front-month trade-print price at (or just before) ``ts_utc``.

        The live analogue of the research reference query
        (``validation/decision_diff_harness.py:594-616``): the MOST RECENT print with
        ``ts <= ts_utc`` within a 30-minute bounded lookback, else ``None``. The
        reference's ``bid/ask > 0`` predicate is parquet row-validity; the live
        analogue is the ``price > 0`` feed gate applied at ring insertion.
        """
        floor = ts_utc - timedelta(minutes=TRADE_PRICE_LOOKBACK_MINUTES)
        for ts, price in reversed(self._trade_ring):
            if ts <= ts_utc:
                return price if ts >= floor else None
        return None

    def _process_trade(self, trade: Trade) -> RuntimeUpdate:
        self._last_event_ts_utc = trade.event_ts_utc
        # D1a: feed the trade ring backing trade_price_at (price > 0 = the live analogue
        # of the reference query's row-validity filter), evicting beyond retention.
        if trade.price_ticks > 0:
            self._trade_ring.append((trade.event_ts_utc, trade.price_ticks * self.tick_size))
            ring_floor = trade.event_ts_utc - self._trade_ring_retention
            while self._trade_ring and self._trade_ring[0][0] < ring_floor:
                self._trade_ring.popleft()
        candle_update = self.candles.process_trade(trade)
        if candle_update.completed:
            self._recent_closed_bars.extend(candle_update.completed)
            if len(self._recent_closed_bars) > self._recent_closed_bar_limit:
                del self._recent_closed_bars[: len(self._recent_closed_bars) - self._recent_closed_bar_limit]
        # S-B3a: the plugin owns the SOLE level fold (R1; the runtime's redundant
        # ``level_state`` copy is deleted) — on_event folds the trade and returns the
        # post-fold level set for RuntimeUpdate.levels.
        levels = self._plugin.on_event(trade, self._ctx)
        touches: list[Touch] = []
        for bar in candle_update.completed:
            if bar.timeframe_ticks != self.decision_timeframe:
                continue
            # The plugin owns the cross-bar first-touch dedup (S-B3a); its touches flow
            # back VERBATIM — no re-derivation, re-keying, or filtering here.
            step = self._plugin.on_bar_closed(bar, self._ctx)
            touches.extend(step.touches)
        if touches:
            self._touches.extend(touches)
        session, trading_day = self._session_state()
        self._feed_status = FeedStatus(state="replaying", mode="runtime", requested_symbol=self.requested_symbol, last_event_ts_utc=trade.event_ts_utc, last_message="trade processed")
        return RuntimeUpdate(
            feed_status=self._feed_status,
            current_bars=candle_update.current,
            closed_bars=candle_update.completed,
            levels=levels,
            zones=self._plugin.snapshot_zones(trading_day),
            touches=tuple(touches),
        )

    def _session_state(self) -> tuple[str | None, date | None]:
        if self._last_event_ts_utc is None:
            return None, None
        info = classify_session(self._last_event_ts_utc, self.scheme)
        return info.session, info.trading_day
