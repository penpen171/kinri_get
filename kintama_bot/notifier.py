"""
通知システムモジュール
Discord WebhookとLINE Notifyへシグナルを送信
"""

import requests
from typing import Dict, Optional
import json
from datetime import datetime

class DiscordNotifier:
    """Discord Webhook通知"""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url

    def send(self, message: str, username: str = "金玉ボット") -> bool:
        """
        Discordにメッセージを送信

        Args:
            message: 送信するメッセージ
            username: ボット名

        Returns:
            送信成功ならTrue
        """
        if not self.webhook_url:
            print("Discord Webhook URLが設定されていません")
            return False

        payload = {
            "username": username,
            "content": message
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 204:
                print(f"Discord通知送信成功: {datetime.now()}")
                return True
            else:
                print(f"Discord通知失敗: {response.status_code}")
                return False

        except Exception as e:
            print(f"Discord通知エラー: {e}")
            return False

    def send_embed(
        self, 
        title: str, 
        description: str, 
        color: int = 0x00ff00,
        fields: Optional[list] = None
    ) -> bool:
        """
        リッチなEmbedメッセージを送信

        Args:
            title: タイトル
            description: 説明
            color: 色（16進数）
            fields: フィールドリスト
        """
        if not self.webhook_url:
            return False

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "金玉ボット"
            }
        }

        if fields:
            embed["fields"] = fields

        payload = {
            "username": "金玉ボット",
            "embeds": [embed]
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            return response.status_code == 204
        except Exception as e:
            print(f"Discord Embed送信エラー: {e}")
            return False


class LineNotifier:
    """LINE Notify通知"""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.api_url = "https://notify-api.line.me/api/notify"

    def send(self, message: str) -> bool:
        """
        LINE Notifyにメッセージを送信

        Args:
            message: 送信するメッセージ

        Returns:
            送信成功ならTrue
        """
        if not self.access_token:
            print("LINE Notify トークンが設定されていません")
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        data = {
            "message": f"
{message}"
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                data=data,
                timeout=10
            )

            if response.status_code == 200:
                print(f"LINE通知送信成功: {datetime.now()}")
                return True
            else:
                print(f"LINE通知失敗: {response.status_code}")
                return False

        except Exception as e:
            print(f"LINE通知エラー: {e}")
            return False


class NotificationManager:
    """通知マネージャー - 複数の通知先を統合管理"""

    def __init__(
        self,
        discord_webhook: Optional[str] = None,
        line_token: Optional[str] = None,
        min_priority: str = "中"
    ):
        self.discord = DiscordNotifier(discord_webhook)
        self.line = LineNotifier(line_token)
        self.min_priority = min_priority
        self.notification_count = 0

    def notify_signal(self, signal: Dict, formatter) -> bool:
        """
        シグナルを通知

        Args:
            signal: シグナル情報
            formatter: SignalFormatterクラス

        Returns:
            いずれかの通知が成功すればTrue
        """
        # 優先度チェック
        if not self._should_notify(signal):
            print(f"優先度が低いためスキップ: {signal.get('priority')}")
            return False

        success = False

        # Discord通知
        if self.discord.webhook_url:
            discord_msg = formatter.format_for_discord(signal)
            if self.discord.send(discord_msg):
                success = True

        # LINE通知
        if self.line.access_token:
            line_msg = formatter.format_for_line(signal)
            if self.line.send(line_msg):
                success = True

        if success:
            self.notification_count += 1

        return success

    def _should_notify(self, signal: Dict) -> bool:
        """通知すべきかを優先度で判定"""
        priority_order = ["最優先", "高", "中", "低"]

        signal_priority = signal.get("priority", "低")

        if signal_priority not in priority_order:
            return False

        signal_index = priority_order.index(signal_priority)
        min_index = priority_order.index(self.min_priority)

        return signal_index <= min_index

    def send_status_report(self, stats: Dict):
        """ステータスレポートを送信"""
        message = f"""
【金玉ボット 稼働状況】
━━━━━━━━━━━━━━━━
稼働時間: {stats.get('uptime', '不明')}
通知送信数: {self.notification_count}回
監視中の時間軸: {', '.join(stats.get('timeframes', []))}
━━━━━━━━━━━━━━━━
"""

        if self.discord.webhook_url:
            self.discord.send(message)

        if self.line.access_token:
            self.line.send(message)

    def send_error_alert(self, error_message: str):
        """エラーアラートを送信"""
        alert = f"⚠️ 【エラー発生】
{error_message}"

        if self.discord.webhook_url:
            self.discord.send(alert)

        if self.line.access_token:
            self.line.send(alert)


class ConsoleNotifier:
    """コンソール出力（デバッグ用）"""

    @staticmethod
    def print_signal(signal: Dict):
        """シグナルをコンソールに出力"""
        print("
" + "="*60)
        print(f"🎯 シグナル発生: {signal['signal_type']} {signal.get('reversal_symbol', '')}")
        print(f"時間軸: {signal['timeframe']}")
        print(f"清算タイプ: {signal['liquidation_type']}")
        print(f"優先度: {signal['priority']}")
        print(f"説明: {signal['description']}")
        print(f"発生時刻: {signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60 + "
")
