import requests
import json

r = requests.get("https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures").json()

# BIRBのデータだけ抜き出して表示
for item in r['data']:
    if item['symbol'] == 'BIRBUSDT':
        print(json.dumps(item, indent=2, ensure_ascii=False))
        break
