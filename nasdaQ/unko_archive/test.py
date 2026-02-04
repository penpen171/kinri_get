import requests

def get_all_bingx_symbols():
    # 最新の有効なエンドポイント
    url = "https://open-api.bingx.com/openApi/swap/v2/quote/tickers"
    
    try:
        print("🔍 BingX最新APIから全銘柄リストを取得中...")
        res = requests.get(url, timeout=10).json()
        
        if res.get("code") == 0:
            tickers = res.get("data", [])
            # ダウを指す可能性のあるキーワード
            keywords = ["DOW", "DJI", "WALLST", "US30", "INDEX", "NAS", "SP500"]
            
            print(f"\n合計 {len(tickers)} 銘柄が見つかりました。")
            print("-" * 50)
            
            found = False
            for t in tickers:
                symbol = t.get("symbol", "")
                # キーワード検索
                if any(k in symbol.upper() for k in keywords):
                    print(f"✅ 候補発見: {symbol:25} | 現在値: {t.get('lastPrice')}")
                    found = True
            
            if not found:
                print("❌ キーワードに合致する銘柄が見つかりませんでした。")
                print("💡 ヒント: BingXのアプリでダウのチャートを開き、その詳細（!ボタンなど）から正確な『取引ペア名』を確認してみてください。")
        else:
            print(f"❌ APIエラー: {res.get('msg')} (Code: {res.get('code')})")
            
    except Exception as e:
        print(f"⚠️ 接続失敗: {e}")

if __name__ == "__main__":
    get_all_bingx_symbols()