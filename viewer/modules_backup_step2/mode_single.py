# modules/mode_single.py
"""
単体金利版モジュール
- 各取引所ごとに金利の高い銘柄をランキング表示
- 裁定取引ではなく、単純に金利収益を狙う
"""

import streamlit as st


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


def run_single_exchange_engine(raw, active_exs, levs, t_key):
    """単体金利版のエンジン"""
    exchange_data = {ex: [] for ex in active_exs}
    
    for ticker, exs in raw.items():
        for ex_name in active_exs:
            if ex_name in exs:
                d = exs[ex_name]
                rate = d.get('rate', 0)
                abs_rate = abs(rate)
                position = "S" if rate >= 0 else "L"
                
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


def render_single_mode(raw, active_exs, levs, t_key, margin):
    """単体金利版の表示"""
    # 並び順の選択UI
    sort_mode = st.radio(
        "📊 並び順",
        ["金利の高い順", "配布時間の近い順"],
        horizontal=True,
        key="single_sort_mode"
    )
    
    exchange_data = run_single_exchange_engine(raw, active_exs, levs, t_key)
    
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
