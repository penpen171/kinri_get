# modules/data_api.py
"""
API取得関連の関数をまとめたモジュール（診断用ログ追加版）
"""

import streamlit as st
import pandas as pd
import requests
import os
import time  # 追加
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob
import csv

# --- [MEXC専用] ---
MEXC_CYCLE_FILE = "mexc_cycle_master.csv"
MEXC_LOG_FILE = "mexc_cycle_changes.log.csv"

def collect_cycle_to_interval(cc):
    try:
        cc = int(float(cc))
    except:
        return None
    if cc in (1, 4, 8):
        return f"{cc}h"
    return f"{cc}h"

@st.cache_data(ttl=300)
def fetch_mexc_funding_meta(symbol_usdt: str):
    url = f"https://contract.mexc.com/api/v1/contract/funding_rate/{symbol_usdt}"
    try:
        return requests.get(url, timeout=5).json()
    except:
        return {}

def save_mexc_cycle_master(cycle_dict):
    df = pd.DataFrame([
        {"Symbol": k, "Interval": v, "UpdatedAtJST": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Source": "auto"}
        for k, v in sorted(cycle_dict.items())
    ])
    df.to_csv(MEXC_CYCLE_FILE, index=False, encoding="utf-8-sig")

def append_mexc_change_log(symbol, old_interval, new_interval, reason, meta_collect=None, meta_nft=None, meta_ts=None):
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
    # (省略してもよいですが、念のため維持)
    updated = False
    new_cycles = current_cycles.copy()
    for sym in displayed_symbols:
        sym_usdt = f"{sym}_USDT"
        meta = fetch_mexc_funding_meta(sym_usdt)
        dmeta = meta.get("data", {}) if isinstance(meta, dict) else {}
        cc = dmeta.get("collectCycle")
        nft = dmeta.get("nextSettleTime")
        ts = dmeta.get("timestamp")
        if cc is None: continue
        new_interval = collect_cycle_to_interval(cc)
        if new_interval is None: continue
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

# --- [BingX専用] ---
@st.cache_data
def load_bingx_catalog():
    bingx_catalog = {}
    try:
        files = glob.glob("bingx_true_catalog_*.csv")
        if files:
            latest_file = max(files, key=os.path.getctime)
            with open(latest_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sym = row.get('Symbol')
                    interval_str = row.get('Interval', '').replace('h', '')
                    if sym and interval_str.isdigit():
                        interval_seconds = int(interval_str) * 3600
                        bingx_catalog[sym] = interval_seconds
    except Exception as e:
        pass
    return bingx_catalog

# --- [共通] ---
@st.cache_data
def load_cycle_masters():
    cycles = {"Bitget": {}, "MEXC": {}}
    bg_file = "bitget_true_catalog_0131_0704.csv"
    if os.path.exists(bg_file):
        try:
            df = pd.read_csv(bg_file, encoding="utf-8-sig")
            if 'Symbol' in df.columns and 'Interval' in df.columns:
                symbols = df['Symbol'].astype(str).str.replace("-USDT", "", regex=False)
                cycles["Bitget"] = dict(zip(symbols, df['Interval'].astype(str)))
        except: pass

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

def interval_to_seconds(interval: str) -> int:
    if interval == "1h": return 3600
    if interval == "4h": return 14400
    if interval == "8h": return 28800
    return 0

def interval_to_sched_hours(interval: str):
    if interval == "1h": return list(range(24))
    if interval == "4h": return [1, 5, 9, 13, 17, 21]
    return [1, 9, 17]

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
    t_start = time.time()
    print("[DEBUG] MEXC: 開始")
    data = {}
    status = "🔴"
    ua = "Mozilla/5.0"
    
    try:
        # Timeoutを短縮 2s -> 3s (安定のため)
        r = requests.get("https://api.mexc.com/api/v1/contract/ticker", 
                         headers={"User-Agent": ua}, 
                         timeout=3).json()
        
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
    except Exception as e:
        print(f"[DEBUG] MEXC エラー: {e}")
        pass
    
    print(f"[DEBUG] MEXC: 完了 ({time.time() - t_start:.2f}秒)")
    return data, status

def fetch_bitget_data(cycle_masters, now_dt):
    """Bitget専用データ取得"""
    t_start = time.time()
    print("[DEBUG] Bitget: 開始")
    data = {}
    status = "🔴"
    
    try:
        # Timeoutを短縮 5s -> 3s
        bg_r = requests.get("https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures", timeout=3).json()
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
    except Exception as e:
        print(f"[DEBUG] Bitget エラー: {e}")
        pass
    
    print(f"[DEBUG] Bitget: 完了 ({time.time() - t_start:.2f}秒)")
    return data, status

# --- [BingX専用] キャッシュ強化版 ---
@st.cache_data(ttl=300, show_spinner=False)  # 5分間キャッシュ
def fetch_bingx_data_cached(now_ts_key):
    """
    BingXのデータ取得（5分間キャッシュ）
    now_ts_key: 5分単位のタイムスタンプ（キャッシュキー用）
    """
    print(f"[DEBUG] BingX: キャッシュ miss - 新規取得開始")
    now_dt = datetime.now()  # 実際の現在時刻を使用
    data, status = fetch_bingx_data_internal(now_dt)
    print(f"[DEBUG] BingX: 取得完了 status={status}, データ件数={len(data)}")
    return data, status


# --- [BingX専用] Session State キャッシュ版 ---
def fetch_bingx_data_with_cache(now_dt):
    """
    BingXのデータ取得（Session Stateでキャッシュ）
    5分間キャッシュを保持
    """
    import streamlit as st
    
    # 5分単位のキャッシュキー
    now_ts = int(now_dt.timestamp())
    cache_key_5min = (now_ts // 300) * 300
    
    # Session Stateの初期化
    if 'bingx_cache' not in st.session_state:
        st.session_state.bingx_cache = {
            'data': {},
            'status': '🔴',
            'cache_key': 0
        }
    
    # キャッシュが有効ならそれを返す
    if st.session_state.bingx_cache['cache_key'] == cache_key_5min:
        print(f"[DEBUG] BingX: キャッシュ hit - 前回データを使用")
        return st.session_state.bingx_cache['data'], st.session_state.bingx_cache['status']
    
    # キャッシュが無効なら新規取得
    print(f"[DEBUG] BingX: キャッシュ miss - 新規取得開始（前回キー:{st.session_state.bingx_cache['cache_key']}, 今回キー:{cache_key_5min}）")
    data, status = fetch_bingx_data_internal(now_dt)
    
    # キャッシュに保存
    st.session_state.bingx_cache = {
        'data': data,
        'status': status,
        'cache_key': cache_key_5min
    }
    
    print(f"[DEBUG] BingX: 取得完了 status={status}, データ件数={len(data)}")
    return data, status


def fetch_bingx_data_internal(now_dt):
    """BingX専用データ取得（内部関数）"""
    t_start = time.time()
    print("[DEBUG] BingX: 開始")
    data = {}
    status = "🔴"
    
    # タイムアウト設定
    TIMEOUT_SET = (3.0, 6.0)  # 接続3秒, 読み込み6秒
    
    try:
        bingx_catalog = load_bingx_catalog()
        
        # 1. Ticker取得
        print("[DEBUG] BingX: Ticker取得中...")
        bx_t = requests.get(
            "https://open-api.bingx.com/openApi/swap/v2/quote/ticker", 
            timeout=TIMEOUT_SET
        ).json()
        
        # 2. PremiumIndex取得
        print("[DEBUG] BingX: PremiumIndex取得中...")
        bx_r = requests.get(
            "https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex", 
            timeout=TIMEOUT_SET
        ).json()
        
        print(f"[DEBUG] BingX: API応答確認 - ticker data count: {len(bx_t.get('data', []))}, premium data count: {len(bx_r.get('data', []))}")
        
        # ボラティリティのマッピング作成
        bx_v = {}
        for x in bx_t.get('data', []):
            sym = x['symbol'].split('-')[0]
            bx_v[sym] = abs(float(x.get('priceChangePercent', 0)))
        
        # メインデータ処理
        processed_count = 0
        for i in bx_r.get('data', []):
            full_sym = i['symbol']
            sym = full_sym.split('-')[0]
            
            # USDTペアのみ処理
            if not full_sym.endswith('-USDT'):
                continue
            
            next_time = float(i.get('nextFundingTime', 0))
            
            # カタログから interval_s を取得
            interval_s = bingx_catalog.get(full_sym, None)
            
            # カタログにない場合は残り時間から推定
            if interval_s is None:
                if next_time > 1000000:
                    next_epoch = int(next_time / 1000)
                    remaining_s_temp = max(0, next_epoch - int(now_dt.timestamp()))
                    if remaining_s_temp < 3600:
                        interval_s = 3600
                    elif remaining_s_temp > 14400:
                        interval_s = 28800
                    else:
                        interval_s = 14400
                else:
                    interval_s = 14400
            
            # 残り時間の計算
            if next_time > 1000000:
                next_epoch = int(next_time / 1000)
                remaining_s = max(0, next_epoch - int(now_dt.timestamp()))
            else:
                if interval_s == 3600:
                    sched_h = list(range(24))
                elif interval_s == 14400:
                    sched_h = [1, 5, 9, 13, 17, 21]
                else:
                    sched_h = [1, 9, 17]
                next_epoch_base = calc_next_settle_epoch_from_sched(sched_h, now_dt)
                remaining_s = max(0, next_epoch_base - int(now_dt.timestamp()))
            
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
            processed_count += 1
        
        print(f"[DEBUG] BingX: 処理完了 - {processed_count}銘柄")
        status = "🟢"
    
    except Exception as e:
        print(f"[DEBUG] BingX エラー: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"[DEBUG] BingX: 完了 ({time.time() - t_start:.2f}秒)")
    return data, status




def fetch_variational_data(now_dt):
    """Variational専用データ取得"""
    t_start = time.time()
    print("[DEBUG] Variational: 開始")
    data = {}
    status = "🔴"
    
    try:
        v_url = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
        # Timeoutを短縮 8s -> 3s
        v = requests.get(v_url, timeout=3).json()
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
    except Exception as e:
        print(f"[DEBUG] Variational エラー: {e}")
        pass
    
    print(f"[DEBUG] Variational: 完了 ({time.time() - t_start:.2f}秒)")
    return data, status

@st.cache_data(ttl=60)
def fetch_api_snapshot():
    """全取引所のデータを並列取得"""
    t_all_start = time.time()
    print(f"[INFO] 全API取得開始: {datetime.now().strftime('%H:%M:%S')}")
    
    data = {}
    status = {"MEXC": "🔴", "BingX": "🔴", "Bitget": "🔴", "Variational": "🔴"}
    
    cycle_masters = load_cycle_masters()
    now_dt = datetime.now()
    
    # 4並列で実行（BingXだけSession Stateキャッシュを使う）
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_mexc_data, cycle_masters, now_dt): "MEXC",
            executor.submit(fetch_bitget_data, cycle_masters, now_dt): "Bitget",
            executor.submit(fetch_bingx_data_with_cache, now_dt): "BingX",  # ← Session State版
            executor.submit(fetch_variational_data, now_dt): "Variational"
        }
        
        for future in as_completed(futures):
            exchange = futures[future]
            try:
                ex_data, ex_status = future.result()
                
                # データをマージ
                for sym, exs in ex_data.items():
                    if sym not in data:
                        data[sym] = {}
                    data[sym].update(exs)
                
                status[exchange] = ex_status
                print(f"[DEBUG] {exchange}: ステータス={ex_status}, データ件数={len(ex_data)}")
                
            except Exception as e:
                print(f"[ERROR] {exchange} スレッドエラー: {e}")
                import traceback
                traceback.print_exc()
                status[exchange] = "🔴"
    
    print(f"[INFO] 全API取得完了: {time.time() - t_all_start:.2f}秒")
    print(f"[INFO] 最終データ: 銘柄数={len(data)}, ステータス={status}")
    
    return data, status, datetime.now().strftime("%H:%M:%S")
