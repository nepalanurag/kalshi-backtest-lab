"""Lightweight orchestrator for the 15-min collection schedule.

Runs collect.py on a schedule with retries and failure alerting.
This is a stdlib-only scheduler (no Dagster dependency) with the same
semantics: fixed interval, exponential-backoff retries, alert after
3 consecutive failures.

Usage: python dag.py [--interval-min 15] [--once]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone

COLLECT = [sys.executable, "pipeline/collect.py",
           "--max-pages", "2", "--days", "1"]
MAX_RETRIES = 3
ALERT_AFTER = 3


def run_once() -> bool:
    for attempt in range(MAX_RETRIES):
        r = subprocess.run(COLLECT, capture_output=True, text=True,
                           timeout=600)
        if r.returncode == 0:
            return True
        time.sleep(2 ** attempt * 30)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval-min", type=int, default=15)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    fails = 0
    while True:
        ok = run_once()
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        if ok:
            print(f"[{ts}] collect ok")
            fails = 0
        else:
            fails += 1
            print(f"[{ts}] collect FAILED ({fails} in a row)")
            if fails >= ALERT_AFTER:
                print(f"[{ts}] ALERT: {fails} consecutive failures")
        if args.once:
            break
        time.sleep(args.interval_min * 60)


if __name__ == "__main__":
    main()
