# modules/data_api.py
"""
API取得関連の関数をまとめたモジュール
- MEXC、Bitget、BingX、Variationalの各取引所からデータを取得
- 並列処理で高速化
"""

import streamlit as st
import pandas as pd
import requests
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob
import csv


# --- [MEXC専用] CSV管理・ログ・API補強 ---
MEXC_CYCLE_FILE = "mexc_cycle_master.csv"
MEXC_LOG_FILE = "mexc_cycle_changes.log.csv"

def collect_cycle_to_interval(cc):
    """collectCycle(時間) → Interval文字列（例: 8 → "8h"）"""
    try:
        cc = int(float(cc))
    except:
        return None
    if cc in (1, 4, 8):
        return f"{cc}h"
    return f"{cc}h"

@st.cache_data(ttl=300)
def fetch_mexc_funding_meta(symbol_usdt: str):
    """MEXC funding_rate API（銘柄別）"""
    url = f"https://contract.mexc.com/api/v1/contract/funding_rate/{symbol_usdt}"
    try:
        return requests.get(url, timeout=5).json()
    except:
        return {}

def save_mexc_cycle_master(cycle_dict):
    """MEXC周期CSVを上書き保存"""
    df = pd.DataFrame([
        {"Symbol": k, "Interval": v, "UpdatedAtJST": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Source": "auto"}
        for k, v in sorted(cycle_dict.items())
    ])
    df.to_csv(MEXC_CYCLE_FILE, index=False, encoding="utf-8-sig")

def append_mexc_change_log(symbol, old_interval, new_interval, reason, meta_collect=None, meta_nft=None, meta_ts=None):
    """MEXC変更ログを追記"""
    row = {
        "ChangedAtJST": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Symbol": symbol,
        "OldInterval": old_interval if old_interval else "NEW",
        "NewInterval": new_interval,
        "Reason": reason,
        "MetaCollectCycle": meta_collect,
        "MetaNextSettleTime": meta_nft,
        "MetaTimestamp": meta_ts,
    }
    df = pd.DataFrame([row])
    header = not os.path.exists(MEXC_LOG_FILE)
    df.to_csv(MEXC_LOG_FILE, mode="a", index=False, header=header, encoding="utf-8-sig")

def verify_and_update_mexc_cycles(displayed_symbols, current_cycles):
    """
    上位40に含まれるMEXC銘柄について、APIで検証してCSV更新
    """
    updated = False
    new_cycles = current_cycles.copy()
    
    for sym in displayed_symbols:
        sym_usdt = f"{sym}_USDT"
        meta = fetch_mexc_funding_meta(sym_usdt)
        dmeta = meta.get("data", {}) if isinstance(meta, dict) else {}
        cc = dmeta.get("collectCycle")
        nft = dmeta.get("nextSettleTime")
        ts = dmeta.get("timestamp")
        
        if cc is None:
            continue
        
        new_interval = collect_cycle_to_interval(cc)
        if new_interval is None:
            continue
        
        old_interval = current_cycles.get(sym)
        
        if old_interval is None:
            new_cycles[sym] = new_interval
            append_mexc_change_log(sym, None, new_interval, "NEW", cc, nft, ts)
            updated = True
        elif old_interval != new_interval:
            new_cycles[sym] = new_interval
            append_mexc_change_log(sym, old_interval, new_interval, "CHANGED", cc, nft, ts)
            updated = True
    
    if updated:
        save_mexc_cycle_master(new_cycles)
    
    return new_cycles


# --- [BingX専用] カタログ読み込み ---
@st.cache_data
@st.cache_data
def load_bingx_catalog():
    """BingXのカタログCSVを読み込み"""
    bingx_catalog = {}
    try:
        files = glob.glob("bingx_true_catalog_*.csv")
        if files:
            latest_file = max(files, key=os.path.getctime)
            print(f"[DEBUG] BingXカタログ読み込み: {latest_file}")
            
            with open(latest_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                count_1h = 0
                count_4h = 0
                count_8h = 0
                
                for row in reader:
                    sym = row.get('Symbol')
                    interval_str = row.get('Interval', '').replace('h', '')
                    if sym and interval_str.isdigit():
                        interval_seconds = int(interval_str) * 3600
                        bingx_catalog[sym] = interval_seconds
                        
                        # カウント
                        if interval_seconds == 3600:
                            count_1h += 1
                        elif interval_seconds == 14400:
                            count_4h += 1
                        elif interval_seconds == 28800:
                            count_8h += 1
            
            print(f"[DEBUG] BingXカタログ統計: 1h={count_1h}件, 4h={count_4h}件, 8h={count_8h}件")
            print(f"[DEBUG] BingXカタログ合計: {len(bingx_catalog)}件")
            
            # サンプルを表示（WLD, SHIB, GLMがあれば）
            for test_sym in ['WLD-USDT', 'SHIB-USDT', 'GLM-USDT', 'SENT-USDT']:
                if test_sym in bingx_catalog:
                    print(f"[DEBUG] {test_sym}: {bingx_catalog[test_sym]}秒")
    
    except Exception as e:
        print(f"[DEBUG] BingXカタログ読み込みエラー: {e}")
    
    return bingx_catalog



# --- [共通] カタログ読み込み ---
@st.cache_data
def load_cycle_masters():
    """Bitget & MEXC のカタログ読み込み"""
    cycles = {"Bitget": {}, "MEXC": {}}
    
    # Bitget
    bg_file = "bitget_true_catalog_0131_0704.csv"
    if os.path.exists(bg_file):
        try:
            df = pd.read_csv(bg_file, encoding="utf-8-sig")
            if 'Symbol' in df.columns and 'Interval' in df.columns:
                symbols = df['Symbol'].astype(str).str.replace("-USDT", "", regex=False)
                cycles["Bitget"] = dict(zip(symbols, df['Interval'].astype(str)))
        except: pass

    # MEXC
    mx_file = MEXC_CYCLE_FILE if os.path.exists(MEXC_CYCLE_FILE) else "mexc_true_catalog.csv"
    if os.path.exists(mx_file):
        try:
            df = pd.read_csv(mx_file, encoding="utf-8-sig")
            if 'Symbol' in df.columns and 'Interval' in df.columns:
                intervals = df['Interval'].astype(str)
                intervals = intervals.apply(lambda x: x if x.endswith("h") else x + "h")
                cycles["MEXC"] = dict(zip(df['Symbol'], intervals))
        except: pass
        
    return cycles


# --- [共通] Interval -> 秒 ---
def interval_to_seconds(interval: str) -> int:
    if interval == "1h": return 3600
    if interval == "4h": return 14400
    if interval == "8h": return 28800
    return 0


# --- [共通] Interval -> 配布時刻スケジュール ---
def interval_to_sched_hours(interval: str):
    if interval == "1h": return list(range(24))
    if interval == "4h": return [1, 5, 9, 13, 17, 21]
    return [1, 9, 17]


# --- [共通] 次回配布時刻(epoch秒)を推定 ---
def calc_next_settle_epoch_from_sched(sched_hours, now_dt_jst: datetime) -> int:
    now_dt = now_dt_jst
    candidates = []
    for h in sched_hours:
        candidates.append(now_dt.replace(hour=h, minute=0, second=0, microsecond=0))
    future = [c for c in candidates if c > now_dt]
    if future:
        nxt = min(future)
    else:
        base = (now_dt + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
        nxt = base.replace(hour=min(sched_hours))
    return int(nxt.timestamp())


# --- [共通] 時刻の正規化 ---
def normalize_time(time_input, exchange_name, cycle_hint=None):
    now_h = (datetime.now().hour)
    sched = [1, 9, 17]
    if exchange_name == "BingX":
        sched = [1, 5, 9, 13, 17, 21]
    
    if cycle_hint:
        if cycle_hint == '1h': sched = list(range(24))
        elif cycle_hint == '4h': sched = [1, 5, 9, 13, 17, 21]
        elif cycle_hint == '8h': sched = [1, 9, 17]

    def get_fallback():
        return next((h for h in sched if h > now_h), sched[0])

    try:
        if not time_input or time_input == 0: return get_fallback()
        if isinstance(time_input, (int, float)):
            if time_input < 1000000: return get_fallback()
            dt = pd.to_datetime(time_input, unit='ms')
        else:
            dt = pd.to_datetime(time_input)
        jst_dt = dt + timedelta(hours=9)
        hour = jst_dt.hour
        
        if exchange_name == "MEXC" and not cycle_hint: 
             mexc_sched = [1, 9, 17]
             return int(min(mexc_sched, key=lambda x: abs(x - hour)))
             
        return int(hour)
    except Exception:
        return get_fallback()


# --- [各取引所のデータ取得] ---
def fetch_mexc_data(cycle_masters, now_dt):
    """MEXC専用データ取得"""
    data = {}
    status = "🔴"
    ua = "Mozilla/5.0"
    
    try:
        r = requests.get("https://api.mexc.com/api/v1/contract/ticker", 
                        headers={"User-Agent": ua}, 
                        timeout=2).json()
        
        if r.get('success'):
            d = r.get("data")
            if isinstance(d, list): items = d
            elif isinstance(d, dict):
                items = d.get("resultList") if isinstance(d.get("resultList"), list) else [d]
            else: items = []

            for i in items:
                sym = str(i.get("symbol", "")).split('_')[0]
                if not sym: continue
                
                fr = i.get("lastFundingRate")
                if fr is None: fr = i.get("fundingRate", 0)
                lp = i.get("lastPrice")
                rr = i.get("riseFallRate", 0)

                hint = cycle_masters["MEXC"].get(sym, "8h") 
                interval_s = interval_to_seconds(hint)

                next_time = i.get("nextSettleTime")
                remaining_s = 0
                try:
                    if next_time is not None and float(next_time) > 1000000:
                        next_epoch = int(float(next_time) / 1000)
                        remaining_s = max(0, next_epoch - int(now_dt.timestamp()))
                except:
                    remaining_s = 0

                if remaining_s <= 0:
                    now_epoch = int(now_dt.timestamp())
                    sched_h = interval_to_sched_hours(hint)
                    next_epoch = calc_next_settle_epoch_from_sched(sched_h, now_dt)
                    remaining_s = max(0, next_epoch - now_epoch)

                t_val = normalize_time(next_time, "MEXC", cycle_hint=hint)

                data.setdefault(sym, {})['MEXC'] = {
                    'rate': float(fr) * 100,
                    'p': float(lp) if lp is not None else 0.0,
                    'v': abs(float(rr)) * 100,
                    'm': 200 if sym in ['BTC', 'ETH'] else 50,
                    't': t_val,
                    'interval_s': interval_s,
                    'remaining_s': remaining_s
                }
            status = "🟢"
    except requests.exceptions.Timeout:
        pass
    except Exception:
        pass
    
    return data, status


def fetch_bitget_data(cycle_masters, now_dt):
    """Bitget専用データ取得"""
    data = {}
    status = "🔴"
    
    try:
        bg_r = requests.get("https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures", timeout=5).json()
        if bg_r.get('code') == '00000':
            for i in bg_r['data']:
                sym = i['symbol'].replace('USDT', '')
                hint = cycle_masters["Bitget"].get(sym, "4h")
                
                sched_h = interval_to_sched_hours(hint)
                next_epoch = calc_next_settle_epoch_from_sched(sched_h, now_dt)
                remaining_s = max(0, next_epoch - int(now_dt.timestamp()))
                interval_s = interval_to_seconds(hint)
                t_val = normalize_time(0, "Bitget", cycle_hint=hint)

                data.setdefault(sym, {})['Bitget'] = {
                    'rate': float(i['fundingRate']) * 100,
                    'p': float(i['lastPr']),
                    'v': abs(float(i.get('priceChangePercent', 0))) * 100,
                    'm': 125 if sym in ['BTC', 'ETH'] else 50,
                    't': t_val,
                    'interval_s': interval_s,
                    'remaining_s': remaining_s
                }
            status = "🟢"
    except: pass
    
    return data, status


def fetch_bingx_data(now_dt):
    """BingX専用データ取得"""
    data = {}
    status = "🔴"
    
    try:
        bingx_catalog = load_bingx_catalog()
        
        bx_t = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/ticker", timeout=10).json()
        bx_r = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex", timeout=10).json()
        bx_v = {x['symbol'].split('-')[0]: abs(float(x.get('priceChangePercent', 0))) for x in bx_t.get('data', [])}

        for i in bx_r.get('data', []):
            full_sym = i['symbol']
            sym = full_sym.split('-')[0]
            
            # USDTペアのみ処理（USDCペアはスキップ）
            if not full_sym.endswith('-USDT'):
                continue
            
            next_time = float(i.get('nextFundingTime', 0))
            
            # カタログから interval_s を取得（最優先）
            interval_s = bingx_catalog.get(full_sym, None)
            
            # カタログにない場合のみ、残り時間から推定
            if interval_s is None:
                if next_time > 1000000:
                    next_epoch = int(next_time / 1000)
                    remaining_s_temp = max(0, next_epoch - int(now_dt.timestamp()))
                    
                    # 残り時間から周期を推定（カタログがない場合のみ）
                    if remaining_s_temp < 3600:
                        interval_s = 3600
                    elif remaining_s_temp > 14400:
                        interval_s = 28800
                    else:
                        interval_s = 14400
                else:
                    interval_s = 14400  # デフォルト
            
            # 残り時間の計算
            if next_time > 1000000:
                next_epoch = int(next_time / 1000)
                remaining_s = max(0, next_epoch - int(now_dt.timestamp()))
            else:
                # nextFundingTime が取得できない場合、スケジュールから推定
                if interval_s == 3600:
                    sched_h = list(range(24))
                elif interval_s == 14400:
                    sched_h = [1, 5, 9, 13, 17, 21]
                else:
                    sched_h = [1, 9, 17]
                
                from modules.data_api import calc_next_settle_epoch_from_sched
                next_epoch_base = calc_next_settle_epoch_from_sched(sched_h, now_dt)
                remaining_s = max(0, next_epoch_base - int(now_dt.timestamp()))

            from modules.data_api import normalize_time
            t_val = normalize_time(next_time, "BingX")
            
            data.setdefault(sym, {})['BingX'] = {
                'rate': float(i['lastFundingRate']) * 100,
                'p': float(i['markPrice']),
                'v': bx_v.get(sym, 0),
                'm': 150 if sym in ['BTC', 'ETH'] else 20,
                't': t_val,
                'interval_s': interval_s, 
                'remaining_s': remaining_s
            }
        status = "🟢"
    except Exception as e:
        print(f"[DEBUG] fetch_bingx_data エラー: {e}")
    
    return data, status



def fetch_variational_data(now_dt):
    """Variational専用データ取得"""
    data = {}
    status = "🔴"
    
    try:
        v_url = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
        v = requests.get(v_url, timeout=8).json()
        listings = v.get("listings") or v.get("data") or []
        
        for it in listings:
            sym = it.get("ticker") or it.get("listing_name") or it.get("symbol") or it.get("name")
            if not sym: continue

            try: interval_s = int(float(it.get("funding_interval_s", 3600)))
            except: interval_s = 3600
            
            try: apr = float(it.get("funding_rate", 0.0))
            except: apr = 0.0

            hourly = apr / 8760.0
            hours_per_settle = max(1.0, interval_s / 3600.0)
            settle_rate = hourly * hours_per_settle

            try: p = float(it.get("mark_price") or 0.0)
            except: p = 0.0
            
            now_epoch = int(now_dt.timestamp())
            remaining_s = interval_s - (now_epoch % interval_s)

            data.setdefault(sym, {})['Variational'] = {
                'rate': settle_rate * 100.0,
                'p': p, 'v': 0.0, 'm': 0, 't': 0,
                'interval_s': interval_s,
                'remaining_s': remaining_s
            }
        status = "🟢"
    except: pass
    
    return data, status


# --- [メイン] 並列データ取得 ---
@st.cache_data(ttl=60)
def fetch_api_snapshot():
    """全取引所のデータを並列取得"""
    data = {}
    status = {"MEXC": "🔴", "BingX": "🔴", "Bitget": "🔴", "Variational": "🔴"}
    
    cycle_masters = load_cycle_masters()
    now_dt = datetime.now()
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_mexc_data, cycle_masters, now_dt): "MEXC",
            executor.submit(fetch_bitget_data, cycle_masters, now_dt): "Bitget",
            executor.submit(fetch_bingx_data, now_dt): "BingX",
            executor.submit(fetch_variational_data, now_dt): "Variational"
        }
        
        for future in as_completed(futures):
            exchange = futures[future]
            try:
                ex_data, ex_status = future.result()
                for sym, exs in ex_data.items():
                    if sym not in data:
                        data[sym] = {}
                    data[sym].update(exs)
                status[exchange] = ex_status
            except Exception as e:
                status[exchange] = "🔴"
    
    return data, status, datetime.now().strftime("%H:%M:%S")
