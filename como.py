import requests
import pandas as pd
from datetime import datetime
import time

EXCHANGES = {
    'MEXC': 'https://contract.mexc.com/api/v1/contract/ticker',
    'Bitget': 'https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES',
    'BingX': 'https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex',
    'Variational': 'https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats'
}

def fetch_commodity_data():
    results = []
    
    # --- データ取得ロジック ---
    # 1. BingX
    try:
        res = requests.get(EXCHANGES['BingX'], timeout=5).json()
        for i in res.get('data', []):
            sym = i['symbol'].upper()
            if 'GOLD' in sym or 'SILVER' in sym:
                results.append({'取引所': 'BingX', '銘柄': sym, '4h金利': float(i['lastFundingRate'])})
    except: pass

    # 2. Variational (実測同期: 1h換算を4倍して4h配布相当にする)
    try:
        res = requests.get(EXCHANGES['Variational'], timeout=5).json()
        for i in res.get('listings', []):
            sym = i['ticker'].upper()
            if 'GOLD' in sym or 'SILVER' in sym:
                rate_4h = (float(i['funding_rate']) / 2170) * 4
                results.append({'取引所': 'Variational', '銘柄': sym, '4h金利': rate_4h})
    except: pass

    # 3. MEXC / Bitget
    for name in ['MEXC', 'Bitget']:
        try:
            res = requests.get(EXCHANGES[name], timeout=5).json()
            for i in res.get('data', []):
                sym = i.get('symbol', i.get('symbolName', '')).upper()
                if 'GOLD' in sym or 'SILVER' in sym:
                    results.append({'取引所': name, '銘柄': sym, '4h金利': float(i.get('fundingRate', 0))})
        except: pass

    return results

def display_with_separator():
    data = fetch_commodity_data()
    if not data:
        print("データを取得中...")
        return

    df = pd.DataFrame(data)
    df['金利(%)'] = df['4h金利'].apply(lambda x: f"{x*100:+.4f}%")

    # 金と銀でデータを分ける
    gold_df = df[df['銘柄'].str.contains('GOLD')].sort_values('4h金利', ascending=False)
    silver_df = df[df['銘柄'].str.contains('SILVER')].sort_values('4h金利', ascending=False)

    print(f"\n【コモディティ金利監視（4h配布ベース）】 {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    print(f"{'取引所':<15} {'銘柄':<20} {'金利(%)':<15}")
    print("-" * 60)

    # 金のセクション表示
    if not gold_df.empty:
        for _, row in gold_df.iterrows():
            print(f"{row['取引所']:<15} {row['銘柄']:<20} {row['金利(%)']:<15}")
    
    # --- ここで金と銀の境界線を引く ---
    print("-" * 60)
    
    # 銀のセクション表示
    if not silver_df.empty:
        for _, row in silver_df.iterrows():
            print(f"{row['取引所']:<15} {row['銘柄']:<20} {row['金利(%)']:<15}")
            
    print("=" * 60)

if __name__ == "__main__":
    while True:
        try:
            display_with_separator()
            time.sleep(60)
        except KeyboardInterrupt:
            break