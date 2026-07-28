"""W3A-READER P3a IDENTITY PROOF: row-wise vs vectorized DatabentoParquetSource.

Full-trading-day, event-by-event compare on 2022-02-15 and 2026-02-18:
event count, order, type, and every field exactly equal (Trade: ts/price_ticks/
size/side; Quote: ts/bid/ask/bid_size/ask_size; DataQualityWarning: to_dict()).
ts compare is ns-exact (pd.Timestamp ==). First divergence reported with both
values. Then PURE timed drains (compare pass runs first so both timed drains see
an equally warm page cache).

Writes W3A_READER_PROOF.log. Re-runnable: python scratch_w3a_reader_proof.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import date, datetime
from itertools import zip_longest
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

from strategy_core.data.databento_parquet import DatabentoParquetSource
from strategy_core.data.events import DataQualityWarning
from strategy_core.types import Quote, Trade

STORE = Path(r"C:/Users/gonza/Documents/Claude-Quant-Lab/data/databento/NQ")
DAYS = (date(2022, 2, 15), date(2026, 2, 18))
LOG = Path(__file__).resolve().parent / "W3A_READER_PROOF.log"

# W3a P2 gate anchors (2026-02-12, fresh, config hash 7850272e):
GATE_PIPELINE_S = 1447.1
GATE_DRAIN_S = 513.4
GATE_DRAIN_EVENTS = 15_303_125
READER_PASSES = 2  # labeling pipeline drains the day stream twice
BUILD_DAYS = 60

CONTRACT = """\
PROOF COVERAGE (the P1 semantic contract this compare must hold over):
 1. L1 projection: mbp-10 row -> Trade iff upper(action) in {T, TRADE}; the SAME row
    also -> Quote iff any of the 8 TOB price-alias cells is non-null. trades schema:
    every row -> Trade only. mbp-1/bbo/tbbo: every row -> Quote only.
 2. TOB-change dedup: a Quote is emitted iff its (bid_ticks, ask_ticks, bid_size,
    ask_size) differs from the previous quote's in merged-stream order (state carries
    across files); first quote always emits. Trades never touch the state.
 3. Order: per batch (65,536 rows, same row groups), events stable-sorted by
    (ts_event, sequence, side_signed_price_ticks, size); equal keys keep row order
    with a row's Trade item before its Quote item; ts ns-precise for ns-unit columns.
    sequence falsiness chain: null OR ZERO 'sequence' falls through to 'seq', then 0.
    side-signed: +price_ticks iff upper(side) == 'B' else -price_ticks (None -> sell).
    Day-mode two-file composition = concatenation (disjoint [start,split)/[split,end)).
    Warnings yield in row order BEFORE their batch's events.
 4. Timestamps: timestamp[ns,tz] -> ns-precision pd.Timestamp (pyarrow as_py + pandas
    present), NO truncation; timestamp[us/ms/s,tz] -> exact datetime; tz-naive column
    -> every row INVALID_TIMESTAMP; integer column -> epoch + value//1000 us.
 5. Prices: Decimal(str(value))/0.25 exact-grid rule == 'value/0.25 integral in
    float64' for finite doubles (division by 0.25 exact); off-grid/null/NaN ->
    INVALID_PRICE warn-and-skip row.
 6. Sizes: trade size strictly int (bool never) and > 0 else INVALID_RECORD (carries
    event ts); quote depths: first non-null alias, _optional_int-or-0 (floats truncate
    toward zero, non-finite/bool -> 0).
 7. Day window: [prev-day 18:00 ET, day 18:00 ET) DST-aware, files split at UTC
    midnight; event kept iff start <= ts < end at full event precision (floor-us
    compare == ns compare for whole-us bounds); invalid rows warn regardless of window.
 8. Symbol filter (front_month_only): spread symbols (raw_symbol-or-symbol contains
    '-', empty raw_symbol falls through) always dropped; dominant instrument by
    TRADE-row count over scanned row groups, ties -> larger id; null instrument_id
    dropped when an id was resolved. Dropped rows never warn.
 9. Warnings: identical code/message/severity/source(file-name-only)/event_ts/metadata,
    identical stream positions (clean-file day-mode: composition warnings first,
    row warnings inline per batch).
KNOWN INTENTIONAL EDGE DIVERGENCES (unreachable on real store data, documented in
DECISIONS.md D-P-15): inf-price / out-of-datetime-range-timestamp / uint64-overflow
cells now warn-and-skip the ROW where the row-wise path aborted the FILE (or, for
|price/0.25| > 2^62, emitted a wrapped value); none occur on the proof days, asserted
by the zero-warning tallies below.
"""


def fields(event):
    if isinstance(event, DataQualityWarning):
        return ("warning", event.to_dict())
    if isinstance(event, Trade):
        return ("trade", event.event_ts_utc, event.price_ticks, event.size, event.side)
    return (
        "quote",
        event.event_ts_utc,
        event.bid_price_ticks,
        event.ask_price_ticks,
        event.bid_size,
        event.ask_size,
    )


def compare_day(out, src) -> dict:
    sentinel = object()
    counts = {"trade": 0, "quote": 0, "warning": 0}
    index = 0
    for index, (old, new) in enumerate(
        zip_longest(src._events_rowwise(), src.events(), fillvalue=sentinel)
    ):
        if old is sentinel or new is sentinel:
            out(f"  DIVERGENCE at event {index}: stream length mismatch")
            out(f"    old: {'<exhausted>' if old is sentinel else repr(old)}")
            out(f"    new: {'<exhausted>' if new is sentinel else repr(new)}")
            return {"identical": False, "index": index}
        if type(old) is not type(new):
            out(f"  DIVERGENCE at event {index}: type {type(old).__name__} != {type(new).__name__}")
            out(f"    old: {old!r}\n    new: {new!r}")
            return {"identical": False, "index": index}
        old_fields, new_fields = fields(old), fields(new)
        if old_fields != new_fields:
            out(f"  DIVERGENCE at event {index} ({old_fields[0]}):")
            out(f"    old: {old!r}\n    new: {new!r}")
            return {"identical": False, "index": index}
        if isinstance(old, Trade | Quote):
            old_ts, new_ts = old.event_ts_utc, new.event_ts_utc
            if isinstance(old_ts, pd.Timestamp) != isinstance(new_ts, pd.Timestamp) or (
                isinstance(old_ts, pd.Timestamp) and old_ts.value != new_ts.value
            ):
                out(f"  DIVERGENCE at event {index}: ts ns mismatch {old_ts!r} != {new_ts!r}")
                return {"identical": False, "index": index}
        counts[old_fields[0]] += 1
    total = index + 1 if counts["trade"] + counts["quote"] + counts["warning"] else 0
    return {"identical": True, "events": total, **counts}


def timed_drain(events_iter) -> tuple[float, int]:
    start = time.perf_counter()
    count = sum(1 for _ in events_iter)
    return time.perf_counter() - start, count


def main() -> int:
    lines: list[str] = []

    def out(text: str = "") -> None:
        print(text, flush=True)
        lines.append(text)

    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
        cwd=Path(__file__).resolve().parent,
    ).stdout.strip()
    out("W3A-READER P3a IDENTITY PROOF — row-wise vs vectorized DatabentoParquetSource")
    out(f"run: {datetime.now().isoformat(timespec='seconds')}  SC HEAD: {head}")
    out(
        f"env: python {sys.version.split()[0]}  pyarrow {pa.__version__}  "
        f"numpy {np.__version__}  pandas {pd.__version__}"
    )
    out(f"store: {STORE}")
    out("")
    out(CONTRACT)

    failed = False
    new_rates = []
    for day in DAYS:
        out(f"== {day.isoformat()} " + "=" * 50)
        src = DatabentoParquetSource.for_trading_day(STORE, day)
        out(f"  files: {[p.name + ' @ ' + p.parent.name for p in src.paths]}")
        out(f"  composition warnings: {[w.code.value for w in src.pending_warnings]}")
        t0 = time.perf_counter()
        result = compare_day(out, src)
        out(f"  compare pass: {time.perf_counter() - t0:.1f}s (cold cache; warms both drains)")
        if not result["identical"]:
            out("  RESULT: NOT IDENTICAL — see divergence above. STOP (fallback per task).")
            failed = True
            break
        out(
            f"  RESULT: IDENTICAL — {result['events']:,} events "
            f"(trades {result['trade']:,} / quotes {result['quote']:,} / "
            f"warnings {result['warning']:,}), order + every field + ns-exact ts equal"
        )
        new_s, new_n = timed_drain(src.events())
        old_s, old_n = timed_drain(src._events_rowwise())
        assert new_n == old_n == result["events"]
        out(
            f"  timed drains (both warm): NEW {new_s:.1f}s  OLD {old_s:.1f}s  "
            f"speedup x{old_s / new_s:.1f}  "
            f"({new_s / new_n * 1e6:.2f} vs {old_s / old_n * 1e6:.2f} us/event)"
        )
        new_rates.append(new_s / new_n)
        out("")

    if failed:
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    out("== BUILD PROJECTION " + "=" * 47)
    rate = max(new_rates)  # conservative: slower of the two proof days
    new_drain_proj = rate * GATE_DRAIN_EVENTS
    per_day = GATE_PIPELINE_S - READER_PASSES * (GATE_DRAIN_S - new_drain_proj)
    out(
        f"  anchors (W3a P2 gate, 2026-02-12): pipeline {GATE_PIPELINE_S:.1f}s/day, "
        f"old drain {GATE_DRAIN_S:.1f}s / {GATE_DRAIN_EVENTS:,} events, "
        f"{READER_PASSES} reader passes/day"
    )
    out(
        f"  new drain projected on that day: {rate * 1e6:.2f} us/event x "
        f"{GATE_DRAIN_EVENTS:,} = {new_drain_proj:.1f}s"
    )
    out(
        f"  projected per-day pipeline: {GATE_PIPELINE_S:.1f} - {READER_PASSES} x "
        f"({GATE_DRAIN_S:.1f} - {new_drain_proj:.1f}) = {per_day:.1f}s"
    )
    out(
        f"  x{BUILD_DAYS} build projection: {per_day * BUILD_DAYS:.0f}s "
        f"= {per_day * BUILD_DAYS / 3600:.2f}h "
        f"(was {GATE_PIPELINE_S * BUILD_DAYS / 3600:.1f}h at the stop-gate)"
    )
    out(
        "  assumption: non-reader pipeline cost (~"
        f"{GATE_PIPELINE_S - READER_PASSES * GATE_DRAIN_S:.0f}s/day: runtime drive, "
        "labeling, features) unchanged; per-day ml_utility caches make reruns instant."
    )
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out(f"\nlog written: {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
