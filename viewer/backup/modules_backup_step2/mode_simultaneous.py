# modules/mode_simultaneous.py
"""
同時刻金利版モジュール
- 2つの取引所で同じ時刻に配布される銘柄を探す
- 金利差を利用した裁定取引
"""

import streamlit as st
import pandas as pd
from modules.data_api import interval_to_seconds


def calculate_risk(d1, d2, levs, t_key):
    """リスク判定（戦術別）"""
    risk_configs = {
        "scalp": {"w": 0.5, "d": 0.9},
        "hedge": {"w": 0.4, "d": 0.7},
        "hold": {"w": 0.3, "d": 0.6}
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


def run_simultaneous_engine(raw, active_exs, levs, t_key):
    """同時刻金利版のエンジン"""
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


def render_simultaneous_mode(raw, active_exs, levs, t_key, margin):
    """同時刻金利版の表示"""
    df = run_simultaneous_engine(raw, active_exs, levs, t_key)
    col1_label, col2_label = "L側 (金利低)", "S側 (金利高)"
    
    if df is not None and not df.empty:
        df = df.sort_values("n", ascending=False).drop_duplicates(subset=['t'])
        
        # サイクル周期で分類（デバッグ版）
        df_1h = []
        df_4h = []
        df_8h = []
        
        # デバッグ用：1時間タブに入る銘柄の詳細を確認
        debug_1h_details = []
        
        for _, r in df.iterrows():
            ticker = r['t']
            ex1 = r['ex1']
            ex2 = r['ex2']
            
            # 両側のinterval_sを取得
            interval_s1 = 0
            interval_s2 = 0
            
            if ticker in raw and ex1 in raw[ticker]:
                interval_s1 = raw[ticker][ex1].get('interval_s', 0)
            
            if ticker in raw and ex2 in raw[ticker]:
                interval_s2 = raw[ticker][ex2].get('interval_s', 0)
            
            # デバッグ情報を記録
            if interval_s1 == 3600 or interval_s2 == 3600:
                debug_1h_details.append(
                    f"{ticker}: {ex1}={interval_s1}秒, {ex2}={interval_s2}秒"
                )
            
            if interval_s1 == 3600 and interval_s2 == 3600:
                df_1h.append(r)
            elif interval_s1 == 14400 and interval_s2 == 14400:
                df_4h.append(r)
            elif interval_s1 == 28800 and interval_s2 == 28800:
                df_8h.append(r)

        
        # デバッグ情報を表示
        with st.expander("🐛 デバッグ：1時間サイクル判定詳細"):
            st.write(f"1時間サイクルとして検出された銘柄: {len(debug_1h_details)}件")
            for detail in debug_1h_details[:20]:
                st.write(detail)

        
        # 各カテゴリで上位10件
        df_1h_top10 = df_1h[:10]
        df_4h_top10 = df_4h[:10]
        df_8h_top10 = df_8h[:10]
        df_all_top40 = df.head(40).to_dict('records')
        
        # タブ作成
        tab_all, tab_1h, tab_4h, tab_8h = st.tabs([
            f"🔥 全て ({len(df_all_top40)})", 
            f"⚡ 1時間毎 ({len(df_1h_top10)})", 
            f"⏰ 4時間毎 ({len(df_4h_top10)})", 
            f"🕐 8時間毎 ({len(df_8h_top10)})"
        ])
        
        # テーブル描画関数
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
        st.info("同時刻金利版のロジックに適合する銘柄が現在ありません。")
