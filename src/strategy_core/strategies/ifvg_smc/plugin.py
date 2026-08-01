"""``@register``-ed protocol shell for ``ifvg_smc``.

Conformance + future live wiring. Offline research does NOT go through this
class — it drives :func:`~strategy_core.strategies.ifvg_smc.replay.run_day`
directly — but the plugin routes bars through the SAME
:class:`~strategy_core.strategies.ifvg_smc.replay.DayOrchestrator`, so the two
consumption shapes cannot drift.

Honest stubs, per the ratified rulings and today's platform reality:

* ``current_levels()`` / ``snapshot_zones()`` return ``()`` (Q-04-S: FVG boxes
  do not ride ``Zone``; live display is the future generic payload).
* ``feature_spec()`` is empty — the ML gate consumes tier-2 records offline,
  not the platform feature pipeline.
* ``StrategyStep`` returns are empty deltas: the runtime has no reader for
  ``setups``/``decisions`` today (runtime/state.py consumes only ``touches``).
  Research emissions are exposed through the additive ``drain_emissions()`` /
  ``day_snapshot()`` / ``load_day_seed()`` taps instead.
* Live multi-TF delivery (F1) does not exist yet: today's runtime routes only
  decision-timeframe TICK bars here, which this plugin ignores by design. When
  TIME delivery lands, ``on_bar_closed`` is already shaped for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from strategy_core.constants import (
    FLATTEN_TIME,
    LABEL_FORWARD_CUTOFF,
    NAN_POLICY,
    TIME_TF_SECONDS,
)
from strategy_core.runtime.levels import StrategyLevelState
from strategy_core.strategies.protocols import (
    BarSpec,
    EventTypeSpec,
    FeatureSpec,
    LabelPolicySpec,
    PlatformContext,
    StrategyStep,
)
from strategy_core.strategies.registry import register
from strategy_core.types import Bar, BarKind, Level, Quote, Trade, Zone

from .records import IfvgEmission
from .replay import DayOrchestrator, _runtime_scheme
from .context_config import ContextFeatureConfig
from .context_features import IfvgContextObserverSeed
from .section import (
    IFVG_STRATEGY_ID,
    IFVG_STRATEGY_VERSION,
    IfvgSmcSection,
    default_ifvg_smc_section,
)
from .state import IFVG_CONTEXT_SEED_CONTAINER_VERSION, IfvgDaySeed, IfvgDaySeedV3

__all__ = ["IfvgSmcPlugin", "RRelativeBarrier"]


@dataclass(frozen=True, slots=True)
class RRelativeBarrier:
    """DECLARATION-ONLY ``r_relative`` barrier (the mode's first producer).

    An r-relative pair is per-setup (SL = the manipulation swing, known only at
    entry), so entry-only price derivation is undefined by construction; the
    concrete pairs are resolved by ``labels.resolve_ifvg_outcome``. Contract
    emission/serving of this mode is a recorded non-goal this window.
    """

    r_multiple: float
    sl_anchor: str = "manipulation_swing"
    kind: str = "r_relative"

    def stop_price(self, entry_price: float, direction: str) -> float:
        raise NotImplementedError(
            "r_relative barriers are per-setup (manipulation swing); resolve via "
            "strategy_core.strategies.ifvg_smc.labels.resolve_ifvg_outcome"
        )

    def target_price(self, entry_price: float, direction: str) -> float:
        raise NotImplementedError(
            "r_relative barriers are per-setup (manipulation swing); resolve via "
            "strategy_core.strategies.ifvg_smc.labels.resolve_ifvg_outcome"
        )


@register
class IfvgSmcPlugin:
    strategy_id = IFVG_STRATEGY_ID
    strategy_version = IFVG_STRATEGY_VERSION
    SectionModel = IfvgSmcSection

    def __init__(
        self,
        *,
        context_config: ContextFeatureConfig | None = None,
        context_seed: IfvgContextObserverSeed | None = None,
        context_symbol: str = "NQ",
        strategy_core_commit: str = "0" * 40,
        strategy_core_source_tree_hash: str = "0" * 64,
    ) -> None:
        self._section: IfvgSmcSection | None = None
        self._orch: DayOrchestrator | None = None
        self._levels: StrategyLevelState | None = None
        self._emissions: list[IfvgEmission] = []
        self._static_levels: tuple[Level, ...] = ()
        self._tick: float = 0.25
        self._context_config = context_config
        self._initial_context_seed = context_seed
        self._context_symbol = context_symbol
        self._strategy_core_commit = strategy_core_commit
        self._strategy_core_source_tree_hash = strategy_core_source_tree_hash

    # ── lifecycle ────────────────────────────────────────────────────────────
    def configure(self, section: IfvgSmcSection, ctx: PlatformContext) -> None:
        self._section = section
        self._tick = ctx.tick_size
        self._levels = StrategyLevelState(
            scheme=_runtime_scheme(section.session_scheme),
            tick_size=ctx.tick_size,
            session_range_names=("asia", "london", "ny"),
            emit_prior_session_levels=("ny",),
        )
        self._levels.set_static_levels(self._static_levels)
        self._orch = DayOrchestrator(
            section=section,
            seed=None,
            tick_size=ctx.tick_size,
            levels_for=lambda _ts: self._levels.levels() if self._levels else (),
            context_config=self._context_config,
            context_seed=self._initial_context_seed,
            context_symbol=self._context_symbol,
            strategy_core_commit=self._strategy_core_commit,
            strategy_core_source_tree_hash=self._strategy_core_source_tree_hash,
        )
        self._initial_context_seed = None
        self._emissions = []

    def reset(self) -> None:
        if self._section is None:
            return
        if self._levels is not None:
            self._levels.reset()
        self._orch = DayOrchestrator(
            section=self._section,
            seed=None,
            tick_size=self._tick,
            levels_for=lambda _ts: self._levels.levels() if self._levels else (),
            context_config=self._context_config,
            context_symbol=self._context_symbol,
            strategy_core_commit=self._strategy_core_commit,
            strategy_core_source_tree_hash=self._strategy_core_source_tree_hash,
        )
        self._emissions = []

    def set_static_levels(self, levels: tuple[Level, ...]) -> None:
        self._static_levels = levels
        if self._levels is not None:
            self._levels.set_static_levels(levels)

    def load_prior_day_summary(self, trading_day: date, *, high_ticks: int, low_ticks: int) -> None:
        if self._levels is not None:
            self._levels.load_prior_day_summary(
                trading_day, high_ticks=high_ticks, low_ticks=low_ticks
            )

    # ── declarations ─────────────────────────────────────────────────────────
    @staticmethod
    def required_bars() -> tuple[BarSpec, ...]:
        return tuple(
            BarSpec(BarKind.TIME, seconds, label) for label, seconds in TIME_TF_SECONDS.items()
        )

    @staticmethod
    def decision_bar_label() -> str:
        return "1m"

    def feature_spec(self) -> FeatureSpec:
        return FeatureSpec(names=(), interaction_features=(), approach_features=(), nan_policy=NAN_POLICY)

    def label_policy(self) -> LabelPolicySpec:
        section = self._section if self._section is not None else default_ifvg_smc_section()
        return LabelPolicySpec(
            resolution="mae_first",
            barrier_mode="r_relative",
            barrier=RRelativeBarrier(r_multiple=section.tp_r_multiple),
            # confirmation_close entry: decision instant == entry instant. The
            # CONTRACT envelope's gt=0 constraint is a recorded non-goal; this
            # plugin-level spec is a plain dataclass and carries the truth.
            decision_offset_minutes=0,
            flatten_time=FLATTEN_TIME,
            forward_cutoff=LABEL_FORWARD_CUTOFF,
            no_resolution_dropped=False,
        )

    def emitted_event_types(self) -> tuple[EventTypeSpec, ...]:
        events = (
            EventTypeSpec(
                "ifvg.setup_lifecycle",
                ("setup_id", "lifecycle_event_id", "transition", "reason"),
            ),
            EventTypeSpec(
                "ifvg.entry_candidate",
                ("setup_id", "candidate_id", "entry_family", "block_reasons"),
            ),
            EventTypeSpec(
                "ifvg.eligible_decision",
                ("setup_id", "candidate_id", "decision_id"),
            ),
            EventTypeSpec(
                "ifvg.executed_trade",
                ("setup_id", "decision_id", "trade_id", "status"),
            ),
        )
        if self._context_config is None:
            return events
        return events + (
            EventTypeSpec(
                "strategy.context_feature",
                ("capture", "state", "structure_deltas", "displacement_windows", "sweep_links"),
            ),
        )

    # ── consumption ──────────────────────────────────────────────────────────
    def on_event(self, event: Trade | Quote, ctx: PlatformContext) -> tuple[Level, ...]:
        if isinstance(event, Trade) and self._levels is not None:
            self._levels.process_trade(event)
        return ()

    def on_bar_closed(self, bar: Bar, ctx: PlatformContext) -> StrategyStep:
        if self._orch is None or bar.kind is not BarKind.TIME:
            # Today's runtime routes only decision-TF TICK bars (F1 gap): inert.
            return StrategyStep()
        if bar.timeframe_ticks == 60:
            self._emissions.extend(self._orch.on_decision_bar(bar))
            context_events = self._orch.drain_context_events()
            # These append-only rows are an offline normalization surface.  The
            # live plugin transports transition events only, so discard its
            # auxiliary copies every step instead of retaining an unbounded log.
            self._orch.drain_context_confirmed_swings()
            self._orch.drain_context_pool_lifecycle()
            self._orch.drain_context_sweep_links()
            self._orch.drain_context_performance_trace()
            return StrategyStep(context_events=context_events)
        elif bar.timeframe_ticks in TIME_TF_SECONDS.values():
            self._orch.on_higher_tf_bar(bar)
        return StrategyStep()

    # ── readback (Q-04-S: FVG geometry does not ride Zone) ──────────────────
    def current_levels(self) -> tuple[Level, ...]:
        return ()

    def snapshot_zones(self, trading_day: date) -> tuple[Zone, ...]:
        return ()

    # ── research taps (additive, not protocol) ──────────────────────────────
    def drain_emissions(self) -> tuple[IfvgEmission, ...]:
        out = tuple(self._emissions)
        self._emissions = []
        return out

    def day_snapshot(self, source_day: date) -> IfvgDaySeed:
        if self._orch is None:
            raise RuntimeError("plugin not configured")
        return self._orch.end_seed(source_day)

    def load_day_seed(self, seed: IfvgDaySeed | IfvgDaySeedV3) -> None:
        if self._section is None:
            raise RuntimeError("plugin not configured")
        core_seed = seed.core if isinstance(seed, IfvgDaySeedV3) else seed
        context_seed = seed.context if isinstance(seed, IfvgDaySeedV3) else None
        if context_seed is not None and self._context_config is None:
            raise ValueError("context seed supplied while the observer is disabled")
        self._orch = DayOrchestrator(
            section=self._section,
            seed=core_seed,
            tick_size=self._tick,
            levels_for=lambda _ts: self._levels.levels() if self._levels else (),
            context_config=self._context_config,
            context_seed=context_seed,
            context_symbol=self._context_symbol,
            strategy_core_commit=self._strategy_core_commit,
            strategy_core_source_tree_hash=self._strategy_core_source_tree_hash,
        )

    def context_day_snapshot(self, source_day: date) -> IfvgDaySeedV3:
        if self._orch is None or self._context_config is None:
            raise RuntimeError("context observer is disabled")
        return IfvgDaySeedV3(
            container_version=IFVG_CONTEXT_SEED_CONTAINER_VERSION,
            core=self._orch.end_seed(source_day),
            context=self._orch.end_context_seed(),
        )

    def finalize_trading_day(self, trading_day: date) -> tuple[IfvgEmission, ...]:
        if self._orch is None:
            return ()
        return self._orch.finalize_day(trading_day)

    def finalize_dataset(self, trading_day: date) -> tuple[IfvgEmission, ...]:
        if self._orch is None:
            return ()
        return self._orch.finalize_dataset(trading_day)
