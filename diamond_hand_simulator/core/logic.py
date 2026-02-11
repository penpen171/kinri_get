"""
判定ロジック：日次集計データから判定結果を生成
"""

import pandas as pd
from core.liquidation.simple_af import SimpleAFModel

# === 設定（ここを変更すれば判定ロジックを調整可能） ===
DEFAULT_THRESHOLD_MIN = 2  # デフォルトの閾値（分）
DEFAULT_JUDGMENT_HOURS = None  # デフォルトの判定時間（None = 次の閉場まで）


def judge_day(row, liq_model, leverage, position_margin, additional_margin=0, 
              threshold_min=DEFAULT_THRESHOLD_MIN, judgment_hours=DEFAULT_JUDGMENT_HOURS,
              df_1min=None):
    """
    1日分のデータを判定
    
    Args:
        row: daily_aggregatesの1行（Series）
        liq_model: ロスカットモデル（SimpleAFModel等）
        leverage: レバレッジ倍率
        position_margin: ポジション証拠金（USD）
        additional_margin: 追加証拠金（USD）
        threshold_min: 開場から◯分までを閾値とする（デフォルト=1分）
        judgment_hours: 判定時間（時間、Noneは次の閉場まで）
        df_1min: 1分足データ（正確なロスカット時刻計算用）
    
    Returns:
        dict: 判定結果
    """
    # 該当する閾値と判定時間のデータのみ使用
    if row['threshold_min'] != threshold_min:
        return None
    
    # judgment_hours の比較（None と NaN を同等に扱う）
    row_judgment = row['judgment_hours']
    
    if judgment_hours is None and pd.isna(row_judgment):
        # 両方とも None/NaN の場合は一致
        pass
    elif judgment_hours is None or pd.isna(row_judgment):
        # 片方だけ None/NaN の場合は不一致
        return None
    elif row_judgment != judgment_hours:
        # 両方とも数値の場合は値を比較
        return None
    
    date = row['date']
    market_type = row['type']
    judgment_label = row['judgment_label']
    judgment_hours_actual = row['judgment_hours_actual']
    
    # 建値
    long_entry = row['long_entry']
    short_entry = row['short_entry']
    
    # Phase1（開場〜閾値）
    phase1_high = row['phase1_high']
    phase1_low = row['phase1_low']
    
    # Phase2（閾値以降〜判定終了時刻）
    phase2_high = row['phase2_high']
    phase2_low = row['phase2_low']
    phase2_breach_long_time = row['phase2_breach_long_time']
    
    # ロスカット価格を計算（追加証拠金込み）
    liq_price_long = liq_model.calc_liq_price_long(long_entry, leverage, position_margin, additional_margin)
    liq_price_short = liq_model.calc_liq_price_short(short_entry, leverage, position_margin, additional_margin)
    
    # ===== 第1ロジック：開場〜閾値での判定 =====
    long_safe_phase1 = phase1_low >= liq_price_long
    short_safe_phase1 = phase1_high <= liq_price_short
    
    if long_safe_phase1 and not short_safe_phase1:
        phase1_result = '🟢'
        position_type = 'LONG'
    elif short_safe_phase1 and not long_safe_phase1:
        phase1_result = '🔴'
        position_type = 'SHORT'
    elif long_safe_phase1 and short_safe_phase1:
        phase1_result = '🟢'
        position_type = 'LONG'
    else:
        phase1_result = '🔵'
        position_type = 'NONE'
        return {
            'date': date,
            'type': market_type,
            'symbol': '🔵',
            'detail': f'開場{threshold_min}分以内にロング/ショート共にロスカット',
            'info': None,
            'judgment_label': judgment_label,
            'judgment_hours_actual': judgment_hours_actual
        }
    
    # ===== 第2ロジック：閾値以降〜判定終了時刻での判定 =====
    if position_type == 'LONG':
        # Phase2でロスカット判定
        is_liquidated = phase2_low <= liq_price_long
        
        # Phase2で建値割れ判定
        breached_entry = phase2_low < long_entry
        
        if is_liquidated:
            # ❌ ロスカット
            # 1分足データから正確なロスカット時刻を取得
            liq_time_str = "不明"
            liq_time = pd.NaT
            if df_1min is not None:
                threshold_time = row['threshold_time']
                judgment_end_time = row['judgment_end_time']
                df_phase2 = df_1min[
                    (df_1min.index >= threshold_time) & 
                    (df_1min.index < judgment_end_time)
                ]
                # ロスカット価格を下回った最初の時刻
                liq_candles = df_phase2[df_phase2['low'] <= liq_price_long]
                if len(liq_candles) > 0:
                    liq_time = liq_candles.index[0]
                    liq_time_str = liq_time.strftime("%H:%M")
            
            symbol = '❌'
            detail = f'ロスカット（{liq_time_str}）'
            info = {
                'liq_time': liq_time,
                'liq_price': liq_price_long,
                'entry': long_entry
            }
        elif breached_entry:
            # 建値を割った → さらに詳細判定
            distance_from_entry = long_entry - phase2_low
            distance_pct = distance_from_entry / long_entry * 100
            
            # 仮の基準：建値から0.5%以内なら回復と見なす
            if distance_pct < 0.5:
                symbol = '✅'
                detail = f'建値割れ後回復（最大-${distance_from_entry:.2f}、{phase2_breach_long_time.strftime("%H:%M") if pd.notna(phase2_breach_long_time) else "不明"}）'
            else:
                symbol = '🟠'
                detail = f'マイナス継続（最大-${distance_from_entry:.2f}、{phase2_breach_long_time.strftime("%H:%M") if pd.notna(phase2_breach_long_time) else "不明"}）'
            
            info = {
                'closest_distance': distance_from_entry,
                'entry': long_entry,
                'phase2_low': phase2_low,
                'breach_time': phase2_breach_long_time
            }
        else:
            # 💎 完全勝利
            symbol = '💎'
            closest_distance = long_entry - phase2_low
            detail = f'完全勝利（最小+${closest_distance:.2f}）'
            info = {
                'closest_distance': closest_distance,
                'entry': long_entry,
                'phase2_low': phase2_low
            }
        
        return {
            'date': date,
            'type': market_type,
            'symbol': f'{phase1_result} → {symbol}',
            'detail': detail,
            'info': info,
            'judgment_label': judgment_label,
            'judgment_hours_actual': judgment_hours_actual
        }
    
    elif position_type == 'SHORT':
        breached_entry = phase2_high > short_entry
        
        if breached_entry:
            symbol = '⤴️'
            detail = f'建値上抜け'
        else:
            symbol = '⏬'
            detail = f'終日マイナス（最低値: ${phase2_low:.2f}）'
        
        return {
            'date': date,
            'type': market_type,
            'symbol': f'{phase1_result} → {symbol}',
            'detail': detail,
            'info': {'phase2_low': phase2_low, 'entry': short_entry},
            'judgment_label': judgment_label,
            'judgment_hours_actual': judgment_hours_actual
        }


def judge_all(df_aggregates, liq_model, leverage, position_margin, additional_margin=0,
              threshold_min=DEFAULT_THRESHOLD_MIN, judgment_hours=DEFAULT_JUDGMENT_HOURS,
              df_1min=None, progress_callback=None):
    """
    全日のデータを判定
    progress_callback: 進捗を報告するコールバック関数（オプション）
    """
    results = []
    total = len(df_aggregates)
    
    for i, (idx, row) in enumerate(df_aggregates.iterrows()):
        result = judge_day(row, liq_model, leverage, position_margin, additional_margin,
                          threshold_min, judgment_hours, df_1min)
        if result is not None:
            results.append(result)
        
        # ⬇️ これを追加
        # 進捗報告（10%ごと）
        if progress_callback and (i % max(1, total // 10) == 0):
            progress_callback(i, total)
    
    # ⬇️ これを追加
    return results


def calculate_statistics(results):
    """判定結果から統計情報を計算"""
    total = len(results)
    
    symbol_counts = {}
    for r in results:
        symbol = r['symbol']
        symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
    
    win_count = sum(1 for r in results if '💎' in r['symbol'])
    recovery_count = sum(1 for r in results if '✅' in r['symbol'])
    warning_count = sum(1 for r in results if '🟠' in r['symbol'])
    loss_count = sum(1 for r in results if '❌' in r['symbol'] or r['symbol'] == '🔵')
    
    win_rate = (win_count / total * 100) if total > 0 else 0
    
    return {
        'total': total,
        'win_count': win_count,
        'recovery_count': recovery_count,
        'warning_count': warning_count,
        'loss_count': loss_count,
        'win_rate': win_rate,
        'symbol_counts': symbol_counts
    }
