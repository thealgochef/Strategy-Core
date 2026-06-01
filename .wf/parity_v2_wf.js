export const meta = {
  name: 'strategy-core-parity-4a-v2',
  description: 'Corrected phase-4a parity: full requested range, deterministic candle ordering (incl open/close), pipeline-order diff, real vectorized benchmark. Additive only.',
  phases: [
    { title: 'Harness', detail: 'build + run corrected harness over the full range' },
    { title: 'Audit', detail: 'independent re-derivation, additive/range compliance, candle determinism' },
  ],
}

const ROOT = 'C:/Users/gonza/Documents/Strategy-core'
const CQL = 'C:/Users/gonza/Documents/Claude-Quant-Lab'
const CQL_SRC = CQL + '/src'
const TL = 'C:/Users/gonza/Documents/Trade-Lab'
const DATA_DIR = 'C:/Users/gonza/Documents/Trade-Dashboard/data/databento'
const BUILDER = CQL_SRC + '/alpha_lab/agents/data_infra/ml/dashboard_utility_builder.py'
const TICKSTORE = CQL_SRC + '/alpha_lab/agents/data_infra/tick_store.py'
const PRIOR = ROOT + '/validation/parity_harness.py'

const ENV = `Environment (verified): python 3.13, duckdb 1.4.4, numpy, pandas, catboost installed. strategy-core pip-installed editable (import strategy_core works). alpha_lab is NOT importable by default — do \`import sys; sys.path.insert(0, r"${CQL_SRC}")\` BEFORE importing alpha_lab. Bars build ~0.5s/day in DuckDB. The PRIOR (passing but wrong-range, non-deterministic-candle) harness is at ${PRIOR} — read it to reuse its research-call patterns and decision-stage diffs.`

const HARNESS_PROMPT = `Build the CORRECTED phase-4a parity harness and run it. This is a money-path gate; report mismatches HONESTLY, never fudge. Additive only: do NOT edit/create/delete ANY file under ${CQL} or ${TL}; write only under ${ROOT}/validation/. Import the research code read-only.

${ENV}

WRITE ${ROOT}/validation/parity_harness_v2.py (report -> ${ROOT}/validation/_out/PARITY_REPORT_V2.md). Keep parity_harness.py untouched.

=== HARD REQUIREMENT 1: DAY RANGE ===
Process EVERY available NQ trading day in 2025-07-01 .. 2025-09-05 INCLUSIVE. Enumerate every calendar day in that range; a day is "available" iff ${DATA_DIR}/NQ/{YYYY-MM-DD}/mbp10.parquet exists and is non-empty. Run all available days; collect the rest into a missing list (weekends/holidays/gaps). Do NOT substitute days outside the range. Do NOT silently change the window. The report MUST state: total calendar days in range, available days run, and the explicit list of unavailable days. (Warm up prior-day session levels by ALSO processing the last available trading day BEFORE 2025-07-01 — e.g. 2025-06-30 — for PDH/PDL carry, but do NOT count it in the reported range.) Process days in ascending order carrying prev_ny_hl/prev_asia_hl/prev_london_hl (mirror ${BUILDER} build_utility_dataset:84-126).

PRODUCTION CONFIG: MLPipelineConfig(training_mode='dashboard_utility', instrument='NQ', tick_size=0.25,
  dashboard_utility=dict(bar_type='147t', interaction_window_minutes=5, approach_window_minutes=30,
  include_approach_features=True, tp_points=15.0, sl_points=30.0, trap_mfe_min=5.0, level_proximity_pts=0.5)).

=== HARD REQUIREMENT 2: DETERMINISM + CANDLE STAGE ===
The canonical book-mid bars come from DuckDB build_tick_bars (${TICKSTORE}:451-540): price=(bid_px_00+ask_px_00)/2.0,
bucket rn//147 via ROW_NUMBER() OVER (ORDER BY ts_event), HAVING COUNT==147, open=FIRST(mid ORDER BY ts_event),
close=LAST(mid ORDER BY ts_event), high/low=MAX/MIN(mid), volume=SUM(size), bar_time=LAST(ts_event)=CLOSE. With duplicate
ts_event, FIRST/LAST/ROW_NUMBER tie-break is NONDETERMINISTIC -> the prior run saw ~2.2% open/close diffs. FIX: impose a
stable TOTAL order (ts_event, original_source_row_sequence) and feed the SAME ordered events to BOTH a harness-local
reference bucketer AND the engine builder.

Build, per day, a DETERMINISTIC event frame (do this in PANDAS to guarantee source order — DuckDB scan order is not
guaranteed): read the day's window with pandas.read_parquet(file, columns=['ts_event','bid_px_00','ask_px_00','size','symbol','action'])
preserving file order; assign seq = np.arange(len). Window = research's: start=datetime(prev,23,0), end=datetime(cur,23,0)
(naive UTC, as ${BUILDER} _build_bars_for_date:276-279); register/union the prev AND current day parquet. Filter to
bid_px_00>0 AND ask_px_00>0 AND the dominant front-month symbol (symbol NOT LIKE '%-%', pick by count, exactly like
build_tick_bars:489-499). mid=(bid_px_00+ask_px_00)/2. Keep ts_event in [start,end]. Sort by ['ts_event','seq'] kind='stable', reset_index.

  REFERENCE BARS (harness-local, deterministic): bar_id = arange(len)//147; groupby bar_id; open=first(mid), high=max,
  low=min, close=last(mid), volume=sum(size), close_ts=last(ts_event), open_ts=first(ts_event), n=size; keep n==147.
  This is build_tick_bars' exact logic made deterministic by the (ts_event,seq) sort.

  ENGINE BARS: frame=DataFrame(ts_event=<UTC tz-aware>, price=mid (points), size=size) in the SAME sorted order; call
  strategy_core.build_tick_bars_from_frame(frame, (147,), scheme=strategy_core.RESEARCH_SESSION_SCHEME, tick_size=0.125).
  Take the COMPLETE bars (is_complete True). NOTE build_tick_bars_from_frame groups by trading_day (18:00 ET, DST-aware) and
  emits a trailing partial per group as END_OF_DAY — that partial is expected/by-design, exclude it from the equality set
  and report its count separately.

  STAGE 0 CANDLES [must_match]: compare REFERENCE BARS vs ENGINE complete BARS: count, open/high/low/close (engine ticks*0.125
  == reference value, abs tol 1e-9), volume, close_ts (instant-equal), open_ts. EXPECTATION after the deterministic sort:
  100% INCLUDING open/close. If NOT 100%, do NOT wave it off — find the FIRST diverging bar and classify the root cause:
  (a) tie-break (should be gone now), (b) trailing partial (exclude, benign), or (c) TRADING-DAY BOUNDARY: the engine uses a
  DST-aware 18:00 ET boundary while research's window edge is a hardcoded 23:00 UTC (=19:00 EDT in this summer range), so the
  engine may SPLIT the 18:00-19:00 EDT tail into a separate trading_day group, diverging from the continuous reference. If you
  see this, REPORT it as a concrete finding (day, the seam bar, both values) — it is a real engine-vs-research difference to
  resolve, not a logic bug to hide. Tally matched/mismatched and set first_diverging_layer if candles mismatch.

=== DECISION STAGES (reuse the prior harness approach; run over the full range) ===
Use research's bars B._build_bars_for_date(...)+_ensure_et_index for the decision stages' shared bar input (downstream uses
bar HIGH/LOW which are tie-break-independent, so these are unaffected by the determinism fix). DIFF IN PIPELINE ORDER so the
FIRST diverging layer is the root cause:
  STAGE A ZONES [must_match]: B._build_zones(levels) vs strategy_core.build_zones(engine Levels).
  STAGE B TOUCHES [must_match]: B._detect_touches(bars_et, fresh canon zones) vs strategy_core.detect_touches(engine Bars
    @tick0.125, fresh engine zones). Compare count, close-ts (instant), direction, representative_price, level_type.
  STAGE C SESSIONS [must_match]: for every bar ts, strategy_core.classify_session(ts).session vs canonical _slice_session
    masks (asia t>=18:00 or t<01:00; london 01:00<=t<08:00; ny_rth 09:30<=t<16:15; else 'none').
  STAGE D LABELS [must_match]: per touch, canonical forward=bars_et[idx>bar_ts][idx<rth_cutoff(16:15 ET)];
    L.label_touch_event vs strategy_core.resolve_outcome(entry=rep, dir, forward engine Bars @0.125, tp15/sl30/trap5).
    Compare label, label_encoded, round(mfe,4), round(mae,4). Skip touches with empty forward (both sides skip).
  STAGE E INTERACTION FORMULA FIDELITY [must_match]: feed IDENTICAL book rows (TickStore.query_tick_feature_rows for
    [event_ts, +5m]) to strategy_core int_* as Trade(price=mid@0.125, size) -> compare to B._compute_interaction_features.
  STAGE F INTERACTION TRADE-PRICE [expected_differ]: feed real TRADE prints (action='T', front-month, bid>0&ask>0) at
    tick 0.25 to strategy_core int_* -> REPORT |engine_trade - canonical_book| distribution; NEVER assert equality; NEVER
    revert the engine to book-mid.
  STAGE G APPROACH (3 model features) [must_match]: B._compute_approach_features vs strategy_core app_large_trade_vol_pct,
    app_avg_trade_size (over base∩action='T' trades), app_max_spread (over base = bid>0&ask>0 rows as Quotes), in
    [event_ts-30m, event_ts), front-month; abs tol 1e-6.

=== BENCHMARK (informational) ===
We are dropping DuckDB as the bar BUILDER in favor of the shared engine builder. Measure the SHARED builder as it will
actually run: fast columnar parquet READ (pandas/pyarrow lean columns) + vectorized strategy_core.build_tick_bars_from_frame
with the deterministic sort, vs the OLD all-DuckDB path (B._build_bars_for_date / TickStore.build_tick_bars), over the FULL
available range. Report total engine-builder seconds, total duckdb seconds, days, bars, and that I/O may dominate. Use the
REAL vectorized builder (not a naive python reshape — the prior "9s" was unoptimized).

=== REPORT (${ROOT}/validation/_out/PARITY_REPORT_V2.md) ===
- Requested calendar days, available days run, explicit list of unavailable days.
- Per-layer (Stage 0..G) match/mismatch AGGREGATE over the full range AND a compact per-day table (day -> each stage pass/fail + touch count).
- Candle confirmation: do candles match 100% incl open/close after the deterministic sort? If not, the first diverging layer + concrete example + root-cause classification (esp. the 18:00 ET vs 23:00 UTC/DST boundary).
- Every must_match mismatch: first diverging layer + concrete example (day, touch/bar, canonical vs engine values).
- Trade-price interaction divergence distribution (reported, not asserted).
- The real vectorized bar-builder benchmark numbers.
- ONE-LINE VERDICT: is the must-match set clean across ALL available requested days? yes/no.

PROCESS: First DIAGNOSE on a single summer day (e.g. 2025-07-02): build reference vs engine bars, print the candle comparison
structure (count, how many open/close match, any boundary split) so you understand the candle divergence shape BEFORE the full
run. Then run all available days. The full run may take several minutes (≈45 days × ~8M book events/day) — be patient, use a
long Bash timeout (e.g. 600000ms). Return the structured summary with REAL counts.`

phase('Harness')

const HARNESS = {
  type: 'object', additionalProperties: false,
  required: ['ran_ok', 'report_path', 'requested_calendar_days', 'available_days_run', 'unavailable_days', 'candles_match_incl_open_close', 'stages', 'must_match_all_pass', 'verdict', 'summary'],
  properties: {
    ran_ok: { type: 'boolean' },
    report_path: { type: 'string' },
    harness_path: { type: 'string' },
    requested_calendar_days: { type: 'integer' },
    available_days_run: { type: 'integer' },
    unavailable_days: { type: 'array', items: { type: 'string' } },
    total_touches: { type: 'integer' },
    candles_match_incl_open_close: { type: 'boolean' },
    candle_finding: { type: 'string', description: 'if candles not 100%: first diverging bar + root cause (tie-break / trailing partial / 18:00ET-vs-23:00UTC DST boundary)' },
    stages: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['stage', 'scope', 'total', 'matched', 'mismatched'],
      properties: {
        stage: { type: 'string' }, scope: { type: 'string', enum: ['must_match', 'expected_differ'] },
        total: { type: 'integer' }, matched: { type: 'integer' }, mismatched: { type: 'integer' },
        first_diverging_example: { type: 'string' }, divergence_summary: { type: 'string' },
      } } },
    benchmark: { type: 'object', additionalProperties: false, required: ['engine_builder_seconds', 'duckdb_seconds', 'days', 'bars'],
      properties: { engine_builder_seconds: { type: 'number' }, duckdb_seconds: { type: 'number' }, days: { type: 'integer' }, bars: { type: 'integer' }, notes: { type: 'string' } } },
    must_match_all_pass: { type: 'boolean' },
    verdict: { type: 'string' },
    summary: { type: 'string' },
  },
}

const harness = await agent(HARNESS_PROMPT, { label: 'build+run harness v2', phase: 'Harness', schema: HARNESS })

phase('Audit')

const AUDIT = {
  type: 'object', additionalProperties: false,
  required: ['check', 'pass', 'detail'],
  properties: { check: { type: 'string' }, pass: { type: 'boolean' }, findings: { type: 'array', items: { type: 'string' } }, detail: { type: 'string' } },
}

const auditRederive = `Adversarially audit the corrected parity harness by INDEPENDENTLY re-deriving from scratch — do not trust the harness code.
${ENV}
Read ${ROOT}/validation/_out/PARITY_REPORT_V2.md and ${ROOT}/validation/parity_harness_v2.py. (1) Pick one AVAILABLE day in
2025-07-01..2025-09-05 and one touch; independently confirm zone, touch (closed interval + close ts), and label (L.label_touch_event
vs strategy_core.resolve_outcome) agree — write your own throwaway script, don't reuse the harness comparison. (2) Independently
verify the CANDLE determinism claim on that day: build reference bars two ways (your own pandas (ts_event,seq) bucketer) and the
engine build_tick_bars_from_frame on the same ordered events, and confirm whether open/close match 100% — and if the harness
reported a 18:00-ET-vs-23:00-UTC boundary split, confirm it exists (or refute it). pass=true only if your independent results
agree with the report's must-match claims and its candle finding. check="independent_rederivation_v2".`

const auditCompliance = `Verify the corrected re-run's COMPLIANCE: additive-only AND correct range.
${ENV}
(1) ADDITIVE-ONLY: run \`git -C ${CQL} status --porcelain\` and \`git -C ${TL} status --porcelain\`; confirm the harness created
NO new files in either production repo (look for _bench*, _tmp*, parity*, validation*, scratch .py at repo roots). Research data-dir
cache files (ml_utility_*.parquet under ${DATA_DIR}) are acceptable (data dir, not a repo) — note if present.
(2) RANGE COMPLIANCE: from PARITY_REPORT_V2.md confirm the harness processed days ONLY within 2025-07-01..2025-09-05 (plus an
optional 2025-06-30 warm-up that must NOT be counted in the reported range), listed unavailable days explicitly, and did NOT
substitute out-of-range days. Cross-check a couple of the "available" days actually have mbp10.parquet and a couple "unavailable"
days actually lack it.
(3) SCOPING: confirm Stage F (trade-price) is reported-not-asserted and the engine was not reverted to book-mid.
pass=false if any repo file was added/modified by the harness, or the range was wrong, or scoping is wrong. check="additive_and_range_compliance".`

const audit = await parallel([
  () => agent(auditRederive, { label: 'audit:re-derive', phase: 'Audit', schema: AUDIT }),
  () => agent(auditCompliance, { label: 'audit:compliance', phase: 'Audit', schema: AUDIT }),
])

return { harness, audit }
