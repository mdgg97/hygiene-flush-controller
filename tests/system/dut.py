"""Driver for the device under test (DUT).

Today it starts the simulator binary and talks to it over stdin/stdout.
On a real board the same class would open a serial port (pyserial) and send
the same commands: the test cases above it do not change. That is the idea of
a hardware abstraction in the test system (SIL today, HIL tomorrow).
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

HOUR = 3600 * 1000
MINUTE = 60 * 1000

_STAT = re.compile(
    r"STAT state=(\w+) valve=(\d) flushes=(\d+) hygiene=(\d+) err=0x([0-9A-F]+) t=(\d+)"
)
_EVT = re.compile(r"EVT t=(\d+) (\w+)(?: reason=(\w+))?")


@dataclass
class Status:
    state: str
    valve: bool
    flushes: int
    hygiene: int
    err: int
    t: int


@dataclass
class Event:
    t: int
    name: str
    reason: str | None


class Dut:
    def __init__(self, binary: str | None = None) -> None:
        binary = binary or os.environ.get("HFC_SIM", "build/hfc_sim")
        self.p = subprocess.Popen(
            [binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1
        )
        assert self._readline().startswith("READY")
        self.events: list[Event] = []

    # --- low level -------------------------------------------------------
    def _readline(self) -> str:
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError("DUT closed the connection")
        return line.strip()

    def cmd(self, text: str) -> str:
        self.p.stdin.write(text + "\n")
        self.p.stdin.flush()
        while True:
            line = self._readline()
            m = _EVT.match(line)
            if m:
                self.events.append(Event(int(m[1]), m[2], m[3]))
                continue
            return line

    def close(self) -> None:
        try:
            self.p.stdin.write("QUIT\n")
            self.p.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass
        self.p.wait(timeout=5)

    # --- test vocabulary ------------------------------------------------
    def presence(self, on: bool) -> None:
        assert self.cmd(f"PRES {int(on)}") == "OK"

    def battery(self, mv: int) -> None:
        assert self.cmd(f"BATT {mv}") == "OK"

    def wait(self, ms: int) -> None:
        assert self.cmd(f"ADV {ms}") == "OK"

    def set_time(self, ms: int) -> None:
        assert self.cmd(f"TIME {ms}") == "OK"

    def config(self, key: str, value: int) -> bool:
        return self.cmd(f"CFG {key} {value}") == "OK"

    def status(self) -> Status:
        m = _STAT.match(self.cmd("STAT"))
        assert m, "bad STAT line"
        return Status(m[1], m[2] == "1", int(m[3]), int(m[4]), int(m[5], 16), int(m[6]))

    def user_visit(self, stay_ms: int, after_ms: int = 10_000) -> None:
        self.presence(True)
        self.wait(stay_ms)
        self.presence(False)
        self.wait(after_ms)

    def flushes(self, reason: str | None = None) -> list[Event]:
        return [e for e in self.events
                if e.name == "FLUSH_START" and (reason is None or e.reason == reason)]
