import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import os

# --- ページ設定 ---
st.set_page_config(page_title="金利ーマン Dashboard v5.2.0", layout="wide")

# --- CSS (実戦視認性) ---
st.markdown("""
<style>
    .report-table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 5px; }
    .report-table th { background-color: #f1f5f9; padding: 6px 2px; font-size: 11px; border: 1px solid #cbd5e1; text-align: center; color: #475569; }
    .report-table td { border: 1px solid #cbd5e1; padding: 6px 2px; text-align: center; vertical-align: middle; line-height: 1.3; }
    .ticker-text { font-weight: 800; font-size: 1.1em; color: #1e293b; }
    .dist-time { font-size: 0.85em; color: #1e293b; background: #e2e8f0; padding: 2px 5px; border-radius: 4px; margin-top: 3px; display: inline-block; font-weight: 900; }
    .ex-label { font-size: 0.75em; font-weight: bold; color: #475569; display: block; margin-bottom: 1px; }
    .rate-val-l { font-size: 1.15em; font-weight: 800; color: #059669; }
    .rate-val-s { font-size: 1.15em; font-weight: 800; color: #dc2626; }
    .lev-amount { font-size: 1.25em; font-weight: 900; color: #000; display: block; letter-spacing: -1px; }
</style>
""", unsafe_allow_html=True)

# --- カタログ読み込み ---
def load_cycle_master():
    target_file = "bitget_true_catalog_0131_0704.csv"
    if os.path.exists(target_file):
        try:
            df = pd.read_csv(target_file)
            return dict(zip(df['Symbol'], df['Interval']))
        except: pass
    return {}

@st.cache_data(ttl=60)
def fetch_raw_data():
    data = {}; ua = "Mozilla/5.0"; now_h = datetime.now().hour
    counts = {"MEXC": 0, "Bitget": 0, "BingX": 0}
    cycle_master = load_cycle_master()
    cycle_scheds = {'1h': list(range(24)), '4h': [1, 5, 9, 13, 17, 21], '8h': [1, 9, 17]}

    def get_info(ticker):
        interval = cycle_master.get(f"{ticker}-USDT", "4h")
        sched = cycle_scheds.get(interval, [1, 5, 9, 13, 17, 21])
        nx = next((h for h in sched if h > now_h), sched[0])
        return nx, (nx - now_h) % 24

    try:
        # MEXC (安定版の金利補正)
        r = requests.get("https://api.mexc.com/api/v1/contract/ticker", headers={"User-Agent": ua}, timeout=5).json()
        if r.get('success'):
            for i in r['data']:
                sym = i['symbol'].split('_')[0]
                nx, wt = get_info(sym)
                raw = float(i.get('lastFundingRate') or i.get('fundingRate', 0))
                # 安定版: 0.1%未満の生データは小数表記とみなして100倍
                rate = raw * 100 if abs(raw) < 0.1 else raw
                data.setdefault(sym, {})['MEXC'] = {'rate': rate, 'p': float(i['lastPrice']), 'v': abs(float(i['riseFallRate'])) * 100, 'm': 50, 't': nx, 'w': wt}
                counts["MEXC"] += 1
        
        # Bitget
        bg_r = requests.get("https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures", timeout=5).json()
        if bg_r.get('code') == '00000':
            for i in bg_r['data']:
                sym = i['symbol'].replace('USDT','')
                nx, wt = get_info(sym)
                rate = float(i['fundingRate']) * 100
                data.setdefault(sym, {})['Bitget'] = {'rate': rate, 'p': float(i['lastPr']), 'v': abs(float(i.get('priceChangePercent', 0))) * 100, 'm': 50, 't': nx, 'w': wt}
                counts["Bitget"] += 1
        
        # BingX
        bx_r = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex", timeout=5).json()
        if bx_r.get('data'):
            for i in bx_r['data']:
                sym = i['symbol'].split('-')[0]
                nx, wt = get_info(sym)
                rate = float(i['lastFundingRate']) * 100
                data.setdefault(sym, {})['BingX'] = {'rate': rate, 'p': float(i['markPrice']), 'v': 0.5, 'm': 20, 't': nx, 'w': wt}
                counts["BingX"] += 1
    except: pass
    return data, datetime.now().strftime("%H:%M:%S"), counts

def run_arb_logic(raw, mode_ui, active_exs, levs):
    rows = []
    for ticker, exs in raw.items():
        ex_list = list(exs.keys())
        if len(ex_list) < 2: continue
        
        for i in range(len(ex_list)):
            for j in range(len(ex_list)):
                if i == j: continue
                e1, e2 = ex_list[i], ex_list[j]
                
                # ここがポイント: フィルター判定を表示用に行うが、計算は常に可能
                if e1 not in active_exs or e2 not in active_exs: continue
                
                d1, d2 = exs[e1], exs[e2]
                if mode_ui == "同時刻金利版" and d1['t'] != d2['t']: continue
                if mode_ui == "時間差ヘッジ" and d1['t'] == d2['t']: continue

                net = (d2['rate'] - d1['rate']) if mode_ui == "同時刻金利版" else abs(d1['rate'])
                price_diff = abs(d1['p'] - d2['p']) / d2['p'] * 100 if d2['p'] != 0 else 0
                
                risk_res = {k: [('❌' if (((d1['v']+d2['v'])/2)/(100/l)) > cfg['d'] else ('⚠️' if (((d1['v']+d2['v'])/2)/(100/l)) > cfg['w'] else '✅')) if l <= d1['m'] and l <= d2['m'] else "MAX" for l in levs] for k, cfg in {"scalp":{"w":0.9,"d":1.2},"hedge":{"w":0.4,"d":0.7},"hold":{"w":0.2,"d":0.4}}.items()}

                rows.append({
                    "ticker": ticker,
                    "t_html": f"<span class='ticker-text'>{ticker}</span><br><span class='dist-time'>{d1['t']}:00 / {d2['t']}:00</span>",
                    "ex1_html": f"<span class='ex-label'>{e1}</span><span class='rate-val-l'>{d1['rate']:.4f}%</span>",
                    "ex2_html": f"<span class='ex-label'>{e2}</span><span class='rate-val-s'>{d2['rate']:.4f}%</span>",
                    "n": net - price_diff,
                    "rk": risk_res
                })
    return pd.DataFrame(rows).sort_values("n", ascending=False).drop_duplicates(subset=['ticker']).head(40) if rows else pd.DataFrame()

# --- メイン UI ---
raw_data, ts, counts = fetch_raw_data()
st.sidebar.header("👔 現場コントロール")
mode_ui = st.sidebar.selectbox("📊 モード", ["単独金利版", "同時刻金利版", "時間差ヘッジ"])
tactic_ui = st.sidebar.radio("🔥 戦術", ["超短期スキャ", "短期ヘッジ", "中期ホールド"])
t_key = "scalp" if "スキャ" in tactic_ui else ("hedge" if "ヘッジ" in tactic_ui else "hold")
margin = st.sidebar.number_input("証拠金", 10, 1000000, 100)
levs = [st.sidebar.number_input(f"S{i+1}", 1, 200, v) for i, v in enumerate([10, 20, 50, 100, 125])]

st.sidebar.markdown("---")
active_exs = [ex for ex in ["MEXC", "Bitget", "BingX"] if st.sidebar.checkbox(f"{ex} ({counts[ex]})", value=True)]

st.markdown(f"<h2>👔 金利ーマン v5.2.0 <span style='font-size:0.5em;color:#94a3b8;'>({ts})</span></h2>", unsafe_allow_html=True)

if mode_ui == "単独金利版":
    tabs = st.tabs(["MEXC", "Bitget", "BingX"])
    for i, ex in enumerate(["MEXC", "Bitget", "BingX"]):
        with tabs[i]:
            res = []
            items = sorted([(t, exs[ex]) for t, exs in raw_data.items() if ex in exs], key=lambda x: abs(x[1]['rate']), reverse=True)[:40]
            for ticker, d in items:
                side = "S" if d['rate'] > 0 else "L"; color = "rate-val-s" if side=="S" else "rate-val-l"
                risk_res = {k: [('❌' if (d['v']/(100/l)) > cfg['d'] else ('⚠️' if (d['v']/(100/l)) > cfg['w'] else '✅')) if l <= d['m'] else "MAX" for l in levs] for k, cfg in {"scalp":{"w":0.9,"d":1.2},"hedge":{"w":0.4,"d":0.7},"hold":{"w":0.2,"d":0.4}}.items()}
                res.append({"t_html": f"<span class='ticker-text'>{ticker}</span><br><span class='dist-time'>{d['t']}:00</span>", "ex1_html": f"<span class='ex-label'>Side</span><span class='{color}'>{side}</span>", "ex2_html": f"<span class='{color}'>{d['rate']:.4f}%</span>", "n": abs(d['rate']), "rk": risk_res})
            
            if res:
                h = f"<thead><tr><th>🔥</th><th>銘柄 / 配布時間</th><th>Side</th><th>1回金利</th>" + "".join([f"<th>{l}倍</th>" for l in levs]) + "</tr></thead>"
                b = "".join([f"<tr><td>🔥</td><td>{r['t_html']}</td><td>{r['ex1_html']}</td><td>{r['ex2_html']}</td>" + "".join([f"<td><span class='lev-amount'>${margin*levs[idx]*(r['n']/100):.2f}</span></td>" for idx in range(len(levs))]) + "</tr>" for r in res])
                st.markdown(f"<table class='report-table'>{h}<tbody>{b}</tbody></table>", unsafe_allow_html=True)
else:
    df_res = run_arb_logic(raw_data, mode_ui, active_exs, levs)
    if not df_res.empty:
        h = f"<thead><tr><th>🔥</th><th>銘柄 / 配布時間</th><th>拠点</th><th>ヘッジ</th><th>差分</th>" + "".join([f"<th>{l}倍</th>" for l in levs]) + "</tr></thead>"
        b = ""
        for _, r in df_res.iterrows():
            b += f"<tr><td>🔥</td><td>{r['t_html']}</td><td>{r['ex1_html']}</td><td>{r['ex2_html']}</td><td>{r['n']:.4f}%</td>" + "".join([f"<td><span class='lev-amount'>${margin*levs[idx]*(r['n']/100):.2f}</span></td>" for idx in range(len(levs))]) + "</tr>"
        st.markdown(f"<table class='report-table'>{h}<tbody>{b}</tbody></table>", unsafe_allow_html=True)
    else:
        st.info("条件に合うペアが見つかりません。サイドバーの取引所選択を確認してください。")