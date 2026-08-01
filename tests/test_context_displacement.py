from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest

from strategy_core.candles._buckets import (
    eligible_minute_close_count,
    eligible_minute_closes,
    is_eligible_minute_close,
)
from strategy_core.constants import IFVG_DOC_SESSION_SCHEME, RESEARCH_SESSION_SCHEME
from strategy_core.strategies.ifvg_smc.context_config import (
    ContextFeatureConfig,
    build_context_identity,
)
from strategy_core.structures.context import MissingReason, canonical_json
from strategy_core.structures.displacement import (
    DisplacementAccumulator,
    candle_primitives,
    overlap_fraction,
)
from strategy_core.types import Bar, BarKind, CloseReason

DAY = date(2026, 1, 6)
BASE = datetime(2026, 1, 6, 14, 0, tzinfo=UTC)
IDENTITY = build_context_identity(ContextFeatureConfig(), symbol="NQ")


def _bar(i: int, o: int, h: int, low: int, close_ticks: int) -> Bar:
    close = BASE + timedelta(minutes=i)
    return Bar(
        timeframe_ticks=60,
        trading_day=DAY,
        bar_index=i,
        bar_id=f"60s:{DAY}:{i}",
        open_ts_utc=close - timedelta(seconds=50),
        close_ts_utc=close - timedelta(seconds=1),
        open_ticks=o,
        high_ticks=h,
        low_ticks=low,
        close_ticks=close_ticks,
        volume=1,
        trade_count=1,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
        kind=BarKind.TIME,
        logical_open_ts_utc=close - timedelta(minutes=1),
        logical_close_ts_utc=close,
    )


def _acc(*, expected: int = 1, setup: int = 1, b0: Bar | None = None):
    return DisplacementAccumulator(
        identity=IDENTITY,
        scheme=RESEARCH_SESSION_SCHEME,
        setup_id="setup",
        window_kind="parent_reaction",
        start_evidence_id="start",
        b0=b0 or _bar(0, 10, 10, 10, 10),
        expected_sign=expected,
        setup_sign=setup,
    )


def test_19_full_body_bullish_candle() -> None:
    p = candle_primitives(_bar(1, 10, 14, 10, 14), previous_close_ticks=10)
    assert (p.range_ticks, p.body_ticks, p.upper_wick_ticks, p.lower_wick_ticks) == (4, 4, 0, 0)
    assert p.close_location_value == 1


def test_20_full_body_bearish_candle() -> None:
    p = candle_primitives(_bar(1, 14, 14, 10, 10), previous_close_ticks=14)
    assert (p.body_ticks, p.upper_wick_ticks, p.lower_wick_ticks) == (4, 0, 0)
    assert p.close_location_value == -1


def test_21_doji_is_neither_directional_nor_opposing() -> None:
    acc = _acc()
    bar = _bar(1, 10, 12, 8, 10)
    acc.on_bar(bar)
    summary = acc.finalize(end_evidence_id="end", end_bar=bar)
    assert summary.metrics["doji_bar_count"] == 1
    assert summary.metrics["directional_bar_count"] == 0
    assert summary.metrics["opposing_bar_count"] == 0


def test_22_zero_range_keeps_raw_ticks_and_nulls_ratios() -> None:
    acc = _acc()
    bar = _bar(1, 10, 10, 10, 10)
    acc.on_bar(bar)
    summary = acc.finalize(end_evidence_id="end", end_bar=bar)
    assert summary.metrics["range_ticks_mean"] == 0
    assert summary.metrics["body_fraction_mean"] is None
    assert summary.metric_missing_reasons["body_fraction_mean"] == MissingReason.ZERO_RANGE


def test_23_upper_and_lower_wick_decomposition() -> None:
    p = candle_primitives(_bar(1, 11, 15, 8, 13), previous_close_ticks=10)
    assert (p.upper_wick_ticks, p.lower_wick_ticks, p.body_ticks) == (2, 3, 2)


def test_24_directional_and_opposing_wicks_mirror_orientation() -> None:
    bar = _bar(1, 11, 15, 8, 13)
    bull = _acc(expected=1)
    bear = _acc(expected=-1)
    bull.on_bar(bar)
    bear.on_bar(bar)
    a = bull.finalize(end_evidence_id="a", end_bar=bar)
    b = bear.finalize(end_evidence_id="b", end_bar=bar)
    assert a.metrics["directional_wick_fraction_mean"] == b.metrics["opposing_wick_fraction_mean"]
    assert a.metrics["opposing_wick_fraction_mean"] == b.metrics["directional_wick_fraction_mean"]


def test_25_bar_overlap_formula_and_zero_union() -> None:
    value, reason = overlap_fraction(_bar(1, 10, 14, 8, 12), _bar(2, 12, 16, 10, 14))
    assert value == pytest.approx(4 / 8)
    assert reason is None
    value, reason = overlap_fraction(_bar(1, 10, 10, 10, 10), _bar(2, 10, 10, 10, 10))
    assert value is None and reason is MissingReason.ZERO_RANGE


def test_26_perfect_directional_path_efficiency() -> None:
    acc = _acc()
    bars = (_bar(1, 10, 12, 10, 12), _bar(2, 12, 14, 12, 14))
    for bar in bars:
        acc.on_bar(bar)
    summary = acc.finalize(end_evidence_id="end", end_bar=bars[-1])
    assert summary.metrics["path_efficiency_abs"] == 1
    assert summary.metrics["expected_path_efficiency_signed"] == 1


def test_27_oscillatory_path_efficiency() -> None:
    acc = _acc()
    bars = (
        _bar(1, 10, 14, 10, 14),
        _bar(2, 14, 14, 11, 11),
        _bar(3, 11, 13, 11, 13),
    )
    for bar in bars:
        acc.on_bar(bar)
    summary = acc.finalize(end_evidence_id="end", end_bar=bars[-1])
    assert summary.metrics["raw_net_move_ticks"] == 3
    assert summary.metrics["path_efficiency_abs"] == pytest.approx(3 / 9)


def test_28_flat_path_returns_zero_efficiency() -> None:
    acc = _acc()
    bar = _bar(1, 10, 10, 10, 10)
    acc.on_bar(bar)
    summary = acc.finalize(end_evidence_id="end", end_bar=bar)
    assert summary.metrics["path_efficiency_abs"] == 0
    assert summary.metrics["raw_path_efficiency_signed"] == 0


def test_29_stage_interval_excludes_b0_and_includes_endpoint() -> None:
    b0 = _bar(0, 10, 12, 8, 10)
    acc = _acc(b0=b0)
    endpoint = _bar(1, 10, 12, 10, 12)
    acc.on_bar(b0)
    acc.on_bar(endpoint)
    summary = acc.finalize(end_evidence_id="end", end_bar=endpoint)
    assert summary.metrics["observed_bar_count"] == 1
    assert summary.last_included_bar_id == endpoint.bar_id


def test_30_post_transition_consumption_fails_closed() -> None:
    acc = _acc()
    endpoint = _bar(1, 10, 12, 10, 12)
    acc.on_bar(endpoint)
    acc.on_bar(_bar(2, 12, 13, 11, 13))
    with pytest.raises(ValueError, match="post-transition"):
        acc.finalize(end_evidence_id="end", end_bar=endpoint)


def test_31_long_setup_normalization() -> None:
    acc = _acc(expected=1, setup=1)
    bar = _bar(1, 10, 13, 10, 13)
    acc.on_bar(bar)
    summary = acc.finalize(end_evidence_id="end", end_bar=bar)
    assert summary.metrics["raw_net_move_ticks"] == 3
    assert summary.metrics["expected_net_move_ticks"] == 3
    assert summary.metrics["setup_net_move_ticks"] == 3


def test_32_short_setup_normalization_mirrors_long() -> None:
    bar = _bar(1, 10, 13, 10, 13)
    long = _acc(expected=1, setup=1)
    short = _acc(expected=-1, setup=-1)
    long.on_bar(bar)
    short.on_bar(bar)
    a = long.finalize(end_evidence_id="long", end_bar=bar)
    b = short.finalize(end_evidence_id="short", end_bar=bar)
    assert a.metrics["setup_net_move_ticks"] == -b.metrics["setup_net_move_ticks"]


def test_33_missing_expected_minute_invalidates_without_imputation() -> None:
    acc = _acc()
    endpoint = _bar(2, 10, 12, 10, 12)
    acc.on_bar(endpoint)
    summary = acc.finalize(end_evidence_id="end", end_bar=endpoint)
    assert not summary.valid
    assert summary.missing_reason is MissingReason.SOURCE_BAR_MISSING
    assert summary.metrics["missing_bar_count"] == 1
    assert summary.metrics["range_ticks_mean"] is None


def test_34_one_bar_interval_is_valid_but_overlap_is_unavailable() -> None:
    acc = _acc()
    bar = _bar(1, 10, 12, 10, 12)
    acc.on_bar(bar)
    summary = acc.finalize(end_evidence_id="end", end_bar=bar)
    assert summary.valid
    assert summary.metrics["overlap_fraction_mean"] is None
    assert summary.metric_missing_reasons["overlap_fraction_mean"] == MissingReason.INSUFFICIENT_PAIRS


def test_35_incremental_snapshot_resume_matches_continuous() -> None:
    bars = (
        _bar(1, 10, 12, 10, 12),
        _bar(2, 12, 13, 11, 11),
        _bar(3, 11, 15, 11, 15),
    )
    continuous = _acc()
    split = _acc()
    for bar in bars:
        continuous.on_bar(bar)
    split.on_bar(bars[0])
    split = DisplacementAccumulator.from_snapshot(
        split.snapshot(), identity=IDENTITY, scheme=RESEARCH_SESSION_SCHEME
    )
    for bar in bars[1:]:
        split.on_bar(bar)
    a = continuous.finalize(end_evidence_id="end", end_bar=bars[-1])
    b = split.finalize(end_evidence_id="end", end_bar=bars[-1])
    assert a.to_dict() == b.to_dict()


@pytest.mark.parametrize(
    ("start", "end"),
    (
        (
            datetime(2026, 1, 5, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 8, 2, 3, tzinfo=UTC),
        ),
        (
            datetime(2026, 3, 7, 0, 0, tzinfo=UTC),
            datetime(2026, 3, 10, 0, 0, tzinfo=UTC),
        ),
        (
            datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 11, 3, 0, 0, tzinfo=UTC),
        ),
        (
            datetime(2026, 1, 5, 0, 0, 17, tzinfo=UTC),
            datetime(2026, 1, 5, 3, 2, 44, tzinfo=UTC),
        ),
    ),
)
@pytest.mark.parametrize("scheme", (RESEARCH_SESSION_SCHEME, IFVG_DOC_SESSION_SCHEME))
def test_eligible_minute_count_and_membership_match_materialized_clock(
    start: datetime,
    end: datetime,
    scheme,
) -> None:
    materialized = eligible_minute_closes(start, end, scheme)
    assert eligible_minute_close_count(start, end, scheme) == len(materialized)
    assert all(is_eligible_minute_close(start, close, scheme) for close in materialized)


def test_ordered_bar_id_hash_uses_portable_length_prefixed_chain() -> None:
    accumulator = _acc()
    bars = tuple(
        _bar(index, 10, 12, 8, 10 + index % 3)
        for index in range(1, 401)
    )
    for bar in bars:
        accumulator.on_bar(bar)
    summary = accumulator.finalize(end_evidence_id="end", end_bar=bars[-1])
    expected = hashlib.sha256(b"ifvg-context-chain-v2\0").digest()
    for bar in bars:
        record = canonical_json(bar.bar_id).encode("utf-8")
        expected = hashlib.sha256(
            expected + len(record).to_bytes(8, "big") + record
        ).digest()
    assert summary.observed_bar_ids_hash == expected.hex()
    assert len(canonical_json(accumulator.snapshot()).encode("utf-8")) < 5_000
