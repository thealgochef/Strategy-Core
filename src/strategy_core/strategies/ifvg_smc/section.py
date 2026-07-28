"""The ``ifvg_smc`` strategy-owned contract SECTION — a CAPTURE PROFILE.

Unlike the touch section, nothing here encodes trade quality: every numeric
field is a WIDE capture bound (3–5x the ifvg-strat.md default, per the
ML-learns-the-discretion ruling) whose only job is to keep the one-setup FSM
finite. The doc's tuned values are recoverable downstream as row filters over
the emitted measurements. ``ifvg_profile_hash`` is the identity stamped on
every emission and folded into QL's capture-cache keys.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import Field

from strategy_core.constants import (
    IFVG_ARMED_TO_INVERSION_1M_BARS_MAX,
    IFVG_DOC_SESSIONS,
    IFVG_ENTRY_FAMILIES,
    IFVG_HTF_REGISTRY_MAX_AGE_DAYS,
    IFVG_HTF_TIMEFRAMES,
    IFVG_LABEL_FAMILY,
    IFVG_LOCK_TO_ARMED_1M_BARS_MAX,
    IFVG_LTF_REGISTRY_MAX_LIVE,
    IFVG_MIN_GAP_TICKS_CAPTURE,
    IFVG_OPPOSING_PARENT_DISTANCE_TICKS_MAX,
    IFVG_PARENT_HTF_DISTANCE_TICKS_MAX,
    IFVG_PARENT_REACTION_WINDOW_1M_BARS_MAX,
    IFVG_PARENT_TIMEFRAMES,
    IFVG_POST_INVERSION_EXPIRY_1M_BARS_MAX,
    IFVG_SELECTED_ENTRY_FAMILY,
    IFVG_SL_BUFFER_TICKS,
    IFVG_SWING_POOL_MAX,
    IFVG_SWING_STRENGTH_BARS,
    IFVG_TP_R_MULTIPLE,
    RESEARCH_SESSION_SCHEME,
    TIME_TF_SECONDS,
)
from strategy_core.contract.schema import SessionScheme, _ContractModel

# Reuse the ratified runtime->contract scheme adapter rather than restating it
# (single-source; it is module-internal to the touch section, same package tree).
from strategy_core.strategies.touch_reversal.section import _contract_scheme_from_runtime

__all__ = [
    "IFVG_STRATEGY_ID",
    "IFVG_STRATEGY_VERSION",
    "IfvgSmcSection",
    "default_ifvg_smc_section",
    "ifvg_profile_hash",
]

IFVG_STRATEGY_ID = "ifvg_smc"
#: Bumped on ANY semantics change of detection / reducer / labels (the QL
#: capture-cache key folds it).
IFVG_STRATEGY_VERSION = "1"


class IfvgSmcSection(_ContractModel):
    """Capture-profile section (``extra="forbid"`` via ``_ContractModel``)."""

    session_scheme: SessionScheme

    # structure capture
    htf_timeframes: tuple[str, ...] = Field(min_length=1)
    parent_timeframes: tuple[str, ...] = Field(min_length=1)
    min_gap_ticks_capture: int = Field(ge=1)

    # WIDE stage bounds (1m-bar clocks)
    parent_reaction_window_1m_bars_max: int = Field(gt=0)
    lock_to_armed_1m_bars_max: int = Field(gt=0)
    armed_to_inversion_1m_bars_max: int = Field(gt=0)
    post_inversion_expiry_1m_bars_max: int = Field(gt=0)

    # WIDE distance bounds (ticks)
    parent_htf_distance_ticks_max: int = Field(gt=0)
    opposing_parent_distance_ticks_max: int = Field(gt=0)

    # registry memory bounds
    htf_registry_max_age_days: int = Field(gt=0)
    ltf_registry_max_live: int | None = None

    # swing/sweep capture
    swing_strength_bars: int = Field(ge=1)
    swing_pool_max: int = Field(ge=1)

    # trade shape (label-family baseline; families sweep offline)
    sl_buffer_ticks: int = Field(ge=0)
    tp_r_multiple: float = Field(gt=0)

    # family declarations (explicit pooling, never silent)
    entry_families: tuple[str, ...] = Field(min_length=1)
    selected_entry_family: str
    label_family: str

    # ifvg-doc session windows, a FEATURE STAMP only ("HH:MM" ET pairs)
    doc_sessions: dict[str, tuple[str, str]]

    def timeframe_seconds(self) -> tuple[int, ...]:
        """All bar timeframes this profile consumes (1m decision + parents + HTF),
        ascending, deduplicated — the ``run_day``/warm-cache bar requirement."""
        labels = ("1m", *self.parent_timeframes, *self.htf_timeframes)
        unknown = [lbl for lbl in labels if lbl not in TIME_TF_SECONDS]
        if unknown:
            raise ValueError(f"unknown timeframe label(s) {unknown!r}")
        return tuple(sorted({TIME_TF_SECONDS[lbl] for lbl in labels}))


def default_ifvg_smc_section() -> IfvgSmcSection:
    """The canonical WIDE capture profile, single-sourced from constants."""
    return IfvgSmcSection(
        session_scheme=_contract_scheme_from_runtime(RESEARCH_SESSION_SCHEME),
        htf_timeframes=IFVG_HTF_TIMEFRAMES,
        parent_timeframes=IFVG_PARENT_TIMEFRAMES,
        min_gap_ticks_capture=IFVG_MIN_GAP_TICKS_CAPTURE,
        parent_reaction_window_1m_bars_max=IFVG_PARENT_REACTION_WINDOW_1M_BARS_MAX,
        lock_to_armed_1m_bars_max=IFVG_LOCK_TO_ARMED_1M_BARS_MAX,
        armed_to_inversion_1m_bars_max=IFVG_ARMED_TO_INVERSION_1M_BARS_MAX,
        post_inversion_expiry_1m_bars_max=IFVG_POST_INVERSION_EXPIRY_1M_BARS_MAX,
        parent_htf_distance_ticks_max=IFVG_PARENT_HTF_DISTANCE_TICKS_MAX,
        opposing_parent_distance_ticks_max=IFVG_OPPOSING_PARENT_DISTANCE_TICKS_MAX,
        htf_registry_max_age_days=IFVG_HTF_REGISTRY_MAX_AGE_DAYS,
        ltf_registry_max_live=IFVG_LTF_REGISTRY_MAX_LIVE,
        swing_strength_bars=IFVG_SWING_STRENGTH_BARS,
        swing_pool_max=IFVG_SWING_POOL_MAX,
        sl_buffer_ticks=IFVG_SL_BUFFER_TICKS,
        tp_r_multiple=IFVG_TP_R_MULTIPLE,
        entry_families=IFVG_ENTRY_FAMILIES,
        selected_entry_family=IFVG_SELECTED_ENTRY_FAMILY,
        label_family=IFVG_LABEL_FAMILY,
        doc_sessions={k: tuple(v) for k, v in IFVG_DOC_SESSIONS.items()},
    )


def ifvg_profile_hash(section: IfvgSmcSection) -> str:
    """sha256 of the canonical JSON dump — the profile identity on every record
    and in every day seed / QL cache key. Canonical form: sorted keys, compact
    separators, pydantic ``mode="json"`` (stable across sessions/platforms)."""
    payload = json.dumps(
        section.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
