import os
import requests
import time
import csv
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

# --- 設定 ---
BASE_URL = "https://open-api.bingx.com"
ENDPOINT = "/openApi/swap/v3/quote/klines"
DETAIL_LOG = "volatility_log.csv"
EVENT_LOG = "distortion_events.csv"
STATUS_JSON = "current_status.json"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# 監視銘柄設定 (v3.6)
WATCH_CONFIG = [
    # --- アクティブ監視銘柄 ---
    {"name": "NASDAQ100", "symbol": "NCSINASDAQ1002USD-USDT", "body_limit": 0.05,  "drop_ratio": 0.6,  "min_vol": 0.01},
    {"name": "S&P500",    "symbol": "NCSISP5002USD-USDT",    "body_limit": 0.02,  "drop_ratio": 0.5,  "min_vol": 0.15},
    {"name": "GOLD",      "symbol": "NCCOGOLD2USD-USDT",     "body_limit": 0.03,  "drop_ratio": 0.5,  "min_vol": 0.10}, 
    {"name": "SILVER",    "symbol": "NCCOSILVER2USD-USDT",   "body_limit": 0.003, "drop_ratio": 0.5,  "min_vol": 0.01}, 
    {"name": "COPPER",    "symbol": "NCCOCOPPER2USD-USDT",   "body_limit": 0.002, "drop_ratio": 0.4,  "min_vol": 0.005},
    {"name": "COCOA",     "symbol": "NCCOCOCOA2USD-USDT",    "body_limit": 5.0,   "drop_ratio": 0.35, "min_vol": 15.0},

    # --- 待機中（除外銘柄） ---
    # {"name": "PALLADIUM", "symbol": "NCCOPALLADIUM2USD-USDT","body_limit": 0.15,  "drop_ratio": 0.3,  "min_vol": 0.5},
    # {"name": "NICKEL",    "symbol": "NCCONICKEL2USD-USDT",   "body_limit": 2.0,   "drop_ratio": 0.5,  "min_vol": 5.0},
    # {"name": "GASOLINE",  "symbol": "NCCOGASOLINE2USD-USDT", "body_limit": 0.001, "drop_ratio": 0.5,  "min_vol": 0.002},
    # {"name": "ALUMINIUM", "symbol": "NCCOALUMINIUM2USD-USDT","body_limit": 0.5,   "drop_ratio": 0.5,  "min_vol": 1.0},
    # {"name": "COFFEE",    "symbol": "NCCOCOFFEE2USD-USDT",   "body_limit": 0.1,   "drop_ratio": 0.4,  "min_vol": 0.3},
    # {"name": "SOYBEANS",  "symbol": "NCCOSOYBEANS2USD-USDT", "body_limit": 0.5,   "drop_ratio": 0.4,  "min_vol": 1.0},
]

class DistortionTrackerV3:
    def __init__(self):
        self.active_stagnation = {}

    def update(self, name, is_active, is_weakening, price):
        now = datetime.now()
        status_info = {"status": "NORMAL", "start_time": None, "duration": 0}
        
        if is_active:
            if name not in self.active_stagnation:
                self.active_stagnation[name] = {"start_time": now, "start_price": price}
            dur = (now - self.active_stagnation[name]["start_time"]).total_seconds() / 60
            status_info = {"status": "STAGNANT", "start_time": self.active_stagnation[name]["start_time"].isoformat(), "duration": dur}
            return f"⏳ STOP/KEEP({dur:.1f}m)", status_info
        elif name in self.active_stagnation:
            data = self.active_stagnation.pop(name)
            duration = (now - data["start_time"]).total_seconds() / 60
            diff = price - data["start_price"]
            direction = "UP" if diff > 0 else "DOWN"
            save_event(name, data["start_time"], now, duration, diff, price)
            return f"💥 解除({direction}:{diff:.2f})", status_info
        return "NORMAL", status_info

tracker = DistortionTrackerV3()

def save_event(name, start, end, duration, diff, price):
    with open(EVENT_LOG, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([name, start.strftime("%H:%M:%S"), end.strftime("%H:%M:%S"), f"{duration:.2f}", f"{diff:.4f}", "UP" if diff > 0 else "DOWN", f"{price:.4f}"])

def save_detail_log(name, status, oc, avg_vol, price):
    file_exists = os.path.isfile(DETAIL_LOG)
    with open(DETAIL_LOG, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["日時", "銘柄", "判定", "実体幅", "過去平均ボラ", "価格"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, status, f"{oc:.6f}", f"{avg_vol:.6f}", f"{price:.6f}"])

def check_symbol(config):
    try:
        params = {"symbol": config["symbol"], "interval": "1m", "limit": 5}
        res = requests.get(f"{BASE_URL}{ENDPOINT}", params=params, timeout=8).json()
        if res.get("code") == 0 and res.get("data"):
            data = res['data']
            curr = data[-1]
            c_oc = abs(float(curr['close']) - float(curr['open']))
            c_hl = float(curr['high']) - float(curr['low'])
            curr_p = float(curr['close'])

            avg_vol = sum([(float(d['high']) - float(d['low'])) for d in data[-4:-1]]) / 3
            
            # 誤検知防止フィルター：相対ボラ判定
            is_trend_noise = avg_vol > (config["min_vol"] * 3) and c_hl > (avg_vol * 0.5)
            is_stagnant = (c_oc <= config["body_limit"]) and (c_hl <= avg_vol * 0.4)
            
            prev_hl = float(data[-2]['high']) - float(data[-2]['low'])
            is_weakening = c_hl <= (prev_hl * config["drop_ratio"]) and prev_hl >= config["min_vol"]

            is_active = is_stagnant and not is_trend_noise
            msg, info = tracker.update(config["name"], is_active, is_weakening, curr_p)
            
            if "💥 解除" in msg: v_label = msg
            elif is_active: v_label = "継続" if info["duration"] > 0 else "停止"
            elif is_weakening: v_label = "予兆"
            else: v_label = "通常"

            return {"name": config["name"], "v_label": v_label, "msg": msg, "info": info, "oc": c_oc, "avg_vol": avg_vol, "price": curr_p, "success": True}
        return {"success": False}
    except:
        return {"success": False}

def main():
    print(f"🚀 感度3000倍 v3.6 [ゴールド・シルバー追加版] 起動")
    last_log_min = -1

    while True:
        now = datetime.now()
        # 監視対象（コメントアウトされていないもの）のみを抽出
        active_watch = [c for c in WATCH_CONFIG if isinstance(c, dict)]
        
        with ThreadPoolExecutor(max_workers=len(active_watch)) as executor:
            results = [r for r in list(executor.map(check_symbol, active_watch)) if r["success"]]
        
        # 15秒ごとのリアルタイムJSON更新（サイドバー用）
        stagnant_dict = {r["name"]: r["info"] for r in results if r["info"]["status"] == "STAGNANT"}
        with open(STATUS_JSON, "w") as f:
            json.dump(stagnant_dict, f)
        
        # ターミナル表示
        if stagnant_dict:
            print(f"\n[{now.strftime('%H:%M:%S')}] ⚠️ 停止中:")
            for name, info in stagnant_dict.items():
                print(f"  > {name:10}: 停止 {info['duration']:.1f}分経過")
        else:
            print(f"\r[{now.strftime('%H:%M:%S')}] 🟢 正常監視中...", end="")

        # 1分ごとのCSV記録
        if now.minute != last_log_min:
            for r in results:
                save_detail_log(r["name"], r["v_label"], r["oc"], r["avg_vol"], r["price"])
            last_log_min = now.minute
        
        time.sleep(15)

if __name__ == "__main__":
    main()