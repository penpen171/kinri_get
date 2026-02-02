import requests
import pandas as pd
import time
from datetime import datetime
import os

def collect_mexc_data_continuous(interval_sec=60):
    print("👔 MEXC サイクル自動蓄積システム起動...")
    print(f"📊 {interval_sec}秒ごとにデータを記録し、'mexc_cycle_log.csv' に保存します。")
    print("🚫 終了するには Ctrl+C を押してください。")
    
    log_file = "mexc_cycle_log.csv"
    
    while True:
        try:
            now = datetime.now()
            ts_str = now.strftime('%Y-%m-%d %H:%M:%S')
            
            # API取得
            url = "https://contract.mexc.com/api/v1/contract/ticker"
            response = requests.get(url, timeout=10).json()
            data = response['data']
            
            records = []
            for item in data:
                symbol = item['symbol']
                if not symbol.endswith("_USDT"): continue
                
                raw_next_t = int(item.get('nextSettleTime', 0))
                # 単位補正
                next_t_ms = raw_next_t * 1000 if len(str(raw_next_t)) == 10 else raw_next_t
                next_dt = datetime.fromtimestamp(next_t_ms / 1000).strftime('%H:%M:%S')
                
                records.append({
                    'timestamp': ts_str,
                    'symbol': symbol,
                    'rate': float(item.get('fundingRate', 0)) * 100,
                    'next_settle': next_dt
                })
            
            # DataFrame化して追記
            df_new = pd.DataFrame(records)
            
            # ファイルが存在しない場合はヘッダー付きで作成、存在すれば追記
            if not os.path.isfile(log_file):
                df_new.to_csv(log_file, index=False, encoding='utf-8-sig')
            else:
                df_new.to_csv(log_file, mode='a', header=False, index=False, encoding='utf-8-sig')
            
            print(f"✅ 記録完了: {ts_str} (対象: {len(df_new)} 銘柄)")
            
            # 指定秒数待機
            time.sleep(interval_sec)
            
        except Exception as e:
            print(f"⚠️ エラー発生(再試行します): {e}")
            time.sleep(10)

if __name__ == "__main__":
    collect_mexc_data_continuous(60) # 60秒間隔