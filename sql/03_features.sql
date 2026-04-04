-- Phase 4: Feature engineering using CTEs and window functions.
-- This file is intentionally verbose and heavily commented for analyst review.
-- It demonstrates reusable SQL patterns for credit risk feature generation.
-- The UCI dataset contains six monthly observations per account.
-- Each CTE below isolates one behavioral signal.
-- The final INSERT joins the CTEs into credit_features.
-- Validation queries at the bottom support model governance and reporting.

TRUNCATE TABLE credit_features;

WITH
-- 001 Base monthly panel with credit limit attached.
monthly_base AS (
    SELECT
        mp.customer_id,
        mp.month_number,
        c.credit_limit,
        mp.bill_amount,
        mp.pay_amount,
        mp.payment_status,
        mp.bill_amount / NULLIF(c.credit_limit, 0) AS utilization
    FROM monthly_payments mp
    JOIN customers c
      ON c.customer_id = mp.customer_id
),
-- 002 Utilization average.
-- 003 This is the primary exposure pressure signal.
-- 004 A customer near the limit has less buffer.
-- 005 NULLIF protects against zero limit anomalies.
utilization_calc AS (
    SELECT
        customer_id,
        AVG(utilization) AS avg_utilization
    FROM monthly_base
    GROUP BY customer_id
),
-- 006 Utilization trend inputs.
-- 007 Linear slope is computed manually for portability.
-- 008 Positive slope means rising utilization.
-- 009 Negative slope means deleveraging.
-- 010 Six months provide a compact trend signal.
utilization_trend_inputs AS (
    SELECT
        customer_id,
        month_number::NUMERIC AS x,
        utilization::NUMERIC AS y
    FROM monthly_base
    WHERE utilization IS NOT NULL
),
-- 011 Utilization trend.
-- 012 Slope formula: cov(x,y) / var(x).
-- 013 Equivalent to a simple one-variable regression coefficient.
-- 014 Uses SUM aggregates to avoid dialect surprises.
-- 015 A denominator guard avoids divide-by-zero.
utilization_trend AS (
    SELECT
        customer_id,
        (
            COUNT(*) * SUM(x * y) - SUM(x) * SUM(y)
        ) / NULLIF(
            COUNT(*) * SUM(x * x) - SUM(x) * SUM(x),
            0
        ) AS utilization_trend
    FROM utilization_trend_inputs
    GROUP BY customer_id
),
-- 016 Payment behaviour.
-- 017 On-time months counts all non-delinquent statuses.
-- 018 Max delinquency captures worst observed arrears.
-- 019 Drift captures volatility in payment behavior.
-- 020 Higher drift implies less stable repayment.
payment_behaviour AS (
    SELECT
        customer_id,
        COUNT(*) FILTER (WHERE payment_status <= 0)::SMALLINT AS on_time_months,
        MAX(payment_status)::SMALLINT AS max_delinquency,
        (MAX(payment_status) - MIN(payment_status))::SMALLINT AS delinquency_drift
    FROM monthly_base
    GROUP BY customer_id
),
-- 021 Delinquent months only.
-- 022 Gaps-and-islands starts by filtering delayed observations.
-- 023 Any status >= 1 is treated as a delay.
-- 024 The month_number establishes ordering.
-- 025 Each account has at most six rows.
delayed_months AS (
    SELECT
        customer_id,
        month_number,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY month_number
        ) AS delayed_sequence
    FROM monthly_base
    WHERE payment_status >= 1
),
-- 026 Island keys.
-- 027 Consecutive delayed months share month_number - row_number.
-- 028 This is the standard gaps-and-islands pattern.
-- 029 It is robust to missing non-delayed months.
-- 030 It avoids procedural loops.
delay_islands AS (
    SELECT
        customer_id,
        month_number,
        month_number - delayed_sequence AS island_key
    FROM delayed_months
),
-- 031 Consecutive delay calculation.
-- 032 Count rows in each island.
-- 033 Take the maximum streak per account.
-- 034 Accounts with no delay are added later as zero.
-- 035 This signal captures persistence of arrears.
consecutive_delay_calc AS (
    SELECT
        customer_id,
        MAX(streak_length)::SMALLINT AS consecutive_delays
    FROM (
        SELECT
            customer_id,
            island_key,
            COUNT(*) AS streak_length
        FROM delay_islands
        GROUP BY customer_id, island_key
    ) streaks
    GROUP BY customer_id
),
-- 036 Payment ratio detail.
-- 037 pay_amount / bill_amount is undefined for zero bills.
-- 038 Zero or negative bill months are excluded from the ratio.
-- 039 This treats no-consumption months as neutral.
-- 040 Higher average payment ratio is lower risk.
payment_ratio_calc AS (
    SELECT
        customer_id,
        AVG(pay_amount / NULLIF(bill_amount, 0)) AS payment_ratio
    FROM monthly_base
    WHERE bill_amount > 0
    GROUP BY customer_id
),
-- 041 Balance volatility.
-- 042 Standard deviation of statement balances.
-- 043 High volatility may indicate spending shocks.
-- 044 Low volatility with high utilization may indicate chronic leverage.
-- 045 This complements utilization level and trend.
balance_volatility_calc AS (
    SELECT
        customer_id,
        STDDEV_SAMP(bill_amount) AS balance_volatility
    FROM monthly_base
    GROUP BY customer_id
),
-- 046 Join guard.
-- 047 We anchor on customers so every account receives a feature row.
-- 048 Missing payment ratios become zero.
-- 049 Missing streaks become zero.
-- 050 Numeric fields are rounded for stable reporting.
feature_join AS (
    SELECT
        c.customer_id,
        ROUND(COALESCE(uc.avg_utilization, 0), 4) AS avg_utilization,
        ROUND(COALESCE(ut.utilization_trend, 0), 4) AS utilization_trend,
        COALESCE(pb.on_time_months, 0)::SMALLINT AS on_time_months,
        COALESCE(pb.max_delinquency, 0)::SMALLINT AS max_delinquency,
        COALESCE(pb.delinquency_drift, 0)::SMALLINT AS delinquency_drift,
        COALESCE(cdc.consecutive_delays, 0)::SMALLINT AS consecutive_delays,
        ROUND(COALESCE(prc.payment_ratio, 0), 4) AS payment_ratio,
        ROUND(COALESCE(bvc.balance_volatility, 0), 2) AS balance_volatility
    FROM customers c
    LEFT JOIN utilization_calc uc ON uc.customer_id = c.customer_id
    LEFT JOIN utilization_trend ut ON ut.customer_id = c.customer_id
    LEFT JOIN payment_behaviour pb ON pb.customer_id = c.customer_id
    LEFT JOIN consecutive_delay_calc cdc ON cdc.customer_id = c.customer_id
    LEFT JOIN payment_ratio_calc prc ON prc.customer_id = c.customer_id
    LEFT JOIN balance_volatility_calc bvc ON bvc.customer_id = c.customer_id
)
INSERT INTO credit_features (
    customer_id,
    avg_utilization,
    utilization_trend,
    on_time_months,
    max_delinquency,
    delinquency_drift,
    consecutive_delays,
    payment_ratio,
    balance_volatility
)
SELECT
    customer_id,
    avg_utilization,
    utilization_trend,
    on_time_months,
    max_delinquency,
    delinquency_drift,
    consecutive_delays,
    payment_ratio,
    balance_volatility
FROM feature_join;

-- 051 Validation query 1: utilization distribution in 10% buckets.
SELECT
    WIDTH_BUCKET(avg_utilization, 0, 1, 10) AS utilization_bucket,
    COUNT(*) AS account_count,
    ROUND(AVG(o.default_next_month) * 100, 2) AS default_rate_pct
FROM credit_features cf
JOIN outcomes o USING (customer_id)
GROUP BY utilization_bucket
ORDER BY utilization_bucket;

-- 052 Validation query 2: default rate by on-time month bucket.
SELECT
    CASE
        WHEN on_time_months BETWEEN 0 AND 1 THEN '0-1'
        WHEN on_time_months BETWEEN 2 AND 3 THEN '2-3'
        WHEN on_time_months BETWEEN 4 AND 5 THEN '4-5'
        WHEN on_time_months = 6 THEN '6'
    END AS on_time_month_bucket,
    COUNT(*) AS account_count,
    ROUND(AVG(o.default_next_month) * 100, 2) AS default_rate_pct
FROM credit_features cf
JOIN outcomes o USING (customer_id)
GROUP BY on_time_month_bucket
ORDER BY on_time_month_bucket;

-- 053 Validation query 3: default rate by max delinquency level.
SELECT
    max_delinquency,
    COUNT(*) AS account_count,
    ROUND(AVG(o.default_next_month) * 100, 2) AS default_rate_pct
FROM credit_features cf
JOIN outcomes o USING (customer_id)
GROUP BY max_delinquency
ORDER BY max_delinquency;

-- 054 Validation query 4: pairwise feature correlation approximation.
WITH feature_values AS (
    SELECT customer_id, 'avg_utilization' AS feature_name, avg_utilization::NUMERIC AS feature_value FROM credit_features
    UNION ALL SELECT customer_id, 'utilization_trend', utilization_trend::NUMERIC FROM credit_features
    UNION ALL SELECT customer_id, 'on_time_months', on_time_months::NUMERIC FROM credit_features
    UNION ALL SELECT customer_id, 'max_delinquency', max_delinquency::NUMERIC FROM credit_features
    UNION ALL SELECT customer_id, 'delinquency_drift', delinquency_drift::NUMERIC FROM credit_features
    UNION ALL SELECT customer_id, 'consecutive_delays', consecutive_delays::NUMERIC FROM credit_features
    UNION ALL SELECT customer_id, 'payment_ratio', payment_ratio::NUMERIC FROM credit_features
    UNION ALL SELECT customer_id, 'balance_volatility', balance_volatility::NUMERIC FROM credit_features
)
SELECT
    a.feature_name AS feature_a,
    b.feature_name AS feature_b,
    ROUND(CORR(a.feature_value, b.feature_value)::NUMERIC, 4) AS correlation
FROM feature_values a
JOIN feature_values b
  ON a.customer_id = b.customer_id
 AND a.feature_name < b.feature_name
GROUP BY a.feature_name, b.feature_name
ORDER BY feature_a, feature_b;

-- 055 Validation query 5: top 10 riskiest customers by composite heuristic score.
SELECT
    customer_id,
    ROUND(
        (avg_utilization * 0.4)
        + (max_delinquency * 0.3)
        + (delinquency_drift * 0.3),
        4
    ) AS composite_risk_score,
    avg_utilization,
    max_delinquency,
    delinquency_drift
FROM credit_features
ORDER BY composite_risk_score DESC
LIMIT 10;
