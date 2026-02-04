import os
import requests
import time
import csv
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- 設定：感度3000倍モード ---
BASE_URL = "https://open-api.bingx.com"
ENDPOINT = "/openApi/swap/v3/quote/klines"
DETAIL_LOG = "volatility_log_v4.csv"

WATCH_CONFIG = [
    {"name": "NASDAQ100", "symbol": "NCSINASDAQ1002USD-USDT", "group": "INDEX", "body_limit": 0.05},
    {"name": "S&P500",    "symbol": "NCSISP5002USD-USDT",    "group": "INDEX", "body_limit": 0.02},
    {"name": "DOW",       "symbol": "NCSIDOWJONES2USD-USDT", "group": "INDEX", "body_limit": 0.02},
    {"name": "GOLD",      "symbol": "NCCOGOLD2USD-USDT",     "group": "METAL", "body_limit": 0.03},
    {"name": "SILVER",    "symbol": "NCCOSILVER2USD-USDT",   "group": "METAL", "body_limit": 0.003},
    {"name": "COPPER",    "symbol": "NCCOCOPPER2USD-USDT",   "group": "METAL", "body_limit": 0.05},
]

market_status = {c["name"]: {"price": 0.0, "prev_price": 0.0, "c_hl": 0.0, "status": "通常"} for c in WATCH_CONFIG}

def save_log(name, status, oc, avg_vol, price, info):
    # CSVの列順を固定：日時, 銘柄, 判定, 実体幅, 過去平均, 価格, ワープ情報
    with open(DETAIL_LOG, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().strftime("%H:%M:%S"), name, status, f"{oc:.6f}", f"{avg_vol:.6f}", f"{price:.6f}", info])

def check_symbol(config):
    try:
        res = requests.get(f"{BASE_URL}{ENDPOINT}", params={"symbol": config["symbol"], "interval": "1m", "limit": 5}, timeout=10).json()
        if res.get("code") == 0 and res.get("data"):
            data = res['data']
            curr_p = float(data[-1]['close'])
            prev_p = float(data[-1]['open'])
            c_oc = abs(curr_p - prev_p)
            c_hl = float(data[-1]['high']) - float(data[-1]['low'])
            avg_vol = sum([(float(d['high']) - float(d['low'])) for d in data[-4:-1]]) / 3
            
            # 停止判定
            is_stagnant = (c_oc <= config["body_limit"]) and (c_hl <= avg_vol * 0.4)
            status = "停止" if is_stagnant else "通常"
            info = ""

            # 価格情報の更新
            m = market_status[config["name"]]
            if m["price"] > 0: m["prev_price"] = m["price"]
            else: m["prev_price"] = prev_p
            m["price"] = curr_p
            m["c_hl"] = c_hl

            # 指令ロジック
            if is_stagnant:
                others = [c for c in WATCH_CONFIG if c["group"] == config["group"] and c["name"] != config["name"]]
                for other in others:
                    o = market_status[other["name"]]
                    if o["c_hl"] > (avg_vol * 0.1): # 相手が動いていたら
                        direction = "🚨【LONG】" if o["price"] > o["prev_price"] else "🚨【SHORT】"
                        info = f"{direction} 仕込み：{other['name']}先行"
                        break
            
            save_log(config["name"], status, c_oc, avg_vol, curr_p, info)
    except:
        pass

def main():
    print("🏹 感度3000倍メイン稼働中...")
    while True:
        with ThreadPoolExecutor(max_workers=len(WATCH_CONFIG)) as e:
            e.map(check_symbol, WATCH_CONFIG)
        time.sleep(10)

if __name__ == "__main__":
    main()