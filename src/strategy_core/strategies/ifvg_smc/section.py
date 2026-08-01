"""Resolved IFVG v2 execution profile.

The v1 section described a wide capture envelope and expected stricter
strategies to be reconstructed with downstream filters. V2 makes sequential
behavior explicit: a section is the canonical *effective* configuration folded
by the reducer. Raw UI values and evaluator-only controls live in Quant-Lab and
cannot alter :func:`ifvg_profile_hash`.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import Field, model_validator

from strategy_core.candles._buckets import HTF_ANCHOR_POLICY
from strategy_core.constants import (
    IFVG_DOC_HTF_SELECTION_MAX_PER_TIMEFRAME,
    IFVG_DOC_MIN_GAP_TICKS,
    IFVG_DOC_OPPOSING_PARENT_DISTANCE_TICKS_MAX,
    IFVG_DOC_PARENT_HTF_DISTANCE_TICKS_MAX,
    IFVG_DOC_PARENT_REACTION_BARS,
    IFVG_DOC_POST_INVERSION_EXPIRY_1M_BARS_MAX,
    IFVG_DOC_SESSIONS,
    IFVG_DOC_SESSION_SCHEME,
    IFVG_ENTRY_FAMILIES,
    IFVG_HTF_REGISTRY_MAX_AGE_DAYS,
    IFVG_HTF_TIMEFRAMES,
    IFVG_LTF_REGISTRY_MAX_LIVE,
    IFVG_PARENT_TIMEFRAMES,
    IFVG_SL_BUFFER_TICKS,
    IFVG_SWING_POOL_MAX,
    IFVG_SWING_STRENGTH_BARS,
    IFVG_TP_R_MULTIPLE,
    TIME_TF_SECONDS,
)
from strategy_core.contract.schema import SessionScheme, _ContractModel
from strategy_core.strategies.touch_reversal.section import _contract_scheme_from_runtime

__all__ = [
    "IFVG_STRATEGY_ID",
    "IFVG_STRATEGY_VERSION",
    "QualificationMode",
    "CausalityPolicy",
    "OutsideSessionPolicy",
    "RetestTrigger",
    "ResolverPolicy",
    "IfvgSmcSection",
    "default_ifvg_smc_section",
    "legacy_ifvg_smc_section",
    "ict_clean_fresh_ifvg_smc_section",
    "ict_clean_retest_ifvg_smc_section",
    "weak_counter_displacement_ifvg_smc_section",
    "ifvg_profile_hash",
]

IFVG_STRATEGY_ID = "ifvg_smc"
IFVG_STRATEGY_VERSION = "2"


class QualificationMode(StrEnum):
    BROAD_CAPTURE = "broad_capture"
    DOC_DEFAULT = "doc_default"
    ICT_CLEAN = "ict_clean"
    CUSTOM_PROFILE = "custom_profile"


class CausalityPolicy(StrEnum):
    CONFIRMED_AFTER = "confirmed_after"
    FULLY_FORMED_AFTER = "fully_formed_after"


class OutsideSessionPolicy(StrEnum):
    KEEP_WAITING = "keep_waiting"
    RESET_SETUP_AS_MISSED = "reset_setup_as_missed"
    MARK_VISIBLE_IGNORED = "mark_visible_ignored"


class RetestTrigger(StrEnum):
    FIRST_TOUCH = "first_touch"
    FIRST_CE_TOUCH = "first_ce_touch"
    FIRST_FRACTIONAL_PENETRATION = "first_fractional_penetration"
    FIRST_REJECTION_CLOSE = "first_rejection_close"
    FIRST_DISPLACEMENT_AFTER_TOUCH = "first_displacement_after_touch"
    LEGACY_PLACEHOLDER_CANDIDATE_ONLY = "legacy_placeholder_candidate_only"


class ResolverPolicy(StrEnum):
    NEXT_1M_BAR_STOP_FIRST_V1 = "next_1m_bar_stop_first_v1"


class IfvgSmcSection(_ContractModel):
    """One resolved replay profile. All fields are load-bearing unless noted."""

    profile_name: str
    qualification_mode: QualificationMode
    runnable: bool
    non_runnable_reason: str | None = None
    execution_enabled: bool = True

    session_scheme: SessionScheme
    doc_sessions: dict[str, tuple[str, str]]
    enabled_entry_sessions: tuple[str, ...] = ("asia", "london", "ny")
    outside_session_policy: OutsideSessionPolicy = OutsideSessionPolicy.KEEP_WAITING

    enable_longs: bool = True
    enable_shorts: bool = False
    htf_timeframes: tuple[str, ...] = Field(min_length=1)
    parent_timeframes: tuple[str, ...] = Field(min_length=1)
    min_gap_ticks_capture: int = Field(ge=1)

    # The active reaction clock is in each parent's own timeframe. The legacy
    # global-minute field is retained only to read v1 profiles and is never
    # populated by a v2 executable profile.
    parent_reaction_window_parent_bars: int = Field(gt=0)
    parent_reaction_window_1m_bars_max: int | None = Field(default=None, gt=0)
    parent_retest_timeout_1m_bars: int | None = Field(default=None, gt=0)
    opposing_timeout_1m_bars: int | None = Field(default=None, gt=0)
    inversion_timeout_1m_bars: int | None = Field(default=None, gt=0)
    post_inversion_expiry_1m_bars_max: int = Field(gt=0)

    parent_htf_distance_ticks_max: int = Field(ge=0)
    opposing_parent_distance_ticks_max: int = Field(ge=0)
    entry_near_parent: bool = False
    entry_parent_distance_ticks_max: int | None = Field(default=None, ge=0)

    htf_registry_max_age_days: int | None = Field(default=None, gt=0)
    ltf_registry_max_live: int | None = Field(default=None, gt=0)
    htf_selection_max_per_timeframe: int = Field(gt=0)

    swing_strength_bars: int = Field(ge=1)
    swing_pool_max: int = Field(ge=1)
    sl_buffer_ticks: int = Field(ge=0)
    tp_r_multiple: float = Field(gt=0)
    break_even_enabled: bool = False

    entry_families: tuple[str, ...] = Field(min_length=1)
    entry_family: str
    retest_trigger: RetestTrigger
    label_family: str

    causality_parent: CausalityPolicy
    causality_opposing: CausalityPolicy
    causality_entry: CausalityPolicy
    anchor_policy: str = HTF_ANCHOR_POLICY
    resolver_policy: ResolverPolicy = ResolverPolicy.NEXT_1M_BAR_STOP_FIRST_V1

    parent_full_fill_invalidation: bool = True
    parent_structural_invalidation: bool = True
    max_executed_trades_per_day: int | None = Field(default=None, ge=1)
    legacy_candidate_row_limit: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_profile(self) -> "IfvgSmcSection":
        unknown = sorted(
            {
                "1m",
                *self.htf_timeframes,
                *self.parent_timeframes,
            }
            - set(TIME_TF_SECONDS)
        )
        if unknown:
            raise ValueError(f"unknown timeframe label(s) {unknown!r}")
        if self.entry_family not in self.entry_families:
            raise ValueError(
                f"entry_family {self.entry_family!r} is not declared in entry_families"
            )
        if self.runnable and not self.execution_enabled:
            raise ValueError("a runnable profile must have execution_enabled=true")
        if not self.runnable and not self.non_runnable_reason:
            raise ValueError("a non-runnable profile requires non_runnable_reason")
        if self.entry_near_parent and self.entry_parent_distance_ticks_max is None:
            raise ValueError(
                "entry_parent_distance_ticks_max is required when entry_near_parent=true"
            )
        return self

    @property
    def selected_entry_family(self) -> str:
        """Read-only v1 spelling; not serialized and not a second control."""
        return self.entry_family

    # Read-only aliases for old plugin/tests. V2 profiles use the explicitly
    # named nullable timeouts above.
    @property
    def lock_to_armed_1m_bars_max(self) -> int | None:
        return self.opposing_timeout_1m_bars

    @property
    def armed_to_inversion_1m_bars_max(self) -> int | None:
        return self.inversion_timeout_1m_bars

    def timeframe_seconds(self) -> tuple[int, ...]:
        labels = ("1m", *self.parent_timeframes, *self.htf_timeframes)
        return tuple(sorted({TIME_TF_SECONDS[label] for label in labels}))


def _base_profile(**updates: object) -> IfvgSmcSection:
    payload: dict[str, object] = {
        "profile_name": "ifvg_v2_doc_default_fresh_static_1r",
        "qualification_mode": QualificationMode.DOC_DEFAULT,
        "runnable": True,
        "execution_enabled": True,
        "session_scheme": _contract_scheme_from_runtime(IFVG_DOC_SESSION_SCHEME),
        "doc_sessions": {key: tuple(value) for key, value in IFVG_DOC_SESSIONS.items()},
        "enabled_entry_sessions": ("asia", "london", "ny"),
        "outside_session_policy": OutsideSessionPolicy.KEEP_WAITING,
        "enable_longs": True,
        "enable_shorts": False,
        "htf_timeframes": IFVG_HTF_TIMEFRAMES,
        "parent_timeframes": IFVG_PARENT_TIMEFRAMES,
        "min_gap_ticks_capture": IFVG_DOC_MIN_GAP_TICKS,
        "parent_reaction_window_parent_bars": IFVG_DOC_PARENT_REACTION_BARS,
        "parent_reaction_window_1m_bars_max": None,
        "parent_retest_timeout_1m_bars": None,
        "opposing_timeout_1m_bars": None,
        "inversion_timeout_1m_bars": None,
        "post_inversion_expiry_1m_bars_max": (
            IFVG_DOC_POST_INVERSION_EXPIRY_1M_BARS_MAX
        ),
        "parent_htf_distance_ticks_max": IFVG_DOC_PARENT_HTF_DISTANCE_TICKS_MAX,
        "opposing_parent_distance_ticks_max": (
            IFVG_DOC_OPPOSING_PARENT_DISTANCE_TICKS_MAX
        ),
        "entry_near_parent": False,
        "entry_parent_distance_ticks_max": None,
        "htf_registry_max_age_days": IFVG_HTF_REGISTRY_MAX_AGE_DAYS,
        "ltf_registry_max_live": IFVG_LTF_REGISTRY_MAX_LIVE,
        "htf_selection_max_per_timeframe": (
            IFVG_DOC_HTF_SELECTION_MAX_PER_TIMEFRAME
        ),
        "swing_strength_bars": IFVG_SWING_STRENGTH_BARS,
        "swing_pool_max": IFVG_SWING_POOL_MAX,
        "sl_buffer_ticks": IFVG_SL_BUFFER_TICKS,
        "tp_r_multiple": IFVG_TP_R_MULTIPLE,
        "break_even_enabled": False,
        "entry_families": IFVG_ENTRY_FAMILIES,
        "entry_family": "fresh_fvg_continuation",
        "retest_trigger": RetestTrigger.FIRST_TOUCH,
        "label_family": "candidate_static_r_long_form_v2",
        "causality_parent": CausalityPolicy.CONFIRMED_AFTER,
        "causality_opposing": CausalityPolicy.CONFIRMED_AFTER,
        "causality_entry": CausalityPolicy.CONFIRMED_AFTER,
        "anchor_policy": HTF_ANCHOR_POLICY,
        "resolver_policy": ResolverPolicy.NEXT_1M_BAR_STOP_FIRST_V1,
        "parent_full_fill_invalidation": True,
        "parent_structural_invalidation": True,
        "max_executed_trades_per_day": None,
        "legacy_candidate_row_limit": None,
    }
    payload.update(updates)
    return IfvgSmcSection.model_validate(payload)


def default_ifvg_smc_section() -> IfvgSmcSection:
    return _base_profile()


def legacy_ifvg_smc_section() -> IfvgSmcSection:
    return _base_profile(
        profile_name="ifvg_v1_legacy_candidate_stream",
        qualification_mode=QualificationMode.BROAD_CAPTURE,
        runnable=False,
        non_runnable_reason="v1 candidate stream is read-only and non-executable",
        execution_enabled=False,
        min_gap_ticks_capture=1,
        parent_reaction_window_1m_bars_max=480,
        parent_htf_distance_ticks_max=400,
        opposing_parent_distance_ticks_max=400,
        parent_retest_timeout_1m_bars=480,
        opposing_timeout_1m_bars=480,
        inversion_timeout_1m_bars=480,
        post_inversion_expiry_1m_bars_max=240,
        retest_trigger=RetestTrigger.LEGACY_PLACEHOLDER_CANDIDATE_ONLY,
        label_family="ifvg_v1_legacy_candidate_label",
    )


def ict_clean_fresh_ifvg_smc_section() -> IfvgSmcSection:
    return _base_profile(
        profile_name="ifvg_v2_ict_clean_fresh_static_1r",
        qualification_mode=QualificationMode.ICT_CLEAN,
        runnable=False,
        non_runnable_reason=(
            "same-reaction-leg, locality, and qualifying-sweep semantics are unresolved"
        ),
        execution_enabled=False,
        causality_parent=CausalityPolicy.FULLY_FORMED_AFTER,
        causality_opposing=CausalityPolicy.FULLY_FORMED_AFTER,
        causality_entry=CausalityPolicy.FULLY_FORMED_AFTER,
    )


def ict_clean_retest_ifvg_smc_section() -> IfvgSmcSection:
    return _base_profile(
        profile_name="ifvg_v2_ict_clean_pure_retest_static_1r",
        qualification_mode=QualificationMode.ICT_CLEAN,
        runnable=False,
        non_runnable_reason=(
            "pure retest trigger plus same-leg/locality/sweep semantics are unresolved"
        ),
        execution_enabled=False,
        entry_family="ifvg_retest",
        retest_trigger=RetestTrigger.FIRST_TOUCH,
        causality_parent=CausalityPolicy.FULLY_FORMED_AFTER,
        causality_opposing=CausalityPolicy.FULLY_FORMED_AFTER,
        causality_entry=CausalityPolicy.FULLY_FORMED_AFTER,
    )


def weak_counter_displacement_ifvg_smc_section() -> IfvgSmcSection:
    return _base_profile(
        profile_name="ifvg_v2_weak_counter_displacement_research",
        qualification_mode=QualificationMode.BROAD_CAPTURE,
        runnable=False,
        non_runnable_reason="weak counter-displacement is candidate-only research",
        execution_enabled=False,
    )


def ifvg_profile_hash(section: IfvgSmcSection) -> str:
    """SHA-256 of canonical resolved behavior only."""
    payload = json.dumps(
        section.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
