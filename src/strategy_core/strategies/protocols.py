"""The strategy-plugin SDK surface — Protocols + supporting types (PLAN §2.2).

DECLARATION-ONLY (PLAN §7 Phase A / Step A1). This module introduces the thin-waist
boundary between the PLATFORM (the event loop, candles, transport, contract loader)
and a STRATEGY PLUGIN, but **nothing in the platform imports it yet**: the runtime's
hardwired touch fold at ``runtime/state.py:271-280`` is still the live path, so touch
behavior is byte-identical. These types only become load-bearing in Phase B, when
``StrategyRuntime`` gains an optional ``plugin`` param.

It lives in a SUBMODULE (not the package ``__init__``) so the registry (A2) and the
plugin (A3) import the protocol types without the package ``__init__`` running any
import-time work — keeping the platform strategy-agnostic and avoiding import cycles.

Authoritative resolutions honored here (see PROGRESS "Plan clarifications"):
* R2 — ``PlatformContext`` is EXACTLY the §2.2 surface PLUS the §9.10 ``quotes_in_window``
  accessor; it has NO levels/scheme accessor. A plugin gets its scheme from its SECTION
  and its levels/zones from its OWN level state, never from ``ctx``.

What lives here (PLAN §2.2, the full plugin surface):
* ``StrategyPlugin`` — the ``runtime_checkable`` structural Protocol every strategy
  satisfies (decision 9.1: Protocol over ABC; the deeper validation runs at
  ``@register`` time, not here).
* ``PlatformContext`` — the read-only, platform-provided context handed to a plugin.
* ``BarSpec`` / ``BarKind`` — a strategy *declares* the tick AND time bars it needs;
  TIME bars are not yet buildable by the engine (decision 9.4 / Phase F) — only the
  declaration shape exists here.
* ``SetupState`` / ``DecisionEvent`` / ``Barrier`` — the multi-stage setup lifecycle,
  fired decisions, and per-setup barriers (``fixed_points`` AND ``r_relative``).
* ``StrategyStep`` — the sparse delta one bar-close returns (modelled on
  ``runtime.RuntimeUpdate``); default-constructible to an empty delta.
* ``FeatureSpec`` / ``LabelPolicySpec`` / ``EventTypeSpec`` — the declarations the
  platform + consumers read (features, label/outcome policy incl. barrier mode, and the
  ws payload schemas the strategy emits).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from strategy_core.decisions.dedup import ZoneKey
from strategy_core.types import Bar, Quote, Touch, Trade, Zone

__all__ = [
    "BarKind",
    "BarSpec",
    "PlatformContext",
    "SetupState",
    "Barrier",
    "DecisionEvent",
    "StrategyStep",
    "FeatureSpec",
    "LabelPolicySpec",
    "EventTypeSpec",
    "StrategyPlugin",
]


# ── Declared data needs (tick AND time) ──────────────────────────────────────
class BarKind(StrEnum):
    """How a bar closes. ``StrEnum`` so ``BarKind.TICK == "tick"`` (PLAN §2.1(3))."""

    TICK = "tick"  # close on trade_count == size      (CURRENT engine)
    TIME = "time"  # close on wall-clock interval edge  (NEW close trigger, Phase F)


@dataclass(frozen=True, slots=True)
class BarSpec:
    """A bar a strategy declares it needs (PLAN §2.1(3)).

    ``size`` is a tick count for ``TICK`` or interval *seconds* for ``TIME``;
    ``label`` is a stable id (e.g. ``"147t"``, ``"1m"``, ``"1H"``) the platform routes
    closed bars by. Archetype 1 declares a single ``TICK`` spec; archetype 2 declares a
    mix of ``TIME`` specs (1m..4H) — which the engine cannot yet build (decision 9.4,
    Phase F).
    """

    kind: BarKind
    size: int
    label: str


# ── Platform-provided context handed to the plugin each step (read-only) ──────
class PlatformContext(Protocol):
    """Read-only platform context handed to a plugin each step (PLAN §2.2 + §9.10).

    R2: this is the COMPLETE surface — there is deliberately NO levels accessor and NO
    scheme attribute. The plugin reads market state through this seam, gets its scheme
    from its section, and owns its own level state. ``quotes_in_window`` is the §9.10
    accessor: quotes stay platform-buffered (the trade-driven candle/level invariant is
    preserved) but a plugin/feature that needs them — e.g. ``app_max_spread`` — can pull
    a bounded window, so the lone quote-consuming feature keeps its data source.
    """

    tick_size: float
    point_value: float

    def closed_bars(self, label: str) -> Sequence[Bar]:
        """Recently-closed bars for the BarSpec identified by ``label``."""
        ...

    def current_bar(self, label: str) -> Bar | None:
        """The forming (not-yet-closed) bar for ``label``, or ``None``."""
        ...

    def trade_price_at(self, ts_utc: datetime) -> float | None:
        """Realistic front-month trade-print price at a decision instant (honest fill)."""
        ...

    def session_at(self, ts_utc: datetime) -> str | None:
        """The session name at ``ts_utc`` via the active ``SessionScheme``."""
        ...

    def quotes_in_window(
        self, start_ts_utc: datetime, end_ts_utc: datetime
    ) -> Sequence[Quote]:
        """Buffered top-of-book quotes whose ts is in ``[start, end)`` (§9.10)."""
        ...


# ── The things a plugin emits (all strategy-owned, platform-opaque) ───────────
class SetupState(Protocol):
    """A multi-stage setup delta: arming → locking → invalidation (PLAN §2.2).

    Archetype 1 is degenerate single-phase (``touched`` → resolved); archetype 2 walks
    the full ifvg-strat.md state machine. ``evidence`` carries the audit payload
    (HTF zone, parent tf, opposing gap, ...).
    """

    setup_id: str
    phase: str  # e.g. "scanning"|"htf_tapped"|"parent_locked"|"armed"|"invalidated"
    direction: str  # "long"|"short"
    status: str  # "active"|"invalidated"|"expired"|"resolved"
    evidence: Mapping[str, Any]


class Barrier(Protocol):
    """A per-setup stop/target (PLAN §2.2). ``kind`` is ``"fixed_points"`` or ``"r_relative"``.

    ``fixed_points`` reproduces today's absolute ``tp_points``/``sl_points``; ``r_relative``
    computes ``SL = swing level`` and ``TP = entry ± 1R`` (``R = |entry − SL|``). Both feed
    the SAME shared MAE-first kernel (the plugin derives per-setup tp/sl from R).
    """

    kind: str

    def stop_price(self, entry_price: float, direction: str) -> float:
        ...

    def target_price(self, entry_price: float, direction: str) -> float:
        ...


class DecisionEvent(Protocol):
    """A fired entry decision (PLAN §2.2).

    ``entry_reference`` is e.g. ``"trade_price_at_decision"`` (archetype 1) or
    ``"confirmation_close"`` (archetype 2). ``barrier`` is the per-setup ``Barrier``
    (fixed OR R-relative).
    """

    setup_id: str
    decision_ts_utc: datetime
    direction: str
    entry_reference: str
    barrier: Barrier


@dataclass(frozen=True, slots=True)
class StrategyStep:
    """What one bar-close step returns — sparse, modelled on ``RuntimeUpdate`` (PLAN §2.2).

    Default-constructible (``StrategyStep()`` == empty delta) so a guard-fail returns an
    empty step. The three fields are the PLAN §2.2 surface; a plugin's concrete
    ``SetupState``/``DecisionEvent`` carry whatever strategy artifacts they need (e.g. the
    touch plugin's setups carry the raw ``Touch``).
    """

    setups: tuple[SetupState, ...] = ()
    decisions: tuple[DecisionEvent, ...] = ()
    features: tuple[Mapping[str, float], ...] = ()
    #: B2: the raw engine touches this bar produced and the (post-detection) zones they
    #: came from, so the platform runtime can fold them onto ``RuntimeUpdate.touches`` and
    #: compute the cross-bar dedup key off the same zones. Both default empty so the step
    #: stays default-constructible.
    touches: tuple[Touch, ...] = ()
    zones: tuple[Zone, ...] = ()


# ── Declarations consumed by the platform + consumers ─────────────────────────
@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """Declared feature vector (PLAN §2.2 / §4.4): names + interaction/approach split + nan_policy.

    The interaction/approach partition is the same one the contract's ``FeatureSet``
    validator enforces (``names == interaction ∪ approach``); the plugin owns which
    features it computes.
    """

    names: tuple[str, ...]
    interaction_features: tuple[str, ...]
    approach_features: tuple[str, ...]
    nan_policy: str


@dataclass(frozen=True, slots=True)
class LabelPolicySpec:
    """Declared label/outcome policy (PLAN §2.2 / §4.5): resolution + barrier MODE + cutoff rule.

    ``barrier_mode`` is ``"fixed_points"`` (archetype 1) or ``"r_relative"`` (archetype 2),
    so the platform's outcome/parity machinery knows whether to score fixed-point or
    R-normalized excursions. ``barrier`` is the concrete per-strategy ``Barrier``.
    """

    resolution: str
    barrier_mode: str
    barrier: Barrier
    decision_offset_minutes: int
    flatten_time: time
    forward_cutoff: str
    no_resolution_dropped: bool


@dataclass(frozen=True, slots=True)
class EventTypeSpec:
    """A ws payload schema the strategy emits (PLAN §2.2 / §4.6).

    The platform fans these out on the GENERIC ``ws.v1`` envelope, so adding a strategy
    delta does not edit the platform's ``MessageType`` literal. ``payload_fields`` names
    the keys the payload carries (descriptive; the strategy owns the schema).
    """

    message_type: str
    payload_fields: tuple[str, ...] = ()


# ── The strategy-plugin Protocol (full surface, PLAN §2.2) ────────────────────
@runtime_checkable
class StrategyPlugin(Protocol):
    """The structural plugin interface (decision 9.1: ``runtime_checkable`` Protocol).

    ``runtime_checkable`` checks method/attr *presence* only — a wrong signature fails
    at call time, not registration. The deeper validation (``required_bars()`` returns
    ``BarSpec``s; ``SectionModel`` is a pydantic ``BaseModel``) is the §9.1 registry-time
    assertion in ``strategy_core.strategies.registry.register`` so a malformed plugin
    fails at ``@register``, not in the hot path.
    """

    # ---- identity / binding ----
    strategy_id: str
    strategy_version: str
    SectionModel: type  # the pydantic section model this strategy OWNS (PLAN §2.4)

    # ---- lifecycle ----
    def configure(self, section: Any, ctx: PlatformContext) -> None:
        """Wire the validated ``SectionModel`` + platform context into plugin state."""
        ...

    def reset(self) -> None:
        """Clear the plugin's own state (the platform resets candles/feed)."""
        ...

    # ---- data requirements (DECLARED, tick AND time) ----
    @staticmethod
    def required_bars() -> tuple[BarSpec, ...]:
        """The tick/time bars this strategy needs (PLAN §2.2)."""
        ...

    @staticmethod
    def decision_bar_label() -> str:
        """The BarSpec label that drives single-bar decisions."""
        ...

    # ---- event consumption ----
    def on_event(self, event: Trade | Quote, ctx: PlatformContext) -> tuple[SetupState, ...]:
        """Fold a trade/quote; return any setup-state deltas."""
        ...

    def on_bar_closed(
        self, bar: Bar, ctx: PlatformContext, already_fired_keys: AbstractSet[ZoneKey]
    ) -> StrategyStep:
        """Fold a closed bar; return the sparse strategy delta (setups/decisions/features/touches/zones).

        ``already_fired_keys`` is the cross-bar first-touch dedup set the PLATFORM owns
        (the runtime's ``_touched_zone_keys``). The plugin pre-marks its zones from it
        (so an already-fired zone does not re-fire) using the shared
        ``strategy_core.decisions.dedup.zone_key``, and MUST NOT mutate it — the platform
        records newly-fired keys after this returns.
        """
        ...

    # ---- declarations consumed by platform + consumers ----
    @staticmethod
    def feature_spec() -> FeatureSpec:
        ...

    @staticmethod
    def label_policy() -> LabelPolicySpec:
        ...

    @staticmethod
    def emitted_event_types() -> tuple[EventTypeSpec, ...]:
        ...
