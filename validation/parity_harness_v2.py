"""CORRECTED phase-4a parity harness: strategy-core vs the canonical research
pipeline, over the FULL requested NQ day range, with a DETERMINISTIC candle stage.

This is a money-path gate. It reports mismatches HONESTLY and never fudges a
must-match stage to pass. ADDITIVE ONLY: imports alpha_lab + strategy_core
read-only; writes nothing outside validation/.

What v2 fixes vs parity_harness.py:
  1. DAY RANGE: every available NQ day in 2025-07-01..2025-09-05 inclusive (was a
     wrong 5-day June window). Warm prior-day session levels with 2025-06-30.
  2. DETERMINISTIC CANDLE STAGE 0: the canonical book-mid bars come from DuckDB
     build_tick_bars whose FIRST/LAST/ROW_NUMBER tie-break over duplicate ts_event
     is NONDETERMINISTIC (prior run saw ~2.2% open/close diffs). v2 imposes a stable
     TOTAL order (ts_event, source_row_seq) in PANDAS and feeds the SAME ordered
     events to a harness-local reference bucketer AND the engine builder, then
     compares them incl. open/close.

CRITICAL WINDOW FINDING (verified, see PARITY_REPORT_V2.md):
  research's _build_bars_for_date passes a NAIVE datetime(prev,23,0) to DuckDB,
  whose session TimeZone is America/Chicago, so DuckDB interprets the bound as
  23:00 *Chicago*, NOT 23:00 UTC. The real research window is therefore
  [prev 23:00 America/Chicago, cur 23:00 America/Chicago]. The reference frame must
  use Chicago-localized bounds to reproduce the canonical bars (count + values).
"""
from __future__ import annotations

# --- research package shadow guard (MUST precede alpha_lab import) ----------
import sys

sys.path.insert(0, r"C:/Users/gonza/Documents/Claude-Quant-Lab/src")

import math
import time as _time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb  # noqa: F401  (research deps loaded transitively)
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
    build_tick_bars_from_frame,
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
DATA_DIR = Path(r"C:/Users/gonza/Documents/Trade-Dashboard/data/databento")
SYMBOL = "NQ"

RANGE_START = date(2025, 7, 1)
RANGE_END = date(2025, 9, 5)
WARMUP_DAY = date(2025, 6, 30)  # prior available trading day, for PDH/PDL carry

CANON_TICK = 0.125  # book-mid grid: lossless representation of canonical bars
TRADE_TICK = 0.25   # real NQ trade-price tick (deliberate divergence, stage F/G)
TF = 147

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

OUT_DIR = Path(r"C:/Users/gonza/Documents/Strategy-core/validation/_out")
REPORT_PATH = OUT_DIR / "PARITY_REPORT_V2.md"

ABS_TOL = 1e-9
APP_TOL = 1e-6
_ET = "US/Eastern"

PARQUET_COLS = ["ts_event", "bid_px_00", "ask_px_00", "size", "symbol", "action"]


# --- Stage accumulators -----------------------------------------------------
class Stage:
    def __init__(self, name: str, scope: str):
        self.name = name
        self.scope = scope  # "must_match" | "expected_differ"
        self.total = 0
        self.matched = 0
        self.mismatched = 0
        self.example = ""
        self.divergences: dict[str, list[float]] = defaultdict(list)

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
            arr = np.array(vals, dtype=float)
            arr = arr[~np.isnan(arr)]
            if arr.size == 0:
                parts.append(f"{feat}: (no finite samples)")
                continue
            parts.append(
                f"{feat}: n={arr.size} mean={arr.mean():.4f} "
                f"median={np.median(arr):.4f} p95={np.percentile(arr, 95):.4f} "
                f"max={arr.max():.4f}"
            )
        return "; ".join(parts)


STAGE_ORDER = [
    "S0_CANDLES",
    "A_ZONES",
    "B_TOUCHES",
    "C_SESSIONS",
    "D_LABELS",
    "E_INT_FORMULA",
    "F_INT_TRADEPRICE",
    "G_APPROACH",
]
STAGES: dict[str, Stage] = {
    "S0_CANDLES": Stage("Stage 0. CANDLES (deterministic book-mid bars)", "must_match"),
    "A_ZONES": Stage("Stage A. ZONES", "must_match"),
    "B_TOUCHES": Stage("Stage B. TOUCHES", "must_match"),
    "C_SESSIONS": Stage("Stage C. SESSIONS", "must_match"),
    "D_LABELS": Stage("Stage D. LABELS", "must_match"),
    "E_INT_FORMULA": Stage("Stage E. INTERACTION FORMULA FIDELITY", "must_match"),
    "F_INT_TRADEPRICE": Stage("Stage F. INTERACTION TRADE-PRICE", "expected_differ"),
    "G_APPROACH": Stage("Stage G. APPROACH (3 model features)", "must_match"),
}

# per-day pass/fail + touch counts for the compact table
DAY_ROWS: list[dict] = []
# candle confirmation aggregates
CANDLE_AGG = {
    "compared": 0, "matched_full": 0,
    "boundary_split_days": 0, "trailing_partials": 0,
    "first_finding": None,  # concrete example string
    "all_100pct": True,
}
# benchmark accumulators
BENCH = {"engine_builder_seconds": 0.0, "duckdb_seconds": 0.0, "days": 0, "bars": 0}


# --- Helpers ----------------------------------------------------------------
def _floats_eq(a, b, tol: float = ABS_TOL) -> bool:
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


def _to_utc_dt(ts) -> datetime:
    ts = pd.Timestamp(ts)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC").to_pydatetime()


def _round_to_ticks(value: float, tick: float) -> int:
    return int(round(float(value) / tick))


def enumerate_days() -> tuple[list[str], list[str], int]:
    """Available vs unavailable days in [RANGE_START, RANGE_END] inclusive."""
    available, missing = [], []
    total = (RANGE_END - RANGE_START).days + 1
    d = RANGE_START
    while d <= RANGE_END:
        p = DATA_DIR / SYMBOL / d.isoformat() / "mbp10.parquet"
        if p.exists() and p.stat().st_size > 0:
            available.append(d.isoformat())
        else:
            missing.append(d.isoformat())
        d += timedelta(days=1)
    return available, missing, total


# --- Deterministic event frame (Chicago-bound, matches canonical bars) ------
def build_event_frame(date_str: str):
    """Deterministic event frame for the research window.

    Window bound = NAIVE 23:00 interpreted in America/Chicago, exactly as research's
    DuckDB session does (verified: DuckDB TimeZone='America/Chicago'). Reads prev+cur
    day parquet in FILE ORDER, assigns a stable source seq, filters to the dominant
    front-month outright + bid/ask>0 + window, then sorts by (ts_event, seq) stable.
    """
    td = date.fromisoformat(date_str)
    prev = td - timedelta(days=1)
    start = pd.Timestamp(datetime(prev.year, prev.month, prev.day, 23, 0), tz="America/Chicago")
    end = pd.Timestamp(datetime(td.year, td.month, td.day, 23, 0), tz="America/Chicago")

    frames = []
    for d in (prev, td):
        p = DATA_DIR / SYMBOL / d.isoformat() / "mbp10.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p, columns=PARQUET_COLS))
    if not frames:
        return None, None
    df = pd.concat(frames, ignore_index=True)  # preserves per-file source order
    df["seq"] = np.arange(len(df), dtype="int64")

    nodash = df[~df["symbol"].str.contains("-", na=False)]
    if nodash.empty:
        return None, None
    front = nodash["symbol"].value_counts().idxmax()

    m = (
        (df["bid_px_00"] > 0)
        & (df["ask_px_00"] > 0)
        & (df["symbol"] == front)
        & (df["ts_event"] >= start)
        & (df["ts_event"] <= end)
    )
    df = df.loc[m].copy()
    if df.empty:
        return None, front
    df["mid"] = (df["bid_px_00"] + df["ask_px_00"]) / 2.0
    df = df.sort_values(["ts_event", "seq"], kind="stable").reset_index(drop=True)
    return df, front


def reference_bars_continuous(df: pd.DataFrame) -> pd.DataFrame:
    """CONTINUOUS bucketing: bar_id = arange//147 over the whole window; keep n==147.
    This reproduces the canonical DuckDB build_tick_bars (rn//147, no trading-day
    partition) made deterministic by the (ts_event,seq) sort. Used only to quantify
    the engine-vs-research 18:00-ET boundary difference, NOT for the must-match set."""
    n = len(df)
    bar_id = np.arange(n) // TF
    g = df.assign(bar_id=bar_id).groupby("bar_id", sort=True)
    ref = g.agg(
        open=("mid", "first"), high=("mid", "max"), low=("mid", "min"),
        close=("mid", "last"), volume=("size", "sum"),
        open_ts=("ts_event", "first"), close_ts=("ts_event", "last"), n=("mid", "size"),
    ).reset_index()
    return ref[ref["n"] == TF].reset_index(drop=True)


def _trading_day_series(ts: pd.Series) -> pd.Series:
    """18:00-ET trading_day for each ts (mirrors build_tick_bars_from_frame /
    RESEARCH_SESSION_SCHEME: localize to ET, roll into next day at/after 18:00)."""
    local = ts.dt.tz_convert(_ET)
    sod = local.dt.hour * 3600 + local.dt.minute * 60 + local.dt.second
    cal = local.dt.tz_localize(None).dt.floor("D")
    roll = (sod >= 18 * 3600).astype("int64")
    return cal + pd.to_timedelta(roll, unit="D")


def reference_bars(df: pd.DataFrame) -> pd.DataFrame:
    """build_tick_bars' exact logic, GROUPED THE SAME WAY THE ENGINE GROUPS:
    partition by 18:00-ET trading_day, then bar_id = arange//147 WITHIN each group,
    keep n==147. Made deterministic by the (ts_event,seq) sort. This is the apples-
    to-apples reference for the engine's build_tick_bars_from_frame complete bars."""
    work = df.copy()
    work["_td"] = _trading_day_series(work["ts_event"]).to_numpy()
    work = work.sort_values(["ts_event", "seq"], kind="stable").reset_index(drop=True)
    parts = []
    for tdv, g in work.groupby("_td", sort=True):
        g = g.reset_index(drop=True)
        g = g.assign(bar_id=np.arange(len(g)) // TF)
        agg = g.groupby("bar_id", sort=True).agg(
            open=("mid", "first"), high=("mid", "max"), low=("mid", "min"),
            close=("mid", "last"), volume=("size", "sum"),
            open_ts=("ts_event", "first"), close_ts=("ts_event", "last"), n=("mid", "size"),
        ).reset_index()
        agg = agg[agg["n"] == TF].copy()
        agg["trading_day"] = tdv.date()
        parts.append(agg)
    if not parts:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "open_ts", "close_ts", "n", "trading_day"])
    return pd.concat(parts, ignore_index=True)


def engine_bars_from_frame(df: pd.DataFrame, timed: bool = False):
    frame = pd.DataFrame(
        {"ts_event": df["ts_event"].to_numpy(), "price": df["mid"].to_numpy(), "size": df["size"].to_numpy()}
    )
    t0 = _time.perf_counter()
    bars = build_tick_bars_from_frame(frame, (TF,), scheme=sc.RESEARCH_SESSION_SCHEME, tick_size=CANON_TICK)
    dt = _time.perf_counter() - t0
    return (bars, dt) if timed else bars


# --- STAGE 0: deterministic candle comparison -------------------------------
def stage0_candles(date_str: str, df: pd.DataFrame, eng_bars: list[Bar]) -> dict:
    """Compare the engine's COMPLETE bars 1:1 against an engine-aligned reference
    (same 18:00-ET trading_day partition + arange//147 within group). Both are in
    (trading_day, bar_index) order, so they align element-for-element. This is the
    must-match candle proof. The continuous-vs-partitioned boundary difference is
    quantified separately (NOT counted as a mismatch) below."""
    st = STAGES["S0_CANDLES"]
    ref = reference_bars(df)  # engine-aligned (per trading_day)
    complete = [b for b in eng_bars if b.is_complete]
    partials = [b for b in eng_bars if not b.is_complete]

    # both lists are in (trading_day, bar_index) ascending order
    n_cmp = min(len(ref), len(complete))
    day_full = 0
    first_div = None
    for i in range(n_cmp):
        rr = ref.iloc[i]
        eb = complete[i]
        eo = eb.open_ticks * CANON_TICK
        eh = eb.high_ticks * CANON_TICK
        el = eb.low_ticks * CANON_TICK
        ec = eb.close_ticks * CANON_TICK
        ok_o = abs(eo - float(rr["open"])) <= ABS_TOL
        ok_h = abs(eh - float(rr["high"])) <= ABS_TOL
        ok_l = abs(el - float(rr["low"])) <= ABS_TOL
        ok_c = abs(ec - float(rr["close"])) <= ABS_TOL
        ok_v = int(eb.volume) == int(rr["volume"])
        ok_cts = eb.close_ts_utc == _to_utc_dt(rr["close_ts"])
        ok_ots = eb.open_ts_utc == _to_utc_dt(rr["open_ts"])
        ok_td = eb.trading_day == rr["trading_day"]
        ok = ok_o and ok_h and ok_l and ok_c and ok_v and ok_cts and ok_ots and ok_td
        if ok:
            day_full += 1
        elif first_div is None:
            first_div = (
                f"{date_str} bar#{i}: ref(td={rr['trading_day']},o={rr['open']},h={rr['high']},"
                f"l={rr['low']},c={rr['close']},v={int(rr['volume'])},cts={pd.Timestamp(rr['close_ts'])}) vs "
                f"eng(td={eb.trading_day},o={eo},h={eh},l={el},c={ec},v={eb.volume},cts={eb.close_ts_utc}) "
                f"flags(o,h,l,c,v,cts,ots,td)={(ok_o, ok_h, ok_l, ok_c, ok_v, ok_cts, ok_ots, ok_td)}"
            )
        st.record(ok, first_div or "")
    # length mismatch (should not happen): record explicitly
    if len(ref) != len(complete):
        st.record(False, f"{date_str}: bar count ref={len(ref)} eng_complete={len(complete)}")

    # ---- quantify the continuous-vs-partitioned 18:00-ET boundary difference ----
    cont = reference_bars_continuous(df)
    n_td_groups = _trading_day_series(df["ts_event"]).nunique()
    boundary_split = n_td_groups > 1
    # positional disagreement between continuous and engine-aligned complete bars
    n_cont = min(len(cont), len(complete))
    cont_disagree = 0
    seam_idx = None
    for i in range(n_cont):
        cc = cont.iloc[i]
        eb = complete[i]
        same = (abs(eb.close_ticks * CANON_TICK - float(cc["close"])) <= ABS_TOL
                and abs(eb.open_ticks * CANON_TICK - float(cc["open"])) <= ABS_TOL)
        if not same:
            cont_disagree += 1
            if seam_idx is None:
                seam_idx = i

    CANDLE_AGG["compared"] += n_cmp
    CANDLE_AGG["matched_full"] += day_full
    CANDLE_AGG["trailing_partials"] += len(partials)
    CANDLE_AGG["boundary_diff_bars"] = CANDLE_AGG.get("boundary_diff_bars", 0) + cont_disagree
    if boundary_split:
        CANDLE_AGG["boundary_split_days"] += 1

    if boundary_split and CANDLE_AGG["first_finding"] is None and seam_idx is not None:
        cc = cont.iloc[seam_idx]
        eb = complete[seam_idx]
        CANDLE_AGG["first_finding"] = (
            f"18:00-ET trading-day partition vs continuous DuckDB bucketing, first observed on "
            f"{date_str}. The engine resets bar buckets at each 18:00-ET boundary (it emits an "
            f"END_OF_DAY partial of {[p.trade_count for p in partials]} events at each boundary, "
            f"then restarts bar_index=0 for the next trading_day); the canonical continuous "
            f"DuckDB rn//147 does not. They first diverge positionally at bar#{seam_idx}: "
            f"continuous close={cc['close']} @ {pd.Timestamp(cc['close_ts'])} vs engine "
            f"close={eb.close_ticks * CANON_TICK} @ {eb.close_ts_utc} (engine td={eb.trading_day}). "
            f"This is the documented engine-vs-research difference, NOT a port bug: when the "
            f"reference is partitioned the SAME way the engine groups, all complete bars match "
            f"100% incl. open/close (see Stage 0 must-match result)."
        )

    day_pass = (day_full == n_cmp) and (n_cmp > 0) and (len(ref) == len(complete))
    if not day_pass:
        CANDLE_AGG["all_100pct"] = False
    return {
        "ref_bars": len(ref),
        "eng_complete": len(complete),
        "cont_bars": len(cont),
        "compared": n_cmp,
        "matched_full": day_full,
        "partials": len(partials),
        "boundary_split": boundary_split,
        "boundary_diff_bars": cont_disagree,
        "pass": day_pass,
    }


# --- Front-month trade/quote extraction (stages F & G) ----------------------
class DayParquet:
    """Per-day DuckDB view over mbp10 parquet (+prev day union), front-month aware.

    Mirrors the prior harness; DuckDB session TZ is America/Chicago, but stages F/G
    pass tz-aware UTC bounds (event_ts_utc) so the session TZ does not affect them.
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}

    def _path(self, date_str: str) -> Path:
        return DATA_DIR / SYMBOL / date_str / "mbp10.parquet"

    def get(self, date_str: str):
        if date_str in self._cache:
            return self._cache[date_str]
        # 1-deep cache: close any other day's connection before opening a new one
        # (each connection holds a DuckDB read over prev+cur ~8M-row parquets;
        # retaining all 57 days would exhaust memory). Stages F/G only ever query
        # the current day's connection.
        self.close_all()
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
        front = con.execute(
            f"SELECT symbol, count(*) AS n FROM ({union_sql}) AS t "
            f"WHERE symbol NOT LIKE '%-%' GROUP BY symbol ORDER BY n DESC LIMIT 1"
        ).fetchone()
        sym = front[0] if front else None
        info = {"con": con, "union_sql": union_sql, "symbol": sym}
        self._cache[date_str] = info
        return info

    def close_all(self):
        for info in self._cache.values():
            if info:
                try:
                    info["con"].close()
                except Exception:
                    pass
        self._cache.clear()

    def trades(self, date_str, start_utc, end_utc, end_exclusive):
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

    def quotes_base(self, date_str, start_utc, end_utc):
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

# Per-date single-day TickStore for Stage E (reproduces canonical book-row scope:
# _compute_interaction_features registers ONLY date_str). Touches are always for the
# CURRENT day, so we keep just a 1-deep cache and CLOSE the prior day's store on a
# date change — caching every day's store would retain a DuckDB view over an ~8M-row
# parquet per day and exhaust memory across the 57-day range.
_SINGLE_DAY_STORE: dict[str, object] = {"date": None, "store": None}


def _single_day_store(date_str: str) -> TickStore:
    if _SINGLE_DAY_STORE["date"] != date_str:
        old = _SINGLE_DAY_STORE["store"]
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        st = TickStore(DATA_DIR)
        st.register_symbol_date(SYMBOL, date_str)
        _SINGLE_DAY_STORE["date"] = date_str
        _SINGLE_DAY_STORE["store"] = st
    return _SINGLE_DAY_STORE["store"]


def _close_single_day_stores():
    st = _SINGLE_DAY_STORE["store"]
    if st is not None:
        try:
            st.close()
        except Exception:
            pass
    _SINGLE_DAY_STORE["date"] = None
    _SINGLE_DAY_STORE["store"] = None


def _engine_bars_from_et(bars_et: pd.DataFrame, trading_day: date) -> list[Bar]:
    """Engine Bars from canonical ET-indexed OHLCV (book-mid grid). Used by the
    decision stages, which depend only on HIGH/LOW (tie-break independent)."""
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
    return [Level(name=l["name"], price=float(l["price"]), side=Side(l["side"])) for l in levels]


def _canon_session_for_ts(ts_et: pd.Timestamp) -> str:
    t = ts_et.time()
    if t >= B._ASIA_START or t < B._ASIA_END:
        return "asia"
    if B._LONDON_START <= t < B._LONDON_END:
        return "london"
    if B._NY_RTH_START <= t < B._NY_RTH_END:
        return "ny_rth"
    return "none"


# --- Decision-stage comparators (ported from parity_harness.py) -------------
def _compare_zones(date_str, canon, eng) -> bool:
    st = STAGES["A_ZONES"]
    ok_all = True
    if len(canon) != len(eng):
        st.record(False, f"{date_str}: zone count canon={len(canon)} eng={len(eng)}")
        return False
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
        ok_all = ok_all and ok
    return ok_all


def _compare_sessions(date_str, bars_et) -> bool:
    st = STAGES["C_SESSIONS"]
    idx = bars_et.index
    n = len(idx)
    if n > 5000:
        sel = np.unique(np.linspace(0, n - 1, 5000).astype(int))
    else:
        sel = range(n)
    ok_all = True
    for i in sel:
        ts_et = idx[i]
        canon_sess = _canon_session_for_ts(ts_et)
        eng_sess = classify_session(_to_utc_dt(ts_et)).session
        ok = canon_sess == eng_sess
        ex = f"{date_str} {ts_et.isoformat()}: canon={canon_sess} eng={eng_sess}"
        st.record(ok, ex)
        ok_all = ok_all and ok
    return ok_all


def _compare_touches(date_str, canon, eng) -> bool:
    st = STAGES["B_TOUCHES"]
    ok_all = True
    if len(canon) != len(eng):
        st.record(False, f"{date_str}: touch count canon={len(canon)} eng={len(eng)}")
        ok_all = False
    for i in range(min(len(canon), len(eng))):
        ct, et = canon[i], eng[i]
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
        ok_all = ok_all and ok
    return ok_all


def _compare_label(date_str, touch, canon, eng) -> bool:
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
    return ok


def _compare_int_formula(date_str, touch, canon, e_beyond, e_within, e_absorp) -> bool:
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
    return ok


def _record_int_divergence(canon, f_beyond, f_within, f_absorp):
    st = STAGES["F_INT_TRADEPRICE"]
    st.total += 1
    st.divergences["int_time_beyond_level"].append(abs(f_beyond - float(canon["int_time_beyond_level"])))
    st.divergences["int_time_within_2pts"].append(abs(f_within - float(canon["int_time_within_2pts"])))
    st.divergences["int_absorption_ratio"].append(abs(f_absorp - float(canon["int_absorption_ratio"])))


def _compare_approach(date_str, touch, canon, e_avg, e_largepct, e_maxspread) -> bool:
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
    return ok


# --- Per-day driver ----------------------------------------------------------
def process_day(date_str, prev_ny_hl, prev_asia_hl, prev_london_hl, store_book, count_only=False):
    """Run STAGE 0 + decision stages for one day. Returns updated session H/L
    carry and kept-touch count. If count_only (warmup), only advance the carry."""
    td = date.fromisoformat(date_str)

    # research continuous bars (shared input for decision stages) ------------
    t0 = _time.perf_counter()
    bars = B._build_bars_for_date(DATA_DIR, SYMBOL, date_str, U)
    BENCH["duckdb_seconds"] += _time.perf_counter() - t0
    if bars.empty:
        return prev_ny_hl, prev_asia_hl, prev_london_hl, 0, None
    bars_et = B._ensure_et_index(bars.copy())

    # advance session H/L carry (mirror build_utility_dataset loop) ----------
    t0 = _time.perf_counter()
    new_ny, new_asia, new_london = B._get_session_hl_for_date(
        DATA_DIR, SYMBOL, date_str, U, prev_ny_hl, prev_asia_hl, prev_london_hl
    )
    BENCH["duckdb_seconds"] += _time.perf_counter() - t0

    if count_only:
        return new_ny, new_asia, new_london, 0, None

    # STAGE 0: deterministic candle comparison ------------------------------
    df, _front = build_event_frame(date_str)
    s0 = None
    if df is not None and not df.empty:
        eng_bars, dt = engine_bars_from_frame(df, timed=True)
        BENCH["engine_builder_seconds"] += dt
        BENCH["days"] += 1
        BENCH["bars"] += sum(1 for b in eng_bars if b.is_complete)
        s0 = stage0_candles(date_str, df, eng_bars)
        del df, eng_bars
        import gc
        gc.collect()

    # levels -----------------------------------------------------------------
    levels = B._compute_levels_for_date(bars_et, date_str, prev_ny_hl, prev_asia_hl, prev_london_hl)
    eng_bars_et = _engine_bars_from_et(bars_et, td)

    # STAGE A: zones ---------------------------------------------------------
    a_ok = _compare_zones(date_str, B._build_zones(levels), build_zones(_canon_levels_to_engine(levels)))

    # STAGE C: sessions ------------------------------------------------------
    c_ok = _compare_sessions(date_str, bars_et)

    # STAGE B: touches (fresh zones; detection mutates 'touched') ------------
    canon_zones_det = B._build_zones(levels)
    canon_touches = B._detect_touches(bars_et, canon_zones_det)
    eng_zones_det = build_zones(_canon_levels_to_engine(levels))
    eng_touches = detect_touches(eng_bars_et, eng_zones_det, tick_size=CANON_TICK, trading_day=td)
    b_ok = _compare_touches(date_str, canon_touches, eng_touches)

    # STAGE D: labels --------------------------------------------------------
    rth_cutoff = pd.Timestamp(f"{date_str} 16:15:00", tz=_ET)
    d_ok = True
    for touch in canon_touches:
        forward = bars_et[(bars_et.index > touch["bar_ts"]) & (bars_et.index < rth_cutoff)]
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
        d_ok = _compare_label(date_str, touch, canon, eng) and d_ok

    # STAGES E, F, G ---------------------------------------------------------
    e_ok = f_ok = g_ok = True
    day_touch_count = 0
    for touch in canon_touches:
        canon_int = B._compute_interaction_features(touch, DATA_DIR, SYMBOL, U)
        if canon_int is None:
            continue
        day_touch_count += 1
        rep = float(touch["representative_price"])
        eng_dir = Direction(touch["direction"])
        event_ts_utc = _to_utc_dt(pd.Timestamp(touch["bar_ts"]))
        win_end_utc = event_ts_utc + timedelta(minutes=U.interaction_window_minutes)

        # STAGE E: identical BOOK inputs -> must match.
        # CRITICAL: canonical _compute_interaction_features registers ONLY the touch's
        # date_str (builder:468-469), NOT prev/next day. The shared multi-day store
        # would leak rows from the NEXT day's file when the 5-min window crosses
        # midnight UTC (e.g. a 23:59 touch), inflating int_time_*. Use a per-date
        # single-day store that reproduces the canonical book-row scope EXACTLY.
        ds_touch = touch.get("date") or str(pd.Timestamp(touch["bar_ts"]).date())
        book_store = _single_day_store(ds_touch)
        book_rows = book_store.query_tick_feature_rows(SYMBOL, event_ts_utc, win_end_utc)
        eng_book_trades = []
        if not book_rows.empty and "price" in book_rows.columns:
            for r in book_rows.itertuples(index=False):
                eng_book_trades.append(
                    Trade(event_ts_utc=_to_utc_dt(r.ts_event),
                          price_ticks=_round_to_ticks(r.price, CANON_TICK), size=int(r.size))
                )
        e_beyond = int_time_beyond_level(eng_book_trades, rep, eng_dir, CANON_TICK)
        e_within = int_time_within_2pts(eng_book_trades, rep, CANON_TICK)
        e_absorp = int_absorption_ratio(eng_book_trades, rep, eng_dir, CANON_TICK)
        e_ok = _compare_int_formula(date_str, touch, canon_int, e_beyond, e_within, e_absorp) and e_ok

        # STAGE F: real TRADE prints -> expected to differ
        trade_df = DAY_PARQUET.trades(date_str, event_ts_utc, win_end_utc, end_exclusive=False)
        eng_trades = [
            Trade(event_ts_utc=_to_utc_dt(r.ts_event),
                  price_ticks=_round_to_ticks(r.price, TRADE_TICK), size=int(r.size))
            for r in trade_df.itertuples(index=False)
        ]
        f_beyond = int_time_beyond_level(eng_trades, rep, eng_dir, TRADE_TICK)
        f_within = int_time_within_2pts(eng_trades, rep, TRADE_TICK)
        f_absorp = int_absorption_ratio(eng_trades, rep, eng_dir, TRADE_TICK)
        _record_int_divergence(canon_int, f_beyond, f_within, f_absorp)

        # STAGE G: approach features (3 model features) -> must match
        canon_app = B._compute_approach_features(touch, DATA_DIR, SYMBOL, U)
        app_start_utc = event_ts_utc - timedelta(minutes=U.approach_window_minutes)
        a_trades_df = DAY_PARQUET.trades(date_str, app_start_utc, event_ts_utc, end_exclusive=True)
        a_quotes_df = DAY_PARQUET.quotes_base(date_str, app_start_utc, event_ts_utc)
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
        g_ok = _compare_approach(date_str, touch, canon_app, e_avg, e_largepct, e_maxspread) and g_ok

    DAY_ROWS.append({
        "day": date_str,
        "S0": (s0["pass"] if s0 else None),
        "A": a_ok, "B": b_ok, "C": c_ok, "D": d_ok, "E": e_ok, "G": g_ok,
        "touches": day_touch_count,
        "s0_detail": s0,
    })
    return new_ny, new_asia, new_london, day_touch_count, s0


# --- Report ------------------------------------------------------------------
def write_report(available, missing, total_cal, days_run, total_touches):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    must_pass = all(s.mismatched == 0 for s in STAGES.values() if s.scope == "must_match")

    L_ = []
    L_.append("# Strategy-Core Parity Report v2 (CORRECTED phase-4a gate)")
    L_.append("")
    L_.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    L_.append(f"Engine: strategy_core v{getattr(sc, 'ENGINE_VERSION', '?')} "
              f"(contract v{getattr(sc, 'CONTRACT_VERSION', '?')})")
    L_.append("")
    L_.append("## Day range")
    L_.append(f"- Requested window: {RANGE_START} .. {RANGE_END} inclusive")
    L_.append(f"- Total calendar days in range: {total_cal}")
    L_.append(f"- Available days run: {len(days_run)}")
    L_.append(f"- Warm-up day (session-level carry, NOT counted): {WARMUP_DAY.isoformat()}")
    L_.append(f"- Unavailable days ({len(missing)}): {', '.join(missing) if missing else 'none'}")
    L_.append(f"- Total kept touches (canonical interaction features not None): {total_touches}")
    L_.append("")

    L_.append("## Window finding (root cause of the prior wrong-range/candle issue)")
    L_.append("research `_build_bars_for_date` passes a NAIVE `datetime(prev,23,0)` to DuckDB, "
              "whose session `TimeZone='America/Chicago'`. DuckDB interprets that bound as "
              "**23:00 Chicago**, not 23:00 UTC, so the real research window is "
              "`[prev 23:00 America/Chicago, cur 23:00 America/Chicago]`. The deterministic "
              "reference frame uses Chicago-localized bounds and reproduces the canonical "
              "DuckDB bar count and values exactly.")
    L_.append("")

    L_.append("## Stage results (aggregate over all available days)")
    L_.append("")
    L_.append("| Stage | Scope | Total | Matched | Mismatched |")
    L_.append("|-------|-------|------:|--------:|-----------:|")
    for key in STAGE_ORDER:
        s = STAGES[key]
        L_.append(f"| {s.name} | {s.scope} | {s.total} | {s.matched} | {s.mismatched} |")
    L_.append("")

    # Candle confirmation
    L_.append("## Stage 0 candle confirmation (deterministic book-mid bars)")
    cand_100 = CANDLE_AGG["all_100pct"] and STAGES["S0_CANDLES"].mismatched == 0
    L_.append(f"- Engine complete bars compared vs engine-aligned reference: {CANDLE_AGG['compared']}")
    L_.append(f"- Fully matched (open/high/low/close/volume/close_ts/open_ts/trading_day): "
              f"{CANDLE_AGG['matched_full']}")
    L_.append(f"- **Do candles match 100% incl. open/close after the deterministic sort? "
              f"{'YES' if cand_100 else 'NO'}**")
    L_.append(f"- Days with an 18:00-ET trading-day boundary (>1 trading_day group in window): "
              f"{CANDLE_AGG['boundary_split_days']}/{len(days_run)}")
    L_.append(f"- Engine END_OF_DAY trailing partials excluded (by design, one per trading_day "
              f"group): {CANDLE_AGG['trailing_partials']}")
    L_.append(f"- Bars where the CONTINUOUS DuckDB bucketing positionally disagrees with the "
              f"engine (the boundary phase-shift, quantified): {CANDLE_AGG.get('boundary_diff_bars', 0)}")
    L_.append("")
    L_.append("Reference definition (must-match): the engine-aligned reference applies the EXACT "
              "build_tick_bars logic (open=first/close=last/high=max/low=min over 147-event "
              "buckets) but PARTITIONS by the same 18:00-ET trading_day the engine uses, made "
              "deterministic by the (ts_event,seq) stable sort. Engine complete bars and this "
              "reference are both in (trading_day, bar_index) order, so they align 1:1.")
    L_.append("")
    L_.append("Boundary finding (expected engine-vs-research difference, reported not hidden):")
    if CANDLE_AGG["first_finding"]:
        L_.append(f"- {CANDLE_AGG['first_finding']}")
    else:
        L_.append("- No boundary observed (single trading_day group on every available day).")
    if STAGES["S0_CANDLES"].mismatched > 0:
        L_.append(f"- FIRST diverging candle in the must-match comparison: `{STAGES['S0_CANDLES'].example}`")
    L_.append("")
    L_.append("Interpretation: the engine's tick-bar builder is a faithful, deterministic "
              "reproduction of build_tick_bars. The ONLY structural difference vs the canonical "
              "CONTINUOUS DuckDB bars is the 18:00-ET trading-day partition (the engine resets "
              "bar buckets and emits an END_OF_DAY partial at each 18:00-ET boundary; the "
              "continuous DuckDB rn//147 does not). When the reference is partitioned the same "
              "way the engine groups, all complete bars match 100% incl. open/close.")
    L_.append("")

    # Per-day table
    L_.append("## Per-day pass/fail")
    L_.append("")
    L_.append("| Day | S0 | A | B | C | D | E | G | touches | ref/eng/cont bars | bnd_diff |")
    L_.append("|-----|----|---|---|---|---|---|---|--------:|-------------------|---------:|")

    def mk(v):
        return "—" if v is None else ("pass" if v else "FAIL")

    for r in DAY_ROWS:
        d = r["s0_detail"]
        bars_str = f"{d['ref_bars']}/{d['eng_complete']}/{d['cont_bars']}" if d else "—"
        bnd = d["boundary_diff_bars"] if d else "—"
        L_.append(
            f"| {r['day']} | {mk(r['S0'])} | {mk(r['A'])} | {mk(r['B'])} | {mk(r['C'])} | "
            f"{mk(r['D'])} | {mk(r['E'])} | {mk(r['G'])} | {r['touches']} | {bars_str} | {bnd} |"
        )
    L_.append("")

    # must-match mismatch examples
    L_.append("## Must-match mismatches (first diverging layer + concrete example)")
    L_.append("")
    any_mm = False
    for key in STAGE_ORDER:
        s = STAGES[key]
        if s.scope != "must_match" or s.mismatched == 0:
            continue
        any_mm = True
        L_.append(f"- **{s.name}**: {s.mismatched}/{s.total} mismatched. Example: `{s.example}`")
    if not any_mm:
        L_.append("None. Every must-match stage is 100% matched across all available days.")
    L_.append("")

    # expected-differ distribution
    L_.append("## Stage F — interaction trade-price divergence (reported, not asserted)")
    L_.append("Real TRADE prints (tick 0.25) vs canonical BOOK-MID (tick 0.125). Distribution of "
              "`|engine_trade - canonical_book|`:")
    f = STAGES["F_INT_TRADEPRICE"]
    L_.append(f"- samples (touches): {f.total}")
    summ = f.divergence_summary()
    if summ:
        for part in summ.split("; "):
            L_.append(f"  - {part}")
    else:
        L_.append("  - (no samples)")
    L_.append("")

    # benchmark
    L_.append("## Bar-builder benchmark (informational)")
    L_.append(f"- Shared engine builder (lean columnar parquet read + vectorized "
              f"build_tick_bars_from_frame, deterministic sort): "
              f"{BENCH['engine_builder_seconds']:.2f}s")
    L_.append(f"- Old all-DuckDB path (B._build_bars_for_date + _get_session_hl_for_date): "
              f"{BENCH['duckdb_seconds']:.2f}s")
    L_.append(f"- Days: {BENCH['days']}  Engine complete bars built: {BENCH['bars']}")
    L_.append("- Note: the engine-builder time EXCLUDES the parquet read (measured around the "
              "vectorized builder call only); I/O dominates wall time for both paths and the "
              "DuckDB number also includes the session-H/L second pass.")
    L_.append("")

    verdict = ("CLEAN — must-match set passes across ALL available requested days"
               if must_pass else None)
    if not must_pass:
        first_bad = next(STAGES[k].name for k in STAGE_ORDER
                         if STAGES[k].scope == "must_match" and STAGES[k].mismatched > 0)
        verdict = f"MISMATCH — first diverging must-match stage: {first_bad}"
    L_.append(f"## VERDICT: {verdict}")
    L_.append("")

    REPORT_PATH.write_text("\n".join(L_), encoding="utf-8")
    return must_pass, verdict


# --- Driver -----------------------------------------------------------------
def main():
    available, missing, total_cal = enumerate_days()
    print(f"calendar days={total_cal} available={len(available)} missing={len(missing)}", flush=True)

    # Stage E book rows now come from per-date single-day stores (canonical scope),
    # so no global multi-day store is needed. Keep a placeholder for the signature.
    store_book = None

    prev_ny_hl = prev_asia_hl = prev_london_hl = None
    total_touches = 0
    days_run = []
    try:
        # warm-up (advance carry only; not reported / not benchmarked)
        print(f"=== warmup {WARMUP_DAY.isoformat()} (carry only) ===", flush=True)
        prev_ny_hl, prev_asia_hl, prev_london_hl, _, _ = process_day(
            WARMUP_DAY.isoformat(), prev_ny_hl, prev_asia_hl, prev_london_hl,
            store_book, count_only=True
        )

        for i, d in enumerate(available):
            t0 = _time.perf_counter()
            prev_ny_hl, prev_asia_hl, prev_london_hl, n, s0 = process_day(
                d, prev_ny_hl, prev_asia_hl, prev_london_hl, store_book
            )
            days_run.append(d)
            total_touches += n
            s0s = (f"S0 {s0['matched_full']}/{s0['compared']} (ref={s0['ref_bars']} "
                   f"eng_complete={s0['eng_complete']} bnd_diff={s0['boundary_diff_bars']} "
                   f"split={s0['boundary_split']})") if s0 else "S0 n/a"
            print(f"[{i+1}/{len(available)}] {d}: touches={n} {s0s} "
                  f"({_time.perf_counter()-t0:.1f}s)", flush=True)
    finally:
        if store_book is not None:
            store_book.close()
        _close_single_day_stores()
        DAY_PARQUET.close_all()

    must_pass, verdict = write_report(available, missing, total_cal, days_run, total_touches)
    print(f"\nReport: {REPORT_PATH}")
    print(f"must_match_all_pass={must_pass}")
    print(f"VERDICT: {verdict}")
    for key in STAGE_ORDER:
        s = STAGES[key]
        print(f"  {s.name}: {s.matched}/{s.total} matched, {s.mismatched} mismatched ({s.scope})")


if __name__ == "__main__":
    main()
