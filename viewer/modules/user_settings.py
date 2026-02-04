# modules/user_settings.py
"""
ユーザー設定の保存・読み込み機能
- ローカルファイルに保存（settings.json）
"""

import json
import os


SETTINGS_FILE = "user_settings.json"


def load_settings():
    """
    ローカルファイルから設定を読み込む
    
    Returns:
        dict: 設定の辞書（ファイルがない場合はデフォルト値）
    """
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
    
    # ファイルが存在する場合は読み込む
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # デフォルト値とマージ（新しいキーが追加された場合に対応）
                default_settings.update(loaded)
                return default_settings
        except Exception as e:
            print(f"[WARN] 設定ファイル読み込みエラー: {e}")
            return default_settings
    else:
        return default_settings


def save_settings(margin, levs, tactic, exchanges):
    """
    ローカルファイルに設定を保存
    
    Args:
        margin: 証拠金
        levs: レバレッジのリスト
        tactic: 戦術（"スキャ", "ヘッジ", "ホールド"）
        exchanges: 取引所選択の辞書
    """
    settings = {
        "margin": margin,
        "levs": levs,
        "tactic": tactic,
        "exchanges": exchanges
    }
    
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 設定ファイル保存エラー: {e}")
