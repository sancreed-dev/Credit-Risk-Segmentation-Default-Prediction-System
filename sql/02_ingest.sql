-- Phase 3: Data ingestion from the UCI CSV.
-- Before running this script, export the Excel file to:
-- data/raw/default_of_credit_card_clients.csv
-- The scripts/build_project_outputs.py helper performs this conversion automatically.

DROP TABLE IF EXISTS staging_default_credit_card_clients;

CREATE TEMP TABLE staging_default_credit_card_clients (
    id INTEGER,
    limit_bal NUMERIC(12,2),
    sex SMALLINT,
    education SMALLINT,
    marriage SMALLINT,
    age INTEGER,
    pay_0 SMALLINT,
    pay_2 SMALLINT,
    pay_3 SMALLINT,
    pay_4 SMALLINT,
    pay_5 SMALLINT,
    pay_6 SMALLINT,
    bill_amt1 NUMERIC(12,2),
    bill_amt2 NUMERIC(12,2),
    bill_amt3 NUMERIC(12,2),
    bill_amt4 NUMERIC(12,2),
    bill_amt5 NUMERIC(12,2),
    bill_amt6 NUMERIC(12,2),
    pay_amt1 NUMERIC(12,2),
    pay_amt2 NUMERIC(12,2),
    pay_amt3 NUMERIC(12,2),
    pay_amt4 NUMERIC(12,2),
    pay_amt5 NUMERIC(12,2),
    pay_amt6 NUMERIC(12,2),
    default_payment_next_month SMALLINT
);

\copy staging_default_credit_card_clients FROM 'data/raw/default_of_credit_card_clients.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

INSERT INTO customers (customer_id, credit_limit, sex, education, marriage, age)
SELECT id, limit_bal, sex, education, marriage, age
FROM staging_default_credit_card_clients
ON CONFLICT (customer_id) DO UPDATE
SET credit_limit = EXCLUDED.credit_limit,
    sex = EXCLUDED.sex,
    education = EXCLUDED.education,
    marriage = EXCLUDED.marriage,
    age = EXCLUDED.age;

INSERT INTO outcomes (customer_id, default_next_month)
SELECT id, default_payment_next_month
FROM staging_default_credit_card_clients
ON CONFLICT (customer_id) DO UPDATE
SET default_next_month = EXCLUDED.default_next_month;

INSERT INTO monthly_payments (customer_id, month_number, bill_amount, pay_amount, payment_status)
SELECT id, month_number, bill_amount, pay_amount, payment_status
FROM staging_default_credit_card_clients
CROSS JOIN LATERAL (
    VALUES
        (1, bill_amt1, pay_amt1, pay_0),
        (2, bill_amt2, pay_amt2, pay_2),
        (3, bill_amt3, pay_amt3, pay_3),
        (4, bill_amt4, pay_amt4, pay_4),
        (5, bill_amt5, pay_amt5, pay_5),
        (6, bill_amt6, pay_amt6, pay_6)
) AS month_rows(month_number, bill_amount, pay_amount, payment_status)
ON CONFLICT (customer_id, month_number) DO UPDATE
SET bill_amount = EXCLUDED.bill_amount,
    pay_amount = EXCLUDED.pay_amount,
    payment_status = EXCLUDED.payment_status;

-- Data quality checks.
SELECT 'customers' AS table_name, COUNT(*) AS rows_loaded FROM customers
UNION ALL
SELECT 'monthly_payments', COUNT(*) FROM monthly_payments
UNION ALL
SELECT 'outcomes', COUNT(*) FROM outcomes;

SELECT
    SUM((customer_id IS NULL)::INTEGER) AS customer_id_nulls,
    SUM((credit_limit IS NULL)::INTEGER) AS credit_limit_nulls,
    SUM((sex IS NULL)::INTEGER) AS sex_nulls,
    SUM((education IS NULL)::INTEGER) AS education_nulls,
    SUM((marriage IS NULL)::INTEGER) AS marriage_nulls,
    SUM((age IS NULL)::INTEGER) AS age_nulls
FROM customers;

SELECT
    default_next_month,
    COUNT(*) AS account_count,
    ROUND(AVG(default_next_month) OVER () * 100, 2) AS portfolio_default_rate_pct
FROM outcomes
GROUP BY default_next_month
ORDER BY default_next_month;

SELECT
    COUNT(*) FILTER (WHERE education = 0) AS education_zero_records,
    COUNT(*) FILTER (WHERE marriage = 0) AS marriage_zero_records
FROM customers;
