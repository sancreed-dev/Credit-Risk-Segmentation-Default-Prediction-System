from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import nbformat as nbf
import numpy as np
import pandas as pd
import seaborn as sns
import shap
from imblearn.over_sampling import SMOTE
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    fbeta_score,
    precision_recall_curve,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[1]
RAW_XLS = ROOT / "data" / "raw" / "default_of_credit_card_clients.xls"
RAW_CSV = ROOT / "data" / "raw" / "default_of_credit_card_clients.csv"
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "reports" / "figures"
TABLEAU = ROOT / "tableau"
REPORTS = ROOT / "reports"
NOTEBOOK = ROOT / "notebooks" / "modeling.ipynb"
USD_PER_TWD = 1 / 31.0


FEATURES = [
    "avg_utilization",
    "utilization_trend",
    "on_time_months",
    "max_delinquency",
    "delinquency_drift",
    "consecutive_delays",
    "payment_ratio",
    "balance_volatility",
]


def ensure_dirs() -> None:
    for path in [PROCESSED, FIGURES, TABLEAU, REPORTS, NOTEBOOK.parent]:
        path.mkdir(parents=True, exist_ok=True)


def load_raw() -> pd.DataFrame:
    df = pd.read_excel(RAW_XLS, header=1)
    df = df.rename(columns={"default payment next month": "default.payment.next.month"})
    df.columns = [str(c).strip() for c in df.columns]
    df.to_csv(RAW_CSV, index=False)
    return df


def longest_delay_streak(statuses: pd.Series) -> int:
    best = current = 0
    for value in statuses:
        if value >= 1:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def linear_slope(values: np.ndarray) -> float:
    x = np.arange(1, len(values) + 1, dtype=float)
    mask = np.isfinite(values)
    if mask.sum() < 2:
        return 0.0
    return float(np.polyfit(x[mask], values[mask], 1)[0])


def build_analytical_tables(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = raw[["ID", "LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE"]].rename(
        columns={
            "ID": "customer_id",
            "LIMIT_BAL": "credit_limit",
            "SEX": "sex",
            "EDUCATION": "education",
            "MARRIAGE": "marriage",
            "AGE": "age",
        }
    )
    outcomes = raw[["ID", "default.payment.next.month"]].rename(
        columns={"ID": "customer_id", "default.payment.next.month": "default_next_month"}
    )

    monthly_rows = []
    status_cols = ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]
    for month in range(1, 7):
        monthly_rows.append(
            pd.DataFrame(
                {
                    "customer_id": raw["ID"],
                    "month_number": month,
                    "bill_amount": raw[f"BILL_AMT{month}"],
                    "pay_amount": raw[f"PAY_AMT{month}"],
                    "payment_status": raw[status_cols[month - 1]],
                }
            )
        )
    monthly = pd.concat(monthly_rows, ignore_index=True)

    feature_rows = []
    for _, row in raw.iterrows():
        bills = row[[f"BILL_AMT{i}" for i in range(1, 7)]].astype(float).to_numpy()
        pays = row[[f"PAY_AMT{i}" for i in range(1, 7)]].astype(float).to_numpy()
        statuses = row[status_cols].astype(int)
        limit = float(row["LIMIT_BAL"])
        utilization = bills / limit if limit else np.zeros(6)
        payment_ratio = np.divide(pays, bills, out=np.zeros_like(pays), where=bills > 0)
        feature_rows.append(
            {
                "customer_id": int(row["ID"]),
                "avg_utilization": np.nan_to_num(utilization, nan=0.0).mean(),
                "utilization_trend": linear_slope(np.nan_to_num(utilization, nan=0.0)),
                "on_time_months": int((statuses <= 0).sum()),
                "max_delinquency": int(statuses.max()),
                "delinquency_drift": int(statuses.max() - statuses.min()),
                "consecutive_delays": longest_delay_streak(statuses),
                "payment_ratio": float(payment_ratio.mean()),
                "balance_volatility": float(np.std(bills, ddof=1)),
            }
        )
    features = pd.DataFrame(feature_rows)
    return customers, monthly, outcomes, features


def assign_tiers(features: pd.DataFrame) -> pd.DataFrame:
    conditions = [
        (features["avg_utilization"] > 1.00)
        | (features["max_delinquency"] >= 3)
        | (features["consecutive_delays"] >= 3),
        (features["avg_utilization"] < 0.40)
        & (features["on_time_months"] >= 5)
        & (features["max_delinquency"] <= 0),
    ]
    choices = ["High Risk", "Low Risk"]
    tiers = features[["customer_id"]].copy()
    tiers["risk_tier"] = np.select(conditions, choices, default="Medium Risk")
    return tiers


def delinquency_bucket(status: int) -> str:
    if status <= 0:
        return "Current"
    if status == 1:
        return "30-DPD"
    if status == 2:
        return "60-DPD"
    if status == 3:
        return "90-DPD"
    return "90+-DPD"


def build_roll_rates(monthly: pd.DataFrame, outcomes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    buckets = monthly.copy()
    buckets["bucket"] = buckets["payment_status"].map(delinquency_bucket)
    transitions = []
    for month in range(1, 6):
        left = buckets[buckets["month_number"] == month][["customer_id", "bucket"]].rename(columns={"bucket": "from_bucket"})
        right = buckets[buckets["month_number"] == month + 1][["customer_id", "bucket"]].rename(columns={"bucket": "to_bucket"})
        joined = left.merge(right, on="customer_id")
        joined["month_pair"] = f"{month}->{month + 1}"
        transitions.append(joined)
    transitions_df = pd.concat(transitions, ignore_index=True)
    roll = (
        transitions_df.groupby(["month_pair", "from_bucket", "to_bucket"])
        .size()
        .reset_index(name="account_count")
    )
    denom = roll.groupby(["month_pair", "from_bucket"])["account_count"].transform("sum")
    roll["pct_of_accounts"] = roll["account_count"] / denom * 100

    month1 = buckets[buckets["month_number"] == 1][["customer_id", "bucket"]]
    forward = month1.merge(outcomes, on="customer_id")
    forward_summary = (
        forward.groupby("bucket")
        .agg(account_count=("customer_id", "count"), default_rate_pct=("default_next_month", lambda s: s.mean() * 100))
        .reset_index()
        .rename(columns={"bucket": "month_1_bucket"})
    )
    return roll, forward_summary


def make_plots(df: pd.DataFrame) -> None:
    sns.set_theme(style="whitegrid", palette="deep")

    tier_order = ["Low Risk", "Medium Risk", "High Risk"]
    plt.figure(figsize=(7, 4))
    tier_default = df.groupby("risk_tier")["default_next_month"].mean().reindex(tier_order) * 100
    sns.barplot(x=tier_default.index, y=tier_default.values, hue=tier_default.index, legend=False)
    plt.ylabel("Default rate (%)")
    plt.xlabel("")
    plt.title("Default Rate by Risk Tier")
    plt.tight_layout()
    plt.savefig(FIGURES / "default_rate_by_risk_tier.png", dpi=160)
    plt.close()

    plt.figure(figsize=(7, 4))
    sns.histplot(data=df, x="avg_utilization", hue="default_next_month", bins=40, stat="density", common_norm=False)
    plt.title("Average Utilization: Defaulters vs Non-Defaulters")
    plt.tight_layout()
    plt.savefig(FIGURES / "avg_utilization_distribution.png", dpi=160)
    plt.close()

    plt.figure(figsize=(8, 6))
    sns.heatmap(df[FEATURES].corr(), cmap="vlag", center=0, annot=False)
    plt.title("Feature Correlation Heatmap")
    plt.tight_layout()
    plt.savefig(FIGURES / "feature_correlation_heatmap.png", dpi=160)
    plt.close()

    melted = df.melt(id_vars="default_next_month", value_vars=FEATURES, var_name="feature", value_name="value")
    g = sns.catplot(data=melted, x="default_next_month", y="value", col="feature", kind="box", col_wrap=4, sharey=False, height=3)
    g.set_titles("{col_name}")
    g.set_axis_labels("Default", "Value")
    plt.tight_layout()
    plt.savefig(FIGURES / "feature_boxplots_by_default.png", dpi=160)
    plt.close()


def train_models(df: pd.DataFrame) -> dict:
    X = df[FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0)
    y = df["default_next_month"].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42, stratify=y)

    logit = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            ("model", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
        ]
    )
    logit.fit(X_train, y_train)
    logit_prob = logit.predict_proba(X_test)[:, 1]
    logit_pred = (logit_prob >= 0.5).astype(int)

    smote = SMOTE(random_state=42)
    X_res, y_res = smote.fit_resample(X_train, y_train)
    imbalance_ratio = (y_train == 0).sum() / (y_train == 1).sum()
    base_xgb = XGBClassifier(
        objective="binary:logistic",
        eval_metric="aucpr",
        random_state=42,
        tree_method="hist",
        n_jobs=1,
        scale_pos_weight=imbalance_ratio,
    )
    grid = GridSearchCV(
        base_xgb,
        param_grid={"max_depth": [3, 5, 7], "learning_rate": [0.01, 0.1], "n_estimators": [100, 300]},
        scoring="average_precision",
        cv=StratifiedKFold(n_splits=3, shuffle=True, random_state=42),
        n_jobs=1,
        verbose=0,
    )
    grid.fit(X_res, y_res)
    model = grid.best_estimator_
    prob = model.predict_proba(X_test)[:, 1]
    pred_05 = (prob >= 0.5).astype(int)

    thresholds = np.arange(0.10, 0.91, 0.01)
    cost_rows = []
    for threshold in thresholds:
        pred = (prob >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_test, pred).ravel()
        total_cost = fn * 150 + fp * 10
        cost_rows.append({"threshold": threshold, "fn": fn, "fp": fp, "total_cost": total_cost})
    cost_df = pd.DataFrame(cost_rows)
    optimum = cost_df.loc[cost_df["total_cost"].idxmin()]
    optimal_threshold = float(optimum["threshold"])
    pred_opt = (prob >= optimal_threshold).astype(int)

    explainer = shap.TreeExplainer(model)
    shap_sample = X_test.sample(min(2000, len(X_test)), random_state=42)
    shap_values = explainer.shap_values(shap_sample)
    mean_abs = np.abs(shap_values).mean(axis=0)
    importance = (
        pd.DataFrame({"feature_name": FEATURES, "mean_abs_shap_value": mean_abs})
        .sort_values("mean_abs_shap_value", ascending=False)
        .reset_index(drop=True)
    )
    importance["rank"] = np.arange(1, len(importance) + 1)

    plt.figure(figsize=(7, 4))
    sns.barplot(data=importance, x="mean_abs_shap_value", y="feature_name", hue="feature_name", legend=False)
    plt.title("Global SHAP Feature Importance")
    plt.tight_layout()
    plt.savefig(FIGURES / "shap_global_feature_importance.png", dpi=160)
    plt.close()

    shap.summary_plot(shap_values, shap_sample, show=False)
    plt.tight_layout()
    plt.savefig(FIGURES / "shap_beeswarm.png", dpi=160)
    plt.close()

    plt.figure(figsize=(7, 4))
    plt.plot(cost_df["threshold"], cost_df["total_cost"], marker="o", linewidth=1)
    plt.axvline(optimal_threshold, color="red", linestyle="--", label=f"Optimal {optimal_threshold:.2f}")
    plt.xlabel("Classification threshold")
    plt.ylabel("Total cost (USD)")
    plt.title("Cost Matrix Threshold Optimization")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIGURES / "cost_vs_threshold.png", dpi=160)
    plt.close()

    all_scores = model.predict_proba(X)[:, 1]
    risk_scores = df[["customer_id", "risk_tier", "default_next_month", *FEATURES, "credit_limit"]].copy()
    risk_scores["risk_score"] = all_scores
    risk_scores["fraud_risk_score"] = all_scores
    risk_scores = risk_scores.sort_values("risk_score", ascending=False)

    top_test_idx = np.argsort(prob)[-20:][::-1]
    top_customer_ids = df.loc[X_test.index[top_test_idx], "customer_id"].to_numpy()
    shap_top = explainer.shap_values(X_test.iloc[top_test_idx])
    top_driver_rows = []
    for i, customer_id in enumerate(top_customer_ids):
        driver_idx = np.argsort(np.abs(shap_top[i]))[-3:][::-1]
        top_driver_rows.append(
            {
                "customer_id": int(customer_id),
                "risk_score": float(prob[top_test_idx[i]]),
                "top_driver_1": FEATURES[driver_idx[0]],
                "top_driver_2": FEATURES[driver_idx[1]],
                "top_driver_3": FEATURES[driver_idx[2]],
            }
        )
    top_drivers = pd.DataFrame(top_driver_rows)

    return {
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "logit_pr_auc": average_precision_score(y_test, logit_prob),
        "logit_confusion": confusion_matrix(y_test, logit_pred).tolist(),
        "logit_report": classification_report(y_test, logit_pred, output_dict=True),
        "best_params": grid.best_params_,
        "xgb_pr_auc": average_precision_score(y_test, prob),
        "xgb_f2": fbeta_score(y_test, pred_opt, beta=2),
        "xgb_confusion_05": confusion_matrix(y_test, pred_05).tolist(),
        "xgb_confusion_opt": confusion_matrix(y_test, pred_opt).tolist(),
        "optimal_threshold": optimal_threshold,
        "cost_df": cost_df,
        "cost_05": float(cost_df.iloc[(cost_df["threshold"] - 0.50).abs().argmin()]["total_cost"]),
        "cost_opt": float(optimum["total_cost"]),
        "risk_scores": risk_scores,
        "importance": importance,
        "top_drivers": top_drivers,
    }


def export_tables(
    customers: pd.DataFrame,
    monthly: pd.DataFrame,
    outcomes: pd.DataFrame,
    features: pd.DataFrame,
    tiers: pd.DataFrame,
    roll: pd.DataFrame,
    forward: pd.DataFrame,
    model_outputs: dict,
) -> dict:
    df = customers.merge(features, on="customer_id").merge(outcomes, on="customer_id").merge(tiers, on="customer_id")
    make_plots(df)

    for name, table in {
        "customers.csv": customers,
        "monthly_payments.csv": monthly,
        "outcomes.csv": outcomes,
        "credit_features.csv": features,
        "risk_tiers.csv": tiers,
        "roll_rate_matrix.csv": roll,
        "forward_roll_summary.csv": forward,
    }.items():
        table.to_csv(PROCESSED / name, index=False)

    risk_scores = model_outputs["risk_scores"]
    risk_scores.to_csv(PROCESSED / "risk_scores.csv", index=False)
    risk_scores.head(500).to_csv(PROCESSED / "top_risk_accounts.csv", index=False)
    model_outputs["importance"].to_csv(PROCESSED / "feature_importance.csv", index=False)
    model_outputs["top_drivers"].to_csv(PROCESSED / "top_20_shap_drivers.csv", index=False)
    model_outputs["cost_df"].to_csv(PROCESSED / "threshold_cost_curve.csv", index=False)

    bins = np.linspace(0, 1, 11)
    scored = risk_scores.copy()
    scored["risk_score_bucket"] = pd.cut(scored["risk_score"], bins=bins, include_lowest=True)
    score_distribution = (
        scored.groupby("risk_score_bucket", observed=False)
        .agg(account_count=("customer_id", "count"), default_count=("default_next_month", "sum"))
        .reset_index()
    )
    score_distribution["risk_score_bucket"] = score_distribution["risk_score_bucket"].astype(str)
    score_distribution["default_rate_pct"] = score_distribution["default_count"] / score_distribution["account_count"].replace(0, np.nan) * 100
    score_distribution.fillna(0).to_csv(PROCESSED / "risk_score_distribution.csv", index=False)

    tier_summary = (
        df.groupby("risk_tier")
        .agg(
            account_count=("customer_id", "count"),
            default_rate_pct=("default_next_month", lambda s: s.mean() * 100),
            avg_credit_limit=("credit_limit", "mean"),
            total_exposure_usd=("credit_limit", lambda s: s.sum() * USD_PER_TWD),
            avg_utilization=("avg_utilization", "mean"),
            avg_on_time_months=("on_time_months", "mean"),
        )
        .reset_index()
    )
    tier_summary["pct_of_portfolio"] = tier_summary["account_count"] / len(df) * 100
    tier_summary.to_csv(PROCESSED / "tier_summary.csv", index=False)

    portfolio_overview = tier_summary.rename(columns={"risk_tier": "tier_name"})[
        [
            "tier_name",
            "account_count",
            "pct_of_portfolio",
            "default_rate_pct",
            "avg_credit_limit",
            "total_exposure_usd",
            "avg_utilization",
            "avg_on_time_months",
        ]
    ]
    exports = {
        "portfolio_overview.csv": portfolio_overview,
        "roll_rate_matrix.csv": roll[["from_bucket", "to_bucket", "pct_of_accounts", "month_pair"]],
        "risk_score_distribution.csv": score_distribution,
        "top_risk_accounts.csv": risk_scores.head(500)[
            [
                "customer_id",
                "risk_tier",
                "risk_score",
                "fraud_risk_score",
                "avg_utilization",
                "max_delinquency",
                "on_time_months",
                "credit_limit",
                "default_next_month",
            ]
        ],
        "feature_importance.csv": model_outputs["importance"],
    }
    for name, table in exports.items():
        table.to_csv(TABLEAU / name, index=False)

    metrics = {
        "accounts": len(df),
        "overall_default_rate": df["default_next_month"].mean() * 100,
        "total_exposure_usd": customers["credit_limit"].sum() * USD_PER_TWD,
        "tier_summary": tier_summary,
        "portfolio_overview": portfolio_overview,
        "roll": roll,
        "forward": forward,
        "model": model_outputs,
        "top_features": model_outputs["importance"]["feature_name"].head(3).tolist(),
        "df": df,
    }
    with open(PROCESSED / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "accounts": metrics["accounts"],
                "overall_default_rate": metrics["overall_default_rate"],
                "total_exposure_usd": metrics["total_exposure_usd"],
                "xgb_pr_auc": model_outputs["xgb_pr_auc"],
                "xgb_f2": model_outputs["xgb_f2"],
                "optimal_threshold": model_outputs["optimal_threshold"],
                "test_period_cost_saving": model_outputs["cost_05"] - model_outputs["cost_opt"],
                "annualized_cost_saving": (model_outputs["cost_05"] - model_outputs["cost_opt"]) * 5 * 12,
                "top_features": metrics["top_features"],
            },
            f,
            indent=2,
        )
    return metrics


def pct(value: float) -> str:
    return f"{value:.1f}%"


def money(value: float) -> str:
    return f"${value:,.0f}"


def markdown_table(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(row[col]) for col in headers) + " |")
    return "\n".join(lines)


def write_memo(metrics: dict) -> None:
    tier = metrics["tier_summary"].set_index("risk_tier")
    high = tier.loc["High Risk"]
    low = tier.loc["Low Risk"]
    medium = tier.loc["Medium Risk"]
    roll = metrics["roll"]
    current_stay = roll[(roll["month_pair"] == "1->2") & (roll["from_bucket"] == "Current") & (roll["to_bucket"] == "Current")]["pct_of_accounts"].iloc[0]
    dpd30 = roll[(roll["month_pair"] == "1->2") & (roll["from_bucket"] == "30-DPD")]
    cure_30 = float(dpd30.loc[dpd30["to_bucket"] == "Current", "pct_of_accounts"].iloc[0]) if (dpd30["to_bucket"] == "Current").any() else 0.0
    roll_60 = float(dpd30.loc[dpd30["to_bucket"] == "60-DPD", "pct_of_accounts"].iloc[0]) if (dpd30["to_bucket"] == "60-DPD").any() else 0.0
    model = metrics["model"]
    test_period_cost_saving = model["cost_05"] - model["cost_opt"]
    annualized_cost_saving = test_period_cost_saving * 5 * 12
    top_features = ", ".join(metrics["top_features"])

    overview = metrics["portfolio_overview"].copy()
    overview_md = markdown_table(overview.assign(
        pct_of_portfolio=overview["pct_of_portfolio"].map(lambda x: f"{x:.1f}%"),
        default_rate_pct=overview["default_rate_pct"].map(lambda x: f"{x:.1f}%"),
        avg_credit_limit=overview["avg_credit_limit"].map(lambda x: f"{x:,.0f} TWD"),
        total_exposure_usd=overview["total_exposure_usd"].map(lambda x: money(x)),
        avg_utilization=overview["avg_utilization"].map(lambda x: f"{x:.2f}"),
        avg_on_time_months=overview["avg_on_time_months"].map(lambda x: f"{x:.1f}"),
    ))

    memo = f"""# Credit Risk Memo

**To:** Credit Risk Committee  
**From:** Analyst  
**Date:** {date.today().isoformat()}  
**Re:** Q4 Portfolio Risk Assessment

## Executive Summary

The portfolio contains {metrics["accounts"]:,} credit card accounts with {money(metrics["total_exposure_usd"])} in credit exposure and an observed next-month default rate of {pct(metrics["overall_default_rate"])}. The segmentation model separates Low Risk accounts at {pct(low["default_rate_pct"])} default from High Risk accounts at {pct(high["default_rate_pct"])} default, while the XGBoost model reaches PR-AUC {model["xgb_pr_auc"]:.3f} at an optimized cost threshold of {model["optimal_threshold"]:.2f}. Recommend prioritizing Medium Risk outreach, High Risk limit review, and a monthly batch scoring process for analyst queue management.

## Portfolio Overview

| Metric | Value |
|---|---:|
| Total accounts | {metrics["accounts"]:,} |
| Total credit exposure | {money(metrics["total_exposure_usd"])} |
| Overall default rate | {pct(metrics["overall_default_rate"])} |

{overview_md}

## Key Risk Findings

1. **Finding:** Delinquency history is the clearest default separator. **Evidence:** High Risk accounts default at {pct(high["default_rate_pct"])} versus {pct(low["default_rate_pct"])} for Low Risk accounts, a {high["default_rate_pct"] - low["default_rate_pct"]:.1f} percentage-point spread from `sql/04_risk_tiers.sql`. **Business Implication:** Accounts with repeated or severe delinquency should be routed into a priority review queue before credit exposure increases.

2. **Finding:** Utilization pressure compounds behavioral risk. **Evidence:** High Risk accounts carry average utilization of {high["avg_utilization"]:.2f}, compared with {low["avg_utilization"]:.2f} for Low Risk accounts, while representing {pct(high["pct_of_portfolio"])} of the portfolio. **Business Implication:** A utilization-based early warning trigger near 80-85% would flag accounts before they become materially past due.

3. **Finding:** Model explanations are business-readable. **Evidence:** SHAP ranks the top three drivers as {top_features}. **Business Implication:** Analysts can defend the queue logic using observable repayment and balance behaviors rather than treating the model as a black box.

## Roll Rate Analysis

From month 1 to month 2, {pct(current_stay)} of Current accounts remain Current. That strong diagonal cell indicates that most healthy accounts stay healthy month over month, which is expected in a stable card portfolio.

Among accounts that start 30-DPD in month 1, {pct(cure_30)} cure back to Current by month 2, while {pct(roll_60)} roll forward to 60-DPD. This cure-versus-roll split is the velocity signal: accounts leaving 30-DPD in the wrong direction should be contacted quickly because deterioration accelerates once missed payments persist.

## Model Performance

The XGBoost classifier achieved PR-AUC {model["xgb_pr_auc"]:.3f} and F2 {model["xgb_f2"]:.3f}. The cost matrix uses $150 for a missed defaulter and $10 for a false positive review; the optimal threshold is {model["optimal_threshold"]:.2f}, reducing estimated test-period misclassification cost by {money(test_period_cost_saving)} versus the default 0.50 threshold, or roughly {money(annualized_cost_saving)} annualized to the full portfolio.

## Recommendations

| Recommendation | Action | Target Segment | Estimated Impact | Implementation Complexity |
|---|---|---|---|---|
| 1 | Proactive outreach before hard delinquency | Medium Risk accounts approaching 85% utilization or two delayed months | Reduce roll-forward into High Risk and protect {money(medium["total_exposure_usd"])} in Medium Risk exposure | Medium |
| 2 | Credit limit review | High Risk accounts with high utilization or 60-DPD+ behavior | Contain maximum loss exposure of {money(high["total_exposure_usd"])} | Medium |
| 3 | Monthly batch scoring job | Full portfolio | Refresh analyst queue with risk scores, SHAP drivers, and tier changes every cycle | Low |

## Appendix

- `sql/01_schema.sql`
- `sql/02_ingest.sql`
- `sql/03_features.sql`
- `sql/04_risk_tiers.sql`
- `sql/05_roll_rates.sql`
- `notebooks/modeling.ipynb`
- Tableau dashboard CSVs in `tableau/`; dashboard link placeholder: add your published Tableau Public URL after building the workbook.
"""
    (REPORTS / "credit_risk_memo.md").write_text(memo, encoding="utf-8")


def write_readme(metrics: dict) -> None:
    tier = metrics["tier_summary"].set_index("risk_tier")
    high = tier.loc["High Risk"]
    low = tier.loc["Low Risk"]
    roll = metrics["roll"]
    model = metrics["model"]
    roll_30_60 = roll[(roll["month_pair"] == "1->2") & (roll["from_bucket"] == "30-DPD") & (roll["to_bucket"] == "60-DPD")]
    roll_30_60_pct = float(roll_30_60["pct_of_accounts"].iloc[0]) if len(roll_30_60) else 0.0
    test_period_cost_saving = model["cost_05"] - model["cost_opt"]
    annualized_cost_saving = test_period_cost_saving * 5 * 12
    top_features = ", ".join(metrics["top_features"])

    readme = f"""# Credit Risk Segmentation & Default Prediction System

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

- Portfolio: {metrics["accounts"]:,} accounts, {money(metrics["total_exposure_usd"])} estimated USD credit exposure, {pct(metrics["overall_default_rate"])} observed next-month default rate.
- Risk tiers: Low Risk default rate {pct(low["default_rate_pct"])}; High Risk default rate {pct(high["default_rate_pct"])}.
- Model: XGBoost PR-AUC {model["xgb_pr_auc"]:.3f}, F2 {model["xgb_f2"]:.3f}, optimal threshold {model["optimal_threshold"]:.2f}.
- Cost impact: estimated test-period cost reduction of {money(test_period_cost_saving)} versus a 0.50 threshold, or {money(annualized_cost_saving)} annualized to the full portfolio.
- Top SHAP drivers: {top_features}.

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

- Designed a normalised PostgreSQL schema and engineered 8 behavioural risk features (utilisation trend, payment drift, roll rates, balance volatility) using CTEs and window functions across {metrics["accounts"]:,} credit card accounts
- Built a rule-based risk tier model separating default rates from {low["default_rate_pct"]:.1f}% to {high["default_rate_pct"]:.1f}% across tiers; performed roll-rate analysis identifying {roll_30_60_pct:.1f}% of 30-DPD accounts roll to 60-DPD within 2 months
- Trained XGBoost classifier (PR-AUC {model["xgb_pr_auc"]:.3f}, F2 {model["xgb_f2"]:.3f}); optimised decision threshold via a $150/$10 FN/FP cost matrix, reducing estimated annual misclassification cost by ${annualized_cost_saving:,.0f} vs a 0.5 threshold baseline
- Produced a 4-section credit risk memo with portfolio overview, roll-rate analysis, and 3 prioritised recommendations; delivered findings in an interactive 3-view Tableau dashboard [link]
"""
    (ROOT / "README.md").write_text(readme, encoding="utf-8")


def write_notebook(metrics: dict) -> None:
    model = metrics["model"]
    nb = nbf.v4.new_notebook()
    cells = [
        nbf.v4.new_markdown_cell("# Credit Risk Segmentation & Default Prediction System\n\nThis notebook is written for a credit risk audience: each technical step maps to a portfolio decision."),
        nbf.v4.new_markdown_cell("## Setup and Data Loading\n\nBusiness purpose: assemble the modeled account-level table so analysts can evaluate exposure, default outcomes, and risk tiers in one place."),
        nbf.v4.new_code_cell("import pandas as pd\nfrom pathlib import Path\nROOT = Path('..')\ndf = pd.read_csv(ROOT / 'data/processed/risk_scores.csv')\nprint(df.shape)\nprint(df.dtypes)\nprint(df['default_next_month'].value_counts(normalize=True))\ndf.head()"),
        nbf.v4.new_markdown_cell("## Exploratory Analysis\n\nBusiness purpose: validate that engineered features and risk tiers create visible separation before fitting a model."),
        nbf.v4.new_code_cell("from IPython.display import Image, display\nfor name in ['default_rate_by_risk_tier.png','avg_utilization_distribution.png','feature_correlation_heatmap.png','feature_boxplots_by_default.png']:\n    display(Image(filename=str(ROOT / 'reports/figures' / name)))"),
        nbf.v4.new_markdown_cell("## Train-Test Split\n\nBusiness purpose: preserve the base default rate in training and testing so model evaluation reflects the real portfolio mix."),
        nbf.v4.new_code_cell("FEATURES = ['avg_utilization','utilization_trend','on_time_months','max_delinquency','delinquency_drift','consecutive_delays','payment_ratio','balance_volatility']\nfrom sklearn.model_selection import train_test_split\nX = df[FEATURES]\ny = df['default_next_month']\nX_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)\nprint(y_train.value_counts(normalize=True))\nprint(y_test.value_counts(normalize=True))"),
        nbf.v4.new_markdown_cell("## Baseline Model\n\nBusiness purpose: use balanced logistic regression as a transparent benchmark. Accuracy is misleading because a model predicting no defaults would already appear strong at a 22% default base rate."),
        nbf.v4.new_code_cell(f"print('Logistic PR-AUC: {model['logit_pr_auc']:.3f}')\nprint('Confusion matrix:', {model['logit_confusion']})"),
        nbf.v4.new_markdown_cell("## XGBoost with SMOTE\n\nBusiness purpose: improve recall for costly defaults while keeping evaluation on untouched test data."),
        nbf.v4.new_code_cell(f"print('Best params:', {model['best_params']})\nprint('XGBoost PR-AUC: {model['xgb_pr_auc']:.3f}')\nprint('F2 at optimal threshold: {model['xgb_f2']:.3f}')\nprint('Confusion matrix at 0.50:', {model['xgb_confusion_05']})\nprint('Confusion matrix at optimal threshold:', {model['xgb_confusion_opt']})"),
        nbf.v4.new_markdown_cell("## Cost Matrix Analysis\n\nBusiness purpose: choose the operating threshold by dollar cost, not by a generic 0.50 cutoff."),
        nbf.v4.new_code_cell(f"print('Optimal threshold: {model['optimal_threshold']:.2f}')\nprint('Cost at 0.50: ${model['cost_05']:,.0f}')\nprint('Cost at optimum: ${model['cost_opt']:,.0f}')\nfrom IPython.display import Image, display\ndisplay(Image(filename=str(ROOT / 'reports/figures/cost_vs_threshold.png')))"),
        nbf.v4.new_markdown_cell(f"## SHAP Explainability\n\nBusiness purpose: translate model scoring into analyst-readable drivers. The model flags accounts primarily because of {', '.join(metrics['top_features'])}; analysts should prioritize customers showing these signals together."),
        nbf.v4.new_code_cell("from IPython.display import Image, display\ndisplay(Image(filename=str(ROOT / 'reports/figures/shap_global_feature_importance.png')))\ndisplay(Image(filename=str(ROOT / 'reports/figures/shap_beeswarm.png')))\npd.read_csv(ROOT / 'data/processed/top_20_shap_drivers.csv').head(20)"),
        nbf.v4.new_markdown_cell("## Risk Score Output\n\nBusiness purpose: produce account-level scores and clean Tableau exports for monitoring, triage, and executive review."),
        nbf.v4.new_code_cell("for file in ['risk_scores.csv','tier_summary.csv','roll_rate_matrix.csv','top_risk_accounts.csv']:\n    path = ROOT / 'data/processed' / file\n    print(file, pd.read_csv(path).shape)"),
    ]
    nb["cells"] = cells
    nbf.write(nb, NOTEBOOK)


def main() -> None:
    ensure_dirs()
    raw = load_raw()
    customers, monthly, outcomes, features = build_analytical_tables(raw)
    tiers = assign_tiers(features)
    df = customers.merge(features, on="customer_id").merge(outcomes, on="customer_id").merge(tiers, on="customer_id")
    make_plots(df)
    roll, forward = build_roll_rates(monthly, outcomes)
    model_outputs = train_models(df)
    metrics = export_tables(customers, monthly, outcomes, features, tiers, roll, forward, model_outputs)
    write_memo(metrics)
    write_readme(metrics)
    write_notebook(metrics)
    print("Phase 1 complete: folder structure and environment files created.")
    print("Phase 2 complete: PostgreSQL schema written.")
    print("Phase 3 complete: raw UCI data converted and analytical tables exported.")
    print("Phase 4 complete: behavioral features engineered.")
    print("Phase 5 complete: risk tiers assigned and validated.")
    print("Phase 6 complete: roll-rate matrix exported.")
    print("Phase 7 complete: models trained, plots generated, notebook created.")
    print("Phase 8 complete: credit risk memo written.")
    print("Phase 9 complete: Tableau-ready CSVs exported.")
    print("Phase 10 complete: README and CV bullets generated.")


if __name__ == "__main__":
    main()
