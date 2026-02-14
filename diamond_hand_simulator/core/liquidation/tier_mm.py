"""Tier-based Maintenance Margin (mm_rate) liquidation model for BingX."""

from pathlib import Path

import yaml


class TierMMModel:
    """維持証拠金率(mm_rate)ティアを使ったロスカット目安モデル。"""

    def __init__(self, config_path=None):
        if config_path is None:
            script_dir = Path(__file__).resolve().parent.parent.parent
            config_path = script_dir / "config" / "exchanges" / "bingx.yaml"

        self.config = self._load_config(config_path)
        self.liquidation_fee_rate = self.config.get('liquidation_fee_rate', 0.0005)
        self.price_tick = self.config.get('price_tick', 0.0)
        self.price_compare_epsilon = self.config.get('price_compare_epsilon', 1e-9)
        self.default_mm_rate = self.config.get('default_mm_rate', 0.001)
        self.tiers = self._load_tiers(self.config)

    def _load_config(self, config_path):
        path = Path(config_path)
        if not path.exists():
            print(f"⚠️  設定ファイルが見つかりません: {config_path}")
            print("   デフォルト値を使用します（tier mm_rate=0.001）")
            return {
                'liquidation_fee_rate': 0.0005,
                'price_tick': 0.0,
                'price_compare_epsilon': 1e-9,
                'default_mm_rate': 0.001,
                'tiers': [
                    {'min_notional': 0, 'max_notional': None, 'mm_rate': 0.001},
                ],
            }

        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _load_tiers(self, config):
        tiers = config.get('tiers')
        if tiers:
            return sorted(tiers, key=lambda x: x.get('min_notional', 0))

        # 後方互換: 旧 maintenance_margin_tiers の notional_max/maintenance_rate を利用
        legacy = config.get('maintenance_margin_tiers', [])
        if not legacy:
            return [{'min_notional': 0, 'max_notional': None, 'mm_rate': self.default_mm_rate}]

        converted = []
        lower = 0.0
        for item in legacy:
            upper = item.get('notional_max')
            converted.append(
                {
                    'min_notional': lower,
                    'max_notional': upper,
                    'mm_rate': item.get('maintenance_rate', self.default_mm_rate),
                }
            )
            if upper is not None:
                lower = upper

        if converted and converted[-1].get('max_notional') is not None:
            converted.append(
                {
                    'min_notional': converted[-1]['max_notional'],
                    'max_notional': None,
                    'mm_rate': converted[-1]['mm_rate'],
                }
            )
        return converted

    def _infer_notional(self, leverage, position_margin, entry_price=None, qty=None):
        if qty is not None and entry_price is not None and qty > 0 and entry_price > 0:
            return entry_price * qty

        if entry_price is not None and entry_price > 0:
            inferred_qty = (position_margin * leverage) / entry_price
            return entry_price * inferred_qty

        return position_margin * leverage

    def _resolve_mm_rate(self, notional):
        for tier in self.tiers:
            min_notional = tier.get('min_notional', 0)
            max_notional = tier.get('max_notional')
            mm_rate = tier.get('mm_rate', self.default_mm_rate)

            if notional < min_notional:
                continue
            if max_notional is None or notional < max_notional:
                return mm_rate

        return self.tiers[-1].get('mm_rate', self.default_mm_rate)

    def calc_liq_distance_pct(self, leverage, position_margin, additional_margin=0, entry_price=None, qty=None):
        total_margin = position_margin + additional_margin
        notional = self._infer_notional(leverage, position_margin, entry_price, qty)
        mm_rate = self._resolve_mm_rate(notional)
        self.current_mm_rate = mm_rate
        self.current_notional = notional  # 任意（デバッグに便利）
        print(f"[TierMM] notional={notional:.2f}, mm_rate={mm_rate:.6f}, total_margin={total_margin:.2f}")


        # 距離 = 総証拠金率 - 維持証拠金率
        distance_pct = (total_margin / notional) - mm_rate
        return max(0.0, distance_pct)

    def calc_liq_price_long(self, entry_price, leverage, position_margin, additional_margin=0, qty=None):
        distance_pct = self.calc_liq_distance_pct(
            leverage,
            position_margin,
            additional_margin,
            entry_price=entry_price,
            qty=qty,
        )
        liq_price = entry_price * (1 - distance_pct)
        return self._normalize_price(liq_price)

    def calc_liq_price_short(self, entry_price, leverage, position_margin, additional_margin=0, qty=None):
        distance_pct = self.calc_liq_distance_pct(
            leverage,
            position_margin,
            additional_margin,
            entry_price=entry_price,
            qty=qty,
        )
        liq_price = entry_price * (1 + distance_pct)
        return self._normalize_price(liq_price)

    def _normalize_price(self, price):
        if not self.price_tick or self.price_tick <= 0:
            return price
        return round(price / self.price_tick) * self.price_tick

    def is_liquidated_long(self, entry_price, current_price, leverage, position_margin, additional_margin=0, qty=None):
        liq_price = self.calc_liq_price_long(entry_price, leverage, position_margin, additional_margin, qty)
        return current_price <= (liq_price + self.price_compare_epsilon)

    def is_liquidated_short(self, entry_price, current_price, leverage, position_margin, additional_margin=0, qty=None):
        liq_price = self.calc_liq_price_short(entry_price, leverage, position_margin, additional_margin, qty)
        return current_price >= (liq_price - self.price_compare_epsilon)

    def get_mm_rate(self, leverage, position_margin, entry_price=None, qty=None):
        notional = self._infer_notional(leverage, position_margin, entry_price, qty)
        return self._resolve_mm_rate(notional)

    def get_info(self):
        return {
            'model': 'TierMM',
            'liquidation_fee_rate': self.liquidation_fee_rate,
            'price_tick': self.price_tick,
            'price_compare_epsilon': self.price_compare_epsilon,
            'default_mm_rate': self.default_mm_rate,
            'tiers': self.tiers,
            'description': 'BingXのティア別維持証拠金率(mm_rate)ベースのロスカット計算',
        }
