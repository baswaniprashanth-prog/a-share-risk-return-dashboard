# 📈 A-Share Risk-Return Dashboard

An interactive financial analysis tool built with Python and Streamlit that lets users compare the risk-return profile of multiple A-share stocks over a chosen time period.

---

## 🎯 Product Overview

**Analytical Problem**: How can a non-technical investor quickly evaluate and compare the performance, risk, and return trade-offs of multiple A-share stocks without needing expertise in finance or coding?

**Target Audience**: Beginner to intermediate investors, finance students, and anyone interested in comparing A-share stock performance at a glance.

**Data Source**: Live OHLCV data fetched on demand from Tencent Finance (primary) and EastMoney Finance (fallback). No local CSV cache required for stock price data. Accessed: April 2026.

---

## ✨ Features

| Feature | Description |
|---|---|
| 📊 Normalised Price Chart | Compares all stocks rebased to 100 at start date |
| 📈 Cumulative Return | Tracks cumulative % gain/loss over time |
| 📉 Drawdown Curve | Visualises peak-to-trough decline for each stock |
| 🎯 Risk-Return Scatter | Plots annualised return vs volatility (colour = Sharpe) |
| 🌊 Rolling Volatility | Configurable rolling-window annualised volatility |
| 🎻 Returns Distribution | Violin plot of daily return distributions |
| 🔗 Correlation Heatmap | Pairwise return correlation matrix |
| 📅 Monthly Returns Heatmap | Calendar-style monthly return grid per ticker |
| 🕯️ Candlestick & Volume | OHLCV candlestick chart with volume bars |
| 📋 Metrics Table | Full metrics table with CSV download |

---

## 📐 Metrics Calculated

- **Total Return**: (P_end / P_start) − 1
- **Annualised Return**: geometric annualisation of total return
- **Annualised Volatility**: σ_daily × √252
- **Maximum Drawdown**: min(P_t / cummax(P) − 1)
- **Sharpe Ratio**: Ann. Return / Ann. Volatility (risk-free rate = 0)
- **Calmar Ratio**: Ann. Return / |Max Drawdown|
- **Win Rate**: proportion of trading days with positive return
- **Average Up/Down Day**: mean return on positive/negative days

---

## 🗂️ Data Cleaning Steps

When data is fetched from the API, the following cleaning steps are applied automatically in memory:

1. Parse date column to `datetime`; drop rows with invalid dates
2. Convert all price/volume columns to numeric; coerce errors to `NaN`
3. Remove rows where `close ≤ 0` (zero or negative prices are invalid)
4. Remove rows where `high < low` (structural sanity check)
5. Deduplicate by date (keep first occurrence)
6. Sort chronologically

---

## 🚀 Setup & Run

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Ensure the stock list file exists

```
stock-dashboard/
└── data/
    └── _all_a_stocks.csv   ← required (columns: symbol, name, exchange)
```

### 3. Run the app

```bash
streamlit run app.py
```

The app opens automatically at `http://localhost:8501`.

Enter ticker codes in the sidebar and click **✅ Apply** — data is fetched live.

---

## 📁 Project Structure

```
stock-dashboard/
├── app.py              # Main Streamlit application (live fetch + full dashboard)
├── requirements.txt    # Python dependencies
├── README.md           # This file
├── clean_data.py       # Offline batch cleaning script (optional, for local CSV mode)
├── data/
│   └── _all_a_stocks.csv   # A-share universe (symbol, name, exchange)
└── notebook/
    └── analysis.ipynb  # Python analytical workflow notebook
```

---

## ⚠️ Disclaimer

This tool is built for **educational purposes only** as part of ACC102 coursework. It does not constitute financial advice. All data is sourced from public APIs and may be subject to inaccuracies or delays.

---

## 📚 ACC102 Submission Info

- **Module**: ACC102 — 2nd Semester 2024-25
- **Track**: Track 4 — Interactive Data Analysis Tool
- **Platform**: Streamlit (local)
- **Data Source**: Tencent Finance / EastMoney Finance (live API), accessed April 2026
