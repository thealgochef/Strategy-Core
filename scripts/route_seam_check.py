#!/usr/bin/env python3
"""W2 P5 (D-P-03): one-shot route-seam shape check — Historical API vs parquet.

Live warm-start fetches its slice from the Databento Historical API while
research/replay consume the local mbp-10 parquets through the canonical
``DatabentoParquetSource`` L1 projection. This script checks the two routes
against each other ONCE for a single trading day:

* trade count + a sequence-identity sample of (ts_event_ns, price_ticks, size)
* TOB-transition count (the canonical post-merge L1 dedup applied to both)
* first/last event instants per route

It is a SCRIPT, not a standing test (D-P-03: "shape-checked against each other
once"). Requires ``DATABENTO_API_KEY``; exits with a clear message when absent.
One attempt — no loops or retries on API errors.

Usage:
    python scripts/route_seam_check.py [--day 2026-02-18]
        [--symbol-dir <store>/NQ] [--out route_seam_report.json]
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from strategy_core.constants import SESSION_TIMEZONE, TRADING_DAY_BOUNDARY
from strategy_core.data.databento_parquet import DatabentoParquetSource
from strategy_core.types import Quote, Trade

_DEFAULT_DAY = "2026-02-18"
_DEFAULT_SYMBOL_DIR = Path(r"C:/Users/gonza/Documents/Trade-Dashboard/data/databento/NQ")
_DEFAULT_OUT = Path("route_seam_report.json")
_DATASET = "GLBX.MDP3"
_REQUESTED_SYMBOL = "NQ.c.0"
_STYPE_IN = "continuous"
_SAMPLE_POSITIONS = 25
_PRICE_SCALE = 1_000_000_000
_TICK_SIZE = 0.25


def _trading_day_window_utc(trading_day: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(SESSION_TIMEZONE)
    boundary = TRADING_DAY_BOUNDARY if isinstance(TRADING_DAY_BOUNDARY, time) else time(18, 0)
    start = datetime.combine(trading_day - timedelta(days=1), boundary, tzinfo=tz)
    end = datetime.combine(trading_day, boundary, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def _ns(ts: datetime) -> int:
    return int(ts.timestamp() * 1_000_000) * 1_000  # µs precision; both routes share it


def _summarize_stream(events) -> dict:
    """Reduce an (ordered) Trade/Quote stream to the seam-check shape."""

    trade_count = 0
    tob_transitions = 0
    last_tob: tuple[int, int, int, int] | None = None
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    trades: list[tuple[int, int, int]] = []
    for event in events:
        if isinstance(event, Trade):
            trade_count += 1
            trades.append((_ns(event.event_ts_utc), event.price_ticks, event.size))
        elif isinstance(event, Quote):
            tob = (
                event.bid_price_ticks,
                event.ask_price_ticks,
                event.bid_size,
                event.ask_size,
            )
            if tob != last_tob:
                last_tob = tob
                tob_transitions += 1
        else:
            continue  # data-quality warnings are not seam-shape inputs
        ts = event.event_ts_utc
        if first_ts is None:
            first_ts = ts
        last_ts = ts
    return {
        "trade_count": trade_count,
        "tob_transitions": tob_transitions,
        "first_event_utc": None if first_ts is None else first_ts.isoformat(),
        "last_event_utc": None if last_ts is None else last_ts.isoformat(),
        "_trades": trades,
    }


def _parquet_route(symbol_dir: Path, trading_day: date) -> dict:
    source = DatabentoParquetSource.for_trading_day(
        symbol_dir, trading_day, requested_symbol=_REQUESTED_SYMBOL
    )
    summary = _summarize_stream(source.events())
    summary["route"] = "parquet (DatabentoParquetSource.for_trading_day)"
    return summary


def _api_route(api_key: str, trading_day: date) -> dict:
    import databento

    client = databento.Historical(api_key)
    start, end = _trading_day_window_utc(trading_day)

    def fetch(schema: str):
        return client.timeseries.get_range(
            dataset=_DATASET,
            schema=schema,
            symbols=[_REQUESTED_SYMBOL],
            stype_in=_STYPE_IN,
            start=start,
            end=end,
        )

    def stream():
        import heapq

        def records(store, kind):
            for record in store:
                yield (_record_ts(record), kind, record)

        merged = heapq.merge(
            records(fetch("trades"), "trade"),
            records(fetch("mbp-1"), "quote"),
            key=lambda item: item[0],
        )
        for ts_ns, kind, record in merged:
            ts = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=ts_ns // 1_000)
            if kind == "trade":
                yield Trade(
                    event_ts_utc=ts,
                    price_ticks=round(record.price / _PRICE_SCALE / _TICK_SIZE),
                    size=int(record.size),
                    side=str(getattr(record, "side", "N")),
                )
            else:
                level = record.levels[0]
                yield Quote(
                    event_ts_utc=ts,
                    bid_price_ticks=round(level.bid_px / _PRICE_SCALE / _TICK_SIZE),
                    ask_price_ticks=round(level.ask_px / _PRICE_SCALE / _TICK_SIZE),
                    bid_size=int(level.bid_sz),
                    ask_size=int(level.ask_sz),
                )

    summary = _summarize_stream(stream())
    summary["route"] = "historical API (trades + mbp-1, canonical L1 dedup)"
    return summary


def _record_ts(record) -> int:
    value = getattr(record, "ts_event", None)
    if value is None:
        value = getattr(getattr(record, "hdr", None), "ts_event", 0)
    return int(value or 0)


def _sequence_sample(parquet_trades, api_trades) -> dict:
    count = min(len(parquet_trades), len(api_trades))
    if count == 0:
        return {"positions_compared": 0, "mismatches": []}
    step = max(count // _SAMPLE_POSITIONS, 1)
    positions = list(range(0, count, step))[:_SAMPLE_POSITIONS]
    mismatches = [
        {"position": i, "parquet": parquet_trades[i], "api": api_trades[i]}
        for i in positions
        if parquet_trades[i] != api_trades[i]
    ]
    return {"positions_compared": len(positions), "mismatches": mismatches}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", default=_DEFAULT_DAY)
    parser.add_argument("--symbol-dir", type=Path, default=_DEFAULT_SYMBOL_DIR)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = parser.parse_args()

    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        print(
            "route_seam_check: DATABENTO_API_KEY is not set — the API side of the "
            "seam cannot be fetched. Set the key and re-run; no report written."
        )
        return 2
    trading_day = date.fromisoformat(args.day)
    if not args.symbol_dir.exists():
        print(f"route_seam_check: symbol dir not found: {args.symbol_dir}; no report written.")
        return 2

    parquet = _parquet_route(args.symbol_dir, trading_day)
    api = _api_route(api_key, trading_day)
    sample = _sequence_sample(parquet.pop("_trades"), api.pop("_trades"))
    report = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "trading_day": trading_day.isoformat(),
        "requested_symbol": _REQUESTED_SYMBOL,
        "parquet": parquet,
        "api": api,
        "diff": {
            "trade_count_delta": api["trade_count"] - parquet["trade_count"],
            "tob_transition_delta": api["tob_transitions"] - parquet["tob_transitions"],
            "first_event_equal": parquet["first_event_utc"] == api["first_event_utc"],
            "last_event_equal": parquet["last_event_utc"] == api["last_event_utc"],
            "trade_sequence_sample": sample,
        },
    }
    text = json.dumps(report, indent=2)
    print(text)
    args.out.write_text(text, encoding="utf-8")
    print(f"route_seam_check: report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
