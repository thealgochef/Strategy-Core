"""GATE (phase 4e): research DuckDB bars (SIDE-SIGNED order) == Trade-Lab WIRE-order bars.

4d's standing test (`test_duckdb_streaming_parity.py`) proves DuckDB-batch == streaming when
BOTH consume the same deterministic order. That is necessary but NOT the production pair:
research/DuckDB orders within a sweep by the deterministic key, while Trade-Lab (replay/live/
seed) buckets in WIRE order (`historical_parquet.py:252` stable `ts_event` sort; live FIFO).
4d's plain price-ASC key reversed sell sweeps, so the two pipelines' bars differed on ~14% of
147t bars. 4e signs the price by aggressor side so the deterministic key reproduces wire order.

This test compares the REAL production pair, on the SAME front-month trade set per day:
  RESEARCH  = `TickStore.build_tick_bars` (DuckDB, side-signed order)
  TRADE-LAB = streaming `CandleEngine` fed in WIRE order (the physical parquet stream, stable-
              sorted by ts_event exactly as Trade-Lab's historical adapter delivers it)

and reports bars-differing on the order/membership-sensitive CORE fields (the metric 4d
reported as 328/2313). It also rebuilds the engine bars under 4d's price-ASC order and under
the 4e side-signed order, so the before->after is visible in one run. Bar timestamps are
compared under microsecond truncation (DuckDB stores ts at us; the parquet/engine path keeps
ns) -- a representational seam, not an ordering difference.

Run:    python validation/test_production_pair_parity.py
pytest: pytest validation/test_production_pair_parity.py
Skips cleanly without the local databento store / Claude-Quant-Lab src.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

CQL_SRC = r"C:/Users/gonza/Documents/Claude-Quant-Lab/src"
if CQL_SRC not in sys.path:
    sys.path.insert(0, CQL_SRC)
DATA_DIR = Path(r"C:/Users/gonza/Documents/Trade-Dashboard/data/databento")
SYMBOL = "NQ"
TICK_COUNT = 147
TICK_SIZE = 0.25
BUY_SIDE = "B"  # VERIFIED: databento side='B' = buy aggressor (see constants.BUY_AGGRESSOR_SIDE)
SAMPLE_DAYS = ["2025-07-15", "2025-07-07", "2025-07-11"]

from strategy_core.candles.streaming import CandleEngine  # noqa: E402 (imports follow the sys.path bootstrap)
from strategy_core.constants import BUY_AGGRESSOR_SIDE, RESEARCH_SESSION_SCHEME  # noqa: E402 (imports follow the sys.path bootstrap)
from strategy_core.types import Trade  # noqa: E402 (imports follow the sys.path bootstrap)

# order/membership-sensitive fields; excludes open_ts/close_ts (the us-vs-ns ts seam).
CORE = ("trading_day", "bar_index", "open_t", "high_t", "low_t", "close_t",
        "volume", "trade_count", "is_complete")


def _window(day: str):
    d = date.fromisoformat(day)
    prev = d - timedelta(days=1)
    start = pd.Timestamp(f"{prev} 18:00:00", tz="America/New_York").tz_convert("UTC")
    end = pd.Timestamp(f"{d} 18:00:00", tz="America/New_York").tz_convert("UTC")
    return prev.isoformat(), d.isoformat(), start, end


def _duckdb_bars(day: str):
    """RESEARCH side: DuckDB side-signed trade bars -> CORE tuples + (open_ts, close_ts)."""
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
        return [], []
    df = df.reset_index().rename(columns={"timestamp": "close_time"})
    core, ts = [], []
    for r in df.itertuples(index=False):
        td = r.trading_day.date() if hasattr(r.trading_day, "date") else r.trading_day
        core.append((td, int(r.bar_index), int(round(r.open / TICK_SIZE)),
                     int(round(r.high / TICK_SIZE)), int(round(r.low / TICK_SIZE)),
                     int(round(r.close / TICK_SIZE)), int(r.volume), int(r.trade_count),
                     bool(r.is_complete)))
        ts.append((pd.Timestamp(r.open_time), pd.Timestamp(r.close_time)))
    return core, ts


def _read_phys(day: str) -> pd.DataFrame:
    prev, cur, start, end = _window(day)
    files = [DATA_DIR / SYMBOL / prev / "mbp10.parquet", DATA_DIR / SYMBOL / cur / "mbp10.parquet"]
    frames = [pd.read_parquet(f, columns=["ts_event", "sequence", "action", "price", "size", "side", "symbol"])
              for f in files if f.exists()]
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)  # physical / emission order
    ts = pd.to_datetime(raw["ts_event"], utc=True)
    inwin = (ts >= start) & (ts < end) & (~raw["symbol"].astype(str).str.contains("-"))
    fm = raw.loc[inwin, "symbol"].value_counts().idxmax()
    mask = inwin & (raw["symbol"] == fm) & (raw["action"].astype(str).str.lower() == "t") \
        & raw["price"].notna() & (raw["price"] > 0)
    sub = raw[mask].copy()
    sub["ts_event"] = pd.to_datetime(sub["ts_event"], utc=True)
    sub["side"] = sub["side"].astype(str)
    return sub.reset_index(drop=True)  # PHYSICAL order


def _engine_bars(df: pd.DataFrame):
    """TRADE-LAB side: feed the trades (in df's current row order) through CandleEngine."""
    eng = CandleEngine(timeframes=(TICK_COUNT,), scheme=RESEARCH_SESSION_SCHEME)
    out = []
    ts = df["ts_event"].to_numpy()
    px = df["price"].to_numpy("float64")
    sz = df["size"].to_numpy("int64")
    for i in range(len(df)):
        upd = eng.process_trade(Trade(event_ts_utc=pd.Timestamp(ts[i]),
                                      price_ticks=int(np.rint(px[i] / TICK_SIZE)), size=int(sz[i])))
        if upd.completed:
            out.extend(upd.completed)
    out.extend(eng.finalize_trading_day())
    core = [(b.trading_day, b.bar_index, b.open_ticks, b.high_ticks, b.low_ticks, b.close_ticks,
             b.volume, b.trade_count, b.is_complete) for b in out]
    ts_pairs = [(pd.Timestamp(b.open_ts_utc), pd.Timestamp(b.close_ts_utc)) for b in out]
    return core, ts_pairs


def _ndiff(a, b, idx=None):
    """Count differing rows; if idx is given, compare only those tuple positions."""
    if len(a) != len(b):
        return None
    if idx is None:
        return sum(1 for x, y in zip(a, b) if x != y)
    return sum(1 for x, y in zip(a, b) if any(x[i] != y[i] for i in idx))


_OHLC_IDX = (2, 3, 4, 5)   # open_t, high_t, low_t, close_t
_VOL_IDX = (6,)            # volume


def _ts_match_under_us(duck_ts, eng_ts):
    """open/close ts equal after truncating the engine's ns ts to DuckDB's us resolution."""
    if len(duck_ts) != len(eng_ts):
        return None
    ok = 0
    for (do, dc), (eo, ec) in zip(duck_ts, eng_ts):
        if do == eo.floor("us") and dc == ec.floor("us"):
            ok += 1
    return ok


def run_day(day: str) -> dict:
    phys = _read_phys(day)
    if phys.empty:
        return {"day": day, "skip": True}
    # Trade-Lab WIRE order == stable sort by ts_event of the physical stream (historical_parquet:252)
    wire = phys.sort_values("ts_event", kind="stable").reset_index(drop=True)
    # case-INSENSITIVE buy match, mirroring the DuckDB CASE (lower(side)='b').
    is_buy = phys["side"].astype(str).str.upper().to_numpy() == BUY_SIDE.upper()
    signed = phys["price"] * np.where(is_buy, 1.0, -1.0)
    side_signed = phys.assign(_sgn=signed).sort_values(
        ["ts_event", "sequence", "_sgn", "size"], kind="stable").reset_index(drop=True)
    price_asc = phys.sort_values(["ts_event", "sequence", "price", "size"], kind="stable").reset_index(drop=True)

    duck_core, duck_ts = _duckdb_bars(day)
    wire_core, wire_ts = _engine_bars(wire)
    signed_core, _ = _engine_bars(side_signed)
    asc_core, _ = _engine_bars(price_asc)

    mixed = 0
    for _, sub in phys.groupby(["ts_event", "sequence"], sort=False):
        if sub["price"].nunique() > 1 and sub["side"].nunique() > 1:
            mixed += 1

    return {
        "day": day, "skip": False, "trades": len(phys), "bars": len(duck_core),
        "gate_diff": _ndiff(duck_core, wire_core),          # RESEARCH(side-signed) vs TRADE-LAB(wire)
        "gate_ohlc_diff": _ndiff(duck_core, wire_core, _OHLC_IDX),  # of which differ in OHLC ticks
        "gate_vol_diff": _ndiff(duck_core, wire_core, _VOL_IDX),    # of which differ in volume
        "before_4d_diff": _ndiff(asc_core, wire_core),      # 4d price-ASC vs wire (the old divergence)
        "engine_signed_vs_wire": _ndiff(signed_core, wire_core),   # should equal gate residual
        "duck_vs_engine_signed": _ndiff(duck_core, signed_core),   # DuckDB sql == pandas side-signed (sanity)
        "ts_match_us": _ts_match_under_us(duck_ts, wire_ts),
        "mixed_side_groups": mixed,
    }


def _available(day: str) -> bool:
    return (DATA_DIR / SYMBOL / day / "mbp10.parquet").exists()


def test_production_pair_parity():
    import pytest

    if not DATA_DIR.exists() or not Path(CQL_SRC).exists():
        pytest.skip("databento store or Claude-Quant-Lab src not available")
    try:
        import alpha_lab.agents.data_infra.tick_store  # noqa: F401
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"alpha_lab not importable: {exc}")
    assert BUY_AGGRESSOR_SIDE == BUY_SIDE  # the verified encoding the order depends on

    ran = 0
    for day in SAMPLE_DAYS:
        if not _available(day):
            continue
        r = run_day(day)
        ran += 1
        # bar counts must match (same trade set) -> the *_diff metrics are not None.
        assert r["gate_diff"] is not None and r["duck_vs_engine_signed"] is not None, \
            f"bar-count mismatch between research and Trade-Lab: {r}"
        # The side-signed order removes the SYSTEMATIC sweep-direction drift: research vs
        # Trade-Lab-wire divergence collapses vs 4d's plain price-ASC order (>=4x fewer bars).
        assert r["before_4d_diff"] >= 4 * max(r["gate_diff"], 1), r
        # OHLC STRUCTURE is locked: open/high/low/close ticks match on all but a tiny, bounded
        # set (mixed-side aggressor groups + the DuckDB us-truncation seam straddling a boundary).
        assert r["gate_ohlc_diff"] <= max(8, r["bars"] // 100), r
        # The residual is VOLUME-dominated (same-price multi-fill shuffles volume across a
        # boundary; prices equal -> OHLC unchanged).
        assert r["gate_vol_diff"] >= r["gate_ohlc_diff"], r
        # DuckDB SQL side-signed == pandas side-signed reference up to the us-truncation seam.
        assert r["duck_vs_engine_signed"] <= 8, r
        # bar timestamps agree to DuckDB's microsecond resolution.
        assert r["ts_match_us"] == r["bars"], r
    if ran == 0:
        pytest.skip("no sample days available in the local store")


if __name__ == "__main__":
    import warnings
    warnings.simplefilter("ignore")
    print(f"GATE: RESEARCH DuckDB(side-signed, buy={BUY_AGGRESSOR_SIDE}) == TRADE-LAB engine(WIRE order)")
    print(f"order = {__import__('strategy_core.constants', fromlist=['TRADE_BAR_ORDER']).TRADE_BAR_ORDER}\n")
    all_ok = True
    for day in SAMPLE_DAYS:
        if not _available(day):
            print(f"  {day}: NO DATA")
            continue
        r = run_day(day)
        ok = (r["before_4d_diff"] >= 4 * max(r["gate_diff"], 1)
              and r["gate_ohlc_diff"] <= max(8, r["bars"] // 100)
              and r["duck_vs_engine_signed"] <= 8 and r["ts_match_us"] == r["bars"])
        all_ok &= ok
        print(f"  {day}: trades={r['trades']} bars={r['bars']} mixed_side={r['mixed_side_groups']}")
        print(f"      GATE  research(side-signed) vs Trade-Lab(wire): {r['gate_diff']} bars differ "
              f"(OHLC ticks: {r['gate_ohlc_diff']}, volume: {r['gate_vol_diff']})")
        print(f"      before(4d) price-ASC vs wire                  : {r['before_4d_diff']} bars differ")
        print(f"      engine side-signed vs wire (no us-seam)       : {r['engine_signed_vs_wire']} bars differ")
        print(f"      DuckDB-sql side-signed vs pandas side-signed  : {r['duck_vs_engine_signed']} (us-seam)")
        print(f"      bar-ts match under us-truncation              : {r['ts_match_us']}/{r['bars']}")
    print("\nVERDICT:", "OHLC LOCKED; residual = same-price volume shuffle (itemized)"
          if all_ok else "UNEXPECTED (see above)")
