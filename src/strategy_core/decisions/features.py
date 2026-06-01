"""Interaction and approach feature formulas for the shared engine.

The three *interaction* features iterate the post-touch TRADE stream and use the
**trade print price** as the price observable. This is a DELIBERATE strategy
standardization, ratified by the strategy owner (see ``constants.MID_PRICE_SOURCE``
== ``"trade_price"``), and it intentionally **diverges** from the legacy
Claude-Quant-Lab training path.

IMPORTANT — do not "fix" this back: the legacy training path did NOT use the trade
price for these features. ``query_tick_feature_rows`` selects
``price = (bid_px_00 + ask_px_00) / 2.0`` over *book* events
(``tick_store.py:264,287``), so the builder's ``mid = ticks["price"]``
(``dashboard_utility_builder.py:488``) is a TOP-OF-BOOK MID, not a trade print. The
``mid`` variable name is the tell. We are moving the strategy off that book-mid and
onto the trade price on purpose.

CONSEQUENCE (must be honored by the migration): a model is only valid under the
engine that produced its features. Any model served under this engine MUST be
(re)trained with the research path repointed onto this engine, so its interaction
features are trade-price. The currently-deployed model encodes TOB-mid features and
is NOT compatible — the contract's ``engine_version`` binding
(``strategy_core_engine_v1``) is exactly what makes Trade-Lab fail-close on that
mismatch instead of silently serving a model under the wrong feature definition.

What is preserved vs changed: the loop STRUCTURE (dwell tempo, within-band band,
absorption buckets, rounding, empty cases) is ported verbatim from the canonical
builder (``dashboard_utility_builder.py:446-538``); ONLY the price observable
changes from book-mid to trade-price, and the iterated row set changes from book
events to trades.

The three *approach* features are unchanged from the canonical DuckDB aggregates
(``alpha_lab/experiment/features.py``), which are already trade/L0-based:
large-trade share and average trade size over trades, max spread over the L0 book.
``LARGE_TRADE_THRESHOLD = 10`` (``experiment/features.py:44``); large/total
(``:114-118,282``); max spread (``:158``).

Rounding: interaction TIME features -> 4 dp, absorption -> 6 dp (builder:534-538);
approach features are unrounded. Empty cases: interaction -> ``0.0``, approach ->
``float("nan")``. The research ``< 5``-tick touch drop (builder:482) is the
ADAPTER's responsibility, not these pure formulas.

Imports limited to ``strategy_core.types``, ``strategy_core.constants``, and the
Python stdlib, per the engine's dependency rules.
"""

from __future__ import annotations

from collections.abc import Sequence

from strategy_core.constants import (
    LARGE_TRADE_THRESHOLD,
    LEVEL_PROXIMITY_PTS,
    MAX_DWELL_GAP_SECONDS,
    WITHIN_BAND_PTS,
)
from strategy_core.types import Direction, Quote, Trade

__all__ = [
    "int_time_beyond_level",
    "int_time_within_2pts",
    "int_absorption_ratio",
    "app_large_trade_vol_pct",
    "app_avg_trade_size",
    "app_max_spread",
]


def int_time_beyond_level(
    trades: Sequence[Trade],
    level_points: float,
    direction: Direction,
    tick_size: float,
    *,
    max_gap_seconds: float = MAX_DWELL_GAP_SECONDS,
) -> float:
    """Seconds the trade price spent on the adverse side of the level.

    Mirrors the tempo loop in ``dashboard_utility_builder.py:495-508``. Adverse is
    *below* the level for a LONG (price ran past support) and *above* it for a
    SHORT (price ran past resistance). The dwell for gap ``[j, j+1]`` is attributed
    to the price *at* trade ``j`` (the price held during that gap); gaps that are
    negative (out-of-order) or exceed ``max_gap_seconds`` are data gaps, not dwell,
    and are skipped (builder:498 ``dt_sec < 0 or dt_sec > 600``).

    Trades are sorted by ``event_ts_utc`` ascending with a stable sort, matching the
    builder's ``ORDER BY ts_event`` tick ordering. Result rounds to 4 decimals
    (builder:535). Returns ``0.0`` for an empty or single-trade window.
    """
    ordered = sorted(trades, key=lambda t: t.event_ts_utc)
    total = 0.0
    for j in range(len(ordered) - 1):
        dt = (ordered[j + 1].event_ts_utc - ordered[j].event_ts_utc).total_seconds()
        if dt < 0 or dt > max_gap_seconds:
            continue
        m = ordered[j].price_points(tick_size)
        if direction is Direction.LONG and m < level_points:
            total += dt
        elif direction is Direction.SHORT and m > level_points:
            total += dt
    return round(total, 4)


def int_time_within_2pts(
    trades: Sequence[Trade],
    level_points: float,
    tick_size: float,
    *,
    within_band_pts: float = WITHIN_BAND_PTS,
    max_gap_seconds: float = MAX_DWELL_GAP_SECONDS,
) -> float:
    """Seconds the trade price stayed within ``within_band_pts`` of the level.

    Same dwell loop as :func:`int_time_beyond_level` with the within-band predicate
    ``abs(m - level_points) <= within_band_pts`` (builder:502, the band hardcoded
    at 2.0 -- deliberately NOT ``level_proximity_pts``). Result rounds to 4 decimals
    (builder:536). Returns ``0.0`` for an empty or single-trade window.
    """
    ordered = sorted(trades, key=lambda t: t.event_ts_utc)
    total = 0.0
    for j in range(len(ordered) - 1):
        dt = (ordered[j + 1].event_ts_utc - ordered[j].event_ts_utc).total_seconds()
        if dt < 0 or dt > max_gap_seconds:
            continue
        m = ordered[j].price_points(tick_size)
        if abs(m - level_points) <= within_band_pts:
            total += dt
    return round(total, 4)


def int_absorption_ratio(
    trades: Sequence[Trade],
    level_points: float,
    direction: Direction,
    tick_size: float,
    *,
    proximity_pts: float = LEVEL_PROXIMITY_PTS,
) -> float:
    """``at_level_vol / (at_level_vol + through_vol)``, clamped to ``[0, 1]``.

    Iterates ALL trades in the window (no inter-event dt loop), per
    ``dashboard_utility_builder.py:519-530``. ``at_level`` is trade volume within
    ``+/- proximity_pts`` of the level (inclusive band, ``low <= p <= high``);
    ``through`` is adverse-direction volume strictly beyond the level (``p < level``
    for LONG, ``p > level`` for SHORT). Returns ``0.0`` when the combined volume is
    ``<= 0`` (builder:530 returns ``0.0`` on ``total == 0``). Result rounds to 6
    decimals (builder:537).
    """
    low = level_points - proximity_pts
    high = level_points + proximity_pts
    at_level_vol = 0.0
    through_vol = 0.0
    for trade in trades:
        p = trade.price_points(tick_size)
        s = float(trade.size)
        if low <= p <= high:
            at_level_vol += s
        elif (direction is Direction.LONG and p < level_points) or (
            direction is Direction.SHORT and p > level_points
        ):
            through_vol += s
    total = at_level_vol + through_vol
    if total <= 0:
        return 0.0
    ratio = at_level_vol / total
    return round(min(1.0, max(0.0, ratio)), 6)


def app_large_trade_vol_pct(
    trades: Sequence[Trade],
    *,
    large_trade_threshold: int = LARGE_TRADE_THRESHOLD,
) -> float:
    """Large-trade volume share: ``sum(size>=threshold) / sum(size)``.

    Reproduces the DuckDB derivation ``large_vol / total_vol``
    (``experiment/features.py:282``) where ``large_vol`` is
    ``SUM(size) FILTER (WHERE size >= 10)`` (features.py:117, threshold ``>=``) and
    ``total_vol`` is ``SUM(size)`` (features.py:114). Returns ``float("nan")`` when
    total volume is ``<= 0`` (the SQL guard ``total_vol > 0`` falling to NaN). No
    rounding.
    """
    total = 0.0
    large = 0.0
    for trade in trades:
        size = float(trade.size)
        total += size
        if trade.size >= large_trade_threshold:
            large += size
    if total <= 0:
        return float("nan")
    return large / total


def app_avg_trade_size(trades: Sequence[Trade]) -> float:
    """Mean trade size over the approach window.

    Reproduces ``AVG(CAST(size AS DOUBLE))`` over trades
    (``experiment/features.py:118``). Returns ``float("nan")`` on an empty window
    (DuckDB ``AVG`` over zero rows is NULL -> NaN). No rounding.
    """
    if not trades:
        return float("nan")
    return sum(trade.size for trade in trades) / len(trades)


def app_max_spread(quotes: Sequence[Quote], tick_size: float) -> float:
    """Widest ask-bid spread (points) over the approach window.

    Reproduces ``MAX(ask_px_00 - bid_px_00)``
    (``experiment/features.py:158``), converting the integer-tick spread to points.
    Returns ``float("nan")`` on an empty window (DuckDB ``MAX`` over zero rows is
    NULL -> NaN). No rounding.
    """
    if not quotes:
        return float("nan")
    return max(
        (q.ask_price_ticks - q.bid_price_ticks) * tick_size for q in quotes
    )
