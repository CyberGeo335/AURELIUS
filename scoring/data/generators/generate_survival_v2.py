"""AURELIUS synthetic financial trajectories + survival (research-only).
Usage: python generate_survival_v2.py --companies 10000 --output ml_data_v2_10000 --seed 42
Produces origination-only train/val/test, dynamic_train/val/test, financial_history,
and episodes. Dynamic rows contain only information observable at each month START.
No real credit calibration. Do not use for lending decisions.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

FEATURES = ['age_months','industry','entity_type','monthly_revenue','revenue_trend_12m','revenue_volatility','operating_margin','cash_buffer_months','dscr','debt_to_revenue','prior_overdue_30d','requested_amount','term_months','annual_rate','macro_stress','month_on_book']
DYNAMIC_FEATURES = FEATURES + ['current_monthly_revenue','current_operating_margin','current_cash_buffer_months','current_dscr','current_debt_to_revenue','current_revenue_trend_3m','current_macro_stress']
INDUSTRIES = np.array(['retail','services','manufacturing','construction','transport','agriculture'])
SEASON = np.array([.12,.07,.10,.19,.13,.30])
SENSITIVITY = np.array([.8,.7,1.0,1.35,1.1,1.2])

def logistic(z):
    return 1/(1+np.exp(-np.clip(z,-30,30)))

def macro_at(t):
    return .35*np.sin(t/11.0) + .8*((t>=74)&(t<90)) + .45*(t>=118)

def save(df, path, parquet):
    if parquet: df.to_parquet(path.with_suffix('.parquet'), index=False)
    else: df.to_csv(path.with_suffix('.csv'), index=False)

def generate(n, out, seed, batch):
    if n < 1 or batch < 1: raise ValueError('companies and batch must be positive')
    out.mkdir(parents=True,exist_ok=True)
    if list(out.glob('*_part_*.parquet')) or list(out.glob('*_part_*.csv')):
        raise FileExistsError(f'{out} already contains data chunks. Choose a NEW output directory.')
    try: import pyarrow  # noqa
    except ImportError: parquet=False
    else: parquet=True
    rng=np.random.default_rng(seed)
    counts={k:0 for k in ['train','val','test','dynamic_train','dynamic_val','dynamic_test','episodes','financial_history']}
    summaries={k:[0,0,0] for k in ['train','val','test']}
    for start in range(0,n,batch):
        m=min(batch,n-start)
        ids=np.arange(start+1,start+m+1,dtype=np.int64)
        cohort=rng.integers(0,84,m)
        split=np.where(cohort<59,'train',np.where(cohort<72,'val','test'))
        ind=rng.choice(len(INDUSTRIES),m,p=[.26,.24,.16,.13,.12,.09])
        entity=rng.choice(['IP','OOO'],m,p=[.44,.56])
        age=np.maximum(3,rng.gamma(3.2,30,m).astype(int))
        quality=rng.normal(0,.65,m)
        base_revenue=np.exp(rng.normal(np.log(2_200_000),.9,m))
        base_margin=np.clip(rng.normal(.16,.065,m)+.025*quality,-.12,.4)
        trend=np.clip(rng.normal(.025,.12,m)+.025*quality,-.35,.35)
        volatility=np.clip(rng.gamma(2,.065,m)*SENSITIVITY[ind],.025,.65)
        initial_buffer=np.clip(rng.gamma(1.7,.95,m)+.3*quality,.1,8)
        base_debt=np.clip(rng.lognormal(-1.15,.7,m),.03,3)
        orig_macro=macro_at(cohort)
        term=rng.choice([12,18,24,36,48,60],m,p=[.16,.13,.24,.24,.14,.09])
        rate=np.clip(.19+rng.normal(0,.025,m),.10,.36)
        amount=np.clip(base_revenue*rng.uniform(.4,2.5,m),50_000,30_000_000)
        # 24 months BEFORE origination. Monthly cash flows are internally coupled.
        cash=base_revenue*initial_buffer
        rev_prev=base_revenue.copy()
        past_revs=[]
        history=[]
        orig=None
        for k in range(-24,1):
            cal=cohort+k
            macro=macro_at(cal)
            season=SEASON[ind]*np.sin(2*np.pi*(cal%12)/12 + ind*.65)
            shock=rng.normal(0,1,m)*volatility
            revenue=np.maximum(20_000,base_revenue*np.exp(trend*k/12 + season - .13*macro*SENSITIVITY[ind] + shock))
            margin=np.clip(base_margin-.065*macro*SENSITIVITY[ind]+rng.normal(0,.035,m),-.28,.48)
            operating_cash=revenue*margin
            debt_service=np.maximum(1,base_revenue*base_debt*.16)
            cash=np.maximum(0,cash+operating_cash-debt_service + rng.normal(0,.025,m)*revenue)
            buffer=np.clip(cash/np.maximum(revenue,1),0,18)
            dscr=np.clip(np.maximum(0,operating_cash)/debt_service,.05,8)
            past_revs.append(revenue)
            if k<0:
                history.append(pd.DataFrame({'borrower_id':ids,'calendar_month_index':cal,'months_relative_to_origination':k,'revenue':revenue.round(2),'operating_cash_flow':operating_cash.round(2),'debt_service':debt_service.round(2),'cash_balance':cash.round(2),'macro_stress':macro.round(5)}))
            else:
                hist=np.stack(past_revs,axis=1)
                trend12=np.clip((hist[:,-1]/np.maximum(hist[:,-13],1))-1,-.9,3)
                vol12=np.clip(np.std(hist[:,-12:],axis=1)/np.maximum(np.mean(hist[:,-12:],axis=1),1),0,3)
                orig={'monthly_revenue':revenue.copy(),'revenue_trend_12m':trend12,'revenue_volatility':vol12,'operating_margin':margin.copy(),'cash_buffer_months':buffer.copy(),'dscr':dscr.copy(),'debt_to_revenue':base_debt.copy()}
        assert orig is not None
        prior_overdue=rng.binomial(1,logistic(-2.6+.75*(orig['dscr']<1)+.5*base_debt))
        # Keep origination features immutable throughout observation.
        fixed={'age_months':age,'industry':INDUSTRIES[ind],'entity_type':entity,
               **orig,'prior_overdue_30d':prior_overdue,'requested_amount':amount,
               'term_months':term,'annual_rate':rate,'macro_stress':orig_macro}
        # Post-origination observations. Dynamic covariates are LAGGED: at start of
        # month t, features use last completed month t-1. No outcome leakage.
        cash=orig['cash_buffer_months']*orig['monthly_revenue']
        last_rev=orig['monthly_revenue'].copy()
        last_margin=orig['operating_margin'].copy()
        last_buffer=orig['cash_buffer_months'].copy()
        last_dscr=orig['dscr'].copy()
        last_debt=base_debt.copy()
        recent=[x.copy() for x in past_revs[-3:]]
        censor_at=rng.integers(7,85,m)
        followup=np.minimum(np.minimum(term,156-cohort),censor_at)
        observed=np.zeros(m,dtype=int)
        event_month=np.zeros(m,dtype=int)
        active=np.ones(m,dtype=bool)
        origin_rows=[]; dynamic_rows=[]
        for month in range(1,int(followup.max())+1):
            eligible=active & (month<=followup)
            if not eligible.any(): break
            ix=np.flatnonzero(eligible)
            cal=cohort+month
            macro=macro_at(cal)
            last_macro=macro_at(cal-1)
            trend3=np.clip(last_rev/np.maximum(recent[0],1)-1,-.9,3)
            # Hazard is driven by observable prior-month finances PLUS hidden shocks.
            # A lower cash buffer and DSCR make default more likely; no deterministic labels.
            logit=(-5.3+.015*month+.95*np.maximum(1.1-last_dscr,0)
                   +.35*np.maximum(last_debt-.65,0)+.8*np.maximum(-trend3,0)
                   +.35*(last_buffer<.7)+.45*prior_overdue
                   +.42*macro+.25*macro*(ind==3)-.18*quality
                   +.42*(last_dscr<1)*(last_buffer<1)
                   +rng.normal(0,.13,m))
            events=rng.random(len(ix))<logistic(logit[ix])
            observed[ix]+=1
            event_month[ix[events]]=month
            active[ix[events]]=False
            common={'borrower_id':ids[ix],'episode_id':ids[ix],
                    'origination_month_index':cohort[ix],'month_on_book':np.full(len(ix),month),
                    **{k:v[ix] for k,v in fixed.items()},'default_event':events.astype(np.int8),'split':split[ix]}
            origin_rows.append(pd.DataFrame(common))
            dynamic_rows.append(pd.DataFrame({**common,
                'current_monthly_revenue':last_rev[ix],
                'current_operating_margin':last_margin[ix],
                'current_cash_buffer_months':last_buffer[ix],
                'current_dscr':last_dscr[ix],
                'current_debt_to_revenue':last_debt[ix],
                'current_revenue_trend_3m':trend3[ix],
                'current_macro_stress':last_macro[ix]}))
            # Generate completed month t AFTER recording the default label for t.
            # Thus financials from month t are not used to predict month-t default.
            season=SEASON[ind]*np.sin(2*np.pi*(cal%12)/12+ind*.65)
            rev=np.maximum(20_000,base_revenue*np.exp(trend*month/12+season-.13*macro*SENSITIVITY[ind]+rng.normal(0,1,m)*volatility))
            mar=np.clip(base_margin-.065*macro*SENSITIVITY[ind]+rng.normal(0,.035,m),-.28,.48)
            debt_service=np.maximum(1,base_revenue*base_debt*.16 + amount*rate/12)
            cash=np.maximum(0,cash+rev*mar-debt_service+rng.normal(0,.025,m)*rev)
            last_rev=rev
            last_margin=mar
            last_buffer=np.clip(cash/np.maximum(rev,1),0,18)
            last_dscr=np.clip(np.maximum(0,rev*mar)/debt_service,.05,8)
            last_debt=np.maximum(.01,base_debt+amount/np.maximum(rev,1)*np.maximum(0,1-month/term))
            recent=recent[1:]+[rev.copy()]
        if not origin_rows: continue
        odf=pd.concat(origin_rows,ignore_index=True)
        ddf=pd.concat(dynamic_rows,ignore_index=True)
        for name,frame in [('origin',odf),('dynamic',ddf)]:
            for s in ['train','val','test']:
                part=frame.loc[frame.split==s].drop(columns='split')
                if part.empty: continue
                key=s if name=='origin' else f'dynamic_{s}'
                save(part,out/f'{key}_part_{counts[key]:04d}',parquet)
                counts[key]+=1
                if name=='origin':
                    summaries[s][0]+=len(part);summaries[s][1]+=int(part.default_event.sum())
        for s in ['train','val','test']: summaries[s][2]+=int(np.count_nonzero(split==s))
        eps=pd.DataFrame({'borrower_id':ids,'episode_id':ids,'origination_month_index':cohort,
                          'split':split,'term_months':term,'observed_months':observed,
                          'event':(event_month>0).astype(np.int8),
                          'event_month':np.where(event_month>0,event_month,np.nan),
                          'censored':((event_month==0)&(observed<term)).astype(np.int8)})
        save(eps,out/f'episodes_part_{counts["episodes"]:04d}',parquet);counts['episodes']+=1
        hdf=pd.concat(history,ignore_index=True)
        save(hdf,out/f'financial_history_part_{counts["financial_history"]:04d}',parquet)
        counts['financial_history']+=1
        print(f'Simulated {start+m:,}/{n:,} borrowers',flush=True)
    pd.DataFrame([{'split':s,'rows':v[0],'events':v[1],'borrowers':v[2],
                   'event_rate_per_month_row':round(v[1]/v[0],5)} for s,v in summaries.items()]).to_csv(out/'summary.csv',index=False)
    (out/'features.txt').write_text('\n'.join(FEATURES)+'\n',encoding='utf-8')
    (out/'dynamic_features.txt').write_text('\n'.join(DYNAMIC_FEATURES)+'\n',encoding='utf-8')
    print(pd.read_csv(out/'summary.csv').to_string(index=False))
    print(f'Output: {out} ({"parquet" if parquet else "csv"} chunks)')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--companies',type=int,default=1000)
    p.add_argument('--output',type=Path,default=Path('ml_data_v2'))
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--batch',type=int,default=1000)
    a=p.parse_args()
    generate(a.companies,a.output,a.seed,a.batch)
