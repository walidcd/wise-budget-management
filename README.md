# Wise Budget Management

An MVP Streamlit app to explore Wise transactions, auto-classify spending, and visualize where your money goes.

## Features
- Upload Wise CSV exports and normalize common column names automatically.
- Auto-classification rules based on merchant/description keywords with editable rule list in the sidebar.
- Category, merchant, and monthly trend charts to understand spending patterns.
- Inline transaction editor for quick category tweaks plus an enriched CSV download.
- Sample dataset included for a quick demo.

## Getting started
1. Create and activate a virtual environment (optional but recommended).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the Streamlit app:
   ```bash
   streamlit run streamlit_app.py
   ```
4. Choose **Connect to Wise** to pull transactions directly from your account or upload a CSV export.

## Connecting to Wise directly
1. Generate a personal API token from Wise: **Settings → API tokens**.
2. Find your **Profile ID** (shown in the same API settings page).
3. Find your **Balance/Account ID** for the currency balance you want to query.
4. In the app, select **Connect to Wise**, paste the token and IDs, set a date range, and click **Fetch transactions from Wise**.

Notes:
- Tokens are only stored in your browser session; they are not persisted or sent elsewhere.
- The app uses the Wise statement endpoint (`/v3/profiles/{profileId}/borderless-accounts/{accountId}/statement.json`) to fetch transactions.
- If you prefer not to use the API, you can still upload CSV exports or load the provided sample data.

## Automatic classification
- Default rules cover common services (Uber, Netflix, Amazon, grocery stores, etc.).
- Add your own rules in the sidebar: specify a keyword and the category it should map to.
- Reset restores the default rule set if you want to start fresh.

## Data notes
- The app looks for typical Wise columns (Date, Amount, Currency, Description, Merchant) but will fall back to empty values when unavailable.
- Expenses are displayed as positive values in charts; income remains positive in summary metrics.

## Exporting results
Use the **Download enriched CSV** button to export the edited transactions (including auto-generated categories) for further analysis.
