# modules/utils.py
"""
共通ユーティリティ関数
- リスク判定
- 時刻フォーマット
- その他の共通処理
"""


def fmt_rem(rem_s: int) -> str:
    """
    残り時間を「あとXX時間XX分XX秒」形式でフォーマット
    
    Args:
        rem_s: 残り秒数
    
    Returns:
        フォーマットされた文字列
    """
    try:
        rem_s = int(rem_s)
    except:
        return "不明"
    
    if rem_s <= 0:
        return "不明"
    
    m, s = divmod(rem_s, 60)
    h, m = divmod(m, 60)
    
    if h > 0:
        return f"あと{h}時間{m}分{s}秒"
    return f"あと{m}分{s}秒"


def calculate_risk(d1, d2, levs, t_key):
    """
    2つの取引所データからレバレッジごとのリスクを判定
    
    Args:
        d1: 取引所1のデータ（dict）
        d2: 取引所2のデータ（dict）
        levs: レバレッジのリスト（list of int）
        t_key: 戦術キー（"scalp", "hedge", "hold"）
    
    Returns:
        リスク判定結果のリスト（["✅", "⚠️", "❌", "MAX"]など）
    """
    # 戦術別リスク基準
    risk_configs = {
        "scalp": {"w": 0.5, "d": 0.9},  # スキャ：金利時刻ボラスパイクに直撃→厳しめ
        "hedge": {"w": 0.4, "d": 0.7},  # ヘッジ：中程度
        "hold": {"w": 0.3, "d": 0.6}    # ホールド：持続的変動に弱い、金利時刻ボラには強い→やや緩め
    }
    
    cfg = risk_configs[t_key]
    res = []
    
    for lev in levs:
        # レバレッジが最大レバレッジを超える場合
        if lev > d1['m'] or lev > d2['m']:
            res.append("MAX")
        else:
            # ボラティリティベースのリスク計算
            vol = ((d1['v'] + d2['v']) / 2) / (100 / lev)
            
            if vol > cfg['d']:
                res.append('❌')  # 危険
            elif vol > cfg['w']:
                res.append('⚠️')  # 警告
            else:
                res.append('✅')  # 安全
    
    return res


def calculate_risk_single(d, levs, t_key):
    """
    単一取引所データからレバレッジごとのリスクを判定（単体金利版用）
    
    Args:
        d: 取引所のデータ（dict）
        levs: レバレッジのリスト（list of int）
        t_key: 戦術キー（"scalp", "hedge", "hold"）
    
    Returns:
        リスク判定結果のリスト（["✅", "⚠️", "❌", "MAX"]など）
    """
    # 戦術別リスク閾値（単体取引の場合）
    risk_thresholds = {
        "scalp": 0.9,
        "hedge": 0.7,
        "hold": 0.6
    }
    
    risk_cfg = risk_thresholds[t_key]
    vol = d.get('v', 0)
    
    risks = []
    for lev in levs:
        if lev > d.get('m', 0):
            risks.append("MAX")
        else:
            vol_adjusted = vol / (100 / lev)
            
            if vol_adjusted > risk_cfg:
                risks.append('❌')
            elif vol_adjusted > risk_cfg * 0.5:
                risks.append('⚠️')
            else:
                risks.append('✅')
    
    return risks
