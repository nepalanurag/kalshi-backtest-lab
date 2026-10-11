"""Tiered storage: archive old BigQuery partitions to Drive as Parquet.

Architecture (agreed 2026-10-10):
- Recent data: BigQuery native tables (fast queries)
- Older data: Drive as Parquet, queried via BigQuery external tables
- Trigger: when BigQuery storage exceeds 10GB (free tier limit)

Usage:
    python -m pipeline.archive --check          # show current BQ storage vs 10GB
    python -m pipeline.archive --archive 2026-08  # archive August 2026 to Drive

The archive flow:
1. Export the month's data from BigQuery to local Parquet (via QuotaGuard)
2. Upload Parquet files to Google Drive (manual step via browser - see README)
3. Create BigQuery external table pointing to Drive Parquet
4. Delete the archived month from BigQuery native tables (frees storage)

All BigQuery operations go through QuotaGuard (10GB/query, 100GB/day limits).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.quota import QuotaGuard, QuotaExceeded

PROJECT = os.environ.get("GCP_PROJECT", "")
DATASET = "kalshi"
STORAGE_LIMIT_BYTES = 10 * 1024**3  # 10GB BigQuery free tier

# Tables and their date columns for month-based archiving
ARCHIVABLE_TABLES = {
    "trades": "trade_ts",      # timestamp column
    "spot_minute": "minute",   # timestamp column
    "spot_hourly": "hour",     # timestamp column
}


def get_table_sizes(qg: QuotaGuard) -> dict:
    """Get storage size for each table in the kalshi dataset."""
    sql = f"""
    SELECT table_id, total_bytes
    FROM `{qg.project}.{DATASET}.INFORMATION_SCHEMA.TABLE_STORAGE`
    WHERE table_type = 'BASE TABLE'
    """
    result = qg.run_query(sql)
    return {row.table_id: row.total_bytes for row in result}


def check_storage(qg: QuotaGuard) -> dict:
    """Check current storage vs 10GB limit."""
    sizes = get_table_sizes(qg)
    total = sum(sizes.values())
    return {
        "tables": {k: round(v / 1024**3, 3) for k, v in sizes.items()},
        "total_gb": round(total / 1024**3, 3),
        "limit_gb": STORAGE_LIMIT_BYTES / 1024**3,
        "needs_archive": total > STORAGE_LIMIT_BYTES,
    }


def export_month_to_parquet(qg: QuotaGuard, table: str, year_month: str, out_dir: str) -> str:
    """Export one month of a table to local Parquet via BigQuery.

    Returns the path to the exported Parquet file.
    """
    date_col = ARCHIVABLE_TABLES[table]
    sql = f"""
    SELECT *
    FROM `{qg.project}.{DATASET}.{table}`
    WHERE FORMAT_TIMESTAMP('%Y-%m', {date_col}, 'UTC') = '{year_month}'
    """
    # QuotaGuard dry-runs first, refuses if over 10GB
    result = qg.run_query(sql)

    import pandas as pd
    df = result.to_dataframe()

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{table}_{year_month}.parquet")
    df.to_parquet(out_path, index=False, compression="snappy")

    print(f"Exported {len(df)} rows to {out_path} ({os.path.getsize(out_path)/1024**2:.1f} MB)")
    return out_path


def create_external_table(qg: QuotaGuard, table: str, year_month: str, drive_file_id: str):
    """Create a BigQuery external table pointing to Parquet on Drive.

    Args:
        table: Base table name (e.g., 'trades')
        year_month: 'YYYY-MM' string
        drive_file_id: Google Drive file ID of the uploaded Parquet file
    """
    from google.cloud import bigquery

    ext_table_id = f"{qg.project}.{DATASET}.{table}_archive_{year_month.replace('-', '_')}"
    drive_uri = f"https://drive.google.com/file/d/{drive_file_id}/view"

    external_config = bigquery.ExternalConfig("PARQUET")
    external_config.source_uris = [drive_uri]
    external_config.autodetect = True

    table_obj = bigquery.Table(ext_table_id)
    table_obj.external_data_configuration = external_config

    client = qg.client
    # Delete if exists (idempotent)
    try:
        client.delete_table(ext_table_id, not_found_ok=True)
    except Exception:
        pass

    client.create_table(table_obj)
    print(f"Created external table: {ext_table_id}")
    print(f"  Source: Drive file {drive_file_id}")
    return ext_table_id


def delete_archived_month(qg: QuotaGuard, table: str, year_month: str, dry_run: bool = True):
    """Delete an archived month from the native BigQuery table.

    WARNING: Only call after verifying the external table works!
    """
    date_col = ARCHIVABLE_TABLES[table]
    sql = f"""
    DELETE FROM `{qg.project}.{DATASET}.{table}`
    WHERE FORMAT_TIMESTAMP('%Y-%m', {date_col}, 'UTC') = '{year_month}'
    """
    if dry_run:
        est = qg.estimate_query_bytes(f"SELECT * FROM `{qg.project}.{DATASET}.{table}` WHERE FORMAT_TIMESTAMP('%Y-%m', {date_col}, 'UTC') = '{year_month}'")
        print(f"DRY RUN: Would delete month {year_month} from {table} (~{est/1024**3:.2f} GB scanned)")
        return

    print(f"WARNING: Deleting {year_month} from {table}. This cannot be undone.")
    print("Verify the external table works first!")
    confirm = input("Type 'DELETE' to confirm: ")
    if confirm != "DELETE":
        print("Aborted.")
        return

    qg.run_query(sql)
    print(f"Deleted {year_month} from {table}")


def main():
    parser = argparse.ArgumentParser(description="Tiered storage: archive old BQ data to Drive")
    parser.add_argument("--check", action="store_true", help="Show storage vs 10GB limit")
    parser.add_argument("--archive", metavar="YYYY-MM", help="Archive a month (export to Parquet)")
    parser.add_argument("--out-dir", default="./archive_staging", help="Local dir for Parquet exports")
    parser.add_argument("--external", nargs=3, metavar=("TABLE", "YYYY-MM", "DRIVE_FILE_ID"),
                        help="Create BQ external table for a Drive Parquet file")
    parser.add_argument("--delete", nargs=2, metavar=("TABLE", "YYYY-MM"),
                        help="Delete archived month from BQ (after verifying external table)")
    args = parser.parse_args()

    if not PROJECT:
        print("Error: GCP_PROJECT env var not set", file=sys.stderr)
        sys.exit(1)

    qg = QuotaGuard(project=PROJECT)

    if args.check:
        status = check_storage(qg)
        print(f"\nBigQuery storage: {status['total_gb']} GB / {status['limit_gb']} GB")
        for table, gb in status["tables"].items():
            print(f"  {table}: {gb} GB")
        if status["needs_archive"]:
            print("\n⚠ Over 10GB limit - archiving recommended")
        else:
            print(f"\n✓ Under limit ({status['limit_gb'] - status['total_gb']:.1f} GB remaining)")
        return

    if args.archive:
        year_month = args.archive
        print(f"\nArchiving {year_month}...")
        print("Step 1: Exporting to Parquet (via QuotaGuard)...")
        for table in ARCHIVABLE_TABLES:
            try:
                path = export_month_to_parquet(qg, table, year_month, args.out_dir)
                print(f"  ✓ {table} -> {path}")
            except QuotaExceeded as e:
                print(f"  ✗ {table}: {e}")
            except Exception as e:
                print(f"  ✗ {table}: {e}")

        print(f"\nStep 2: Upload the Parquet files in {args.out_dir}/ to Google Drive")
        print("  (Use the browser - Drive CLI cannot access workspace files)")
        print("  Then run with --external to create BigQuery external tables")
        return

    if args.external:
        table, year_month, drive_id = args.external
        create_external_table(qg, table, year_month, drive_id)
        print(f"\nVerify with: SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.{table}_archive_{year_month.replace('-', '_')}`")
        print("If the count matches, run with --delete to free BQ storage")
        return

    if args.delete:
        table, year_month = args.delete
        delete_archived_month(qg, table, year_month, dry_run=False)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
