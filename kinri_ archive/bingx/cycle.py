import requests
import json
from datetime import datetime

def check_bingx_funding():
    url = "https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex"
    print(f"Fetching BingX premiumIndex from {url} ...")
    
    try:
        r = requests.get(url, timeout=10).json()
        data = r.get("data", [])
        
        # チェックしたい銘柄
        targets = ["SENT-USDT", "BTC-USDT", "ETH-USDT"]
        
        print(f"Current System Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)
        
        found_count = 0
        for item in data:
            symbol = item.get("symbol")
            if symbol in targets:
                found_count += 1
                nft = item.get("nextFundingTime")
                lfr = item.get("lastFundingRate")
                
                print(f"Symbol: {symbol}")
                print(f"  lastFundingRate: {lfr}")
                print(f"  nextFundingTime: {nft} (ms)")
                
                if nft:
                    dt = datetime.fromtimestamp(int(nft)/1000)
                    print(f"  -> DateTime: {dt} (Local)")
                    
                    # 残り時間計算
                    rem_s = int(nft)/1000 - datetime.now().timestamp()
                    m, s = divmod(int(rem_s), 60)
                    h, m = divmod(m, 60)
                    print(f"  -> Remaining: {h}h {m}m {s}s")
                else:
                    print("  -> nextFundingTime is NULL/Missing")
                    
                print("-" * 60)
        
        if found_count == 0:
            print("Target symbols not found in API response.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_bingx_funding()
