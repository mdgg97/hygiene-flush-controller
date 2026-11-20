"""Synthetic fleet telemetry, as a gateway (S/GATE-like) would collect it.

One row = one device x one day. Some devices get a fault injected from a
random day on; the label column is the ground truth used to *evaluate* the
detector (the detector itself never sees it).

Fault types (also the FMEA failure modes in docs/FMEA.md):
  LEAK          valve does not seal -> water flows after closing   (FM-03b)
  SENSOR_DRIFT  dirty / misaligned IR window -> false triggers      (FM-01)
  BATT_DRAIN    abnormal current draw -> battery voltage falls fast (FM-04)
  LOW_PRESSURE  clogged strainer -> less water per flush            (FM-06)
"""
from __future__ import annotations

import argparse
import csv
import pathlib

import numpy as np

SITES = {"office": 25, "school": 40, "train": 90}   # mean uses per weekday
FAULTS = ["LEAK", "SENSOR_DRIFT", "BATT_DRAIN", "LOW_PRESSURE"]


def generate(n_devices: int = 60, days: int = 90, fault_share: float = 0.25, seed: int = 7):
    rng = np.random.default_rng(seed)
    rows = []
    for dev in range(n_devices):
        site = rng.choice(list(SITES))
        fault = rng.choice(FAULTS) if rng.random() < fault_share else None
        fault_day = int(rng.integers(days // 3, days - 10)) if fault else days + 1
        batt = rng.normal(6100, 60)
        drain = rng.normal(4.0, 0.8)                     # mV per day, healthy
        for day in range(days):
            weekend = day % 7 in (5, 6)
            mean_uses = SITES[site] * (0.25 if weekend and site != "train" else 1.0)
            uses = int(rng.poisson(mean_uses))
            false_ratio = float(np.clip(rng.normal(0.05, 0.015), 0, 1))
            presence_s = float(rng.normal(95, 12))
            liters = float(rng.normal(6.0, 0.15))        # 6 l full flush (EN 997 class)
            leak_l = float(abs(rng.normal(0, 0.03)))
            label = "OK"
            if day >= fault_day:
                age = day - fault_day + 1
                label = fault
                if fault == "LEAK":
                    leak_l += min(0.4 * age, 25) + rng.normal(0, 0.3)
                elif fault == "SENSOR_DRIFT":
                    false_ratio = float(np.clip(false_ratio + 0.03 * age, 0, 0.9))
                    presence_s += 4 * age
                elif fault == "BATT_DRAIN":
                    drain = 25.0
                elif fault == "LOW_PRESSURE":
                    liters -= min(0.12 * age, 2.5)
            batt -= drain * (1 + uses / 200) + rng.normal(0, 3)
            rows.append({
                "device": f"WC-{dev:03d}", "site": site, "day": day,
                "uses": uses,
                "hygiene_flushes": int(uses == 0 and rng.random() < 0.4),
                "false_trigger_ratio": round(false_ratio, 4),
                "avg_presence_s": round(presence_s, 1),
                "liters_per_flush": round(liters, 3),
                "post_close_flow_l": round(max(leak_l, 0.0), 3),
                "battery_mV": int(batt),
                "label": label,
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build/telemetry.csv")
    ap.add_argument("--devices", type=int, default=60)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rows = generate(a.devices, a.days, seed=a.seed)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    faulty = {r["device"]: r["label"] for r in rows if r["label"] != "OK"}
    print(f"wrote {len(rows)} rows, {a.devices} devices, {len(faulty)} with injected faults -> {out}")


if __name__ == "__main__":
    main()
