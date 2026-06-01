export const meta = {
  name: 'build-strategy-core',
  description: 'Port candle + decision + contract layers into strategy-core with tests, then adversarially verify fidelity to the research training path.',
  phases: [
    { title: 'Engine', detail: 'port 7 module groups + co-located unit tests in parallel' },
    { title: 'Verify', detail: 'run pytest + adversarial fidelity review vs canonical source' },
  ],
}

const ROOT = 'C:/Users/gonza/Documents/Strategy-core'
const BUILDER = 'C:/Users/gonza/Documents/Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/dashboard_utility_builder.py'
const LABELER = 'C:/Users/gonza/Documents/Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/dashboard_utility_labeling.py'
const QL_FEATURES = 'C:/Users/gonza/Documents/Claude-Quant-Lab/src/alpha_lab/experiment/features.py'
const TL_SEED = 'C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/seed.py'
const TL_CANDLES = 'C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/candles.py'
const TL_FEATS = 'C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/inference/features/feature_functions.py'
const TL_OUTCOME = 'C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/inference/outcome_tracker.py'
const TL_CONTRACT = 'C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/contracts/strategy_contract.py'

const COMMON = `
You are porting ONE module group into the shared engine package \`strategy-core\` at ${ROOT}.
The package is already pip-installed editable; new .py files under src/strategy_core are importable immediately.

FIRST, read these foundation files and use their EXACT names — do not invent or rename:
  ${ROOT}/src/strategy_core/__init__.py    (ENGINE_VERSION, CONTRACT_VERSION)
  ${ROOT}/src/strategy_core/types.py       (Trade, Quote, Bar, Level, Zone, Touch, Side, Direction, CloseReason, SessionWindow, SessionScheme, SessionInfo)
  ${ROOT}/src/strategy_core/constants.py   (all magic values + RESEARCH_SESSION_SCHEME)

HARD RULES:
- Import ONLY from strategy_core.types, strategy_core.constants, the Python stdlib, and numpy.
  (pandas is allowed ONLY inside candles/batch.py and the candle parity test — nowhere else.)
- NEVER import from Trade-Lab or Claude-Quant-Lab. This package has no dependency on either repo.
- Begin every module with \`from __future__ import annotations\`. Full type hints. Module + function docstrings
  that CITE the canonical source file:line you ported from. Match the house style of the foundation files.
- Reproduce the canonical behavior EXACTLY: same comparisons (<= vs <), same tie-breaks, same rounding,
  same empty-case values. Fidelity to the training path is the entire point (zero drift, money on it).
- Write your module(s) AND a co-located pytest test file under ${ROOT}/tests/. Tests must be deterministic:
  use fixed timezone-aware UTC datetimes (datetime(2025,6,2,13,30,tzinfo=timezone.utc)), never now()/random.
- Do NOT run pytest (a later phase does). You MAY run a single \`python -c "import strategy_core.<yourmod>"\`
  sanity check via Bash. If it fails only because a DIFFERENT concurrent module isn't written yet, ignore it.
- Return ONLY the structured summary.
`

const SUMMARY = {
  type: 'object',
  additionalProperties: false,
  required: ['files_written', 'public_api', 'sanity_import_ok', 'notes'],
  properties: {
    files_written: { type: 'array', items: { type: 'string' } },
    public_api: { type: 'array', items: { type: 'string' }, description: 'exact signatures of public functions/classes written' },
    sanity_import_ok: { type: 'boolean' },
    notes: { type: 'string', description: 'fidelity decisions, rounding, any parity caveat for phase 7' },
  },
}

phase('Engine')

const sessionsPrompt = `${COMMON}
MODULE: decisions/sessions.py  (+ tests/test_sessions.py)
Canonical source to read and match: ${BUILDER} lines 44-54 (_ET, session time constants) and 314-344
(_ensure_et_index, _slice_session). Also cross-check Trade-Lab's structure: ${TL_CANDLES} is NOT canonical for
sessions (it is Chicago); the canonical scheme is ET and already encoded as constants.RESEARCH_SESSION_SCHEME.

Implement THREE public functions, all parameterized by a SessionScheme (default constants.RESEARCH_SESSION_SCHEME):

1) classify_session(ts_utc: datetime, scheme: SessionScheme = RESEARCH_SESSION_SCHEME) -> SessionInfo
   - Convert ts_utc (must be tz-aware; raise ValueError if naive) to the scheme timezone via zoneinfo.ZoneInfo(scheme.timezone).
   - If scheme.closed_window is set and start <= local.time() < end: return SessionInfo(trading_day=None, session="closed", local_ts=local).
   - trading_day: if local.time() >= scheme.trading_day_boundary -> local.date() + 1 day, else local.date().
   - session name: the first window name in scheme.sessions whose SessionWindow.contains(local.time()) is True; if none match, "none".
   - return SessionInfo(trading_day, session_name, local).
   The canonical ET windows (from RESEARCH_SESSION_SCHEME): asia 18:00->01:00 (crosses midnight), london 01:00->08:00, ny_rth 09:30->16:15.
   Note the deliberate gaps: 08:00-09:30 and 16:15-18:00 ET are inside a trading day but in NO named window -> "none".

2) trading_day_for(ts_utc: datetime, scheme: SessionScheme = RESEARCH_SESSION_SCHEME) -> date | None
   - The trading-day primitive the candle builders share. Same rule as above; returns None for closed-window times.

3) is_in_closed_window(ts_utc: datetime, scheme: SessionScheme = RESEARCH_SESSION_SCHEME) -> bool

Tests: cover ET boundary cases — 17:59 vs 18:00 ET rollover (trading_day +1 at 18:00), 00:30 ET (asia, same day),
02:00 ET (london), 09:29 vs 09:30 ET (none -> ny_rth), 16:14 vs 16:15 ET (ny_rth -> none), a naive datetime raises,
and that the reference TRADE_LAB_CT_SESSION_SCHEME produces a closed window 16:00-18:00 CT (session "closed", trading_day None).`

const zonesPrompt = `${COMMON}
MODULE: decisions/zones.py  (+ tests/test_zones.py)
Canonical source to read and match EXACTLY: ${BUILDER} lines 382-411 (_build_zones).

Implement:
  build_zones(levels: list[Level], *, zone_proximity_pts: float = ZONE_PROXIMITY_PTS) -> list[Zone]
Behavior, byte-for-byte with _build_zones:
  - if not levels: return [].
  - sort levels by price ascending.
  - greedy merge: start groups=[[sorted[0]]]; for each next level, if (lvl.price - groups[-1][-1].price) <= zone_proximity_pts
    append to the current group, else start a new group. (Note: compares against the LAST level's price in the group,
    not the group min — preserve this exactly.)
  - per group: representative_price = mean(prices) = sum(prices)/len(prices); names = tuple of level.name in group order;
    side = Side.HIGH if (count of HIGH levels) > len(group)/2 else Side.LOW (strict >, so ties -> LOW); touched=False.
  - return list[Zone] in ascending price order.
Tests: single level; two levels 2.0 apart merge, 3.01 apart do not; exactly 3.0 apart merge (<=); majority-side tie -> LOW;
representative_price is the mean; chain-merge where consecutive gaps are each <=3 but span >3 total still merges (because
the compare is against the last level, not the first).`

const touchPrompt = `${COMMON}
MODULE: decisions/touch.py  (+ tests/test_touch.py)
Canonical source to read and match EXACTLY: ${BUILDER} lines 414-440 (_detect_touches).

Implement:
  is_touch(bar_low_points: float, bar_high_points: float, zone_rep_points: float) -> bool
      -> returns bar_low_points <= zone_rep_points <= bar_high_points  (closed interval, exactly as canonical line 429).

  detect_touches(bars: Sequence[Bar], zones: list[Zone], *, tick_size: float, trading_day: date,
                 direction_from_side: Mapping[Side, Direction] = DIRECTION_FROM_SIDE) -> list[Touch]
   - Iterate bars IN ORDER. For each bar compute low_points = bar.low_ticks*tick_size, high_points = bar.high_ticks*tick_size.
   - For each zone NOT yet touched (zone.touched is mutable state on the Zone): if is_touch(low_points, high_points, zone.representative_price):
       set zone.touched = True;
       direction = direction_from_side[zone.side]  (Side.LOW -> Direction.LONG, Side.HIGH -> Direction.SHORT);
       append Touch(bar_ts_utc=bar.close_ts_utc, representative_price=zone.representative_price, direction=direction,
                    level_type=zone.names[0], trading_day=trading_day).
   - first-touch-per-zone: once touched, a zone never fires again (matches canonical zone["touched"] guard).
   - return touches in detection order.
   IMPORTANT fidelity note to record: canonical uses the bar's index timestamp as the touch ts; we use bar.close_ts_utc.
   Flag this in notes as a phase-7 parity item (open vs close bar timestamp).
Tests: a bar straddling the zone rep fires; a zone fires only on its FIRST straddling bar (second is ignored); multiple
zones can fire on the same bar; LOW side -> LONG, HIGH side -> SHORT; boundary touch (rep == bar_high exactly) fires.`

const featuresPrompt = `${COMMON}
MODULE: decisions/features.py  (+ tests/test_features.py)
THIS IS THE ZERO-DRIFT-CRITICAL MODULE. Canonical source to read and match EXACTLY:
  ${BUILDER} lines 446-538 (_compute_interaction_features) — the 3 interaction features.
  ${QL_FEATURES} line 44 (LARGE_TRADE_THRESHOLD=10) and the approach SQL semantics (lines ~116-176) — the 3 live approach features.
Cross-reference (NON-canonical, do not copy its quote-mid behavior): ${TL_FEATS}.

CRITICAL: the canonical interaction-TIME features iterate TRADES and use the TRADE price
(builder:488 \`mid = ticks["price"]\`), NOT a top-of-book quote mid. constants.MID_PRICE_SOURCE == "trade_price".
Trade-Lab currently uses quote-mid over quotes — that is the drift we are removing. Implement the TRADE-price version.

Implement these pure functions (interaction features take trades; approach features as noted). Prices are integer ticks;
convert to points via tick_size. Round EXACTLY as the canonical return dict does.

  int_time_beyond_level(trades: Sequence[Trade], level_points: float, direction: Direction, tick_size: float,
                        *, max_gap_seconds: float = MAX_DWELL_GAP_SECONDS) -> float
    - sort trades by event_ts_utc ascending (stable). For j in range(len-1): dt = (trades[j+1].event_ts_utc - trades[j].event_ts_utc).total_seconds();
      if dt < 0 or dt > max_gap_seconds: continue. m = trades[j].price_points(tick_size).
      if direction is Direction.LONG and m < level_points: total += dt;  elif direction is Direction.SHORT and m > level_points: total += dt.
    - return round(total, 4).  Empty/one-trade -> 0.0.

  int_time_within_2pts(trades, level_points, tick_size, *, within_band_pts: float = WITHIN_BAND_PTS,
                       max_gap_seconds: float = MAX_DWELL_GAP_SECONDS) -> float
    - same dwell loop; predicate: abs(m - level_points) <= within_band_pts. return round(total, 4).

  int_absorption_ratio(trades, level_points, direction, tick_size, *, proximity_pts: float = LEVEL_PROXIMITY_PTS) -> float
    - iterate ALL trades (no dt loop). low=level-proximity, high=level+proximity. p=trade.price_points; s=float(trade.size).
      if low <= p <= high: at_level_vol += s;  elif (LONG and p<level) or (SHORT and p>level): through_vol += s.
    - total = at_level_vol+through_vol; if total <= 0: return 0.0; ratio = at_level_vol/total; return round(min(1.0, max(0.0, ratio)), 6).

  app_large_trade_vol_pct(trades: Sequence[Trade], *, large_trade_threshold: int = LARGE_TRADE_THRESHOLD) -> float
    - total = sum(size); large = sum(size for size>=threshold). if total <= 0: return float("nan"). else large/total. (no rounding)

  app_avg_trade_size(trades: Sequence[Trade]) -> float
    - if not trades: return float("nan"). else sum(size)/len(trades). (no rounding)

  app_max_spread(quotes: Sequence[Quote], tick_size: float) -> float
    - if not quotes: return float("nan"). else max((q.ask_price_ticks - q.bid_price_ticks)*tick_size for q in quotes). (no rounding)

Record in notes: (a) the trade-price vs quote-mid resolution, (b) that research drops touches with <5 ticks — that <5
filter is the ADAPTER's job, not these formulas (the formulas return 0.0/NaN on empty per the rules above),
(c) research rounds int time to 4 and absorption to 6 while Trade-Lab does not round — we round (canonical wins).
Tests: a hand-built trade list where you compute the expected dwell seconds by hand for LONG and SHORT; the >600s gap
is skipped; absorption with known at/through volumes gives the exact ratio; large_trade_vol_pct and avg_trade_size on a
known list; max_spread over known quotes; every empty-input case (0.0 for int_*, NaN for app_*).`

const outcomesPrompt = `${COMMON}
MODULE: decisions/outcomes.py  (+ tests/test_outcomes.py)
Canonical source to read and match EXACTLY: ${LABELER} lines 44-108 (label_touch_event, MAE-first ladder).
Cross-reference (already aligned): ${TL_OUTCOME} _classify lines 160-191.

Provide a shared MAE-first kernel AND a batch driver:

  classify_mae_first(max_mfe: float, max_mae: float, *, tp_points: float, sl_points: float, trap_mfe_min: float,
                     forced: bool = False) -> str | None
    - if max_mae >= sl_points: return TRAP_REVERSAL if max_mfe >= trap_mfe_min else AGGRESSIVE_BLOWTHROUGH.
    - if max_mfe >= tp_points: return TRADEABLE_REVERSAL.
    - if forced: return TRAP_REVERSAL if max_mfe >= trap_mfe_min else AGGRESSIVE_BLOWTHROUGH.
    - return None.
    (MAE checked FIRST so a bar breaching both stop and target resolves to the LOSS. Use constants for the label strings.)

  @dataclass(frozen=True, slots=True) class OutcomeResult:
      label: str; label_encoded: int | None; max_mfe: float; max_mae: float; bars_to_resolution: int

  resolve_outcome(entry_points: float, direction: Direction, forward_bars: Sequence[Bar], tick_size: float, *,
                  tp_points: float, sl_points: float, trap_mfe_min: float) -> OutcomeResult
    - max_mfe = max_mae = 0.0; label = NO_RESOLUTION; bars_to_resolution = -1.
    - for i, bar in enumerate(forward_bars): high=bar.high_ticks*tick_size; low=bar.low_ticks*tick_size.
        if LONG: bar_mfe = high-entry; bar_mae = entry-low.  else SHORT: bar_mfe = entry-low; bar_mae = high-entry.
        max_mfe = max(max_mfe, bar_mfe); max_mae = max(max_mae, bar_mae).
        decided = classify_mae_first(max_mfe, max_mae, tp_points=..., sl_points=..., trap_mfe_min=..., forced=False).
        if decided is not None: label = decided; bars_to_resolution = i; break.
    - label_encoded = LABEL_ENCODING.get(label) (None for no_resolution).
    - return OutcomeResult(label, label_encoded, round(max_mfe,4), round(max_mae,4), bars_to_resolution).
    Note: forward_bars must already be the post-touch bars truncated at the RTH cutoff — that filtering is the ADAPTER's
    job (canonical does it before calling label_touch_event). resolve_outcome does NOT itself apply the 16:15 cutoff.
Tests: a LONG that hits TP before SL -> tradeable_reversal at the right bar index; a LONG where a single bar breaches both
SL and TP -> the LOSS (trap or blowthrough) NOT the win (this is the MAE-first guard — assert it explicitly); SL with MFE
>= trap_mfe_min -> trap_reversal vs < -> aggressive_blowthrough; never resolved -> no_resolution, encoded None, bars -1;
SHORT direction mirrored.`

const candlesPrompt = `${COMMON}
MODULE GROUP: candles/batch.py, candles/streaming.py, a small shared candles/_ids.py (make_bar_id), AND tests/test_candle_parity.py.
Promote and GENERALIZE Trade-Lab's two builders so they are parameterized by a SessionScheme instead of hardcoded Chicago:
  BATCH (vectorized, pandas+numpy):  ${TL_SEED} lines 42-131 (build_tick_bars_from_frame).
  STREAMING (event-at-a-time):       ${TL_CANDLES} lines 103-196 (CandleEngine, _MutableCandle, make_bar_id).
Both must emit strategy_core.types.Bar (NOT Trade-Lab's Candle). Use CloseReason from types.

make_bar_id(timeframe_ticks: int, trading_day: date, bar_index: int) -> str  == f"{tf}t:{trading_day.isoformat()}:{bar_index}"  (put in candles/_ids.py; both builders import it).

streaming.py — class CandleEngine:
  __init__(self, timeframes: tuple[int,...] = (147, 987, 2000), *, scheme: SessionScheme = RESEARCH_SESSION_SCHEME)
  process_trade(self, trade: Trade) -> CandleUpdate  and process_event passthrough is not needed (no event union here; accept Trade only).
  Use strategy_core.decisions.sessions.trading_day_for(trade.event_ts_utc, self._scheme) for the trading day; if None (closed window) skip the trade.
  Keep the EXACT bar mechanics: per-timeframe current bar; on trading-day change freeze the open bar as END_OF_DAY (is_complete=False)
  and start fresh; accumulate high/low/close/volume/trade_count; when trade_count == timeframe freeze COMPLETE (is_complete=True) and clear.
  Provide CandleUpdate(completed: tuple[Bar,...], current: tuple[Bar,...]), snapshot_update, finalize_trading_day(),
  and _allocate_bar_index(timeframe, trading_day) (per-(timeframe,trading_day) counter from 0). Preserve the timeframe==1 special case
  (emit immediately as COMPLETE). NOTE: trading_day_for is written by a concurrent agent; if your sanity import fails for that reason only, ignore it.

batch.py — build_tick_bars_from_frame(frame: "pd.DataFrame", timeframes: tuple[int,...], *, scheme: SessionScheme = RESEARCH_SESSION_SCHEME, tick_size: float = DEFAULT_TICK_SIZE) -> list[Bar]
  frame has ts_event (UTC), price (tick-aligned points), size. Reproduce seed.py vectorized logic but parameterized:
   - localize ts to scheme.timezone; sod = hour*3600+min*60+sec.
   - trading_day = calendar_date + (sod >= seconds_of(scheme.trading_day_boundary) ? 1 day : 0).
   - if scheme.closed_window is set: drop rows where closed_start_sod <= sod < closed_end_sod (for RESEARCH_SESSION_SCHEME closed_window is None -> drop nothing).
   - price_ticks = rint(price / tick_size). sort by ts stable. group by trading_day; bar_index = cumcount()//timeframe;
     aggregate open/close/high/low/volume/trade_count; is_complete = (trade_count == timeframe); close_reason COMPLETE if complete else END_OF_DAY.
   Emit Bar objects identical in fields to the streaming output.

tests/test_candle_parity.py — THE KEY TEST: build a deterministic synthetic trade stream (fixed UTC timestamps spanning
an ET session, ~a few hundred trades, a couple of timeframes e.g. (3, 5)), feed the SAME trades to (a) CandleEngine via
process_trade then finalize_trading_day, and (b) build_tick_bars_from_frame via a pandas DataFrame, under RESEARCH_SESSION_SCHEME.
Assert the two Bar lists are IDENTICAL after sorting by (timeframe_ticks, trading_day, bar_index): every field equal
(open/high/low/close ticks, volume, trade_count, is_complete, close_reason, bar_id). Include trades that cross the 18:00 ET
trading-day boundary so the day-rollover END_OF_DAY behavior is exercised. Also add one test feeding the same stream under
TRADE_LAB_CT_SESSION_SCHEME and assert batch==streaming there too (proves the closed-window drop path is parity-safe).`

const contractPrompt = `${COMMON}
MODULE: contract/schema.py and contract/loader.py  (+ tests/test_contract.py)
Promote Trade-Lab's contract into the package as the SINGLE definition. Canonical source to port: ${TL_CONTRACT} (entire file).

schema.py:
  - Port every Pydantic model EXACTLY: _ContractModel (extra='forbid', frozen=True), Model, FeatureSet (with the
    names==interaction+approach partition validator), SessionWindow, SessionScheme, LevelScheme, TouchRule, FeatureWindows,
    LabelPolicy, InferencePolicy, DataRequirements, Provenance, ClassMap (string-key coercion + contiguous-from-zero +
    unique-labels validators + labels property + __len__), and StrategyContract.
  - ADD one new REQUIRED field to StrategyContract: \`engine_version: str = Field(min_length=1, max_length=64)\`, placed
    right after contract_version. This is the structural binding (spec §6). Keep contract_version too.
  - Import CONTRACT_VERSION and ENGINE_VERSION from strategy_core (the package __init__). Define ContractError(ValueError).
  - Do NOT change FeatureWindows.mid_price_source typing (it stays a free string field; the VALUE "trade_price" is set by
    the research emitter, not validated here).

loader.py:
  - load_strategy_contract(path, *, expected_engine_version: str | None = None) -> StrategyContract
  - Same fail-closed flow as canonical: unreadable -> ContractError; bad JSON -> ContractError; non-dict -> ContractError;
    contract_version != CONTRACT_VERSION -> ContractError. THEN, if expected_engine_version is not None and the payload's
    engine_version != expected_engine_version -> ContractError (this is the fail-close-on-engine-mismatch hook Trade-Lab will use).
    Then StrategyContract.model_validate(...) wrapping ValueError as ContractError.
  - Re-export the public names from contract/__init__.py is NOT your job (leave __init__ as-is).
Tests: build a COMPLETE valid contract dict in the test (every section, engine_version=ENGINE_VERSION, a 6-feature feature_set
whose names == interaction+approach, class_map {"0":"tradeable_reversal","1":"trap_reversal","2":"aggressive_blowthrough"});
assert it loads; assert wrong contract_version, wrong engine_version (with expected_engine_version set), an unknown extra key,
a non-contiguous class_map, and a feature_set whose names != union each raise ContractError. Write the dict to a tmp_path json file.`

const built = await parallel([
  () => agent(sessionsPrompt, { label: 'sessions', phase: 'Engine', schema: SUMMARY }),
  () => agent(zonesPrompt, { label: 'zones', phase: 'Engine', schema: SUMMARY }),
  () => agent(touchPrompt, { label: 'touch', phase: 'Engine', schema: SUMMARY }),
  () => agent(featuresPrompt, { label: 'features', phase: 'Engine', schema: SUMMARY }),
  () => agent(outcomesPrompt, { label: 'outcomes', phase: 'Engine', schema: SUMMARY }),
  () => agent(candlesPrompt, { label: 'candles', phase: 'Engine', schema: SUMMARY }),
  () => agent(contractPrompt, { label: 'contract', phase: 'Engine', schema: SUMMARY }),
])

phase('Verify')

const PYTEST = {
  type: 'object',
  additionalProperties: false,
  required: ['collected', 'passed', 'failed', 'errors', 'overall_ok', 'failing_tests', 'raw_tail'],
  properties: {
    collected: { type: 'integer' },
    passed: { type: 'integer' },
    failed: { type: 'integer' },
    errors: { type: 'integer' },
    overall_ok: { type: 'boolean' },
    failing_tests: { type: 'array', items: { type: 'string' } },
    raw_tail: { type: 'string', description: 'last ~60 lines of pytest output' },
  },
}

const REVIEW = {
  type: 'object',
  additionalProperties: false,
  required: ['module', 'fidelity_ok', 'findings', 'summary'],
  properties: {
    module: { type: 'string' },
    fidelity_ok: { type: 'boolean' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'detail'],
        properties: {
          severity: { type: 'string', enum: ['drift', 'minor', 'question'] },
          detail: { type: 'string' },
          engine_loc: { type: 'string' },
          canonical_loc: { type: 'string' },
        },
      },
    },
    summary: { type: 'string' },
  },
}

const pytestPrompt = `Run the strategy-core test suite and report results as structured data.
Run exactly: \`cd ${ROOT} && python -m pytest -q\` via Bash (use dangerouslyDisableSandbox only if a normal run is blocked).
Parse the summary line. Put the last ~60 lines of output in raw_tail. List node ids of any failing/erroring tests in failing_tests.
overall_ok = (failed == 0 and errors == 0 and collected > 0). Do not edit any files; only run and report.`

const reviewPrompt = (mod, engineFile, canonicalRef, focus) => `You are an adversarial fidelity reviewer. Read the WRITTEN engine module and the CANONICAL source side by side and hunt for ANY behavioral drift. Default to skepticism: if a detail could differ, flag it as a question.
WRITTEN: ${ROOT}/${engineFile}
CANONICAL: ${canonicalRef}
Focus points: ${focus}
Check specifically: comparison operators (<= vs <), tie-breaks, rounding (digits and whether rounding happens at all),
empty/edge-case return values, ordering/sorting, off-by-one in loops/indices, and any place the engine uses a different
data source than canonical (e.g. quote-mid vs trade-price). For each issue set severity: "drift" (engine will produce a
different value/behavior than the training path), "minor" (cosmetic), or "question" (needs human confirmation, e.g. the
bar open-vs-close timestamp). Give engine_loc and canonical_loc as file:line. fidelity_ok=true ONLY if there are no "drift"
findings. Do NOT edit anything.`

const verify = await parallel([
  () => agent(pytestPrompt, { label: 'pytest', phase: 'Verify', schema: PYTEST }),
  () => agent(reviewPrompt('features', 'src/strategy_core/decisions/features.py', `${BUILDER} (446-538) and ${QL_FEATURES} (44,116-176)`,
      'trade-price (not quote-mid) for the time features; dt<0 or dt>600 skip; <=2.0 within band; absorption proximity 0.5 and clamp[0,1]; rounding time->4 absorption->6; NaN vs 0.0 empty cases'),
      { label: 'review:features', phase: 'Verify', schema: REVIEW }),
  () => agent(reviewPrompt('touch', 'src/strategy_core/decisions/touch.py', `${BUILDER} (414-440)`,
      'closed-interval bar_low<=rep<=bar_high; first-touch-per-zone via touched flag; low->long high->short; level_type=names[0]; bar timestamp choice'),
      { label: 'review:touch', phase: 'Verify', schema: REVIEW }),
  () => agent(reviewPrompt('outcomes', 'src/strategy_core/decisions/outcomes.py', `${LABELER} (44-108)`,
      'MAE checked BEFORE MFE each bar; break on first resolution; trap vs blowthrough split at trap_mfe_min; no_resolution -> encoded None, bars -1; round mfe/mae 4'),
      { label: 'review:outcomes', phase: 'Verify', schema: REVIEW }),
  () => agent(reviewPrompt('sessions', 'src/strategy_core/decisions/sessions.py', `${BUILDER} (44-54, 314-344)`,
      'ET timezone; 18:00 trading-day rollover (>=); asia crosses midnight; ny_rth 09:30-16:15 with the 08:00-09:30 and 16:15-18:00 gaps as "none"; closed-window handling'),
      { label: 'review:sessions', phase: 'Verify', schema: REVIEW }),
  () => agent(reviewPrompt('candles', 'src/strategy_core/candles/streaming.py', `${TL_CANDLES} (103-196) and ${TL_SEED} (42-131)`,
      'streaming vs batch parity; trade_count==timeframe close; day-rollover END_OF_DAY; per-(tf,day) bar_index; scheme-parameterized trading day instead of hardcoded CT'),
      { label: 'review:candles', phase: 'Verify', schema: REVIEW }),
])

return { built, verify }
