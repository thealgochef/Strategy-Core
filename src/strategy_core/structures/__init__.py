"""Market-structure vocabulary over :class:`~strategy_core.types.Bar` sequences.

Strategy-agnostic primitives (fair-value gaps, swing points, liquidity sweeps)
that sit beside ``candles/`` (bars from trades) and ``decisions/`` (the touch /
outcome kernel). Modules here are stdlib-only, integer-tick, and deterministic:
streaming shapes ship with batch twins locked together by parity tests, exactly
like the candle builders.

Import from the submodules directly (``strategy_core.structures.fvg``); this
package ``__init__`` deliberately imports nothing.
"""
