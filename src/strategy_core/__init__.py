"""strategy-core: the shared, versioned strategy engine.

This package is the single implementation that both Claude-Quant-Lab (research /
training, batch over parquet) and Trade-Lab (live + replay inference, streaming)
import, so a strategy configured in research executes identically in Trade-Lab.

Two version stamps live here:

* ``ENGINE_VERSION`` -- the *structural* version of the engine. A model binds to
  the engine version that produced its labels/features. Trade-Lab fail-closes on
  a model whose ``engine_version`` it cannot match. Bump this only when a
  genuinely new mechanism is added (a new touch rule, feature family, or label
  scheme) -- never for a parameter change, which is config-only.
* ``CONTRACT_VERSION`` -- the version of the ``strategy.json`` *format* (schema).

The contract carries ``engine_version`` so the binding is explicit per bundle.

Importing this package pulls only numpy + pydantic + stdlib; pandas is loaded
lazily and only when the batch candle builder is actually called.
"""

from __future__ import annotations

#: Structural version of the decision/candle engine. See module docstring.
ENGINE_VERSION = "strategy_core_engine_v1"

#: Version of the strategy.json contract *format* (Pydantic schema in contract/).
CONTRACT_VERSION = "trade_lab_contract_v1"

# ── Public API re-exports ───────────────────────────────────────────────────
from strategy_core.candles.batch import build_tick_bars_from_frame
from strategy_core.candles.streaming import CandleEngine, CandleUpdate
from strategy_core.candles._ids import make_bar_id
from strategy_core.constants import (
    RESEARCH_SESSION_SCHEME,
    TRADE_LAB_CT_SESSION_SCHEME,
)
from strategy_core.contract.loader import load_strategy_contract
from strategy_core.contract.schema import ContractError, StrategyContract
from strategy_core.decisions.features import (
    app_avg_trade_size,
    app_large_trade_vol_pct,
    app_max_spread,
    int_absorption_ratio,
    int_time_beyond_level,
    int_time_within_2pts,
)
from strategy_core.decisions.outcomes import (
    OutcomeResult,
    classify_mae_first,
    resolve_outcome,
)
from strategy_core.decisions.sessions import (
    classify_session,
    is_in_closed_window,
    trading_day_for,
)
from strategy_core.decisions.touch import detect_touches, is_touch
from strategy_core.decisions.zones import build_zones
from strategy_core.types import (
    Bar,
    CloseReason,
    Direction,
    Level,
    Quote,
    SessionInfo,
    SessionScheme,
    SessionWindow,
    Side,
    Touch,
    Trade,
    Zone,
)

__all__ = [
    "ENGINE_VERSION",
    "CONTRACT_VERSION",
    # types
    "Trade",
    "Quote",
    "Bar",
    "Level",
    "Zone",
    "Touch",
    "Side",
    "Direction",
    "CloseReason",
    "SessionScheme",
    "SessionWindow",
    "SessionInfo",
    # schemes
    "RESEARCH_SESSION_SCHEME",
    "TRADE_LAB_CT_SESSION_SCHEME",
    # candles
    "CandleEngine",
    "CandleUpdate",
    "build_tick_bars_from_frame",
    "make_bar_id",
    # decisions: zones / touch / sessions
    "build_zones",
    "is_touch",
    "detect_touches",
    "classify_session",
    "trading_day_for",
    "is_in_closed_window",
    # decisions: features
    "int_time_beyond_level",
    "int_time_within_2pts",
    "int_absorption_ratio",
    "app_large_trade_vol_pct",
    "app_avg_trade_size",
    "app_max_spread",
    # decisions: outcomes
    "classify_mae_first",
    "resolve_outcome",
    "OutcomeResult",
    # contract
    "StrategyContract",
    "load_strategy_contract",
    "ContractError",
]
