# validate_freeze_events.py
# 検知された停止イベントを精査（エラー修正版）

import csv
import statistics

def analyze_event_quality(csv_file):
    """停止イベントの質を分析"""
    
    print("=" * 80)
    print("🔍 停止イベントの質的分析")
    print("=" * 80)
    
    events = []
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            events.append({
                'duration': float(row['継続時間(分)']),
                'change': abs(float(row['価格変動'])),
                'change_pct': abs(float(row['変動率(%)'])),
                'date': row['日付'],
                'time': row['開始時刻'],
                'direction': row['方向']
            })
    
    # 統計分析
    durations = [e['duration'] for e in events]
    changes = [e['change'] for e in events]
    change_pcts = [e['change_pct'] for e in events]
    
    print(f"\n📊 基本統計:")
    print(f"   総イベント数: {len(events)}件")
    print(f"   停止時間: 最小{min(durations):.1f}分 / 平均{statistics.mean(durations):.1f}分 / 中央値{statistics.median(durations):.1f}分 / 最大{max(durations):.1f}分")
    print(f"   価格変動: 最小{min(changes):.2f} / 平均{statistics.mean(changes):.2f} / 中央値{statistics.median(changes):.2f} / 最大{max(changes):.2f}")
    print(f"   変動率: 最小{min(change_pcts):.3f}% / 平均{statistics.mean(change_pcts):.3f}% / 中央値{statistics.median(change_pcts):.3f}% / 最大{max(change_pcts):.3f}%")
    
    # 疑わしいイベントの抽出
    print("\n" + "=" * 80)
    print("⚠️  疑わしいイベント（誤検知の可能性が高い）")
    print("=" * 80)
    
    # 条件1: 停止時間が短い（5分未満）かつ価格変動が小さい（10未満）
    suspicious_short = [e for e in events if e['duration'] < 5 and e['change'] < 10]
    pct_short = len(suspicious_short) / len(events) * 100
    print(f"\n【停止時間が短く変動も小さい】: {len(suspicious_short)}件 ({pct_short:.1f}%)")
    if suspicious_short:
        print("  （最初の10件を表示）")
        for e in suspicious_short[:10]:
            print(f"    {e['date']} {e['time']} | {e['duration']:.1f}分 | 変動{e['change']:.2f}")
    
    # 条件2: 価格変動がほぼゼロ（<2.0）
    suspicious_no_change = [e for e in events if e['change'] < 2.0]
    pct_no_change = len(suspicious_no_change) / len(events) * 100
    print(f"\n【価格変動がほぼゼロ（<2.0）】: {len(suspicious_no_change)}件 ({pct_no_change:.1f}%)")
    if suspicious_no_change:
        print("  （最初の10件を表示）")
        for e in suspicious_no_change[:10]:
            print(f"    {e['date']} {e['time']} | {e['duration']:.1f}分 | 変動{e['change']:.2f}")
    
    # 条件3: 異常に長い停止（30分以上）
    suspicious_long = [e for e in events if e['duration'] >= 30]
    pct_long = len(suspicious_long) / len(events) * 100
    print(f"\n【異常に長い停止（30分以上）】: {len(suspicious_long)}件 ({pct_long:.1f}%)")
    if suspicious_long:
        for e in suspicious_long:
            print(f"    {e['date']} {e['time']} | {e['duration']:.1f}分 | 変動{e['change']:.2f}")
    
    # 信頼性の高いイベント
    print("\n" + "=" * 80)
    print("✅ 信頼性の高いイベント（明確な停止パターン）")
    print("=" * 80)
    
    # 条件: 5分以上停止 AND 10以上の価格変動
    reliable_events = [e for e in events if e['duration'] >= 5 and e['change'] >= 10]
    pct_reliable = len(reliable_events) / len(events) * 100
    print(f"\n【5分以上 & 変動10以上】: {len(reliable_events)}件 ({pct_reliable:.1f}%)")
    if reliable_events:
        print("  （変動が大きい順に15件）")
        for e in sorted(reliable_events, key=lambda x: x['change'], reverse=True)[:15]:
            direction_icon = "⬆️" if e['direction'] == 'UP' else "⬇️"
            print(f"    {e['date']} {e['time']} | {e['duration']:.1f}分 | 変動{e['change']:6.2f} {direction_icon}")
    
    # 分布の可視化
    print("\n" + "=" * 80)
    print("📈 停止時間の分布")
    print("=" * 80)
    
    duration_bins = {
        '1-2分': 0,
        '3-4分': 0,
        '5-9分': 0,
        '10-19分': 0,
        '20-29分': 0,
        '30分以上': 0
    }
    
    for d in durations:
        if d < 3:
            duration_bins['1-2分'] += 1
        elif d < 5:
            duration_bins['3-4分'] += 1
        elif d < 10:
            duration_bins['5-9分'] += 1
        elif d < 20:
            duration_bins['10-19分'] += 1
        elif d < 30:
            duration_bins['20-29分'] += 1
        else:
            duration_bins['30分以上'] += 1
    
    for label, count in duration_bins.items():
        bar = "█" * min(count, 50)
        pct = count / len(events) * 100
        print(f"  {label:10s}: {bar} {count:3d}件 ({pct:5.1f}%)")
    
    print("\n" + "=" * 80)
    print("💰 価格変動の分布")
    print("=" * 80)
    
    change_bins = {
        '0-5': 0,
        '5-10': 0,
        '10-20': 0,
        '20-30': 0,
        '30-50': 0,
        '50以上': 0
    }
    
    for c in changes:
        if c < 5:
            change_bins['0-5'] += 1
        elif c < 10:
            change_bins['5-10'] += 1
        elif c < 20:
            change_bins['10-20'] += 1
        elif c < 30:
            change_bins['20-30'] += 1
        elif c < 50:
            change_bins['30-50'] += 1
        else:
            change_bins['50以上'] += 1
    
    for label, count in change_bins.items():
        bar = "█" * min(count, 50)
        pct = count / len(events) * 100
        print(f"  {label:10s}: {bar} {count:3d}件 ({pct:5.1f}%)")
    
    # 推奨フィルター
    print("\n" + "=" * 80)
    print("💡 様々な条件での絞り込み結果")
    print("=" * 80)
    
    print(f"\n現在の検知数: {len(events)}件")
    
    # 様々な条件での絞り込み結果を計算
    filter_results = []
    filter_results.append(("【現在】連続5回", len(events)))
    filter_results.append(("連続7回 & 変動5以上", len([e for e in events if e['duration'] >= 5 and e['change'] >= 5])))
    filter_results.append(("連続7回 & 変動10以上", len([e for e in events if e['duration'] >= 5 and e['change'] >= 10])))
    filter_results.append(("連続7回 & 変動15以上", len([e for e in events if e['duration'] >= 5 and e['change'] >= 15])))
    filter_results.append(("連続10回 & 変動10以上", len([e for e in events if e['duration'] >= 8 and e['change'] >= 10])))
    filter_results.append(("連続10回 & 変動15以上", len([e for e in events if e['duration'] >= 8 and e['change'] >= 15])))
    
    for i, (label, count) in enumerate(filter_results):
        if i == 0:
            print(f"\n  {label}: {count}件")
        else:
            pct = count / len(events) * 100
            reduction = 100 - pct
            print(f"  {label}: {count:3d}件 ({pct:5.1f}%) ← 元の{reduction:.1f}%を除外")
    
    # 推奨設定
    print("\n" + "=" * 80)
    print("🎯 推奨設定")
    print("=" * 80)
    
    # 品質の良いイベントの割合を計算
    high_quality = [e for e in events if e['duration'] >= 5 and e['change'] >= 15]
    medium_quality = [e for e in events if e['duration'] >= 5 and e['change'] >= 10]
    
    hq_pct = len(high_quality) / len(events) * 100
    mq_pct = len(medium_quality) / len(events) * 100
    
    print(f"\n  高品質（5分以上 & 変動15以上）: {len(high_quality)}件 ({hq_pct:.1f}%)")
    print(f"  中品質（5分以上 & 変動10以上）: {len(medium_quality)}件 ({mq_pct:.1f}%)")
    
    reduction_pct = 100 - mq_pct
    
    print(f"\n  ✅ 推奨: 連続7回（7分） & 価格変動10以上")
    print(f"     → 約{len(medium_quality)}件に絞り込み")
    print(f"     → 誤検知を約{reduction_pct:.1f}%削減")


if __name__ == "__main__":
    analyze_event_quality("freeze_events_report.csv")
