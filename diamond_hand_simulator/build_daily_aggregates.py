"""
日次集計データを作成するスクリプト（複数時間窓対応版）
市場休場情報と1分足データから、各日の集計データを生成
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import timedelta


def calc_phase2_stats(df_phase2, long_entry):
    """
    Phase2の統計情報を計算
    
    Args:
        df_phase2: Phase2の1分足データ
        long_entry: ロングの建値
    
    Returns:
        dict: Phase2の統計情報
    """
    if len(df_phase2) == 0:
        return {
            'high': np.nan,
            'low': np.nan,
            'breach_long_time': pd.NaT,
            'breach_long_min': np.nan,
            'breach_short_time': pd.NaT,
            'breach_short_max': np.nan,
        }
    
    phase2_high = df_phase2['high'].max()
    phase2_low = df_phase2['low'].min()
    
    # ロングの建値割れ時刻
    breach_long = df_phase2[df_phase2['low'] < long_entry]
    if len(breach_long) > 0:
        breach_long_time = breach_long.index[0]
        breach_long_min = (breach_long_time - df_phase2.index[0]).total_seconds() / 60
    else:
        breach_long_time = pd.NaT
        breach_long_min = np.nan
    
    # ショートの建値上抜け時刻（ショート用・将来の拡張）
    breach_short_time = pd.NaT
    breach_short_max = np.nan
    
    return {
        'high': phase2_high,
        'low': phase2_low,
        'breach_long_time': breach_long_time,
        'breach_long_min': breach_long_min,
        'breach_short_time': breach_short_time,
        'breach_short_max': breach_short_max,
    }


def process_daily_data(df_1min, df_market, threshold_minutes=[1], 
                       judgment_hours=[1, 3, 6, 12, 22, None]):
    """
    日次集計データを作成
    """
    results = []
    
    for idx, row in df_market.iterrows():
        close_time = row['閉場時刻']
        open_time = row['開場時刻']
        next_close_time = row['次の閉場時刻']
        
        if pd.isna(open_time) or pd.isna(next_close_time):
            continue
        
        # 建値（閉場時の価格）
        # ロング：閉場時の高値で建てる（最も不利な価格）
        # ショート：閉場時の安値で建てる（最も不利な価格）
        df_close = df_1min[
            (df_1min.index >= close_time - timedelta(minutes=1)) & 
            (df_1min.index <= close_time)
        ]
        
        if len(df_close) == 0:
            # 閉場時のデータが取れない場合はスキップ
            continue
        
        long_entry = df_close['high'].max()   # 閉場時の高値
        short_entry = df_close['low'].min()   # 閉場時の安値
        
        # 開場〜次の閉場までのデータを取得
        df_session = df_1min[
            (df_1min.index >= open_time) & 
            (df_1min.index < next_close_time)
        ].copy()
        
        if len(df_session) == 0:
            continue
        
        # 実際の開場期間（時間）
        actual_session_hours = (next_close_time - open_time).total_seconds() / 3600
        
        # 各閾値で処理
        for threshold_min in threshold_minutes:
            threshold_time = open_time + timedelta(minutes=threshold_min)
            
            # Phase1: 開場〜閾値
            df_phase1 = df_session[df_session.index < threshold_time]
            
            if len(df_phase1) == 0:
                continue
            
            phase1_high = df_phase1['high'].max()
            phase1_low = df_phase1['low'].min()
            
            # 各判定時間で処理
            for judgment_hour in judgment_hours:
                # 判定終了時刻を決定
                if judgment_hour is None:
                    # 次の閉場まで
                    judgment_end_time = next_close_time
                    judgment_label = "次の閉場"
                    judgment_hours_actual = actual_session_hours
                else:
                    # 指定時間 または 実際の閉場時間の短い方
                    specified_end_time = open_time + timedelta(hours=judgment_hour)
                    judgment_end_time = min(specified_end_time, next_close_time)
                    judgment_label = f"{judgment_hour}h"
                    judgment_hours_actual = (judgment_end_time - open_time).total_seconds() / 3600
                
                # Phase2: 閾値〜判定終了時刻
                df_phase2 = df_session[
                    (df_session.index >= threshold_time) & 
                    (df_session.index < judgment_end_time)
                ]
                
                phase2 = calc_phase2_stats(df_phase2, long_entry)
                
                results.append({
                    'date': open_time.date(),
                    'close_time': close_time,
                    'open_time': open_time,
                    'next_close_time': next_close_time,
                    'type': row['タイプ'],
                    'threshold_min': threshold_min,
                    'threshold_time': threshold_time,
                    'judgment_hours': judgment_hour,
                    'judgment_label': judgment_label,
                    'judgment_hours_actual': judgment_hours_actual,
                    'judgment_end_time': judgment_end_time,
                    
                    # 建値
                    'long_entry': long_entry,
                    'short_entry': short_entry,
                    
                    # 開場〜閾値（第1ロジック用）
                    'phase1_high': phase1_high,
                    'phase1_low': phase1_low,
                    
                    # 閾値以降〜判定終了時刻（第2ロジック用）
                    'phase2_high': phase2['high'],
                    'phase2_low': phase2['low'],
                    'phase2_breach_long_time': phase2['breach_long_time'],
                    'phase2_breach_long_min': phase2['breach_long_min'],
                    'phase2_breach_short_time': phase2['breach_short_time'],
                    'phase2_breach_short_max': phase2['breach_short_max'],
                })
    
    return pd.DataFrame(results)


def main():
    # このスクリプトがあるフォルダ（diamond_hand_simulator）を基準
    SCRIPT_DIR = Path(__file__).resolve().parent
    
    print("=" * 60)
    print("日次集計データの作成（複数時間窓対応版）")
    print("=" * 60)
    
    # データ読み込み
    print("\n[1/4] データ読み込み中...")
    # 修正：絶対パスに
    market_csv_path = SCRIPT_DIR / "data" / "raw" / "market_hours_20251101_.csv"
    df_market = pd.read_csv(
        market_csv_path,
        parse_dates=['閉場日時', '開場日時']
    )
    
    # 次の閉場時刻を計算（次の行の閉場日時）
    df_market['次の閉場時刻'] = df_market['閉場日時'].shift(-1)
    
    # カラム名を統一
    df_market = df_market.rename(columns={
        '閉場日時': '閉場時刻',
        '開場日時': '開場時刻'
    })
    
    print(f"  市場休場データ: {len(df_market)}行")
    
    gold_csv_path = SCRIPT_DIR / "data" / "raw" / "gold_1min_20251101_.csv"
    df_1min = pd.read_csv(
        gold_csv_path,
        parse_dates=['日時']
    )
    
    # カラム名を統一
    df_1min = df_1min.rename(columns={
        '日時': 'timestamp',
        '始値': 'open',
        '高値': 'high',
        '安値': 'low',
        '終値': 'close'
    })
    
    df_1min.set_index('timestamp', inplace=True)
    print(f"  1分足データ: {len(df_1min)}行")
    
    # 集計処理
    print("\n[2/4] 日次集計中...")
    print("  閾値: 1分")
    print("  判定時間: 1h, 3h, 6h, 12h, 22h, 次の閉場")
    
    # 集計処理
    print("\n[2/4] 日次集計中...")
    print("  閾値: 1分")
    print("  判定時間: 1h〜24h（1時間刻み）+ 次の閉場")

    df_aggregates = process_daily_data(
        df_1min, 
        df_market,
        threshold_minutes=[1, 2, 3, 4, 5],
        judgment_hours=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 
                        13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, None]
    )

    
    print(f"  集計完了: {len(df_aggregates)}行")
    
    # 保存
    print("\n[3/4] データ保存中...")
    output_dir = SCRIPT_DIR / "data" / "derived"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / 'daily_aggregates.parquet'
    df_aggregates.to_parquet(output_path, index=False)
    print(f"   保存完了: {output_path}")
    
    # サマリー表示
    print("\n[4/4] サマリー")
    print("=" * 60)
    print(f"総データ数: {len(df_aggregates)}行")
    print(f"日数: {df_aggregates['date'].nunique()}日")
    print(f"判定時間別:")
    for label, count in df_aggregates['judgment_label'].value_counts().items():
        print(f"  {label}: {count}日")
    
    print("\n✅ 完了")


if __name__ == '__main__':
    main()
