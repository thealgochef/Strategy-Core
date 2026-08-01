"""Frozen configuration and ordered registry for IFVG deterministic context."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from strategy_core.candles._buckets import HTF_ANCHOR_POLICY
from strategy_core.candles.exchange_calendar import (
    CALENDAR_POLICY_ID,
    SOURCE_GAP_POLICY_ID,
    CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
)
from strategy_core.structures.context import ContextIdentity, canonical_sha256

__all__ = [
    "CONTEXT_RECORD_SCHEMA_VERSION",
    "FEATURE_FORMULA_VERSION",
    "FEATURE_SCHEMA_HASH",
    "FEATURE_SET_VERSION",
    "ContextFeatureConfig",
    "FeatureDefinition",
    "build_context_identity",
    "build_feature_registry",
    "context_config_hash",
    "feature_schema_hash",
]

FEATURE_SET_VERSION = "ifvg_context_v1"
FEATURE_FORMULA_VERSION = "ifvg_context_formula_v2"
CONTEXT_RECORD_SCHEMA_VERSION = 2

_NORMALIZED_TO_BARSPEC = (
    ("1m", "1m", 60),
    ("3m", "3m", 180),
    ("5m", "5m", 300),
    ("10m", "10m", 600),
    ("15m", "15m", 900),
    ("30m", "30m", 1800),
    ("60m", "1H", 3600),
    ("240m", "4H", 14400),
)


@dataclass(frozen=True, slots=True)
class ContextFeatureConfig:
    feature_set_version: str = FEATURE_SET_VERSION
    feature_formula_version: str = FEATURE_FORMULA_VERSION
    normalized_timeframes: tuple[str, ...] = (
        "1m",
        "3m",
        "5m",
        "10m",
        "15m",
        "30m",
        "60m",
        "240m",
    )
    mtf_timeframes: tuple[str, ...] = (
        "3m",
        "5m",
        "10m",
        "15m",
        "30m",
        "60m",
        "240m",
    )
    local_execution_timeframe: str = "1m"
    anchor_policy: str = HTF_ANCHOR_POLICY
    require_complete_time_bars: bool = True
    shared_close_order_policy: str = "duration_descending_1m_last_v1"
    calendar_policy: str = CALENDAR_POLICY_ID
    calendar_schedule_hash: str = CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE.content_hash
    swing_strength: int = 3
    swing_capacity_per_timeframe: int = 64
    structure_policy: str = "strict_confirmed_close_break_v1"
    displacement_source_timeframe: str = "1m"
    displacement_windows: tuple[str, ...] = (
        "parent_reaction",
        "counter_leg",
        "inversion_response",
        "post_inversion",
    )
    source_gap_policy: str = SOURCE_GAP_POLICY_ID
    equal_level_tolerance_policy: str = "instrument_tick_grid_one_tick_span_v1"
    atr_scale_period: int = 14
    local_range_scale_period: int = 20
    pool_max_active_per_timeframe: int = 64
    pool_max_members: int = 16
    pool_max_unmatched_per_timeframe_side: int = 64
    pool_max_inactive_tombstones_per_timeframe: int = 64
    pool_lifecycle_policy: str = "no_time_expiry_no_merge_no_split_v1"
    sweep_reclaim_policy: str = "strict_bound_strict_close_reclaim_v1"
    capture_policy: str = "all_ifvg_context_transitions_v1"

    def __post_init__(self) -> None:
        if self.normalized_timeframes != (
            self.local_execution_timeframe,
            *self.mtf_timeframes,
        ):
            raise ValueError("normalized timeframes must be local 1m followed by ordered MTFs")
        if self.anchor_policy != HTF_ANCHOR_POLICY:
            raise ValueError("unsupported context anchor policy")
        if not self.require_complete_time_bars:
            raise ValueError("context v1 requires completed TIME bars")
        if self.calendar_policy != CALENDAR_POLICY_ID:
            raise ValueError("unsupported context exchange-calendar policy")
        if self.calendar_schedule_hash != CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE.content_hash:
            raise ValueError("context exchange-calendar snapshot hash mismatch")
        if self.source_gap_policy != SOURCE_GAP_POLICY_ID:
            raise ValueError("unsupported context source-gap policy")
        if self.equal_level_tolerance_policy != "instrument_tick_grid_one_tick_span_v1":
            raise ValueError("unsupported context equal-level tolerance policy")
        for name, value in (
            ("swing_strength", self.swing_strength),
            ("swing_capacity_per_timeframe", self.swing_capacity_per_timeframe),
            ("atr_scale_period", self.atr_scale_period),
            ("local_range_scale_period", self.local_range_scale_period),
            ("pool_max_active_per_timeframe", self.pool_max_active_per_timeframe),
            ("pool_max_members", self.pool_max_members),
            (
                "pool_max_unmatched_per_timeframe_side",
                self.pool_max_unmatched_per_timeframe_side,
            ),
            (
                "pool_max_inactive_tombstones_per_timeframe",
                self.pool_max_inactive_tombstones_per_timeframe,
            ),
        ):
            if value < 1:
                raise ValueError(f"{name} must be positive")

    @property
    def timeframe_map(self) -> tuple[tuple[str, str, int], ...]:
        return _NORMALIZED_TO_BARSPEC

    def seconds_for(self, normalized: str) -> int:
        for name, _label, seconds in self.timeframe_map:
            if name == normalized:
                return seconds
        raise KeyError(f"unknown normalized timeframe: {normalized!r}")

    def label_for(self, normalized: str) -> str:
        for name, label, _seconds in self.timeframe_map:
            if name == normalized:
                return label
        raise KeyError(f"unknown normalized timeframe: {normalized!r}")


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    feature_name: str
    feature_family: str
    data_type: str
    units: str
    raw_or_setup_normalized: str
    formula_key: str
    validity_rule: str


_STRUCTURE_FIELDS = (
    ("swing_sequence_state", "enum", "state", "raw", "SV"),
    ("high_relationship", "enum", "relationship", "raw", "SV"),
    ("low_relationship", "enum", "relationship", "raw", "SV"),
    ("structure_direction", "enum", "direction", "raw", "SV"),
    ("last_break_type", "enum", "event_type", "raw", "SV"),
    ("last_break_direction", "enum", "direction", "raw", "BR"),
    ("bars_since_break", "uint32", "bars", "raw", "BR"),
    ("minutes_since_break", "float64", "minutes", "raw", "BR"),
    ("last_confirmed_swing_high_ticks", "int64", "ticks", "raw", "SV"),
    ("last_confirmed_swing_low_ticks", "int64", "ticks", "raw", "SV"),
    ("state_age_bars", "uint32", "bars", "raw", "SV"),
    ("structure_alignment", "int8?", "sign", "setup", "SV"),
    ("break_alignment", "int8?", "sign", "setup", "BR"),
    ("state_valid", "bool", "flag", "raw", "always"),
    ("anchor_status", "enum", "status", "raw", "always"),
)

_SUMMARY_FIELDS = (
    ("aligned_tf_count", "uint8", "timeframes", "setup"),
    ("conflicting_tf_count", "uint8", "timeframes", "setup"),
    ("neutral_tf_count", "uint8", "timeframes", "setup"),
    ("valid_tf_count", "uint8", "timeframes", "raw"),
    ("break_aligned_tf_count", "uint8", "timeframes", "setup"),
    ("break_conflicting_tf_count", "uint8", "timeframes", "setup"),
    ("highest_aligned_tf_seconds", "uint32?", "seconds", "setup"),
    ("highest_conflicting_tf_seconds", "uint32?", "seconds", "setup"),
    ("lowest_conflicting_tf_seconds", "uint32?", "seconds", "setup"),
    ("contiguous_alignment_span", "uint8", "timeframes", "setup"),
    ("contiguous_conflict_span", "uint8", "timeframes", "setup"),
    ("adjacent_tf_transition_count", "uint8", "pairs", "setup"),
    ("lower_support_higher_conflict", "bool?", "flag", "setup"),
    ("lower_conflict_higher_support", "bool?", "flag", "setup"),
    ("execution_pullback_inside_htf_trend", "bool?", "flag", "setup"),
    ("execution_expansion_against_htf_trend", "bool?", "flag", "setup"),
)

_DELTA_FIELDS = (
    "changed_timeframe_count",
    "support_to_conflict_count",
    "conflict_to_support_count",
    "direction_flip_count",
    "newly_confirmed_break_count",
)

_DISPLACEMENT_FIELDS = (
    "observed_bar_count",
    "expected_eligible_bar_count",
    "missing_bar_count",
    "wall_elapsed_minutes",
    "eligible_elapsed_minutes",
    "range_ticks_mean",
    "range_ticks_min",
    "range_ticks_max",
    "body_ticks_sum",
    "upper_wick_ticks_mean",
    "lower_wick_ticks_mean",
    "true_range_ticks_mean",
    "body_fraction_mean",
    "body_fraction_min",
    "body_fraction_max",
    "upper_wick_fraction_mean",
    "lower_wick_fraction_mean",
    "directional_wick_fraction_mean",
    "opposing_wick_fraction_mean",
    "raw_close_location_mean",
    "expected_close_location_mean",
    "setup_close_location_mean",
    "overlap_fraction_mean",
    "bullish_bar_count",
    "bearish_bar_count",
    "doji_bar_count",
    "directional_bar_count",
    "opposing_bar_count",
    "directional_bar_fraction",
    "opposing_bar_fraction",
    "max_consecutive_directional_bars",
    "directional_body_ticks_sum",
    "opposing_body_ticks_sum",
    "raw_close_progress_ticks_mean",
    "expected_close_progress_ticks_mean",
    "setup_close_progress_ticks_mean",
    "raw_net_move_ticks",
    "expected_net_move_ticks",
    "setup_net_move_ticks",
    "raw_net_move_normalized",
    "expected_net_move_normalized",
    "setup_net_move_normalized",
    "raw_velocity_normalized",
    "expected_velocity_normalized",
    "setup_velocity_normalized",
    "path_efficiency_abs",
    "raw_path_efficiency_signed",
    "expected_path_efficiency_signed",
    "setup_path_efficiency_signed",
    "max_pullback_ticks",
    "max_pullback_fraction",
    "bullish_fvg_count",
    "bearish_fvg_count",
    "directional_fvg_count",
    "opposing_fvg_count",
    "bullish_fvg_width_sum_ticks",
    "bearish_fvg_width_sum_ticks",
    "directional_fvg_width_sum_ticks",
    "opposing_fvg_width_sum_ticks",
    "directional_fvg_width_sum_normalized",
    "directional_gap_density",
)

_POOL_SELECTOR_FIELDS = (
    "pool_present",
    "pool_id",
    "pool_type",
    "source_timeframe_seconds",
    "distance_ticks",
    "distance_normalized_by_atr",
    "swing_count",
    "age_minutes",
    "span_minutes",
    "width_ticks",
    "width_normalized_by_atr",
    "creation_separation_ticks",
    "creation_separation_normalized_by_atr",
    "creation_separation_normalized_by_local_range",
)

_OPPOSING_LINK_FIELDS = (
    "qualifying_sweep_count",
    "sweep_link_present",
    "pool_id",
    "pool_type",
    "source_timeframe_seconds",
    "distance_at_lock_ticks",
    "distance_at_lock_normalized",
    "sweep_depth_ticks",
    "sweep_depth_normalized",
    "reclaimed_after_sweep",
    "reclaim_latency_bars",
    "reclaim_close_distance_ticks",
    "reclaim_close_distance_normalized",
)


def _definition(
    name: str,
    family: str,
    data_type: str,
    units: str,
    normalization: str,
    validity: str,
    *,
    formula_version: str = FEATURE_FORMULA_VERSION,
) -> FeatureDefinition:
    return FeatureDefinition(
        feature_name=name,
        feature_family=family,
        data_type=data_type,
        units=units,
        raw_or_setup_normalized=normalization,
        formula_key=f"{formula_version}:{name}",
        validity_rule=validity,
    )


def build_feature_registry(
    config: ContextFeatureConfig | None = None,
) -> tuple[FeatureDefinition, ...]:
    """Expand the four finite templates in the contract's required order."""

    cfg = config or ContextFeatureConfig()
    out: list[FeatureDefinition] = []
    for timeframe in cfg.mtf_timeframes:
        for field, dtype, units, normalization, validity in _STRUCTURE_FIELDS:
            out.append(
                _definition(
                    f"mtf_structure.{timeframe}.{field}",
                    "structure",
                    dtype,
                    units,
                    normalization,
                    validity,
                    formula_version=cfg.feature_formula_version,
                )
            )
    for field, dtype, units, normalization, validity in _STRUCTURE_FIELDS:
        out.append(
            _definition(
                f"local_execution_structure.{field}",
                "local_structure",
                dtype,
                units,
                normalization,
                validity,
                formula_version=cfg.feature_formula_version,
            )
        )
    for field, dtype, units, normalization in _SUMMARY_FIELDS:
        out.append(
            _definition(
                f"mtf_structure.{field}",
                "structure_summary",
                dtype,
                units,
                normalization,
                "summary",
                formula_version=cfg.feature_formula_version,
            )
        )
    for delta in ("tap_to_lock", "lock_to_opposing", "opposing_to_inversion", "inversion_to_entry"):
        for field in _DELTA_FIELDS:
            out.append(
                _definition(
                    f"structure_change.{delta}.{field}",
                    "structure_delta",
                    "uint8",
                    "count",
                    "setup" if "conflict" in field or "support" in field else "raw",
                    "both_endpoints_valid",
                    formula_version=cfg.feature_formula_version,
                )
            )
    for window in cfg.displacement_windows:
        for field in _DISPLACEMENT_FIELDS:
            dtype = "float64" if any(
                token in field
                for token in ("mean", "fraction", "normalized", "efficiency", "velocity", "minutes")
            ) else "int64"
            out.append(
                _definition(
                    f"displacement.{window}.{field}",
                    "displacement_fvg" if "fvg" in field or "gap_density" in field else "displacement",
                    dtype,
                    "contracted",
                    "setup" if field.startswith("setup_") else (
                        "expected_leg" if field.startswith(("expected_", "directional_", "opposing_", "max_pullback")) else "raw"
                    ),
                    "window_metric",
                    formula_version=cfg.feature_formula_version,
                )
            )
    for selector in (
        "nearest_eqh",
        "nearest_eql",
        "nearest_thesis_supporting",
        "nearest_thesis_opposing",
    ):
        for field in _POOL_SELECTOR_FIELDS:
            out.append(
                _definition(
                    f"equal_levels.{selector}.{field}",
                    "equal_level_context",
                    "typed",
                    "contracted",
                    "setup" if "thesis" in selector else "raw",
                    "POOL",
                    formula_version=cfg.feature_formula_version,
                )
            )
    out.append(
        _definition(
            "equal_levels.containing_pool_count",
            "equal_level_context",
            "uint16",
            "pools",
            "raw",
            "always",
            formula_version=cfg.feature_formula_version,
        )
    )
    for field in _OPPOSING_LINK_FIELDS:
        out.append(
            _definition(
                f"equal_levels.opposing_leg.{field}",
                "equal_level_sweep",
                "typed",
                "contracted",
                "setup",
                "LINK",
                formula_version=cfg.feature_formula_version,
            )
        )
    names = [item.feature_name for item in out]
    if len(names) != len(set(names)):
        raise AssertionError("context feature registry contains duplicate names")
    return tuple(out)


def context_config_hash(config: ContextFeatureConfig) -> str:
    return canonical_sha256(asdict(config))


def _schema_payload(config: ContextFeatureConfig) -> dict[str, Any]:
    return {
        "feature_set_version": config.feature_set_version,
        "feature_formula_version": config.feature_formula_version,
        "context_record_schema_version": CONTEXT_RECORD_SCHEMA_VERSION,
        "ordered_expanded_feature_definitions": build_feature_registry(config),
        "normalized_timeframe_to_barspec_map": config.timeframe_map,
        "local_execution_timeframe": config.local_execution_timeframe,
        "mtf_timeframes": config.mtf_timeframes,
        "anchor_policy_and_status": {
            "policy": config.anchor_policy,
            "240m": "experimental_q40_open",
            "other": "ratified",
        },
        "swing_confirmation_policy": {
            "strength": config.swing_strength,
            "capacity": config.swing_capacity_per_timeframe,
            "ties": "reject",
        },
        "structure_break_policy": config.structure_policy,
        "displacement_window_contract": {
            "windows": config.displacement_windows,
            "bounds": "(B0,end]",
        },
        "eligible_bucket_policy": {
            "complete_only": config.require_complete_time_bars,
            "order": config.shared_close_order_policy,
            "gap": config.source_gap_policy,
            "calendar_policy": config.calendar_policy,
            "calendar_schedule_hash": config.calendar_schedule_hash,
        },
        "equal_level_tolerance_policy": config.equal_level_tolerance_policy,
        "observational_scale_periods": {
            "atr": config.atr_scale_period,
            "local_range": config.local_range_scale_period,
        },
        "pool_assignment_and_lifecycle_policy": config.pool_lifecycle_policy,
        "capacity_limits": {
            "active": config.pool_max_active_per_timeframe,
            "members": config.pool_max_members,
            "unmatched": config.pool_max_unmatched_per_timeframe_side,
            "tombstones": config.pool_max_inactive_tombstones_per_timeframe,
        },
    }


def feature_schema_hash(config: ContextFeatureConfig | None = None) -> str:
    return canonical_sha256(_schema_payload(config or ContextFeatureConfig()))


# Frozen literal generated from the implemented ordered registry.  The assertion is
# deliberately import-time and side-effect-free: an edit to any load-bearing registry
# or policy must update the reviewed literal rather than silently changing identity.
FEATURE_SCHEMA_HASH = "5e56063984841b7a8ada99cc36fbccf6c912a09b14b4d5dd50d0bcbf1294cda3"
if FEATURE_SCHEMA_HASH != "TO_BE_FROZEN" and feature_schema_hash() != FEATURE_SCHEMA_HASH:
    raise RuntimeError("implemented context registry does not match frozen schema hash")


def build_context_identity(
    config: ContextFeatureConfig,
    *,
    symbol: str,
    tick_size: str = "0.25",
    strategy_core_commit: str = "0" * 40,
    strategy_core_source_tree_hash: str = "0" * 64,
) -> ContextIdentity:
    schema_hash = feature_schema_hash(config)
    if FEATURE_SCHEMA_HASH != "TO_BE_FROZEN" and config == ContextFeatureConfig():
        if schema_hash != FEATURE_SCHEMA_HASH:
            raise RuntimeError("implemented context registry does not match frozen schema hash")
    return ContextIdentity(
        schema_version=CONTEXT_RECORD_SCHEMA_VERSION,
        feature_set_version=config.feature_set_version,
        feature_formula_version=config.feature_formula_version,
        feature_schema_hash=schema_hash,
        context_config_hash=context_config_hash(config),
        strategy_core_commit=strategy_core_commit,
        strategy_core_source_tree_hash=strategy_core_source_tree_hash,
        symbol=symbol,
        tick_size=tick_size,
    )
