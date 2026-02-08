import requests
from config import API_KEY, SECRET_KEY, SYMBOL, BASE_URL

# APIのベースURL
BASE_URL = "https://open-api.bingx.com"

def get_available_symbols():
    """利用可能なシンボル一覧を取得"""
    url = f"{BASE_URL}/openApi/swap/v2/quote/contracts"
    response = requests.get(url)
    return response.json()

# シンボル一覧を取得して表示
print("BingX利用可能なシンボル一覧を取得中...")
symbols_data = get_available_symbols()

if symbols_data['code'] == 0:
    print(f"\n取得成功！{len(symbols_data['data'])}個のシンボルが見つかりました\n")
    
    # 金（XAU）関連のシンボルを検索
    print("=== 金（XAU）関連のシンボル ===")
    for contract in symbols_data['data']:
        if 'XAU' in contract['symbol'].upper() or 'GOLD' in contract['symbol'].upper():
            print(f"シンボル: {contract['symbol']}")
            print(f"  名前: {contract.get('asset', 'N/A')}")
            print(f"  最小数量: {contract.get('minQty', 'N/A')}")
            print(f"  数量精度: {contract.get('quantityPrecision', 'N/A')}")
            print(f"  価格精度: {contract.get('pricePrecision', 'N/A')}")
            print()
    
    # 全シンボルを表示（多い場合は最初の20個のみ）
    print("\n=== 全利用可能シンボル（最初の20個）===")
    for i, contract in enumerate(symbols_data['data'][:20]):
        print(f"{i+1}. {contract['symbol']}")
else:
    print(f"エラー: {symbols_data}")
