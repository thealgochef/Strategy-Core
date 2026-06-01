"""Single source of truth for every strategy magic value.

The whole point of this module: the numbers that used to be *restated* in the
contract emitter (``strategy_contract.py``) -- ``3.0`` zone proximity, ``2.0``
within-band, ``10`` large-trade, the session windows, the trading-day boundary --
live here exactly once. Both the engine (which *computes* with them) and the
contract emitter (which *describes* them) read them from here, so they can never
drift apart again.

Provenance of each value is cited to the canonical research training path:
``dashboard_utility_builder.py``, ``dashboard_utility_labeling.py``,
``ml/config.py``, and ``experiment/features.py`` in Claude-Quant-Lab.
"""

from __future__ import annotations

from datetime import time

from strategy_core.types import Direction, SessionScheme, SessionWindow, Side

# ── Instrument ──────────────────────────────────────────────────────────────
DEFAULT_TICK_SIZE = 0.25
#: USD per 1.0 point. NQ=20, ES=50. (strategy_contract.py:62)
POINT_VALUE: dict[str, float] = {"NQ": 20.0, "ES": 50.0}

# ── Touch / zones ───────────────────────────────────────────────────────────
#: Merge levels whose prices are within this many points into one zone.
#: (dashboard_utility_builder.py:54  _ZONE_PROXIMITY = 3.0)
ZONE_PROXIMITY_PTS = 3.0
#: Side -> trade direction. low touch -> long, high touch -> short.
#: (dashboard_utility_builder.py:431)
DIRECTION_FROM_SIDE: dict[Side, Direction] = {
    Side.LOW: Direction.LONG,
    Side.HIGH: Direction.SHORT,
}

# ── Feature windows / thresholds ────────────────────────────────────────────
#: Half-width (points) of the within-band dwell feature ``int_time_within_2pts``.
#: Deliberately NOT level_proximity_pts; the research feature pins it at 2.0.
#: (dashboard_utility_builder.py:502  abs(m - rep_price) <= 2.0)
WITHIN_BAND_PTS = 2.0
#: +/- band (points) for absorption-ratio "at level" volume.
#: (DashboardUtilityConfig.level_proximity_pts default, ml/config.py)
LEVEL_PROXIMITY_PTS = 0.50
#: A trade with size >= this is "large". (experiment/features.py:44)
LARGE_TRADE_THRESHOLD = 10
#: Inter-event gaps outside [0, this] seconds are data gaps, not dwell, and are
#: skipped in the tempo loop. (dashboard_utility_builder.py:498  dt_sec > 600)
MAX_DWELL_GAP_SECONDS = 600.0

#: RESOLVED open decision (spec §7), ratified by the strategy owner: the shared
#: engine standardizes the interaction features on the TRADE PRINT price over trades.
#: This DIVERGES from the legacy training path, which actually used a TOP-OF-BOOK MID:
#: query_tick_feature_rows selects price = (bid_px_00 + ask_px_00) / 2.0 over book
#: events (tick_store.py:264,287), so the builder's `mid = ticks["price"]`
#: (dashboard_utility_builder.py:488) is a book mid, not a trade price — the spec's and
#: the earlier audit's "trade price" reading was a misread of that `mid` variable.
#: Because the deployed model encoded TOB-mid features, moving to trade_price REQUIRES
#: RETRAINING the model under this engine. The engine_version binding
#: (strategy_core_engine_v1) is what makes Trade-Lab fail-close on the old model.
MID_PRICE_SOURCE = "trade_price"

# ── Feature sets (ml/config.py LIVE_* lists) ────────────────────────────────
#: Always-on interaction features (the 3 canonical dashboard features).
INTERACTION_FEATURES: tuple[str, ...] = (
    "int_time_beyond_level",
    "int_time_within_2pts",
    "int_absorption_ratio",
)
#: Full live-computable approach feature menu (MBP-1 + trades only).
APPROACH_FEATURES: tuple[str, ...] = (
    "app_large_trade_vol_pct",
    "app_trade_count",
    "app_volume_acceleration",
    "app_avg_trade_size",
    "app_avg_tob_imbalance",
    "app_max_spread",
    "app_volatility_recent",
    "app_volatility_ratio",
)
#: The approach features the runtime currently implements as scalar functions
#: (the subset with formulas ported into decisions/features.py).
RUNTIME_APPROACH_FEATURES: tuple[str, ...] = (
    "app_large_trade_vol_pct",
    "app_avg_trade_size",
    "app_max_spread",
)

# ── Labels (dashboard_utility_labeling.py:27-38) ────────────────────────────
TRADEABLE_REVERSAL = "tradeable_reversal"
TRAP_REVERSAL = "trap_reversal"
AGGRESSIVE_BLOWTHROUGH = "aggressive_blowthrough"
NO_RESOLUTION = "no_resolution"

LABEL_ENCODING: dict[str, int] = {
    TRADEABLE_REVERSAL: 0,
    TRAP_REVERSAL: 1,
    AGGRESSIVE_BLOWTHROUGH: 2,
}
CLASS_NAMES: dict[int, str] = {v: k for k, v in LABEL_ENCODING.items()}

#: Label-policy defaults (DashboardUtilityConfig). These are config-driven at
#: train time; the values here are the documented defaults / the bundle's values
#: flow through the contract, not these literals.
DEFAULT_TP_POINTS = 15.0
DEFAULT_SL_POINTS = 30.0
DEFAULT_TRAP_MFE_MIN = 5.0
DEFAULT_INTERACTION_WINDOW_MINUTES = 5
DEFAULT_APPROACH_WINDOW_MINUTES = 90

# ── Sessions (ET) — canonical dashboard_utility scheme ──────────────────────
SESSION_TIMEZONE = "US/Eastern"
TRADING_DAY_BOUNDARY = time(18, 0)  # CME 6pm ET rollover
#: RTH close: forward-label cutoff and ny_rth end.
#: (dashboard_utility_labeling.py:40  RTH_END = time(16, 15))
RTH_END = time(16, 15)

#: The canonical ET session scheme the trained model's dataset was built under.
#: (dashboard_utility_builder.py:44-51, _slice_session:332-344)
RESEARCH_SESSION_SCHEME = SessionScheme(
    timezone=SESSION_TIMEZONE,
    trading_day_boundary=TRADING_DAY_BOUNDARY,
    sessions={
        "asia": SessionWindow(time(18, 0), time(1, 0), crosses_midnight=True),
        "london": SessionWindow(time(1, 0), time(8, 0)),
        "ny_rth": SessionWindow(time(9, 30), RTH_END),
    },
    closed_window=None,  # research drops nothing; bars span the full 18:00->18:00 ET day
)

#: NON-CANONICAL reference: Trade-Lab's current Chicago scheme, kept only so the
#: divergence is documented and testable. Trade-Lab must migrate OFF this onto
#: RESEARCH_SESSION_SCHEME (spec §7: sessions ET, not Chicago).
#: (Trade-Lab domain/sessions.py:35-52)
TRADE_LAB_CT_SESSION_SCHEME = SessionScheme(
    timezone="America/Chicago",
    trading_day_boundary=time(18, 0),
    sessions={
        "asia": SessionWindow(time(18, 0), time(2, 0), crosses_midnight=True),
        "london": SessionWindow(time(2, 0), time(8, 0)),
        "ny": SessionWindow(time(8, 0), time(16, 0)),
    },
    closed_window=(time(16, 0), time(18, 0)),
)

__all__ = [
    "DEFAULT_TICK_SIZE",
    "POINT_VALUE",
    "ZONE_PROXIMITY_PTS",
    "DIRECTION_FROM_SIDE",
    "WITHIN_BAND_PTS",
    "LEVEL_PROXIMITY_PTS",
    "LARGE_TRADE_THRESHOLD",
    "MAX_DWELL_GAP_SECONDS",
    "MID_PRICE_SOURCE",
    "INTERACTION_FEATURES",
    "APPROACH_FEATURES",
    "RUNTIME_APPROACH_FEATURES",
    "TRADEABLE_REVERSAL",
    "TRAP_REVERSAL",
    "AGGRESSIVE_BLOWTHROUGH",
    "NO_RESOLUTION",
    "LABEL_ENCODING",
    "CLASS_NAMES",
    "DEFAULT_TP_POINTS",
    "DEFAULT_SL_POINTS",
    "DEFAULT_TRAP_MFE_MIN",
    "DEFAULT_INTERACTION_WINDOW_MINUTES",
    "DEFAULT_APPROACH_WINDOW_MINUTES",
    "SESSION_TIMEZONE",
    "TRADING_DAY_BOUNDARY",
    "RTH_END",
    "RESEARCH_SESSION_SCHEME",
    "TRADE_LAB_CT_SESSION_SCHEME",
]
