"""Shared candle layer: a vectorized batch builder and a streaming builder.

Both produce identical :class:`strategy_core.types.Bar` sequences from the same
trades under the same :class:`strategy_core.types.SessionScheme`; the parity test
(`tests/test_candle_parity.py`) locks them together. Promoted from Trade-Lab's
``build_tick_bars_from_frame`` (batch) and ``CandleEngine`` (streaming).
"""
