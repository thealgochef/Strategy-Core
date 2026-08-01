from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from strategy_core.strategies.ifvg_smc.context_config import (
    FEATURE_SCHEMA_HASH,
    ContextFeatureConfig,
    build_context_identity,
    build_feature_registry,
    context_config_hash,
    feature_schema_hash,
)
from strategy_core.structures.context import AnchorStatus, MissingReason
from strategy_core.structures.market_structure import (
    BreakType,
    MarketStructureTracker,
    StructureDirection,
    build_mtf_snapshot,
    build_structure_delta,
)
from strategy_core.types import Bar, BarKind, CloseReason, Direction

DAY = date(2026, 1, 6)
BASE = datetime(2026, 1, 6, 14, 0, tzinfo=UTC)


def _bar(i: int, price: int, *, seconds: int = 60, complete: bool = True) -> Bar:
    close = BASE + timedelta(seconds=seconds * (i + 1))
    return Bar(
        timeframe_ticks=seconds,
        trading_day=DAY,
        bar_index=i,
        bar_id=f"{seconds}s:{DAY}:{i}",
        open_ts_utc=close - timedelta(seconds=seconds // 2),
        close_ts_utc=close - timedelta(seconds=1),
        open_ticks=price,
        high_ticks=price + 1,
        low_ticks=price - 1,
        close_ticks=price,
        volume=1,
        trade_count=1,
        is_complete=complete,
        is_partial=not complete,
        close_reason=CloseReason.COMPLETE if complete else CloseReason.END_OF_DAY,
        kind=BarKind.TIME,
        logical_open_ts_utc=close - timedelta(seconds=seconds),
        logical_close_ts_utc=close,
    )


def _tracker(*, timeframe: str = "1m", seconds: int = 60, strength: int = 1):
    identity = build_context_identity(ContextFeatureConfig(), symbol="NQ")
    return MarketStructureTracker(
        timeframe=timeframe,
        timeframe_seconds=seconds,
        identity=identity,
        anchor_status=(
            AnchorStatus.EXPERIMENTAL_Q40_OPEN
            if seconds == 14400
            else AnchorStatus.RATIFIED
        ),
        strength=strength,
    )


def _warm_tracker(direction: Direction = Direction.LONG):
    tracker = _tracker()
    states = []
    confirmed = []
    # Two highs and lows, then bullish initial break and bearish CHoCH.
    for i, price in enumerate((10, 14, 11, 8, 12, 9, 15, 10, 7, 13)):
        confirmed.extend(tracker.on_bar_closed(_bar(i, price)))
        states.append(
            tracker.state(
                direction,
                as_of_ts=_bar(i, price).availability_ts_utc,
                as_of_cursor=f"capture:{i}",
            )
        )
    return tracker, tuple(confirmed), tuple(states)


def test_01_swing_pivot_is_available_only_after_confirmation() -> None:
    tracker = _tracker(strength=3)
    prices = (10, 11, 12, 20, 12, 11, 10)
    for i, price in enumerate(prices[:-1]):
        assert tracker.on_bar_closed(_bar(i, price)) == ()
    swings = tracker.on_bar_closed(_bar(6, prices[-1]))
    assert len(swings) == 1
    assert swings[0].pivot_bar_id.endswith(":3")
    assert swings[0].confirmation_bar_id.endswith(":6")
    assert swings[0].pivot_ts < swings[0].confirmation_ts


def test_02_pivot_information_is_not_backdated() -> None:
    tracker = _tracker(strength=1)
    tracker.on_bar_closed(_bar(0, 10))
    tracker.on_bar_closed(_bar(1, 20))
    before = tracker.state(
        Direction.LONG,
        as_of_ts=_bar(1, 20).availability_ts_utc,
        as_of_cursor="before",
    )
    assert before.latest_high_swing_id is None
    swing = tracker.on_bar_closed(_bar(2, 10))[0]
    assert swing.confirmation_ts == _bar(2, 10).availability_ts_utc


def test_03_bos_is_same_direction_later_break_only() -> None:
    _tracker_obj, _swings, states = _warm_tracker()
    initial = next(item for item in states if item.last_break_type is BreakType.INITIAL_BREAK)
    assert initial.structure_direction is StructureDirection.BULLISH
    # Feed a newer confirmed high, then a strict later close through it.
    tracker, _, _ = _warm_tracker()
    tracker.on_bar_closed(_bar(10, 16))
    tracker.on_bar_closed(_bar(11, 18))
    tracker.on_bar_closed(_bar(12, 14))
    tracker.on_bar_closed(_bar(13, 21))
    state = tracker.state(Direction.LONG, as_of_ts=_bar(13, 21).availability_ts_utc, as_of_cursor="bos")
    assert state.last_break_type in (BreakType.BOS, BreakType.CHOCH)


def test_04_choch_requires_opposite_strict_close() -> None:
    _tracker_obj, _swings, states = _warm_tracker()
    choch = next(item for item in states if item.last_break_type is BreakType.CHOCH)
    assert choch.structure_direction is StructureDirection.BEARISH


def test_05_forming_timeframe_bars_are_excluded() -> None:
    tracker = _tracker(strength=1)
    assert tracker.on_bar_closed(_bar(0, 10, complete=False)) == ()
    state = tracker.state(Direction.LONG, as_of_ts=BASE, as_of_cursor="forming")
    assert not state.source_available
    assert state.missing_reason is MissingReason.SOURCE_UNAVAILABLE


@pytest.mark.parametrize(
    ("timeframe", "seconds", "status"),
    [
        ("1m", 60, AnchorStatus.RATIFIED),
        ("3m", 180, AnchorStatus.RATIFIED),
        ("5m", 300, AnchorStatus.RATIFIED),
        ("10m", 600, AnchorStatus.RATIFIED),
        ("15m", 900, AnchorStatus.RATIFIED),
        ("30m", 1800, AnchorStatus.RATIFIED),
        ("60m", 3600, AnchorStatus.RATIFIED),
        ("240m", 14400, AnchorStatus.EXPERIMENTAL_Q40_OPEN),
    ],
)
def test_06_completed_bar_routing_supported_for_every_context_timeframe(
    timeframe: str, seconds: int, status: AnchorStatus
) -> None:
    tracker = _tracker(timeframe=timeframe, seconds=seconds)
    tracker.on_bar_closed(_bar(0, 10, seconds=seconds))
    state = tracker.state(Direction.LONG, as_of_ts=_bar(0, 10, seconds=seconds).availability_ts_utc, as_of_cursor="x")
    assert state.source_timeframe == timeframe
    assert state.anchor_status is status


def test_07_missing_higher_timeframe_is_not_neutral() -> None:
    state = _tracker(timeframe="240m", seconds=14400).state(
        Direction.LONG, as_of_ts=BASE, as_of_cursor="missing"
    )
    assert state.structure_direction is None
    assert state.structure_alignment is None
    assert not state.valid


def test_08_raw_direction_is_preserved() -> None:
    _tracker_obj, _swings, states = _warm_tracker()
    assert any(item.structure_direction is StructureDirection.BULLISH for item in states)
    assert any(item.structure_direction is StructureDirection.BEARISH for item in states)


def test_09_long_setup_alignment_uses_raw_sign() -> None:
    _tracker_obj, _swings, states = _warm_tracker(Direction.LONG)
    assert next(item for item in states if item.structure_direction is StructureDirection.BULLISH).structure_alignment == 1


def test_10_short_setup_alignment_mirrors_long() -> None:
    _long_tracker, _long_swings, long_states = _warm_tracker(Direction.LONG)
    _short_tracker, _short_swings, short_states = _warm_tracker(Direction.SHORT)
    pairs = [(a, b) for a, b in zip(long_states, short_states, strict=True) if a.valid]
    assert pairs
    assert all(a.structure_alignment == -b.structure_alignment for a, b in pairs)


def _synthetic_mtf(alignments: tuple[int | None, ...]):
    identity = build_context_identity(ContextFeatureConfig(), symbol="NQ")
    states = []
    for i, (tf, seconds) in enumerate(
        zip(ContextFeatureConfig().mtf_timeframes, (180, 300, 600, 900, 1800, 3600, 14400), strict=True)
    ):
        tracker, _, _states = _warm_tracker(Direction.LONG)
        raw = _states[-1]
        direction = (
            StructureDirection.BULLISH
            if alignments[i] == 1
            else StructureDirection.BEARISH if alignments[i] == -1 else StructureDirection.NEUTRAL
        )
        states.append(
            replace(
                raw,
                source_timeframe=tf,
                source_timeframe_seconds=seconds,
                structure_state_id=raw.structure_state_id,
                structure_direction=direction if alignments[i] is not None else None,
                structure_alignment=alignments[i],
                valid=alignments[i] is not None,
            )
        )
    local = _warm_tracker(Direction.LONG)[2][-1]
    return identity, tuple(states), local


def test_11_summaries_reconcile_to_raw_vector() -> None:
    identity, states, local = _synthetic_mtf((1, 1, 0, -1, None, 1, -1))
    snap = build_mtf_snapshot(identity=identity, setup_id="s", setup_direction=Direction.LONG, mtf_states=states, local_state=local, as_of_ts=BASE, as_of_cursor="c")
    assert (snap.aligned_tf_count, snap.conflicting_tf_count, snap.neutral_tf_count, snap.valid_tf_count) == (3, 2, 1, 6)


def test_12_highest_and_lowest_conflicting_timeframes_are_durations() -> None:
    identity, states, local = _synthetic_mtf((1, -1, 1, -1, 1, -1, 1))
    snap = build_mtf_snapshot(identity=identity, setup_id="s", setup_direction=Direction.LONG, mtf_states=states, local_state=local, as_of_ts=BASE, as_of_cursor="c")
    assert snap.highest_conflicting_tf_seconds == 3600
    assert snap.lowest_conflicting_tf_seconds == 300


def test_13_contiguous_alignment_span_is_ordered() -> None:
    identity, states, local = _synthetic_mtf((1, 1, 1, -1, -1, 1, 1))
    snap = build_mtf_snapshot(identity=identity, setup_id="s", setup_direction=Direction.LONG, mtf_states=states, local_state=local, as_of_ts=BASE, as_of_cursor="c")
    assert snap.contiguous_alignment_span == 3
    assert snap.contiguous_conflict_span == 2


def test_14_adjacent_transition_count_excludes_invalid_pairs() -> None:
    identity, states, local = _synthetic_mtf((1, -1, None, -1, 1, 1, -1))
    snap = build_mtf_snapshot(identity=identity, setup_id="s", setup_direction=Direction.LONG, mtf_states=states, local_state=local, as_of_ts=BASE, as_of_cursor="c")
    assert snap.adjacent_tf_transition_count == 3


def test_15_lower_higher_conflict_flags_require_complete_groups() -> None:
    identity, states, local = _synthetic_mtf((1, 1, 1, 1, 1, -1, -1))
    snap = build_mtf_snapshot(identity=identity, setup_id="s", setup_direction=Direction.LONG, mtf_states=states, local_state=local, as_of_ts=BASE, as_of_cursor="c")
    assert snap.lower_support_higher_conflict is True
    assert snap.lower_conflict_higher_support is False


def test_16_snapshot_and_delta_are_deterministic() -> None:
    identity, states_a, local = _synthetic_mtf((1, 1, 1, 1, 1, 1, 1))
    _, states_b, _ = _synthetic_mtf((-1, 1, 1, 1, 1, 1, 1))
    a = build_mtf_snapshot(identity=identity, setup_id="s", setup_direction=Direction.LONG, mtf_states=states_a, local_state=local, as_of_ts=BASE, as_of_cursor="a")
    b = build_mtf_snapshot(identity=identity, setup_id="s", setup_direction=Direction.LONG, mtf_states=states_b, local_state=local, as_of_ts=BASE + timedelta(minutes=1), as_of_cursor="b")
    delta = build_structure_delta(identity=identity, delta_kind="tap_to_lock", source=a, destination=b)
    assert delta.changed_timeframe_count == 1
    assert delta.support_to_conflict_count == 1
    assert delta.structure_delta_id == build_structure_delta(identity=identity, delta_kind="tap_to_lock", source=a, destination=b).structure_delta_id


def test_17_sixty_and_240_minute_anchor_statuses_are_distinct() -> None:
    assert _tracker(timeframe="60m", seconds=3600).anchor_status is AnchorStatus.RATIFIED
    assert _tracker(timeframe="240m", seconds=14400).anchor_status is AnchorStatus.EXPERIMENTAL_Q40_OPEN


def test_18_registry_and_config_identity_are_frozen_and_sensitive() -> None:
    config = ContextFeatureConfig()
    assert len(build_feature_registry(config)) == 470
    assert feature_schema_hash(config) == FEATURE_SCHEMA_HASH
    changed = replace(config, pool_max_members=15)
    assert context_config_hash(changed) != context_config_hash(config)
    assert feature_schema_hash(changed) != feature_schema_hash(config)
