import hashlib
import hmac
import time
import requests
from config import API_KEY, SECRET_KEY, BASE_URL

SYMBOL = "XAUT-USDT"

def generate_signature(query_string, secret_key):
    """署名を生成"""
    signature = hmac.new(
        secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def get_current_price():
    """現在価格を取得"""
    url = f"{BASE_URL}/openApi/swap/v2/quote/price"
    params = {"symbol": SYMBOL}
    response = requests.get(url, params=params)
    data = response.json()
    if data['code'] == 0:
        return float(data['data']['price'])
    return None

def test_trigger_order_v3():
    """トリガー注文のテスト（パラメータ修正版）"""
    print("=== トリガー注文テスト（パラメータ修正版） ===\n")
    
    # 現在価格取得
    current_price = get_current_price()
    if not current_price:
        print("❌ 価格取得失敗")
        return
    
    print(f"現在価格: {current_price}")
    
    # パラメータ準備
    trigger_price = str(round(current_price + 5, 1))
    quantity = "0.001"
    timestamp = str(int(time.time() * 1000))
    
    print(f"トリガー価格: {trigger_price}")
    print(f"数量: {quantity}\n")
    
    # パラメータを辞書で作成（positionSideとworkingTypeを修正）
    params = {
        "symbol": SYMBOL,
        "side": "BUY",
        "positionSide": "LONG",  # 追加：LONG, SHORT, BOTH
        "type": "TRIGGER_MARKET",
        "quantity": quantity,
        "stopPrice": trigger_price,
        "workingType": "MARK_PRICE",  # 修正：LAST_PRICE → MARK_PRICE
        "timestamp": timestamp
    }
    
    # クエリ文字列を生成
    query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
    print(f"署名前のクエリ文字列:\n{query_string}\n")
    
    # 署名を生成
    signature = generate_signature(query_string, SECRET_KEY)
    
    # 署名を含めた完全なクエリ文字列
    full_query = f"{query_string}&signature={signature}"
    
    # ヘッダー
    headers = {
        "X-BX-APIKEY": API_KEY
    }
    
    # URLに直接クエリパラメータを含める
    url = f"{BASE_URL}/openApi/swap/v2/trade/order?{full_query}"
    
    print("注文送信中...\n")
    
    # POSTリクエスト
    response = requests.post(url, headers=headers)
    data = response.json()
    
    print(f"レスポンス: {data}\n")
    
    if data['code'] == 0:
        print(f"✅ 注文成功！")
        if 'data' in data and 'order' in data['data']:
            order_info = data['data']['order']
            print(f"   注文ID: {order_info.get('orderId', 'N/A')}")
            print(f"   シンボル: {order_info.get('symbol', 'N/A')}")
            print(f"   サイド: {order_info.get('side', 'N/A')}")
            print(f"   数量: {order_info.get('origQty', 'N/A')}")
            print(f"   トリガー価格: {order_info.get('stopPrice', 'N/A')}")
    else:
        print(f"❌ 注文失敗")
        print(f"   エラーコード: {data['code']}")
        print(f"   エラーメッセージ: {data.get('msg', '不明')}")

# ショート注文のテストも追加
def test_short_trigger_order():
    """ショートトリガー注文のテスト"""
    print("\n=== ショートトリガー注文テスト ===\n")
    
    current_price = get_current_price()
    if not current_price:
        print("❌ 価格取得失敗")
        return
    
    print(f"現在価格: {current_price}")
    
    trigger_price = str(round(current_price - 5, 1))  # 現在価格-5ドル
    quantity = "0.001"
    timestamp = str(int(time.time() * 1000))
    
    print(f"トリガー価格: {trigger_price}")
    print(f"数量: {quantity}\n")
    
    params = {
        "symbol": SYMBOL,
        "side": "SELL",  # ショートはSELL
        "positionSide": "SHORT",  # ショートポジション
        "type": "TRIGGER_MARKET",
        "quantity": quantity,
        "stopPrice": trigger_price,
        "workingType": "MARK_PRICE",
        "timestamp": timestamp
    }
    
    query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
    signature = generate_signature(query_string, SECRET_KEY)
    full_query = f"{query_string}&signature={signature}"
    
    headers = {"X-BX-APIKEY": API_KEY}
    url = f"{BASE_URL}/openApi/swap/v2/trade/order?{full_query}"
    
    print("注文送信中...\n")
    response = requests.post(url, headers=headers)
    data = response.json()
    
    print(f"レスポンス: {data}\n")
    
    if data['code'] == 0:
        print(f"✅ ショート注文成功！")
        if 'data' in data and 'order' in data['data']:
            order_info = data['data']['order']
            print(f"   注文ID: {order_info.get('orderId', 'N/A')}")
    else:
        print(f"❌ 注文失敗")
        print(f"   エラーコード: {data['code']}")
        print(f"   エラーメッセージ: {data.get('msg', '不明')}")

if __name__ == "__main__":
    # ロング注文テスト
    test_trigger_order_v3()
    
    # ショート注文テスト
    time.sleep(1)  # 1秒待機
    test_short_trigger_order()
