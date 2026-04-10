"""
Tableau dashboard specification
===============================

View 1 - Portfolio Risk Overview:
KPI cards for total accounts, total exposure, overall default rate, and high-risk
account count. Add a bar chart of default rate by risk tier and a treemap of
credit exposure by tier. Use High Risk = red, Medium Risk = amber, Low Risk = green.

View 2 - Roll Rate Matrix:
Heatmap where rows = from_bucket, columns = to_bucket, color intensity =
pct_of_accounts. A dark diagonal means most accounts stay in their current
state; dark off-diagonal cells are warning signals.

View 3 - Account Risk Explorer:
Scatter plot of avg_utilization (x) vs risk_score (y), colored by risk_tier.
Filter by credit_limit band. Tooltip shows utilization, delinquency, on-time
months, credit limit, and default label.
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

    # These three files are normally produced by notebooks/modeling.ipynb.
    for name in ["risk_score_distribution.csv", "top_risk_accounts.csv", "feature_importance.csv"]:
        src = ROOT / "data" / "processed" / name
        if src.exists():
            pd.read_csv(src).to_csv(TABLEAU_DIR / name, index=False)
            print(f"Copied {name}")
        else:
            print(f"Skipped {name}; run notebooks/modeling.ipynb or scripts/build_project_outputs.py first.")


if __name__ == "__main__":
    main()
