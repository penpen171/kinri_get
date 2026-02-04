import os
import requests
import time
import csv
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

# ==========================================
#               基本設定
# ==========================================
BASE_URL = "https://open-api.bingx.com"
ENDPOINT = "/openApi/swap/v3/quote/klines"
LOG_FILE = "volatility_log.csv"
IS_MONITORING_MODE = True
MARKET_CLOSE_THRESHOLD_MIN = 5 

# --- 高精度モード：流動性・再始動誤検知対策済み ---
WATCH_CONFIG = [
    {"name": "NASDAQ100", "symbol": "NCSINASDAQ1002USD-USDT", "body_limit": 0.15, "drop_ratio": 0.45, "min_vol": 0.8},
    {"name": "S&P500",    "symbol": "NCSISP5002USD-USDT",    "body_limit": 0.05, "drop_ratio": 0.4,  "min_vol": 0.3},
    {"name": "ALUMINIUM", "symbol": "NCCOALUMINIUM2USD-USDT","body_limit": 0.5,  "drop_ratio": 0.5,  "min_vol": 5.0},
    {"name": "SOYBEANS",  "symbol": "NCCOSOYBEANS2USD-USDT", "body_limit": 0.5,  "drop_ratio": 0.4,  "min_vol": 3.0},
    # 他の銘柄も同様に min_vol を調整して追加
]

def save_log(name, status, body_val, drop_val, price):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["日時", "銘柄", "判定", "実体幅", "直前幅", "価格"])
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([now_str, name, status, f"{body_val:.4f}", f"{drop_val:.4f}", f"{price:.2f}"])

def check_symbol_volatility(config):
    try:
        params = {"symbol": config["symbol"], "interval": "1m", "limit": 3}
        response = requests.get(f"{BASE_URL}{ENDPOINT}", params=params, timeout=10)
        res_json = response.json()
        
        if res_json.get("code") == 0 and "data" in res_json:
            data = res_json['data']
            curr_k, prev_k, b_prev_k = data[-1], data[-2], data[-3]

            # 閉場チェック
            last_k_time = datetime.fromtimestamp(curr_k['time'] / 1000, tz=timezone.utc)
            if (datetime.now(timezone.utc) - last_k_time) > timedelta(minutes=MARKET_CLOSE_THRESHOLD_MIN):
                return f"{config['name']:10} | 😴 閉場中"

            # 数値算出
            curr_price = float(curr_k['close'])
            c_oc = abs(float(curr_k['close']) - float(curr_k['open'])) 
            w1_hl = float(prev_k['high']) - float(prev_k['low'])       
            w2_hl = float(b_prev_k['high']) - float(b_prev_k['low'])    

            # 判定ロジック
            status_text = "✅ 通常"
            
            # 【重要】現在進行形の足が、直前より広がっているなら「再始動」とみなして無視
            if c_oc > (w1_hl * 1.1) and c_oc > config["body_limit"]:
                return f"{config['name']:10} | 価格:{curr_price:10.2f} | 実体:{c_oc:8.4f} | {status_text}"

            # A: 急減衰（前々回比）
            is_dropping = w1_hl <= (w2_hl * config["drop_ratio"]) and w2_hl >= config["min_vol"]
            
            # B: 静止判定
            is_stagnant = c_oc <= config["body_limit"]

            if is_dropping and is_stagnant:
                status_text = "🚨🚨🚨 【停止】"
                save_log(config['name'], "停止", c_oc, w1_hl, curr_price)
            elif is_dropping:
                status_text = "🟡 【予兆】"
                save_log(config['name'], "予兆", c_oc, w1_hl, curr_price)
            elif is_stagnant:
                # 継続判定：直近2分間のどこかに勢いがあった形跡がある場合のみ
                if max(w1_hl, w2_hl) >= config["min_vol"]:
                    status_text = "🚨 【継続】"
                    save_log(config['name'], "停止", c_oc, w1_hl, curr_price)

            return f"{config['name']:10} | 価格:{curr_price:10.2f} | 実体:{c_oc:8.4f} | {status_text}"
    except Exception as e:
        return f"{config['name']} エラー: {e}"

def main():
    print(f"=== 高精度監視：誤検知フィルタ適用済み ({len(WATCH_CONFIG)}銘柄) ===")
    with ThreadPoolExecutor(max_workers=len(WATCH_CONFIG)) as executor:
        while True:
            now = datetime.now()
            results = list(executor.map(check_symbol_volatility, WATCH_CONFIG))
            print(f"\n[{now.strftime('%H:%M:%S')}] --------------------")
            for res in results:
                if res: print(res)
            
            next_run = (now + timedelta(minutes=1)).replace(second=1, microsecond=0)
            wait_seconds = (next_run - datetime.now()).total_seconds()
            if wait_seconds > 0: time.sleep(wait_seconds)

if __name__ == "__main__":
    main()