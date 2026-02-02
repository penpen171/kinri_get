import requests
import pandas as pd
from datetime import datetime
import time
import schedule

# --- 設定 ---
TOP_N = 10 
# Bitget V2 の全銘柄Tickerエンドポイント
# productType=USDT-FUTURES でUSDT無期限先物を指定
BITGET_API_URL = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"

def fetch_bitget_funding_rates():
    try:
        response = requests.get(BITGET_API_URL, timeout=15)
        response.raise_for_status()
        res_data = response.json()

        # Bitget V2は {'code': '00000', 'data': [...], 'msg': 'success'} 形式
        items = res_data.get('data', [])
        
        if not items:
            print("Bitgetからデータを取得できませんでした。")
            return

        processed_data = []
        for item in items:
            symbol = item.get('symbol')
            # Bitget V2 Ticker APIの金利キーは 'fundingRate'
            rate_raw = item.get('fundingRate')
            
            if symbol and rate_raw is not None:
                try:
                    funding_rate = float(rate_raw)
                    processed_data.append({
                        'symbol': symbol,
                        'raw_rate': funding_rate,
                        'rate_pct': f"{funding_rate * 100:.4f}%"
                    })
                except (ValueError, TypeError):
                    continue

        df = pd.DataFrame(processed_data)

        def print_ranking(title, sorted_df):
            print(f"\n{title}")
            display_df = sorted_df[['symbol', 'rate_pct']].copy()
            display_df.columns = ['銘柄', '金利']
            display_df.index = range(1, len(display_df) + 1)
            display_df.index.name = '順位'
            print(display_df.to_string())

        print("\n" + "="*45)
        print(f"Bitget 取得時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"有効銘柄数: {len(processed_data)}")
        print("="*45)

        # プラス金利ランキング
        top_positive = df.sort_values(by='raw_rate', ascending=False).head(TOP_N)
        print_ranking("【Bitget プラス金利 Top 10】", top_positive)

        # マイナス金利ランキング
        top_negative = df.sort_values(by='raw_rate', ascending=True).head(TOP_N)
        print_ranking("【Bitget マイナス金利 Top 10】", top_negative)

    except Exception as e:
        print(f"Bitget通信エラー: {e}")

def main():
    print("Bitget金利監視を開始します（V2 API使用）...")
    fetch_bitget_funding_rates()
    schedule.every(1).hours.do(fetch_bitget_funding_rates)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n終了します。")
            break

if __name__ == "__main__":
    main()