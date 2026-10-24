import hashlib
import json
import math
from pathlib import Path

from ..config import Settings
from ..schemas import ConfigurationError, InputError, ScoringResult


class Predictor:
    """Load the trained classifier once and keep feature ordering unchanged."""

    def __init__(self, settings: Settings | None = None):
        settings = settings or Settings.from_env()
        for path in (settings.model_path, settings.features_path, settings.model_config_path):
            if not Path(path).is_file():
                raise ConfigurationError(f"Missing artifact: {path}. See main/README.md")
        config = json.loads(settings.features_path.read_text(encoding="utf-8"))
        training = json.loads(settings.model_config_path.read_text(encoding="utf-8"))
        self.features = config["features"]
        self.categories = config["categorical_features"]
        self.horizons = {int(k): v for k, v in training["horizons_by_term"].items()}
        if "month_on_book" not in self.features or "term_months" in self.features:
            raise ConfigurationError("Expected the final discrete-time feature contract")
        from catboost import CatBoostClassifier
        self.model = CatBoostClassifier()
        self.model.load_model(str(settings.model_path))
        if self.model.feature_names_ != self.features:
            raise ConfigurationError("Model and features.json do not match")
        self.model_sha256 = hashlib.sha256(settings.model_path.read_bytes()).hexdigest()
        if training.get("model_sha256") and training["model_sha256"] != self.model_sha256:
            raise ConfigurationError("Model SHA256 does not match its versioned configuration")
        self.model_version = training.get("model_name", "dt_stage2") + "_" + self.model_sha256[:16]

    def predict(self, features: dict, term_months: int) -> ScoringResult:
        if isinstance(term_months, bool) or term_months not in self.horizons:
            raise InputError(f"Unsupported model term: {term_months}; use {sorted(self.horizons)}")
        missing = [f for f in self.features if f != "month_on_book" and features.get(f) is None]
        if missing:
            raise InputError(f"Missing model features: {missing}")
        for key in self.features:
            if key not in self.categories and key != "month_on_book":
                if not math.isfinite(float(features[key])):
                    raise InputError(f"Non-finite feature: {key}")
        import pandas as pd
        frame = pd.DataFrame([
            {key: month if key == "month_on_book" else features[key] for key in self.features}
            for month in range(1, term_months + 1)
        ], columns=self.features)
        for key in self.categories:
            frame[key] = frame[key].astype(str)
        hazards = [float(x) for x in self.model.predict_proba(frame)[:, 1]]
        survival, curve = 1.0, []
        for hazard in hazards:
            if not math.isfinite(hazard) or not 0 <= hazard <= 1:
                raise InputError("Model returned invalid hazard")
            survival *= 1 - hazard
            curve.append(1 - survival)
        return ScoringResult(self.model_version, hazards, curve,
                             {h: curve[h - 1] for h in self.horizons[term_months]}, term_months)
