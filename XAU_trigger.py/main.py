import hashlib
import hmac
import time
import requests
import schedule
from datetime import datetime
from config import API_KEY, SECRET_KEY, BASE_URL

# ============================================
# 設定項目
# ============================================

# 取引設定
SYMBOL = "XAUT-USDT"  # 通貨ペア

# 証拠金ベースの設定
USE_MARGIN_MODE = True  # True: 証拠金ベース, False: 固定数量
MARGIN_AMOUNT = 1.0  # 使用する証拠金額（ドル）
QUANTITY = 0.001  # USE_MARGIN_MODE=Falseの時の固定数量

# レバレッジ設定
LEVERAGE = 50  # レバレッジ倍率（1-125）
LEVERAGE_SIDE = "BOTH"  # BOTH（片建て）, LONG（両建てロング）, SHORT（両建てショート）

# 証拠金モード設定
MARGIN_TYPE = "ISOLATED"  # ISOLATED（分離）または CROSSED（クロス）

# トリガー注文設定（現在価格からの幅：ドル）
TRIGGER_OFFSET_LONG = 5.0  # ロングのトリガー幅
TRIGGER_OFFSET_SHORT = -5.0  # ショートのトリガー幅

# ============================================
# 損切り設定モード
# ============================================
# 選択肢: "NONE" (設定なし), "FIXED_OFFSET" (固定幅), "PERCENTAGE" (パーセント), "LOSS_AMOUNT" (損失額)
STOP_LOSS_MODE = "PERCENTAGE"

# 1. 固定幅モード (FIXED_OFFSET) - 現在価格からの幅をドルで指定
STOP_LOSS_OFFSET_LONG = -1.0  # ロング損切り幅（ドル）例：現在価格-1ドル
STOP_LOSS_OFFSET_SHORT = 1.0  # ショート損切り幅（ドル）例：現在価格+1ドル

# 2. パーセントモード (PERCENTAGE) - 現在価格からのパーセントで指定
STOP_LOSS_PERCENTAGE_LONG = -10.0  # ロング損切り（%）例：-0.5% = 現在価格の0.5%下
STOP_LOSS_PERCENTAGE_SHORT = 10.0  # ショート損切り（%）例：+0.5% = 現在価格の0.5%上

# 3. 損失額モード (LOSS_AMOUNT) - 許容する損失額をドルで指定
MAX_LOSS_AMOUNT_LONG = 5.0  # ロングの最大損失額（ドル）
MAX_LOSS_AMOUNT_SHORT = 5.0  # ショートの最大損失額（ドル）

# 利確設定（オプション）
TAKE_PROFIT_OFFSET_LONG = None
TAKE_PROFIT_OFFSET_SHORT = None

# 比率モード（トリガー注文用）
USE_RATIO_MODE = False
TRIGGER_RATIO_LONG = 1/10000
TRIGGER_RATIO_SHORT = -1/10000

# スケジュール設定
SCHEDULE_TIME = "07:54"  # 実行時刻（HH:MM形式）
USE_SCHEDULE = False  # True: スケジュール実行, False: 即時実行

# 価格設定
PRICE_TYPE = "MARK_PRICE"  # MARK_PRICE または CONTRACT_PRICE
PRICE_DECIMALS = 1
QUANTITY_DECIMALS = 6
MIN_QUANTITY = 0.000001

# ============================================
# 関数定義
# ============================================

def generate_signature(query_string, secret_key):
    """署名を生成"""
    signature = hmac.new(
        secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def get_current_price(symbol):
    """現在価格を取得"""
    url = f"{BASE_URL}/openApi/swap/v2/quote/price"
    params = {"symbol": symbol}
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if data['code'] == 0:
            return float(data['data']['price'])
        else:
            raise Exception(f"価格取得エラー: {data}")
    except Exception as e:
        print(f"エラー: {e}")
        return None

def calculate_quantity(current_price, margin_amount, leverage):
    """証拠金から数量を計算"""
    position_value = margin_amount * leverage
    quantity = position_value / current_price
    quantity = round(quantity / MIN_QUANTITY) * MIN_QUANTITY
    quantity = round(quantity, QUANTITY_DECIMALS)
    return quantity

def calculate_stop_loss_prices(current_price, quantity):
    """損切り価格を計算（4つのモードに対応）"""
    
    if STOP_LOSS_MODE == "NONE":
        # モード0: 損切り設定なし
        print(f"\n  【損切り設定: なし】")
        print(f"    損切り注文は発注されません")
        return None
    
    elif STOP_LOSS_MODE == "FIXED_OFFSET":
        # モード1: 固定幅（ドル）
        sl_long = current_price + STOP_LOSS_OFFSET_LONG
        sl_short = current_price + STOP_LOSS_OFFSET_SHORT
        
        print(f"\n  【損切り設定: 固定幅モード】")
        print(f"    ロング: 現在価格 {STOP_LOSS_OFFSET_LONG:+.1f}ドル = {sl_long:.1f}")
        print(f"    ショート: 現在価格 {STOP_LOSS_OFFSET_SHORT:+.1f}ドル = {sl_short:.1f}")
        
    elif STOP_LOSS_MODE == "PERCENTAGE":
        # モード2: パーセント
        sl_long = current_price * (1 + STOP_LOSS_PERCENTAGE_LONG / 100)
        sl_short = current_price * (1 + STOP_LOSS_PERCENTAGE_SHORT / 100)
        
        print(f"\n  【損切り設定: パーセントモード】")
        print(f"    ロング: 現在価格 {STOP_LOSS_PERCENTAGE_LONG:+.2f}% = {sl_long:.1f}")
        print(f"    ショート: 現在価格 {STOP_LOSS_PERCENTAGE_SHORT:+.2f}% = {sl_short:.1f}")
        
    elif STOP_LOSS_MODE == "LOSS_AMOUNT":
        # モード3: 損失額
        price_move_long = MAX_LOSS_AMOUNT_LONG / (quantity * LEVERAGE)
        price_move_short = MAX_LOSS_AMOUNT_SHORT / (quantity * LEVERAGE)
        
        sl_long = current_price - price_move_long
        sl_short = current_price + price_move_short
        
        print(f"\n  【損切り設定: 損失額モード】")
        print(f"    ロング: 最大損失 ${MAX_LOSS_AMOUNT_LONG} → 損切り価格 {sl_long:.1f}")
        print(f"    ショート: 最大損失 ${MAX_LOSS_AMOUNT_SHORT} → 損切り価格 {sl_short:.1f}")
        print(f"    (数量: {quantity}, レバレッジ: {LEVERAGE}x を考慮)")
        
    else:
        raise ValueError(f"無効な損切りモード: {STOP_LOSS_MODE}")
    
    return {
        'sl_long': round(sl_long, PRICE_DECIMALS),
        'sl_short': round(sl_short, PRICE_DECIMALS)
    }

def set_leverage(symbol, side, leverage):
    """レバレッジを設定（両建て対応）"""
    timestamp = str(int(time.time() * 1000))
    
    # 両建てモードの場合、LONGとSHORTを個別に設定
    if side == "BOTH":
        results = []
        for position_side in ["LONG", "SHORT"]:
            params = {
                "symbol": symbol,
                "side": position_side,
                "leverage": str(leverage),
                "timestamp": str(int(time.time() * 1000))  # タイムスタンプを更新
            }
            
            query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
            signature = generate_signature(query_string, SECRET_KEY)
            
            headers = {"X-BX-APIKEY": API_KEY}
            url = f"{BASE_URL}/openApi/swap/v2/trade/leverage?{query_string}&signature={signature}"
            
            try:
                response = requests.post(url, headers=headers)
                results.append({position_side: response.json()})
                time.sleep(0.1)  # API制限対策
            except Exception as e:
                results.append({position_side: {"error": str(e)}})
        
        return {"BOTH": results}
    else:
        params = {
            "symbol": symbol,
            "side": side,
            "leverage": str(leverage),
            "timestamp": timestamp
        }
        
        query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
        signature = generate_signature(query_string, SECRET_KEY)
        
        headers = {"X-BX-APIKEY": API_KEY}
        url = f"{BASE_URL}/openApi/swap/v2/trade/leverage?{query_string}&signature={signature}"
        
        try:
            response = requests.post(url, headers=headers)
            return response.json()
        except Exception as e:
            return {"error": str(e)}


def set_margin_type(symbol, margin_type):
    """証拠金モードを設定"""
    timestamp = str(int(time.time() * 1000))
    
    params = {
        "symbol": symbol,
        "marginType": margin_type,
        "timestamp": timestamp
    }
    
    query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
    signature = generate_signature(query_string, SECRET_KEY)
    
    headers = {"X-BX-APIKEY": API_KEY}
    url = f"{BASE_URL}/openApi/swap/v2/trade/marginType?{query_string}&signature={signature}"
    
    try:
        response = requests.post(url, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def calculate_trigger_prices(current_price):
    """トリガー価格を計算"""
    if USE_RATIO_MODE:
        trigger_long = current_price * (1 + TRIGGER_RATIO_LONG)
        trigger_short = current_price * (1 + TRIGGER_RATIO_SHORT)
    else:
        trigger_long = current_price + TRIGGER_OFFSET_LONG
        trigger_short = current_price + TRIGGER_OFFSET_SHORT
    
    return {
        'trigger_long': round(trigger_long, PRICE_DECIMALS),
        'trigger_short': round(trigger_short, PRICE_DECIMALS)
    }

def place_order(symbol, side, position_side, order_type, quantity, stop_price=None):
    """注文を発注（統一関数）"""
    timestamp = str(int(time.time() * 1000))
    
    params = {
        "symbol": symbol,
        "side": side,
        "positionSide": position_side,
        "type": order_type,
        "quantity": str(quantity),
        "workingType": PRICE_TYPE,
        "timestamp": timestamp
    }
    
    if stop_price:
        params["stopPrice"] = str(stop_price)
    
    query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
    signature = generate_signature(query_string, SECRET_KEY)
    
    headers = {"X-BX-APIKEY": API_KEY}
    url = f"{BASE_URL}/openApi/swap/v2/trade/order?{query_string}&signature={signature}"
    
    try:
        response = requests.post(url, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def execute_trading_strategy():
    """トリガー注文＋損切り設定を実行"""
    print("=" * 60)
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 現在価格を取得
    current_price = get_current_price(SYMBOL)
    if current_price is None:
        print("価格取得に失敗しました")
        return
    
    print(f"\n現在価格: {current_price}")
    
    # 数量を計算
    if USE_MARGIN_MODE:
        calculated_quantity = calculate_quantity(current_price, MARGIN_AMOUNT, LEVERAGE)
        position_value = MARGIN_AMOUNT * LEVERAGE
        print(f"\n【証拠金ベース計算】")
        print(f"  証拠金: {MARGIN_AMOUNT}ドル")
        print(f"  レバレッジ: {LEVERAGE}x")
        print(f"  ポジション価値: {position_value}ドル")
        print(f"  計算された数量: {calculated_quantity}")
        order_quantity = calculated_quantity
    else:
        order_quantity = QUANTITY
        position_value = order_quantity * current_price
        required_margin = position_value / LEVERAGE
        print(f"\n【固定数量モード】")
        print(f"  数量: {order_quantity}")
        print(f"  ポジション価値: {position_value:.2f}ドル")
        print(f"  必要証拠金: {required_margin:.2f}ドル")
    
    # レバレッジ設定
    print("\n" + "=" * 60)
    print("レバレッジ設定")
    print("=" * 60)
    leverage_result = set_leverage(SYMBOL, LEVERAGE_SIDE, LEVERAGE)
    print(f"  結果: {leverage_result}")
    
    # 証拠金モード設定
    print("\n" + "=" * 60)
    print("証拠金モード設定")
    print("=" * 60)
    margin_result = set_margin_type(SYMBOL, MARGIN_TYPE)
    print(f"  結果: {margin_result}")
    
    # トリガー価格を計算
    trigger_prices = calculate_trigger_prices(current_price)
    
    # 損切り価格を計算（Noneの場合もある）
    stop_loss_prices = calculate_stop_loss_prices(current_price, order_quantity)
    
    print("\n" + "=" * 60)
    print("計算された注文価格")
    print("=" * 60)
    print(f"  ロング トリガー: {trigger_prices['trigger_long']}")
    print(f"  ショート トリガー: {trigger_prices['trigger_short']}")
    
    if stop_loss_prices:
        print(f"  ロング 損切り: {stop_loss_prices['sl_long']}")
        print(f"  ショート 損切り: {stop_loss_prices['sl_short']}")
    else:
        print(f"  損切り: 設定なし")
    
    print("\n" + "=" * 60)
    print("トリガー注文設定")
    print("=" * 60)
    
    # ロングトリガー注文
    print(f"\n【ロング注文】")
    long_order = place_order(SYMBOL, "BUY", "LONG", "TRIGGER_MARKET", order_quantity, trigger_prices['trigger_long'])
    if long_order.get('code') == 0:
        print(f"  ✅ 成功 ID: {long_order['data']['order']['orderId']}")
    else:
        print(f"  ❌ 失敗: {long_order}")
    
    # ショートトリガー注文
    print(f"\n【ショート注文】")
    short_order = place_order(SYMBOL, "SELL", "SHORT", "TRIGGER_MARKET", order_quantity, trigger_prices['trigger_short'])
    if short_order.get('code') == 0:
        print(f"  ✅ 成功 ID: {short_order['data']['order']['orderId']}")
    else:
        print(f"  ❌ 失敗: {short_order}")
    
    # 損切り設定（STOP_LOSS_MODE == "NONE"の場合はスキップ）
    if stop_loss_prices:
        print("\n" + "=" * 60)
        print("損切り注文設定")
        print("=" * 60)
        
        # ロングの損切り
        print(f"\n【ロング損切り】")
        long_sl = place_order(SYMBOL, "SELL", "LONG", "STOP_MARKET", order_quantity, stop_loss_prices['sl_long'])
        if long_sl.get('code') == 0:
            print(f"  ✅ 成功 ID: {long_sl['data']['order']['orderId']}")
        else:
            print(f"  ❌ 失敗: {long_sl}")
        
        # ショートの損切り
        print(f"\n【ショート損切り】")
        short_sl = place_order(SYMBOL, "BUY", "SHORT", "STOP_MARKET", order_quantity, stop_loss_prices['sl_short'])
        if short_sl.get('code') == 0:
            print(f"  ✅ 成功 ID: {short_sl['data']['order']['orderId']}")
        else:
            print(f"  ❌ 失敗: {short_sl}")
    else:
        print("\n" + "=" * 60)
        print("損切り注文: スキップ（設定なし）")
        print("=" * 60)
    
    print("\n" + "=" * 60)
    print("全ての注文処理が完了しました")
    print("=" * 60)

def schedule_execution():
    """スケジュール実行"""
    schedule.every().day.at(SCHEDULE_TIME).do(execute_trading_strategy)
    
    print(f"\nスケジューラ起動中: 毎日 {SCHEDULE_TIME} に実行")
    print(f"次回実行予定: {schedule.next_run()}")
    print("停止する場合は Ctrl+C を押してください\n")
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# ============================================
# メイン実行部分
# ============================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("BingX XAUT 自動トリガー注文＋損切りシステム")
    print("=" * 60)
    print(f"\n【設定内容】")
    print(f"  通貨ペア: {SYMBOL}")
    
    if USE_MARGIN_MODE:
        print(f"  証拠金ベースモード: ON")
        print(f"  証拠金額: {MARGIN_AMOUNT}ドル")
        print(f"  ポジション価値: {MARGIN_AMOUNT * LEVERAGE}ドル")
    else:
        print(f"  固定数量モード: ON")
        print(f"  注文数量: {QUANTITY}")
    
    print(f"  レバレッジ: {LEVERAGE}x ({LEVERAGE_SIDE})")
    print(f"  証拠金モード: {MARGIN_TYPE}")
    
    print(f"\n  【トリガー設定】")
    print(f"  ロング: 現在価格 + {TRIGGER_OFFSET_LONG}ドル")
    print(f"  ショート: 現在価格 + {TRIGGER_OFFSET_SHORT}ドル")
    
    print(f"\n  【損切り設定モード: {STOP_LOSS_MODE}】")
    if STOP_LOSS_MODE == "NONE":
        print(f"  損切り設定なし")
    elif STOP_LOSS_MODE == "FIXED_OFFSET":
        print(f"  ロング: {STOP_LOSS_OFFSET_LONG:+.1f}ドル")
        print(f"  ショート: {STOP_LOSS_OFFSET_SHORT:+.1f}ドル")
    elif STOP_LOSS_MODE == "PERCENTAGE":
        print(f"  ロング: {STOP_LOSS_PERCENTAGE_LONG:+.2f}%")
        print(f"  ショート: {STOP_LOSS_PERCENTAGE_SHORT:+.2f}%")
    elif STOP_LOSS_MODE == "LOSS_AMOUNT":
        print(f"  ロング最大損失: ${MAX_LOSS_AMOUNT_LONG}")
        print(f"  ショート最大損失: ${MAX_LOSS_AMOUNT_SHORT}")
    
    print(f"\n  価格タイプ: {PRICE_TYPE}")
    print(f"  実行時刻: {SCHEDULE_TIME if USE_SCHEDULE else '即時実行'}")
    print()
    
    if USE_SCHEDULE:
        schedule_execution()
    else:
        execute_trading_strategy()
