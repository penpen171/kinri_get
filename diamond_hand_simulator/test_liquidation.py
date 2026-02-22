import sys
sys.path.insert(0, '.')

from core.liquidation.simple_af import SimpleAFModel

entry_price    = 5000.0
leverage       = 500
position_margin = 100.0

model = SimpleAFModel()


def test_liq_price_long():
    liq = model.calc_liq_price_long(entry_price, leverage, position_margin, 0.0)
    assert liq < entry_price, "ロングのロスカット価格は建値より低いはず"


def test_liq_price_short():
    liq = model.calc_liq_price_short(entry_price, leverage, position_margin, 0.0)
    assert liq > entry_price, "ショートのロスカット価格は建値より高いはず"


def test_liq_distance_pct():
    pct = model.calc_liq_distance_pct(leverage, position_margin, 0.0)
    assert 0 < pct < 1, "変動率は0〜100%の間のはず"


def test_is_liquidated_long_safe():
    assert not model.is_liquidated_long(entry_price, 4992.0, leverage, position_margin, 0.0)


def test_is_liquidated_long_liq():
    assert model.is_liquidated_long(entry_price, 4990.0, leverage, position_margin, 0.0)
