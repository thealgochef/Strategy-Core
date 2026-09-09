# Strategy Core validation notes

This directory is an audit trail, not the current source of truth. Most stale v1/v2 phase reports were pruned from the working tree; use Git history only if old audit context is needed.

## How to read these files

  Current Core entry points are [README.md](../README.md),
  [package version stamps](../src/strategy_core/__init__.py),
  [contract schema](../src/strategy_core/contract/schema.py), and
  [IFVG context features](../docs/IFVG_CONTEXT_FEATURES.md).
  `../MIGRATION.md` and `../V3_COMPATIBILITY_MATRIX.md` are historical June 2026
  snapshots and do not establish current consumer compatibility.
  Retained `PHASE8*.md` files are historical snapshots from late validation phases. They intentionally mention old engine versions, old session windows, old cutoffs, book mid experiments, and intermediate blockers.
  Do **not** cite an older report as current behavior unless the current code still verifies it.

## Current state anchors

  `strategy_core.PLATFORM_VERSION`: `strategy_core_platform_v1` (the engine axis renamed at E1)
  `strategy_core.CONTRACT_VERSION`: `trade_lab_contract_v3` (platform envelope plus strategy-owned section).
  Touch-reversal defaults: ET `asia` 19:00→02:45, `london` 03:00→08:00, `ny` 09:00→17:00; 18:00 ET trading day boundary.
  Touch-reversal label defaults: realistic decision time entry at touch+5m, flatten at 16:40 ET, forward cutoff at 17:00 ET. IFVG has its own strategy section and R-relative outcome policy.
  Current test count: see CI — `python -m pytest -q` at the repo root collects `tests/` + `validation/`.

## Retained report categories

| File family | Use for | Caution |
|---|---|---|
| `PHASE8_REPORT.md`, `PHASE8_1_REPORT.md` | Late v2 trade bar and honest entry alignment / relocation history. | Superseded by v3 for sessions, availability, PDH/PDL, flatten/cutoff. |

When in doubt, read the current [constants](../src/strategy_core/constants.py),
[version stamps](../src/strategy_core/__init__.py), and
[contract schema](../src/strategy_core/contract/schema.py). Run focused tests
appropriate to the behavior being changed; the historical reports are not a
substitute for current verification.
