# ==========================================
# improved_freeze_detector.py
# BingX価格停止検知システム v4.0
# ==========================================

import os
import requests
import time
import csv
import json
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import statistics

load_dotenv()

# --- 設定 ---
BASE_URL = "https://open-api.bingx.com"
ENDPOINT = "/openApi/swap/v3/quote/klines"
DETAIL_LOG = "freeze_detection_log.csv"
EVENT_LOG = "freeze_events.csv"
STATUS_JSON = "freeze_status.json"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# 監視銘柄（簡素化・自動適応）
WATCH_CONFIG = [
    {"name": "NASDAQ100", "symbol": "NCSINASDAQ1002USD-USDT", "pair_symbol": "^IXIC"},
    {"name": "S&P500", "symbol": "NCSISP5002USD-USDT", "pair_symbol": "^GSPC"},
    {"name": "GOLD", "symbol": "NCCOGOLD2USD-USDT", "pair_symbol": "GC=F"},
    {"name": "SILVER", "symbol": "NCCOSILVER2USD-USDT", "pair_symbol": "SI=F"},
]


class AdaptiveVolatilityAnalyzer:
    """適応的ボラティリティ分析器"""
    
    def __init__(self, window_size=100):
        self.window_size = window_size
        self.history = deque(maxlen=window_size)
        
    def add_candle(self, candle):
        """ローソク足を履歴に追加"""
        hl_range = candle['high'] - candle['low']
        self.history.append(hl_range)
    
    def get_baseline_volatility(self):
        """ベースラインのボラティリティを計算"""
        if len(self.history) < 20:
            return None
        return statistics.median(self.history)
    
    def get_recent_volatility(self, n=5):
        """直近n本のボラティリティ"""
        if len(self.history) < n:
            return None
        recent = list(self.history)[-n:]
        return statistics.mean(recent)
    
    def calculate_freeze_score(self):
        """停止スコアを0-100で計算（100が完全停止）"""
        baseline = self.get_baseline_volatility()
        recent = self.get_recent_volatility(5)
        
        if baseline is None or recent is None or baseline == 0:
            return 0
        
        # 直近のボラティリティがベースラインの何%か
        ratio = recent / baseline
        
        # 10%以下なら高スコア
        if ratio <= 0.1:
            return 100
        elif ratio <= 0.2:
            return 80
        elif ratio <= 0.3:
            return 60
        elif ratio <= 0.5:
            return 40
        else:
            return 0


class ExternalPriceChecker:
    """他取引所・データソースとの価格比較"""
    
    def __init__(self):
        self.cache = {}
        self.cache_time = {}
        self.cache_duration = 30  # 30秒キャッシュ
    
    def get_binance_price(self, symbol="BTCUSDT"):
        """Binanceから価格取得"""
        cache_key = f"binance_{symbol}"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                price = float(response.json()['price'])
                self._update_cache(cache_key, price)
                return price
        except:
            pass
        return None
    
    def get_yahoo_finance_price(self, symbol="^IXIC"):
        """Yahoo Financeから価格取得（yfinance使用）"""
        cache_key = f"yahoo_{symbol}"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="1m")
            if len(data) > 0:
                price = float(data['Close'].iloc[-1])
                self._update_cache(cache_key, price)
                return price
        except:
            pass
        return None
    
    def compare_prices(self, bingx_price, external_symbol):
        """価格を比較して乖離率を返す"""
        external_price = self.get_yahoo_finance_price(external_symbol)
        
        if external_price is None:
            return None
        
        divergence = (bingx_price - external_price) / external_price * 100
        return {
            'bingx_price': bingx_price,
            'external_price': external_price,
            'divergence_pct': divergence,
            'is_significant': abs(divergence) > 0.05  # 0.05%以上の乖離
        }
    
    def _is_cache_valid(self, key):
        if key not in self.cache:
            return False
        elapsed = time.time() - self.cache_time[key]
        return elapsed < self.cache_duration
    
    def _update_cache(self, key, value):
        self.cache[key] = value
        self.cache_time[key] = time.time()


class FreezeState:
    """停止状態を管理"""
    NORMAL = "NORMAL"
    SUSPECTED = "SUSPECTED"
    CONFIRMED = "CONFIRMED"
    RESOLVING = "RESOLVING"


class ImprovedFreezeDetector:
    """改善版停止検知器"""
    
    def __init__(self, config):
        self.config = config
        self.name = config['name']
        self.symbol = config['symbol']
        
        # 適応的分析器
        self.volatility_analyzer = AdaptiveVolatilityAnalyzer(window_size=100)
        self.external_checker = ExternalPriceChecker()
        
        # 状態管理
        self.state = FreezeState.NORMAL
        self.freeze_start_time = None
        self.freeze_start_price = None
        self.consecutive_high_scores = 0
        
        # データ保持
        self.candle_history = deque(maxlen=100)
        
    def fetch_candles(self, limit=20):
        """ローソク足データ取得（より多くのデータを取得）"""
        try:
            params = {
                "symbol": self.symbol,
                "interval": "1m",
                "limit": limit
            }
            response = requests.get(f"{BASE_URL}{ENDPOINT}", params=params, timeout=8)
            data = response.json()
            
            if data.get("code") == 0 and data.get("data"):
                candles = []
                for c in data['data']:
                    candle = {
                        'timestamp': datetime.fromtimestamp(int(c['time']) / 1000),
                        'open': float(c['open']),
                        'high': float(c['high']),
                        'low': float(c['low']),
                        'close': float(c['close']),
                        'volume': float(c.get('volume', 0))
                    }
                    candles.append(candle)
                return candles
        except Exception as e:
            print(f"  ⚠️ {self.name} データ取得エラー: {e}")
        return None
    
    def analyze(self):
        """メイン分析ロジック"""
        candles = self.fetch_candles(limit=20)
        if not candles:
            return None
        
        # 履歴更新
        for candle in candles[:-1]:  # 確定済みのローソク足のみ
            if candle not in self.candle_history:
                self.candle_history.append(candle)
                self.volatility_analyzer.add_candle(candle)
        
        current_candle = candles[-1]
        
        # === Stage 1: 停止スコア計算 ===
        freeze_score = self.volatility_analyzer.calculate_freeze_score()
        
        # === Stage 2: 他取引所との比較 ===
        comparison = None
        if 'pair_symbol' in self.config:
            comparison = self.external_checker.compare_prices(
                current_candle['close'],
                self.config['pair_symbol']
            )
        
        # === Stage 3: 状態判定 ===
        result = self._update_state(freeze_score, comparison, current_candle)
        
        return result
    
    def _update_state(self, freeze_score, comparison, candle):
        """状態を更新して結果を返す"""
        now = datetime.now()
        
        # 高スコアのカウント
        if freeze_score >= 60:
            self.consecutive_high_scores += 1
        else:
            self.consecutive_high_scores = 0
        
        # 外部乖離の有無
        has_divergence = comparison and comparison['is_significant']
        
        result = {
            'name': self.name,
            'state': self.state,
            'freeze_score': freeze_score,
            'price': candle['close'],
            'comparison': comparison,
            'duration_minutes': 0,
            'action': None,
            'confidence': 0
        }
        
        # --- 状態遷移ロジック ---
        if self.state == FreezeState.NORMAL:
            if self.consecutive_high_scores >= 3 and has_divergence:
                # 3分連続で高スコア + 外部乖離 = 停止疑い
                self.state = FreezeState.SUSPECTED
                result['state'] = self.state
                result['action'] = "ALERT_SUSPECTED"
                result['confidence'] = 50
                print(f"  ⚠️ {self.name}: 停止の疑いを検知")
                
        elif self.state == FreezeState.SUSPECTED:
            if self.consecutive_high_scores >= 5:
                # 5分連続 = 停止確定
                self.state = FreezeState.CONFIRMED
                self.freeze_start_time = now - timedelta(minutes=self.consecutive_high_scores)
                self.freeze_start_price = candle['close']
                result['state'] = self.state
                result['action'] = "FREEZE_CONFIRMED"
                result['confidence'] = 80
                print(f"  🚨 {self.name}: 停止を確定！")
                self._log_event("FREEZE_START", candle['close'])
                
            elif freeze_score < 40:
                # スコア低下 = 誤検知
                self.state = FreezeState.NORMAL
                self.consecutive_high_scores = 0
                
        elif self.state == FreezeState.CONFIRMED:
            duration = (now - self.freeze_start_time).total_seconds() / 60
            result['duration_minutes'] = duration
            
            if freeze_score < 40:
                # 停止解消の兆候
                self.state = FreezeState.RESOLVING
                result['state'] = self.state
                result['action'] = "PREPARE_ENTRY"
                result['confidence'] = 90
                price_diff = candle['close'] - self.freeze_start_price
                direction = "UP" if price_diff > 0 else "DOWN"
                print(f"  💥 {self.name}: 停止解消！{direction}方向へ（{duration:.1f}分停止）")
                self._log_event("FREEZE_RESOLVE", candle['close'], duration, direction)
                
        elif self.state == FreezeState.RESOLVING:
            # 解消後は一旦NORMALに戻る
            self.state = FreezeState.NORMAL
            self.freeze_start_time = None
            self.consecutive_high_scores = 0
        
        return result
    
    def _log_event(self, event_type, price, duration=None, direction=None):
        """イベントをログに記録"""
        with open(EVENT_LOG, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.name,
                event_type,
                f"{price:.4f}",
                f"{duration:.2f}" if duration else "",
                direction or ""
            ]
            writer.writerow(row)


def main():
    print("🚀 BingX停止検知システム v4.0 起動")
    print("=" * 60)
    
    # 検知器を初期化
    detectors = [ImprovedFreezeDetector(config) for config in WATCH_CONFIG]
    
    iteration = 0
    
    while True:
        iteration += 1
        now = datetime.now()
        
        print(f"\n[{now.strftime('%H:%M:%S')}] --- チェック #{iteration} ---")
        
        # 並列処理で全銘柄を分析
        with ThreadPoolExecutor(max_workers=len(detectors)) as executor:
            results = list(executor.map(lambda d: d.analyze(), detectors))
        
        # 結果を集計
        active_freezes = []
        suspected_freezes = []
        
        for result in results:
            if not result:
                continue
                
            if result['state'] == FreezeState.CONFIRMED:
                active_freezes.append(result)
            elif result['state'] == FreezeState.SUSPECTED:
                suspected_freezes.append(result)
            
            # 詳細ログ記録
            if result['action']:
                log_detail(result)
        
        # ステータス表示
        if active_freezes:
            print(f"\n🚨 停止確定: {len(active_freezes)}件")
            for r in active_freezes:
                print(f"  > {r['name']}: {r['duration_minutes']:.1f}分経過（信頼度{r['confidence']}%）")
        
        if suspected_freezes:
            print(f"\n⚠️  停止の疑い: {len(suspected_freezes)}件")
            for r in suspected_freezes:
                print(f"  > {r['name']}: スコア{r['freeze_score']}")
        
        if not active_freezes and not suspected_freezes:
            print("  🟢 全銘柄正常")
        
        # JSON出力（ダッシュボード用）
        status_data = {
            'timestamp': now.isoformat(),
            'active_freezes': active_freezes,
            'suspected_freezes': suspected_freezes
        }
        with open(STATUS_JSON, 'w') as f:
            json.dump(status_data, f, indent=2, default=str)
        
        # 15秒待機
        time.sleep(15)


def log_detail(result):
    """詳細ログをCSVに記録"""
    file_exists = os.path.isfile(DETAIL_LOG)
    with open(DETAIL_LOG, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["日時", "銘柄", "状態", "スコア", "価格", "外部乖離%", "アクション", "信頼度"])
        
        div = result['comparison']['divergence_pct'] if result['comparison'] else 0
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            result['name'],
            result['state'],
            result['freeze_score'],
            f"{result['price']:.4f}",
            f"{div:.3f}",
            result['action'] or "",
            result['confidence']
        ])


if __name__ == "__main__":
    # 必要なライブラリチェック
    try:
        import yfinance
    except ImportError:
        print("⚠️  yfinanceがインストールされていません")
        print("  実行: pip install yfinance")
        exit(1)
    
    main()
