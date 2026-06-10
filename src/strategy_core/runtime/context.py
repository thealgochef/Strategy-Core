"""RuntimePlatformContext — the live, runtime-backed PlatformContext (PLAN §2.2 / B2).

The seam (`StrategyPlugin`) reads market state through a `PlatformContext`. This is the
concrete implementation the streaming runtime hands to its plugin: it is backed by the
runtime's LIVE state via accessors (so `closed_bars`/`current_bar` reflect the latest
bars even after `reset()` swaps the candle engine, and `session_at` uses the live
scheme).

Surface (exactly PLAN §2.2 + the §9.10 quote accessor):
* `tick_size` / `point_value` — the runtime's real values. Only `tick_size` is on the
  B2 byte-identity hot path (it feeds the plugin's `detect_touches`).
* `closed_bars(label)` / `current_bar(label)` — correct against live runtime state
  (recent closed bars filtered to the label's timeframe; the in-progress bar from the
  candle engine snapshot).
* `session_at(ts)` — `classify_session` under the live scheme.
* `trade_price_at(ts)` — D1a: backed by the runtime's bounded trade ring (the honest
  decision-time fill query; `StrategyRuntime.trade_price_at`). The touch strategy still
  does not call it.
* `quotes_in_window(start, end)` — STILL a stub returning `()`: the §9.10 bounded quote
  buffer (retention window decision) is open — see the TODO.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import datetime

from strategy_core.constants import POINT_VALUE
from strategy_core.decisions.sessions import classify_session
from strategy_core.types import Bar, Quote, SessionScheme

__all__ = ["RuntimePlatformContext", "point_value_for_symbol"]


def point_value_for_symbol(symbol: str | None) -> float:
    """Best-effort USD-per-point for a requested symbol (e.g. ``"NQ.c.0"`` -> 20.0).

    Reads the canonical ``constants.POINT_VALUE`` keyed by the symbol's leading alpha
    root; ``0.0`` when unknown/absent. Not on the byte-identity hot path (the touch
    strategy does not consume ``point_value``).
    """
    if not symbol:
        return 0.0
    match = re.match(r"[A-Za-z]+", symbol)
    return POINT_VALUE.get(match.group(0), 0.0) if match else 0.0


def _label_to_timeframe(label: str) -> int | None:
    """Parse the leading integer from a BarSpec label (e.g. ``"147t"`` -> 147)."""
    match = re.match(r"\d+", label)
    return int(match.group(0)) if match else None


class RuntimePlatformContext:
    """Live PlatformContext backed by the runtime's candles / closed-bar ring / scheme."""

    def __init__(
        self,
        *,
        tick_size: float,
        point_value: float,
        get_candles: Callable[[], object],
        get_closed_bars: Callable[[], Sequence[Bar]],
        get_scheme: Callable[[], SessionScheme],
        get_trade_price: Callable[[datetime], float | None] | None = None,
    ) -> None:
        self.tick_size = tick_size
        self.point_value = point_value
        self._get_candles = get_candles
        self._get_closed_bars = get_closed_bars
        self._get_scheme = get_scheme
        self._get_trade_price = get_trade_price

    def closed_bars(self, label: str) -> Sequence[Bar]:
        tf = _label_to_timeframe(label)
        bars = self._get_closed_bars()
        if tf is None:
            return tuple(bars)
        return tuple(bar for bar in bars if bar.timeframe_ticks == tf)

    def current_bar(self, label: str) -> Bar | None:
        tf = _label_to_timeframe(label)
        # snapshot_update(()) is a pure read of the in-progress bars (one per timeframe).
        current = self._get_candles().snapshot_update(()).current
        for bar in current:
            if tf is None or bar.timeframe_ticks == tf:
                return bar
        return None

    def trade_price_at(self, ts_utc: datetime) -> float | None:
        # D1a: backed by the runtime's trade ring (StrategyRuntime.trade_price_at — the
        # most recent price>0 print at/before ts_utc within the 30-min bounded lookback).
        # The touch strategy does not call this; the streaming honest resolver's wiring
        # reads the same ring through the runtime accessor.
        if self._get_trade_price is None:
            return None
        return self._get_trade_price(ts_utc)

    def session_at(self, ts_utc: datetime) -> str | None:
        return classify_session(ts_utc, self._get_scheme()).session

    def quotes_in_window(
        self, start_ts_utc: datetime, end_ts_utc: datetime
    ) -> Sequence[Quote]:
        # TODO(§9.10): back this with a bounded quote buffer so app_max_spread has live
        # data when a quote-consuming plugin is wired. The touch strategy's runtime path
        # does not call this.
        return ()
