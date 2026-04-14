# Tableau Build Instructions

Use this file to build a polished 5-tab Tableau dashboard for the **Credit Risk Segmentation & Default Prediction System**.

## Before You Start

Open Tableau Public or Tableau Desktop and connect to the CSV files inside:

```text
C:\Users\sanch\OneDrive\Documents\Credit Risk\credit-risk-project\tableau
```

Use these files:

- `executive_kpis.csv`
- `tier_summary_enhanced.csv`
- `risk_tier_feature_profile.csv`
- `monthly_delinquency_trend.csv`
- `roll_rate_matrix.csv`
- `roll_rate_sankey_edges.csv`
- `forward_roll_summary.csv`
- `utilization_band_analysis.csv`
- `risk_score_deciles.csv`
- `credit_limit_band_analysis.csv`
- `threshold_cost_analysis.csv`
- `account_action_queue.csv`
- `feature_importance_story.csv`

You do **not** need to physically join every file. In Tableau, it is cleaner to create one worksheet per CSV and assemble them into dashboards.

## Global Design Rules

Use a clean financial dashboard style:

- Background: white or very light grey
- Header text: dark charcoal
- High Risk: red `#C62828`
- Medium Risk: amber `#F9A825`
- Low Risk: green `#2E7D32`
- Avoid decorative gradients
- Keep chart titles business-focused, not technical
- Every tab should answer: “What decision should a credit risk analyst make?”

Suggested dashboard size:

```text
Desktop Browser: 1400 x 850
```

## Tab 1: Executive Overview

Purpose: show the portfolio health in 10 seconds.

### KPI Cards

Data source: `executive_kpis.csv`

Create 6 KPI cards:

- Total Accounts
- Total Exposure
- Overall Default Rate
- High Risk Accounts
- High-Low Default Spread
- Annualized Cost Reduction

Fields:

- Drag `metric` to Text or Label
- Drag `formatted_value` to Text
- Use `tooltip` in Tooltip

Best layout:

```text
[Total Accounts] [Total Exposure] [Default Rate]
[High Risk Accounts] [Risk Spread] [Cost Reduction]
```

### Default Rate by Tier

Data source: `tier_summary_enhanced.csv`

Chart type: bar chart

Fields:

- Columns: `risk_tier`
- Rows: `default_rate_pct`
- Color: `risk_tier`
- Label: `default_rate_pct`
- Sort by `tier_sort`

Title:

```text
Default Rate Separates Sharply by Risk Tier
```

Callout:

```text
High Risk accounts default at 56.1% vs 11.1% for Low Risk, creating a 45.0-point separation.
```

### Exposure by Tier

Data source: `tier_summary_enhanced.csv`

Chart type: treemap

Fields:

- Size: `total_exposure_usd`
- Color: `risk_tier`
- Label: `risk_tier`, `total_exposure_usd`

Title:

```text
Credit Exposure Concentration by Tier
```

## Tab 2: Portfolio Segmentation

Purpose: explain why customers fall into different risk groups.

### Feature Profile Heatmap

Data source: `risk_tier_feature_profile.csv`

Chart type: highlight table / heatmap

Fields:

- Rows: `feature`
- Columns: `risk_tier`
- Color: `average_value`
- Label: `average_value`

Recommended formatting:

- Use a sequential color scale
- Format values to 2 decimals

Title:

```text
Behavioral Feature Profile by Risk Tier
```

Insight:

```text
High Risk customers show fewer on-time months, higher consecutive delays, and higher repayment stress.
```

### Utilization Band Analysis

Data source: `utilization_band_analysis.csv`

Chart type: stacked bar

Fields:

- Columns: `utilization_band`
- Rows: `account_count`
- Color: `risk_tier`
- Sort by `band_sort`

Add tooltip:

- `default_rate_pct`
- `avg_risk_score`
- `total_exposure_usd`

Title:

```text
Risk Concentrates as Utilization Rises
```

### Credit Limit Band Risk

Data source: `credit_limit_band_analysis.csv`

Chart type: bar chart

Fields:

- Columns: `credit_limit_band`
- Rows: `expected_loss_usd`
- Color: `risk_tier`

Title:

```text
Expected Loss by Credit Limit Band
```

## Tab 3: Delinquency Migration

Purpose: show how accounts move from healthy to delinquent states.

### Roll Rate Matrix

Data source: `roll_rate_matrix.csv`

Chart type: heatmap

Fields:

- Rows: `from_bucket`
- Columns: `to_bucket`
- Color: `pct_of_accounts`
- Label: `pct_of_accounts`
- Filter: `month_pair`

Recommended filter:

Show `month_pair` as a dropdown so recruiters can switch between month transitions.

Title:

```text
Month-over-Month Delinquency Migration
```

Insight:

```text
Off-diagonal movement from 30-DPD to 60-DPD identifies accounts deteriorating before default.
```

### Monthly Delinquency Trend

Data source: `monthly_delinquency_trend.csv`

Chart type: stacked area or stacked bar

Fields:

- Columns: `month_number`
- Rows: `account_count`
- Color: `bucket`
- Filter: `risk_tier`

Title:

```text
Delinquency Composition Over Time
```

### Forward Roll Summary

Data source: `forward_roll_summary.csv`

Chart type: bar chart

Fields:

- Columns: `month_1_bucket`
- Rows: `default_rate_pct`
- Label: `default_rate_pct`

Title:

```text
Starting Delinquency Bucket Predicts Future Default
```

## Tab 4: Model & Cost

Purpose: prove the model is evaluated using business impact, not just accuracy.

### Threshold Cost Curve

Data source: `threshold_cost_analysis.csv`

Chart type: line chart

Fields:

- Columns: `threshold`
- Rows: `total_cost`
- Color or Shape: `is_optimal_threshold`

Add reference line:

```text
Threshold = 0.10
```

Title:

```text
Cost-Based Threshold Optimization
```

Insight:

```text
The optimal threshold is 0.10 because missing defaulters is much more expensive than extra reviews.
```

### Annualized Cost Saving

Data source: `threshold_cost_analysis.csv`

Chart type: bar or line chart

Fields:

- Columns: `threshold`
- Rows: `annualized_cost_saving_vs_050`

Title:

```text
Cost Saving vs 0.50 Baseline Threshold
```

### SHAP Feature Importance

Data source: `feature_importance_story.csv`

Chart type: horizontal bar

Fields:

- Rows: `feature_name`
- Columns: `mean_abs_shap_value`
- Sort: descending by `rank`
- Tooltip: `business_interpretation`

Title:

```text
Top Model Drivers Are Repayment Behavior Signals
```

### Risk Score Deciles

Data source: `risk_score_deciles.csv`

Chart type: bar chart

Fields:

- Columns: `risk_score_decile`
- Rows: `default_rate_pct`
- Label: `default_rate_pct`

Title:

```text
Default Rate Rises Across Risk Score Deciles
```

## Tab 5: Account Action Queue

Purpose: make the dashboard actionable for a credit risk analyst.

### Account Table

Data source: `account_action_queue.csv`

Chart type: text table

Fields:

- `customer_id`
- `risk_tier`
- `risk_score`
- `recommended_action`
- `action_reason`
- `action_priority`
- `credit_limit_usd`
- `expected_loss_usd`
- `avg_utilization`
- `max_delinquency`
- `consecutive_delays`

Filters:

- `risk_tier`
- `recommended_action`
- `action_priority`

Title:

```text
Prioritized Account Action Queue
```

### Risk Score vs Utilization Scatter

Data source: `account_action_queue.csv`

Chart type: scatter plot

Fields:

- Columns: `avg_utilization`
- Rows: `risk_score`
- Size: `credit_limit_usd`
- Color: `recommended_action`
- Detail: `customer_id`
- Tooltip: `customer_id`, `risk_tier`, `expected_loss_usd`, `action_reason`

Title:

```text
High-Utilization Accounts with Elevated Model Risk
```

Insight:

```text
Accounts in the upper-right quadrant combine high utilization with high predicted default risk.
```

## Recommended Dashboard Story Flow

Use this flow when presenting:

1. The portfolio has 30,000 accounts and $162.1M exposure.
2. Risk segmentation separates default rates by 45.0 points.
3. Roll-rate analysis shows which delinquency states deteriorate fastest.
4. The model threshold is optimized by cost, not accuracy.
5. The action queue turns the analysis into operational decisions.

## Final Recruiter Talking Points

Use these while demoing:

- “This is not just a prediction model; it is a credit risk decision dashboard.”
- “The dashboard connects exposure, default risk, roll-rate migration, and account-level action.”
- “I used cost-sensitive thresholding because false negatives are much more expensive in credit risk.”
- “The account queue is what makes the project operational rather than just analytical.”

## Common Mistakes To Avoid

- Do not create one overloaded dashboard with every chart on one page.
- Do not use random colors for risk tiers.
- Do not lead with model metrics before business KPIs.
- Do not show account IDs without recommended actions.
- Use `risk_score` or `default_risk_score` consistently for the model score.

## Files Checklist

Before publishing, confirm these tabs exist:

- Executive Overview
- Portfolio Segmentation
- Delinquency Migration
- Model & Cost
- Account Action Queue

Before recording a walkthrough, confirm these insights are visible:

- 45.0-point default spread
- $1.88M annualized cost reduction
- 56.1% High Risk default rate
- 11.1% Low Risk default rate
- 30-DPD roll-forward behavior
- Top model drivers from SHAP
- Prioritized account actions
