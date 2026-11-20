"""Predictive maintenance for a sanitary sensor fleet.

Two layers, as is common in industrial ML:
 1. Unsupervised anomaly detection (Isolation Forest) on per-device features
    normalised against the device's own first 14 days (its "baseline"),
    combined with a z-score limit (IF alone misses values far outside the
    training range - found while testing this script, see README).
 2. Explainable rules + a battery trend forecast (linear regression):
    "battery reaches cut-off 4000 mV in N days" -> plan the service visit.

The ground-truth label from the generator is used ONLY to measure the
detector (precision / recall / detection delay), like a test oracle.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict

import numpy as np
from sklearn.ensemble import IsolationForest

FEATURES = ["false_trigger_ratio", "avg_presence_s", "liters_per_flush", "post_close_flow_l"]
BASELINE_DAYS = 14
CUTOFF_MV = 4000


def load(path):
    by_dev = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            by_dev[r["device"]].append(r)
    return by_dev


def featurise(rows):
    """Rolling 3-day mean, z-scored against the device's own baseline."""
    x = np.array([[float(r[k]) for k in FEATURES] for r in rows])
    kernel = np.ones(3) / 3
    smooth = np.vstack([np.convolve(x[:, i], kernel, mode="full")[: len(x)] for i in range(x.shape[1])]).T
    smooth[:2] = x[:2]
    base = x[:BASELINE_DAYS]
    mu, sd = base.mean(0), base.std(0) + 1e-3
    z = (smooth - mu) / sd
    batt = np.array([float(r["battery_mV"]) for r in rows])
    slope = np.array([np.polyfit(np.arange(min(i + 1, 7)), batt[max(0, i - 6): i + 1], 1)[0] if i >= 2 else 0.0
                      for i in range(len(batt))])
    zs = (slope - slope[2:BASELINE_DAYS].mean()) / (slope[2:BASELINE_DAYS].std() + 1.0)
    return np.column_stack([z, zs]), batt, slope


def explain(zrow, slope):
    reasons = []
    if zrow[3] > 6:  reasons.append("water flows after valve closed -> LEAK suspected")
    if zrow[0] > 6:  reasons.append("many short presences -> sensor window dirty / drift")
    if zrow[2] < -6: reasons.append("less water per flush -> low pressure / clogged strainer")
    if slope < -15:  reasons.append(f"battery falls {abs(slope):.0f} mV/day -> abnormal drain")
    return reasons or ["unusual combination of features"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--contamination", type=float, default=0.02)
    ap.add_argument("--z-limit", type=float, default=6.0)
    a = ap.parse_args()

    by_dev = load(a.csv)
    feats, meta = [], []
    for dev, rows in by_dev.items():
        f, batt, slope = featurise(rows)
        for i, r in enumerate(rows):
            feats.append(f[i]); meta.append((dev, int(r["day"]), r["label"], batt[i], slope[i]))
    X = np.array(feats)
    train = np.array([m[1] < BASELINE_DAYS for m in meta])   # fit on baseline period only
    model = IsolationForest(n_estimators=300, contamination=a.contamination, random_state=0)
    model.fit(X[train])
    # Hybrid: Isolation Forest catches unusual *combinations*, but it cannot
    # score values far outside the training range well (its splits only cover
    # the baseline range) - a known weakness. A robust z-score limit catches those.
    iso_flag = model.predict(X) == -1
    z_flag = np.abs(X).max(axis=1) > a.z_limit
    flag = iso_flag | z_flag

    # device-level alarm: 3 flagged days in a row (debounce, avoids alarm fatigue).
    # Every new run of 3 is one alarm "episode".
    episodes, truth_start, truth_label = defaultdict(list), {}, {}
    run = defaultdict(int)
    for (dev, day, label, batt, slope), fl, x in zip(meta, flag, X):
        if label != "OK" and dev not in truth_start:
            truth_start[dev], truth_label[dev] = day, label
        run[dev] = run[dev] + 1 if (fl and day >= BASELINE_DAYS) else 0
        if run[dev] == 3:
            episodes[dev].append((day, explain(x, slope)))

    detected, false_eps, n_eps = {}, 0, 0
    for dev, eps in episodes.items():
        for day, why in eps:
            n_eps += 1
            if dev in truth_start and day >= truth_start[dev]:
                detected.setdefault(dev, (day, why))
            else:
                false_eps += 1
    missed = [d for d in truth_start if d not in detected]
    delays = [detected[d][0] - truth_start[d] for d in detected]
    prec = (n_eps - false_eps) / max(n_eps, 1)
    rec = len(detected) / max(len(truth_start), 1)

    print("== Predictive maintenance report ==")
    print(f"devices: {len(by_dev)}, with injected fault: {len(truth_start)}, alarm episodes: {n_eps}")
    print(f"precision {prec:.2f}  recall {rec:.2f}  false alarms {false_eps}  "
          f"median detection delay {np.median(delays) if delays else float('nan'):.0f} days")
    print("\nDetected faults:")
    for d in sorted(detected):
        day, why = detected[d]
        print(f"  {d} fault={truth_label[d]:<13} start day {truth_start[d]:3d}, alarm day {day:3d} -> {'; '.join(why)}")
    if missed:
        print("\nMissed:", ", ".join(f"{d}({truth_label[d]})" for d in missed))

    print("\nBattery forecast (service planning, cut-off 4000 mV):")
    for dev, rows in sorted(by_dev.items()):
        b = np.array([float(r["battery_mV"]) for r in rows[-14:]])
        k = np.polyfit(np.arange(len(b)), b, 1)[0]
        if k < 0:
            days_left = (b[-1] - CUTOFF_MV) / -k
            if days_left < 120:
                print(f"  {dev}: {b[-1]:.0f} mV, {k:.1f} mV/day -> cut-off in ~{days_left:.0f} days")


if __name__ == "__main__":
    main()
