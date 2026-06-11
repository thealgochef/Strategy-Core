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

- **Active phase:** **Phase E — E1+E2 DONE locally (see the E-WINDOW bullet below); Phase D COMPLETE and PUSHED** (D1b greenlit 2026-06-10: SC pushed to `2cb27dc`, TL pin chore `5ede158` pushed; decision 9.6 pin convention honored). D-window record: **D1b (flip + delete)** (SC `945f381` + TL `94610ff`): the dashboard now SERVES the streaming honest resolver — resolutions adapt to served `Outcome`s (entry = the real trade print, NEW `entry_price` field; TL-side correctness; SC ZERO-BASED `bars_to_resolution`; `resolved_ts` from the new SC `StreamResolution.resolved_ts_utc`), drops surface explicitly (`prediction.dropped` WS frame + snapshot `dropped` ring + `RuntimeUpdate.dropped` + IntelligencePanel badge w/ reason, NO chart marker), and the legacy `OutcomeTracker` + its 16 tests + the gate-B characterization harness are DELETED; `ResolutionType.SESSION_END`/`NO_RESOLUTION` REMOVED (grep-proven zero refs). Gates: TL suite **419** (= 420 − 16 tracker + 13 adapter + 1 dropped-frame + 1 swallow pin); seam-by-name **4** (acceptance 3 incl. the D2 guard + replay 1); TL ruff clean; frontend typecheck + vitest **142** + build green; SC suite **152** + ruff + frozen b3 regressions **2** (fixtures untouched). 6-agent adversarial verify on the exact commits: **5 PASS (high) + 1 finding REPAIRED in-window** (the `_track_outcomes` per-item swallow guard). Prior D-window state (D1a DARK SC `c7564fd` + TL `c7f2a84`; D2 TL `73aa7df`) unchanged beneath. Decision 9.6 unchanged (pin DECLARED c615e40; enforcement DEFERRED; QL cold-install debt open).
- **E-WINDOW (E1+E2) DONE and PUSHED at the E greenlight 2026-06-10** (SC `8e5c017` + QL `baecf66` + TL `9b00eb5` on `platform-refactor`, followed by the greenlight chore commits QL `e10d226` + TL `ef8a189` — pin bumps to SC `8e5c017` + CI branch filters — and the SC greenlight doc commit): two-axis versioning live end-to-end. `ENGINE_VERSION` → `PLATFORM_VERSION` (`"strategy_core_platform_v1"`, clean rename, no alias); `CONTRACT_VERSION` → `"trade_lab_contract_v2"` (shape break); contract field `engine_version` → `platform_version` + NEW required `strategy_version`; `strategy_id` re-pointed to the REGISTRY ROUTER KEY. QL emits via `get_strategy` (unknown id fail-closes EMISSION), flips `supported_by_runtime=True` (full contract), and MIGRATED the deployed store in place (3 v3 bundles → v2 w/ backups; the 3 legacy/v1/v2-engine bundles deliberately NOT migrated — see D-E-c); TL gates BOTH registry entries on the platform hook + the 4-check strategy gate (resolve / version-equality / servable-flag / serving-id guard), and `Prediction.contract_id` re-sources to the active bundle id (values byte-compatible). QL CI rider pays the 9.6 debt (cold-install workflow authored; **ENFORCED pending its first green run post-push**); QL tooling aligned py313. REAL-BUNDLE GATE: exactly the 3 migrated bundles discoverable; all 3 activate incl. hot-swap; un-migrated .bak copy rejected on contract_version. Gates: SC **154** + ruff + b3 regressions **2** (fixtures untouched) + decision-fn **2** UNCHANGED; QL **740** (739+1) + ruff (src/tests clean; 13 pre-existing scratch findings stand); TL **424** (419+5) + seam-by-name **4** + ruff + frontend untouched.
- **E3 DONE LOCALLY (full stop before push), 2026-06-10** — SC `dc14652` + QL `523ff98` + TL `3d79bc4` on `platform-refactor`; diffs exported as `E3_SC_DIFF.txt`/`E3_QL_DIFF.txt`/`E3_TL_DIFF.txt`. Contract v3 envelope/section split per the ratified consumer classification; loader section hook; QL emits the section from the plugin's SectionModel + migration #2 executed on the real store (3 MIGRATED + 3 SKIP); TL validates the section at both registry entries, threads the typed section to its two section reads, and closes ALL FOUR D-E-h ledger items. See the E3 deviations (D-E3-a..j) and the status row.
- **Next step:** owner review of the E3 diffs → E3 greenlight (push + the pin bumps) — then F1 per the owner's call. The owner watches the FIRST 9.6-enforcing QL CI run on GitHub (the workflow now triggers on platform-refactor pushes; green = 9.6 ENFORCED).
- **Drift-net status:** **S-B3a DONE (fold-collapse + dedup-into-plugin), byte-identical.** The runtime's `level_state`, `_zones_for_snapshot`, `_touched_zone_keys`/`_zone_key`/`_touch_zone_key_from_touch` are DELETED; `RuntimeUpdate.levels` ← `plugin.on_event` return, snapshot/update `zones` ← `plugin.snapshot_zones`, snapshot `levels` ← `plugin.current_levels`, dedup = plugin-owned `_fired_keys`, touches flow back VERBATIM. Proven against the **FROZEN, UNTOUCHED** B3 digests: `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression` **2 passed** (3,284,775 trades, 8 reset boundaries — every per-trade `to_dict()` + snapshot byte-identical). Full SC suite **144**; TL acceptance+replay **3**; decision-fn gates **2** (UNCHANGED); ruff clean. 5-agent adversarial verify: **5 PASS (all high confidence)**. Verified 2026-06-09 on the final tree.
- **Last-verified date:** 2026-06-10
- **Note (release, decision 9.6) — AMENDED 2026-06-10 (E greenlight):** BOTH consumers pin SC at `8e5c017` (the E1 commit). Pin history: TL `cbf9b99 → c615e40` (`0e1c7ce`, C-window) `→ c7564fd` (`4bb9290`, D-window) `→ 945f381` (`5ede158`, D1b greenlight) `→ 8e5c017` (`ef8a189`, E greenlight); QL `c615e40` (`9b8e798`, declared) `→ 8e5c017` (`e10d226`, the long-deferred bump, E greenlight). PIN CONVENTION unchanged: the pin tracks the latest SC commit with CONSUMER-FACING content; doc-only SC commits do not move it. **STATUS: ENFORCED pending the first green CI run** — QL now has the cold-install workflow (`.github/workflows/ci.yml`, the E-window rider) AND it is reachable: both CI workflows trigger on `platform-refactor` pushes as of the greenlight chore commits (QL `e10d226`, TL `ef8a189`), so the first 9.6-enforcing run fires on this push rather than waiting for merge day. The former NAMED DEBT (QL cold-install resolution check) is PAID by that workflow; green run = ENFORCED.
- **B3-prep (PRE-FLIP soak):** the multi-day reset-bracketed real-data coverage authored as a soak (2026-06-09) is now **repurposed into the plugin-path regression** `test_b3_multiday_reset_plugin_regression` (9 days, 8 reset boundaries) vs the frozen digests — see the "Phase B — B3 deviations (flip+delete)" subsection.

---

## Decisions ratified (record verbatim)

- **9.1** = Protocol (+registry-time assertion).
- **9.2** = in-package registry module.
- **9.3** = two-axis version (platform_version + per-plugin strategy_version).
- **9.4** = time-bars land in Phase F.
- **9.5** = keep `strategy_core` name, layout `strategy_core/strategies/<id>/`.
- **9.6** = declare+SHA-pin strategy-core in Quant-Lab. Pin DECLARED 2026-06-09 (QL `9b8e798`, `c615e40…`, byte-identical to TL's pin form; `requires-python` rider `>=3.14` → `>=3.13`, see D-9.6a); enforcement deferred at declaration — dev resolves SC via the editable install. **AMENDED 2026-06-10 (E greenlight): ENFORCED pending the first green CI run** — QL's cold-install workflow (`.github/workflows/ci.yml`, the E-window rider, D-E-f) pays the named debt; both pins bumped to SC `8e5c017` (QL `e10d226`, TL `ef8a189`) and both CI workflows now trigger on `platform-refactor` pushes, so the enforcing run fires on this push. See the dated release note in Current state for the full pin history.
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
- **D-A3f (A3):** the A3 test file adds 4 companion assertions beyond the required
  equivalence test (non-decision-bar → empty step; registry resolves + fails closed;
  section `extra="forbid"`; declarations match engine constants). As of B2 PART 1 the
  plugin has TWO importers: the A3 test and the B2 seam-parity test (no production path).

### Phase B — deviations / clarifications (B2 PART 1, additive)

- **D-B2a (3b keep-both-folds):** on the plugin path the runtime KEEPS its level fold
  (`level_state.process_trade`, feeding `RuntimeUpdate.levels` + the snapshot) AND adds the
  plugin's `on_event` fold into the plugin's OWN level state (feeding its detection).
  Redundant by design; B3 collapses it once the plugin owns the single fold.
- **D-B2b (dedup stays runtime-owned):** the cross-bar `_touched_zone_keys` set stays the
  RUNTIME's; the plugin only READS it (the new `already_fired_keys` param) to pre-mark its
  zones and never mutates it. FORCED because the end-of-`_process_trade` snapshot pre-marks
  off `_touched_zone_keys` (not only detection), so the platform must own the set. The final
  placement (runtime vs plugin) is the open architect decision (see b2_context.md).
- **D-B2c (single-sourced zone key, I3):** new `strategy_core/decisions/dedup.py` hoists the
  zone-identity key; `StrategyRuntime._zone_key` delegates to it and the plugin pre-marks
  with it, so the two cannot drift.
- **D-B2d:** `StrategyStep` gained `touches`/`zones` (both defaulted; still
  default-constructible); `StrategyPlugin.on_bar_closed` gained `already_fired_keys:
  AbstractSet[ZoneKey]`; new `strategy_core/runtime/context.py` `RuntimePlatformContext`
  (backed by live getters so it survives `reset()`); `StrategyRuntime.__init__` gained a
  trailing `strategy_section` param + builds an inert `self._ctx`. The A3 test's
  `on_bar_closed` calls now pass `frozenset()`. `AbstractSet` is imported as
  `collections.abc.Set as AbstractSet` (the spec's `collections.abc.AbstractSet` does not exist).
- **D-B2e (I4b precondition):** the seam harness pins `section.touch_rule.zone_proximity_pts
  == build_zones' default (ZONE_PROXIMITY_PTS)` — the byte-identity precondition between the
  plugin's section-driven zones and the runtime's default-proximity zones.

**PART 2 (wire) requirements surfaced by PART 1 (must land before flag-on):**

- `StrategyRuntime.reset()` does NOT call `self._plugin.reset()`, and
  `set_static_levels` / `load_prior_day_summary` write only to `self.level_state`, not the
  plugin's `self._plugin._levels`. PART 1's byte-identity is proven only for the no-reset
  streaming path (the seam test seeds the plugin manually). PART 2 MUST wire reset +
  level-seed propagation to the plugin, or the drift net diverges when the construction flag
  flips. (Completeness-critic minor.)
- PART 2 adds the feature flag, production/TL construction through the plugin, and the
  money-path GATE harnesses run flag-on. **→ ALL RESOLVED in PART 2 (below).**

### Phase B — deviations / clarifications (B2 PART 2, additive + cross-repo)

- **D-B2f (the flag — resolver):** `strategy_core/config.py` `plugin_routing_enabled()`,
  env `SC_PLUGIN_ROUTING`, default OFF, truthy `1`/`true`/`yes` (case-insensitive). ONE
  switch, TRANSIENT (deleted at B3). EVERY construction site reads it only through the single
  helper `strategy_core/runtime/wiring.py` `touch_reversal_kwargs()` — which lazily imports the
  plugin module ONLY on the flag-ON branch (so `import strategy_core` leaves the registry
  empty, W2).
- **D-B2g (production wiring):** the ONLY production `StrategyRuntime(` site is Trade-Lab
  `services/strategy_core_service.py` `StrategyCoreService.__init__` — wired via
  `**touch_reversal_kwargs()` (SC validation harnesses + Quant-Lab construct no runtime). Flag
  OFF (default) → `{}` → byte-identical None path (W1).
- **D-B2h (W5 — section matches the runtime):** the runtime's `level_state` uses
  `RESEARCH_SESSION_SCHEME` (default; no scheme passed) + `DEFAULT_TICK_SIZE` (default) + the
  hardcoded asia/london level set, with `decision_timeframe = min(display_timeframes) = 147`
  in production. `default_touch_reversal_section()` round-trips to `RESEARCH_SESSION_SCHEME`
  (via `_contract_scheme_from_runtime`, the inverse of the plugin's `_runtime_scheme_from_section`)
  and pins `touch_rule.zone_proximity_pts == ZONE_PROXIMITY_PTS`; the plugin's `configure` uses
  `ctx.tick_size == runtime.tick_size`. So `self._levels` is built identically to `level_state`.
- **D-B2i (decision-tf gate removal — refines D-A3b):** the plugin's `on_bar_closed` NO LONGER
  self-gates on its declared `_DECISION_TIMEFRAME` (147). The runtime's plugin-path `else` branch
  already gates on `self.decision_timeframe` ONE-FOR-ONE with the None branch, so re-gating on a
  hardcoded 147 would break byte-identity for ANY other `decision_timeframe` (e.g. the tf=2 TL
  acceptance harness). The decision-tf gate is now runtime-owned; `required_bars()` still DECLARES
  147 (advisory). The A3 `test_non_decision_bar` companion was repurposed to assert the new behavior.
- **D-B2j (W4 — lifecycle propagation):** `reset` / `set_static_levels` / `load_prior_day_summary`
  propagate to the plugin (each gated on `if self._plugin is not None:`); new plugin
  `load_prior_day_summary` hook. None path unchanged.
- **D-B2k (cross-repo — Trade-Lab modified):** Phase A's "do not touch TL" no longer applies — B2
  PART 2 wires production. TL `services/strategy_core_service.py` modified (import + `**touch_reversal_kwargs()`),
  committed on TL branch `platform-refactor` (`242c606`). TL imports the NEW SC module
  `runtime/wiring.py` at load even flag-OFF, so TL's SC SHA pin must include it before deploy
  (release step, decision 9.6; the editable branch install resolves it today).

**Go-live gate mapping (reviewable, B2's DONE gate):** dates **2025-07-15** and **2025-07-07**;
harness `validation/test_b2_golive_runtime_parity.py`; **real-store** data
(`Trade-Dashboard/data/databento/NQ/<DATE>/mbp10.parquet`) front-month trades in WIRE order driven
**through `StrategyRuntime.process_event`**; off-vs-on runtimes built via `touch_reversal_kwargs()`
with the flag toggled; per-trade `ua == ub` (≡ `ua.to_dict() == ub.to_dict()`, the deterministic
serialization) + final-snapshot equality; **339,997 + 306,103 trades, OFF==ON throughout**, 5 touches
and 6 max zones/day (PDH/PDL via `load_prior_day_summary` + trade-built asia/london availability-gated
+ merged zones — the breadth the synthetic seam harness did not reach).

### Phase B — B3 PRE-FLIP soak coverage (PREP only; B3 still NOT STARTED — no flip, no deletion)

**Why (gap B2 left):** B2's go-live gate proved flag-ON == flag-OFF per trade on full real
days, but only WITHIN two single continuous streams. It never crossed a reset/restart
boundary — exactly where the W4 lifecycle propagation (`reset` / `set_static_levels` /
`load_prior_day_summary` → plugin) is load-bearing — and two days is thin breadth. Once
B3 deletes the hardwired touch block there is no flag-OFF path left to diff against, so
this proves BOTH the multi-day breadth AND the restart-cycle coverage BEFORE the flip.
This is PRE-FLIP coverage only: the default stays OFF, the hardwired `state.py` touch
block stays, and the redundant level fold (D-B2a) is NOT collapsed.

**New drift-net member:** `validation/test_b3_multiday_reset_parity.py`
(`test_b3_multiday_reset_bracketed_parity`). Reuses the go-live machinery verbatim —
`_read_trades` (real store `Trade-Dashboard/data/databento/NQ/<DATE>/mbp10.parquet`,
front-month, WIRE order) and `_build_runtime` (OFF = `{}` None path; ON = registered
`touch_reversal` plugin via `touch_reversal_kwargs()`). Skips cleanly if the store is
absent or fewer than 7 days resolve.

- **Dates (9 CONSECUTIVE trading days):** 2025-07-10, 2025-07-11, 2025-07-14, 2025-07-15,
  2025-07-16, 2025-07-17, 2025-07-18, 2025-07-21, 2025-07-22. Each day's calendar-prev
  file is present, so the Globex window [prev 18:00 ET, day 18:00 ET) is fully captured;
  the prior-day reseed is sourced from the PRECEDING processed day, which IS the real
  preceding trading day (weekend gaps correct: 07-11 Fri precedes 07-14 Mon).
- **Production-style day roll at EACH boundary (8 boundaries; day 1 is the cold start):**
  `reset()` BOTH runtimes, then reseed BOTH identically via `load_prior_day_summary`
  (PDH/PDL = the preceding processed day's high/low in ticks) + `set_static_levels` (a
  touchable `prior_session_mid` reference) — written through the runtime's lifecycle
  methods, which propagate to the plugin (W4). The bars right after each reset are
  serialized-cross-checked specifically.
- **Driven through `StrategyRuntime.process_event`:** per-trade `ua == ub` (≡
  `ua.to_dict() == ub.to_dict()`, the deterministic serialization) asserted THROUGHOUT,
  plus explicit `to_dict()` cross-checks on every touch-bearing update and on the first
  trade + first decision bar after each reset; per-day and final snapshot equality.
- **W4 across boundaries (white-box):** asserts the plugin's `self._levels` fingerprint ==
  the runtime's `level_state` fingerprint (`_trading_day`/`_day_high`/`_day_low`/`_ranges`/
  `_summaries`/`_static_levels`) right after every reset+reseed AND at each day's end — so
  `self._levels` stays byte-identical across resets, not only at a cold t0.
- **Result:** **2,638,675 trades/runtime (5,277,350 `process_event` calls); OFF==ON
  byte-identical on every trade; 42 touches firing on ALL 9 days (non-vacuous);** plugin
  `self._levels` == runtime `level_state` at all 8 boundaries and 9 day-ends; final
  snapshot equal. Per-day touches: 4/3/6/4/5/4/5/6/5; max zones/day up to 7.

**Flag-ON drift net run (all green, reported by name):**

- Full SC suite (`tests/`, incl. `test_b2_plugin_seam_parity`, `test_b2_wiring`, A3
  `test_touch_reversal_plugin`, the runtime/touch/zone/level golden suite): **145 passed**
  with `SC_PLUGIN_ROUTING=1`; **145 passed** flag-OFF (default) too.
- `tests/test_b2_plugin_seam_parity.py` + `tests/test_b2_wiring.py` +
  `validation/test_b2_golive_runtime_parity.py` + `validation/test_b3_multiday_reset_parity.py`:
  **7 passed** flag-ON.
- TL `tests/test_strategy_core_acceptance.py` + `tests/test_strategy_core_replay_integration.py`:
  **3 passed** flag-ON (routes TL's `StrategyCoreService` through the plugin) AND **3
  passed** flag-OFF.
- Decision-fn gates `validation/test_production_pair_parity.py` +
  `validation/test_decision_diff.py`: **2 passed** flag-ON.
- ruff clean: `ruff check src tests` → All checks passed (the project's lint scope); the
  new test file also passes `ruff check` on its own. (Pre-existing un-linted `validation/`
  harness files are unchanged.)

**Scope guard:** the only working-tree change is the ADDED file
`validation/test_b3_multiday_reset_parity.py`. No tracked source edited; `state.py`'s
hardwired touch block and the `SC_PLUGIN_ROUTING` default OFF are untouched. B3 (flip +
delete) remains the NEXT prompt.

### Phase B — B3 deviations / clarifications (the FLIP + DELETE — irreversible)

B3 made the plugin the SOLE path and deleted the flag-OFF/None path. Because that removes
the on-vs-off comparator, the order was: (1) run the full off-vs-on parity green ONE FINAL
TIME with both paths present (`test_b2_plugin_seam_parity` + `test_b2_wiring` flag-OFF +
go-live + the multi-day soak — **7 passed**); (2) FREEZE a compact regression digest of the
plugin path from that green run (canonical-correct because plugin == None there), off==on
cross-checked on **3,284,775 trades/path**; (3) only then remove.

- **D-B3a (plugin is mandatory; auto-attach).** `StrategyRuntime.__init__` now auto-attaches
  the registered `touch_reversal` plugin + its default section when `plugin is None` (PLAN §7
  B3: "plugin defaults to the registered touch plugin"). The `plugin`/`strategy_section`
  params remain (optional) for explicit injection (forward-looking Phase-E router + tests).
  A fail-LOUD `ValueError` guards the untested non-default-scheme case: the default section is
  `RESEARCH_SESSION_SCHEME`, so a runtime built with a different scheme MUST pass its own
  plugin+section (else `plugin._levels` could silently diverge from `level_state`). Verified
  ALL current call sites (the whole golden suite + production) use the default scheme, so none
  hit the guard. `reset`/`set_static_levels`/`load_prior_day_summary`/`on_event`/`configure`
  are now UNCONDITIONAL (no `if self._plugin is not None`).
- **D-B3b (off-vs-on tests → frozen-digest regressions).** The real-data gates lost their
  comparator, so they are repurposed into plugin-path REGRESSIONS that re-run the plugin path
  and assert against the frozen digests. New `validation/_b3_regression_util.py` (shared
  `SeqDigest` = order-sensitive sha256 over every per-trade `RuntimeUpdate.to_dict()` + touch
  count + final-snapshot sha) + `validation/_fixtures/b3_regression/{golive,multiday}.json`
  (the canonical digests). `test_b2_golive_runtime_parity.py` → `test_b3_golive_plugin_regression`
  (2 days); `test_b3_multiday_reset_parity.py` → `test_b3_multiday_reset_plugin_regression`
  (9 days, 8 reset boundaries, fails-loud if the chain is incomplete). The synthetic
  `test_b2_plugin_seam_parity` → a plugin-path cross-bar first-touch suppression test;
  `test_b2_wiring` keeps kwargs-attaches/auto-attach/lifecycle and RETIRES the
  resolver/kwargs-OFF/W2-empty-registry assertions. **Decision-fn gates
  (`test_production_pair_parity`, `test_decision_diff`) LEFT UNCHANGED** — flag-agnostic, the
  canonical anchor. (Cosmetic debt: the repurposed files keep their `test_b2_*`/`parity`
  filenames; contents/function-names/docstrings updated — a trivial rename is a follow-up.)
- **D-B3c (W2 migration guard retired).** "registry empty on bare `import strategy_core`" was
  a MIGRATION guard; the plugin is now the production strategy and registers when
  `runtime/wiring.py` is imported (runtime construction or TL import) — intended, not a leak.
  (Incidentally `strategy_core/__init__.py` still imports neither `wiring` nor the plugin, so a
  BARE `import strategy_core` leaves the registry empty — but it is no longer load-bearing.)
- **D-B3d (dead-helper removal; out-of-scope KEPT).** Removed `state.py`'s now-unused
  `detect_touches` import and the `_zones_for_detection` helper (exclusive to the deleted None
  block). KEPT exactly as-is (out of scope — they belong to S-B3a): the runtime's own
  `level_state.process_trade` fold, the snapshot premark `_zones_for_snapshot`, the
  `_touched_zone_keys` set + its placement/writes, `_touch_zone_key_from_touch`, `_zone_key`.
- **Cross-repo (TL).** `services/strategy_core_service.py` already constructed via
  `**touch_reversal_kwargs()`; only its stale flag comment was updated. No behavior change.
- **Verification.** A 6-agent adversarial workflow (read-only) checked: removal correctness,
  out-of-scope untouched, flag fully removed (no live-code refs in SC/TL/QL), plugin always
  non-None, regression non-vacuity, and completeness — **5 PASS (high) + 1 FAIL** whose sole
  finding was a stale `TYPE_CHECKING` comment in `state.py` (since fixed). PLAN unmodified.

**STOP point (resolved):** B3 was surfaced for review per the flip+delete prompt, re-verified
green on the final tree (full SC suite 144 + ruff clean + both real-data digest regressions),
and committed as SC `85cb7b6` on `platform-refactor`.

### Phase B — S-B3a deviations / clarifications (fold-collapse + dedup-into-plugin)

S-B3a deleted the runtime's redundant copies (exactly D-B3d's KEPT list) and made the
plugin the sole owner of levels, zones, and the first-touch dedup. Behavior-preservation
is anchored on the FROZEN, UNTOUCHED B3 digest fixtures: both regressions reproduce every
per-trade `RuntimeUpdate.to_dict()` and every snapshot byte-identically (3,284,775 trades,
8 reset boundaries). The decision-tf gate stays RUNTIME-owned (D-B2i untouched); the
auto-attach + fail-loud non-default-scheme guard is code-identical (D-B3a untouched);
`self._touches` (the snapshot's touch accumulator) stays RUNTIME-owned (not level/dedup
state — explicitly out of scope).

- **D-SB3a-a (D-B2b RESOLVED — dedup is PLUGIN-owned, owner-ratified).** The open
  placement decision from D-B2b is closed: the cross-bar dedup moved INTO the plugin as
  `TouchReversalPlugin._fired_keys` — initialized empty in `__init__`, pre-marked AND
  written inside `on_bar_closed` (keys recorded after `detect_touches` via the relocated
  key helper), read by `snapshot_zones`, cleared ONLY in `reset()`. That is the exact
  lifecycle the runtime's deleted `_touched_zone_keys` had: keys are day-scoped, so they
  accumulate across day rolls and clear only on reset; `configure()` deliberately does
  NOT clear them (the old runtime had no analogous re-configure path; configure runs only
  at construction). D-B2b's "FORCED runtime-owned because the snapshot pre-marks off the
  set" constraint is dissolved by D-SB3a-b's snapshot accessor.
- **D-SB3a-b (protocol temporarily carries touch vocabulary).** `StrategyPlugin` gained
  `current_levels() -> tuple[Level, ...]` (mirrors the deleted snapshot read
  `level_state.levels()`) and `snapshot_zones(trading_day: date | None) -> tuple[Zone, ...]`
  (faithful relocation of the deleted `_zones_for_snapshot`: zones from
  `StrategyLevelState.zones()` — the DEFAULT-proximity display derivation, deliberately
  NOT `on_bar_closed`'s section-driven DETECTION derivation; `trading_day is None` →
  unmarked; premark via the shared `zone_key`; returns a tuple where the old helper
  returned a list both call sites tupled — identical payload). Precedent:
  `StrategyStep.touches`/`zones` (D-B2d); the generic plugin-event payload that removes
  the typed `levels`/`zones` fields stays deferred per PLAN §2.1(5).
- **D-SB3a-c (`on_event` return-type change).** `on_event` now returns
  `tuple[Level, ...]` — for a `Trade`, the plugin's full post-fold level set (maps onto
  `RuntimeUpdate.levels` one-for-one with the deleted runtime fold's return,
  `level_state.process_trade`); `()` for a `Quote`. The §2.2 sketch's
  `tuple[SetupState, ...]` return was never consumed (the plugin returned `()` since A3).
- **D-SB3a-d (`already_fired_keys` RETIRED).** Removed from `StrategyPlugin.on_bar_closed`
  (protocol), the plugin implementation, the runtime call site, and both test callers.
  Side effect: direct `on_bar_closed` calls are no longer read-only on dedup state (they
  record into `_fired_keys`) — the intended production semantics; both unit-test callers
  use fresh single-call plugins, so their outputs are unchanged.
- **D-SB3a-e (relocated key helper; `dedup.py` stays).** `_touch_zone_key_from_touch`
  moved VERBATIM (including the defensive fallback tuple) from `StrategyRuntime` into the
  plugin as a `@staticmethod`; the only delta is calling the single-sourced `zone_key`
  directly instead of through the deleted `_zone_key` delegate (same function — I3
  preserved). `decisions/dedup.py` STAYS; its sole consumer is now the plugin (docstrings
  updated to past tense).
- **D-SB3a-f (test edits, enumerated — the complete list).** (1)
  `tests/test_touch_reversal_plugin.py`: the two `on_bar_closed` call sites dropped the
  retired `frozenset()` arg; every assertion unchanged. (2) `tests/test_b2_wiring.py`:
  `test_lifecycle_propagation_keeps_plugin_levels_in_lockstep` →
  `test_lifecycle_propagation_reaches_plugin_state` — the runtime-vs-plugin fingerprint
  lockstep lost its comparator (the runtime fold is deleted), so it now white-box-asserts
  the lifecycle WRITE-THROUGH (seeded summary + static level present in
  `plugin._levels`), `_fired_keys` non-empty after a fired touch, `reset()` clearing BOTH
  (levels cleared + `_fired_keys == set()`), and a re-seeded SAME-day replay re-firing
  (which would be suppressed had reset not cleared the day-scoped dedup). (3)
  `tests/test_runtime_touch_zones.py`: docstring/comment staleness only — no assertion
  changed. (4) `tests/test_b2_plugin_seam_parity.py`: UNCHANGED (drives the public API
  only). The golden runtime suite's observable-behavior assertions are untouched; NO
  non-test consumer needed re-pointing (TL backend + QL grep: zero references to any
  deleted member, public or private).
- **D-SB3a-g (staleness fixes riding the step).** `plugin.py` module docstring rewritten
  off the pre-B3 "registered but NOT constructed by any production path" world; every
  "mirrors state.py:NNN" cross-reference dropped (incl. a stale `(state.py:188)` line
  number); `protocols.py` module header de-staled (Phase-A "declaration-only / nothing
  imports it" framing); `wiring.py`/`section.py`/`dedup.py` docstrings updated off the
  deleted `level_state`/`_zones_for_detection`/shared-set language;
  `tests/test_runtime_touch_zones.py` docstring reworded; the stale untracked
  `__pycache__/config.cpython-313.pyc` deleted. The `test_b2_*` filenames are NOT renamed
  (separate follow-up, already logged in D-B3b).
- **Surfaced by the adversarial verify (recorded, deliberately NOT touched — out of the
  enumerated scope):** (i) `V3_COMPATIBILITY_MATRIX.md:11` is present-tense stale
  ("Runtime level state supports … via `StrategyLevelState`" — the level state is
  plugin-owned now). (ii) The `StrategyPlugin` Protocol does not declare
  `set_static_levels`/`load_prior_day_summary` although the runtime now depends on them
  as the SOLE seed path (gap pre-exists since D-B2j; a future non-touch plugin would
  AttributeError on the lifecycle calls) — protocol addition left to the architect.
  (iii) `StrategyLevelState` still physically lives at `runtime/levels.py` (now
  plugin-imported only; the physical move stays deferred per the ADDITIVE COROLLARY).
  (iv) Out-of-contract edge: an EXPLICIT `plugin=` passed WITHOUT `strategy_section`
  never gets `configure()`, so its level state stays at `__init__` defaults — no such
  call site exists; production always supplies the section (D-B3a guard unchanged).

**STOP point (resolved):** S-B3a was surfaced for review per the S-B3a prompt, greenlit
against the exact reviewed bytes (byte-identical diff comparison at commit time), and
committed as SC `f6e9be8` on `platform-refactor`.

### Post-Phase-B tidy — S-B3b deviations (protocol seed path + drift-net renames + doc de-stale)

S-B3b closes three recorded debts: S-B3a adversarial-verify items (i) and (ii), and
D-B3b's cosmetic filename debt. No runtime/plugin behavior change; the frozen digest
fixtures are untouched. TL/QL untouched — the TL pin bump is deliberately DEFERRED to C1
(S-B3b has no TL-facing change; the editable install resolves the working tree).

- **D-SB3b-a (protocol declares the seed path — closes verify item ii).** `StrategyPlugin`
  gained `set_static_levels(levels)` and `load_prior_day_summary(trading_day, *,
  high_ticks, low_ticks)` in the lifecycle section, mirroring the touch plugin's
  signatures exactly — the SOLE level-seed path since S-B3a (W4/D-B2j). Because the
  Protocol is `@runtime_checkable`, the §9.1 registry-time assertion now also requires
  these methods at registration — deliberate strengthening: a future plugin missing the
  seed hooks fails at `@register`, not with an `AttributeError` mid-session. The touch
  plugin already implements both (since B2 PART 2 / D-B2j).
- **D-SB3b-b (drift-net renames — closes D-B3b's cosmetic debt).** `git mv`, contents/
  function names/assertions UNCHANGED:
  `tests/test_b2_wiring.py` → `tests/test_plugin_wiring.py`;
  `tests/test_b2_plugin_seam_parity.py` → `tests/test_plugin_cross_bar_suppression.py`;
  `validation/test_b2_golive_runtime_parity.py` → `validation/test_b3_golive_plugin_regression.py`;
  `validation/test_b3_multiday_reset_parity.py` → `validation/test_b3_multiday_reset_plugin_regression.py`.
  Living references updated (the complete set, from a 3-repo grep): the `Run:/pytest:`
  docstring self-hints in both renamed validation files, and the multiday file's LIVE
  cross-import (`from test_b3_golive_plugin_regression import DATA_DIR, TICK_SIZE,
  _build_runtime, _read_trades` — previously the old golive module name). Historical
  PROGRESS/change-log mentions left untouched (they are the record); TL's untracked
  `test.md` scratch note left untouched; QL has zero references; no CI/script references
  exist in any repo.
- **D-SB3b-c (V3 matrix de-stale — closes verify item i).** `V3_COMPATIBILITY_MATRIX.md`
  PDH/PDL row reworded to the post-S-B3a reality: level state is plugin-owned
  (`StrategyLevelState` under the `touch_reversal` plugin); the runtime seeds it through
  its lifecycle methods and reads levels/zones back via the plugin accessors.

### Phase C — C1+C2 deviations / clarifications (cross-repo) + decision 9.6 implementation

C1 and C2 landed as ONE TL commit (`0e1c7ce`): the C2 deletion is safe only with C1's
repoint in place, and the C1 tree was never meant to exist with the local copy still
importable. SC CODE is untouched this window (record-only commit). Engine gate semantics
were the load-bearing recon fact: SC's loader performs NO engine check on a bare call
(opt-in `expected_engine_version` hook, checked after `contract_version`, BEFORE
`model_validate`), whereas TL's deleted local loader bound inline whenever the field was
present and loaded legacy no-field contracts "unbound" with a warning.

- **D-C1a (hook at BOTH loader entries — refines the prompt's call-shape).** The task named
  `model_registry._load_contract` (activation) as the hook site; recon found `model_registry`
  has TWO loader entries into contracts — `_describe_bundle` (DISCOVERY, :135) and
  `_load_contract` (activation, :286) — and the real-store v2-class bundle
  (`NQ_20260602_232808`, `engine_version='strategy_core_engine_v2'`) is SCHEMA-VALID under SC,
  so a hookless discovery would have LISTED it (the old local loader engine-bound inside
  discovery too). The hook is wired at BOTH entries:
  `load_strategy_contract(..., expected_engine_version=ENGINE_VERSION)` with `ENGINE_VERSION`
  imported from `strategy_core` (single-sourced, no literal). Adversarial bypass hunt: zero
  other paths in `backend/src` turn strategy.json bytes into a `StrategyContract`.
- **D-C1b (legacy loads-unbound RETIRED — owner-ratified).** A contract with ABSENT
  engine_version now fails closed twice over: the hook rejects it
  (`unsupported engine_version None; expected 'strategy_core_engine_v3'`) and SC's schema
  requires the field anyway. Real-store effect (proven through the registry): the legacy
  `NQ_20260405_…iterations800_depth4` bundle — the ONLY previously-activatable one — is now
  rejected; discovery yields EXACTLY the 3 v3 bundles (`NQ_20260603_233847`,
  `NQ_20260604_012623`, `NQ_20260604_015413`), all 3 activate end-to-end (CatBoost load +
  feature-name validation + hot-swap; checksum step no-op — no sidecars exist in the store),
  and v1/v2/legacy fail with `ModelValidationError` wrapping the engine-hook `ContractError`.
- **D-C1c (import surface).** Package-root imports everywhere: `from strategy_core import
  CONTRACT_VERSION / ENGINE_VERSION / ContractError / StrategyContract /
  load_strategy_contract` (all root-exported; SC `CONTRACT_VERSION` is the SAME string
  `"trade_lab_contract_v1"` TL's local copy used, so no fixture version change). No submodule
  fallback was needed: TL imports neither `LabelPolicy` nor `DECISION_OFFSET_MINUTES` (the
  only names not root-exported). `feature_functions.py`'s TYPE_CHECKING deep import
  (`trade_lab.domain.contracts.strategy_contract`) likewise → package root.
- **D-C1d (test/assertion edits — the complete list).** (1)
  `tests/test_engine_version_binding.py` REWRITTEN to the hook call shape (the registry's
  exact production shape): `test_matching_engine_version_loads` passes
  `expected_engine_version=strategy_core.ENGINE_VERSION` (assertions unchanged);
  `test_mismatched_engine_version_fails_closed` uses the v2-style literal
  `"strategy_core_engine_v2"` (was `"strategy_core_engine_v0_does_not_match"`) + the hook
  (assertion unchanged: `ContractError` match `"engine_version"`);
  `test_legacy_bundle_without_engine_version_still_loads` (asserted loads + `engine_version is
  None`) → `test_absent_engine_version_fails_closed` (asserts `ContractError` match
  `"engine_version"` via the hook) — the loads-unbound regression is retired WITH the behavior.
  Module docstring rewritten. (2) `tests/test_strategy_contract.py`: import repoint ONLY —
  ZERO assertion changes; all error-string matches (`unsupported contract_version`,
  `invalid strategy contract`, `not valid JSON`) hold verbatim because SC's loader was ported
  from TL's (run-verified, not assumed). (3) `test_inference_engine.py` /
  `test_outcome_tracker.py` / `test_feature_functions.py`: import repoints only; nothing else
  forced. Suite count integrity: 435 passed + 1 skip BEFORE and AFTER (the skip =
  `test_benchmark_smoke.py:35`, requires `--run-benchmark`, pre-existing).
- **D-C1e (fixture regeneration — minimal).** `backend/tests/fixtures/strategy.json` gained
  EXACTLY two keys (git diff: +2/−0): top-level `"engine_version": "strategy_core_engine_v3"`
  and `label_policy.decision_offset_minutes: 5` (= SC `constants.DECISION_OFFSET_MINUTES`,
  itself `DEFAULT_INTERACTION_WINDOW_MINUTES`). Validation forced nothing else
  (`research_session_experiment` is Optional; `contract_version` unchanged per D-C1c).
- **D-C1f (before-state CORRECTION — probe-verified, amended 2026-06-09).** The C-window
  recon's framing of "3 activatable v3 bundles (pre-C1)" was WRONG. Probe (temporary TL
  worktree at `be90af3`, the pre-C1 LOCAL loader
  `trade_lab.domain.contracts.strategy_contract.load_strategy_contract`, real store, run
  2026-06-09): all 3 v3 bundles FAIL with `ContractError` → pydantic `extra_forbidden` on
  `label_policy.decision_offset_minutes` (the old schema lacks the field, `extra="forbid"`);
  legacy `NQ_20260405_…iterations800_depth4` loads UNBOUND ("strategy contract has no
  engine_version; loading unbound against strategy_core_engine_v3" warning); v1
  `NQ_20260602_184719` rejected on the engine binding (`unsupported engine_version
  'strategy_core_engine_v1'`); v2 `NQ_20260602_232808` rejected on SCHEMA
  (`decision_offset_minutes` extra_forbidden — the old loader ran `model_validate` BEFORE its
  engine bind, so v2 never reached the engine check). The exact set TL could serve at
  `be90af3` = **{legacy, UNBOUND}** only. TRUE C1 behavior change: the served set **FLIPPED**
  {legacy-unbound} → {3× v3} — it was NOT trimmed from a v3-capable superset. (D-C1b's "the
  ONLY previously-activatable one" phrasing is consistent and now probe-proven.)
- **D-C2a (deletion).** `git rm` of `domain/contracts/strategy_contract.py` + `__init__.py`;
  emptied directory (+ gitignored `__pycache__`) removed from disk. Full-repo grep
  (`domain.contracts` / `domain/contracts` / `strategy_contract`, all import/path forms):
  ZERO live hits — remaining mentions are historical docs/plans prose
  (`docs/inference-integration-plan.md`, `docs/SESSION-HANDOFF-2026-05-30.md`, `plans/*.md`)
  + the untracked `BASELINE_REPORT.md`/`test.md`, left as record.
- **D-9.6a (QL pin implementation detail).** QL `pyproject.toml` `[project].dependencies` +=
  the pin line byte-identical to TL's form (HTTPS git URL + full 40-char SHA `c615e40e…`);
  setuptools accepts direct references without extra config (TL needed
  `hatch.metadata.allow-direct-references`; QL does not). The editable/`PYTHONPATH=src`
  resolution STAYS for dev — the pin is the cold-install declaration. RIDER:
  `requires-python` `">=3.14"` → `">=3.13"` (the working interpreter is 3.13.1; `py --list`
  shows NO 3.14 on the machine). QL-side debt recorded, deliberately NOT touched (outside the
  enumerated scope): the two script `sys.path` hacks (`scripts/phase8_1_golden.py:32-36`,
  `scripts/run_databento_acceptance.py:147-149`), and — surfaced by the adversarial verify —
  `[tool.ruff] target-version = "py314"` + `[tool.mypy] python_version = "3.14"` now lag the
  relaxed `requires-python`, and QL's `.python-version` file still says `3.14.5`. AMENDED
  2026-06-09: the pin is DECLARED, not ENFORCED — nothing currently exercises it; NAMED DEBT:
  QL cold-install resolution check (the analog of TL's cold-install CI) — required to make
  9.6 enforced rather than declared.
- **Surfaced by the adversarial verify (recorded, deliberately NOT touched):** (i)
  `test_inference_engine.py:451` bare-loads a real bundle's strategy.json — safe ONLY because
  the same test activates that bundle through the gated registry first; if the activation step
  were removed, the bare load would accept an engine-drifted bundle. (ii) TL
  `backend/pyproject.toml:14` declares `httpx2>=2.3` (pre-existing, unusual package name —
  flagged for the owner, possibly intended `httpx`). **AMENDED (D-window probe): RESOLVED —
  correct AND load-bearing.** Cold CI resolves starlette 1.x whose testclient imports
  `httpx2 as httpx` (verified against the starlette 1.2.1 wheel + the passing cold-CI run);
  zero direct imports anywhere in TL; sole consumers are the 5 TestClient test files; the
  local env is stale (starlette 0.52.1 + plain httpx), so local probes mislead. Moved to the
  dev extra in the D2 commit (CI installs `.[dev]`, backend-ci.yml:37).

### Phase D — D1a deviations / clarifications (streaming honest resolver, DARK)

Ratified design implemented exactly: live scoring adopts batch honest semantics (entry =
realistic trade print at the decision instant; registration drops {flatten, cutoff}; {no_fill,
no_forward}; unresolved-at-cutoff → no_resolution drop). SESSION_END classification dies at
D1b, NOT this window — zero WS/DTO/frontend changes. bars_to_resolution: the new path is SC
batch 0-based; gate A compares raw, gate B normalizes the tracker's 1-based count.

- **D-D1a-a (output shapes).** `StreamDrop.reason ∈ {flatten, cutoff, no_fill, no_forward,
  no_resolution}` — the four `HonestEntryDrop` arms PLUS the streaming terminal arm; the
  no_resolution drop carries the 4dp extremes + `bars_to_resolution=-1`, mirroring the batch
  `OutcomeResult` no_resolution arm byte-for-byte. Resolutions are emitted as
  `StreamResolution` envelopes (key + decision_ts + ENTRY price + the intact kernel
  `OutcomeResult`) — the serving consumer and both gates need the fill the excursions were
  anchored on. Root-exported: `StreamingHonestResolver`, `StreamResolution`, `StreamDrop`.
- **D-D1a-b (caller contract).** `register()` MUST be invoked at-or-after the setup's decision
  instant (the ring only holds what has printed). Production satisfies this STRUCTURALLY:
  predictions register at observation expiry (= touch + the same 5-minute window); the gate-A
  harness registers a pending touch on the first trade at/after its decision instant, with
  post-loop registration for decisions landing in the 17:00–18:00 print-less halt (those drop
  flatten/cutoff identically to batch — no entry query reached).
- **D-D1a-c (bar-inclusion rule — gate-A arbitrated).** Every closed bar of the forward
  timeframe the caller feeds is a candidate — INCLUDING END_OF_DAY partials — exactly as the
  batch path consumes its `day_bars` list; membership is decided ONLY by the strict
  `(decision_ts, trading-day 17:00 ET)` close-instant bounds. On the real store partials are
  unreachable in practice (they freeze at the 18:00 ET roll, after the cutoff that
  strictly upper-bounds every window). Documented in the module docstring.
- **D-D1a-d (cutoff signal).** Prints halt AT the 17:00 ET cutoff, so the finalizing signal
  can never arrive as a same-trading-day forward bar close: a bar closing at/after a setup's
  cutoff finalizes it WITHOUT contributing its range (batch bound is strictly
  `close < cutoff`), and the explicit `flush(now_ts)` finalizes by absolute cutoff instant —
  TL live relies on the next session's bars crossing the ABSOLUTE cutoff datetime; the gate-A
  harness flushes at each day's 18:00 ET window end (asserts `open_count == 0` after).
- **D-D1a-e (ring/accessor).** `StrategyRuntime` keeps a bounded `(ts, price>0)` deque fed in
  `_process_trade` — retention 2× the 30-min lookback, the EXACT 30-min bound enforced at
  query time (never by eviction); cleared on `reset()`. `price>0` is the ratified live
  analogue of the reference query's `bid/ask>0` parquet row-validity predicate
  (`decision_diff_harness.py:594-616`). `RuntimePlatformContext.trade_price_at` is now backed
  by the ring via a live getter; **`quotes_in_window` STAYS a stub** (§9.10 retention window
  open — named debt). The b3 frozen digests reproduce byte-identically on the
  ring-instrumented runtime (the ring touches no emitted value).
- **D-D1a-f (TL forced test adaptation — enumerated).** 5 pre-existing tests
  (`test_inference_api.py` ×2 via `_runtime_app_with_active_model`,
  `test_inference_engine.py` ×3 via `_runtime_with_engine`) activated the REAL 147t contract
  on `tick_timeframes=(2,)` — exactly the silent-never-resolve hole the new fail-loud
  activation validation closes, so they now fail loud by design. Helpers changed to
  `(2, 147)`; the 2t decision bar still drives their touch flow (decision timeframe pins to
  `min()`); ZERO assertion changes.
- **D-D1a-g (gate-A reference).** The batch `trade_price_at` reference is implemented over the
  SAME front-month print set `_read_trades` feeds the runtime (most recent `ts <= as_of`
  within 30 min, binary-searched) — isolating the mechanism comparison (incremental ring vs
  whole-day random access); the bid/ask>0 ≙ price>0 mapping is documented in the gate file.
  Params both sides = the engine constants (tp 15 / sl 30 / trap 5 / offset 5).
- **D-D1a-h (gate-B scope).** Trades-only, live-like CONTINUOUS replay (no per-day reset) with
  the real bundle `NQ_20260604_015413` (label_policy tp15/sl15/trap5/147t/17:00) activated
  through the registry: quote-dependent approach features are NaN (model_native policy), and
  the no-reset level evolution yields 29 predictions vs the reset-bracketed gate-A roll's 42
  touches — both counts honest, different configurations. HEADLINES: 29/29 resolved on both
  paths (zero SESSION_END this window); entry Δ (trade print − level price) mean −20.5 ticks,
  mean |Δ| **55.6 ticks**, max |Δ| 226; **6 label changes** (5× old sl_hit → new
  tradeable_reversal; 1× tp_hit → blowthrough; 1× tp_hit→trap; net old 15 tp/14 sl → new 18
  tradeable/8 blowthrough/3 trap); **5/29 correctness flips**; bars_to_resolution deltas
  spread −72..+12 (entry anchor changes when barriers trip).
- **D-D1a-i (rider).** The gate-B harness file's lint debt (unused noqa / int cast / long
  lines) was fixed in the D2 commit — TL's ruff project scope includes `validation/`, missed
  at the D1a commit.
- **D-D1a-j (post-review terminal-path unit coverage — greenlight addendum).** New SC
  `tests/test_streaming_resolver.py` (synthetic, 7 tests) pins exactly the arms the gate-A
  window never exercised: registration cutoff drop at the NON-STRICT 17:00 ET boundary
  (flatten pushed aside, mirroring `test_honest_entry`'s cutoff arm); flatten at the EXACT
  16:40:00 ET boundary (non-strict); no_fill; no_forward via `flush` (entry carried);
  no_resolution via `flush` (4dp extremes + `bars_to_resolution=-1`); no_resolution via
  `on_bar` where the finalizing bar closes at the cutoff with a both-barriers range —
  asserting that bar contributed NOTHING to the extremes (the strict `close < cutoff`
  window); and the StrategyRuntime trade-ring edges (30-min lookback bound exact; a print
  beyond the 60-min retention is EVICTED — a query that would have matched it inside its
  own lookback returns None). NOTE for D1b: TL's dark wiring imports the private
  `_parse_bar_type` from `outcome_tracker` — that helper needs a new home when D1b deletes
  the tracker.

### Phase D — D2 deviations / clarifications (shadow-engine deletion + guard)

- **D-D2-a (deleted inventory).** `domain/candles.py`: `CandleEngine` (:103-192),
  `_MutableCandle` (:35-94, incl. the already-dead `from_trade`), `CandleUpdate` (:97-100)
  DELETED; KEPT `Candle`, `CandleCloseReason`, `make_bar_id` (live importers:
  runtime/service/seed/dto/outcome_tracker). `domain/levels.py`: `SessionLevelEngine`
  (:118-311), `_SessionRange`, `_DaySummary`, `LevelUpdate`, `SESSION_LEVELS`, `LEVEL_ORIGIN`
  DELETED; KEPT `LevelKind`, `LevelDirection`, `DisplayLevel`, `TouchEvent` (live importers:
  observations/service/runtime/dto). `domain/sessions.py` NOT deleted — production-reached
  via `seed.py` (named debt below). Deleted TESTS (24 collected): `test_benchmark_smoke.py`
  whole file (2 — orphans the `--run-benchmark` conftest hook, harmless; removes the suite's
  standing 1-skip); `test_prices_sessions_candles.py` 6 CandleEngine tests (14 engine-free
  survive); `test_levels_observations.py` 14 SessionLevelEngine tests (the
  ObservationEngine-guard test survives); `test_seed.py` 2 (bar-id collision +
  vectorized-builder-vs-engine parity).
- **D-D2-b (guard strengthening).** New
  `test_deleted_shadow_engines_stay_deleted_across_backend_src`: bans the six deleted names
  across ALL of `backend/src` (any reintroduction fails), confines `SessionClassifier` to
  `sessions.py` + the `seed.py` carve-out, and pins `domain/candles` + `domain/levels` to
  their DTO-only public surface. Carve-outs documented IN the test docstring: `seed.py`
  warm-up builder (display-only; Chicago-clock divergence = named debt), the tracker's
  cutoff math (dies at D1b), `strategy_core_service.py:316-325` display-flag re-derivation.
  The stale `SessionLevelEngine` comment in `adapters/synthetic_replay.py:58` was reworded
  (it would have tripped the token scan); the kept modules' docstrings deliberately avoid
  the literal engine names for the same reason.
- **D-D2-c (oracle losses — recorded).** Deleting the engines removed (1) the ONLY parity
  cross-check of the production seed builder `build_tick_bars_from_frame` (the engine WAS
  its oracle — `test_vectorized_builder_matches_candle_engine`) and (2) the live-side
  generator of the seed bar-id non-collision check. The builder keeps its 6 functional
  tests; re-anchoring it against SC's batch builder (engine-locked by
  `test_candle_parity`) is a candidate follow-up, NOT done this window (scope).
- **NAMED DEBTS (Phase D):** (1) `seed.py` Chicago-clock session math diverges from SC's ET
  scheme (18:00 CT vs 18:00 ET trading-day boundary) — display-only warm-up, guard
  carve-out; (2) the `Barrier` Protocol cannot reach `trap_mfe_min` (kind + 2 price methods
  only) — fix at E3; (3) §9.10 `quotes_in_window` retention window open (stub stays); (4)
  the orphaned `--run-benchmark` conftest hook; (5) QL cold-install resolution check
  (carried from the C-window, unchanged). INFORMATIONAL: the repo test fixture keeps the
  synthetic policy (tp15/**sl30**/16:15) while the deployed bundle carries
  tp15/**sl15**/17:00 — tests deliberately keep the synthetic policy; recorded, not changed.
  **AMENDED at D1b:** the D2 guard's `outcome_tracker.py` docstring carve-out (the
  tracker's cutoff wall-clock math, "dies WITH the tracker at D1b") is **RETIRED on
  schedule** — the tracker is deleted and the bullet removed; the guard's scan code never
  carved the tracker out, so no code change.

### Phase D — D1b deviations / clarifications (flip + delete: serve the honest resolver, retire the tracker)

Ratified semantics implemented exactly: full honest alignment — the dashboard serves the
D1a streaming resolver's outcomes; drops are surfaced explicitly with reasons;
SESSION_END classification retires; entry is the real trade print. The legacy
`OutcomeTracker` is DELETED. SC PART 1 (`945f381`) is additive; TL PART 2 (`94610ff`) is
the flip.

- **D-D1b-a (SC `resolved_ts_utc` + the documented asymmetry).** `StreamResolution`
  gained `resolved_ts_utc` (the RESOLVING bar's `close_ts_utc`, stamped in `on_bar`).
  DELIBERATE ASYMMETRY, documented in the `StreamResolution` docstring: the kernel batch
  `OutcomeResult` carries NO timestamp (a batch caller indexes `bars_to_resolution` into
  the `day_bars` list it already holds; the timestamp is the envelope's concern). Gate A
  cannot arbitrate the field against batch, so it is PINNED in
  `tests/test_streaming_resolver.py`. CLARIFICATION vs the prompt's "extend the
  resolution-path test": that file had NO resolution-path test (gate A owned resolutions;
  the D-D1a-j tests pin terminal arms only), so one was **ADDED**
  (`test_resolution_carries_the_resolving_bars_close_instant` — also pins
  label/entry/decision_ts/zero-based bars on the same emission). Gate A verified
  field-read-only (never constructs `StreamResolution`, never compares whole dataclasses);
  no other construction site exists in SC/TL/QL.
- **D-D1b-b (the adapter + `parse_bar_type`'s new home).** NEW
  `services/inference/resolution_adapter.py` (TL) — placed in `services/inference/` rather
  than beside `outcome_to_dto` (api/dto.py) because the runtime consumes it to build
  DOMAIN objects; api/ importing into the hot path would invert layering. Mapping table
  (ratified): `tradeable_reversal → TP_HIT`; `aggressive_blowthrough → SL_HIT`;
  `trap_reversal → SL_HIT`; an unmapped label fails LOUD (`ValueError`), so a future
  4th engine label must be mapped deliberately. `correct = (result.label ==
  prediction.predicted_class)` computed TL-side (SC stays correctness-free).
  `_parse_bar_type` RELOCATED here VERBATIM (regex + strip().lower() + ValueError message
  intact) as **public `parse_bar_type`** — its sole src consumer is the resolver build
  (`runtime._build_honest_resolver`); parse unit tests kept alive in
  `tests/test_resolution_adapter.py` (2 accept forms + 5 reject cases).
- **D-D1b-c (bars semantics + entry price — SERVED SHAPE CHANGE).** `bars_to_resolution`
  is now the SC ZERO-BASED index of the resolving bar within the forward window; the
  retired tracker served a 1-based bar count (gate B normalized old−1 for comparison —
  same fact, now documented in `domain/outcomes.py` + the adapter). `Outcome`/`OutcomeDTO`
  gained `entry_price` (ADDITIVE) — the honest decision-time fill the excursions were
  anchored on, replacing the tracker's level-price anchor (which was never surfaced).
- **D-D1b-d (the drop surface).** New domain `DroppedPrediction` {prediction_id,
  touch_id, reason, decision_ts_utc, entry_price?} + `DroppedPredictionDTO`; WS frame
  `prediction.dropped` with payload `{"dropped": {…}}` (mirrors `prediction.resolved`'s
  `{"outcome": {…}}` wrapper); snapshot gains a `dropped` ring beside `outcomes` (SAME
  cap, `outcome_limit=500`); `RuntimeUpdate.dropped` (+ `has_deltas`); replay
  `_coalesce_replay_updates` accumulates it event-style (the audit-#N4 rule). Reason
  vocabulary = the SC `StreamDrop.reason` arms verbatim: registration {flatten, cutoff,
  no_fill} (entry None — never queried/no fill) + terminal {no_forward, no_resolution}
  (entry carried). Frontend: `MessageType` + DTO + `normalizeDropped` + store ring (cap
  100, de-dupe by prediction id, cleared on reset/clear) + per-prediction annotation
  (`prediction.dropped`, parallel to `prediction.outcome`) + IntelligencePanel `dropped`
  badge with the reason; drops NEVER enter `prediction.outcome`, so
  `normalizeOutcomeMarkers` produces no chart marker by construction.
- **D-D1b-e (runtime rewiring).** `_track_outcomes` serves resolver emissions through the
  adapter (resolutions → outcomes ring + `prediction.resolved`; terminal drops → dropped
  ring + `prediction.dropped`); registration-time drops from `_register_prediction` (ex
  `_register_dark` — same touch anchors, same fail-loud missing-anchor ValueError, same
  swallow-on-exception posture) ride the same `RuntimeUpdate`. New `_open_predictions`
  map (prediction_id → `Prediction`) correlates resolver keys back to predictions —
  populated on live registration, popped on emission, cleared in LOCKSTEP with
  `resolver.reset()` (reset / hot-swap / clear_predictions); an emission with no open
  prediction logs a warning and is skipped (lifecycle-bug guard, hot path never breaks).
  The dark ring, `dark_outcomes` property, `_append_dark`, and `_build_outcome_tracker`
  are DELETED — the resolver IS the serving path. **VERIFY-DRIVEN REPAIR (in-window):**
  the first cut guarded only `resolver.on_bar`, leaving the per-emission consumption
  (pop → adapt → ring-append) unguarded — a failing adaptation (e.g. the adapter's
  deliberate fail-loud arm, or a stale-pin AttributeError on a cold install) would have
  escaped the hot path and orphaned same-loop ring-appended drops off the
  `RuntimeUpdate`, contradicting the docstring's swallow invariant. Repaired with a
  PER-ITEM guard (a failing adaptation loses only that emission, logged; the bar's other
  emissions, the drops already collected, and the trade event all survive) and PINNED by
  `test_failing_adaptation_never_breaks_the_hot_path` (monkeypatched adapter raise →
  nothing propagates, loss logged, subsequent trades process).
- **D-D1b-f (ResolutionType TRIM — REMOVED).** `SESSION_END` and `NO_RESOLUTION` members
  REMOVED. Grep proof (backend/src + backend/tests + frontend/src, post-flip): zero
  references — the producers/consumers were exactly the deleted tracker, its deleted
  tests, and the deleted gate-B harness. Surviving string hits are unrelated: the contract
  key `label_policy.no_resolution_dropped` (fixture), the `StreamDrop.reason`
  "no_resolution" vocabulary (a drop reason, not a resolution type), and the adapter
  test's use of "session_end" as an example UNMAPPED label.
- **D-D1b-g (gate-B harness RETIRED — deleted).** `validation/d1_characterization_harness.py`
  deleted: its comparison subject (the tracker) is gone, and a single-path repoint would
  count resolver events while characterizing nothing. `backend/D1_CHARACTERIZATION.md`
  (untracked export) + git history are the record. `backend/validation/` is now empty and
  gone; TL's ruff invocation drops it from scope.
- **D-D1b-h (test accounting — the complete assertion-change enumeration).**
  (1) `tests/test_outcome_tracker.py` DELETED (−16) — every assertion tested the retired
  tracker/classification. (2) `tests/test_dark_honest_resolver.py` → git mv →
  `tests/test_honest_resolver_serving.py` (7 → 7, rewritten to the served surfaces):
  dark-ring assertions → outcomes/dropped ring + `RuntimeUpdate`/snapshot assertions;
  tracker-parallel assertions dropped WITH the tracker; the isolation test now asserts the
  dark surfaces are GONE + served streams stay domain-typed; includes the drop-frame
  END-TO-END test (flatten registration drop → `prediction.dropped` WS envelope) and the
  0-BASED-BARS-SERVED pin (first in-window bar resolves at index 0; the tracker would have
  served 1). (3) NEW `tests/test_resolution_adapter.py` (+13): mapping table ×3 labels,
  correctness both directions, fail-loud unmapped label, outcome-id uniqueness, drop
  mapping ×2, `parse_bar_type` ×2 accept + 5 reject. (4) `tests/test_inference_api.py`:
  the synthesized `Outcome` gains `entry_price` (construction would fail without it); the
  resolved-payload test ADDS a full key-set pin incl. `entry_price` (the old test asserted
  DTO round-trip equality only); NEW `test_dropped_prediction_envelope_validates` (+1).
  (5) `tests/test_api_contract.py`: both snapshot key-set assertions + the empty-snapshot
  key-set gain `"dropped"`; new `dropped == []` empty assertion. (6)
  `tests/test_strategy_core_acceptance.py`: docstring bullet removal ONLY — zero assertion
  changes. (7) Frontend: fixture builders gain the new required fields
  (`entryPrice`/`entry_price`, `dropped: null`) in viewModels/ChartWorkspace/
  IntelligencePanel/stores/client/normalize tests; `normalize.test.ts`'s full-equality
  `normalizeOutcome` expectation gains `entryPrice`; +5 new tests (store annotate/cap ×2,
  client route ×1, panel badge ×1, normalize ×1); the clear-test also asserts `dropped`
  clears. (8) +1 NEW `test_failing_adaptation_never_breaks_the_hot_path` (the
  verify-driven swallow pin, D-D1b-e). **Suite math: TL 420 → 419 = −16 +13 +1 +1 (dark
  file 7→8); frontend 137 → 142.**
- **D-D1b-i (adversarial-verify record + informational findings).** 6-agent read-only
  verify on the exact local commits: flip-correctness **FAIL → REPAIRED in-window**
  (the per-item guard, D-D1b-e — the other 5 lenses and the FAIL's own sweep verified
  registration semantics, lockstep, no-double-serve, caps, surfaces, deletion totality,
  adapter fidelity, frontend, and scope all clean at high confidence). INFORMATIONAL
  (recorded, deliberately NOT changed): (i) `StreamingHonestResolver.flush()` has no TL
  src caller — setups still open at a replay day-end / session shutdown are cleared by
  `reset()` without emitting their `no_forward`/`no_resolution` drops; LIVE continuity is
  unaffected (the next session's bars cross the ABSOLUTE cutoff and finalize via
  `on_bar`, exactly D-D1a-d's design), so this is an end-of-stream drop-GENERATION gap,
  not a transport gap — candidate flush hook at replay completion, future window. (ii)
  The frontend snapshot-with-drops seeding path is code-verified but not test-covered
  (the only snapshot fixture omits `dropped`; reconnect-to-older-backend clears stale
  drops via `?? []` — verified by reading). (iii) The cold-install pin reachability is
  the PIN NOTE above.

### Phase E — E1/E2 deviations / clarifications (two-axis versioning + registry router gate; cross-repo, 3 commits)

Ratified design implemented: CONTRACT v2 shape break; `ENGINE_VERSION` →
`PLATFORM_VERSION` (clean rename, no alias); contract `engine_version` →
`platform_version` + NEW required `strategy_version`; `strategy_id` = the registry
ROUTER KEY; `supported_by_runtime` becomes meaningful (QL writes True, TL refuses
False); deployed-bundle migration in scope; `contract_id` stamping re-sourced.

- **D-E-a (the axis rename, SC `8e5c017`).** `PLATFORM_VERSION = "strategy_core_platform_v1"`
  (the engine v1/v2/v3 lineage recorded as superseded history in the doc-comment);
  `CONTRACT_VERSION = "trade_lab_contract_v2"`; schema field renamed (same constraints) +
  `strategy_version: str` (1..64) required; loader hook `expected_engine_version` →
  `expected_platform_version` (same position/None-skip; error strings name the platform
  axis); plugin `strategy_version = "1"` UNCHANGED in value, its placeholder comment
  rewritten to load-bearing (stamped by QL, equality-checked by TL). Every recon-enumerated
  reference updated (tests, validation banners, doc-comments). +2 SC negatives (v1
  contract_version rejected at the FIRST check; missing strategy_version rejected).
- **D-E-b (QL emitter routes through the registry).** `build_strategy_contract` resolves
  `strategy_version = get_strategy(strategy_id).strategy_version` — an unknown id
  fail-closes EMISSION (an unroutable contract is never written); the explicit
  `strategy_core.strategies.touch_reversal` registration import precedes it (the registry
  is deliberately empty on a bare `import strategy_core`, D-B3c). The caller
  (`ml_training_tab.py`) passes `"touch_reversal"`, NOT `output_dir.name`; the dir name
  stays the bundle identity everywhere else. `dataset_config_hash` input renames
  `engine_version=` → `platform_version=` — cache tags ROLL by design (the axis is a hash
  input). FLAG SCOPE CLARIFICATION: `supported_by_runtime=True` applies to the FULL
  contract; the minimal non-`dashboard_utility` record stays `False` (schema-incomplete by
  design — it cannot load, so it must not advertise servability).
- **D-E-c (deployed-store migration — DELIBERATE NARROWING, the window's one design
  correction).** `scripts/migrate_contracts_v2.py` (idempotent, in-place,
  `strategy.json.pre_v2.bak` backups, sidecar regeneration branch — no-op, no sidecars
  exist) EXECUTED against the real store. The store held **6** bundles, not 3: legacy
  (no engine_version), engine-v1, engine-v2, and the 3 engine-v3. The prompt's rewrite
  spec (stamp `platform_v1` on every bundle) would have FORGED the structural binding for
  the v1/v2-engine bundles — the v2-engine bundle is SC-schema-valid (D-C1a) and would
  have ACTIVATED under semantics it was not built with, and discovery would have listed
  >3 (breaking the real-bundle gate's own acceptance). The first run did exactly that;
  it was caught, all 6 restored from backups, and the script corrected: ONLY
  `engine_version == "strategy_core_engine_v3"` bundles migrate (the platform axis
  RENAMES engine v3); non-v3 bundles stay at contract v1, fail-closed at the loader's
  first check — the same rejection class they had pre-E. Final run: 3 MIGRATED
  {v2, platform_v1, touch_reversal, strategy_version "1"} + 3 SKIP(not-migratable);
  re-run: 6 SKIP (idempotent). Per-bundle before/after output in the window report.
  NOTE: all 6 on-disk bundles carried `supported_by_runtime: true` pre-migration
  (including the never-True-emitting era — the A3 recon's "patched outside QL code"
  observation re-confirmed); migration left the flag as-is per spec.
  `models/NQ_20260603_233847/strategy.json` is git-TRACKED in QL (pre-dates the
  `models/` gitignore) — its migration is committed (`git add -f`); the other two live
  untracked on disk.
- **D-E-d (TL router gate, `9b00eb5`).** Both `model_registry` entries pass
  `expected_platform_version=PLATFORM_VERSION` (the D-C1a both-entries precedent). NEW
  shared `_strategy_binding_error`: (i) `get_strategy(contract.strategy_id)` — TL's first,
  intended import of the SC strategy registry (explicit registration import alongside);
  (ii) `plugin.strategy_version == contract.strategy_version`; (iii)
  `supported_by_runtime is True`. Discovery skips with a precise warning; activation
  raises `ModelValidationError` between contract load and model load. Check (iv): NEW
  `ModelRegistry(serving_strategy_id=…)` ctor param — production `app.py` passes the
  runtime service's wired plugin id (NEW `StrategyCoreService.plugin_strategy_id`/
  `plugin_strategy_version` properties); a registry-valid contract routed to another
  strategy is refused. The hardcoded wiring stays, now guarded.
- **D-E-e (stamping source).** `Prediction.contract_id` = `active.model_id` (the bundle
  dir name), not `contract.strategy_id` (now the shared router key). Byte-compatible with
  pre-E observed values (the contract previously restated the bundle name); pinned by
  test. UI-VISIBLE VALUE CHANGE (shape unchanged): `ModelStatus`/`ModelBundle`
  `strategy_id` DTO values become `"touch_reversal"` for migrated bundles (previously the
  dir name); per-bundle identity remains `model_id`. Report-key rename:
  `strategy_core_engine_version` → `strategy_core_platform_version` (both
  `strategy_core_service` sites: snapshot metadata + the feed-status mapper);
  `StrategyCoreService.engine_version` property → `platform_version`.
- **D-E-f (QL CI rider — 9.6 status change).** NEW `.github/workflows/ci.yml` mirroring
  TL's `backend-ci.yml` (py3.13, cold `pip install -e ".[dev]"` resolving the SC pin
  anonymously, `ruff check src tests`, `pytest -q`). 9.6: **DECLARED → ENFORCED pending
  the first green run**, which structurally requires the greenlight pin bump + push (the
  committed pin `c615e40` predates `PLATFORM_VERSION`; stated in the workflow file).
  Tooling alignment riders: ruff `py314`→`py313`, mypy `3.14`→`3.13`, `.python-version`
  → `3.13.1`. The two recorded `sys.path` debt items deliberately untouched.
- **D-E-g (test churn, enumerated — the complete list).** SC: `test_contract.py` fixture
  + assertions to the new axes, 2 renamed tests (matching/mismatch → platform), +2 new
  negatives; `test_databento_live_source.py` asserts the platform prefix. QL:
  `nodrift` — structural map gains `platform_version` (constant) + `strategy_version`
  (registry-sourced), fixture id → `touch_reversal`, `test_engine_version_is_stamped` →
  `test_platform_version_is_stamped`, `test_engine_version_is_v3` →
  `test_platform_version_is_v1_and_strategy_axis_is_registry_sourced` (+ flag True), NEW
  `test_unknown_strategy_id_fails_emission_closed`, loader round-trip + mismatch tests →
  the platform hook, the axis-boundary test now uses the RETIRED engine literal as the
  mismatch case; `repoint` — ids → `touch_reversal`,
  `…advertises_runtime_activation_blocked` → `…advertises_runtime_servable` (False→True;
  minimal record stays False with the rationale in-test), stamp/round-trip → platform;
  `acceptance_cli` — fixture → v2 shape, summary keys
  (`engine_version`→`platform_version` + new id/version keys), the flag-rejection test
  INVERTS (False now rejected, match string `supported_by_runtime=true`). TL:
  `test_engine_version_binding.py` → git mv `test_platform_version_binding.py`, 3 tests
  re-axised + 5 NEW negatives (v1-rejected, unknown-id at discovery AND activation,
  version-mismatch at both, unservable at both, serving-guard); `test_strategy_contract`
  unsupported-version literal v2→v1 (v2 is now the supported shape);
  `test_inference_engine` contract_id pin `startswith("NQ_")` → `== "good-model"`;
  `test_strategy_core_dependency` → PLATFORM_VERSION; `tests/fixtures/strategy.json` →
  v2 shape incl. the recon-flagged `mid_price_source` drift fix (`top_of_book` →
  `trade_price`, the emitter's value). **Suite math: SC 152→154 (+2); QL 739→740 (+1);
  TL 419→424 (+5).**
- **D-E-h (RECORDED-NOT-CHANGED — assigned to the E3 ledger).** (i) activation never
  consults discovery's `validation_ok` (covered near-equivalently by the model-binary
  feature check); (ii) checksum verification is sidecar-optional (silently skipped when
  absent — and the store has none); (iii) `ModelStatus.validation_ok` is hardcoded True
  for any active model; (iv) the section-default `forward_bar_type="tick"`
  (`section.py:131,153`) vs TL's `^(\d+)t$` `parse_bar_type` would REJECT a
  section-defaulted contract — plus the `closed_window` contract↔runtime scheme
  round-trip gap (`section.py:91-93`). All four are E3-band hardening items.
  **AMENDED at E3: ALL FOUR CLOSED** — see D-E3-g below.

### Phase E — E3 deviations / clarifications (envelope/section split, contract v3; cross-repo, 3 commits)

Ratified design implemented: classification by CONSUMER — platform-consumed fields
stay flat on the ENVELOPE (`contract_version`/`platform_version`/`strategy_id`/
`strategy_version`/`training_mode`/`supported_by_runtime`/`instrument`/`tick_size`/
`point_value`/`model`/`class_map`/`feature_set` SHELL (names/order_is_contractual/
nan_policy)/`label_policy` (+ NEW `barrier_mode`)/`inference`/`data_requirements`/
`provenance`); plugin-consumed fields move into ONE `section` subtree typed by the
plugin's `SectionModel` (`session_scheme`/`level_scheme`/`touch_rule`/
`feature_windows`/`research_session_experiment` + the interaction/approach feature
partition MOVED out of `feature_set`). `CONTRACT_VERSION` → `"trade_lab_contract_v3"`
(shape break #2, same fail-closed-at-first-check + in-place-migration pattern as v2).
E3 is BEHAVIOR-PRESERVING: the runtime still configures from wiring constants
(`default_touch_reversal_section()`); bundle sections are consumed only where their
fields were consumed before; the E2 serving guard (check iv) stays.

- **D-E3-a (the classification table as applied).** Envelope/section assignment is
  exactly the ratified list above. `label_policy` and `inference` are ENVELOPE
  (TL's resolver build `runtime.py:_build_honest_resolver` and the inference gate
  consume them — platform reads), so `TouchReversalSection` LOST its Phase-A
  `label_policy`/`inference` fields and GAINED `interaction_features`/
  `approach_features`. The partition validator moved with the partition: the
  section-LOCAL check (disjoint + duplicate-free) is a `model_validator` on
  `TouchReversalSection`; the envelope cross-check (partition == `feature_set.names`)
  is the new single-sourced `validate_feature_partition` helper, run at the TWO
  validation sites — QL emission and TL activation.
- **D-E3-b (the loader carrier, defined precisely).** New opt-in loader kwarg
  `validate_section_via_registry: bool = False`. When True, after envelope
  validation: `get_strategy(contract.strategy_id)` (fail-closed; the §9.1
  registry-time SectionModel assertion is now LOAD-BEARING) →
  `SectionModel.model_validate(section)` → the typed instance is attached to the
  returned contract as the private NON-FIELD attribute `_section_model`
  (`PrivateAttr`, settable on the frozen model) and read via the
  `StrategyContract.section_model` property. A `(contract, typed_section)` tuple
  return was ratified OUT; the loader keeps its plain single-return call shape, and
  reading `section_model` on a hooklessly loaded contract raises `ContractError`
  (fail closed — an unvalidated section is never handed back as typed). The
  registry import is LAZY inside the hook branch (the loader stays import-light;
  callers own the plugin-registration import, D-B3c).
- **D-E3-c (closed_window placement — interpretation recorded).** The prompt's
  "contract SessionWindow gains OPTIONAL closed_window" is implemented as the
  contract **SessionScheme** gaining `closed_window: SessionWindow | None = None`
  (the start/end PAIR is carried AS a SessionWindow; `crosses_midnight` is not
  meaningful for it and stays False) — the runtime `types.SessionScheme.closed_window`
  is scheme-level, so a per-window field could not express the CT scheme.
  `_contract_scheme_from_runtime` / `_runtime_scheme_from_section` are now
  drop-nothing BOTH directions; the `TRADE_LAB_CT_SESSION_SCHEME` round-trip
  (16:00–18:00 closed window) is pinned by `test_session_scheme_round_trips_drop_nothing`.
- **D-E3-d (the forward_bar_type landmine death — refines the prompt's wording).**
  `label_policy` left the section, so the section default no longer carries ANY
  `forward_bar_type` — the D-E-h(iv) landmine died by the MOVE, not by an edit. The
  surviving `"tick"` literal in the section default (`touch_rule.bar_type`) was
  fixed to the canonical production bar literal `f"{DEFAULT_TICK_COUNT}t"` ("147t",
  constant-sourced). The envelope's `forward_bar_type` has no SC-side default at
  all: the QL emitter sources it per-run (`du.bar_type`, production "147t").
- **D-E3-e (emission re-sourcing + recorded wire-shape facts).** QL's emitter
  builds a configured `TouchReversalSection` INSTANCE (`_build_touch_reversal_section`):
  the plugin's `default_touch_reversal_section()` supplies every structural value;
  ONLY per-run config is overridden (`du.bar_type`, the two windows,
  `level_proximity_pts`, the selected feature partition, the session-experiment
  scope); `section_instance.model_dump(mode="json", exclude_none=True)` IS the
  emitted subtree, and `barrier_mode` is sourced from the PLUGIN's `label_policy()`
  declaration. Two recorded projections: (1) `direction_from_side` keeps the shipped
  lowercase `low->long/high->short` form (still sourced from `DIRECTION_FROM_SIDE`;
  the plugin default's uppercase enum-value form is a cosmetic divergence,
  unconsumed by the plugin); (2) newly-emitted session blocks carry
  `crosses_midnight` ALWAYS (model_dump), while pre-E3 emission omitted it when
  False and MIGRATED bundles keep their old block shape verbatim — all three forms
  are SectionModel-identical after validation.
- **D-E3-f (migration #2).** `scripts/migrate_contracts_v3.py`, same proven
  pattern, with D-E-c's narrowing applied UP FRONT: ONLY
  `contract_version == "trade_lab_contract_v2"` bundles migrate; the store's
  legacy/v1 bundles SKIP with precise reasons and stay fail-closed at the loader's
  first check. Backups `strategy.json.pre_v3.bak` (never overwritten); restructure
  preserves kept fields byte-for-byte (five section fields + the feature_set
  partition moved verbatim; `barrier_mode: "fixed_points"` injected after
  `resolution`; `section` appended last); idempotent. EXECUTED against the real
  store: **3 MIGRATED** (`NQ_20260603_233847`/`NQ_20260604_012623`/`NQ_20260604_015413`)
  **+ 3 SKIP** (not migratable); re-run **6 SKIP**. All 3 migrated bundles re-load
  through the SC loader WITH the section hook + partition cross-check. The
  git-tracked `NQ_20260603_233847/strategy.json` migration is committed.
- **D-E3-g (the four D-E-h ledger items CLOSED).** (a) TL activation now runs the
  metadata cross-check FAIL-CLOSED (`_validate_against_metadata` → raise
  `ModelValidationError` on mismatch); (b) checksum sidecar ABSENT →
  `logger.warning` (was silent; fired visibly on all 3 real-store activations —
  the store still has no sidecars); (c) `ModelStatus.validation_ok`/`_detail` =
  the active bundle's REAL activation-time result carried on `ActiveModel` (no
  longer hardcoded True); (iv) closed by D-E3-c + D-E3-d. NOTE on the Phase-D
  Barrier debt: `barrier_mode` gives the CONTRACT a binding for the barrier
  interpretation ("fixed_points"|"r_relative", enum-constrained, default
  fixed_points; sourced from the plugin's declaration at emission) — the
  PROTOCOL-level gap (the `Barrier` Protocol cannot reach `trap_mfe_min`) is NOT
  in E3 scope and stays a named debt.
- **D-E3-h (KNOWN TL COUPLING — recorded, deliberately accepted).** Generic TL
  code duck-types touch-section attributes: `model_registry` imports the touch
  section's `validate_feature_partition`; `inference_engine._direction_from_section`
  reads `section.touch_rule.direction_from_side`; `feature_functions` reads
  `section.feature_windows`. Acceptable single-strategy behavior; the F-era cleanup
  moves these reads into the plugin.
- **D-E3-i (test churn, enumerated — the complete list).** SC: `test_contract.py`
  fixture → v3 envelope+section (strategy_id = the real router key); v1-rejection
  test re-targeted v2; RETIRED `test_feature_set_names_not_union_raises` (the
  FeatureSet validator moved); `test_feature_set_validator_independently` →
  `test_section_partition_duplicates_rejected`; +8 new (missing-section, hook
  positive carrier, section_model-without-hook fails, section unknown-key rejected
  + hookless still loads, section missing-group rejected, unknown strategy_id at
  the hook, partition cross-check, barrier_mode enum); `test_touch_reversal_plugin.py`
  section fixture drops label_policy/inference + gains the partition; +1 round-trip
  pin. **SC 154 → 162.** QL: `nodrift` — structural map drops the section-bound
  leaves + gains plugin-sourced `label_policy.barrier_mode`; allowlist drops the 7
  section-bound entries; coverage guard gains the `_PLUGIN_SECTION_FIELDS` source
  (+ stale/pairwise-disjoint checks); section-bound reads → `contract["section"]`;
  loader round-trips run the section hook and read `section_model`; +2 new
  (section-sourcing honesty incl. the partition cross-check; emission fail-closed
  on partition mismatch). `repoint` — section-bound reads repointed; round-trip
  reads `section_model`. `acceptance_cli` — `bar_type` + research-scope reads →
  the section subtree; fixture hand-migrated v3. **QL 740 → 742.** TL: fixture
  hand-migrated v3 (values byte-preserved; `barrier_mode` added;
  `forward_bar_type` stays "147t"); `test_strategy_contract` — the
  all-sections parse test loads hook-on and reads `section_model`; unsupported
  literal v1 → v2; the feature_set partition-mismatch loader negative →
  the section-hook rejection; `test_feature_functions` — fixture loads hook-on,
  section threaded through `LevelContext.from_contract`/`build_feature_vector`
  (signature change: both now take the typed section);
  `test_platform_version_binding` +4 new (invalid section at discovery AND
  activation; partition cross-check mismatch at activation; metadata mismatch
  rejected at activation; missing sidecar warns on the real activation path);
  `test_inference_engine` +1 (typed section + real validation result on
  ActiveModel). **TL 424 → 429.**
- **D-E3-j (REAL-BUNDLE GATE, post-migration — verbatim in the window report).**
  Discovery lists EXACTLY the 3 migrated bundles (the legacy/v1 bundles skip on
  contract_version v1, the v2-era backup-shaped contract on v2); all 3 ACTIVATE
  sequentially (= hot-swap) with typed `TouchReversalSection`s (bar_type 147t;
  per-bundle partitions 2+3 / 3+3 / 3+2), real validation results, and the new
  sidecar-absent warnings; an un-migrated v2 `.bak` copy (temp-dir probe) is
  skipped at discovery and REJECTED at activation on
  `unsupported contract_version 'trade_lab_contract_v2'`.

## Status table

| Phase | Step | Goal (short) | Status | Date | Commit | Harnesses passed | Notes/deviations |
|---|---|---|---|---|---|---|---|
| A | A1 | Introduce the StrategyPlugin Protocol + BarSpec/SetupState/DecisionEvent/Barrier types in strategy_core, unused | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; full SC suite 140 passed | New submodule `strategies/protocols.py`; declaration-only, unimported by runtime. D-A1, D-A1b. |
| A | A2 | Introduce the registry (@register + get_strategy(strategy_id)) in strategy_core/strategies/registry.py, empty | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; unwired-invariant check green | §9.1 registry-time assertion (isinstance StrategyPlugin + BarSpec tuple + SectionModel BaseModel); fail-closed get_strategy. Registry stays empty on `import strategy_core`. |
| A | A3 | Author TouchReversalSection SectionModel + a TouchReversalPlugin that wraps the existing functions, registered but not yet wired into the runtime | DONE | 2026-06-08 | `68eef26` | test_touch_reversal_plugin (5 incl. equivalence) + golden suite (12) green | Wraps build_zones→detect_touches verbatim; plugin owns level state (R1); scheme←section (R2, D-A3a); decision tf as config (R3, D-A3b). D-A3c..f. |
| B | B1 | Add an optional plugin param to StrategyRuntime.__init__, defaulting to None; when None, run the exact current state.py:271-280 block | DONE | 2026-06-08 | `1491921` | full SC suite 140 passed (incl. test_runtime_state/touches/touch_zones/levels + A3 test_touch_reversal_plugin); TL test_strategy_core_acceptance + test_strategy_core_replay_integration (3 passed vs branch SC); GATE test_production_pair_parity + test_duckdb_streaming_parity + test_decision_diff (3 passed, store+alpha_lab present) | None-path byte-identical (inner lines unchanged, +4 indent only); else = no-op `pass` (B2 placeholder); `plugin` added last (no param reorder); StrategyPlugin TYPE_CHECKING-only → registry stays empty. Only runtime/state.py changed. |
| B | B2 | Route _process_trade through plugin.on_bar_closed when a plugin is present, and construct StrategyRuntime with the registered TouchReversalPlugin in a feature-flagged path | DONE | 2026-06-08 | SC `7a5cc96`+`5061163`; TL `242c606` | full SC suite 145; test_b2_plugin_seam_parity (PART1); test_b2_wiring (resolver/W2/W4-lifecycle); GO-LIVE test_b2_golive_runtime_parity (real days 2025-07-15 339997 trades + 2025-07-07 306103 trades, OFF==ON per trade, 5 touches/6 zones); TL test_strategy_core_acceptance + test_strategy_core_replay_integration (3 OFF + 3 ON); decision-fn gates test_production_pair_parity + test_decision_diff (2 passed); ruff clean | flag SC_PLUGIN_ROUTING default OFF via wiring.touch_reversal_kwargs(); TL StrategyCoreService wired; lifecycle propagation + plugin load_prior_day_summary hook; plugin internal decision-tf gate REMOVED (runtime gates). Deviations D-B2f..k. |
| B | B3 | Make the plugin path the default for strategy_id="touch_reversal"; remove the dead hardwired duplicate only after a full green soak | DONE | 2026-06-09 | `85cb7b6` | pre-removal off-vs-on parity 7 (FINAL green, both paths present); digests frozen (off==on on 3,284,775 trades/path); full SC suite 144; real-data plugin regressions vs frozen digests (golive + multiday) 2; TL acceptance+replay 3; decision-fn gates 2; ruff clean | flip+delete: None path + `SC_PLUGIN_ROUTING`/`config.py` removed; plugin auto-attached (D-B3a, fail-loud non-default-scheme guard); off-vs-on real-data tests repurposed to frozen-digest regressions + seam/wiring converted (D-B3b); W2 guard retired (D-B3c); dead `_zones_for_detection`+`detect_touches` import removed, level_state fold/snapshot/dedup KEPT (D-B3d); fold-collapse + dedup-move SPLIT to S-B3a. 6-agent adversarial verify 5 PASS + 1 stale-comment fixed. |
| (added) | S-B3a | Collapse the redundant runtime level fold (D-B2a) + move the once-per-day `_touched_zone_keys` dedup INTO the plugin + flow the raw `Touch` back onto `RuntimeUpdate.touches` | DONE | 2026-06-09 | `f6e9be8` | frozen-digest regressions `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression` 2 (fixtures UNTOUCHED; 3,284,775 trades, 8 reset boundaries, byte-identical); full SC suite 144; TL acceptance+replay 3; decision-fn gates 2 (UNCHANGED); ruff clean | runtime `level_state`/`_zones_for_snapshot`/`_touched_zone_keys`/`_zone_key`/`_touch_zone_key_from_touch` DELETED; plugin = sole owner (on_event returns the level fold; new `current_levels`/`snapshot_zones` accessors; plugin-owned `_fired_keys`; `already_fired_keys` retired; key helper relocated verbatim); raw `Touch` flow-back verbatim; D-B2b RESOLVED plugin-owned (owner-ratified); D-B2i gate + D-B3a guard untouched. Deviations D-SB3a-a..g. 5-agent adversarial verify 5 PASS (high). the LAST Phase-B tidy, before C; split out of B3's flip+delete prompt (added step, not in plan §7 — per deviation rule) |
| (added) | S-B3b | Tidy: declare the plugin seed path (`set_static_levels`/`load_prior_day_summary`) in the StrategyPlugin Protocol; rename the repurposed drift-net files off their `test_b2_*`/`parity` names; de-stale the V3 matrix PDH/PDL row | DONE | 2026-06-09 | `19c64da` | full SC suite 144 (same tests, new paths); digest regressions under the NEW filenames `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression` 2 (fixtures untouched); ruff clean | closes S-B3a verify items (i)+(ii) and D-B3b's filename debt. §9.1 registry assertion now requires the seed hooks (deliberate strengthening). Living refs updated incl. the multiday file's live cross-import; historical PROGRESS mentions left as record. Deviations D-SB3b-a..c. TL pin bump DEFERRED to C1 (no TL-facing change). added step, not in plan §7 — per deviation rule |
| C | C1 | Repoint TL model_registry import from the local contract copy to strategy_core.contract, keeping today's flat StrategyContract shape | DONE | 2026-06-09 | TL `0e1c7ce` | TL full suite 435 passed + 1 skip (benchmark, flag-gated); real-bundle registry gate (exactly 3 v3 discoverable; all 3 activate end-to-end incl. hot-swap; legacy/v1/v2 rejected fail-closed); TL seam test_strategy_core_acceptance + test_strategy_core_replay_integration 3; QL suite 739 (incl. nodrift 9 + repoint 11); TL ruff clean; QL ruff unchanged (13 pre-existing, scratch files) | ALL 9 import sites (4 prod + 5 test) → strategy_core package root; engine hook at BOTH registry loader entries (D-C1a); legacy loads-unbound RETIRED, owner-ratified (D-C1b); fixture → minimal valid SC-v3, +2 keys only (D-C1e); binding tests → hook call shape (D-C1d); TL pin cbf9b99→c615e40 rode this commit (deferred S-B3b bump). 6-agent adversarial verify 6 PASS (high). Deviations D-C1a..e |
| C | C2 | Delete TL's local strategy_contract.py once nothing imports it | DONE | 2026-06-09 | TL `0e1c7ce` (same commit as C1) | full-repo grep: zero live importers (D-C2a); TL full suite 435 + 1 skip post-deletion; ruff clean | `domain/contracts/strategy_contract.py` + `__init__.py` git rm'd; emptied dir removed; only historical docs/plans prose + untracked BASELINE_REPORT.md/test.md still mention it (left as record) |
| D | D1 | Retire TL's local outcome tracker in favor of the engine's honest decision-time fill | DONE (pushed at the D1b greenlight — D1a DARK + D1b flip+delete) | 2026-06-10 | D1a: SC `c7564fd` + TL `c7f2a84`; D1b: SC `945f381` + TL `94610ff` (pushed at the D1b greenlight) | D1a: GATE A `test_d1_streaming_vs_batch_parity` EXACT per-touch parity (9 days, 42 touches/35 resolved, drops {flatten: 7}); GATE B characterization (29 preds; mean abs entry delta 55.6 ticks; 6 label changes; 5/29 correctness flips). D1b: SC suite 152 + ruff + b3 frozen-digest regressions 2 (fixtures untouched); TL suite 419 (= 420 − 16 tracker + 13 adapter + 1 dropped-frame + 1 swallow pin; dark file 7→8) + ruff; seam-by-name 4 (acceptance 3 incl. D2 guard + replay 1); frontend typecheck + vitest 142 (+5) + build green; 6-agent adversarial verify 5 PASS + 1 repaired | D1a: SC streaming resolver + trade ring + fail-loud activation validation; TL DARK seat (D-D1a-a..i). D1b: resolver SERVES via the new resolution adapter (TP/SL mapping, TL-side correctness, 0-BASED bars, additive `entry_price`, `resolved_ts` from new SC `StreamResolution.resolved_ts_utc`); drops surfaced (`prediction.dropped` + snapshot ring + RuntimeUpdate + frontend badge w/ reason, no chart marker); tracker + 16 tests + gate-B harness DELETED; ResolutionType SESSION_END/NO_RESOLUTION REMOVED (grep-proven); `parse_bar_type` relocated public; D2-guard tracker carve-out retired (D-D1b-a..i) |
| D | D2 | Confirm TL holds no local candle/session/level recompute, then assert it via test | DONE (pushed at the D1b greenlight) | 2026-06-10 | TL `73aa7df` | TL suite 420 passed 0 skipped (443 collected − 24 deleted engine tests + 1 new guard); strengthened guard + seam green; src-wide grep zero engine names; ruff clean | CandleEngine/_MutableCandle/CandleUpdate + SessionLevelEngine/_SessionRange/_DaySummary/LevelUpdate/SESSION_LEVELS/LEVEL_ORIGIN deleted, DTO types kept; guard = src-wide reintroduction ban + SessionClassifier confinement + DTO-surface pin with documented carve-outs; sessions.py NOT deleted (seed.py debt); httpx2→dev rider. Deviations D-D2-a..c + named debts |
| E | E1 | Introduce platform_version alongside ENGINE_VERSION, both stamped, loader fail-closes on either | DONE (pushed at the E greenlight) | 2026-06-10 | SC `8e5c017` + QL `baecf66` + TL `9b00eb5` | SC suite 154 (+2 negatives) + ruff + frozen b3 regressions 2 (fixtures untouched) + decision-fn gates 2 UNCHANGED; QL suite 740 + ruff; TL suite 424 + seam 4 + ruff | RATIFIED DEVIATION from the step wording: not "alongside" — a CLEAN RENAME (ENGINE_VERSION → PLATFORM_VERSION "strategy_core_platform_v1", no alias) + contract v2 shape break (engine_version→platform_version field, + required strategy_version); deployed store migrated in place w/ backups (3 v3 bundles; non-v3 deliberately not migratable — D-E-c). D-E-a..c,f |
| E | E2 | Add per-plugin strategy_version/strategy_id, fail-closed via registry-lookup equality; turn strategy_id into a router | DONE (pushed at the E greenlight) | 2026-06-10 | same window/commits as E1 | TL suite 424 (incl. 5 new gate negatives, both-entry coverage); REAL-BUNDLE GATE: exactly 3 migrated bundles discoverable, all 3 activate incl. hot-swap via the serving-guard registry, un-migrated .bak copy rejected on contract_version | strategy_id = registry ROUTER KEY end-to-end: QL emission resolves get_strategy (unknown id refuses to EMIT), TL gates both registry entries (resolve / version-equality / servable-flag / serving-id guard); contract_id stamping re-sourced to the active bundle id (byte-compatible); supported_by_runtime meaningful (QL True, TL refuses False, QL acceptance flipped). D-E-b,d,e,g,h |
| E | E3 | Decompose the flat StrategyContract into StrategyEnvelope + typed SectionModel; emit from the plugin | DONE (LOCAL — full stop before push) | 2026-06-10 | SC `dc14652` + QL `523ff98` + TL `3d79bc4` | SC suite 162 (+8 contract-v3 negatives, +1 round-trip pin, −1 retired FeatureSet validator test) + frozen b3 digest regressions 2 (fixtures untouched) + decision-fn gates 2 UNCHANGED + ruff; QL suite 742 (740+2) + ruff; TL suite 429 (424+5) + seam-by-name 4 + ruff + frontend untouched; migration #2 on the real store (3 MIGRATED + 3 SKIP, idempotent re-run 6 SKIP); REAL-BUNDLE GATE: exactly 3 discoverable, all 3 activate incl. hot-swap w/ typed sections, v2 .bak copy rejected on contract_version | CONTRACT v3 (shape break #2): envelope = platform-consumed flat keys (+ label_policy.barrier_mode, + SessionScheme.closed_window); ONE "section" subtree typed by the plugin's SectionModel via the loader's opt-in validate_section_via_registry hook (non-field section_model carrier); partition + its validator moved to TouchReversalSection + the validate_feature_partition cross-check at the two validation sites; QL emits the section FROM a configured plugin SectionModel instance; TL validates the section at BOTH registry entries + threads ActiveModel.section to the two read paths; D-E-h ledger items (a)(b)(c)(iv) ALL CLOSED. Deviations D-E3-a..j. |
| F | F1 | Extend the candle data shape with a BarSpec/kind and add CloseReason.INTERVAL, with TICK behavior unchanged | NOT STARTED |  |  |  |  |
| F | F2 | Mirror the TIME close trigger into the vectorized batch path and pin it with a new parity test | NOT STARTED |  |  |  |  |
| F | F3 | Validate archetype 2 (HTF-FVG/iFVG) end-to-end on the same interface as a NEW plugin, behind its own strategy_id | NOT STARTED |  |  |  |  |
| (added) | S9.9 | data-drive session-name set in StrategyLevelState (drop hardcoded asia/london); behavior-preserving; feeds F | NOT STARTED |  |  |  | added step, not in plan §7 — per deviation rule |

---

## Change log (newest first)

- **2026-06-10** — **E3 (contract v3 — envelope/section split + emission from the
  plugin + the D-E-h ledger) landed as LOCAL commits across all THREE repos → E3
  DONE locally — FULL STOP before push** (SC `dc14652` + QL `523ff98` + TL
  `3d79bc4` on `platform-refactor`; diffs exported as `E3_SC_DIFF.txt` /
  `E3_QL_DIFF.txt` / `E3_TL_DIFF.txt`). SC: `StrategyContract` becomes the
  platform ENVELOPE + ONE raw `section` subtree; the five plugin-consumed groups
  + the feature partition move into `TouchReversalSection` (partition validator
  with them; new `validate_feature_partition` cross-check for the two validation
  sites); loader gains the opt-in `validate_section_via_registry` hook with the
  NON-FIELD `section_model` carrier (single-return shape preserved, hookless
  access fails closed); `LabelPolicy.barrier_mode`
  (`fixed_points|r_relative`, default fixed_points); contract `SessionScheme`
  gains the optional `closed_window` pair — scheme adapters now round-trip
  drop-nothing BOTH directions (CT scheme pinned); the section-default
  `touch_rule.bar_type` "tick" → constant-sourced "147t" and the
  `forward_bar_type` landmine died with `label_policy`'s move to the envelope;
  `CONTRACT_VERSION` → v3 (shape break #2). QL: the emitter builds a configured
  `TouchReversalSection` INSTANCE (plugin default + per-run overrides) and
  `model_dump()`s it as the section subtree; `barrier_mode` sourced from the
  plugin's `label_policy()` declaration; the partition cross-check runs AT
  EMISSION; `scripts/migrate_contracts_v3.py` EXECUTED on the real store —
  **3 MIGRATED + 3 SKIP (not migratable), idempotent re-run 6 SKIP**, backups
  `strategy.json.pre_v3.bak`, the tracked bundle's migration committed. TL: BOTH
  `model_registry` entries load with the section hook (discovery
  skips-with-warning, activation raises); `ActiveModel` carries the TYPED
  `section` + the REAL metadata cross-check result; the partition cross-check
  runs at ACTIVATION; LEDGER (a) metadata cross-check FAIL-CLOSED at activation,
  (b) absent checksum sidecar now WARNS, (c) `ModelStatus.validation_ok` is the
  real result, (iv) closed SC-side; the two section read paths
  (`inference_engine` direction map, `feature_functions` windows/bands) thread
  `ActiveModel.section` (the duck-typed touch coupling recorded, D-E3-h).
  REAL-BUNDLE GATE (post-migration): exactly the 3 migrated bundles
  discoverable; all 3 activate incl. hot-swap with typed sections; an
  un-migrated v2 `.bak` copy rejected on contract_version. Gates on the final
  trees: SC **162** + ruff + frozen b3 digest regressions **2** (fixtures
  untouched) + decision-fn gates **2** UNCHANGED; QL **742** (740+2) + ruff; TL
  **429** (424+5) + seam-by-name **4** + ruff + frontend UNTOUCHED. Deviations
  **D-E3-a..j**. PLAN unmodified. PIN NOTE: SC `dc14652` is CONSUMER-FACING for
  BOTH consumers (the loader hook kwarg, the section model reshape, and the
  v3 CONTRACT_VERSION are all consumer-imported) — both pins bump to the final
  pushed SC sha AT GREENLIGHT as chore commits, per the standing pin convention.
- **2026-06-10** — **E GREENLIGHT executed and PUSHED (all three repos)** after the
  6-lens adversarial verify (6/6 PASS high; journal `wf_a70536bc-ba9`) and owner review
  of the exported diffs. No reviewed commit amended; greenlight work = new commits:
  (1) QL `e10d226` `chore: pin strategy-core @ E1 + CI branch filter` — pin
  `c615e40 → 8e5c017` (the LONG-DEFERRED 9.6 bump) + `ci.yml` `on.push.branches` +=
  `platform-refactor` (without it the 9.6-enforcing run could not fire before merge
  day); QL suite **740** + ruff green on the bumped tree. (2) TL `ef8a189` (same chore
  shape) — pin `945f381 → 8e5c017` + `backend-ci.yml` push trigger was main-only, +=
  `platform-refactor`; TL suite **424** + ruff green on the bumped tree. (3) This SC
  doc commit — status rows D1/D2/E1/E2 stripped of LOCAL qualifiers (D pushed at the
  D1b greenlight; E pushed at this one); 9.6 re-statused **ENFORCED pending the first
  green CI run** with the full pin history recorded; PLUS the axis-presentation pass on
  the four stale top-level docs the E verify flagged (README / MIGRATION /
  V3_COMPATIBILITY_MATRIX / validation README: ENGINE_VERSION → the PLATFORM_VERSION
  presentation). Safety asserts (4 reviewed shas exist unchanged + ancestry + clean
  trees + branch) ran before the pushes. PLAN unmodified.
- **2026-06-10** — **E-WINDOW (E1 two-axis versioning + E2 registry router gate) landed
  as LOCAL commits across all THREE repos → E1/E2 DONE locally — FULL STOP before push**
  (SC `8e5c017` + QL `baecf66` + TL `9b00eb5` on `platform-refactor`; diffs exported as
  `E_SC_DIFF.txt`/`E_QL_DIFF.txt`/`E_TL_DIFF.txt`). SC: `ENGINE_VERSION` →
  `PLATFORM_VERSION` ("strategy_core_platform_v1", clean rename, no alias);
  `CONTRACT_VERSION` → v2 (shape break); contract field `engine_version` →
  `platform_version` + NEW required `strategy_version`; loader hook →
  `expected_platform_version`; `strategy_id` re-documented as the REGISTRY ROUTER KEY;
  the plugin's `strategy_version="1"` is now LOAD-BEARING. QL: the emitter resolves
  `strategy_version` via `get_strategy` (unknown id fail-closes EMISSION), stamps the
  router id (caller passes "touch_reversal", not the dir name), flips
  `supported_by_runtime=True` (full contract; minimal stays False — schema-incomplete by
  design); `dataset_config_hash` input renamed (cache tags roll);
  `scripts/migrate_contracts_v2.py` EXECUTED against the real store — 3 v3-engine bundles
  migrated in place w/ `.pre_v2.bak` backups, idempotent; the prompt's blanket
  platform_v1 stamp was NARROWED to engine-v3-only after the first run exposed that it
  would FORGE the binding for the store's legacy/v1/v2-engine bundles (caught, restored
  from backups, corrected — D-E-c); acceptance gate flips to assert the flag True; NEW
  `.github/workflows/ci.yml` cold-install CI (9.6: DECLARED → **ENFORCED pending the
  first green run**, which requires the greenlight pin bump + push); tooling aligned
  py313. TL: BOTH `model_registry` entries pass the platform hook + the NEW 4-check
  strategy gate — get_strategy resolve / strategy_version equality / servable-flag /
  serving-id guard (`ModelRegistry(serving_strategy_id=…)` fed by the new
  `StrategyCoreService.plugin_strategy_id`); `Prediction.contract_id` re-sourced to the
  active bundle id (byte-compatible; UI-visible: bundle `strategy_id` DTO values become
  "touch_reversal"); report keys → `strategy_core_platform_version`; fixture → v2 (+ the
  recon-flagged `mid_price_source` drift fix); `test_engine_version_binding` → git mv
  `test_platform_version_binding` + 5 new negatives. REAL-BUNDLE GATE (post-migration):
  exactly the 3 migrated bundles discoverable; all 3 activate end-to-end incl. hot-swap;
  an un-migrated `.bak` copy rejected on contract_version. Gates on the final trees: SC
  **154** + ruff + frozen b3 regressions **2** (fixtures untouched) + decision-fn gates
  **2** UNCHANGED; QL **740** (739+1) + ruff src/tests clean (the 13 pre-existing
  scratch findings stand); TL **424** (419+5) + seam-by-name **4** + ruff + frontend
  UNTOUCHED. Deviations **D-E-a..h**. PLAN unmodified. PIN NOTE: SC `8e5c017` is
  CONSUMER-FACING for BOTH consumers — both pins (TL from `945f381`; QL's long-deferred
  from `c615e40`) bump to the final pushed SC sha at greenlight as chore commits.
- **2026-06-10** — **D1b GREENLIGHT executed and PUSHED** (SC `77015de..2cb27dc`, TL
  `4bb9290..5ede158` fast-forward to origin; QL untouched): the stale pre-amend sha in
  the D-D1b header fixed (SC `2cb27dc`); TL pin bumped to the pushed D1b SC sha
  `945f381` (TL `5ede158`, suite 419 + ruff green on the bumped tree); safety asserts
  (commit existence + ancestry + clean trees) passed before push.
- **2026-06-10** — **D1b (flip + delete: SERVE the honest resolver, RETIRE the tracker)
  landed as LOCAL commits → D1 DONE locally — FULL STOP before push** (SC `945f381` + TL
  `94610ff` on `platform-refactor`; QL untouched at `9b8e798`; diffs exported as
  `D1B_SC_DIFF.txt` / `D1B_TL_DIFF.txt` for owner review). SC PART 1 (additive):
  `StreamResolution.resolved_ts_utc` = the resolving bar's `close_ts_utc`, stamped in
  `on_bar`; the batch `OutcomeResult` deliberately stays timestamp-free (caller concern) —
  asymmetry documented in the `StreamResolution` docstring; gate A cannot arbitrate the
  field, so it is pinned by a NEW resolution-path unit test (the file had none — gate A
  owned resolutions; D-D1b-a). TL PART 2 (the flip): NEW
  `services/inference/resolution_adapter.py` maps `StreamResolution`+`Prediction` → served
  `Outcome` (tradeable_reversal→TP_HIT, blowthrough/trap→SL_HIT, fail-loud unmapped;
  correct computed TL-side; ZERO-BASED bars — the tracker was 1-based; NEW additive
  `entry_price` = the honest fill) and `StreamDrop`+`Prediction` → NEW `DroppedPrediction`;
  drops broadcast as `prediction.dropped`, ride the snapshot (`dropped` ring, same cap) +
  `RuntimeUpdate.dropped` + replay coalesce, and render in IntelligencePanel as a distinct
  badge with reason (no chart marker — drops never enter `prediction.outcome`);
  `ApplicationRuntime` serves resolver emissions through the adapter with the new
  `_open_predictions` correlation map (lockstep clear with `resolver.reset()`); the DARK
  ring + `dark_outcomes` + gate-B plumbing DELETED; `outcome_tracker.py` + its 16 tests
  DELETED (`parse_bar_type` relocated VERBATIM, now public in the adapter module);
  `ResolutionType.SESSION_END`/`NO_RESOLUTION` REMOVED (grep proof: zero post-flip refs);
  `validation/d1_characterization_harness.py` RETIRED (deleted — comparison subject gone;
  the md artifact + git history are the record); the D2 guard's tracker carve-out bullet
  removed ON SCHEDULE. Gates on the final trees: SC suite **152** + ruff + frozen b3
  digest regressions **2** (fixtures untouched); TL suite **419** (accounted exactly:
  420 − 16 tracker + 13 adapter + 1 dropped-frame + 1 swallow pin; dark file 7→8
  adapted); seam-by-name **4**; TL ruff clean; frontend typecheck clean + vitest **142**
  (137 + 5 new) + vite build green. Assertion changes enumerated in D-D1b-h. 6-agent
  read-only adversarial verify on the exact local commits: **5 PASS (high) + 1 FAIL
  REPAIRED in-window** (the `_track_outcomes` per-emission consumption was unguarded
  vs the docstring's hot-path swallow invariant → per-item guard + pinning test;
  D-D1b-e/D-D1b-i; informational findings recorded in D-D1b-i). Deviations
  **D-D1b-a..i**. PLAN unmodified. PIN NOTE: SC `945f381` is CONSUMER-FACING — TL's
  adapter reads `resolved_ts_utc`, so a cold install from the current `c7564fd` pin would
  AttributeError on the first resolution (dev editable masks it); the pin bump to the
  final pushed SC sha rides the greenlight as a NEW chore commit (same flow as
  `4bb9290`).
- **2026-06-10** — **D-WINDOW: D1a (streaming honest resolver, DARK) + D2 (shadow-engine
  deletion + guard) landed as LOCAL commits — FULL STOP before push** (SC `c7564fd`, TL
  `c7f2a84` + `73aa7df`; QL untouched; pushes + the TL pin amend await explicit owner
  greenlight after diff review — the SC D1a commit is consumer-facing, so per the pin
  convention TL's pin bumps to the final pushed SC sha AT GREENLIGHT). D1a: SC
  `decisions/streaming.py` `StreamingHonestResolver` (incremental `resolve_honest_outcome`
  over the outcomes kernel: register-at-decision with the exact flatten→cutoff→no_fill
  firing order; strict-window per-bar excursions; cutoff → no_forward/no_resolution drops),
  runtime trade ring + `trade_price_at` (price>0 ≙ the reference's row-validity; 30-min
  query bound; ctx stub backed; quotes_in_window stays a §9.10 stub), fail-loud
  forward-timeframe activation validation; TL runs the resolver DARK alongside the tracker
  (touch-anchored registration off the observation chain, same closed-bars hook, parallel
  500-cap dark ring, zero WS/DTO/frontend change; offset-mismatch warning once at
  activation). **GATE A: EXACT streaming==batch per-touch parity** over the 9 real store
  days (42 touches: 35 resolved {tradeable 25, blowthrough 7, trap 3} + drops {flatten 7};
  every drop-vs-outcome/reason/label/mfe/mae/bars/entry equal). **GATE B characterization**
  (real bundle through the registry, trades-only, live-like): 29 predictions, 29/29
  resolved both paths, mean |entry Δ| 55.6 ticks (max 226), 6 label changes, 5/29
  correctness flips, zero SESSION_END — `D1_CHARACTERIZATION.md` exported. Forced test
  adaptation (D-D1a-f): 5 pre-existing TL tests activated the 147t contract on
  (2,)-timeframes (the very hole the validation closes) → helpers now (2, 147). D2: the
  dormant `CandleEngine`/`SessionLevelEngine` shadow engines + 24 engine tests deleted (DTO
  types kept; oracle losses recorded D-D2-c), acceptance guard strengthened to an src-wide
  reintroduction ban + SessionClassifier confinement + DTO-surface pins (carve-outs
  documented in-test), httpx2 → dev extra (probe verdict: correct + load-bearing via the
  starlette-1.x cold-CI testclient; C-window verify item (ii) RESOLVED). Gates on the final
  trees: SC suite **144** + ruff; b3 frozen-digest regressions **2** (fixtures untouched);
  decision-fn gates **2**; gate A **1**; TL suite **442+1skip** at D1a and **420/0** after
  D2 (collection fully accounted); seam **3** (+ the new guard); TL ruff clean. Deviations
  **D-D1a-a..i, D-D2-a..c** + Phase-D named debts. PLAN unmodified. D1b = the flip+delete
  (serve the resolver, retire the tracker + SESSION_END + the WS surface), NEXT, pending
  greenlight.
- **2026-06-09** — **POST-C AMENDMENT (doc-only):** (1) **9.6 re-statused: pin DECLARED
  (c615e40), enforcement DEFERRED** — dev resolves SC via the editable install; nothing
  currently exercises the pin; NAMED DEBT added: **QL cold-install resolution check** (the
  analog of TL's cold-install CI), required to make 9.6 enforced rather than declared. The
  C-window record's "9.6 IMPLEMENTED" headlines are amended accordingly (Current state, the
  9.6 decision line, D-9.6a, the C-window entry below). (2) **Before-state CORRECTION
  (D-C1f), probe-verified:** through a temporary TL worktree at `be90af3` running the pre-C1
  LOCAL loader against the real store, the pre-C1 servable set was **{legacy
  `NQ_20260405_…iterations800_depth4`, UNBOUND}** only — all 3 v3 bundles failed
  `extra_forbidden` on `label_policy.decision_offset_minutes`, v1 failed the engine bind, v2
  failed SCHEMA (never reached the old loader's engine check). C1 therefore **FLIPPED** the
  served set {legacy-unbound} → {3× v3}; the recon's "3 activatable v3 bundles (pre-C1)"
  framing was wrong. Worktree removed after the probe; TL/QL untouched; PLAN unmodified.
- **2026-06-09** — **Phase C (C1+C2) landed → Phase C COMPLETE; 9.6 pin DECLARED
  (headline amended 2026-06-09: enforcement DEFERRED — see the POST-C AMENDMENT entry above)**
  (TL `0e1c7ce` + QL `9b8e798`, both on `platform-refactor`; SC CODE untouched — this record
  commit only). C1: all 9 TL import sites (4 production incl. the TYPE_CHECKING deep import +
  5 tests) repointed onto the `strategy_core` package root; the fail-closed engine gate is
  preserved single-sourced via SC's opt-in hook — `load_strategy_contract(...,
  expected_engine_version=ENGINE_VERSION)` at BOTH `model_registry` loader entries (discovery
  `_describe_bundle` AND activation `_load_contract` — the v2-class store bundle is SC-schema-
  valid, so a hookless discovery would have listed it; D-C1a). Legacy loads-unbound RETIRED,
  owner-ratified (D-C1b). Fixture regenerated as a minimal valid SC-v3 contract (+2 keys
  exactly; D-C1e); `test_engine_version_binding` rewritten to the hook call shape
  (matching loads / mismatched-v2 fails / absent fails; D-C1d). C2: local copy
  `trade_lab/domain/contracts/` DELETED with zero live importers by full-repo grep (D-C2a).
  9.6: QL declares + SHA-pins strategy-core byte-identically to TL's pin form at `c615e40`;
  TL's pin bumped cbf9b99 → c615e40 in the same TL commit (the deferred S-B3b bump);
  `requires-python` rider `>=3.14` → `>=3.13` (D-9.6a; editable stays for dev; QL `sys.path`
  script hacks recorded as debt). PIN CONVENTION: the pin tracks the latest SC commit with
  consumer-facing content; doc-only SC commits do not move it. Gates on the final trees:
  real-bundle gate THROUGH the repointed registry (exactly the 3 v3 bundles discoverable —
  `NQ_20260603_233847`/`NQ_20260604_012623`/`NQ_20260604_015413`; all 3 activated end-to-end
  incl. hot-swap; legacy/v1/v2 rejected with the unsupported-engine_version `ContractError`);
  TL full suite **435 passed + 1 skip** (benchmark, flag-gated, pre-existing); TL seam gates
  **3**; QL suite **739** (= pre-change baseline; incl. `test_strategy_contract_nodrift` 9 +
  `test_strategy_contract_repoint` 11); TL ruff clean; QL ruff unchanged vs baseline (13
  pre-existing findings in root scratch files); pin reachability `ls-remote` +
  `merge-base --is-ancestor` PIN-REACHABLE. Verified by a 6-agent read-only adversarial
  workflow (repoint-completeness / call-shape / gate-preservation / fixture-validity / scope /
  pin-correctness — **6 PASS, all high confidence**). Deviations **D-C1a..e, D-C2a, D-9.6a**.
  PLAN unmodified.
- **2026-06-09** — **S-B3b tidy landed → S-B3b DONE** (committed as SC `19c64da` on
  `platform-refactor`; post-Phase-B, pre-C1). Three recorded
  debts closed in one doc/declaration-only pass (no runtime/plugin behavior change; frozen
  digest fixtures untouched): (1) `StrategyPlugin` now DECLARES the seed path —
  `set_static_levels` + `load_prior_day_summary` — so the §9.1 registry-time assertion
  fail-closes a plugin missing the hooks at `@register` instead of an `AttributeError`
  mid-session (closes S-B3a verify item ii); (2) the repurposed drift-net files renamed off
  their stale `test_b2_*`/`parity` names via `git mv` (contents/function names/assertions
  unchanged; living refs updated incl. the multiday gate's live cross-import; map in
  D-SB3b-b — closes D-B3b's cosmetic debt); (3) the V3 compatibility matrix PDH/PDL row
  reworded to plugin-owned level state (closes S-B3a verify item i). Harnesses on the final
  tree: full SC suite **144** (same tests, new paths); digest regressions under the NEW
  filenames **2 passed** (fixtures untouched); ruff clean. TL/QL untouched; TL pin bump
  deferred to C1. Deviations **D-SB3b-a..c**. PLAN unmodified.
- **2026-06-09** — Phase B Step **S-B3a landed → S-B3a DONE, Phase B COMPLETE** (committed as SC
  `f6e9be8` on `platform-refactor` after review + a byte-identical diff comparison against the
  reviewed export; the LAST Phase-B step). One behavior-preserving collapse: the plugin's level state is now the
  SOLE source of levels, zones, and the first-touch dedup — the runtime's redundant copies
  (`self.level_state` + its fold, the snapshot reads + `_zones_for_snapshot` premark,
  `_touched_zone_keys`/`_zone_key`/`_touch_zone_key_from_touch` — exactly D-B3d's KEPT list) are
  DELETED. New wiring, each mirroring the exact deleted `StrategyLevelState` call:
  `RuntimeUpdate.levels` ← `plugin.on_event` return (`process_trade`); snapshot/update `zones` ←
  new `plugin.snapshot_zones(trading_day)` (`zones()` + premark, `None` → unmarked); snapshot
  `levels` ← new `plugin.current_levels()` (`levels()`); dedup = plugin-owned `_fired_keys`
  (premark + record inside `on_bar_closed`, cleared only on `reset()`; `already_fired_keys`
  RETIRED from the protocol; key helper relocated verbatim); raw `Touch` flow-back verbatim
  (no re-derivation/re-keying/filtering). D-B2b is RESOLVED plugin-owned (owner-ratified);
  D-B2i (runtime-owned decision-tf gate) and D-B3a (auto-attach + fail-loud guard) untouched;
  `decisions/dedup.py` stays (plugin-consumed only). Staleness fixes rode along (plugin/protocols/
  wiring/section/dedup docstrings, stale config `.pyc`). BYTE-IDENTITY proven on the final tree
  against the FROZEN, UNTOUCHED B3 digests: `test_b3_golive_plugin_regression` +
  `test_b3_multiday_reset_plugin_regression` **2 passed** (3,284,775 trades, 8 reset boundaries,
  every per-trade `to_dict()` + snapshot identical); full SC suite **144**; TL
  `test_strategy_core_acceptance` + `test_strategy_core_replay_integration` **3**; decision-fn
  gates **2** (UNCHANGED); ruff clean. Verified by a 5-agent read-only adversarial workflow
  (removal / sole-source / dedup-equivalence / non-vacuity / completeness — **5 PASS, all high
  confidence**). Deviations **D-SB3a-a..g** + surfaced-deferred items recorded above. PLAN
  unmodified.
- **2026-06-09** — Phase B Step B3 **FLIP + DELETE landed → B3 DONE** (IRREVERSIBLE; committed as
  SC `85cb7b6` on `platform-refactor` after review + a green re-verify of the final tree — full SC
  suite 144 + ruff clean + both real-data digest regressions). The touch strategy now runs ONLY
  through the registered `touch_reversal`
  plugin: deleted the `if self._plugin is None:` hardwired touch block in
  `runtime/state.py._process_trade` (plugin loop + `on_event` now unconditional), made the plugin
  mandatory (auto-attached when not supplied; fail-loud guard for a non-default scheme — D-B3a),
  deleted the `SC_PLUGIN_ROUTING` flag + `strategy_core/config.py` and made
  `runtime/wiring.touch_reversal_kwargs()` unconditional, and removed the dead
  `_zones_for_detection`/`detect_touches` import (D-B3d). The runtime's own `level_state` fold,
  the snapshot premark, and the `_touched_zone_keys` dedup are KEPT — the fold-collapse +
  dedup-into-plugin is split out to **S-B3a** (the last Phase-B tidy). ORDER (one-way door):
  ran the final off-vs-on parity green (**7 passed**) with both paths present, FROZE the canonical
  plugin-path digests from it (off==on cross-checked on **3,284,775 trades/path**), THEN removed;
  the off-vs-on real-data gates are repurposed to plugin-path regressions vs those frozen digests
  (D-B3b), seam→cross-bar, wiring resolver/W2 retired (D-B3c). Plugin-only drift net green: full
  SC suite **144**; `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression`
  **2**; TL `test_strategy_core_acceptance` + `test_strategy_core_replay_integration` **3**;
  decision-fn gates **2** (UNCHANGED); ruff clean. Verified by a 6-agent adversarial workflow
  (5 PASS high-confidence + 1 FAIL = a single stale comment, fixed). PLAN unmodified.
- **2026-06-09** — Phase B **B3 PRE-FLIP soak coverage added** (B3 still **NOT STARTED**;
  **no flip, no deletion** — default stays OFF, the hardwired touch block and the flag-OFF
  path both remain). New drift-net member `validation/test_b3_multiday_reset_parity.py`
  proves flag-ON == flag-OFF byte-identical across **9 consecutive real store days**
  (2025-07-10 → 2025-07-22) **AND 8 reset/restart boundaries** — the W4-across-boundaries
  breadth the 2-day, single-stream B2 go-live gate never reached. Reuses the go-live
  machinery (`_read_trades` + `_build_runtime` via `touch_reversal_kwargs()`, flag toggled
  OFF vs ON); rolls each day production-style (`reset()` + `load_prior_day_summary` PDH/PDL
  from the PRECEDING processed day + `set_static_levels` reference, all propagated to the
  plugin via W4); asserts `ua == ub` per trade through `StrategyRuntime.process_event` plus
  serialized cross-checks on every touch-bearing update and on the first trade/decision-bar
  after each reset; and white-box-asserts the plugin's `self._levels` == the runtime's
  `level_state` at every boundary and each day's end. **2,638,675 trades/runtime
  (5,277,350 process_event calls), 42 touches firing on all 9 days (non-vacuous), OFF==ON
  throughout.** Flag-ON drift net all green: full SC suite **145** (and 145 flag-OFF);
  `test_b2_plugin_seam_parity` + `test_b2_wiring` + go-live + this new test **7**; TL
  `test_strategy_core_acceptance` + `test_strategy_core_replay_integration` **3** ON (and 3
  OFF); decision-fn gates `test_production_pair_parity` + `test_decision_diff` **2**; ruff
  clean (`ruff check src tests`). Only an ADDED test file — no tracked source/plan edits.
- **2026-06-08** — Phase B Step B2 **PART 2 of 2 (WIRE-UP) landed → B2 DONE.** SC `5061163`
  on `platform-refactor`; Trade-Lab `242c606` on TL `platform-refactor`. Adds the SC-owned flag
  `SC_PLUGIN_ROUTING` (default OFF) via `strategy_core/config.py` + the single construction helper
  `strategy_core/runtime/wiring.py` `touch_reversal_kwargs()` (lazy plugin import on the ON branch only);
  wires TL `StrategyCoreService` to construct via `**touch_reversal_kwargs()`; adds `default_touch_reversal_section()`
  (round-trips to RESEARCH, W5); propagates `reset`/`set_static_levels`/`load_prior_day_summary` to the plugin
  (W4, + new plugin `load_prior_day_summary` hook); and REMOVES the plugin's internal decision-tf gate so the
  runtime is the sole gate authority (flag-ON byte-identical at any `decision_timeframe`). Harnesses: full SC
  suite 145; `test_b2_wiring` (resolver/W2/W4); GO-LIVE `test_b2_golive_runtime_parity` (real days 2025-07-15 +
  2025-07-07, 646K trades, OFF==ON through `StrategyRuntime.process_event`); TL `test_strategy_core_acceptance` +
  `test_strategy_core_replay_integration` 3 passed flag-OFF AND 3 passed flag-ON; decision-fn gates
  `test_production_pair_parity` + `test_decision_diff` 2 passed; ruff clean. Verified by a 5-agent adversarial
  workflow (W1–W5 + TL/completeness, all pass, high confidence; one W4 test-strength nit fixed). Default stays OFF;
  the hardwired block is NOT deleted (that is B3).
- **2026-06-08** — Phase B Step B2 **PART 1 of 2 (the plugin SEAM)** landed on `platform-refactor`,
  commit `7a5cc96`. Routes `_process_trade` through `self._plugin.on_bar_closed(bar, ctx,
  already_fired_keys)` when a plugin is present (else branch), folds each trade into the plugin via
  `on_event`, and builds an inert `RuntimePlatformContext`. New `decisions/dedup.py` single-sources the
  cross-bar zone key (I3); `protocols.py` `StrategyStep` += `touches`/`zones` and `on_bar_closed` +=
  `already_fired_keys`; new `runtime/context.py`. Production/TL construction is UNCHANGED (plugin-less →
  None path); the plugin path is reachable only from `tests/test_b2_plugin_seam_parity.py`. None-path
  byte-identical to B1 (I1); registry empty on `import strategy_core` (I2). Harnesses: full SC suite 141
  passed; the multi-bar seam-parity test proves plugin-path == None-path incl. cross-bar first-touch
  suppression (a zone fires once across 3 re-straddling bars); ruff clean. Verified by a 5-agent
  adversarial workflow (I1/I2/I3/I4 + completeness — all pass, high confidence; I4 empirically falsified:
  1 touch with premark vs 3 without). B2 stays IN PROGRESS — PART 2 (wire-up) pending.
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
