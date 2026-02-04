import streamlit as st
import pandas as pd
import requests
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.data_api import fetch_api_snapshot
from modules.mode_simultaneous import render_simultaneous_mode
from modules.mode_time_diff import render_time_diff_mode
from modules.mode_single import render_single_mode
from modules.user_settings import init_settings, save_settings_to_browser


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


# --- サイドバー構成 ---
# --- サイドバー構成 ---
st.sidebar.header("👔 現場コントロール")

# 設定のデフォルト値
DEFAULT_SETTINGS = {
    "margin": 100,
    "levs": [10, 20, 50, 100, 125],
    "tactic": "スキャ",
    "exchanges": {"BingX": True, "MEXC": True, "Bitget": True, "Variational": True}
}

# 初回のみsession_stateに保存
if 'user_settings' not in st.session_state:
    st.session_state.user_settings = DEFAULT_SETTINGS.copy()

settings = st.session_state.user_settings

if st.sidebar.button('⚡️ 最新データ更新', use_container_width=True):
    st.cache_data.clear()
    raw, status, ts = fetch_api_snapshot()
    st.session_state.update({'raw': raw, 'api': status, 'update_ts': ts})

mode_ui = st.sidebar.selectbox("📊 プログラム選択", ["同時刻金利版", "時間差ヘッジ版", "単体金利版"])
st.sidebar.markdown("---")

# 戦術選択（保存された値を初期値に）
tactic_options = ["スキャ", "ヘッジ", "ホールド"]
default_tactic = settings.get("tactic", "スキャ")
default_tactic_index = tactic_options.index(default_tactic) if default_tactic in tactic_options else 0
tactic_ui = st.sidebar.radio("🔥 戦術判定", tactic_options, index=default_tactic_index, key="tactic_radio")
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

# 証拠金（保存された値を初期値に）
margin = st.sidebar.number_input("証拠金 (USDT)", 10, 1000000, settings.get("margin", 100), key="margin_input")

# レバレッジ設定（保存された値を初期値に）
st.sidebar.markdown("🕹️ **レバレッジ設定**")
cols = st.sidebar.columns(5)
saved_levs = settings.get("levs", [10, 20, 50, 100, 125])
levs = [cols[i].number_input(str(i+1), 1, 200, saved_levs[i], key=f"lev_{i}") for i in range(5)]

st.sidebar.markdown("---")

# 取引所選択（保存された値を初期値に）
st.sidebar.markdown("🏦 **対象取引所**")
saved_exchanges = settings.get("exchanges", {"BingX": True, "MEXC": True, "Bitget": True, "Variational": True})
sel_bn = st.sidebar.checkbox("BingX", value=saved_exchanges.get("BingX", True), key="ex_bn")
sel_m = st.sidebar.checkbox("MEXC", value=saved_exchanges.get("MEXC", True), key="ex_m")
sel_bt = st.sidebar.checkbox("Bitget", value=saved_exchanges.get("Bitget", True), key="ex_bt")
sel_vr = st.sidebar.checkbox("Variational", value=saved_exchanges.get("Variational", True), key="ex_vr")
active_exs = [ex for ex, s in zip(["BingX", "MEXC", "Bitget", "Variational"], [sel_bn, sel_m, sel_bt, sel_vr]) if s]

# 設定をsession_stateに保存（次回起動時の初期値に）
st.session_state.user_settings = {
    "margin": margin,
    "levs": levs,
    "tactic": tactic_ui,
    "exchanges": {"BingX": sel_bn, "MEXC": sel_m, "Bitget": sel_bt, "Variational": sel_vr}
}




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
        render_simultaneous_mode(st.session_state.raw, active_exs, levs, t_key, margin)
    
    elif mode_ui == "時間差ヘッジ版":
        render_time_diff_mode(st.session_state.raw, active_exs, levs, t_key, margin)
    
    else:  # 単体金利版
        render_single_mode(st.session_state.raw, active_exs, levs, t_key, margin)
