# Hygiene Flush Controller – firmware, tests and predictive maintenance

A small but complete portfolio project around a **battery-powered touchless WC
flush controller** with an automatic **hygiene (stagnation) flush** against
Legionella. It shows the full QA chain for embedded sanitary products:

```
requirements ─► C firmware core ─► unit tests (100 % branch coverage)
     │                │
     │                └─► simulator (virtual DUT, UART-like protocol)
     │                          └─► Python system tests (SIL → HIL-ready)
     │                                   └─► traceability report (REQ ↔ test ↔ standard)
     ├─► FMEA / DMAIC (Six Sigma) ─► risk-based test priorities
     ├─► ML: fleet telemetry ─► anomaly detection + battery forecast
     └─► GenAI: Claude proposes test cases ─► automatic gate ─► human review
```

## Quick start

```bash
pip install -r requirements.txt
make test        # 17 unit tests + 35 system tests
make coverage    # gcov: 100 % lines / 100 % branches of flush_ctrl.c
make bug-demo    # injects a timer-overflow bug -> the suites must FAIL
make ml          # simulated fleet (60 devices x 90 days) -> anomaly report
python3 ml/genai_testgen.py --dry-run      # see the prompt
python3 ml/genai_testgen.py                # needs ANTHROPIC_API_KEY
```

Needs only `gcc`, `make` and Python 3.10+.

## Layout

| Path | Content |
|---|---|
| `src/flush_ctrl.[ch]` | Hardware-independent control logic (state machine). No registers, no HAL – time, sensor and battery come in as parameters. |
| `sim/main.c` | Virtual DUT. Line protocol `PRES / BATT / ADV / TIME / CFG / STAT`, like a UART test port on a real board. |
| `tests/unit/` | Component tests in plain C, each named after its ISTQB technique and requirement. |
| `tests/system/` | pytest system tests. `dut.py` is the only part that changes for HIL (pyserial instead of subprocess). |
| `ml/generate_telemetry.py` | Synthetic gateway telemetry with injected faults (leak, sensor drift, battery drain, low pressure). |
| `ml/anomaly_detector.py` | Isolation Forest + z-score limit, debounced alarms, explanations, battery cut-off forecast. |
| `ml/genai_testgen.py` | Claude API with JSON-schema output → review gate (known REQ? valid technique? executable?) → human review. |
| `docs/` | Requirements, test plan (ISO/IEC/IEEE 29119-3), FMEA + DMAIC, standards map. |

## State machine

```
            presence
   IDLE ─────────────► OCCUPIED ── present ≥ 10 min ──► FAULT
    ▲  ▲                 │   │                           │  ▲
    │  │   left < 3 s    │   │ left ≥ 3 s                │  │ (hygiene flush
    │  └─────────────────┘   ▼                           │  │  still allowed)
    │                   WAIT_FLUSH ── back ──► OCCUPIED  │  │
    │                        │ 1 s                       │  │
    │  4 s                   ▼                           │  │
    └─────────────────── FLUSHING ◄── 72 h no flush ─────┘──┘
                         (valve open; closes at once below 4000 mV)
```

## Results

| Check | Result |
|---|---|
| Unit tests | 17 / 17 pass |
| System tests | 35 / 35 pass (20 test cases, some parametrised) |
| Coverage `flush_ctrl.c` | 100 % lines, 100 % branches |
| Requirements covered | 9 / 9 (see `build/traceability.csv`) |
| Bug injection (uint32 wrap) | caught by TC-U15 and TC-17 |
| Defect found by the tests | corrupted state left the valve open → fixed (TC-U17) |
| Predictive maintenance, simulated fleet | precision 0.94, recall 1.00, median 5 days to alarm (other seeds: precision 0.80–1.00) |

### Lesson from the ML part
An Isolation Forest trained on "healthy" data **missed every leak** at first:
its splits only cover the range seen in training, so a value 100 σ outside
gets almost the same score as one at the edge. Adding a simple z-score limit
fixed it (recall 0.20 → 1.00 on the default data set). Testing the detector like any other software,
with a known ground truth, found this.

### GenAI with a QA gate
The model may only *propose* tests. A rule gate rejects hallucinations (e.g. a
test for a requirement `REQ-11` that does not exist), duplicates and steps the
DUT cannot execute. Two proposals from `ml/sample_ai_output.json` were
reviewed and became TC-19 and TC-20.

## Roadmap
1. Port the core to an nRF52/ESP32 board, real IR sensor + latching valve;
   switch `dut.py` to pyserial → real HIL test bench.
2. BLE GATT service for telemetry (gateway → cloud), protocol fuzz tests.
3. Signed OTA update with rollback test, SBOM – Cyber Resilience Act.
4. MISRA C check (cppcheck addon) in CI.

---

## Interview summary

> I built a small portfolio project: a touchless WC flush controller with an
> automatic **stagnation flush** against Legionella, which is exactly SELCO's
> field. The logic is written in C and is hardware-independent, so I can test
> it on a PC. I designed the test cases according to **ISTQB** (boundary value
> analysis, equivalence partitioning, state transitions) and set the
> priorities with an **FMEA**. The unit tests reach 100 % branch coverage, and
> the system tests run over a serial interface: today against a simulator,
> later against real hardware as a **HIL** test. One highlight is a typical
> timer overflow bug after 49 days, and my tests catch it. I also used
> **machine learning** to analyse fleet data and detect leaks or empty
> batteries early, and **generative AI** to propose additional test cases,
> always with a human review.

Built with AI assistance as a learning and portfolio project. All field
numbers are simulated; standards are listed as orientation, not as certification.
