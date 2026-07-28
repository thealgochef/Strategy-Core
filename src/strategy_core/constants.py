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

from strategy_core.types import SessionScheme, SessionWindow

# ── Instrument ──────────────────────────────────────────────────────────────
#: NQ trade-price grid. Production tick bars are TRADE-PRICE tick bars (a "tick" is
#: a trade print, action='T'), and NQ trade prints land EXACTLY on the 0.25 grid
#: (empirically: 0 off-grid trades over a full 18:00-ET day), so integer ticks are
#: lossless. This supersedes the book-mid bars (which used a 0.125 grid because a
#: top-of-book mid can land on a half-tick); the 0.125 value now lives only in the
#: legacy/comparison harnesses, never in the production engine path.
DEFAULT_TICK_SIZE = 0.25
#: Bar-price source for the production tick bars (ratified): OHLC is built from the
#: TRADE PRINT price over trades, not a top-of-book mid over book events. Distinct
#: from MID_PRICE_SOURCE (which governs the 3 interaction FEATURES); they happen to
#: agree ("trade_price") but answer different questions — one defines the bars, the
#: other the features computed at a touch. The DuckDB batch builder filters to
#: action='T' and the streaming CandleEngine only accepts Trade events, so both
#: builders bucket the identical trade stream.
BAR_PRICE_SOURCE = "trade_price"
#: Production bar size: a bar closes on the Nth trade. 147 is the interaction-bar
#: hyperparameter the deployed contract trains under (a retrain may change it; this
#: is just the default). The streaming CandleEngine builds (147, 987, 2000) tick
#: bars concurrently; 147 is the one the decision layer touches.
DEFAULT_TICK_COUNT = 147
#: Aggressor-side encoding, VERIFIED empirically on real NQ front-month trades (phase 4e,
#: two independent checks agreeing with 0 cross-contamination across 3 days): databento
#: ``side='B'`` is the BUY aggressor (lifts ascending asks; prints above the top-of-book mid)
#: and ``side='A'`` is the SELL aggressor (hits descending bids; prints below mid). ``'N'``
#: occurs ~once/day on trades and is treated as a sell by the side-signed rule below.
BUY_AGGRESSOR_SIDE = "B"
#: Canonical deterministic trade-bar order (phase 4e). Within a (ts_event, sequence) matching
#: event the sweep prints are ordered by SIDE-SIGNED price -- ``+price`` for a buy aggressor,
#: ``-price`` for a sell -- then size, so an ascending sort reproduces the true chronological
#: WIRE direction (buy sweeps ascending as they lift asks, sell sweeps descending as they hit
#: bids). This makes research == replay == live with NO reorder buffer, and supersedes phase
#: 4d's plain ``price``-ascending key, which reversed sell sweeps and diverged from Trade-Lab's
#: wire-order bars on ~14% of bars. The streaming CandleEngine never sorts; producers (the
#: DuckDB builder, Trade-Lab's adapters) deliver events in this order, which equals wire order.
TRADE_BAR_ORDER = "(ts_event, sequence, side_signed_price, size)"
#: USD per 1.0 point. NQ=20, ES=50. (strategy_contract.py:62)
POINT_VALUE: dict[str, float] = {"NQ": 20.0, "ES": 50.0}

# ── Touch / zones ───────────────────────────────────────────────────────────
#: Merge levels whose prices are within this many points into one zone.
#: (dashboard_utility_builder.py:54  _ZONE_PROXIMITY = 3.0)
ZONE_PROXIMITY_PTS = 3.0
#: Ratified §3 (W1 P2c): the side->direction map is plugin-owned, not a platform
#: constant. The typed engine default lives in ``decisions/touch.py``
#: (``DEFAULT_DIRECTION_FROM_SIDE``); the lowercase WIRE vocabulary is emitted by
#: ``default_touch_reversal_section()`` and sourced verbatim by the QL emitter.

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
#: RETRAINING the model under this engine. The platform_version binding (the engine
#: axis, then strategy_core_engine_v1) is what makes Trade-Lab fail-close on the old model.
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

# ── Sessions (ET) — canonical dashboard_utility scheme (v3 re-clock) ─────────
SESSION_TIMEZONE = "US/Eastern"
TRADING_DAY_BOUNDARY = time(18, 0)  # CME 6pm ET rollover (UNCHANGED in v3)
#: Forward-label cutoff = the NY session END (engine v3). A touch's forward/label
#: window is scanned up to this ET wall-clock instant (also the ny SessionWindow end
#: below, single-sourced). v2 -> v3: 16:15 (old RTH close) -> 17:00 (the user's 4:00pm
#: CST NY-session end). NOT DST-ambiguous (DST flips at 02:00 ET). The symbol keeps its
#: historical name for continuity; it now denotes the ny-session-close forward cutoff,
#: not the cash-RTH close.
RTH_END = time(17, 0)

#: The canonical ET session scheme the v3 dataset is built under. The clock times are
#: the user's CST spec + a flat 1h (ET = CST + 1): asia 6:00pm-1:45am CST, london
#: 2:00am-7:00am CST, ny 8:00am-4:00pm CST. The engine stays ET-NATIVE and DST-aware
#: (bars are converted to US/Eastern and compared by ET wall-clock); there is NO CST
#: handling anywhere — CST is only the provenance of these ET numbers.
#:   asia   19:00 -> 02:45 ET  CROSSES MIDNIGHT (mask: t >= 19:00 OR t < 02:45). Its
#:          two halves (prior-evening 19:00->23:59 and this-morning 00:00->02:45) fall
#:          in the SAME trading day via the 18:00 ET boundary below.
#:   london 03:00 -> 08:00 ET
#:   ny     09:00 -> 17:00 ET  (end == RTH_END, the forward cutoff)
#: The ET hours 18:00-19:00, 02:45-03:00 and 08:00-09:00 are INTENTIONALLY unsessioned
#: (classify_session returns "none"); bars still exist there and still belong to the
#: trading day, they are just not in a named window.
#: (dashboard_utility_builder.py:44-51, _slice_session:332-344)
RESEARCH_SESSION_SCHEME = SessionScheme(
    timezone=SESSION_TIMEZONE,
    trading_day_boundary=TRADING_DAY_BOUNDARY,
    sessions={
        "asia": SessionWindow(time(19, 0), time(2, 45), crosses_midnight=True),
        "london": SessionWindow(time(3, 0), time(8, 0)),
        "ny": SessionWindow(time(9, 0), RTH_END),
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

# ── Contract descriptors ─────────────────────────────────────────────────────
# The remaining strategy.json STRINGS/tuples the contract emitter used to RESTATE
# inline (nan policy, level scheme, touch rule semantics, label policy, inference
# gating, data requirements). They are descriptive labels of how the canonical
# research path (the dashboard_utility builder/labeler) behaves, with no prior
# constant. Promoted here so the description (the emitter) and the mechanism (the
# engine + the research builder it reproduces) read from one source and cannot
# silently drift. Provenance cited per value to the canonical research code.

#: Feature-vector NaN handling. Missing feature values pass through as NaN and the
#: CatBoost model applies its trained ``nan_mode``; the runtime must NOT substitute
#: a 0.0 sentinel (except where a feature's own formula defines an empty-case value,
#: e.g. int_absorption_ratio -> 0.0). (strategy_contract.py feature_set.nan_policy)
NAN_POLICY = "model_native"

#: PDH/PDL are the FULL prior TRADING day's high/low (engine v3): the max-high /
#: min-low over the entire prior [18:00, 18:00) ET window — the daily-candle extremes
#: (ICT standard). v2 -> v3: "prior_day_ny_rth" (the prior NY cash slice) ->
#: "prior_day_full". (dashboard_utility_builder.py _compute_levels_for_date)
PDH_PDL_SOURCE = "prior_day_full"
#: The session-derived level names the level scheme exposes (asia/london highs &
#: lows plus prior-day high/low). (dashboard_utility_builder.py _compute_levels_for_date)
SESSION_LEVELS: tuple[str, ...] = (
    "asia_high",
    "asia_low",
    "london_high",
    "london_low",
    "pdh",
    "pdl",
)
#: A level is only usable once its defining session has CLOSED — the "available_from"
#: guard that, in engine v3, is ACTUALLY ENFORCED by detect_touches (v1/v2 emitted this
#: flag in the contract but never gated on it, so 71% of training labels were
#: look-ahead self-touches). Each level carries an availability instant — PDH/PDL from
#: the trading-day start (prior 18:00 ET); asia_high/low from the Asia close (02:45 ET);
#: london_high/low from the London close (08:00 ET); a merged zone from the MAX of its
#: constituents — and a touch is recorded only on a bar that CLOSES at/after it, so the
#: touch is a RETURN to an existing level, never the forming bar.
#: (strategy_core.decisions.touch.detect_touches; dashboard_utility_builder.py)
LEVEL_AVAILABLE_FROM_GUARD = True

#: Touch-rule descriptors. A touch is a BAR whose [low, high] range intersects a
#: zone's representative price ("bar_intersect"); the zone's representative price is
#: the MEAN of its constituent level prices (Zone.representative_price); only the
#: FIRST touch of a given zone per trading day is kept (first-touch scope).
#: (dashboard_utility_builder.py _detect_touches; types.Zone docstring)
TOUCH_TYPE = "bar_intersect"
ZONE_REPRESENTATIVE_PRICE = "mean_of_constituent_levels"
TOUCH_SCOPE = "first_touch_per_zone_per_day"

#: Label-policy descriptors. Resolution is MAE-FIRST (a stop is checked before a
#: target on the same bar); unresolved touches (no TP/SL hit before the cutoff) are
#: DROPPED. (dashboard_utility_labeling.py label_touch_event)
LABEL_RESOLUTION = "mae_first"
#: Entry reference for the canonical OUTCOME (engine v2, honest-entry re-anchor).
#: The label is now measured from the REALISTIC price at the DECISION INSTANT
#: (touch + DECISION_OFFSET_MINUTES), i.e. the market price WHEN THE PREDICTION CAN
#: FIRE — the touch + interaction window — matching the Trade-Lab EXECUTOR
#: convention (trade_executor.on_prediction enters at the market price when the
#: prediction fires, NOT the level price 5 min earlier). This SUPERSEDES the v1
#: "level_representative_price" anchor (the idealized level-at-touch entry that
#: overlapped the feature window). The decision-time entry PRICE and the
#: post-decision forward window are computed by the ADAPTER (engine_decision /
#: the decision-diff harness / the TL executor); resolve_outcome stays a pure
#: forward-scan over whatever (entry_points, forward_bars) the adapter supplies.
LABEL_ENTRY_REFERENCE = "realistic_at_decision"
#: Decision offset: how long AFTER the touch the decision can fire. Equals the
#: interaction window (the model needs the post-touch interaction features before it
#: can predict), so the feature window [touch, touch+offset] and the label window
#: (touch+offset, RTH_END] do NOT overlap — the look-ahead closure. Single-sourced
#: from DEFAULT_INTERACTION_WINDOW_MINUTES.
DECISION_OFFSET_MINUTES = DEFAULT_INTERACTION_WINDOW_MINUTES
#: Flatten time (ET): the executor rejects NEW entries at/after this wall-clock time
#: (trade_executor.on_prediction). A touch whose decision_time (touch + offset) is
#: at/after the flatten gets NO tradeable outcome — it is dropped / no_resolution,
#: matching the executor's no-entry rule. Single-sources that runtime rule into the
#: engine's label policy so research and execution agree on which touches are
#: tradeable. v2 -> v3: 15:55 -> 16:40 ET (the user's 3:40pm CST flatten), 20 min
#: before the 17:00 ET forward cutoff.
FLATTEN_TIME = time(16, 40)
LABEL_NO_RESOLUTION_DROPPED = True
#: Format for the forward-label cutoff descriptor: "<HH:MM>_<timezone>_ny_close",
#: built from RTH_END + SESSION_TIMEZONE so the literal is not restated. v3: RTH_END is
#: now the 17:00 ET ny-session close (not the old 16:15 cash-RTH close).
#: (dashboard_utility_labeling.py forward cutoff = ny session close)
LABEL_FORWARD_CUTOFF = f"{RTH_END.strftime('%H:%M')}_{SESSION_TIMEZONE}_ny_close"

#: Inference-gating descriptors. The runtime acts on the eligible class only inside
#: the NY session, gated by a confidence floor. ``INFERENCE_ELIGIBLE_SESSION`` is the
#: ny window name in RESEARCH_SESSION_SCHEME (v3: "ny" 09:00-17:00 ET, was "ny_rth").
#: The confidence gate (reversal_prob >= 0.70) is a runtime convention the runtime may
#: override. (strategy_contract.py inference block)
INFERENCE_ELIGIBLE_SESSION = "ny"
DEFAULT_CONFIDENCE_GATE = 0.70

#: Data-requirement descriptors. The strategy needs top-of-book (L1/mbp-1) depth
#: plus trades to compute features live; replay additionally ships mbp-10 for the
#: lossless book-mid comparison harnesses, but only top-of-book is USED.
#: (strategy_contract.py data_requirements block)
MIN_BOOK_LEVEL = "L1"
LIVE_SCHEMAS: tuple[str, ...] = ("trades", "mbp-1")
REPLAY_SCHEMAS: tuple[str, ...] = ("trades", "mbp-1", "mbp-10")
DEPTH_USAGE = "top_of_book_only"

# ── IFVG (ifvg_smc) capture-profile defaults — WIDE bounds, not doc values ───
#: Canonical TIME timeframe label -> seconds map (ruling 9.11 set). Single-sourced
#: here for the ifvg section/plugin; candles/time_streaming.py keeps the tuple.
TIME_TF_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "10m": 600,
    "15m": 900,
    "30m": 1800,
    "1H": 3600,
    "4H": 14400,
}
#: Every IFVG_* bound below is a CAPTURE bound (WIDE-capture ruling, IFVG window):
#: it exists to keep the one-setup FSM finite, NEVER to encode trade quality. The
#: ifvg-strat.md doc default it widens is noted per line; the doc value is an
#: emitted measurement/filter downstream, not a gate.
IFVG_HTF_TIMEFRAMES = ("1H", "4H")
IFVG_PARENT_TIMEFRAMES = ("3m", "5m", "10m", "15m", "30m")
IFVG_MIN_GAP_TICKS_CAPTURE = 1  # doc §6.2: 4 ticks -> size_ticks emitted per structure
IFVG_PARENT_REACTION_WINDOW_1M_BARS_MAX = 480  # doc §6.2: 40 PARENT bars
IFVG_PARENT_HTF_DISTANCE_TICKS_MAX = 400  # doc §6.2: 80 ticks
IFVG_OPPOSING_PARENT_DISTANCE_TICKS_MAX = 400  # doc §6.2: 80 ticks
IFVG_LOCK_TO_ARMED_1M_BARS_MAX = 480  # doc §14.3: no timeout -> bounded capture
IFVG_ARMED_TO_INVERSION_1M_BARS_MAX = 480  # doc §14.3: no timeout -> bounded capture
IFVG_POST_INVERSION_EXPIRY_1M_BARS_MAX = 240  # doc §6.2: 80 1m bars
IFVG_HTF_REGISTRY_MAX_AGE_DAYS = 15  # census: 4H first-touch p90 ~2.8 days
IFVG_LTF_REGISTRY_MAX_LIVE = 512  # census: ~317 1m gaps/day, 98%+ fill same day
IFVG_SWING_STRENGTH_BARS = 3
IFVG_SWING_POOL_MAX = 64
IFVG_SL_BUFFER_TICKS = 1  # doc §6.3
IFVG_TP_R_MULTIPLE = 1.0  # doc §6.3 fixed_1R — the label-family baseline
IFVG_ENTRY_FAMILIES = ("fresh_fvg_continuation", "ifvg_retest")
IFVG_SELECTED_ENTRY_FAMILY = "fresh_fvg_continuation"  # doc default family
IFVG_LABEL_FAMILY = "mae_first_r1_eod"
#: ifvg-strat.md §6.4 session windows (ET) — a FEATURE STAMP on records, never an
#: engine scheme (the engine classifies with RESEARCH_SESSION_SCHEME).
IFVG_DOC_SESSIONS = {
    "asia": ("16:00", "01:45"),
    "london": ("02:00", "07:00"),
    "ny": ("08:00", "14:00"),
}

__all__ = [
    "DEFAULT_TICK_SIZE",
    "BAR_PRICE_SOURCE",
    "DEFAULT_TICK_COUNT",
    "BUY_AGGRESSOR_SIDE",
    "TRADE_BAR_ORDER",
    "POINT_VALUE",
    "ZONE_PROXIMITY_PTS",
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
    # contract descriptors
    "NAN_POLICY",
    "PDH_PDL_SOURCE",
    "SESSION_LEVELS",
    "LEVEL_AVAILABLE_FROM_GUARD",
    "TOUCH_TYPE",
    "ZONE_REPRESENTATIVE_PRICE",
    "TOUCH_SCOPE",
    "LABEL_RESOLUTION",
    "LABEL_ENTRY_REFERENCE",
    "DECISION_OFFSET_MINUTES",
    "FLATTEN_TIME",
    "LABEL_NO_RESOLUTION_DROPPED",
    "LABEL_FORWARD_CUTOFF",
    "INFERENCE_ELIGIBLE_SESSION",
    "DEFAULT_CONFIDENCE_GATE",
    "MIN_BOOK_LEVEL",
    "LIVE_SCHEMAS",
    "REPLAY_SCHEMAS",
    "DEPTH_USAGE",
    # ifvg_smc capture profile
    "TIME_TF_SECONDS",
    "IFVG_HTF_TIMEFRAMES",
    "IFVG_PARENT_TIMEFRAMES",
    "IFVG_MIN_GAP_TICKS_CAPTURE",
    "IFVG_PARENT_REACTION_WINDOW_1M_BARS_MAX",
    "IFVG_PARENT_HTF_DISTANCE_TICKS_MAX",
    "IFVG_OPPOSING_PARENT_DISTANCE_TICKS_MAX",
    "IFVG_LOCK_TO_ARMED_1M_BARS_MAX",
    "IFVG_ARMED_TO_INVERSION_1M_BARS_MAX",
    "IFVG_POST_INVERSION_EXPIRY_1M_BARS_MAX",
    "IFVG_HTF_REGISTRY_MAX_AGE_DAYS",
    "IFVG_LTF_REGISTRY_MAX_LIVE",
    "IFVG_SWING_STRENGTH_BARS",
    "IFVG_SWING_POOL_MAX",
    "IFVG_SL_BUFFER_TICKS",
    "IFVG_TP_R_MULTIPLE",
    "IFVG_ENTRY_FAMILIES",
    "IFVG_SELECTED_ENTRY_FAMILY",
    "IFVG_LABEL_FAMILY",
    "IFVG_DOC_SESSIONS",
]
