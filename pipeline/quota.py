"""Application-level cost guardrails for BigQuery.

GCP trial accounts cannot set custom BigQuery quotas via console,
so we enforce limits in code. Every BigQuery operation in this
project must go through QuotaGuard.

Limits (conservative, well within the 1TB/month free tier):
- Max 100 GB scanned per day
- Max 10 GB per single query (dry-run estimate)
- Hard stop: refuse to run if either limit would be exceeded

Usage:
    from pipeline.quota import QuotaGuard
    qg = QuotaGuard(project=os.environ["GCP_PROJECT"])
    qg.check_query("SELECT ...")  # raises QuotaExceeded if over limit
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

DAILY_LIMIT_BYTES = 100 * 1024**3      # 100 GB/day
PER_QUERY_LIMIT_BYTES = 10 * 1024**3   # 10 GB per query
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "data", "quota_state.json")


class QuotaExceeded(RuntimeError):
    pass


class QuotaGuard:
    def __init__(self, project: str, credentials_path: str = ""):
        self.project = project
        self.credentials_path = credentials_path
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if self.credentials_path:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path
            from google.cloud import bigquery
            self._client = bigquery.Client(project=self.project)
        return self._client

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_state(self) -> dict:
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self, state: dict) -> None:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)

    def bytes_used_today(self) -> int:
        state = self._load_state()
        return state.get(self._today(), 0)

    def _record(self, n_bytes: int) -> None:
        state = self._load_state()
        today = self._today()
        state[today] = state.get(today, 0) + n_bytes
        # prune old days
        for k in [k for k in state if k < today]:
            del state[k]
        self._save_state(state)

    def estimate_query_bytes(self, sql: str) -> int:
        """Dry-run to estimate bytes scanned without executing."""
        from google.cloud import bigquery
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = self.client.query(sql, job_config=job_config)
        return job.total_bytes_processed or 0

    def check_query(self, sql: str) -> int:
        """Estimate + enforce. Returns estimated bytes. Raises QuotaExceeded."""
        est = self.estimate_query_bytes(sql)
        if est > PER_QUERY_LIMIT_BYTES:
            raise QuotaExceeded(
                f"Query would scan {est/1024**3:.1f} GB, "
                f"over per-query limit of {PER_QUERY_LIMIT_BYTES/1024**3:.0f} GB. "
                f"Refusing to run."
            )
        used = self.bytes_used_today()
        if used + est > DAILY_LIMIT_BYTES:
            raise QuotaExceeded(
                f"Daily quota exceeded: used {used/1024**3:.1f} GB today, "
                f"this query needs {est/1024**3:.1f} GB, "
                f"limit is {DAILY_LIMIT_BYTES/1024**3:.0f} GB/day. Refusing to run."
            )
        return est

    def run_query(self, sql: str):
        """Check quota, run, record usage."""
        est = self.check_query(sql)
        job = self.client.query(sql)
        result = job.result()
        # record actual, fall back to estimate
        actual = job.total_bytes_processed or est
        self._record(actual)
        return result

    def status(self) -> dict:
        used = self.bytes_used_today()
        return {
            "date": self._today(),
            "used_gb": round(used / 1024**3, 3),
            "limit_gb": DAILY_LIMIT_BYTES / 1024**3,
            "remaining_gb": round((DAILY_LIMIT_BYTES - used) / 1024**3, 3),
        }
