# Six Sigma (Black Belt toolset) applied to the Hygiene Flush Controller

Six Sigma's DMAIC cycle structures *why* each test exists. The FMEA (Failure
Mode and Effects Analysis) is the core "Analyze" tool: every high-risk
failure mode gets at least one test (marked `@fmea("FM-xx")` in the code,
and visible in `build/traceability.csv`).

> All numbers here come from the simulation in this repository, not from real
> field data. The method is the point, not the values.

## D – Define

**Problem statement:** Touchless WC controllers in public buildings and trains
must flush reliably, must not waste water through false triggers, and must
keep drinking-water pipes hygienic when the toilet is not used (Legionella
risk from stagnation).

**Voice of the Customer → CTQ (Critical to Quality):**

| Customer need | CTQ | Target (spec limit) |
|---|---|---|
| "It flushes when I leave" | User flush rate after valid visit | 100 % |
| "It doesn't waste water" | False flushes per 1000 passers-by | 0 |
| "Water stays hygienic" | Max time without water exchange | ≤ 72 h |
| "It doesn't flood" | Valve open time | ≤ 10 s, always |
| "Low service cost" | Battery / fault warning before failure | ≥ 7 days ahead |

**SIPOC (short):** Supplier = sensor, battery, water supply → Input = presence
signal, voltage, time → Process = flush control state machine → Output = valve
command, telemetry → Customer = user, facility manager, water-hygiene officer.

## M – Measure

| Metric | How measured | Result |
|---|---|---|
| Statement / branch coverage of `flush_ctrl.c` | `make coverage` (gcov) | 100 % / 100 % |
| Requirements with ≥ 1 passing test | `build/traceability.csv` | 9 / 9 |
| Tests | `make test` | 17 unit + 35 system |
| Field fault detection (simulated fleet, 60 devices × 90 days) | `make ml` | precision 0.94, recall 1.00, median 5 days to alarm |

**Measurement system check (MSA idea):** the test harness itself was tested –
with the overflow bug injected (`make bug-demo`) the suite *must* fail; it does
(TC-U15 and TC-17). A test suite that cannot fail measures nothing.

## A – Analyze: FMEA

Scale 1–10 for Severity (S), Occurrence (O), Detection (D). RPN = S × O × D.
"Before" = without the mitigation, "After" = with mitigation + tests.

| ID | Function | Failure mode | Effect | Cause | S | O | D | RPN before | Mitigation (design + test) | O | D | RPN after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FM-01 | Detect user | False trigger | Water waste | Passer-by, reflections, dirty IR window | 5 | 7 | 5 | 175 | 3 s min. presence (REQ-02); TC-02, TC-01 BVA; ML drift alarm | 3 | 2 | 30 |
| FM-02 | Detect user | Sensor stuck "present" | No flush, no hygiene flush | Object in front of sensor, HW defect | 7 | 4 | 7 | 196 | Stuck detection 10 min, hygiene flush keeps running (REQ-06); TC-11..13 | 4 | 2 | 56 |
| FM-03 | Hygiene | No water exchange > 72 h | Legionella growth, health risk | Toilet unused (holidays, closed coach) | 9 | 5 | 8 | 360 | Stagnation flush (REQ-04/05); TC-05..08, TC-19 | 2 | 2 | 36 |
| FM-03b | Valve | Valve does not seal | Water loss, flooding risk | Debris, worn seal | 8 | 3 | 7 | 168 | Max open time 10 s (REQ-03); ML leak alarm on post-close flow | 3 | 3 | 72 |
| FM-04 | Power | Battery empties during flush | Valve stays open (latching valve) | End of life, cold | 8 | 4 | 6 | 192 | Cut-off + close on brown-out (REQ-07); TC-14, TC-15, TC-20; ML battery forecast | 3 | 2 | 48 |
| FM-05 | Timing | 32-bit ms counter wraps | Wrong flush every 49.7 days | `since + dur` overflow | 6 | 6 | 9 | 324 | Unsigned subtraction (REQ-09); TC-U15, TC-17, `make bug-demo` | 1 | 2 | 12 |
| FM-06 | Water | Low pressure / clogged strainer | Bowl not clean | Limescale, building pressure | 5 | 4 | 8 | 160 | ML: liters-per-flush trend alarm | 4 | 3 | 60 |
| FM-07 | Software | RAM corruption of state variable | Undefined valve state | EMC, bit flip | 8 | 2 | 8 | 128 | `default:` closes valve, goes IDLE; TC-U17 | 2 | 3 | 48 |

**Pareto of RPN (before):** FM-03 (360) > FM-05 (324) > FM-02 (196) > FM-04
(192) → hygiene and timing first. These four carry 63 % of the total risk and
got boundary tests and fault-injection tests first.

**Root cause tools used:** 5-Why for FM-05 (why false flush? → elapsed() true
too early → `since + dur` wrapped → uint32 overflow → no overflow-safe time
helper), Ishikawa categories for FM-01 (Man: passer-by, cleaner; Machine: IR
window; Method: no debounce; Environment: sunlight/reflection).

## I – Improve

Design changes that came out of the FMEA, each with its test:

1. Overflow-safe `elapsed()` helper used for **all** timing → TC-U15, TC-17.
2. 100 mV hysteresis on battery thresholds (no flag toggling) → TC-U12, TC-20.
3. Fail-safe `default:` branch closes the valve → TC-U17.
4. Hygiene flush allowed in sensor-fault state (hygiene > comfort) → TC-12.
5. Debounced fleet alarms (3 days in a row) to avoid alarm fatigue → `make ml`.

## C – Control

* **CI** (`.github/workflows/ci.yml`) runs unit + system tests, coverage and
  the bug-injection check on every push → regressions cannot come back silently.
* **Traceability CSV** as audit evidence (REQ ↔ test ↔ technique ↔ FMEA).
* **Field control:** the anomaly detector is the "control chart" of the
  fleet; z-score limit ±6 σ against each device's own baseline.
* **Reaction plan:** alarm → ticket with explanation text (e.g. "water flows
  after valve closed → LEAK suspected") → service visit before failure.
