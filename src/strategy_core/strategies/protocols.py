"""The strategy-plugin SDK surface — Protocols + supporting types (PLAN §2.2).

Introduced declaration-only in Phase A (Step A1); LOAD-BEARING since Phase B — the
runtime routes the touch strategy solely through this seam (B3 deleted the hardwired
fold), and since S-B3a the plugin also owns the single level fold and the cross-bar
first-touch dedup (the platform reads levels/zones back through ``on_event``'s return
and the ``current_levels``/``snapshot_zones`` accessors).

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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from strategy_core.types import Bar, Level, Quote, Touch, Trade, Zone

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
    #: The raw engine touches this bar produced (folded VERBATIM onto
    #: ``RuntimeUpdate.touches`` — the platform performs no re-derivation, re-keying, or
    #: filtering since S-B3a) and the post-detection zones they came from (informational;
    #: the cross-bar dedup key is derived INSIDE the plugin since S-B3a). Both default
    #: empty so the step stays default-constructible.
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

    def set_static_levels(self, levels: tuple[Level, ...]) -> None:
        """Seed static reference levels — written through by the runtime's lifecycle
        method; the SOLE level-seed path since S-B3a (W4/D-B2j)."""
        ...

    def load_prior_day_summary(self, trading_day: date, *, high_ticks: int, low_ticks: int) -> None:
        """Seed the prior-day PDH/PDL summary — written through by the runtime's
        lifecycle method; the SOLE level-seed path since S-B3a (W4/D-B2j)."""
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
    def on_event(self, event: Trade | Quote, ctx: PlatformContext) -> tuple[Level, ...]:
        """Fold a trade/quote into the plugin's own state; return the level delta.

        S-B3a: the plugin owns the SOLE level fold (R1), so for a ``Trade`` this returns
        the plugin's full post-fold level set (the platform maps it onto
        ``RuntimeUpdate.levels`` — previously the runtime's own redundant fold supplied
        it); for a ``Quote`` it returns ``()``.
        """
        ...

    def on_bar_closed(self, bar: Bar, ctx: PlatformContext) -> StrategyStep:
        """Fold a closed bar; return the sparse strategy delta (setups/decisions/features/touches/zones).

        S-B3a: the cross-bar first-touch dedup is PLUGIN-owned (the D-B2b placement was
        resolved to the plugin). The plugin pre-marks its zones from its OWN fired-keys
        set and records newly-fired keys itself — the retired ``already_fired_keys``
        parameter is gone and the platform performs no dedup bookkeeping.
        """
        ...

    # ---- platform-read state accessors (S-B3a; see the deviation note below) ----
    def current_levels(self) -> tuple[Level, ...]:
        """The plugin's full current level set (feeds the platform snapshot's ``levels``)."""
        ...

    def snapshot_zones(self, trading_day: date | None) -> tuple[Zone, ...]:
        """Display zones with already-fired zones pre-marked ``touched`` (feeds the
        platform snapshot's / per-trade update's ``zones``). ``trading_day=None`` (no
        event processed yet) returns the zones unmarked.

        Deviation (S-B3a, recorded in PROGRESS): the protocol temporarily carries touch
        vocabulary (``current_levels``/``snapshot_zones``, like ``StrategyStep.touches``/
        ``zones`` per D-B2d) because ``RuntimeUpdate``/``RuntimeSnapshot`` still expose
        typed ``levels``/``zones`` fields; the generic plugin-event payload that removes
        them stays deferred per PLAN §2.1(5).
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
