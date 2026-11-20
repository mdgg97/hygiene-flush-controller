# Requirements – Hygiene Flush Controller (HFC)

Product: battery-powered touchless WC flush controller with automatic hygiene
(stagnation) flush. Requirement IDs are used in code comments, tests and the
traceability report (`build/traceability.csv`).

| ID | Requirement | Acceptance criterion | Related standard / guideline |
|----|-------------|----------------------|------------------------------|
| REQ-01 | After a user was present for at least `min_presence` (default 3 s) and leaves, the valve opens after `flush_delay` (default 1 s). | Flush starts 1 s ± 10 ms after leaving. | EN 15091 (electronic opening and closing sanitary tapware) |
| REQ-02 | A presence shorter than `min_presence` (passer-by, cleaning staff) must not trigger a flush. | 2.99 s presence → 0 flushes. | EN 15091 |
| REQ-03 | The valve is open for `flush_duration` (default 4 s, configurable 1 ms–10 s). Values outside the range are rejected. | Valve closes 4 s ± 10 ms after opening; 10 001 ms rejected. | EN 14055 (flushing cisterns), EN 12541 (pressure flushing valves) |
| REQ-04 | If no flush happened for `hygiene_interval` (default 72 h, range 24–168 h), the controller flushes automatically (stagnation flush against Legionella). | Hygiene flush at exactly 72 h idle. | VDI/DVGW 6023, DIN EN 806-5, TrinkwV 2023 |
| REQ-05 | A hygiene flush must not start while a person is detected; it is deferred. | No valve opening while presence = 1. | VDI/DVGW 6023 (user safety) |
| REQ-06 | Presence that lasts longer than `sensor_stuck` (default 10 min) is a sensor fault. In fault state no user flushes happen, but hygiene flushes still run. The fault clears when the presence signal goes low. | FAULT at 10:00.00, recovery without flush. | IEC 60730-1 Annex H (fault detection, class B) |
| REQ-07 | Battery below `batt_warn` (4400 mV) sets a warning. Below `batt_cutoff` (4000 mV) the valve is disabled; an open valve is closed at once. 100 mV hysteresis. | 3999 mV → no flush; brown-out during flush → FLUSH_ABORT. | IEC 60730-1 Annex H, EN 15091 (power supply) |
| REQ-08 | The controller exposes state, flush count, hygiene flush count and error flags for diagnostics / lifecycle monitoring. Unknown commands are rejected. | STAT line correct after 5 user + 1 hygiene flush. | EN 18031-1 (radio equipment cybersecurity), EU Cyber Resilience Act |
| REQ-09 | All timing must work across the 32-bit millisecond counter overflow (every ~49.7 days). | No false flush when the counter wraps during a presence. | IEC 60730-1 Annex H (software timing) |

> Note: the standards are listed as orientation for a portfolio project. The
> default values (e.g. 72 h) follow common practice; for a real product the
> current editions of the standards must be checked.
