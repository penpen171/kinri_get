import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import time

# ==========================================
# ユーザー設定エリア
# ==========================================
SYMBOL = "NCCOGOLD2USD-USDT"   # 対象シンボル
START_DATE_STR = "2026-01-01"  # 取得開始日

# 取得したい時間枠 (JST)
# 枠1: 早朝の仕込み・決済ゾーン
MORNING_START = (5, 30)
MORNING_END = (7, 0)

# 枠2: 寄り付きのトレンド判定ゾーン (広めに8:00-8:15)
OPEN_START = (8, 0)
OPEN_END = (8, 15)

# 保存ファイル名
OUTPUT_FILENAME = "bingx_gold_1min_full_detail.csv"

# ==========================================
# API設定
# ==========================================
BASE_URL = "https://open-api.bingx.com"
JST = timezone(timedelta(hours=9))

def get_klines_raw(symbol, start_ts, end_ts):
    """BingX APIから指定範囲のKラインを取得"""
    url = BASE_URL + "/openApi/swap/v2/quote/klines"
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": int(start_ts * 1000),
        "endTime": int(end_ts * 1000),
        "limit": 1440
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        if data.get("code") == 0 and data.get("data"):
            return data["data"]
        return []
    except Exception as e:
        print(f"Connection Error: {e}")
        return []

def main():
    start_date = datetime.strptime(START_DATE_STR, "%Y-%m-%d").replace(tzinfo=JST)
    now = datetime.now(JST)
    current_date = start_date
    
    all_records = []
    
    print(f"--- Full 1-Min Data Collection Started ---")
    print(f"Symbol: {SYMBOL}")
    print(f"Targets: {MORNING_START[0]}:{MORNING_START[1]:02d}-{MORNING_END[0]}:{MORNING_END[1]:02d} AND {OPEN_START[0]}:{OPEN_START[1]:02d}-{OPEN_END[0]}:{OPEN_END[1]:02d}")
    print("Fetching data... (Ctrl+C to stop manually)\n")

    try:
        while current_date < now:
            date_str = current_date.strftime("%Y-%m-%d")
            
            # 時間枠の定義 (JST)
            m_start = current_date.replace(hour=MORNING_START[0], minute=MORNING_START[1], second=0, microsecond=0)
            m_end = current_date.replace(hour=MORNING_END[0], minute=MORNING_END[1], second=0, microsecond=0)
            
            o_start = current_date.replace(hour=OPEN_START[0], minute=OPEN_START[1], second=0, microsecond=0)
            o_end = current_date.replace(hour=OPEN_END[0], minute=OPEN_END[1], second=0, microsecond=0)
            
            # 未来の日付なら終了
            if m_start > now:
                break
            
            # データ取得 (Morning)
            m_data = get_klines_raw(SYMBOL, m_start.timestamp(), m_end.timestamp())
            # データ取得 (Open)
            o_data = get_klines_raw(SYMBOL, o_start.timestamp(), o_end.timestamp())
            
            daily_data = m_data + o_data
            
            if daily_data:
                for kline in daily_data:
                    # タイムスタンプ変換
                    ts = int(kline["time"])
                    dt_utc = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                    dt_jst = dt_utc.astimezone(JST)
                    
                    # セッション名の付与
                    time_val = dt_jst.time()
                    session_label = "OTHER"
                    
                    # 時間比較用のオブジェクト作成
                    t_val = time_val
                    t_m_start = m_start.time()
                    t_m_end = m_end.time()
                    t_o_start = o_start.time()
                    t_o_end = o_end.time()

                    if t_m_start <= t_val <= t_m_end:
                        session_label = "MORNING"
                    elif t_o_start <= t_val <= t_o_end:
                        session_label = "OPEN"
                    
                    all_records.append({
                        "Date": dt_jst.strftime("%Y-%m-%d"),
                        "Time": dt_jst.strftime("%H:%M:%S"),
                        "Session": session_label,
                        "Open": float(kline["open"]),
                        "High": float(kline["high"]),
                        "Low": float(kline["low"]),
                        "Close": float(kline["close"]),
                        "Volume": float(kline["volume"])
                    })
                
                print(f"[{date_str}] OK - {len(daily_data)} bars collected")
            else:
                print(f"[{date_str}] No data (Weekend/Holiday?)")
                
            current_date += timedelta(days=1)
            time.sleep(0.15) # サーバー負荷軽減

    except KeyboardInterrupt:
        print("\nStopped by user.")
    
    # 保存処理
    if all_records:
        df = pd.DataFrame(all_records)
        # 日付と時間でソート
        df = df.sort_values(["Date", "Time"])
        
        df.to_csv(OUTPUT_FILENAME, index=False)
        print(f"\n[Done] Saved {len(df)} rows to {OUTPUT_FILENAME}")
        
        # 簡易確認
        print(f"Top 3 rows:\n{df.head(3)}")
    else:
        print("\nNo records found to save.")

if __name__ == "__main__":
    main()
