#!/usr/bin/env python3
"""Run all tests. Usage: python run_tests.py"""
import sys
import traceback

sys.path.insert(0, ".")

suites = [
    ("backtest.tests.test_engine", "engine"),
    ("backtest.tests.test_ledger", "ledger"),
    ("pipeline.tests.test_pipeline", "pipeline"),
    ("stats.tests.test_stats", "stats"),
]

total_ok = total_n = 0
for mod_name, label in suites:
    mod = __import__(mod_name, fromlist=["*"])
    fns = [f for f in dir(mod) if f.startswith("test_")]
    ok = 0
    for f in fns:
        try:
            getattr(mod, f)()
            ok += 1
        except Exception as e:
            print(f"FAIL [{label}] {f}: {e}")
            traceback.print_exc(limit=3)
    print(f"[{label}] {ok}/{len(fns)} passed")
    total_ok += ok
    total_n += len(fns)

print(f"\nTOTAL: {total_ok}/{total_n} passed")
sys.exit(0 if total_ok == total_n else 1)
