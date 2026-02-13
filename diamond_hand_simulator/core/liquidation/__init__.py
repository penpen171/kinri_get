from pathlib import Path

import yaml

from .simple_af import SimpleAFModel
from .tier_mm import TierMMModel


def create_liquidation_model(config_path=None):
    if config_path is None:
        script_dir = Path(__file__).resolve().parent.parent.parent
        config_path = script_dir / "config" / "exchanges" / "bingx.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}

    model_type = str(cfg.get('liquidation_model', 'tier_mm')).lower()
    if model_type == 'simple_af':
        return SimpleAFModel(config_path=config_path)
    return TierMMModel(config_path=config_path)


__all__ = ['SimpleAFModel', 'TierMMModel', 'create_liquidation_model']
