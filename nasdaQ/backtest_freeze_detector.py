# backtest_freeze_detector_v2.py
# v2 APIで過去データを取得してバックテスト

import requests
import time
from datetime import datetime, timedelta, timezone
from collections import deque
import statistics

BASE_URL = "https://open-api.bingx.com"
ENDPOINT_V2 = "/openApi/swap/v2/quote/klines"  # v2を使用
JST = timezone(timedelta(hours=9))


class BacktestFreezeDetector:
    """バックテスト用の停止検知器"""
    
    def __init__(self, symbol, name):
        self.symbol = symbol
        self.name = name
        self.volatility_history = deque(maxlen=100)
        self.consecutive_high_scores = 0
        self.state = "NORMAL"
        self.freeze_start_time = None
        self.freeze_start_price = None
        
    def add_candle(self, candle):
        """ローソク足を追加して分析"""
        hl_range = candle['high'] - candle['low']
        self.volatility_history.append(hl_range)
        
    def calculate_freeze_score(self):
        """停止スコアを計算"""
        if len(self.volatility_history) < 20:
            return 0
        
        baseline = statistics.median(self.volatility_history)
        recent = statistics.mean(list(self.volatility_history)[-5:])
        
        if baseline == 0:
            return 0
        
        ratio = recent / baseline
        
        if ratio <= 0.1:
            return 100
        elif ratio <= 0.2:
            return 80
        elif ratio <= 0.3:
            return 60
        elif ratio <= 0.5:
            return 40
        else:
            return 0
    
    def analyze_candle(self, candle, candle_index):
        """1本のローソク足を分析"""
        self.add_candle(candle)
        
        freeze_score = self.calculate_freeze_score()
        
        # スコアのカウント
        if freeze_score >= 60:
            self.consecutive_high_scores += 1
        else:
            self.consecutive_high_scores = 0
        
        timestamp = candle['timestamp']
        price = candle['close']
        hl_range = candle['high'] - candle['low']
        body = abs(candle['close'] - candle['open'])
        
        # 状態遷移
        detection_msg = None
        
        if self.state == "NORMAL":
            if self.consecutive_high_scores >= 3:
                self.state = "SUSPECTED"
                detection_msg = f"⚠️  停止の疑いを検知"
                
        elif self.state == "SUSPECTED":
            if self.consecutive_high_scores >= 5:
                self.state = "CONFIRMED"
                self.freeze_start_time = timestamp
                self.freeze_start_price = price
                detection_msg = f"🚨 停止を確定！"
            elif freeze_score < 40:
                self.state = "NORMAL"
                self.consecutive_high_scores = 0
                
        elif self.state == "CONFIRMED":
            if freeze_score < 40:
                duration = (timestamp - self.freeze_start_time).total_seconds() / 60
                price_diff = price - self.freeze_start_price
                direction = "UP" if price_diff > 0 else "DOWN"
                detection_msg = f"💥 停止解消！{direction}方向へ（{duration:.1f}分停止、変動{price_diff:.2f}）"
                self.state = "NORMAL"
                self.consecutive_high_scores = 0
        
        return {
            'index': candle_index,
            'timestamp': timestamp,
            'price': price,
            'body': body,
            'hl_range': hl_range,
            'freeze_score': freeze_score,
            'consecutive': self.consecutive_high_scores,
            'state': self.state,
            'detection_msg': detection_msg
        }


def get_klines_v2(symbol, start_time, end_time):
    """v2 APIでKラインを取得"""
    url = BASE_URL + ENDPOINT_V2
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": int(start_time.timestamp() * 1000),
        "endTime": int(end_time.timestamp() * 1000),
        "limit": 1440
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get("code") == 0 and data.get("data"):
            candles = []
            for kline in data["data"]:
                ts = int(kline["time"])
                dt_utc = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                dt_jst = dt_utc.astimezone(JST)
                
                candle = {
                    'timestamp': dt_jst,
                    'open': float(kline['open']),
                    'high': float(kline['high']),
                    'low': float(kline['low']),
                    'close': float(kline['close']),
                    'volume': float(kline.get('volume', 0))
                }
                candles.append(candle)
            
            return candles
        else:
            print(f"  APIエラー: {data}")
            return []
            
    except Exception as e:
        print(f"  接続エラー: {e}")
        return []


def run_backtest_specific_date(symbol, name, target_date_str, start_hour=10, end_hour=11):
    """特定の日時のデータでバックテスト"""
    print("=" * 80)
    print(f"🔬 バックテスト: {name}")
    print(f"   対象日: {target_date_str}")
    print(f"   時間帯: {start_hour}:00 ～ {end_hour}:00")
    print("=" * 80)
    
    # 日時をパース（JST）
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
    target_date = target_date.replace(tzinfo=JST)
    
    # ベースライン確立のため2時間前から取得
    start_time = target_date.replace(hour=start_hour-2, minute=0, second=0)
    end_time = target_date.replace(hour=end_hour, minute=0, second=0)
    
    print(f"\n📥 データ取得中: {start_time.strftime('%Y-%m-%d %H:%M')} ～ {end_time.strftime('%Y-%m-%d %H:%M')}")
    
    # v2 APIでデータ取得
    candles = get_klines_v2(symbol, start_time, end_time)
    
    if not candles:
        print("❌ データ取得失敗")
        return
    
    print(f"✅ {len(candles)}本のローソク足を取得")
    print(f"   最古: {candles[0]['timestamp'].strftime('%m/%d %H:%M:%S')}")
    print(f"   最新: {candles[-1]['timestamp'].strftime('%m/%d %H:%M:%S')}")
    
    # 検知器で分析
    print("\n" + "=" * 80)
    print("📊 停止検知分析")
    print("=" * 80)
    
    detector = BacktestFreezeDetector(symbol, name)
    
    events = []
    all_results = []
    
    for i, candle in enumerate(candles):
        result = detector.analyze_candle(candle, i)
        all_results.append(result)
        
        # 重要なイベントを記録
        if result['detection_msg']:
            events.append(result)
            print(f"\n[{result['timestamp'].strftime('%m/%d %H:%M:%S')}] {result['detection_msg']}")
            print(f"   価格: {result['price']:.2f}")
            print(f"   スコア: {result['freeze_score']}")
            print(f"   連続: {result['consecutive']}回")
    
    # 対象時間帯の詳細表示
    print("\n" + "=" * 80)
    print(f"📋 対象時間帯({start_hour}:00-{end_hour}:00)の詳細")
    print("=" * 80)
    
    target_start = target_date.replace(hour=start_hour, minute=0)
    target_end = target_date.replace(hour=end_hour, minute=0)
    
    for result in all_results:
        if target_start <= result['timestamp'] <= target_end:
            status_icon = "🔴" if result['state'] == "CONFIRMED" else "🟡" if result['state'] == "SUSPECTED" else "🟢"
            
            print(f"{status_icon} [{result['timestamp'].strftime('%H:%M:%S')}] "
                  f"価格:{result['price']:8.2f} | "
                  f"実体:{result['body']:6.4f} | "
                  f"レンジ:{result['hl_range']:6.4f} | "
                  f"スコア:{result['freeze_score']:3d} | "
                  f"連続:{result['consecutive']} | "
                  f"状態:{result['state']:10s}")
    
    # サマリー
    if events:
        print("\n" + "=" * 80)
        print("📌 イベントサマリー")
        print("=" * 80)
        for event in events:
            print(f"  {event['timestamp'].strftime('%m/%d %H:%M')} - {event['detection_msg']}")
    else:
        print("\n  ℹ️  この時間帯に停止イベントは検出されませんでした")
    
    print("\n" + "=" * 80)
    print("✅ バックテスト完了")
    print("=" * 80)


if __name__ == "__main__":
    # 画像の日時（2026-01-29 10:20頃）でテスト
    TARGET_SYMBOL = "NCSINASDAQ1002USD-USDT"
    TARGET_NAME = "NASDAQ100"
    TARGET_DATE = "2026-01-29"
    START_HOUR = 10  # 10:00から
    END_HOUR = 11    # 11:00まで
    
    run_backtest_specific_date(TARGET_SYMBOL, TARGET_NAME, TARGET_DATE, START_HOUR, END_HOUR)
