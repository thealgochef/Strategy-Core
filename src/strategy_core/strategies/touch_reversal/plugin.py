"""TouchReversalPlugin — archetype 1 as a behavior-identical WRAPPER (PLAN §4).

This is the existing hardwired touch/zone/level pipeline expressed behind the §2.2
``StrategyPlugin`` protocol. Nothing in the decision/feature/label kernel changes: the
plugin is a thin declaration + dispatch shell that IMPORTS and CALLS the existing
functions verbatim (PLAN "ADDITIVE COROLLARY": Phase A does NOT physically move
``StrategyLevelState``/``build_zones``/``detect_touches`` — it wraps them in place).

Wiring note (PLAN §7 / Steps A3, B2): the plugin is registered but **NOT constructed by
any production path** — production/Trade-Lab build ``StrategyRuntime`` plugin-less, so the
verbatim hardwired touch fold is still live. As of B2 PART 1 the runtime CAN route through
``on_bar_closed`` when a plugin is explicitly passed, but that path is exercised only by
tests. Importing this module is the ONLY thing that registers ``touch_reversal`` (the
``@register`` side effect); no ``import strategy_core`` path reaches it. Its only importers
are the A3 equivalence test (proves ``detect_touches`` output is byte-identical to a direct
call) and the B2 seam-parity test (proves the runtime plugin-path equals the None path
across multiple bars, incl. cross-bar suppression).

Authoritative resolutions honored (see PROGRESS "Plan clarifications"):
* R1 — the plugin OWNS its level state (``self._levels``), configured in
  ``configure(section, ctx)``; it folds trades into it via ``on_event`` (mirroring the
  runtime's ``level_state.process_trade`` at ``state.py:269``).
* R2 — the scheme comes from ``section.session_scheme`` and zones come from
  ``self._levels``, never from ``ctx`` (``ctx`` exposes no levels/scheme accessor).
* R3 — ``TouchRule`` has NO ``decision_tf``; the decision timeframe is the engine's
  default min tick-count (``state.py:188`` resolves ``decision_timeframe or min(timeframes)``;
  the default timeframes are ``(147, 987, 2000)`` so the default is ``DEFAULT_TICK_COUNT``).
"""

from __future__ import annotations

from collections.abc import Mapping, Set as AbstractSet
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from types import MappingProxyType
from typing import Any

from strategy_core.constants import (
    DECISION_OFFSET_MINUTES,
    DEFAULT_SL_POINTS,
    DEFAULT_TICK_COUNT,
    DEFAULT_TICK_SIZE,
    DEFAULT_TP_POINTS,
    DEFAULT_TRAP_MFE_MIN,
    FLATTEN_TIME,
    INTERACTION_FEATURES,
    LABEL_FORWARD_CUTOFF,
    LABEL_NO_RESOLUTION_DROPPED,
    LABEL_RESOLUTION,
    NAN_POLICY,
    RUNTIME_APPROACH_FEATURES,
    ZONE_PROXIMITY_PTS,
)
from strategy_core.decisions.dedup import ZoneKey, zone_key
from strategy_core.decisions.touch import detect_touches
from strategy_core.decisions.zones import build_zones
from strategy_core.runtime.levels import StrategyLevelState
from strategy_core.strategies.protocols import (
    BarKind,
    BarSpec,
    EventTypeSpec,
    FeatureSpec,
    LabelPolicySpec,
    PlatformContext,
    StrategyStep,
)
from strategy_core.strategies.registry import register
from strategy_core.strategies.touch_reversal.section import TouchReversalSection
from strategy_core.types import (
    Bar,
    Level,
    Quote,
    SessionScheme,
    SessionWindow,
    Touch,
    Trade,
)

__all__ = ["TouchReversalPlugin", "FixedPointsBarrier"]

# R3: the decision timeframe is the engine's default smallest tick-count. The runtime
# resolves ``decision_timeframe = decision_timeframe or min(timeframes)`` (state.py:188)
# with default timeframes (147, 987, 2000), i.e. DEFAULT_TICK_COUNT. Held as a constant
# because required_bars()/decision_bar_label() are @staticmethod per §2.2; a configurable
# decision tf is a wiring concern deferred to Phase B.
_DECISION_TIMEFRAME = DEFAULT_TICK_COUNT
_DECISION_BAR_LABEL = f"{DEFAULT_TICK_COUNT}t"


def _runtime_scheme_from_section(scheme: Any) -> SessionScheme:
    """Adapt the section's CONTRACT-form ``SessionScheme`` into the runtime type.

    ``section.session_scheme`` is the ``contract.schema.SessionScheme`` (string clock
    times); ``StrategyLevelState`` needs the ``strategy_core.types.SessionScheme``
    (``datetime.time`` objects). The scheme still ORIGINATES from the section (R2) — only
    its representation is converted. ``closed_window`` is ``None`` (the contract form
    carries no closed window; the canonical research scheme drops nothing).
    """
    return SessionScheme(
        timezone=scheme.timezone,
        trading_day_boundary=time.fromisoformat(scheme.trading_day_boundary),
        sessions={
            name: SessionWindow(
                time.fromisoformat(window.start),
                time.fromisoformat(window.end),
                crosses_midnight=window.crosses_midnight,
            )
            for name, window in scheme.sessions.items()
        },
        closed_window=None,
    )


@dataclass(frozen=True, slots=True)
class FixedPointsBarrier:
    """The archetype-1 ``fixed_points`` ``Barrier`` (PLAN §2.2 / §4.5).

    Reproduces today's absolute thresholds. The defaults are ANCHORED to the engine
    constants (``constants.py:139-141`` — tp=15 / sl=30 / trap=5), NOT to any shipped
    bundle's per-model contract values (a bundle may carry e.g. tp=15/sl=15; that is a
    contract value, not the engine default). ``resolve_outcome`` consumes the same
    tp/sl/trap unchanged.
    """

    kind: str = "fixed_points"
    tp_points: float = DEFAULT_TP_POINTS
    sl_points: float = DEFAULT_SL_POINTS
    trap_mfe_min: float = DEFAULT_TRAP_MFE_MIN

    @staticmethod
    def _is_long(direction: Any) -> bool:
        # Accept the engine Direction enum (value "LONG") or the protocol "long" string.
        return str(getattr(direction, "value", direction)).upper().startswith("L")

    def stop_price(self, entry_price: float, direction: Any) -> float:
        return entry_price - self.sl_points if self._is_long(direction) else entry_price + self.sl_points

    def target_price(self, entry_price: float, direction: Any) -> float:
        return entry_price + self.tp_points if self._is_long(direction) else entry_price - self.tp_points


#: One shared, frozen fixed-points barrier (the touch strategy's barrier is constant).
_FIXED_BARRIER = FixedPointsBarrier()


@dataclass(frozen=True, slots=True)
class TouchSetup:
    """Concrete ``SetupState`` for a touch — single-phase (``touched``/``active``).

    Carries the authoritative engine ``Touch`` (PLAN §4.6: the touch's Core direction is
    carried, not re-derived) so the platform runtime can map it onto ``RuntimeUpdate.touches``
    when the seam is wired (Phase B), and the A3 equivalence test can read it directly.
    """

    setup_id: str
    phase: str
    direction: str
    status: str
    evidence: Mapping[str, Any]
    touch: Touch


@dataclass(frozen=True, slots=True)
class TouchDecision:
    """Concrete ``DecisionEvent`` for a touch (PLAN §2.2 / §4.6).

    ``decision_ts_utc = touch close + decision_offset`` (honest_entry.py:127);
    ``entry_reference = "trade_price_at_decision"`` (PLAN §2.6); ``barrier`` is the
    shared ``fixed_points`` barrier.
    """

    setup_id: str
    decision_ts_utc: datetime
    direction: str
    entry_reference: str
    barrier: FixedPointsBarrier
    touch: Touch


def _setup_id(touch: Touch) -> str:
    return f"{touch.trading_day.isoformat()}:{touch.level_type}:{touch.representative_price}"


@register
class TouchReversalPlugin:
    """Archetype 1 (touch / zone-reversal / 3-class MAE-first) behind the §2.2 protocol."""

    strategy_id = "touch_reversal"
    #: Placeholder — NOT load-bearing until Phase E splits ENGINE_VERSION into
    #: platform_version + per-plugin strategy_version (decision 9.3). Set to "1" for now.
    strategy_version = "1"
    SectionModel = TouchReversalSection

    def __init__(self) -> None:
        self._section: TouchReversalSection | None = None
        self._tick_size: float = DEFAULT_TICK_SIZE
        # Default level state until configure() rebuilds it from the section scheme.
        self._levels: StrategyLevelState = StrategyLevelState(tick_size=DEFAULT_TICK_SIZE)

    # ---- lifecycle ----
    def configure(self, section: TouchReversalSection, ctx: PlatformContext) -> None:
        # R1: the plugin OWNS the level state; R2: scheme from the section, tick_size
        # from ctx. This mirrors the runtime's __init__ wiring at state.py:187-189, but
        # owned by the plugin instead of the runtime.
        self._section = section
        self._tick_size = ctx.tick_size
        self._levels = StrategyLevelState(
            scheme=_runtime_scheme_from_section(section.session_scheme),
            tick_size=ctx.tick_size,
        )

    def reset(self) -> None:
        # Mirror StrategyRuntime.reset's level_state.reset() (state.py:205); the platform
        # still owns candle/feed reset.
        self._levels.reset()

    def set_static_levels(self, levels: tuple[Level, ...]) -> None:
        """Seed prior-day/static levels — mirrors ``StrategyRuntime.set_static_levels`` (state.py:242-243)."""
        self._levels.set_static_levels(levels)

    def load_prior_day_summary(self, trading_day: date, *, high_ticks: int, low_ticks: int) -> None:
        """Mirror ``StrategyRuntime.load_prior_day_summary`` onto the plugin's level state (W4).

        ``self._levels`` is the SAME ``StrategyLevelState`` class the runtime owns, so this
        delegates the identical call — keeping PDH/PDL in lockstep with the runtime."""
        self._levels.load_prior_day_summary(trading_day, high_ticks=high_ticks, low_ticks=low_ticks)

    # ---- data requirements (DECLARED) ----
    @staticmethod
    def required_bars() -> tuple[BarSpec, ...]:
        # One TICK BarSpec at the decision timeframe (R3).
        return (BarSpec(kind=BarKind.TICK, size=_DECISION_TIMEFRAME, label=_DECISION_BAR_LABEL),)

    @staticmethod
    def decision_bar_label() -> str:
        return _DECISION_BAR_LABEL

    # ---- event consumption ----
    def on_event(self, event: Trade | Quote, ctx: PlatformContext) -> tuple:
        # Fold trades into the plugin-owned level state — mirrors state.py:269
        # (level_state.process_trade). Quotes are inert here (as today; the runtime's
        # _process_quote only buffers the last quote).
        if isinstance(event, Trade):
            self._levels.process_trade(event)
        return ()

    def on_bar_closed(
        self, bar: Bar, ctx: PlatformContext, already_fired_keys: AbstractSet[ZoneKey]
    ) -> StrategyStep:
        # The PLATFORM gates which bars reach here. The runtime's plugin-path loop only
        # calls on_bar_closed for bars whose timeframe == the runtime's decision_timeframe
        # (state.py else branch), EXACTLY as the None path gates. So this method does NOT
        # re-gate on its own declared decision bar (_DECISION_TIMEFRAME): re-gating on a
        # hardcoded timeframe would break byte-identity whenever the runtime's
        # decision_timeframe differs from it (e.g. a tf=2 acceptance harness). It processes
        # the decision bar it is handed, mirroring the hardwired fold (state.py:316-321,287):
        # build zones from ALL current levels, PRE-MARK zones already fired this day from the
        # platform-owned dedup set using the SHARED zone_key (I3), then detect_touches with
        # the identical call shape. It only READS already_fired_keys (never mutates it).
        zone_proximity = (
            self._section.touch_rule.zone_proximity_pts
            if self._section is not None
            else ZONE_PROXIMITY_PTS
        )
        zones = build_zones(list(self._levels.levels()), zone_proximity_pts=zone_proximity)
        for zone in zones:
            if zone_key(bar.trading_day, zone) in already_fired_keys:  # mirrors state.py:319-321
                zone.touched = True
        touches = detect_touches(
            (bar,), zones, tick_size=ctx.tick_size, trading_day=bar.trading_day
        )  # state.py:287
        setups = tuple(self._setup_for(touch) for touch in touches)
        decisions = tuple(self._decision_for(touch) for touch in touches)
        return StrategyStep(
            setups=setups, decisions=decisions, features=(),
            touches=tuple(touches), zones=tuple(zones),
        )

    # ---- declarations consumed by platform + consumers ----
    @staticmethod
    def feature_spec() -> FeatureSpec:
        # The six current features (features.py __all__), partitioned 3 interaction +
        # 3 approach (PLAN §4.4), single-sourced from constants (no restated literals).
        return FeatureSpec(
            names=(*INTERACTION_FEATURES, *RUNTIME_APPROACH_FEATURES),
            interaction_features=INTERACTION_FEATURES,
            approach_features=RUNTIME_APPROACH_FEATURES,
            nan_policy=NAN_POLICY,
        )

    @staticmethod
    def label_policy() -> LabelPolicySpec:
        # barrier_mode = "fixed_points" reusing resolve_outcome (PLAN §4.5); tp/sl/trap
        # anchored to constants.py, NOT a bundle value.
        return LabelPolicySpec(
            resolution=LABEL_RESOLUTION,
            barrier_mode="fixed_points",
            barrier=_FIXED_BARRIER,
            decision_offset_minutes=DECISION_OFFSET_MINUTES,
            flatten_time=FLATTEN_TIME,
            forward_cutoff=LABEL_FORWARD_CUTOFF,
            no_resolution_dropped=LABEL_NO_RESOLUTION_DROPPED,
        )

    @staticmethod
    def emitted_event_types() -> tuple[EventTypeSpec, ...]:
        # The touch deltas (PLAN §4.6); the platform fans them out on the generic ws.v1
        # frame, so no top-level MessageType literal is added.
        return (
            EventTypeSpec(
                "touch.detected",
                ("bar_ts_utc", "representative_price", "direction", "level_type", "trading_day"),
            ),
            EventTypeSpec("observation.updated", ("setup_id", "phase", "status", "direction")),
            EventTypeSpec(
                "prediction.created",
                ("setup_id", "decision_ts_utc", "direction", "entry_reference"),
            ),
            EventTypeSpec("prediction.resolved", ("setup_id", "label", "max_mfe", "max_mae")),
        )

    # ---- helpers ----
    @staticmethod
    def _setup_for(touch: Touch) -> TouchSetup:
        return TouchSetup(
            setup_id=_setup_id(touch),
            phase="touched",
            direction=touch.direction.value.lower(),  # "long"/"short" (protocol vocab)
            status="active",
            evidence=MappingProxyType(
                {
                    "level_type": touch.level_type,
                    "representative_price": touch.representative_price,
                    "trading_day": touch.trading_day.isoformat(),
                }
            ),
            touch=touch,
        )

    @staticmethod
    def _decision_for(touch: Touch) -> TouchDecision:
        return TouchDecision(
            setup_id=_setup_id(touch),
            decision_ts_utc=touch.bar_ts_utc + timedelta(minutes=DECISION_OFFSET_MINUTES),
            direction=touch.direction.value.lower(),
            entry_reference="trade_price_at_decision",
            barrier=_FIXED_BARRIER,
            touch=touch,
        )
