"""Phase-4d LIVE-ORDER analysis for TRADE-PRICE tick bars (closes the 4c §5 caveat).

The standing parity test (`test_duckdb_streaming_parity.py`) proves DuckDB-batch ==
streaming when BOTH consume the deterministic composite order
`(ts_event, sequence, price, size)`. This harness asks the *production* question §5 raised:
does the LIVE WIRE order reproduce that composite order, or does Trade-Lab have to reorder?

It reads the front-month trade stream from the raw mbp-10 parquet in PHYSICAL
(databento emission / ts_recv) order and, on the SAME trade set, builds 147t trade bars
under three orderings, comparing bucket-membership-sensitive fields (open/high/low/close
ticks, volume, trade_count -- timestamps excluded so the sub-microsecond DuckDB-vs-ns ts
artifact does not contaminate the comparison):

  COMP  = composite replay order  (ts_event, sequence, price, size)   [= the proven DuckDB order]
  TE    = stable sort by ts_event only (wire sub-order kept within equal ts_event)
  PHYS  = raw physical/arrival order (no sort = naive live feed)

Decomposition:
  TE vs PHYS   -> GLOBAL ts_event-vs-arrival jitter (measured: 0 -- the wire is already
                  ts_event-monotonic, so no large reorder window is needed).
  COMP vs PHYS -> the within-(ts_event, sequence) sub-key effect: the composite key sorts
                  price ASCENDING, which REVERSES descending (sell) sweeps relative to the
                  wire. Each matching event's prints are a CONTIGUOUS monotonic burst, so a
                  bounded single-event reorder buffer (sort the burst by price asc) makes
                  live == replay. The databento aggressor `side` (VERIFIED in phase 4e:
                  B=buy/ascending, A=sell/descending) is fully populated on trades, so a
                  deterministic side-signed-price order reproduces CHRONOLOGICAL wire order
                  directly -- implemented in phase 4e (see test_production_pair_parity.py).

Read-only. Requires the local databento store; skips cleanly otherwise.
Run:  python validation/phase4d_liveorder.py
"""
from __future__ import annotations

import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_core.candles.streaming import CandleEngine
from strategy_core.constants import RESEARCH_SESSION_SCHEME
from strategy_core.types import Trade

DATA = Path(r"C:/Users/gonza/Documents/Trade-Dashboard/data/databento")
SYMBOL = "NQ"
TICK_COUNT = 147
TICK_SIZE = 0.25
SAMPLE_DAYS = ["2025-07-15", "2025-07-07", "2025-07-11"]
# order/membership-sensitive bar fields; excludes open_ts/close_ts (sub-us ts artifact).
CORE = ("trading_day", "bar_index", "open_t", "high_t", "low_t", "close_t",
        "volume", "trade_count", "is_complete")


def _window(day: str):
    d = date.fromisoformat(day)
    prev = d - timedelta(days=1)
    start = pd.Timestamp(f"{prev} 18:00:00", tz="America/New_York").tz_convert("UTC")
    end = pd.Timestamp(f"{d} 18:00:00", tz="America/New_York").tz_convert("UTC")
    return prev.isoformat(), d.isoformat(), start, end


def _read_phys(day: str) -> pd.DataFrame:
    prev, cur, start, end = _window(day)
    files = [DATA / SYMBOL / prev / "mbp10.parquet", DATA / SYMBOL / cur / "mbp10.parquet"]
    frames = [
        pd.read_parquet(f, columns=["ts_event", "sequence", "action", "price", "size", "side", "symbol"])
        for f in files if f.exists()
    ]
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)  # physical order: prev file then cur file
    ts = pd.to_datetime(raw["ts_event"], utc=True)
    inwin = (ts >= start) & (ts < end) & (~raw["symbol"].astype(str).str.contains("-"))
    fm = raw.loc[inwin, "symbol"].value_counts().idxmax()
    mask = inwin & (raw["symbol"] == fm) & (raw["action"].astype(str).str.lower() == "t") \
        & raw["price"].notna() & (raw["price"] > 0)
    sub = raw[mask].copy()
    sub["ts_event"] = pd.to_datetime(sub["ts_event"], utc=True)
    return sub.reset_index(drop=True)  # PHYSICAL order, no sort


def _bars(df: pd.DataFrame) -> list[tuple]:
    eng = CandleEngine(timeframes=(TICK_COUNT,), scheme=RESEARCH_SESSION_SCHEME)
    out = []
    ts = df["ts_event"].to_numpy()
    px = df["price"].to_numpy("float64")
    sz = df["size"].to_numpy("int64")
    for i in range(len(df)):
        pt = int(np.rint(px[i] / TICK_SIZE))
        upd = eng.process_trade(Trade(event_ts_utc=pd.Timestamp(ts[i]), price_ticks=pt, size=int(sz[i])))
        if upd.completed:
            out.extend(upd.completed)
    out.extend(eng.finalize_trading_day())
    return [
        (b.trading_day, b.bar_index, b.open_ticks, b.high_ticks, b.low_ticks,
         b.close_ticks, b.volume, b.trade_count, b.is_complete)
        for b in out
    ]


def _ndiff(a: list[tuple], b: list[tuple]) -> tuple[int | None, dict]:
    if len(a) != len(b):
        return None, {"COUNT": f"{len(a)} vs {len(b)}"}
    n, fc = 0, {}
    for x, y in zip(a, b):
        if x != y:
            n += 1
            for j in range(len(x)):
                if x[j] != y[j]:
                    fc[CORE[j]] = fc.get(CORE[j], 0) + 1
    return n, fc


def _sweep_breakdown(phys: pd.DataFrame) -> dict:
    phys = phys.assign(arr=range(len(phys)))
    asc = desc = nonmono = noncontig = mixed_side = 0
    for _, sub in phys.groupby(["ts_event", "sequence"], sort=False):
        if sub["price"].nunique() <= 1:
            continue
        a = sub["arr"].to_numpy()
        if a.max() - a.min() != len(a) - 1:
            noncontig += 1
        if sub["side"].nunique() > 1:
            mixed_side += 1
        p = sub.sort_values("arr")["price"].to_numpy()
        nondec = all(p[i] <= p[i + 1] for i in range(len(p) - 1))
        noninc = all(p[i] >= p[i + 1] for i in range(len(p) - 1))
        if nondec and not noninc:
            asc += 1
        elif noninc and not nondec:
            desc += 1
        else:
            nonmono += 1
    return {"asc": asc, "desc": desc, "nonmono": nonmono,
            "noncontig": noncontig, "mixed_side": mixed_side}


def run_day(day: str) -> dict:
    phys = _read_phys(day)
    if phys.empty:
        return {"day": day, "skip": True}
    te_ns = phys["ts_event"].astype("int64").to_numpy()
    inversions = int((np.diff(te_ns) < 0).sum()) if len(phys) > 1 else 0
    comp = phys.sort_values(["ts_event", "sequence", "price", "size"], kind="stable").reset_index(drop=True)
    te = phys.sort_values(["ts_event"], kind="stable").reset_index(drop=True)
    b_comp, b_te, b_phys = _bars(comp), _bars(te), _bars(phys)
    n_tp, _ = _ndiff(b_te, b_phys)
    n_cp, fc_cp = _ndiff(b_comp, b_phys)
    return {
        "day": day, "skip": False, "trades": len(phys), "bars": len(b_comp),
        "ts_event_inversions": inversions,
        "te_vs_phys_diff_bars": n_tp,
        "comp_vs_phys_diff_bars": n_cp, "comp_vs_phys_fields": fc_cp,
        "sweeps": _sweep_breakdown(phys),
    }


def main() -> None:
    warnings.simplefilter("ignore")
    if not DATA.exists():
        print("databento store not available; skipping")
        return
    print("PHASE-4d LIVE-ORDER: replay composite order vs wire physical order (147t trade bars)\n")
    for day in SAMPLE_DAYS:
        if not (DATA / SYMBOL / day / "mbp10.parquet").exists():
            print(f"  {day}: NO DATA")
            continue
        r = run_day(day)
        if r["skip"]:
            print(f"  {day}: NO DATA")
            continue
        s = r["sweeps"]
        print(f"  {day}: trades={r['trades']} bars={r['bars']}")
        print(f"      ts_event inversions in wire order = {r['ts_event_inversions']}  "
              f"(0 => no global arrival jitter; TE==PHYS diff_bars={r['te_vs_phys_diff_bars']})")
        print(f"      multi-price sweeps: asc(buy)={s['asc']} desc(sell)={s['desc']} "
              f"non-monotonic={s['nonmono']} non-contiguous={s['noncontig']} mixed-side={s['mixed_side']}")
        print(f"      COMP vs WIRE (naive live, no reorder): {r['comp_vs_phys_diff_bars']} bars differ  "
              f"{r['comp_vs_phys_fields']}")
    print("\nFINDING: wire order is ts_event-monotonic with no global jitter; the only divergence is")
    print("the composite key sorting price ASCENDING, which reverses descending (sell) sweeps. Each")
    print("matching event is a contiguous monotonic burst, so a bounded per-event reorder buffer (or a")
    print("deterministic side-signed-price order) makes live == replay. The DuckDB<->streaming parity")
    print("gate itself is unaffected: both sides use the composite order and are byte-identical.")


if __name__ == "__main__":
    sys.exit(main())
