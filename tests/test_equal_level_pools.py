from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from strategy_core.constants import RESEARCH_SESSION_SCHEME
from strategy_core.strategies.ifvg_smc.context_config import (
    ContextFeatureConfig,
    build_context_identity,
)
from strategy_core.strategies.ifvg_smc.context_features import IfvgContextObserver
from strategy_core.structures.context import record_provenance
from strategy_core.structures.equal_levels import EqualLevelPoolTracker, PoolType
from strategy_core.structures.market_structure import ConfirmedSwingEvidence
from strategy_core.structures.sweeps import (
    strict_pool_reclaim_distance,
    strict_pool_sweep_depth,
)
from strategy_core.types import Bar, BarKind, CloseReason, Direction, Side

DAY = date(2026, 1, 6)
BASE = datetime(2026, 1, 6, 14, 0, tzinfo=UTC)
IDENTITY = build_context_identity(ContextFeatureConfig(), symbol="NQ")


def _bar(i: int, *, o: int = 100, high: int = 101, low: int = 99, close: int = 100) -> Bar:
    ts = BASE + timedelta(minutes=i)
    return Bar(
        timeframe_ticks=60,
        trading_day=DAY,
        bar_index=i,
        bar_id=f"60s:{DAY}:{i}",
        open_ts_utc=ts - timedelta(seconds=40),
        close_ts_utc=ts - timedelta(seconds=1),
        open_ticks=o,
        high_ticks=high,
        low_ticks=low,
        close_ticks=close,
        volume=1,
        trade_count=1,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
        kind=BarKind.TIME,
        logical_open_ts_utc=ts - timedelta(minutes=1),
        logical_close_ts_utc=ts,
    )


def _swing(i: int, price: int, side: Side, *, timeframe: str = "1m", seconds: int = 60):
    ts = BASE + timedelta(minutes=i)
    cursor = f"{ts.isoformat()}|{seconds}|{DAY}|confirm:{i}"
    from strategy_core.structures.context import context_uuid

    return ConfirmedSwingEvidence(
        **record_provenance(
            IDENTITY,
            as_of_ts=ts,
            as_of_cursor=cursor,
            source_close_ts=ts,
            source_confirmed_ts=ts,
            valid=True,
            warmup_complete=True,
            source_available=True,
            missing_reason=None,
        ),
        swing_id=context_uuid("swing-test", seconds, side, i, price),
        source_timeframe=timeframe,
        source_timeframe_seconds=seconds,
        side=side,
        price_ticks=price,
        pivot_bar_id=f"pivot:{i}",
        pivot_ts=ts - timedelta(minutes=3),
        confirmation_bar_id=f"confirm:{i}",
        confirmation_ts=ts,
        availability_cursor=cursor,
        confirmation_strength=3,
    )


def _pool_tracker(**kwargs) -> EqualLevelPoolTracker:
    return EqualLevelPoolTracker(identity=IDENTITY, **kwargs)


def _create_pool(
    tracker: EqualLevelPoolTracker,
    side: Side,
    first: int,
    second: int,
    *,
    start_i: int = 1,
):
    tracker.on_confirmed_swing(_swing(start_i, first, side))
    pool_id = tracker.on_confirmed_swing(_swing(start_i + 1, second, side))
    assert pool_id is not None
    return pool_id


def test_36_pool_unavailable_before_second_confirmation() -> None:
    tracker = _pool_tracker()
    tracker.on_confirmed_swing(_swing(1, 100, Side.HIGH))
    assert tracker.active_pool_records(as_of_ts=BASE + timedelta(minutes=1), as_of_cursor="a") == ()
    tracker.on_confirmed_swing(_swing(2, 100, Side.HIGH))
    assert tracker.active_pool_records(as_of_ts=BASE + timedelta(minutes=2, seconds=-1), as_of_cursor="b") == ()
    assert len(tracker.active_pool_records(as_of_ts=BASE + timedelta(minutes=2), as_of_cursor="c")) == 1


def test_37_pool_confirmation_is_not_backdated_to_pivot() -> None:
    tracker = _pool_tracker()
    pool_id = _create_pool(tracker, Side.HIGH, 100, 100)
    pool = tracker.pool_at(pool_id)
    assert pool is not None
    assert pool.confirmation_ts > pool.latest_pivot_ts


def test_38_two_equal_highs_create_one_eqh_pool() -> None:
    tracker = _pool_tracker()
    _create_pool(tracker, Side.HIGH, 100, 100)
    pools = tracker.active_pool_records(as_of_ts=BASE + timedelta(minutes=3), as_of_cursor="x")
    assert len(pools) == 1 and pools[0].pool_type is PoolType.EQH


def test_39_two_equal_lows_create_one_eql_pool() -> None:
    tracker = _pool_tracker()
    _create_pool(tracker, Side.LOW, 100, 100)
    pools = tracker.active_pool_records(as_of_ts=BASE + timedelta(minutes=3), as_of_cursor="x")
    assert len(pools) == 1 and pools[0].pool_type is PoolType.EQL


def test_40_multiple_compatible_swings_do_not_create_pairwise_duplicates() -> None:
    tracker = _pool_tracker()
    pool_id = _create_pool(tracker, Side.HIGH, 100, 101)
    tracker.on_confirmed_swing(_swing(3, 100, Side.HIGH))
    tracker.on_confirmed_swing(_swing(4, 101, Side.HIGH))
    pools = tracker.active_pool_records(as_of_ts=BASE + timedelta(minutes=5), as_of_cursor="x")
    assert [pool.pool_id for pool in pools] == [pool_id]
    assert pools[0].swing_count == 4


def test_41_chain_merging_cannot_expand_beyond_one_tick() -> None:
    tracker = _pool_tracker()
    pool_id = _create_pool(tracker, Side.HIGH, 100, 101)
    tracker.on_confirmed_swing(_swing(3, 102, Side.HIGH))
    pool = tracker.pool_at(pool_id)
    assert pool is not None
    assert pool.upper_bound_ticks - pool.lower_bound_ticks == 1
    assert pool.swing_count == 2


def test_42_representative_price_update_is_deterministic() -> None:
    tracker = _pool_tracker()
    pool_id = _create_pool(tracker, Side.HIGH, 100, 101)
    tracker.on_confirmed_swing(_swing(3, 101, Side.HIGH))
    pool = tracker.pool_at(pool_id)
    assert pool is not None and pool.representative_price_ticks == 101


def test_43_pool_bounds_update_deterministically() -> None:
    tracker = _pool_tracker()
    pool_id = _create_pool(tracker, Side.LOW, 100, 100)
    tracker.on_confirmed_swing(_swing(3, 99, Side.LOW))
    pool = tracker.pool_at(pool_id)
    assert pool is not None
    assert (pool.lower_bound_ticks, pool.upper_bound_ticks) == (99, 100)


def test_44_pool_ids_are_stable_across_replay() -> None:
    first = _pool_tracker()
    second = _pool_tracker()
    assert _create_pool(first, Side.HIGH, 100, 101) == _create_pool(second, Side.HIGH, 100, 101)


def test_45_v1_has_no_time_expiry() -> None:
    tracker = _pool_tracker()
    pool_id = _create_pool(tracker, Side.HIGH, 100, 100)
    pool = tracker.active_pool_records(as_of_ts=BASE + timedelta(days=30), as_of_cursor="later")[0]
    assert pool.pool_id == pool_id and pool.expiration_reason is None


def test_46_capacity_invalidation_is_deterministic() -> None:
    tracker = _pool_tracker(max_active_per_timeframe=1)
    first = _create_pool(tracker, Side.HIGH, 100, 100, start_i=1)
    second = _create_pool(tracker, Side.HIGH, 110, 110, start_i=3)
    assert tracker.pool_at(first) is not None
    assert tracker.pool_at(first).invalidation_reason == "capacity_evicted"  # type: ignore[union-attr]
    assert tracker.active_pool_records(as_of_ts=BASE + timedelta(minutes=5), as_of_cursor="x")[0].pool_id == second


def test_47_eqh_eql_use_shared_strict_sweep_helpers() -> None:
    bar = _bar(4, high=102, low=98, close=100)
    assert strict_pool_sweep_depth("eqh", lower_bound_ticks=100, upper_bound_ticks=101, bar=bar) == 1
    assert strict_pool_sweep_depth("eql", lower_bound_ticks=99, upper_bound_ticks=100, bar=bar) == 1


def test_48_sweep_reference_id_and_type_are_exact() -> None:
    tracker = _pool_tracker()
    pool_id = _create_pool(tracker, Side.HIGH, 100, 100)
    bar = _bar(4, high=102, low=99, close=101)
    tracker.on_source_bar(bar)
    link = tracker.on_probe_bar(bar)[0]
    assert link.pool_id == pool_id and link.pool_type is PoolType.EQH


def test_49_sweep_depth_uses_strict_outer_bound() -> None:
    tracker = _pool_tracker()
    _create_pool(tracker, Side.LOW, 100, 101)
    bar = _bar(4, high=103, low=97, close=99)
    tracker.on_source_bar(bar)
    link = tracker.on_probe_bar(bar)[0]
    assert link.sweep_depth_ticks == 3


def test_50_reclaim_is_point_in_time_and_same_bar_latency_is_zero() -> None:
    tracker = _pool_tracker()
    _create_pool(tracker, Side.HIGH, 100, 100)
    sweep = _bar(4, high=102, low=98, close=100)
    tracker.on_source_bar(sweep)
    link = tracker.on_probe_bar(sweep)[0]
    assert not link.reclaimed_after_sweep
    reclaim = _bar(5, high=101, low=98, close=99)
    tracker.on_source_bar(reclaim)
    updated = tracker.on_probe_bar(reclaim)[0]
    assert updated.reclaimed_after_sweep and updated.reclaim_latency_bars == 1
    assert strict_pool_reclaim_distance("eqh", lower_bound_ticks=100, upper_bound_ticks=100, close_ticks=99) == 1


def test_51_swept_pool_cannot_be_reused() -> None:
    tracker = _pool_tracker()
    pool_id = _create_pool(tracker, Side.HIGH, 100, 100)
    sweep = _bar(4, high=102, low=99, close=101)
    tracker.on_source_bar(sweep)
    tracker.on_probe_bar(sweep)
    tracker.on_confirmed_swing(_swing(5, 100, Side.HIGH))
    pool = tracker.pool_at(pool_id)
    assert pool is not None and not pool.active and pool.swing_count == 2


def _two_sided_tracker() -> EqualLevelPoolTracker:
    tracker = _pool_tracker()
    _create_pool(tracker, Side.HIGH, 110, 110, start_i=1)
    _create_pool(tracker, Side.LOW, 90, 90, start_i=3)
    return tracker


def test_52_long_thesis_relative_pool_features() -> None:
    tracker = _two_sided_tracker()
    context, containing = tracker.nearest_context(price_ticks=100, setup_direction=Direction.LONG, as_of_ts=BASE + timedelta(minutes=6), as_of_cursor="x")
    assert containing == 0
    assert context["nearest_thesis_supporting"].pool_type is PoolType.EQH  # type: ignore[union-attr]
    assert context["nearest_thesis_opposing"].pool_type is PoolType.EQL  # type: ignore[union-attr]


def test_53_short_thesis_relative_pool_features_mirror_long() -> None:
    tracker = _two_sided_tracker()
    context, _ = tracker.nearest_context(price_ticks=100, setup_direction=Direction.SHORT, as_of_ts=BASE + timedelta(minutes=6), as_of_cursor="x")
    assert context["nearest_thesis_supporting"].pool_type is PoolType.EQL  # type: ignore[union-attr]
    assert context["nearest_thesis_opposing"].pool_type is PoolType.EQH  # type: ignore[union-attr]


def test_54_snapshot_resume_matches_continuous_pool_state() -> None:
    continuous = _pool_tracker()
    split = _pool_tracker()
    for tracker in (continuous, split):
        _create_pool(tracker, Side.HIGH, 100, 101)
    restored = EqualLevelPoolTracker.from_snapshot(split.snapshot(), identity=IDENTITY)
    continuous.on_confirmed_swing(_swing(3, 100, Side.HIGH))
    restored.on_confirmed_swing(_swing(3, 100, Side.HIGH))
    as_of = BASE + timedelta(minutes=4)
    assert [item.to_dict() for item in continuous.active_pool_records(as_of_ts=as_of, as_of_cursor="x")] == [item.to_dict() for item in restored.active_pool_records(as_of_ts=as_of, as_of_cursor="x")]


@pytest.mark.parametrize(
    ("direction", "side", "pool_type", "probe"),
    (
        (
            Direction.LONG,
            Side.LOW,
            PoolType.EQL,
            _bar(4, high=103, low=97, close=99),
        ),
        (
            Direction.SHORT,
            Side.HIGH,
            PoolType.EQH,
            _bar(4, high=103, low=97, close=101),
        ),
    ),
)
def test_formula_v2_pins_long_eql_and_short_eqh_opposing_leg_evidence(
    direction: Direction,
    side: Side,
    pool_type: PoolType,
    probe: Bar,
) -> None:
    observer = IfvgContextObserver(
        config=ContextFeatureConfig(),
        scheme=RESEARCH_SESSION_SCHEME,
        symbol="NQ",
    )
    observer._active_setup_id = "setup"  # noqa: SLF001 - adversarial observer fixture
    observer._active_direction = direction  # noqa: SLF001
    observer._parent_lock_cursor = "lock"  # noqa: SLF001
    pool_id = _create_pool(observer._equal, side, 100, 100)  # noqa: SLF001
    observer._armed_pool_distances[pool_id] = (4, None)  # noqa: SLF001
    observer._equal.on_source_bar(probe)  # noqa: SLF001
    new_links = observer._equal.on_probe_bar(probe)  # noqa: SLF001
    observer._collect_leg_links(new_links)  # noqa: SLF001
    assert len(observer._leg_sweep_links) == 1  # noqa: SLF001

    # Simulate bounded tombstone eviction, then seed/resume before inversion.
    observer._equal._links.clear()  # noqa: SLF001
    resumed = IfvgContextObserver(
        config=ContextFeatureConfig(),
        scheme=RESEARCH_SESSION_SCHEME,
        symbol="NQ",
        seed=observer.snapshot(),
    )
    resumed._last_bar_1m = probe  # noqa: SLF001
    inversion = SimpleNamespace(
        envelope=SimpleNamespace(setup_id="setup"),
        opposing_fvg_id="opposing",
        inversion_cursor="inversion",
    )
    qualified = resumed._qualifying_links(inversion)  # noqa: SLF001
    assert len(qualified) == 1
    assert qualified[0].pool_type is pool_type
    assert qualified[0].qualifies_opposing_leg
