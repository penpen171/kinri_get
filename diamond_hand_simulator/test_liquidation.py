
import sys
sys.path.insert(0, '.')

from core.liquidation.simple_af import SimpleAFModel

model = SimpleAFModel()

print("=" * 60)
print("ロスカットモデルのテスト")
print("=" * 60)
print(f"モデル情報: {model.get_info()}")

# テストケース: レバレッジ500倍、建値5000ドル
entry_price = 5000.0
leverage = 500

print(f"\n建値: ${entry_price:,.2f}")
print(f"レバレッジ: {leverage}x")
print(f"Adjustment Factor: {model.adjustment_factor * 100}%")

liq_long = model.calc_liq_price_long(entry_price, leverage)
liq_short = model.calc_liq_price_short(entry_price, leverage)
distance_pct = model.calc_liq_distance_pct(leverage)

print(f"\n【ロングの場合】")
print(f"  ロスカット価格: ${liq_long:,.2f}")
print(f"  ロスカット幅: ${entry_price - liq_long:,.2f} ({distance_pct * 100:.3f}%)")

print(f"\n【ショートの場合】")
print(f"  ロスカット価格: ${liq_short:,.2f}")
print(f"  ロスカット幅: ${liq_short - entry_price:,.2f} ({distance_pct * 100:.3f}%)")

# 判定テスト
test_price_safe = 4992.0
test_price_liq = 4990.0

print(f"\n\n【判定テスト】")
print(f"テスト価格1: ${test_price_safe:,.2f}")
print(f"  ロングがロスカット? {model.is_liquidated_long(entry_price, test_price_safe, leverage)}")

print(f"\nテスト価格2: ${test_price_liq:,.2f}")
print(f"  ロングがロスカット? {model.is_liquidated_long(entry_price, test_price_liq, leverage)}")

print("\n✅ テスト完了")
