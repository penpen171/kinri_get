import hashlib
import hmac
import time
import requests
from datetime import datetime
from config import API_KEY, SECRET_KEY, BASE_URL

# ============================================
# 監視設定
# ============================================

SYMBOL = "XAUT-USDT"  # 監視する通貨ペア
CHECK_INTERVAL = 5  # ポジションチェック間隔（秒）

# 損切り設定モード
STOP_LOSS_MODE = "PERCENTAGE"  # "NONE", "FIXED_OFFSET", "PERCENTAGE", "LOSS_AMOUNT"

# 固定幅モード
STOP_LOSS_OFFSET_LONG = -1.0
STOP_LOSS_OFFSET_SHORT = 1.0

# パーセントモード
STOP_LOSS_PERCENTAGE_LONG = -10.0
STOP_LOSS_PERCENTAGE_SHORT = 10.0

# 損失額モード
MAX_LOSS_AMOUNT_LONG = 5.0
MAX_LOSS_AMOUNT_SHORT = 5.0

# レバレッジ（損失額計算用）
LEVERAGE = 50

# 価格設定
PRICE_TYPE = "MARK_PRICE"
PRICE_DECIMALS = 1

# ============================================
# 関数定義
# ============================================

def generate_signature(query_string, secret_key):
    """署名を生成"""
    signature = hmac.new(
        secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def get_positions():
    """現在のポジションを取得"""
    timestamp = str(int(time.time() * 1000))
    
    params = {
        "symbol": SYMBOL,
        "timestamp": timestamp
    }
    
    query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
    signature = generate_signature(query_string, SECRET_KEY)
    
    headers = {"X-BX-APIKEY": API_KEY}
    url = f"{BASE_URL}/openApi/swap/v2/user/positions?{query_string}&signature={signature}"
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if data['code'] == 0:
            return data['data']
        else:
            print(f"ポジション取得エラー: {data}")
            return []
    except Exception as e:
        print(f"エラー: {e}")
        return []

def get_open_orders():
    """未約定の注文を取得"""
    timestamp = str(int(time.time() * 1000))
    
    params = {
        "symbol": SYMBOL,
        "timestamp": timestamp
    }
    
    query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
    signature = generate_signature(query_string, SECRET_KEY)
    
    headers = {"X-BX-APIKEY": API_KEY}
    url = f"{BASE_URL}/openApi/swap/v2/trade/openOrders?{query_string}&signature={signature}"
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if data['code'] == 0:
            return data['data']['orders']
        else:
            return []
    except Exception as e:
        print(f"注文取得エラー: {e}")
        return []

def has_stop_loss_order(position_side):
    """指定されたポジション方向に損切り注文があるか確認"""
    open_orders = get_open_orders()
    
    for order in open_orders:
        # STOP_MARKET注文で、該当ポジション方向か確認
        if order.get('type') == 'STOP_MARKET' and order.get('positionSide') == position_side:
            return True
    
    return False

def calculate_stop_loss_price(entry_price, position_side, quantity):
    """損切り価格を計算"""
    
    if STOP_LOSS_MODE == "NONE":
        return None
    
    elif STOP_LOSS_MODE == "FIXED_OFFSET":
        if position_side == "LONG":
            sl_price = entry_price + STOP_LOSS_OFFSET_LONG
        else:  # SHORT
            sl_price = entry_price + STOP_LOSS_OFFSET_SHORT
    
    elif STOP_LOSS_MODE == "PERCENTAGE":
        if position_side == "LONG":
            sl_price = entry_price * (1 + STOP_LOSS_PERCENTAGE_LONG / 100)
        else:  # SHORT
            sl_price = entry_price * (1 + STOP_LOSS_PERCENTAGE_SHORT / 100)
    
    elif STOP_LOSS_MODE == "LOSS_AMOUNT":
        if position_side == "LONG":
            price_move = MAX_LOSS_AMOUNT_LONG / (quantity * LEVERAGE)
            sl_price = entry_price - price_move
        else:  # SHORT
            price_move = MAX_LOSS_AMOUNT_SHORT / (quantity * LEVERAGE)
            sl_price = entry_price + price_move
    
    else:
        raise ValueError(f"無効な損切りモード: {STOP_LOSS_MODE}")
    
    return round(sl_price, PRICE_DECIMALS)

def place_stop_loss_order(position):
    """損切り注文を発注"""
    position_side = position['positionSide']
    quantity = abs(float(position['positionAmt']))
    entry_price = float(position['avgPrice'])
    
    if quantity <= 0:
        return None
    
    # 損切り価格を計算
    sl_price = calculate_stop_loss_price(entry_price, position_side, quantity)
    
    if sl_price is None:
        return None
    
    # 損切り注文の方向を決定
    if position_side == "LONG":
        side = "SELL"  # ロングの損切りは売り
    else:  # SHORT
        side = "BUY"  # ショートの損切りは買い
    
    timestamp = str(int(time.time() * 1000))
    
    params = {
        "symbol": SYMBOL,
        "side": side,
        "positionSide": position_side,
        "type": "STOP_MARKET",
        "quantity": str(quantity),
        "stopPrice": str(sl_price),
        "workingType": PRICE_TYPE,
        "timestamp": timestamp
    }
    
    query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
    signature = generate_signature(query_string, SECRET_KEY)
    
    headers = {"X-BX-APIKEY": API_KEY}
    url = f"{BASE_URL}/openApi/swap/v2/trade/order?{query_string}&signature={signature}"
    
    try:
        response = requests.post(url, headers=headers)
        data = response.json()
        
        if data['code'] == 0:
            print(f"✅ {position_side} 損切り注文成功")
            print(f"   数量: {quantity}")
            print(f"   損切り価格: {sl_price}")
            print(f"   注文ID: {data['data']['order']['orderId']}")
            return data
        else:
            print(f"❌ {position_side} 損切り注文失敗: {data}")
            return None
    except Exception as e:
        print(f"❌ エラー: {e}")
        return None

def monitor_positions():
    """ポジションを監視して損切りを自動設定"""
    print("=" * 60)
    print("BingX ポジション監視 & 自動損切り設定")
    print("=" * 60)
    print(f"通貨ペア: {SYMBOL}")
    print(f"損切りモード: {STOP_LOSS_MODE}")
    print(f"チェック間隔: {CHECK_INTERVAL}秒")
    print(f"停止する場合は Ctrl+C を押してください")
    print("=" * 60)
    
    processed_positions = set()  # 処理済みポジションを記録
    
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ポジションチェック中...")
            
            positions = get_positions()
            
            if not positions:
                print("  ポジションなし")
            else:
                for position in positions:
                    position_side = position['positionSide']
                    position_amt = float(position['positionAmt'])
                    
                    # ポジションがある場合のみ処理
                    if position_amt != 0:
                        position_key = f"{SYMBOL}_{position_side}"
                        
                        print(f"\n  {position_side} ポジション検出")
                        print(f"    数量: {position_amt}")
                        print(f"    平均価格: {position['avgPrice']}")
                        print(f"    未実現損益: {position['unrealizedProfit']}")
                        
                        # 損切り注文がすでにあるか確認
                        if has_stop_loss_order(position_side):
                            print(f"    ✓ 損切り注文設定済み")
                        elif position_key in processed_positions:
                            print(f"    ✓ 損切り注文処理済み")
                        else:
                            print(f"    ⚠ 損切り注文なし - 設定中...")
                            result = place_stop_loss_order(position)
                            if result:
                                processed_positions.add(position_key)
                    else:
                        # ポジションがクローズされた場合、処理済みリストから削除
                        position_key = f"{SYMBOL}_{position_side}"
                        if position_key in processed_positions:
                            processed_positions.remove(position_key)
                            print(f"  {position_side} ポジションクローズ - 記録削除")
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n\n監視を停止しました")
            break
        except Exception as e:
            print(f"\nエラーが発生しました: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor_positions()
