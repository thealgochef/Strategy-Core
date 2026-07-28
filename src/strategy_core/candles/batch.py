"""Vectorized (pandas + numpy) tick-bar builder over a trades DataFrame.

Promoted from Trade-Lab's ``build_tick_bars_from_frame``
(``Trade-Lab/backend/src/trade_lab/services/seed.py:42-131``) and generalized so the
trading-day calendar / closed window come from a
:class:`~strategy_core.types.SessionScheme` instead of the hardcoded Chicago
16:00/18:00 boundaries. It is the vectorized equivalent of feeding the same trades
through :class:`strategy_core.candles.streaming.CandleEngine`; the parity test
(``tests/test_candle_parity.py``) locks the two paths together.

Pandas-import rule (see package rules): the BATCH builders — this module and
``candles/time_batch.py`` — import pandas; the streaming engines
(``candles/streaming.py``, ``candles/time_streaming.py``) and ``candles/_buckets.py``
do not. The batch path is the research/warm-up fast path, run off the event loop. Emits
:class:`strategy_core.types.Bar` (not Trade-Lab's ``Candle``) with
:class:`strategy_core.types.CloseReason`.
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from strategy_core.constants import DEFAULT_TICK_SIZE, RESEARCH_SESSION_SCHEME
from strategy_core.candles._ids import make_bar_id
from strategy_core.types import Bar, CloseReason, SessionScheme

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["build_tick_bars_from_frame"]


def _seconds_of(t: time) -> int:
    """Seconds-of-day for a local wall-clock ``time`` (mirrors the streaming
    classifier's minute-aligned boundaries; matches ``seed.py:78`` sod math)."""
    return t.hour * 3600 + t.minute * 60 + t.second


def build_tick_bars_from_frame(
    frame: "pd.DataFrame",
    timeframes: tuple[int, ...],
    *,
    scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
    tick_size: float = DEFAULT_TICK_SIZE,
) -> list[Bar]:
    """Vectorized equivalent of feeding ``frame``'s trades through ``CandleEngine``.

    ``frame`` must have ``ts_event`` (UTC), ``price`` (tick-aligned points) and
    ``size``. Generalized port of ``build_tick_bars_from_frame``
    (``seed.py:42-131``); the only change is parameterization by ``scheme``:

    * Localize ``ts_event`` to ``scheme.timezone`` and compute the local
      seconds-of-day ``sod = hour*3600 + minute*60 + second`` (``seed.py:77-78``).
    * ``trading_day = calendar_date + (sod >= boundary_sod ? 1 day : 0)`` where
      ``boundary_sod`` is ``scheme.trading_day_boundary`` in seconds-of-day
      (``seed.py:79-81``; Chicago hardcoded 18:00 generalized).
    * If ``scheme.closed_window`` is set, drop rows with
      ``closed_start_sod <= sod < closed_end_sod`` (``seed.py:82-84``; for
      ``RESEARCH_SESSION_SCHEME`` it is ``None`` so nothing is dropped).
    * Sort by ``ts_event`` (stable), group by ``trading_day``,
      ``bar_index = cumcount() // timeframe`` (``seed.py:91``), aggregate
      open/close/high/low/volume/trade_count, ``is_complete = trade_count ==
      timeframe`` and ``close_reason`` ``COMPLETE`` / ``END_OF_DAY`` accordingly.

    Returns bars over timeframes in ascending order; for a fixed timeframe the
    bars are in ``(trading_day, bar_index)`` order, identical to the streaming
    builder's emission for the same trades.
    """
    import warnings

    import numpy as np
    import pandas as pd

    # seed.py:56-57 -- empty / None frame yields no bars.
    if frame is None or len(frame) == 0:
        return []

    # seed.py:59-65 -- coerce ts_event to a tz-aware UTC datetime series.
    ts = frame["ts_event"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        ts = pd.to_datetime(ts, utc=True, unit="ns")
    elif ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")

    # seed.py:67 -- price (points) -> integer ticks via round-half-to-even rint,
    # exactly matching the streaming Trade's already-integer price_ticks.
    price_ticks = np.rint(frame["price"].to_numpy(dtype="float64") / tick_size).astype("int64")
    work = pd.DataFrame(
        {
            "ts_event": ts.to_numpy(),
            "price_ticks": price_ticks,
            "size": frame["size"].to_numpy(dtype="int64"),
        }
    )
    work["ts_event"] = pd.to_datetime(work["ts_event"], utc=True)

    # seed.py:77-81 -- localize to the scheme timezone, derive seconds-of-day and
    # the trading day (roll into the next calendar day at/after the boundary).
    local = work["ts_event"].dt.tz_convert(scheme.timezone)
    sod = local.dt.hour * 3600 + local.dt.minute * 60 + local.dt.second
    cal_date = local.dt.tz_localize(None).dt.floor("D")
    boundary_sod = _seconds_of(scheme.trading_day_boundary)
    roll = (sod >= boundary_sod).astype("int64")
    work["trading_day"] = cal_date + pd.to_timedelta(roll, unit="D")

    # seed.py:82-84 -- drop the scheme's closed window (half-open [start, end));
    # None (research scheme) drops nothing.
    if scheme.closed_window is not None:
        closed_start_sod = _seconds_of(scheme.closed_window[0])
        closed_end_sod = _seconds_of(scheme.closed_window[1])
        closed = (sod >= closed_start_sod) & (sod < closed_end_sod)
        work = work[~closed]
    work = work.sort_values("ts_event", kind="stable").reset_index(drop=True)
    if work.empty:
        return []

    # seed.py:88 -- cumcount is taken per trading day so bar_index restarts daily.
    day_groups = work.groupby("trading_day", sort=True)
    bars: list[Bar] = []
    for timeframe in sorted(set(timeframes)):
        # seed.py:91 -- floor-divide the per-day running count to bucket trades
        # into fixed N-trade bars.
        work["bar_index"] = (day_groups.cumcount() // timeframe).to_numpy()
        agg = (
            work.groupby(["trading_day", "bar_index"], sort=True)
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
        # Vectorized emit (seed.py:106-130 did one Bar per row via .itertuples()).
        # On ~60k bars/day the per-row namedtuple plus per-row
        # ``Timestamp.to_pydatetime`` dominated the build. Here every agg column is
        # converted to Python scalars/datetimes ONCE, then Bars are built in a single
        # comprehension. The output is byte-identical to the per-row build: ``.tolist()``
        # yields the same Python ``int`` the old ``int(...)`` produced, ``.dt.date``
        # the same ``date``, and ``.dt.to_pydatetime`` truncates nanoseconds exactly as
        # the old ``row.<ts>.to_pydatetime(warn=False)`` did (the discard is intended).
        td_dates = agg["trading_day"].dt.date.to_numpy()
        bar_index_arr = agg["bar_index"].to_numpy().tolist()
        open_ticks_arr = agg["open_ticks"].to_numpy().tolist()
        high_ticks_arr = agg["high_ticks"].to_numpy().tolist()
        low_ticks_arr = agg["low_ticks"].to_numpy().tolist()
        close_ticks_arr = agg["close_ticks"].to_numpy().tolist()
        volume_arr = agg["volume"].to_numpy().tolist()
        trade_count_arr = agg["trade_count"].to_numpy().tolist()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # nanosecond discard == old warn=False
            open_dt = agg["open_ts"].dt.to_pydatetime()
            close_dt = agg["close_ts"].dt.to_pydatetime()
        bars.extend(
            Bar(
                timeframe_ticks=timeframe,
                trading_day=td,
                bar_index=bi,
                bar_id=make_bar_id(timeframe, td, bi),
                open_ts_utc=ots,
                close_ts_utc=cts,
                open_ticks=ot,
                high_ticks=ht,
                low_ticks=lt,
                close_ticks=ct,
                volume=vol,
                trade_count=tc,
                # seed.py:109 -- complete iff it filled exactly N trades; the day's
                # trailing partial is END_OF_DAY, matching finalize_trading_day.
                is_complete=tc == timeframe,
                is_partial=tc != timeframe,
                close_reason=CloseReason.COMPLETE if tc == timeframe else CloseReason.END_OF_DAY,
            )
            for td, bi, ots, cts, ot, ht, lt, ct, vol, tc in zip(
                td_dates,
                bar_index_arr,
                open_dt,
                close_dt,
                open_ticks_arr,
                high_ticks_arr,
                low_ticks_arr,
                close_ticks_arr,
                volume_arr,
                trade_count_arr,
                strict=True,
            )
        )
    return bars
