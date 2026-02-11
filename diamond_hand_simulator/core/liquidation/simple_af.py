"""
Simple Adjustment Factor ロスカットモデル
BingXの adjustment factor をベースにした簡易ロスカット計算
"""

import yaml
from pathlib import Path


class SimpleAFModel:
    """
    Adjustment Factor（調整係数）ベースの簡易ロスカット計算
    
    分離マージンの場合:
    - ロスカット価格 = 建値 ± (建値 × (総証拠金/必要証拠金) × (1 - AF) / レバレッジ)
    """
    
    def __init__(self, config_path=None):
        """
        Args:
            config_path: 設定ファイルのパス（Noneの場合はデフォルトパス）
        """
        if config_path is None:
            # このファイル（simple_af.py）があるフォルダを基準
            script_dir = Path(__file__).resolve().parent.parent
            config_path = script_dir / "config" / "exchanges" / "bingx.yaml"
        
        self.config = self._load_config(config_path)
        self.adjustment_factor = self.config.get('adjustment_factor', 0.10)
        self.liquidation_fee_rate = self.config.get('liquidation_fee_rate', 0.0005)
        
        
    def _load_config(self, config_path):
        """設定ファイルを読み込む"""
        path = Path(config_path)
        if not path.exists():
            print(f"⚠️  設定ファイルが見つかりません: {config_path}")
            print(f"   デフォルト値を使用します（AF=0.10）")
            return {'adjustment_factor': 0.10, 'liquidation_fee_rate': 0.0005}
        
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def calc_liq_distance_pct(self, leverage, position_margin, additional_margin=0):
        """
        建値からロスカット価格までの変動率（%）を計算
        
        Args:
            leverage: レバレッジ倍率
            position_margin: ポジション証拠金（必要証拠金）
            additional_margin: 追加証拠金
        
        Returns:
            float: 変動率（例: 0.0018 = 0.18%）
        """
        total_margin = position_margin + additional_margin
        margin_ratio = total_margin / position_margin
        return margin_ratio * (1 - self.adjustment_factor) / leverage
    
    def calc_liq_price_long(self, entry_price, leverage, position_margin, additional_margin=0):
        """
        ロングポジションのロスカット価格を計算
        
        Args:
            entry_price: 建値（エントリー価格）
            leverage: レバレッジ倍率
            position_margin: ポジション証拠金
            additional_margin: 追加証拠金
        
        Returns:
            float: ロスカット価格
        """
        distance_pct = self.calc_liq_distance_pct(leverage, position_margin, additional_margin)
        return entry_price * (1 - distance_pct)
    
    def calc_liq_price_short(self, entry_price, leverage, position_margin, additional_margin=0):
        """
        ショートポジションのロスカット価格を計算
        
        Args:
            entry_price: 建値（エントリー価格）
            leverage: レバレッジ倍率
            position_margin: ポジション証拠金
            additional_margin: 追加証拠金
        
        Returns:
            float: ロスカット価格
        """
        distance_pct = self.calc_liq_distance_pct(leverage, position_margin, additional_margin)
        return entry_price * (1 + distance_pct)
    
    def is_liquidated_long(self, entry_price, current_price, leverage, position_margin, additional_margin=0):
        """
        ロングポジションがロスカットされたか判定
        
        Args:
            entry_price: 建値
            current_price: 現在価格
            leverage: レバレッジ倍率
            position_margin: ポジション証拠金
            additional_margin: 追加証拠金
        
        Returns:
            bool: True=ロスカット、False=生存
        """
        liq_price = self.calc_liq_price_long(entry_price, leverage, position_margin, additional_margin)
        return current_price <= liq_price
    
    def is_liquidated_short(self, entry_price, current_price, leverage, position_margin, additional_margin=0):
        """
        ショートポジションがロスカットされたか判定
        
        Args:
            entry_price: 建値
            current_price: 現在価格
            leverage: レバレッジ倍率
            position_margin: ポジション証拠金
            additional_margin: 追加証拠金
        
        Returns:
            bool: True=ロスカット、False=生存
        """
        liq_price = self.calc_liq_price_short(entry_price, leverage, position_margin, additional_margin)
        return current_price >= liq_price
    
    def get_info(self):
        """モデル情報を返す"""
        return {
            'model': 'SimpleAF',
            'adjustment_factor': self.adjustment_factor,
            'liquidation_fee_rate': self.liquidation_fee_rate,
            'description': 'Adjustment Factor ベースの簡易ロスカット計算（追加証拠金対応）'
        }


# テスト用
if __name__ == '__main__':
    model = SimpleAFModel()
    
    print("=" * 60)
    print("ロスカットモデルのテスト（追加証拠金対応）")
    print("=" * 60)
    print(f"モデル: {model.get_info()}")
    
    # テストケース
    entry_price = 5000.0
    leverage = 500
    position_margin = 100.0
    additional_margin_cases = [0, 25, 50, 100]
    
    print(f"\n建値: ${entry_price:,.2f}")
    print(f"レバレッジ: {leverage}x")
    print(f"ポジション証拠金: ${position_margin:.2f}")
    print(f"AF: {model.adjustment_factor * 100}%")
    
    for additional in additional_margin_cases:
        liq_long = model.calc_liq_price_long(entry_price, leverage, position_margin, additional)
        liq_distance_pct = model.calc_liq_distance_pct(leverage, position_margin, additional)
        
        print(f"\n【追加証拠金: ${additional:.2f}】")
        print(f"  ロスカット価格（ロング）: ${liq_long:,.2f}")
        print(f"  ロスカット幅: ${entry_price - liq_long:,.2f} ({liq_distance_pct * 100:.3f}%)")
