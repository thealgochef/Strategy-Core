"""The ``touch_reversal`` plugin's typed contract SECTION (PLAN §2.4 / §4.3).

The contract split (PLAN §2.4, executed at E3 / contract v3) lifts the
strategy-specific groups out of the flat ``StrategyContract`` into a per-plugin
``SectionModel`` the strategy OWNS. For archetype 1 that section is
``TouchReversalSection``: it RE-PARENTS the existing canonical sub-models (each
already an ``extra="forbid"`` ``_ContractModel``) into one section, so this is a
re-parent, not a rewrite — and the platform never owns a second copy of these
fields to drift.

Classification by CONSUMER (the E3 ratified rule): the section holds exactly what
the PLUGIN consumes — ``session_scheme``, ``level_scheme``, ``touch_rule``,
``feature_windows``, the optional ``research_session_experiment``, and the
interaction/approach feature PARTITION (moved out of the envelope's
``feature_set``, which keeps only the platform-consumed shell). ``label_policy``
and ``inference`` are PLATFORM-consumed (TL builds the honest resolver and the
inference gate from them) and therefore live in the ENVELOPE, not here.

As of E3 this section is LOAD-BEARING: the loader's
``validate_section_via_registry`` hook validates every bundle's ``section``
subtree against this model (resolved via ``get_strategy(strategy_id).SectionModel``
— the §9.1 registry-time assertion made that resolvable), and the QL emitter
emits the subtree FROM a configured instance of this model.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field, model_validator

# Re-parent the CURRENT canonical contract sub-models (no rewrite). ``_ContractModel``
# is the shared ``extra="forbid", frozen=True`` base; importing it keeps the section's
# unknown-key fail-close identical to every other contract section.
from strategy_core.constants import (
    DEFAULT_APPROACH_WINDOW_MINUTES,
    DEFAULT_INTERACTION_WINDOW_MINUTES,
    DEFAULT_TICK_COUNT,
    INTERACTION_FEATURES,
    LEVEL_AVAILABLE_FROM_GUARD,
    LARGE_TRADE_THRESHOLD,
    LEVEL_PROXIMITY_PTS,
    MID_PRICE_SOURCE,
    PDH_PDL_SOURCE,
    RESEARCH_SESSION_SCHEME,
    RUNTIME_APPROACH_FEATURES,
    SESSION_LEVELS,
    TOUCH_SCOPE,
    TOUCH_TYPE,
    WITHIN_BAND_PTS,
    ZONE_PROXIMITY_PTS,
    ZONE_REPRESENTATIVE_PRICE,
)
from strategy_core.contract.schema import (
    ContractError,
    FeatureWindows,
    LevelScheme,
    ResearchSessionExperiment,
    SessionScheme,
    SessionWindow,
    TouchRule,
    _ContractModel,
)
from strategy_core.types import SessionScheme as RuntimeSessionScheme

__all__ = [
    "TouchReversalSection",
    "default_touch_reversal_section",
    "validate_feature_partition",
]


class TouchReversalSection(_ContractModel):
    """The archetype-1 (touch / zone-reversal) strategy-owned contract section (PLAN §2.4).

    Holds exactly the strategy-specific groups that moved out of the flat contract
    at E3: ``session_scheme``, ``level_scheme``, ``touch_rule``, ``feature_windows``,
    the interaction/approach feature partition (ex ``feature_set``), and the
    optional ``research_session_experiment``. ``extra="forbid"`` (via
    ``_ContractModel``) so any unknown key still fails closed.

    The partition validator here checks what the section can check ALONE (the two
    tuples are disjoint and duplicate-free); the cross-check against the ENVELOPE's
    ``feature_set.names`` is :func:`validate_feature_partition`, run at the two
    validation sites (QL emission, TL activation).
    """

    session_scheme: SessionScheme
    level_scheme: LevelScheme
    touch_rule: TouchRule
    feature_windows: FeatureWindows
    interaction_features: tuple[str, ...] = Field(max_length=256)
    approach_features: tuple[str, ...] = Field(max_length=256)
    research_session_experiment: ResearchSessionExperiment | None = None

    @model_validator(mode="after")
    def _partition_is_disjoint_and_duplicate_free(self) -> TouchReversalSection:
        split = (*self.interaction_features, *self.approach_features)
        if len(set(split)) != len(split):
            raise ValueError(
                "interaction_features and approach_features must be disjoint and "
                "duplicate-free"
            )
        return self


def validate_feature_partition(
    feature_names: Sequence[str], section: TouchReversalSection
) -> None:
    """The envelope<->section feature-partition cross-check (contract v3, E3).

    The section's ``interaction_features + approach_features`` must be EXACTLY the
    envelope's ``feature_set.names`` (same elements, same count — the moved
    semantics of the pre-v3 ``FeatureSet`` partition validator). Single-sourced
    here so the TWO validation sites (QL emission, TL activation) cannot drift.
    Raises :class:`ContractError` on a mismatch.
    """
    split = (*section.interaction_features, *section.approach_features)
    if set(split) != set(feature_names) or len(split) != len(feature_names):
        raise ContractError(
            "feature_set.names must be exactly the union of the section's "
            "interaction_features and approach_features"
        )


def _contract_scheme_from_runtime(scheme: RuntimeSessionScheme) -> SessionScheme:
    """Adapt a runtime ``types.SessionScheme`` (``datetime.time``) into its CONTRACT form
    (``"HH:MM"`` strings). The inverse of ``plugin._runtime_scheme_from_section``, so a
    section built from the runtime's scheme round-trips back to exactly that scheme (W5).

    Drop-nothing BOTH directions as of E3: a non-``None`` runtime ``closed_window``
    is carried as the contract scheme's optional ``closed_window`` start/end pair
    (closing the recorded round-trip gap for ``TRADE_LAB_CT_SESSION_SCHEME``).
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
        closed_window=(
            SessionWindow(
                start=scheme.closed_window[0].strftime("%H:%M"),
                end=scheme.closed_window[1].strftime("%H:%M"),
            )
            if scheme.closed_window is not None
            else None
        ),
    )


def default_touch_reversal_section() -> TouchReversalSection:
    """The canonical archetype-1 section matching the runtime's DEFAULT construction (W5).

    Its ``session_scheme`` round-trips to the runtime default ``RESEARCH_SESSION_SCHEME``
    (so the plugin's ``self._levels`` — the sole level fold since S-B3a — is built with
    the SAME scheme the runtime classifies sessions with), and
    ``touch_rule.zone_proximity_pts == ZONE_PROXIMITY_PTS`` (the ``build_zones`` default,
    so the section-driven DETECTION zones match the default-proximity zones
    ``StrategyLevelState.zones()`` builds for the snapshot). Every value is
    single-sourced from ``strategy_core.constants`` — no restated literals — and the QL
    emitter generates its emitted section from THIS default (overriding only the
    per-run config values). The non-detection fields are descriptive and do not affect
    the plugin's touch output.

    E3 ledger fix: ``touch_rule.bar_type`` defaults to the canonical production bar
    literal (``f"{DEFAULT_TICK_COUNT}t"`` = ``"147t"``, the same form Trade-Lab's
    ``parse_bar_type`` accepts), not the pre-E3 ``"tick"`` placeholder. The old
    ``label_policy.forward_bar_type="tick"`` landmine died with ``label_policy``'s
    move to the ENVELOPE (the section carries no label policy; the emitter sources
    ``forward_bar_type`` per-run).
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
            bar_type=f"{DEFAULT_TICK_COUNT}t",
            zone_proximity_pts=ZONE_PROXIMITY_PTS,
            zone_representative_price=ZONE_REPRESENTATIVE_PRICE,
            scope=TOUCH_SCOPE,
            # Ratified §3 (W1 P2c): the plugin OWNS the wire vocabulary — lowercase,
            # emitted verbatim into contracts and read directly by Trade-Lab.
            direction_from_side={"low": "long", "high": "short"},
        ),
        feature_windows=FeatureWindows(
            interaction_window_minutes=DEFAULT_INTERACTION_WINDOW_MINUTES,
            approach_window_minutes=DEFAULT_APPROACH_WINDOW_MINUTES,
            within_band_pts=WITHIN_BAND_PTS,
            level_proximity_pts=LEVEL_PROXIMITY_PTS,
            large_trade_threshold=LARGE_TRADE_THRESHOLD,
            mid_price_source=MID_PRICE_SOURCE,
        ),
        interaction_features=INTERACTION_FEATURES,
        approach_features=RUNTIME_APPROACH_FEATURES,
    )
