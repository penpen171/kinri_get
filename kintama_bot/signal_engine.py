"""
シグナル判定エンジン
清算データ + 平均足転換 + MTF分析を統合
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd

class KintamaSignalEngine:
    """金玉ボット シグナル判定エンジン"""

    def __init__(self):
        self.signal_history = []

    def evaluate_signal(
        self,
        liquidation_data: Dict,
        heikin_ashi_reversal: Dict,
        mtf_validity: Dict,
        timeframe: str
    ) -> Optional[Dict]:
        """
        総合的なシグナル評価

        Args:
            liquidation_data: 清算データ（青玉・金玉情報）
            heikin_ashi_reversal: 平均足の転換情報
            mtf_validity: MTF分析による有効性チェック
            timeframe: 時間軸

        Returns:
            シグナル情報（なければNone）
        """
        # 1. 清算ドット（異常な清算）が発生しているか
        has_liquidation = liquidation_data.get("is_abnormal", False)

        # 2. 平均足が転換しているか
        has_reversal = heikin_ashi_reversal.get("has_reversal", False)

        # 3. 上位足のバイアスと矛盾しないか
        is_valid = mtf_validity.get("is_valid", True)

        # シグナル発生条件: すべてTrueの場合
        if not (has_liquidation and has_reversal and is_valid):
            return None

        # シグナル生成
        signal_type = heikin_ashi_reversal.get("signal")
        liquidation_type = liquidation_data.get("dominant_type")

        signal = {
            "timestamp": datetime.now(),
            "timeframe": timeframe,
            "signal_type": signal_type,  # "ロング" or "ショート"
            "liquidation_type": liquidation_type,  # "青玉" or "金玉"
            "liquidation_strength": liquidation_data.get("strength", "中"),
            "reversal_symbol": heikin_ashi_reversal.get("symbol"),
            "description": self._generate_description(
                signal_type, 
                liquidation_type, 
                liquidation_data
            ),
            "priority": self._calculate_priority(timeframe, liquidation_data),
            "is_boss_signal": timeframe == "144m"
        }

        self.signal_history.append(signal)
        return signal

    def _generate_description(
        self, 
        signal_type: str, 
        liquidation_type: str,
        liq_data: Dict
    ) -> str:
        """シグナルの説明文を生成"""
        strength = liq_data.get("strength", "中")
        ratio = liq_data.get("ratio", 1.0)

        if signal_type == "ロング":
            base = f"【{liquidation_type}発生】大量のロング清算により売り圧力が一掃"
            action = "→ ロングエントリー検討"
        else:
            base = f"【{liquidation_type}発生】大量のショート清算により買い圧力が解消"
            action = "→ ショートエントリー検討"

        return f"{base}（強度: {strength}、通常の{ratio:.1f}倍）{action}"

    def _calculate_priority(self, timeframe: str, liq_data: Dict) -> str:
        """シグナルの優先度を計算"""
        if timeframe == "144m":
            return "最優先"
        elif timeframe == "24m":
            return "高"
        else:
            strength = liq_data.get("strength", "中")
            if strength in ["極強", "非常に強"]:
                return "中"
            return "低"

    def check_confirmation_time(
        self, 
        signal: Dict, 
        timeframe: str
    ) -> Dict:
        """
        シグナル発生から平均足確定までの時間を確認

        Args:
            signal: シグナル情報
            timeframe: 時間軸

        Returns:
            確定待ち情報
        """
        timeframe_minutes = {
            "6m": 6,
            "24m": 24,
            "144m": 144
        }

        minutes = timeframe_minutes.get(timeframe, 0)
        max_wait_hours = minutes / 60

        # 144分足の場合、最大16時間の猶予
        if timeframe == "144m":
            max_wait_hours = 16

        return {
            "timeframe": timeframe,
            "signal_time": signal.get("timestamp"),
            "max_wait_hours": max_wait_hours,
            "status": "確定待ち",
            "note": f"平均足確定まで最大{max_wait_hours}時間の猶予あり"
        }

    def filter_by_priority(
        self, 
        signals: List[Dict], 
        min_priority: str = "中"
    ) -> List[Dict]:
        """
        優先度でシグナルをフィルタリング

        Args:
            signals: シグナルリスト
            min_priority: 最低優先度（"最優先"、"高"、"中"、"低"）

        Returns:
            フィルタされたシグナルリスト
        """
        priority_order = ["最優先", "高", "中", "低"]
        min_index = priority_order.index(min_priority)

        return [
            sig for sig in signals
            if priority_order.index(sig.get("priority", "低")) <= min_index
        ]

    def get_latest_signals(self, count: int = 10) -> List[Dict]:
        """最新のシグナルを取得"""
        return sorted(
            self.signal_history[-count:],
            key=lambda x: x["timestamp"],
            reverse=True
        )


class SignalFormatter:
    """シグナルを通知用にフォーマット"""

    @staticmethod
    def format_for_discord(signal: Dict) -> str:
        """Discord通知用フォーマット"""
        emoji_map = {
            "ロング": "🟢",
            "ショート": "🔴"
        }

        priority_emoji = {
            "最優先": "⭐⭐⭐",
            "高": "⭐⭐",
            "中": "⭐",
            "低": ""
        }

        emoji = emoji_map.get(signal["signal_type"], "⚪")
        priority_stars = priority_emoji.get(signal["priority"], "")

        message = f"""
{emoji} **金玉ボット シグナル発生** {priority_stars}

**時間軸**: {signal["timeframe"]}
**シグナル**: {signal["signal_type"]} {signal["reversal_symbol"]}
**清算タイプ**: {signal["liquidation_type"]}
**強度**: {signal["liquidation_strength"]}

{signal["description"]}

---
**発生時刻**: {signal["timestamp"].strftime("%Y-%m-%d %H:%M:%S")}
"""

        if signal["is_boss_signal"]:
            message = "🚨 **【144分足ボスシグナル】** 🚨
" + message

        return message.strip()

    @staticmethod
    def format_for_line(signal: Dict) -> str:
        """LINE通知用フォーマット（シンプル）"""
        return (
            f"【金玉ボット】
"
            f"{signal['signal_type']} {signal['reversal_symbol']}
"
            f"{signal['timeframe']} | {signal['liquidation_type']}
"
            f"{signal['description']}"
        )
