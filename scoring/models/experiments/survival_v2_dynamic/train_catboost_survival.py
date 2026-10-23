"""AURELIUS synthetic discrete-time survival baseline.

Run from project root:
 python data/AURELIUS_ML/train_catboost_survival.py --data ml_data_10000 --output models/survival_baseline

Dependencies: pip install catboost pandas numpy scikit-learn pyarrow matplotlib
Synthetic demonstration only; NOT calibrated for real lending.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss

FEATURES = ["age_months", "industry", "entity_type", "monthly_revenue", "revenue_trend_12m",
            "revenue_volatility", "operating_margin", "cash_buffer_months", "dscr",
            "debt_to_revenue", "prior_overdue_30d", "requested_amount", "term_months",
            "annual_rate", "macro_stress", "month_on_book"]
CATEGORICAL = ["industry", "entity_type"]


def load_parts(folder, prefix):
    paths = sorted(folder.glob(f"{prefix}_part_*.parquet"))
    if paths:
        return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    paths = sorted(folder.glob(f"{prefix}_part_*.csv"))
    if paths:
        return pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    raise FileNotFoundError(f"No {prefix}_part_*.parquet or .csv in {folder}")


def predict_episode_curves(model, df, horizon=12):
    """Predict 1..horizon hazards using only origination features and month_on_book.
    Never use future outcomes or future covariates for a forecast.
    """
    origin = df.sort_values('month_on_book').drop_duplicates('episode_id').copy()
    pieces = []
    for month in range(1, horizon + 1):
        x = origin[FEATURES].copy()
        x['month_on_book'] = month
        h = model.predict_proba(x)[:, 1]
        pieces.append(np.clip(h, 1e-8, 1 - 1e-8))
    hazard = np.column_stack(pieces)
    cumulative = 1 - np.cumprod(1 - hazard, axis=1)
    return origin[['episode_id', 'borrower_id']].reset_index(drop=True), hazard, cumulative


def censor_survival(ep):
    """P(C >= t) by reverse Kaplan-Meier, pooled within evaluation split.
    A censoring event occurs only for episodes marked censored. For IPCW event
    at month t, use G(t-); for survival through H use G(H).
    """
    times = ep['observed_months'].to_numpy(dtype=int)
    cens = ep['censored'].to_numpy(dtype=int)
    max_t = int(max(times.max(), 12))
    before = np.ones(max_t + 2, dtype=float)
    after = np.ones(max_t + 2, dtype=float)
    survival = 1.0
    for t in range(1, max_t + 2):
        before[t] = survival
        risk = np.count_nonzero(times >= t)
        n_censor = np.count_nonzero((times == t) & (cens == 1))
        if risk:
            survival *= (1 - n_censor / risk)
        after[t] = survival
    return before, after


def horizon_metrics(episodes, ids, cumulative, horizon):
    frame = ids.merge(episodes, on=['episode_id', 'borrower_id'], validate='one_to_one')
    pred = cumulative[:, horizon - 1]
    # Outcomes known: default on/before H, or observed event-free through H.
    event = (frame['event'].to_numpy() == 1)
    duration = frame['observed_months'].to_numpy(dtype=int)
    event_by_h = event & (duration <= horizon)
    survived_h = duration >= horizon
    usable = event_by_h | survived_h
    y = event_by_h[usable].astype(int)
    before, after = censor_survival(episodes)
    weights = np.zeros(len(frame))
    weights[event_by_h] = 1 / np.maximum(before[duration[event_by_h]], 1e-5)
    weights[survived_h & ~event_by_h] = 1 / max(after[horizon], 1e-5)
    w = weights[usable]
    p = pred[usable]
    result = {'horizon_months': horizon, 'episodes': len(frame), 'known_outcomes': int(usable.sum()),
              'censored_before_horizon': int((~usable).sum()),
              'weighted_event_fraction': float(np.average(y, weights=w)),
              'mean_predicted_pd': float(np.average(p, weights=w)),
              'ipcw_brier': float(np.average((y-p)**2, weights=w))}
    if len(np.unique(y)) == 2:
        result['ipcw_roc_auc'] = float(roc_auc_score(y, p, sample_weight=w))
        result['ipcw_pr_auc'] = float(average_precision_score(y, p, sample_weight=w))
    else:
        result['ipcw_roc_auc'] = None
        result['ipcw_pr_auc'] = None
    # Deciles with IPCW event rates; estimates are meaningful only if censoring
    # is independent conditional on the assumptions of the censoring model.
    cal = pd.DataFrame({'prediction': p, 'outcome': y, 'weight': w})
    cal['decile'] = pd.qcut(cal['prediction'].rank(method='first'), q=10, labels=False) + 1
    calibration = cal.groupby('decile').apply(lambda g: pd.Series({
        'episodes': len(g), 'mean_predicted_pd': np.average(g.prediction, weights=g.weight),
        'ipcw_observed_event_rate': np.average(g.outcome, weights=g.weight)
    }), include_groups=False).reset_index()
    return result, calibration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('ml_data_10000'))
    parser.add_argument('--output', type=Path, default=Path('models/survival_baseline'))
    parser.add_argument('--iterations', type=int, default=650)
    parser.add_argument('--depth', type=int, default=6)
    parser.add_argument('--learning-rate', type=float, default=0.04)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--horizon', type=int, default=12)
    parser.add_argument('--device', choices=['CPU','GPU'], default='CPU')
    args = parser.parse_args()
    if args.horizon < 1 or args.horizon > 60:
        parser.error('--horizon must be between 1 and 60')
    args.output.mkdir(parents=True, exist_ok=True)
    print('Reading train/val/test and episode metadata...', flush=True)
    train = load_parts(args.data, 'train')
    val = load_parts(args.data, 'val')
    test = load_parts(args.data, 'test')
    episodes = load_parts(args.data, 'episodes')
    for name, df in [('train',train),('val',val),('test',test)]:
        missing = set(FEATURES + ['default_event','episode_id','borrower_id']) - set(df.columns)
        if missing:
            raise ValueError(f'{name}: missing {sorted(missing)}')
        print(f'{name}: {len(df):,} rows, {df.episode_id.nunique():,} episodes, {df.default_event.sum():,} defaults', flush=True)
    if not set(['episode_id','borrower_id','split','observed_months','event','censored']).issubset(episodes.columns):
        raise ValueError('Missing episode metadata fields')
    ids = {name:set(df.borrower_id.unique()) for name,df in [('train',train),('val',val),('test',test)]}
    if (ids['train'] & ids['val']) or (ids['train'] & ids['test']) or (ids['val'] & ids['test']):
        raise ValueError('Borrower leakage between splits')
    for df in (train,val,test):
        for cat in CATEGORICAL:
            df[cat] = df[cat].astype(str)
    model = CatBoostClassifier(iterations=args.iterations, depth=args.depth,
                               learning_rate=args.learning_rate, loss_function='Logloss',
                               eval_metric='Logloss', random_seed=args.seed,
                               task_type=args.device, thread_count=-1,
                               verbose=100, l2_leaf_reg=5)
    print('Training discrete monthly hazard model...', flush=True)
    model.fit(train[FEATURES], train['default_event'], cat_features=CATEGORICAL,
              eval_set=(val[FEATURES],val['default_event']), early_stopping_rounds=75,
              use_best_model=True)
    model.save_model(str(args.output/'catboost_hazard.cbm'))
    metrics = {'model': 'CatBoost discrete-time hazard (synthetic)', 'seed': args.seed,
               'best_iteration': model.get_best_iteration(), 'horizon_months':args.horizon,
               'warning': 'Synthetic data only; no real-world credit calibration.'}
    for split_name, df in [('train',train),('val',val),('test',test)]:
        prob = np.clip(model.predict_proba(df[FEATURES])[:,1],1e-8,1-1e-8)
        y = df['default_event'].to_numpy(dtype=int)
        row_metric = {'rows':len(df), 'defaults':int(y.sum()),
                      'row_logloss':float(log_loss(y,prob,labels=[0,1])),
                      'row_brier':float(brier_score_loss(y,prob)),
                      'row_roc_auc':float(roc_auc_score(y,prob)),
                      'row_pr_auc':float(average_precision_score(y,prob))}
        origin, hazard, cum = predict_episode_curves(model, df, args.horizon)
        ep = episodes[episodes['split']==split_name].copy()
        horizon_metric, calibration = horizon_metrics(ep, origin, cum, args.horizon)
        calibration.to_csv(args.output/f'calibration_{split_name}.csv',index=False)
        predictions = origin.copy()
        predictions[f'pd_{args.horizon}m'] = cum[:,-1]
        predictions.to_csv(args.output/f'predictions_{split_name}.csv',index=False)
        metrics[split_name] = {'row_level':row_metric, 'horizon':horizon_metric}
        print(f"{split_name}: row AUC={row_metric['row_roc_auc']:.4f}; "
              f"PD{args.horizon} IPCW AUC={horizon_metric['ipcw_roc_auc']:.4f}; "
              f"Brier={horizon_metric['ipcw_brier']:.4f}",flush=True)
    importance = pd.DataFrame({'feature':FEATURES,'importance':model.get_feature_importance()})
    importance.sort_values('importance',ascending=False).to_csv(args.output/'feature_importance.csv',index=False)
    (args.output/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\nTop features:\n'+importance.sort_values('importance',ascending=False).head(10).to_string(index=False))
    print(f'\nSaved to {args.output.resolve()}')
    print('Note: IPCW uses pooled censoring KM; interpret as an exploratory synthetic benchmark.')

if __name__=='__main__':
    main()
