import datetime as dt
from dataclasses import dataclass
from typing import Dict, List, Optional

import altair as alt
import pandas as pd
import requests
import streamlit as st


@dataclass
class ClassificationRule:
    keyword: str
    category: str

    def matches(self, text: str) -> bool:
        return self.keyword.lower() in text.lower()


DEFAULT_RULES: List[ClassificationRule] = [
    ClassificationRule("uber", "Transport"),
    ClassificationRule("bolt", "Transport"),
    ClassificationRule("airbnb", "Travel"),
    ClassificationRule("hotel", "Travel"),
    ClassificationRule("coffee", "Food"),
    ClassificationRule("cafe", "Food"),
    ClassificationRule("restaurant", "Food"),
    ClassificationRule("grocery", "Groceries"),
    ClassificationRule("supermarket", "Groceries"),
    ClassificationRule("amazon", "Shopping"),
    ClassificationRule("itunes", "Entertainment"),
    ClassificationRule("netflix", "Entertainment"),
    ClassificationRule("gym", "Health"),
    ClassificationRule("pharmacy", "Health"),
]

WISE_API_BASE = "https://api.transferwise.com"


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize common Wise CSV column variations."""
    normalized = {col.strip().lower(): col for col in df.columns}

    column_map = {
        "date": "date",
        "created on": "date",
        "amount": "amount",
        "amount (in source currency)": "amount",
        "amount (in target currency)": "amount",
        "total amount": "amount",
        "currency": "currency",
        "source currency": "currency",
        "description": "description",
        "merchant": "merchant",
        "name": "merchant",
        "reference": "description",
        "category": "category",
    }

    data: Dict[str, pd.Series] = {}
    for norm_key, target in column_map.items():
        if norm_key in normalized:
            data[target] = df[normalized[norm_key]]

    if "date" in data:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
    if "amount" in data:
        data["amount"] = pd.to_numeric(data["amount"], errors="coerce")

    fallback_columns = {
        "currency": "Unknown",
        "description": "",
        "merchant": "",
    }

    for column, default in fallback_columns.items():
        if column not in data:
            data[column] = default

    return pd.DataFrame(data)


def statement_to_dataframe(statement: Dict) -> pd.DataFrame:
    """Convert Wise borderless statement response to a normalized dataframe."""

    transactions = statement.get("transactions", [])
    rows: List[Dict] = []

    for tx in transactions:
        amount_info = tx.get("amount") or {}
        details = tx.get("details") or {}
        merchant_info = tx.get("merchant") or {}
        rows.append(
            {
                "date": tx.get("date"),
                "amount": amount_info.get("value"),
                "currency": amount_info.get("currency"),
                "description": details.get("description")
                or details.get("type")
                or tx.get("type"),
                "merchant": merchant_info.get("name")
                or details.get("merchantName")
                or details.get("recipientName")
                or details.get("senderName"),
                "category": details.get("category"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    return normalize_columns(df)


def fetch_wise_statement(
    api_token: str,
    profile_id: str,
    account_id: str,
    start_date: dt.date,
    end_date: dt.date,
) -> pd.DataFrame:
    """Fetch transactions directly from Wise Borderless account statements."""

    if end_date < start_date:
        raise ValueError("End date must be on or after start date.")

    interval_start = dt.datetime.combine(start_date, dt.time.min).isoformat() + "Z"
    interval_end = dt.datetime.combine(end_date, dt.time.max).isoformat() + "Z"

    url = f"{WISE_API_BASE}/v3/profiles/{profile_id}/borderless-accounts/{account_id}/statement.json"
    params = {
        "intervalStart": interval_start,
        "intervalEnd": interval_end,
        "type": "COMPACT",
    }
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }

    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    statement = response.json()
    return statement_to_dataframe(statement)


def classify_row(row: pd.Series, rules: List[ClassificationRule]) -> str:
    existing = row.get("category")
    if isinstance(existing, str) and existing.strip():
        return existing

    combined = f"{row.get('description', '')} {row.get('merchant', '')}"
    for rule in rules:
        if rule.matches(combined):
            return rule.category
    return "Uncategorized"


def apply_classification(df: pd.DataFrame, rules: List[ClassificationRule]) -> pd.DataFrame:
    enriched = df.copy()
    enriched["category"] = enriched.apply(lambda row: classify_row(row, rules), axis=1)
    return enriched


def render_summary_metrics(df: pd.DataFrame) -> None:
    total_spent = df.loc[df["amount"] < 0, "amount"].sum()
    total_income = df.loc[df["amount"] > 0, "amount"].sum()
    avg_ticket = df.loc[df["amount"] < 0, "amount"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total spent", f"€ {abs(total_spent):,.2f}")
    col2.metric("Total income", f"€ {total_income:,.2f}")
    col3.metric("Avg. expense", f"€ {abs(avg_ticket):,.2f}")


def category_breakdown_chart(df: pd.DataFrame) -> alt.Chart:
    summary = df.groupby("category", dropna=False)["amount"].sum().reset_index()
    summary["amount"] = summary["amount"].abs()
    return (
        alt.Chart(summary)
        .mark_bar()
        .encode(
            x=alt.X("amount:Q", title="Total"),
            y=alt.Y("category:N", sort="-x", title="Category"),
            color="category",
            tooltip=["category", alt.Tooltip("amount:Q", format=",.2f")],
        )
    )


def monthly_trend_chart(df: pd.DataFrame) -> alt.Chart:
    monthly = (
        df.assign(month=df["date"].dt.to_period("M").dt.to_timestamp())
        .groupby(["month", "category"])["amount"]
        .sum()
        .reset_index()
    )
    monthly["amount"] = monthly["amount"].abs()
    return (
        alt.Chart(monthly)
        .mark_line(point=True)
        .encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("amount:Q", title="Amount"),
            color="category",
            tooltip=["month", "category", alt.Tooltip("amount:Q", format=",.2f")],
        )
    )


def merchant_breakdown_chart(df: pd.DataFrame) -> alt.Chart:
    merchants = (
        df.assign(merchant=df.get("merchant", "Unknown").fillna("Unknown"))
        .groupby("merchant")["amount"]
        .sum()
        .reset_index()
    )
    merchants["amount"] = merchants["amount"].abs()
    top_merchants = merchants.nlargest(10, "amount")
    return (
        alt.Chart(top_merchants)
        .mark_bar()
        .encode(
            x=alt.X("amount:Q", title="Total"),
            y=alt.Y("merchant:N", sort="-x", title="Merchant"),
            tooltip=["merchant", alt.Tooltip("amount:Q", format=",.2f")],
        )
    )


def load_sample_data() -> pd.DataFrame:
    sample_path = "sample_data/wise_sample.csv"
    df = pd.read_csv(sample_path)
    return normalize_columns(df)


def main():
    st.set_page_config(page_title="Wise Expense Tracker", layout="wide")
    st.title("Wise Expense Tracker")
    st.caption(
        "Connect to Wise or upload CSV exports to auto-classify spending and explore where your money goes."
    )

    if "rules" not in st.session_state:
        st.session_state.rules = list(DEFAULT_RULES)

    with st.sidebar:
        st.header("Classification rules")
        st.caption("Add a keyword to map transactions to a category.")
        keyword = st.text_input("Keyword", placeholder="e.g., ikea")
        category = st.text_input("Category", placeholder="e.g., Home")
        if st.button("Add rule") and keyword and category:
            st.session_state.rules.append(ClassificationRule(keyword, category))
            st.success(f"Added rule: {keyword} → {category}")

        if st.button("Reset to defaults"):
            st.session_state.rules = list(DEFAULT_RULES)
            st.info("Classification rules restored.")

        if st.session_state.rules:
            st.subheader("Active rules")
            st.write(pd.DataFrame([r.__dict__ for r in st.session_state.rules]))

    st.markdown("### Data source")
    source = st.radio(
        "Choose how to load your transactions",
        ["Connect to Wise", "Upload CSV", "Use sample data"],
        horizontal=True,
    )

    df: Optional[pd.DataFrame] = None
    if source == "Connect to Wise":
        with st.form("wise_api_form"):
            st.write("Enter your Wise API credentials (kept in your browser session only).")
            api_token = st.text_input("API token", type="password", help="Wise personal API token")
            profile_id = st.text_input("Profile ID", help="Found in Wise API settings")
            account_id = st.text_input(
                "Balance/account ID",
                help="Borderless/balance ID for the currency you want to fetch",
            )
            today = dt.date.today()
            start_date = st.date_input(
                "Start date",
                value=today - dt.timedelta(days=30),
            )
            end_date = st.date_input("End date", value=today)
            submitted = st.form_submit_button("Fetch transactions from Wise")

        if submitted:
            missing = [label for label, value in [
                ("API token", api_token),
                ("Profile ID", profile_id),
                ("Balance/account ID", account_id),
            ] if not value]
            if missing:
                st.error(f"Please provide: {', '.join(missing)}")
            else:
                with st.spinner("Fetching from Wise..."):
                    try:
                        df = fetch_wise_statement(
                            api_token=api_token,
                            profile_id=profile_id,
                            account_id=account_id,
                            start_date=start_date,
                            end_date=end_date,
                        )
                        if df.empty:
                            st.warning("No transactions returned for the selected range.")
                        else:
                            st.success("Loaded transactions from Wise.")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Failed to fetch data: {exc}")

    elif source == "Upload CSV":
        uploaded = st.file_uploader("Upload Wise CSV export", type=["csv"])
        if uploaded:
            df = normalize_columns(pd.read_csv(uploaded))

    elif source == "Use sample data":
        if st.button("Load sample transactions"):
            df = load_sample_data()

    if df is None or df.empty:
        st.info(
            "Connect to Wise, upload a CSV export, or load the sample to see the dashboard."
        )
        return

    df = df.dropna(subset=["date", "amount"])
    df = apply_classification(df, st.session_state.rules)

    st.subheader("Overview")
    render_summary_metrics(df)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Spend by category")
        st.altair_chart(category_breakdown_chart(df), use_container_width=True)
    with col2:
        st.markdown("### Monthly trend")
        st.altair_chart(monthly_trend_chart(df), use_container_width=True)

    st.markdown("### Top merchants")
    st.altair_chart(merchant_breakdown_chart(df), use_container_width=True)

    st.markdown("### Transactions")
    editable = st.data_editor(
        df.sort_values("date", ascending=False),
        num_rows="dynamic",
        column_config={"amount": st.column_config.NumberColumn(format="€ %.2f")},
    )
    st.caption(
        "Edit categories directly in the grid—changes stay in your browser session."
    )

    csv = editable.to_csv(index=False).encode("utf-8")
    st.download_button("Download enriched CSV", csv, "wise_enriched.csv", "text/csv")


if __name__ == "__main__":
    main()
