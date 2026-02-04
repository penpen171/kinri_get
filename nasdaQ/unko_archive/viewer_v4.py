import streamlit as st
import pandas as pd
import os
import time

st.set_page_config(page_title="感度3000倍 v4 モニタ", layout="wide")

DETAIL_LOG = "volatility_log_v4.csv"

def load_data():
    if not os.path.exists(DETAIL_LOG): return pd.DataFrame()
    try:
        cols = ["日時", "銘柄", "判定", "実体幅", "過去平均", "価格", "ワープ情報"]
        df = pd.read_csv(DETAIL_LOG, names=cols, header=None, encoding='utf-8-sig')
        # nan対策：数値を強制変換
        df["価格"] = pd.to_numeric(df["価格"], errors='coerce')
        df["実体幅"] = pd.to_numeric(df["実体幅"], errors='coerce')
        return df
    except:
        return pd.DataFrame()

st.title("🏹 感度3000倍：全銘柄・仕込み指令")

df = load_data()

if not df.empty:
    # 各銘柄の最新一行を取得
    latest = df.sort_values("日時").groupby("銘柄").last().reset_index()
    
    # 銘柄カードを横並びに表示
    cols = st.columns(len(latest))
    for i, (_, row) in enumerate(latest.iterrows()):
        with cols[i]:
            title = f"{row['銘柄']} ({row['判定']})"
            # 🚨 指令がある場合は、タイトル部分にも表示
            info = str(row["ワープ情報"]) if pd.notna(row["ワープ情報"]) else ""
            
            if "🚨" in info:
                st.caption(info) # カード上部に指令を表示
                st.metric(label=title, value=f"{row['価格']:.2f}", delta=f"Vol: {row['実体幅']:.4f}", delta_color="inverse")
            else:
                st.metric(label=title, value=f"{row['価格']:.2f}", delta=f"Vol: {row['実体幅']:.4f}")

st.divider()
st.subheader("📋 リアルタイム監視ログ")
st.dataframe(df.iloc[::-1].head(100), use_container_width=True)

time.sleep(5)
st.rerun()