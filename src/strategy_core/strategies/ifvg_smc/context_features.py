"""Post-reducer, measurement-only IFVG deterministic context observer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Mapping, Sequence
from uuid import UUID

from strategy_core.candles.exchange_calendar import (
    CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
    DEFAULT_CONTEXT_SOURCE_COVERAGE,
    ContextSourceCoverage,
    ExchangeMinuteSchedule,
)
from strategy_core.structures.context import (
    AnchorStatus,
    ContextIdentity,
    canonical_json,
    canonical_sha256,
    context_uuid,
    record_provenance,
)
from strategy_core.structures.displacement import (
    DisplacementAccumulator,
    DisplacementAccumulatorSnapshot,
    DisplacementWindowSummary,
)
from strategy_core.structures.equal_levels import (
    EqualLevelPoolLifecycleEvent,
    EqualLevelPoolTracker,
    EqualLevelPoolTrackerSnapshot,
    EqualLevelSweepLink,
    interval_distance_ticks,
)
from strategy_core.structures.fvg import Fvg
from strategy_core.structures.market_structure import (
    ConfirmedSwingEvidence,
    MarketStructureTracker,
    MarketStructureTrackerSnapshot,
    MtfConfluenceSnapshot,
    StructureTransitionDelta,
    build_mtf_snapshot,
    build_structure_delta,
)
from strategy_core.types import Bar, Direction, SessionScheme

from .context_config import ContextFeatureConfig, build_context_identity
from .context_records import (
    CaptureKind,
    ContextStateSnapshot,
    IfvgContextCapture,
    IfvgContextEvent,
)
from .records import (
    EligibleDecisionRecord,
    EntryCandidateRecord,
    HtfTapRecord,
    IfvgEmission,
    InversionRecord,
    OpposingGapRecord,
    ParentCandidateRecord,
    ParentLockRecord,
    SetupLifecycleEventRecord,
    bar_cursor,
)

__all__ = [
    "CONTEXT_OBSERVER_SEED_SCHEMA_VERSION",
    "IfvgContextObserver",
    "IfvgContextObserverSeed",
    "context_observer_seed_hash",
]

CONTEXT_OBSERVER_SEED_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class IfvgContextObserverSeed:
    schema_version: int
    identity: ContextIdentity
    calendar_schedule_hash: str
    source_coverage_hash: str
    structures: tuple[MarketStructureTrackerSnapshot, ...]
    equal_levels: EqualLevelPoolTrackerSnapshot
    active_accumulators: tuple[tuple[str, DisplacementAccumulatorSnapshot], ...]
    active_setup_id: str | None
    active_direction: Direction | None
    selected_parent_id: str | None
    selected_opposing_id: str | None
    parent_summaries: tuple[tuple[str, DisplacementWindowSummary], ...]
    opposing_summaries: tuple[tuple[str, DisplacementWindowSummary], ...]
    endpoint_snapshots: tuple[tuple[str, MtfConfluenceSnapshot], ...]
    candidate_events: tuple[tuple[str, IfvgContextEvent], ...]
    decision_events: tuple[tuple[str, IfvgContextEvent], ...]
    parent_lock_cursor: str | None
    armed_pool_distances: tuple[tuple[UUID, int, float | None], ...]
    leg_sweep_links: tuple[EqualLevelSweepLink, ...]
    qualified_links: tuple[EqualLevelSweepLink, ...]
    pending_lifecycle: tuple[EqualLevelPoolLifecycleEvent, ...]

    @property
    def context_config_hash(self) -> str:
        """Compatibility view derived from the single stored identity."""

        return self.identity.context_config_hash


def context_observer_seed_hash(seed: IfvgContextObserverSeed) -> str:
    return hashlib.sha256(canonical_json(seed).encode("utf-8")).hexdigest()


class IfvgContextObserver:
    """One-way observer: advance shared state before reducer, capture after reducer."""

    def __init__(
        self,
        *,
        config: ContextFeatureConfig,
        scheme: SessionScheme,
        schedule: ExchangeMinuteSchedule = CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
        source_coverage: ContextSourceCoverage = DEFAULT_CONTEXT_SOURCE_COVERAGE,
        symbol: str,
        tick_size: str = "0.25",
        strategy_core_commit: str = "0" * 40,
        strategy_core_source_tree_hash: str = "0" * 64,
        seed: IfvgContextObserverSeed | None = None,
    ) -> None:
        self.config = config
        self.scheme = scheme
        self.schedule = schedule
        self.source_coverage = source_coverage
        self.identity = build_context_identity(
            config,
            symbol=symbol,
            tick_size=tick_size,
            strategy_core_commit=strategy_core_commit,
            strategy_core_source_tree_hash=strategy_core_source_tree_hash,
        )
        self._trackers: dict[int, MarketStructureTracker] = {}
        if seed is not None:
            self._restore(seed)
            return
        for timeframe in config.normalized_timeframes:
            seconds = config.seconds_for(timeframe)
            self._trackers[seconds] = MarketStructureTracker(
                timeframe=timeframe,
                timeframe_seconds=seconds,
                identity=self.identity,
                anchor_status=(
                    AnchorStatus.EXPERIMENTAL_Q40_OPEN
                    if timeframe == "240m"
                    else AnchorStatus.RATIFIED
                ),
                strength=config.swing_strength,
                capacity=config.swing_capacity_per_timeframe,
            )
        self._equal = EqualLevelPoolTracker(
            identity=self.identity,
            tolerance_policy=config.equal_level_tolerance_policy,
            atr_period=config.atr_scale_period,
            local_range_period=config.local_range_scale_period,
            max_active_per_timeframe=config.pool_max_active_per_timeframe,
            max_members=config.pool_max_members,
            max_unmatched_per_side=config.pool_max_unmatched_per_timeframe_side,
            max_tombstones_per_timeframe=(
                config.pool_max_inactive_tombstones_per_timeframe
            ),
        )
        self._accumulators: dict[str, DisplacementAccumulator] = {}
        self._active_setup_id: str | None = None
        self._active_direction: Direction | None = None
        self._selected_parent_id: str | None = None
        self._selected_opposing_id: str | None = None
        self._parent_summaries: dict[str, DisplacementWindowSummary] = {}
        self._opposing_summaries: dict[str, DisplacementWindowSummary] = {}
        self._endpoints: dict[str, MtfConfluenceSnapshot] = {}
        self._candidate_events: dict[str, IfvgContextEvent] = {}
        self._decision_events: dict[str, IfvgContextEvent] = {}
        self._parent_lock_cursor: str | None = None
        self._armed_pool_distances: dict[UUID, tuple[int, float | None]] = {}
        self._leg_sweep_links: dict[UUID, EqualLevelSweepLink] = {}
        self._qualified_links: dict[UUID, EqualLevelSweepLink] = {}
        self._pending_lifecycle: list[EqualLevelPoolLifecycleEvent] = []
        self._aux_lifecycle: list[EqualLevelPoolLifecycleEvent] = []
        self._aux_swings: list[ConfirmedSwingEvidence] = []
        self._aux_sweep_links: list[EqualLevelSweepLink] = []
        self._last_bar_1m: Bar | None = None
        self._events: list[IfvgContextEvent] = []
        self._state_cache: dict[tuple[str, str, Direction], ContextStateSnapshot] = {}

    def _restore(self, seed: IfvgContextObserverSeed) -> None:
        if seed.schema_version != CONTEXT_OBSERVER_SEED_SCHEMA_VERSION:
            raise ValueError("context observer seed version mismatch")
        if seed.identity.context_config_hash != self.identity.context_config_hash:
            raise ValueError("context observer seed config hash mismatch")
        if seed.identity != self.identity:
            raise ValueError("context observer seed identity mismatch")
        if seed.calendar_schedule_hash != self.schedule.content_hash:
            raise ValueError("context observer seed calendar hash mismatch")
        if seed.source_coverage_hash != self.source_coverage.content_hash:
            raise ValueError("context observer seed source coverage hash mismatch")
        self._trackers = {
            snapshot.timeframe_seconds: MarketStructureTracker.from_snapshot(
                snapshot, identity=self.identity
            )
            for snapshot in seed.structures
        }
        expected = {self.config.seconds_for(item) for item in self.config.normalized_timeframes}
        if set(self._trackers) != expected:
            raise ValueError("context observer seed timeframe set mismatch")
        self._equal = EqualLevelPoolTracker.from_snapshot(
            seed.equal_levels, identity=self.identity
        )
        self._accumulators = {
            key: DisplacementAccumulator.from_snapshot(
                snapshot,
                identity=self.identity,
                scheme=self.scheme,
                schedule=self.schedule,
                source_coverage=self.source_coverage,
            )
            for key, snapshot in seed.active_accumulators
        }
        self._active_setup_id = seed.active_setup_id
        self._active_direction = seed.active_direction
        self._selected_parent_id = seed.selected_parent_id
        self._selected_opposing_id = seed.selected_opposing_id
        self._parent_summaries = dict(seed.parent_summaries)
        self._opposing_summaries = dict(seed.opposing_summaries)
        self._endpoints = dict(seed.endpoint_snapshots)
        self._candidate_events = dict(seed.candidate_events)
        self._decision_events = dict(seed.decision_events)
        self._parent_lock_cursor = seed.parent_lock_cursor
        self._armed_pool_distances = {
            pool_id: (distance, normalized)
            for pool_id, distance, normalized in seed.armed_pool_distances
        }
        self._leg_sweep_links = {
            link.sweep_link_id: link for link in seed.leg_sweep_links
        }
        self._qualified_links = {
            link.sweep_link_id: link for link in seed.qualified_links
        }
        self._pending_lifecycle = list(seed.pending_lifecycle)
        self._aux_lifecycle = []
        self._aux_swings = []
        self._aux_sweep_links = []
        self._last_bar_1m = None
        self._events = []
        self._state_cache = {}

    def advance_step(
        self,
        due_htf_bars: Sequence[Bar],
        bar_1m: Bar,
        new_fvgs: Mapping[int, Sequence[Fvg]],
    ) -> None:
        """Advance all point-in-time shared state before the unchanged reducer."""

        if self._state_cache:
            self._state_cache.clear()
        for bar in due_htf_bars:
            if not bar.is_complete or bar.timeframe_ticks == 60:
                continue
            self._advance_source_bar(bar)

        self._equal.on_source_bar(bar_1m)
        if self._accumulators:
            gaps_1m = new_fvgs.get(60, ())
            for accumulator in self._accumulators.values():
                accumulator.on_bar(bar_1m)
                for fvg in gaps_1m:
                    accumulator.on_fvg(fvg)
        new_links = self._equal.on_probe_bar(bar_1m)
        if new_links:
            self._aux_sweep_links.extend(new_links)
            self._collect_leg_links(new_links)
        confirmed = self._trackers[60].on_bar_closed(bar_1m)
        if confirmed:
            self._aux_swings.extend(confirmed)
            for swing in confirmed:
                self._equal.on_confirmed_swing(swing)
        lifecycle = self._equal.drain_lifecycle()
        if lifecycle:
            self._pending_lifecycle.extend(lifecycle)
            self._aux_lifecycle.extend(lifecycle)
        self._last_bar_1m = bar_1m

    def _advance_source_bar(self, bar: Bar) -> None:
        tracker = self._trackers.get(bar.timeframe_ticks)
        if tracker is None:
            raise ValueError(f"context received undeclared timeframe {bar.timeframe_ticks}s")
        self._equal.on_source_bar(bar)
        confirmed = tracker.on_bar_closed(bar)
        if confirmed:
            self._aux_swings.extend(confirmed)
            for swing in confirmed:
                self._equal.on_confirmed_swing(swing)

    def _collect_leg_links(self, links: Sequence[EqualLevelSweepLink]) -> None:
        if self._parent_lock_cursor is None or self._active_direction is None:
            return
        wanted = "eql" if self._active_direction is Direction.LONG else "eqh"
        for link in links:
            if (
                link.pool_id in self._armed_pool_distances
                and link.pool_type.value == wanted
            ):
                # Keep immutable evidence on the active setup.  A later reclaim
                # update replaces this value, but pool/tombstone eviction cannot
                # make the qualifying sweep disappear.
                self._leg_sweep_links[link.sweep_link_id] = link

    def capture(self, emissions: Sequence[IfvgEmission]) -> tuple[IfvgContextEvent, ...]:
        if self._last_bar_1m is None:
            raise RuntimeError("advance_step must precede context capture")
        if not emissions:
            if self._pending_lifecycle:
                self._pending_lifecycle.clear()
            return ()
        start = len(self._events)
        for emission in emissions:
            record = emission.record
            if emission.kind == "htf_tap" and isinstance(record, HtfTapRecord):
                if record.selected and record.envelope.setup_id:
                    self._activate_setup(record)
            elif emission.kind == "parent_candidate" and isinstance(record, ParentCandidateRecord):
                self._capture_parent(record)
            elif emission.kind == "parent_lock" and isinstance(record, ParentLockRecord):
                self._capture_parent_lock(record)
            elif emission.kind == "opposing" and isinstance(record, OpposingGapRecord):
                self._capture_opposing(record)
            elif emission.kind == "inversion" and isinstance(record, InversionRecord):
                self._capture_inversion(record)
            elif emission.kind == "entry_candidate" and isinstance(record, EntryCandidateRecord):
                self._capture_entry(record)
            elif emission.kind == "eligible_decision" and isinstance(record, EligibleDecisionRecord):
                self._capture_decision(record)
            elif emission.kind == "setup_lifecycle_event" and isinstance(
                record, SetupLifecycleEventRecord
            ):
                if record.transition == "trade_opened":
                    self._capture_trade_opened(record)
                elif record.transition in {
                    "setup_ended",
                    "trade_resolved",
                    "trade_unresolved",
                }:
                    self._clear_setup(record.envelope.setup_id)
        out = tuple(self._events[start:])
        # Lifecycle rows are drained independently for normalized offline tables.  Live
        # transition payloads carry only lifecycle changes from this same 1m step.
        self._pending_lifecycle.clear()
        return out

    def _activate_setup(self, record: HtfTapRecord) -> None:
        setup_id = record.envelope.setup_id
        self._active_setup_id = setup_id
        self._active_direction = record.direction
        self._selected_parent_id = None
        self._selected_opposing_id = None
        self._parent_summaries.clear()
        self._opposing_summaries.clear()
        self._endpoints.clear()
        self._candidate_events.clear()
        self._decision_events.clear()
        self._parent_lock_cursor = None
        self._armed_pool_distances.clear()
        self._leg_sweep_links.clear()
        self._qualified_links.clear()
        self._accumulators.clear()
        state = self._state(setup_id, record.direction)
        event = self._event(
            capture_kind=CaptureKind.HTF_TAP,
            state=state,
            evidence_id=f"htf_tap:{setup_id}:{record.tap_cursor}",
            evidence_cursor=record.tap_cursor,
        )
        self._endpoints["tap"] = state.mtf_snapshot
        self._events.append(event)
        self._accumulators["parent_reaction"] = self._new_accumulator(
            "parent_reaction",
            start_evidence_id=event.capture.evidence_id,
            expected_sign=self._direction_sign(record.direction),
        )

    def _capture_parent(self, record: ParentCandidateRecord) -> None:
        if not self._matches_active(record.envelope.setup_id):
            return
        accumulator = self._accumulators.get("parent_reaction")
        windows: tuple[DisplacementWindowSummary, ...] = ()
        if accumulator is not None:
            summary = accumulator.finalize(
                end_evidence_id=record.fvg.fvg_id,
                end_bar=self._last_bar(),
            )
            windows = (summary,)
        replacement = record.selected and self._selected_parent_id is not None
        if record.selected:
            self._selected_parent_id = record.fvg.fvg_id
            self._parent_summaries.clear()
            if accumulator is not None:
                self._parent_summaries[record.fvg.fvg_id] = summary
        state = self._state(record.envelope.setup_id, self._direction())
        self._events.append(
            self._event(
                capture_kind=(
                    CaptureKind.PARENT_REPLACEMENT
                    if replacement
                    else CaptureKind.PARENT_CANDIDATE
                ),
                state=state,
                evidence_id=record.fvg.fvg_id,
                evidence_cursor=bar_cursor(self._last_bar()),
                windows=windows,
            )
        )

    def _capture_parent_lock(self, record: ParentLockRecord) -> None:
        if not self._matches_active(record.envelope.setup_id):
            return
        state = self._state(record.envelope.setup_id, self._direction())
        deltas: tuple[StructureTransitionDelta, ...] = ()
        tap = self._endpoints.get("tap")
        if tap is not None:
            deltas = (
                build_structure_delta(
                    identity=self.identity,
                    delta_kind="tap_to_lock",
                    source=tap,
                    destination=state.mtf_snapshot,
                ),
            )
        summary = self._parent_summaries.get(record.parent_fvg_id)
        windows = (summary,) if summary is not None else ()
        event = self._event(
            capture_kind=CaptureKind.PARENT_LOCK,
            state=state,
            evidence_id=record.parent_fvg_id,
            evidence_cursor=record.lock_cursor,
            windows=windows,
            deltas=deltas,
        )
        self._events.append(event)
        self._endpoints["lock"] = state.mtf_snapshot
        self._parent_lock_cursor = record.lock_cursor
        self._armed_pool_distances.clear()
        for pool in self._equal.active_pool_records(
            as_of_ts=self._last_bar().availability_ts_utc,
            as_of_cursor=record.lock_cursor,
        ):
            distance = interval_distance_ticks(
                self._last_bar().close_ticks,
                pool.lower_bound_ticks,
                pool.upper_bound_ticks,
            )
            atr = self._equal.atr_at(pool.source_timeframe_seconds)
            self._armed_pool_distances[pool.pool_id] = (
                distance,
                distance / atr if atr else None,
            )
        self._accumulators["counter_leg"] = self._new_accumulator(
            "counter_leg",
            start_evidence_id=event.capture.evidence_id,
            expected_sign=-self._direction_sign(self._direction()),
        )

    def _capture_opposing(self, record: OpposingGapRecord) -> None:
        if not self._matches_active(record.envelope.setup_id):
            return
        counter = self._accumulators.get("counter_leg")
        windows: list[DisplacementWindowSummary] = []
        if counter is not None:
            summary = counter.finalize(
                end_evidence_id=record.fvg.fvg_id,
                end_bar=self._last_bar(),
            )
            windows.append(summary)
        replacement = record.selected and self._selected_opposing_id is not None
        if record.selected:
            self._selected_opposing_id = record.fvg.fvg_id
            self._opposing_summaries.clear()
            if counter is not None:
                self._opposing_summaries[record.fvg.fvg_id] = summary
        state = self._state(record.envelope.setup_id, self._direction())
        event = self._event(
            capture_kind=(
                CaptureKind.OPPOSING_REPLACEMENT
                if replacement
                else CaptureKind.OPPOSING_CANDIDATE
            ),
            state=state,
            evidence_id=record.fvg.fvg_id,
            evidence_cursor=bar_cursor(self._last_bar()),
            windows=tuple(windows),
        )
        self._events.append(event)
        if record.selected:
            self._endpoints["opposing"] = state.mtf_snapshot
            self._accumulators["inversion_response"] = self._new_accumulator(
                "inversion_response",
                start_evidence_id=record.fvg.fvg_id,
                expected_sign=self._direction_sign(self._direction()),
            )

    def _capture_inversion(self, record: InversionRecord) -> None:
        if not self._matches_active(record.envelope.setup_id):
            return
        state = self._state(record.envelope.setup_id, self._direction())
        windows: list[DisplacementWindowSummary] = []
        selected = self._opposing_summaries.get(record.opposing_fvg_id)
        if selected is not None:
            windows.append(selected)
        response = self._accumulators.get("inversion_response")
        if response is not None:
            windows.append(
                response.finalize(
                    end_evidence_id=f"inversion:{record.envelope.setup_id}:{record.inversion_cursor}",
                    end_bar=self._last_bar(),
                )
            )
        deltas: list[StructureTransitionDelta] = []
        lock = self._endpoints.get("lock")
        opposing = self._endpoints.get("opposing")
        if lock is not None and opposing is not None:
            deltas.append(
                build_structure_delta(
                    identity=self.identity,
                    delta_kind="lock_to_opposing",
                    source=lock,
                    destination=opposing,
                )
            )
        if opposing is not None:
            deltas.append(
                build_structure_delta(
                    identity=self.identity,
                    delta_kind="opposing_to_inversion",
                    source=opposing,
                    destination=state.mtf_snapshot,
                )
            )
        links = self._qualifying_links(record)
        self._qualified_links = {item.sweep_link_id: item for item in links}
        event = self._event(
            capture_kind=CaptureKind.INVERSION,
            state=state,
            evidence_id=f"inversion:{record.envelope.setup_id}:{record.inversion_cursor}",
            evidence_cursor=record.inversion_cursor,
            windows=tuple(windows),
            deltas=tuple(deltas),
            sweep_links=links,
        )
        self._events.append(event)
        self._endpoints["inversion"] = state.mtf_snapshot
        self._accumulators["post_inversion"] = self._new_accumulator(
            "post_inversion",
            start_evidence_id=event.capture.evidence_id,
            expected_sign=self._direction_sign(self._direction()),
        )

    def _capture_entry(self, record: EntryCandidateRecord) -> None:
        if not self._matches_active(record.envelope.setup_id):
            return
        state = self._state(record.envelope.setup_id, record.direction)
        windows: tuple[DisplacementWindowSummary, ...] = ()
        post = self._accumulators.get("post_inversion")
        if post is not None:
            windows = (
                post.finalize(end_evidence_id=record.candidate_id, end_bar=self._last_bar()),
            )
        deltas: tuple[StructureTransitionDelta, ...] = ()
        inversion = self._endpoints.get("inversion")
        if inversion is not None:
            deltas = (
                build_structure_delta(
                    identity=self.identity,
                    delta_kind="inversion_to_entry",
                    source=inversion,
                    destination=state.mtf_snapshot,
                ),
            )
        links = self._current_qualified_links()
        event = self._event(
            capture_kind=CaptureKind.ENTRY_CANDIDATE,
            state=state,
            evidence_id=record.candidate_id,
            evidence_cursor=record.trigger_cursor,
            candidate_id=record.candidate_id,
            windows=windows,
            deltas=deltas,
            sweep_links=links,
        )
        self._events.append(event)
        self._candidate_events[record.candidate_id] = event

    def _capture_decision(self, record: EligibleDecisionRecord) -> None:
        candidate = self._candidate_events.get(record.candidate_id)
        if candidate is None:
            raise ValueError("eligible decision has no exact candidate context capture")
        event = self._event(
            capture_kind=CaptureKind.ELIGIBLE_DECISION,
            state=candidate.state,
            evidence_id=record.decision_id,
            evidence_cursor=record.entry_cursor,
            candidate_id=record.candidate_id,
            decision_id=record.decision_id,
            windows=candidate.displacement_windows,
            deltas=candidate.structure_deltas,
            sweep_links=candidate.sweep_links,
        )
        self._events.append(event)
        self._decision_events[record.decision_id] = event

    def _capture_trade_opened(self, record: SetupLifecycleEventRecord) -> None:
        if not record.trade_id or not record.decision_id:
            raise ValueError("trade_opened lifecycle lacks exact trade/decision IDs")
        decision = self._decision_events.get(record.decision_id)
        if decision is None:
            raise ValueError("trade_opened has no exact decision context capture")
        event = self._event(
            capture_kind=CaptureKind.EXECUTED_TRADE_LINK,
            state=decision.state,
            evidence_id=record.trade_id,
            evidence_cursor=decision.capture.evidence_cursor,
            candidate_id=record.candidate_id,
            decision_id=record.decision_id,
            trade_id=record.trade_id,
            windows=decision.displacement_windows,
            deltas=(),
            sweep_links=decision.sweep_links,
            frozen_from_capture_id=decision.capture.context_capture_id,
        )
        self._events.append(event)

    def _state(self, setup_id: str, direction: Direction) -> ContextStateSnapshot:
        bar = self._last_bar()
        cursor = bar_cursor(bar)
        cache_key = (cursor, setup_id, direction)
        cached = self._state_cache.get(cache_key)
        if cached is not None:
            return cached
        mtf_states = tuple(
            self._trackers[self.config.seconds_for(timeframe)].state(
                direction,
                as_of_ts=bar.availability_ts_utc,
                as_of_cursor=cursor,
            )
            for timeframe in self.config.mtf_timeframes
        )
        local = self._trackers[60].state(
            direction,
            as_of_ts=bar.availability_ts_utc,
            as_of_cursor=cursor,
        )
        mtf = build_mtf_snapshot(
            identity=self.identity,
            setup_id=setup_id,
            setup_direction=direction,
            mtf_states=mtf_states,
            local_state=local,
            as_of_ts=bar.availability_ts_utc,
            as_of_cursor=cursor,
        )
        nearest, containing = self._equal.nearest_context(
            price_ticks=bar.close_ticks,
            setup_direction=direction,
            as_of_ts=bar.availability_ts_utc,
            as_of_cursor=cursor,
        )
        active_pool_hash = canonical_sha256(
            self._equal.active_pool_versions(as_of_ts=bar.availability_ts_utc)
        )
        payload = {
            "setup_id": setup_id,
            "direction": direction,
            "mtf_snapshot_id": mtf.mtf_snapshot_id,
            "active_pool_state_hash": active_pool_hash,
            "nearest": nearest,
            "containing": containing,
        }
        state_hash = canonical_sha256(payload)
        state_id = context_uuid(
            self.identity.feature_set_version,
            self.identity.feature_formula_version,
            self.identity.feature_schema_hash,
            self.identity.context_config_hash,
            self.identity.symbol,
            setup_id,
            cursor,
            state_hash,
        )
        state = ContextStateSnapshot(
            **record_provenance(
                self.identity,
                as_of_ts=bar.availability_ts_utc,
                as_of_cursor=cursor,
                source_close_ts=bar.availability_ts_utc,
                source_confirmed_ts=mtf.source_confirmed_ts,
                valid=mtf.valid,
                warmup_complete=mtf.warmup_complete,
                source_available=True,
                missing_reason=mtf.missing_reason,
            ),
            context_state_id=state_id,
            state_payload_hash=state_hash,
            setup_id=setup_id,
            setup_direction=direction.value.lower(),
            mtf_snapshot_id=mtf.mtf_snapshot_id,
            local_structure_state_id=local.structure_state_id,
            active_pool_state_hash=active_pool_hash,
            mtf_snapshot=mtf,
            nearest_context=nearest,
            containing_pool_count=containing,
        )
        self._state_cache[cache_key] = state
        return state

    def _event(
        self,
        *,
        capture_kind: CaptureKind,
        state: ContextStateSnapshot,
        evidence_id: str,
        evidence_cursor: str,
        candidate_id: str | None = None,
        decision_id: str | None = None,
        trade_id: str | None = None,
        windows: Sequence[DisplacementWindowSummary] = (),
        deltas: Sequence[StructureTransitionDelta] = (),
        sweep_links: Sequence[EqualLevelSweepLink] = (),
        frozen_from_capture_id: UUID | None = None,
    ) -> IfvgContextEvent:
        links = tuple(sweep_links)
        selected = max(
            links,
            key=lambda item: (item.sweep_cursor, str(item.pool_id)),
            default=None,
        )
        capture_id = context_uuid(
            self.identity.feature_set_version,
            self.identity.feature_formula_version,
            self.identity.feature_schema_hash,
            capture_kind,
            evidence_id,
            state.context_state_id,
        )
        capture = IfvgContextCapture(
            **record_provenance(
                self.identity,
                as_of_ts=state.as_of_ts,
                as_of_cursor=evidence_cursor,
                source_close_ts=state.source_close_ts,
                source_confirmed_ts=state.source_confirmed_ts,
                valid=state.valid,
                warmup_complete=state.warmup_complete,
                source_available=state.source_available,
                missing_reason=state.missing_reason,
            ),
            context_capture_id=capture_id,
            capture_kind=capture_kind,
            context_state_id=state.context_state_id,
            setup_id=state.setup_id,
            candidate_id=candidate_id,
            decision_id=decision_id,
            trade_id=trade_id,
            evidence_id=evidence_id,
            evidence_cursor=evidence_cursor,
            displacement_window_ids=tuple(item.displacement_window_id for item in windows),
            structure_delta_ids=tuple(item.structure_delta_id for item in deltas),
            opposing_leg_sweep_link_ids=tuple(item.sweep_link_id for item in links),
            selected_opposing_leg_sweep_link_id=(
                selected.sweep_link_id if selected is not None else None
            ),
            frozen_from_capture_id=frozen_from_capture_id,
        )
        lifecycle = tuple(self._pending_lifecycle)
        self._pending_lifecycle.clear()
        return IfvgContextEvent(
            capture=capture,
            state=state,
            structure_states=(*state.mtf_snapshot.states, state.mtf_snapshot.local_state),
            structure_deltas=tuple(deltas),
            displacement_windows=tuple(windows),
            pool_lifecycle_events=lifecycle,
            sweep_links=links,
        )

    def _qualifying_links(self, inversion: InversionRecord) -> tuple[EqualLevelSweepLink, ...]:
        out: list[EqualLevelSweepLink] = []
        for link in self._leg_sweep_links.values():
            if link.sweep_ts > self._last_bar().availability_ts_utc:
                continue
            distance, normalized = self._armed_pool_distances[link.pool_id]
            out.append(
                replace(
                    link,
                    setup_id=inversion.envelope.setup_id,
                    opposing_fvg_id=inversion.opposing_fvg_id,
                    parent_lock_cursor=self._parent_lock_cursor,
                    inversion_cursor=inversion.inversion_cursor,
                    qualifies_opposing_leg=True,
                    distance_at_lock_ticks=distance,
                    distance_at_lock_normalized=normalized,
                    as_of_ts=self._last_bar().availability_ts_utc,
                    as_of_cursor=inversion.inversion_cursor,
                )
            )
        return tuple(sorted(out, key=lambda item: (item.sweep_cursor, str(item.pool_id))))

    def _current_qualified_links(self) -> tuple[EqualLevelSweepLink, ...]:
        out: list[EqualLevelSweepLink] = []
        for link in self._qualified_links.values():
            distance, normalized = self._armed_pool_distances[link.pool_id]
            out.append(
                replace(
                    link,
                    setup_id=self._active_setup_id,
                    opposing_fvg_id=self._selected_opposing_id,
                    parent_lock_cursor=self._parent_lock_cursor,
                    inversion_cursor=(
                        self._endpoints["inversion"].as_of_cursor
                        if "inversion" in self._endpoints
                        else None
                    ),
                    qualifies_opposing_leg=True,
                    distance_at_lock_ticks=distance,
                    distance_at_lock_normalized=normalized,
                    as_of_ts=self._last_bar().availability_ts_utc,
                    as_of_cursor=bar_cursor(self._last_bar()),
                )
            )
        return tuple(sorted(out, key=lambda item: (item.sweep_cursor, str(item.pool_id))))

    def _new_accumulator(
        self,
        window_kind: str,
        *,
        start_evidence_id: str,
        expected_sign: int,
    ) -> DisplacementAccumulator:
        return DisplacementAccumulator(
            identity=self.identity,
            scheme=self.scheme,
            schedule=self.schedule,
            source_coverage=self.source_coverage,
            setup_id=self._active_setup_id or "",
            window_kind=window_kind,
            start_evidence_id=start_evidence_id,
            b0=self._last_bar(),
            expected_sign=expected_sign,
            setup_sign=self._direction_sign(self._direction()),
        )

    @staticmethod
    def _direction_sign(direction: Direction) -> int:
        return 1 if direction is Direction.LONG else -1

    def _direction(self) -> Direction:
        if self._active_direction is None:
            raise RuntimeError("no active context setup direction")
        return self._active_direction

    def _last_bar(self) -> Bar:
        if self._last_bar_1m is None:
            raise RuntimeError("no current 1m context bar")
        return self._last_bar_1m

    def _matches_active(self, setup_id: str) -> bool:
        return bool(setup_id and setup_id == self._active_setup_id)

    def _clear_setup(self, setup_id: str) -> None:
        if setup_id != self._active_setup_id:
            return
        self._active_setup_id = None
        self._active_direction = None
        self._selected_parent_id = None
        self._selected_opposing_id = None
        self._accumulators.clear()
        self._parent_summaries.clear()
        self._opposing_summaries.clear()
        self._endpoints.clear()
        self._candidate_events.clear()
        self._decision_events.clear()
        self._parent_lock_cursor = None
        self._armed_pool_distances.clear()
        self._leg_sweep_links.clear()
        self._qualified_links.clear()

    def drain_events(self) -> tuple[IfvgContextEvent, ...]:
        out = tuple(self._events)
        self._events.clear()
        return out

    def drain_lifecycle_records(self) -> tuple[EqualLevelPoolLifecycleEvent, ...]:
        out = tuple(self._aux_lifecycle)
        self._aux_lifecycle.clear()
        return out

    def drain_confirmed_swings(self) -> tuple[ConfirmedSwingEvidence, ...]:
        out = tuple(self._aux_swings)
        self._aux_swings.clear()
        return out

    def drain_sweep_link_records(self) -> tuple[EqualLevelSweepLink, ...]:
        out = tuple(self._aux_sweep_links)
        self._aux_sweep_links.clear()
        return out

    def snapshot(self) -> IfvgContextObserverSeed:
        return IfvgContextObserverSeed(
            schema_version=CONTEXT_OBSERVER_SEED_SCHEMA_VERSION,
            identity=self.identity,
            calendar_schedule_hash=self.schedule.content_hash,
            source_coverage_hash=self.source_coverage.content_hash,
            structures=tuple(
                self._trackers[seconds].snapshot() for seconds in sorted(self._trackers)
            ),
            equal_levels=self._equal.snapshot(),
            active_accumulators=tuple(
                (key, self._accumulators[key].snapshot())
                for key in sorted(self._accumulators)
            ),
            active_setup_id=self._active_setup_id,
            active_direction=self._active_direction,
            selected_parent_id=self._selected_parent_id,
            selected_opposing_id=self._selected_opposing_id,
            parent_summaries=tuple(sorted(self._parent_summaries.items())),
            opposing_summaries=tuple(sorted(self._opposing_summaries.items())),
            endpoint_snapshots=tuple(sorted(self._endpoints.items())),
            candidate_events=tuple(sorted(self._candidate_events.items())),
            decision_events=tuple(sorted(self._decision_events.items())),
            parent_lock_cursor=self._parent_lock_cursor,
            armed_pool_distances=tuple(
                (pool_id, distance, normalized)
                for pool_id, (distance, normalized) in sorted(
                    self._armed_pool_distances.items(), key=lambda item: str(item[0])
                )
            ),
            leg_sweep_links=tuple(
                self._leg_sweep_links[key]
                for key in sorted(self._leg_sweep_links, key=str)
            ),
            qualified_links=tuple(
                self._qualified_links[key]
                for key in sorted(self._qualified_links, key=str)
            ),
            pending_lifecycle=tuple(self._pending_lifecycle),
        )

    def state_size_bytes(self) -> int:
        return len(canonical_json(self.snapshot()).encode("utf-8"))
