# test_freeze_detector.py
import requests
from datetime import datetime

BASE_URL = "https://open-api.bingx.com"
ENDPOINT = "/openApi/swap/v3/quote/klines"

def test_bingx_connection():
    """BingX APIの接続テスト"""
    print("🔍 BingX API接続テスト開始...")
    
    test_symbol = "NCSINASDAQ1002USD-USDT"
    
    try:
        params = {
            "symbol": test_symbol,
            "interval": "1m",
            "limit": 5
        }
        
        response = requests.get(f"{BASE_URL}{ENDPOINT}", params=params, timeout=8)
        data = response.json()
        
        if data.get("code") == 0 and data.get("data"):
            print(f"✅ 接続成功！")
            print(f"\n取得データ:")
            
            for i, candle in enumerate(data['data'][-3:], 1):
                timestamp = datetime.fromtimestamp(int(candle['time']) / 1000)
                open_p = float(candle['open'])
                close_p = float(candle['close'])
                high_p = float(candle['high'])
                low_p = float(candle['low'])
                
                body = abs(close_p - open_p)
                range_val = high_p - low_p
                
                print(f"\n  ローソク足 #{i}")
                print(f"    時刻: {timestamp.strftime('%H:%M:%S')}")
                print(f"    価格: {close_p:.2f}")
                print(f"    実体: {body:.4f}")
                print(f"    レンジ: {range_val:.4f}")
            
            return True
        else:
            print(f"❌ エラー: {data}")
            return False
            
    except Exception as e:
        print(f"❌ 例外エラー: {e}")
        return False

if __name__ == "__main__":
    test_bingx_connection()
