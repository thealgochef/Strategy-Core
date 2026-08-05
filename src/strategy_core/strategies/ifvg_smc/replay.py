"""The ``ifvg_smc`` day orchestrator + ``run_day`` batch twin (QL's drive surface).

``DayOrchestrator`` owns the per-day wiring around the reducer — detectors,
registries, swing tracker, step assembly — and is shared by BOTH consumption
shapes so they cannot drift: ``run_day`` (offline: whole-day bar lists, the QL
research path) and the plugin (live: bars pushed one at a time when multi-TF
delivery lands). Canonical per-1m-close order (module contract, tested):

1. deliver every higher-TF bar with ``close_ts <=`` this 1m close (descending
   timeframe at a shared instant), detect their FVGs (NOT yet registered);
2. detect the 1m bar's own FVG (NOT yet registered);
3. registry fill maintenance for ALL timeframes on this 1m bar;
4. confirm swings on this bar;
5. ``reducer.step`` with the assembled :class:`IfvgStepInput` (live HTF view is
   post-maintenance; new gaps ride ``new_fvgs`` only);
6. register the new gaps (intake — usable from the NEXT bar, and never
   fillable by their own confirming bar thanks to the strict-after rule).

Levels are an INPUT (``levels_for``): the timeline must come from
``StrategyLevelState`` folds (QL Phase-A artifact offline; the plugin's own
fold live) — never re-derived from bars, per the one-surface rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from time import perf_counter_ns
from typing import TYPE_CHECKING, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from strategy_core.candles.exchange_calendar import (
    CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
    DEFAULT_CONTEXT_SOURCE_COVERAGE,
    ContextSourceCoverage,
    ExchangeMinuteSchedule,
)
from strategy_core.constants import DEFAULT_TICK_SIZE
from strategy_core.decisions.sessions import classify_session
from strategy_core.structures.fvg import FvgDetector, FvgFillEvent, FvgRegistry
from strategy_core.structures.swings import SwingTracker
from strategy_core.types import (
    Bar,
    Level,
    SessionScheme as RuntimeSessionScheme,
    SessionWindow,
    Side,
)

from .records import (
    IFVG_RECORD_SCHEMA_VERSION,
    DayFunnelRecord,
    IfvgEmission,
    RecordEnvelope,
)
from .reducer import IfvgReducer, IfvgReducerConfig, IfvgStepInput
from .section import (
    IFVG_STRATEGY_ID,
    IFVG_STRATEGY_VERSION,
    IfvgSmcSection,
    ifvg_profile_hash,
)
from .state import IFVG_SEED_SCHEMA_VERSION, IfvgDaySeed

if TYPE_CHECKING:
    from .context_config import ContextFeatureConfig
    from .context_features import IfvgContextObserverSeed
    from .context_records import IfvgContextEvent
    from strategy_core.structures.equal_levels import (
        EqualLevelPoolLifecycleEvent,
        EqualLevelSweepLink,
    )
    from strategy_core.structures.market_structure import ConfirmedSwingEvidence

__all__ = [
    "ContextReplayTape",
    "ContextPerformanceTrace",
    "DayOrchestrator",
    "IfvgContextDayResult",
    "IfvgDayResult",
    "run_day",
]

LevelsFor = Callable[[datetime], tuple[Level, ...]]


def _no_levels(_ts: datetime) -> tuple[Level, ...]:
    return ()


def _parse_doc_sessions(
    doc_sessions: Mapping[str, tuple[str, str]],
) -> tuple[tuple[str, time, time], ...]:
    parsed = []
    for name, (start_s, end_s) in doc_sessions.items():
        sh, sm = start_s.split(":")
        eh, em = end_s.split(":")
        parsed.append((name, time(int(sh), int(sm)), time(int(eh), int(em))))
    return tuple(parsed)


def _runtime_scheme(section_scheme) -> RuntimeSessionScheme:
    closed = section_scheme.closed_window
    return RuntimeSessionScheme(
        timezone=section_scheme.timezone,
        trading_day_boundary=time.fromisoformat(
            section_scheme.trading_day_boundary
        ),
        sessions={
            name: SessionWindow(
                time.fromisoformat(window.start),
                time.fromisoformat(window.end),
                crosses_midnight=window.crosses_midnight,
            )
            for name, window in section_scheme.sessions.items()
        },
        closed_window=(
            (
                time.fromisoformat(closed.start),
                time.fromisoformat(closed.end),
            )
            if closed is not None
            else None
        ),
    )


@dataclass(frozen=True, slots=True)
class IfvgDayResult:
    emissions: tuple[IfvgEmission, ...]
    end_seed: IfvgDaySeed
    funnel: DayFunnelRecord
    #: FSM audit channel (opt-in; empty when ``audit_capture_mode="disabled"``).
    #: Never hashed anywhere; tape playback regenerates it identically because
    #: the core reducer runs live under playback.
    audit_emissions: tuple[IfvgEmission, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextPerformanceTrace:
    completed_step_ns: tuple[int, ...]
    observer_step_ns: tuple[int, ...]
    multi_timeframe_callback_ns: tuple[int, ...]
    observer_advance_ns: tuple[int, ...] = ()
    event_capture_ns: tuple[int, ...] = ()
    seed_restore_ns: tuple[int, ...] = ()
    seed_snapshot_ns: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class IfvgContextDayResult:
    """Generation-3 wrapper; the nested v2 result remains structurally unchanged."""

    core: IfvgDayResult
    context_events: tuple[IfvgContextEvent, ...]
    confirmed_swings: tuple[ConfirmedSwingEvidence, ...]
    pool_lifecycle_events: tuple[EqualLevelPoolLifecycleEvent, ...]
    sweep_link_events: tuple[EqualLevelSweepLink, ...]
    end_context_seed: IfvgContextObserverSeed
    performance_trace: ContextPerformanceTrace

    @property
    def emissions(self) -> tuple[IfvgEmission, ...]:
        return self.core.emissions

    @property
    def end_seed(self) -> IfvgDaySeed:
        return self.core.end_seed

    @property
    def funnel(self) -> DayFunnelRecord:
        return self.core.funnel


@dataclass(frozen=True, slots=True)
class _ContextReplayEntry:
    section: IfvgSmcSection
    tick_size: float
    context_config: ContextFeatureConfig
    context_schedule_hash: str
    context_source_coverage_hash: str
    context_symbol: str
    strategy_core_commit: str
    strategy_core_source_tree_hash: str
    bars_by_tf: tuple[tuple[int, tuple[Bar, ...]], ...]
    incoming_context_seed: IfvgContextObserverSeed | None
    step_emissions: tuple[tuple[IfvgEmission, ...], ...]
    multi_timeframe_steps: tuple[bool, ...]
    tail_emissions: tuple[IfvgEmission, ...]
    core_end_seed: IfvgDaySeed
    context_events: tuple[IfvgContextEvent, ...]
    confirmed_swings: tuple[ConfirmedSwingEvidence, ...]
    pool_lifecycle_events: tuple[EqualLevelPoolLifecycleEvent, ...]
    sweep_link_events: tuple[EqualLevelSweepLink, ...]
    end_context_seed: IfvgContextObserverSeed


class ContextReplayTape:
    """Ephemeral acceleration for repeated replay of one preloaded source chain.

    The first visit to a trading day runs the normal observer and records its exact
    inputs and outputs. A later visit is accepted only when it reuses the same frozen
    bars and incoming context seed; every reducer emission is then checked while the
    raw core replay still runs. The tape is deliberately opt-in and process-local, so
    live/plugin consumers cannot enter this path.
    """

    def __init__(self) -> None:
        self._entries: dict[date, _ContextReplayEntry] = {}

    @staticmethod
    def _bars_by_tf(
        bars_by_tf: Mapping[int, Sequence[Bar]],
    ) -> tuple[tuple[int, tuple[Bar, ...]], ...]:
        return tuple(
            (timeframe, tuple(bars_by_tf[timeframe]))
            for timeframe in sorted(bars_by_tf)
        )

    def playback_entry(
        self,
        trading_day: date,
        *,
        bars_by_tf: Mapping[int, Sequence[Bar]],
        section: IfvgSmcSection,
        tick_size: float,
        context_config: ContextFeatureConfig,
        context_seed: IfvgContextObserverSeed | None,
        context_schedule: ExchangeMinuteSchedule,
        context_source_coverage: ContextSourceCoverage,
        context_symbol: str,
        strategy_core_commit: str,
        strategy_core_source_tree_hash: str,
    ) -> _ContextReplayEntry | None:
        entry = self._entries.get(trading_day)
        if entry is None:
            return None
        expected = (
            entry.section,
            entry.tick_size,
            entry.context_config,
            entry.context_schedule_hash,
            entry.context_source_coverage_hash,
            entry.context_symbol,
            entry.strategy_core_commit,
            entry.strategy_core_source_tree_hash,
            entry.bars_by_tf,
        )
        observed = (
            section,
            tick_size,
            context_config,
            context_schedule.content_hash,
            context_source_coverage.content_hash,
            context_symbol,
            strategy_core_commit,
            strategy_core_source_tree_hash,
            self._bars_by_tf(bars_by_tf),
        )
        if observed != expected:
            raise ValueError(
                f"context replay tape input drifted for {trading_day.isoformat()}"
            )
        if context_seed is not entry.incoming_context_seed:
            raise ValueError(
                f"context replay tape seed chain drifted for {trading_day.isoformat()}"
            )
        return entry

    def record(
        self,
        trading_day: date,
        *,
        bars_by_tf: Mapping[int, Sequence[Bar]],
        section: IfvgSmcSection,
        tick_size: float,
        context_config: ContextFeatureConfig,
        context_seed: IfvgContextObserverSeed | None,
        context_schedule: ExchangeMinuteSchedule,
        context_source_coverage: ContextSourceCoverage,
        context_symbol: str,
        strategy_core_commit: str,
        strategy_core_source_tree_hash: str,
        step_emissions: Sequence[tuple[IfvgEmission, ...]],
        multi_timeframe_steps: Sequence[bool],
        tail_emissions: Sequence[IfvgEmission],
        result: IfvgContextDayResult,
    ) -> None:
        if trading_day in self._entries:
            raise ValueError(
                f"context replay tape refuses overwrite for {trading_day.isoformat()}"
            )
        self._entries[trading_day] = _ContextReplayEntry(
            section=section,
            tick_size=tick_size,
            context_config=context_config,
            context_schedule_hash=context_schedule.content_hash,
            context_source_coverage_hash=context_source_coverage.content_hash,
            context_symbol=context_symbol,
            strategy_core_commit=strategy_core_commit,
            strategy_core_source_tree_hash=strategy_core_source_tree_hash,
            bars_by_tf=self._bars_by_tf(bars_by_tf),
            incoming_context_seed=context_seed,
            step_emissions=tuple(step_emissions),
            multi_timeframe_steps=tuple(multi_timeframe_steps),
            tail_emissions=tuple(tail_emissions),
            core_end_seed=result.end_seed,
            context_events=result.context_events,
            confirmed_swings=result.confirmed_swings,
            pool_lifecycle_events=result.pool_lifecycle_events,
            sweep_link_events=result.sweep_link_events,
            end_context_seed=result.end_context_seed,
        )


class DayOrchestrator:
    """Deterministic wiring around one :class:`IfvgReducer` (any number of days)."""

    def __init__(
        self,
        *,
        section: IfvgSmcSection,
        seed: IfvgDaySeed | None,
        tick_size: float = DEFAULT_TICK_SIZE,
        levels_for: LevelsFor = _no_levels,
        context_config: ContextFeatureConfig | None = None,
        context_seed: IfvgContextObserverSeed | None = None,
        context_schedule: ExchangeMinuteSchedule = CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
        context_source_coverage: ContextSourceCoverage = DEFAULT_CONTEXT_SOURCE_COVERAGE,
        context_symbol: str = "NQ",
        strategy_core_commit: str = "0" * 40,
        strategy_core_source_tree_hash: str = "0" * 64,
        audit_capture_mode: str = "disabled",
    ) -> None:
        self._section = section
        self._tick = tick_size
        self._levels_for = levels_for
        self._audit_capture_mode = audit_capture_mode
        self._audit_enabled = audit_capture_mode != "disabled"
        self._audit_emissions: list[IfvgEmission] = []
        self._profile_hash = ifvg_profile_hash(section)
        self._cfg = IfvgReducerConfig.from_section(
            section,
            tick_size=tick_size,
            strategy_id=IFVG_STRATEGY_ID,
            strategy_version=IFVG_STRATEGY_VERSION,
        )
        self._tfs = section.timeframe_seconds()
        self._htf_set = set(self._cfg.htf_tf_seconds)
        self._doc_sessions = _parse_doc_sessions(section.doc_sessions)
        self._runtime_session_scheme = _runtime_scheme(section.session_scheme)
        self._et = ZoneInfo(section.session_scheme.timezone)

        self._detectors: dict[int, FvgDetector] = {}
        self._registries: dict[int, FvgRegistry] = {}
        if seed is not None:
            if seed.schema_version != IFVG_SEED_SCHEMA_VERSION:
                raise ValueError(
                    f"IfvgDaySeed schema {seed.schema_version} != "
                    f"supported {IFVG_SEED_SCHEMA_VERSION}"
                )
            if seed.profile_hash != self._profile_hash:
                raise ValueError(
                    "day seed profile_hash does not match the active section "
                    f"({seed.profile_hash[:12]}... != {self._profile_hash[:12]}...)"
                )
            by_tf = {snap.timeframe_seconds: snap for snap in seed.registries}
            for tf in self._tfs:
                snap = by_tf.get(tf)
                if snap is not None:
                    self._registries[tf] = FvgRegistry.from_snapshot(snap)
                    self._detectors[tf] = FvgDetector.from_tail(
                        tf, snap.detector_tail, min_gap_ticks=section.min_gap_ticks_capture
                    )
            self._swings = SwingTracker.from_snapshot(seed.swings)
            self._reducer = (
                IfvgReducer.from_snapshot(
                    seed.reducer, self._cfg, audit_capture_mode=audit_capture_mode
                )
                if seed.reducer is not None
                else IfvgReducer(self._cfg, audit_capture_mode=audit_capture_mode)
            )
        else:
            self._swings = SwingTracker(
                strength=section.swing_strength_bars, max_kept=section.swing_pool_max
            )
            self._reducer = IfvgReducer(self._cfg, audit_capture_mode=audit_capture_mode)
        for tf in self._tfs:
            if tf not in self._detectors:
                self._detectors[tf] = FvgDetector(
                    tf, min_gap_ticks=section.min_gap_ticks_capture
                )
                self._registries[tf] = FvgRegistry(
                    timeframe_seconds=tf,
                    max_live=(
                        section.ltf_registry_max_live if tf not in self._htf_set else None
                    ),
                    max_age_days=(
                        section.htf_registry_max_age_days if tf in self._htf_set else None
                    ),
                )
        #: Higher-TF bars pushed but not yet delivered to a 1m step (per tf FIFO).
        self._pending: dict[int, list[Bar]] = {tf: [] for tf in self._tfs if tf != 60}
        self._last_1m_close: datetime | None = None
        self._last_1m_bar: Bar | None = None
        self._last_step_had_multi_timeframe = False
        self._context = None
        self._context_events: list[IfvgContextEvent] = []
        self._context_confirmed_swings: list[ConfirmedSwingEvidence] = []
        self._context_pool_lifecycle: list[EqualLevelPoolLifecycleEvent] = []
        self._context_sweep_links: list[EqualLevelSweepLink] = []
        self._context_completed_step_ns: list[int] = []
        self._context_observer_step_ns: list[int] = []
        self._context_multi_tf_ns: list[int] = []
        self._context_advance_ns: list[int] = []
        self._context_capture_ns: list[int] = []
        self._context_seed_restore_ns: list[int] = []
        self._context_seed_snapshot_ns: list[int] = []
        if context_seed is not None and context_config is None:
            raise ValueError("context_seed requires context_config")
        if context_config is not None:
            from .context_features import IfvgContextObserver

            required_seconds = {
                context_config.seconds_for(item)
                for item in context_config.normalized_timeframes
            }
            if not required_seconds.issubset(set(self._tfs)):
                raise ValueError("context timeframes are not declared by the IFVG section")
            restore_started_ns = perf_counter_ns()
            self._context = IfvgContextObserver(
                config=context_config,
                scheme=self._runtime_session_scheme,
                schedule=context_schedule,
                source_coverage=context_source_coverage,
                symbol=context_symbol,
                tick_size=str(tick_size),
                strategy_core_commit=strategy_core_commit,
                strategy_core_source_tree_hash=strategy_core_source_tree_hash,
                seed=context_seed,
            )
            if context_seed is not None:
                self._context_seed_restore_ns.append(
                    perf_counter_ns() - restore_started_ns
                )

    # ── bar feeds ────────────────────────────────────────────────────────────
    def on_higher_tf_bar(self, bar: Bar) -> None:
        if bar.timeframe_ticks == 60 or bar.timeframe_ticks not in self._pending:
            raise ValueError(f"not a configured higher timeframe: {bar.timeframe_ticks}s")
        queue = self._pending[bar.timeframe_ticks]
        queue.append(bar)
        if len(queue) > 1:
            previous = queue[-2]
            if (bar.availability_ts_utc, bar.bar_id) < (
                previous.availability_ts_utc,
                previous.bar_id,
            ):
                queue.sort(key=lambda item: (item.availability_ts_utc, item.bar_id))

    def on_decision_bar(self, bar_1m: Bar) -> tuple[IfvgEmission, ...]:
        step_started_ns = perf_counter_ns() if self._context is not None else 0
        observer_ns = 0
        if bar_1m.timeframe_ticks != 60:
            raise ValueError(f"decision bar must be 60s (got {bar_1m.timeframe_ticks}s)")
        self._last_1m_close = bar_1m.availability_ts_utc
        self._last_1m_bar = bar_1m

        tf_bars_closed: dict[int, Bar] = {}
        due_htf_bars: list[Bar] = []
        tf_bar_close_counts: dict[int, int] = {}
        new_fvgs: dict[int, list] = {}
        # 1. deliver due higher-TF bars, descending timeframe at a shared instant.
        for tf in sorted(self._pending, reverse=True):
            queue = self._pending[tf]
            while (
                queue
                and queue[0].availability_ts_utc
                <= bar_1m.availability_ts_utc
            ):
                tf_bar = queue.pop(0)
                due_htf_bars.append(tf_bar)
                tf_bars_closed[tf] = tf_bar
                tf_bar_close_counts[tf] = tf_bar_close_counts.get(tf, 0) + 1
                gap = self._detectors[tf].on_bar_closed(tf_bar)
                if gap is not None:
                    new_fvgs.setdefault(tf, []).append(gap)
        # 2. the 1m bar's own gap.
        gap_1m = self._detectors[60].on_bar_closed(bar_1m)
        if gap_1m is not None:
            new_fvgs.setdefault(60, []).append(gap_1m)
        self._last_step_had_multi_timeframe = bool(due_htf_bars)
        if self._context is not None and len(due_htf_bars) > 1:
            due_keys = [
                (
                    item.availability_ts_utc,
                    -item.timeframe_ticks,
                    item.bar_id,
                )
                for item in due_htf_bars
            ]
            if any(
                current < previous
                for previous, current in zip(due_keys, due_keys[1:], strict=False)
            ):
                due_htf_bars.sort(
                    key=lambda item: (
                        item.availability_ts_utc,
                        -item.timeframe_ticks,
                        item.bar_id,
                    )
                )
        normalized_new_fvgs = {
            tf: tuple(gaps) for tf, gaps in new_fvgs.items()
        }
        # 3. fill maintenance (before the reducer sees the live views).
        fill_events: list[FvgFillEvent] = []
        for tf in self._tfs:
            fill_events.extend(self._registries[tf].on_execution_bar(bar_1m))
        if self._audit_enabled:
            # Observed BEFORE the step so linkage reflects the entering state.
            self._reducer.audit_observe_fill_events(tuple(fill_events), bar_1m)
        # 4. swings confirm on this bar.
        self._swings.on_bar_closed(bar_1m)
        if self._context is not None and bar_1m.is_complete:
            context_started_ns = perf_counter_ns()
            self._context.advance_step(
                tuple(due_htf_bars),
                bar_1m,
                normalized_new_fvgs,
            )
            advance_ns = perf_counter_ns() - context_started_ns
            observer_ns += advance_ns
            self._context_advance_ns.append(advance_ns)
            if due_htf_bars:
                self._context_multi_tf_ns.append(advance_ns)
        htf_live = tuple(
            state for tf in self._cfg.htf_tf_seconds for state in self._registries[tf].live()
        )
        # 5. reduce.
        step = IfvgStepInput(
            bar_1m=bar_1m,
            tf_bars_closed=tf_bars_closed,
            new_fvgs=normalized_new_fvgs,
            fill_events=tuple(fill_events),
            htf_live=htf_live,
            levels=self._levels_for(bar_1m.availability_ts_utc),
            recent_swing_highs=self._swings.recent(
                side=Side.HIGH,
                before=bar_1m.availability_ts_utc,
                limit=self._section.swing_pool_max,
            ),
            recent_swing_lows=self._swings.recent(
                side=Side.LOW,
                before=bar_1m.availability_ts_utc,
                limit=self._section.swing_pool_max,
            ),
            session_engine=classify_session(
                bar_1m.availability_ts_utc, self._runtime_session_scheme
            ).session,
            session_doc=self._doc_session(bar_1m.availability_ts_utc),
            tf_bar_close_counts=tf_bar_close_counts,
        )
        emissions = self._reducer.step(step)
        # 6. intake — register the new gaps (usable from the next bar).
        intake_events: list[FvgFillEvent] = []
        for tf, gaps in new_fvgs.items():
            for gap in gaps:
                evictions = self._registries[tf].add(gap)
                if self._audit_enabled and evictions:
                    intake_events.extend(evictions)
        if self._audit_enabled:
            # Per-step drain: the reducer's audit buffer never spans a step
            # boundary, so any interruption or seed/resume point sees it empty.
            if intake_events:
                self._reducer.audit_observe_intake_events(
                    tuple(intake_events), bar_1m
                )
            self._audit_emissions.extend(self._reducer.drain_audit())
        if self._context is not None and bar_1m.is_complete:
            context_started_ns = perf_counter_ns()
            self._context_events.extend(self._context.capture(emissions))
            self._context_confirmed_swings.extend(
                self._context.drain_confirmed_swings()
            )
            self._context_pool_lifecycle.extend(
                self._context.drain_lifecycle_records()
            )
            self._context_sweep_links.extend(
                self._context.drain_sweep_link_records()
            )
            capture_ns = perf_counter_ns() - context_started_ns
            observer_ns += capture_ns
            self._context_capture_ns.append(capture_ns)
            self._context_observer_step_ns.append(observer_ns)
            self._context_completed_step_ns.append(perf_counter_ns() - step_started_ns)
        return emissions

    @property
    def last_step_had_multi_timeframe(self) -> bool:
        return self._last_step_had_multi_timeframe

    # ── day boundary ─────────────────────────────────────────────────────────
    def finalize_day(self, trading_day: date) -> tuple[IfvgEmission, ...]:
        if self._last_1m_close is None:
            return ()
        return self._reducer.finalize_day(
            last_ts_utc=self._last_1m_close, trading_day=trading_day
        )

    def finalize_dataset(self, trading_day: date) -> tuple[IfvgEmission, ...]:
        if self._last_1m_close is None:
            return ()
        out = self._reducer.finalize_dataset(
            last_ts_utc=self._last_1m_close,
            trading_day=trading_day,
        )
        if self._audit_enabled:
            self._audit_emissions.extend(self._reducer.drain_audit())
        return out

    def drain_audit_emissions(self) -> tuple[IfvgEmission, ...]:
        """All audit emissions accumulated since the last drain (already
        per-step drained from the reducer, so this is complete at any
        boundary). Empty when the channel is disabled."""
        emissions = tuple(self._audit_emissions)
        self._audit_emissions.clear()
        return emissions

    def day_funnel(self, trading_day: date, ts_utc: datetime) -> DayFunnelRecord:
        return DayFunnelRecord(
            envelope=RecordEnvelope(
                schema_version=IFVG_RECORD_SCHEMA_VERSION,
                strategy_id=IFVG_STRATEGY_ID,
                strategy_version=IFVG_STRATEGY_VERSION,
                profile_hash=self._profile_hash,
                trading_day=trading_day,
                ts_utc=ts_utc,
                setup_id="",
                profile_name=self._cfg.profile_name,
                qualification_mode=self._cfg.qualification_mode,
                section_config_hash=self._profile_hash,
                entry_family=self._cfg.entry_family,
                label_family=self._cfg.label_family,
                entry_session="none",
                anchor_policy=self._cfg.anchor_policy,
                resolver_policy=self._cfg.resolver_policy,
                causality_parent=self._cfg.causality_parent,
                causality_opposing=self._cfg.causality_opposing,
                causality_entry=self._cfg.causality_entry,
                timeout_policy=self._cfg.timeout_policy,
            ),
            counters=self._reducer.funnel_counters(),
        )

    def reset_funnel(self) -> None:
        self._reducer.reset_funnel()

    def end_seed(self, source_day: date) -> IfvgDaySeed:
        return IfvgDaySeed(
            schema_version=IFVG_SEED_SCHEMA_VERSION,
            profile_hash=self._profile_hash,
            source_day=source_day,
            registries=tuple(
                self._registries[tf].snapshot(
                    detector_tail=self._detectors[tf].snapshot_tail(),
                    min_gap_ticks=self._section.min_gap_ticks_capture,
                )
                for tf in self._tfs
            ),
            swings=self._swings.snapshot(),
            reducer=self._reducer.snapshot(),
        )

    def drain_context_events(self) -> tuple[IfvgContextEvent, ...]:
        out = tuple(self._context_events)
        self._context_events.clear()
        return out

    def end_context_seed(self) -> IfvgContextObserverSeed:
        if self._context is None:
            raise RuntimeError("context observer is disabled")
        started_ns = perf_counter_ns()
        seed = self._context.snapshot()
        self._context_seed_snapshot_ns.append(perf_counter_ns() - started_ns)
        return seed

    def drain_context_pool_lifecycle(self) -> tuple[EqualLevelPoolLifecycleEvent, ...]:
        out = tuple(self._context_pool_lifecycle)
        self._context_pool_lifecycle.clear()
        return out

    def drain_context_confirmed_swings(self) -> tuple[ConfirmedSwingEvidence, ...]:
        out = tuple(self._context_confirmed_swings)
        self._context_confirmed_swings.clear()
        return out

    def drain_context_sweep_links(self) -> tuple[EqualLevelSweepLink, ...]:
        out = tuple(self._context_sweep_links)
        self._context_sweep_links.clear()
        return out

    def drain_context_performance_trace(self) -> ContextPerformanceTrace:
        trace = ContextPerformanceTrace(
            completed_step_ns=tuple(self._context_completed_step_ns),
            observer_step_ns=tuple(self._context_observer_step_ns),
            multi_timeframe_callback_ns=tuple(self._context_multi_tf_ns),
            observer_advance_ns=tuple(self._context_advance_ns),
            event_capture_ns=tuple(self._context_capture_ns),
            seed_restore_ns=tuple(self._context_seed_restore_ns),
            seed_snapshot_ns=tuple(self._context_seed_snapshot_ns),
        )
        self._context_completed_step_ns.clear()
        self._context_observer_step_ns.clear()
        self._context_multi_tf_ns.clear()
        self._context_advance_ns.clear()
        self._context_capture_ns.clear()
        self._context_seed_restore_ns.clear()
        self._context_seed_snapshot_ns.clear()
        return trace

    # ── stamps ───────────────────────────────────────────────────────────────
    def _doc_session(self, ts_utc: datetime) -> str:
        local = ts_utc.astimezone(self._et).time()
        for name, start, end in self._doc_sessions:
            if start <= end:
                if start <= local < end:
                    return name
            elif local >= start or local < end:  # crosses midnight
                return name
        return "none"


def run_day(
    bars_by_tf: Mapping[int, Sequence[Bar]],
    *,
    section: IfvgSmcSection,
    seed: IfvgDaySeed | None,
    trading_day: date,
    tick_size: float = DEFAULT_TICK_SIZE,
    levels_for: LevelsFor = _no_levels,
    dataset_exhausted: bool = False,
    context_config: ContextFeatureConfig | None = None,
    context_seed: IfvgContextObserverSeed | None = None,
    context_schedule: ExchangeMinuteSchedule = CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
    context_source_coverage: ContextSourceCoverage = DEFAULT_CONTEXT_SOURCE_COVERAGE,
    context_symbol: str = "NQ",
    strategy_core_commit: str = "0" * 40,
    strategy_core_source_tree_hash: str = "0" * 64,
    context_replay_tape: ContextReplayTape | None = None,
    audit_capture_mode: str = "disabled",
) -> IfvgDayResult | IfvgContextDayResult:
    """One trading day through the orchestrator — pure over its inputs.

    ``bars_by_tf`` maps interval seconds to that timeframe's bars for the day
    (missing timeframes are simply absent that day). Chained calls
    (``seed = previous.end_seed``) are emission-identical to one continuous
    orchestrator with a finalize at each roll — the cache-trust theorem,
    pinned by ``tests/test_ifvg_replay_parity.py``.
    """
    tape_restore_started_ns = perf_counter_ns()
    tape_entry = None
    if context_replay_tape is not None:
        if context_config is None:
            raise ValueError("context replay tape requires context_config")
        tape_entry = context_replay_tape.playback_entry(
            trading_day,
            bars_by_tf=bars_by_tf,
            section=section,
            tick_size=tick_size,
            context_config=context_config,
            context_seed=context_seed,
            context_schedule=context_schedule,
            context_source_coverage=context_source_coverage,
            context_symbol=context_symbol,
            strategy_core_commit=strategy_core_commit,
            strategy_core_source_tree_hash=strategy_core_source_tree_hash,
        )
    tape_restore_ns = perf_counter_ns() - tape_restore_started_ns
    tape_playback = tape_entry is not None
    orch = DayOrchestrator(
        section=section,
        seed=seed,
        tick_size=tick_size,
        levels_for=levels_for,
        context_config=None if tape_playback else context_config,
        context_seed=None if tape_playback else context_seed,
        context_schedule=context_schedule,
        context_source_coverage=context_source_coverage,
        context_symbol=context_symbol,
        strategy_core_commit=strategy_core_commit,
        strategy_core_source_tree_hash=strategy_core_source_tree_hash,
        audit_capture_mode=audit_capture_mode,
    )
    orch.reset_funnel()
    for tf, bars in bars_by_tf.items():
        if tf == 60:
            continue
        for bar in bars:
            orch.on_higher_tf_bar(bar)
    emissions: list[IfvgEmission] = []
    step_emissions: list[tuple[IfvgEmission, ...]] = []
    multi_timeframe_steps: list[bool] = []
    playback_completed_ns: list[int] = []
    playback_observer_ns: list[int] = []
    playback_multi_ns: list[int] = []
    last_ts: datetime | None = None
    for step_index, bar in enumerate(bars_by_tf.get(60, ())):
        step_started_ns = perf_counter_ns() if tape_playback else 0
        emitted = orch.on_decision_bar(bar)
        if tape_playback:
            observer_started_ns = perf_counter_ns()
            if step_index >= len(tape_entry.step_emissions):
                raise ValueError("context replay tape has fewer steps than the source")
            if emitted != tape_entry.step_emissions[step_index]:
                raise ValueError(
                    "context replay tape core emissions drifted at "
                    f"{trading_day.isoformat()} step {step_index}"
                )
            observer_ns = perf_counter_ns() - observer_started_ns
            playback_observer_ns.append(observer_ns)
            if tape_entry.multi_timeframe_steps[step_index]:
                playback_multi_ns.append(observer_ns)
            playback_completed_ns.append(perf_counter_ns() - step_started_ns)
        elif context_replay_tape is not None and context_config is not None:
            step_emissions.append(emitted)
            multi_timeframe_steps.append(orch.last_step_had_multi_timeframe)
        emissions.extend(emitted)
        last_ts = bar.availability_ts_utc
    if tape_playback and len(tape_entry.step_emissions) != len(playback_observer_ns):
        raise ValueError("context replay tape has more steps than the source")
    tail_start = len(emissions)
    emissions.extend(orch.finalize_day(trading_day))
    if dataset_exhausted:
        emissions.extend(orch.finalize_dataset(trading_day))
    funnel = orch.day_funnel(
        trading_day,
        last_ts if last_ts is not None else datetime(2000, 1, 1, tzinfo=UTC),
    )
    emissions.append(IfvgEmission(kind="funnel", record=funnel))
    core = IfvgDayResult(
        emissions=tuple(emissions),
        end_seed=orch.end_seed(trading_day),
        funnel=funnel,
        audit_emissions=orch.drain_audit_emissions(),
    )
    if context_config is None:
        return core
    if tape_playback:
        snapshot_started_ns = perf_counter_ns()
        if tuple(emissions[tail_start:]) != tape_entry.tail_emissions:
            raise ValueError("context replay tape final emissions drifted")
        if core.end_seed != tape_entry.core_end_seed:
            raise ValueError("context replay tape core end seed drifted")
        snapshot_ns = perf_counter_ns() - snapshot_started_ns
        return IfvgContextDayResult(
            core=core,
            context_events=tape_entry.context_events,
            confirmed_swings=tape_entry.confirmed_swings,
            pool_lifecycle_events=tape_entry.pool_lifecycle_events,
            sweep_link_events=tape_entry.sweep_link_events,
            end_context_seed=tape_entry.end_context_seed,
            performance_trace=ContextPerformanceTrace(
                completed_step_ns=tuple(playback_completed_ns),
                observer_step_ns=tuple(playback_observer_ns),
                multi_timeframe_callback_ns=tuple(playback_multi_ns),
                observer_advance_ns=tuple(0 for _ in playback_observer_ns),
                event_capture_ns=tuple(playback_observer_ns),
                seed_restore_ns=(tape_restore_ns,),
                seed_snapshot_ns=(snapshot_ns,),
            ),
        )
    result = IfvgContextDayResult(
        core=core,
        context_events=orch.drain_context_events(),
        confirmed_swings=orch.drain_context_confirmed_swings(),
        pool_lifecycle_events=orch.drain_context_pool_lifecycle(),
        sweep_link_events=orch.drain_context_sweep_links(),
        end_context_seed=orch.end_context_seed(),
        performance_trace=orch.drain_context_performance_trace(),
    )
    if context_replay_tape is not None:
        context_replay_tape.record(
            trading_day,
            bars_by_tf=bars_by_tf,
            section=section,
            tick_size=tick_size,
            context_config=context_config,
            context_seed=context_seed,
            context_schedule=context_schedule,
            context_source_coverage=context_source_coverage,
            context_symbol=context_symbol,
            strategy_core_commit=strategy_core_commit,
            strategy_core_source_tree_hash=strategy_core_source_tree_hash,
            step_emissions=step_emissions,
            multi_timeframe_steps=multi_timeframe_steps,
            tail_emissions=emissions[tail_start:],
            result=result,
        )
    return result
