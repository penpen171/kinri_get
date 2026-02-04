# backtest_specific_time.py
# 特定の日時のデータを分析

import requests
import time
from datetime import datetime, timedelta
from collections import deque
import statistics

BASE_URL = "https://open-api.bingx.com"
ENDPOINT = "/openApi/swap/v3/quote/klines"

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
            'detection_msg': detection_msg,
            'baseline_vol': statistics.median(self.volatility_history) if len(self.volatility_history) >= 20 else 0
        }


def fetch_data_around_time(symbol, target_time_str):
    """指定時刻の前後のデータを取得"""
    target_time = datetime.strptime(target_time_str, "%Y-%m-%d %H:%M")
    
    print("=" * 80)
    print(f"📥 データ取得: {target_time.strftime('%Y年%m月%d日 %H:%M')} の前後")
    print("=" * 80)
    
    # 目標時刻の2時間前から1時間後までのデータを取得
    start_time = target_time - timedelta(hours=2)
    end_time = target_time + timedelta(hours=1)
    
    # まず現在時刻との差を計算
    now = datetime.now()
    hours_ago = (now - target_time).total_seconds() / 3600
    
    print(f"   目標時刻: {target_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"   現在時刻: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"   差分: 約{hours_ago:.1f}時間前")
    
    # 現在から逆算して必要な本数を計算
    # 目標時刻の2時間前から1時間後 = 3時間分 = 180本
    minutes_needed = int((now - start_time).total_seconds() / 60)
    
    print(f"   取得必要本数: {minutes_needed}本（約{minutes_needed/60:.1f}時間分）")
    
    try:
        # 可能な限り多くのデータを取得
        limit = min(minutes_needed, 1000)
        
        params = {
            "symbol": symbol,
            "interval": "1m",
            "limit": limit
        }
        
        print(f"\n   APIリクエスト: limit={limit}")
        
        response = requests.get(f"{BASE_URL}{ENDPOINT}", params=params, timeout=10)
        data = response.json()
        
        if data.get("code") == 0 and data.get("data"):
            all_candles = []
            for c in data['data']:
                candle_time = datetime.fromtimestamp(int(c['time']) / 1000)
                candle = {
                    'timestamp': candle_time,
                    'open': float(c['open']),
                    'high': float(c['high']),
                    'low': float(c['low']),
                    'close': float(c['close']),
                    'volume': float(c.get('volume', 0))
                }
                all_candles.append(candle)
            
            # 時刻でフィルタリング
            filtered_candles = [c for c in all_candles if start_time <= c['timestamp'] <= end_time]
            
            print(f"\n✅ 取得成功:")
            print(f"   全取得: {len(all_candles)}本")
            if all_candles:
                print(f"   最古: {all_candles[0]['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   最新: {all_candles[-1]['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            
            print(f"   目標範囲内: {len(filtered_candles)}本")
            if filtered_candles:
                print(f"   範囲: {filtered_candles[0]['timestamp'].strftime('%H:%M')} ～ {filtered_candles[-1]['timestamp'].strftime('%H:%M')}")
            
            if len(filtered_candles) > 0:
                return filtered_candles
            else:
                print("\n⚠️ 目標時刻のデータが範囲外です。全データを返します。")
                return all_candles
                
        else:
            print(f"\n❌ APIエラー: {data}")
            return None
            
    except Exception as e:
        print(f"\n❌ 例外エラー: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_analysis(symbol, name, target_time_str):
    """分析実行"""
    print("=" * 80)
    print(f"🔬 バックテスト: {name}")
    print(f"   目標時刻: {target_time_str}")
    print("=" * 80)
    
    # データ取得
    candles = fetch_data_around_time(symbol, target_time_str)
    
    if not candles or len(candles) < 30:
        print("\n❌ 十分なデータが取得できませんでした")
        return
    
    target_time = datetime.strptime(target_time_str, "%Y-%m-%d %H:%M")
    
    # 検知器で分析
    print("\n" + "=" * 80)
    print("📊 停止検知分析")
    print("=" * 80)
    
    detector = BacktestFreezeDetector(symbol, name)
    
    events = []
    
    for i, candle in enumerate(candles):
        result = detector.analyze_candle(candle, i)
        
        # 重要なイベントを記録
        if result['detection_msg']:
            events.append(result)
            print(f"\n[{result['timestamp'].strftime('%m/%d %H:%M:%S')}] {result['detection_msg']}")
            print(f"   価格: {result['price']:.2f}")
            print(f"   スコア: {result['freeze_score']}")
            print(f"   連続: {result['consecutive']}回")
    
    # 目標時刻の前後30分を詳細表示
    print("\n" + "=" * 80)
    print(f"📋 目標時刻({target_time.strftime('%H:%M')})前後の詳細")
    print("=" * 80)
    
    window_start = target_time - timedelta(minutes=30)
    window_end = target_time + timedelta(minutes=30)
    
    detector2 = BacktestFreezeDetector(symbol, name)
    
    for i, candle in enumerate(candles):
        result = detector2.analyze_candle(candle, i)
        
        if window_start <= candle['timestamp'] <= window_end:
            status_icon = "🔴" if result['state'] == "CONFIRMED" else "🟡" if result['state'] == "SUSPECTED" else "🟢"
            
            # 目標時刻付近は★マーク
            time_mark = "★" if abs((candle['timestamp'] - target_time).total_seconds()) < 300 else " "
            
            print(f"{status_icon}{time_mark} [{result['timestamp'].strftime('%H:%M:%S')}] "
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


if __name__ == "__main__":
    # 2026年2月3日 5:05頃を分析
    TARGET_SYMBOL = "NCSINASDAQ1002USD-USDT"
    TARGET_NAME = "NASDAQ100"
    TARGET_TIME = "2026-02-03 05:05"
    
    run_analysis(TARGET_SYMBOL, TARGET_NAME, TARGET_TIME)
