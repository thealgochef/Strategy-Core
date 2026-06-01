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

One structural addition over the canonical Trade-Lab source: ``StrategyContract``
gains a required ``engine_version`` field (spec §6) so each bundle explicitly binds
to the engine version that produced its labels/features. ``CONTRACT_VERSION`` and
``ENGINE_VERSION`` are imported from :mod:`strategy_core` (the package ``__init__``)
rather than restated, so the version stamps live in one place.

Ported from:
``backend/src/trade_lab/domain/contracts/strategy_contract.py:1-218`` (Trade-Lab).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from strategy_core import CONTRACT_VERSION, ENGINE_VERSION

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
    "Provenance",
    "ClassMap",
    "StrategyContract",
    "CONTRACT_VERSION",
    "ENGINE_VERSION",
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
    """Contractual feature vector. Ported from ``strategy_contract.py:37-52``."""

    names: tuple[str, ...] = Field(min_length=1, max_length=256)
    order_is_contractual: bool
    interaction_features: tuple[str, ...] = Field(max_length=256)
    approach_features: tuple[str, ...] = Field(max_length=256)
    nan_policy: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _names_partition_into_interaction_and_approach(self) -> FeatureSet:
        split = (*self.interaction_features, *self.approach_features)
        if set(split) != set(self.names) or len(split) != len(self.names):
            raise ValueError(
                "feature_set.names must be exactly the union of interaction_features "
                "and approach_features"
            )
        return self


class SessionWindow(_ContractModel):
    """Named session window (contract form). Ported from ``strategy_contract.py:55-58``."""

    start: str = Field(min_length=1, max_length=8)
    end: str = Field(min_length=1, max_length=8)
    crosses_midnight: bool = False


class SessionScheme(_ContractModel):
    """Session/trading-day scheme (contract form). Ported from ``strategy_contract.py:61-64``."""

    timezone: str = Field(min_length=1, max_length=64)
    trading_day_boundary: str = Field(min_length=1, max_length=8)
    sessions: dict[str, SessionWindow]


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
    """Forward-labeling policy. Ported from ``strategy_contract.py:91-99``."""

    resolution: str = Field(min_length=1, max_length=32)
    entry_reference: str = Field(min_length=1, max_length=64)
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
    """A fully parsed, validated ``strategy.json`` for one model bundle.

    Ported from ``strategy_contract.py:156-180`` with one required field added:
    ``engine_version`` (spec §6), placed right after ``contract_version``. It is the
    structural binding between a bundle and the engine version that produced its
    labels/features; Trade-Lab fail-closes on a mismatch via the loader hook.
    """

    contract_version: str = Field(min_length=1, max_length=64)
    engine_version: str = Field(min_length=1, max_length=64)
    strategy_id: str = Field(min_length=1, max_length=256)
    training_mode: str = Field(min_length=1, max_length=64)
    supported_by_runtime: bool
    instrument: str = Field(min_length=1, max_length=32)
    tick_size: float = Field(gt=0.0)
    point_value: float = Field(gt=0.0)
    model: Model
    feature_set: FeatureSet
    class_map: ClassMap
    session_scheme: SessionScheme
    level_scheme: LevelScheme
    touch_rule: TouchRule
    feature_windows: FeatureWindows
    label_policy: LabelPolicy
    inference: InferencePolicy
    data_requirements: DataRequirements
    provenance: Provenance

    @property
    def feature_count(self) -> int:
        return len(self.feature_set.names)
