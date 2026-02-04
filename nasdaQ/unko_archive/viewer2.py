import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime

# ==========================================
# 1. ページ基本設定
# ==========================================
st.set_page_config(page_title="感度3000倍・統合解析モニタ", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 0rem; }
        h1 { margin-top: -1rem; margin-bottom: 0rem; font-size: 1.5rem; }
        .stTabs { margin-top: -0.5rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏹 歪み・統合解析ダッシュボード")

# --- パス設定 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
# 1分ごとの詳細ログ
DETAIL_LOG = os.path.join(PARENT_DIR, "volatility_log.csv")
# 解除イベントのログ
EVENT_LOG = os.path.join(PARENT_DIR, "distortion_events.csv")

# ==========================================
# 2. データ読み込み関数
# ==========================================
def load_detail_data():
    if not os.path.isfile(DETAIL_LOG): return pd.DataFrame()
    try:
        # 6列形式で読み込み
        cols = ["日時", "銘柄", "判定", "実体幅", "直前幅", "価格"]
        df = pd.read_csv(DETAIL_LOG, names=cols, header=0, engine='python', on_bad_lines='skip')
        df["日時"] = pd.to_datetime(df["日時"], errors='coerce')
        return df.dropna(subset=["日時"]).sort_values("日時", ascending=False)
    except: return pd.DataFrame()

def load_event_data():
    if not os.path.isfile(EVENT_LOG): return pd.DataFrame()
    try:
        df = pd.read_csv(EVENT_LOG, engine='python')
        return df.sort_index(ascending=False)
    except: return pd.DataFrame()

# ==========================================
# 3. 画面表示
# ==========================================
tab1, tab2 = st.tabs(["💥 解除イベント解析", "📋 過去の全詳細ログ"])

# --- Tab 1: 解除イベント（結論） ---
with tab1:
    df_ev = load_event_data()
    if not df_ev.empty:
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("総イベント", len(df_ev))
        with c2: st.metric("平均停滞", f"{df_ev['継続分'].mean():.1f}分")
        with c3: 
            up_rate = (len(df_ev[df_ev['方向'] == 'UP']) / len(df_ev)) * 100
            st.metric("上昇解除率", f"{up_rate:.1f}%")

        st.subheader("歪み開放の履歴")
        # 方向によって色を変える
        def style_event(row):
            color = 'color: #00ff7f;' if row['方向'] == 'UP' else 'color: #ff4b4b;'
            return [color if v == row['方向'] else '' for v in row]
        
        st.dataframe(df_ev.style.apply(style_event, axis=1), use_container_width=True)
        
        st.subheader("📊 停滞時間 vs 変動幅（エネルギー相関）")
        st.scatter_chart(data=df_ev, x="継続分", y="変動幅", color="方向")
    else:
        st.info("解除イベントの発生を待機中...")

# --- Tab 2: 詳細ログ（過程） ---
with tab2:
    df_dt = load_detail_data()
    if not df_dt.empty:
        # 判定列に色を付ける
        def color_status(val):
            if val == '停止': return 'background-color: #ff4b4b; color: white;'
            if val == '継続': return 'background-color: #1c83e1; color: white;'
            if val == '予兆': return 'background-color: #fca503; color: black;'
            return ''

        # フィルタリング機能
        unique_symbols = ["すべて"] + sorted(df_dt["銘柄"].unique().tolist())
        selected = st.selectbox("銘柄フィルタ", unique_symbols)
        
        display_df = df_dt if selected == "すべて" else df_dt[df_dt["銘柄"] == selected]
        
        st.dataframe(
            display_df.style.applymap(color_status, subset=['判定']),
            use_container_width=True,
            height=700
        )
    else:
        st.info("詳細ログが見つかりません。")

# --- 自動リロード ---
st.sidebar.caption(f"最終更新: {datetime.now().strftime('%H:%M:%S')}")
if st.sidebar.button("🔄 今すぐ更新"):
    st.rerun()

time.sleep(10)
st.rerun()