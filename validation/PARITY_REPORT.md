# Strategy-Core Parity Report

Generated: 2026-06-01T02:20:51.599403+00:00
Engine: strategy_core vstrategy_core_engine_v1 (contract vtrade_lab_contract_v1)

Proves strategy-core reproduces the canonical dashboard-utility research pipeline on REAL NQ data. The canonical pipeline runs on BOOK-MID bars; those bars are represented LOSSLESSLY in the engine (tick_size=0.125), so any zones/touches/labels difference would be a PORT BUG. Feature *price-source* differences (stage F) are the deliberate trade-price change and are reported, not asserted.

- Days processed: 2025-06-02, 2025-06-03, 2025-06-04, 2025-06-05, 2025-06-06
- Total kept touches (canonical features not None): 22

## Stage results

| Stage | Scope | Total | Matched | Mismatched |
|-------|-------|------:|--------:|-----------:|
| A. ZONES | must_match | 26 | 26 | 0 |
| B. SESSIONS | must_match | 25000 | 25000 | 0 |
| C. TOUCHES | must_match | 22 | 22 | 0 |
| D. LABELS | must_match | 21 | 21 | 0 |
| E. INTERACTION FORMULA FIDELITY | must_match | 22 | 22 | 0 |
| F. INTERACTION TRADE-PRICE DIVERGENCE | expected_differ | 22 | 0 | 0 |
| G. APPROACH FEATURES (3 model features) | must_match | 22 | 22 | 0 |

## Must-match mismatches (concrete examples)

None. Every must-match stage is 100% matched.

## Expected-differ divergence distributions

Stage F feeds REAL TRADE prints (tick 0.25) where the canonical feature used BOOK-MID prints (tick 0.125). This is the deliberate price-source change. Distribution of `|engine_trade - canonical_book|`:

- samples (touches): 22
  - int_time_beyond_level: n=22 mean=0.7625 median=0.0000 max=7.2512
  - int_time_within_2pts: n=22 mean=5.2720 median=1.5547 max=46.9743
  - int_absorption_ratio: n=22 mean=0.1458 median=0.0003 max=1.0000

## Pinned open-item resolutions (applied)

1. **Touch timestamp = bar CLOSE (LAST(ts_event)).** The canonical tick-bar timestamp is the last event time of the bar (tick_store build_tick_bars: LAST(ts_event ORDER BY ts_event)). strategy_core.detect_touches stamps each touch with `bar.close_ts_utc`, which equals that close time. Stage C compares these as instant-equal and they match.
2. **Absorption size source.** The canonical interaction features use BOOK-EVENT size over book rows. The engine on the trade-price path uses TRADE size. That is a DELIBERATE divergence and is NOT forced to match: stage E proves the int_* FORMULA is faithful by feeding the SAME book rows to both, while stage F reports (does not assert) the trade-price divergence.

## VERDICT: PORT FIDELITY PROVEN
