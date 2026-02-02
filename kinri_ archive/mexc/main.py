import requests
import pandas as pd
from datetime import datetime
import time
import schedule

# --- 設定 ---
TOP_N = 10 
TICKER_API_URL = "https://contract.mexc.com/api/v1/contract/ticker"

def fetch_mexc_funding_rates():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(TICKER_API_URL, headers=headers, timeout=15)
        response.raise_for_status()
        res_data = response.json()

        items = res_data.get('data', [])
        
        processed_data = []
        for item in items:
            symbol = item.get('symbol')
            # ログにより確定したキー名 'fundingRate' を使用
            rate_raw = item.get('fundingRate')
            
            if symbol and rate_raw is not None:
                try:
                    # 指数表記（2.2e-05など）もfloat()で正しく数値化されます
                    funding_rate = float(rate_raw)
                    
                    processed_data.append({
                        'symbol': symbol,
                        'raw_rate': funding_rate,
                        'rate_pct': f"{funding_rate * 100:.4f}%"
                    })
                except (ValueError, TypeError):
                    continue

        if not processed_data:
            print("解析に失敗しました。データの形式が再度変更された可能性があります。")
            return

        df = pd.DataFrame(processed_data)

        def print_ranking(title, sorted_df):
            print(f"\n{title}")
            display_df = sorted_df[['symbol', 'rate_pct']].copy()
            display_df.columns = ['銘柄', '金利']
            display_df.index = range(1, len(display_df) + 1)
            display_df.index.name = '順位'
            print(display_df.to_string())

        print("\n" + "="*45)
        print(f"MEXC 取得時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"有効銘柄数: {len(processed_data)}")
        print("="*45)

        # 1. プラス金利ランキング
        top_positive = df.sort_values(by='raw_rate', ascending=False).head(TOP_N)
        print_ranking("【MEXC プラス金利 Top 10】", top_positive)

        # 2. マイナス金利ランキング
        top_negative = df.sort_values(by='raw_rate', ascending=True).head(TOP_N)
        print_ranking("【MEXC マイナス金利 Top 10】", top_negative)

    except Exception as e:
        print(f"エラー: {e}")

def main():
    print("MEXC金利監視システム（確定版ロジック）を起動中...")
    fetch_mexc_funding_rates()
    schedule.every(1).hours.do(fetch_mexc_funding_rates)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n終了します。")
            break

if __name__ == "__main__":
    main()