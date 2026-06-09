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
from strategy_core.constants import (
    DECISION_OFFSET_MINUTES,
    DEFAULT_APPROACH_WINDOW_MINUTES,
    DEFAULT_CONFIDENCE_GATE,
    DEFAULT_INTERACTION_WINDOW_MINUTES,
    DEFAULT_SL_POINTS,
    DEFAULT_TP_POINTS,
    DEFAULT_TRAP_MFE_MIN,
    DIRECTION_FROM_SIDE,
    INFERENCE_ELIGIBLE_SESSION,
    LEVEL_AVAILABLE_FROM_GUARD,
    LABEL_ENTRY_REFERENCE,
    LABEL_FORWARD_CUTOFF,
    LABEL_NO_RESOLUTION_DROPPED,
    LABEL_RESOLUTION,
    LARGE_TRADE_THRESHOLD,
    LEVEL_PROXIMITY_PTS,
    MID_PRICE_SOURCE,
    PDH_PDL_SOURCE,
    RESEARCH_SESSION_SCHEME,
    SESSION_LEVELS,
    TOUCH_SCOPE,
    TOUCH_TYPE,
    TRADEABLE_REVERSAL,
    WITHIN_BAND_PTS,
    ZONE_PROXIMITY_PTS,
    ZONE_REPRESENTATIVE_PRICE,
)
from strategy_core.contract.schema import (
    FeatureWindows,
    InferencePolicy,
    LabelPolicy,
    LevelScheme,
    ResearchSessionExperiment,
    SessionScheme,
    SessionWindow,
    TouchRule,
    _ContractModel,
)
from strategy_core.types import SessionScheme as RuntimeSessionScheme

__all__ = ["TouchReversalSection", "default_touch_reversal_section"]


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


def _contract_scheme_from_runtime(scheme: RuntimeSessionScheme) -> SessionScheme:
    """Adapt a runtime ``types.SessionScheme`` (``datetime.time``) into its CONTRACT form
    (``"HH:MM"`` strings). The inverse of ``plugin._runtime_scheme_from_section``, so a
    section built from the runtime's scheme round-trips back to exactly that scheme (W5).

    The contract form carries no ``closed_window``; the canonical research scheme has none,
    so the round-trip is identity for it. (A scheme with a non-``None`` ``closed_window``
    would not round-trip — not a production case; the touch strategy uses the research scheme.)
    """
    return SessionScheme(
        timezone=scheme.timezone,
        trading_day_boundary=scheme.trading_day_boundary.strftime("%H:%M"),
        sessions={
            name: SessionWindow(
                start=window.start.strftime("%H:%M"),
                end=window.end.strftime("%H:%M"),
                crosses_midnight=window.crosses_midnight,
            )
            for name, window in scheme.sessions.items()
        },
    )


def default_touch_reversal_section() -> TouchReversalSection:
    """The canonical archetype-1 section matching the runtime's DEFAULT construction (W5).

    Its ``session_scheme`` round-trips to the runtime default ``RESEARCH_SESSION_SCHEME``
    (so the plugin's ``self._levels`` is built with the SAME scheme as the runtime's
    ``level_state``), and ``touch_rule.zone_proximity_pts == ZONE_PROXIMITY_PTS`` (the
    ``build_zones`` default the runtime's ``_zones_for_detection`` uses). Every value is
    single-sourced from ``strategy_core.constants`` — no restated literals — so this is the
    same section the QL emitter will generate from the plugin (a later phase). The non-detection
    fields are descriptive and do not affect the plugin's touch output.
    """
    return TouchReversalSection(
        session_scheme=_contract_scheme_from_runtime(RESEARCH_SESSION_SCHEME),
        level_scheme=LevelScheme(
            pdh_pdl_source=PDH_PDL_SOURCE,
            session_levels=SESSION_LEVELS,
            available_from_guard=LEVEL_AVAILABLE_FROM_GUARD,
        ),
        touch_rule=TouchRule(
            type=TOUCH_TYPE,
            bar_type="tick",
            zone_proximity_pts=ZONE_PROXIMITY_PTS,
            zone_representative_price=ZONE_REPRESENTATIVE_PRICE,
            scope=TOUCH_SCOPE,
            direction_from_side={
                side.value: direction.value for side, direction in DIRECTION_FROM_SIDE.items()
            },
        ),
        feature_windows=FeatureWindows(
            interaction_window_minutes=DEFAULT_INTERACTION_WINDOW_MINUTES,
            approach_window_minutes=DEFAULT_APPROACH_WINDOW_MINUTES,
            within_band_pts=WITHIN_BAND_PTS,
            level_proximity_pts=LEVEL_PROXIMITY_PTS,
            large_trade_threshold=LARGE_TRADE_THRESHOLD,
            mid_price_source=MID_PRICE_SOURCE,
        ),
        label_policy=LabelPolicy(
            resolution=LABEL_RESOLUTION,
            entry_reference=LABEL_ENTRY_REFERENCE,
            decision_offset_minutes=DECISION_OFFSET_MINUTES,
            tp_points=DEFAULT_TP_POINTS,
            sl_points=DEFAULT_SL_POINTS,
            trap_mfe_min=DEFAULT_TRAP_MFE_MIN,
            forward_bar_type="tick",
            forward_cutoff=LABEL_FORWARD_CUTOFF,
            no_resolution_dropped=LABEL_NO_RESOLUTION_DROPPED,
        ),
        inference=InferencePolicy(
            eligible_class=TRADEABLE_REVERSAL,
            eligible_session=INFERENCE_ELIGIBLE_SESSION,
            confidence_gate=DEFAULT_CONFIDENCE_GATE,
        ),
    )
