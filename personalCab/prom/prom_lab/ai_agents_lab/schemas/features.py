"""Exact feature names used by the registered synthetic CatBoost artifacts."""
BASELINE_FEATURES = ['age_months','industry','entity_type','monthly_revenue','revenue_trend_12m',
                    'revenue_volatility','operating_margin','cash_buffer_months','dscr',
                    'debt_to_revenue','prior_overdue_30d','requested_amount','term_months',
                    'annual_rate','macro_stress','month_on_book']
DYNAMIC_FEATURES = BASELINE_FEATURES + ['current_monthly_revenue','current_operating_margin',
                    'current_cash_buffer_months','current_dscr','current_debt_to_revenue',
                    'current_revenue_trend_3m','current_macro_stress']
