# market_direction_calendar.py
# 開場後の方向性をカレンダー表示（🟢上昇 / 🔴下落）

import pandas as pd
import calendar
from datetime import datetime, timedelta
from collections import defaultdict

# 設定
INPUT_FILE = "gold_1min_20260201_20260209.csv"  # 入力CSVファイル
START_DATE = None  # 開始日（Noneの場合は全期間）
END_DATE = None    # 終了日（Noneの場合は全期間）
OPEN_START_TIME = "08:00:00"  # 開場開始時刻
OPEN_END_TIME = "08:15:00"    # 開場終了時刻（判定用）

def analyze_daily_direction(input_file, start_date=None, end_date=None):
    """
    開場後の価格方向を日ごとに判定
    """
    
    print("=" * 80)
    print("📊 開場後の方向性分析 & カレンダー表示")
    print("=" * 80)
    
    # データ読み込み
    print(f"\n📂 読み込み中: {input_file}")
    df = pd.read_csv(input_file)
    
    # 日時変換
    if '日時' in df.columns:
        df['DateTime'] = pd.to_datetime(df['日時'])
    else:
        df['DateTime'] = pd.to_datetime(df['日付'] + ' ' + df['時刻'])
    
    df['Date'] = df['DateTime'].dt.date
    df['Time'] = df['DateTime'].dt.time
    
    # 期間フィルタ
    if start_date:
        df = df[df['DateTime'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['DateTime'] <= pd.to_datetime(end_date) + timedelta(days=1)]
    
    print(f"✅ データ期間: {df['DateTime'].min().date()} ～ {df['DateTime'].max().date()}")
    
    # 開場セッションのデータを抽出
    open_start = pd.to_datetime(OPEN_START_TIME).time()
    open_end = pd.to_datetime(OPEN_END_TIME).time()
    
    open_session = df[
        (df['Time'] >= open_start) & 
        (df['Time'] <= open_end)
    ].copy()
    
    print(f"\n🔍 開場セッション分析中（{OPEN_START_TIME} ～ {OPEN_END_TIME}）...")
    
    # 日ごとの方向性を判定
    daily_results = {}
    
    for date in open_session['Date'].unique():
        day_data = open_session[open_session['Date'] == date].sort_values('DateTime')
        
        if len(day_data) < 2:
            continue
        
        # 開場直後の価格（最初の足の始値）
        open_price = day_data.iloc[0]['始値']
        
        # 開場15分後の価格（最後の足の終値）
        close_price = day_data.iloc[-1]['終値']
        
        # 方向判定
        change = close_price - open_price
        change_pct = (change / open_price) * 100 if open_price > 0 else 0
        
        direction = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
        
        daily_results[date] = {
            'direction': direction,
            'change': change,
            'change_pct': change_pct,
            'open': open_price,
            'close': close_price
        }
    
    print(f"✅ {len(daily_results)}日分のデータを分析")
    
    return daily_results


def print_calendar(daily_results):
    """
    カレンダー形式で表示
    """
    
    if not daily_results:
        print("表示するデータがありません")
        return
    
    # 日付でグループ化（年月ごと）
    dates = sorted(daily_results.keys())
    
    # 年月ごとに整理
    months = defaultdict(list)
    for date in dates:
        year_month = (date.year, date.month)
        months[year_month].append(date)
    
    # 統計
    up_days = sum(1 for d in daily_results.values() if d['direction'] == "🟢")
    down_days = sum(1 for d in daily_results.values() if d['direction'] == "🔴")
    neutral_days = sum(1 for d in daily_results.values() if d['direction'] == "⚪")
    
    print("\n" + "=" * 80)
    print("📅 方向性カレンダー")
    print("=" * 80)
    print(f"\n🟢 上昇: {up_days}日 ({up_days/len(daily_results)*100:.1f}%)")
    print(f"🔴 下落: {down_days}日 ({down_days/len(daily_results)*100:.1f}%)")
    if neutral_days > 0:
        print(f"⚪ 横ばい: {neutral_days}日")
    
    # 月ごとにカレンダー表示
    for (year, month), month_dates in sorted(months.items()):
        print("\n" + "=" * 80)
        print(f"📆 {year}年{month}月")
        print("=" * 80)
        
        # カレンダーのヘッダー
        print("\n  月   火   水   木   金   土   日")
        print("-" * 40)
        
        # その月のカレンダー情報を取得
        cal = calendar.monthcalendar(year, month)
        
        # 週ごとに表示
        for week in cal:
            week_str = ""
            for day in week:
                if day == 0:
                    week_str += "     "  # 空白
                else:
                    current_date = datetime(year, month, day).date()
                    if current_date in daily_results:
                        symbol = daily_results[current_date]['direction']
                        week_str += f" {day:2d}{symbol} "
                    else:
                        week_str += f" {day:2d}  "  # データなし
            print(week_str)
        
        # 月次サマリー
        month_up = sum(1 for d in month_dates if daily_results[d]['direction'] == "🟢")
        month_down = sum(1 for d in month_dates if daily_results[d]['direction'] == "🔴")
        
        print(f"\n月次集計: 🟢{month_up}日 🔴{month_down}日")
    
    # 詳細データテーブル
    print("\n" + "=" * 80)
    print("📋 詳細データ")
    print("=" * 80)
    
    detail_df = pd.DataFrame([
        {
            '日付': date.strftime('%Y-%m-%d'),
            '曜日': ['月','火','水','木','金','土','日'][date.weekday()],
            '方向': data['direction'],
            '変動': f"{data['change']:+.2f}",
            '変動率': f"{data['change_pct']:+.2f}%",
            '開場': f"{data['open']:.2f}",
            '終了': f"{data['close']:.2f}"
        }
        for date, data in sorted(daily_results.items())
    ])
    
    print(detail_df.to_string(index=False))
    
    # CSV保存
    output_file = "market_direction_calendar.csv"
    detail_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n💾 詳細データを保存: {output_file}")


def main():
    """
    メイン処理
    """
    daily_results = analyze_daily_direction(INPUT_FILE, START_DATE, END_DATE)
    
    if daily_results:
        print_calendar(daily_results)
        
        print("\n" + "=" * 80)
        print("✅ 完了")
        print("=" * 80)
    else:
        print("\n⚠️  分析可能なデータがありませんでした")


if __name__ == "__main__":
    main()
