import streamlit as st
import pandas as pd
import requests
import os
from datetime import datetime, timedelta


# --- ページ基本設定 ---
st.set_page_config(page_title="金利ーマン Dashboard v3.5.1", layout="wide")


# --- 現場専用スタイルシート ---
st.markdown("""
<style>
    .report-table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 5px; }
    .report-table th { background-color: #f1f5f9; padding: 6px 2px; font-size: 11px; border: 1px solid #cbd5e1; text-align: center; color: #475569; }
    .report-table td { border: 1px solid #cbd5e1; padding: 8px 2px; text-align: center; vertical-align: middle; line-height: 1.2; }
    .ticker-text { font-weight: 800; font-size: 1.15em; color: #1e293b; }
    .ex-label { font-size: 0.85em; font-weight: bold; color: #334155; display: block; margin-bottom: 2px; }
    .rate-val { font-size: 1.1em; font-weight: 600; color: #0f172a; }
    .dist-time { font-size: 0.75em; color: #64748b; background: #f1f5f9; padding: 1px 4px; border-radius: 3px; display: inline-block; margin-top: 3px; }
    .net-profit { background-color: #fffbeb; font-size: 1.3em !important; font-weight: 900; color: #b45309; }
    .lev-amount { font-size: 1.1em; font-weight: 700; color: #000; }
    .update-ts { font-size: 0.5em; color: #94a3b8; font-weight: normal; margin-left: 10px; }
</style>
""", unsafe_allow_html=True)


# --- [共通モジュール] カタログ読み込み (Bitget Interval列対応) ---
def load_cycle_master():
    target_file = "bitget_true_catalog_0131_0704.csv"
    if os.path.exists(target_file):
        try:
            df = pd.read_csv(target_file)
            if 'Symbol' in df.columns and 'Interval' in df.columns:
                return dict(zip(
                    df['Symbol'].str.replace('USDT', '', regex=False), 
                    df['Interval']
                ))
        except: pass
    return {}


# --- [共通モジュール] 時間正規化ロジック (Interval対応版) ---
def normalize_time(time_input, exchange_name, cycle_hint=None):
    now_h = (datetime.now().hour)
    sched = [1, 9, 17]
    if exchange_name == "BingX": sched = [1, 5, 9, 13, 17, 21]
    
    if cycle_hint:
        if cycle_hint == '1h': sched = list(range(24))
        elif cycle_hint == '4h': sched = [1, 5, 9, 13, 17, 21]
        elif cycle_hint == '8h': sched = [1, 9, 17]

    def get_fallback():
        return next((h for h in sched if h > now_h), sched[0])

    try:
        if not time_input or time_input == 0: return get_fallback()
        
        if isinstance(time_input, (int, float)):
            if time_input < 1000000: return get_fallback()
            dt = pd.to_datetime(time_input, unit='ms')
        else:
            dt = pd.to_datetime(time_input)
        
        jst_dt = dt + timedelta(hours=9)
        hour = jst_dt.hour
        
        if exchange_name == "MEXC":
            mexc_sched = [1, 9, 17]
            return int(min(mexc_sched, key=lambda x: abs(x - hour)))
            
        return int(hour)
    except Exception:
        return get_fallback()


# --- [共通モジュール] APIデータ取得 ---
@st.cache_data(ttl=60)
def fetch_api_snapshot():
    data = {}; status = {"MEXC": "🔴", "BingX": "🔴", "Bitget": "🔴"}; ua = "Mozilla/5.0"
    cycle_master = load_cycle_master() 
    
    # 1. MEXC
    try:
        r = requests.get("https://api.mexc.com/api/v1/contract/ticker", headers={"User-Agent": ua}, timeout=5).json()
        if r.get('success'):
            for i in r['data']:
                sym = i['symbol'].split('_')[0]
                next_time = i.get('nextSettleTime')
                t_val = normalize_time(next_time, "MEXC")
                data.setdefault(sym, {})['MEXC'] = {
                    'rate': float(i.get('lastFundingRate') or i.get('fundingRate', 0))*100, 
                    'p': float(i['lastPrice']), 
                    'v': abs(float(i['riseFallRate']))*100, 
                    'm': 200 if sym in ['BTC','ETH'] else 50, 't': t_val
                }
            status["MEXC"] = "🟢"
    except: pass

    # 2. Bitget
    try:
        bg_r = requests.get("https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures", timeout=5).json()
        if bg_r.get('code')=='00000':
            for i in bg_r['data']:
                sym = i['symbol'].replace('USDT','')
                next_time = float(i.get('nextFundingTime', 0))
                hint = cycle_master.get(sym, None)
                t_val = normalize_time(next_time, "Bitget", cycle_hint=hint)
                data.setdefault(sym, {})['Bitget'] = {
                    'rate': float(i['fundingRate'])*100, 
                    'p': float(i['lastPr']), 
                    'v': abs(float(i.get('priceChangePercent',0)))*100, 
                    'm': 125 if sym in ['BTC','ETH'] else 50, 't': t_val
                }
            status["Bitget"] = "🟢"
    except: pass

    # 3. BingX
    try:
        bx_t = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/ticker", timeout=5).json()
        bx_r = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex", timeout=5).json()
        bx_v = {x['symbol'].split('-')[0]: abs(float(x['priceChangePercent'])) for x in bx_t.get('data', [])}
        for i in bx_r.get('data', []):
            sym = i['symbol'].split('-')[0]
            next_time = float(i.get('nextFundingTime', 0))
            t_val = normalize_time(next_time, "BingX")
            data.setdefault(sym, {})['BingX'] = {
                'rate': float(i['lastFundingRate'])*100, 
                'p': float(i['markPrice']), 
                'v': bx_v.get(sym,0), 
                'm': 150 if sym in ['BTC','ETH'] else 20, 't': t_val
            }
        status["BingX"] = "🟢"
    except: pass
    
    return data, status, datetime.now().strftime("%H:%M:%S")


# --- [共通モジュール] リスク判定エンジン ---
def calculate_risk(d1, d2, levs, t_key):
    risk_configs = {"scalp":{"w":0.9,"d":1.2},"hedge":{"w":0.4,"d":0.7},"hold":{"w":0.2,"d":0.4}}
    cfg = risk_configs[t_key]
    res = []
    for l in levs:
        if l > d1['m'] or l > d2['m']: res.append("MAX")
        else:
            vol = ((d1['v']+d2['v'])/2) / (100/l)
            res.append('❌' if vol > cfg['d'] else ('⚠️' if vol > cfg['w'] else '✅'))
    return res


# --- [エンジンA] 同時刻金利版（裁定取引） ---
def run_simultaneous_engine(raw, active_exs, levs, t_key):
    rows = []
    for ticker, exs in raw.items():
        filtered = {k: v for k, v in exs.items() if k in active_exs}
        if len(filtered) < 2: continue
        it = list(filtered.items())
        for i in range(len(it)):
            for j in range(i+1, len(it)):
                ex1, d1 = it[i]; ex2, d2 = it[j]
                
                # 0時(無効値)が含まれる場合はスキップ
                if d1['t'] == 0 or d2['t'] == 0: continue
                
                if d1['t'] == d2['t']:
                    low, high = (it[i], it[j]) if d1['rate'] < d2['rate'] else (it[j], it[i])
                    net = high[1]['rate'] - low[1]['rate']
                    diff = abs(d1['p'] - d2['p']) / d2['p'] * 100
                    rows.append({
                        "t": ticker, "ex1": low[0], "r1": low[1]['rate'], "t1": low[1]['t'], "tp1": "L",
                        "ex2": high[0], "r2": high[1]['rate'], "t2": high[1]['t'], "tp2": "S",
                        "df": diff, "n": net - diff, "rk": calculate_risk(d1, d2, levs, t_key)
                    })
    return pd.DataFrame(rows)


# --- [エンジンB] 時間差ヘッジ版（修正: 早期配布優先） ---
def run_hedge_engine(raw, active_exs, levs, t_key):
    rows = []
    now_h = datetime.now().hour
    
    for ticker, exs in raw.items():
        filtered = {k: v for k, v in exs.items() if k in active_exs}
        if len(filtered) < 2: continue
        it = list(filtered.items())
        
        # 重複計算を避けるため、i, jの総当たりではなくペア作成
        for i in range(len(it)): 
            for j in range(i+1, len(it)): 
                
                # ペア候補を取得
                cand_a = it[i] # (ex_name, data)
                cand_b = it[j]
                
                # 0時(無効値)は除外
                if cand_a[1]['t'] == 0 or cand_b[1]['t'] == 0: continue
                # 配布時間が同じ場合は除外
                if int(cand_a[1]['t']) == int(cand_b[1]['t']): continue
                
                # --- どっちが早いか判定 ---
                # 現在時刻からの残り時間を計算 (小さい方が早い)
                diff_a = (cand_a[1]['t'] - now_h) % 24
                diff_b = (cand_b[1]['t'] - now_h) % 24
                
                if diff_a < diff_b:
                    # Aが早い -> Aが拠点(ex1), Bがヘッジ(ex2)
                    ex1, d1 = cand_a
                    ex2, d2 = cand_b
                else:
                    # Bが早い -> Bが拠点(ex1), Aがヘッジ(ex2)
                    ex1, d1 = cand_b
                    ex2, d2 = cand_a
                # -------------------------

                # 拠点側(早い方)の金利を収益源とする
                # 金利がプラスならショート(S)で受け取り、マイナスならロング(L)で受け取り
                p1_type = "S" if d1['rate'] >= 0 else "L"
                # ヘッジ側は逆ポジション
                p2_type = "L" if p1_type == "S" else "S"
                
                net = abs(d1['rate']) # 単純に拠点側の受取金利が利益
                diff = abs(d1['p'] - d2['p']) / d2['p'] * 100
                
                rows.append({
                    "t": ticker, "ex1": ex1, "r1": d1['rate'], "t1": d1['t'], "tp1": p1_type,
                    "ex2": ex2, "r2": d2['rate'], "t2": d2['t'], "tp2": p2_type,
                    "df": diff, "n": net - diff, "rk": calculate_risk(d1, d2, levs, t_key)
                })
    return pd.DataFrame(rows)


# --- サイドバー構成 ---
st.sidebar.header("👔 現場コントロール")
if st.sidebar.button('⚡️ 最新データ更新', use_container_width=True):
    st.cache_data.clear()
    raw, status, ts = fetch_api_snapshot()
    st.session_state.update({'raw': raw, 'api': status, 'update_ts': ts})


mode_ui = st.sidebar.selectbox("📊 プログラム選択", ["同時刻金利版", "時間差ヘッジ"])
tactic_ui = st.sidebar.radio("🔥 戦術判定", ["スキャ", "ヘッジ", "ホールド"])
t_key = "scalp" if "スキャ" in tactic_ui else ("hedge" if "ヘッジ" in tactic_ui else "hold")


st.sidebar.markdown("---")
margin = st.sidebar.number_input("証拠金 (USDT)", 10, 1000000, 100)
st.sidebar.markdown("🕹️ **レバレッジ設定**")
cols = st.sidebar.columns(5)
levs = [cols[i].number_input(str(i+1), 1, 200, [10,20,50,100,125][i], key=f"v341_l{i}") for i in range(5)]
st.sidebar.markdown("---")
st.sidebar.markdown("🏦 **対象取引所**")
sel_m = st.sidebar.checkbox("MEXC", value=True)
sel_bt = st.sidebar.checkbox("Bitget", value=True)
sel_bn = st.sidebar.checkbox("BingX", value=True)
active_exs = [ex for ex, s in zip(["MEXC", "Bitget", "BingX"], [sel_m, sel_bt, sel_bn]) if s]


# --- メインロジック分岐 ---
if 'raw' not in st.session_state:
    raw, status, ts = fetch_api_snapshot()
    st.session_state.update({'raw': raw, 'api': status, 'update_ts': ts})


st.markdown(f"<h2>👔 金利ーマン Dashboard <span class='update-ts'>({st.session_state.update_ts} 更新)</span></h2>", unsafe_allow_html=True)


if len(active_exs) < 2:
    st.warning("取引所を2つ以上選択してください。")
else:
    if mode_ui == "同時刻金利版":
        df = run_simultaneous_engine(st.session_state.raw, active_exs, levs, t_key)
        col1_label, col2_label = "L側 (金利低)", "S側 (金利高)"
    else:
        df = run_hedge_engine(st.session_state.raw, active_exs, levs, t_key)
        col1_label, col2_label = "拠点側 (金利源)", "ヘッジ側 (価格固定用)"


    if df is not None and not df.empty:
        df = df.sort_values("n", ascending=False).drop_duplicates(subset=['t']).head(40)
        h = f"<thead><tr><th>🔥</th><th>銘柄</th><th>{col1_label}</th><th>{col2_label}</th><th>乖離</th><th>実質</th>" + "".join([f"<th>{l}倍</th>" for l in levs]) + "</tr></thead>"
        b = "<tbody>"
        for _, r in df.iterrows():
            l_cells = "".join([f"<td style='color:#94a3b8;font-size:0.8em'>MAX</td>" if r['rk'][i]=="MAX" else f"<td><span class='lev-amount'>${margin*levs[i]*(r['n']/100):.1f}</span><br>{r['rk'][i]}</td>" for i in range(5)])
            b += f"<tr><td></td><td><span class='ticker-text'>{r['t']}</span></td>" \
                 f"<td><span class='ex-label'>{r['ex1']} ({r['tp1']})</span><span class='rate-val'>{r['r1']:.3f}%</span><br><span class='dist-time'>{r['t1']}:00 配布</span></td>" \
                 f"<td><span class='ex-label'>{r['ex2']} ({r['tp2']})</span><span class='rate-val'>{r['r2']:.3f}%</span><br><span class='dist-time'>{r['t2']}:00 配布</span></td>" \
                 f"<td>{r['df']:.3f}%</td><td class='net-profit'>{r['n']:.3f}%</td>{l_cells}</tr>"
        st.markdown(f"<table class='report-table'>{h}{b}</tbody></table>", unsafe_allow_html=True)
    else:
        st.info(f"{mode_ui} のロジックに適合する銘柄が現在ありません。")
