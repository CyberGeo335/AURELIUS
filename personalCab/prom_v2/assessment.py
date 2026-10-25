"""Actual CatBoost attribution for one monthly logit, preserving M4 probability semantics."""
import math
from personalCab.prom.prom_lab.ai_agents_lab.services.assessment import AssessmentService
from personalCab.prom.prom_lab.ai_agents_lab.schemas.features import BASELINE_FEATURES, DYNAMIC_FEATURES


class ExplainableAssessmentService(AssessmentService):
    def __init__(self):
        self._models={}
        super().__init__(model_loader=self._load)

    def _load(self, path):
        if path not in self._models:
            from catboost import CatBoostClassifier
            model=CatBoostClassifier()
            model.load_model(str(path))
            self._models[path]=model
        return self._models[path]

    def assess(self, feature_input, **kwargs):
        result=super().assess(feature_input,**kwargs)
        if result['status']!='DEMO_ESTIMATE':return result
        try:
            result['explanation']=self._explain(result)
        except Exception:
            # An explanation failure is explicit and cannot replace a real inference.
            result['explanation']={'status':'UNAVAILABLE','reason':'SHAP_CALCULATION_UNAVAILABLE'}
        return result

    def _explain(self, result):
        from catboost import Pool
        bundle=result['feature_input']
        entry=next(m for m in self.registry['models'] if m['model_id']==result['model_id'])
        from personalCab.prom.prom_lab.ai_agents_lab.services.assessment import ROOT
        model=self._load((ROOT/entry['path']).resolve())
        names=BASELINE_FEATURES if bundle['kind']=='baseline' else DYNAMIC_FEATURES
        features=dict(bundle['features'])
        if bundle['kind']=='baseline':features['month_on_book']=1
        pool=Pool([[features[n] for n in names]],feature_names=names,cat_features=model.get_cat_feature_indices())
        values=[float(v) for v in model.get_feature_importance(pool,type='ShapValues',thread_count=2)[0]]
        raw=float(model.predict(pool,prediction_type='RawFormulaVal',thread_count=2)[0])
        if not all(math.isfinite(v) for v in [*values,raw]) or not math.isclose(sum(values),raw,rel_tol=1e-7,abs_tol=1e-7):
            raise ValueError('Attribution does not reconstruct the raw model output')
        return {'status':'AVAILABLE','method':'CATBOOST_SHAP','space':'RAW_MONTHLY_LOGIT',
                'month_on_book':features['month_on_book'],'base_value':values[-1],'raw_output':raw,
                'source_ref':bundle['source_ref'],'model_sha256':result['model_sha256'],
                'contributions':[{'feature':name,'contribution':value} for name,value in zip(names,values[:-1])],
                'note':'Вклады объясняют логит указанного месяца. Это не вклады в накопленную PD и не причинный эффект.'}
