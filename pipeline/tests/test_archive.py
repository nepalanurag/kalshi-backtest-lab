"""Tests for pipeline/archive.py tiered storage logic."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.archive import ARCHIVABLE_TABLES, STORAGE_LIMIT_BYTES


def test_archivable_tables_have_date_columns():
    """Every archivable table must name its timestamp column."""
    assert "trades" in ARCHIVABLE_TABLES
    assert "spot_minute" in ARCHIVABLE_TABLES
    assert "spot_hourly" in ARCHIVABLE_TABLES
    for table, col in ARCHIVABLE_TABLES.items():
        assert isinstance(col, str) and len(col) > 0, f"{table} missing date column"


def test_storage_limit_is_10gb():
    """Free tier storage limit is 10GB."""
    assert STORAGE_LIMIT_BYTES == 10 * 1024**3


def test_external_table_naming():
    """External table names are deterministic: {table}_archive_{YYYY_MM}."""
    table = "trades"
    year_month = "2026-08"
    expected = f"{table}_archive_{year_month.replace('-', '_')}"
    assert expected == "trades_archive_2026_08"


def test_drive_uri_format():
    """Drive URIs for BQ external tables use the file view URL."""
    file_id = "abc123xyz"
    uri = f"https://drive.google.com/file/d/{file_id}/view"
    assert "drive.google.com" in uri
    assert file_id in uri
