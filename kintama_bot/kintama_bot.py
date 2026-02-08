#!/usr/bin/env python3
"""
金玉ボット - メイン実行プログラム
Bybitの清算データを監視し、平均足転換シグナルを通知
"""

import time
import sys
from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd

# 自作モジュールのインポート
from bybit_liquidation import BybitLiquidationMonitor, LiquidationAggregator
from heikin_ashi import HeikinAshi, TrendStrength
from mtf_analysis import MTFAnalyzer, LiquidationSignalDetector
from signal_engine import KintamaSignalEngine, SignalFormatter
from notifier import NotificationManager, ConsoleNotifier
from config import Config


class KintamaBot:
    """金玉ボット メインクラス"""

    def __init__(self):
        print("金玉ボット 初期化中...")

        # 設定の表示
        Config.print_config()

        # 各コンポーネントの初期化
        self.liquidation_monitor = BybitLiquidationMonitor(Config.BYBIT_SYMBOL)
        self.liquidation_aggregator = LiquidationAggregator()
        self.mtf_analyzer = MTFAnalyzer()
        self.signal_engine = KintamaSignalEngine()
        self.notification_manager = NotificationManager(
            discord_webhook=Config.DISCORD_WEBHOOK_URL,
            line_token=Config.LINE_NOTIFY_TOKEN,
            min_priority=Config.MIN_NOTIFICATION_PRIORITY
        )

        # データ管理
        self.candle_data = {tf: [] for tf in Config.TIMEFRAMES.keys()}
        self.start_time = datetime.now()
        self.last_status_report = datetime.now()

        # コールバック登録
        self.liquidation_monitor.add_callback(self.on_liquidation_event)

        print("✓ 金玉ボット 初期化完了\n")

    def on_liquidation_event(self, liq_data: Dict):
        """清算イベント発生時のコールバック"""
        # データを集約
        self.liquidation_aggregator.add_liquidation(liq_data)

        if Config.DEBUG_MODE:
            print(f"[清算検知] {liq_data['type']} | "
                  f"価格: ${liq_data['price']:,.2f} | "
                  f"サイズ: {liq_data['size']:.4f}")

    def analyze_and_signal(self):
        """定期的な分析とシグナル判定"""

        for timeframe in Config.TIMEFRAMES.keys():
            try:
                # 1. 清算ボリュームの取得と異常検出
                liq_volume = self.liquidation_aggregator.get_aggregated_volume(timeframe)

                # 過去平均と比較して異常判定
                historical_avg = self._calculate_historical_avg(timeframe)

                # 青玉・金玉どちらが支配的か判定
                if liq_volume['青玉_volume'] > liq_volume['金玉_volume']:
                    dominant_type = "青玉"
                    dominant_volume = liq_volume['青玉_volume']
                else:
                    dominant_type = "金玉"
                    dominant_volume = liq_volume['金玉_volume']

                liq_signal = LiquidationSignalDetector.detect_abnormal_liquidation(
                    dominant_volume,
                    historical_avg,
                    Config.LIQUIDATION_THRESHOLD_MULTIPLIER
                )

                if not liq_signal.get("is_abnormal"):
                    continue

                liq_signal["dominant_type"] = dominant_type

                # 2. 平均足データの取得（実際にはBybit APIから取得が必要）
                # ここではダミーデータで処理フローを示す
                # TODO: Bybit APIからOHLCデータを取得する実装

                # 3. 平均足の転換判定
                # df = self._get_ohlc_data(timeframe)  # 実装が必要
                # ha_df = HeikinAshi.calculate(df)
                # reversal = HeikinAshi.detect_reversal(ha_df)

                # 仮のreversal（実装時は上記に置き換え）
                reversal = {"has_reversal": False}

                if not reversal.get("has_reversal"):
                    continue

                # 4. MTF分析による有効性チェック
                signal_type = reversal.get("signal")
                mtf_validity = self.mtf_analyzer.check_signal_validity(
                    timeframe,
                    signal_type
                )

                # 5. シグナル判定
                signal = self.signal_engine.evaluate_signal(
                    liq_signal,
                    reversal,
                    mtf_validity,
                    timeframe
                )

                if signal:
                    # シグナル発生！
                    ConsoleNotifier.print_signal(signal)

                    # 通知送信
                    self.notification_manager.notify_signal(
                        signal,
                        SignalFormatter
                    )

                    # シグナル履歴を保存
                    if Config.SAVE_SIGNAL_HISTORY:
                        self._save_signal_to_csv(signal)

            except Exception as e:
                print(f"[エラー] {timeframe} 分析中にエラー: {e}")
                if Config.DEBUG_MODE:
                    import traceback
                    traceback.print_exc()

    def _calculate_historical_avg(self, timeframe: str) -> float:
        """過去の平均清算ボリュームを計算（簡易版）"""
        # TODO: より精密な統計処理を実装
        return 100000.0  # 仮の値

    def _save_signal_to_csv(self, signal: Dict):
        """シグナルをCSVファイルに保存"""
        try:
            import csv
            import os

            file_exists = os.path.isfile(Config.SIGNAL_HISTORY_FILE)

            with open(Config.SIGNAL_HISTORY_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'timestamp', 'timeframe', 'signal_type', 
                    'liquidation_type', 'priority', 'description'
                ])

                if not file_exists:
                    writer.writeheader()

                writer.writerow({
                    'timestamp': signal['timestamp'].isoformat(),
                    'timeframe': signal['timeframe'],
                    'signal_type': signal['signal_type'],
                    'liquidation_type': signal['liquidation_type'],
                    'priority': signal['priority'],
                    'description': signal['description']
                })
        except Exception as e:
            print(f"[警告] シグナル保存エラー: {e}")

    def send_status_report(self):
        """ステータスレポートを送信"""
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() / 3600)
        minutes = int((uptime.total_seconds() % 3600) / 60)

        stats = {
            'uptime': f"{hours}時間{minutes}分",
            'timeframes': list(Config.TIMEFRAMES.keys())
        }

        self.notification_manager.send_status_report(stats)
        self.last_status_report = datetime.now()

    def run(self):
        """メインループ実行"""
        print("🚀 金玉ボット 起動\n")
        print("清算データ監視を開始します...")
        print("Ctrl+C で終了\n")

        # 清算データ監視開始
        self.liquidation_monitor.start()

        try:
            while True:
                # 定期的な分析（60秒ごと）
                self.analyze_and_signal()

                # ステータスレポート（設定した間隔で）
                if (datetime.now() - self.last_status_report).total_seconds() > \
                   Config.STATUS_REPORT_INTERVAL_HOURS * 3600:
                    self.send_status_report()

                time.sleep(60)

        except KeyboardInterrupt:
            print("\n金玉ボット を停止します...")
            self.liquidation_monitor.stop()
            print("停止完了")
            sys.exit(0)
        except Exception as e:
            print(f"\n[致命的エラー] {e}")
            self.notification_manager.send_error_alert(str(e))
            self.liquidation_monitor.stop()
            sys.exit(1)


def main():
    """エントリーポイント"""
    bot = KintamaBot()
    bot.run()


if __name__ == "__main__":
    main()
