# check_close_calls.py
import pandas as pd
from core.logic import judge_all, DEFAULT_THRESHOLD_MIN
from core.liquidation.simple_af import SimpleAFModel

df = pd.read_parquet('data/derived/daily_aggregates.parquet')
model = SimpleAFModel()

results = judge_all(df, model, leverage=500, position_margin=100, additional_margin=0, threshold_min=1)

print("=" * 60)
print("💎 完全勝利のうち、建値に近いケース（冷や汗レベル）")
print("=" * 60)

close_calls = []

for r in results:
    if '💎' in r['symbol']:
        info = r['info']
        closest_distance = info['closest_distance']
        entry = info['entry']
        distance_pct = closest_distance / entry * 100
        
        # 0.2%以下を「冷や汗」と定義
        if distance_pct < 0.2:
            close_calls.append({
                'date': r['date'],
                'distance_usd': closest_distance,
                'distance_pct': distance_pct
            })
            print(f"{r['date']}: ${closest_distance:.2f} ({distance_pct:.3f}%)")

print(f"\n総💎数: {sum(1 for r in results if '💎' in r['symbol'])}")
print(f"冷や汗💎数: {len(close_calls)}")
print(f"割合: {len(close_calls) / sum(1 for r in results if '💎' in r['symbol']) * 100:.1f}%")
