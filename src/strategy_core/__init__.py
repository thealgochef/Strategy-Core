# ruff: noqa: E402
"""strategy-core: the shared, versioned strategy engine.

This package is the single implementation that both Claude-Quant-Lab (research /
training, batch over parquet) and Trade-Lab (live + replay inference, streaming)
import, so a strategy configured in research executes identically in Trade-Lab.

Two version stamps live here (decision 9.3 — the two-axis split is PLATFORM +
per-plugin ``strategy_version``, declared on each ``StrategyPlugin``):

* ``PLATFORM_VERSION`` -- the *structural* version of the shared platform (the
  engine axis, renamed at E1). A model binds to the platform version that
  produced its labels/features. A runtime MUST refuse to serve a model whose
  ``platform_version`` it cannot match. Bump this only when a genuinely new
  platform mechanism is added (a new bar kind, feature family, or label
  scheme) -- never for a parameter change, which is config-only, and never for
  a single strategy's semantics, which is that plugin's ``strategy_version``.
* ``CONTRACT_VERSION`` -- the version of the ``strategy.json`` *format* (schema).

The contract carries ``platform_version`` AND ``strategy_id``/``strategy_version``
so both axes of the binding are explicit per bundle.

Importing this package pulls only numpy + pydantic + stdlib; pandas is loaded
lazily and only when the batch candle builder is actually called.
"""

from __future__ import annotations

#: Structural version of the shared platform (decision/candle engine). See the
#: module docstring. RENAMED at E1 (ENGINE_VERSION -> PLATFORM_VERSION, value
#: "strategy_core_engine_v3" -> "strategy_core_platform_v1"); the v1/v2/v3 history
#: below is the ENGINE-axis lineage this platform axis supersedes.
#: v1 -> v2 (trade-bar cutover + honest-entry re-anchor): the canonical OUTCOME is
#: now anchored to the DECISION-TIME entry (touch + decision_offset = the realistic
#: price when the prediction can actually fire, matching the Trade-Lab executor),
#: NOT the level price at the touch instant; and the 3 interaction FEATURES re-source
#: to TRADE PRINTS (MID_PRICE_SOURCE="trade_price") on the 0.25 trade grid. Both are
#: decision-FORMULA changes, so the structural version bumps. The 3 classes, tp=15,
#: sl=30, trap_mfe_min=5, and the MAE-first ladder are UNCHANGED — only the entry
#: reference + the forward-window start move.
#: v2 -> v3 (session redefinition + ENFORCED level availability + full-prior-day
#: PDH/PDL + later flatten/cutoff): four coupled decision-MEANING changes.
#:   1. Sessions re-clocked to ET asia 19:00->02:45 (crosses midnight), london
#:      03:00->08:00, ny 09:00->17:00 (the prior ny_rth 09:30->16:15 window + name
#:      retired); the 18:00 ET trading-day boundary is UNCHANGED. The gaps
#:      18:00-19:00 / 02:45-03:00 / 08:00-09:00 ET are intentionally unsessioned.
#:   2. The contract's available_from guard is now ACTUALLY ENFORCED: a level can
#:      only be first-touched once its defining session has CLOSED (PDH/PDL from the
#:      trading-day start = prior 18:00 ET; asia H/L from 02:45 ET; london H/L from
#:      08:00 ET; a merged zone from the MAX of its constituents). This closes the
#:      look-ahead hole where a session high/low "self-touched" at its own forming
#:      bar before the session that defines it had closed.
#:      3. PDH/PDL move from the prior NY-RTH slice to the FULL prior TRADING day's
#:      high/low (the daily-candle extremes over the entire prior [18:00,18:00) ET
#:      window — the ICT standard).
#:   4. The flatten (entry/decision cutoff) moves to 16:40 ET and the forward-label
#:      cutoff to 17:00 ET (the new ny session end); the 5-minute decision offset is
#:      UNCHANGED. The 3 classes / tp / sl / trap_mfe_min / MAE-first ladder and the
#:      trade-price bars + trade-print features are all UNCHANGED from v2. A model
#:      built under v2 (e.g. NQ_20260602_232808) correctly fails the v3 loader.
PLATFORM_VERSION = "strategy_core_platform_v1"

#: Version of the strategy.json contract *format* (Pydantic schema in contract/).
#: v1 -> v2 (E1): engine_version field renamed platform_version + required
#: strategy_version added — a SHAPE break; v1 bundles fail closed at the loader's
#: first check and are migrated in place (QL scripts/migrate_contracts_v2.py).
#: v2 -> v3 (E3): the flat contract DECOMPOSES into the platform-consumed ENVELOPE
#: (flat keys) + ONE strategy-owned "section" subtree typed by the plugin's
#: SectionModel — session_scheme/level_scheme/touch_rule/feature_windows/
#: research_session_experiment move INTO the section, the interaction/approach
#: feature partition moves out of feature_set INTO the section, label_policy gains
#: barrier_mode, and the contract SessionScheme gains the optional closed_window
#: pair. A SHAPE break (#2): v2 bundles fail closed at the loader's first check and
#: are migrated in place (QL scripts/migrate_contracts_v3.py, same proven pattern).
CONTRACT_VERSION = "trade_lab_contract_v3"

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
from strategy_core.decisions.honest_entry import (
    HonestEntryDrop,
    resolve_honest_outcome,
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
from strategy_core.decisions.streaming import (
    OpenSetupView,
    StreamDrop,
    StreamingHonestResolver,
    StreamResolution,
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
    "PLATFORM_VERSION",
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
    # decisions: honest-entry orchestration
    "resolve_honest_outcome",
    "HonestEntryDrop",
    # decisions: streaming honest resolution (D1a)
    "StreamingHonestResolver",
    "StreamResolution",
    "StreamDrop",
    "OpenSetupView",
    # contract
    "StrategyContract",
    "load_strategy_contract",
    "ContractError",
]
