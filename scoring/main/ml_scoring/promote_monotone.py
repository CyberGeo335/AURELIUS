"""Install only the validated frozen candidate, preserving prior model provenance."""
import hashlib
import json
from pathlib import Path
import shutil

from ..config import ROOT
from .train_monotone import OUT


def main():
    cfg = json.loads((OUT / "best_config.json").read_text(encoding="utf-8"))
    validation = json.loads((OUT / "validation_report.json").read_text(encoding="utf-8"))
    holdout = json.loads((OUT / "test_report.json").read_text(encoding="utf-8"))
    if not cfg["accepted"] or not validation["accepted"] or sum(validation["candidate_monotonicity_violations"].values()):
        raise RuntimeError("Refusing to promote an unaccepted candidate")
    target = ROOT / "main/ml_scoring/model"
    previous = {"config": json.loads((target / "best_config.json").read_text(encoding="utf-8")),
                "sha256": hashlib.sha256((target / "best_model.cbm").read_bytes()).hexdigest(),
                "original_artifact": "models/experiments/survival_v3_optuna_stage2/best_model.cbm"}
    if (target / "previous_model_info.json").exists():
        previous = json.loads((target / "previous_model_info.json").read_text(encoding="utf-8"))
    cfg["model_sha256"] = hashlib.sha256((OUT / "candidate_model.cbm").read_bytes()).hexdigest()
    cfg["serving_contracts"] = ["db_proxy_v2", "db_auto_v3", "db_diagnostic_v2", "synthetic_origination_v2"]
    cfg["previous_model_sha256"] = previous["sha256"]
    if not (target / "previous_model_info.json").exists():
        (target / "previous_model_info.json").write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(OUT / "candidate_model.cbm", target / "best_model.cbm.new")
    (target / "best_config.json.new").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (target / "best_model.cbm.new").replace(target / "best_model.cbm")
    (target / "best_config.json.new").replace(target / "best_config.json")
    (target / "validation_report.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    (target / "test_report.json").write_text(json.dumps(holdout, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model": cfg["model_name"], "sha256": cfg["model_sha256"]}))


if __name__ == "__main__":
    main()
