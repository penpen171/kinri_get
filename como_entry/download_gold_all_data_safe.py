# download_gold_all_data_safe.py
# 指定した期間の1分足を取得する
# API負荷を最小限にした安全版（期間指定改良版）

import requests
import time
import csv
from datetime import datetime, timedelta, timezone

BASE_URL = "https://open-api.bingx.com"
ENDPOINT_V2 = "/openApi/swap/v2/quote/klines"
JST = timezone(timedelta(hours=9))

# 設定
SYMBOL = "NCCOGOLD2USD-USDT"
START_DATE = "2026-02-10"  # 開始日（必須）
END_DATE = None  # 終了日（任意、Noneの場合は開始日から最大2ヶ月後まで）
OUTPUT_FILE = None  # Noneの場合は自動生成（例: gold_1min_20260201_20260401.csv）

#シンボルリスト
# NCCOGOLD2USD-USDT         GOLD
# NCCOSILVER2USD-USDT       SILVER
# NCSISP5002USD-USDT        S&P500
# NCSINASDAQ1002USD-USDT    NASDAQ
# NCSIDOWJONES2USD-USDT     DAW
# NCCOOILWTI2USD-USDT       WTI
# NCCOOILBRENT2USD-USDT     BRENT


# API制限対策の設定
REQUEST_INTERVAL = 0.3  # リクエスト間隔を0.3秒に（より安全）
MAX_RETRIES = 3         # リトライ回数
RETRY_DELAY = 5         # リトライ時の待機時間（秒）


def get_klines_v2_safe(symbol, start_time, end_time, retry_count=0):
    """v2 APIでKラインを取得（リトライ機能付き）"""
    url = BASE_URL + ENDPOINT_V2
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": int(start_time.timestamp() * 1000),
        "endTime": int(end_time.timestamp() * 1000),
        "limit": 1440
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        # レート制限チェック
        if data.get("code") == -1003:  # レート制限エラー
            if retry_count < MAX_RETRIES:
                print(f"    ⚠️  レート制限検知。{RETRY_DELAY}秒待機してリトライ...")
                time.sleep(RETRY_DELAY)
                return get_klines_v2_safe(symbol, start_time, end_time, retry_count + 1)
            else:
                print(f"    ❌ リトライ上限到達")
                return []
        
        if data.get("code") == 0 and data.get("data"):
            candles = []
            for kline in data["data"]:
                ts = int(kline["time"])
                dt_utc = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                dt_jst = dt_utc.astimezone(JST)
                
                candle = {
                    'timestamp': dt_jst,
                    'date': dt_jst.strftime('%Y-%m-%d'),
                    'time': dt_jst.strftime('%H:%M:%S'),
                    'datetime': dt_jst.strftime('%Y-%m-%d %H:%M:%S'),
                    'open': float(kline['open']),
                    'high': float(kline['high']),
                    'low': float(kline['low']),
                    'close': float(kline['close']),
                    'volume': float(kline.get('volume', 0))
                }
                candles.append(candle)
            
            return candles
        else:
            print(f"    APIエラー: {data.get('msg', 'Unknown error')}")
            return []
            
    except Exception as e:
        print(f"    接続エラー: {e}")
        if retry_count < MAX_RETRIES:
            print(f"    {RETRY_DELAY}秒後にリトライ...")
            time.sleep(RETRY_DELAY)
            return get_klines_v2_safe(symbol, start_time, end_time, retry_count + 1)
        return []


def download_all_data_safe(symbol, start_date_str, end_date_str=None, output_file=None):
    """全期間のデータをダウンロード（安全版・期間指定対応）"""
    
    print("=" * 80)
    print(f"📥 {symbol} 全データダウンロード（API負荷最小化版）")
    print("=" * 80)
    
    # 開始日の設定
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=JST, hour=0, minute=0)
    
    # 終了日の設定
    if end_date_str:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=JST, hour=23, minute=59)
    else:
        # 終了日未指定の場合、開始日から2ヶ月後または現在日時の早い方
        max_end = start_date + timedelta(days=60)  # 2ヶ月 = 約60日
        now = datetime.now(JST)
        end_date = min(max_end, now)
    
    # 出力ファイル名の自動生成
    if output_file is None:
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        output_file = f"gold_1min_{start_str}_{end_str}.csv"
    
    total_days = (end_date - start_date).days + 1
    estimated_time = total_days * REQUEST_INTERVAL
    
    print(f"\n期間:")
    print(f"  開始: {start_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"  終了: {end_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"  日数: {total_days}日")
    print(f"\nAPI設定:")
    print(f"  リクエスト間隔: {REQUEST_INTERVAL}秒")
    print(f"  推定完了時間: 約{estimated_time:.0f}秒 ({estimated_time/60:.1f}分)")
    print(f"\n保存先: {output_file}")
    print("\n" + "=" * 80)
    print("ダウンロード開始...")
    print("-" * 80)
    
    all_candles = []
    current_date = start_date
    request_count = 0
    start_time_total = time.time()
    
    while current_date <= end_date:
        day_start = current_date
        day_end = current_date + timedelta(days=1)
        
        if day_end > end_date:
            day_end = end_date
        
        # データ取得
        candles = get_klines_v2_safe(symbol, day_start, day_end)
        request_count += 1
        
        if candles:
            all_candles.extend(candles)
            elapsed = time.time() - start_time_total
            remaining_days = max(0, (end_date - current_date).days)
            eta = remaining_days * REQUEST_INTERVAL
            
            print(f"  {current_date.strftime('%Y-%m-%d')}: {len(candles):4d}本 | "
                  f"累計: {len(all_candles):6d}本 | "
                  f"リクエスト: {request_count:3d} | "
                  f"残り約{eta:.0f}秒")
        else:
            print(f"  {current_date.strftime('%Y-%m-%d')}: データなし")
        
        current_date += timedelta(days=1)
        
        # API負荷対策の待機
        time.sleep(REQUEST_INTERVAL)
    
    elapsed_total = time.time() - start_time_total
    
    print("-" * 80)
    print(f"✅ ダウンロード完了")
    print(f"   合計: {len(all_candles):,}本")
    print(f"   リクエスト数: {request_count}")
    print(f"   所要時間: {elapsed_total:.1f}秒 ({elapsed_total/60:.1f}分)")
    print(f"   平均速度: {len(all_candles)/elapsed_total:.1f}本/秒")
    
    # CSVに保存
    if all_candles:
        print(f"\n💾 CSVファイルに保存中...")
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            writer.writerow([
                '日時', '日付', '時刻', '始値', '高値', '安値', '終値', '出来高'
            ])
            
            for candle in all_candles:
                writer.writerow([
                    candle['datetime'],
                    candle['date'],
                    candle['time'],
                    f"{candle['open']:.2f}",
                    f"{candle['high']:.2f}",
                    f"{candle['low']:.2f}",
                    f"{candle['close']:.2f}",
                    f"{candle['volume']:.4f}"
                ])
        
        print(f"✅ 保存完了: {output_file}")
        
        # サマリー表示
        print("\n" + "=" * 80)
        print("📊 データサマリー")
        print("=" * 80)
        
        prices = [c['close'] for c in all_candles]
        
        print(f"\nレコード数: {len(all_candles):,}本")
        print(f"期間: {all_candles[0]['datetime']} ～ {all_candles[-1]['datetime']}")
        print(f"\n価格:")
        print(f"  最安値: {min(prices):.2f}")
        print(f"  最高値: {max(prices):.2f}")
        print(f"  価格差: {max(prices) - min(prices):.2f}")
        
        # プレビュー
        print("\n" + "=" * 80)
        print("📋 データプレビュー（最初の3行 / 最後の3行）")
        print("=" * 80)
        for candle in all_candles[:3]:
            print(f"  {candle['datetime']} | C:{candle['close']:7.2f}")
        print("  ...")
        for candle in all_candles[-3:]:
            print(f"  {candle['datetime']} | C:{candle['close']:7.2f}")
        
    else:
        print("\n❌ データが取得できませんでした")
    
    print("\n" + "=" * 80)
    print("✅ 完了")
    print("=" * 80)


if __name__ == "__main__":
    download_all_data_safe(SYMBOL, START_DATE, END_DATE, OUTPUT_FILE)
