# auto_trader.py - 統合版
import subprocess
import time
import sys

def run_both():
    """トリガー注文発注 + ポジション監視を同時実行"""
    print("=" * 60)
    print("自動トレードシステム起動")
    print("=" * 60)
    
    # 1. トリガー注文を発注
    print("\n[1/2] トリガー注文を発注中...")
    subprocess.run([sys.executable, "main.py"])
    
    print("\n注文完了。3秒後にポジション監視を開始します...")
    time.sleep(3)
    
    # 2. ポジション監視を開始
    print("\n[2/2] ポジション監視を開始...")
    subprocess.run([sys.executable, "position_monitor.py"])

if __name__ == "__main__":
    run_both()
