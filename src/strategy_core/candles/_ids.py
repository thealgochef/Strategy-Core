"""Shared deterministic bar-id construction for both candle builders.

A bar id is the join key the rest of the stack uses to reconcile a streaming
bar with its batch-built twin, so the two builders MUST format it identically.
Single-sourced here and imported by both ``candles/batch.py`` and
``candles/streaming.py``.

Ported verbatim from Trade-Lab's ``make_bar_id``:
``Trade-Lab/backend/src/trade_lab/domain/candles.py:195-196``.
"""

from __future__ import annotations

from datetime import date

__all__ = ["make_bar_id"]


def make_bar_id(timeframe_ticks: int, trading_day: date, bar_index: int) -> str:
    """Format the canonical bar id ``f"{tf}t:{trading_day}:{bar_index}"``.

    Exactly reproduces ``make_bar_id`` (``candles.py:195-196``): the timeframe in
    ticks followed by a ``t`` literal, the ISO trading day, and the per-day
    bar index, colon-separated. ``date.isoformat()`` is used for the day so the
    string is identical across the batch and streaming paths.
    """
    return f"{timeframe_ticks}t:{trading_day.isoformat()}:{bar_index}"
