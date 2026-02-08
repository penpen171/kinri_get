import hashlib
import hmac
import time
import requests
from datetime import datetime

# configファイルから読み込む方法（推奨）
from config import API_KEY, SECRET_KEY, SYMBOL, BASE_URL

# または直接記述（APIキーを正しくコピー）
# API_KEY = "ここに83文字のAPIキーを1行で貼り付け"
# SECRET_KEY = "ここに82文字のシークレットキーを1行で貼り付け"
# SYMBOL = "XAUT-USDT"
# BASE_URL = "https://open-api.bingx.com"

def generate_signature(params, secret_key):
    """APIシグネチャを生成"""
    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    signature = hmac.new(
        secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def check_open_orders():
    """現在の未約定注文を確認"""
    print(f"\n=== 未約定の注文を確認中 ({SYMBOL}) ===")
    
    timestamp = int(time.time() * 1000)
    params = {
        "symbol": SYMBOL,
        "timestamp": timestamp
    }
    
    signature = generate_signature(params, SECRET_KEY)
    params["signature"] = signature
    headers = {"X-BX-APIKEY": API_KEY}
    
    url = f"{BASE_URL}/openApi/swap/v2/trade/openOrders"
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    
    if data['code'] == 0:
        orders = data['data']['orders']
        if not orders:
            print("未約定の注文はありません。")
        else:
            print(f"{len(orders)}件の未約定注文が見つかりました:")
            for order in orders:
                print(f"  ID: {order['orderId']}")
                print(f"  タイプ: {order['type']}")
                print(f"  サイド: {order['side']}")
                print(f"  価格: {order.get('price', '成行')}")
                print(f"  トリガー価格: {order.get('stopPrice', 'なし')}")
                print(f"  数量: {order['origQty']}")
                print("-" * 30)
    else:
        print(f"エラー: {data}")

def check_order_history():
    """最近の注文履歴を確認"""
    print(f"\n=== 最近の注文履歴を確認中 ({SYMBOL}) ===")
    
    timestamp = int(time.time() * 1000)
    params = {
        "symbol": SYMBOL,
        "limit": 10,
        "timestamp": timestamp
    }
    
    signature = generate_signature(params, SECRET_KEY)
    params["signature"] = signature
    headers = {"X-BX-APIKEY": API_KEY}
    
    url = f"{BASE_URL}/openApi/swap/v2/trade/allOrders"
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    
    if data['code'] == 0:
        orders = data['data']['orders']
        if not orders:
            print("注文履歴がありません。")
        else:
            print(f"最新{len(orders)}件の履歴:")
            for order in orders:
                status_map = {
                    "NEW": "新規",
                    "FILLED": "約定済",
                    "PARTIALLY_FILLED": "部分約定",
                    "CANCELED": "キャンセル",
                    "FAILED": "失敗"
                }
                status = status_map.get(order['status'], order['status'])
                
                print(f"  時間: {datetime.fromtimestamp(order['time']/1000)}")
                print(f"  ID: {order['orderId']}")
                print(f"  タイプ: {order['type']}")
                print(f"  ステータス: {status}")
                print(f"  サイド: {order['side']}")
                print(f"  数量: {order['origQty']}")
                print("-" * 30)
    else:
        print(f"エラー: {data}")

if __name__ == "__main__":
    check_open_orders()
    check_order_history()
