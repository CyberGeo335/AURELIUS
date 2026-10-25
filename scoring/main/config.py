"""Runtime paths. No passwords or machine-specific absolute paths."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    model_path: Path = ROOT / "main/ml_scoring/model/best_model.cbm"
    features_path: Path = ROOT / "main/ml_scoring/model/features.json"
    model_config_path: Path = ROOT / "main/ml_scoring/model/best_config.json"
    database_url: str | None = None

    @classmethod
    def from_env(cls):
        return cls(
            model_path=Path(os.getenv("AURELIUS_MODEL_PATH", str(cls.model_path))),
            features_path=Path(os.getenv("AURELIUS_FEATURES_PATH", str(cls.features_path))),
            model_config_path=Path(os.getenv("AURELIUS_MODEL_CONFIG_PATH", str(cls.model_config_path))),
            database_url=os.getenv("DATABASE_URL"),
        )
