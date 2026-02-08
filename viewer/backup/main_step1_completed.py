import streamlit as st
import pandas as pd
import requests
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from modules.data_api import (
    fetch_api_snapshot,
    interval_to_seconds,
    interval_to_sched_hours,
    calc_next_settle_epoch_from_sched,
    normalize_time
)


# --- ページ基本設定 ---
st.set_page_config(page_title="金利ーマン Dashboard v3.7.0", layout="wide")


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


# --- [表示用] remaining_s -> "あとxx分xx秒" ---
def fmt_rem(rem_s: int) -> str:
    try:
        rem_s = int(rem_s)
    except:
        return "不明"
    if rem_s <= 0: return "不明"
    m, s = divmod(rem_s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"あと{h}時間{m}分{s}秒"
    return f"あと{m}分{s}秒"


# --- [共通モジュール] リスク判定 ---
def calculate_risk(d1, d2, levs, t_key):
    # 戦術別リスク基準（金利時刻またぎボラ＆持続的変動を考慮）
    risk_configs = {
        "scalp": {"w": 0.5, "d": 0.9},    # スキャ：金利時刻ボラスパイクに直撃→厳しめ
        "hedge": {"w": 0.4, "d": 0.7},    # ヘッジ：中程度
        "hold": {"w": 0.3, "d": 0.6}      # ホールド：持続的変動に弱い、金利時刻ボラには強い→やや緩め
    }
    cfg = risk_configs[t_key]
    res = []
    for l in levs:
        if l > d1['m'] or l > d2['m']: 
            res.append("MAX")
        else:
            vol = ((d1['v'] + d2['v']) / 2) / (100 / l)
            res.append('❌' if vol > cfg['d'] else ('⚠️' if vol > cfg['w'] else '✅'))
    return res



# --- [エンジンA] 同時刻金利版 ---
def run_simultaneous_engine(raw, active_exs, levs, t_key):
    rows = []
    for ticker, exs in raw.items():
        filtered = {k: v for k, v in exs.items() if k in active_exs}
        if len(filtered) < 2: continue
        it = list(filtered.items())
        for i in range(len(it)):
            for j in range(i + 1, len(it)):
                ex1, d1 = it[i]; ex2, d2 = it[j]
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


# --- [エンジンB] 時間差ヘッジ版 ---
def run_hedge_engine(raw, active_exs, levs, t_key):
    rows = []
    overlap_tol_s = 30

    for ticker, exs in raw.items():
        filtered = {k: v for k, v in exs.items() if k in active_exs}
        if len(filtered) < 2: continue
        it = list(filtered.items())

        for i in range(len(it)):
            for j in range(i + 1, len(it)):
                cand_a = it[i]; cand_b = it[j]
                dA = cand_a[1]; dB = cand_b[1]

                if ('remaining_s' not in dA) or ('remaining_s' not in dB): continue
                if dA['remaining_s'] <= 0 or dB['remaining_s'] <= 0: continue
                
                cycle_same = (int(dA.get("interval_s", 0)) == int(dB.get("interval_s", 0)))
                diff_s = abs(int(dA['remaining_s']) - int(dB['remaining_s']))
                
                if cycle_same and diff_s <= 120: continue
                if not cycle_same and diff_s <= 30: continue

                if dA['remaining_s'] < dB['remaining_s']:
                    ex1, d1 = cand_a; ex2, d2 = cand_b
                else:
                    ex1, d1 = cand_b; ex2, d2 = cand_a

                p1_type = "S" if d1['rate'] >= 0 else "L"
                p2_type = "L" if p1_type == "S" else "S"
                net = abs(d1['rate'])
                diff = abs(d1['p'] - d2['p']) / d2['p'] * 100 if d2['p']!=0 else 0

                rows.append({
                    "t": ticker,
                    "ex1": ex1, "r1": d1['rate'], "t1": d1.get('t', 0), "tp1": p1_type, "rem1": int(d1.get("remaining_s", 0)),
                    "ex2": ex2, "r2": d2['rate'], "t2": d2.get('t', 0), "tp2": p2_type, "rem2": int(d2.get("remaining_s", 0)),
                    "df": diff, "n": net - diff, "rk": calculate_risk(d1, d2, levs, t_key)
                })
    return pd.DataFrame(rows)


# --- [エンジンC] 単体金利版（各取引所ごとのランキング表示） ---
def run_single_exchange_engine(raw, active_exs, levs, t_key):
    """各取引所ごとに金利の高い順にランキング表示"""
    exchange_data = {ex: [] for ex in active_exs}
    
    for ticker, exs in raw.items():
        for ex_name in active_exs:
            if ex_name in exs:
                d = exs[ex_name]
                rate = d.get('rate', 0)
                
                # 金利の絶対値でランキング（正負問わず大きい方が有利）
                abs_rate = abs(rate)
                
                # ポジション方向（金利がプラスならショート、マイナスならロング）
                position = "S" if rate >= 0 else "L"
                
                # 単体取引なのでリスクは当該取引所のボラティリティのみ
                vol = d.get('v', 0)
                risk_cfg = {"scalp": 0.9, "hedge": 0.7, "hold": 0.6}[t_key]
                
                risks = []
                for lev in levs:
                    if lev > d.get('m', 0):
                        risks.append("MAX")
                    else:
                        vol_adjusted = vol / (100 / lev)
                        risks.append('❌' if vol_adjusted > risk_cfg else ('⚠️' if vol_adjusted > risk_cfg * 0.5 else '✅'))
                
                exchange_data[ex_name].append({
                    "ticker": ticker,
                    "rate": rate,
                    "abs_rate": abs_rate,
                    "position": position,
                    "price": d.get('p', 0),
                    "volatility": vol,
                    "max_lev": d.get('m', 0),
                    "time": d.get('t', 0),
                    "remaining_s": d.get('remaining_s', 0),
                    "risks": risks
                })
    
    # 各取引所ごとに金利の絶対値でソート（デフォルト）
    for ex_name in exchange_data:
        exchange_data[ex_name] = sorted(exchange_data[ex_name], key=lambda x: x['abs_rate'], reverse=True)
    
    return exchange_data


# --- サイドバー構成 ---
st.sidebar.header("👔 現場コントロール")
if st.sidebar.button('⚡️ 最新データ更新', use_container_width=True):
    st.cache_data.clear()
    raw, status, ts = fetch_api_snapshot()
    st.session_state.update({'raw': raw, 'api': status, 'update_ts': ts})

mode_ui = st.sidebar.selectbox("📊 プログラム選択", ["同時刻金利版", "時間差ヘッジ版", "単体金利版"])

st.sidebar.markdown("---")
tactic_ui = st.sidebar.radio("🔥 戦術判定", ["スキャ", "ヘッジ", "ホールド"])
t_key = "scalp" if "スキャ" in tactic_ui else ("hedge" if "ヘッジ" in tactic_ui else "hold")

# 戦術の説明（折りたたみ式）
tactic_descriptions = {
    "スキャ": """
**📌 スキャ（短期）**
- **保有時間**: 数分（直前イン、直後アウト）
- **リスク**: 金利配布時刻をまたぐ瞬間のボラティリティスパイクに直撃
- **向き**: 素早い判断と実行ができる人向け
    """,
    "ヘッジ": """
**📌 ヘッジ（中期）**
- **保有時間**: 30分〜1時間
- **リスク**: 金利時刻またぎボラ + 持続的な価格変動の両方
- **向き**: バランス重視、ある程度余裕を持ちたい人向け
    """,
    "ホールド": """
**📌 ホールド（長期）**
- **保有時間**: 3時間程度
- **リスク**: 持続的な価格変動に弱い（金利時刻ボラには強い）
- **向き**: じっくり保持、金利差ヘッジ向け
    """
}

with st.sidebar.expander("ℹ️ 戦術の説明を見る"):
    st.markdown(tactic_descriptions[tactic_ui])

st.sidebar.markdown("---")
margin = st.sidebar.number_input("証拠金 (USDT)", 10, 1000000, 100)
st.sidebar.markdown("🕹️ **レバレッジ設定**")
cols = st.sidebar.columns(5)
levs = [cols[i].number_input(str(i+1), 1, 200, [10, 20, 50, 100, 125][i], key=f"v370_l{i}") for i in range(5)]
st.sidebar.markdown("---")
st.sidebar.markdown("🏦 **対象取引所**")
sel_bn = st.sidebar.checkbox("BingX", value=True)
sel_m = st.sidebar.checkbox("MEXC", value=True)
sel_bt = st.sidebar.checkbox("Bitget", value=True)
sel_vr = st.sidebar.checkbox("Variational", value=True)
active_exs = [ex for ex, s in zip(["BingX", "MEXC", "Bitget", "Variational"], [sel_bn, sel_m, sel_bt, sel_vr]) if s]



# --- メインロジック ---
if 'raw' not in st.session_state:
    raw, status, ts = fetch_api_snapshot()
    st.session_state.update({'raw': raw, 'api': status, 'update_ts': ts})

st.markdown(f"<h2>👔 金利ーマン Dashboard <span class='update-ts'>({st.session_state.update_ts} 更新)</span></h2>", unsafe_allow_html=True)

if len(active_exs) < 2 and mode_ui != "単体金利版":
    st.warning("取引所を2つ以上選択してください。")
elif len(active_exs) < 1 and mode_ui == "単体金利版":
    st.warning("取引所を1つ以上選択してください。")
else:
    if mode_ui == "同時刻金利版":
        df = run_simultaneous_engine(st.session_state.raw, active_exs, levs, t_key)
        col1_label, col2_label = "L側 (金利低)", "S側 (金利高)"
        
        if df is not None and not df.empty:
            df = df.sort_values("n", ascending=False).drop_duplicates(subset=['t'])
            
            # サイクル周期で分類（拠点側のinterval_sで判定）
            df_1h = []
            df_4h = []
            df_8h = []
            
            # デバッグ用：各銘柄の interval_s を確認
            debug_info = []
            
            for _, r in df.iterrows():
                ticker = r['t']
                ex1 = r['ex1']
                # 拠点側のinterval_sを取得
                if ticker in st.session_state.raw and ex1 in st.session_state.raw[ticker]:
                    interval_s = st.session_state.raw[ticker][ex1].get('interval_s', 0)
                    
                    # デバッグ情報を記録
                    debug_info.append(f"{ticker} ({ex1}): {interval_s}秒")
                    
                    if interval_s == 3600:
                        df_1h.append(r)
                    elif interval_s == 14400:
                        df_4h.append(r)
                    elif interval_s == 28800:
                        df_8h.append(r)
                    else:
                        df_8h.append(r)  # デフォルトは8hタブに
            
            # デバッグ情報を表示
            with st.expander("🐛 デバッグ情報（interval_s確認）"):
                st.write(f"全体: {len(df)}件")
                st.write(f"1時間毎: {len(df_1h)}件")
                st.write(f"4時間毎: {len(df_4h)}件")
                st.write(f"8時間毎: {len(df_8h)}件")
                st.write("---")
                for info in debug_info[:20]:  # 最初の20件を表示
                    st.write(info)

            
            # 各カテゴリで上位10を取得
            df_1h_top10 = df_1h[:10]
            df_4h_top10 = df_4h[:10]
            df_8h_top10 = df_8h[:10]
            
            # 全てタブは全体の上位40
            df_all_top40 = df.head(40).to_dict('records')
            
            # タブ作成
            tab_all, tab_1h, tab_4h, tab_8h = st.tabs([
                f"🔥 全て ({len(df_all_top40)})", 
                f"⚡ 1時間毎 ({len(df_1h_top10)})", 
                f"⏰ 4時間毎 ({len(df_4h_top10)})", 
                f"🕐 8時間毎 ({len(df_8h_top10)})"
            ])
            
            # 各タブに表示
            def render_table(rows, label1, label2):
                if len(rows) == 0:
                    st.info("該当する銘柄がありません")
                    return
                    
                h = f"<thead><tr><th>🔥</th><th>銘柄</th><th>{label1}</th><th>{label2}</th><th>乖離</th><th>実質</th>" + "".join([f"<th>{l}倍</th>" for l in levs]) + "</tr></thead>"
                b = "<tbody>"
                for r in rows:
                    l_cells = "".join(
                        [f"<td style='color:#94a3b8;font-size:0.8em'>MAX</td>" if r['rk'][i] == "MAX"
                         else f"<td><span class='lev-amount'>${margin * levs[i] * (r['n'] / 100):.1f}</span><br>{r['rk'][i]}</td>"
                         for i in range(5)]
                    )
                    t1_str = f"{int(r['t1'])}:00 配布"
                    t2_str = f"{int(r['t2'])}:00 配布"
                    
                    b += f"<tr><td></td><td><span class='ticker-text'>{r['t']}</span></td>" \
                         f"<td><span class='ex-label'>{r['ex1']} ({r['tp1']})</span><span class='rate-val'>{r['r1']:.3f}%</span><br><span class='dist-time'>{t1_str}</span></td>" \
                         f"<td><span class='ex-label'>{r['ex2']} ({r['tp2']})</span><span class='rate-val'>{r['r2']:.3f}%</span><br><span class='dist-time'>{t2_str}</span></td>" \
                         f"<td>{r['df']:.3f}%</td><td class='net-profit'>{r['n']:.3f}%</td>{l_cells}</tr>"
                st.markdown(f"<table class='report-table'>{h}{b}</tbody></table>", unsafe_allow_html=True)
            
            with tab_all:
                render_table(df_all_top40, col1_label, col2_label)
            
            with tab_1h:
                render_table(df_1h_top10, col1_label, col2_label)
            
            with tab_4h:
                render_table(df_4h_top10, col1_label, col2_label)
            
            with tab_8h:
                render_table(df_8h_top10, col1_label, col2_label)
        else:
            st.info(f"{mode_ui} のロジックに適合する銘柄が現在ありません。")
    
    elif mode_ui == "時間差ヘッジ版":
        df = run_hedge_engine(st.session_state.raw, active_exs, levs, t_key)
        col1_label, col2_label = "拠点側 (金利源)", "ヘッジ側 (価格固定用)"
        
        if df is not None and not df.empty:
            df = df.sort_values("n", ascending=False).drop_duplicates(subset=['t']).head(40)
            
            h = f"<thead><tr><th>🔥</th><th>銘柄</th><th>{col1_label}</th><th>{col2_label}</th><th>価格乖離</th><th>実質</th>" + "".join([f"<th>{l}倍</th>" for l in levs]) + "</tr></thead>"
            b = "<tbody>"
            for _, r in df.iterrows():
                l_cells = "".join(
                    [f"<td style='color:#94a3b8;font-size:0.8em'>MAX</td>" if r['rk'][i] == "MAX"
                     else f"<td><span class='lev-amount'>${margin * levs[i] * (r['n'] / 100):.1f}</span><br>{r['rk'][i]}</td>"
                     for i in range(5)]
                )
                t1_str = fmt_rem(int(r.get("rem1", 0)))
                t2_str = fmt_rem(int(r.get("rem2", 0)))
                
                b += f"<tr><td></td><td><span class='ticker-text'>{r['t']}</span></td>" \
                     f"<td><span class='ex-label'>{r['ex1']} ({r['tp1']})</span><span class='rate-val'>{r['r1']:.3f}%</span><br><span class='dist-time'>{t1_str}</span></td>" \
                     f"<td><span class='ex-label'>{r['ex2']} ({r['tp2']})</span><span class='rate-val'>{r['r2']:.3f}%</span><br><span class='dist-time'>{t2_str}</span></td>" \
                     f"<td>{r['df']:.3f}%</td><td class='net-profit'>{r['n']:.3f}%</td>{l_cells}</tr>"
            st.markdown(f"<table class='report-table'>{h}{b}</tbody></table>", unsafe_allow_html=True)
        else:
            st.info(f"{mode_ui} のロジックに適合する銘柄が現在ありません。")
    
    else:  # 単体金利版（新規追加）
        # 並び順の選択UI
        sort_mode = st.radio(
            "📊 並び順",
            ["金利の高い順", "配布時間の近い順"],
            horizontal=True,
            key="single_sort_mode"
        )
        
        exchange_data = run_single_exchange_engine(st.session_state.raw, active_exs, levs, t_key)
        
        # タブで各取引所を表示
        tabs = st.tabs([f"🏦 {ex}" for ex in active_exs])
        
        for idx, ex_name in enumerate(active_exs):
            with tabs[idx]:
                rows = exchange_data[ex_name]
                
                # ソート処理
                if sort_mode == "金利の高い順":
                    rows = sorted(rows, key=lambda x: x['abs_rate'], reverse=True)
                else:  # 配布時間の近い順
                    rows = sorted(rows, key=lambda x: x.get('remaining_s', 999999))
                
                rows = rows[:40]  # 上位40件
                
                if len(rows) == 0:
                    st.info(f"{ex_name} に該当する銘柄がありません")
                    continue
                
                # テーブルヘッダー
                h = f"<thead><tr><th>順位</th><th>銘柄</th><th>金利率</th><th>方向</th><th>配布時刻</th>" + "".join([f"<th>{l}倍</th>" for l in levs]) + "</tr></thead>"
                b = "<tbody>"
                
                for rank, r in enumerate(rows, 1):
                    # レバレッジごとの利益とリスク
                    l_cells = "".join(
                        [f"<td style='color:#94a3b8;font-size:0.8em'>MAX</td>" if r['risks'][i] == "MAX"
                         else f"<td><span class='lev-amount'>${margin * levs[i] * (r['abs_rate'] / 100):.1f}</span><br>{r['risks'][i]}</td>"
                         for i in range(5)]
                    )
                    
                    # 配布時刻の表示（色分け強化）
                    rem_s = r.get('remaining_s', 0)
                    if rem_s > 0:
                        time_str = fmt_rem(rem_s)
                        if rem_s <= 1800:  # 30分以内：⚡赤背景
                            time_display = f"<span style='background:#fee2e2;color:#dc2626;padding:3px 8px;border-radius:4px;font-weight:700;font-size:0.9em'>⚡{time_str}</span>"
                        elif rem_s <= 3600:  # 1時間以内：⏰黄背景
                            time_display = f"<span style='background:#fef3c7;color:#d97706;padding:3px 8px;border-radius:4px;font-weight:700;font-size:0.9em'>⏰{time_str}</span>"
                        else:
                            time_display = f"<span class='dist-time'>{time_str}</span>"
                    elif r['time'] > 0:
                        time_display = f"<span class='dist-time'>{int(r['time'])}:00 配布</span>"
                    else:
                        time_display = "<span class='dist-time'>不明</span>"
                    
                    # 金利率の色分け（プラスは赤、マイナスは青）
                    rate_color = "#dc2626" if r['rate'] >= 0 else "#2563eb"
                    
                    b += f"<tr><td><strong>{rank}</strong></td>" \
                         f"<td><span class='ticker-text'>{r['ticker']}</span></td>" \
                         f"<td><span class='rate-val' style='color:{rate_color}'>{r['rate']:.3f}%</span></td>" \
                         f"<td><span style='font-weight:700;font-size:1.2em'>{r['position']}</span></td>" \
                         f"<td>{time_display}</td>" \
                         f"{l_cells}</tr>"
                
                b += "</tbody>"
                st.markdown(f"<table class='report-table'>{h}{b}</table>", unsafe_allow_html=True)
