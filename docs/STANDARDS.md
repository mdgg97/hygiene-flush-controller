# Standards map

How the project relates to the standards that matter for SELCO-type sanitary
electronics and for the test process. "Covered" means: the project shows the
idea in code or documents – not a certification.

## Test process and quality

| Standard | What it asks for | Where in this project |
|---|---|---|
| **ISTQB Foundation Level (CTFL 4.0)** | Test levels, black-box techniques (EP, BVA, decision table, state transition, use case), experience-based (error guessing), risk-based testing | Unit = component test, system tests = system test; every test tagged with its technique (`@tech`) |
| **ISO/IEC/IEEE 29119-3** | Test documentation: test plan, test design, test case spec, test report | `docs/TESTPLAN.md`, test IDs, `build/traceability.csv` |
| **ISO/IEC 25010** | Product quality model (functional suitability, reliability, safety, maintainability) | Test plan maps the quality characteristics to tests |
| **ISO 9001** | Process approach, traceability, corrective action | Requirements ↔ tests ↔ FMEA, CI as control |
| **Six Sigma / DMAIC** (ISO 13053-1 describes DMAIC) | Define-Measure-Analyze-Improve-Control, FMEA | `docs/FMEA_DMAIC.md` |

## Sanitary products and drinking water

| Standard | Topic | Requirement in this project |
|---|---|---|
| **EN 15091** | Electronic opening and closing sanitary tapware | REQ-01, REQ-02, REQ-07 |
| **EN 14055** | WC and urinal flushing cisterns (flush volume, function) | REQ-03 |
| **EN 12541** | Pressure flushing valves and automatic closing urinal valves | REQ-03 |
| **EN 997** | WC pans with integral trap (flush volume classes, e.g. 6 l) | Telemetry model uses 6 l per flush |
| **VDI/DVGW 6023** | Hygiene in drinking-water installations (water exchange, stagnation) | REQ-04, REQ-05 |
| **DIN EN 806-5** | Operation and maintenance of drinking-water installations | REQ-04 |
| **TrinkwV 2023** (German Drinking Water Ordinance) | Legal frame, Legionella testing duty | Motivation of REQ-04 |

## Electronic control and cybersecurity

| Standard | Topic | Requirement in this project |
|---|---|---|
| **IEC 60730-1, Annex H** | Software in automatic electrical controls (class B: fault detection, timing) | REQ-06, REQ-07, REQ-09, FM-07 |
| **EN 18031-1** | Cybersecurity for internet-connected radio equipment (RED delegated act, mandatory since 1 Aug 2025) | Relevant for a BLE/gateway version; REQ-08 rejects unknown commands |
| **EU Cyber Resilience Act** (Regulation (EU) 2024/2847) | Security by design, vulnerability handling; reporting duties from 11 Sep 2026, full application 11 Dec 2027 | Next step: signed OTA update + SBOM (see README roadmap) |
| **MISRA C:2012** (industry guideline) | Safe C subset | Not yet checked – roadmap item (cppcheck MISRA addon) |

> Check the current edition of each standard before using it for a real product.
