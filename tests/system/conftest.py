"""Pytest fixtures + a traceability report (test case -> requirement -> standard).

Every test carries @pytest.mark.req("REQ-xx") and @pytest.mark.technique("...").
After the run, build/traceability.csv lists each test with its requirement,
the ISTQB test technique and the verdict. This is the evidence an auditor
(ISO 9001 / IEC 60730 Annex H style) asks for.
"""
import csv
import os
import pathlib

import pytest

from dut import Dut

REQ_STANDARD = {
    "REQ-01": "EN 15091 (electronic opening/closing)",
    "REQ-02": "EN 15091 (false triggering)",
    "REQ-03": "EN 14055 / EN 12541 (flush volume, closing)",
    "REQ-04": "VDI/DVGW 6023, DIN EN 806-5, TrinkwV (stagnation)",
    "REQ-05": "VDI/DVGW 6023 (user safety during hygiene flush)",
    "REQ-06": "IEC 60730-1 Annex H (fault detection)",
    "REQ-07": "IEC 60730-1 Annex H / EN 15091 (power supply)",
    "REQ-08": "EN 18031-1 / CRA (logging, diagnostics)",
    "REQ-09": "IEC 60730-1 Annex H (timing, software class B)",
}

_rows: list[dict] = []


def pytest_configure(config):
    config.addinivalue_line("markers", "req(id): requirement covered by the test")
    config.addinivalue_line("markers", "technique(name): ISTQB test design technique")
    config.addinivalue_line("markers", "fmea(id): FMEA failure mode the test verifies")


@pytest.fixture
def dut():
    d = Dut()
    yield d
    d.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call":
        return
    reqs = [m.args[0] for m in item.iter_markers("req")]
    tech = ",".join(m.args[0] for m in item.iter_markers("technique"))
    fmea = ",".join(m.args[0] for m in item.iter_markers("fmea"))
    for r in reqs or ["-"]:
        _rows.append({
            "test": item.nodeid.split("::")[-1], "requirement": r,
            "standard": REQ_STANDARD.get(r, "-"), "technique": tech,
            "fmea": fmea, "verdict": rep.outcome.upper(),
        })


def pytest_sessionfinish(session, exitstatus):
    if not _rows:
        return
    out = pathlib.Path(os.environ.get("HFC_REPORT", "build/traceability.csv"))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(_rows[0]))
        w.writeheader()
        w.writerows(_rows)
