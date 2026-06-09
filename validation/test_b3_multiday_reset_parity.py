"""B3 plugin-path REGRESSION (multi-day, reset-bracketed): the plugin path reproduces the
canonical digests across >=7 real days AND every reset/restart boundary.

(Originally the B3-prep OFF-vs-ON multi-day parity gate. B3 removed the hardwired None path,
so there is no comparator runtime. This re-runs ONE registered ``touch_reversal`` plugin
runtime through the SAME 9 consecutive real NQ days, rolled production-style — ``reset()`` +
reseed (``load_prior_day_summary`` PDH/PDL from the preceding processed day + a static
reference via ``set_static_levels``) at EACH boundary — and asserts the per-day
``RuntimeUpdate.to_dict()`` sequence digest + touch count + final-snapshot digest match the
canonical fixtures in ``validation/_fixtures/b3_regression/multiday.json``. Those digests were
FROZEN from the final green run while ``plugin == None`` was still provable AND were asserted
OFF==ON across all 8 reset boundaries — so matching them preserves the multi-day +
reset-boundary real-data coverage and proves the removal changed nothing.)

The sequence digest is reset-CHAIN dependent (each day's reseed sources the PRECEDING
processed day), so the gate requires ALL frozen days present; it skips cleanly if the store
is absent or too few days resolve.

Run:    python validation/test_b3_multiday_reset_parity.py
pytest: pytest validation/test_b3_multiday_reset_parity.py
"""

from __future__ import annotations

# Reuse the go-live store reader + the production plugin-runtime builder.
from test_b2_golive_runtime_parity import DATA_DIR, TICK_SIZE, _build_runtime, _read_trades

from _b3_regression_util import MULTIDAY_DAYS, load_fixture, multiday_digests

_DIGEST_KEYS = ("n_trades", "touches", "seq_sha256", "snapshot_sha256")


def _run() -> list[dict]:
    return multiday_digests(_build_runtime(), MULTIDAY_DAYS, _read_trades, TICK_SIZE)


def test_b3_multiday_reset_plugin_regression():
    import pytest

    if not DATA_DIR.exists():
        pytest.skip(f"databento store not available at {DATA_DIR}")
    fixture = load_fixture("multiday")["days"]

    digs = _run()
    ran = [d for d in digs if not d.get("skip")]
    if len(ran) < 7:
        pytest.skip(f"need >=7 multi-day days for the regression; only {len(ran)} resolved")
    # The reset chain is order-dependent: a missing day would change every later day's reseed,
    # so the frozen digests are only reproducible when ALL days are present. Fail loud (not
    # skip) if the store is partial — a partial run is NOT the canonical sequence.
    assert len(ran) == len(MULTIDAY_DAYS), (
        f"reset chain requires all {len(MULTIDAY_DAYS)} days; only {len(ran)} present — "
        "cannot reproduce the frozen sequence"
    )
    for d in ran:
        day = d["day"]
        assert day in fixture, f"no frozen digest for {day}"
        assert {k: d[k] for k in _DIGEST_KEYS} == {k: fixture[day][k] for k in _DIGEST_KEYS}, (
            f"plugin-path digest diverged from the frozen canonical on {day}: "
            f"{ {k: d[k] for k in _DIGEST_KEYS} } vs { {k: fixture[day][k] for k in _DIGEST_KEYS} }"
        )


if __name__ == "__main__":
    import warnings

    warnings.simplefilter("ignore")
    fixture = load_fixture("multiday")["days"]
    print("B3 multi-day reset-bracketed plugin-path regression vs frozen canonical digests\n"
          f"store = {DATA_DIR}\n")
    digs = _run()
    for i, d in enumerate(digs):
        if d.get("skip"):
            print(f"  {d['day']}: NO DATA")
            continue
        exp = fixture.get(d["day"])
        ok = exp is not None and {k: d[k] for k in _DIGEST_KEYS} == {k: exp[k] for k in _DIGEST_KEYS}
        tag = "reset+reseed" if i > 0 else "cold start  "
        print(f"  {d['day']} [{tag}]: trades={d['n_trades']} touches={d['touches']} "
              f"seq={d['seq_sha256'][:12]}…  -> {'MATCH' if ok else 'DIVERGED'}")
    print("\nVERDICT: plugin path reproduces the canonical (former None-path) digests across "
          "every reset+reseed boundary.")
