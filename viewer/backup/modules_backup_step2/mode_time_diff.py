# modules/mode_time_diff.py
"""
時間差ヘッジ版モジュール
- 配布時刻が異なる2つの取引所でヘッジ
- 先に配布される側で金利を受け取り、後から価格固定
"""

import streamlit as st
import pandas as pd


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


def fmt_rem(rem_s: int) -> str:
    """残り時間の表示用フォーマット"""
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


def run_hedge_engine(raw, active_exs, levs, t_key):
    """時間差ヘッジ版のエンジン"""
    rows = []

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


def render_time_diff_mode(raw, active_exs, levs, t_key, margin):
    """時間差ヘッジ版の表示"""
    df = run_hedge_engine(raw, active_exs, levs, t_key)
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
        st.info("時間差ヘッジ版のロジックに適合する銘柄が現在ありません。")
