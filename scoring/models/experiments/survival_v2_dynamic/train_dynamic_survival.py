"""AURELIUS V2: dynamic one-month-ahead hazard vs origination baseline.

At each month start, predict default DURING that month using lagged covariates.
Does not claim a prospective 12-month PD from future realized covariates.

Run: python train_dynamic_survival.py --data ml_data_v2_10000 \
 --baseline models/survival_v2_baseline/catboost_hazard.cbm \
 --output models/survival_v2_dynamic
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss

ORIGIN_FEATURES = ['age_months','industry','entity_type','monthly_revenue','revenue_trend_12m',
                   'revenue_volatility','operating_margin','cash_buffer_months','dscr',
                   'debt_to_revenue','prior_overdue_30d','requested_amount','term_months',
                   'annual_rate','macro_stress','month_on_book']
DYNAMIC_EXTRA = ['current_monthly_revenue','current_operating_margin',
                 'current_cash_buffer_months','current_dscr','current_debt_to_revenue',
                 'current_revenue_trend_3m','current_macro_stress']
FEATURES = ORIGIN_FEATURES + DYNAMIC_EXTRA
CATEGORICAL = ['industry','entity_type']
KEYS = ['episode_id','borrower_id','month_on_book']


def read_parts(folder, prefix):
    for ext in ('parquet','csv'):
        files = sorted(folder.glob(f'{prefix}_part_*.{ext}'))
        if files:
            return pd.concat([(pd.read_parquet(p) if ext=='parquet' else pd.read_csv(p)) for p in files], ignore_index=True)
    raise FileNotFoundError(f'Missing {prefix}_part_*.parquet/.csv in {folder}')


def check_split(name, df, orig):
    required = set(FEATURES + KEYS + ['default_event'])
    if missing := required - set(df.columns):
        raise ValueError(f'{name}: missing {sorted(missing)}')
    if df.duplicated(KEYS).any() or orig.duplicated(KEYS).any():
        raise ValueError(f'{name}: duplicate episode-month keys')
    if len(df) != len(orig):
        raise ValueError(f'{name}: dynamic and origin row counts differ')
    chk = df[KEYS+['default_event']].merge(orig[KEYS+['default_event']], on=KEYS,
                                         how='outer', validate='one_to_one', indicator=True,
                                         suffixes=('_dynamic','_origin'))
    if (chk['_merge']!='both').any() or (chk.default_event_dynamic != chk.default_event_origin).any():
        raise ValueError(f'{name}: dynamic and origination targets do not match')
    if df[FEATURES].select_dtypes(include='number').isna().any().any():
        raise ValueError(f'{name}: missing numeric feature values')
    if not np.isfinite(df[FEATURES].select_dtypes(include='number').to_numpy()).all():
        raise ValueError(f'{name}: nonfinite features')
    for col in CATEGORICAL:
        if df[col].isna().any():
            raise ValueError(f'{name}: missing categorical values in {col}')
        df[col] = df[col].astype(str)
    print(f'{name}: {len(df):,} rows, {df.episode_id.nunique():,} episodes, '
          f'{int(df.default_event.sum()):,} defaults', flush=True)


def metrics(y, p):
    y = np.asarray(y, dtype=int)
    p = np.clip(np.asarray(p, dtype=float), 1e-8, 1-1e-8)
    result = {'rows':int(len(y)), 'events':int(y.sum()), 'event_rate':float(y.mean()),
              'logloss':float(log_loss(y,p,labels=[0,1])),
              'brier':float(brier_score_loss(y,p)),
              'mean_predicted_hazard':float(p.mean())}
    if len(np.unique(y))==2:
        result['roc_auc'] = float(roc_auc_score(y,p))
        result['pr_auc'] = float(average_precision_score(y,p))
    else:
        result['roc_auc'] = None
        result['pr_auc'] = None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('ml_data_v2_10000'))
    parser.add_argument('--output', type=Path, default=Path('models/survival_v2_dynamic'))
    parser.add_argument('--baseline', type=Path, default=Path('models/survival_v2_baseline/catboost_hazard.cbm'))
    parser.add_argument('--iterations', type=int, default=650)
    parser.add_argument('--depth', type=int, default=6)
    parser.add_argument('--learning-rate', type=float, default=0.04)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--device', choices=['CPU','GPU'], default='CPU')
    args = parser.parse_args()
    if not args.baseline.exists():
        parser.error(f'Origination baseline model not found: {args.baseline}')
    args.output.mkdir(parents=True,exist_ok=True)
    print('Loading V2 origination and dynamic rows...',flush=True)
    dynamic, origin = {}, {}
    for split in ('train','val','test'):
        dynamic[split] = read_parts(args.data, 'dynamic_'+split)
        origin[split] = read_parts(args.data, split)
        check_split(split, dynamic[split], origin[split])
    ids = {s:set(dynamic[s].borrower_id.unique()) for s in dynamic}
    if any(ids[a] & ids[b] for a,b in [('train','val'),('train','test'),('val','test')]):
        raise ValueError('Borrower leakage across splits')
    # Do not pass future outcomes or IDs as features. V2 generator's current_* fields
    # are lagged and available at the START of the month; inspect generator if changed.
    model = CatBoostClassifier(iterations=args.iterations, depth=args.depth,
                               learning_rate=args.learning_rate, loss_function='Logloss',
                               eval_metric='Logloss', random_seed=args.seed,
                               task_type=args.device, verbose=100, l2_leaf_reg=5)
    print('Training dynamic one-month-ahead hazard...',flush=True)
    model.fit(dynamic['train'][FEATURES],dynamic['train'].default_event,
              cat_features=CATEGORICAL,
              eval_set=(dynamic['val'][FEATURES],dynamic['val'].default_event),
              early_stopping_rounds=75,use_best_model=True)
    model.save_model(str(args.output/'catboost_dynamic_hazard.cbm'))
    baseline = CatBoostClassifier()
    baseline.load_model(str(args.baseline))
    if baseline.feature_names_ != ORIGIN_FEATURES:
        raise ValueError('Baseline feature list does not match V2 origination model')
    report = {'purpose':'Compare dynamic vs origination one-month hazard on IDENTICAL V2 rows',
              'prediction_time':'start of each month; outcome is default during that month',
              'important':'Not a 12-month forecast using future realized dynamic covariates',
              'best_iteration':model.get_best_iteration(), 'splits':{}}
    for split in ('train','val','test'):
        d = dynamic[split]
        o = origin[split]
        # Align baseline rows explicitly, never rely on chunk/merge ordering.
        aligned = d[KEYS].merge(o[KEYS+[f for f in ORIGIN_FEATURES if f not in KEYS]],on=KEYS,how='left',validate='one_to_one',sort=False)
        if aligned[ORIGIN_FEATURES].isna().any().any():
            raise ValueError(f'{split}: missing aligned origination features')
        for col in CATEGORICAL:
            aligned[col] = aligned[col].astype(str)
        y = d.default_event.to_numpy(dtype=int)
        pdyn = model.predict_proba(d[FEATURES])[:,1]
        pbase = baseline.predict_proba(aligned[ORIGIN_FEATURES])[:,1]
        report['splits'][split] = {'dynamic':metrics(y,pdyn), 'origination_baseline':metrics(y,pbase)}
        out = d[KEYS+['default_event']].copy()
        out['dynamic_hazard'] = pdyn
        out['baseline_hazard'] = pbase
        out.to_csv(args.output/f'predictions_{split}.csv',index=False)
        for mode, p in [('dynamic',pdyn),('baseline',pbase)]:
            cal = pd.DataFrame({'pred':p,'event':y})
            cal['decile'] = pd.qcut(cal.pred.rank(method='first'),10,labels=False)+1
            cal.groupby('decile').agg(rows=('event','size'),observed_rate=('event','mean'),
                                      predicted_rate=('pred','mean')).reset_index().to_csv(
                                          args.output/f'calibration_{split}_{mode}.csv',index=False)
        md,mb = report['splits'][split]['dynamic'],report['splits'][split]['origination_baseline']
        print(f'{split}: dynamic AUC={md["roc_auc"]:.4f}, Brier={md["brier"]:.5f}; '
              f'baseline AUC={mb["roc_auc"]:.4f}, Brier={mb["brier"]:.5f}',flush=True)
    importance = pd.DataFrame({'feature':FEATURES,'importance':model.get_feature_importance()})
    importance.sort_values('importance',ascending=False).to_csv(args.output/'feature_importance.csv',index=False)
    (args.output/'metrics.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('\nTop features:\n'+importance.sort_values('importance',ascending=False).head(12).to_string(index=False))
    print(f'\nSaved to {args.output.resolve()}')
    print('NOTE: row-level one-month metrics are conditional on remaining at risk. '
          'They are NOT PD12, and are not a deployment validation.')

if __name__=='__main__':
    main()
