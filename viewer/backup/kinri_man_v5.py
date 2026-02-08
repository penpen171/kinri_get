import streamlit as st
import pandas as pd
import requests
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed


# --- ページ基本設定 ---
st.set_page_config(page_title="金利ーマン Dashboard v3.6.4", layout="wide")


# --- 現場専用スタイルシート ---
st.markdown("""
<style>
    .report-table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 5px; }
    .report-table th { background-color: #f1f5f9; padding: 6px 2px; font-size: 11px; border: 1px solid #cbd5e1; text-align: center; color: #475569; }
    .report-table td { border: 1px solid #cbd5e1; padding: 8px 2px; text-align: center; vertical-align: middle; line-height: 1.2; }
    .ticker-text { font-weight: 800; font-size: 1.15em; color: #1e293b; }
    .ex-label { font-size: 0.85em; font-weight: bold; color: #334155; display: block; margin-bottom: 2px; }
    .rate-val { font-size: 1.1em; font-weight: 600; color: #0f172a; }
    .dist-time { font-size: 0.75em; color: #64748b; background: #f1f5f9; padding: 1px 4px; border-radius: 3px; display: inline-block; margin-top: 3px; }
    .net-profit { background-color: #fffbeb; font-size: 1.3em !important; font-weight: 900; color: #b45309; }
    .lev-amount { font-size: 1.1em; font-weight: 700; color: #000; }
    .update-ts { font-size: 0.5em; color: #94a3b8; font-weight: normal; margin-left: 10px; }
</style>
""", unsafe_allow_html=True)


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
    displayed_symbols: set (例: {"BTC", "ETH", "ANKR"})
    current_cycles: dict (例: {"BTC": "8h", "ETH": "8h"})
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


# --- [BingX専用] カタログ読み込み（キャッシュ化） ---
@st.cache_data
def load_bingx_catalog():
    """BingXのカタログCSVを読み込み（キャッシュ化で高速化）"""
    import glob
    import csv
    
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
                        bingx_catalog[sym] = int(interval_str) * 3600
    except:
        pass
    return bingx_catalog


# --- [共通モジュール] カタログ読み込み (Bitget & MEXC) ---
@st.cache_data
def load_cycle_masters():
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


# --- [共通モジュール] Interval -> 秒 ---
def interval_to_seconds(interval: str) -> int:
    if interval == "1h": return 3600
    if interval == "4h": return 14400
    if interval == "8h": return 28800
    return 0


# --- [共通モジュール] Interval -> 配布時刻スケジュール(JST時) ---
def interval_to_sched_hours(interval: str):
    if interval == "1h": return list(range(24))
    if interval == "4h": return [1, 5, 9, 13, 17, 21]
    return [1, 9, 17]


# --- [共通モジュール] JSTの「次回配布時刻」(epoch秒) を推定 ---
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


# --- [共通モジュール] 時刻(t=時) の正規化 ---
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


# --- [表示用] remaining_s -> "あとxx分xx秒" ---
def fmt_rem(rem_s: int) -> str:
    try:
        rem_s = int(rem_s)
    except:
        return "不明"
    if rem_s <= 0: return "不明"
    m, s = divmod(rem_s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"あと{h}時間{m}分{s}秒"
    return f"あと{m}分{s}秒"


# --- [並列化] 各取引所のデータ取得関数 ---
def fetch_mexc_data(cycle_masters, now_dt):
    """MEXC専用データ取得（高速化：timeout短縮＋エラー時スキップ）"""
    data = {}
    status = "🔴"
    ua = "Mozilla/5.0"
    
    try:
        # timeout を 2秒に短縮（遅い場合は諦める）
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
        # タイムアウト時は静かに失敗（他の取引所は表示される）
        pass
    except Exception:
        # その他のエラーも静かに失敗
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
        bingx_catalog = load_bingx_catalog()  # キャッシュ化済み
        
        bx_t = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/ticker", timeout=10).json()
        bx_r = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex", timeout=10).json()
        bx_v = {x['symbol'].split('-')[0]: abs(float(x.get('priceChangePercent', 0))) for x in bx_t.get('data', [])}

        for i in bx_r.get('data', []):
            full_sym = i['symbol']
            sym = full_sym.split('-')[0]
            next_time = float(i.get('nextFundingTime', 0))
            interval_s = bingx_catalog.get(full_sym, 14400)
            
            if next_time > 1000000:
                next_epoch = int(next_time / 1000)
                remaining_s = max(0, next_epoch - int(now_dt.timestamp()))
                if full_sym not in bingx_catalog:
                    if remaining_s < 3600:
                        interval_s = 3600
                    elif remaining_s > 14400:
                        interval_s = 28800
            else:
                sched_h = [1, 5, 9, 13, 17, 21]
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
        status = "🟢"
    except: pass
    
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


# --- [API] データ取得（並列化版） ---
@st.cache_data(ttl=60)
def fetch_api_snapshot():
    """全取引所のデータを並列取得（高速化版）"""
    data = {}
    status = {"MEXC": "🔴", "BingX": "🔴", "Bitget": "🔴", "Variational": "🔴"}
    
    cycle_masters = load_cycle_masters()
    now_dt = datetime.now()
    
    # 並列実行
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
                # データをマージ
                for sym, exs in ex_data.items():
                    if sym not in data:
                        data[sym] = {}
                    data[sym].update(exs)
                status[exchange] = ex_status
            except Exception as e:
                status[exchange] = "🔴"
    
    return data, status, datetime.now().strftime("%H:%M:%S")


# --- [共通モジュール] リスク判定 ---
def calculate_risk(d1, d2, levs, t_key):
    # 戦術別リスク基準（金利時刻またぎボラ＆持続的変動を考慮）
    risk_configs = {
        "scalp": {"w": 0.5, "d": 0.9},    # スキャ：金利時刻ボラスパイクに直撃→厳しめ
        "hedge": {"w": 0.4, "d": 0.7},    # ヘッジ：中程度
        "hold": {"w": 0.3, "d": 0.6}      # ホールド：持続的変動に弱い、金利時刻ボラには強い→やや緩め
    }
    cfg = risk_configs[t_key]
    res = []
    for l in levs:
        if l > d1['m'] or l > d2['m']: 
            res.append("MAX")
        else:
            vol = ((d1['v'] + d2['v']) / 2) / (100 / l)
            res.append('❌' if vol > cfg['d'] else ('⚠️' if vol > cfg['w'] else '✅'))
    return res



# --- [エンジンA] 同時刻金利版 ---
def run_simultaneous_engine(raw, active_exs, levs, t_key):
    rows = []
    for ticker, exs in raw.items():
        filtered = {k: v for k, v in exs.items() if k in active_exs}
        if len(filtered) < 2: continue
        it = list(filtered.items())
        for i in range(len(it)):
            for j in range(i + 1, len(it)):
                ex1, d1 = it[i]; ex2, d2 = it[j]
                if d1['t'] == 0 or d2['t'] == 0: continue
                if d1['t'] == d2['t']:
                    low, high = (it[i], it[j]) if d1['rate'] < d2['rate'] else (it[j], it[i])
                    net = high[1]['rate'] - low[1]['rate']
                    diff = abs(d1['p'] - d2['p']) / d2['p'] * 100
                    rows.append({
                        "t": ticker, "ex1": low[0], "r1": low[1]['rate'], "t1": low[1]['t'], "tp1": "L",
                        "ex2": high[0], "r2": high[1]['rate'], "t2": high[1]['t'], "tp2": "S",
                        "df": diff, "n": net - diff, "rk": calculate_risk(d1, d2, levs, t_key)
                    })
    return pd.DataFrame(rows)


# --- [エンジンB] 時間差ヘッジ版 ---
def run_hedge_engine(raw, active_exs, levs, t_key):
    rows = []
    overlap_tol_s = 30

    for ticker, exs in raw.items():
        filtered = {k: v for k, v in exs.items() if k in active_exs}
        if len(filtered) < 2: continue
        it = list(filtered.items())

        for i in range(len(it)):
            for j in range(i + 1, len(it)):
                cand_a = it[i]; cand_b = it[j]
                dA = cand_a[1]; dB = cand_b[1]

                if ('remaining_s' not in dA) or ('remaining_s' not in dB): continue
                if dA['remaining_s'] <= 0 or dB['remaining_s'] <= 0: continue
                
                cycle_same = (int(dA.get("interval_s", 0)) == int(dB.get("interval_s", 0)))
                diff_s = abs(int(dA['remaining_s']) - int(dB['remaining_s']))
                
                if cycle_same and diff_s <= 120: continue
                if not cycle_same and diff_s <= 30: continue

                if dA['remaining_s'] < dB['remaining_s']:
                    ex1, d1 = cand_a; ex2, d2 = cand_b
                else:
                    ex1, d1 = cand_b; ex2, d2 = cand_a

                p1_type = "S" if d1['rate'] >= 0 else "L"
                p2_type = "L" if p1_type == "S" else "S"
                net = abs(d1['rate'])
                diff = abs(d1['p'] - d2['p']) / d2['p'] * 100 if d2['p']!=0 else 0

                rows.append({
                    "t": ticker,
                    "ex1": ex1, "r1": d1['rate'], "t1": d1.get('t', 0), "tp1": p1_type, "rem1": int(d1.get("remaining_s", 0)),
                    "ex2": ex2, "r2": d2['rate'], "t2": d2.get('t', 0), "tp2": p2_type, "rem2": int(d2.get("remaining_s", 0)),
                    "df": diff, "n": net - diff, "rk": calculate_risk(d1, d2, levs, t_key)
                })
    return pd.DataFrame(rows)


# --- サイドバー構成 ---
st.sidebar.header("👔 現場コントロール")
if st.sidebar.button('⚡️ 最新データ更新', use_container_width=True):
    st.cache_data.clear()
    raw, status, ts = fetch_api_snapshot()
    st.session_state.update({'raw': raw, 'api': status, 'update_ts': ts})

mode_ui = st.sidebar.selectbox("📊 プログラム選択", ["同時刻金利版", "時間差ヘッジ"])

st.sidebar.markdown("---")
tactic_ui = st.sidebar.radio("🔥 戦術判定", ["スキャ", "ヘッジ", "ホールド"])
t_key = "scalp" if "スキャ" in tactic_ui else ("hedge" if "ヘッジ" in tactic_ui else "hold")

# 戦術の説明（折りたたみ式）
tactic_descriptions = {
    "スキャ": """
**📌 スキャ（短期）**
- **保有時間**: 数分（直前イン、直後アウト）
- **リスク**: 金利配布時刻をまたぐ瞬間のボラティリティスパイクに直撃
- **向き**: 素早い判断と実行ができる人向け
    """,
    "ヘッジ": """
**📌 ヘッジ（中期）**
- **保有時間**: 30分〜1時間
- **リスク**: 金利時刻またぎボラ + 持続的な価格変動の両方
- **向き**: バランス重視、ある程度余裕を持ちたい人向け
    """,
    "ホールド": """
**📌 ホールド（長期）**
- **保有時間**: 3時間程度
- **リスク**: 持続的な価格変動に弱い（金利時刻ボラには強い）
- **向き**: じっくり保持、金利差ヘッジ向け
    """
}

with st.sidebar.expander("ℹ️ 戦術の説明を見る"):
    st.markdown(tactic_descriptions[tactic_ui])

st.sidebar.markdown("---")
margin = st.sidebar.number_input("証拠金 (USDT)", 10, 1000000, 100)
st.sidebar.markdown("🕹️ **レバレッジ設定**")
cols = st.sidebar.columns(5)
levs = [cols[i].number_input(str(i+1), 1, 200, [10, 20, 50, 100, 125][i], key=f"v341_l{i}") for i in range(5)]
st.sidebar.markdown("---")
st.sidebar.markdown("🏦 **対象取引所**")
sel_m = st.sidebar.checkbox("MEXC", value=True)
sel_bt = st.sidebar.checkbox("Bitget", value=True)
sel_bn = st.sidebar.checkbox("BingX", value=True)
sel_vr = st.sidebar.checkbox("Variational", value=True)
active_exs = [ex for ex, s in zip(["MEXC", "Bitget", "BingX", "Variational"], [sel_m, sel_bt, sel_bn, sel_vr]) if s]



# --- メインロジック ---
if 'raw' not in st.session_state:
    raw, status, ts = fetch_api_snapshot()
    st.session_state.update({'raw': raw, 'api': status, 'update_ts': ts})

st.markdown(f"<h2>👔 金利ーマン Dashboard <span class='update-ts'>({st.session_state.update_ts} 更新)</span></h2>", unsafe_allow_html=True)

if len(active_exs) < 2:
    st.warning("取引所を2つ以上選択してください。")
else:
    if mode_ui == "同時刻金利版":
        df = run_simultaneous_engine(st.session_state.raw, active_exs, levs, t_key)
        col1_label, col2_label = "L側 (金利低)", "S側 (金利高)"
        
        if df is not None and not df.empty:
            df = df.sort_values("n", ascending=False).drop_duplicates(subset=['t'])
            
            # サイクル周期で分類（拠点側のinterval_sで判定）
            df_1h = []
            df_4h = []
            df_8h = []
            
            for _, r in df.iterrows():
                ticker = r['t']
                ex1 = r['ex1']
                # 拠点側のinterval_sを取得
                if ticker in st.session_state.raw and ex1 in st.session_state.raw[ticker]:
                    interval_s = st.session_state.raw[ticker][ex1].get('interval_s', 0)
                    if interval_s == 3600:
                        df_1h.append(r)
                    elif interval_s == 14400:
                        df_4h.append(r)
                    elif interval_s == 28800:
                        df_8h.append(r)
                    else:
                        df_8h.append(r)  # デフォルトは8hタブに
            
            # 各カテゴリで上位10を取得
            df_1h_top10 = df_1h[:10]
            df_4h_top10 = df_4h[:10]
            df_8h_top10 = df_8h[:10]
            
            # 全てタブは全体の上位40
            df_all_top40 = df.head(40).to_dict('records')
            
            # タブ作成
            tab_all, tab_1h, tab_4h, tab_8h = st.tabs([
                f"🔥 全て ({len(df_all_top40)})", 
                f"⚡ 1時間毎 ({len(df_1h_top10)})", 
                f"⏰ 4時間毎 ({len(df_4h_top10)})", 
                f"🕐 8時間毎 ({len(df_8h_top10)})"
            ])
            
            # 各タブに表示
            def render_table(rows, label1, label2):
                if len(rows) == 0:
                    st.info("該当する銘柄がありません")
                    return
                    
                h = f"<thead><tr><th>🔥</th><th>銘柄</th><th>{label1}</th><th>{label2}</th><th>乖離</th><th>実質</th>" + "".join([f"<th>{l}倍</th>" for l in levs]) + "</tr></thead>"
                b = "<tbody>"
                for r in rows:
                    l_cells = "".join(
                        [f"<td style='color:#94a3b8;font-size:0.8em'>MAX</td>" if r['rk'][i] == "MAX"
                         else f"<td><span class='lev-amount'>${margin * levs[i] * (r['n'] / 100):.1f}</span><br>{r['rk'][i]}</td>"
                         for i in range(5)]
                    )
                    t1_str = f"{int(r['t1'])}:00 配布"
                    t2_str = f"{int(r['t2'])}:00 配布"
                    
                    b += f"<tr><td></td><td><span class='ticker-text'>{r['t']}</span></td>" \
                         f"<td><span class='ex-label'>{r['ex1']} ({r['tp1']})</span><span class='rate-val'>{r['r1']:.3f}%</span><br><span class='dist-time'>{t1_str}</span></td>" \
                         f"<td><span class='ex-label'>{r['ex2']} ({r['tp2']})</span><span class='rate-val'>{r['r2']:.3f}%</span><br><span class='dist-time'>{t2_str}</span></td>" \
                         f"<td>{r['df']:.3f}%</td><td class='net-profit'>{r['n']:.3f}%</td>{l_cells}</tr>"
                st.markdown(f"<table class='report-table'>{h}{b}</tbody></table>", unsafe_allow_html=True)
            
            with tab_all:
                render_table(df_all_top40, col1_label, col2_label)
            
            with tab_1h:
                render_table(df_1h_top10, col1_label, col2_label)
            
            with tab_4h:
                render_table(df_4h_top10, col1_label, col2_label)
            
            with tab_8h:
                render_table(df_8h_top10, col1_label, col2_label)
        else:
            st.info(f"{mode_ui} のロジックに適合する銘柄が現在ありません。")
    
    else:  # ヘッジ版は従来通り
        df = run_hedge_engine(st.session_state.raw, active_exs, levs, t_key)
        col1_label, col2_label = "拠点側 (金利源)", "ヘッジ側 (価格固定用)"
        
        if df is not None and not df.empty:
            df = df.sort_values("n", ascending=False).drop_duplicates(subset=['t']).head(40)
            
            h = f"<thead><tr><th>🔥</th><th>銘柄</th><th>{col1_label}</th><th>{col2_label}</th><th>価格乖離</th><th>実質</th>" + "".join([f"<th>{l}倍</th>" for l in levs]) + "</tr></thead>"
            b = "<tbody>"
            for _, r in df.iterrows():
                l_cells = "".join(
                    [f"<td style='color:#94a3b8;font-size:0.8em'>MAX</td>" if r['rk'][i] == "MAX"
                     else f"<td><span class='lev-amount'>${margin * levs[i] * (r['n'] / 100):.1f}</span><br>{r['rk'][i]}</td>"
                     for i in range(5)]
                )
                t1_str = fmt_rem(int(r.get("rem1", 0)))
                t2_str = fmt_rem(int(r.get("rem2", 0)))
                
                b += f"<tr><td></td><td><span class='ticker-text'>{r['t']}</span></td>" \
                     f"<td><span class='ex-label'>{r['ex1']} ({r['tp1']})</span><span class='rate-val'>{r['r1']:.3f}%</span><br><span class='dist-time'>{t1_str}</span></td>" \
                     f"<td><span class='ex-label'>{r['ex2']} ({r['tp2']})</span><span class='rate-val'>{r['r2']:.3f}%</span><br><span class='dist-time'>{t2_str}</span></td>" \
                     f"<td>{r['df']:.3f}%</td><td class='net-profit'>{r['n']:.3f}%</td>{l_cells}</tr>"
            st.markdown(f"<table class='report-table'>{h}{b}</tbody></table>", unsafe_allow_html=True)
        else:
            st.info(f"{mode_ui} のロジックに適合する銘柄が現在ありません。")

