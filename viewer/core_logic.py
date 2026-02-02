import pandas as pd
import requests
from datetime import datetime, timedelta

def normalize_time(time_input, exchange_name):
    """
    あらゆる形式の時間データを、JST(0-23時)の整数(int)に変換する。
    """
    try:
        if isinstance(time_input, (int, float)):
            # ミリ秒単位のタイムスタンプの場合
            dt = pd.to_datetime(time_input, unit='ms')
        else:
            # 文字列の場合
            dt = pd.to_datetime(time_input)
        
        # JST補正 (+9時間) ※APIがUTCで返していることを想定
        jst_dt = dt + timedelta(hours=9)
        hour = jst_dt.hour
        
        # MEXCのような特殊な配布サイクルの場合、直近の決済時刻に丸める処理
        if exchange_name == "MEXC":
            settle_hours = [1, 9, 17]
            return int(min(settle_hours, key=lambda x: abs(x - hour)))
            
        return int(hour)
    except Exception:
        return 0

def fetch_raw_data():
    """
    3取引所(MEXC, Bitget, BingX)からデータを取得し、正規化して返す。
    """
    raw_data = {}
    counts = {"MEXC": 0, "Bitget": 0, "BingX": 0}
    
    # ---------------------------------------------------------
    # 1. MEXC (仮のAPIロジック: 実際のURL/Keyに合わせて調整)
    # ---------------------------------------------------------
    try:
        # endpoint = "https://contract.mexc.com/api/v1/contract/ticker"
        # res = requests.get(endpoint).json()
        # サンプルループ
        mexc_items = [{"symbol": "ASTR_USDT", "lastPrice": 0.05, "fundingRate": -0.00727, "nextSettleTime": "2026-02-01T16:00:00Z"}]
        for item in mexc_items:
            ticker = item['symbol'].replace("_USDT", "")
            if ticker not in raw_data: raw_data[ticker] = {}
            raw_data[ticker]["MEXC"] = {
                "rate": float(item['fundingRate']) * 100,
                "p": float(item['lastPrice']),
                "t": normalize_time(item['nextSettleTime'], "MEXC"),
                "v": 0.01,
                "m": 125
            }
            counts["MEXC"] += 1
    except: pass

    # ---------------------------------------------------------
    # 2. Bitget (仮のAPIロジック)
    # ---------------------------------------------------------
    try:
        bitget_items = [{"symbol": "ZKUSDT", "lastPr": 0.1, "fundingRate": -0.018, "nextFundingTime": 1738422000000}]
        for item in bitget_items:
            ticker = item['symbol'].replace("USDT", "")
            if ticker not in raw_data: raw_data[ticker] = {}
            raw_data[ticker]["Bitget"] = {
                "rate": float(item['fundingRate']) * 100,
                "p": float(item['lastPr']),
                "t": normalize_time(item['nextFundingTime'], "Bitget"),
                "v": 0.01,
                "m": 125
            }
            counts["Bitget"] += 1
    except: pass

    # ---------------------------------------------------------
    # 3. BingX (仮のAPIロジック)
    # ---------------------------------------------------------
    try:
        bingx_items = [{"symbol": "ZK-USDT", "markPrice": 0.1, "lastFundingRate": -0.010, "nextFundingTime": 1738422000000}]
        for item in bingx_items:
            ticker = item['symbol'].replace("-USDT", "")
            if ticker not in raw_data: raw_data[ticker] = {}
            raw_data[ticker]["BingX"] = {
                "rate": float(item['lastFundingRate']) * 100,
                "p": float(item['markPrice']),
                "t": normalize_time(item['nextFundingTime'], "BingX"),
                "v": 0.01,
                "m": 125
            }
            counts["BingX"] += 1
    except: pass

    update_time = datetime.now().strftime("%H:%M:%S")
    return raw_data, update_time, counts