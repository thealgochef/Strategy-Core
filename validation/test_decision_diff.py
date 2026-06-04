"""STANDING TEST (phase 4f Part 2 / engine-v2 alignment): does the 147t trade-price
bar residual reach the DECISION layer under the HONEST decision-time rule?

This is the real test of the 4e/4f bar residual. It builds BOTH 147t trade-price
bar sets — RESEARCH (CQL DuckDB side-signed) and TRADE-LAB (streaming wire-order)
— on the SAME front-month trade set per day, runs the FULL strategy_core decision
pipeline (levels -> zones -> touches -> session eligibility -> HONEST decision-time
labels -> 6 features) on EACH bar set, and asserts the decision OUTPUTS are
identical (or differ only on a negligible, itemized handful with NO label flips,
the SAME survive/drop partition, and feature diffs below epsilon). It is NOT a
comparison to canonical / book-mid / the deployed model — strategy correctness is
out of scope.

ENGINE v2 honest labeling: per touch, decision_ts = touch close + DECISION_OFFSET
(5m); entry = realistic trade price at the decision instant; forward window =
(decision_ts, 16:15 ET]; touches whose decision_ts is at/after FLATTEN_TIME
(15:55 ET) get NO tradeable outcome (dropped). The 3 classes / tp=15 / sl=30 /
trap_mfe_min=5 / MAE-first are HELD EXACTLY. Labels under this rule DIFFER from the
OLD book-mid level-entry labels — that is the re-anchor, NOT drift.

No look-ahead: the feature window [touch, touch+offset] and the label window
(decision_ts, 16:15] do NOT overlap. No canonical/book-mid leakage: BOTH bar sets
are the new trade-price gate pair, and BOTH sides apply the SAME honest rule.

Run:    python validation/test_decision_diff.py
pytest: python -m pytest validation/test_decision_diff.py -q
Skips cleanly without the local databento store / Claude-Quant-Lab src.
"""
from __future__ import annotations

import sys
from pathlib import Path

CQL_SRC = r"C:/Users/gonza/Documents/Claude-Quant-Lab/src"
if CQL_SRC not in sys.path:
    sys.path.insert(0, CQL_SRC)

import decision_diff_harness as H  # noqa: E402  (sibling module in validation/)

CORE_DAYS = ["2025-07-15", "2025-07-07", "2025-07-11"]

# Acceptance epsilons for the standing assertion. The measured result is exact
# byte-identity on the 3 core days; these bounds give a tiny, explicit tolerance
# (a single itemized touch and a sub-epsilon feature wobble) without ever
# admitting a label flip or a material touch/zone divergence.
MAX_TOUCH_DIFF = 1          # at most one itemized non-matching touch per day
MAX_FEATURE_TOUCHES = 1     # at most one matched touch with any feature diff
FEATURE_EPS = 1e-6          # max abs feature diff allowed on a differing touch


def _store_available() -> bool:
    if not H.DATA_DIR.exists() or not Path(CQL_SRC).exists():
        return False
    try:
        import alpha_lab.agents.data_infra.tick_store  # noqa: F401
    except Exception:
        return False
    return True


def test_decision_diff_research_vs_tradelab():
    import pytest

    if not _store_available():
        pytest.skip("databento store or Claude-Quant-Lab src not available")

    ran = 0
    for day in CORE_DAYS:
        if not H._available(day):
            continue
        dd = H.diff_day(day)
        if dd.skip:
            continue
        ran += 1

        # bar counts must match (same trade set, same window) — the two pipelines
        # are diffable.
        assert dd.research_bars == dd.tradelab_bars, (
            f"{day}: bar-count mismatch research={dd.research_bars} "
            f"tradelab={dd.tradelab_bars}"
        )

        # LEVELS: the 6 session level prices (PDH/PDL/asia/london H/L) must match.
        # This is the upstream link — a session-defining bar diff would surface here.
        assert dd.levels_identical, f"{day}: session levels differ: {dd.level_detail}"

        # ZONES: same (representative_price, side, names) set.
        assert dd.zones_identical, f"{day}: zones differ: {dd.zone_detail}"

        # TOUCHES: at most a negligible itemized handful differ; both pipelines must
        # detect essentially the same first-touch events.
        assert dd.touches_differing <= MAX_TOUCH_DIFF, (
            f"{day}: {dd.touches_differing} touches differ (>{MAX_TOUCH_DIFF}): "
            f"{dd.touch_detail}"
        )

        # HONEST SURVIVE/DROP PARTITION (engine v2): the set of touches that yield a
        # tradeable outcome (decision_ts before flatten/cutoff, fill + forward exist)
        # must be IDENTICAL across the two bar sets. A divergence here would mean the
        # bar residual changed which touches are tradeable under the honest rule.
        assert dd.survive_set_identical, (
            f"{day}: honest survive/drop partition differs: {dd.survive_detail}"
        )

        # LABELS: NO label flips on any surviving matched touch. A flip means the bar
        # residual changed a model TARGET — that would warrant the emitter fix.
        # (These are the honest decision-time labels — re-anchored vs the OLD book-mid
        # level-entry labels by design; the comparison here is research-vs-tradelab on
        # the SAME rule, NOT new-vs-old.)
        assert dd.label_flips == 0, (
            f"{day}: {dd.label_flips} label flips: {dd.label_detail}"
        )

        # FEATURES: the 6 values match on all matched touches, except at most one
        # touch and only below epsilon. The streams are bar-set-independent; a
        # feature differs only if a touch anchor shifted.
        n_feat_touches = max((n for (_mx, n) in dd.feature_worst.values()), default=0)
        assert n_feat_touches <= MAX_FEATURE_TOUCHES, (
            f"{day}: {n_feat_touches} matched touches have feature diffs "
            f"(>{MAX_FEATURE_TOUCHES}): {dd.feature_detail}"
        )
        worst_mag = max((mx for (mx, _n) in dd.feature_worst.values()), default=0.0)
        assert worst_mag <= FEATURE_EPS, (
            f"{day}: feature diff magnitude {worst_mag} exceeds eps {FEATURE_EPS}: "
            f"{dd.feature_detail}"
        )

    if ran == 0:
        pytest.skip("no core sample days available in the local store")


if __name__ == "__main__":
    import warnings

    warnings.simplefilter("ignore")
    if not _store_available():
        print("SKIP: databento store or Claude-Quant-Lab src not available")
    else:
        for day in CORE_DAYS:
            if not H._available(day):
                print(f"  {day}: NO DATA")
                continue
            print(H._fmt_day(H.diff_day(day)))
        print("\n(standing assertions: levels/zones identical, <=1 touch diff, "
              "0 label flips, <=1 feature-touch below 1e-6)")
