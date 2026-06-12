"""Standing parity test: research DuckDB batch bars == engine STREAMING bars, BYTE-FOR-BYTE.

Why this pair: research trains on DuckDB-built bars; Trade-Lab serves on streaming-built
bars. Zero-drift requires the two to be identical on the SAME spec.

The spec is TRADE-PRICE tick bars -- a "tick" is a trade print (action='T'), OHLC from the
trade `price` (NQ trade grid 0.25, lossless integer ticks; phase 4d). Within a (ts_event,
sequence) matching event the sweep prints are ordered by SIDE-SIGNED price -- +price for a
buy aggressor (side='B'), -price for a sell -- so the order reproduces the chronological wire
direction (phase 4e, supersedes 4d's plain price-ascending order). Everything else is reused:
the 18:00-ET trading-day boundary and the kept trailing partial.
`TickStore.build_tick_bars`/`query_tick_events` default to `price_source='trade'`.

This is the SUPPORTING test: it feeds the EXACT trade stream DuckDB buckets
(`query_tick_events`, side-signed order) through the streaming `CandleEngine` and compares
every Bar field, proving the two builders agree byte-for-byte on the SAME order. The GATE
(research vs Trade-Lab's real WIRE order) is `test_production_pair_parity.py`.

Requires: the Claude-Quant-Lab `duckdb-18et-boundary` branch (`build_tick_bars` +
`query_tick_events` with `price_source`) and the local databento store. Skips cleanly if
either is absent, so it is a real standing test, not a throwaway harness.

Run directly:  python validation/test_duckdb_streaming_parity.py
Or via pytest: pytest validation/test_duckdb_streaming_parity.py
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
TICK_SIZE = 0.25  # NQ trade prints land on the 0.25 grid -> lossless integer ticks

from strategy_core.candles._ids import make_bar_id  # noqa: E402 (imports follow the sys.path bootstrap)
from strategy_core.candles.streaming import CandleEngine  # noqa: E402 (imports follow the sys.path bootstrap)
from strategy_core.constants import RESEARCH_SESSION_SCHEME  # noqa: E402 (imports follow the sys.path bootstrap)
from strategy_core.types import Trade  # noqa: E402 (imports follow the sys.path bootstrap)

# ties-heavy big day; Sunday-Globex / 18:00-ET-seam day (Monday's trading day opens at
# Sunday 18:00 ET and pulls in the Sunday-evening Globex); ordinary RTH weekday.
SAMPLE_DAYS = ["2025-07-15", "2025-07-07", "2025-07-11"]


def _et_window(day: str):
    d = date.fromisoformat(day)
    prev = d - timedelta(days=1)
    start = pd.Timestamp(f"{prev.isoformat()} 18:00:00", tz="America/New_York").tz_convert("UTC")
    end = pd.Timestamp(f"{d.isoformat()} 18:00:00", tz="America/New_York").tz_convert("UTC")
    return prev.isoformat(), d.isoformat(), start, end


def _duckdb_rows(day: str):
    """Return DuckDB bars as comparable tuples + the ordered event frame."""
    from alpha_lab.agents.data_infra.tick_store import TickStore

    prev, cur, start, end = _et_window(day)
    st = TickStore(DATA_DIR)
    try:
        for ds in (prev, cur):
            st.register_symbol_date(SYMBOL, ds)
        bars = st.build_tick_bars(SYMBOL, start, end, tick_count=TICK_COUNT)
        events = st.query_tick_events(SYMBOL, start, end)
    finally:
        st.close()
    if bars.empty:
        return [], events
    bars = bars.reset_index().rename(columns={"timestamp": "close_time"})
    rows = []
    for r in bars.itertuples(index=False):
        complete = bool(r.is_complete)
        rows.append((
            r.trading_day.date() if hasattr(r.trading_day, "date") else r.trading_day,
            int(r.bar_index),
            pd.Timestamp(r.open_time),
            pd.Timestamp(r.close_time),
            int(round(r.open / TICK_SIZE)),
            int(round(r.high / TICK_SIZE)),
            int(round(r.low / TICK_SIZE)),
            int(round(r.close / TICK_SIZE)),
            int(r.volume),
            int(r.trade_count),
            complete,
            "complete" if complete else "end_of_day",
        ))
    return rows, events


def _streaming_rows(events: pd.DataFrame):
    """Feed the SAME ordered events through the streaming engine; return comparable tuples."""
    if events is None or events.empty:
        return []
    ts_series = events["ts_event"]  # datetime64[ns, UTC] -> yields ns-precision pd.Timestamp
    price_ticks = np.rint(events["price"].to_numpy(dtype="float64") / TICK_SIZE).astype("int64").tolist()
    sizes = events["size"].to_numpy(dtype="int64").tolist()

    eng = CandleEngine(timeframes=(TICK_COUNT,), scheme=RESEARCH_SESSION_SCHEME)
    bars = []
    for ts, pt, sz in zip(ts_series, price_ticks, sizes, strict=True):
        upd = eng.process_trade(Trade(event_ts_utc=ts, price_ticks=pt, size=sz))
        if upd.completed:
            bars.extend(upd.completed)
    bars.extend(eng.finalize_trading_day())  # day's trailing partial -> END_OF_DAY

    rows = []
    for b in bars:
        # bar_id is fully determined by (timeframe, trading_day, bar_index); verify it too.
        assert b.bar_id == make_bar_id(b.timeframe_ticks, b.trading_day, b.bar_index)
        rows.append((
            b.trading_day,
            b.bar_index,
            pd.Timestamp(b.open_ts_utc),
            pd.Timestamp(b.close_ts_utc),
            b.open_ticks,
            b.high_ticks,
            b.low_ticks,
            b.close_ticks,
            b.volume,
            b.trade_count,
            b.is_complete,
            (b.close_reason.value if b.close_reason is not None else None),
        ))
    return rows


_FIELDS = ("trading_day", "bar_index", "open_ts", "close_ts", "open_t", "high_t",
           "low_t", "close_t", "volume", "trade_count", "is_complete", "close_reason")


def _first_diff(duck, stream):
    if len(duck) != len(stream):
        return f"BAR COUNT differs: duckdb={len(duck)} streaming={len(stream)}"
    for i, (a, b) in enumerate(zip(duck, stream)):
        if a != b:
            diffs = [f"{_FIELDS[j]}: duck={a[j]!r} stream={b[j]!r}" for j in range(len(a)) if a[j] != b[j]]
            return f"bar #{i}: " + "; ".join(diffs)
    return None


def run_day(day: str) -> dict:
    duck, events = _duckdb_rows(day)
    stream = _streaming_rows(events)
    n_partial_duck = sum(1 for r in duck if not r[10])
    n_partial_stream = sum(1 for r in stream if not r[10])
    diff = _first_diff(duck, stream)
    return {
        "day": day, "events": (0 if events is None else len(events)),
        "duck_bars": len(duck), "stream_bars": len(stream),
        "trailing_partial_duck": n_partial_duck, "trailing_partial_stream": n_partial_stream,
        "byte_identical": diff is None, "first_diff": diff,
    }


def _available(day: str) -> bool:
    return (DATA_DIR / SYMBOL / day / "mbp10.parquet").exists()


def test_duckdb_streaming_parity():
    import pytest

    if not DATA_DIR.exists() or not Path(CQL_SRC).exists():
        pytest.skip("databento store or Claude-Quant-Lab src not available")
    try:
        import alpha_lab.agents.data_infra.tick_store  # noqa: F401
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"alpha_lab not importable: {exc}")

    ran = 0
    for day in SAMPLE_DAYS:
        if not _available(day):
            continue
        res = run_day(day)
        ran += 1
        assert res["trailing_partial_duck"] == res["trailing_partial_stream"], res
        assert res["byte_identical"], res["first_diff"]
    if ran == 0:
        pytest.skip("no sample days available in the local store")


if __name__ == "__main__":
    import warnings
    warnings.simplefilter("ignore")
    print(f"Engine boundary={RESEARCH_SESSION_SCHEME.trading_day_boundary} "
          f"tz={RESEARCH_SESSION_SCHEME.timezone}; bars=TRADE-PRICE tick (action='T', tick {TICK_SIZE}); "
          f"order=(ts_event, sequence, side_signed_price, size) [intrinsic]")
    all_ok = True
    for day in SAMPLE_DAYS:
        if not _available(day):
            print(f"  {day}: NO DATA (skip)")
            continue
        r = run_day(day)
        ok = r["byte_identical"] and r["trailing_partial_duck"] == r["trailing_partial_stream"]
        all_ok &= ok
        print(f"  {day}: events={r['events']} duck_bars={r['duck_bars']} stream_bars={r['stream_bars']} "
              f"trailing_partial(duck={r['trailing_partial_duck']},stream={r['trailing_partial_stream']}) "
              f"BYTE_IDENTICAL={r['byte_identical']}")
        if r["first_diff"]:
            print(f"      FIRST DIFF: {r['first_diff']}")
    print("VERDICT:", "ALL BYTE-IDENTICAL" if all_ok else "MISMATCH (see above)")
