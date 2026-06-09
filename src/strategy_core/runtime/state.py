"""Neutral Strategy-Core streaming runtime state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from strategy_core.candles.streaming import CandleEngine
from strategy_core.constants import DEFAULT_TICK_SIZE, RESEARCH_SESSION_SCHEME
from strategy_core.data.events import DataQualityWarning, safe_text
from strategy_core.decisions.dedup import ZoneKey, zone_key
from strategy_core.decisions.sessions import classify_session
from strategy_core.decisions.touch import detect_touches
from strategy_core.runtime.context import RuntimePlatformContext, point_value_for_symbol
from strategy_core.runtime.levels import StrategyLevelState
from strategy_core.types import Bar, Quote, SessionScheme, Touch, Trade, Zone, Level

if TYPE_CHECKING:
    # Annotation-only (under `from __future__ import annotations`): importing the plugin
    # protocol here would NOT execute at runtime, so `import strategy_core` still imports
    # nothing from the strategies package and the registry stays empty. The B1 `plugin`
    # param is dead in production (defaults to None) until B2 wires the routing.
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
        # B1: dead in production — `plugin` defaults to None, so _process_trade runs the
        # verbatim hardwired touch fold. B2 routes through plugin.on_bar_closed when set.
        self._plugin = plugin
        self.candles = CandleEngine(timeframes, scheme=scheme)
        self.decision_timeframe = decision_timeframe or min(timeframes)
        self.level_state = StrategyLevelState(scheme=scheme, tick_size=tick_size)
        self._recent_closed_bar_limit = recent_closed_bar_limit
        self._warning_limit = warning_limit
        self._recent_closed_bars: list[Bar] = []
        self._warnings: list[DataQualityWarning] = []
        self._last_quote: Quote | None = None
        self._last_event_ts_utc: datetime | None = None
        self._touches: list[Touch] = []
        self._touched_zone_keys: set[tuple[date, tuple[str, ...], float, str]] = set()
        self._metadata: dict[str, Any] = {}
        self._feed_status = FeedStatus(state="disconnected", mode="idle", requested_symbol=requested_symbol, last_message="Market-data feed is not started.")
        # B2: the platform context the plugin reads. INERT on the None path (never read
        # there). Backed by live accessors so closed_bars/current_bar/session_at reflect
        # current runtime state across reset(). configure() the plugin if one was supplied.
        self._ctx = RuntimePlatformContext(
            tick_size=tick_size,
            point_value=point_value_for_symbol(requested_symbol),
            get_candles=lambda: self.candles,
            get_closed_bars=lambda: self._recent_closed_bars,
            get_scheme=lambda: self.scheme,
        )
        if self._plugin is not None and strategy_section is not None:
            self._plugin.configure(strategy_section, self._ctx)

    def reset(self, *, requested_symbol: str | None = None) -> RuntimeUpdate:
        if requested_symbol is not None:
            self.requested_symbol = requested_symbol
        self.candles = CandleEngine(self.candles.timeframes, scheme=self.scheme)
        self.level_state.reset()
        self._recent_closed_bars.clear()
        self._warnings.clear()
        self._touches.clear()
        self._touched_zone_keys.clear()
        self._last_quote = None
        self._last_event_ts_utc = None
        self._metadata.clear()
        self._feed_status = FeedStatus(state="disconnected", mode="idle", requested_symbol=self.requested_symbol, last_message="runtime reset")
        return RuntimeUpdate(feed_status=self._feed_status)

    def set_static_levels(self, levels: tuple[Level, ...]) -> None:
        self.level_state.set_static_levels(levels)

    def load_prior_day_summary(self, trading_day: date, *, high_ticks: int, low_ticks: int) -> None:
        self.level_state.load_prior_day_summary(trading_day, high_ticks=high_ticks, low_ticks=low_ticks)

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
        zones = tuple(self._zones_for_snapshot(trading_day))
        return RuntimeSnapshot(
            current_bars=candle_update.current,
            recent_closed_bars=tuple(self._recent_closed_bars),
            levels=self.level_state.levels(),
            zones=zones,
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

    def _process_trade(self, trade: Trade) -> RuntimeUpdate:
        self._last_event_ts_utc = trade.event_ts_utc
        candle_update = self.candles.process_trade(trade)
        if candle_update.completed:
            self._recent_closed_bars.extend(candle_update.completed)
            if len(self._recent_closed_bars) > self._recent_closed_bar_limit:
                del self._recent_closed_bars[: len(self._recent_closed_bars) - self._recent_closed_bar_limit]
        levels = self.level_state.process_trade(trade)
        if self._plugin is not None:
            # Keep-both-folds (B2 PART 1, deviation 3b): the runtime level fold above stays
            # for RuntimeUpdate.levels + the snapshot; the plugin folds the SAME trade into
            # its OWN level state so its on_bar_closed detection sees identical levels (I4d).
            # B3 collapses this redundancy once the plugin owns the single fold.
            self._plugin.on_event(trade, self._ctx)
        touches: list[Touch] = []
        if self._plugin is None:
            for bar in candle_update.completed:
                if bar.timeframe_ticks != self.decision_timeframe:
                    continue
                zones = self._zones_for_detection(bar.trading_day)
                detected = detect_touches((bar,), zones, tick_size=self.tick_size, trading_day=bar.trading_day)
                for touch in detected:
                    self._touched_zone_keys.add(self._touch_zone_key_from_touch(touch, zones))
                touches.extend(detected)
        else:
            # Plugin path — mirrors the None branch one-for-one (same loop, same
            # decision-timeframe gate, same dedup write shape) with detected -> step.touches
            # and zones -> step.zones, so any divergence is obvious on review.
            for bar in candle_update.completed:
                if bar.timeframe_ticks != self.decision_timeframe:
                    continue
                step = self._plugin.on_bar_closed(bar, self._ctx, self._touched_zone_keys)
                for touch in step.touches:
                    self._touched_zone_keys.add(self._touch_zone_key_from_touch(touch, step.zones))
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
            zones=tuple(self._zones_for_snapshot(trading_day)),
            touches=tuple(touches),
        )

    def _zones_for_detection(self, trading_day: date) -> list[Zone]:
        # audit #3: build zones from ALL current levels -- do NOT pre-filter by
        # availability before build_zones. Pre-filtering diverged from canonical
        # merge-all / gate-each-zone-on-MAX semantics and from the snapshot path
        # (_zones_for_snapshot below). detect_touches (decisions/touch.py:93) already
        # gates each zone on ``bar.close_ts_utc < zone.available_from``, so the v3
        # look-ahead protection is preserved while zone composition now matches
        # canonical (and _zones_for_snapshot's unfiltered build).
        from strategy_core.decisions.zones import build_zones

        zones = build_zones(list(self.level_state.levels()))
        for zone in zones:
            if self._zone_key(trading_day, zone) in self._touched_zone_keys:
                zone.touched = True
        return zones

    def _zones_for_snapshot(self, trading_day: date | None) -> list[Zone]:
        zones = self.level_state.zones()
        if trading_day is None:
            return zones
        for zone in zones:
            if self._zone_key(trading_day, zone) in self._touched_zone_keys:
                zone.touched = True
        return zones

    @staticmethod
    def _zone_key(trading_day: date, zone: Zone) -> ZoneKey:
        # Delegate to the single-sourced key (I3) so the runtime and the plugin cannot
        # drift. The result is identical to the prior inline body.
        return zone_key(trading_day, zone)

    def _touch_zone_key_from_touch(self, touch: Touch, zones: list[Zone]) -> tuple[date, tuple[str, ...], float, str]:
        for zone in zones:
            if zone.representative_price == touch.representative_price and touch.level_type in zone.names:
                return self._zone_key(touch.trading_day, zone)
        return (touch.trading_day, (touch.level_type,), touch.representative_price, touch.direction.value)

    def _session_state(self) -> tuple[str | None, date | None]:
        if self._last_event_ts_utc is None:
            return None, None
        info = classify_session(self._last_event_ts_utc, self.scheme)
        return info.session, info.trading_day
