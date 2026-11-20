# Test plan – Hygiene Flush Controller
Structure based on ISO/IEC/IEEE 29119-3, terms from ISTQB CTFL 4.0.

## 1. Scope
Test item: `src/flush_ctrl.c` (control logic) through two interfaces:
* **Component test** – direct C calls (`tests/unit`), white-box coverage.
* **System test** – black box through the DUT protocol (`tests/system`),
  today against the simulator (SIL), tomorrow against a board via UART (HIL)
  with the same test cases – only `dut.py` changes.

Out of scope: sensor hardware, valve hydraulics, BLE stack (roadmap).

## 2. Approach (risk-based)
Priority comes from the FMEA (`FMEA_DMAIC.md`): highest RPN first.
Techniques per risk:

| Risk area | Technique | Why |
|---|---|---|
| Thresholds (time, voltage, config) | BVA (2-/3-value) | Defects cluster at boundaries |
| Input classes (passer-by / user, battery ok / low / empty) | EP | One representative per class is enough |
| Combinations (hygiene due × presence × fault) | Decision table | Rules interact |
| Mode logic | State transition (0-switch coverage + invalid events) | It is a state machine |
| Real usage (daily visits, telemetry) | Use case | End-to-end value |
| Embedded classics (counter wrap, brown-out, RAM corruption) | Error guessing / fault injection | Experience-based |

## 3. Quality characteristics (ISO/IEC 25010)
Functional correctness (TC-01..10), reliability/fault tolerance (TC-11..15,
U17), safety (valve ≤ 10 s, close on brown-out), maintainability (100 %
branch coverage, HAL-free core), security (TC-18 rejects unknown commands).

## 4. Test cases (system level)

| TC | Title | REQ | Technique | FMEA |
|---|---|---|---|---|
| TC-01 | Min presence 2.99 / 3.00 / 3.01 s | 01, 02 | BVA | – |
| TC-02 | Passer-by classes never flush | 02 | EP | FM-01 |
| TC-03 | Delay 1 s and valve 4 s timing | 01, 03 | BVA | – |
| TC-04 | Flush duration 0 / 1 / 10000 / 10001 ms | 03 | BVA | – |
| TC-05 | Hygiene flush exactly at 72 h | 04 | BVA | FM-03 |
| TC-06 | Hygiene interval 23 / 24 / 168 / 169 h | 04 | BVA | – |
| TC-07 | Daily use resets hygiene timer | 04 | UC | – |
| TC-08 | Hygiene deferred while user present | 05 | DT | – |
| TC-09 | User returns during flush delay | 01 | ST | – |
| TC-10 | Presence during flush ignored | 03 | ST | – |
| TC-11 | Stuck sensor detected at 10:00.00 | 06 | BVA | FM-02 |
| TC-12 | Hygiene flush runs in fault state | 04, 06 | DT | FM-02 |
| TC-13 | Fault recovery without flush | 06 | ST | – |
| TC-14 | Battery partitions + boundaries | 07 | EP, BVA | FM-04 |
| TC-15 | Brown-out during flush closes valve | 07 | EG | FM-04 |
| TC-16 | Counters for lifecycle monitoring | 08 | UC | – |
| TC-17 | 32-bit tick wrap-around | 09 | EG | FM-05 |
| TC-18 | Unknown command rejected | 08 | EG | – |
| TC-19 | Hygiene due + user arrives in same tick *(AI-proposed, reviewed)* | 05 | ST | – |
| TC-20 | Battery hysteresis upper boundary *(AI-proposed, reviewed)* | 07 | BVA | – |

Component tests TC-U01..U17 are listed in `tests/unit/test_flush_ctrl.c`.

## 5. Entry / exit criteria
* Entry: code compiles with `-Wall -Wextra -Werror -Wconversion`.
* Exit: all tests pass, 100 % branch coverage of `flush_ctrl.c`, every REQ
  has ≥ 1 passing test, bug-injection run fails as expected.

## 6. Defect report template
ID · title · build · steps (DUT commands) · expected · actual · severity
(S from FMEA) · REQ · log excerpt (`EVT` lines) · attachments.

Example (found during this project, fixed): *"Corrupted state variable
leaves valve open"* – TC-U17 – S8 – the `default:` branch went to IDLE but did
not close the valve. Fix: close valve in `default:`. Retest: pass.
