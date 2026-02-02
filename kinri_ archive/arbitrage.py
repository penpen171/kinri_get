import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import sys
import os

# ================= 設定エリア =================
MARGIN_USDT = 100     
DIFF_THRESHOLD = 0.10  
INTERVAL = 60
CYCLE_FILE = "ticker_cycles.csv"
LEVERAGES = [10, 20, 30, 40, 50]  
# =============================================

APIS = {
    'BingX': "https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex",
    'MEXC': "https://contract.mexc.com/api/v1/contract/ticker",
    'Bitget': "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
}

def load_cycle_list():
    if os.path.exists(CYCLE_FILE) and os.path.getsize(CYCLE_FILE) > 0:
        try: return pd.read_csv(CYCLE_FILE, index_col='ticker')
        except: return pd.DataFrame(columns=['ticker', 'cycle']).set_index('ticker')
    else:
        return pd.DataFrame(columns=['ticker', 'cycle']).set_index('ticker')

def get_next_funding_time_jst(cycle_hours):
    """次の配布時刻を日本時間(JST)で算出する"""
    now = datetime.now()
    # 多くの取引所の標準: UTC 0,4,8,12,16,20 -> JST 9,13,17,21,1,5
    # 計算を簡略化するため、1時を起点としたサイクルで算出
    base_hours = [1, 5, 9, 13, 17, 21] if cycle_hours == 4 else [1, 9, 17]
    
    next_hour = None
    for h in base_hours:
        if h > now.hour:
            next_hour = h
            break
    
    # 21時(または17時)を過ぎていた場合は翌日の1時
    if next_hour is None:
        return "01:00"
    else:
        return f"{next_hour:02d}:00"

def get_exchanges_data(df_cycles):
    all_data = {}
    def process_ex(ex_name, api_url, t_key, r_key, suffix):
        try:
            res = requests.get(api_url, timeout=10).json()
            items = res.get('data', []) if isinstance(res.get('data'), list) else res.get('data', {}).get('list', [])
            if not items and ex_name == 'MEXC': items = res.get('data', [])
            for i in items:
                t = i[t_key].replace(suffix, '').replace('_USDT', '').replace('-USDT', '')
                raw_rate = float(i[r_key])
                try:
                    c_val = df_cycles.loc[t, 'cycle']
                    cyc_num = 8 if str(c_val) in ['8', '8.0'] else 4
                except: cyc_num = 4
                all_data.setdefault(t, {})[ex_name] = {'raw': raw_rate * 100, 'cyc': cyc_num}
        except: pass

    process_ex('BingX', APIS['BingX'], 'symbol', 'lastFundingRate', '-USDT')
    process_ex('MEXC', APIS['MEXC'], 'symbol', 'fundingRate', '_USDT')
    process_ex('Bitget', APIS['Bitget'], 'symbol', 'fundingRate', 'USDT')
    return all_data

def main():
    print(f"【他社間シミュレーター】証拠金: {MARGIN_USDT:,} USDT / 次回配布時刻表示モード")
    while True:
        try:
            df_cycles = load_cycle_list()
            data = get_exchanges_data(df_cycles)
            results = []

            for ticker, ex_dict in data.items():
                if len(ex_dict) < 2: continue
                ex_names = list(ex_dict.keys())
                for i in range(len(ex_names)):
                    for j in range(i + 1, len(ex_names)):
                        ex_a, ex_b = ex_names[i], ex_names[j]
                        info_a, info_b = ex_dict[ex_a], ex_dict[ex_b]
                        diff = abs(info_a['raw'] - info_b['raw'])
                        
                        if diff >= DIFF_THRESHOLD:
                            # 日本時間の次回配布時刻を取得
                            cyc_num = info_a['cyc']
                            next_time_jst = get_next_funding_time_jst(cyc_num)
                            ticker_display = f"{ticker}({cyc_num}h) [次回 {next_time_jst}]"
                            
                            if info_a['raw'] > info_b['raw']:
                                s_ex, l_ex, s_rate, l_rate = ex_a, ex_b, info_a['raw'], info_b['raw']
                            else:
                                s_ex, l_ex, s_rate, l_rate = ex_b, ex_a, info_b['raw'], info_a['raw']

                            res = {'銘柄': ticker_display, 'Short先': s_ex, 'Long先': l_ex, 'S金利': s_rate, 'L金利': l_rate, '金利差': diff}
                            for lev in LEVERAGES:
                                res[f"{lev}倍"] = MARGIN_USDT * lev * (diff / 100)
                            results.append(res)

            print(f"\n【他社間 金利差収益シミュレーション】 [{datetime.now().strftime('%H:%M:%S')}]")
            if results:
                df = pd.DataFrame(results).sort_values('金利差', ascending=False)
                df['raw_ticker'] = df['銘柄'].str.split('(').str[0]
                df = df.drop_duplicates(subset=['raw_ticker']).head(5)
                
                print("-" * 140)
                header = f"{'銘柄(周期) [次回配布]':<25} {'Short(金利)':<18} {'Long(金利)':<18} | " + " ".join([f"{lev:>8}倍" for lev in LEVERAGES])
                print(header)
                print("-" * 140)
                
                for _, r in df.iterrows():
                    s_info = f"{r['Short先']}: {r['S金利']:>+7.4f}%"
                    l_info = f"{r['Long先']}: {r['L金利']:>+7.4f}%"
                    vals = " ".join([f"{r[f'{lev}倍']:>10.2f}" for lev in LEVERAGES])
                    print(f"{r['銘柄']:<25} {s_info:<18} {l_info:<18} | {vals}")
                
                print("-" * 140)
                print(f"※[次回配布]は日本時間(JST)での予定時刻です。証拠金: {MARGIN_USDT:,} USDT")
            else:
                print(f"現在、金利差 {DIFF_THRESHOLD}% 以上の銘柄はありません。")

            time.sleep(INTERVAL)
        except KeyboardInterrupt: sys.exit(0)
        except Exception as e:
            print(f"エラー: {e}"); time.sleep(10)

if __name__ == "__main__":
    main()