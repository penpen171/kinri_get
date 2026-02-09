import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import time

# ==========================================
# 設定
# ==========================================
SYMBOL = "NCCOGOLD2USD-USDT"
START_DATE_STR = "2026-01-01"
GAP_THRESHOLD_MINUTES = 15  # 休場判定用
CHECK_WINDOW_MINUTES = 5    # 開場後の監視期間 (5分)

BASE_URL = "https://open-api.bingx.com"
JST = timezone(timedelta(hours=9))

def get_all_klines(symbol, start_ts, end_ts):
    # 前回のコードと同様、データを一括取得
    url = BASE_URL + "/openApi/swap/v2/quote/klines"
    all_data = []
    current_ts = start_ts
    while current_ts < end_ts:
        req_end = min(current_ts + (24 * 3600), end_ts)
        params = {
            "symbol": symbol, "interval": "1m",
            "startTime": int(current_ts * 1000), "endTime": int(req_end * 1000), "limit": 1440
        }
        try:
            res = requests.get(url, params=params)
            data = res.json()
            if data.get("code") == 0 and data.get("data"):
                all_data.extend(data["data"])
        except Exception: pass
        current_ts = req_end
        time.sleep(0.1)
    return all_data

def main():
    start_date = datetime.strptime(START_DATE_STR, "%Y-%m-%d").replace(tzinfo=JST)
    now = datetime.now(JST)
    
    print(f"--- 5-Minute Trend Analysis: {SYMBOL} ---")
    
    # 1. データ取得
    raw_data = get_all_klines(SYMBOL, start_date.timestamp(), now.timestamp())
    if not raw_data: return

    df = pd.DataFrame(raw_data)
    if "time" in df.columns:
        # データ整理
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True).dt.tz_convert(JST)
        df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
        df = df.sort_values("time").reset_index(drop=True).drop_duplicates(subset="time")
        
        # 2. ギャップ検出
        df["time_diff"] = df["time"].diff()
        gap_indices = df[df["time_diff"] > timedelta(minutes=GAP_THRESHOLD_MINUTES)].index
        
        results = []
        
        for idx in gap_indices:
            # クローズ情報
            close_row = df.loc[idx - 1]
            close_price = close_row["close"]
            
            # オープン後の5分間のデータ取得
            # idx (Openの瞬間) から idx+4 (5分後) までのデータを確認
            # ※データの欠損がない前提だが、インデックス範囲外エラーを防ぐ
            end_idx = min(idx + CHECK_WINDOW_MINUTES, len(df))
            open_window_df = df.iloc[idx : end_idx]
            
            if open_window_df.empty: continue

            # 開場5分間の最安値
            window_low = open_window_df["low"].min()
            window_open_price = open_window_df.iloc[0]["open"]
            
            # --- 判定ロジック ---
            # 開場5分間の最安値が、閉場価格よりも上にあれば「強いUP」
            # 閉場価格を一度でも割ったら「DOWN (窓埋め/下落)」
            if window_low >= close_price:
                trend = "UP"
            else:
                trend = "DOWN"
            
            # ギャップ自体の方向（参考用）
            gap_raw = window_open_price - close_price
            
            results.append({
                "Date": open_window_df.iloc[0]["time"].strftime("%Y-%m-%d"),
                "Close_Time": close_row["time"].strftime("%H:%M"),
                "Open_Time": open_window_df.iloc[0]["time"].strftime("%H:%M"),
                "Close_Price": close_price,
                "Open_5min_Low": window_low,
                "Gap_Raw": gap_raw,
                "5min_Trend": trend
            })
            
            print(f"[{open_window_df.iloc[0]['time'].date()}] Close:{close_price:.1f} -> 5mLow:{window_low:.1f} | Trend:{trend}")

        # 3. 保存
        if results:
            res_df = pd.DataFrame(results)
            res_df.to_csv("bingx_gold_5min_trend.csv", index=False)
            print("\nSaved to bingx_gold_5min_trend.csv")
            print(res_df["5min_Trend"].value_counts())

if __name__ == "__main__":
    main()
