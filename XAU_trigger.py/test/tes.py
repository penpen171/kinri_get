import hashlib
import hmac
import time
import requests

# ============================================
# APIキー設定（実際の値を入力）
# ============================================
API_KEY = "VrjIg16ORbQfSgFwjHt0yC2V6taekTSZ8eNPCS7Dpwhxfy7azBlQk68DC5OD9s6BGf3oOAywOKyq6F90kPQ"  # ここに実際のAPIキーを貼り付け
SECRET_KEY = "t3lz7ALUX69aFQ1fXrdHorJmMlIYhlcXQcVSoG8RfgxFi6DNsBLqvBxCrA9oJLZeo9AoCNREqA6aFzU84g"  # ここに実際のシークレットキーを貼り付け

BASE_URL = "https://open-api.bingx.com"

def generate_signature(params, secret_key):
    """APIシグネチャを生成"""
    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    signature = hmac.new(
        secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def test_api_key():
    """APIキーの認証テスト"""
    print("=== APIキー認証テスト ===\n")
    
    # 1. APIキーの長さチェック
    print(f"1. APIキーの長さ: {len(API_KEY)} 文字")
    print(f"   シークレットキーの長さ: {len(SECRET_KEY)} 文字")
    
    if API_KEY == "your_api_key_here" or SECRET_KEY == "your_secret_key_here":
        print("\n⚠️ エラー: APIキーが設定されていません！")
        print("   'your_api_key_here' を実際のAPIキーに置き換えてください。")
        return
    
    # 2. 空白文字チェック
    if API_KEY.strip() != API_KEY or SECRET_KEY.strip() != SECRET_KEY:
        print("\n⚠️ 警告: APIキーに前後の空白が含まれています。")
    
    # 3. APIキーでアカウント情報を取得してみる
    print("\n2. アカウント情報取得テスト...")
    timestamp = int(time.time() * 1000)
    params = {
        "timestamp": timestamp
    }
    
    signature = generate_signature(params, SECRET_KEY)
    params["signature"] = signature
    
    headers = {
        "X-BX-APIKEY": API_KEY
    }
    
    # 残高照会（認証が必要なエンドポイント）
    url = f"{BASE_URL}/openApi/swap/v2/user/balance"
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    
    print(f"\nレスポンス:")
    print(f"  コード: {data.get('code')}")
    print(f"  メッセージ: {data.get('msg')}")
    
    if data['code'] == 0:
        print("\n✅ 成功: APIキーは正しく設定されています！")
        print(f"\n残高情報:")
        if 'data' in data and 'balance' in data['data']:
            balance = data['data']['balance']
            print(f"  利用可能残高: {balance.get('availableMargin', 'N/A')} USDT")
            print(f"  総残高: {balance.get('balance', 'N/A')} USDT")
    else:
        print("\n❌ エラー: 認証に失敗しました")
        print("\n考えられる原因:")
        print("  1. APIキーまたはシークレットキーが間違っている")
        print("  2. 先物取引の権限が有効化されていない")
        print("  3. IP制限がかかっている")
        print("  4. APIキーが無効化または削除されている")
        print("\nBingXで確認してください:")
        print("  https://bingx.com/en/account/api")

if __name__ == "__main__":
    test_api_key()
