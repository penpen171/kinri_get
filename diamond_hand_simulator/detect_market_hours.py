# detect_market_hours.py
# ゴールドの閉場・開場時刻を自動検出して一覧化（エラーハンドリング強化版）

import pandas as pd
from datetime import datetime, timedelta
import os

# 設定
INPUT_FILE = "gold_1min_20260211_20260222.csv"  # 入力CSVファイル
START_DATE = None  # 開始日（例: "2026-02-01"）Noneの場合は全期間
END_DATE = None    # 終了日（例: "2026-02-07"）Noneの場合は全期間
OUTPUT_FILE = None  # Noneの場合は自動生成
GAP_THRESHOLD_MINUTES = 15  # これ以上の空白を「休場」とみなす（分）

def detect_market_hours(input_file, start_date=None, end_date=None, 
                        output_file=None, gap_threshold=15):
    """
    1分足データから閉場・開場時刻を自動検出（期間指定対応）
    """
    
    print("=" * 80)
    print("📅 ゴールド市場の閉場・開場時刻を検出（期間指定対応版）")
    print("=" * 80)
    
    # ファイルの存在確認
    if not os.path.exists(input_file):
        print(f"\n❌ エラー: ファイルが見つかりません")
        print(f"   指定されたファイル: {input_file}")
        print(f"\n現在のディレクトリ: {os.getcwd()}")
        print(f"\n利用可能なCSVファイル:")
        
        # 同じディレクトリ内のCSVファイルを探す
        csv_files = [f for f in os.listdir('.') if f.endswith('.csv')]
        if csv_files:
            for i, file in enumerate(csv_files, 1):
                file_size = os.path.getsize(file) / 1024  # KB
                print(f"  {i}. {file} ({file_size:.1f} KB)")
            print(f"\n💡 ヒント: スクリプトの INPUT_FILE を上記のファイル名に変更してください")
        else:
            print("  （CSVファイルが見つかりません）")
            print(f"\n💡 ヒント: 先に download_gold_all_data_safe.py を実行してデータを取得してください")
        
        return None
    
    # データ読み込み
    print(f"\n📂 読み込み中: {input_file}")
    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        print(f"❌ ファイル読み込みエラー: {e}")
        return None
    
    # 日時列の作成・変換
    try:
        if '日時' in df.columns:
            df['DateTime'] = pd.to_datetime(df['日時'])
        else:
            df['DateTime'] = pd.to_datetime(df['日付'] + ' ' + df['時刻'])
    except Exception as e:
        print(f"❌ 日時変換エラー: {e}")
        print(f"利用可能なカラム: {list(df.columns)}")
        return None
    
    df = df.sort_values('DateTime').reset_index(drop=True)
    
    print(f"✅ 読み込み完了: {len(df):,}行")
    print(f"   全期間: {df['DateTime'].min()} ～ {df['DateTime'].max()}")
    
    # 期間フィルタリング
    if start_date or end_date:
        original_len = len(df)
        
        if start_date:
            start_dt = pd.to_datetime(start_date)
            df = df[df['DateTime'] >= start_dt]
            print(f"\n📅 開始日でフィルタ: {start_date}")
        
        if end_date:
            end_dt = pd.to_datetime(end_date) + timedelta(days=1) - timedelta(seconds=1)
            df = df[df['DateTime'] <= end_dt]
            print(f"📅 終了日でフィルタ: {end_date}")
        
        df = df.reset_index(drop=True)
        print(f"✅ フィルタ後: {len(df):,}行（{original_len - len(df):,}行除外）")
        
        if len(df) > 0:
            print(f"   対象期間: {df['DateTime'].min()} ～ {df['DateTime'].max()}")
        else:
            print("⚠️  指定期間にデータがありません")
            return None
    
    # ギャップ検出
    print(f"\n🔍 休場期間を検出中（閾値: {gap_threshold}分以上）...")
    df['TimeDiff'] = df['DateTime'].diff()
    
    # 閾値以上の空白を検出
    gaps = df[df['TimeDiff'] > timedelta(minutes=gap_threshold)].copy()
    
    print(f"✅ {len(gaps)}件の休場期間を検出")
    
    if len(gaps) == 0:
        print("⚠️  検出された休場期間はありません")
        print(f"💡 ヒント: gap_threshold（現在{gap_threshold}分）を小さくすると、より短い休場も検出できます")
        return pd.DataFrame()
    
    # 閉場・開場情報の整理
    market_hours = []
    
    for idx in gaps.index:
        # 閉場情報（ギャップの直前）
        close_row = df.loc[idx - 1]
        close_time = close_row['DateTime']
        close_price = close_row['終値']
        
        # 開場情報（ギャップの直後）
        open_row = df.loc[idx]
        open_time = open_row['DateTime']
        open_price = open_row['始値']
        
        # 休場時間
        duration = open_time - close_time
        duration_hours = duration.total_seconds() / 3600
        
        # タイプ判定
        if duration_hours < 2:
            gap_type = "メンテナンス"
        elif duration_hours < 24:
            gap_type = "日次休場"
        elif duration_hours < 72:
            gap_type = "週末"
        else:
            gap_type = "長期休場"
        
        # 価格変動
        price_change = open_price - close_price
        price_change_pct = (price_change / close_price) * 100 if close_price > 0 else 0
        
        market_hours.append({
            '閉場日時': close_time.strftime('%Y-%m-%d %H:%M:%S'),
            '閉場価格': f"{close_price:.2f}",
            '開場日時': open_time.strftime('%Y-%m-%d %H:%M:%S'),
            '開場価格': f"{open_price:.2f}",
            '休場時間(h)': f"{duration_hours:.2f}",
            'タイプ': gap_type,
            '価格変動': f"{price_change:+.2f}",
            '変動率(%)': f"{price_change_pct:+.3f}"
        })
    
    # DataFrame化
    result_df = pd.DataFrame(market_hours)
    
    # 出力ファイル名の自動生成
    if output_file is None:
        # 期間情報をファイル名に含める
        if start_date and end_date:
            period_str = f"{start_date.replace('-', '')}_{end_date.replace('-', '')}"
        elif start_date:
            period_str = f"{start_date.replace('-', '')}_latest"
        elif end_date:
            period_str = f"oldest_{end_date.replace('-', '')}"
        else:
            # 元のファイル名から期間を抽出
            base_name = input_file.replace('gold_1min_', '').replace('.csv', '')
            period_str = base_name
        
        output_file = f"market_hours_{period_str}.csv"
    
    # CSV出力
    print(f"\n💾 保存中: {output_file}")
    try:
        result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"✅ 保存完了: {os.path.abspath(output_file)}")
    except Exception as e:
        print(f"❌ 保存エラー: {e}")
    
    # サマリー表示
    print("\n" + "=" * 80)
    print("📊 検出結果サマリー")
    print("=" * 80)
    print(f"\n休場回数: {len(result_df)}回")
    
    if len(result_df) > 0:
        print("\nタイプ別内訳:")
        print(result_df['タイプ'].value_counts().to_string())
        
        # 統計情報
        print("\n価格変動統計:")
        price_changes = result_df['価格変動'].str.replace('+', '').astype(float)
        print(f"  平均: {price_changes.mean():+.2f}")
        print(f"  最大: {price_changes.max():+.2f}")
        print(f"  最小: {price_changes.min():+.2f}")
    
    # プレビュー
    print("\n" + "=" * 80)
    print("📋 データプレビュー（最初の5件）")
    print("=" * 80)
    if len(result_df) > 0:
        print(result_df.head().to_string(index=False))
        
        if len(result_df) > 5:
            print("\n... （以下略）")
    
    print("\n" + "=" * 80)
    print("✅ 完了")
    print("=" * 80)
    
    return result_df


if __name__ == "__main__":
    result = detect_market_hours(
        INPUT_FILE, 
        start_date=START_DATE,
        end_date=END_DATE,
        output_file=OUTPUT_FILE,
        gap_threshold=GAP_THRESHOLD_MINUTES
    )
