# Tableau Dashboard Upgrade Plan

Build this as a polished 5-tab credit risk command center.

## Tab 1: Executive Overview
- KPI cards from `executive_kpis.csv`: Total Accounts, Total Exposure, Overall Default Rate, High Risk Accounts, High-Low Default Spread, Annualized Cost Reduction.
- Bar: default rate by tier using `tier_summary_enhanced.csv`.
- Treemap: total exposure by tier.
- Add one callout text: "High Risk accounts default at 56.1% vs 11.1% for Low Risk."

## Tab 2: Portfolio Segmentation
- Heatmap: `risk_tier_feature_profile.csv`, feature on rows and tier on columns.
- Stacked bar: account count by utilization band and tier from `utilization_band_analysis.csv`.
- Bar: expected loss by credit limit band from `credit_limit_band_analysis.csv`.

## Tab 3: Delinquency Migration
- Heatmap: from bucket to to bucket using `roll_rate_matrix.csv`.
- Flow/Sankey-style chart: `roll_rate_sankey_edges.csv`.
- Line/stacked area: monthly delinquency bucket trend from `monthly_delinquency_trend.csv`.
- Forward roll table: `forward_roll_summary.csv`.

## Tab 4: Model & Cost
- Line chart: threshold vs total cost from `threshold_cost_analysis.csv`.
- Highlight the optimal threshold at 0.10.
- Bar: SHAP feature importance from `feature_importance_story.csv`.
- Decile chart: default rate by risk score decile from `risk_score_deciles.csv`.

## Tab 5: Account Action Queue
- Table: `account_action_queue.csv`.
- Filters: risk tier, recommended action, credit limit band, utilization band.
- Scatter: risk score vs utilization, sized by exposure, colored by recommended action.
- Tooltip: customer id, risk tier, expected loss, delinquency, recommended action.

## Design Notes
- Use a white/charcoal background, not random gradients.
- Use exactly three risk colors: red High, amber Medium, green Low.
- Put the business insight beside every chart, not just the chart title.
- Recruiter should understand the story in 10 seconds: exposure, risk spread, migration, action.
