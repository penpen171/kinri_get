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
        self.safety_multiplier = self._sanitize_safety_multiplier(
            self.config.get('safety_multiplier', 1.0)
        )
        self.tiers = self._load_tiers(self.config)

        self.current_mm_rate = None
        self.current_notional = None
        self.current_tier_index = None
        self.current_tier_min_notional = None
        self.current_tier_max_notional = None

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
                'safety_multiplier': 1.0,
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

    def _sanitize_safety_multiplier(self, multiplier):
        try:
            value = float(multiplier)
        except (TypeError, ValueError):
            return 1.0

        if value <= 0:
            return 1.0

        return min(2.0, max(0.5, value))

<<<<<<< HEAD
    def _resolve_tier(self, notional):
        for idx, tier in enumerate(self.tiers, start=1):
=======
    def _resolve_mm_rate(self, notional):
        for tier in self.tiers:
>>>>>>> main
            min_notional = tier.get('min_notional', 0)
            max_notional = tier.get('max_notional')

            if notional < min_notional:
                continue
            if max_notional is None or notional < max_notional:
                return tier, idx

        return self.tiers[-1], len(self.tiers)

    def _resolve_mm_rate(self, notional):
        tier, tier_index = self._resolve_tier(notional)
        return (
            tier.get('mm_rate', self.default_mm_rate),
            tier_index,
            tier.get('min_notional', 0),
            tier.get('max_notional'),
        )

    def calc_liq_distance_pct(self, leverage, position_margin, additional_margin=0, entry_price=None, qty=None):
        total_margin = position_margin + additional_margin
        notional = self._infer_notional(leverage, position_margin, entry_price, qty)
<<<<<<< HEAD
        mm_rate, tier_index, tier_min, tier_max = self._resolve_mm_rate(notional)
        effective_mm_rate = mm_rate * self.safety_multiplier
=======
        mm_rate = self._resolve_mm_rate(notional)
        effective_mm_rate = mm_rate * self.safety_multiplier
        self.current_mm_rate = effective_mm_rate
        self.current_notional = notional  # 任意（デバッグに便利）
        print(
            f"[TierMM] notional={notional:.2f}, mm_rate={mm_rate:.6f}, "
            f"safety_multiplier={self.safety_multiplier:.3f}, "
            f"effective_mm_rate={effective_mm_rate:.6f}, total_margin={total_margin:.2f}"
        )
>>>>>>> main

        self.current_mm_rate = effective_mm_rate
        self.current_notional = notional
        self.current_tier_index = tier_index
        self.current_tier_min_notional = tier_min
        self.current_tier_max_notional = tier_max

<<<<<<< HEAD
        print(
            f"[TierMM] notional={notional:.2f}, tier_index={tier_index}, "
            f"tier_range=[{tier_min}, {tier_max}], mm_rate={mm_rate:.6f}, "
            f"safety_multiplier={self.safety_multiplier:.3f}, "
            f"effective_mm_rate={effective_mm_rate:.6f}, total_margin={total_margin:.2f}"
        )

=======
        # 距離 = 総証拠金率 - 維持証拠金率
>>>>>>> main
        distance_pct = (total_margin / notional) - effective_mm_rate
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
        mm_rate, _, _, _ = self._resolve_mm_rate(notional)
        return mm_rate

    def get_info(self):
        return {
            'model': 'TierMM',
            'liquidation_fee_rate': self.liquidation_fee_rate,
            'price_tick': self.price_tick,
            'price_compare_epsilon': self.price_compare_epsilon,
            'default_mm_rate': self.default_mm_rate,
            'safety_multiplier': self.safety_multiplier,
            'tiers': self.tiers,
            'description': 'BingXのティア別維持証拠金率(mm_rate)ベースのロスカット計算',
        }
