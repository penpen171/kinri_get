import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tempfile

import pytest
import yaml

from core.liquidation.tier_mm import TierMMModel


@pytest.fixture
def tier_model():
    cfg = {
        'price_tick': 0.0,
        'price_compare_epsilon': 1e-9,
        'tiers': [
            {'min_notional': 0, 'max_notional': 100, 'mm_rate': 0.001},
            {'min_notional': 100, 'max_notional': 200, 'mm_rate': 0.002},
            {'min_notional': 200, 'max_notional': None, 'mm_rate': 0.003},
        ],
    }

    with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
        yaml.safe_dump(cfg, f)
        path = Path(f.name)

    yield TierMMModel(config_path=str(path))
    path.unlink(missing_ok=True)


def test_tier_boundary_selection(tier_model):
    # [0,100) -> tier1
    assert tier_model.get_mm_rate(leverage=10, position_margin=10, entry_price=10, qty=9.999) == pytest.approx(0.001)
    # 100 ちょうど -> tier2
    assert tier_model.get_mm_rate(leverage=10, position_margin=10, entry_price=10, qty=10.0) == pytest.approx(0.002)
    # 200 ちょうど -> tier3 (max=None)
    assert tier_model.get_mm_rate(leverage=10, position_margin=10, entry_price=10, qty=20.0) == pytest.approx(0.003)


def test_mm_rate_monotonic_effect_on_distance_and_liq_price(tier_model):
    entry_price = 100.0
    leverage = 10
    position_margin = 10.0

    # notional=50 => mm=0.001
    d_low_mm = tier_model.calc_liq_distance_pct(leverage, position_margin, entry_price=entry_price, qty=0.5)
    p_low_mm = tier_model.calc_liq_price_long(entry_price, leverage, position_margin, qty=0.5)

    # notional=100 => mm=0.002
    d_high_mm = tier_model.calc_liq_distance_pct(leverage, position_margin, entry_price=entry_price, qty=1.0)
    p_high_mm = tier_model.calc_liq_price_long(entry_price, leverage, position_margin, qty=1.0)

    # mm_rate上昇で distance は縮小し、liq price は建値に近づく（longなら上がる）
    assert d_high_mm < d_low_mm
    assert p_high_mm > p_low_mm
