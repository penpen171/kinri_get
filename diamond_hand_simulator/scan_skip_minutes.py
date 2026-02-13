import pandas as pd
from pathlib import Path
import time

base = Path("data/derived")
files = sorted(base.glob("daily_aggregates*.parquet"),
               key=lambda p: p.stat().st_mtime, reverse=True)

print("found:", len(files))
print("---- newest 10 ----")
for p in files[:10]:
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)), p)

print("\n---- files that have skip_minutes ----")
hit = 0
for p in files:
    df = pd.read_parquet(p)
    if "skip_minutes" in df.columns:
        hit += 1
        s = df["skip_minutes"].fillna(0).astype(int)
        print(f"{p}  rows={len(df)}  skip>0={(s>0).sum()}")
print("\nHIT:", hit)
