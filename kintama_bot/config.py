"""
設定ファイル
API接続情報と通知設定を管理
"""

import os
from typing import Dict

class Config:
    """金玉ボット設定"""

    # ===== Bybit設定 =====
    BYBIT_SYMBOL = "BTCUSDT"  # 監視するシンボル

    # ===== 時間軸設定 =====
    TIMEFRAMES = {
        "6m": 6,      # 6分足
        "24m": 24,    # 24分足
        "144m": 144   # 144分足（ボス）
    }

    # ===== シグナル判定設定 =====
    # 異常清算判定の倍率（通常の何倍で異常とみなすか）
    LIQUIDATION_THRESHOLD_MULTIPLIER = 2.0

    # 清算データの履歴保持時間（時間）
    LIQUIDATION_HISTORY_HOURS = 24

    # ===== 通知設定 =====
    # 最低通知優先度（"最優先", "高", "中", "低"）
    MIN_NOTIFICATION_PRIORITY = "中"

    # Discord Webhook URL（環境変数から取得）
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

    # LINE Notify トークン（環境変数から取得）
    LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN", "")

    # ステータスレポート送信間隔（時間）
    STATUS_REPORT_INTERVAL_HOURS = 6

    # ===== ログ設定 =====
    LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
    LOG_FILE = "kintama_bot.log"

    # ===== データ保存設定 =====
    SAVE_SIGNAL_HISTORY = True
    SIGNAL_HISTORY_FILE = "signal_history.csv"

    # ===== デバッグ設定 =====
    DEBUG_MODE = False  # Trueでコンソール出力を詳細化

    @classmethod
    def validate(cls) -> Dict[str, bool]:
        """設定の妥当性をチェック"""
        checks = {
            "Discord設定": bool(cls.DISCORD_WEBHOOK_URL),
            "LINE設定": bool(cls.LINE_NOTIFY_TOKEN),
            "シンボル設定": bool(cls.BYBIT_SYMBOL),
            "時間軸設定": len(cls.TIMEFRAMES) > 0
        }
        return checks

    @classmethod
    def print_config(cls):
        """現在の設定を表示"""
        print("
" + "="*60)
        print("金玉ボット 設定情報")
        print("="*60)
        print(f"監視シンボル: {cls.BYBIT_SYMBOL}")
        print(f"時間軸: {', '.join(cls.TIMEFRAMES.keys())}")
        print(f"清算異常判定倍率: {cls.LIQUIDATION_THRESHOLD_MULTIPLIER}x")
        print(f"最低通知優先度: {cls.MIN_NOTIFICATION_PRIORITY}")
        print(f"Discord通知: {'有効' if cls.DISCORD_WEBHOOK_URL else '無効'}")
        print(f"LINE通知: {'有効' if cls.LINE_NOTIFY_TOKEN else '無効'}")
        print(f"デバッグモード: {'ON' if cls.DEBUG_MODE else 'OFF'}")
        print("="*60 + "
")


# 環境変数テンプレート用の.envファイル生成
def create_env_template():
    """環境変数テンプレートファイルを生成"""
    template = """# 金玉ボット 環境変数設定
# このファイルを .env としてコピーし、実際の値を設定してください

# Discord Webhook URL（オプション）
# Discordサーバー設定 > 連携サービス > ウェブフックから取得
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL

# LINE Notify トークン（オプション）
# https://notify-bot.line.me/my/ から取得
LINE_NOTIFY_TOKEN=YOUR_LINE_NOTIFY_TOKEN

# デバッグモード（True/False）
DEBUG_MODE=False
"""

    with open('.env.template', 'w', encoding='utf-8') as f:
        f.write(template)

    print("✓ .env.template ファイルを作成しました")
    print("  実際の設定は .env ファイルを作成して記入してください")


if __name__ == "__main__":
    Config.print_config()
    create_env_template()
