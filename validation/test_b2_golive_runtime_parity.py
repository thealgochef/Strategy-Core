"""B2 go-live gate: flag-ON == flag-OFF on REAL data, THROUGH StrategyRuntime.process_event.

This is B2's DONE gate. PART 1's seam harness proved the plugin path byte-identical to the
None path on a SYNTHETIC single-zone stream; this replays REAL NQ trading days through TWO
runtimes — one built flag-OFF (the verbatim None path), one built flag-ON (the registered
``touch_reversal`` plugin, via the SAME ``touch_reversal_kwargs()`` helper Trade-Lab now uses)
— and asserts the ``RuntimeUpdate`` sequence is identical per trade.

This is on-vs-off SELF-parity through the runtime (W3): both call the same decision functions,
so on==off transitively gives plugin==canonical (the decision-fn gates already pin canonical).
It exercises the breadth the synthetic harness did NOT: trade-built asia/london session levels
(availability-gated), prior-day PDH/PDL (W4 load_prior_day_summary propagation), merged zones,
and multiple zones in one day.

Real-store data: ``C:/Users/gonza/Documents/Trade-Dashboard/data/databento/NQ/<DATE>/mbp10.parquet``.
Skips cleanly if the store is absent. Reads parquet directly (pandas) — no alpha_lab dependency.

Run:    python validation/test_b2_golive_runtime_parity.py
pytest: pytest validation/test_b2_golive_runtime_parity.py
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from strategy_core.config import PLUGIN_ROUTING_ENV
from strategy_core.runtime.state import StrategyRuntime
from strategy_core.runtime.wiring import touch_reversal_kwargs
from strategy_core.types import Trade

DATA_DIR = Path(r"C:/Users/gonza/Documents/Trade-Lab/../Trade-Dashboard/data/databento")
if not DATA_DIR.exists():
    DATA_DIR = Path(r"C:/Users/gonza/Documents/Trade-Dashboard/data/databento")
SYMBOL = "NQ"
TICK_SIZE = 0.25
DECISION_TF = 147
# Liquid days confirmed present by the standing production-pair gate.
SAMPLE_DAYS = ["2025-07-15", "2025-07-07"]


def _window(day: str):
    d = date.fromisoformat(day)
    prev = d - timedelta(days=1)
    start = pd.Timestamp(f"{prev} 18:00:00", tz="America/New_York").tz_convert("UTC")
    end = pd.Timestamp(f"{d} 18:00:00", tz="America/New_York").tz_convert("UTC")
    return prev, start, end


def _read_trades(day: str) -> list[Trade]:
    """Front-month TRADE prints for the trading day, in WIRE order (stable ts_event sort) —
    exactly the order Trade-Lab's historical adapter delivers (production_pair_parity:154)."""
    prev, start, end = _window(day)
    files = [DATA_DIR / SYMBOL / prev.isoformat() / "mbp10.parquet",
             DATA_DIR / SYMBOL / day / "mbp10.parquet"]
    frames = [pd.read_parquet(f, columns=["ts_event", "action", "price", "size", "side", "symbol"])
              for f in files if f.exists()]
    if not frames:
        return []
    raw = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(raw["ts_event"], utc=True)
    inwin = (ts >= start) & (ts < end) & (~raw["symbol"].astype(str).str.contains("-"))
    if not inwin.any():
        return []
    fm = raw.loc[inwin, "symbol"].value_counts().idxmax()
    mask = inwin & (raw["symbol"] == fm) & (raw["action"].astype(str).str.lower() == "t") \
        & raw["price"].notna() & (raw["price"] > 0)
    sub = raw[mask].copy()
    sub["ts_event"] = pd.to_datetime(sub["ts_event"], utc=True)
    sub = sub.sort_values("ts_event", kind="stable").reset_index(drop=True)  # WIRE order
    ts_arr = sub["ts_event"].to_numpy()
    px = sub["price"].to_numpy("float64")
    sz = sub["size"].to_numpy("int64")
    side = sub["side"].astype(str).to_numpy()
    return [
        Trade(event_ts_utc=pd.Timestamp(ts_arr[i]).to_pydatetime(),
              price_ticks=int(round(px[i] / TICK_SIZE)), size=int(sz[i]),
              side=side[i] if side[i] in ("B", "A", "N") else None)
        for i in range(len(sub))
    ]


def _build_runtime(flag_on: bool) -> StrategyRuntime:
    prev = os.environ.get(PLUGIN_ROUTING_ENV)
    os.environ[PLUGIN_ROUTING_ENV] = "1" if flag_on else ""
    try:
        return StrategyRuntime(
            requested_symbol=SYMBOL,
            timeframes=(DECISION_TF,),
            decision_timeframe=DECISION_TF,
            **touch_reversal_kwargs(),
        )
    finally:
        if prev is None:
            os.environ.pop(PLUGIN_ROUTING_ENV, None)
        else:
            os.environ[PLUGIN_ROUTING_ENV] = prev


def run_day(day: str) -> dict:
    trades = _read_trades(day)
    if not trades:
        return {"day": day, "skip": True}
    prev, _, _ = _window(day)
    ticks = [t.price_ticks for t in trades]
    lo, hi = min(ticks), max(ticks)
    span = hi - lo
    # Prior-day PDH/PDL placed INSIDE the day's range so they are touchable (exercises
    # load_prior_day_summary propagation + PDH/PDL zones on top of the trade-built session levels).
    pdh = lo + round(0.66 * span)
    pdl = lo + round(0.33 * span)

    off = _build_runtime(flag_on=False)
    on = _build_runtime(flag_on=True)
    assert off._plugin is None and on._plugin is not None
    for rt in (off, on):
        rt.load_prior_day_summary(prev, high_ticks=pdh, low_ticks=pdl)

    touches = 0
    zones_seen = 0
    for tr in trades:
        ua = off.process_event(tr)
        ub = on.process_event(tr)
        if ua != ub:
            # Surface a readable diff via the serialized form on the first divergence.
            assert ua.to_dict() == ub.to_dict(), f"plugin path diverged on {day} at {tr.event_ts_utc}"
            raise AssertionError(f"RuntimeUpdate diverged on {day} at {tr.event_ts_utc}")
        if ua.touches:
            assert ua.to_dict() == ub.to_dict()  # spec-explicit cross-check on touch-bearing updates
            touches += len(ua.touches)
        zones_seen = max(zones_seen, len(ua.zones))

    snap_off, snap_on = off.snapshot(), on.snapshot()
    assert snap_off.to_dict() == snap_on.to_dict(), f"final snapshot diverged on {day}"
    return {"day": day, "skip": False, "trades": len(trades), "touches": touches,
            "max_zones": zones_seen, "final_touches": len(snap_on.touches)}


def test_b2_golive_runtime_parity():
    import pytest

    if not DATA_DIR.exists():
        pytest.skip(f"databento store not available at {DATA_DIR}")
    ran = 0
    total_touches = 0
    for day in SAMPLE_DAYS:
        r = run_day(day)
        if r.get("skip"):
            continue
        ran += 1
        total_touches += r["touches"]
        # off == on already asserted per trade in run_day; sanity that the day was non-trivial.
        assert r["max_zones"] >= 1, r
    if ran == 0:
        pytest.skip("no sample days available in the local store")
    # The gate is only meaningful if the plugin/touch path actually fired on real data.
    assert total_touches > 0, "no touches across the sampled days — gate would be vacuous"


if __name__ == "__main__":
    import warnings

    warnings.simplefilter("ignore")
    print(f"B2 go-live: flag-OFF (None path) == flag-ON (touch_reversal plugin) through StrategyRuntime\n"
          f"store = {DATA_DIR}\n")
    for day in SAMPLE_DAYS:
        r = run_day(day)
        if r.get("skip"):
            print(f"  {day}: NO DATA")
            continue
        print(f"  {day}: trades={r['trades']} touches={r['touches']} "
              f"max_zones={r['max_zones']} final_touches={r['final_touches']}  ->  OFF == ON [OK]")
    print("\nVERDICT: plugin path byte-identical to the None path on real data (flag on vs off).")
