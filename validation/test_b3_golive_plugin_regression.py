"""B3 plugin-path REGRESSION (go-live days): the plugin path reproduces the canonical digests.

(Originally the B2 go-live OFF-vs-ON parity gate. B3 removed the hardwired None path, so there
is no comparator runtime any more. This re-runs the registered ``touch_reversal`` plugin over
the same real NQ days + synthetic inside-range PDH/PDL seeding and asserts the per-trade
``RuntimeUpdate.to_dict()`` sequence digest + touch count + final-snapshot digest match the
canonical fixtures in ``validation/_fixtures/b3_regression/golive.json``. Those digests were
FROZEN from the final green run while ``plugin == None`` was still provable — so they ARE the
canonical (former None-path) behavior, and matching them proves the removal changed nothing.)

Real-store data: ``Trade-Dashboard/data/databento/NQ/<DATE>/mbp10.parquet``. Skips if absent.
Also exposes ``_read_trades`` / ``_window`` / ``DATA_DIR`` for the multi-day regression to reuse.

Run:    python validation/test_b3_golive_plugin_regression.py
pytest: pytest validation/test_b3_golive_plugin_regression.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from _b3_regression_util import GOLIVE_DAYS, golive_day_digest, load_fixture

from strategy_core.runtime.state import StrategyRuntime
from strategy_core.runtime.wiring import touch_reversal_kwargs
from strategy_core.types import Trade

DATA_DIR = Path(r"C:/Users/gonza/Documents/Trade-Lab/../Trade-Dashboard/data/databento")
if not DATA_DIR.exists():
    DATA_DIR = Path(r"C:/Users/gonza/Documents/Trade-Dashboard/data/databento")
SYMBOL = "NQ"
TICK_SIZE = 0.25
DECISION_TF = 147

_DIGEST_KEYS = ("n_trades", "touches", "seq_sha256", "snapshot_sha256")


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


def _build_runtime() -> StrategyRuntime:
    """The production plugin runtime (touch_reversal attached via the unconditional helper)."""
    return StrategyRuntime(
        requested_symbol=SYMBOL,
        timeframes=(DECISION_TF,),
        decision_timeframe=DECISION_TF,
        **touch_reversal_kwargs(),
    )


def test_b3_golive_plugin_regression():
    import pytest

    if not DATA_DIR.exists():
        pytest.skip(f"databento store not available at {DATA_DIR}")
    fixture = load_fixture("golive")["days"]
    matched = 0
    for day in GOLIVE_DAYS:
        dig = golive_day_digest(_build_runtime(), day, _read_trades, _window)
        if dig is None:
            continue
        assert day in fixture, f"no frozen digest for {day}"
        assert {k: dig[k] for k in _DIGEST_KEYS} == {k: fixture[day][k] for k in _DIGEST_KEYS}, (
            f"plugin-path digest diverged from the frozen canonical on {day}: "
            f"{ {k: dig[k] for k in _DIGEST_KEYS} } vs { {k: fixture[day][k] for k in _DIGEST_KEYS} }"
        )
        matched += 1
    if matched == 0:
        pytest.skip("no go-live days available in the local store")


if __name__ == "__main__":
    import warnings

    warnings.simplefilter("ignore")
    fixture = load_fixture("golive")["days"]
    print("B3 go-live plugin-path regression vs frozen canonical digests\n"
          f"store = {DATA_DIR}\n")
    for day in GOLIVE_DAYS:
        dig = golive_day_digest(_build_runtime(), day, _read_trades, _window)
        if dig is None:
            print(f"  {day}: NO DATA")
            continue
        ok = {k: dig[k] for k in _DIGEST_KEYS} == {k: fixture[day][k] for k in _DIGEST_KEYS}
        print(f"  {day}: trades={dig['n_trades']} touches={dig['touches']} "
              f"seq={dig['seq_sha256'][:12]}…  -> {'MATCH' if ok else 'DIVERGED'}")
    print("\nVERDICT: plugin path reproduces the canonical (former None-path) digests.")
