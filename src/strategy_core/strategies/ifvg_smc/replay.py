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
from typing import Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from strategy_core.constants import DEFAULT_TICK_SIZE, RESEARCH_SESSION_SCHEME
from strategy_core.decisions.sessions import classify_session
from strategy_core.structures.fvg import FvgDetector, FvgFillEvent, FvgRegistry
from strategy_core.structures.swings import SwingTracker
from strategy_core.types import Bar, Level, Side

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

__all__ = ["DayOrchestrator", "IfvgDayResult", "run_day"]

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


@dataclass(frozen=True, slots=True)
class IfvgDayResult:
    emissions: tuple[IfvgEmission, ...]
    end_seed: IfvgDaySeed
    funnel: DayFunnelRecord


class DayOrchestrator:
    """Deterministic wiring around one :class:`IfvgReducer` (any number of days)."""

    def __init__(
        self,
        *,
        section: IfvgSmcSection,
        seed: IfvgDaySeed | None,
        tick_size: float = DEFAULT_TICK_SIZE,
        levels_for: LevelsFor = _no_levels,
    ) -> None:
        self._section = section
        self._tick = tick_size
        self._levels_for = levels_for
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
        self._et = ZoneInfo(RESEARCH_SESSION_SCHEME.timezone)

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
                IfvgReducer.from_snapshot(seed.reducer, self._cfg)
                if seed.reducer is not None
                else IfvgReducer(self._cfg)
            )
        else:
            self._swings = SwingTracker(
                strength=section.swing_strength_bars, max_kept=section.swing_pool_max
            )
            self._reducer = IfvgReducer(self._cfg)
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

    # ── bar feeds ────────────────────────────────────────────────────────────
    def on_higher_tf_bar(self, bar: Bar) -> None:
        if bar.timeframe_ticks == 60 or bar.timeframe_ticks not in self._pending:
            raise ValueError(f"not a configured higher timeframe: {bar.timeframe_ticks}s")
        self._pending[bar.timeframe_ticks].append(bar)

    def on_decision_bar(self, bar_1m: Bar) -> tuple[IfvgEmission, ...]:
        if bar_1m.timeframe_ticks != 60:
            raise ValueError(f"decision bar must be 60s (got {bar_1m.timeframe_ticks}s)")
        self._last_1m_close = bar_1m.close_ts_utc

        tf_bars_closed: dict[int, Bar] = {}
        new_fvgs: dict[int, list] = {}
        # 1. deliver due higher-TF bars, descending timeframe at a shared instant.
        for tf in sorted(self._pending, reverse=True):
            queue = self._pending[tf]
            while queue and queue[0].close_ts_utc <= bar_1m.close_ts_utc:
                tf_bar = queue.pop(0)
                tf_bars_closed[tf] = tf_bar
                gap = self._detectors[tf].on_bar_closed(tf_bar)
                if gap is not None:
                    new_fvgs.setdefault(tf, []).append(gap)
        # 2. the 1m bar's own gap.
        gap_1m = self._detectors[60].on_bar_closed(bar_1m)
        if gap_1m is not None:
            new_fvgs.setdefault(60, []).append(gap_1m)
        # 3. fill maintenance (before the reducer sees the live views).
        fill_events: list[FvgFillEvent] = []
        for tf in self._tfs:
            fill_events.extend(self._registries[tf].on_execution_bar(bar_1m))
        # 4. swings confirm on this bar.
        self._swings.on_bar_closed(bar_1m)
        htf_live = tuple(
            state for tf in self._cfg.htf_tf_seconds for state in self._registries[tf].live()
        )
        # 5. reduce.
        step = IfvgStepInput(
            bar_1m=bar_1m,
            tf_bars_closed=tf_bars_closed,
            new_fvgs={tf: tuple(gaps) for tf, gaps in new_fvgs.items()},
            fill_events=tuple(fill_events),
            htf_live=htf_live,
            levels=self._levels_for(bar_1m.close_ts_utc),
            recent_swing_highs=self._swings.recent(
                side=Side.HIGH, before=bar_1m.close_ts_utc, limit=self._section.swing_pool_max
            ),
            recent_swing_lows=self._swings.recent(
                side=Side.LOW, before=bar_1m.close_ts_utc, limit=self._section.swing_pool_max
            ),
            session_engine=classify_session(bar_1m.close_ts_utc, RESEARCH_SESSION_SCHEME).session,
            session_doc=self._doc_session(bar_1m.close_ts_utc),
        )
        emissions = self._reducer.step(step)
        # 6. intake — register the new gaps (usable from the next bar).
        for tf, gaps in new_fvgs.items():
            for gap in gaps:
                self._registries[tf].add(gap)
        return emissions

    # ── day boundary ─────────────────────────────────────────────────────────
    def finalize_day(self, trading_day: date) -> tuple[IfvgEmission, ...]:
        if self._last_1m_close is None:
            return ()
        return self._reducer.finalize_day(
            last_ts_utc=self._last_1m_close, trading_day=trading_day
        )

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
) -> IfvgDayResult:
    """One trading day through the orchestrator — pure over its inputs.

    ``bars_by_tf`` maps interval seconds to that timeframe's bars for the day
    (missing timeframes are simply absent that day). Chained calls
    (``seed = previous.end_seed``) are emission-identical to one continuous
    orchestrator with a finalize at each roll — the cache-trust theorem,
    pinned by ``tests/test_ifvg_replay_parity.py``.
    """
    orch = DayOrchestrator(
        section=section, seed=seed, tick_size=tick_size, levels_for=levels_for
    )
    orch.reset_funnel()
    for tf, bars in bars_by_tf.items():
        if tf == 60:
            continue
        for bar in bars:
            orch.on_higher_tf_bar(bar)
    emissions: list[IfvgEmission] = []
    last_ts: datetime | None = None
    for bar in bars_by_tf.get(60, ()):
        emissions.extend(orch.on_decision_bar(bar))
        last_ts = bar.close_ts_utc
    emissions.extend(orch.finalize_day(trading_day))
    funnel = orch.day_funnel(
        trading_day,
        last_ts if last_ts is not None else datetime(2000, 1, 1, tzinfo=UTC),
    )
    emissions.append(IfvgEmission(kind="funnel", record=funnel))
    return IfvgDayResult(
        emissions=tuple(emissions),
        end_seed=orch.end_seed(trading_day),
        funnel=funnel,
    )
