-- Phase 2: PostgreSQL schema for Credit Risk Segmentation & Default Prediction System

DROP TABLE IF EXISTS risk_tiers CASCADE;
DROP TABLE IF EXISTS credit_features CASCADE;
DROP TABLE IF EXISTS monthly_payments CASCADE;
DROP TABLE IF EXISTS outcomes CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    credit_limit NUMERIC(12,2) NOT NULL CHECK (credit_limit >= 0),
    sex SMALLINT CHECK (sex IN (1, 2)),
    education SMALLINT CHECK (education BETWEEN 0 AND 6),
    marriage SMALLINT CHECK (marriage BETWEEN 0 AND 3),
    age INTEGER CHECK (age BETWEEN 18 AND 100),
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE customers IS 'One row per credit card account holder in the UCI portfolio.';
COMMENT ON COLUMN customers.customer_id IS 'Unique customer/account identifier from the UCI dataset.';
COMMENT ON COLUMN customers.credit_limit IS 'Approved credit limit in TWD; primary exposure measure.';
COMMENT ON COLUMN customers.sex IS 'Customer sex: 1=male, 2=female.';
COMMENT ON COLUMN customers.education IS 'Education code: 1=graduate school, 2=university, 3=high school, 4=others; 0/5/6 are undocumented source codes.';
COMMENT ON COLUMN customers.marriage IS 'Marital status: 1=married, 2=single, 3=others; 0 is undocumented.';
COMMENT ON COLUMN customers.age IS 'Customer age in years.';
COMMENT ON COLUMN customers.created_at IS 'Timestamp when the row was loaded into the analytical schema.';

CREATE TABLE monthly_payments (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    month_number SMALLINT NOT NULL CHECK (month_number BETWEEN 1 AND 6),
    bill_amount NUMERIC(12,2),
    pay_amount NUMERIC(12,2),
    payment_status SMALLINT CHECK (payment_status BETWEEN -2 AND 9),
    UNIQUE (customer_id, month_number)
);

COMMENT ON TABLE monthly_payments IS 'One row per customer per observed month; month 1 is September 2005 and month 6 is April 2005 in reverse statement order.';
COMMENT ON COLUMN monthly_payments.customer_id IS 'Customer/account identifier linked to customers.';
COMMENT ON COLUMN monthly_payments.month_number IS 'Statement month index, 1 through 6.';
COMMENT ON COLUMN monthly_payments.bill_amount IS 'Monthly statement balance in TWD.';
COMMENT ON COLUMN monthly_payments.pay_amount IS 'Actual payment made in TWD.';
COMMENT ON COLUMN monthly_payments.payment_status IS 'Repayment status: -2=no consumption, -1=paid in full, 0=revolving credit, 1=one month delay, up to 9.';

CREATE TABLE credit_features (
    customer_id INTEGER PRIMARY KEY REFERENCES customers(customer_id) ON DELETE CASCADE,
    avg_utilization NUMERIC(8,4),
    utilization_trend NUMERIC(8,4),
    on_time_months SMALLINT,
    max_delinquency SMALLINT,
    delinquency_drift SMALLINT,
    consecutive_delays SMALLINT,
    payment_ratio NUMERIC(8,4),
    balance_volatility NUMERIC(12,2)
);

COMMENT ON TABLE credit_features IS 'Engineered behavioral risk features computed from six months of billing and repayment history.';
COMMENT ON COLUMN credit_features.avg_utilization IS 'Average bill-to-limit ratio across six months; high values indicate limited remaining credit capacity.';
COMMENT ON COLUMN credit_features.utilization_trend IS 'Linear slope of utilization over time; positive values imply rising utilization and worsening risk.';
COMMENT ON COLUMN credit_features.on_time_months IS 'Number of months with payment_status <= 0.';
COMMENT ON COLUMN credit_features.max_delinquency IS 'Worst repayment status observed across the six months.';
COMMENT ON COLUMN credit_features.delinquency_drift IS 'Difference between worst and best payment status; captures repayment volatility.';
COMMENT ON COLUMN credit_features.consecutive_delays IS 'Longest consecutive streak with payment_status >= 1.';
COMMENT ON COLUMN credit_features.payment_ratio IS 'Average payment-to-bill ratio; higher values indicate stronger repayment behavior.';
COMMENT ON COLUMN credit_features.balance_volatility IS 'Standard deviation of monthly bill amounts; high values can signal unstable spending or income shocks.';

CREATE TABLE outcomes (
    customer_id INTEGER PRIMARY KEY REFERENCES customers(customer_id) ON DELETE CASCADE,
    default_next_month SMALLINT NOT NULL CHECK (default_next_month IN (0, 1))
);

COMMENT ON TABLE outcomes IS 'Observed target variable for next-month default.';
COMMENT ON COLUMN outcomes.default_next_month IS '1 if the customer defaulted next month, 0 otherwise.';

CREATE INDEX idx_monthly_payments_customer_month ON monthly_payments(customer_id, month_number);
CREATE INDEX idx_monthly_payments_status ON monthly_payments(payment_status);
CREATE INDEX idx_outcomes_default ON outcomes(default_next_month);
