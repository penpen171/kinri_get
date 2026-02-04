import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import sys
import os

# ================= 設定エリア =================
MARGIN_USDT = 1000     
V_DIFF_THRESHOLD = 0.20 
EX_DIFF_THRESHOLD = 0.10 
LEVERAGES = [10, 20, 30, 40, 50]
INTERVAL = 60
CYCLE_FILE = "ticker_cycles.csv"
V_CYCLE_FILE = "v_cycles.csv" 
# =============================================

APIS = {
    'Variational': "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats",
    'BingX': "https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex",
    'MEXC': "https://contract.mexc.com/api/v1/contract/ticker",
    'Bitget': "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
}

EX_SHORT = {'BingX': 'BX', 'MEXC': 'MX', 'Bitget': 'BG'}

def load_cycles(file_path):
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        try: return pd.read_csv(file_path, index_col='ticker')
        except: return pd.DataFrame(columns=['ticker', 'cycle']).set_index('ticker')
    return pd.DataFrame(columns=['ticker', 'cycle']).set_index('ticker')

def update_cycle_files(v_tickers, o_tickers):
    df_v = load_cycles(V_CYCLE_FILE)
    v_upd = False
    for t in v_tickers:
        if t not in df_v.index:
            df_v.loc[t] = [0]
            v_upd = True
    if v_upd: df_v.to_csv(V_CYCLE_FILE)

    df_o = load_cycles(CYCLE_FILE)
    o_upd = False
    for t in o_tickers:
        if t not in df_o.index:
            df_o.loc[t] = [0]
            o_upd = True
    if o_upd: df_o.to_csv(CYCLE_FILE)

def get_next_funding_jst(cycle_hours):
    calc_cyc = 1 if not cycle_hours or cycle_hours == 0 else int(cycle_hours)
    now = datetime.now()
    if calc_cyc == 1:
        next_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    else:
        base_hours = [1, 5, 9, 13, 17, 21] if calc_cyc == 4 else [1, 9, 17]
        next_h = next((h for h in base_hours if h > now.hour), 1)
        next_time = now.replace(hour=next_h, minute=0, second=0, microsecond=0)
        if next_h == 1 and now.hour >= 21: next_time += timedelta(days=1)
    return next_time.strftime('%H:%M')

def get_v_data(v_cycles):
    try:
        res = requests.get(APIS['Variational'], timeout=15).json()
        data = {}
        for item in res['listings']:
            t = item['ticker']
            try:
                raw_val = v_cycles.loc[t, 'cycle']
                v_cyc = int(raw_val) if raw_val and int(raw_val) != 0 else 1
                disp_cyc = int(raw_val)
            except:
                v_cyc = 1
                disp_cyc = 0
            # Variationalは年利ベースなので (年利/8760)*周期
            rate = (float(item['funding_rate']) / 8760) * v_cyc * 100
            spread = (float(item.get('base_spread_bps', 0)) / 10000) * 100
            data[t] = {'rate': rate, 'spread': spread, 'cyc_calc': v_cyc, 'cyc_disp': disp_cyc}
        return data
    except: return {}

def get_others_data(df_cycles):
    others = {}
    def process(ex_name, api_url, t_key, r_key, suffix):
        try:
            res = requests.get(api_url, timeout=15).json()
            items = res.get('data', []) if isinstance(res.get('data'), list) else res.get('data', {}).get('list', [])
            if not items and ex_name == 'MEXC': items = res.get('data', [])
            for i in items:
                t = i[t_key].replace(suffix, '').replace('_USDT', '').replace('-USDT', '')
                try:
                    raw_val = df_cycles.loc[t, 'cycle']
                    calc_cyc = int(raw_val) if raw_val and int(raw_val) != 0 else 1
                    disp_cyc = int(raw_val)
                except:
                    calc_cyc = 1
                    disp_cyc = 0
                
                # 他社は従来通り、APIの値をそのまま利率（1回分）として使用
                raw_rate = (float(i[r_key]) * 100)
                others.setdefault(t, {})[ex_name] = {'raw': raw_rate, 'cyc_calc': calc_cyc, 'cyc_disp': disp_cyc}
        except: pass
    for name, url in [('BingX', APIS['BingX']), ('MEXC', APIS['MEXC']), ('Bitget', APIS['Bitget'])]:
        r_field = 'fundingRate' if name=='MEXC' else ('lastFundingRate' if name=='BingX' else 'fundingRate')
        suf = '-USDT' if name=='BingX' else ('_USDT' if name=='MEXC' else 'USDT')
        process(name, url, 'symbol', r_field, suf)
    return others

def main():
    while True:
        try:
            v_cycles = load_cycles(V_CYCLE_FILE)
            o_cycles = load_cycles(CYCLE_FILE)
            v_dict = get_v_data(v_cycles)
            o_dict = get_others_data(o_cycles)
            
            v_results, ex_results = [], []
            detected_v, detected_o = [], []

            for t, v_info in v_dict.items():
                if t in o_dict:
                    for ex_n, o_info in o_dict[t].items():
                        diff = abs(v_info['rate'] - o_info['raw'])
                        if diff >= V_DIFF_THRESHOLD:
                            v_results.append({
                                'ID': f"{t}(V:{v_info['cyc_disp']}h/O:{o_info['cyc_disp']}h)",
                                'V金利': v_info['rate'], '他': EX_SHORT[ex_n], '他金利': o_info['raw'],
                                '乖離': diff, '10倍': v_info['spread']*10, 'raw_t': t, 'next': get_next_funding_jst(v_info['cyc_calc'])
                            })
                            detected_v.append(t)
                            detected_o.append(t)

            for t, exs in o_dict.items():
                if len(exs) < 2: continue
                names = list(exs.keys())
                for i in range(len(names)):
                    for j in range(i+1, len(names)):
                        ex_a, ex_b = names[i], names[j]
                        ia, ib = exs[ex_a], exs[ex_b]
                        diff = abs(ia['raw'] - ib['raw'])
                        if diff >= EX_DIFF_THRESHOLD:
                            ex_results.append({
                                'ID': f"{t}({ia['cyc_disp']}h) [{get_next_funding_jst(ia['cyc_calc'])}]",
                                'S': f"{EX_SHORT[ex_a] if ia['raw']>ib['raw'] else EX_SHORT[ex_b]}",
                                'L': f"{EX_SHORT[ex_b] if ia['raw']>ib['raw'] else EX_SHORT[ex_a]}",
                                'SR': max(ia['raw'], ib['raw']), 'LR': min(ia['raw'], ib['raw']),
                                'diff': diff, 't': t
                            })
                            detected_o.append(t)

            update_cycle_files(list(set(detected_v)), list(set(detected_o)))

            os.system('cls' if os.name == 'nt' else 'clear')
            now = datetime.now().strftime('%H:%M:%S')
            
            print(f"【Variational 乖離】 {now} (Vのみ周期換算 / 他社はAPI生金利)")
            print("-" * 115)
            print(f"{'銘柄(周期構成) [次回]':<35} {'V金利':<10} {'他':<5} {'他金利':<10} {'乖離':<10} {'10倍コスト':<10}")
            if v_results:
                v_df = pd.DataFrame(v_results).sort_values('乖離', ascending=False).drop_duplicates('raw_t').head(5)
                for _, r in v_df.iterrows():
                    star = "★" if r['乖離'] > r['10倍'] else ""
                    print(f"{r['ID'] + ' [' + r['next'] + ']':<35} {r['V金利']:>+8.4f}% {r['他']:<5} {r['他金利']:>+8.4f}% {r['乖離']:>8.4f}% {r['10倍']:>8.2f}% {star}")
            
            print(f"\n【他社間 収益シミュレーション (USDT)】 証拠金: {MARGIN_USDT}U")
            print("-" * 140)
            print(f"{'銘柄(周期) [次回]':<28} {'Short':<12} {'Long':<12} {'差%':<10} |" + "".join([f"{l:>10}倍" for l in LEVERAGES]))
            if ex_results:
                ex_df = pd.DataFrame(ex_results).sort_values('diff', ascending=False).drop_duplicates('t').head(5)
                for _, r in ex_df.iterrows():
                    s_inf, l_inf = f"{r['S']}:{r['SR']:>+6.3f}%", f"{r['L']}:{r['LR']:>+6.3f}%"
                    vals = "".join([f"{MARGIN_USDT * lev * (r['diff']/100):>12.2f}" for lev in LEVERAGES])
                    print(f"{r['ID']:<28} {s_inf:<12} {l_inf:<12} {r['diff']:>8.4f}% |{vals}")
            
            time.sleep(INTERVAL)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(10)

if __name__ == "__main__": main()