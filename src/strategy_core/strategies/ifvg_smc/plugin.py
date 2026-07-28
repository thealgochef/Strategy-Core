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
from .replay import DayOrchestrator
from .section import (
    IFVG_STRATEGY_ID,
    IFVG_STRATEGY_VERSION,
    IfvgSmcSection,
    default_ifvg_smc_section,
)
from .state import IfvgDaySeed

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

    def __init__(self) -> None:
        self._section: IfvgSmcSection | None = None
        self._orch: DayOrchestrator | None = None
        self._levels: StrategyLevelState | None = None
        self._emissions: list[IfvgEmission] = []
        self._static_levels: tuple[Level, ...] = ()
        self._tick: float = 0.25

    # ── lifecycle ────────────────────────────────────────────────────────────
    def configure(self, section: IfvgSmcSection, ctx: PlatformContext) -> None:
        self._section = section
        self._tick = ctx.tick_size
        self._levels = StrategyLevelState(
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
        )
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
        return (
            EventTypeSpec("ifvg.setup", ("setup_id", "phase", "direction")),
            EventTypeSpec("ifvg.entry", ("setup_id", "entry_family", "entry", "stop", "tp")),
            EventTypeSpec("ifvg.resolution", ("setup_id", "resolution")),
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

    def load_day_seed(self, seed: IfvgDaySeed) -> None:
        if self._section is None:
            raise RuntimeError("plugin not configured")
        self._orch = DayOrchestrator(
            section=self._section,
            seed=seed,
            tick_size=self._tick,
            levels_for=lambda _ts: self._levels.levels() if self._levels else (),
        )

    def finalize_trading_day(self, trading_day: date) -> tuple[IfvgEmission, ...]:
        if self._orch is None:
            return ()
        return self._orch.finalize_day(trading_day)
