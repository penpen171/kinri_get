import time
import os
import glob
import requests
import pandas as pd
from datetime import datetime

# このpyファイルの場所（viewer）を基準にする
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

API_URL = "https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures"
INTERVAL_TO_S = {"1h": 3600, "4h": 14400, "8h": 28800}


def find_catalog_file() -> str:
    # viewer フォルダ内の bitget_true_catalog_*.csv を検索して最新を使う
    pattern = os.path.join(BASE_DIR, "bitget_true_catalog_*.csv")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No catalog CSV found. Looked for: {pattern}")
    return files[0]


def load_catalog(path: str) -> pd.DataFrame:
    # Excel由来のBOMがある場合があるので utf-8-sig を優先
    df = pd.read_csv(path, encoding="utf-8-sig")

    # CSV: Symbol,Interval,Current_Rate(%),Daily_Rate(%),Exchange
    # 例: "AUCTION-USDT" -> "AUCTIONUSDT"（Bitget API側のsymbol表記に合わせる）
    df["symbol_api"] = df["Symbol"].astype(str).str.replace("-USDT", "USDT", regex=False)
    df["interval_s_B"] = df["Interval"].map(INTERVAL_TO_S)

    return df[["Symbol", "Interval", "symbol_api", "interval_s_B"]]


def fetch_bitget_tickers() -> pd.DataFrame:
    r = requests.get(API_URL, timeout=10).json()
    if r.get("code") != "00000":
        raise RuntimeError(f"Bitget API error: {r.get('msg')}")
    df = pd.DataFrame(r.get("data", []))

    cols = ["symbol", "fundingRate", "nextFundingTime", "lastPr"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


def evaluate_once(catalog_file: str) -> pd.DataFrame:
    now_ms = int(time.time() * 1000)

    cat = load_catalog(catalog_file)
    api = fetch_bitget_tickers()

    merged = cat.merge(api, left_on="symbol_api", right_on="symbol", how="left")

    # A: nextFundingTime(ms) -> remaining seconds
    merged["nextFundingTime_ms_A"] = pd.to_numeric(merged["nextFundingTime"], errors="coerce")
    merged["remaining_s_A"] = (merged["nextFundingTime_ms_A"] - now_ms) / 1000.0

    # 整合判定（許容幅）
    tol_s = 120  # ±2分
    merged["in_range_strict"] = (merged["remaining_s_A"] >= 0) & (merged["remaining_s_A"] <= merged["interval_s_B"])
    merged["in_range_tol"] = (merged["remaining_s_A"] >= -tol_s) & (merged["remaining_s_A"] <= merged["interval_s_B"] + tol_s)

    # 異常フラグ
    merged["flag_missing_A"] = merged["nextFundingTime_ms_A"].isna()
    merged["flag_negative_A"] = merged["remaining_s_A"] < -tol_s
    merged["flag_too_large_A"] = merged["remaining_s_A"] > (merged["interval_s_B"] + tol_s)

    merged["checked_at_jst"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    merged["catalog_file"] = os.path.basename(catalog_file)
    return merged


def main():
    catalog_file = find_catalog_file()
    df = evaluate_once(catalog_file)

    total = len(df)
    ok_tol = int(df["in_range_tol"].sum())
    miss = int(df["flag_missing_A"].sum())
    neg = int(df["flag_negative_A"].sum())
    large = int(df["flag_too_large_A"].sum())

    print("---- Bitget nextFundingTime(A) vs Interval(B) ----")
    print(f"Catalog file: {catalog_file}")
    print(f"Total symbols in catalog: {total}")
    print(f"OK (within tol): {ok_tol} ({ok_tol/total:.1%})")
    print(f"Missing A: {miss}")
    print(f"Negative A: {neg}")
    print(f"Too large A: {large}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_all = os.path.join(BASE_DIR, f"bitget_ab_check_{ts}.csv")
    out_bad = os.path.join(BASE_DIR, f"bitget_ab_check_bad_{ts}.csv")

    df.to_csv(out_all, index=False, encoding="utf-8-sig")
    df.loc[~df["in_range_tol"]].to_csv(out_bad, index=False, encoding="utf-8-sig")

    print(f"Saved: {out_all}")
    print(f"Saved (bad only): {out_bad}")


if __name__ == "__main__":
    main()
