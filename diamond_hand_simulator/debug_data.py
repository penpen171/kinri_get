# debug_data.py
import pandas as pd

df = pd.read_parquet('data/derived/daily_aggregates.parquet')

print("=" * 60)
print("データの確認")
print("=" * 60)
print(f"総行数: {len(df)}")
print(f"\njudgment_hours のユニーク値:")
print(df['judgment_hours'].value_counts())
print(f"\njudgment_label のユニーク値:")
print(df['judgment_label'].value_counts())
print(f"\nthreshold_min のユニーク値:")
print(df['threshold_min'].value_counts())

print(f"\n最初の5行:")
print(df.head())
