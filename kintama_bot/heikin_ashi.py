"""
平均足（Heikin-Ashi）計算モジュール
ノイズを除去してトレンド転換を明確に判定
"""

import pandas as pd
import numpy as np
from typing import Dict, List

class HeikinAshi:
    """平均足計算と転換判定"""

    def __init__(self):
        self.candles = []

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        """
        通常のOHLCデータから平均足を計算

        Args:
            df: columns=['open', 'high', 'low', 'close', 'volume'] のDataFrame

        Returns:
            平均足OHLC付きDataFrame
        """
        ha_df = df.copy()

        # 平均足の終値 = (始値 + 高値 + 安値 + 終値) / 4
        ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4

        # 平均足の始値 = (前の平均足始値 + 前の平均足終値) / 2
        ha_df['ha_open'] = np.nan
        ha_df.loc[0, 'ha_open'] = (df.loc[0, 'open'] + df.loc[0, 'close']) / 2

        for i in range(1, len(ha_df)):
            ha_df.loc[i, 'ha_open'] = (
                ha_df.loc[i-1, 'ha_open'] + ha_df.loc[i-1, 'ha_close']
            ) / 2

        # 平均足の高値 = 実際の高値、平均足始値、平均足終値の最大
        ha_df['ha_high'] = ha_df[['high', 'ha_open', 'ha_close']].max(axis=1)

        # 平均足の安値 = 実際の安値、平均足始値、平均足終値の最小
        ha_df['ha_low'] = ha_df[['low', 'ha_open', 'ha_close']].min(axis=1)

        # 陽線・陰線の判定
        ha_df['is_bullish'] = ha_df['ha_close'] > ha_df['ha_open']

        return ha_df

    @staticmethod
    def detect_reversal(df: pd.DataFrame) -> Dict:
        """
        平均足の転換を検出

        Returns:
            転換情報の辞書
        """
        if len(df) < 2:
            return {"has_reversal": False}

        # 最新の足と1つ前の足を比較
        current = df.iloc[-1]
        previous = df.iloc[-2]

        current_bullish = current['is_bullish']
        previous_bullish = previous['is_bullish']

        # 転換判定
        if previous_bullish == False and current_bullish == True:
            # 陰線→陽線: ロングシグナル
            return {
                "has_reversal": True,
                "signal": "ロング",
                "type": "bullish_reversal",
                "symbol": "▲",
                "color": "green",
                "description": "平均足が陽線に転換（買いシグナル）"
            }
        elif previous_bullish == True and current_bullish == False:
            # 陽線→陰線: ショートシグナル
            return {
                "has_reversal": True,
                "signal": "ショート",
                "type": "bearish_reversal",
                "symbol": "▼",
                "color": "red",
                "description": "平均足が陰線に転換（売りシグナル）"
            }
        else:
            return {
                "has_reversal": False,
                "current_trend": "上昇" if current_bullish else "下落"
            }

    @staticmethod
    def is_candle_confirmed(timestamp, timeframe_minutes: int) -> bool:
        """
        足が確定したかを判定

        Args:
            timestamp: 現在時刻
            timeframe_minutes: 時間軸（分）

        Returns:
            確定していればTrue
        """
        from datetime import datetime

        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        minutes_since_midnight = timestamp.hour * 60 + timestamp.minute
        return minutes_since_midnight % timeframe_minutes == 0


class TrendStrength:
    """トレンドの強さを評価"""

    @staticmethod
    def calculate_consecutive_candles(df: pd.DataFrame) -> Dict:
        """
        連続した陽線・陰線の本数をカウント

        Returns:
            トレンド強度情報
        """
        if len(df) < 2:
            return {"consecutive": 0, "trend": "不明"}

        consecutive = 1
        current_trend = df.iloc[-1]['is_bullish']

        for i in range(len(df) - 2, -1, -1):
            if df.iloc[i]['is_bullish'] == current_trend:
                consecutive += 1
            else:
                break

        trend_name = "上昇" if current_trend else "下落"

        strength = "弱い"
        if consecutive >= 5:
            strength = "非常に強い"
        elif consecutive >= 3:
            strength = "強い"
        elif consecutive >= 2:
            strength = "やや強い"

        return {
            "consecutive": consecutive,
            "trend": trend_name,
            "strength": strength,
            "is_strong": consecutive >= 3
        }
