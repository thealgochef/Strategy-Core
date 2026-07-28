# B2 design-review context bundle  (DISPOSABLE — do not commit)
Generated read-only for the architect's Phase B / Step B2 design review. No source was changed. Part 1 is verbatim from disk; Part 2 is an in-process grep; Part 3 is analysis.

---

## PART 1 — Verbatim source

### runtime/state.py  —  _process_trade  (state.py:273-306)

```python
    def _process_trade(self, trade: Trade) -> RuntimeUpdate:
        self._last_event_ts_utc = trade.event_ts_utc
        candle_update = self.candles.process_trade(trade)
        if candle_update.completed:
            self._recent_closed_bars.extend(candle_update.completed)
            if len(self._recent_closed_bars) > self._recent_closed_bar_limit:
                del self._recent_closed_bars[: len(self._recent_closed_bars) - self._recent_closed_bar_limit]
        levels = self.level_state.process_trade(trade)
        touches: list[Touch] = []
        if self._plugin is None:
            for bar in candle_update.completed:
                if bar.timeframe_ticks != self.decision_timeframe:
                    continue
                zones = self._zones_for_detection(bar.trading_day)
                detected = detect_touches((bar,), zones, tick_size=self.tick_size, trading_day=bar.trading_day)
                for touch in detected:
                    self._touched_zone_keys.add(self._touch_zone_key_from_touch(touch, zones))
                touches.extend(detected)
        else:
            # B2: route through self._plugin.on_bar_closed(...) and map its touches back
            # onto `touches`. No-op in B1 (the plugin path is dead until B2).
            pass
        if touches:
            self._touches.extend(touches)
        session, trading_day = self._session_state()
        self._feed_status = FeedStatus(state="replaying", mode="runtime", requested_symbol=self.requested_symbol, last_event_ts_utc=trade.event_ts_utc, last_message="trade processed")
        return RuntimeUpdate(
            feed_status=self._feed_status,
            current_bars=candle_update.current,
            closed_bars=candle_update.completed,
            levels=levels,
            zones=tuple(self._zones_for_snapshot(trading_day)),
            touches=tuple(touches),
        )
```

### runtime/state.py  —  _zones_for_detection  (state.py:308-322)

```python
    def _zones_for_detection(self, trading_day: date) -> list[Zone]:
        # audit #3: build zones from ALL current levels -- do NOT pre-filter by
        # availability before build_zones. Pre-filtering diverged from canonical
        # merge-all / gate-each-zone-on-MAX semantics and from the snapshot path
        # (_zones_for_snapshot below). detect_touches (decisions/touch.py:93) already
        # gates each zone on ``bar.close_ts_utc < zone.available_from``, so the v3
        # look-ahead protection is preserved while zone composition now matches
        # canonical (and _zones_for_snapshot's unfiltered build).
        from strategy_core.decisions.zones import build_zones

        zones = build_zones(list(self.level_state.levels()))
        for zone in zones:
            if self._zone_key(trading_day, zone) in self._touched_zone_keys:
                zone.touched = True
        return zones
```

### runtime/state.py  —  _zones_for_snapshot  (state.py:324-331)  [the SECOND read of _touched_zone_keys]

```python
    def _zones_for_snapshot(self, trading_day: date | None) -> list[Zone]:
        zones = self.level_state.zones()
        if trading_day is None:
            return zones
        for zone in zones:
            if self._zone_key(trading_day, zone) in self._touched_zone_keys:
                zone.touched = True
        return zones
```

### runtime/state.py  —  _zone_key  (state.py:333-335)

```python
    @staticmethod
    def _zone_key(trading_day: date, zone: Zone) -> tuple[date, tuple[str, ...], float, str]:
        return (trading_day, zone.names, zone.representative_price, zone.side.value)
```

### runtime/state.py  —  _touch_zone_key_from_touch  (state.py:337-341)

```python
    def _touch_zone_key_from_touch(self, touch: Touch, zones: list[Zone]) -> tuple[date, tuple[str, ...], float, str]:
        for zone in zones:
            if zone.representative_price == touch.representative_price and touch.level_type in zone.names:
                return self._zone_key(touch.trading_day, zone)
        return (touch.trading_day, (touch.level_type,), touch.representative_price, touch.direction.value)
```

### runtime/state.py  —  self._touch / self._touched_zone_keys declaration+init  (state.py:207-208)

```python
        self._touches: list[Touch] = []
        self._touched_zone_keys: set[tuple[date, tuple[str, ...], float, str]] = set()
```

### runtime/state.py  —  reset(): _touches.clear() + _touched_zone_keys.clear()  (state.py:219-220)

```python
        self._touches.clear()
        self._touched_zone_keys.clear()
```

### decisions/touch.py  —  is_touch + detect_touches  (touch.py:34-109)

```python
def is_touch(bar_low_points: float, bar_high_points: float, zone_rep_points: float) -> bool:
    """Return whether a bar's range straddles a zone's representative price.

    Closed interval, exactly as canonical
    ``dashboard_utility_builder.py:429``::

        if bar_low <= rep <= bar_high:

    so a touch on either boundary (``rep == bar_low`` or ``rep == bar_high``) fires.
    """
    return bar_low_points <= zone_rep_points <= bar_high_points


def detect_touches(
    bars: Sequence[Bar],
    zones: list[Zone],
    *,
    tick_size: float,
    trading_day: date,
    direction_from_side: Mapping[Side, Direction] = DIRECTION_FROM_SIDE,
) -> list[Touch]:
    """Detect first-touch events over ``bars`` in order.

    Ported from ``dashboard_utility_builder.py:414-440`` (``_detect_touches``).

    Iterate ``bars`` IN ORDER. For each bar, convert its high/low ticks to points
    (the decision layer compares in points). For each zone not yet touched, if the
    bar straddles the zone's representative price (``is_touch``), flip the zone's
    ``touched`` flag (mutable first-touch state, canonical line 430), map the zone
    side to a trade direction (canonical line 431), and append a ``Touch``. A zone
    fires only on its FIRST straddling bar and never again (canonical line 425
    guard). Multiple zones may fire on the same bar.

    ``level_type`` is the zone's first constituent level name (``zone["names"][0]``,
    canonical line 436). Touches are returned in detection order.

    LEVEL-AVAILABILITY GATE (engine v3 look-ahead guard): a zone with a non-``None``
    ``available_from`` can only be touched on a bar that CLOSES at/after that instant
    (``bar.close_ts_utc >= zone.available_from``). A bar that closes BEFORE the zone's
    defining session has closed is SKIPPED for that zone — it does NOT consume the
    zone's first-touch (the ``touched`` flag is left unset), so the recorded touch is
    the first qualifying RETURN to the level once it exists, never the forming bar.
    ``available_from is None`` means ungated (the legacy/book-mid path), reproducing
    the pre-v3 no-guard behavior exactly. ``is_touch`` and the
    first-touch-per-zone-per-day scope are otherwise UNCHANGED.
    """
    touches: list[Touch] = []

    for bar in bars:
        low_points = bar.low_ticks * tick_size
        high_points = bar.high_ticks * tick_size

        for zone in zones:
            if zone.touched:
                continue

            # v3 look-ahead guard: the level is not yet available at this bar's close
            # -- skip WITHOUT consuming first-touch so a later (post-availability) bar
            # can record the real return-to-level touch.
            if zone.available_from is not None and bar.close_ts_utc < zone.available_from:
                continue

            if is_touch(low_points, high_points, zone.representative_price):
                zone.touched = True
                direction = direction_from_side[zone.side]
                touches.append(
                    Touch(
                        bar_ts_utc=bar.close_ts_utc,
                        representative_price=zone.representative_price,
                        direction=direction,
                        level_type=zone.names[0],
                        trading_day=trading_day,
                    )
                )

    return touches
```

### types.py  —  Zone (incl. `touched` flag) + Touch  (types.py:142-173)

```python
@dataclass(slots=True)
class Zone:
    """A merged cluster of nearby levels.

    ``representative_price`` is the mean of the constituent level prices (the
    canonical training rule). ``touched`` is mutable first-touch state and is the
    only mutable field on any engine type; first-touch scope tracking flips it.

    ``available_from`` is the UTC instant at/after which this zone may first be
    touched (engine v3 look-ahead guard) — the MAX of its constituent levels'
    ``available_from`` (a merged level isn't real until its latest-closing session has
    closed). ``None`` means UNGATED (all constituents ungated, i.e. the legacy/book-mid
    path). ``detect_touches`` skips a zone on any bar that closes before this instant.
    """

    representative_price: float
    names: tuple[str, ...]
    side: Side
    touched: bool = False
    available_from: datetime | None = None


@dataclass(frozen=True, slots=True)
class Touch:
    """A detected first-touch event: a bar's range straddled a zone's price."""

    bar_ts_utc: datetime
    representative_price: float
    direction: Direction
    level_type: str
    trading_day: date

```

### strategies/protocols.py  —  FULL

```python
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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from strategy_core.types import Bar, Quote, Trade

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

    def on_bar_closed(self, bar: Bar, ctx: PlatformContext) -> StrategyStep:
        """Fold a closed bar; return the sparse strategy delta (setups/decisions/features)."""
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
```

### strategies/registry.py  —  FULL

```python
"""The single-sourced strategy registry (PLAN §2.3, decision 9.2).

A greppable, version-controlled, in-package ``{strategy_id: plugin_cls}`` table
populated by a ``@register`` decorator at import time, with a fail-closed
``get_strategy(strategy_id)`` lookup. Chosen over setuptools entry-points so the
SHA-pinned Trade-Lab and the (to-be-pinned) Quant-Lab resolve the SAME registry by
construction — entry-points would couple discovery to install state, which is exactly
the asymmetric-binding risk this design removes.

Phase A note (PLAN §7 / Step A2): the registry starts EMPTY and is imported by nothing
in the platform — no dispatch path consults it; the runtime's single fixed pipeline
still runs unconditionally and ``strategy_id`` remains the opaque label it is today. A
strategy lands in the table only when its plugin module is explicitly imported (the
``@register`` side-effect). It becomes a router in Phase E (``model_registry.activate``
gains ``get_strategy(contract.strategy_id)``).

Registry-time assertion (decision 9.1): because the plugin interface is a structural
``runtime_checkable`` Protocol (presence-only), ``register`` does the deeper checks AT
REGISTRATION so a malformed plugin fails at ``@register``, not in the hot path:
``isinstance(plugin_cls, StrategyPlugin)`` (the runtime_checkable presence check),
``required_bars()`` returns a non-empty tuple of ``BarSpec``, and ``SectionModel`` is a
pydantic ``BaseModel`` subclass.
"""

from __future__ import annotations

from pydantic import BaseModel

from strategy_core.contract.schema import ContractError
from strategy_core.strategies.protocols import BarSpec, StrategyPlugin

__all__ = ["register", "get_strategy"]

#: The single registry table. Keyed by ``plugin_cls.strategy_id``.
_REGISTRY: dict[str, type[StrategyPlugin]] = {}


def register(plugin_cls: type[StrategyPlugin]) -> type[StrategyPlugin]:
    """Register a strategy plugin under its ``strategy_id`` (decorator form, PLAN §2.3).

    Runs the §9.1 registry-time assertions BEFORE inserting, so a structurally-loose
    plugin (the trade-off of a ``runtime_checkable`` Protocol) is rejected at import,
    not at first hot-path call. Raises :class:`~strategy_core.contract.schema.ContractError`
    (the engine's single fail-closed contract exception) on any violation.

    Returns the class unchanged so it can be used as a ``@register`` decorator.
    """
    # §9.1 (presence): the class must structurally satisfy StrategyPlugin. isinstance
    # against a runtime_checkable Protocol checks that every required member name is
    # present on the class (methods + identity attrs), catching a plugin missing a hook.
    if not isinstance(plugin_cls, StrategyPlugin):
        raise ContractError(
            f"{plugin_cls!r} does not satisfy the StrategyPlugin protocol "
            f"(missing one or more required members)"
        )

    strategy_id = plugin_cls.strategy_id
    if not isinstance(strategy_id, str) or not strategy_id:
        raise ContractError(
            f"{plugin_cls.__name__} must declare a non-empty str strategy_id"
        )

    # §9.1: required_bars() must return a non-empty tuple of BarSpec.
    try:
        bars = plugin_cls.required_bars()
    except Exception as exc:  # noqa: BLE001 -- surface any declaration error as ContractError
        raise ContractError(
            f"{plugin_cls.__name__}.required_bars() raised at register time: {exc!r}"
        ) from exc
    if not isinstance(bars, tuple) or not bars or not all(isinstance(b, BarSpec) for b in bars):
        raise ContractError(
            f"{plugin_cls.__name__}.required_bars() must return a non-empty tuple of BarSpec"
        )

    # §9.1: SectionModel must be a pydantic BaseModel subclass.
    section_model = getattr(plugin_cls, "SectionModel", None)
    if not (isinstance(section_model, type) and issubclass(section_model, BaseModel)):
        raise ContractError(
            f"{plugin_cls.__name__}.SectionModel must be a pydantic BaseModel subclass"
        )

    existing = _REGISTRY.get(strategy_id)
    if existing is not None and existing is not plugin_cls:
        raise ContractError(
            f"strategy_id {strategy_id!r} is already registered to {existing.__name__}"
        )

    _REGISTRY[strategy_id] = plugin_cls
    return plugin_cls


def get_strategy(strategy_id: str) -> type[StrategyPlugin]:
    """Resolve a registered plugin class by ``strategy_id``; fail closed on unknown id.

    Raises :class:`~strategy_core.contract.schema.ContractError` (never ``KeyError``)
    listing the registered ids, so callers fail closed on a single exception type.
    """
    try:
        return _REGISTRY[strategy_id]
    except KeyError:
        raise ContractError(
            f"unknown strategy_id {strategy_id!r}; registered: {sorted(_REGISTRY)}"
        ) from None
```

### strategies/touch_reversal/section.py  —  FULL

```python
"""The ``touch_reversal`` plugin's typed contract SECTION (PLAN §2.4 / §4.3).

The contract split (PLAN §2.4) lifts the strategy-specific groups out of the flat
``StrategyContract`` (``contract/schema.py:246-278``) into a per-plugin ``SectionModel``
the strategy OWNS. For archetype 1 that section is ``TouchReversalSection``: it RE-PARENTS
the existing canonical sub-models (each already an ``extra="forbid"`` ``_ContractModel``)
into one section, so this is a re-parent, not a rewrite — and the platform never owns a
second copy of these fields to drift.

Phase A note (PLAN §7 / Step A3): this is declaration-only and unwired. The platform
loader is NOT yet split into envelope + section (that is Phase E / Step E3); nothing
calls ``model_validate`` on this section in production yet. It exists so the plugin can
declare ``SectionModel = TouchReversalSection`` and the §9.1 registry-time assertion has
a real pydantic ``BaseModel`` subclass to check.
"""

from __future__ import annotations

# Re-parent the CURRENT canonical contract sub-models (no rewrite). ``_ContractModel``
# is the shared ``extra="forbid", frozen=True`` base; importing it keeps the section's
# unknown-key fail-close identical to every other contract section.
from strategy_core.contract.schema import (
    FeatureWindows,
    InferencePolicy,
    LabelPolicy,
    LevelScheme,
    ResearchSessionExperiment,
    SessionScheme,
    TouchRule,
    _ContractModel,
)

__all__ = ["TouchReversalSection"]


class TouchReversalSection(_ContractModel):
    """The archetype-1 (touch / zone-reversal) strategy-owned contract section (PLAN §2.4).

    Holds exactly the strategy-specific groups that move out of the flat contract:
    ``session_scheme``, ``level_scheme``, ``touch_rule``, ``feature_windows``,
    ``label_policy`` (barrier mode is ``fixed_points`` for this strategy), ``inference``,
    and the optional ``research_session_experiment``. ``extra="forbid"`` (via
    ``_ContractModel``) so any unknown key still fails closed.
    """

    session_scheme: SessionScheme
    level_scheme: LevelScheme
    touch_rule: TouchRule
    feature_windows: FeatureWindows
    label_policy: LabelPolicy
    inference: InferencePolicy
    research_session_experiment: ResearchSessionExperiment | None = None
```

### strategies/touch_reversal/plugin.py  —  FULL

```python
"""TouchReversalPlugin — archetype 1 as a behavior-identical WRAPPER (PLAN §4).

This is the existing hardwired touch/zone/level pipeline expressed behind the §2.2
``StrategyPlugin`` protocol. Nothing in the decision/feature/label kernel changes: the
plugin is a thin declaration + dispatch shell that IMPORTS and CALLS the existing
functions verbatim (PLAN "ADDITIVE COROLLARY": Phase A does NOT physically move
``StrategyLevelState``/``build_zones``/``detect_touches`` — it wraps them in place).

Phase A note (PLAN §7 / Step A3): the plugin is registered but **NOT wired into the
runtime** — ``runtime/state.py:271-280`` is still the live touch path. Importing this
module is the ONLY thing that registers ``touch_reversal`` (the ``@register`` side
effect); no ``import strategy_core`` path reaches it. The A3 equivalence test is the
sole importer, and it proves the wrapper's ``detect_touches`` output is byte-identical
to a direct ``detect_touches`` call on the same bars+zones.

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

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta
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
        """Seed prior-day/static levels — mirrors ``StrategyRuntime.set_static_levels`` (state.py:216-217)."""
        self._levels.set_static_levels(levels)

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

    def on_bar_closed(self, bar: Bar, ctx: PlatformContext) -> StrategyStep:
        # Mirror the hardwired touch fold (state.py:271-280) for ONE decision bar:
        # guard on the decision timeframe, build zones from ALL current levels
        # (_zones_for_detection core, state.py:300-302), then detect_touches with the
        # identical call shape (state.py:275). Cross-bar first-touch dedup
        # (_touched_zone_keys) is runtime bookkeeping that the seam carries in Phase B.
        if bar.timeframe_ticks != _DECISION_TIMEFRAME:  # state.py:272-273
            return StrategyStep()
        zone_proximity = (
            self._section.touch_rule.zone_proximity_pts
            if self._section is not None
            else ZONE_PROXIMITY_PTS
        )
        zones = build_zones(list(self._levels.levels()), zone_proximity_pts=zone_proximity)
        touches = detect_touches(
            (bar,), zones, tick_size=ctx.tick_size, trading_day=bar.trading_day
        )  # state.py:275
        setups = tuple(self._setup_for(touch) for touch in touches)
        decisions = tuple(self._decision_for(touch) for touch in touches)
        return StrategyStep(setups=setups, decisions=decisions, features=())

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
```

### tests/test_touch_reversal_plugin.py  —  FULL

```python
"""A3 equivalence: the TouchReversalPlugin wrapper mirrors detect_touches exactly.

PLAN §7 Step A3 acceptance: the plugin's touch output equals a direct ``detect_touches``
call on the SAME bars + the SAME zones derived the identical way. This is the proof that
wrapping ``build_zones → detect_touches`` behind the §2.2 plugin protocol is byte-faithful
(the plugin is "call-site-only" — it moves no math).

This file is the ONLY place that imports the plugin, so its ``@register`` side effect
fires only here — the runtime registry stays empty for every other import path.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from strategy_core.constants import DEFAULT_TICK_SIZE, ZONE_PROXIMITY_PTS
from strategy_core.contract.schema import (
    ContractError,
    FeatureWindows,
    InferencePolicy,
    LabelPolicy,
    LevelScheme,
    SessionScheme,
    SessionWindow,
    TouchRule,
)
from strategy_core.decisions.touch import detect_touches
from strategy_core.decisions.zones import build_zones
from strategy_core.strategies.registry import get_strategy
from strategy_core.strategies.touch_reversal.plugin import (  # noqa: F401 -- import registers the plugin
    TouchReversalPlugin,
)
from strategy_core.strategies.touch_reversal.section import TouchReversalSection
from strategy_core.types import Bar, CloseReason, Direction, Level, Side


class _Ctx:
    """Minimal PlatformContext stub — only ``tick_size`` is exercised by the touch path."""

    tick_size = DEFAULT_TICK_SIZE
    point_value = 20.0

    def closed_bars(self, label: str):
        return ()

    def current_bar(self, label: str):
        return None

    def trade_price_at(self, ts_utc):
        return None

    def session_at(self, ts_utc):
        return None

    def quotes_in_window(self, start_ts_utc, end_ts_utc):
        return ()


def _section() -> TouchReversalSection:
    """A valid v3 touch section (contract-form), sourced from the canonical constants."""
    return TouchReversalSection(
        session_scheme=SessionScheme(
            timezone="US/Eastern",
            trading_day_boundary="18:00",
            sessions={
                "asia": SessionWindow(start="19:00", end="02:45", crosses_midnight=True),
                "london": SessionWindow(start="03:00", end="08:00"),
                "ny": SessionWindow(start="09:00", end="17:00"),
            },
        ),
        level_scheme=LevelScheme(
            pdh_pdl_source="prior_day_full",
            session_levels=("asia_high", "asia_low", "london_high", "london_low", "pdh", "pdl"),
            available_from_guard=True,
        ),
        touch_rule=TouchRule(
            type="bar_intersect",
            bar_type="tick",
            zone_proximity_pts=ZONE_PROXIMITY_PTS,
            zone_representative_price="mean_of_constituent_levels",
            scope="first_touch_per_zone_per_day",
            direction_from_side={"LOW": "LONG", "HIGH": "SHORT"},
        ),
        feature_windows=FeatureWindows(
            interaction_window_minutes=5,
            approach_window_minutes=90,
            within_band_pts=2.0,
            level_proximity_pts=0.5,
            large_trade_threshold=10,
            mid_price_source="trade_price",
        ),
        label_policy=LabelPolicy(
            resolution="mae_first",
            entry_reference="realistic_at_decision",
            decision_offset_minutes=5,
            tp_points=15.0,
            sl_points=30.0,
            trap_mfe_min=5.0,
            forward_bar_type="tick",
            forward_cutoff="17:00_US/Eastern_ny_close",
            no_resolution_dropped=True,
        ),
        inference=InferencePolicy(
            eligible_class="tradeable_reversal",
            eligible_session="ny",
            confidence_gate=0.70,
        ),
    )


def _bar(timeframe_ticks: int, low_ticks: int, high_ticks: int, day: date, close_ts: datetime) -> Bar:
    return Bar(
        timeframe_ticks=timeframe_ticks,
        trading_day=day,
        bar_index=0,
        bar_id="b0",
        open_ts_utc=close_ts,
        close_ts_utc=close_ts,
        open_ticks=low_ticks,
        high_ticks=high_ticks,
        low_ticks=low_ticks,
        close_ticks=high_ticks,
        volume=2,
        trade_count=timeframe_ticks,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
    )


def test_plugin_touch_output_equals_direct_detect_touches() -> None:
    """The plugin's on_bar_closed touches == a direct detect_touches on the same bars+zones."""
    day = date(2026, 1, 6)
    close_ts = datetime(2026, 1, 6, 14, 2, tzinfo=UTC)
    # Two UNGATED levels (available_from=None → no look-ahead gate): a LOW at 100.0 and a
    # HIGH at 110.0. Gap 10 > ZONE_PROXIMITY_PTS so they form two separate zones.
    levels = (
        Level("pdl", 100.0, Side.LOW, None),
        Level("pdh", 110.0, Side.HIGH, None),
    )

    plugin = get_strategy("touch_reversal")()
    plugin.configure(_section(), _Ctx())
    plugin.set_static_levels(levels)

    tf = plugin.required_bars()[0].size
    # Bar range [99.0, 101.0] points straddles the LOW zone's rep price 100.0, not 110.0.
    low_ticks = round(99.0 / DEFAULT_TICK_SIZE)
    high_ticks = round(101.0 / DEFAULT_TICK_SIZE)
    bar = _bar(tf, low_ticks, high_ticks, day, close_ts)

    step = plugin.on_bar_closed(bar, _Ctx())
    plugin_touches = tuple(setup.touch for setup in step.setups)

    # Direct call on the SAME bar and the SAME zones, derived the identical way.
    direct_zones = build_zones(list(levels), zone_proximity_pts=ZONE_PROXIMITY_PTS)
    direct_touches = tuple(
        detect_touches((bar,), direct_zones, tick_size=DEFAULT_TICK_SIZE, trading_day=day)
    )

    # Byte-identical touches (Touch is a frozen dataclass; == compares all fields).
    assert plugin_touches == direct_touches
    assert len(plugin_touches) == 1
    assert plugin_touches[0].representative_price == 100.0
    assert plugin_touches[0].direction is Direction.LONG  # LOW touch → LONG
    # The plugin's decisions mirror the same touches one-for-one.
    assert tuple(decision.touch for decision in step.decisions) == direct_touches


def test_non_decision_bar_returns_empty_step() -> None:
    """A bar whose timeframe is not the decision timeframe yields an empty delta."""
    plugin = get_strategy("touch_reversal")()
    plugin.configure(_section(), _Ctx())
    plugin.set_static_levels((Level("pdl", 100.0, Side.LOW, None),))
    decision_tf = plugin.required_bars()[0].size
    bar = _bar(decision_tf + 1, round(99.0 / DEFAULT_TICK_SIZE), round(101.0 / DEFAULT_TICK_SIZE),
               date(2026, 1, 6), datetime(2026, 1, 6, 14, 2, tzinfo=UTC))
    step = plugin.on_bar_closed(bar, _Ctx())
    assert step.setups == ()
    assert step.decisions == ()


def test_registry_resolves_touch_reversal_and_fails_closed() -> None:
    """get_strategy resolves the registered plugin and fail-closes on an unknown id (A2)."""
    assert get_strategy("touch_reversal") is TouchReversalPlugin
    with pytest.raises(ContractError):
        get_strategy("does_not_exist")


def test_section_forbids_unknown_keys() -> None:
    """TouchReversalSection is extra='forbid' — an unknown key fails closed (A3)."""
    section = _section()
    assert section.touch_rule.zone_proximity_pts == ZONE_PROXIMITY_PTS
    with pytest.raises(ValidationError):
        TouchReversalSection.model_validate({**section.model_dump(), "bogus_key": 1})


def test_plugin_declarations_match_engine_constants() -> None:
    """feature_spec/label_policy declare the six features and the fixed-points barrier (A3)."""
    spec = TouchReversalPlugin.feature_spec()
    assert spec.names == (
        "int_time_beyond_level",
        "int_time_within_2pts",
        "int_absorption_ratio",
        "app_large_trade_vol_pct",
        "app_avg_trade_size",
        "app_max_spread",
    )
    policy = TouchReversalPlugin.label_policy()
    assert policy.barrier_mode == "fixed_points"
    # tp=15 / sl=30 anchored to constants.py (NOT a bundle's per-model value).
    assert policy.barrier.tp_points == 15.0
    assert policy.barrier.sl_points == 30.0
    # The barrier projects fixed points off the entry, direction-aware.
    assert policy.barrier.stop_price(100.0, Direction.LONG) == 70.0
    assert policy.barrier.target_price(100.0, Direction.LONG) == 115.0
```

### Trade-Lab  services/strategy_core_service.py  —  StrategyRuntime(...) construction + engine_version  (:89-119)

```python
    def __init__(
        self,
        *,
        requested_symbol: str | None,
        tick_timeframes: tuple[int, ...],
        recent_closed_bar_limit: int = 500,
        warning_limit: int = 100,
    ) -> None:
        self.requested_symbol = requested_symbol
        self._display_timeframes = tuple(sorted(set(tick_timeframes)))
        self._runtime = StrategyRuntime(
            requested_symbol=requested_symbol,
            timeframes=self._display_timeframes,
            # audit #5: PIN the decision bar to the smallest configured timeframe
            # explicitly instead of relying on StrategyRuntime's implicit min() fallback.
            # With the production Trade-Lab defaults this is the 147t contract bar,
            # preserving Strategy-Core bar-range touch semantics. Pinning it means a
            # future SMALLER display timeframe cannot silently shrink the decision bar
            # and degenerate the bar-range touch back to a one-print exact-touch path.
            decision_timeframe=min(self._display_timeframes),
            recent_closed_bar_limit=recent_closed_bar_limit,
            warning_limit=warning_limit,
        )
        self._last_trade: TradeEvent | None = None
        self._last_schema: str | None = None
        self._touch_sequence: dict[tuple[date, str], int] = {}

    @property
    def engine_version(self) -> str:
        return strategy_core.ENGINE_VERSION

```

---

## PART 2 — Greps (file:line: matched line)

### 2a. `_touched_zone_keys` across the Strategy-Core tree (.py)

```
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:208:          self._touched_zone_keys: set[tuple[date, tuple[str, ...], float, str]] = set()
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:220:          self._touched_zone_keys.clear()
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:289:                      self._touched_zone_keys.add(self._touch_zone_key_from_touch(touch, zones))
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:320:              if self._zone_key(trading_day, zone) in self._touched_zone_keys:
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:329:              if self._zone_key(trading_day, zone) in self._touched_zone_keys:
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\strategies\touch_reversal\plugin.py:241:          # (_touched_zone_keys) is runtime bookkeeping that the seam carries in Phase B.
C:\Users\gonza\Documents\Strategy-core\tests\test_runtime_touch_zones.py:77:      # (first-touch-per-cluster-per-day dedup via _touched_zone_keys).
```

### 2b. `.touched` (the Zone.touched flag) across the Strategy-Core tree (.py)

```
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\touch.py:87:              if zone.touched:
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\touch.py:97:                  zone.touched = True
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:67:          "touched": zone.touched,
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:321:                  zone.touched = True
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:330:                  zone.touched = True
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:100:      assert zone.touched is True
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:146:      assert low_zone.touched is True
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:147:      assert high_zone.touched is True
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:193:      assert zone.touched is False
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:36:      assert zones[0].touched is False
C:\Users\gonza\Documents\Strategy-core\validation\decision_diff_harness.py:417:      # 3. touches (fresh zones; detection mutates zone.touched, so rebuild)
```

### 2c. `detect_touches` / `build_zones` call sites — STRATEGY-CORE (.py)

```
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\__init__.py:91:  from strategy_core.decisions.touch import detect_touches, is_touch
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\__init__.py:92:  from strategy_core.decisions.zones import build_zones
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\__init__.py:133:      "build_zones",
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\__init__.py:135:      "detect_touches",
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\constants.py:227:  #: guard that, in engine v3, is ACTUALLY ENFORCED by detect_touches (v1/v2 emitted this
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\constants.py:234:  #: (strategy_core.decisions.touch.detect_touches; dashboard_utility_builder.py)
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\constants.py:241:  #: (dashboard_utility_builder.py _detect_touches; types.Zone docstring)
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\touch.py:4:  ``_detect_touches`` in Claude-Quant-Lab
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\touch.py:31:  __all__ = ["is_touch", "detect_touches"]
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\touch.py:47:  def detect_touches(
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\touch.py:57:      Ported from ``dashboard_utility_builder.py:414-440`` (``_detect_touches``).
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:3:  Single-sourced from the canonical research training path. ``build_zones`` is a
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:4:  byte-for-byte port of ``_build_zones`` in the dashboard utility builder, the
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:12:  lines 382-411 (``_build_zones``).
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:20:  __all__ = ["build_zones"]
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:23:  def build_zones(
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:38:      Mirrors ``_build_zones`` exactly
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:57:      # _build_zones:384-385 -- empty input is the empty list, not a single zone.
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:61:      # _build_zones:387 -- sort ascending by price; stable, mirrors the dict sort.
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:63:      # _build_zones:388 -- seed the first group with the lowest-priced level.
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:66:      # _build_zones:390-394 -- chained merge. The compare is against the LAST
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:78:          # _build_zones:398-399 -- representative price is the arithmetic mean.
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:81:          # _build_zones:400 -- names in group (price-sorted) order, as a tuple.
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:83:          # _build_zones:402-403 -- strict-majority side; ties (high_count not
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\decisions\zones.py:105:      # _build_zones:411 -- zones in the same ascending price order as the groups.
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\levels.py:11:  from strategy_core.decisions.zones import build_zones
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\levels.py:100:          return build_zones(list(self.levels()))
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:15:  from strategy_core.decisions.touch import detect_touches
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:287:                  detected = detect_touches((bar,), zones, tick_size=self.tick_size, trading_day=bar.trading_day)
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:310:          # availability before build_zones. Pre-filtering diverged from canonical
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:312:          # (_zones_for_snapshot below). detect_touches (decisions/touch.py:93) already
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:316:          from strategy_core.decisions.zones import build_zones
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\runtime\state.py:318:          zones = build_zones(list(self.level_state.levels()))
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\strategies\touch_reversal\plugin.py:7:  ``StrategyLevelState``/``build_zones``/``detect_touches`` — it wraps them in place).
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\strategies\touch_reversal\plugin.py:13:  sole importer, and it proves the wrapper's ``detect_touches`` output is byte-identical
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\strategies\touch_reversal\plugin.py:14:  to a direct ``detect_touches`` call on the same bars+zones.
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\strategies\touch_reversal\plugin.py:51:  from strategy_core.decisions.touch import detect_touches
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\strategies\touch_reversal\plugin.py:52:  from strategy_core.decisions.zones import build_zones
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\strategies\touch_reversal\plugin.py:239:          # (_zones_for_detection core, state.py:300-302), then detect_touches with the
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\strategies\touch_reversal\plugin.py:249:          zones = build_zones(list(self._levels.levels()), zone_proximity_pts=zone_proximity)
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\strategies\touch_reversal\plugin.py:250:          touches = detect_touches(
C:\Users\gonza\Documents\Strategy-core\src\strategy_core\types.py:154:      path). ``detect_touches`` skips a zone on any bar that closes before this instant.
C:\Users\gonza\Documents\Strategy-core\tests\test_runtime_touch_zones.py:5:  ``detect_touches`` gates each *merged* zone on its MAX availability -- rather than
C:\Users\gonza\Documents\Strategy-core\tests\test_runtime_touch_zones.py:6:  the old behavior of pre-filtering levels by availability before ``build_zones``
C:\Users\gonza\Documents\Strategy-core\tests\test_runtime_touch_zones.py:19:      # generated -- the two static levels are the only thing build_zones sees.
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:4:  ``dashboard_utility_builder.py:414-440`` (``_detect_touches``): closed-interval
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:14:  from strategy_core.decisions.touch import detect_touches, is_touch
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:82:  # ── detect_touches ──────────────────────────────────────────────────────────
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:90:      touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:110:      touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:125:      touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:136:      touches = detect_touches(
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:153:      touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:160:      touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:169:      touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:180:      touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:190:      touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:198:      touches = detect_touches([], [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch.py:207:      touches = detect_touches(
C:\Users\gonza\Documents\Strategy-core\tests\test_touch_reversal_plugin.py:1:  """A3 equivalence: the TouchReversalPlugin wrapper mirrors detect_touches exactly.
C:\Users\gonza\Documents\Strategy-core\tests\test_touch_reversal_plugin.py:3:  PLAN §7 Step A3 acceptance: the plugin's touch output equals a direct ``detect_touches``
C:\Users\gonza\Documents\Strategy-core\tests\test_touch_reversal_plugin.py:5:  wrapping ``build_zones → detect_touches`` behind the §2.2 plugin protocol is byte-faithful
C:\Users\gonza\Documents\Strategy-core\tests\test_touch_reversal_plugin.py:30:  from strategy_core.decisions.touch import detect_touches
C:\Users\gonza\Documents\Strategy-core\tests\test_touch_reversal_plugin.py:31:  from strategy_core.decisions.zones import build_zones
C:\Users\gonza\Documents\Strategy-core\tests\test_touch_reversal_plugin.py:134:  def test_plugin_touch_output_equals_direct_detect_touches() -> None:
C:\Users\gonza\Documents\Strategy-core\tests\test_touch_reversal_plugin.py:135:      """The plugin's on_bar_closed touches == a direct detect_touches on the same bars+zones."""
C:\Users\gonza\Documents\Strategy-core\tests\test_touch_reversal_plugin.py:159:      direct_zones = build_zones(list(levels), zone_proximity_pts=ZONE_PROXIMITY_PTS)
C:\Users\gonza\Documents\Strategy-core\tests\test_touch_reversal_plugin.py:161:          detect_touches((bar,), direct_zones, tick_size=DEFAULT_TICK_SIZE, trading_day=day)
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:1:  """Fidelity tests for ``build_zones`` against canonical ``_build_zones``.
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:13:  from strategy_core.decisions.zones import build_zones
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:26:      """_build_zones:384-385 -- no levels yields the empty list."""
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:27:      assert build_zones([]) == []
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:32:      zones = build_zones([_high("PDH", 100.0)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:41:      zones = build_zones([_high("a", 100.0), _high("b", 102.0)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:49:      zones = build_zones([_high("a", 100.0), _high("b", 103.01)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:58:      zones = build_zones([_high("a", 100.0), _high("b", 103.0)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:66:      zones = build_zones([_high("h", 100.0), _low("l", 101.0)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:73:      zones = build_zones([_high("h1", 100.0), _high("h2", 101.0), _low("l", 102.0)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:80:      zones = build_zones([_high("a", 100.0), _high("b", 101.0), _high("c", 103.0)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:91:      zones = build_zones([_low("a", 100.0), _low("b", 102.5), _low("c", 105.0)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:99:      zones = build_zones([_low("a", 100.0), _low("b", 102.0), _high("c", 106.0), _high("d", 108.0)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:107:      zones = build_zones([_high("hi", 110.0), _low("lo", 100.0)])
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:115:      assert len(build_zones(levels)) == 1
C:\Users\gonza\Documents\Strategy-core\tests\test_zones.py:116:      assert len(build_zones(levels, zone_proximity_pts=ZONE_PROXIMITY_PTS)) == 1
C:\Users\gonza\Documents\Strategy-core\validation\decision_diff_harness.py:43:    2. ZONES   = build_zones(levels).
C:\Users\gonza\Documents\Strategy-core\validation\decision_diff_harness.py:44:    3. TOUCHES = detect_touches(day_bars, zones, tick_size=0.25, trading_day=D).
C:\Users\gonza\Documents\Strategy-core\validation\decision_diff_harness.py:110:      build_zones,
C:\Users\gonza\Documents\Strategy-core\validation\decision_diff_harness.py:112:      detect_touches,
C:\Users\gonza\Documents\Strategy-core\validation\decision_diff_harness.py:342:      detect_touches ENFORCES the look-ahead guard. Names/sides match research
C:\Users\gonza\Documents\Strategy-core\validation\decision_diff_harness.py:415:      zones = build_zones(levels)
C:\Users\gonza\Documents\Strategy-core\validation\decision_diff_harness.py:418:      zones_for_touch = build_zones(levels)
C:\Users\gonza\Documents\Strategy-core\validation\decision_diff_harness.py:419:      touches = detect_touches(day_bars, zones_for_touch, tick_size=TICK_SIZE, trading_day=D)
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness.py:66:      build_zones,
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness.py:68:      detect_touches,
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness.py:338:      canon_zones_cmp = B._build_zones(levels)  # for comparison (not mutated by detection)
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness.py:340:      eng_zones_cmp = build_zones(eng_levels)
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness.py:348:      canon_zones_det = B._build_zones(levels)
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness.py:349:      canon_touches = B._detect_touches(bars_et, canon_zones_det)
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness.py:350:      eng_zones_det = build_zones(_canon_levels_to_engine(levels))
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness.py:351:      eng_touches = detect_touches(eng_bars, eng_zones_det, tick_size=CANON_TICK, trading_day=td)
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness.py:676:                   "strategy_core.detect_touches stamps each touch with `bar.close_ts_utc`, "
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness_v2.py:62:      build_zones,
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness_v2.py:64:      detect_touches,
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness_v2.py:770:      a_ok = _compare_zones(date_str, B._build_zones(levels), build_zones(_canon_levels_to_engine(levels)))
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness_v2.py:776:      canon_zones_det = B._build_zones(levels)
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness_v2.py:777:      canon_touches = B._detect_touches(bars_et, canon_zones_det)
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness_v2.py:778:      eng_zones_det = build_zones(_canon_levels_to_engine(levels))
C:\Users\gonza\Documents\Strategy-core\validation\parity_harness_v2.py:779:      eng_touches = detect_touches(eng_bars_et, eng_zones_det, tick_size=CANON_TICK, trading_day=td)
C:\Users\gonza\Documents\Strategy-core\validation\phase4b_validate.py:306:          zc = B._build_zones([dict(l) for l in levels])
C:\Users\gonza\Documents\Strategy-core\validation\phase4b_validate.py:307:          ze = sc.build_zones(levels_to_engine(levels))
C:\Users\gonza\Documents\Strategy-core\validation\phase4b_validate.py:313:          canon_t_same_bars = B._detect_touches(bars_et, [dict(z) for z in B._build_zones([dict(l) for l in levels])])
C:\Users\gonza\Documents\Strategy-core\validation\phase4b_validate.py:314:          eng_t_same_bars = sc.detect_touches(df_to_engine_bars(bars_et, day),
C:\Users\gonza\Documents\Strategy-core\validation\phase4b_validate.py:315:                                              sc.build_zones(levels_to_engine(levels)),
C:\Users\gonza\Documents\Strategy-core\validation\phase4b_validate.py:323:          canon_touches = B._detect_touches(bars_et, [dict(z) for z in B._build_zones([dict(l) for l in levels])])
C:\Users\gonza\Documents\Strategy-core\validation\phase4b_validate.py:324:          eng_touches = sc.detect_touches(df_to_engine_bars(eng_bars_et, day),
C:\Users\gonza\Documents\Strategy-core\validation\phase4b_validate.py:325:                                          sc.build_zones(levels_to_engine(levels)),
```

### 2d. `detect_touches` / `build_zones` call sites — QUANT-LAB (.py)

```
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\audit_NQ_20260602\enrich_dates.py:31:      build_zones,
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\audit_NQ_20260602\enrich_dates.py:32:      detect_touches,
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\audit_NQ_20260602\enrich_dates.py:144:      zones = build_zones(levels_to_engine(levels))
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\audit_NQ_20260602\enrich_dates.py:145:      touches = detect_touches(eng_bars, zones, tick_size=tick, trading_day=td)
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\audit_NQ_20260602\trace_leakage.py:17:  from strategy_core import build_zones, detect_touches
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\audit_NQ_20260602\trace_leakage.py:61:      touches = detect_touches(
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\audit_NQ_20260602\trace_leakage.py:63:          _zones := build_zones(levels_to_engine(levels)),
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\decision_repoint_proof.py:143:      legacy_zones = B._build_zones(levels)
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\decision_repoint_proof.py:144:      eng_zones = E.build_zones(E.levels_to_engine(levels))
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\decision_repoint_proof.py:150:      legacy_touches = B._detect_touches(bars_et, B._build_zones(levels))
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\decision_repoint_proof.py:151:      eng_touches = E.detect_touches(
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\decision_repoint_proof.py:153:          E.build_zones(E.levels_to_engine(levels)),
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\levels_probe\probe.py:5:  build_zones / is_touch / detect_touches) so diagnostics match the cached dataset. Scans EVERY
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\levels_probe\probe.py:24:  from strategy_core import build_zones
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\levels_probe\probe.py:103:      zones = build_zones(levels_to_engine(levels))  # PRODUCTION zone build
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\levels_probe\probe.py:157:          # recorded touch context (first straddle = the detect_touches record)
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\phase8_1_golden.py:40:  from strategy_core import build_zones, detect_touches, resolve_outcome  # noqa: E402
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\phase8_1_golden.py:82:      zones = build_zones(eng_levels)
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\phase8_1_golden.py:83:      touches = detect_touches(eng_bars, zones, tick_size=ED.TRADE_TICK, trading_day=td)
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\census_v3.py:29:  from strategy_core import build_zones, classify_session, detect_touches
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\census_v3.py:104:              zones_av = build_zones(levels_to_engine(levels, with_availability=True))
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\census_v3.py:106:              gated = detect_touches(
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\census_v3.py:108:                  build_zones(levels_to_engine(levels, with_availability=True)),
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\census_v3.py:112:              ungated = detect_touches(
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\census_v3.py:114:                  build_zones(levels_to_engine(levels, with_availability=False)),
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\ny_baseline_enrich.py:35:      build_zones,
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\ny_baseline_enrich.py:37:      detect_touches,
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\ny_baseline_enrich.py:119:      zones_av = build_zones(levels_to_engine(levels, with_availability=True))
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\ny_baseline_enrich.py:121:      zones = build_zones(levels_to_engine(levels, with_availability=True))
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\ny_baseline_enrich.py:122:      touches = detect_touches(eng_bars, zones, tick_size=tick, trading_day=td)
C:\Users\gonza\Documents\Claude-Quant-Lab\scripts\v3_verify\trace_20260603.py:4:  bar with the canonical engine ``classify_session`` (the same function detect_touches
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\dashboard_utility_builder.py:297:      zones = _build_zones(levels)
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\dashboard_utility_builder.py:298:      touches = _detect_touches(bars_et, zones)
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\dashboard_utility_builder.py:481:      look-ahead guard can gate detect_touches. PDH/PDL are the FULL prior trading day's
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\dashboard_utility_builder.py:492:          # bars' close_ts_utc are produced, so the detect_touches gate compares like
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\dashboard_utility_builder.py:558:  def _build_zones(levels: list[dict]) -> list[dict]:
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\dashboard_utility_builder.py:592:  def _detect_touches(
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:5:  ``dashboard_utility_builder.py`` (``_build_zones`` / ``_detect_touches`` /
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:9:  ``build_zones -> detect_touches -> resolve_outcome -> the 6 engine features``.
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:57:      build_zones,
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:59:      detect_touches,
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:148:      guard in ``detect_touches`` (a level cannot be touched before it exists). When
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:185:      Pipeline: ``build_zones -> detect_touches -> resolve_outcome -> the 6 engine
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:207:      # availability so detect_touches gates a touch to bars closing at/after the level's
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:212:      zones = build_zones(eng_levels)
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:213:      touches = detect_touches(eng_bars, zones, tick_size=tick_size, trading_day=td)
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\agents\data_infra\ml\engine_decision.py:416:      # that date is the ET-INDEXED bar_ts date (``_detect_touches`` set
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\dashboard\engine\level_engine.py:96:          self._rebuild_zones()
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\dashboard\engine\level_engine.py:120:          self._rebuild_zones()
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\dashboard\engine\level_engine.py:128:                  self._rebuild_zones()
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\dashboard\engine\level_engine.py:260:      def _rebuild_zones(self) -> None:
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\experiment\event_detection.py:51:  def build_zones(
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\experiment\event_detection.py:169:  def detect_touches_single_day(
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\experiment\event_detection.py:180:          zones: Pre-built zones for this day (from build_zones).
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\experiment\event_detection.py:274:          zones = build_zones(day_levels, date_str, proximity_threshold)
C:\Users\gonza\Documents\Claude-Quant-Lab\src\alpha_lab\experiment\event_detection.py:282:          day_events = detect_touches_single_day(bars, zones, date_str)
C:\Users\gonza\Documents\Claude-Quant-Lab\tests\agents\test_decision_repoint_parity.py:6:  (``_build_zones`` / ``_detect_touches`` / ``label_touch_event`` /
C:\Users\gonza\Documents\Claude-Quant-Lab\tests\agents\test_decision_repoint_parity.py:17:  ``detect_touches(tick_size=BOOK_MID_TICK)``,
C:\Users\gonza\Documents\Claude-Quant-Lab\tests\agents\test_decision_repoint_parity.py:201:      zones = B._build_zones(levels)
C:\Users\gonza\Documents\Claude-Quant-Lab\tests\agents\test_decision_repoint_parity.py:202:      touches = B._detect_touches(bars_et, zones)
C:\Users\gonza\Documents\Claude-Quant-Lab\tests\agents\test_decision_repoint_parity.py:258:      legacy_zones = B._build_zones(levels)
C:\Users\gonza\Documents\Claude-Quant-Lab\tests\agents\test_decision_repoint_parity.py:259:      eng_zones = E.build_zones(E.levels_to_engine(levels))
C:\Users\gonza\Documents\Claude-Quant-Lab\tests\agents\test_decision_repoint_parity.py:265:      legacy_touches = B._detect_touches(bars_et, B._build_zones(levels))
C:\Users\gonza\Documents\Claude-Quant-Lab\tests\agents\test_decision_repoint_parity.py:266:      eng_touches = E.detect_touches(
C:\Users\gonza\Documents\Claude-Quant-Lab\tests\agents\test_decision_repoint_parity.py:268:          E.build_zones(E.levels_to_engine(levels)),
```

### 2e. `detect_touches` / `build_zones` call sites — TRADE-LAB (.py)

```
C:\Users\gonza\Documents\Trade-Lab\backend\src\trade_lab\domain\levels.py:146:          touches = self._detect_touches(trade, trading_day, session)
C:\Users\gonza\Documents\Trade-Lab\backend\src\trade_lab\domain\levels.py:264:      def _detect_touches(
```

> Note: Trade-Lab's only `detect_touches` is its LEGACY local engine `domain/levels.py` (`_detect_touches`, the COLLAPSED/DELETED-in-plan path); TL does NOT call Strategy-Core's `detect_touches`/`build_zones` directly — it goes through `StrategyRuntime` via `StrategyCoreService`.

---

## PART 3 — Written trace (analysis)

### 1. Cross-bar re-fire suppression (once-per-zone-per-day): WHERE it lives

There are **two layers**, and the cross-bar layer lives in the **RUNTIME**, not in `detect_touches`:

- **Within a single `detect_touches` call** — the `Zone.touched` mutable flag (`types.py` Zone; read at `touch.py:87` `if zone.touched: continue`, written at `touch.py:97` `zone.touched = True`). This only suppresses a re-fire among the bars passed in ONE call. The runtime calls `detect_touches((bar,), zones, ...)` one bar at a time and **rebuilds the zone list fresh every bar** (`_zones_for_detection` → `build_zones(...)`, so every zone starts `touched=False`). So `Zone.touched` alone does **not** persist across bars.

- **Across bars / across the day** — the RUNTIME's `self._touched_zone_keys` set. It is:
  - **declared/initialized** at `state.py:208` (`self._touched_zone_keys: set[...] = set()`), **cleared** in `reset()` at `state.py:220`.
  - **WRITTEN** at `state.py:289`, immediately after a touch fires: `self._touched_zone_keys.add(self._touch_zone_key_from_touch(touch, zones))` (inside the `if self._plugin is None:` branch as of B1).
  - **READ** at `state.py:320` (in `_zones_for_detection`) and again at `state.py:329` (in `_zones_for_snapshot`). It is **NOT** write-only.

  The load-bearing READ is `_zones_for_detection` (state.py:319-321):
  ```python
          zones = build_zones(list(self.level_state.levels()))
          for zone in zones:
              if self._zone_key(trading_day, zone) in self._touched_zone_keys:
                  zone.touched = True
  ```
  i.e. each freshly-rebuilt zone whose key is already in `_touched_zone_keys` is **pre-marked `zone.touched = True`** so the subsequent `detect_touches` call skips it via its `if zone.touched: continue` guard. The snapshot read at `state.py:328-330` does the same re-marking for the snapshot/display path.

  **Plainly:** `detect_touches`/`Zone.touched` = within-call dedup; the runtime's `_touched_zone_keys` (write @289, read @320 & @329) = the cross-bar, once-per-cluster-per-day memory. The cross-bar suppression is RUNTIME state, applied by re-marking fresh zones BEFORE detection. **This is exactly the logic that has no home in the A3 plugin yet (deviation D-A3d) and is the central B2 design question.**

### 2. The A3 plugin's `on_bar_closed`: zones, dedup, and StrategyStep

- **Zones**: built from the plugin's OWN level state — `zones = build_zones(list(self._levels.levels()), zone_proximity_pts=zone_proximity)` (`plugin.py:249`), fresh every call (so `touched=False`). It never reads `ctx` for levels/zones (R2).
- **Cross-bar dedup**: the plugin **maintains NONE**. There is no `_touched_zone_keys` equivalent (the only occurrence of that name in `plugin.py` is a comment at `plugin.py:241`). So across multiple decision bars the plugin would **re-fire** a zone the runtime would suppress (D-A3d).
- **What it puts in `StrategyStep`**: NOTE — `StrategyStep` has **no `touches` field** (its fields are `setups`, `decisions`, `features`; see `protocols.py`). The plugin returns `StrategyStep(setups=..., decisions=..., features=())` where each `setup` is a concrete `TouchSetup` and each `decision` a `TouchDecision`, and **the raw `Touch` rides on those objects' `.touch` attribute** (`TouchSetup.touch` / `TouchDecision.touch`). So the touches are carried per-setup/per-decision, not in a `StrategyStep.touches` collection. **B2 must decide how the runtime recovers the raw `Touch` objects to populate `RuntimeUpdate.touches`** — read them off `step.setups[i].touch`, or add a `touches` field to `StrategyStep`.

### 3. Does `on_event` keep the plugin's level state current?

Yes — it mirrors the runtime's `self.level_state.process_trade(trade)` (state.py:280). In `plugin.py`:
```python
    def on_event(self, event: Trade | Quote, ctx: PlatformContext) -> tuple:
        if isinstance(event, Trade):
            self._levels.process_trade(event)
        return ()
```
So every trade is folded into `self._levels` (the plugin-owned `StrategyLevelState`), keeping PDH/PDL/asia/london levels current — but note that in the runtime today the level fold happens on the PLATFORM side (`state.py:280`), so B2 must decide whether the level fold moves into `plugin.on_event` or stays in the runtime (R1 says the plugin owns the level state; the wiring is the B2 decision).

### 4. The A3 equivalence test: same zone objects, or independent builds?

**Independent builds from the same level set** (NOT shared zone objects). The plugin builds its own zones internally from `self._levels` (seeded via `set_static_levels(levels)`), and the test builds a SEPARATE zone list for the direct call:
```python
    direct_zones = build_zones(list(levels), zone_proximity_pts=ZONE_PROXIMITY_PTS)   # test:159
    direct_touches = tuple(
        detect_touches((bar,), direct_zones, tick_size=DEFAULT_TICK_SIZE, trading_day=day)  # test:161
    )
```
Core assertions (test:163-167):
```python
    assert plugin_touches == direct_touches        # plugin_touches = tuple(s.touch for s in step.setups)
    assert len(plugin_touches) == 1
    assert plugin_touches[0].representative_price == 100.0
    assert plugin_touches[0].direction is Direction.LONG
```
Independent builds are deliberate: `detect_touches` MUTATES `zone.touched`, so sharing one zone list between the two paths would cross-contaminate (the first call would mark zones touched and starve the second). Because `build_zones` is deterministic over the same `levels`, the two independently-built zone lists are value-equal, and the touches compare equal. **Consequence for B2: this test proves only SINGLE-BAR, single-`detect_touches` equivalence with no cross-bar `_touched_zone_keys` involved — it does NOT exercise the cross-bar once-per-day dedup. B2 needs a multi-bar equivalence harness once the dedup placement is decided.**
