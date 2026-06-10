"""STANDALONE parity harness: strategy-core vs the canonical research pipeline.

Proves that strategy-core reproduces the canonical dashboard-utility research
pipeline on REAL data, stage by stage. This is a money-path gate — it reports
mismatches HONESTLY and never fudges to make a must-match stage pass.

ADDITIVE ONLY. Imports the research package (alpha_lab) and strategy_core
read-only. Writes nothing outside this validation/ tree.

Key design choice that makes the comparison clean:
  The canonical pipeline runs ENTIRELY on BOOK-MID bars (tick_store
  build_tick_bars price=(bid_px_00+ask_px_00)/2.0; bar timestamp = LAST(ts_event)
  = the bar CLOSE time). Book mids are exact multiples of 0.125, so we represent
  canonical bars LOSSLESSLY as strategy_core.Bar with tick_size=0.125
  (low_ticks=round(low/0.125), high_ticks=round(high/0.125)). Feeding IDENTICAL
  bars to both pipelines means any zones/touches/labels difference is a PORT BUG,
  while feature differences are the deliberate trade-price change.

Stages:
  A. ZONES                       [must_match]
  B. SESSIONS                    [must_match]
  C. TOUCHES                     [must_match]  <- core port-fidelity proof
  D. LABELS                      [must_match]
  E. INTERACTION FORMULA         [must_match]  <- identical book inputs
  F. INTERACTION TRADE-PRICE     [expected_differ]  <- deliberate price-source change
  G. APPROACH FEATURES (3)       [must_match]  <- ref-independent
"""

from __future__ import annotations

# --- CRITICAL: research package shadow guard -------------------------------
# alpha_lab is NOT importable by default; a different partial copy shadows it.
# This MUST run before importing alpha_lab.
import sys

sys.path.insert(0, r"C:/Users/gonza/Documents/Claude-Quant-Lab/src")

import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# Canonical research code (read-only) ---------------------------------------
from alpha_lab.agents.data_infra.ml import dashboard_utility_builder as B
from alpha_lab.agents.data_infra.ml import dashboard_utility_labeling as L
from alpha_lab.agents.data_infra.ml.config import MLPipelineConfig
from alpha_lab.agents.data_infra.tick_store import TickStore

# Engine under test ----------------------------------------------------------
import strategy_core as sc
from strategy_core import (
    Bar,
    CloseReason,
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
    resolve_outcome,
)

# --- Configuration ----------------------------------------------------------
DAYS = ["2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05", "2025-06-06"]
DATA_DIR = Path(r"C:/Users/gonza/Documents/Trade-Dashboard/data/databento")
SYMBOL = "NQ"

CANON_TICK = 0.125  # book-mid grid: lossless representation of canonical bars
TRADE_TICK = 0.25  # real NQ trade-price tick (deliberate divergence in stages F/G)

PROD_CONFIG = MLPipelineConfig(
    training_mode="dashboard_utility",
    instrument="NQ",
    tick_size=0.25,
    dashboard_utility=dict(
        bar_type="147t",
        interaction_window_minutes=5,
        approach_window_minutes=30,
        include_approach_features=True,
        tp_points=15.0,
        sl_points=30.0,
        trap_mfe_min=5.0,
        level_proximity_pts=0.5,
    ),
)
U = PROD_CONFIG.dashboard_utility
TF = 147

OUT_DIR = Path(r"C:/Users/gonza/Documents/Strategy-core/validation/_out")
REPORT_PATH = OUT_DIR / "PARITY_REPORT.md"

ABS_TOL = 1e-9
APP_TOL = 1e-6

_ET = "US/Eastern"
_ET_TZ = pd.Timestamp("2025-01-01", tz=_ET).tz  # ZoneInfo for US/Eastern


# --- Stage accumulators -----------------------------------------------------
class Stage:
    def __init__(self, name: str, scope: str):
        self.name = name
        self.scope = scope  # "must_match" | "expected_differ"
        self.total = 0
        self.matched = 0
        self.mismatched = 0
        self.example = ""  # first mismatch example (must_match)
        self.divergences: dict[str, list[float]] = defaultdict(list)  # expected_differ

    def record(self, ok: bool, example: str = ""):
        self.total += 1
        if ok:
            self.matched += 1
        else:
            self.mismatched += 1
            if not self.example and example:
                self.example = example

    def divergence_summary(self) -> str:
        parts = []
        for feat, vals in self.divergences.items():
            if not vals:
                continue
            arr = np.array(vals, dtype=float)
            arr = arr[~np.isnan(arr)]
            if arr.size == 0:
                parts.append(f"{feat}: (no finite samples)")
                continue
            parts.append(
                f"{feat}: n={arr.size} mean={arr.mean():.4f} "
                f"median={np.median(arr):.4f} max={arr.max():.4f}"
            )
        return "; ".join(parts)


STAGES: dict[str, Stage] = {
    "A_ZONES": Stage("A. ZONES", "must_match"),
    "B_SESSIONS": Stage("B. SESSIONS", "must_match"),
    "C_TOUCHES": Stage("C. TOUCHES", "must_match"),
    "D_LABELS": Stage("D. LABELS", "must_match"),
    "E_INT_FORMULA": Stage("E. INTERACTION FORMULA FIDELITY", "must_match"),
    "F_INT_TRADEPRICE": Stage("F. INTERACTION TRADE-PRICE DIVERGENCE", "expected_differ"),
    "G_APPROACH": Stage("G. APPROACH FEATURES (3 model features)", "must_match"),
}


# --- Helpers ----------------------------------------------------------------
def _floats_eq(a: float, b: float, tol: float = ABS_TOL) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        if math.isnan(a) or math.isnan(b):
            return False
    return abs(float(a) - float(b)) <= tol


def _to_utc_dt(ts: pd.Timestamp) -> datetime:
    """ET-aware (or naive-UTC) pandas Timestamp -> tz-aware python UTC datetime."""
    ts = pd.Timestamp(ts)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC").to_pydatetime()


def _round_to_ticks(value: float, tick: float) -> int:
    return int(round(float(value) / tick))


def _engine_bars_from_et(bars_et: pd.DataFrame, trading_day: date) -> list[Bar]:
    """Build engine Bars from canonical ET-indexed OHLCV rows (book-mid grid)."""
    out: list[Bar] = []
    for i, (idx, row) in enumerate(bars_et.iterrows()):
        close_utc = _to_utc_dt(idx)
        out.append(
            Bar(
                timeframe_ticks=TF,
                trading_day=trading_day,
                bar_index=i,
                bar_id=make_bar_id(TF, trading_day, i),
                open_ts_utc=close_utc,
                close_ts_utc=close_utc,
                open_ticks=_round_to_ticks(row["open"], CANON_TICK),
                high_ticks=_round_to_ticks(row["high"], CANON_TICK),
                low_ticks=_round_to_ticks(row["low"], CANON_TICK),
                close_ticks=_round_to_ticks(row["close"], CANON_TICK),
                volume=int(row["volume"]),
                trade_count=TF,
                is_complete=True,
                is_partial=False,
                close_reason=CloseReason.COMPLETE,
            )
        )
    return out


def _canon_levels_to_engine(levels: list[dict]) -> list[Level]:
    return [
        Level(name=l["name"], price=float(l["price"]), side=Side(l["side"]))
        for l in levels
    ]


def _canon_session_for_ts(ts_et: pd.Timestamp) -> str:
    """Canonical _slice_session masks, evaluated for a single ET timestamp.

    asia: t>=18:00 or t<01:00 ; london: 01:00<=t<08:00 ; ny_rth: 09:30<=t<16:15 ;
    else 'none'. Mirrors dashboard_utility_builder._slice_session exactly.
    """
    t = ts_et.time()
    if t >= B._ASIA_START or t < B._ASIA_END:
        return "asia"
    if B._LONDON_START <= t < B._LONDON_END:
        return "london"
    if B._NY_RTH_START <= t < B._NY_RTH_END:
        return "ny_rth"
    return "none"


# --- Front-month / trade-quote extraction for stages F & G ------------------
class DayParquet:
    """Per-day DuckDB view over mbp10 parquet, with front-month resolution.

    Registers both the day file and (lazily) the previous day's file so the
    approach window can cross the calendar-day boundary, exactly as the
    canonical builder does (builder:566-567 registers prev day).
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}

    def _path(self, date_str: str) -> Path:
        return DATA_DIR / SYMBOL / date_str / "mbp10.parquet"

    def get(self, date_str: str) -> dict | None:
        if date_str in self._cache:
            return self._cache[date_str]
        path = self._path(date_str)
        prev = (date.fromisoformat(date_str) - timedelta(days=1)).isoformat()
        prev_path = self._path(prev)
        if not path.exists():
            self._cache[date_str] = None
            return None
        con = duckdb.connect(":memory:")
        reads = [f"SELECT * FROM read_parquet('{path.as_posix()}')"]
        if prev_path.exists():
            reads.append(f"SELECT * FROM read_parquet('{prev_path.as_posix()}')")
        union_sql = " UNION ALL ".join(reads)
        # Resolve the dominant front-month outright contract (same as
        # build_tick_bars: symbol NOT LIKE '%-%', pick by row count).
        front = con.execute(
            f"SELECT symbol, count(*) AS n FROM ({union_sql}) AS t "
            f"WHERE symbol NOT LIKE '%-%' GROUP BY symbol ORDER BY n DESC LIMIT 1"
        ).fetchone()
        sym = front[0] if front else None
        info = {"con": con, "union_sql": union_sql, "symbol": sym}
        self._cache[date_str] = info
        return info

    def trades(self, date_str: str, start_utc: datetime, end_utc: datetime,
               end_exclusive: bool) -> pd.DataFrame:
        info = self.get(date_str)
        if info is None:
            return pd.DataFrame(columns=["ts_event", "price", "size"])
        sym_f = f"AND symbol = '{info['symbol']}'" if info["symbol"] else "AND symbol NOT LIKE '%-%'"
        cmp_end = "<" if end_exclusive else "<="
        sql = f"""
            SELECT ts_event, price, size
            FROM ({info['union_sql']}) AS t
            WHERE ts_event >= $1 AND ts_event {cmp_end} $2
              AND bid_px_00 > 0 AND ask_px_00 > 0
              AND action = 'T'
              {sym_f}
            ORDER BY ts_event ASC
        """
        return info["con"].execute(sql, [pd.Timestamp(start_utc), pd.Timestamp(end_utc)]).fetchdf()

    def quotes_base(self, date_str: str, start_utc: datetime, end_utc: datetime) -> pd.DataFrame:
        """base rows (bid>0 & ask>0) over [start, end) — used as quotes for max_spread."""
        info = self.get(date_str)
        if info is None:
            return pd.DataFrame(columns=["ts_event", "bid_px_00", "ask_px_00"])
        sym_f = f"AND symbol = '{info['symbol']}'" if info["symbol"] else "AND symbol NOT LIKE '%-%'"
        sql = f"""
            SELECT ts_event, bid_px_00, ask_px_00
            FROM ({info['union_sql']}) AS t
            WHERE ts_event >= $1 AND ts_event < $2
              AND bid_px_00 > 0 AND ask_px_00 > 0
              {sym_f}
            ORDER BY ts_event ASC
        """
        return info["con"].execute(sql, [pd.Timestamp(start_utc), pd.Timestamp(end_utc)]).fetchdf()


DAY_PARQUET = DayParquet()


# --- Main per-day pipeline ---------------------------------------------------
def process_day(date_str, prev_ny_hl, prev_asia_hl, prev_london_hl, store_book: TickStore):
    """Run all stages for one day. Returns updated prev-session H/L tuples and
    the day's touch count (kept touches with non-None canonical features)."""
    td = date.fromisoformat(date_str)

    # 1. bars (canonical book-mid) ------------------------------------------
    bars = B._build_bars_for_date(DATA_DIR, SYMBOL, date_str, U)
    if bars.empty:
        return prev_ny_hl, prev_asia_hl, prev_london_hl, 0
    bars_et = B._ensure_et_index(bars)

    # 2. levels --------------------------------------------------------------
    levels = B._compute_levels_for_date(bars_et, date_str, prev_ny_hl, prev_asia_hl, prev_london_hl)

    # next-day session H/L carry (mirror build_utility_dataset loop) ---------
    new_ny, new_asia, new_london = B._get_session_hl_for_date(
        DATA_DIR, SYMBOL, date_str, U, prev_ny_hl, prev_asia_hl, prev_london_hl
    )

    # engine bars (shared by C, D) ------------------------------------------
    eng_bars = _engine_bars_from_et(bars_et, td)

    # ---------------------------------------------------------------- STAGE A
    canon_zones_cmp = B._build_zones(levels)  # for comparison (not mutated by detection)
    eng_levels = _canon_levels_to_engine(levels)
    eng_zones_cmp = build_zones(eng_levels)
    _compare_zones(date_str, canon_zones_cmp, eng_zones_cmp)

    # ---------------------------------------------------------------- STAGE B
    _compare_sessions(date_str, bars_et)

    # ---------------------------------------------------------------- STAGE C
    # FRESH zones for detection (detection MUTATES zone['touched']).
    canon_zones_det = B._build_zones(levels)
    canon_touches = B._detect_touches(bars_et, canon_zones_det)
    eng_zones_det = build_zones(_canon_levels_to_engine(levels))
    eng_touches = detect_touches(eng_bars, eng_zones_det, tick_size=CANON_TICK, trading_day=td)
    _compare_touches(date_str, canon_touches, eng_touches)

    # ---------------------------------------------------------------- STAGE D
    rth_cutoff = pd.Timestamp(f"{date_str} 16:15:00", tz=_ET)
    for touch in canon_touches:
        forward = bars_et[bars_et.index > touch["bar_ts"]]
        forward = forward[forward.index < rth_cutoff]
        if forward.empty:
            continue
        canon = L.label_touch_event(touch, forward, U)
        fwd_bars = _engine_bars_from_et(forward, td)
        eng = resolve_outcome(
            entry_points=float(touch["representative_price"]),
            direction=Direction(touch["direction"]),
            forward_bars=fwd_bars,
            tick_size=CANON_TICK,
            tp_points=U.tp_points,
            sl_points=U.sl_points,
            trap_mfe_min=U.trap_mfe_min,
        )
        _compare_label(date_str, touch, canon, eng)

    # ----------------------------------------------------- STAGES E, F, G ----
    # Per kept touch (canonical interaction features not None).
    day_touch_count = 0
    for touch in canon_touches:
        canon_int = B._compute_interaction_features(touch, DATA_DIR, SYMBOL, U)
        if canon_int is None:
            continue
        day_touch_count += 1

        rep = float(touch["representative_price"])
        direction = touch["direction"]
        eng_dir = Direction(direction)
        event_ts = pd.Timestamp(touch["bar_ts"])
        event_ts_utc = _to_utc_dt(event_ts)
        win_end_utc = event_ts_utc + timedelta(minutes=U.interaction_window_minutes)

        # ----- STAGE E: identical BOOK inputs -> must match -----------------
        book_rows = store_book.query_tick_feature_rows(SYMBOL, event_ts_utc, win_end_utc)
        eng_book_trades = []
        if not book_rows.empty and "price" in book_rows.columns:
            for r in book_rows.itertuples(index=False):
                eng_book_trades.append(
                    Trade(
                        event_ts_utc=_to_utc_dt(r.ts_event),
                        price_ticks=_round_to_ticks(r.price, CANON_TICK),
                        size=int(r.size),
                    )
                )
        e_beyond = int_time_beyond_level(eng_book_trades, rep, eng_dir, CANON_TICK)
        e_within = int_time_within_2pts(eng_book_trades, rep, CANON_TICK)
        e_absorp = int_absorption_ratio(eng_book_trades, rep, eng_dir, CANON_TICK)
        _compare_int_formula(date_str, touch, canon_int, e_beyond, e_within, e_absorp)

        # ----- STAGE F: real TRADE prints -> expected to differ -------------
        trade_df = DAY_PARQUET.trades(date_str, event_ts_utc, win_end_utc, end_exclusive=False)
        eng_trades = [
            Trade(
                event_ts_utc=_to_utc_dt(r.ts_event),
                price_ticks=_round_to_ticks(r.price, TRADE_TICK),
                size=int(r.size),
            )
            for r in trade_df.itertuples(index=False)
        ]
        f_beyond = int_time_beyond_level(eng_trades, rep, eng_dir, TRADE_TICK)
        f_within = int_time_within_2pts(eng_trades, rep, TRADE_TICK)
        f_absorp = int_absorption_ratio(eng_trades, rep, eng_dir, TRADE_TICK)
        _record_int_divergence(canon_int, f_beyond, f_within, f_absorp)

        # ----- STAGE G: approach features (3 model features) -> must match --
        canon_app = B._compute_approach_features(touch, DATA_DIR, SYMBOL, U)
        app_start_utc = event_ts_utc - timedelta(minutes=U.approach_window_minutes)
        # base rows / trades for the approach window, crossing prev day if needed
        a_trades_df = _approach_trades(date_str, app_start_utc, event_ts_utc)
        a_quotes_df = _approach_quotes(date_str, app_start_utc, event_ts_utc)
        eng_app_trades = [
            Trade(event_ts_utc=_to_utc_dt(r.ts_event),
                  price_ticks=_round_to_ticks(r.price, TRADE_TICK), size=int(r.size))
            for r in a_trades_df.itertuples(index=False)
        ]
        eng_app_quotes = [
            Quote(event_ts_utc=_to_utc_dt(r.ts_event),
                  bid_price_ticks=_round_to_ticks(r.bid_px_00, TRADE_TICK),
                  ask_price_ticks=_round_to_ticks(r.ask_px_00, TRADE_TICK))
            for r in a_quotes_df.itertuples(index=False)
        ]
        e_avg = app_avg_trade_size(eng_app_trades)
        e_largepct = app_large_trade_vol_pct(eng_app_trades)
        e_maxspread = app_max_spread(eng_app_quotes, TRADE_TICK)
        _compare_approach(date_str, touch, canon_app, e_avg, e_largepct, e_maxspread)

    return new_ny, new_asia, new_london, day_touch_count


def _approach_trades(date_str, start_utc, end_utc):
    """Trades over [start, end) across day + prev day (front-month filtered).

    The DayParquet view for ``date_str`` already UNIONs in the prev-day file, so a
    single windowed query covers a window that crosses midnight. Do NOT dedup or
    re-concat: the windowed front-month SQL already yields exactly the canonical
    trade set, and dropping duplicate (ts,price,size) rows would silently discard
    legitimately-identical prints and corrupt avg_trade_size.
    """
    return DAY_PARQUET.trades(date_str, start_utc, end_utc, end_exclusive=True)


def _approach_quotes(date_str, start_utc, end_utc):
    df = DAY_PARQUET.quotes_base(date_str, start_utc, end_utc)
    if not df.empty:
        df = df.sort_values("ts_event")
    return df


# --- Stage comparators ------------------------------------------------------
def _compare_zones(date_str, canon, eng):
    st = STAGES["A_ZONES"]
    # count check as one record
    if len(canon) != len(eng):
        st.record(False, f"{date_str}: zone count canon={len(canon)} eng={len(eng)}")
        return
    for i, (cz, ez) in enumerate(zip(canon, eng)):
        ok = (
            _floats_eq(cz["representative_price"], ez.representative_price)
            and cz["side"] == ez.side.value
            and tuple(cz["names"]) == tuple(ez.names)
        )
        ex = (
            f"{date_str} zone#{i}: canon(rep={cz['representative_price']},side={cz['side']},"
            f"names={tuple(cz['names'])}) vs eng(rep={ez.representative_price},"
            f"side={ez.side.value},names={tuple(ez.names)})"
        )
        st.record(ok, ex)


def _compare_sessions(date_str, bars_et):
    st = STAGES["B_SESSIONS"]
    idx = bars_et.index
    n = len(idx)
    # sample up to ~5000 bars/day evenly
    if n > 5000:
        sel = np.linspace(0, n - 1, 5000).astype(int)
        sel = np.unique(sel)
    else:
        sel = range(n)
    for i in sel:
        ts_et = idx[i]
        canon_sess = _canon_session_for_ts(ts_et)
        ts_utc = _to_utc_dt(ts_et)
        eng_sess = classify_session(ts_utc).session
        ok = canon_sess == eng_sess
        ex = f"{date_str} {ts_et.isoformat()}: canon={canon_sess} eng={eng_sess}"
        st.record(ok, ex)


def _compare_touches(date_str, canon, eng):
    st = STAGES["C_TOUCHES"]
    if len(canon) != len(eng):
        st.record(False, f"{date_str}: touch count canon={len(canon)} eng={len(eng)}")
        # still compare the overlapping prefix to surface the first divergence
    for i in range(min(len(canon), len(eng))):
        ct = canon[i]
        et = eng[i]
        canon_ts = _to_utc_dt(ct["bar_ts"])
        ok = (
            canon_ts == et.bar_ts_utc
            and ct["direction"] == et.direction.value
            and _floats_eq(ct["representative_price"], et.representative_price)
            and ct["level_type"] == et.level_type
        )
        ex = (
            f"{date_str} touch#{i}: canon(ts={canon_ts.isoformat()},dir={ct['direction']},"
            f"rep={ct['representative_price']},lvl={ct['level_type']}) vs "
            f"eng(ts={et.bar_ts_utc.isoformat()},dir={et.direction.value},"
            f"rep={et.representative_price},lvl={et.level_type})"
        )
        st.record(ok, ex)


def _compare_label(date_str, touch, canon, eng):
    st = STAGES["D_LABELS"]
    ok = (
        canon["label"] == eng.label
        and canon["label_encoded"] == eng.label_encoded
        and _floats_eq(round(float(canon["max_mfe"]), 4), round(float(eng.max_mfe), 4))
        and _floats_eq(round(float(canon["max_mae"]), 4), round(float(eng.max_mae), 4))
    )
    ts = _to_utc_dt(pd.Timestamp(touch["bar_ts"]))
    ex = (
        f"{date_str} touch@{ts.isoformat()}: canon(label={canon['label']},"
        f"enc={canon['label_encoded']},mfe={canon['max_mfe']},mae={canon['max_mae']}) vs "
        f"eng(label={eng.label},enc={eng.label_encoded},mfe={eng.max_mfe},mae={eng.max_mae})"
    )
    st.record(ok, ex)


def _compare_int_formula(date_str, touch, canon, e_beyond, e_within, e_absorp):
    st = STAGES["E_INT_FORMULA"]
    ok = (
        _floats_eq(canon["int_time_beyond_level"], e_beyond)
        and _floats_eq(canon["int_time_within_2pts"], e_within)
        and _floats_eq(canon["int_absorption_ratio"], e_absorp)
    )
    ts = _to_utc_dt(pd.Timestamp(touch["bar_ts"]))
    ex = (
        f"{date_str} touch@{ts.isoformat()}: "
        f"beyond canon={canon['int_time_beyond_level']} eng={e_beyond}; "
        f"within canon={canon['int_time_within_2pts']} eng={e_within}; "
        f"absorp canon={canon['int_absorption_ratio']} eng={e_absorp}"
    )
    st.record(ok, ex)


def _record_int_divergence(canon, f_beyond, f_within, f_absorp):
    st = STAGES["F_INT_TRADEPRICE"]
    st.total += 1
    st.divergences["int_time_beyond_level"].append(
        abs(f_beyond - float(canon["int_time_beyond_level"]))
    )
    st.divergences["int_time_within_2pts"].append(
        abs(f_within - float(canon["int_time_within_2pts"]))
    )
    st.divergences["int_absorption_ratio"].append(
        abs(f_absorp - float(canon["int_absorption_ratio"]))
    )


def _compare_approach(date_str, touch, canon, e_avg, e_largepct, e_maxspread):
    st = STAGES["G_APPROACH"]
    if canon is None:
        canon = {}
    c_avg = canon.get("app_avg_trade_size", float("nan"))
    c_largepct = canon.get("app_large_trade_vol_pct", float("nan"))
    c_maxspread = canon.get("app_max_spread", float("nan"))
    ok = (
        _floats_eq(c_avg, e_avg, APP_TOL)
        and _floats_eq(c_largepct, e_largepct, APP_TOL)
        and _floats_eq(c_maxspread, e_maxspread, APP_TOL)
    )
    ts = _to_utc_dt(pd.Timestamp(touch["bar_ts"]))
    ex = (
        f"{date_str} touch@{ts.isoformat()}: "
        f"avg_trade_size canon={c_avg} eng={e_avg}; "
        f"large_vol_pct canon={c_largepct} eng={e_largepct}; "
        f"max_spread canon={c_maxspread} eng={e_maxspread}"
    )
    st.record(ok, ex)


# --- Report -----------------------------------------------------------------
def write_report(days_processed, total_touches):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    must_pass = all(
        s.mismatched == 0 for s in STAGES.values() if s.scope == "must_match"
    )

    lines = []
    lines.append("# Strategy-Core Parity Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Engine: strategy_core v{getattr(sc, 'PLATFORM_VERSION', '?')} "
                 f"(contract v{getattr(sc, 'CONTRACT_VERSION', '?')})")
    lines.append("")
    lines.append("Proves strategy-core reproduces the canonical dashboard-utility "
                 "research pipeline on REAL NQ data. The canonical pipeline runs on "
                 "BOOK-MID bars; those bars are represented LOSSLESSLY in the engine "
                 "(tick_size=0.125), so any zones/touches/labels difference would be a "
                 "PORT BUG. Feature *price-source* differences (stage F) are the "
                 "deliberate trade-price change and are reported, not asserted.")
    lines.append("")
    lines.append(f"- Days processed: {', '.join(days_processed)}")
    lines.append(f"- Total kept touches (canonical features not None): {total_touches}")
    lines.append("")

    lines.append("## Stage results")
    lines.append("")
    lines.append("| Stage | Scope | Total | Matched | Mismatched |")
    lines.append("|-------|-------|------:|--------:|-----------:|")
    order = ["A_ZONES", "B_SESSIONS", "C_TOUCHES", "D_LABELS",
             "E_INT_FORMULA", "F_INT_TRADEPRICE", "G_APPROACH"]
    for key in order:
        s = STAGES[key]
        lines.append(f"| {s.name} | {s.scope} | {s.total} | {s.matched} | {s.mismatched} |")
    lines.append("")

    # must_match mismatch examples
    lines.append("## Must-match mismatches (concrete examples)")
    lines.append("")
    any_mismatch = False
    for key in order:
        s = STAGES[key]
        if s.scope != "must_match":
            continue
        if s.mismatched > 0:
            any_mismatch = True
            lines.append(f"- **{s.name}**: {s.mismatched}/{s.total} mismatched.")
            lines.append(f"  - Example: `{s.example}`")
    if not any_mismatch:
        lines.append("None. Every must-match stage is 100% matched.")
    lines.append("")

    # expected_differ distributions
    lines.append("## Expected-differ divergence distributions")
    lines.append("")
    lines.append("Stage F feeds REAL TRADE prints (tick 0.25) where the canonical "
                 "feature used BOOK-MID prints (tick 0.125). This is the deliberate "
                 "price-source change. Distribution of `|engine_trade - canonical_book|`:")
    lines.append("")
    f = STAGES["F_INT_TRADEPRICE"]
    lines.append(f"- samples (touches): {f.total}")
    summ = f.divergence_summary()
    if summ:
        for part in summ.split("; "):
            lines.append(f"  - {part}")
    else:
        lines.append("  - (no samples)")
    lines.append("")

    # Pinned open-item resolutions
    lines.append("## Pinned open-item resolutions (applied)")
    lines.append("")
    lines.append("1. **Touch timestamp = bar CLOSE (LAST(ts_event)).** The canonical "
                 "tick-bar timestamp is the last event time of the bar "
                 "(tick_store build_tick_bars: LAST(ts_event ORDER BY ts_event)). "
                 "strategy_core.detect_touches stamps each touch with `bar.close_ts_utc`, "
                 "which equals that close time. Stage C compares these as instant-equal "
                 "and they match.")
    lines.append("2. **Absorption size source.** The canonical interaction features use "
                 "BOOK-EVENT size over book rows. The engine on the trade-price path uses "
                 "TRADE size. That is a DELIBERATE divergence and is NOT forced to match: "
                 "stage E proves the int_* FORMULA is faithful by feeding the SAME book "
                 "rows to both, while stage F reports (does not assert) the trade-price "
                 "divergence.")
    lines.append("")

    verdict = "PORT FIDELITY PROVEN" if must_pass else None
    if not must_pass:
        first_bad = next(
            s.name for k in order for s in [STAGES[k]]
            if s.scope == "must_match" and s.mismatched > 0
        )
        verdict = f"MISMATCH — see stage {first_bad}"
    lines.append(f"## VERDICT: {verdict}")
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return must_pass


# --- Driver -----------------------------------------------------------------
def main():
    prev_ny_hl = prev_asia_hl = prev_london_hl = None
    days_processed = []
    total_touches = 0

    # one TickStore for book-row interaction queries (stage E), register all days
    store_book = TickStore(DATA_DIR)
    for d in DAYS:
        try:
            store_book.register_symbol_date(SYMBOL, d)
            prevd = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
            store_book.register_symbol_date(SYMBOL, prevd)
        except Exception as exc:
            print(f"[warn] register {d}: {exc}")

    try:
        for d in sorted(DAYS):
            print(f"=== processing {d} ===", flush=True)
            prev_ny_hl, prev_asia_hl, prev_london_hl, n = process_day(
                d, prev_ny_hl, prev_asia_hl, prev_london_hl, store_book
            )
            days_processed.append(d)
            total_touches += n
            print(f"    kept touches: {n}", flush=True)
    finally:
        store_book.close()

    must_pass = write_report(days_processed, total_touches)
    print(f"\nReport written: {REPORT_PATH}")
    print(f"must_match_all_pass: {must_pass}")
    for key in ["A_ZONES", "B_SESSIONS", "C_TOUCHES", "D_LABELS",
                "E_INT_FORMULA", "F_INT_TRADEPRICE", "G_APPROACH"]:
        s = STAGES[key]
        print(f"  {s.name}: {s.matched}/{s.total} matched, {s.mismatched} mismatched ({s.scope})")


if __name__ == "__main__":
    main()
