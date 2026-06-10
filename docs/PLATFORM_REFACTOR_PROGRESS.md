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

- **Active phase:** **Phase D — D1 DONE locally (D1a + D1b), D2 DONE locally; ALL LOCAL, NOT pushed.** **D1b (flip + delete) landed LOCALLY** (SC `945f381` + TL `94610ff`, both on `platform-refactor`): the dashboard now SERVES the streaming honest resolver — resolutions adapt to served `Outcome`s (entry = the real trade print, NEW `entry_price` field; TL-side correctness; SC ZERO-BASED `bars_to_resolution`; `resolved_ts` from the new SC `StreamResolution.resolved_ts_utc`), drops surface explicitly (`prediction.dropped` WS frame + snapshot `dropped` ring + `RuntimeUpdate.dropped` + IntelligencePanel badge w/ reason, NO chart marker), and the legacy `OutcomeTracker` + its 16 tests + the gate-B characterization harness are DELETED; `ResolutionType.SESSION_END`/`NO_RESOLUTION` REMOVED (grep-proven zero refs). Gates: TL suite **419** (= 420 − 16 tracker + 13 adapter + 1 dropped-frame + 1 swallow pin); seam-by-name **4** (acceptance 3 incl. the D2 guard + replay 1); TL ruff clean; frontend typecheck + vitest **142** + build green; SC suite **152** + ruff + frozen b3 regressions **2** (fixtures untouched). 6-agent adversarial verify on the exact commits: **5 PASS (high) + 1 finding REPAIRED in-window** (the `_track_outcomes` per-item swallow guard). Prior D-window state (D1a DARK SC `c7564fd` + TL `c7f2a84`; D2 TL `73aa7df`) unchanged beneath. Decision 9.6 unchanged (pin DECLARED c615e40; enforcement DEFERRED; QL cold-install debt open).
- **Next step:** **FULL STOP — owner review of the D1b diffs (`D1B_SC_DIFF.txt` / `D1B_TL_DIFF.txt`), then push at greenlight.** PIN NOTE: SC `945f381` (D1b PART 1) is CONSUMER-FACING — TL's adapter reads the new `StreamResolution.resolved_ts_utc`, so a COLD install from TL's current pin (`c7564fd`, D1a) would AttributeError on the first resolution (dev resolves SC editable, masking it) — per the pin convention TL's pin bump to the final pushed SC sha rides the greenlight as a NEW chore commit (same flow as the D-window pin chore `4bb9290`); QL's bump stays deferred to its next window.
- **Drift-net status:** **S-B3a DONE (fold-collapse + dedup-into-plugin), byte-identical.** The runtime's `level_state`, `_zones_for_snapshot`, `_touched_zone_keys`/`_zone_key`/`_touch_zone_key_from_touch` are DELETED; `RuntimeUpdate.levels` ← `plugin.on_event` return, snapshot/update `zones` ← `plugin.snapshot_zones`, snapshot `levels` ← `plugin.current_levels`, dedup = plugin-owned `_fired_keys`, touches flow back VERBATIM. Proven against the **FROZEN, UNTOUCHED** B3 digests: `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression` **2 passed** (3,284,775 trades, 8 reset boundaries — every per-trade `to_dict()` + snapshot byte-identical). Full SC suite **144**; TL acceptance+replay **3**; decision-fn gates **2** (UNCHANGED); ruff clean. 5-agent adversarial verify: **5 PASS (all high confidence)**. Verified 2026-06-09 on the final tree.
- **Last-verified date:** 2026-06-09
- **Note (release, decision 9.6):** BOTH consumers now pin SC at `c615e40` (the post-S-B3b stamp commit): TL `backend/pyproject.toml:19` (bumped cbf9b99 → c615e40 in `0e1c7ce`, the deferred S-B3b bump) and QL `pyproject.toml` (declared in `9b8e798`). PIN CONVENTION (clarification): the pin tracks the latest SC commit with CONSUMER-FACING content; doc-only SC commits (like this C-window record commit) do NOT move it. **STATUS (amended 2026-06-09): pin DECLARED (c615e40); enforcement DEFERRED** — dev resolves SC via the editable install; nothing currently exercises the pin. **NAMED DEBT: QL cold-install resolution check (the analog of TL's cold-install CI) — required to make 9.6 enforced rather than declared.**
- **B3-prep (PRE-FLIP soak):** the multi-day reset-bracketed real-data coverage authored as a soak (2026-06-09) is now **repurposed into the plugin-path regression** `test_b3_multiday_reset_plugin_regression` (9 days, 8 reset boundaries) vs the frozen digests — see the "Phase B — B3 deviations (flip+delete)" subsection.

---

## Decisions ratified (record verbatim)

- **9.1** = Protocol (+registry-time assertion).
- **9.2** = in-package registry module.
- **9.3** = two-axis version (platform_version + per-plugin strategy_version).
- **9.4** = time-bars land in Phase F.
- **9.5** = keep `strategy_core` name, layout `strategy_core/strategies/<id>/`.
- **9.6** = declare+SHA-pin strategy-core in Quant-Lab. **Pin DECLARED 2026-06-09 (QL `9b8e798`); enforcement DEFERRED:** pin `strategy-core @ git+https://github.com/thealgochef/Strategy-Core.git@c615e40ec13ef5a34d69910a78d144c677b138a8` added to QL `[project].dependencies`, byte-identical to TL's pin form; `requires-python` rider `>=3.14` → `>=3.13` (see D-9.6a). Dev resolves SC via the editable install; nothing currently exercises the pin. NAMED DEBT: QL cold-install resolution check (the analog of TL's cold-install CI) — required to make 9.6 enforced rather than declared.
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
| D | D1 | Retire TL's local outcome tracker in favor of the engine's honest decision-time fill | DONE (LOCAL, not pushed — D1a DARK + D1b flip+delete) | 2026-06-10 | D1a: SC `c7564fd` + TL `c7f2a84`; D1b: SC `945f381` + TL `94610ff` (all LOCAL) | D1a: GATE A `test_d1_streaming_vs_batch_parity` EXACT per-touch parity (9 days, 42 touches/35 resolved, drops {flatten: 7}); GATE B characterization (29 preds; mean abs entry delta 55.6 ticks; 6 label changes; 5/29 correctness flips). D1b: SC suite 152 + ruff + b3 frozen-digest regressions 2 (fixtures untouched); TL suite 419 (= 420 − 16 tracker + 13 adapter + 1 dropped-frame + 1 swallow pin; dark file 7→8) + ruff; seam-by-name 4 (acceptance 3 incl. D2 guard + replay 1); frontend typecheck + vitest 142 (+5) + build green; 6-agent adversarial verify 5 PASS + 1 repaired | D1a: SC streaming resolver + trade ring + fail-loud activation validation; TL DARK seat (D-D1a-a..i). D1b: resolver SERVES via the new resolution adapter (TP/SL mapping, TL-side correctness, 0-BASED bars, additive `entry_price`, `resolved_ts` from new SC `StreamResolution.resolved_ts_utc`); drops surfaced (`prediction.dropped` + snapshot ring + RuntimeUpdate + frontend badge w/ reason, no chart marker); tracker + 16 tests + gate-B harness DELETED; ResolutionType SESSION_END/NO_RESOLUTION REMOVED (grep-proven); `parse_bar_type` relocated public; D2-guard tracker carve-out retired (D-D1b-a..i) |
| D | D2 | Confirm TL holds no local candle/session/level recompute, then assert it via test | DONE (LOCAL, not pushed) | 2026-06-10 | TL `73aa7df` | TL suite 420 passed 0 skipped (443 collected − 24 deleted engine tests + 1 new guard); strengthened guard + seam green; src-wide grep zero engine names; ruff clean | CandleEngine/_MutableCandle/CandleUpdate + SessionLevelEngine/_SessionRange/_DaySummary/LevelUpdate/SESSION_LEVELS/LEVEL_ORIGIN deleted, DTO types kept; guard = src-wide reintroduction ban + SessionClassifier confinement + DTO-surface pin with documented carve-outs; sessions.py NOT deleted (seed.py debt); httpx2→dev rider. Deviations D-D2-a..c + named debts |
| E | E1 | Introduce platform_version alongside ENGINE_VERSION, both stamped, loader fail-closes on either | NOT STARTED |  |  |  |  |
| E | E2 | Add per-plugin strategy_version/strategy_id, fail-closed via registry-lookup equality; turn strategy_id into a router | NOT STARTED |  |  |  |  |
| E | E3 | Decompose the flat StrategyContract into StrategyEnvelope + typed SectionModel; emit from the plugin | NOT STARTED |  |  |  |  |
| F | F1 | Extend the candle data shape with a BarSpec/kind and add CloseReason.INTERVAL, with TICK behavior unchanged | NOT STARTED |  |  |  |  |
| F | F2 | Mirror the TIME close trigger into the vectorized batch path and pin it with a new parity test | NOT STARTED |  |  |  |  |
| F | F3 | Validate archetype 2 (HTF-FVG/iFVG) end-to-end on the same interface as a NEW plugin, behind its own strategy_id | NOT STARTED |  |  |  |  |
| (added) | S9.9 | data-drive session-name set in StrategyLevelState (drop hardcoded asia/london); behavior-preserving; feeds F | NOT STARTED |  |  |  | added step, not in plan §7 — per deviation rule |

---

## Change log (newest first)

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
