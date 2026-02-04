import requests

# 2026年現在の有効なエンドポイント候補
BASE_URL = "https://open-api.bingx.com"
# 標準的な一括取得パス
ENDPOINT = "/openApi/swap/v2/quote/tickers"

def find_symbols_final():
    try:
        print(f"🔍 BingX全銘柄スキャン開始...")
        # v2/quote/tickers がダメな場合は、基本の contracts を再試行
        response = requests.get(f"{BASE_URL}{ENDPOINT}", timeout=10)
        data = response.json()
        
        # もし quote/tickers が存在しない場合は、代替エンドポイントを自動試行
        if data.get("code") == 100400:
            print("⚠️ v2/quote/tickers 無効。代替エンドポイントを試行中...")
            ENDPOINT_ALT = "/openApi/swap/v2/quote/contracts"
            response = requests.get(f"{BASE_URL}{ENDPOINT_ALT}", timeout=10)
            data = response.json()

        if data.get("code") == 0:
            # dataの中身が直接リストの場合と、dictの場合があるため対応
            raw_data = data.get("data", [])
            print(f"--- 検索結果 ---")
            
            keywords = ["DOW", "DJI", "WALLST", "US30", "NAS", "SP500", "USDT"]
            found_count = 0
            
            # リスト構造を解析して表示
            items = raw_data if isinstance(raw_data, list) else [raw_data]
            for item in items:
                # 銘柄情報のキーを探す (symbol か name)
                symbol = item.get("symbol", item.get("name", "")).upper()
                if any(k in symbol for k in keywords):
                    print(f"✅ 発見: {symbol}")
                    found_count += 1
            
            if found_count == 0:
                print("❌ 該当するインデックスが見つかりません。")
                # 全銘柄の最初の10個だけ表示して構造を確認
                print("【構造確認用サンプル】:", items[:3])
        else:
            print(f"❌ エラー内容: {data}")
            
    except Exception as e:
        print(f"⚠️ 通信エラー: {e}")

if __name__ == "__main__":
    find_symbols_final()