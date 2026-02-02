import streamlit as st
import pandas as pd
import requests
import os
from datetime import datetime, timedelta



# --- ページ基本設定 ---
st.set_page_config(page_title="金利ーマン Dashboard v3.6.2", layout="wide")



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



# --- [共通モジュール] カタログ読み込み (Bitget Interval列対応) ---
def load_cycle_master():
    target_file = "bitget_true_catalog_0131_0704.csv"
    if os.path.exists(target_file):
        try:
            df = pd.read_csv(target_file, encoding="utf-8-sig")
            if 'Symbol' in df.columns and 'Interval' in df.columns:
                symbols = df['Symbol'].astype(str).str.replace("-USDT", "", regex=False)
                return dict(zip(symbols, df['Interval'].astype(str)))
        except:
            pass
    return {}



# --- [共通モジュール] Interval -> 秒 ---
def interval_to_seconds(interval: str) -> int:
    if interval == "1h":
        return 3600
    if interval == "4h":
        return 14400
    if interval == "8h":
        return 28800
    return 0



# --- [共通モジュール] Interval -> 配布時刻スケジュール(JST時) ---
def interval_to_sched_hours(interval: str):
    if interval == "1h":
        return list(range(24))
    if interval == "4h":
        return [1, 5, 9, 13, 17, 21]
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



# --- [共通モジュール] 時刻(t=時) の正規化 (同時刻版が依存しているため維持) ---
def normalize_time(time_input, exchange_name, cycle_hint=None):
    now_h = (datetime.now().hour)
    sched = [1, 9, 17]
    if exchange_name == "BingX":
        sched = [1, 5, 9, 13, 17, 21]

    if cycle_hint:
        if cycle_hint == '1h':
            sched = list(range(24))
        elif cycle_hint == '4h':
            sched = [1, 5, 9, 13, 17, 21]
        elif cycle_hint == '8h':
            sched = [1, 9, 17]

    def get_fallback():
        return next((h for h in sched if h > now_h), sched[0])

    try:
        if not time_input or time_input == 0:
            return get_fallback()

        if isinstance(time_input, (int, float)):
            if time_input < 1000000:
                return get_fallback()
            dt = pd.to_datetime(time_input, unit='ms')
        else:
            dt = pd.to_datetime(time_input)

        jst_dt = dt + timedelta(hours=9)
        hour = jst_dt.hour

        if exchange_name == "MEXC":
            mexc_sched = [1, 9, 17]
            return int(min(mexc_sched, key=lambda x: abs(x - hour)))

        return int(hour)
    except Exception:
        return get_fallback()



# --- [表示用] remaining_s -> "あとxx分" ---
def fmt_rem(rem_s: int) -> str:
    try:
        rem_s = int(rem_s)
    except:
        return "配布時刻不明"
    if rem_s <= 0:
        return "配布時刻不明"
    m, s = divmod(rem_s, 60)
    if m >= 60:
        h, m2 = divmod(m, 60)
        return f"あと {h}時間{m2}分"
    return f"あと {m}分{s}秒"



# --- [共通モジュール] APIデータ取得 ---
@st.cache_data(ttl=60)
def fetch_api_snapshot():
    data = {}
    status = {"MEXC": "🔴", "BingX": "🔴", "Bitget": "🔴", "Variational": "🔴"}
    ua = "Mozilla/5.0"

    cycle_master = load_cycle_master()
    now_dt = datetime.now()  # ローカル=JST想定

    # 1. MEXC
    try:
        r = requests.get("https://api.mexc.com/api/v1/contract/ticker", headers={"User-Agent": ua}, timeout=5).json()
        if r.get('success'):
            d = r.get("data")

            # data の形を吸収（list / dict / resultList）
            if isinstance(d, list):
                items = d
            elif isinstance(d, dict):
                if isinstance(d.get("resultList"), list):
                    items = d["resultList"]
                else:
                    items = [d]
            else:
                items = []

            for i in items:
                # symbol: "BTC_USDT"
                sym = str(i.get("symbol", "")).split('_')[0]
                if not sym:
                    continue

                # 金利：lastFundingRate が無い場合 fundingRate を使う
                fr = i.get("lastFundingRate")
                if fr is None:
                    fr = i.get("fundingRate", 0)

                # 価格：lastPrice
                lp = i.get("lastPrice")

                # 変動率：riseFallRate
                rr = i.get("riseFallRate", 0)

                # 次回：nextSettleTime(ms) があるなら残り秒はそれを最優先
                next_time = i.get("nextSettleTime")
                remaining_s = 0
                try:
                    if next_time is not None and float(next_time) > 1000000:
                        next_epoch = int(float(next_time) / 1000)
                        remaining_s = max(0, next_epoch - int(now_dt.timestamp()))
                except:
                    remaining_s = 0

                # t（同時刻版表示用）は、nextSettleTime から推定（取れない時だけフォールバック）
                t_val = normalize_time(next_time, "MEXC")
                
                # remaining_s が取れない場合は 1h 推定で埋める（MEXCは1hが多い前提）
                if remaining_s <= 0:
                    interval_s_guess = 3600
                    now_epoch = int(now_dt.timestamp())
                    remaining_s = interval_s_guess - (now_epoch % interval_s_guess)

                data.setdefault(sym, {})['MEXC'] = {
                    'rate': float(fr) * 100,
                    'p': float(lp) if lp is not None else 0.0,
                    'v': abs(float(rr)) * 100,
                    'm': 200 if sym in ['BTC', 'ETH'] else 50,
                    't': t_val,
                    # intervalはMEXC側で銘柄ごとに違う可能性があるが、まずは remaining_s が正しいことを優先
                    'interval_s': 3600,
                    'remaining_s': remaining_s
                }

            status["MEXC"] = "🟢"
    except:
        pass

    # 2. Bitget（tickersにnextFundingTimeが無いためCSV Intervalからremaining_s推定）
    try:
        bg_r = requests.get("https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures", timeout=5).json()
        if bg_r.get('code') == '00000':
            for i in bg_r['data']:
                sym = i['symbol'].replace('USDT', '')

                hint = cycle_master.get(sym, None)
                if not hint:
                    hint = "4h"

                t_val = normalize_time(0, "Bitget", cycle_hint=hint)

                sched_h = interval_to_sched_hours(hint)
                next_epoch = calc_next_settle_epoch_from_sched(sched_h, now_dt)
                remaining_s = max(0, next_epoch - int(now_dt.timestamp()))
                interval_s = interval_to_seconds(hint)

                data.setdefault(sym, {})['Bitget'] = {
                    'rate': float(i['fundingRate']) * 100,
                    'p': float(i['lastPr']),
                    'v': abs(float(i.get('priceChangePercent', 0))) * 100,
                    'm': 125 if sym in ['BTC', 'ETH'] else 50,
                    't': t_val,
                    'interval_s': interval_s,
                    'remaining_s': remaining_s
                }
            status["Bitget"] = "🟢"
    except:
        pass

    # 3. BingX
    try:
        bx_t = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/ticker", timeout=5).json()
        bx_r = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex", timeout=5).json()
        bx_v = {x['symbol'].split('-')[0]: abs(float(x['priceChangePercent'])) for x in bx_t.get('data', [])}

        sched_h = [1, 5, 9, 13, 17, 21]
        next_epoch = calc_next_settle_epoch_from_sched(sched_h, now_dt)
        remaining_s_base = max(0, next_epoch - int(now_dt.timestamp()))

        for i in bx_r.get('data', []):
            sym = i['symbol'].split('-')[0]
            next_time = float(i.get('nextFundingTime', 0))
            t_val = normalize_time(next_time, "BingX")

            data.setdefault(sym, {})['BingX'] = {
                'rate': float(i['lastFundingRate']) * 100,
                'p': float(i['markPrice']),
                'v': bx_v.get(sym, 0),
                'm': 150 if sym in ['BTC', 'ETH'] else 20,
                't': t_val,
                'interval_s': 14400,
                'remaining_s': remaining_s_base
            }
        status["BingX"] = "🟢"
    except:
        pass

    # 4. Variational（APR→1h→配布ぶん）
    try:
        v_url = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
        v = requests.get(v_url, timeout=8).json()

        listings = v.get("listings") or v.get("data") or []
        for it in listings:
            sym = it.get("ticker") or it.get("listing_name") or it.get("symbol") or it.get("name")
            if not sym:
                continue

            try:
                interval_s = int(float(it.get("funding_interval_s", 3600)))
            except:
                interval_s = 3600

            try:
                apr = float(it.get("funding_rate", 0.0))
            except:
                apr = 0.0

            hourly = apr / 8760.0
            hours_per_settle = max(1.0, interval_s / 3600.0)
            settle_rate = hourly * hours_per_settle  # 1回配布ぶん

            try:
                p = float(it.get("mark_price") or 0.0)
            except:
                p = 0.0

            now_epoch = int(now_dt.timestamp())
            remaining_s = interval_s - (now_epoch % interval_s)

            data.setdefault(sym, {})['Variational'] = {
                'rate': settle_rate * 100.0,
                'p': p,
                'v': 0.0,
                'm': 0,
                't': 0,  # ヘッジ版は残り時間表示にするので問題なし
                'interval_s': interval_s,
                'remaining_s': remaining_s
            }

        status["Variational"] = "🟢"
    except:
        pass

    return data, status, datetime.now().strftime("%H:%M:%S")



# --- [共通モジュール] リスク判定エンジン ---
def calculate_risk(d1, d2, levs, t_key):
    risk_configs = {"scalp": {"w": 0.9, "d": 1.2}, "hedge": {"w": 0.4, "d": 0.7}, "hold": {"w": 0.2, "d": 0.4}}
    cfg = risk_configs[t_key]
    res = []
    for l in levs:
        if l > d1['m'] or l > d2['m']:
            res.append("MAX")
        else:
            vol = ((d1['v'] + d2['v']) / 2) / (100 / l)
            res.append('❌' if vol > cfg['d'] else ('⚠️' if vol > cfg['w'] else '✅'))
    return res



# --- [エンジンA] 同時刻金利版（裁定取引） ※変更なし ---
def run_simultaneous_engine(raw, active_exs, levs, t_key):
    rows = []
    for ticker, exs in raw.items():
        filtered = {k: v for k, v in exs.items() if k in active_exs}
        if len(filtered) < 2:
            continue
        it = list(filtered.items())
        for i in range(len(it)):
            for j in range(i + 1, len(it)):
                ex1, d1 = it[i]
                ex2, d2 = it[j]

                if d1['t'] == 0 or d2['t'] == 0:
                    continue

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



# --- [エンジンB] 時間差ヘッジ版（remaining_s版） ---
def run_hedge_engine(raw, active_exs, levs, t_key):
    st.write("DEBUG mexc remaining_s sample:", next((v["MEXC"]["remaining_s"] for k,v in raw.items() if "MEXC" in v and "remaining_s" in v["MEXC"]), None))
    rows = []
    overlap_tol_s = 120  # “ほぼ同時”除外

    for ticker, exs in raw.items():
        filtered = {k: v for k, v in exs.items() if k in active_exs}
        if len(filtered) < 2:
            continue
        it = list(filtered.items())

        for i in range(len(it)):
            for j in range(i + 1, len(it)):
                cand_a = it[i]
                cand_b = it[j]

                dA = cand_a[1]
                dB = cand_b[1]

                if ('remaining_s' not in dA) or ('remaining_s' not in dB):
                    continue
                if dA['remaining_s'] <= 0 or dB['remaining_s'] <= 0:
                    continue

                # 配布がほぼ重なる場合は除外（ヘッジにならない）
                if abs(int(dA['remaining_s']) - int(dB['remaining_s'])) <= overlap_tol_s:
                    continue

                # 早い方（remaining_sが小さい方）を拠点にする
                if dA['remaining_s'] < dB['remaining_s']:
                    ex1, d1 = cand_a
                    ex2, d2 = cand_b
                else:
                    ex1, d1 = cand_b
                    ex2, d2 = cand_a

                p1_type = "S" if d1['rate'] >= 0 else "L"
                p2_type = "L" if p1_type == "S" else "S"

                net = abs(d1['rate'])
                diff = abs(d1['p'] - d2['p']) / d2['p'] * 100 if d2['p'] != 0 else 0

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
tactic_ui = st.sidebar.radio("🔥 戦術判定", ["スキャ", "ヘッジ", "ホールド"])
t_key = "scalp" if "スキャ" in tactic_ui else ("hedge" if "ヘッジ" in tactic_ui else "hold")



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



# --- メインロジック分岐 ---
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
    else:
        df = run_hedge_engine(st.session_state.raw, active_exs, levs, t_key)
        col1_label, col2_label = "拠点側 (金利源)", "ヘッジ側 (価格固定用)"



    if df is not None and not df.empty:
        df = df.sort_values("n", ascending=False).drop_duplicates(subset=['t']).head(40)

        h = f"<thead><tr><th>🔥</th><th>銘柄</th><th>{col1_label}</th><th>{col2_label}</th><th>乖離</th><th>実質</th>" + "".join([f"<th>{l}倍</th>" for l in levs]) + "</tr></thead>"
        b = "<tbody>"

        for _, r in df.iterrows():
            l_cells = "".join(
                [f"<td style='color:#94a3b8;font-size:0.8em'>MAX</td>" if r['rk'][i] == "MAX"
                 else f"<td><span class='lev-amount'>${margin * levs[i] * (r['n'] / 100):.1f}</span><br>{r['rk'][i]}</td>"
                 for i in range(5)]
            )

            if mode_ui == "時間差ヘッジ":
                t1_str = fmt_rem(int(r.get("rem1", 0)))
                t2_str = fmt_rem(int(r.get("rem2", 0)))
            else:
                t1_str = f"{int(r['t1'])}:00 配布"
                t2_str = f"{int(r['t2'])}:00 配布"

            b += f"<tr><td></td><td><span class='ticker-text'>{r['t']}</span></td>" \
                 f"<td><span class='ex-label'>{r['ex1']} ({r['tp1']})</span><span class='rate-val'>{r['r1']:.3f}%</span><br><span class='dist-time'>{t1_str}</span></td>" \
                 f"<td><span class='ex-label'>{r['ex2']} ({r['tp2']})</span><span class='rate-val'>{r['r2']:.3f}%</span><br><span class='dist-time'>{t2_str}</span></td>" \
                 f"<td>{r['df']:.3f}%</td><td class='net-profit'>{r['n']:.3f}%</td>{l_cells}</tr>"

        st.markdown(f"<table class='report-table'>{h}{b}</tbody></table>", unsafe_allow_html=True)
    else:
        st.info(f"{mode_ui} のロジックに適合する銘柄が現在ありません。")
