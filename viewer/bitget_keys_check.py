import requests
import json

url = "https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures"
j = requests.get(url, timeout=10).json()

print("code:", j.get("code"), "msg:", j.get("msg"))

data = j.get("data") or []
print("data length:", len(data))

if not data:
    raise SystemExit("No data returned")

first = data[0]
print("first item keys:", list(first.keys()))

# 先頭の中身も少し見せる（長すぎるので一部だけ）
sample_keys = list(first.keys())[:30]
sample = {k: first.get(k) for k in sample_keys}
print("first item sample:")
print(json.dumps(sample, ensure_ascii=False, indent=2))
