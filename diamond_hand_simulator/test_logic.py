import pandas as pd
from core.logic import judge_all, calculate_statistics
from core.liquidation.simple_af import SimpleAFModel

df = pd.read_parquet('data/derived/daily_aggregates.parquet')
model = SimpleAFModel()

results = judge_all(df, model, leverage=500, margin=100, threshold_min=5)
stats = calculate_statistics(results)

print("=" * 60)
print("判定結果サンプル（最初の10件）")
print("=" * 60)
for r in results[:10]:
    print(f"{r['date']} | {r['symbol']} | {r['detail']}")

print("\n" + "=" * 60)
print("統計情報")
print("=" * 60)
print(f"総日数: {stats['total']}")
print(f"💎 完全勝利: {stats['win_count']} ({stats['win_rate']:.1f}%)")
print(f"⚠️ 建値割れ: {stats['warning_count']}")
print(f"❌ ロスカット: {stats['loss_count']}")
print(f"\n絵文字別カウント:")
for symbol, count in sorted(stats['symbol_counts'].items()):
    print(f"  {symbol}: {count}")
