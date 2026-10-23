"""AURELIUS: synthetic discrete-time credit survival dataset.
Synthetic ONLY. No real-world calibration or lending use.
Usage: python generate_survival.py --companies 10000 --output ./ml_data --seed 42
Requires numpy, pandas; optional pyarrow for Parquet (otherwise CSV).
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

FEATURES = ["age_months", "industry", "entity_type", "monthly_revenue", "revenue_trend_12m", "revenue_volatility", "operating_margin", "cash_buffer_months", "dscr", "debt_to_revenue", "prior_overdue_30d", "requested_amount", "term_months", "annual_rate", "macro_stress", "month_on_book"]


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -35, 35)))


def simulate(n: int, seed: int, out: Path, batch: int = 5000):
    rng = np.random.default_rng(seed)
    out.mkdir(parents=True, exist_ok=True)
    industries = np.array(["retail", "services", "manufacturing", "construction", "transport", "agriculture"])
    # Write chunks directly to disk; avoid holding millions of rows in RAM.
    has_parquet = __import__("importlib").util.find_spec("pyarrow") is not None
    suffix = "parquet" if has_parquet else "csv"
    chunks = {"train": 0, "val": 0, "test": 0}
    episode_chunks = 0
    summary = {"train": [0, 0, 0], "val": [0, 0, 0], "test": [0, 0, 0]}
    # Each borrower has exactly one credit episode. Chronological origination cohorts
    # define the holdout; borrower IDs are disjoint across splits.
    for start in range(0, n, batch):
        m = min(batch, n - start)
        borrower = np.arange(start + 1, start + m + 1, dtype=np.int64)
        cohort = rng.integers(0, 84, m)  # origination month: 2012-01 ... 2018-12
        # Holdout by origination date; observation window ends 2024-12.
        split = np.where(cohort < 59, "train", np.where(cohort < 72, "val", "test"))
        industry_idx = rng.choice(len(industries), size=m, p=[.26, .24, .16, .13, .12, .09])
        entity = rng.choice(["IP", "OOO"], size=m, p=[.44, .56])
        age = np.maximum(3, rng.gamma(3.2, 30, m).astype(int))
        revenue = np.exp(rng.normal(np.log(2_200_000), .95, m))
        industry_cycle = np.array([.9, .8, 1.1, 1.35, 1.05, 1.25])[industry_idx]
        seasonality = np.array([.10, .06, .09, .18, .11, .28])[industry_idx]
        latent_management = rng.normal(0, .65, m)  # hidden from model
        trend = np.clip(rng.normal(.035, .19, m) + .035 * latent_management, -.60, .60)
        volatility = np.clip(rng.gamma(2.0, .095, m) * industry_cycle, .025, .95)
        margin = np.clip(rng.normal(.16, .095, m) + .025 * latent_management, -.25, .50)
        buffer = np.clip(rng.gamma(1.5, 1.2, m) + .35 * latent_management, 0, 12)
        debt_ratio = np.clip(rng.lognormal(-1.15, .85, m), .01, 5)
        dscr = np.clip(1.35 + 1.3 * margin + .24 * trend - .50 * debt_ratio + .15 * latent_management + rng.normal(0, .32, m), .15, 4.5)
        past_overdue = rng.binomial(1, sigmoid(-2.5 + 1.25 * (1.0 - dscr) + .8 * debt_ratio), m)
        amount = np.clip(revenue * rng.uniform(.4, 3.8, m), 50_000, 30_000_000)
        term = rng.choice([12, 18, 24, 36, 48, 60], size=m, p=[.16, .13, .24, .24, .14, .09])
        rate = np.clip(.19 + rng.normal(0, .035, m) + .012 * (dscr < 1), .10, .40)
        origination_macro = (.35 * np.sin(cohort / 11.0) +
                             .8 * ((cohort >= 74) & (cohort < 90)) +
                             .45 * (cohort >= 118)).astype(float)
        # One macro stress value for each calendar month, common to all companies.
        # Unseen shocks in later periods make temporal evaluation harder.
        max_followup = np.minimum(term, 156 - cohort)  # through 2024-12
        # Artificial right censoring, independent conditional on cohort and attributes.
        censor_at = rng.integers(7, 85, m)
        max_followup = np.minimum(max_followup, censor_at)
        active = np.ones(m, dtype=bool)
        event_month = np.zeros(m, dtype=int)
        observed = np.zeros(m, dtype=int)
        chunk_rows = []
        for month in range(1, int(max_followup.max()) + 1):
            eligible = active & (month <= max_followup)
            if not eligible.any():
                break
            ix = np.flatnonzero(eligible)
            calendar_month = cohort[ix] + month
            # Slow macro cycles + stress periods, all known at assessment month.
            macro = (.35 * np.sin(calendar_month / 11.0) +
                     .8 * ((calendar_month >= 74) & (calendar_month < 90)) +
                     .45 * (calendar_month >= 118)).astype(float)
            # Frozen origination features + month on book; no post-origination
            # financial updates are leaked into these features.
            # Underlying hazard has interactions, nonlinearities and unobserved risk.
            logit = (-5.05 + .025 * month + .9 * np.maximum(1.1 - dscr[ix], 0)
                     + .45 * np.maximum(debt_ratio[ix] - .7, 0)
                     + 1.1 * np.maximum(-trend[ix], 0)
                     + .60 * volatility[ix] + .55 * past_overdue[ix]
                     + .30 * (buffer[ix] < .6) + .55 * macro
                     + .42 * macro * (industry_idx[ix] == 3)
                     + .60 * (dscr[ix] < 1) * (buffer[ix] < 1)
                     - .14 * np.log1p(age[ix] / 12)
                     - .20 * latent_management[ix]
                     + .18 * np.sin((month + cohort[ix]) / 12) * seasonality[ix])
            h = sigmoid(logit)
            events = rng.random(len(ix)) < h
            observed[ix] += 1
            event_month[ix[events]] = month
            active[ix[events]] = False
            rows = pd.DataFrame({
                "borrower_id": borrower[ix], "episode_id": borrower[ix],
                "origination_month_index": cohort[ix], "month_on_book": month,
                "age_months": age[ix], "industry": industries[industry_idx[ix]],
                "entity_type": entity[ix], "monthly_revenue": revenue[ix].round(2),
                "revenue_trend_12m": trend[ix].round(5),
                "revenue_volatility": volatility[ix].round(5),
                "operating_margin": margin[ix].round(5),
                "cash_buffer_months": buffer[ix].round(4), "dscr": dscr[ix].round(4),
                "debt_to_revenue": debt_ratio[ix].round(4),
                "prior_overdue_30d": past_overdue[ix],
                "requested_amount": amount[ix].round(2),
                "term_months": term[ix], "annual_rate": rate[ix].round(5),
                "macro_stress": origination_macro[ix].round(5),
                "default_event": events.astype(np.int8),
                "split": split[ix]
            })
            chunk_rows.append(rows)
        frame = pd.concat(chunk_rows, ignore_index=True)
        for s in chunks:
            part = frame[frame.split == s].drop(columns="split")
            if not part.empty:
                dest = out / f"{s}_part_{chunks[s]:04d}.{suffix}"
                (part.to_parquet(dest, index=False) if has_parquet else part.to_csv(dest, index=False))
                chunks[s] += 1
                summary[s][0] += len(part)
                summary[s][1] += int(part.default_event.sum())
                summary[s][2] += int((split == s).sum())
        episode_frame = pd.DataFrame({
            "borrower_id": borrower, "episode_id": borrower,
            "origination_month_index": cohort, "split": split,
            "term_months": term, "observed_months": observed,
            "event": (event_month > 0).astype(np.int8),
            "event_month": np.where(event_month > 0, event_month, np.nan),
            "censored": ((event_month == 0) & (observed < term)).astype(np.int8)
        })
        epdest = out / f"episodes_part_{episode_chunks:04d}.{suffix}"
        (episode_frame.to_parquet(epdest, index=False) if has_parquet else episode_frame.to_csv(epdest, index=False))
        episode_chunks += 1
        print(f"Simulated {start+m:,}/{n:,} borrowers", flush=True)
    pd.DataFrame([{"split": s, "rows": v[0], "events": v[1], "borrowers": v[2],
                   "event_rate_per_month_row": round(v[1] / v[0], 5) if v[0] else 0}
                  for s, v in summary.items()]).to_csv(out / "summary.csv", index=False)
    (out / "features.txt").write_text("\n".join(FEATURES) + "\n", encoding="utf-8")
    print(pd.read_csv(out / "summary.csv").to_string(index=False))
    print(f"Output: {out} ({suffix} chunks; install pyarrow for Parquet)")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--companies", type=int, default=1000)
    p.add_argument("--output", type=Path, default=Path("ml_data"))
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--batch", type=int, default=5000)
    a = p.parse_args()
    simulate(a.companies, a.seed, a.output, a.batch)
