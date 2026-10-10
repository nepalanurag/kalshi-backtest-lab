"""Consolidate per-market trades into daily Parquet files, streaming with incremental writers."""
import glob
import os
import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd

RAW = "data/raw"
OUT = "data/bq_staging"
os.makedirs(OUT, exist_ok=True)

files = sorted(glob.glob(f"{RAW}/trades_*.parquet"))
print(f"Consolidating {len(files)} trade files...", flush=True)

BATCH = 100
writers = {}  # date -> ParquetWriter
schema = None
n_rows = 0

for i in range(0, len(files), BATCH):
    chunk = files[i:i+BATCH]
    tables = [pq.read_table(f) for f in chunk]
    combined = pa.concat_tables(tables)
    del tables
    df = combined.to_pandas()
    del combined
    df["td"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.date.astype(str)
    for date, group in df.groupby("td"):
        tbl = pa.Table.from_pandas(group.drop(columns=["td"]), preserve_index=False)
        if date not in writers:
            writers[date] = pq.ParquetWriter(f"{OUT}/trades_{date}.parquet", tbl.schema)
        writers[date].write_table(tbl)
        del tbl
    n_rows += len(df)
    del df
    print(f"  {min(i+BATCH, len(files))}/{len(files)}, {n_rows} rows", flush=True)

for w in writers.values():
    w.close()
print(f"Done. {n_rows} total rows, {len(writers)} daily files.", flush=True)

for src, dst in [
    (f"{RAW}/markets_20261009.parquet", f"{OUT}/markets.parquet"),
    (f"{RAW}/spot_btc_hourly.parquet", f"{OUT}/spot_btc_hourly.parquet"),
    (f"{RAW}/spot_btc_minute.parquet", f"{OUT}/spot_btc_minute.parquet"),
]:
    if os.path.exists(src):
        pq.write_table(pq.read_table(src), dst)
        print(f"{dst} written", flush=True)
