from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from strategy_core.candles.exchange_calendar import (
    CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
    ContextSourceCoverage,
    MinuteSlotStatus,
    SourceCoverageStatus,
    SourcePartitionCoverage,
)
from strategy_core.candles.time_batch import build_time_bars_from_frame
from strategy_core.candles.time_streaming import TimeBarEngine
from strategy_core.constants import RESEARCH_SESSION_SCHEME
from strategy_core.strategies.ifvg_smc.context_config import (
    ContextFeatureConfig,
    build_context_identity,
)
from strategy_core.structures.context import MissingReason
from strategy_core.structures.displacement import DisplacementAccumulator
from strategy_core.types import Bar, BarKind, CloseReason, Trade

SCHEDULE = CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE
IDENTITY = build_context_identity(ContextFeatureConfig(), symbol="NQ")


def _bar(close: datetime, index: int, price: int = 100) -> Bar:
    return Bar(
        timeframe_ticks=60,
        trading_day=close.astimezone(UTC).date(),
        bar_index=index,
        bar_id=f"60s:{close.isoformat()}:{index}",
        open_ts_utc=close.replace(second=10),
        close_ts_utc=close.replace(second=50),
        open_ticks=price,
        high_ticks=price + 2,
        low_ticks=price - 1,
        close_ticks=price + 1,
        volume=1,
        trade_count=1,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
        kind=BarKind.TIME,
        logical_open_ts_utc=close.replace(second=0) - pd.Timedelta(minutes=1),
        logical_close_ts_utc=close.replace(second=0),
    )


def _acc(
    b0: Bar,
    *,
    coverage: ContextSourceCoverage | None = None,
) -> DisplacementAccumulator:
    kwargs = {} if coverage is None else {"source_coverage": coverage}
    return DisplacementAccumulator(
        identity=IDENTITY,
        scheme=RESEARCH_SESSION_SCHEME,
        schedule=SCHEDULE,
        setup_id="setup",
        window_kind="counter_leg",
        start_evidence_id="start",
        b0=b0,
        expected_sign=-1,
        setup_sign=1,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("close", "status"),
    (
        (datetime(2026, 1, 6, 22, 1, tzinfo=UTC), MinuteSlotStatus.SCHEDULED_MAINTENANCE),
        (datetime(2026, 1, 9, 22, 1, tzinfo=UTC), MinuteSlotStatus.WEEKEND_CLOSURE),
        (datetime(2026, 1, 11, 23, 1, tzinfo=UTC), MinuteSlotStatus.ELIGIBLE),
        (datetime(2026, 1, 19, 18, 1, tzinfo=UTC), MinuteSlotStatus.HOLIDAY_CLOSURE),
        (datetime(2026, 4, 3, 16, 0, tzinfo=UTC), MinuteSlotStatus.HOLIDAY_CLOSURE),
        (datetime(2026, 3, 8, 22, 1, tzinfo=UTC), MinuteSlotStatus.ELIGIBLE),
        (datetime(2026, 11, 1, 23, 1, tzinfo=UTC), MinuteSlotStatus.ELIGIBLE),
    ),
)
def test_committed_schedule_classifies_maintenance_weekend_holiday_and_dst(
    close: datetime,
    status: MinuteSlotStatus,
) -> None:
    assert SCHEDULE.slot(close).status is status
    assert len(SCHEDULE.content_hash) == 64


@pytest.mark.parametrize(
    ("b0_close", "endpoint_close"),
    (
        (
            datetime(2026, 1, 6, 22, 0, tzinfo=UTC),
            datetime(2026, 1, 6, 23, 1, tzinfo=UTC),
        ),
        (
            datetime(2026, 1, 9, 22, 0, tzinfo=UTC),
            datetime(2026, 1, 11, 23, 1, tzinfo=UTC),
        ),
        (
            datetime(2026, 1, 19, 18, 0, tzinfo=UTC),
            datetime(2026, 1, 19, 23, 1, tzinfo=UTC),
        ),
    ),
)
def test_scheduled_closures_do_not_create_displacement_source_gaps(
    b0_close: datetime,
    endpoint_close: datetime,
) -> None:
    accumulator = _acc(_bar(b0_close, 0))
    endpoint = _bar(endpoint_close, 1)
    accumulator.on_bar(endpoint)
    summary = accumulator.finalize(end_evidence_id="end", end_bar=endpoint)
    assert summary.valid
    assert summary.metrics["expected_eligible_bar_count"] == 1
    assert summary.metrics["missing_bar_count"] == 0


@pytest.mark.parametrize(
    ("start", "end", "partition_timezone"),
    (
        (
            datetime(2026, 1, 9, 16, 37, tzinfo=UTC),
            datetime(2026, 1, 12, 3, 19, tzinfo=UTC),
            "UTC",
        ),
        (
            datetime(2026, 3, 7, 20, 0, tzinfo=UTC),
            datetime(2026, 3, 9, 5, 0, tzinfo=UTC),
            "America/New_York",
        ),
        (
            datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
            datetime(2026, 11, 2, 5, 0, tzinfo=UTC),
            "America/New_York",
        ),
    ),
)
def test_cached_partition_counts_match_exact_minute_iteration(
    start: datetime,
    end: datetime,
    partition_timezone: str,
) -> None:
    counts = SCHEDULE.eligible_counts_by_partition(
        start,
        end,
        partition_timezone=partition_timezone,
    )
    assert sum(count for _day, count in counts) == SCHEDULE.eligible_close_count(
        start,
        end,
    )
    assert counts == SCHEDULE.eligible_counts_by_partition(
        start,
        end,
        partition_timezone=partition_timezone,
    )


def test_unavailable_permitted_partition_has_distinct_missing_reason() -> None:
    coverage = ContextSourceCoverage(
        partitions=(
            SourcePartitionCoverage(date(2026, 1, 6), SourceCoverageStatus.AVAILABLE),
            SourcePartitionCoverage(date(2026, 1, 7), SourceCoverageStatus.UNAVAILABLE),
            SourcePartitionCoverage(date(2026, 1, 8), SourceCoverageStatus.AVAILABLE),
        ),
        cutoff_ts_utc=datetime(2026, 1, 8, 1, 0, tzinfo=UTC),
    )
    accumulator = _acc(_bar(datetime(2026, 1, 6, 23, 59, tzinfo=UTC), 0), coverage=coverage)
    last_close_in_first_partition = _bar(datetime(2026, 1, 7, 0, 0, tzinfo=UTC), 1)
    endpoint = _bar(datetime(2026, 1, 8, 0, 1, tzinfo=UTC), 2)
    accumulator.on_bar(last_close_in_first_partition)
    accumulator.on_bar(endpoint)
    summary = accumulator.finalize(end_evidence_id="end", end_bar=endpoint)
    assert not summary.valid
    assert summary.missing_reason is MissingReason.SOURCE_PARTITION_UNAVAILABLE
    assert summary.unavailable_partition_dates == ("2026-01-07",)
    assert summary.metrics["missing_bar_count"] == 0


def test_observed_bar_during_scheduled_closure_is_an_invariant_failure() -> None:
    accumulator = _acc(_bar(datetime(2026, 1, 6, 22, 0, tzinfo=UTC), 0))
    with pytest.raises(ValueError, match="scheduled_maintenance"):
        accumulator.on_bar(_bar(datetime(2026, 1, 6, 22, 1, tzinfo=UTC), 1))


def test_time_builders_share_schedule_filter() -> None:
    trades = (
        Trade(
            event_ts_utc=datetime(2026, 1, 6, 22, 30, 10, tzinfo=UTC),
            price_ticks=999,
            size=1,
        ),
        Trade(
            event_ts_utc=datetime(2026, 1, 6, 23, 0, 10, tzinfo=UTC),
            price_ticks=100,
            size=1,
        ),
        Trade(
            event_ts_utc=datetime(2026, 1, 6, 23, 1, 10, tzinfo=UTC),
            price_ticks=101,
            size=1,
        ),
    )
    engine = TimeBarEngine((60,), schedule=SCHEDULE)
    streamed = []
    for trade in trades:
        streamed.extend(engine.process_trade(trade).completed)
    streamed.extend(engine.finalize_trading_day())

    frame = pd.DataFrame(
        {
            "ts_event": [trade.event_ts_utc for trade in trades],
            "price": [trade.price_ticks * 0.25 for trade in trades],
            "size": [trade.size for trade in trades],
        }
    )
    batch = build_time_bars_from_frame(frame, (60,), schedule=SCHEDULE)
    assert [bar.open_ticks for bar in streamed] == [100, 101]
    assert [bar.open_ticks for bar in batch] == [100, 101]
    assert all(bar.open_ticks != 999 for bar in (*streamed, *batch))
