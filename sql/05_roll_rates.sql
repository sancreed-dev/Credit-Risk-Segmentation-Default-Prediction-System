-- Phase 6: Roll-rate analysis for delinquency migration.

DROP VIEW IF EXISTS delinquency_buckets;

CREATE VIEW delinquency_buckets AS
SELECT
    customer_id,
    month_number,
    payment_status,
    CASE
        WHEN payment_status <= 0 THEN 'Current'
        WHEN payment_status = 1 THEN '30-DPD'
        WHEN payment_status = 2 THEN '60-DPD'
        WHEN payment_status = 3 THEN '90-DPD'
        WHEN payment_status >= 4 THEN '90+-DPD'
    END AS delinquency_bucket
FROM monthly_payments;

-- Roll-rate matrix across consecutive month pairs.
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
transition_counts AS (
    SELECT
        from_month,
        to_month,
        from_bucket,
        to_bucket,
        COUNT(*) AS account_count
    FROM transitions
    GROUP BY from_month, to_month, from_bucket, to_bucket
)
SELECT
    CONCAT(from_month, '->', to_month) AS month_pair,
    from_bucket,
    to_bucket,
    account_count,
    ROUND(account_count * 100.0 / SUM(account_count) OVER (PARTITION BY from_month, from_bucket), 2) AS pct_of_accounts
FROM transition_counts
ORDER BY from_month, from_bucket, to_bucket;

-- Forward roll summary from month 1 bucket to default by month 6 / next-month default.
SELECT
    db.delinquency_bucket AS month_1_bucket,
    COUNT(*) AS account_count,
    ROUND(AVG(o.default_next_month) * 100, 2) AS default_next_month_rate_pct
FROM delinquency_buckets db
JOIN outcomes o USING (customer_id)
WHERE db.month_number = 1
GROUP BY db.delinquency_bucket
ORDER BY default_next_month_rate_pct DESC;

-- PostgreSQL server-side export example. Adjust the path for your local machine.
-- \copy (
--     WITH transitions AS (
--         SELECT a.month_number AS from_month, b.month_number AS to_month,
--                a.delinquency_bucket AS from_bucket, b.delinquency_bucket AS to_bucket
--         FROM delinquency_buckets a
--         JOIN delinquency_buckets b ON b.customer_id = a.customer_id AND b.month_number = a.month_number + 1
--     )
--     SELECT CONCAT(from_month, '->', to_month) AS month_pair,
--            from_bucket, to_bucket,
--            COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY from_month, from_bucket) AS pct_of_accounts
--     FROM transitions
--     GROUP BY from_month, to_month, from_bucket, to_bucket
-- ) TO 'data/processed/roll_rate_matrix.csv' WITH CSV HEADER;
