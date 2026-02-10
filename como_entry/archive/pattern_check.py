import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import time

# ==========================================
# 確定したシンボル設定
# ==========================================
SYMBOL = "NCCOGOLD2USD-USDT"   # API検索で見つかった正しいシンボル
START_DATE_STR = "2026-01-01"  # 開始日

# ターゲット時間枠 (日本時間)
TARGET_START_HOUR = 5
TARGET_START_MINUTE = 30
TARGET_END_HOUR = 7
TARGET_END_MINUTE = 0

# API設定
BASE_URL = "https://open-api.bingx.com"
JST = timezone(timedelta(hours=9))

def get_klines(symbol, start_ts, end_ts):
    """
    Kラインデータを取得
    """
    # エンドポイント: V2 Swap
    url = BASE_URL + "/openApi/swap/v2/quote/klines"
    
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": int(start_ts * 1000),
        "endTime": int(end_ts * 1000),
        "limit": 1440
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get("code") == 0:
            return data.get("data", [])
        else:
            # エラー詳細を表示しない（ループを続けるため）
            # print(f"API Code: {data.get('code')}") 
            return []
    except Exception as e:
        print(f"Connection Error: {e}")
        return []

def main():
    start_date = datetime.strptime(START_DATE_STR, "%Y-%m-%d").replace(tzinfo=JST)
    now = datetime.now(JST)
    current_date = start_date
    
    records = []
    
    print(f"--- Analysis Start: {SYMBOL} ---")
    print(f"Period: {START_DATE_STR} ~ Present")
    print(f"Time: {TARGET_START_HOUR}:{TARGET_START_MINUTE:02d} ~ {TARGET_END_HOUR}:{TARGET_END_MINUTE:02d} (JST)\n")
    
    while current_date < now:
        # ターゲット時間の計算
        t_start = current_date.replace(hour=TARGET_START_HOUR, minute=TARGET_START_MINUTE, second=0, microsecond=0)
        t_end = current_date.replace(hour=TARGET_END_HOUR, minute=TARGET_END_MINUTE, second=0, microsecond=0)
        
        # 未来の日付は除外
        if t_start > now:
            break
            
        # データ取得
        klines = get_klines(SYMBOL, t_start.timestamp(), t_end.timestamp())
        
        if klines:
            df = pd.DataFrame(klines)
            
            # APIのレスポンス形式チェック
            # {"time": ..., "open": ...} の辞書リスト形式を想定
            if "time" in df.columns:
                # 数値型変換
                df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
                
                # *** 修正ポイント: tz_convert を使用 ***
                df["time"] = df["time"].dt.tz_convert(JST)
                
                df["low"] = df["low"].astype(float)
                df["high"] = df["high"].astype(float)
                
                # 時間フィルタリング
                mask = (df["time"] >= t_start) & (df["time"] <= t_end)
                period_df = df.loc[mask].copy() # copy()で警告回避
                
                if not period_df.empty:
                    min_price = period_df["low"].min()
                    max_price = period_df["high"].max()
                    diff = max_price - min_price
                    
                    min_row = period_df.loc[period_df["low"].idxmin()]
                    min_time_str = min_row["time"].strftime("%H:%M")
                    
                    records.append({
                        "Date": t_start.strftime("%Y-%m-%d"),
                        "Min_Time": min_time_str,
                        "Min_Price": min_price,
                        "Price_Diff": diff
                    })
                    print(f"[{t_start.date()}] Min: {min_price:.2f} at {min_time_str}")
                else:
                    # 時間内データなし（休場日など）
                    pass 
            else:
                print(f"[{t_start.date()}] Unexpected data format.")
        else:
            # データなし（休場日など）
            print(f"[{t_start.date()}] No data available.")
            
        current_date += timedelta(days=1)
        time.sleep(0.2)

    # 保存と集計
    if records:
        df_result = pd.DataFrame(records)
        csv_name = "bingx_gold_stats_final.csv"
        df_result.to_csv(csv_name, index=False)
        print(f"\nSaved to {csv_name}")
        
        print("\n--- Summary: Top 5 Lowest Price Times ---")
        print(df_result["Min_Time"].value_counts().head(5))
    else:
        print("\nNo records processed. Please check if the market was open during these dates.")

if __name__ == "__main__":
    main()
