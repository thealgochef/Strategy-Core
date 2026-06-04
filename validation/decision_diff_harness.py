"""PHASE 4f Part 2 — decision-layer diff harness (RESEARCH vs TRADE-LAB, SAME bar def).

ENGINE v3 ALIGNMENT RE-RUN: both sides now run under strategy_core_engine_v3 — the
re-clocked ET sessions (asia 19:00->02:45 crossing midnight, london 03:00->08:00, ny
09:00->17:00), the ENFORCED level-availability guard (a level can only be touched once
its defining session has closed), FULL-prior-day PDH/PDL, and the HONEST decision-time
labeling (entry = the realistic TRADE price at the DECISION instant = touch close +
DECISION_OFFSET_MINUTES (5m); forward window = bars whose close is in (decision_time,
17:00 ET]; touches whose decision_time is at/after the FLATTEN_TIME (16:40 ET) or past
the forward cutoff are DROPPED — no tradeable outcome).
This MIRRORS the production adapter ``engine_decision.process_single_date_engine``
(honest_entry=True) and the Trade-Lab EXECUTOR convention (enter at the market price
WHEN THE PREDICTION FIRES, not the level price 5 min earlier; reject entries at/after
the flatten). The 3 classes / tp=15 / sl=30 / trap_mfe_min=5 / MAE-first ladder are
HELD EXACTLY — only the entry anchor + the forward-window start moved. Labels under
this rule DIFFER from the OLD book-mid level-entry labels: that is the re-anchor, NOT
drift. The class-balance shift is reported.

This is the real test of the phase-4e/4f bar residual: it does NOT compare to
canonical / book-mid / the deployed model. It builds BOTH 147t TRADE-PRICE bar
sets (the exact production pair the 4e gate locks) on the SAME front-month trade
set per day, then runs the FULL strategy_core decision pipeline on EACH bar set
and DIFFS the decision OUTPUTS. Strategy correctness is OUT OF SCOPE; we measure
ONLY whether the ~1% bar residual (same-price volume sub-splits + a handful of
mixed-side OHLC bars) propagates into levels / zones / touches / labels / features.

THE TWO BAR SETS (same window per day: [prev 18:00 ET, day 18:00 ET)):
  RESEARCH  = CQL TickStore.build_tick_bars(price_source="trade")  (DuckDB,
              side-signed deterministic order, ns-aligned after 4f Part 1).
  TRADE-LAB = streaming CandleEngine(scheme=RESEARCH_SESSION_SCHEME, tf=(147,))
              fed the front-month trades in WIRE order (the physical parquet
              stream stable-sorted by ts_event, exactly historical_parquet.py:252
              / the gate's _read_phys + sort_values("ts_event", kind="stable")).
Both yield a list[strategy_core.types.Bar] over the same window. Then per bar set:

  1. LEVELS  (engine-native mirror of _compute_levels_for_date):
       asia/london H/L from THIS day's bars bucketed by classify_session(close).
       PDH/PDL = the PRIOR trading day's NY-RTH H/L, where the prior day's bars
       are built with the SAME pipeline (research-prior via build_tick_bars(trade);
       trade-lab-prior via streaming-wire), so PDH/PDL residual propagation is
       captured. Walk back to the most recent prior date whose window has a ny_rth
       session (handles 07-07: prev cal day 07-06 is Sunday; last NY RTH ~07-03).
  2. ZONES   = build_zones(levels).
  3. TOUCHES = detect_touches(day_bars, zones, tick_size=0.25, trading_day=D).
  4. SESSIONS= classify_session(touch.bar_ts_utc).session; ny_rth eligibility.
  5. LABELS  = HONEST decision-time rule (engine v2). Per touch: decision_ts =
              touch close + DECISION_OFFSET_MINUTES (5m); DROP if decision_ts is
              at/after FLATTEN_TIME (15:55 ET) or >= 16:15 ET. entry = realistic
              front-month TRADE price at the decision instant (point query, 30-min
              bounded lookback). forward bars = close in (decision_ts, 16:15 ET].
              resolve_outcome(entry_points=entry, forward_bars=forward; MAE-first;
              tp=15, sl=30, trap_mfe_min=5). The adapter (this harness) computes the
              entry price + forward window; resolve_outcome stays a PURE forward-scan.
  6. FEATURES= the 6 model features. Interaction window [touch, touch+5min) and
              approach window [touch-30min, touch) read the raw TRADE / L0-quote
              streams via DuckDB (bar-set-INDEPENDENT streams; the only bar-set
              dependence is the touch anchor). Both anchors floored to us to
              neutralize the us-vs-ns representational seam.

DIFF the outputs between the two bar sets, per day, exact counts/magnitudes.

Importable and runnable (``python validation/decision_diff_harness.py``). Skips
cleanly without the local databento store / Claude-Quant-Lab src. Writes nothing
outside validation/. Does NOT modify the engine, the gate, or any pinning.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# --- research package path (read-only) --------------------------------------
CQL_SRC = r"C:/Users/gonza/Documents/Claude-Quant-Lab/src"
if CQL_SRC not in sys.path:
    sys.path.insert(0, CQL_SRC)

DATA_DIR = Path(r"C:/Users/gonza/Documents/Trade-Dashboard/data/databento")
SYMBOL = "NQ"
TICK_COUNT = 147
TICK_SIZE = 0.25
_ET = "America/New_York"

# label policy (production dashboard_utility defaults)
TP_POINTS = 15.0
SL_POINTS = 30.0
TRAP_MFE_MIN = 5.0
INT_WINDOW_MIN = 5
APP_WINDOW_MIN = 30
RTH_CUTOFF = time(17, 0)  # informational: mirrors engine RTH_END (v3 ny-session close)
# honest decision-time fill: bounded lookback for the trade-price point query
ENTRY_LOOKBACK_MIN = 30

# how far back to look for the most recent prior trading day with a NY-RTH session
MAX_PRIOR_WALKBACK_DAYS = 7

from strategy_core import (  # noqa: E402
    Bar,
    Direction,
    Level,
    Quote,
    Side,
    Trade,
    app_avg_trade_size,
    app_large_trade_vol_pct,
    app_max_spread,
    build_zones,
    classify_session,
    detect_touches,
    int_absorption_ratio,
    int_time_beyond_level,
    int_time_within_2pts,
    make_bar_id,
    resolve_honest_outcome,
)
from strategy_core.decisions.honest_entry import HonestEntryDrop  # noqa: E402
from strategy_core.constants import (  # noqa: E402
    DECISION_OFFSET_MINUTES,
    FLATTEN_TIME,
    RESEARCH_SESSION_SCHEME,
)

# single-source the honest decision-time semantics from the engine constants so the
# harness can never drift from the production rule. The decision fires DECISION_OFFSET
# minutes after the touch (== the interaction feature window, so the feature window
# [touch, touch+offset] and the label window (decision, 16:15] never overlap), and a
# decision at/after FLATTEN_TIME is never traded.
DECISION_OFFSET_MIN = int(DECISION_OFFSET_MINUTES)


# ── window helpers ──────────────────────────────────────────────────────────
def _window(day: str):
    """[prev 18:00 ET, day 18:00 ET) as tz-aware UTC bounds (DST-correct)."""
    d = date.fromisoformat(day)
    prev = d - timedelta(days=1)
    start = pd.Timestamp(f"{prev} 18:00:00", tz=_ET).tz_convert("UTC")
    end = pd.Timestamp(f"{d} 18:00:00", tz=_ET).tz_convert("UTC")
    return prev.isoformat(), d.isoformat(), start, end


def _available(day: str) -> bool:
    return (DATA_DIR / SYMBOL / day / "mbp10.parquet").exists()


# ── front-month physical trade stream (the gate's _read_phys, verbatim) ─────
def _read_phys(day: str) -> pd.DataFrame:
    prev, cur, start, end = _window(day)
    files = [DATA_DIR / SYMBOL / prev / "mbp10.parquet", DATA_DIR / SYMBOL / cur / "mbp10.parquet"]
    frames = [
        pd.read_parquet(f, columns=["ts_event", "sequence", "action", "price", "size", "side", "symbol"])
        for f in files
        if f.exists()
    ]
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)  # physical / emission order
    ts = pd.to_datetime(raw["ts_event"], utc=True)
    inwin = (ts >= start) & (ts < end) & (~raw["symbol"].astype(str).str.contains("-"))
    if not inwin.any():
        return pd.DataFrame()
    fm = raw.loc[inwin, "symbol"].value_counts().idxmax()
    mask = (
        inwin
        & (raw["symbol"] == fm)
        & (raw["action"].astype(str).str.lower() == "t")
        & raw["price"].notna()
        & (raw["price"] > 0)
    )
    sub = raw[mask].copy()
    sub["ts_event"] = pd.to_datetime(sub["ts_event"], utc=True)
    sub["side"] = sub["side"].astype(str)
    return sub.reset_index(drop=True)  # PHYSICAL order


# ── RESEARCH bar set: CQL build_tick_bars(trade) -> engine Bar list ─────────
def _research_bars(day: str) -> list[Bar]:
    """TickStore.build_tick_bars(price_source='trade') over the window, converted
    to strategy_core Bar objects. trading_day/bar_index/is_complete from the frame;
    close_ts from the bar_time index, open_ts from open_time; OHLC ticks = round(px/0.25)."""
    from alpha_lab.agents.data_infra.tick_store import TickStore

    prev, cur, start, end = _window(day)
    st = TickStore(DATA_DIR)
    try:
        for ds in (prev, cur):
            st.register_symbol_date(SYMBOL, ds)
        df = st.build_tick_bars(SYMBOL, start, end, tick_count=TICK_COUNT)  # default trade, side-signed
    finally:
        st.close()
    if df.empty:
        return []
    df = df.reset_index().rename(columns={"timestamp": "close_time"})
    bars: list[Bar] = []
    for r in df.itertuples(index=False):
        td = r.trading_day.date() if hasattr(r.trading_day, "date") else r.trading_day
        bar_index = int(r.bar_index)
        close_ts = pd.Timestamp(r.close_time).to_pydatetime()
        open_ts = pd.Timestamp(r.open_time).to_pydatetime()
        if close_ts.tzinfo is None:
            close_ts = close_ts.replace(tzinfo=timezone.utc)
        if open_ts.tzinfo is None:
            open_ts = open_ts.replace(tzinfo=timezone.utc)
        bars.append(
            Bar(
                timeframe_ticks=TICK_COUNT,
                trading_day=td,
                bar_index=bar_index,
                bar_id=make_bar_id(TICK_COUNT, td, bar_index),
                open_ts_utc=open_ts,
                close_ts_utc=close_ts,
                open_ticks=int(round(r.open / TICK_SIZE)),
                high_ticks=int(round(r.high / TICK_SIZE)),
                low_ticks=int(round(r.low / TICK_SIZE)),
                close_ticks=int(round(r.close / TICK_SIZE)),
                volume=int(r.volume),
                trade_count=int(r.trade_count),
                is_complete=bool(r.is_complete),
                is_partial=not bool(r.is_complete),
            )
        )
    return bars


# ── TRADE-LAB bar set: streaming CandleEngine in WIRE order ─────────────────
def _tradelab_bars(day: str) -> list[Bar]:
    """Streaming CandleEngine fed the front-month trades in WIRE order (physical
    stream stable-sorted by ts_event), finalized at end-of-window for the partial."""
    from strategy_core.candles.streaming import CandleEngine

    phys = _read_phys(day)
    if phys.empty:
        return []
    wire = phys.sort_values("ts_event", kind="stable").reset_index(drop=True)
    eng = CandleEngine(timeframes=(TICK_COUNT,), scheme=RESEARCH_SESSION_SCHEME)
    out: list[Bar] = []
    ts = wire["ts_event"].to_numpy()
    px = wire["price"].to_numpy("float64")
    sz = wire["size"].to_numpy("int64")
    for i in range(len(wire)):
        upd = eng.process_trade(
            Trade(
                event_ts_utc=pd.Timestamp(ts[i]).to_pydatetime(),
                price_ticks=int(np.rint(px[i] / TICK_SIZE)),
                size=int(sz[i]),
            )
        )
        if upd.completed:
            out.extend(upd.completed)
    out.extend(eng.finalize_trading_day())
    return out


# ── pipeline stage 1: LEVELS (engine-native) ────────────────────────────────
def _session_bucket_hl(bars: list[Bar], session_name: str) -> tuple[float, float] | None:
    """High/low (points) over bars whose close-ts classifies into ``session_name``.

    Mirrors _compute_levels_for_date / _slice_session, but engine-native: each bar
    is bucketed by strategy_core.classify_session(bar.close_ts_utc).session (the
    canonical ET windows), and H/L is max(high)/min(low) over that bucket in POINTS.
    """
    highs: list[float] = []
    lows: list[float] = []
    for b in bars:
        if classify_session(b.close_ts_utc).session == session_name:
            highs.append(b.high_ticks * TICK_SIZE)
            lows.append(b.low_ticks * TICK_SIZE)
    if not highs:
        return None
    return max(highs), min(lows)


def _full_day_hl(bars: list[Bar]) -> tuple[float, float] | None:
    """High/low (points) over ALL bars of a trading day — the daily-candle extremes.

    Engine v3 PDH/PDL source: the FULL prior [18:00, 18:00) ET window, not the NY-RTH
    slice. ``day_bars`` already span exactly one trading day, so this is max(high)/
    min(low) over the whole list."""
    if not bars:
        return None
    highs = [b.high_ticks * TICK_SIZE for b in bars]
    lows = [b.low_ticks * TICK_SIZE for b in bars]
    return max(highs), min(lows)


def _prior_full_hl(day: str, build_bars) -> tuple[float, float, str] | None:
    """Most-recent prior trading day's FULL-day H/L (engine v3), built with the SAME
    pipeline. Walk back from the calendar day before ``day``; for each available prior
    date, build its bars over [prev-1 18:00 ET, prev 18:00 ET) and take the full-day
    H/L. Returns (high, low, prior_date) for the first prior date that yields bars
    (handles weekends/holidays). None if none found.
    """
    d = date.fromisoformat(day)
    for back in range(1, MAX_PRIOR_WALKBACK_DAYS + 1):
        pd_date = (d - timedelta(days=back)).isoformat()
        if not _available(pd_date):
            continue
        bars = build_bars(pd_date)
        if not bars:
            continue
        hl = _full_day_hl(bars)
        if hl is not None:
            return hl[0], hl[1], pd_date
    return None


def _availability_instants(day: str):
    """(pdh_pdl, asia_close, london_close) UTC instants for ``day`` — engine v3 guard.

    Single-sourced from the engine session scheme: PDH/PDL available from the
    trading-day start (prior 18:00 ET = the window start); asia from the Asia close
    (02:45 ET); london from the London close (08:00 ET). DST-aware via the ET tz.
    """
    prev, cur, start, _end = _window(day)
    S = RESEARCH_SESSION_SCHEME

    def _avail(ds: str, t) -> datetime:
        # DST-safe localize (see dashboard_utility_builder._avail): a spring-forward
        # 02:45 ET does not exist -> shift_forward to 03:00 ET; the anchors never land
        # in the fall-back fold so ambiguous is moot.
        naive = pd.Timestamp(f"{ds} {t.strftime('%H:%M:%S')}")
        return (
            naive.tz_localize(_ET, nonexistent="shift_forward", ambiguous=False)
            .tz_convert("UTC")
            .to_pydatetime()
        )

    pdh_pdl = start.to_pydatetime()  # == prev 18:00 ET (the [prev 18:00, day 18:00) start)
    asia_close = _avail(cur, S.sessions["asia"].end)     # 02:45 ET
    london_close = _avail(cur, S.sessions["london"].end)  # 08:00 ET
    return pdh_pdl, asia_close, london_close


def compute_levels(day: str, day_bars: list[Bar], build_bars) -> list[Level]:
    """Engine-native v3 level set for ``day`` from ``day_bars`` (one bar set / pipeline).

    PDH/PDL from the prior trading day's FULL-day H/L (built via the SAME pipeline);
    asia/london H/L from this day's bars. Each level carries its ``available_from``
    instant (PDH/PDL = prior 18:00 ET; asia = 02:45 ET; london = 08:00 ET) so
    detect_touches ENFORCES the look-ahead guard. Names/sides match research
    (_compute_levels_for_date): PDH(HIGH), PDL(LOW), asia_high(HIGH), asia_low(LOW),
    london_high(HIGH), london_low(LOW). The current day's own range carries to the
    next day as PDH/PDL.
    """
    pdh_pdl_avail, asia_avail, london_avail = _availability_instants(day)
    levels: list[Level] = []

    prior = _prior_full_hl(day, build_bars)
    if prior is not None:
        pdh, pdl, _pdate = prior
        levels.append(Level(name="PDH", price=pdh, side=Side.HIGH, available_from=pdh_pdl_avail))
        levels.append(Level(name="PDL", price=pdl, side=Side.LOW, available_from=pdh_pdl_avail))

    asia = _session_bucket_hl(day_bars, "asia")
    if asia is not None:
        levels.append(Level(name="asia_high", price=asia[0], side=Side.HIGH, available_from=asia_avail))
        levels.append(Level(name="asia_low", price=asia[1], side=Side.LOW, available_from=asia_avail))

    london = _session_bucket_hl(day_bars, "london")
    if london is not None:
        levels.append(Level(name="london_high", price=london[0], side=Side.HIGH, available_from=london_avail))
        levels.append(Level(name="london_low", price=london[1], side=Side.LOW, available_from=london_avail))

    return levels


# ── pipeline stages 2-5: zones / touches / sessions / labels ────────────────
@dataclass
class PipelineResult:
    """Decision outputs for one bar set on one day."""

    levels: list[Level]
    zones: list  # list[Zone]
    touches: list  # list[Touch]
    labels: dict  # touch-key -> OutcomeResult (only touches with a tradeable outcome)
    features: dict  # touch-key -> dict of 6 features
    ny_rth_touch_keys: set  # touch-keys eligible (touch in ny_rth session)
    dropped: dict  # touch-key -> drop reason (honest no-entry: flatten / cutoff / no-fill)


def _touch_key(t) -> tuple:
    """Stable, bar-set-comparable touch identity: (level_type, side-of-zone via
    direction, touch bar close truncated to us, representative_price rounded)."""
    ts_us = pd.Timestamp(t.bar_ts_utc).floor("us").to_pydatetime()
    return (t.level_type, t.direction.value, ts_us, round(float(t.representative_price), 6))


def run_pipeline(
    day: str,
    day_bars: list[Bar],
    build_bars,
    trade_reader,
    quote_reader,
    price_at,
) -> PipelineResult:
    """Full engine decision pipeline on ONE bar set under the engine-v2 HONEST rule.

    trade_reader/quote_reader/price_at are bar-set-INDEPENDENT DuckDB stream
    accessors (shared across both pipelines). The honest decision-time outcome is the
    SINGLE engine orchestration ``strategy_core.resolve_honest_outcome`` — this
    harness is now a THIN injector: it only wires in ``price_at`` (the trade-price
    accessor) and the day's ``Bar`` list; the engine owns the decision_ts / flatten /
    cutoff / entry-lookup / forward-selection / resolve_outcome rule. Per touch the
    engine returns either an ``OutcomeResult`` (tradeable) or a ``HonestEntryDrop``
    (reason flatten / cutoff / no_fill / no_forward).
    """
    D = date.fromisoformat(day)

    # 1. levels (this pipeline's own bars + its own prior-day bars)
    levels = compute_levels(day, day_bars, build_bars)

    # 2. zones
    zones = build_zones(levels)

    # 3. touches (fresh zones; detection mutates zone.touched, so rebuild)
    zones_for_touch = build_zones(levels)
    touches = detect_touches(day_bars, zones_for_touch, tick_size=TICK_SIZE, trading_day=D)

    # 4. session eligibility (engine v3: the ny window 09:00-17:00 ET)
    ny_keys: set = set()
    for t in touches:
        if classify_session(t.bar_ts_utc).session == "ny":
            ny_keys.add(_touch_key(t))

    # 5. labels (HONEST decision-time rule, via the engine) + 6. features
    labels: dict = {}
    features: dict = {}
    dropped: dict = {}
    # The engine's discriminated drop reasons mapped back to this harness's reason
    # taxonomy (the diff only uses dropped-set membership + count, not the strings).
    _drop_reason = {
        "flatten": "flatten_or_cutoff",
        "cutoff": "flatten_or_cutoff",
        "no_fill": "no_fill",
        "no_forward": "empty_forward",
    }
    for t in touches:
        key = _touch_key(t)

        result = resolve_honest_outcome(
            t,
            day_bars,
            price_at,
            tick_size=TICK_SIZE,
            tp_points=TP_POINTS,
            sl_points=SL_POINTS,
            trap_mfe_min=TRAP_MFE_MIN,
            decision_offset_minutes=DECISION_OFFSET_MIN,
        )
        if isinstance(result, HonestEntryDrop):
            dropped[key] = _drop_reason[result.reason]
            continue

        labels[key] = result
        features[key] = _compute_features(t, trade_reader, quote_reader)

    return PipelineResult(
        levels=levels,
        zones=zones,
        touches=touches,
        labels=labels,
        features=features,
        ny_rth_touch_keys=ny_keys,
        dropped=dropped,
    )


# ── pipeline stage 6: FEATURES (6 model features) ───────────────────────────
FEATURE_NAMES = (
    "int_time_beyond_level",
    "int_time_within_2pts",
    "int_absorption_ratio",
    "app_large_trade_vol_pct",
    "app_avg_trade_size",
    "app_max_spread",
)


def _compute_features(touch, trade_reader, quote_reader) -> dict:
    """6 model features for one touch. Windows anchored at the touch bar close,
    FLOORED to microseconds (neutralizes the us-vs-ns anchor representational seam).

    Interaction window [anchor, anchor+5min): post-touch TRADE stream.
    Approach window    [anchor-30min, anchor): TRADE stream (avg size, large-vol pct)
                       + L0 QUOTE stream (max spread). End-exclusive on the approach.
    """
    rep = float(touch.representative_price)
    direction = touch.direction
    anchor = pd.Timestamp(touch.bar_ts_utc).floor("us")
    int_end = anchor + pd.Timedelta(minutes=INT_WINDOW_MIN)
    app_start = anchor - pd.Timedelta(minutes=APP_WINDOW_MIN)

    # interaction: [anchor, anchor+5min) trades (end-exclusive)
    int_df = trade_reader(anchor, int_end, end_exclusive=True)
    int_trades = [
        Trade(
            event_ts_utc=pd.Timestamp(r.ts_event).to_pydatetime(),
            price_ticks=int(round(float(r.price) / TICK_SIZE)),
            size=int(r.size),
        )
        for r in int_df.itertuples(index=False)
    ]
    int_beyond = int_time_beyond_level(int_trades, rep, direction, TICK_SIZE)
    int_within = int_time_within_2pts(int_trades, rep, TICK_SIZE)
    int_absorp = int_absorption_ratio(int_trades, rep, direction, TICK_SIZE)

    # approach: [anchor-30min, anchor) trades + L0 quotes (end-exclusive)
    app_df = trade_reader(app_start, anchor, end_exclusive=True)
    app_trades = [
        Trade(
            event_ts_utc=pd.Timestamp(r.ts_event).to_pydatetime(),
            price_ticks=int(round(float(r.price) / TICK_SIZE)),
            size=int(r.size),
        )
        for r in app_df.itertuples(index=False)
    ]
    q_df = quote_reader(app_start, anchor)
    app_quotes = [
        Quote(
            event_ts_utc=pd.Timestamp(r.ts_event).to_pydatetime(),
            bid_price_ticks=int(round(float(r.bid_px_00) / TICK_SIZE)),
            ask_price_ticks=int(round(float(r.ask_px_00) / TICK_SIZE)),
        )
        for r in q_df.itertuples(index=False)
    ]
    app_large = app_large_trade_vol_pct(app_trades)
    app_avg = app_avg_trade_size(app_trades)
    app_spread = app_max_spread(app_quotes, TICK_SIZE)

    return {
        "int_time_beyond_level": int_beyond,
        "int_time_within_2pts": int_within,
        "int_absorption_ratio": int_absorp,
        "app_large_trade_vol_pct": app_large,
        "app_avg_trade_size": app_avg,
        "app_max_spread": app_spread,
    }


# ── bar-set-independent DuckDB trade/quote stream readers (stages F/G style) ─
class DayStreams:
    """DuckDB views over the current+prev day mbp10 parquet, front-month aware.

    Mirrors parity_harness_v2's DayParquet: trades() and quotes_base() filter to
    the dominant front-month outright with bid/ask>0, action='T' for trades. These
    streams do NOT depend on which bar set produced the touch — both pipelines read
    them identically; features differ ONLY when a touch's anchor differs."""

    def __init__(self, day: str):
        import duckdb

        prev, cur, _s, _e = _window(day)
        path = DATA_DIR / SYMBOL / cur / "mbp10.parquet"
        prev_path = DATA_DIR / SYMBOL / prev / "mbp10.parquet"
        reads = [f"SELECT * FROM read_parquet('{path.as_posix()}')"]
        if prev_path.exists():
            reads.append(f"SELECT * FROM read_parquet('{prev_path.as_posix()}')")
        self._union = " UNION ALL ".join(reads)
        self._con = duckdb.connect(":memory:")
        front = self._con.execute(
            f"SELECT symbol, count(*) AS n FROM ({self._union}) AS t "
            f"WHERE symbol NOT LIKE '%-%' GROUP BY symbol ORDER BY n DESC LIMIT 1"
        ).fetchone()
        self._sym = front[0] if front else None

    def trades(self, start, end, *, end_exclusive: bool) -> pd.DataFrame:
        sym_f = f"AND symbol = '{self._sym}'" if self._sym else "AND symbol NOT LIKE '%-%'"
        cmp_end = "<" if end_exclusive else "<="
        sql = f"""
            SELECT ts_event, price, size
            FROM ({self._union}) AS t
            WHERE ts_event >= $1 AND ts_event {cmp_end} $2
              AND bid_px_00 > 0 AND ask_px_00 > 0
              AND action = 'T'
              {sym_f}
            ORDER BY ts_event ASC
        """
        return self._con.execute(sql, [pd.Timestamp(start), pd.Timestamp(end)]).fetchdf()

    def quotes(self, start, end) -> pd.DataFrame:
        sym_f = f"AND symbol = '{self._sym}'" if self._sym else "AND symbol NOT LIKE '%-%'"
        sql = f"""
            SELECT ts_event, bid_px_00, ask_px_00
            FROM ({self._union}) AS t
            WHERE ts_event >= $1 AND ts_event < $2
              AND bid_px_00 > 0 AND ask_px_00 > 0
              {sym_f}
            ORDER BY ts_event ASC
        """
        return self._con.execute(sql, [pd.Timestamp(start), pd.Timestamp(end)]).fetchdf()

    def trade_price_at(self, as_of, *, lookback_min: int = ENTRY_LOOKBACK_MIN) -> float | None:
        """Most-recent front-month TRADE print price with ts_event <= as_of.

        The honest decision-time FILL: the realistic trade price prevailing at the
        decision instant (touch + DECISION_OFFSET_MIN). Mirrors
        ``engine_decision._trade_price_at`` (action='T', price>0, book-valid,
        front-month) with the SAME 30-min bounded lookback, on the same bar-set-
        INDEPENDENT DuckDB trade stream both pipelines read. Returns None if no
        qualifying print exists in the lookback window."""
        sym_f = f"AND symbol = '{self._sym}'" if self._sym else "AND symbol NOT LIKE '%-%'"
        lo = pd.Timestamp(as_of) - pd.Timedelta(minutes=lookback_min)
        sql = f"""
            SELECT price
            FROM ({self._union}) AS t
            WHERE ts_event <= $1 AND ts_event >= $2
              AND action = 'T'
              AND price IS NOT NULL AND price > 0
              AND bid_px_00 > 0 AND ask_px_00 > 0
              {sym_f}
            ORDER BY ts_event DESC LIMIT 1
        """
        row = self._con.execute(sql, [pd.Timestamp(as_of), lo]).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def close(self):
        try:
            self._con.close()
        except Exception:
            pass


# ── DIFF the two pipelines' decision outputs ────────────────────────────────
FEATURE_EPS = 1e-6  # below this, two feature values are "identical" (approach unrounded)


def _level_map(levels: list[Level]) -> dict:
    return {l.name: (round(float(l.price), 6), l.side.value) for l in levels}


def _zone_set(zones: list) -> set:
    return {(round(float(z.representative_price), 6), z.side.value, tuple(z.names)) for z in zones}


def _feat_eq(a, b) -> bool:
    if a is None and b is None:
        return True
    fa, fb = float(a), float(b)
    if np.isnan(fa) and np.isnan(fb):
        return True
    if np.isnan(fa) or np.isnan(fb):
        return False
    return abs(fa - fb) <= FEATURE_EPS


@dataclass
class DayDiff:
    day: str
    skip: bool = False
    reason: str = ""
    research_bars: int = 0
    tradelab_bars: int = 0
    levels_identical: bool = False
    level_detail: str = ""
    zones_identical: bool = False
    zone_detail: str = ""
    touches_research: int = 0
    touches_tradelab: int = 0
    touches_matched: int = 0
    touches_differing: int = 0
    touch_detail: str = ""
    ny_rth_touches: int = 0
    # honest decision-time rule: touches that survived (got a tradeable outcome) vs
    # dropped (flatten/cutoff/no-fill/empty-forward), and whether the survive/drop
    # PARTITION is identical across the two bar sets.
    labeled_research: int = 0
    labeled_tradelab: int = 0
    dropped_research: int = 0
    dropped_tradelab: int = 0
    survive_set_identical: bool = True
    survive_detail: str = ""
    labels_identical: bool = True
    label_detail: str = ""
    label_flips: int = 0
    features_identical: bool = True
    feature_detail: str = ""
    feature_worst: dict = field(default_factory=dict)  # feat -> (max_abs_diff, n_touches)
    # class balance over the labeled (surviving) touches, this bar set (research side;
    # both sides identical when survive_set_identical & no label flips).
    class_balance: dict = field(default_factory=dict)  # label -> count


def diff_day(day: str) -> DayDiff:
    """Build BOTH bar sets, run the FULL pipeline on each, diff the outputs."""
    if not _available(day):
        return DayDiff(day=day, skip=True, reason="no data")

    research_bars = _research_bars(day)
    tradelab_bars = _tradelab_bars(day)
    if not research_bars or not tradelab_bars:
        return DayDiff(day=day, skip=True, reason="empty bar set")

    streams = DayStreams(day)
    try:
        trade_reader = streams.trades
        quote_reader = streams.quotes
        price_at = streams.trade_price_at
        r_res = run_pipeline(
            day, research_bars, _research_bars, trade_reader, quote_reader, price_at
        )
        r_tl = run_pipeline(
            day, tradelab_bars, _tradelab_bars, trade_reader, quote_reader, price_at
        )
    finally:
        streams.close()

    dd = DayDiff(day=day, research_bars=len(research_bars), tradelab_bars=len(tradelab_bars))

    # --- levels ---
    lm_r, lm_t = _level_map(r_res.levels), _level_map(r_tl.levels)
    dd.levels_identical = lm_r == lm_t
    if not dd.levels_identical:
        diffs = []
        for name in sorted(set(lm_r) | set(lm_t)):
            if lm_r.get(name) != lm_t.get(name):
                diffs.append(f"{name}: research={lm_r.get(name)} tradelab={lm_t.get(name)}")
        dd.level_detail = "; ".join(diffs)

    # --- zones ---
    zs_r, zs_t = _zone_set(r_res.zones), _zone_set(r_tl.zones)
    dd.zones_identical = zs_r == zs_t
    if not dd.zones_identical:
        dd.zone_detail = (
            f"research_only={sorted(zs_r - zs_t)} tradelab_only={sorted(zs_t - zs_r)}"
        )

    # --- touches ---
    keys_r = {_touch_key(t) for t in r_res.touches}
    keys_t = {_touch_key(t) for t in r_tl.touches}
    matched = keys_r & keys_t
    dd.touches_research = len(r_res.touches)
    dd.touches_tradelab = len(r_tl.touches)
    dd.touches_matched = len(matched)
    dd.touches_differing = len(keys_r ^ keys_t)
    dd.ny_rth_touches = len(r_res.ny_rth_touch_keys | r_tl.ny_rth_touch_keys)
    if keys_r != keys_t:
        dd.touch_detail = (
            f"research_only={sorted(keys_r - keys_t)} tradelab_only={sorted(keys_t - keys_r)}"
        )

    # --- honest survive/drop partition (engine-v2 decision-time rule) ---
    # Under the honest rule a detected touch only yields a label if its decision_ts
    # is before the flatten/cutoff AND a fill + forward bars exist. The survive set
    # (keys with a tradeable outcome) must be the SAME across both bar sets.
    surv_r = set(r_res.labels)
    surv_t = set(r_tl.labels)
    dd.labeled_research = len(surv_r)
    dd.labeled_tradelab = len(surv_t)
    dd.dropped_research = len(r_res.dropped)
    dd.dropped_tradelab = len(r_tl.dropped)
    dd.survive_set_identical = surv_r == surv_t
    if not dd.survive_set_identical:
        dd.survive_detail = (
            f"research_only={sorted(surv_r - surv_t)} tradelab_only={sorted(surv_t - surv_r)}"
        )

    # --- labels (over touches that SURVIVED the honest rule on BOTH sides) ---
    labeled_matched = surv_r & surv_t
    label_flips = 0
    flip_examples = []
    for key in labeled_matched:
        lr, lt = r_res.labels[key], r_tl.labels[key]
        if lr.label != lt.label:
            label_flips += 1
            if len(flip_examples) < 5:
                flip_examples.append(f"{key}: research={lr.label} tradelab={lt.label}")
    dd.label_flips = label_flips
    dd.labels_identical = label_flips == 0
    if flip_examples:
        dd.label_detail = "; ".join(flip_examples)

    # class balance over the research side's surviving labels (both sides identical
    # when survive_set_identical & no label flips). Reported for the re-anchor shift.
    cb: dict = {}
    for key in surv_r:
        lab = r_res.labels[key].label
        cb[lab] = cb.get(lab, 0) + 1
    dd.class_balance = cb

    # --- features (over surviving matched touches) ---
    worst: dict = {}
    feat_diff_examples = []
    for key in labeled_matched:
        fr, ft = r_res.features[key], r_tl.features[key]
        for fname in FEATURE_NAMES:
            if not _feat_eq(fr[fname], ft[fname]):
                a, b = fr[fname], ft[fname]
                fa = 0.0 if (a is None or np.isnan(float(a))) else float(a)
                fb = 0.0 if (b is None or np.isnan(float(b))) else float(b)
                d = abs(fa - fb)
                mx, n = worst.get(fname, (0.0, 0))
                worst[fname] = (max(mx, d), n + 1)
                if len(feat_diff_examples) < 8:
                    feat_diff_examples.append(f"{fname}@{key[2]}: research={a} tradelab={b}")
    dd.features_identical = len(worst) == 0
    dd.feature_worst = worst
    if feat_diff_examples:
        dd.feature_detail = "; ".join(feat_diff_examples)

    return dd


# ── table / report ──────────────────────────────────────────────────────────
DEFAULT_DAYS = ["2025-07-15", "2025-07-07", "2025-07-11"]
EXTRA_DAYS = [
    "2025-07-09", "2025-07-10", "2025-07-13", "2025-07-14",
    "2025-07-16", "2025-07-17", "2025-07-18",
]


def _fmt_day(dd: DayDiff) -> str:
    if dd.skip:
        return f"  {dd.day}: SKIP ({dd.reason})"
    lines = [
        f"  {dd.day}: research_bars={dd.research_bars} tradelab_bars={dd.tradelab_bars}",
        f"      levels   identical={dd.levels_identical}"
        + (f"  [{dd.level_detail}]" if not dd.levels_identical else ""),
        f"      zones    identical={dd.zones_identical}"
        + (f"  [{dd.zone_detail}]" if not dd.zones_identical else ""),
        f"      touches  research={dd.touches_research} tradelab={dd.touches_tradelab} "
        f"matched={dd.touches_matched} differing={dd.touches_differing} "
        f"ny_rth_eligible={dd.ny_rth_touches}"
        + (f"  [{dd.touch_detail}]" if dd.touches_differing else ""),
        f"      honest   labeled(research={dd.labeled_research} tradelab={dd.labeled_tradelab}) "
        f"dropped(research={dd.dropped_research} tradelab={dd.dropped_tradelab}) "
        f"survive_set_identical={dd.survive_set_identical}"
        + (f"  [{dd.survive_detail}]" if not dd.survive_set_identical else ""),
        f"      labels   identical={dd.labels_identical} flips={dd.label_flips} "
        f"class_balance={dd.class_balance}"
        + (f"  [{dd.label_detail}]" if dd.label_flips else ""),
        f"      features identical={dd.features_identical}"
        + (f"  worst={dd.feature_worst}  [{dd.feature_detail}]" if not dd.features_identical else ""),
    ]
    return "\n".join(lines)


def run(days: list[str]) -> list[DayDiff]:
    results: list[DayDiff] = []
    for day in days:
        results.append(diff_day(day))
    return results


def main():
    import warnings

    warnings.simplefilter("ignore")
    days = list(DEFAULT_DAYS)
    if "--extended" in sys.argv:
        days = days + [d for d in EXTRA_DAYS if d not in days]
    print("PHASE 4f Part 2 — RESEARCH vs TRADE-LAB decision-layer diff (SAME 147t trade-price bar def)")
    print("ENGINE v3 honest decision-time labeling (entry=trade price at touch+%dm; "
          "flatten=%s; forward=(decision,%s])" % (DECISION_OFFSET_MIN, FLATTEN_TIME, RTH_CUTOFF))
    print(f"window per day = [prev 18:00 ET, day 18:00 ET); tick={TICK_SIZE}; tf={TICK_COUNT}\n")
    results = run(days)
    ran = 0
    any_label_flip = False
    any_touch_diff = False
    any_feature_diff = False
    any_survive_diff = False
    agg_cb: dict = {}
    for dd in results:
        print(_fmt_day(dd))
        if dd.skip:
            continue
        ran += 1
        any_label_flip |= dd.label_flips > 0
        any_touch_diff |= dd.touches_differing > 0
        any_feature_diff |= not dd.features_identical
        any_survive_diff |= not dd.survive_set_identical
        for lab, n in dd.class_balance.items():
            agg_cb[lab] = agg_cb.get(lab, 0) + n
    total = sum(agg_cb.values())
    print(f"\ndays_run={ran}")
    print("aggregate class balance (honest decision-time labels, surviving touches):")
    for lab in sorted(agg_cb):
        n = agg_cb[lab]
        pct = (100.0 * n / total) if total else 0.0
        print(f"    {lab}: {n} ({pct:.1f}%)")
    print(f"    total labeled = {total}")
    if any_label_flip or any_touch_diff or any_survive_diff:
        verdict = "DRIFT (label flip / touch diff / survive-set diff across bar sets)"
    elif any_feature_diff:
        verdict = "ALIGNED (no label flips / touch diffs / survive-set diffs; feature diffs below eps — see worst)"
    else:
        verdict = "ALIGNED (zones/touches/features/labels identical across both bar sets under the honest v3 rule)"
    print(f"VERDICT: {verdict}")
    return results


if __name__ == "__main__":
    main()
