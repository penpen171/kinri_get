import requests
import pandas as pd
import time
import schedule
from datetime import datetime

# --- 設定 ---
TOP_N = 10  # ランキング表示数

def fetch_and_rank_funding_rates():
    """
    BingXから資金調達率を取得し、日本語の表形式でランキングを表示する
    """
    url = "https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['code'] != 0:
            print(f"API Error: {data['msg']}")
            return

        items = data['data']
        processed_data = []

        for item in items:
            symbol = item['symbol']
            try:
                funding_rate = float(item['lastFundingRate'])
                next_funding_time = int(item['nextFundingTime'])
                
                # 時刻変換
                dt_object = datetime.fromtimestamp(next_funding_time / 1000)
                formatted_time = dt_object.strftime('%m-%d %H:%M')

                processed_data.append({
                    'symbol': symbol,
                    'raw_rate': funding_rate,
                    'rate_pct': f"{funding_rate * 100:.4f}%",
                    'time': formatted_time
                })
            except (ValueError, TypeError):
                continue

        # データフレーム作成
        df = pd.DataFrame(processed_data)

        if df.empty:
            print("データが取得できませんでした。")
            return

        # --- 表示用関数 ---
        def print_ranking(title, sorted_df):
            print(f"\n{title}")
            
            # 表示用にデータを整形（カラム名を日本語に変更）
            display_df = sorted_df[['symbol', 'rate_pct', 'time']].copy()
            display_df.columns = ['銘柄', '金利', '次回時刻']
            
            # インデックスを1から振って「順位」とする
            display_df.index = range(1, len(display_df) + 1)
            display_df.index.name = '順位'
            
            # 表として出力
            print(display_df.to_string())

        # --- 実行時刻 ---
        print("\n" + "="*40)
        print(f"取得時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*40)

        # --- プラス金利ランキング (高い順) ---
        # ロングがショートに支払う金利
        top_positive = df.sort_values(by='raw_rate', ascending=False).head(TOP_N)
        print_ranking("【プラス金利 Top 10 (ロング支払い)】", top_positive)

        # --- マイナス金利ランキング (低い順) ---
        # ショートがロングに支払う金利 (ロング受け取り)
        top_negative = df.sort_values(by='raw_rate', ascending=True).head(TOP_N)
        print_ranking("【マイナス金利 Top 10 (ロング受取)】", top_negative)
        
        print("\n" + "-"*40 + "\n")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

# --- 実行制御 ---
def main():
    print("スクリプトを開始します。(Ctrl+C で終了)")
    
    # 初回実行
    fetch_and_rank_funding_rates()

    # 1時間毎に実行
    schedule.every(1).hours.do(fetch_and_rank_funding_rates)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()