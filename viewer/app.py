import streamlit as st
import core_logic as core

st.set_page_config(page_title="金利ーマン Dashboard", layout="wide")

# デザイン定義
STYLE = """
<style>
    .report-table { width: 100%; border-collapse: collapse; font-family: sans-serif; background: white; text-align: center; }
    .report-table th { background: #f8fafc; padding: 12px; border: 1px solid #e2e8f0; font-size: 13px; color: #64748b; }
    .report-table td { border: 1px solid #e2e8f0; padding: 10px; vertical-align: middle; }
    .ticker { font-weight: 800; font-size: 1.1em; color: #1e293b; }
    .rate-box { font-weight: 800; display: block; font-size: 1.05em; margin: 2px 0; }
    .rate-l { color: #059669; }
    .rate-s { color: #dc2626; }
    .time-sub { color: #94a3b8; font-size: 0.75em; }
    .net-cell { background: #fffbeb; font-weight: 800; color: #b45309; font-size: 1.1em; }
    .lev-val { font-weight: 700; color: #334155; }
    .icon-ok { color: #22c55e; font-size: 1.1em; }
</style>
"""

def main():
    raw, ts, counts = core.fetch_raw_data()
    
    st.sidebar.header("👔 現場コントロール")
    mode = st.sidebar.selectbox("プログラム", ["同時刻金利版", "時間差ヘッジ"])
    margin = st.sidebar.number_input("証拠金 ($)", 10, 1000000, 100)
    active_exs = [ex for ex in ["MEXC", "Bitget", "BingX"] if st.sidebar.checkbox(f"{ex} ({counts.get(ex, 0)})", value=True)]
    levs = [10, 20, 50, 100, 125]

    st.title(f"👔 Dashboard ({ts})")

    rows_html = ""
    for ticker, exs in raw.items():
        v_exs = [e for e in exs.keys() if e in active_exs]
        if len(v_exs) < 2: continue
        
        for i in range(len(v_exs)):
            for j in range(len(v_exs)):
                if i == j: continue
                e1, e2 = v_exs[i], v_exs[j]
                d1, d2 = exs[e1], exs[e2]

                # 型を確実に int にキャストして判定
                t1, t2 = int(d1['t']), int(d2['t'])
                is_same = (t1 == t2)
                if mode == "同時刻金利版" and not is_same: continue
                if mode == "時間差ヘッジ" and is_same: continue

                # 方向と利益計算
                diff_l, diff_s = d2['rate'] - d1['rate'], d1['rate'] - d2['rate']
                net, s1, s2 = (diff_l, "L", "S") if diff_l > diff_s else (diff_s, "S", "L")
                p_diff = abs(d1['p'] - d2['p']) / d2['p'] * 100 if d2['p'] != 0 else 0
                final = net - p_diff
                if final <= 0: continue

                # レバレッジ列
                lev_tds = ""
                for l in levs:
                    if l > d1.get('m', 100) or l > d2.get('m', 100):
                        lev_tds += "<td><span style='color:#cbd5e1'>MAX</span></td>"
                    else:
                        usd = (margin * l * final / 100)
                        lev_tds += f"<td><span class='lev-val'>${usd:.1f}</span><br><span class='icon-ok'>✅</span></td>"

                # 各行を結合
                rows_html += f"""
                <tr>
                    <td>🔥</td>
                    <td><span class='ticker'>{ticker}</span></td>
                    <td>{e1}({s1})<br><span class='rate-box {"rate-l" if s1=="L" else "rate-s"}'>{d1['rate']:.3f}%</span><br><span class='time-sub'>{t1}:00</span></td>
                    <td>{e2}({s2})<br><span class='rate-box {"rate-l" if s2=="L" else "rate-s"}'>{d2['rate']:.3f}%</span><br><span class='time-sub'>{t2}:00</span></td>
                    <td>{p_diff:.3f}%</td>
                    <td class='net-cell'>{final:.4f}%</td>
                    {lev_tds}
                </tr>
                """

    if rows_html:
        header = f"<tr><th>🔥</th><th>銘柄</th><th>拠点側</th><th>ヘッジ側</th><th>乖離</th><th>実質</th>{''.join([f'<th>{l}倍</th>' for l in levs])}</tr>"
        # 全体を一つのHTML文字列として構築
        full_html = f"{STYLE}<table class='report-table'><thead>{header}</thead><tbody>{rows_html}</tbody></table>"
        # 唯一の st.markdown 実行
        st.markdown(full_html, unsafe_allow_html=True)
    else:
        st.warning(f"現在、{mode} の条件を満たすペアが見つかりません。")

if __name__ == "__main__":
    main()