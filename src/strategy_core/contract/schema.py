"""Pydantic models mirroring ``strategy.json`` -- the SINGLE contract definition.

Promoted verbatim from Trade-Lab's
``backend/src/trade_lab/domain/contracts/strategy_contract.py`` (the whole file),
so the contract *format* lives exactly once and cannot drift between the research
emitter (Claude-Quant-Lab) and the live/replay loader (Trade-Lab).

Pydantic is used here because contracts live at a trust boundary: they are
authored externally (by Claude-Quant-Lab) and shipped with each model bundle, so
they must be parsed strictly and rejected loudly on drift. Nothing in this module
loads the CatBoost binary or computes features; it only describes and validates
the contract that later inference stages consume.

Structural additions over the canonical Trade-Lab source (contract v2, E1):
``StrategyContract`` carries the two-axis binding (decision 9.3) — a required
``platform_version`` field (ex ``engine_version``, spec §6) binding each bundle to
the platform that produced its labels/features, plus required
``strategy_id``/``strategy_version`` binding it to the registered plugin.
``CONTRACT_VERSION`` and ``PLATFORM_VERSION`` are imported from
:mod:`strategy_core` (the package ``__init__``) rather than restated, so the
version stamps live in one place.

Contract v3 (E3 — the envelope/section split, PLAN §2.4): ``StrategyContract`` is
now the platform-consumed ENVELOPE only. The plugin-consumed groups
(``session_scheme``/``level_scheme``/``touch_rule``/``feature_windows``/
``research_session_experiment`` + the interaction/approach feature partition)
moved into ONE ``section`` subtree, carried here as a RAW mapping and typed by
the owning plugin's ``SectionModel`` (validated via the loader's opt-in
``validate_section_via_registry`` hook). Classification rule: a field lives in
the envelope iff the PLATFORM consumes it; a field the plugin consumes lives in
its section.

Ported from:
``backend/src/trade_lab/domain/contracts/strategy_contract.py:1-218`` (Trade-Lab).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from strategy_core import CONTRACT_VERSION, PLATFORM_VERSION

__all__ = [
    "ContractError",
    "Model",
    "FeatureSet",
    "SessionWindow",
    "SessionScheme",
    "LevelScheme",
    "TouchRule",
    "FeatureWindows",
    "LabelPolicy",
    "InferencePolicy",
    "DataRequirements",
    "ResearchSessionExperiment",
    "Provenance",
    "ClassMap",
    "StrategyContract",
    "CONTRACT_VERSION",
    "PLATFORM_VERSION",
]


class ContractError(ValueError):
    """Raised when a ``strategy.json`` fails to parse or violates the contract.

    Ported from ``strategy_contract.py:21-22``.
    """


class _ContractModel(BaseModel):
    """Base for contract sections: forbid unknown keys so drift is never silent.

    Ported from ``strategy_contract.py:25-28``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class Model(_ContractModel):
    """Model bundle descriptor. Ported from ``strategy_contract.py:31-34``."""

    type: str = Field(min_length=1, max_length=32)
    loss_function: str = Field(min_length=1, max_length=32)
    file: str = Field(min_length=1, max_length=128)


class FeatureSet(_ContractModel):
    """Contractual feature vector SHELL. Ported from ``strategy_contract.py:37-52``.

    Contract v3 (E3): the interaction/approach partition is PLUGIN semantics, so it
    moved into the strategy-owned section (``TouchReversalSection`` for archetype 1)
    together with its partition validator. The cross-check that the section's
    partition is exactly ``names`` runs at the two validation sites (QL emission,
    TL activation) via the section's ``validate_feature_partition`` helper — the
    envelope alone cannot check it because the partition no longer lives here.
    """

    names: tuple[str, ...] = Field(min_length=1, max_length=256)
    order_is_contractual: bool
    nan_policy: str = Field(min_length=1, max_length=32)


class SessionWindow(_ContractModel):
    """Named session window (contract form). Ported from ``strategy_contract.py:55-58``."""

    start: str = Field(min_length=1, max_length=8)
    end: str = Field(min_length=1, max_length=8)
    crosses_midnight: bool = False


class SessionScheme(_ContractModel):
    """Session/trading-day scheme (contract form). Ported from ``strategy_contract.py:61-64``.

    Contract v3 (E3): gains the OPTIONAL ``closed_window`` — a start/end pair
    (carried as a :class:`SessionWindow`; its ``crosses_midnight`` flag is not
    meaningful for a closed window and stays at its ``False`` default) — so the
    runtime ``types.SessionScheme.closed_window`` (e.g. the Chicago-clock
    ``TRADE_LAB_CT_SESSION_SCHEME``'s 16:00-18:00 halt) round-trips drop-nothing
    through ``_contract_scheme_from_runtime`` / ``_runtime_scheme_from_section``.
    """

    timezone: str = Field(min_length=1, max_length=64)
    trading_day_boundary: str = Field(min_length=1, max_length=8)
    sessions: dict[str, SessionWindow]
    closed_window: SessionWindow | None = None


class LevelScheme(_ContractModel):
    """Level construction scheme. Ported from ``strategy_contract.py:67-70``."""

    pdh_pdl_source: str = Field(min_length=1, max_length=64)
    session_levels: tuple[str, ...] = Field(max_length=64)
    available_from_guard: bool


class TouchRule(_ContractModel):
    """First-touch detection rule. Ported from ``strategy_contract.py:73-79``."""

    type: str = Field(min_length=1, max_length=32)
    bar_type: str = Field(min_length=1, max_length=16)
    zone_proximity_pts: float = Field(ge=0.0)
    zone_representative_price: str = Field(min_length=1, max_length=64)
    scope: str = Field(min_length=1, max_length=64)
    direction_from_side: dict[str, str]


class FeatureWindows(_ContractModel):
    """Feature window/threshold parameters. Ported from ``strategy_contract.py:82-88``.

    ``mid_price_source`` stays a free string field (typed only by length): the VALUE
    ``"trade_price"`` is set by the research emitter, not validated here.
    """

    interaction_window_minutes: int = Field(gt=0, le=1440)
    approach_window_minutes: int = Field(gt=0, le=1440)
    within_band_pts: float = Field(ge=0.0)
    level_proximity_pts: float = Field(ge=0.0)
    large_trade_threshold: int = Field(gt=0)
    mid_price_source: str = Field(min_length=1, max_length=32)


class LabelPolicy(_ContractModel):
    """Forward-labeling policy. Ported from ``strategy_contract.py:91-99``.

    Engine v2 additive field: ``decision_offset_minutes`` -- minutes AFTER the touch
    at which the decision fires (= the interaction window), single-sourced by the
    emitter from ``strategy_core.constants.DECISION_OFFSET_MINUTES``. It pins the
    honest-entry re-anchor: the label is measured from the realistic price at
    touch+offset (``entry_reference == "realistic_at_decision"``), and the feature
    window [touch, touch+offset] and label window (touch+offset, cutoff] do not
    overlap. Typed only by range here; the VALUE is set by the research emitter.
    """

    resolution: str = Field(min_length=1, max_length=32)
    #: Contract v3 (E3): how the tp/sl/trap thresholds are interpreted —
    #: "fixed_points" (absolute points off the entry, today's only implemented
    #: barrier, ``FixedPointsBarrier``) or "r_relative" (thresholds expressed in
    #: R-multiples; declared for forward compatibility, no producer emits it yet).
    #: Closes the Phase-D named debt that the Barrier abstraction had no contract
    #: field to bind to.
    barrier_mode: Literal["fixed_points", "r_relative"] = "fixed_points"
    entry_reference: str = Field(min_length=1, max_length=64)
    decision_offset_minutes: int = Field(gt=0, le=1440)
    tp_points: float = Field(gt=0.0)
    sl_points: float = Field(gt=0.0)
    trap_mfe_min: float = Field(ge=0.0)
    forward_bar_type: str = Field(min_length=1, max_length=16)
    forward_cutoff: str = Field(min_length=1, max_length=64)
    no_resolution_dropped: bool


class InferencePolicy(_ContractModel):
    """Runtime inference gating. Ported from ``strategy_contract.py:102-105``."""

    eligible_class: str = Field(min_length=1, max_length=64)
    eligible_session: str = Field(min_length=1, max_length=32)
    confidence_gate: float = Field(ge=0.0, le=1.0)


class DataRequirements(_ContractModel):
    """Live/replay data needs. Ported from ``strategy_contract.py:108-112``."""

    min_book_level: str = Field(min_length=1, max_length=8)
    live_schemas: tuple[str, ...] = Field(max_length=16)
    replay_schemas: tuple[str, ...] = Field(max_length=16)
    depth_usage: str = Field(min_length=1, max_length=32)


class ResearchSessionExperiment(_ContractModel):
    """Research-only train/evaluation/gate session scope emitted by Quant-Lab.

    This does not make a bundle runtime-supported. It records which Strategy-Core
    sessions were used for model refit, reported OOS stats, and confidence-gated
    research metrics so experimental bundles remain auditable.
    """

    training_sessions: tuple[str, ...] = Field(min_length=1, max_length=3)
    evaluation_sessions: tuple[str, ...] = Field(min_length=1, max_length=3)
    production_gate_sessions: tuple[str, ...] = Field(min_length=1, max_length=3)
    report_session_breakdowns: bool = True


class Provenance(_ContractModel):
    """Training provenance. Ported from ``strategy_contract.py:115-117``."""

    dataset_config_hash: str = Field(min_length=1, max_length=64)
    catboost: dict[str, Any]


class ClassMap(_ContractModel):
    """The integer class index -> human label map from the model bundle.

    Stored as a model (not a bare dict) so a contract with a malformed class map
    is rejected at parse time and ``labels`` can expose an ordered, contiguous view.

    Ported from ``strategy_contract.py:120-153``.
    """

    model_config = ConfigDict(frozen=True)

    mapping: dict[int, str]

    @model_validator(mode="before")
    @classmethod
    def _coerce_string_keys(cls, value: Any) -> Any:
        # strategy.json encodes class indices as JSON object keys (strings).
        if isinstance(value, dict) and "mapping" not in value:
            return {"mapping": value}
        return value

    @model_validator(mode="after")
    def _classes_are_contiguous_from_zero(self) -> ClassMap:
        keys = sorted(self.mapping)
        if not keys or keys != list(range(len(keys))):
            raise ValueError("class_map indices must be contiguous and start at 0")
        if len(set(self.mapping.values())) != len(self.mapping):
            raise ValueError("class_map labels must be unique")
        return self

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(self.mapping[index] for index in range(len(self.mapping)))

    def __len__(self) -> int:
        return len(self.mapping)


class StrategyContract(_ContractModel):
    """The platform-consumed ENVELOPE of a ``strategy.json`` (contract v3, E3).

    Two-axis version binding (decision 9.3, contract v2): ``platform_version``
    (ex ``engine_version``) binds the bundle to the shared platform that produced
    its labels/features, and ``strategy_id``/``strategy_version`` bind it to the
    registered plugin. ``strategy_id`` is the REGISTRY ROUTER KEY — it must
    resolve via ``strategies.registry.get_strategy`` (it is no longer the bundle
    name; bundle identity stays the directory name). Consumers fail-close on a
    mismatch of either axis (loader hook for the platform; activation gate for
    the strategy).

    Envelope/section split (contract v3, E3): every field declared here is
    PLATFORM-consumed. The plugin-consumed groups live in the ONE ``section``
    subtree — a RAW mapping at this layer (the envelope stays strategy-agnostic),
    typed by ``get_strategy(strategy_id).SectionModel`` when the loader is called
    with ``validate_section_via_registry=True``. The typed instance then rides
    this object as the private ``_section_model`` attribute, exposed read-only via
    :attr:`section_model` (a deliberate NON-FIELD carrier: the loader keeps its
    plain single-return call shape and hookless callers never see it).
    """

    contract_version: str = Field(min_length=1, max_length=64)
    platform_version: str = Field(min_length=1, max_length=64)
    strategy_id: str = Field(min_length=1, max_length=256)
    strategy_version: str = Field(min_length=1, max_length=64)
    training_mode: str = Field(min_length=1, max_length=64)
    supported_by_runtime: bool
    instrument: str = Field(min_length=1, max_length=32)
    tick_size: float = Field(gt=0.0)
    point_value: float = Field(gt=0.0)
    model: Model
    class_map: ClassMap
    feature_set: FeatureSet
    label_policy: LabelPolicy
    inference: InferencePolicy
    data_requirements: DataRequirements
    provenance: Provenance
    #: The strategy-owned subtree, raw. The envelope never interprets it; the
    #: loader's registry hook (or the owning plugin) validates it as SectionModel.
    section: Mapping[str, Any]

    _section_model: Any = PrivateAttr(default=None)

    @property
    def section_model(self) -> BaseModel:
        """The typed, plugin-validated section instance (loader-hook carrier).

        Populated ONLY by ``load_strategy_contract(...,
        validate_section_via_registry=True)``. Accessing it on a hooklessly loaded
        contract raises :class:`ContractError` (fail closed — never hand back an
        unvalidated section as if it were typed).
        """
        if self._section_model is None:
            raise ContractError(
                "contract section has not been registry-validated; load with "
                "validate_section_via_registry=True to populate section_model"
            )
        return self._section_model

    @property
    def feature_count(self) -> int:
        return len(self.feature_set.names)
