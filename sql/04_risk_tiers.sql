-- Phase 5: Rule-based risk tier model.

DROP TABLE IF EXISTS risk_tiers;

CREATE TABLE risk_tiers (
    customer_id INTEGER PRIMARY KEY REFERENCES customers(customer_id) ON DELETE CASCADE,
    risk_tier TEXT NOT NULL CHECK (risk_tier IN ('High Risk', 'Medium Risk', 'Low Risk')),
    tier_reason TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE risk_tiers IS 'Three-tier business segmentation model for portfolio monitoring and analyst queueing.';

INSERT INTO risk_tiers (customer_id, risk_tier, tier_reason)
SELECT
    customer_id,
    CASE
        -- High Risk: high utilization or repeated/severe delinquency indicates limited liquidity and elevated charge-off odds.
        WHEN avg_utilization > 1.00
          OR max_delinquency >= 3
          OR consecutive_delays >= 3
        THEN 'High Risk'
        -- Low Risk: low utilization, nearly all months current, and no recorded delinquency implies a stable revolver/transactor profile.
        WHEN avg_utilization < 0.40
          AND on_time_months >= 5
          AND max_delinquency <= 0
        THEN 'Low Risk'
        -- Medium Risk: remaining accounts need monitoring but do not yet show hard high-risk triggers.
        ELSE 'Medium Risk'
    END AS risk_tier,
    CASE
        WHEN avg_utilization > 1.00 THEN 'Average utilization above 100%'
        WHEN max_delinquency >= 3 THEN 'At least 90-DPD observed'
        WHEN consecutive_delays >= 3 THEN 'Three or more consecutive delayed months'
        WHEN avg_utilization < 0.40 AND on_time_months >= 5 AND max_delinquency <= 0 THEN 'Low utilization with strong on-time history'
        ELSE 'Intermediate behavioral risk'
    END AS tier_reason
FROM credit_features;

-- Validation block: these outputs feed the memo and README.
SELECT
    risk_tier,
    COUNT(*) AS account_count,
    ROUND(AVG(default_next_month) * 100, 2) AS default_rate_pct
FROM risk_tiers
JOIN outcomes USING (customer_id)
GROUP BY risk_tier
ORDER BY default_rate_pct DESC;

SELECT
    rt.risk_tier,
    ROUND(AVG(c.credit_limit), 2) AS avg_credit_limit,
    ROUND(SUM(c.credit_limit), 2) AS total_credit_exposure_twd
FROM risk_tiers rt
JOIN customers c USING (customer_id)
GROUP BY rt.risk_tier
ORDER BY total_credit_exposure_twd DESC;

SELECT
    ROUND(SUM(c.credit_limit), 2) AS high_risk_max_possible_loss_twd
FROM risk_tiers rt
JOIN customers c USING (customer_id)
WHERE rt.risk_tier = 'High Risk';

SELECT
    risk_tier,
    COUNT(*) AS account_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct_of_portfolio
FROM risk_tiers
GROUP BY risk_tier
ORDER BY pct_of_portfolio DESC;

SELECT
    rt.risk_tier,
    ROUND(AVG(c.age), 2) AS avg_age,
    ROUND(AVG((c.sex = 2)::INTEGER) * 100, 2) AS pct_female,
    ROUND(AVG((c.education = 1)::INTEGER) * 100, 2) AS pct_graduate_educated
FROM risk_tiers rt
JOIN customers c USING (customer_id)
GROUP BY rt.risk_tier
ORDER BY rt.risk_tier;
