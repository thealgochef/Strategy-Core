"""Optional Databento live source boundary, fake-testable without the SDK."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from strategy_core.constants import DEFAULT_TICK_SIZE
from strategy_core.data.events import DataQualityCode, DataQualityWarning, safe_text
from strategy_core.types import Quote, Trade

__all__ = ["DatabentoLiveSource", "normalize_provider_message"]

_TRADE_SCHEMAS = {"trade", "trades"}
_QUOTE_SCHEMAS = {"mbp-1", "cmbp-1", "bbo", "tbbo", "cbbo"}
_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=UTC)  # audit #2: base for integer-µs timestamp arithmetic


def normalize_provider_message(message: Any, *, requested_symbol: str, schema: str) -> Trade | Quote:
    """Normalize a Databento-like fake/provider record to a neutral event."""

    _ = requested_symbol
    lowered = schema.lower()
    if lowered in _TRADE_SCHEMAS:
        size = _positive_int(_get(message, "size", "qty"), field="provider trade size")
        explicit_price_ticks = _get(message, "price_ticks")
        return Trade(
            event_ts_utc=_timestamp(_get(message, "ts_event", "event_ts_utc", "ts")),
            price_ticks=(
                _int(explicit_price_ticks, default=0)
                if explicit_price_ticks is not None
                else _price_ticks(_get(message, "price", "px"))
            ),
            size=size,
            side=None if _get(message, "side") is None else str(_get(message, "side")).upper(),
        )
    if lowered in _QUOTE_SCHEMAS:
        explicit_bid_ticks = _get(message, "bid_price_ticks")
        explicit_ask_ticks = _get(message, "ask_price_ticks")
        return Quote(
            event_ts_utc=_timestamp(_get(message, "ts_event", "event_ts_utc", "ts")),
            bid_price_ticks=(
                _int(explicit_bid_ticks, default=0)
                if explicit_bid_ticks is not None
                else _price_ticks(_get(message, "bid_px", "bid", "bid_px_00"))
            ),
            ask_price_ticks=(
                _int(explicit_ask_ticks, default=0)
                if explicit_ask_ticks is not None
                else _price_ticks(_get(message, "ask_px", "ask", "ask_px_00"))
            ),
            bid_size=_int(_get(message, "bid_size", "bid_sz", "bid_sz_00"), default=0),
            ask_size=_int(_get(message, "ask_size", "ask_sz", "ask_sz_00"), default=0),
        )
    raise ValueError("unsupported Databento provider schema")


class DatabentoLiveSource:
    """Small live-source queue with no import/connect side effects.

    Real SDK startup can be layered behind ``start`` later; tests and Trade-Lab use
    ``start_fake``/``provider_callback`` to validate normalization, queueing, and
    warning behavior without network access.
    """

    def __init__(self, *, api_key: str, requested_symbol: str, queue_maxsize: int = 10_000) -> None:
        if not api_key:
            raise ValueError("Databento API key is required")
        if queue_maxsize < 1:
            raise ValueError("queue_maxsize must be positive")
        self._api_key = api_key
        self.requested_symbol = requested_symbol
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=queue_maxsize)
        self._overflow_count = 0
        self._started = False

    def __repr__(self) -> str:
        return f"DatabentoLiveSource(requested_symbol={self.requested_symbol!r}, started={self._started!r})"

    async def start(self) -> None:
        """Start the real provider. Kept explicit; never called on import/app creation."""

        try:
            import databento  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("Databento SDK is not installed") from exc
        raise RuntimeError("real Databento live startup is not implemented in Strategy-Core tests")

    async def stop(self) -> None:
        self._started = False

    def start_fake(self) -> None:
        self._started = True

    def provider_callback(self, message: Any, *, schema: str) -> None:
        if not self._started:
            return
        try:
            self._queue.put_nowait((schema, message))
        except asyncio.QueueFull:
            self._overflow_count += 1

    async def collect_available(self) -> list[Trade | Quote | DataQualityWarning]:
        items: list[Trade | Quote | DataQualityWarning] = []
        if self._overflow_count:
            items.append(
                DataQualityWarning(
                    code=DataQualityCode.BACKPRESSURE_DROP,
                    message="Databento live queue overflow; newest provider messages were dropped",
                    metadata={"dropped": self._overflow_count},
                )
            )
            self._overflow_count = 0
        while not self._queue.empty():
            schema, message = await self._queue.get()
            try:
                items.append(normalize_provider_message(message, requested_symbol=self.requested_symbol, schema=schema))
            except Exception as exc:
                items.append(
                    DataQualityWarning(
                        code=DataQualityCode.PROVIDER_ERROR,
                        message=f"Databento provider message could not be normalized: {safe_text(str(exc))}",
                    )
                )
        return items


def _get(message: Any, *names: str) -> Any:
    if isinstance(message, Mapping):
        for name in names:
            if name in message and message[name] is not None:
                return message[name]
        return None
    for name in names:
        if hasattr(message, name):
            value = getattr(message, name)
            if value is not None:
                return value
    return None


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("provider timestamp must be timezone-aware")
        return value.astimezone(UTC)
    if isinstance(value, int) and not isinstance(value, bool):
        # audit #2: use integer-microsecond arithmetic instead of the lossy
        # fromtimestamp(value / 1_000_000_000); value is ns since epoch and
        # datetime resolves to µs, so floor-divide ns->µs to avoid float
        # precision loss. Matches the parquet timestamp fix.
        return _EPOCH_UTC + timedelta(microseconds=value // 1000)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("provider timestamp must be timezone-aware")
        return parsed.astimezone(UTC)
    raise ValueError("provider timestamp is missing or invalid")


def _price_ticks(value: Any) -> int:
    try:
        ticks = Decimal(str(value)) / Decimal(str(DEFAULT_TICK_SIZE))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("provider price is invalid") from exc
    if ticks != ticks.to_integral_value():
        raise ValueError("provider price is off tick grid")
    return int(ticks)


def _positive_int(value: Any, *, field: str) -> int:
    parsed = _int(value, default=0)
    if parsed <= 0:
        raise ValueError(f"{field} is missing or invalid")
    return parsed


def _int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("provider integer field is invalid")
    return int(value)
