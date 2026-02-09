import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import time

# ==========================================
# 設定
# ==========================================
SYMBOL = "NCCOGOLD2USD-USDT"   # 正しいシンボル
START_DATE_STR = "2026-01-01"  # 集計開始日

# ターゲット時間枠 (JST 5:30 ~ 7:00)
TARGET_START_HOUR = 5
TARGET_START_MINUTE = 30
TARGET_END_HOUR = 7
TARGET_END_MINUTE = 0

BASE_URL = "https://open-api.bingx.com"
JST = timezone(timedelta(hours=9))

def get_klines(symbol, start_ts, end_ts):
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
        return []
    except Exception:
        return []

def main():
    start_date = datetime.strptime(START_DATE_STR, "%Y-%m-%d").replace(tzinfo=JST)
    now = datetime.now(JST)
    current_date = start_date
    
    records = []
    
    print(f"--- High Price Analysis: {SYMBOL} ---")
    print(f"Period: {START_DATE_STR} ~ Present")
    print(f"Time: {TARGET_START_HOUR}:{TARGET_START_MINUTE:02d} ~ {TARGET_END_HOUR}:{TARGET_END_MINUTE:02d} (JST)\n")
    
    while current_date < now:
        t_start = current_date.replace(hour=TARGET_START_HOUR, minute=TARGET_START_MINUTE, second=0, microsecond=0)
        t_end = current_date.replace(hour=TARGET_END_HOUR, minute=TARGET_END_MINUTE, second=0, microsecond=0)
        
        if t_start > now: break
            
        klines = get_klines(SYMBOL, t_start.timestamp(), t_end.timestamp())
        
        if klines:
            df = pd.DataFrame(klines)
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True).dt.tz_convert(JST)
                df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
                
                # 時間フィルタリング
                mask = (df["time"] >= t_start) & (df["time"] <= t_end)
                period_df = df.loc[mask].copy()
                
                if not period_df.empty:
                    # ★ ここが変更点: 最高値の特定
                    max_price = period_df["high"].max()
                    min_price = period_df["low"].min()
                    volatility = max_price - min_price
                    
                    # 最高値をつけた時間を特定
                    max_row = period_df.loc[period_df["high"].idxmax()]
                    max_time_str = max_row["time"].strftime("%H:%M")
                    
                    records.append({
                        "Date": t_start.strftime("%Y-%m-%d"),
                        "Max_Time": max_time_str,      # 最高値の時間
                        "Max_Price": max_price,        # 最高値
                        "Volatility": volatility       # 変動幅
                    })
                    print(f"[{t_start.date()}] Max: {max_price:.2f} at {max_time_str}")
        else:
            print(f"[{t_start.date()}] No data.")
            
        current_date += timedelta(days=1)
        time.sleep(0.15) # API負荷軽減

    if records:
        df_res = pd.DataFrame(records)
        filename = "bingx_gold_highs.csv"
        df_res.to_csv(filename, index=False)
        print(f"\nSaved to {filename}")
        
        print("\n--- Summary: Top 5 Highest Price Times ---")
        print(df_res["Max_Time"].value_counts().head(5))
    else:
        print("\nNo records found.")

if __name__ == "__main__":
    main()
