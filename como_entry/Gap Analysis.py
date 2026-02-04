import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import time

# ==========================================
# 設定
# ==========================================
SYMBOL = "NCCOGOLD2USD-USDT"
START_DATE_STR = "2026-01-01"

# ギャップとみなす最小時間（分）
# 通常のメンテナンスや週末を検出するため、15分以上のデータ欠損を「休場」と定義
GAP_THRESHOLD_MINUTES = 15 

BASE_URL = "https://open-api.bingx.com"
JST = timezone(timedelta(hours=9))

def get_all_klines(symbol, start_ts, end_ts):
    """
    指定期間の全Kラインデータを取得（ページネーションなしの簡易版）
    長期間の場合は分割取得が必要だが、ここでは日次ループで蓄積する
    """
    url = BASE_URL + "/openApi/swap/v2/quote/klines"
    all_data = []
    
    # 1日ごとに取得して結合する（確実に全データを拾うため）
    current_ts = start_ts
    while current_ts < end_ts:
        # 1回のリクエストで最大1440分（24時間）取得可能
        req_end = min(current_ts + (24 * 3600), end_ts)
        
        params = {
            "symbol": symbol,
            "interval": "1m",
            "startTime": int(current_ts * 1000),
            "endTime": int(req_end * 1000),
            "limit": 1440
        }
        
        try:
            res = requests.get(url, params=params)
            data = res.json()
            if data.get("code") == 0 and data.get("data"):
                # データは新しい順に来ることが多いので逆順にする等の注意が必要だが
                # ここではそのまま受け取り、後でPandasでソートする
                batch = data["data"]
                all_data.extend(batch)
        except Exception:
            pass
            
        current_ts = req_end
        time.sleep(0.1) # レート制限対策
        
    return all_data

def main():
    start_date = datetime.strptime(START_DATE_STR, "%Y-%m-%d").replace(tzinfo=JST)
    now = datetime.now(JST)
    
    print(f"--- Flexible Gap Analysis: {SYMBOL} ---")
    print("Fetching data (this may take a moment)...")
    
    # 1. データの一括取得
    raw_data = get_all_klines(SYMBOL, start_date.timestamp(), now.timestamp())
    
    if not raw_data:
        print("No data found.")
        return

    # 2. DataFrame化と整理
    df = pd.DataFrame(raw_data)
    
    # APIのレスポンス形式に合わせてカラム処理（辞書型前提）
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True).dt.tz_convert(JST)
        df["close"] = df["close"].astype(float)
        df["open"] = df["open"].astype(float)
        
        # 時間順にソート（必須）
        df = df.sort_values("time").reset_index(drop=True)
        
        # 重複削除（念のため）
        df = df.drop_duplicates(subset="time")
        
        # 3. ギャップ検出ロジック
        # 前の行との時間差を計算
        df["time_diff"] = df["time"].diff()
        
        # 閾値（15分）以上の時間差がある行を特定
        # time_diff が大きい行 = ギャップ明けの最初の足（Open）
        gap_rows = df[df["time_diff"] > timedelta(minutes=GAP_THRESHOLD_MINUTES)]
        
        results = []
        
        for idx in gap_rows.index:
            # ギャップ明け（Open）のデータ
            open_row = df.loc[idx]
            
            # ギャップ入り（Close）のデータ = その1つ前の行
            # ※ indexは連続しているので idx-1 で参照可能
            close_row = df.loc[idx - 1]
            
            gap_duration = open_row["time"] - close_row["time"]
            price_gap = open_row["open"] - close_row["close"]
            
            # ギャップの種類判定
            gap_type = "Daily Maint."
            if gap_duration > timedelta(hours=24):
                gap_type = "Weekend/Holiday"
            
            results.append({
                "Close_Time": close_row["time"].strftime("%Y-%m-%d %H:%M"),
                "Open_Time": open_row["time"].strftime("%Y-%m-%d %H:%M"),
                "Duration": str(gap_duration),
                "Close_Price": close_row["close"],
                "Open_Price": open_row["open"],
                "Gap_Value": price_gap,
                "Gap_Type": gap_type
            })
            
            # 進捗表示
            print(f"Found {gap_type} Gap: {close_row['time'].date()} -> {open_row['time'].date()} | Gap: {price_gap:+.2f}")

        # 4. 結果保存
        if results:
            res_df = pd.DataFrame(results)
            res_df.to_csv("bingx_flexible_gaps.csv", index=False)
            print("\nAnalysis Complete. Saved to bingx_flexible_gaps.csv")
            
            # 統計
            print("\n--- Statistics ---")
            print(f"Total Gaps Found: {len(res_df)}")
            print(f"Average Gap Size: {res_df['Gap_Value'].abs().mean():.2f}")
            print("\nGap Direction:")
            print(res_df["Gap_Value"].apply(lambda x: "UP" if x > 0 else "DOWN").value_counts())
        else:
            print("No significant gaps found.")
            
    else:
        print("Data format error (columns mismatch).")

if __name__ == "__main__":
    main()
