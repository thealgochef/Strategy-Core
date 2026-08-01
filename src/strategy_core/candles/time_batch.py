"""Vectorized (pandas + numpy) TIME-bar builder over a trades DataFrame (Phase F).

The batch twin of :class:`~strategy_core.candles.time_streaming.TimeBarEngine`,
mirroring ``build_tick_bars_from_frame``'s signature shape and input contract
(``ts_event`` UTC, ``price`` points, ``size``). Same architect-ratified rules:

* ``bucket = floor((ts_utc - day_start_utc) / interval)`` anchored at the trading-day
  boundary INSTANT (:func:`~strategy_core.candles._buckets.trading_day_start_utc`) —
  DST-correct by construction; here computed in integer nanoseconds.
* DERIVE ONCE, AGGREGATE UPWARD: one 60s aggregation over trades; every requested
  timeframe (60s included) is a groupby over those 60s rows via
  ``hbucket = bucket60 * 60 // interval`` — never a second pass over trades.
  Higher OHLC = first open / max high / min low / last close over constituent 60s
  rows; volume / trade_count are sums over the 60s rows that EXIST (skipped empty
  minutes contribute nothing).
* NO EMPTY BARS; ``bar_index`` dense over emitted bars per (timeframe, trading_day).
* COMPLETENESS: the last bar of each (timeframe, trading_day) is ``END_OF_DAY``
  incomplete (no later bucket produced a bar); every other bar is ``COMPLETE``.

The parity test (``tests/test_time_bar_parity.py``) locks this against the
streaming engine. Pandas-import rule: the BATCH builders (``candles/batch.py`` and
this module) import pandas; the streaming engines and ``candles/_buckets.py`` do
not. The batch path is the research / warm-up fast path, run off the event loop.

UNIT NOTE — batch buckets in integer NANOSECONDS while the streaming engine buckets
in integer MICROSECONDS, and the two are provably equivalent: for positive integers
``floor(x / (a*b)) == floor(floor(x / a) / b)``, so flooring a nanosecond timestamp
to microseconds (a=1000) and then to buckets (b=interval*1e6 us) lands in the same
bucket as flooring the nanoseconds directly by interval*1e9 — PROVIDED the ns->us
step is a TRUNCATION (floor), not a rounding.
That truncation is ENGINE-side, not reader-side. The reader PRESERVES full
nanosecond precision: ``event_ts_utc`` is a ns-unit ``pd.Timestamp``
(``data/databento_parquet.py:618``, ``:624-625``; the ``raw // 1000`` at ``:621``
feeds only the window masks, never the event objects), and real store timestamps
DO carry sub-microsecond components. The truncation happens in
``candles/time_streaming.py``, whose bucket arithmetic decomposes
``event_ts_utc - day_start`` via ``Timedelta.days/seconds/microseconds`` and
DISCARDS ``.nanoseconds``. Floor-composition therefore applies end to end and
batch-in-ns == stream-in-us holds on real ns-precision store data — VERIFIED at
TIMEBAR-FIX Part 8b (probes: +60s+999ns -> bucket 1 on both paths;
+59.999999999s -> bucket 0 on both paths).

BUCKET ASSIGNMENT ONLY. The emitted ``open_ts_utc`` / ``close_ts_utc`` are NOT
proven equal across the two paths on real data: the streaming engine assigns the
ns-precision ``pd.Timestamp`` straight onto the bar, while this module emits
stdlib ``datetime`` at us precision via ``.dt.to_pydatetime()``. On a trade
carrying nonzero sub-microsecond nanoseconds those values differ. The parity
harness cannot see it — its synthetic streams are built from stdlib ``datetime``
(zero ns). The tick path has the same structure and the same exposure
(``candles/streaming.py`` vs ``candles/batch.py``), so this is pre-existing, not
introduced here. OPEN — TIMEBAR-FIX architect review finding.
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from strategy_core.candles._buckets import logical_bucket_bounds, trading_day_start_utc
from strategy_core.candles.exchange_calendar import ExchangeMinuteSchedule, MinuteSlotStatus
from strategy_core.candles._ids import make_bar_id
from strategy_core.candles.time_streaming import BASE_INTERVAL_SECONDS
from strategy_core.constants import DEFAULT_TICK_SIZE, RESEARCH_SESSION_SCHEME
from strategy_core.types import Bar, BarKind, CloseReason, SessionScheme

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["build_time_bars_from_frame"]

_NS_PER_SECOND = 1_000_000_000


def _seconds_of(t: time) -> int:
    """Seconds-of-day for a local wall-clock ``time`` (same as ``batch.py``)."""
    return t.hour * 3600 + t.minute * 60 + t.second


def _index_to_ns(values):
    """Int64 epoch NANOSECONDS for a datetime Series/Index — the ONE place the batch
    path turns the timestamp column into integers. Lives here (not ``_buckets.py``)
    because ``_buckets`` must stay pandas-free for the streaming engine.

    Unit-explicit: ``.asi8`` returns integers in the dtype's OWN unit, and pandas 3
    no longer renormalizes source units to ns (the SC ci 30331205481 red), so the
    index is forced to nanosecond resolution first and the forced unit is verified
    loudly — a future pandas change fails with a named unit, never a silent rescale.
    """
    import pandas as pd

    index = pd.DatetimeIndex(values).as_unit("ns")
    if index.unit != "ns":
        raise ValueError(
            f"ns extraction expected datetime64[ns] after as_unit('ns'); observed "
            f"unit {index.unit!r} (dtype {index.dtype})"
        )
    return index.asi8


def _timestamp_to_ns(ts) -> int:
    """Epoch NANOSECONDS for a single timestamp — the ONE place the per-day anchor
    becomes an integer. Unit-explicit for the same reason as ``_index_to_ns``:
    ``.value`` is the underlying integer in the Timestamp's OWN unit."""
    import pandas as pd

    stamp = pd.Timestamp(ts).as_unit("ns")
    if stamp.unit != "ns":
        raise ValueError(
            f"ns extraction expected a ns-unit Timestamp after as_unit('ns'); "
            f"observed unit {stamp.unit!r}"
        )
    return int(stamp.value)


def build_time_bars_from_frame(
    frame: "pd.DataFrame",
    timeframes_seconds: tuple[int, ...],
    *,
    scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
    schedule: ExchangeMinuteSchedule | None = None,
    tick_size: float = DEFAULT_TICK_SIZE,
) -> list[Bar]:
    """Vectorized equivalent of feeding ``frame``'s trades through ``TimeBarEngine``.

    ``frame`` must have ``ts_event`` (UTC), ``price`` (tick-aligned points) and
    ``size`` — the exact ``build_tick_bars_from_frame`` input contract, with the
    same coercion, tick rounding, trading-day derivation, closed-window drop and
    stable sort. Returns bars over timeframes in ascending order; for a fixed
    timeframe in ``(trading_day, bar_index)`` order — identical to the streaming
    engine's emission for the same trades.
    """
    import warnings

    import numpy as np
    import pandas as pd

    if not timeframes_seconds:
        raise ValueError("time timeframes must be non-empty")
    for seconds in timeframes_seconds:
        if seconds < BASE_INTERVAL_SECONDS or seconds % BASE_INTERVAL_SECONDS:
            raise ValueError(
                "time timeframes must be positive multiples of "
                f"{BASE_INTERVAL_SECONDS}s (got {seconds})"
            )

    if frame is None or len(frame) == 0:
        return []

    # ── identical trade normalization to batch.py (coerce ts, points -> ticks) ──
    ts = frame["ts_event"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        ts = pd.to_datetime(ts, utc=True, unit="ns")
    elif ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")

    price_ticks = np.rint(frame["price"].to_numpy(dtype="float64") / tick_size).astype("int64")
    work = pd.DataFrame(
        {
            "ts_event": ts.to_numpy(),
            "price_ticks": price_ticks,
            "size": frame["size"].to_numpy(dtype="int64"),
        }
    )
    work["ts_event"] = pd.to_datetime(work["ts_event"], utc=True)

    if schedule is not None:
        minute_closes = work["ts_event"].dt.floor("min") + pd.Timedelta(minutes=1)
        unique_closes = minute_closes.drop_duplicates().tolist()
        eligibility = {
            close: schedule.slot(close.to_pydatetime()).status is MinuteSlotStatus.ELIGIBLE
            for close in unique_closes
        }
        work = work[minute_closes.map(eligibility)].copy()
        if work.empty:
            return []

    local = work["ts_event"].dt.tz_convert(scheme.timezone)
    sod = local.dt.hour * 3600 + local.dt.minute * 60 + local.dt.second
    cal_date = local.dt.tz_localize(None).dt.floor("D")
    boundary_sod = _seconds_of(scheme.trading_day_boundary)
    roll = (sod >= boundary_sod).astype("int64")
    work["trading_day"] = cal_date + pd.to_timedelta(roll, unit="D")

    if scheme.closed_window is not None:
        closed_start_sod = _seconds_of(scheme.closed_window[0])
        closed_end_sod = _seconds_of(scheme.closed_window[1])
        closed = (sod >= closed_start_sod) & (sod < closed_end_sod)
        work = work[~closed]
    work = work.sort_values("ts_event", kind="stable").reset_index(drop=True)
    if work.empty:
        return []

    # ── 60s bucketing anchored at each trading day's boundary instant ──────────
    # Integer-nanosecond floor-divide so an edge-exact trade buckets identically to
    # the streaming engine's integer-microsecond arithmetic.
    day_start_ns = {
        td: _timestamp_to_ns(trading_day_start_utc(td.date(), scheme))
        for td in work["trading_day"].unique()
    }
    ts_ns = _index_to_ns(work["ts_event"])
    start_ns = work["trading_day"].map(day_start_ns).to_numpy(dtype="int64")
    work["bucket60"] = (ts_ns - start_ns) // (BASE_INTERVAL_SECONDS * _NS_PER_SECOND)

    # ── the ONE aggregation over trades: the 60s series ────────────────────────
    minute = (
        work.groupby(["trading_day", "bucket60"], sort=True)
        .agg(
            open_ts=("ts_event", "first"),
            close_ts=("ts_event", "last"),
            open_ticks=("price_ticks", "first"),
            close_ticks=("price_ticks", "last"),
            high_ticks=("price_ticks", "max"),
            low_ticks=("price_ticks", "min"),
            volume=("size", "sum"),
            trade_count=("price_ticks", "size"),
        )
        .reset_index()
    )

    # ── every timeframe aggregates the 60s rows (60s itself: hbucket == bucket60) ─
    bars: list[Bar] = []
    for interval in sorted(set(timeframes_seconds)):
        minute["hbucket"] = minute["bucket60"] * BASE_INTERVAL_SECONDS // interval
        agg = (
            minute.groupby(["trading_day", "hbucket"], sort=True)
            .agg(
                open_ts=("open_ts", "first"),
                close_ts=("close_ts", "last"),
                open_ticks=("open_ticks", "first"),
                close_ticks=("close_ticks", "last"),
                high_ticks=("high_ticks", "max"),
                low_ticks=("low_ticks", "min"),
                volume=("volume", "sum"),
                trade_count=("trade_count", "sum"),
            )
            .reset_index()
        )
        day_group = agg.groupby("trading_day", sort=True)
        agg["bar_index"] = day_group.cumcount()
        # END_OF_DAY iff no later bucket in the same day produced a bar == the
        # day's last emitted row (matches the streaming day-roll / finalize).
        is_last = day_group.cumcount(ascending=False).to_numpy() == 0

        td_dates = agg["trading_day"].dt.date.to_numpy()
        hbucket_arr = agg["hbucket"].to_numpy().tolist()
        bar_index_arr = agg["bar_index"].to_numpy().tolist()
        open_ticks_arr = agg["open_ticks"].to_numpy().tolist()
        high_ticks_arr = agg["high_ticks"].to_numpy().tolist()
        low_ticks_arr = agg["low_ticks"].to_numpy().tolist()
        close_ticks_arr = agg["close_ticks"].to_numpy().tolist()
        volume_arr = agg["volume"].to_numpy().tolist()
        trade_count_arr = agg["trade_count"].to_numpy().tolist()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # nanosecond discard, as in batch.py
            open_dt = agg["open_ts"].dt.to_pydatetime()
            close_dt = agg["close_ts"].dt.to_pydatetime()
        bars.extend(
            Bar(
                timeframe_ticks=interval,
                trading_day=td,
                bar_index=bi,
                bar_id=make_bar_id(interval, td, bi, BarKind.TIME),
                open_ts_utc=ots,
                close_ts_utc=cts,
                open_ticks=ot,
                high_ticks=ht,
                low_ticks=lt,
                close_ticks=ct,
                volume=vol,
                trade_count=tc,
                is_complete=not last,
                is_partial=bool(last),
                close_reason=CloseReason.END_OF_DAY if last else CloseReason.COMPLETE,
                kind=BarKind.TIME,
                logical_open_ts_utc=logical_bucket_bounds(td, hb, interval, scheme)[0],
                logical_close_ts_utc=logical_bucket_bounds(td, hb, interval, scheme)[1],
            )
            for td, hb, bi, ots, cts, ot, ht, lt, ct, vol, tc, last in zip(
                td_dates,
                hbucket_arr,
                bar_index_arr,
                open_dt,
                close_dt,
                open_ticks_arr,
                high_ticks_arr,
                low_ticks_arr,
                close_ticks_arr,
                volume_arr,
                trade_count_arr,
                is_last,
                strict=True,
            )
        )
    return bars
