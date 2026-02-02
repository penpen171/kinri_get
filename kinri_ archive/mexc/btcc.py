import requests
import pandas as pd
from datetime import datetime
import time

def verify_mexc_funding_history_stealth():
    print("👔 MEXC 履歴照合（ステルスモード）を開始します...")
    
    # 調査対象銘柄（疑わしいもの＋メジャーどころ）
    target_symbols = [
        'BTC_USDT',    # 基準
        'SILVER_USDT', # 1h疑惑
        'ALU_USDT',    # 1h疑惑
        'PONKE_USDT',  # 1h疑惑
        'SENT_USDT',   # 本命
        'BAN_USDT'     # 高金利
    ]
    
    # ブラウザのフリをするための「通行手形」ヘッダー
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.mexc.com/",
        "Origin": "https://www.mexc.com"
    }

    results = []
    
    for symbol in target_symbols:
        try:
            # 1. 少し待機（連打検知を避ける）
            time.sleep(1)
            
            url = "https://contract.mexc.com/api/v1/contract/funding-rate/history"
            params = {
                'symbol': symbol,
                'pageSize': 6, # 直近6回分
                'pageNum': 1
            }
            
            # ヘッダー付きでリクエスト
            res = requests.get(url, headers=headers, params=params, timeout=10)
            
            # 応答チェック
            if res.status_code != 200:
                print(f"⚠️ {symbol}: アクセス拒否 (Status: {res.status_code})")
                continue
                
            try:
                data = res.json()
            except:
                print(f"❌ {symbol}: JSON変換失敗（まだブロックされています）")
                continue
            
            if not data.get('success'):
                # 成功フラグがFalseの場合
                print(f"⚠️ {symbol}: APIエラー ({data.get('message')})")
                continue
                
            history = data['data']['resultList']
            if not history:
                print(f"⚠️ {symbol}: 履歴データなし")
                continue
            
            # --- ここで真実が判明します ---
            times = []
            for h in history:
                ts = h['settleTime']
                dt = datetime.fromtimestamp(ts / 1000)
                times.append(dt.strftime('%d日 %H:%M'))
            
            # 最新とその前の差分計算（時間）
            latest_ts = history[0]['settleTime']
            prev_ts = history[1]['settleTime']
            diff_hours = (latest_ts - prev_ts) / (1000 * 3600)
            
            # 判定
            if 0.9 <= diff_hours <= 1.1:
                cycle_status = "🔥 1h (確定)"
            elif 3.9 <= diff_hours <= 4.1:
                cycle_status = "⚠️ 4h (確定)"
            elif 7.9 <= diff_hours <= 8.1:
                cycle_status = "🛡️ 8h (確定)"
            else:
                cycle_status = f"❓ 不明 ({round(diff_hours,1)}h)"
            
            print(f"✅ {symbol} 取得成功: {cycle_status}")
            
            results.append({
                'Symbol': symbol.replace('_', '-'),
                'Cycle_Verdict': cycle_status,
                'Interval_Hours': round(diff_hours, 1),
                'History_Log (Latest First)': " -> ".join(times[:3])
            })
            
        except Exception as e:
            print(f"❌ {symbol} 処理エラー: {e}")

    # 結果表示
    if results:
        df = pd.DataFrame(results)
        print("-" * 60)
        print("📊 【最終結論】MEXC配布サイクル真偽判定:")
        print(df.to_string(index=False))
        df.to_csv("mexc_cycle_final_verdict.csv", index=False, encoding='utf-8-sig')
    else:
        print("\n❌ データを取得できませんでした。VPN等でIPを変える必要があるかもしれません。")

if __name__ == "__main__":
    verify_mexc_funding_history_stealth()