import requests
import pandas as pd
from datetime import datetime
import time

# --- 各取引所の設定 ---
EXCHANGES = {
    'MEXC': {
        'url': 'https://contract.mexc.com/api/v1/contract/ticker',
        'rate_key': 'fundingRate',
        'sym_key': 'symbol'
    },
    'Bitget': {
        'url': 'https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES',
        'rate_key': 'fundingRate',
        'sym_key': 'symbol'
    },
    'BingX': {
        'url': 'https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex',
        'rate_key': 'lastFundingRate',
        'sym_key': 'symbol'
    }
}

def fetch_data(name, config):
    try:
        res = requests.get(config['url'], timeout=10).json()
        items = res.get('data', [])
        
        extracted = []
        for item in items:
            raw_rate = item.get(config['rate_key'])
            if raw_rate is not None:
                rate = float(raw_rate)
                extracted.append({
                    '取引所': name,
                    '銘柄': item.get(config['sym_key']),
                    '金利': rate,
                    '表示金利': f"{rate * 100:+.4f}%"
                })
        return pd.DataFrame(extracted)
    except Exception as e:
        print(f"【{name}】取得エラー: {e}")
        return pd.DataFrame()

def show_all_rankings():
    print(f"\n" + "█"*60)
    print(f" 全取引所 金利一括モニタリング [{datetime.now().strftime('%H:%M:%S')}]")
    print("█"*60)

    for name, config in EXCHANGES.items():
        df = fetch_data(name, config)
        
        if df.empty:
            continue

        print(f"\n─── 【 {name} 】 ───")
        
        # 1. プラス金利 Top 5 (高い順に並べて、一番上が最大)
        top_pos = df.sort_values(by='金利', ascending=False).head(5)
        
        # 2. マイナス金利 Top 5 (0に近い順から並べて、一番下が最もマイナス)
        # 修正ポイント：ascending=False にすることで、-0.1% -> -0.5% -> -1.2% の順に並びます
        top_neg = df.sort_values(by='金利', ascending=True).head(5).sort_values(by='金利', ascending=False)

        # 表示用に結合
        summary = pd.concat([top_pos, top_neg])
        
        # 整理して表示
        display_df = summary[['銘柄', '表示金利']].copy()
        display_df.columns = ['銘柄', 'Funding Rate']
        print(display_df.to_string(index=False))

def main():
    while True:
        try:
            show_all_rankings()
            print("\n" + "─"*60)
            print("60秒後に再取得します (Ctrl+C で終了)")
            time.sleep(60)
        except KeyboardInterrupt:
            print("\nプログラムを終了します。")
            break

if __name__ == "__main__":
    main()