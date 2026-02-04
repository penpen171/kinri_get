# modules/user_settings.py
"""
ユーザー設定の保存・読み込み機能
- ブラウザのLocalStorageを使用
- 証拠金、レバレッジ、戦術、取引所選択を保存
"""

import streamlit as st
import streamlit.components.v1 as components
import json


def load_settings_from_browser():
    """
    ブラウザのLocalStorageから設定を読み込む
    """
    # JavaScriptでLocalStorageから読み込み
    js_code = """
    <script>
        const settings = localStorage.getItem('kinriman_settings');
        if (settings) {
            const data = JSON.parse(settings);
            // Streamlitに送信
            window.parent.postMessage({
                type: 'streamlit:setComponentValue',
                value: data
            }, '*');
        } else {
            window.parent.postMessage({
                type: 'streamlit:setComponentValue',
                value: null
            }, '*');
        }
    </script>
    """
    
    result = components.html(js_code, height=0)
    return result


def save_settings_to_browser(margin, levs, tactic, exchanges):
    """
    ブラウザのLocalStorageに設定を保存
    
    Args:
        margin: 証拠金
        levs: レバレッジのリスト
        tactic: 戦術（"スキャ", "ヘッジ", "ホールド"）
        exchanges: 取引所選択の辞書 {"BingX": True, "MEXC": False, ...}
    """
    settings = {
        "margin": margin,
        "levs": levs,
        "tactic": tactic,
        "exchanges": exchanges
    }
    
    settings_json = json.dumps(settings)
    
    # JavaScriptでLocalStorageに保存
    js_code = f"""
    <script>
        const settings = {settings_json};
        localStorage.setItem('kinriman_settings', JSON.stringify(settings));
    </script>
    """
    
    components.html(js_code, height=0)


def init_settings():
    """
    設定の初期化（デフォルト値またはLocalStorageから復元）
    
    Returns:
        dict: 設定の辞書
    """
    # デフォルト値
    default_settings = {
        "margin": 100,
        "levs": [10, 20, 50, 100, 125],
        "tactic": "スキャ",
        "exchanges": {
            "BingX": True,
            "MEXC": True,
            "Bitget": True,
            "Variational": True
        }
    }
    
    # session_stateに保存されていればそれを使用
    if 'user_settings' in st.session_state:
        return st.session_state.user_settings
    
    # LocalStorageから読み込み試行
    # （初回アクセス時は None が返る）
    loaded = load_settings_from_browser()
    
    if loaded:
        # LocalStorageから読み込めた場合
        st.session_state.user_settings = loaded
        return loaded
    else:
        # 読み込めなかった場合はデフォルト値
        st.session_state.user_settings = default_settings
        return default_settings
