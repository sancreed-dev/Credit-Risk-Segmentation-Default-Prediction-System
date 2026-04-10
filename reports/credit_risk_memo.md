# Credit Risk Memo

**To:** Credit Risk Committee  
**From:** Analyst  
**Date:** 2026-05-26  
**Re:** Q4 Portfolio Risk Assessment

## Executive Summary

The portfolio contains 30,000 credit card accounts with $162,081,603 in credit exposure and an observed next-month default rate of 22.1%. The segmentation model separates Low Risk accounts at 11.1% default from High Risk accounts at 56.1% default, while the XGBoost model reaches PR-AUC 0.466 at an optimized cost threshold of 0.10. Recommend prioritizing Medium Risk outreach, High Risk limit review, and a monthly batch scoring process for analyst queue management.

## Portfolio Overview

| Metric | Value |
|---|---:|
| Total accounts | 30,000 |
| Total credit exposure | $162,081,603 |
| Overall default rate | 22.1% |

| tier_name | account_count | pct_of_portfolio | default_rate_pct | avg_credit_limit | total_exposure_usd | avg_utilization | avg_on_time_months |
| --- | --- | --- | --- | --- | --- | --- | --- |
| High Risk | 3939 | 13.1% | 56.1% | 94,327 TWD | $11,985,677 | 0.66 | 1.9 |
| Low Risk | 12211 | 40.7% | 11.1% | 222,534 TWD | $87,656,774 | 0.10 | 6.0 |
| Medium Risk | 13850 | 46.2% | 22.2% | 139,756 TWD | $62,439,151 | 0.53 | 5.3 |

## Key Risk Findings

1. **Finding:** Delinquency history is the clearest default separator. **Evidence:** High Risk accounts default at 56.1% versus 11.1% for Low Risk accounts, a 45.0 percentage-point spread from `sql/04_risk_tiers.sql`. **Business Implication:** Accounts with repeated or severe delinquency should be routed into a priority review queue before credit exposure increases.

2. **Finding:** Utilization pressure compounds behavioral risk. **Evidence:** High Risk accounts carry average utilization of 0.66, compared with 0.10 for Low Risk accounts, while representing 13.1% of the portfolio. **Business Implication:** A utilization-based early warning trigger near 80-85% would flag accounts before they become materially past due.

3. **Finding:** Model explanations are business-readable. **Evidence:** SHAP ranks the top three drivers as on_time_months, consecutive_delays, balance_volatility. **Business Implication:** Analysts can defend the queue logic using observable repayment and balance behaviors rather than treating the model as a black box.

## Roll Rate Analysis

From month 1 to month 2, 98.1% of Current accounts remain Current. That strong diagonal cell indicates that most healthy accounts stay healthy month over month, which is expected in a stable card portfolio.

Among accounts that start 30-DPD in month 1, 49.8% cure back to Current by month 2, while 45.3% roll forward to 60-DPD. This cure-versus-roll split is the velocity signal: accounts leaving 30-DPD in the wrong direction should be contacted quickly because deterioration accelerates once missed payments persist.

## Model Performance

The XGBoost classifier achieved PR-AUC 0.466 and F2 0.593. The cost matrix uses $150 for a missed defaulter and $10 for a false positive review; the optimal threshold is 0.10, reducing estimated test-period misclassification cost by $31,290 versus the default 0.50 threshold, or roughly $1,877,400 annualized to the full portfolio.

## Recommendations

| Recommendation | Action | Target Segment | Estimated Impact | Implementation Complexity |
|---|---|---|---|---|
| 1 | Proactive outreach before hard delinquency | Medium Risk accounts approaching 85% utilization or two delayed months | Reduce roll-forward into High Risk and protect $62,439,151 in Medium Risk exposure | Medium |
| 2 | Credit limit review | High Risk accounts with high utilization or 60-DPD+ behavior | Contain maximum loss exposure of $11,985,677 | Medium |
| 3 | Monthly batch scoring job | Full portfolio | Refresh analyst queue with risk scores, SHAP drivers, and tier changes every cycle | Low |

## Appendix

- `sql/01_schema.sql`
- `sql/02_ingest.sql`
- `sql/03_features.sql`
- `sql/04_risk_tiers.sql`
- `sql/05_roll_rates.sql`
- `notebooks/modeling.ipynb`
- Tableau dashboard CSVs in `tableau/`; dashboard link placeholder: add your published Tableau Public URL after building the workbook.
