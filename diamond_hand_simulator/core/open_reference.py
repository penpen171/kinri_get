from datetime import timedelta

import pandas as pd


DEFAULT_OPEN_BAR_OFFSET_MINUTES = 1
DEFAULT_OPEN_BAR_MAX_SKIP = 3
DEFAULT_PRICE_TICK_FALLBACK = 0.01


def resolve_price_tick(price_tick, fallback=DEFAULT_PRICE_TICK_FALLBACK):
    """price_tick を正規化し、無効値のときは fallback を返す。"""
    if price_tick is None:
        return fallback
    try:
        value = float(price_tick)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def select_open_reference_bar(bars_df, open_time, offset_min=DEFAULT_OPEN_BAR_OFFSET_MINUTES,
                              max_skip=DEFAULT_OPEN_BAR_MAX_SKIP, price_tick=DEFAULT_PRICE_TICK_FALLBACK):
    """
    開場基準足を選択する。

    基本は open_time + offset_min の1分足を採用し、
    (high-low) < price_tick のときだけ次の1分足へスキップする（最大 max_skip 本）。

    Returns:
        tuple[pd.Series | None, int]: (採用した足, スキップ分数)
        対象足が1本も無ければ (None, 0)
    """
    if bars_df is None or len(bars_df) == 0:
        return None, 0

    reference_start = open_time + timedelta(minutes=int(offset_min))
    max_skip = max(int(max_skip), 0)
    tick = resolve_price_tick(price_tick)

    last_bar = None
    last_skip = 0

    for skip in range(max_skip + 1):
        bar_time = reference_start + timedelta(minutes=skip)
        df_target = bars_df[(bars_df.index >= bar_time) & (bars_df.index < bar_time + timedelta(minutes=1))]
        if len(df_target) == 0:
            continue

        bar = df_target.iloc[0]
        last_bar = bar
        last_skip = skip

        bar_range = float(bar['high']) - float(bar['low'])
        if bar_range >= tick:
            return bar, skip

    if last_bar is None:
        return None, 0
    return last_bar, last_skip
