from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
TABLEAU = ROOT / "tableau"
USD_PER_TWD = 1 / 31.0


TIER_ORDER = ["Low Risk", "Medium Risk", "High Risk"]
TIER_COLORS = {
    "Low Risk": "#2E7D32",
    "Medium Risk": "#F9A825",
    "High Risk": "#C62828",
}


def money_band(value: float) -> str:
    usd = value * USD_PER_TWD
    if usd < 2_000:
        return "<$2K"
    if usd < 5_000:
        return "$2K-$5K"
    if usd < 10_000:
        return "$5K-$10K"
    if usd < 20_000:
        return "$10K-$20K"
    return "$20K+"


def utilization_band(value: float) -> str:
    if value < 0.2:
        return "0-20%"
    if value < 0.4:
        return "20-40%"
    if value < 0.6:
        return "40-60%"
    if value < 0.8:
        return "60-80%"
    if value < 1.0:
        return "80-100%"
    return "100%+"


def action_for_account(row: pd.Series) -> tuple[str, str, str]:
    if row["risk_tier"] == "High Risk" and row["max_delinquency"] >= 3:
        return "Priority collections review", "Severe delinquency history", "High"
    if row["risk_tier"] == "High Risk" and row["consecutive_delays"] >= 3:
        return "Hardship outreach", "Persistent delayed payments", "High"
    if row["risk_tier"] == "High Risk" and row["avg_utilization"] > 1:
        return "Credit line review", "Utilization above approved limit", "High"
    if row["risk_tier"] == "Medium Risk" and row["avg_utilization"] >= 0.8:
        return "Pre-delinquency outreach", "Approaching high utilization threshold", "Medium"
    if row["risk_score"] >= 0.5:
        return "Manual analyst review", "High model score", "Medium"
    return "Monitor", "No immediate intervention", "Low"


def export(frame: pd.DataFrame, filename: str) -> None:
    path = TABLEAU / filename
    frame.to_csv(path, index=False)
    print(f"wrote {path.name}: {len(frame):,} rows")


def main() -> None:
    TABLEAU.mkdir(parents=True, exist_ok=True)

    customers = pd.read_csv(PROCESSED / "customers.csv")
    features = pd.read_csv(PROCESSED / "credit_features.csv")
    outcomes = pd.read_csv(PROCESSED / "outcomes.csv")
    monthly = pd.read_csv(PROCESSED / "monthly_payments.csv")
    tiers = pd.read_csv(PROCESSED / "risk_tiers.csv")
    scores = pd.read_csv(PROCESSED / "risk_scores.csv")
    roll = pd.read_csv(PROCESSED / "roll_rate_matrix.csv")
    forward = pd.read_csv(PROCESSED / "forward_roll_summary.csv")
    threshold = pd.read_csv(PROCESSED / "threshold_cost_curve.csv")
    importance = pd.read_csv(PROCESSED / "feature_importance.csv")

    base = (
        customers.merge(features, on="customer_id")
        .merge(outcomes, on="customer_id")
        .merge(tiers, on="customer_id")
        .merge(scores[["customer_id", "risk_score"]], on="customer_id")
    )
    base["credit_limit_usd"] = base["credit_limit"] * USD_PER_TWD
    base["expected_loss_usd"] = base["risk_score"] * base["credit_limit_usd"]
    base["utilization_band"] = base["avg_utilization"].map(utilization_band)
    base["credit_limit_band"] = base["credit_limit"].map(money_band)
    base["tier_color"] = base["risk_tier"].map(TIER_COLORS)

    high_risk = base[base["risk_tier"] == "High Risk"]
    low_risk = base[base["risk_tier"] == "Low Risk"]
    optimal = threshold.loc[threshold["total_cost"].idxmin()]
    baseline_05 = threshold.iloc[(threshold["threshold"] - 0.50).abs().argmin()]

    executive_kpis = pd.DataFrame(
        [
            {"metric": "Total Accounts", "value": len(base), "formatted_value": f"{len(base):,}", "tooltip": "Total accounts in the analyzed card portfolio"},
            {
                "metric": "Total Exposure",
                "value": base["credit_limit_usd"].sum(),
                "formatted_value": f"${base['credit_limit_usd'].sum():,.0f}",
                "tooltip": "Maximum approved credit exposure converted from TWD to USD",
            },
            {
                "metric": "Overall Default Rate",
                "value": base["default_next_month"].mean() * 100,
                "formatted_value": f"{base['default_next_month'].mean() * 100:.1f}%",
                "tooltip": "Observed next-month default rate",
            },
            {
                "metric": "High Risk Accounts",
                "value": len(high_risk),
                "formatted_value": f"{len(high_risk):,}",
                "tooltip": "Accounts assigned to High Risk tier by behavioral rules",
            },
            {
                "metric": "High-Low Default Spread",
                "value": (high_risk["default_next_month"].mean() - low_risk["default_next_month"].mean()) * 100,
                "formatted_value": f"{(high_risk['default_next_month'].mean() - low_risk['default_next_month'].mean()) * 100:.1f} pts",
                "tooltip": "Difference in default rate between High Risk and Low Risk tiers",
            },
            {
                "metric": "Annualized Cost Reduction",
                "value": (baseline_05["total_cost"] - optimal["total_cost"]) * 5 * 12,
                "formatted_value": f"${(baseline_05['total_cost'] - optimal['total_cost']) * 5 * 12:,.0f}",
                "tooltip": "Cost saving annualized from the 20% holdout set to full monthly portfolio scoring",
            },
        ]
    )
    export(executive_kpis, "executive_kpis.csv")

    tier_summary = (
        base.groupby("risk_tier")
        .agg(
            account_count=("customer_id", "count"),
            pct_of_portfolio=("customer_id", lambda s: len(s) / len(base) * 100),
            default_rate_pct=("default_next_month", lambda s: s.mean() * 100),
            total_exposure_usd=("credit_limit_usd", "sum"),
            expected_loss_usd=("expected_loss_usd", "sum"),
            avg_risk_score=("risk_score", "mean"),
            avg_utilization=("avg_utilization", "mean"),
            avg_on_time_months=("on_time_months", "mean"),
            avg_max_delinquency=("max_delinquency", "mean"),
        )
        .reset_index()
    )
    tier_summary["tier_sort"] = tier_summary["risk_tier"].map({name: i for i, name in enumerate(TIER_ORDER, start=1)})
    tier_summary["tier_color"] = tier_summary["risk_tier"].map(TIER_COLORS)
    export(tier_summary.sort_values("tier_sort"), "tier_summary_enhanced.csv")

    feature_profile = (
        base.groupby("risk_tier")[
            [
                "avg_utilization",
                "utilization_trend",
                "on_time_months",
                "max_delinquency",
                "delinquency_drift",
                "consecutive_delays",
                "payment_ratio",
                "balance_volatility",
                "risk_score",
            ]
        ]
        .mean()
        .reset_index()
        .melt(id_vars="risk_tier", var_name="feature", value_name="average_value")
    )
    feature_profile["tier_color"] = feature_profile["risk_tier"].map(TIER_COLORS)
    export(feature_profile, "risk_tier_feature_profile.csv")

    monthly_enriched = monthly.merge(tiers, on="customer_id").merge(outcomes, on="customer_id")
    monthly_enriched["bucket"] = np.select(
        [
            monthly_enriched["payment_status"] <= 0,
            monthly_enriched["payment_status"] == 1,
            monthly_enriched["payment_status"] == 2,
            monthly_enriched["payment_status"] == 3,
            monthly_enriched["payment_status"] >= 4,
        ],
        ["Current", "30-DPD", "60-DPD", "90-DPD", "90+-DPD"],
        default="Unknown",
    )
    monthly_trend = (
        monthly_enriched.groupby(["month_number", "risk_tier", "bucket"])
        .agg(account_count=("customer_id", "count"), default_rate_pct=("default_next_month", lambda s: s.mean() * 100))
        .reset_index()
    )
    monthly_trend["tier_color"] = monthly_trend["risk_tier"].map(TIER_COLORS)
    export(monthly_trend, "monthly_delinquency_trend.csv")

    roll_sankey = roll.copy()
    roll_sankey["from_node"] = roll_sankey["month_pair"].str.split("->").str[0] + ": " + roll_sankey["from_bucket"]
    roll_sankey["to_node"] = roll_sankey["month_pair"].str.split("->").str[1] + ": " + roll_sankey["to_bucket"]
    roll_sankey["transition_label"] = roll_sankey["from_bucket"] + " -> " + roll_sankey["to_bucket"]
    export(roll_sankey, "roll_rate_sankey_edges.csv")

    export(forward, "forward_roll_summary.csv")

    utilization_view = (
        base.groupby(["utilization_band", "risk_tier"])
        .agg(
            account_count=("customer_id", "count"),
            default_rate_pct=("default_next_month", lambda s: s.mean() * 100),
            avg_risk_score=("risk_score", "mean"),
            total_exposure_usd=("credit_limit_usd", "sum"),
        )
        .reset_index()
    )
    band_order = {"0-20%": 1, "20-40%": 2, "40-60%": 3, "60-80%": 4, "80-100%": 5, "100%+": 6}
    utilization_view["band_sort"] = utilization_view["utilization_band"].map(band_order)
    utilization_view["tier_color"] = utilization_view["risk_tier"].map(TIER_COLORS)
    export(utilization_view.sort_values(["band_sort", "risk_tier"]), "utilization_band_analysis.csv")

    base["risk_score_decile"] = pd.qcut(base["risk_score"].rank(method="first"), 10, labels=[f"D{i}" for i in range(1, 11)])
    deciles = (
        base.groupby("risk_score_decile", observed=False)
        .agg(
            account_count=("customer_id", "count"),
            default_count=("default_next_month", "sum"),
            default_rate_pct=("default_next_month", lambda s: s.mean() * 100),
            min_score=("risk_score", "min"),
            max_score=("risk_score", "max"),
            total_exposure_usd=("credit_limit_usd", "sum"),
            expected_loss_usd=("expected_loss_usd", "sum"),
        )
        .reset_index()
    )
    export(deciles, "risk_score_deciles.csv")

    limit_view = (
        base.groupby(["credit_limit_band", "risk_tier"])
        .agg(
            account_count=("customer_id", "count"),
            default_rate_pct=("default_next_month", lambda s: s.mean() * 100),
            total_exposure_usd=("credit_limit_usd", "sum"),
            expected_loss_usd=("expected_loss_usd", "sum"),
        )
        .reset_index()
    )
    export(limit_view, "credit_limit_band_analysis.csv")

    demographics = base.copy()
    demographics["sex_label"] = demographics["sex"].map({1: "Male", 2: "Female"}).fillna("Unknown")
    demographics["education_label"] = demographics["education"].map(
        {1: "Graduate School", 2: "University", 3: "High School", 4: "Other", 0: "Undocumented", 5: "Undocumented", 6: "Undocumented"}
    )
    demographics["marriage_label"] = demographics["marriage"].map({1: "Married", 2: "Single", 3: "Other", 0: "Undocumented"}).fillna("Unknown")
    demographic_mix = (
        demographics.groupby(["risk_tier", "sex_label", "education_label", "marriage_label"])
        .agg(
            account_count=("customer_id", "count"),
            default_rate_pct=("default_next_month", lambda s: s.mean() * 100),
            avg_risk_score=("risk_score", "mean"),
            avg_credit_limit_usd=("credit_limit_usd", "mean"),
        )
        .reset_index()
    )
    demographic_mix["tier_color"] = demographic_mix["risk_tier"].map(TIER_COLORS)
    export(demographic_mix, "demographic_risk_mix.csv")

    threshold_view = threshold.copy()
    threshold_view["cost_saving_vs_050"] = baseline_05["total_cost"] - threshold_view["total_cost"]
    threshold_view["annualized_cost_saving_vs_050"] = threshold_view["cost_saving_vs_050"] * 5 * 12
    threshold_view["is_optimal_threshold"] = threshold_view["threshold"].eq(optimal["threshold"])
    export(threshold_view, "threshold_cost_analysis.csv")

    action_queue = base.sort_values(["risk_tier", "risk_score"], ascending=[True, False]).copy()
    actions = action_queue.apply(action_for_account, axis=1, result_type="expand")
    action_queue["recommended_action"] = actions[0]
    action_queue["action_reason"] = actions[1]
    action_queue["action_priority"] = actions[2]
    action_queue = action_queue.sort_values(["action_priority", "risk_score"], ascending=[True, False])
    export(
        action_queue[
            [
                "customer_id",
                "risk_tier",
                "risk_score",
                "recommended_action",
                "action_reason",
                "action_priority",
                "credit_limit_usd",
                "expected_loss_usd",
                "avg_utilization",
                "on_time_months",
                "max_delinquency",
                "consecutive_delays",
                "balance_volatility",
                "default_next_month",
            ]
        ].head(1500),
        "account_action_queue.csv",
    )

    importance = importance.copy()
    importance["business_interpretation"] = importance["feature_name"].map(
        {
            "on_time_months": "Fewer current months indicate deteriorating payment discipline.",
            "consecutive_delays": "Persistent delays are stronger warning signals than one-off misses.",
            "balance_volatility": "Large balance swings can indicate unstable spending or income shocks.",
            "max_delinquency": "Worst arrears level captures severity of repayment stress.",
            "avg_utilization": "High utilization means low remaining credit buffer.",
            "utilization_trend": "Rising utilization shows worsening credit dependence.",
            "payment_ratio": "Higher repayment relative to bill balance lowers risk.",
            "delinquency_drift": "Repayment status volatility indicates inconsistent behavior.",
        }
    )
    export(importance, "feature_importance_story.csv")

    storyboard = ROOT / "tableau" / "dashboard_storyboard.md"
    storyboard.write_text(
        """# Tableau Dashboard Upgrade Plan

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
""",
        encoding="utf-8",
    )
    print(f"wrote {storyboard.name}")


if __name__ == "__main__":
    main()
