import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from core.open_reference import select_open_reference_bar
from build_daily_aggregates import process_daily_data


def test_select_open_reference_bar_skips_low_range_bar():
    open_time = pd.Timestamp('2025-01-01 08:00:00')
    bars = pd.DataFrame(
        {
            'open': [100.00, 100.01, 100.03],
            'high': [100.005, 100.050, 100.060],
            'low': [100.000, 100.010, 100.040],
            'close': [100.002, 100.030, 100.050],
        },
        index=pd.to_datetime([
            '2025-01-01 08:01:00',
            '2025-01-01 08:02:00',
            '2025-01-01 08:03:00',
        ]),
    )

    bar, skip_minutes = select_open_reference_bar(
        bars_df=bars,
        open_time=open_time,
        offset_min=1,
        max_skip=3,
        price_tick=0.01,
    )

    assert bar.name == pd.Timestamp('2025-01-01 08:02:00')
    assert skip_minutes == 1


def test_select_open_reference_bar_returns_last_checked_when_all_skipped():
    open_time = pd.Timestamp('2025-01-01 08:00:00')
    bars = pd.DataFrame(
        {
            'open': [100.0, 100.0, 100.0],
            'high': [100.001, 100.001, 100.001],
            'low': [100.000, 100.000, 100.000],
            'close': [100.0, 100.0, 100.0],
        },
        index=pd.to_datetime([
            '2025-01-01 08:01:00',
            '2025-01-01 08:02:00',
            '2025-01-01 08:03:00',
        ]),
    )

    bar, skip_minutes = select_open_reference_bar(
        bars_df=bars,
        open_time=open_time,
        offset_min=1,
        max_skip=2,
        price_tick=0.01,
    )

    assert bar.name == pd.Timestamp('2025-01-01 08:03:00')
    assert skip_minutes == 2


def test_process_daily_data_records_skip_minutes():
    df_1min = pd.DataFrame(
        {
            'open': [100.0, 100.0, 100.0, 100.0, 99.5, 99.0],
            'high': [100.1, 100.001, 100.050, 100.2, 99.7, 99.2],
            'low': [99.9, 100.000, 100.010, 99.8, 99.3, 98.8],
            'close': [100.0, 100.0, 100.03, 100.0, 99.4, 99.0],
        },
        index=pd.to_datetime([
            '2025-01-01 07:59:00',
            '2025-01-01 08:01:00',
            '2025-01-01 08:02:00',
            '2025-01-01 08:03:00',
            '2025-01-01 08:04:00',
            '2025-01-01 08:05:00',
        ]),
    )

    df_market = pd.DataFrame(
        {
            '閉場時刻': [pd.Timestamp('2025-01-01 08:00:00')],
            '開場時刻': [pd.Timestamp('2025-01-01 08:00:00')],
            '次の閉場時刻': [pd.Timestamp('2025-01-01 08:06:00')],
            'タイプ': ['テスト'],
        }
    )

    out = process_daily_data(
        df_1min=df_1min,
        df_market=df_market,
        threshold_minutes=[1],
        judgment_hours=[1],
        open_bar_offset_minutes=1,
        open_bar_max_skip=3,
        price_tick=0.01,
    )

    assert len(out) == 1
    assert int(out.iloc[0]['skip_minutes']) == 1
    assert out.iloc[0]['reference_open_time'] == pd.Timestamp('2025-01-01 08:02:00')
