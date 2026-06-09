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
