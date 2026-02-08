"""
Bybit清算データ取得モジュール
リアルタイムで清算イベントを監視し、青玉・金玉を判定
"""

import websocket
import json
import time
from datetime import datetime
from typing import Dict, List, Callable
import threading

class BybitLiquidationMonitor:
    """Bybitの清算データをWebSocketで監視"""

    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        self.ws = None
        self.liquidation_callbacks = []
        self.is_running = False

    def add_callback(self, callback: Callable):
        """清算イベント発生時のコールバック関数を追加"""
        self.liquidation_callbacks.append(callback)

    def on_message(self, ws, message):
        """WebSocketメッセージ受信時の処理"""
        try:
            data = json.loads(message)

            # 清算データの処理
            if "topic" in data and "liquidation" in data["topic"]:
                liquidation_data = data.get("data", [])

                for liq in liquidation_data:
                    processed = self._process_liquidation(liq)

                    # コールバック実行
                    for callback in self.liquidation_callbacks:
                        callback(processed)

        except Exception as e:
            print(f"メッセージ処理エラー: {e}")

    def _process_liquidation(self, liq_data: Dict) -> Dict:
        """清算データを処理して青玉・金玉を判定"""
        side = liq_data.get("side", "")
        price = float(liq_data.get("price", 0))
        size = float(liq_data.get("size", 0))
        timestamp = liq_data.get("time", int(time.time() * 1000))

        # 青玉: ロング清算（Buy側の清算 = 買いポジションが焼かれた）
        # 金玉: ショート清算（Sell側の清算 = 売りポジションが焼かれた）
        liquidation_type = "青玉" if side == "Buy" else "金玉"

        return {
            "timestamp": datetime.fromtimestamp(timestamp / 1000),
            "type": liquidation_type,
            "side": side,
            "price": price,
            "size": size,
            "value": price * size
        }

    def on_error(self, ws, error):
        """エラー処理"""
        print(f"WebSocketエラー: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """接続終了時の処理"""
        print(f"WebSocket接続終了: {close_status_code} - {close_msg}")
        if self.is_running:
            print("再接続を試みます...")
            time.sleep(5)
            self.start()

    def on_open(self, ws):
        """接続確立時の処理"""
        print(f"WebSocket接続確立: {self.symbol}")

        # 清算データのサブスクライブ
        subscribe_message = {
            "op": "subscribe",
            "args": [f"liquidation.{self.symbol}"]
        }
        ws.send(json.dumps(subscribe_message))
        print(f"清算データ購読開始: liquidation.{self.symbol}")

    def start(self):
        """監視開始"""
        self.is_running = True
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

        # 別スレッドで実行
        ws_thread = threading.Thread(target=self.ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()
        print("清算データ監視開始")

    def stop(self):
        """監視停止"""
        self.is_running = False
        if self.ws:
            self.ws.close()
        print("清算データ監視停止")


# 清算データ集約クラス
class LiquidationAggregator:
    """清算データを時間軸ごとに集約"""

    def __init__(self):
        self.liquidations: List[Dict] = []
        self.timeframes = {
            "6m": 6 * 60,
            "24m": 24 * 60,
            "144m": 144 * 60
        }

    def add_liquidation(self, liq_data: Dict):
        """清算データを追加"""
        self.liquidations.append(liq_data)

        # 古いデータを削除（24時間以上前）
        cutoff_time = datetime.now().timestamp() - (24 * 60 * 60)
        self.liquidations = [
            liq for liq in self.liquidations
            if liq["timestamp"].timestamp() > cutoff_time
        ]

    def get_aggregated_volume(self, timeframe: str) -> Dict:
        """指定時間軸での清算ボリュームを集計"""
        if timeframe not in self.timeframes:
            raise ValueError(f"未対応の時間軸: {timeframe}")

        seconds = self.timeframes[timeframe]
        cutoff_time = datetime.now().timestamp() - seconds

        recent_liqs = [
            liq for liq in self.liquidations
            if liq["timestamp"].timestamp() > cutoff_time
        ]

        # 青玉・金玉それぞれの合計
        ao_dama_volume = sum(
            liq["value"] for liq in recent_liqs if liq["type"] == "青玉"
        )
        kin_dama_volume = sum(
            liq["value"] for liq in recent_liqs if liq["type"] == "金玉"
        )

        return {
            "timeframe": timeframe,
            "青玉_volume": ao_dama_volume,
            "金玉_volume": kin_dama_volume,
            "total_volume": ao_dama_volume + kin_dama_volume,
            "count": len(recent_liqs)
        }
