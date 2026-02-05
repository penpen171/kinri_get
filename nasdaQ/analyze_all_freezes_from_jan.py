# analyze_all_freezes_from_jan.py
# 1月1日から全ての停止イベントをリスト化

import requests
import time
from datetime import datetime, timedelta, timezone
from collections import deque
import statistics
import csv

BASE_URL = "https://open-api.bingx.com"
ENDPOINT_V2 = "/openApi/swap/v2/quote/klines"
JST = timezone(timedelta(hours=9))

# 出力ファイル
OUTPUT_CSV = "freeze_events_report.csv"


class FreezeEventDetector:
    """停止イベント検知専用クラス"""
    
    def __init__(self):
        self.volatility_history = deque(maxlen=100)
        self.consecutive_high_scores = 0
        self.state = "NORMAL"
        self.freeze_start_index = None
        self.freeze_start_time = None
        self.freeze_start_price = None
        self.all_events = []
        
    def add_candle(self, candle):
        hl_range = candle['high'] - candle['low']
        self.volatility_history.append(hl_range)
        
    def calculate_freeze_score(self):
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
    
    def analyze_candle(self, candle, index):
        self.add_candle(candle)
        freeze_score = self.calculate_freeze_score()
        
        # スコアのカウント
        if freeze_score >= 60:
            self.consecutive_high_scores += 1
        else:
            self.consecutive_high_scores = 0
        
        # 状態遷移
        if self.state == "NORMAL":
            if self.consecutive_high_scores >= 3:
                self.state = "SUSPECTED"
                
        elif self.state == "SUSPECTED":
            if self.consecutive_high_scores >= 5:
                self.state = "CONFIRMED"
                self.freeze_start_index = index - 4  # 5本前から
                self.freeze_start_time = candle['timestamp']
                self.freeze_start_price = candle['close']
            elif freeze_score < 40:
                self.state = "NORMAL"
                self.consecutive_high_scores = 0
                
        elif self.state == "CONFIRMED":
            if freeze_score < 40:
                # 停止解消
                duration = (candle['timestamp'] - self.freeze_start_time).total_seconds() / 60
                price_diff = candle['close'] - self.freeze_start_price
                direction = "UP" if price_diff > 0 else "DOWN"
                
                event = {
                    'start_time': self.freeze_start_time,
                    'end_time': candle['timestamp'],
                    'duration_minutes': duration,
                    'start_price': self.freeze_start_price,
                    'end_price': candle['close'],
                    'price_change': price_diff,
                    'direction': direction,
                    'date': self.freeze_start_time.strftime('%Y-%m-%d'),
                    'start_time_str': self.freeze_start_time.strftime('%H:%M:%S'),
                    'end_time_str': candle['timestamp'].strftime('%H:%M:%S'),
                    'day_of_week': self.freeze_start_time.strftime('%A')
                }
                
                self.all_events.append(event)
                
                self.state = "NORMAL"
                self.consecutive_high_scores = 0


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
            return []
            
    except Exception as e:
        print(f"  エラー: {e}")
        return []


def analyze_entire_period(symbol, name, start_date_str, end_date_str=None):
    """指定期間の全データを分析"""
    print("=" * 80)
    print(f"🔬 全期間停止イベント分析")
    print(f"   銘柄: {name} ({symbol})")
    print("=" * 80)
    
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=JST, hour=0, minute=0)
    
    if end_date_str:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=JST, hour=23, minute=59)
    else:
        end_date = datetime.now(JST)
    
    print(f"\n📅 分析期間:")
    print(f"   開始: {start_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"   終了: {end_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"   日数: {(end_date - start_date).days}日")
    
    # 検知器を初期化
    detector = FreezeEventDetector()
    
    # 日ごとにデータ取得
    current_date = start_date
    total_candles = 0
    
    print(f"\n📥 データ取得中...")
    print("-" * 80)
    
    while current_date < end_date:
        day_start = current_date
        day_end = current_date + timedelta(days=1)
        
        if day_end > end_date:
            day_end = end_date
        
        # データ取得
        candles = get_klines_v2(symbol, day_start, day_end)
        
        if candles:
            for i, candle in enumerate(candles):
                detector.analyze_candle(candle, total_candles + i)
            
            total_candles += len(candles)
            print(f"  {current_date.strftime('%Y-%m-%d')}: {len(candles):4d}本 | 累計停止: {len(detector.all_events):3d}件")
        else:
            print(f"  {current_date.strftime('%Y-%m-%d')}: データなし")
        
        current_date += timedelta(days=1)
        time.sleep(0.1)  # API制限対策
    
    print("-" * 80)
    print(f"✅ データ取得完了: 合計 {total_candles:,}本のローソク足")
    
    return detector.all_events


def save_events_to_csv(events, filename):
    """イベントをCSVに保存"""
    if not events:
        print("\n  停止イベントが見つかりませんでした")
        return
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            '日付', '曜日', '開始時刻', '終了時刻', '継続時間(分)', 
            '開始価格', '終了価格', '価格変動', '方向', '変動率(%)'
        ])
        
        for event in events:
            change_pct = (event['price_change'] / event['start_price']) * 100
            writer.writerow([
                event['date'],
                event['day_of_week'],
                event['start_time_str'],
                event['end_time_str'],
                f"{event['duration_minutes']:.1f}",
                f"{event['start_price']:.2f}",
                f"{event['end_price']:.2f}",
                f"{event['price_change']:+.2f}",
                event['direction'],
                f"{change_pct:+.3f}"
            ])
    
    print(f"\n💾 CSVファイルに保存: {filename}")


def display_summary(events):
    """サマリーを表示"""
    if not events:
        return
    
    print("\n" + "=" * 80)
    print("📊 停止イベントサマリー")
    print("=" * 80)
    
    # 基本統計
    total = len(events)
    avg_duration = statistics.mean([e['duration_minutes'] for e in events])
    avg_change = statistics.mean([abs(e['price_change']) for e in events])
    
    up_count = sum(1 for e in events if e['direction'] == 'UP')
    down_count = sum(1 for e in events if e['direction'] == 'DOWN')
    
    print(f"\n総停止回数: {total}回")
    print(f"平均停止時間: {avg_duration:.1f}分")
    print(f"平均価格変動: {avg_change:.2f}")
    print(f"上昇解消: {up_count}回 ({up_count/total*100:.1f}%)")
    print(f"下落解消: {down_count}回 ({down_count/total*100:.1f}%)")
    
    # 時間帯分析
    print("\n" + "-" * 80)
    print("⏰ 停止発生時間帯の分布")
    print("-" * 80)
    
    hours = {}
    for event in events:
        hour = event['start_time'].hour
        hours[hour] = hours.get(hour, 0) + 1
    
    for hour in sorted(hours.keys()):
        count = hours[hour]
        bar = "█" * (count * 2)
        print(f"  {hour:02d}時台: {bar} {count}回")
    
    # 曜日分析
    print("\n" + "-" * 80)
    print("📅 曜日別の分布")
    print("-" * 80)
    
    days = {}
    for event in events:
        day = event['day_of_week']
        days[day] = days.get(day, 0) + 1
    
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for day in day_order:
        if day in days:
            count = days[day]
            bar = "█" * (count * 2)
            print(f"  {day:10s}: {bar} {count}回")
    
    # トップ10の大きな変動
    print("\n" + "-" * 80)
    print("💥 価格変動が大きかった停止イベント TOP10")
    print("-" * 80)
    
    sorted_events = sorted(events, key=lambda e: abs(e['price_change']), reverse=True)[:10]
    
    for i, event in enumerate(sorted_events, 1):
        direction_icon = "⬆️" if event['direction'] == 'UP' else "⬇️"
        print(f"  #{i:2d} [{event['date']} {event['start_time_str']}] "
              f"{direction_icon} {event['price_change']:+7.2f} ({event['duration_minutes']:.1f}分停止)")


def display_all_events(events):
    """全イベントを表形式で表示"""
    print("\n" + "=" * 80)
    print("📋 全停止イベント一覧")
    print("=" * 80)
    print(f"\n{'No':>3} {'日付':>10} {'曜日':>9} {'開始時刻':>8} {'終了時刻':>8} "
          f"{'時間':>6} {'価格変動':>9} {'方向':>4}")
    print("-" * 80)
    
    for i, event in enumerate(events, 1):
        direction_icon = "⬆️" if event['direction'] == 'UP' else "⬇️"
        print(f"{i:3d} {event['date']:>10} {event['day_of_week']:>9} "
              f"{event['start_time_str']:>8} {event['end_time_str']:>8} "
              f"{event['duration_minutes']:5.1f}分 {event['price_change']:+8.2f} {direction_icon}")


if __name__ == "__main__":
    # 設定
    TARGET_SYMBOL = "NCSINASDAQ1002USD-USDT"
    TARGET_NAME = "NASDAQ100"
    START_DATE = "2026-01-01"
    END_DATE = None  # Noneで現在まで
    
    # 分析実行
    events = analyze_entire_period(TARGET_SYMBOL, TARGET_NAME, START_DATE, END_DATE)
    
    # 結果表示
    display_summary(events)
    display_all_events(events)
    
    # CSV保存
    save_events_to_csv(events, OUTPUT_CSV)
    
    print("\n" + "=" * 80)
    print("✅ 分析完了")
    print("=" * 80)
