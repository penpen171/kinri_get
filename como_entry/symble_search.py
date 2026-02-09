import requests
import pandas as pd

def find_gold_symbol():
    # BingXの主要なコントラクト取得エンドポイント（V2）
    url = "https://open-api.bingx.com/openApi/swap/v2/quote/contracts"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get("code") == 0:
            all_symbols = data.get("data", [])
            print(f"Total symbols found: {len(all_symbols)}")
            
            # 'XAU' または 'GOLD' を含むシンボルを検索
            gold_symbols = [s for s in all_symbols if "OIL" in s['symbol'] or "WTI" in s['symbol']]
            
            if gold_symbols:
                print("\n=== Found Gold Symbols ===")
                for s in gold_symbols:
                    print(f"Symbol: {s['symbol']} | Asset: {s.get('asset')} | Currency: {s.get('currency')}")
                return gold_symbols[0]['symbol'] # 最初の候補を返す
            else:
                print("No symbols found containing 'XAU' or 'GOLD'.")
                return None
        else:
            print(f"API Error: {data}")
            return None
            
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

# 実行
valid_symbol = find_gold_symbol()
