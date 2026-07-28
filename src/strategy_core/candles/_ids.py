"""Shared deterministic bar-id construction for both candle builders.

A bar id is the join key the rest of the stack uses to reconcile a streaming
bar with its batch-built twin, so the two builders MUST format it identically.
Single-sourced here and imported by both ``candles/batch.py`` and
``candles/streaming.py`` (tick) and ``candles/time_batch.py`` /
``candles/time_streaming.py`` (time).

Ported verbatim from Trade-Lab's ``make_bar_id``
(``Trade-Lab/backend/src/trade_lab/domain/candles.py:195-196``) for the TICK
kind; Phase F adds the TIME branch (``s`` unit suffix, interval seconds).
"""

from __future__ import annotations

from datetime import date

from strategy_core.types import BarKind

__all__ = ["make_bar_id"]


def make_bar_id(
    timeframe_ticks: int,
    trading_day: date,
    bar_index: int,
    kind: BarKind = BarKind.TICK,
) -> str:
    """Format the canonical bar id, branching on ``kind``.

    * ``TICK`` -> ``f"{tf}t:{trading_day}:{bar_index}"`` — byte-identical to the
      original (``candles.py:195-196``); ``kind`` defaults to TICK so every
      pre-Phase-F call site keeps producing the exact same ids.
    * ``TIME`` -> ``f"{tf}s:{trading_day}:{bar_index}"`` — the same shape with an
      ``s`` unit suffix; ``timeframe_ticks`` carries the interval in seconds
      (the ``BarSpec.size`` convention).

    ``date.isoformat()`` is used for the day so the string is identical across
    the batch and streaming paths.
    """
    unit = "s" if kind is BarKind.TIME else "t"
    return f"{timeframe_ticks}{unit}:{trading_day.isoformat()}:{bar_index}"
