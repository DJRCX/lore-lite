"""Load and validate the project governance configuration."""

from pathlib import Path

import yaml

from lore_lite.schema import LoreConfig


def load_config(path: str | Path = "lore.config.yaml") -> LoreConfig:
    """Read a YAML config file and validate it against the shared contract."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration at {config_path} must be a YAML mapping")
    return LoreConfig.model_validate(data)
