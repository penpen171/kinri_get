import requests
import pandas as pd
import time
from datetime import datetime

def export_bingx_true_catalog():
    # 1. まず全銘柄リストを取得
    ticker_url = "https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex"
    print("👔 BingX全USDTペアを履歴解析中...（APIの嘘を履歴で暴きます）")
    
    try:
        response = requests.get(ticker_url, timeout=10).json()
        if response.get('code') != 0: return

        full_list = []
        # 時間がかかるため、全銘柄をループ
        for item in response.get('data', []):
            symbol = item.get('symbol')
            if not symbol.endswith("-USDT") or "-USDC" in symbol:
                continue
            
            # --- 履歴から周期を特定する「履歴探偵」ロジック ---
            # その銘柄の直近3件の金利履歴を取得
            hist_url = f"https://open-api.bingx.com/openApi/swap/v2/quote/fundingRate?symbol={symbol}"
            hist_data = requests.get(hist_url, timeout=5).json()
            
            interval = 8 # デフォルト
            if hist_data.get('code') == 0 and len(hist_data['data']) >= 2:
                # 直近2つの金利配布時間の差を計算
                t1 = int(hist_data['data'][0]['fundingTime'])
                t2 = int(hist_data['data'][1]['fundingTime'])
                diff_h = abs(t1 - t2) / (1000 * 3600)
                
                if 0.5 <= diff_h <= 1.5: interval = 1
                elif 3.5 <= diff_h <= 4.5: interval = 4
                else: interval = 8
            
            rate = float(item.get('lastFundingRate', 0)) * 100
            full_list.append({
                'Symbol': symbol,
                'Interval': f"{interval}h",
                'Current_Rate(%)': rate,
                'Daily_Rate(%)': rate * (24 / interval),
                'Method': "History_Search"
            })
            # API負荷軽減のためわずかに待機
            time.sleep(0.05)

        df = pd.DataFrame(full_list)
        df = df.sort_values(by=['Interval', 'Symbol'])
        filename = f"bingx_true_catalog_history_{datetime.now().strftime('%m%d_%H%M')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        
        print("-" * 60)
        print(f"✅ 完了: {len(df)} 銘柄を履歴から確定させました。")
        print(f"📊 統計:\n{df['Interval'].value_counts().sort_index().to_string()}")
        print(f"💾 保存先: {filename}")

    except Exception as e:
        print(f"❌ エラー: {e}")

if __name__ == "__main__":
    export_bingx_true_catalog()