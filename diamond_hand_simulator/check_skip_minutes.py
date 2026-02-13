import pandas as pd
from pathlib import Path

candidates = list(Path("data").rglob("*.parquet"))
print("parquet files:", len(candidates))
for p in candidates[:20]:
    print(" -", p)

target = None
for p in candidates:
    if "daily_aggregates" in p.name:
        target = p
        break

if target is None:
    print("No daily_aggregates parquet found.")
    raise SystemExit(1)

print("\nUsing:", target)
df = pd.read_parquet(target)

cols = [c for c in df.columns if ("skip" in c or "reference" in c or "open" in c)]
print("columns:", cols[:50])

if "skip_minutes" not in df.columns:
    print("skip_minutes column NOT found -> 再集計未反映 or 実装未接続")
else:
    s = df["skip_minutes"].fillna(0).astype(int)
    print("rows:", len(df))
    print("skip_minutes>0:", int((s>0).sum()))
    if (s>0).any():
        show_cols = ["date","skip_minutes"]
        for c in ["detail","詳細","symbol"]:
            if c in df.columns:
                show_cols.append(c)
        print(df.loc[s>0, show_cols].head(20))

