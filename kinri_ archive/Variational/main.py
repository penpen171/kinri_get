import requests
import pandas as pd
from datetime import datetime

VARIATIONAL_API_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"

def fetch_variational_smart_cycle():
    try:
        response = requests.get(VARIATIONAL_API_URL, timeout=10)
        response.raise_for_status()
        res = response.json()
        listings = res.get('listings', [])
        
        # --- 4時間配布銘柄の定義リスト ---
        # 実測に基づき、GUA, SXP, コモディティ（GOLD/SILVER）などを指定
        FOUR_HOUR_TICKERS = ['GUA', 'SXP', 'GOLD', 'SILVER', 'NCCO']

        processed = []
        for item in listings:
            ticker = item.get('ticker')
            apr_raw = float(item.get('funding_rate', 0))
            
            # 理論値の算出 (1h = 8760分割)
            hourly_rate = apr_raw / 8760
            
            # --- 配布サイクルの自動判定 ---
            is_4h = any(key in ticker for key in FOUR_HOUR_TICKERS)
            
            if is_4h:
                # 4時間ごとの銘柄：1hの値を4倍して「4h配布分」を表示
                display_val = hourly_rate * 4
                cycle_label = "4h"
            else:
                # 1時間ごとの銘柄：1hの値をそのまま表示
                display_val = hourly_rate
                cycle_label = "1h"
            
            # スプレッド補正 (実測に基づき API値を約0.45倍)
            spread_bps = float(item.get('base_spread_bps', 0))
            real_spread = (spread_bps / 100) * 0.45 
            
            processed.append({
                '銘柄': ticker,
                'raw_hourly': hourly_rate, # ソート用の1h換算値
                '表示金利': f"{display_val * 100:+.4f}%",
                '周期': cycle_label,
                '実効スプ': f"{real_spread:.3f}%",
                '警告': "[!!!]" if real_spread >= 0.15 else "[!]" if real_spread >= 0.08 else ""
            })
            
        df = pd.DataFrame(processed)
        
        # 期待値が高い順に抽出（1hあたりの効率でソートすることで公平に比較）
        top_pos = df.sort_values('raw_hourly', ascending=False).head(3)
        top_neg = df.sort_values('raw_hourly', ascending=True).head(3).sort_values('raw_hourly', ascending=False)
        result = pd.concat([top_pos, top_neg])

        print(f"\nVariational サイクル同期モニター [{datetime.now().strftime('%H:%M:%S')}]")
        print("=" * 72)
        # 列幅を固定して表示を揃える
        header = f"{'銘柄':<10} {'金利(実配布)':<16} {'周期':<8} {'実効スプ':<12} {'警告':<8}"
        print(header)
        print("-" * 72)
        
        for _, row in result.iterrows():
            print(f"{row['銘柄']:<10} {row['表示金利']:<16} {row['周期']:<8} {row['実効スプ']:<12} {row['警告']:<8}")
            
        print("=" * 72)
        print("※周期が4hの銘柄は、画面に表示されている4時間分の金利を表示しています。")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_variational_smart_cycle()