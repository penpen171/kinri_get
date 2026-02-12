import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tempfile
import pandas as pd
import pytest
import yaml

from core.logic import judge_all
from core.liquidation.simple_af import SimpleAFModel


@pytest.fixture
def model_factory():
    temp_paths = []

    def _create(af):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
            yaml.safe_dump(
                {
                    'adjustment_factor': af,
                    'liquidation_fee_rate': 0.0005,
                    'price_compare_epsilon': 1e-9,
                    'price_tick': 0.0,
                },
                f,
            )
            temp_paths.append(Path(f.name))
        return SimpleAFModel(config_path=str(temp_paths[-1]))

    yield _create

    for p in temp_paths:
        p.unlink(missing_ok=True)


def test_af_micro_change_produces_micro_distance_and_price_delta(model_factory):
    model_010 = model_factory(0.1)
    model_00999 = model_factory(0.0999)

    entry_price = 5000.0
    leverage = 500
    position_margin = 100.0

    d_010 = model_010.calc_liq_distance_pct(leverage, position_margin)
    d_00999 = model_00999.calc_liq_distance_pct(leverage, position_margin)

    p_010 = model_010.calc_liq_price_long(entry_price, leverage, position_margin)
    p_00999 = model_00999.calc_liq_price_long(entry_price, leverage, position_margin)

    assert abs(d_010 - d_00999) == pytest.approx(2e-7, rel=1e-6)
    assert abs(p_010 - p_00999) == pytest.approx(0.001, rel=1e-6)


def test_af_micro_change_does_not_massively_flip_liquidation_results(model_factory):
    df = pd.read_parquet('data/derived/daily_aggregates_t2_jclose.parquet')

    model_010 = model_factory(0.1)
    model_00999 = model_factory(0.0999)

    results_010 = judge_all(df, model_010, leverage=500, position_margin=100, additional_margin=0)
    results_00999 = judge_all(df, model_00999, leverage=500, position_margin=100, additional_margin=0)

    liquidated_010 = [('❌' in r['symbol']) or (r['symbol'] == '🔵') for r in results_010]
    liquidated_00999 = [('❌' in r['symbol']) or (r['symbol'] == '🔵') for r in results_00999]

    flips = sum(a != b for a, b in zip(liquidated_010, liquidated_00999))

    assert len(results_010) == len(results_00999)
    assert flips == 0
