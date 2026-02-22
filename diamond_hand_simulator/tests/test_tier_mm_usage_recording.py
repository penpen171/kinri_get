import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest
import yaml

from core.liquidation.tier_mm import TierMMModel
from core.logic import judge_day


def test_tier_mm_model_records_current_tier_fields(tmp_path):
    cfg = {
        'price_tick': 0.0,
        'price_compare_epsilon': 1e-9,
        'safety_multiplier': 1.2,
        'tiers': [
            {'min_notional': 0, 'max_notional': 1000, 'mm_rate': 0.01},
            {'min_notional': 1000, 'max_notional': None, 'mm_rate': 0.02},
        ],
    }
    cfg_path = tmp_path / 'tiermm.yaml'
    cfg_path.write_text(yaml.safe_dump(cfg), encoding='utf-8')

    model = TierMMModel(config_path=str(cfg_path))
    _ = model.calc_liq_distance_pct(
        leverage=10,
        position_margin=100,
        entry_price=100,
        qty=20,
    )

    assert model.current_notional == 2000
    assert model.current_tier_index == 2  # 1始まり
    assert model.current_tier_min_notional == 1000
    assert model.current_tier_max_notional is None
    assert model.current_mm_rate == pytest.approx(0.024)  # 0.02 * 1.2


def test_judge_day_includes_used_tier_columns(tmp_path):
    cfg = {
        'price_tick': 0.0,
        'price_compare_epsilon': 1e-9,
        'safety_multiplier': 1.1,
        'tiers': [
            {'min_notional': 0, 'max_notional': 2000, 'mm_rate': 0.01},
            {'min_notional': 2000, 'max_notional': None, 'mm_rate': 0.02},
        ],
    }
    cfg_path = tmp_path / 'tiermm_judge.yaml'
    cfg_path.write_text(yaml.safe_dump(cfg), encoding='utf-8')

    model = TierMMModel(config_path=str(cfg_path))

    row = pd.Series(
        {
            'date': pd.Timestamp('2025-01-01').date(),
            'type': 'TEST',
            'judgment_label': 'close',
            'judgment_hours_actual': None,
            'long_entry': 100.0,
            'short_entry': 100.0,
            'phase1_high': 200.0,
            'phase1_low': 95.0,
            'phase2_high': 105.0,
            'phase2_low': 99.0,
            'phase2_breach_long_time': pd.NaT,
            'threshold_time': pd.Timestamp('2025-01-01 08:02:00'),
            'judgment_end_time': pd.Timestamp('2025-01-01 16:00:00'),
            'threshold_min': 2,
            'skip_minutes': 0,
        }
    )

    result = judge_day(
        row=row,
        liq_model=model,
        leverage=10,
        position_margin=100,
        additional_margin=0,
        df_1min=None,
    )

    assert result is not None
    assert 'used_notional' in result
    assert 'used_mm_rate' in result
    assert 'used_tier_index' in result
    assert 'used_tier_min_notional' in result
    assert 'used_tier_max_notional' in result

    assert result['used_notional'] == 1000
    assert result['used_tier_index'] == 1  # 1始まり
    assert result['used_tier_min_notional'] == 0
    assert result['used_tier_max_notional'] == 2000
    assert result['used_mm_rate'] == pytest.approx(0.011)  # 0.01 * 1.1
