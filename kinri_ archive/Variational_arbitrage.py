import requests
import pandas as pd
from datetime import datetime
import time
import sys
import os

# ================= 設定エリア =================
DIFF_THRESHOLD = 0.20  # 表示ベースの乖離が 0.2% 以上でアラート
LEVERAGE = 10          
INTERVAL = 60          
CYCLE_FILE = "ticker_cycles.csv"  
# =============================================

APIS = {
    'Variational': "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats",
    'BingX': "https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex",
    'MEXC': "https://contract.mexc.com/api/v1/contract/ticker",
    'Bitget': "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
}

def load_cycle_list():
    if os.path.exists(CYCLE_FILE) and os.path.getsize(CYCLE_FILE) > 0:
        try: return pd.read_csv(CYCLE_FILE, index_col='ticker')
        except: return pd.DataFrame(columns=['ticker', 'cycle']).set_index('ticker')
    else:
        df = pd.DataFrame(columns=['ticker', 'cycle']).set_index('ticker')
        try: df.to_csv(CYCLE_FILE)
        except: pass
        return df

def update_cycle_list(found_tickers):
    df_cycles = load_cycle_list()
    updated = False
    for t in found_tickers:
        if t not in df_cycles.index:
            df_cycles.loc[t] = [None]
            updated = True
    if updated:
        try:
            df_cycles.to_csv(CYCLE_FILE)
            print(f"  [Info] リストを更新しました: {found_tickers}")
        except PermissionError:
            print(f"  [Warning] CSVが開かれているため更新をスキップしました。")
    return df_cycles

def get_v_data():
    try:
        res = requests.get(APIS['Variational'], timeout=10).json()
        data = {}
        for item in res['listings']:
            ticker = item['ticker']
            apr = float(item['funding_rate'])
            data[ticker] = {'rate': apr / 8760, 'spread': (float(item.get('base_spread_bps', 0)) / 10000)}
        return data
    except: return {}

def get_others_data(df_cycles):
    others = {}
    def process_ex(ex_name, api_url, t_key, r_key, suffix):
        try:
            res = requests.get(api_url, timeout=10).json()
            items = res.get('data', []) if isinstance(res.get('data'), list) else res.get('data', {}).get('list', [])
            if not items and ex_name == 'MEXC': items = res.get('data', [])
            for i in items:
                t = i[t_key].replace(suffix, '').replace('_USDT', '').replace('-USDT', '')
                raw = float(i[r_key])
                try:
                    c_val = df_cycles.loc[t, 'cycle']
                    cyc_n = 8 if str(c_val) in ['8', '8.0'] else 4
                except: cyc_n = 4
                others.setdefault(t, {})[ex_name] = {'raw': raw, 'cyc': f"{cyc_n}h"}
        except: pass

    process_ex('BingX', APIS['BingX'], 'symbol', 'lastFundingRate', '-USDT')
    process_ex('MEXC', APIS['MEXC'], 'symbol', 'fundingRate', '_USDT')
    process_ex('Bitget', APIS['Bitget'], 'symbol', 'fundingRate', 'USDT')
    return others

def main():
    print(f"監視開始。上位5銘柄（重複排除）を表示します。")
    while True:
        try:
            v_dict = get_v_data()
            df_cycles = load_cycle_list()
            o_dict = get_others_data(df_cycles)
            all_found = []
            
            for ticker, v_info in v_dict.items():
                if ticker in o_dict:
                    v_rate_pct = v_info['rate'] * 100
                    for ex_name, ex_info in o_dict[ticker].items():
                        other_rate_pct = ex_info['raw'] * 100
                        diff = abs(v_rate_pct - other_rate_pct)
                        if diff >= DIFF_THRESHOLD:
                            v_spread_pct = v_info['spread'] * 100
                            all_found.append({
                                '銘柄': ticker,
                                'V金利(1h)': v_rate_pct,
                                '比較先': f"{ex_name}({ex_info['cyc']})",
                                '他社表示': other_rate_pct,
                                '乖離(表示)': diff,
                                'Vスプ': v_spread_pct,
                                '10倍コスト': v_spread_pct * LEVERAGE
                            })

            print(f"\n【厳選上位5銘柄】 [{datetime.now().strftime('%H:%M:%S')}]")
            if all_found:
                # 1. まず乖離順に並び替え
                df = pd.DataFrame(all_found).sort_values('乖離(表示)', ascending=False)
                # 2. 銘柄の重複排除（一番乖離が高い行だけ残す）
                df = df.drop_duplicates(subset=['銘柄'], keep='first')
                # 3. 上位5銘柄に絞り込み
                df_top5 = df.head(5)
                
                # CSV更新用（表示される5銘柄のみ）
                update_cycle_list(df_top5['銘柄'].tolist())

                print("=" * 115)
                header = f"{'銘柄':<12} {'V金利(1h)':<14} {'比較対象(周期)':<18} {'他社表示':<14} {'乖離(表示)':<12} {'Vスプ':<8} {'10倍コスト':<8}"
                print(header)
                print("-" * 115)
                for _, r in df_top5.iterrows():
                    star = "★" if r['乖離(表示)'] > r['10倍コスト'] else "  "
                    print(f"{r['銘柄']:<12} {r['V金利(1h)']:>+12.4f}% {r['比較先']:<18} {r['他社表示']:>+12.4f}% {r['乖離(表示)']:>11.4f}% {r['Vスプ']:>7.3f}% {r['10倍コスト']:>8.2f}% {star}")
                print("=" * 115)
            else:
                print(f"現在、基準値 {DIFF_THRESHOLD}% を超える乖離はありません。")
            
            time.sleep(INTERVAL)
        except KeyboardInterrupt: sys.exit(0)
        except Exception as e:
            print(f"エラー発生(継続): {e}")
            time.sleep(10)

if __name__ == "__main__": main()