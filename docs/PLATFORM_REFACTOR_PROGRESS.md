# Platform + Strategy-Plugin SDK — Migration PROGRESS (execution log)

This is the **living execution log** for the migration specified in
`docs/PLATFORM_REFACTOR_PLAN.md`. The PLAN is the authoritative spec and must **NOT**
be edited. This PROGRESS doc tracks state, decisions-as-applied, clarifications, and
deviations.

---

## How to update (follow on EVERY step)

- Move each step's **Status** through `NOT STARTED → IN PROGRESS → DONE` (or `BLOCKED`).
- On completing a step, record: **date**, **commit SHA**, **files touched**, the
  **parity/golden harnesses you ACTUALLY RAN and that passed** (by name), and **any
  deviation** from the plan/decisions.
- **NEVER mark a step DONE** unless the harnesses REQUIRED FOR THAT STEP (per PLAN §7)
  are green AND were actually run. If any required harness is red OR could not be run
  (e.g. missing data), set the step **BLOCKED** with the reason and do not proceed.
  Do NOT claim a harness is green that you did not run.
- Keep the **"Current state"** line accurate. Record deviations and clarifications
  **HERE**, never by editing the plan.

---

## Current state

- **Active phase:** B in progress.
- **Next step:** B2.
- **Drift-net status:** B1: None-path byte-identical (char-level proof + green None-path tests); full SC suite 140 passed; TL cross-runtime acceptance + replay 3 passed vs branch SC; money-path GATE harnesses (test_production_pair_parity, test_duckdb_streaming_parity, test_decision_diff) ran GREEN this session (local databento store + alpha_lab present). Verified 2026-06-08.
- **Last-verified date:** 2026-06-08
- **Note (B2 gating):** B2 is gated on (a) the local data/model zip for the money-path GATE harnesses and (b) the architect's design decision on gate/dedup placement (how much touch logic moves into the plugin vs stays in the runtime) — B2 must not start until both are resolved. (Re (a): the GATE store/data was confirmed present and the GATE harnesses ran green this session; (b) the gate/dedup placement decision — esp. the cross-bar `_touched_zone_keys` first-touch dedup, per deviation D-A3d — remains OPEN and is required before B2.)

---

## Decisions ratified (record verbatim)

- **9.1** = Protocol (+registry-time assertion).
- **9.2** = in-package registry module.
- **9.3** = two-axis version (platform_version + per-plugin strategy_version).
- **9.4** = time-bars land in Phase F.
- **9.5** = keep `strategy_core` name, layout `strategy_core/strategies/<id>/`.
- **9.6** = declare+SHA-pin strategy-core in Quant-Lab.
- **9.7** = delete TL's local contract copy.
- **9.8** = Option A (Barrier abstraction + retire TL outcome tracker, lands in the C/D band).
- **9.9** = parameterize the session-name set.
- **9.10** = quote accessor on PlatformContext.

**§3 correction (already in the plan):** Direction (LONG/SHORT) stays PLATFORM; Side
(HIGH/LOW) → touch PLUGIN with Level/Touch; DIRECTION_FROM_SIDE moves to the plugin with
Side (QL emitter sources it from the plugin, not platform constants). Honored when the
move-map executes (Phase B+).

---

## Plan clarifications (authoritative resolutions — recorded here, not in the plan)

The plan has 3 internal inconsistencies; the owner ratified that **the §3.1 move-map
TABLE wins** wherever prose conflicts. These resolutions are authoritative for the
implementation:

- **R1 — LEVEL OWNERSHIP.** §3.1 is authoritative — `StrategyLevelState` is **PLUGIN-owned**,
  configured in `configure(section, ctx)`. §4.1's prose "the level fold stays on the
  PLATFORM side" is OVERRIDDEN. *(Applied: the touch plugin owns `self._levels` and folds
  trades into it via `on_event`.)*
- **R2 — PlatformContext SURFACE.** `PlatformContext` = EXACTLY §2.2 (`tick_size`,
  `point_value`, `closed_bars(label)`, `current_bar(label)`, `trade_price_at(ts)`,
  `session_at(ts)`) PLUS `quotes_in_window(...)` (§9.10). NO levels accessor and NO
  scheme attribute were added. The §4.2 sketch's `ctx.scheme` / `ctx.levels_for(...)` are
  ERRORS: the plugin gets the scheme from `section.session_scheme` and gets levels/zones
  from its OWN `self._levels`, never from `ctx`.
- **R3 — NO NEW CONTRACT FIELDS.** `TouchRule` has no `decision_tf` (verified §4.3 fields:
  type, bar_type, zone_proximity_pts, zone_representative_price, scope,
  direction_from_side). The §4.2 sketch's `touch_rule.decision_tf` is an ERROR. The
  decision timeframe is a construct/config value as today (`state.py:188`:
  `decision_timeframe = decision_timeframe or min(timeframes)`); `required_bars()` returns
  ONE TICK `BarSpec` at that value.
- **ADDITIVE COROLLARY.** Phase A does NOT physically move `StrategyLevelState` (or
  `build_zones`/`detect_touches`/`resolve_outcome`/features) out of their current modules
  — the move happens in the move-map execution (Phase B+). In Phase A the plugin IMPORTS
  the existing symbols from their current locations and instantiates/calls them.
- **Slotting:** 9.10 is implemented in A1 (`PlatformContext.quotes_in_window`). 9.9
  (data-drive the session-name set; drop hardcoded `"asia"`/`"london"` at `levels.py:49`)
  is an ADDED step NOT in PLAN §7 and is NOT part of Phase A (it modifies
  `StrategyLevelState`); it lands when `StrategyLevelState` becomes plugin-owned / as prep
  before Phase F.

### Phase A — additional deviations / clarifications (additive, behavior-preserving)

- **D-A1 (A1):** `StrategyStep` is a concrete `frozen` dataclass (default-constructible to
  an empty delta, per A1's explicit requirement), modelled on `RuntimeUpdate`; §2.2
  sketches it as a `Protocol`, but a Protocol is not constructible.
- **D-A1b (A1):** module is `strategy_core/strategies/protocols.py` (matching A1's stated
  example name); types live in the submodule, not the package `__init__`.
- **D-A3a (A3):** `configure()` converts the section's CONTRACT-form `SessionScheme`
  (string clock times) into the runtime `types.SessionScheme` (`datetime.time` objects)
  before constructing `StrategyLevelState`. The two `SessionScheme` types differ; the
  scheme still ORIGINATES from the section (R2) — only its representation is adapted.
- **D-A3b (A3):** the decision timeframe is held as a module constant
  `_DECISION_TIMEFRAME = DEFAULT_TICK_COUNT` (the engine default min tick-count per
  `state.py:188`), because `required_bars()`/`decision_bar_label()` are `@staticmethod`
  per §2.2; a per-instance configurable decision tf is deferred to wiring (Phase B).
- **D-A3c (A3):** `strategy_version = "1"` is a PLACEHOLDER — NOT load-bearing until
  Phase E splits the version axis (decision 9.3).
- **D-A3d (A3):** the cross-bar first-touch dedup (`_touched_zone_keys`) is NOT replicated
  in the plugin; it is runtime bookkeeping the seam carries in Phase B. A3's single-bar
  equivalence is unaffected (the wrapper mirrors the per-bar `build_zones → detect_touches`
  core exactly).
- **D-A3e (A3):** `touch_reversal/__init__.py` imports the plugin so importing the PACKAGE
  registers it (PLAN §5.2). `strategy_core/__init__.py` and `strategy_core/strategies/__init__.py`
  remain import-free, so NO `import strategy_core` path registers a plugin (verified).
- **D-A3f (A3):** the new test file adds 4 companion assertions beyond the required
  equivalence test (non-decision-bar → empty step; registry resolves + fails closed;
  section `extra="forbid"`; declarations match engine constants). All live in the one new
  test file, which remains the SOLE importer of the plugin.

---

## Status table

| Phase | Step | Goal (short) | Status | Date | Commit | Harnesses passed | Notes/deviations |
|---|---|---|---|---|---|---|---|
| A | A1 | Introduce the StrategyPlugin Protocol + BarSpec/SetupState/DecisionEvent/Barrier types in strategy_core, unused | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; full SC suite 140 passed | New submodule `strategies/protocols.py`; declaration-only, unimported by runtime. D-A1, D-A1b. |
| A | A2 | Introduce the registry (@register + get_strategy(strategy_id)) in strategy_core/strategies/registry.py, empty | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; unwired-invariant check green | §9.1 registry-time assertion (isinstance StrategyPlugin + BarSpec tuple + SectionModel BaseModel); fail-closed get_strategy. Registry stays empty on `import strategy_core`. |
| A | A3 | Author TouchReversalSection SectionModel + a TouchReversalPlugin that wraps the existing functions, registered but not yet wired into the runtime | DONE | 2026-06-08 | `68eef26` | test_touch_reversal_plugin (5 incl. equivalence) + golden suite (12) green | Wraps build_zones→detect_touches verbatim; plugin owns level state (R1); scheme←section (R2, D-A3a); decision tf as config (R3, D-A3b). D-A3c..f. |
| B | B1 | Add an optional plugin param to StrategyRuntime.__init__, defaulting to None; when None, run the exact current state.py:271-280 block | DONE | 2026-06-08 | `1491921` | full SC suite 140 passed (incl. test_runtime_state/touches/touch_zones/levels + A3 test_touch_reversal_plugin); TL test_strategy_core_acceptance + test_strategy_core_replay_integration (3 passed vs branch SC); GATE test_production_pair_parity + test_duckdb_streaming_parity + test_decision_diff (3 passed, store+alpha_lab present) | None-path byte-identical (inner lines unchanged, +4 indent only); else = no-op `pass` (B2 placeholder); `plugin` added last (no param reorder); StrategyPlugin TYPE_CHECKING-only → registry stays empty. Only runtime/state.py changed. |
| B | B2 | Route _process_trade through plugin.on_bar_closed when a plugin is present, and construct StrategyRuntime with the registered TouchReversalPlugin in a feature-flagged path | NOT STARTED |  |  |  |  |
| B | B3 | Make the plugin path the default for strategy_id="touch_reversal"; remove the dead hardwired duplicate only after a full green soak | NOT STARTED |  |  |  |  |
| C | C1 | Repoint TL model_registry import from the local contract copy to strategy_core.contract, keeping today's flat StrategyContract shape | NOT STARTED |  |  |  |  |
| C | C2 | Delete TL's local strategy_contract.py once nothing imports it | NOT STARTED |  |  |  |  |
| D | D1 | Retire TL's local outcome tracker in favor of the engine's honest decision-time fill | NOT STARTED |  |  |  |  |
| D | D2 | Confirm TL holds no local candle/session/level recompute, then assert it via test | NOT STARTED |  |  |  |  |
| E | E1 | Introduce platform_version alongside ENGINE_VERSION, both stamped, loader fail-closes on either | NOT STARTED |  |  |  |  |
| E | E2 | Add per-plugin strategy_version/strategy_id, fail-closed via registry-lookup equality; turn strategy_id into a router | NOT STARTED |  |  |  |  |
| E | E3 | Decompose the flat StrategyContract into StrategyEnvelope + typed SectionModel; emit from the plugin | NOT STARTED |  |  |  |  |
| F | F1 | Extend the candle data shape with a BarSpec/kind and add CloseReason.INTERVAL, with TICK behavior unchanged | NOT STARTED |  |  |  |  |
| F | F2 | Mirror the TIME close trigger into the vectorized batch path and pin it with a new parity test | NOT STARTED |  |  |  |  |
| F | F3 | Validate archetype 2 (HTF-FVG/iFVG) end-to-end on the same interface as a NEW plugin, behind its own strategy_id | NOT STARTED |  |  |  |  |
| (added) | S9.9 | data-drive session-name set in StrategyLevelState (drop hardcoded asia/london); behavior-preserving; feeds F | NOT STARTED |  |  |  | added step, not in plan §7 — per deviation rule |

---

## Change log (newest first)

- **2026-06-08** — Phase B Step B1 landed on `platform-refactor`, commit `1491921`. Additive
  keyword-only `plugin: StrategyPlugin | None = None` on `StrategyRuntime.__init__` (stored as
  `self._plugin`); the hardwired touch fold in `_process_trade` is wrapped in `if self._plugin is None:`
  (verbatim block, +4 indentation only) with an `else: pass` B2 placeholder. `StrategyPlugin` imported
  TYPE_CHECKING-only so `import strategy_core` still leaves the registry empty. ONLY `runtime/state.py`
  changed. Harnesses: full SC suite 140 passed; None-path tests (test_runtime_state/touches/touch_zones/levels)
  green; TL test_strategy_core_acceptance + test_strategy_core_replay_integration 3 passed vs branch SC;
  GATE test_production_pair_parity + test_duckdb_streaming_parity + test_decision_diff 3 passed (data present);
  ruff clean. Verified by a 4-agent adversarial workflow (all pass, high confidence).
- **2026-06-08** — Phase A (A1–A3) landed on branch `platform-refactor`, commit `68eef26`.
  Additive + unwired plugin SDK: `strategies/protocols.py` (StrategyPlugin/PlatformContext/
  BarSpec/SetupState/DecisionEvent/Barrier/StrategyStep/FeatureSpec/LabelPolicySpec/
  EventTypeSpec), `strategies/registry.py` (@register + get_strategy with the §9.1
  registry-time assertion), `strategies/touch_reversal/` (TouchReversalSection +
  TouchReversalPlugin wrapping build_zones→detect_touches), and `tests/test_touch_reversal_plugin.py`.
  Golden suite (test_runtime_state, test_runtime_touches, test_runtime_touch_zones,
  test_runtime_levels, test_touch, test_zones, test_outcomes, test_features, test_sessions,
  test_honest_entry, test_candle_parity, test_contract) + the A3 equivalence test all green;
  full SC suite 140 passed; ruff clean; unwired-invariant verified (`import strategy_core`
  leaves the registry empty). No protected file modified (state.py:271-280 untouched).
