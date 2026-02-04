import hashlib
import hmac
import time
import requests
import schedule
from datetime import datetime

# ============================================
# 設定項目
# ============================================

# API認証情報
API_KEY = "VrjIg16ORbQfSgFwjHt0yC2V6taekTSZ8eNPCS7Dpwhxfy7azBlQk68DC5OD9s6BGf3oOAywOKyq6F90kPQ"
SECRET_KEY = "t3lz7ALUX69aFQ1fXrdHorJmMlIYhlcXQcVSoG8RfgxFi6DNsBLqvBxCrA9oJLZeo9AoCNREqA6aFzU84g"

# 取引設定
SYMBOL = "XAUT-USDT"  # 通貨ペア

# 証拠金ベースの設定
USE_MARGIN_MODE = True  # True: 証拠金ベース, False: 固定数量
MARGIN_AMOUNT = 1.0  # 使用する証拠金額（ドル）
QUANTITY = 0.01  # USE_MARGIN_MODE=Falseの時の固定数量

# レバレッジ設定
LEVERAGE = 50  # レバレッジ倍率（1-125）
LEVERAGE_SIDE = "BOTH"  # BOTH（片建て）, LONG（両建てロング）, SHORT（両建てショート）

# 証拠金モード設定
MARGIN_TYPE = "ISOLATED"  # ISOLATED（分離）または CROSSED（クロス）

# トリガー注文設定（現在価格からの幅：ドル）
TRIGGER_OFFSET_LONG = 5.00  # ロングのトリガー幅（現在価格 + 50ドル）
TRIGGER_OFFSET_SHORT = -5.00  # ショートのトリガー幅（現在価格 - 50ドル）

# 損切り設定（現在価格からの幅：ドル）
STOP_LOSS_OFFSET_LONG = -1.00  # ロング損切り幅（現在価格 - 30ドル）
STOP_LOSS_OFFSET_SHORT = 1.00  # ショート損切り幅（現在価格 + 30ドル）

# 利確設定（現在価格からの幅：ドル、オプション）
TAKE_PROFIT_OFFSET_LONG = None  # ロング利確幅（使用しない場合はNone）
TAKE_PROFIT_OFFSET_SHORT = None  # ショート利確幅（使用しない場合はNone）

# 別の設定方法：比率で指定する場合
USE_RATIO_MODE = False  # True: 比率モード, False: 固定幅モード
TRIGGER_RATIO_LONG = 1/10000  # ロングトリガー比率（0.01%）
TRIGGER_RATIO_SHORT = -1/10000  # ショートトリガー比率（-0.01%）
STOP_LOSS_RATIO_LONG = -1/5000  # ロング損切り比率（-0.02%）
STOP_LOSS_RATIO_SHORT = 1/5000  # ショート損切り比率（0.02%）

# スケジュール設定
SCHEDULE_TIME = "07:52"  # 実行時刻（HH:MM形式）
USE_SCHEDULE = False  # True: スケジュール実行, False: 即時実行

# 価格タイプ
PRICE_TYPE = "LAST_PRICE"  # LAST_PRICE, MARK_PRICE, INDEX_PRICE

# 小数点以下の桁数
PRICE_DECIMALS = 1  # 価格精度: 1桁
QUANTITY_DECIMALS = 6  # 数量精度: 6桁
MIN_QUANTITY = 0.000001  # 最小注文数量単位

# ============================================
# API接続設定
# ============================================

BASE_URL = "https://open-api.bingx.com"

def generate_signature(params, secret_key):
    """APIシグネチャを生成"""
    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
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
    
    # 最小数量単位に合わせて調整
    quantity = round(quantity / MIN_QUANTITY) * MIN_QUANTITY
    quantity = round(quantity, QUANTITY_DECIMALS)
    
    return quantity

def set_leverage(symbol, side, leverage):
    """レバレッジを設定"""
    timestamp = int(time.time() * 1000)
    
    params = {
        "symbol": symbol,
        "side": side,  # BOTH, LONG, SHORT
        "leverage": leverage,
        "timestamp": timestamp
    }
    
    signature = generate_signature(params, SECRET_KEY)
    params["signature"] = signature
    
    headers = {
        "X-BX-APIKEY": API_KEY
    }
    
    url = f"{BASE_URL}/openApi/swap/v2/trade/leverage"
    
    try:
        response = requests.post(url, params=params, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def set_margin_type(symbol, margin_type):
    """証拠金モードを設定"""
    timestamp = int(time.time() * 1000)
    
    params = {
        "symbol": symbol,
        "marginType": margin_type,  # ISOLATED または CROSSED
        "timestamp": timestamp
    }
    
    signature = generate_signature(params, SECRET_KEY)
    params["signature"] = signature
    
    headers = {
        "X-BX-APIKEY": API_KEY
    }
    
    url = f"{BASE_URL}/openApi/swap/v2/trade/marginType"
    
    try:
        response = requests.post(url, params=params, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def calculate_prices(current_price):
    """現在価格から各注文価格を計算"""
    if USE_RATIO_MODE:
        # 比率モード
        trigger_long = current_price * (1 + TRIGGER_RATIO_LONG)
        trigger_short = current_price * (1 + TRIGGER_RATIO_SHORT)
        sl_long = current_price * (1 + STOP_LOSS_RATIO_LONG)
        sl_short = current_price * (1 + STOP_LOSS_RATIO_SHORT)
        
        tp_long = None
        tp_short = None
        if TAKE_PROFIT_OFFSET_LONG is not None:
            tp_long = current_price * (1 + TAKE_PROFIT_OFFSET_LONG)
        if TAKE_PROFIT_OFFSET_SHORT is not None:
            tp_short = current_price * (1 + TAKE_PROFIT_OFFSET_SHORT)
    else:
        # 固定幅モード
        trigger_long = current_price + TRIGGER_OFFSET_LONG
        trigger_short = current_price + TRIGGER_OFFSET_SHORT
        sl_long = current_price + STOP_LOSS_OFFSET_LONG
        sl_short = current_price + STOP_LOSS_OFFSET_SHORT
        
        tp_long = None
        tp_short = None
        if TAKE_PROFIT_OFFSET_LONG is not None:
            tp_long = current_price + TAKE_PROFIT_OFFSET_LONG
        if TAKE_PROFIT_OFFSET_SHORT is not None:
            tp_short = current_price + TAKE_PROFIT_OFFSET_SHORT
    
    # 小数点以下を丸める
    return {
        'trigger_long': round(trigger_long, PRICE_DECIMALS),
        'trigger_short': round(trigger_short, PRICE_DECIMALS),
        'sl_long': round(sl_long, PRICE_DECIMALS),
        'sl_short': round(sl_short, PRICE_DECIMALS),
        'tp_long': round(tp_long, PRICE_DECIMALS) if tp_long else None,
        'tp_short': round(tp_short, PRICE_DECIMALS) if tp_short else None
    }

def place_trigger_order(symbol, side, quantity, stop_price, price_type="LAST_PRICE"):
    """トリガー成行注文を発注"""
    timestamp = int(time.time() * 1000)
    
    params = {
        "symbol": symbol,
        "side": side,
        "type": "TRIGGER_MARKET",
        "quantity": quantity,
        "stopPrice": stop_price,
        "workingType": price_type,
        "timestamp": timestamp
    }
    
    signature = generate_signature(params, SECRET_KEY)
    params["signature"] = signature
    
    headers = {
        "X-BX-APIKEY": API_KEY
    }
    
    url = f"{BASE_URL}/openApi/swap/v2/trade/order"
    
    try:
        response = requests.post(url, params=params, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def place_stop_loss_order(symbol, side, quantity, stop_price, price_type="LAST_PRICE"):
    """損切り注文を発注（STOP_MARKET）"""
    timestamp = int(time.time() * 1000)
    
    # ロングポジションの損切りはSELL、ショートポジションの損切りはBUY
    stop_side = "SELL" if side == "BUY" else "BUY"
    
    params = {
        "symbol": symbol,
        "side": stop_side,
        "type": "STOP_MARKET",
        "quantity": quantity,
        "stopPrice": stop_price,
        "workingType": price_type,
        "timestamp": timestamp
    }
    
    signature = generate_signature(params, SECRET_KEY)
    params["signature"] = signature
    
    headers = {
        "X-BX-APIKEY": API_KEY
    }
    
    url = f"{BASE_URL}/openApi/swap/v2/trade/order"
    
    try:
        response = requests.post(url, params=params, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def place_take_profit_order(symbol, side, quantity, tp_price, price_type="LAST_PRICE"):
    """利確注文を発注（TAKE_PROFIT_MARKET）"""
    timestamp = int(time.time() * 1000)
    
    # ロングポジションの利確はSELL、ショートポジションの利確はBUY
    tp_side = "SELL" if side == "BUY" else "BUY"
    
    params = {
        "symbol": symbol,
        "side": tp_side,
        "type": "TAKE_PROFIT_MARKET",
        "quantity": quantity,
        "stopPrice": tp_price,
        "workingType": price_type,
        "timestamp": timestamp
    }
    
    signature = generate_signature(params, SECRET_KEY)
    params["signature"] = signature
    
    headers = {
        "X-BX-APIKEY": API_KEY
    }
    
    url = f"{BASE_URL}/openApi/swap/v2/trade/order"
    
    try:
        response = requests.post(url, params=params, headers=headers)
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
    print(f"  レバレッジ: {LEVERAGE}x")
    print(f"  方向: {LEVERAGE_SIDE}")
    
    leverage_result = set_leverage(SYMBOL, LEVERAGE_SIDE, LEVERAGE)
    print(f"  結果: {leverage_result}")
    
    # 証拠金モード設定
    print("\n" + "=" * 60)
    print("証拠金モード設定")
    print("=" * 60)
    print(f"  証拠金モード: {MARGIN_TYPE}")
    
    margin_result = set_margin_type(SYMBOL, MARGIN_TYPE)
    print(f"  結果: {margin_result}")
    
    # 各注文価格を計算
    prices = calculate_prices(current_price)
    
    print("\n" + "=" * 60)
    print("計算された注文価格")
    print("=" * 60)
    if USE_RATIO_MODE:
        print(f"  ロング トリガー: {prices['trigger_long']} (現在価格 × {1 + TRIGGER_RATIO_LONG:.6f})")
        print(f"  ショート トリガー: {prices['trigger_short']} (現在価格 × {1 + TRIGGER_RATIO_SHORT:.6f})")
        print(f"  ロング 損切り: {prices['sl_long']} (現在価格 × {1 + STOP_LOSS_RATIO_LONG:.6f})")
        print(f"  ショート 損切り: {prices['sl_short']} (現在価格 × {1 + STOP_LOSS_RATIO_SHORT:.6f})")
    else:
        print(f"  ロング トリガー: {prices['trigger_long']} (現在価格 + {TRIGGER_OFFSET_LONG})")
        print(f"  ショート トリガー: {prices['trigger_short']} (現在価格 + {TRIGGER_OFFSET_SHORT})")
        print(f"  ロング 損切り: {prices['sl_long']} (現在価格 + {STOP_LOSS_OFFSET_LONG})")
        print(f"  ショート 損切り: {prices['sl_short']} (現在価格 + {STOP_LOSS_OFFSET_SHORT})")
    
    if prices['tp_long']:
        print(f"  ロング 利確: {prices['tp_long']}")
    if prices['tp_short']:
        print(f"  ショート 利確: {prices['tp_short']}")
    
    print("\n" + "=" * 60)
    print("トリガー注文設定")
    print("=" * 60)
    
    # ロングトリガー注文
    print(f"\n【ロング注文】")
    print(f"  トリガー価格: {prices['trigger_long']}")
    print(f"  数量: {order_quantity}")
    long_order = place_trigger_order(
        symbol=SYMBOL,
        side="BUY",
        quantity=order_quantity,
        stop_price=prices['trigger_long'],
        price_type=PRICE_TYPE
    )
    print(f"  結果: {long_order}")
    
    # ショートトリガー注文
    print(f"\n【ショート注文】")
    print(f"  トリガー価格: {prices['trigger_short']}")
    print(f"  数量: {order_quantity}")
    short_order = place_trigger_order(
        symbol=SYMBOL,
        side="SELL",
        quantity=order_quantity,
        stop_price=prices['trigger_short'],
        price_type=PRICE_TYPE
    )
    print(f"  結果: {short_order}")
    
    # 損切り設定
    print("\n" + "=" * 60)
    print("損切り注文設定")
    print("=" * 60)
    
    # ロングの損切り
    print(f"\n【ロングポジション損切り】")
    print(f"  損切り価格: {prices['sl_long']}")
    print(f"  数量: {order_quantity}")
    long_sl = place_stop_loss_order(
        symbol=SYMBOL,
        side="BUY",
        quantity=order_quantity,
        stop_price=prices['sl_long'],
        price_type=PRICE_TYPE
    )
    print(f"  結果: {long_sl}")
    
    # ショートの損切り
    print(f"\n【ショートポジション損切り】")
    print(f"  損切り価格: {prices['sl_short']}")
    print(f"  数量: {order_quantity}")
    short_sl = place_stop_loss_order(
        symbol=SYMBOL,
        side="SELL",
        quantity=order_quantity,
        stop_price=prices['sl_short'],
        price_type=PRICE_TYPE
    )
    print(f"  結果: {short_sl}")
    
    # 利確設定（オプション）
    if prices['tp_long'] or prices['tp_short']:
        print("\n" + "=" * 60)
        print("利確注文設定")
        print("=" * 60)
        
        if prices['tp_long']:
            print(f"\n【ロングポジション利確】")
            print(f"  利確価格: {prices['tp_long']}")
            print(f"  数量: {order_quantity}")
            long_tp = place_take_profit_order(
                symbol=SYMBOL,
                side="BUY",
                quantity=order_quantity,
                tp_price=prices['tp_long'],
                price_type=PRICE_TYPE
            )
            print(f"  結果: {long_tp}")
        
        if prices['tp_short']:
            print(f"\n【ショートポジション利確】")
            print(f"  利確価格: {prices['tp_short']}")
            print(f"  数量: {order_quantity}")
            short_tp = place_take_profit_order(
                symbol=SYMBOL,
                side="SELL",
                quantity=order_quantity,
                tp_price=prices['tp_short'],
                price_type=PRICE_TYPE
            )
            print(f"  結果: {short_tp}")
    
    print("\n" + "=" * 60)
    print("全ての注文処理が完了しました")
    print("=" * 60)

def schedule_execution():
    """スケジュール実行"""
    schedule.every().day.at(SCHEDULE_TIME).do(execute_trading_strategy)
    
    print(f"スケジューラ起動中: 毎日 {SCHEDULE_TIME} に実行")
    print("停止する場合は Ctrl+C を押してください\n")
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# ============================================
# メイン実行部分
# ============================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("BingX XAU 自動トリガー注文＋損切りシステム")
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
    
    if USE_RATIO_MODE:
        print(f"\n  【比率モード】")
        print(f"  ロング トリガー: 現在価格 × {1 + TRIGGER_RATIO_LONG:.6f} ({TRIGGER_RATIO_LONG*100:.4f}%)")
        print(f"  ショート トリガー: 現在価格 × {1 + TRIGGER_RATIO_SHORT:.6f} ({TRIGGER_RATIO_SHORT*100:.4f}%)")
        print(f"  ロング 損切り: 現在価格 × {1 + STOP_LOSS_RATIO_LONG:.6f} ({STOP_LOSS_RATIO_LONG*100:.4f}%)")
        print(f"  ショート 損切り: 現在価格 × {1 + STOP_LOSS_RATIO_SHORT:.6f} ({STOP_LOSS_RATIO_SHORT*100:.4f}%)")
    else:
        print(f"\n  【固定幅モード】")
        print(f"  ロング トリガー: 現在価格 + {TRIGGER_OFFSET_LONG}ドル")
        print(f"  ショート トリガー: 現在価格 + {TRIGGER_OFFSET_SHORT}ドル")
        print(f"  ロング 損切り: 現在価格 + {STOP_LOSS_OFFSET_LONG}ドル")
        print(f"  ショート 損切り: 現在価格 + {STOP_LOSS_OFFSET_SHORT}ドル")
    
    if TAKE_PROFIT_OFFSET_LONG:
        print(f"  ロング 利確幅: {TAKE_PROFIT_OFFSET_LONG}ドル")
    if TAKE_PROFIT_OFFSET_SHORT:
        print(f"  ショート 利確幅: {TAKE_PROFIT_OFFSET_SHORT}ドル")
    
    print(f"\n  価格タイプ: {PRICE_TYPE}")
    print(f"  実行時刻: {SCHEDULE_TIME if USE_SCHEDULE else '即時実行'}")
    print()
    
    if USE_SCHEDULE:
        # スケジュール実行
        schedule_execution()
    else:
        # 即時実行
        execute_trading_strategy()
