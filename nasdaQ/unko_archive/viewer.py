import streamlit as st
import pandas as pd
import os
import time
import json
from datetime import datetime

st.set_page_config(page_title="感度3000倍 v3.2・司令塔", layout="wide")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
DETAIL_LOG = os.path.join(PARENT_DIR, "volatility_log.csv")
EVENT_LOG = os.path.join(PARENT_DIR, "distortion_events.csv")
STATUS_JSON = os.path.join(PARENT_DIR, "current_status.json")

def load_json_status():
    if os.path.exists(STATUS_JSON):
        try:
            with open(STATUS_JSON, "r") as f: return json.load(f)
        except: return {}
    return {}

def load_detail_data():
    if not os.path.exists(DETAIL_LOG): return pd.DataFrame()
    cols = ["日時", "銘柄", "判定", "実体幅", "直前幅", "価格"]
    df = pd.read_csv(DETAIL_LOG, names=cols, header=0, engine='python', on_bad_lines='skip')
    df["日時"] = pd.to_datetime(df["日時"], errors='coerce')
    return df.dropna(subset=["日時"]).sort_values("日時", ascending=False)

def load_event_data():
    if not os.path.exists(EVENT_LOG): return pd.DataFrame()
    return pd.read_csv(EVENT_LOG, engine='python').sort_index(ascending=False)

with st.sidebar:
    st.header("💥 歪み・イベント解析")
    st.subheader("⚠️ 現在発生中の停止中") # 「沈黙中」から変更
    current_stagnant = load_json_status()
    if current_stagnant:
        for name, info in current_stagnant.items():
            st.error(f"**{name}** 停止中\n\n経過: **{info['duration']:.1f} 分**")
    else:
        st.success("現在、顕著な歪みなし")
    st.divider()
    df_ev = load_event_data()
    if not df_ev.empty:
        st.subheader("最新の解除履歴 (結果)")
        st.dataframe(df_ev[['銘柄', '継続分', '方向', '変動幅']].head(10), hide_index=True)
    st.caption(f"最終同期: {datetime.now().strftime('%H:%M:%S')}")

st.title("📋 歪み検知ログ (正常スキップ)")
df_dt = load_detail_data()
if not df_dt.empty:
    # --- 【重要】「解除」が含まれる行も表示対象に追加 ---
    df_dist = df_dt[df_dt["判定"].str.contains("停止|継続|予兆|解除", na=False)]
    
    unique_symbols = sorted(df_dt["銘柄"].unique().tolist())
    tabs = st.tabs(["🌐 すべての歪み"] + unique_symbols)
    
    def color_status(val):
        if '解除' in val: return 'background-color: #00ff7f; color: black; font-weight: bold;'
        if val == '停止': return 'background-color: #ff4b4b; color: white; font-weight: bold;'
        if val == '継続': return 'background-color: #1c83e1; color: white;'
        if val == '予兆': return 'background-color: #fca503; color: black;'
        return ''

    for i, tab in enumerate(tabs):
        with tab:
            data = df_dist if i == 0 else df_dist[df_dist["銘柄"] == unique_symbols[i-1]]
            if not data.empty:
                st.dataframe(data.style.applymap(color_status, subset=['判定']), use_container_width=True, height=700)
            else:
                st.info("現在、歪みログはありません。")

time.sleep(10)
st.rerun()