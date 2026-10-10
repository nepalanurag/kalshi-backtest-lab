"""Append-only warehouse: parquet batches, hashed, idempotent.

Layout:
  data/raw/markets_YYYYMMDD.parquet
  data/raw/trades_<TICKER>.parquet
  data/raw/spot_btc_hourly.parquet
  data/raw/_manifest.json   # batch hashes -> skip reruns

Idempotency: a batch is keyed by sha256 of its canonical JSON. If the key
is already in the manifest, the load is skipped.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Dict, List

RAW = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw")


def _manifest_path() -> str:
    return os.path.join(RAW, "_manifest.json")


def load_manifest() -> Dict:
    p = _manifest_path()
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"batches": {}}


def save_manifest(m: Dict) -> None:
    os.makedirs(RAW, exist_ok=True)
    with open(_manifest_path(), "w") as f:
        json.dump(m, f, indent=1)


def batch_key(rows: List[Dict]) -> str:
    canon = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def already_loaded(key: str) -> bool:
    return key in load_manifest().get("batches", {})


def record_batch(key: str, kind: str, n_rows: int, note: str = "") -> None:
    m = load_manifest()
    m["batches"][key] = {
        "kind": kind, "n_rows": n_rows, "note": note,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }
    save_manifest(m)


def write_parquet(rows: List[Dict], filename: str) -> str:
    """Write rows to data/raw/<filename>. Returns absolute path."""
    import pandas as pd
    os.makedirs(RAW, exist_ok=True)
    path = os.path.join(RAW, filename)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path
