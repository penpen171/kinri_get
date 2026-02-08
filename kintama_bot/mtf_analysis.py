"""
マルチタイムフレーム（MTF）分析モジュール
144分足（ボス）、24分足、6分足の階層的分析
"""

from typing import Dict, List
from datetime import datetime, timedelta
import pandas as pd

class MTFAnalyzer:
    """マルチタイムフレーム分析"""

    TIMEFRAMES = {
        "6m": {"minutes": 6, "priority": 3, "name": "6分足"},
        "24m": {"minutes": 24, "priority": 2, "name": "24分足"},
        "144m": {"minutes": 144, "priority": 1, "name": "144分足（ボス）"}
    }

    def __init__(self):
        self.data = {tf: [] for tf in self.TIMEFRAMES.keys()}

    def add_data(self, timeframe: str, candle_data: Dict):
        """時間軸ごとのローソク足データを追加"""
        if timeframe not in self.TIMEFRAMES:
            raise ValueError(f"未対応の時間軸: {timeframe}")

        self.data[timeframe].append(candle_data)

    def get_hierarchy_bias(self) -> Dict:
        """
        階層的バイアスを取得
        上位足が下位足に優先する

        Returns:
            各時間軸のバイアス情報
        """
        bias = {}

        for tf, config in sorted(
            self.TIMEFRAMES.items(), 
            key=lambda x: x[1]["priority"]
        ):
            if tf in self.data and len(self.data[tf]) > 0:
                latest = self.data[tf][-1]
                bias[tf] = {
                    "name": config["name"],
                    "priority": config["priority"],
                    "trend": latest.get("trend", "不明"),
                    "signal": latest.get("signal"),
                    "liquidation_type": latest.get("liquidation_type")
                }

        return bias

    def check_signal_validity(
        self, 
        timeframe: str, 
        signal: str
    ) -> Dict:
        """
        シグナルが上位足のバイアスと矛盾しないかチェック

        Args:
            timeframe: シグナルが出た時間軸
            signal: "ロング" or "ショート"

        Returns:
            有効性判定結果
        """
        current_priority = self.TIMEFRAMES[timeframe]["priority"]

        # より優先度の高い（数字が小さい）時間軸をチェック
        for tf, config in self.TIMEFRAMES.items():
            if config["priority"] < current_priority:
                if tf in self.data and len(self.data[tf]) > 0:
                    boss_data = self.data[tf][-1]
                    boss_trend = boss_data.get("trend", "不明")

                    # 上位足のトレンドと矛盾チェック
                    if boss_trend == "上昇" and signal == "ショート":
                        return {
                            "is_valid": False,
                            "reason": f"{config['name']}が上昇トレンド中のため、ショートシグナルは無視",
                            "boss_timeframe": tf,
                            "boss_trend": boss_trend,
                            "action": "シグナルトラップ - エントリー見送り"
                        }
                    elif boss_trend == "下落" and signal == "ロング":
                        return {
                            "is_valid": False,
                            "reason": f"{config['name']}が下落トレンド中のため、ロングシグナルは無視",
                            "boss_timeframe": tf,
                            "boss_trend": boss_trend,
                            "action": "シグナルトラップ - エントリー見送り"
                        }

        return {
            "is_valid": True,
            "reason": "上位足のバイアスと整合性あり",
            "action": "エントリー検討可"
        }

    def apply_one_tenth_rule(self, target_timeframe: str) -> str:
        """
        1/10の法則を適用
        大きな時間軸の初動を捉えるため、その1/10の時間軸を推奨

        Args:
            target_timeframe: 捉えたい時間軸（例: "60m"）

        Returns:
            推奨する監視時間軸
        """
        # 60分足の1/10 = 6分足
        if target_timeframe == "60m":
            return "6m"
        # 144分足の1/10 ≈ 14分 → 最も近い24分足を推奨
        elif target_timeframe == "144m":
            return "24m"
        else:
            return "6m"

    def get_dominant_signal(self) -> Dict:
        """
        最も優先度の高い時間軸からシグナルを取得

        Returns:
            支配的なシグナル情報
        """
        # 優先度順にソート（144m → 24m → 6m）
        sorted_tfs = sorted(
            self.TIMEFRAMES.items(),
            key=lambda x: x[1]["priority"]
        )

        for tf, config in sorted_tfs:
            if tf in self.data and len(self.data[tf]) > 0:
                latest = self.data[tf][-1]

                if latest.get("has_signal"):
                    return {
                        "timeframe": tf,
                        "name": config["name"],
                        "signal": latest.get("signal"),
                        "priority": "最優先" if config["priority"] == 1 else "通常",
                        "description": latest.get("description", ""),
                        "is_boss": config["priority"] == 1
                    }

        return {
            "timeframe": None,
            "signal": None,
            "description": "現在シグナルなし（スキャルピングゾーン）"
        }

    def get_no_trade_zone_status(self) -> bool:
        """
        ノートレードゾーン（スキャルピングゾーン）かどうか判定

        Returns:
            True: トレード不可、False: トレード可
        """
        dominant = self.get_dominant_signal()
        return dominant["signal"] is None


class LiquidationSignalDetector:
    """清算データに基づくシグナル検出"""

    @staticmethod
    def detect_abnormal_liquidation(
        current_volume: float,
        historical_avg: float,
        threshold_multiplier: float = 2.0
    ) -> Dict:
        """
        異常な清算ボリュームを検出

        Args:
            current_volume: 現在の清算ボリューム
            historical_avg: 過去の平均ボリューム
            threshold_multiplier: 異常判定の倍率

        Returns:
            異常検出結果
        """
        if historical_avg == 0:
            return {"is_abnormal": False}

        ratio = current_volume / historical_avg

        if ratio >= threshold_multiplier:
            strength = "強"
            if ratio >= 5.0:
                strength = "極強"
            elif ratio >= 3.0:
                strength = "非常に強"

            return {
                "is_abnormal": True,
                "ratio": ratio,
                "strength": strength,
                "description": f"通常の{ratio:.1f}倍の清算発生"
            }

        return {"is_abnormal": False}
