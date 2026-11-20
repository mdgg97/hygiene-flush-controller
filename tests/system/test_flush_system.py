"""System tests (black box, via the DUT protocol).

Test IDs TC-xx match docs/TESTPLAN.md. Techniques follow the ISTQB
Foundation Level syllabus: equivalence partitioning (EP), boundary value
analysis (BVA), decision table testing (DT), state transition testing (ST),
use case / scenario testing (UC), and experience-based error guessing (EG).
FMEA ids (FM-xx) come from docs/FMEA.md (Six Sigma, DMAIC "Analyze").
"""
import pytest

from dut import HOUR, MINUTE

req = pytest.mark.req
tech = pytest.mark.technique
fmea = pytest.mark.fmea


# --------------------------------------------------------------- REQ-01/02
@req("REQ-01")
@req("REQ-02")
@tech("BVA")
@pytest.mark.parametrize("stay_ms, expect_flush", [
    (2990, False),   # just below the 3 s boundary
    (3000, True),    # on the boundary
    (3010, True),    # just above
])
def test_tc01_min_presence_boundary(dut, stay_ms, expect_flush):
    dut.user_visit(stay_ms)
    assert (len(dut.flushes("USER")) == 1) is expect_flush


@req("REQ-02")
@tech("EP")
@fmea("FM-01")
@pytest.mark.parametrize("stay_ms", [100, 1500, 2500])   # partition "passer-by"
def test_tc02_passer_by_never_flushes(dut, stay_ms):
    dut.user_visit(stay_ms)
    assert dut.flushes() == []


@req("REQ-01")
@req("REQ-03")
@tech("BVA")
def test_tc03_flush_timing(dut):
    dut.presence(True); dut.wait(5000); dut.presence(False)
    t_leave = dut.status().t
    dut.wait(10_000)
    start = next(e for e in dut.events if e.name == "FLUSH_START")
    end = next(e for e in dut.events if e.name == "FLUSH_END")
    assert start.t - t_leave == pytest.approx(1000, abs=10)   # 1 s delay
    assert end.t - start.t == pytest.approx(4000, abs=10)     # 4 s valve


# --------------------------------------------------------------- REQ-03 config
@req("REQ-03")
@tech("BVA")
@pytest.mark.parametrize("value, accepted", [(0, False), (1, True), (10_000, True), (10_001, False)])
def test_tc04_flush_duration_limits(dut, value, accepted):
    assert dut.config("duration", value) is accepted


# --------------------------------------------------------------- REQ-04/05
@req("REQ-04")
@tech("BVA")
@fmea("FM-03")
def test_tc05_hygiene_flush_at_72h(dut):
    dut.wait(72 * HOUR - 10)
    assert dut.flushes() == []
    dut.wait(10_000)
    assert len(dut.flushes("HYGIENE")) == 1


@req("REQ-04")
@tech("BVA")
@pytest.mark.parametrize("hours, accepted", [(23, False), (24, True), (168, True), (169, False)])
def test_tc06_hygiene_interval_limits(dut, hours, accepted):
    assert dut.config("hygiene", hours * HOUR) is accepted


@req("REQ-04")
@tech("UC")
def test_tc07_regular_use_resets_hygiene_timer(dut):
    for _ in range(3):                     # one visit per day for 3 days
        dut.wait(24 * HOUR - 20_000)
        dut.user_visit(5000)
    dut.wait(24 * HOUR)
    assert dut.flushes("HYGIENE") == []
    assert len(dut.flushes("USER")) == 3


@req("REQ-05")
@tech("DT")
def test_tc08_hygiene_deferred_while_user_present(dut):
    dut.wait(72 * HOUR - 2000)
    dut.presence(True)
    dut.wait(5000)
    assert not dut.status().valve, "valve must not open while a person is present"
    dut.presence(False)
    dut.wait(10_000)
    assert [e.reason for e in dut.flushes()] == ["USER"]


# --------------------------------------------------------------- state transitions
@req("REQ-01")
@tech("ST")
def test_tc09_user_returns_during_delay(dut):
    dut.presence(True); dut.wait(4000)
    dut.presence(False); dut.wait(500)        # WAIT_FLUSH
    dut.presence(True); dut.wait(500)         # back -> OCCUPIED
    assert dut.status().state == "OCCUPIED"
    dut.presence(False); dut.wait(10_000)
    assert len(dut.flushes()) == 0            # 2nd stay only 0.5 s: passer-by rule


@req("REQ-03")
@tech("ST")
def test_tc10_presence_during_flush_is_ignored(dut):
    dut.presence(True); dut.wait(5000)
    dut.presence(False); dut.wait(2000)       # flushing now
    dut.presence(True); dut.wait(100)
    assert dut.status().valve
    dut.wait(3000)
    assert dut.status().state == "OCCUPIED"
    assert len(dut.flushes()) == 1


# --------------------------------------------------------------- REQ-06 sensor fault
@req("REQ-06")
@tech("BVA")
@fmea("FM-02")
def test_tc11_stuck_sensor_detected(dut):
    dut.presence(True)
    dut.wait(10 * MINUTE)
    assert dut.status().state == "OCCUPIED"
    dut.wait(10)
    s = dut.status()
    assert s.state == "FAULT" and s.err & 0x01


@req("REQ-06")
@req("REQ-04")
@tech("DT")
@fmea("FM-02")
def test_tc12_hygiene_flush_runs_even_with_faulty_sensor(dut):
    dut.presence(True)
    dut.wait(72 * HOUR + 10_000)
    assert len(dut.flushes("HYGIENE")) == 1
    assert dut.status().state == "FAULT"


@req("REQ-06")
@tech("ST")
def test_tc13_fault_recovery_without_flush(dut):
    dut.presence(True); dut.wait(11 * MINUTE)
    dut.presence(False); dut.wait(10_000)
    assert [e.name for e in dut.events] == ["FAULT_SET", "FAULT_CLEAR"]
    assert dut.status().state == "IDLE"


# --------------------------------------------------------------- REQ-07 battery
@req("REQ-07")
@tech("EP")
@tech("BVA")
@fmea("FM-04")
@pytest.mark.parametrize("mv, err, can_flush", [
    (6000, 0x00, True),    # partition: good
    (4400, 0x00, True),    # boundary warn
    (4399, 0x02, True),    # partition: low (warning only)
    (4000, 0x02, True),    # boundary cut-off
    (3999, 0x06, False),   # partition: empty -> valve disabled
])
def test_tc14_battery_partitions(dut, mv, err, can_flush):
    dut.battery(mv)
    dut.user_visit(5000)
    assert dut.status().err == err
    assert (len(dut.flushes()) == 1) is can_flush


@req("REQ-07")
@tech("EG")
@fmea("FM-04")
def test_tc15_brownout_during_flush_closes_valve(dut):
    dut.presence(True); dut.wait(5000)
    dut.presence(False); dut.wait(2000)
    assert dut.status().valve
    dut.battery(3500); dut.wait(10)
    assert not dut.status().valve
    assert any(e.name == "FLUSH_ABORT" for e in dut.events)


# --------------------------------------------------------------- REQ-08 telemetry
@req("REQ-08")
@tech("UC")
def test_tc16_counters_for_lifecycle_monitoring(dut):
    for _ in range(5):
        dut.user_visit(5000)
    dut.wait(72 * HOUR)
    s = dut.status()
    assert (s.flushes, s.hygiene) == (6, 1)


# --------------------------------------------------------------- REQ-09 timing
@req("REQ-09")
@tech("EG")
@fmea("FM-05")
def test_tc17_tick_counter_wraparound(dut):
    """49.7-day uint32 ms wrap: a classic embedded bug (error guessing)."""
    dut.set_time(2**32 - 1500)
    dut.user_visit(1000)                      # 1 s: must stay a passer-by
    assert dut.flushes() == []
    dut.user_visit(5000)
    assert len(dut.flushes("USER")) == 1


@req("REQ-08")
@tech("EG")
def test_tc18_unknown_command_is_rejected(dut):
    assert dut.cmd("FLUSH NOW").startswith("ERR")
    assert dut.status().state == "IDLE"


# --------------------------------------------------------------- proposed by GenAI, reviewed by a human
@req("REQ-05")
@tech("ST")
def test_tc19_hygiene_due_and_user_arrives_same_tick(dut):
    """From ml/genai_testgen.py, accepted after review: timer/presence race."""
    dut.wait(72 * HOUR - 10)
    dut.presence(True)
    dut.wait(10)                       # hygiene becomes due in the same tick
    s = dut.status()
    assert not s.valve and s.state == "OCCUPIED"


@req("REQ-07")
@tech("BVA")
@pytest.mark.parametrize("mv, cutoff_active", [(4099, True), (4100, False)])
def test_tc20_battery_hysteresis_upper_boundary(dut, mv, cutoff_active):
    """From ml/genai_testgen.py, accepted after review: hysteresis 4000+100 mV."""
    dut.battery(3990); dut.wait(10)
    dut.battery(mv); dut.wait(10)
    assert bool(dut.status().err & 0x04) is cutoff_active
