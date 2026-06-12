"""Phase 4b-prep validation (targeted, small sample). strategy-core only; reads the
research repo + databento store READ-ONLY. Validates the vectorized bar-emit and the
ratified 18:00 ET trading-day boundary on 2-3 stress days.

Checks:
  a. EMIT EQUIVALENCE  : new vectorized build_tick_bars_from_frame == old .itertuples() emit, exactly.
  b. NO-REGRESSION DIFF: engine (18:00 ET bars) vs canonical (research 23:00 CT bars) touches/labels;
                         every diff attributable to the bar-bucketing boundary (logic held identical).
  c. SEAM AUDIT        : re-derive one 18:00-ET-seam touch from raw events (day assignment, bar_index
                         reset, windows, no look-ahead).
  d. BENCHMARK         : new emit build time vs old emit and vs DuckDB.
"""
from __future__ import annotations

import sys
import time
import warnings
from datetime import date, timedelta
from pathlib import Path

CQL_SRC = r"C:/Users/gonza/Documents/Claude-Quant-Lab/src"
sys.path.insert(0, CQL_SRC)
DATA_DIR = Path(r"C:/Users/gonza/Documents/Trade-Dashboard/data/databento")
SYMBOL = "NQ"
CANON_TICK = 0.125  # book-mid lands on the 0.125 grid -> lossless integer ticks

import numpy as np  # noqa: E402 (imports follow the sys.path bootstrap)
import pandas as pd  # noqa: E402 (imports follow the sys.path bootstrap)

import strategy_core as sc  # noqa: E402 (imports follow the sys.path bootstrap)
from strategy_core.candles._ids import make_bar_id  # noqa: E402 (imports follow the sys.path bootstrap)
from strategy_core.candles.batch import build_tick_bars_from_frame  # noqa: E402 (imports follow the sys.path bootstrap)
from strategy_core.types import Bar, CloseReason, Level, Side  # noqa: E402 (imports follow the sys.path bootstrap)
from strategy_core.constants import RESEARCH_SESSION_SCHEME  # noqa: E402 (imports follow the sys.path bootstrap)

from alpha_lab.agents.data_infra.ml.config import MLPipelineConfig  # noqa: E402 (imports follow the sys.path bootstrap)
from alpha_lab.agents.data_infra.ml import dashboard_utility_builder as B  # noqa: E402 (imports follow the sys.path bootstrap)
from alpha_lab.agents.data_infra.ml import dashboard_utility_labeling as L  # noqa: E402 (imports follow the sys.path bootstrap)

CFG = MLPipelineConfig(
    training_mode="dashboard_utility", instrument=SYMBOL, tick_size=0.25,
    dashboard_utility=dict(bar_type="147t", interaction_window_minutes=5, approach_window_minutes=30,
                           include_approach_features=True, tp_points=15.0, sl_points=30.0,
                           trap_mfe_min=5.0, level_proximity_pts=0.5),
)
U = CFG.dashboard_utility
TF = 147
ET = "US/Eastern"

EMIT_DAYS = ["2025-07-01", "2025-07-06", "2025-07-15"]  # big(ties)+RTH, Sunday-Globex, big(ties)
SEAM_DAYS = ["2025-07-01", "2025-07-06"]                # weekday post-18:00 tail, Sunday session


# ───────────────────────── shared IO ─────────────────────────
def _front_month(df: pd.DataFrame) -> pd.DataFrame:
    if "symbol" not in df.columns:
        return df
    out = df[~df["symbol"].astype(str).str.contains("-")]
    if out.empty:
        return out
    dom = out["symbol"].value_counts().idxmax()
    return out[out["symbol"] == dom]


def load_book_mid_events(start_utc: pd.Timestamp, end_utc: pd.Timestamp, day_files: list[str]) -> pd.DataFrame:
    """Deterministic book-mid event frame over [start_utc, end_utc] across the given day files.

    Reads in file order (pandas preserves it), assigns a stable source-row seq, filters to
    bid>0 & ask>0 + dominant front-month, computes mid, sorts by (ts_event, seq). end is inclusive
    on the upper bound to match research's BETWEEN; callers pass the exact window they want.
    """
    frames = []
    base = 0
    for f in day_files:
        p = DATA_DIR / SYMBOL / f / "mbp10.parquet"
        if not p.exists():
            continue
        cols = ["ts_event", "bid_px_00", "ask_px_00", "size", "symbol"]
        d = pd.read_parquet(p, columns=[c for c in cols if c])
        d = d.reset_index(drop=True)
        d["seq"] = np.arange(base, base + len(d))
        base += len(d)
        frames.append(d)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(df["ts_event"], utc=True)
    df = df.assign(ts_event=ts)
    df = df[(df["bid_px_00"] > 0) & (df["ask_px_00"] > 0)]
    df = df[(df["ts_event"] >= start_utc) & (df["ts_event"] <= end_utc)]
    df = _front_month(df)
    if df.empty:
        return df
    df = df.assign(mid=(df["bid_px_00"].astype("float64") + df["ask_px_00"].astype("float64")) / 2.0)
    df = df.sort_values(["ts_event", "seq"], kind="stable").reset_index(drop=True)
    return df[["ts_event", "mid", "size", "seq"]]


def events_to_frame(ev: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"ts_event": ev["ts_event"].to_numpy(),
                         "price": ev["mid"].to_numpy(dtype="float64"),
                         "size": ev["size"].to_numpy(dtype="int64")})


# ───────────── legacy (pre-refactor) emit, verbatim itertuples path ─────────────
def legacy_build(frame: pd.DataFrame, timeframe: int, scheme=RESEARCH_SESSION_SCHEME, tick_size=CANON_TICK) -> list[Bar]:
    if frame is None or len(frame) == 0:
        return []
    ts = frame["ts_event"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        ts = pd.to_datetime(ts, utc=True, unit="ns")
    elif ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    price_ticks = np.rint(frame["price"].to_numpy(dtype="float64") / tick_size).astype("int64")
    work = pd.DataFrame({"ts_event": ts.to_numpy(), "price_ticks": price_ticks,
                         "size": frame["size"].to_numpy(dtype="int64")})
    work["ts_event"] = pd.to_datetime(work["ts_event"], utc=True)
    local = work["ts_event"].dt.tz_convert(scheme.timezone)
    sod = local.dt.hour * 3600 + local.dt.minute * 60 + local.dt.second
    cal_date = local.dt.tz_localize(None).dt.floor("D")
    boundary_sod = scheme.trading_day_boundary.hour * 3600 + scheme.trading_day_boundary.minute * 60
    roll = (sod >= boundary_sod).astype("int64")
    work["trading_day"] = cal_date + pd.to_timedelta(roll, unit="D")
    if scheme.closed_window is not None:
        cs = scheme.closed_window[0].hour * 3600 + scheme.closed_window[0].minute * 60
        ce = scheme.closed_window[1].hour * 3600 + scheme.closed_window[1].minute * 60
        work = work[~((sod >= cs) & (sod < ce))]
    work = work.sort_values("ts_event", kind="stable").reset_index(drop=True)
    if work.empty:
        return []
    day_groups = work.groupby("trading_day", sort=True)
    bars: list[Bar] = []
    for tf in sorted({timeframe}):
        work["bar_index"] = (day_groups.cumcount() // tf).to_numpy()
        agg = (work.groupby(["trading_day", "bar_index"], sort=True)
               .agg(open_ts=("ts_event", "first"), close_ts=("ts_event", "last"),
                    open_ticks=("price_ticks", "first"), close_ticks=("price_ticks", "last"),
                    high_ticks=("price_ticks", "max"), low_ticks=("price_ticks", "min"),
                    volume=("size", "sum"), trade_count=("price_ticks", "size")).reset_index())
        for row in agg.itertuples(index=False):
            td = row.trading_day.date()
            bi = int(row.bar_index)
            complete = int(row.trade_count) == tf
            bars.append(Bar(timeframe_ticks=tf, trading_day=td, bar_index=bi,
                            bar_id=make_bar_id(tf, td, bi),
                            open_ts_utc=row.open_ts.to_pydatetime(warn=False),
                            close_ts_utc=row.close_ts.to_pydatetime(warn=False),
                            open_ticks=int(row.open_ticks), high_ticks=int(row.high_ticks),
                            low_ticks=int(row.low_ticks), close_ticks=int(row.close_ticks),
                            volume=int(row.volume), trade_count=int(row.trade_count),
                            is_complete=complete, is_partial=not complete,
                            close_reason=CloseReason.COMPLETE if complete else CloseReason.END_OF_DAY))
    return bars


# ───────────────────────── windows ─────────────────────────
def research_window(day: str) -> tuple[pd.Timestamp, pd.Timestamp, list[str]]:
    d = date.fromisoformat(day)
    prev = d - timedelta(days=1)
    start = pd.Timestamp(f"{prev.isoformat()} 23:00:00", tz="America/Chicago").tz_convert("UTC")
    end = pd.Timestamp(f"{d.isoformat()} 23:00:00", tz="America/Chicago").tz_convert("UTC")
    return start, end, [prev.isoformat(), d.isoformat()]


def engine_td_window(day: str) -> tuple[pd.Timestamp, pd.Timestamp, list[str]]:
    """Events whose 18:00-ET trading_day == day: [prev 18:00 ET, day 18:00 ET)."""
    d = date.fromisoformat(day)
    prev = d - timedelta(days=1)
    start = pd.Timestamp(f"{prev.isoformat()} 18:00:00", tz=ET).tz_convert("UTC")
    end = pd.Timestamp(f"{d.isoformat()} 18:00:00", tz=ET).tz_convert("UTC")
    return start, end, [prev.isoformat(), d.isoformat()]


def engine_bars_for_day(day: str) -> list[Bar]:
    s, e, files = engine_td_window(day)
    ev = load_book_mid_events(s, e - pd.Timedelta(nanoseconds=1), files)
    if ev.empty:
        return []
    bars = build_tick_bars_from_frame(events_to_frame(ev), (TF,),
                                      scheme=RESEARCH_SESSION_SCHEME, tick_size=CANON_TICK)
    return [b for b in bars if b.trading_day == date.fromisoformat(day)]


def bars_to_et_df(bars: list[Bar]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    idx = pd.DatetimeIndex([b.close_ts_utc for b in bars]).tz_convert(ET)
    return pd.DataFrame({"open": [b.open_ticks * CANON_TICK for b in bars],
                         "high": [b.high_ticks * CANON_TICK for b in bars],
                         "low": [b.low_ticks * CANON_TICK for b in bars],
                         "close": [b.close_ticks * CANON_TICK for b in bars],
                         "volume": [b.volume for b in bars]}, index=idx)


def df_to_engine_bars(bars_et: pd.DataFrame, day: str) -> list[Bar]:
    td = date.fromisoformat(day)
    out = []
    for i, (ts, r) in enumerate(bars_et.iterrows()):
        ts_utc = ts.tz_convert("UTC").to_pydatetime()
        out.append(Bar(timeframe_ticks=TF, trading_day=td, bar_index=i, bar_id=make_bar_id(TF, td, i),
                       open_ts_utc=ts_utc, close_ts_utc=ts_utc,
                       open_ticks=round(r["open"] / CANON_TICK), high_ticks=round(r["high"] / CANON_TICK),
                       low_ticks=round(r["low"] / CANON_TICK), close_ticks=round(r["close"] / CANON_TICK),
                       volume=int(r["volume"]), trade_count=TF, is_complete=True, is_partial=False,
                       close_reason=CloseReason.COMPLETE))
    return out


# ───────────── canonical levels/zones (prev-day carry) ─────────────
def prior_available(day: str, back: int = 7) -> list[str]:
    d = date.fromisoformat(day)
    out = []
    for k in range(back, 0, -1):
        c = (d - timedelta(days=k)).isoformat()
        if (DATA_DIR / SYMBOL / c / "mbp10.parquet").exists():
            out.append(c)
    out.append(day)
    return out


def canonical_levels_and_bars(day: str):
    """Run research's per-day pipeline with proper prev-day session-level carry; return
    (research bars_et for `day`, levels list)."""
    seq = prior_available(day, back=4)
    prev_ny = prev_asia = prev_london = None
    bars_et = None
    levels = None
    for ds in seq:
        bars = B._build_bars_for_date(DATA_DIR, SYMBOL, ds, U)
        if bars.empty:
            continue
        be = B._ensure_et_index(bars)
        lv = B._compute_levels_for_date(be, ds, prev_ny, prev_asia, prev_london)
        prev_ny, prev_asia, prev_london = B._get_session_hl_for_date(
            DATA_DIR, SYMBOL, ds, U, prev_ny, prev_asia, prev_london)
        if ds == day:
            bars_et, levels = be, lv
    return bars_et, levels


def levels_to_engine(levels):
    return [Level(name=lvl["name"], price=float(lvl["price"]), side=Side(lvl["side"])) for lvl in levels]


# ───────────────────────── checks ─────────────────────────
def bar_tuple(b: Bar):
    return (b.timeframe_ticks, b.trading_day, b.bar_index, b.bar_id, b.open_ts_utc, b.close_ts_utc,
            b.open_ticks, b.high_ticks, b.low_ticks, b.close_ticks, b.volume, b.trade_count,
            b.is_complete, b.is_partial, b.close_reason)


def check_a_and_d():
    print("\n===== (a) EMIT EQUIVALENCE  &  (d) BENCHMARK =====")
    for day in EMIT_DAYS:
        s, e, files = research_window(day)
        ev = load_book_mid_events(s, e, files)
        frame = events_to_frame(ev)
        # legacy timing
        t0 = time.perf_counter()
        legacy = legacy_build(frame, TF)
        t_leg = time.perf_counter() - t0
        # new timing
        t0 = time.perf_counter()
        new = build_tick_bars_from_frame(frame, (TF,), scheme=RESEARCH_SESSION_SCHEME, tick_size=CANON_TICK)
        t_new = time.perf_counter() - t0
        # DuckDB baseline
        t0 = time.perf_counter()
        _ = B._build_bars_for_date(DATA_DIR, SYMBOL, day, U)
        t_duck = time.perf_counter() - t0
        same = len(legacy) == len(new) and all(bar_tuple(a) == bar_tuple(b) for a, b in zip(legacy, new))
        n_complete = sum(1 for b in new if b.is_complete)
        print(f"  {day}: bars new={len(new)} legacy={len(legacy)} complete={n_complete} | "
              f"IDENTICAL={same} | emit new={t_new:.3f}s legacy={t_leg:.3f}s (x{t_leg/max(t_new,1e-9):.1f}) | duckdb_build={t_duck:.3f}s")
        if not same:
            for a, b in zip(legacy, new):
                if bar_tuple(a) != bar_tuple(b):
                    print(f"     FIRST DIFF: legacy={bar_tuple(a)}\n                  new   ={bar_tuple(b)}")
                    break


def _norm(t):
    """Normalize a canonical-dict touch or an engine Touch object to a common dict."""
    if isinstance(t, dict):
        return dict(rep=round(float(t["representative_price"]), 4), direction=str(t["direction"]),
                    level_type=t.get("level_type", ""), ts=pd.Timestamp(t["bar_ts"]).tz_convert("UTC"))
    return dict(rep=round(float(t.representative_price), 4), direction=str(t.direction),
                level_type=t.level_type, ts=pd.Timestamp(t.bar_ts_utc))


def match_touches(canon, eng):
    """First-touch-per-zone => (rep, direction, level_type) is a unique key per day."""
    def k(n): return (n["rep"], n["direction"], n["level_type"])
    cmap = {k(_norm(t)): _norm(t) for t in canon}
    emap = {k(_norm(t)): _norm(t) for t in eng}
    matched = [(cmap[key], emap[key]) for key in cmap if key in emap]
    only_canon = [cmap[key] for key in cmap if key not in emap]
    only_eng = [emap[key] for key in emap if key not in cmap]
    return matched, only_canon, only_eng


def label_for(touch_rep, direction, forward_et: pd.DataFrame):
    ev = {"representative_price": touch_rep, "direction": direction}
    return L.label_touch_event(ev, forward_et, U)


def check_b_c():
    print("\n===== (b) NO-REGRESSION DIFF (engine 18:00 ET vs canonical 23:00 CT)  &  (c) SEAM AUDIT =====")
    classes_seen = set()
    for day in SEAM_DAYS:
        bars_et, levels = canonical_levels_and_bars(day)
        if bars_et is None or not levels:
            print(f"  {day}: no canonical bars/levels (skip)")
            continue
        eng_bars = engine_bars_for_day(day)
        eng_bars_et = bars_to_et_df(eng_bars)

        # zones: identical inputs (levels are session max/min -> bucketing-independent)
        zc = B._build_zones([dict(lvl) for lvl in levels])
        ze = sc.build_zones(levels_to_engine(levels))
        zones_same = (len(zc) == len(ze) and all(
            abs(a["representative_price"] - b.representative_price) < 1e-9 and str(a["side"]) == str(b.side)
            and tuple(a["names"]) == tuple(b.names) for a, b in zip(zc, ze)))

        # (b1) LOGIC UNCHANGED: identical bars -> identical touches (research fn vs engine fn)
        canon_t_same_bars = B._detect_touches(bars_et, [dict(z) for z in B._build_zones([dict(lvl) for lvl in levels])])
        eng_t_same_bars = sc.detect_touches(df_to_engine_bars(bars_et, day),
                                            sc.build_zones(levels_to_engine(levels)),
                                            tick_size=CANON_TICK, trading_day=date.fromisoformat(day))
        logic_same = len(canon_t_same_bars) == len(eng_t_same_bars) and all(
            abs(a["representative_price"] - b.representative_price) < 1e-9
            and str(a["direction"]) == str(b.direction) and a["level_type"] == b.level_type
            for a, b in zip(canon_t_same_bars, eng_t_same_bars))

        # (b2) BOUNDARY EFFECT: canonical bars vs engine 18:00-ET bars (same zones)
        canon_touches = B._detect_touches(bars_et, [dict(z) for z in B._build_zones([dict(lvl) for lvl in levels])])
        eng_touches = sc.detect_touches(df_to_engine_bars(eng_bars_et, day),
                                        sc.build_zones(levels_to_engine(levels)),
                                        tick_size=CANON_TICK, trading_day=date.fromisoformat(day))
        matched, only_c, only_e = match_touches(canon_touches, eng_touches)
        # label compare for matched (normalized dicts: rep/direction/level_type/ts)
        lbl_match = lbl_diff = 0
        ts_shift = []
        cutoff = pd.Timestamp(f"{day} 16:15:00", tz=ET)
        for ct, et in matched:
            classes_seen.add(ct["level_type"])
            ts_shift.append(abs((et["ts"] - ct["ts"]).total_seconds()))
            fwd_c = bars_et[(bars_et.index > ct["ts"].tz_convert(ET)) & (bars_et.index < cutoff)]
            lc = label_for(ct["rep"], ct["direction"], fwd_c)
            fwd_e = eng_bars_et[(eng_bars_et.index > et["ts"].tz_convert(ET)) & (eng_bars_et.index < cutoff)]
            le = label_for(et["rep"], et["direction"], fwd_e)
            classes_seen.add(lc["label"])
            classes_seen.add(le["label"])
            if lc["label"] == le["label"]:
                lbl_match += 1
            else:
                lbl_diff += 1
        med_shift = float(np.median(ts_shift)) if ts_shift else 0.0
        max_shift = float(np.max(ts_shift)) if ts_shift else 0.0
        print(f"  {day}: zones_same={zones_same} | LOGIC_UNCHANGED(identical bars)={logic_same} | "
              f"canon_touches={len(canon_touches)} eng_touches={len(eng_touches)} matched={len(matched)} "
              f"only_canon={len(only_c)} only_eng={len(only_e)} | matched_label_same={lbl_match} diff={lbl_diff} | "
              f"touch_ts_shift med={med_shift:.1f}s max={max_shift:.1f}s")

        # (c) SEAM AUDIT on first seam day: re-derive one engine touch in the 18:00-ET tail/Sunday session
        if day == SEAM_DAYS[0] or day == "2025-07-06":
            seam_audit(day, eng_bars)

    print(f"\n  Label/level classes seen across sample: {sorted(c for c in classes_seen if c)}")


def seam_audit(day: str, eng_bars: list[Bar]):
    """Independently confirm the 18:00-ET day assignment + bar_index reset + no look-ahead for one bar."""
    d = date.fromisoformat(day)
    seam = pd.Timestamp(f"{(d - timedelta(days=1)).isoformat()} 18:00:00", tz=ET)  # td-D opens here
    if not eng_bars:
        print(f"    [seam audit {day}] no engine bars")
        return
    b0 = eng_bars[0]  # first bar of trading_day D
    # raw events for td-D window, independently
    s, e, files = engine_td_window(day)
    ev = load_book_mid_events(s, e - pd.Timedelta(nanoseconds=1), files)
    n_before_seam = int((ev["ts_event"] < seam.tz_convert("UTC")).sum())
    first_ev_ts = pd.Timestamp(ev["ts_event"].iloc[0]).tz_convert(ET)
    # bar0 should open at the first event of td-D and bar_index reset to 0
    b0_open_et = pd.Timestamp(b0.open_ts_utc).tz_convert(ET)
    b0_close_et = pd.Timestamp(b0.close_ts_utc).tz_convert(ET)
    # recompute bar0 OHLC from first TF events independently
    head = ev.head(TF)
    rec_open = round(float(head["mid"].iloc[0]) / CANON_TICK)
    rec_close = round(float(head["mid"].iloc[-1]) / CANON_TICK)
    rec_high = round(float(head["mid"].max()) / CANON_TICK)
    rec_low = round(float(head["mid"].min()) / CANON_TICK)
    ok = (b0.bar_index == 0 and b0.trading_day == d and b0.open_ticks == rec_open and
          b0.close_ticks == rec_close and b0.high_ticks == rec_high and b0.low_ticks == rec_low)
    print(f"    [SEAM AUDIT {day}] td-D opens at {seam} ET; first td-D event {first_ev_ts} ET; "
          f"events before 18:00-ET seam in window={n_before_seam}")
    print(f"      bar0: trading_day={b0.trading_day} bar_index={b0.bar_index} open_et={b0_open_et} close_et={b0_close_et}")
    print(f"      independent recompute of bar0 from first {TF} raw events matches engine bar0: {ok} "
          f"(open {b0.open_ticks}=={rec_open}, close {b0.close_ticks}=={rec_close}, high {b0.high_ticks}=={rec_high}, low {b0.low_ticks}=={rec_low})")
    print(f"      NO LOOK-AHEAD: bar0 close_ts={b0_close_et} ET is the {TF}th event's time; bar emitted only at that count.")


if __name__ == "__main__":
    warnings.simplefilter("ignore")
    print(f"Engine {sc.PLATFORM_VERSION} | boundary={RESEARCH_SESSION_SCHEME.trading_day_boundary} "
          f"tz={RESEARCH_SESSION_SCHEME.timezone} (18:00 ET locked)")
    check_a_and_d()
    check_b_c()
    print("\nDONE.")
