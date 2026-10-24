"""Reproducible semantic repair candidate; no tuning on the 30 demo companies.

Use python -m main.ml_scoring.train_monotone. Training uses only the original
train split. Candidate acceptance is based on the original validation split.
"""
import gc
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sksurv.metrics import brier_score
from sksurv.nonparametric import kaplan_meier_estimator
from sksurv.util import Surv

from ..config import ROOT

OUT = ROOT / "models/experiments/survival_v4_monotone"
CONSTRAINTS = {"dscr": -1, "debt_to_revenue": 1, "cash_buffer_months": -1,
               "operating_margin": -1, "revenue_trend_12m": -1,
               "prior_overdue_30d": 1, "requested_amount": 1, "macro_stress": 1,
               "annual_rate": 1, "revenue_volatility": 1}


def expand(episodes, features, cats, observed=True):
    durations = episodes["duration" if observed else "term_months"].to_numpy(dtype=np.int32)
    ids = np.repeat(np.arange(len(episodes), dtype=np.int32), durations)
    ends = np.cumsum(durations, dtype=np.int64)
    starts = np.repeat(ends - durations, durations)
    months = (np.arange(len(ids)) - starts + 1).astype(np.int16)
    columns = {}
    for key in features:
        if key == "month_on_book":
            columns[key] = months
        elif key in cats:
            columns[key] = episodes[key].to_numpy()[ids]
        else:
            columns[key] = episodes[key].to_numpy(dtype=np.float32)[ids]
    frame = pd.DataFrame(columns, columns=features)
    if not observed:
        return frame
    labels = ((episodes["event"].to_numpy(dtype=np.int8)[ids] == 1) & (months == durations[ids])).astype(np.int8)
    return frame, labels


def evaluate(model, train, validation, features, cats, horizons):
    rows = []
    for term, times in horizons.items():
        tr = train.loc[train.term_months == term]
        va = validation.loc[validation.term_months == term].reset_index(drop=True)
        predictions = []
        for left in range(0, len(va), 1000):
            frame = expand(va.iloc[left:left + 1000], features, cats, observed=False)
            h = model.predict_proba(frame)[:, 1].reshape(-1, term)
            predictions.append(np.cumprod(1 - h, axis=1))
        survival = np.vstack(predictions)
        ytr = Surv.from_arrays(tr.event.to_numpy(bool), tr.duration.to_numpy(float))
        yva = Surv.from_arrays(va.event.to_numpy(bool), va.duration.to_numpy(float))
        _, scores = brier_score(ytr, yva, survival[:, np.asarray(times) - 1], np.asarray(times, float))
        for horizon, score in zip(times, scores):
            p = 1 - survival[:, horizon - 1]
            bins = pd.qcut(pd.Series(p), 10, labels=False, duplicates="drop")
            error = 0.0
            for index in sorted(bins.dropna().unique()):
                mask = bins.to_numpy() == index
                group = va.loc[mask]
                t, s = kaplan_meier_estimator(group.event.to_numpy(bool), group.duration.to_numpy(float))
                position = np.searchsorted(t, horizon, side="right") - 1
                observed = 1 - s[position] if position >= 0 else 0
                error += abs(float(p[mask].mean()) - observed) * int(mask.sum()) / len(va)
            rows.append({"term_months": term, "horizon_months": horizon,
                         "n": len(va), "ipcw_brier": float(score), "calibration_abs_error": float(error)})
    weighted = float(np.average([r["ipcw_brier"] for r in rows], weights=[r["n"] for r in rows]))
    return {"weighted_ipcw_brier": weighted, "max_calibration_abs_error": max(r["calibration_abs_error"] for r in rows), "by_horizon": rows}


def monotonicity_check(model, episodes, features, constraints):
    base = episodes.sample(min(128, len(episodes)), random_state=123)[[f for f in features if f != "month_on_book"]].copy()
    base["month_on_book"] = 12
    grids = {"dscr": [.05, .5, 1, 1.5, 3.6, 8, 18], "debt_to_revenue": [.03,.1,.3,1,3,15],
             "cash_buffer_months": [0,.5,1,3,8,18], "operating_margin": [-.28,0,.1,.27,.48],
             "revenue_trend_12m": [-.9,-.2,0,.2,1,3], "prior_overdue_30d": [0,1],
             "requested_amount": [50000,300000,1000000,3000000,30000000], "macro_stress": [-.35,0,.35,.8],
             "annual_rate": [.10,.15,.19,.255,.30,.36], "revenue_volatility": [0,.03,.1,.3,.65,1,3]}
    counts = {}
    for key, direction in constraints.items():
        predictions = []
        for value in grids[key]:
            modified = base.copy()
            modified[key] = value
            predictions.append(model.predict_proba(modified[features])[:, 1])
        delta = np.diff(np.asarray(predictions), axis=0)
        counts[key] = int(np.sum(direction * delta < -1e-10))
    return counts


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    original = ROOT / "models/experiments/survival_v3_optuna_stage2"
    cfg = json.loads((original / "best_config.json").read_text(encoding="utf-8"))
    features, cats = cfg["features"], cfg["categorical_features"]
    horizons = {int(k): v for k, v in cfg["horizons_by_term"].items()}
    df = pd.read_parquet(ROOT / "data/processed/ml_survival_dataset.parquet")
    split_path = ROOT / "models/experiments/survival_v3_baseline/splits.npz"
    with np.load(split_path) as split:
        train = df.iloc[split["train_idx"]].reset_index(drop=True)
        validation = df.iloc[split["val_idx"]].reset_index(drop=True)
    del df
    # Fixed, outcome-independent sample within train only to fit the available
    # workstation RAM. Validation stays complete; no business-demo selection.
    train_reference = train
    train = train.sample(n=min(35000, len(train)), random_state=20261024).reset_index(drop=True)
    print("Building train person-month pool", flush=True)
    X, y = expand(train, features, cats)
    train_pool = Pool(X, y, cat_features=cats)
    train_pool.quantize(border_count=128, random_seed=42)
    del X, y
    gc.collect()
    print("Building validation person-month pool", flush=True)
    X, y = expand(validation, features, cats)
    # Apply precisely the train borders to validation (no val-derived bins).
    borders = OUT / "train_borders.tsv"
    train_pool.save_quantization_borders(str(borders))
    val_pool = Pool(X, y, cat_features=cats)
    val_pool.quantize(input_borders=str(borders))
    del X, y
    gc.collect()
    model = CatBoostClassifier(iterations=500, depth=3, learning_rate=.08, l2_leaf_reg=3,
        loss_function="Logloss", eval_metric="Logloss", random_seed=42, thread_count=2,
        task_type="CPU", monotone_constraints=CONSTRAINTS, early_stopping_rounds=80,
        # Complex CTRs may combine category and numeric bins, bypassing a
        # numerical monotonic constraint through a derived categorical feature.
        max_ctr_complexity=1,
        allow_writing_files=False, verbose=50, border_count=128, used_ram_limit="1200mb")
    model.fit(train_pool, eval_set=val_pool, use_best_model=True)
    del train_pool, val_pool
    gc.collect()
    model.save_model(str(OUT / "candidate_model.cbm"))
    print("Evaluating frozen candidate on validation", flush=True)
    baseline = CatBoostClassifier()
    baseline.load_model(str(original / "best_model.cbm"))
    before = evaluate(baseline, train_reference, validation, features, cats, horizons)
    after = evaluate(model, train_reference, validation, features, cats, horizons)
    old_violations = monotonicity_check(baseline, validation, features, CONSTRAINTS)
    new_violations = monotonicity_check(model, validation, features, CONSTRAINTS)
    accepted = (after["weighted_ipcw_brier"] <= before["weighted_ipcw_brier"] + .003
                and after["max_calibration_abs_error"] <= .06 and sum(new_violations.values()) == 0)
    metadata = {"model_name": "dt_monotone_v1", "features": features, "categorical_features": cats,
        "horizons_by_term": horizons, "monotone_constraints": CONSTRAINTS,
        "training_params": model.get_params(), "best_iteration": model.get_best_iteration(),
        "training_dataset": "data/processed/ml_survival_dataset.parquet",
        "train_sample_episodes": len(train), "train_sample_seed": 20261024,
        "train_reference_episodes": len(train_reference), "validation_episodes": len(validation),
        "split_sha256": hashlib.sha256(split_path.read_bytes()).hexdigest(),
        "selection": "original validation only; no tuning on 30 demo businesses or test",
        "test_used_for_selection": False, "accepted": accepted,
        "acceptance_rule": "validation weighted IPCW Brier <= original + 0.003; max bin calibration error <=0.06; zero tested monotonicity violations"}
    (OUT / "best_config.json").write_text(json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8")
    (OUT / "validation_report.json").write_text(json.dumps({"baseline": before, "candidate": after,
        "baseline_monotonicity_violations": old_violations, "candidate_monotonicity_violations": new_violations,
        "accepted": accepted, "elapsed_seconds": time.monotonic()-start}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": accepted, "baseline_brier": before["weighted_ipcw_brier"],
                      "candidate_brier": after["weighted_ipcw_brier"], "violations": new_violations}), flush=True)


if __name__ == "__main__":
    main()
