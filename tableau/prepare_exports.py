"""
Tableau dashboard specification
===============================

This script is the PostgreSQL-backed export path. For the local CSV-backed path,
run scripts/enhance_tableau_exports.py after scripts/build_project_outputs.py.

Build the final dashboard as a 5-tab credit risk command center:

Tab 1 - Executive Overview:
KPI cards for total accounts, total exposure, overall default rate, high-risk
accounts, High-Low default spread, and annualized cost reduction. Add a bar chart
of default rate by tier and a treemap of exposure by tier.

Tab 2 - Portfolio Segmentation:
Feature profile heatmap by risk tier, stacked utilization-band distribution, and
expected loss by credit-limit band.

Tab 3 - Delinquency Migration:
Roll-rate heatmap, month-over-month delinquency trend, and forward roll summary.

Tab 4 - Model & Cost:
Threshold cost curve, annualized cost saving versus 0.50 threshold, SHAP feature
importance, and risk-score decile validation.

Tab 5 - Account Action Queue:
Prioritized account table and scatter plot of utilization versus risk score,
colored by recommended action and sized by exposure.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
TABLEAU_DIR = ROOT / "tableau"


def get_engine():
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "credit_risk")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "yourpassword")
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}")


def export_query(engine, filename: str, sql: str) -> None:
    df = pd.read_sql_query(text(sql), engine)
    df.to_csv(TABLEAU_DIR / filename, index=False)
    print(f"Exported {filename}: {len(df):,} rows")


def main() -> None:
    engine = get_engine()
    TABLEAU_DIR.mkdir(parents=True, exist_ok=True)

    export_query(
        engine,
        "portfolio_overview.csv",
        """
        SELECT
            rt.risk_tier AS tier_name,
            COUNT(*) AS account_count,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct_of_portfolio,
            ROUND(AVG(o.default_next_month) * 100, 2) AS default_rate_pct,
            ROUND(AVG(c.credit_limit / 31.0), 2) AS avg_credit_limit,
            ROUND(SUM(c.credit_limit / 31.0), 2) AS total_exposure_usd,
            ROUND(AVG(cf.avg_utilization), 4) AS avg_utilization,
            ROUND(AVG(cf.on_time_months), 2) AS avg_on_time_months
        FROM risk_tiers rt
        JOIN customers c USING (customer_id)
        JOIN outcomes o USING (customer_id)
        JOIN credit_features cf USING (customer_id)
        GROUP BY rt.risk_tier
        ORDER BY default_rate_pct DESC
        """,
    )

    export_query(
        engine,
        "roll_rate_matrix.csv",
        """
        WITH transitions AS (
            SELECT
                a.customer_id,
                a.month_number AS from_month,
                b.month_number AS to_month,
                a.delinquency_bucket AS from_bucket,
                b.delinquency_bucket AS to_bucket
            FROM delinquency_buckets a
            JOIN delinquency_buckets b
              ON b.customer_id = a.customer_id
             AND b.month_number = a.month_number + 1
        ),
        counts AS (
            SELECT from_month, to_month, from_bucket, to_bucket, COUNT(*) AS account_count
            FROM transitions
            GROUP BY from_month, to_month, from_bucket, to_bucket
        )
        SELECT
            from_bucket,
            to_bucket,
            ROUND(account_count * 100.0 / SUM(account_count) OVER (PARTITION BY from_month, from_bucket), 2) AS pct_of_accounts,
            CONCAT(from_month, '->', to_month) AS month_pair
        FROM counts
        ORDER BY from_month, from_bucket, to_bucket
        """,
    )

    # These files are normally produced by scripts/build_project_outputs.py and
    # scripts/enhance_tableau_exports.py. Copy them into tableau/ when present.
    generated_exports = [
        "risk_score_distribution.csv",
        "top_risk_accounts.csv",
        "feature_importance.csv",
        "executive_kpis.csv",
        "tier_summary_enhanced.csv",
        "risk_tier_feature_profile.csv",
        "monthly_delinquency_trend.csv",
        "roll_rate_sankey_edges.csv",
        "forward_roll_summary.csv",
        "utilization_band_analysis.csv",
        "risk_score_deciles.csv",
        "credit_limit_band_analysis.csv",
        "demographic_risk_mix.csv",
        "threshold_cost_analysis.csv",
        "account_action_queue.csv",
        "feature_importance_story.csv",
    ]
    for name in generated_exports:
        src = ROOT / "data" / "processed" / name
        if src.exists():
            df = pd.read_csv(src)
            if name == "top_risk_accounts.csv":
                if "default_risk_score" not in df.columns and "risk_score" in df.columns:
                    df.insert(df.columns.get_loc("risk_score") + 1, "default_risk_score", df["risk_score"])
            df.to_csv(TABLEAU_DIR / name, index=False)
            print(f"Copied {name}")
            continue
        src = ROOT / "tableau" / name
        if src.exists():
            print(f"Already available {name}")
        else:
            print(f"Skipped {name}; run scripts/build_project_outputs.py and scripts/enhance_tableau_exports.py first.")


if __name__ == "__main__":
    main()
