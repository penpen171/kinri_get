import requests
import pandas as pd
from datetime import datetime
import time

# --- 各取引所の取得先設定 ---
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

def clean_symbol(sym):
    """シンボル名を比較用に正規化 (BTC_USDT, BTC-USDT, BTCUSDT_UMCBL -> BTCUSDT)"""
    if not sym: return ""
    return sym.replace('_', '').replace('-', '').replace('USDT_UMCBL', 'USDT').upper()

def fetch_all_data():
    all_raw = {}
    normalized_data = {}
    
    for name, config in EXCHANGES.items():
        try:
            res = requests.get(config['url'], timeout=10).json()
            items = res.get('data', [])
            
            exch_dict = {}
            raw_list = []
            for item in items:
                sym = item.get(config['sym_key'])
                rate_raw = item.get(config['rate_key'])
                if rate_raw is not None:
                    rate = float(rate_raw)
                    clean_sym = clean_symbol(sym)
                    exch_dict[clean_sym] = rate
                    raw_list.append({'銘柄': sym, '金利': rate, '表示': f"{rate*100:+.4f}%"})
            
            normalized_data[name] = exch_dict
            all_raw[name] = pd.DataFrame(raw_list)
        except:
            normalized_data[name] = {}
            all_raw[name] = pd.DataFrame()
            
    return normalized_data, all_raw

def run_combined_monitor():
    norm_data, raw_dfs = fetch_all_data()
    
    print("\n" + "█"*85)
    print(f"  GLOBAL FUNDING MONITORING SYSTEM - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*85)

    # --- 1. 各取引所のランキング表示 ---
    print("\n[ 各取引所別 金利ランキング (Top/Bottom 3) ]")
    print("-" * 85)
    
    summary_cols = []
    for name in EXCHANGES.keys():
        df = raw_dfs[name]
        if df.empty: continue
        
        # プラス最大3件とマイナス最大3件（マイナスが強い方が下）
        top3 = df.sort_values('金利', ascending=False).head(3)
        bot3 = df.sort_values('金利', ascending=True).head(3).sort_values('金利', ascending=False)
        
        print(f"【{name}】")
        combined_top_bot = pd.concat([top3, bot3])
        print(combined_top_bot[['銘柄', '表示']].to_string(index=False, header=False))
        print("-" * 30)

    # --- 2. 取引所間の金利差モニター ---
    print("\n[ 取引所間 アービトラージ・スプレッド (Max Diff Top 10) ]")
    print("=" * 85)
    
    all_syms = sorted(set(norm_data['MEXC'].keys()) | set(norm_data['Bitget'].keys()) | set(norm_data['BingX'].keys()))
    diff_results = []
    
    for s in all_syms:
        if "USDT" not in s: continue
        m, bt, bx = norm_data['MEXC'].get(s), norm_data['Bitget'].get(s), norm_data['BingX'].get(s)
        rates = [r for r in [m, bt, bx] if r is not None]
        
        if len(rates) >= 2:
            diff = max(rates) - min(rates)
            diff_results.append({
                '銘柄': s,
                'MEXC': m, 'Bitget': bt, 'BingX': bx, '最大差': diff
            })
            
    if diff_results:
        diff_df = pd.DataFrame(diff_results).sort_values('最大差', ascending=False).head(10)
        # 表示整形
        for col in ['MEXC', 'Bitget', 'BingX', '最大差']:
            diff_df[col] = diff_df[col].apply(lambda x: f"{x*100:+.3f}%" if pd.notnull(x) else "---")
        print(diff_df.to_string(index=False))
    
    print("=" * 85)

if __name__ == "__main__":
    while True:
        try:
            run_combined_monitor()
            print("\n60秒後に更新します (Ctrl+C で終了)")
            time.sleep(60)
        except KeyboardInterrupt:
            print("\n終了します。")
            break