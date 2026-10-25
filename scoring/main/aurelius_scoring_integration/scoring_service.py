"""AURELIUS: scoring of a credit application using a trained discrete-time CatBoost model."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sqlalchemy import create_engine, text

HORIZONS = {12: [6], 18: [6, 12], 24: [6, 12, 18], 36: [6, 12, 24], 48: [6, 12, 24, 36], 60: [6, 12, 24, 36, 48]}


def predict_pd(model_path, features_path, episode_features, term_months):
    if term_months not in HORIZONS:
        raise ValueError(f"Unsupported term: {term_months}; supported: {list(HORIZONS)}")
    config = json.loads(Path(features_path).read_text(encoding='utf-8'))
    columns = config['features']
    categories = config['categorical_features']
    if 'month_on_book' not in columns or 'term_months' in columns:
        raise ValueError('Unexpected features.json schema for this trained model')
    missing = [c for c in columns if c != 'month_on_book' and c not in episode_features]
    if missing:
        raise ValueError(f'Missing required model features: {missing}')
    rows = []
    for month in range(1, term_months + 1):
        row = {c: (month if c == 'month_on_book' else episode_features[c]) for c in columns}
        rows.append(row)
    frame = pd.DataFrame(rows, columns=columns)
    for c in categories:
        frame[c] = frame[c].fillna('UNKNOWN').astype(str)
    model = CatBoostClassifier()
    model.load_model(str(model_path))
    hazard = np.clip(model.predict_proba(frame)[:, 1], 1e-10, 1 - 1e-10)
    pd_curve = 1 - np.cumprod(1 - hazard)
    return {'term_months': term_months, 'pd_by_horizon': {str(h): float(pd_curve[h-1]) for h in HORIZONS[term_months]}, 'monthly_pd': pd_curve.tolist()}


def load_application(engine, application_id):
    with engine.connect() as connection:
        record = connection.execute(text('''
            SELECT ca.application_id, ca.company_id, ca.product_code,
                   ca.requested_amount, ca.requested_term_days,
                   ca.requested_monthly_payment
            FROM credit_applications ca WHERE ca.application_id = :id
        '''), {'id': application_id}).mappings().one_or_none()
    if record is None:
        raise ValueError(f'Application {application_id} not found')
    return dict(record)


def store_result(engine, application_id, result, episode_features, model_version='survival_v3_optuna_stage2_trial_0027'):
    # The current scoring_results schema stores one PD value, not the full PD curve.
    # Save the largest evaluated horizon in pd, and all horizons in feature_snapshot.
    horizon = max(map(int, result['pd_by_horizon']))
    pd_value = result['pd_by_horizon'][str(horizon)]
    snapshot = json.dumps({'features': episode_features, 'pd_by_horizon': result['pd_by_horizon'], 'pd_horizon_months': horizon}, ensure_ascii=False, default=str)
    with engine.begin() as connection:
        rid = connection.execute(text('''
            INSERT INTO scoring_results (application_id, model_version, pd, risk_grade, feature_snapshot)
            VALUES (:application_id, :model_version, :pd, 'UNRATED', CAST(:snapshot AS jsonb))
            RETURNING scoring_result_id
        '''), {'application_id': application_id, 'model_version': model_version, 'pd': pd_value, 'snapshot': snapshot}).scalar_one()
    return rid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--features-config', required=True)
    parser.add_argument('--episode-json', required=True, help='Precomputed episode features in JSON; no automatic DB feature extraction yet')
    parser.add_argument('--term-months', type=int, required=True)
    parser.add_argument('--database-url', help='SQLAlchemy PostgreSQL URL')
    parser.add_argument('--application-id', type=int)
    parser.add_argument('--save', action='store_true')
    args = parser.parse_args()
    if args.save and (not args.database_url or not args.application_id):
        parser.error('--save requires --database-url and --application-id')
    features = json.loads(Path(args.episode_json).read_text(encoding='utf-8'))
    result = predict_pd(args.model, args.features_config, features, args.term_months)
    if args.database_url and args.application_id:
        engine = create_engine(args.database_url)
        application = load_application(engine, args.application_id)
        result['application_id'] = application['application_id']
        if args.save:
            result['scoring_result_id'] = store_result(engine, args.application_id, result, features)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
