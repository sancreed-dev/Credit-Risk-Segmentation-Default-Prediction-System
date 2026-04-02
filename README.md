# Credit Risk Segmentation & Default Prediction System

An analyst-grade credit risk project that converts six months of credit card repayment history into risk tiers, roll-rate diagnostics, cost-sensitive default predictions, and Tableau-ready portfolio monitoring exports. The project is framed for a financial analyst audience: the emphasis is not just prediction, but exposure management, delinquency migration, and defensible recommendations.

## Business Context

Credit risk segmentation helps a card issuer decide which accounts need proactive outreach, credit limit review, or routine monitoring. Roll rates measure how accounts migrate between delinquency states, such as Current to 30-DPD or 30-DPD to 60-DPD, and are a standard early-warning tool in card portfolios. The cost matrix treats missed defaulters as more expensive than false alerts, so the production threshold is chosen by expected business loss rather than model accuracy.

## Setup

1. Install PostgreSQL and create a database named `credit_risk`.
2. Create a Python environment and install dependencies:

```powershell
pip install -r requirements.txt
```

3. Put the UCI Default of Credit Card Clients Excel file at `data/raw/default_of_credit_card_clients.xls`.
4. Run the local output builder:

```powershell
python scripts/build_project_outputs.py
```

5. To run in PostgreSQL, export `data/raw/default_of_credit_card_clients.csv`, then execute:

```powershell
psql -d credit_risk -f sql/01_schema.sql
psql -d credit_risk -f sql/02_ingest.sql
psql -d credit_risk -f sql/03_features.sql
psql -d credit_risk -f sql/04_risk_tiers.sql
psql -d credit_risk -f sql/05_roll_rates.sql
```

6. Open `notebooks/modeling.ipynb` for the full modeling workflow.
7. Use the CSVs in `tableau/` to build the three-view dashboard.

## Key Findings

- Portfolio: 30,000 accounts, $162,081,603 estimated USD credit exposure, 22.1% observed next-month default rate.
- Risk tiers: Low Risk default rate 11.1%; High Risk default rate 56.1%.
- Model: XGBoost PR-AUC 0.466, F2 0.593, optimal threshold 0.10.
- Cost impact: estimated test-period cost reduction of $31,290 versus a 0.50 threshold, or $1,877,400 annualized to the full portfolio.
- Top SHAP drivers: on_time_months, consecutive_delays, balance_volatility.

## File Structure

```text
credit-risk-project/
+-- sql/                 PostgreSQL schema, ingest, features, tiers, roll rates
+-- notebooks/           Business-first modeling notebook
+-- reports/             Credit risk memo and generated figures
+-- data/raw/            UCI source file and exported CSV
+-- data/processed/      Modeled tables and scoring outputs
+-- tableau/             Clean dashboard-ready CSV exports
+-- scripts/             Reproducible local output builder
```

## Technologies Used

PostgreSQL, Python, pandas, scikit-learn, XGBoost, SHAP, imbalanced-learn, matplotlib, seaborn, SQLAlchemy, Tableau.

## CV Summary

- Designed a normalised PostgreSQL schema and engineered 8 behavioural risk features (utilisation trend, payment drift, roll rates, balance volatility) using CTEs and window functions across 30,000 credit card accounts
- Built a rule-based risk tier model separating default rates from 11.1% to 56.1% across tiers; performed roll-rate analysis identifying 45.3% of 30-DPD accounts roll to 60-DPD within 2 months
- Trained XGBoost classifier (PR-AUC 0.466, F2 0.593); optimised decision threshold via a $150/$10 FN/FP cost matrix, reducing estimated annual misclassification cost by $1,877,400 vs a 0.5 threshold baseline
- Produced a 4-section credit risk memo with portfolio overview, roll-rate analysis, and 3 prioritised recommendations; delivered findings in an interactive 3-view Tableau dashboard [link]
