"""Final holdout report for the frozen, validation-selected candidate."""
import json
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from ..config import ROOT
from .train_monotone import OUT, evaluate


def main():
    cfg = json.loads((OUT / "best_config.json").read_text(encoding="utf-8"))
    if not cfg["accepted"]:
        raise RuntimeError("Candidate was not accepted on validation")
    data = pd.read_parquet(ROOT / "data/processed/ml_survival_dataset.parquet")
    with np.load(ROOT / "models/experiments/survival_v3_baseline/splits.npz") as splits:
        train, test = data.iloc[splits["train_idx"]], data.iloc[splits["test_idx"]]
    horizons = {int(k): v for k, v in cfg["horizons_by_term"].items()}
    rows = {}
    for name, path in (("baseline", ROOT / "models/experiments/survival_v3_optuna_stage2/best_model.cbm"),
                       ("candidate", OUT / "candidate_model.cbm")):
        model = CatBoostClassifier()
        model.load_model(str(path))
        rows[name] = evaluate(model, train, test, cfg["features"], cfg["categorical_features"], horizons)
    rows["notes"] = ["Frozen candidate selected on original validation; no HPO on test or demo businesses",
                     "Synthetic holdout; does not establish calibration on real bank borrowers",
                     "The original test split was previously examined for the original model; this is not a newly collected external holdout"]
    (OUT / "test_report.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: {metric: rows[key][metric] for metric in ("weighted_ipcw_brier", "max_calibration_abs_error")}
                      for key in ("baseline", "candidate")}))


if __name__ == "__main__":
    main()
