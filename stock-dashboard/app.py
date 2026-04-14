"""
A-Share Risk-Return Dashboard
ACC102 | Track 4 — Interactive Data Analysis Tool

Fetches live OHLCV data from Tencent / EastMoney on demand.
Only requires: stock-dashboard/data/_all_a_stocks.csv
"""

import os
import time
from datetime import datetime, date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="A-Share Risk-Return Dashboard",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
<style>
[data-testid="stAppViewContainer"] {background:#0f1226;color:#e6e8ef;}
[data-testid="stSidebar"]          {background:#161a33;}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span     {color:#d9dcee !important;}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea {color:#111 !important;background:#f2f4ff !important;}
.kpi {background:#1d2142;border:1px solid #2d3468;border-radius:12px;
      padding:16px 12px;text-align:center;margin-bottom:4px;}
.kpi b     {font-size:1.25rem;display:block;margin-top:4px;}
.kpi small {font-size:0.85rem;color:#aab0cc;}
[data-testid="stSidebar"] .stButton > button {
  border:1px solid #3b4b8f !important;
  background:linear-gradient(180deg,#2a3c89,#1f2f75) !important;
  color:#f8fbff !important;
  font-weight:700 !important;
  box-shadow:0 0 0 1px rgba(120,160,255,.25), 0 6px 16px rgba(0,0,0,.25) !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  filter:brightness(1.12);
}
[data-testid="stTabs"] [role="tablist"] {
  gap: 8px;
  flex-wrap: wrap !important;
  overflow: visible !important;
  white-space: normal !important;
}
[data-testid="stTabs"] [role="tab"] {
  min-height: 38px !important;
}
[data-testid="stTabs"] [role="tab"] {
  color: #cfd6ff !important;
  background: rgba(76, 95, 185, 0.18) !important;
  border: 1px solid rgba(111, 131, 227, 0.45) !important;
  border-radius: 10px !important;
  padding: 6px 12px !important;
  font-weight: 600 !important;
}
[data-testid="stTabs"] [role="tab"]:hover {
  background: rgba(96, 120, 235, 0.30) !important;
  color: #ffffff !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
  color: #ffffff !important;
  background: linear-gradient(180deg, #3b56c8, #2a3f99) !important;
  border: 1px solid #8ea3ff !important;
  box-shadow: 0 0 0 1px rgba(142, 163, 255, 0.35), 0 6px 16px rgba(0,0,0,.25) !important;
}
.stDownloadButton > button {
  border:1px solid #3b4b8f !important;
  background:linear-gradient(180deg,#2a3c89,#1f2f75) !important;
  color:#f8fbff !important;
  font-weight:700 !important;
  box-shadow:0 0 0 1px rgba(120,160,255,.25), 0 6px 16px rgba(0,0,0,.25) !important;
}
.stDownloadButton > button:hover {
  filter:brightness(1.12);
}
</style>
""",
    unsafe_allow_html=True,
)

# ─── Constants ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_LIST_CSV = os.path.join(BASE_DIR, "data", "_all_a_stocks.csv")
RISK_FREE = 0.0

EASTMONEY_KLINE_URLS = [
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    "http://push2his.eastmoney.com/api/qt/stock/kline/get",
]
EASTMONEY_UT = "fa5fd1943c7b386f172d6893dbfba10b"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json,text/plain,*/*",
}


# ─── Stock list helpers ───────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_stock_list() -> pd.DataFrame:
    """Load _all_a_stocks.csv → DataFrame with columns: symbol, name, exchange."""
    if not os.path.exists(STOCK_LIST_CSV):
        return pd.DataFrame(columns=["symbol", "name", "exchange"])
    df = pd.read_csv(STOCK_LIST_CSV, dtype=str)
    df.columns = [c.lower().strip() for c in df.columns]
    df["symbol"] = df["symbol"].str.zfill(6)
    return df.dropna(subset=["symbol", "exchange"])


def infer_exchange(code: str) -> str:
    """Infer exchange from 6-digit A-share code if not in the list."""
    c = code.zfill(6)
    if c.startswith(("6", "5", "9")):
        return "SH"
    return "SZ"


# ─── Fetch functions (adapted from fetch_eastmoney_a_stocks.py) ───────────────

def _make_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False   # bypass system proxy
    s.headers.update(HEADERS)
    return s


def _fetch_tencent(session, symbol: str, exchange: str,
                   start: str, end: str, timeout: int = 15) -> list[dict]:
    """Tencent Finance kline (preferred source)."""
    tsym = f"sz{symbol}" if exchange.upper() == "SZ" else f"sh{symbol}"
    param = f"{tsym},day,{start},{end},640,qfq"
    resp = session.get(TENCENT_KLINE_URL, params={"param": param}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    klines = (data.get(tsym) or {})
    klines = klines.get("qfqday") or klines.get("day") or []
    rows = []
    for k in klines:
        if len(k) >= 6:
            rows.append({"date": str(k[0]), "open": str(k[1]), "high": str(k[3]),
                         "low": str(k[4]), "close": str(k[2]), "volume": str(k[5])})
    return rows


def _fetch_eastmoney(session, symbol: str, exchange: str,
                     beg: str, end: str, timeout: int = 15) -> list[dict]:
    """EastMoney Finance kline (fallback source)."""
    secid = f"0.{symbol}" if exchange.upper() == "SZ" else f"1.{symbol}"
    params = {
        "secid": secid, "ut": EASTMONEY_UT,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": "101", "fqt": "0", "beg": beg, "end": end,
    }
    last_err = None
    for url in EASTMONEY_KLINE_URLS:
        try:
            resp = session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            klines = (resp.json().get("data") or {}).get("klines") or []
            rows = []
            for k in klines:
                p = k.split(",")
                if len(p) >= 6:
                    rows.append({"date": p[0], "open": p[1], "high": p[3],
                                 "low": p[4], "close": p[2], "volume": p[5]})
            return rows
        except Exception as e:
            last_err = e
    raise RuntimeError(f"EastMoney fetch failed: {last_err}")


def fetch_ohlcv(symbol: str, exchange: str,
                start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch daily OHLCV, try Tencent first then EastMoney.
    start_date / end_date: 'YYYY-MM-DD'
    Returns a cleaned DataFrame indexed by date.
    """
    session = _make_session()
    rows: list[dict] = []

    # Tencent
    try:
        rows = _fetch_tencent(session, symbol, exchange, start_date, end_date)
    except Exception:
        rows = []

    # EastMoney fallback
    if not rows:
        beg = start_date.replace("-", "")
        end = end_date.replace("-", "")
        rows = _fetch_eastmoney(session, symbol, exchange, beg, end)

    if not rows:
        raise ValueError(f"No data returned for {symbol} ({exchange})")

    # Deduplicate & sort
    dedup: dict[str, dict] = {}
    for r in rows:
        dedup[r["date"]] = r
    rows = [dedup[d] for d in sorted(dedup)]

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Data cleaning ---
    df = df.dropna(subset=["date", "close"])
    df = df[df["close"] > 0]                          # remove zero/negative prices
    df = df[df["high"] >= df["low"]]                  # sanity: high >= low
    df = df.drop_duplicates("date").sort_values("date")
    return df.set_index("date")[["open", "high", "low", "close", "volume"]]


# ─── Metrics ──────────────────────────────────────────────────────────────────

def calc_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    rets = prices.pct_change().dropna()
    rows = []
    for c in prices.columns:
        p = prices[c].dropna()
        if len(p) < 2:
            continue
        r = rets[c].dropna()
        total = p.iloc[-1] / p.iloc[0] - 1
        n = len(p)
        ann_ret = (1 + total) ** (252 / n) - 1
        ann_vol = r.std() * np.sqrt(252)
        dd = p / p.cummax() - 1
        max_dd = dd.min()
        sharpe = (ann_ret - RISK_FREE) / ann_vol if ann_vol > 0 else np.nan
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else np.nan
        win_rate = (r > 0).mean()
        avg_up = r[r > 0].mean() if (r > 0).any() else np.nan
        avg_dn = r[r < 0].mean() if (r < 0).any() else np.nan
        rows.append({
            "Ticker": c,
            "Total Return": total,
            "Ann. Return": ann_ret,
            "Ann. Volatility": ann_vol,
            "Max Drawdown": max_dd,
            "Sharpe": sharpe,
            "Calmar": calmar,
            "Win Rate": win_rate,
            "Avg Up Day": avg_up,
            "Avg Down Day": avg_dn,
        })
    return pd.DataFrame(rows).set_index("Ticker")


# ─── Chart functions ──────────────────────────────────────────────────────────

def fig_price(prices):
    norm = prices / prices.iloc[0] * 100
    fig = go.Figure()
    for c in norm.columns:
        fig.add_trace(go.Scatter(x=norm.index, y=norm[c], mode="lines", name=c))
    fig.update_layout(template="plotly_dark", title="Normalised Price (Base = 100)",
                      height=460, hovermode="x unified", yaxis_title="Indexed Price")
    return fig


def fig_cumret(prices):
    cumret = (prices / prices.iloc[0] - 1) * 100
    fig = go.Figure()
    for c in cumret.columns:
        fig.add_trace(go.Scatter(x=cumret.index, y=cumret[c], mode="lines", name=c))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(template="plotly_dark", title="Cumulative Return (%)",
                      height=460, hovermode="x unified", yaxis_title="Cumulative Return %")
    return fig


def fig_drawdown(prices):
    fig = go.Figure()
    for c in prices.columns:
        dd = (prices[c] / prices[c].cummax() - 1) * 100
        fig.add_trace(go.Scatter(x=dd.index, y=dd, mode="lines", name=c, fill="tozeroy"))
    fig.update_layout(template="plotly_dark", title="Drawdown Curves (%)",
                      height=460, hovermode="x unified", yaxis_title="Drawdown %")
    return fig


def fig_rolling_vol(prices, window=20):
    rv = prices.pct_change().rolling(window).std() * np.sqrt(252) * 100
    fig = go.Figure()
    for c in rv.columns:
        fig.add_trace(go.Scatter(x=rv.index, y=rv[c], mode="lines", name=c))
    fig.update_layout(template="plotly_dark",
                      title=f"Rolling Annualised Volatility ({window}-day window, %)",
                      height=460, hovermode="x unified", yaxis_title="Ann. Volatility %")
    return fig


def fig_scatter(metrics):
    fig = px.scatter(
        metrics.reset_index(),
        x="Ann. Volatility", y="Ann. Return",
        text="Ticker", color="Sharpe",
        color_continuous_scale="RdYlGn",
        template="plotly_dark",
        title="Risk-Return Scatter (colour = Sharpe Ratio)",
    )
    fig.update_traces(textposition="top center", marker=dict(size=14))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(height=480,
                      xaxis_tickformat=".0%", yaxis_tickformat=".0%")
    return fig


def fig_violin(prices):
    rets = prices.pct_change().dropna() * 100
    fig = go.Figure()
    for c in rets.columns:
        fig.add_trace(go.Violin(y=rets[c], name=c, box_visible=True,
                                meanline_visible=True, points="outliers"))
    fig.update_layout(template="plotly_dark",
                      title="Daily Returns Distribution (Violin Plot, %)",
                      height=480, yaxis_title="Daily Return %")
    return fig


def fig_corr(prices):
    corr = prices.pct_change().dropna().corr()
    fig = px.imshow(corr, text_auto=".2f",
                    color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                    template="plotly_dark",
                    title="Return Correlation Heatmap")
    fig.update_layout(height=460)
    return fig


def fig_monthly(prices, code):
    r = prices[code].pct_change().dropna()
    monthly = r.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100
    df = monthly.reset_index()
    df.columns = ["date", "ret"]
    df["year"] = df["date"].dt.year.astype(str)
    df["month"] = df["date"].dt.month
    pivot = df.pivot(index="year", columns="month", values="ret")
    pivot.columns = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    fig = px.imshow(pivot, text_auto=".1f",
                    color_continuous_scale="RdYlGn",
                    template="plotly_dark",
                    title=f"Monthly Returns Heatmap — {code} (%)")
    fig.update_layout(height=340)
    return fig


def fig_candle(df, code):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25])
    fig.add_trace(
        go.Candlestick(x=df.index, open=df["open"], high=df["high"],
                       low=df["low"], close=df["close"], name=code),
        row=1, col=1,
    )
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume"), row=2, col=1)
    fig.update_layout(template="plotly_dark",
                      title=f"Candlestick & Volume — {code}",
                      xaxis_rangeslider_visible=False, height=540)
    return fig


# ─── Load stock list ──────────────────────────────────────────────────────────
stock_df = load_stock_list()
# Build lookup: symbol → (name, exchange)
sym_lookup: dict[str, tuple[str, str]] = {}
if not stock_df.empty:
    for _, row in stock_df.iterrows():
        sym_lookup[row["symbol"]] = (row.get("name", "—"), row.get("exchange", "SZ"))

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Settings")
    st.caption(f"Stock universe: **{len(sym_lookup)}** A-shares loaded from `_all_a_stocks.csv`")

    default_codes = st.session_state.get("last_input", "000001,000002,600519,300750,601318")
    code_input = st.text_area(
        "Ticker codes (comma-separated)",
        value=default_codes,
        height=90,
        help="e.g. 000001,600519,300750",
        key="code_input",
    )

    col_a, col_b = st.columns(2)
    apply_btn = col_a.button("✅ Apply", use_container_width=True, type="primary")
    clear_btn = col_b.button("🗑️ Clear Cache", use_container_width=True)

    start_date = st.date_input("Start date", value=date(2022, 1, 1),
                               min_value=date(2015, 1, 1), max_value=date.today())
    end_date   = st.date_input("End date",   value=date.today(),
                               min_value=date(2015, 1, 1), max_value=date.today())
    roll_window = st.slider("Rolling volatility window (days)", 5, 60, 20, 5)
    max_tickers = st.slider("Max tickers to display", 2, 20, 10)

    st.markdown("---")
    st.markdown(f"### 📋 Available Stocks ({len(sym_lookup)} total)")
    if sym_lookup:
        list_df = pd.DataFrame([
            {"Code": c, "Name": n, "Exchange": e}
            for c, (n, e) in sorted(sym_lookup.items())
        ])
        st.dataframe(list_df, use_container_width=True, height=320)
    else:
        st.warning("Could not load `_all_a_stocks.csv`. Place it in `stock-dashboard/data/`.")

# ─── Cache management ─────────────────────────────────────────────────────────
if "ohlcv_cache" not in st.session_state:
    st.session_state["ohlcv_cache"] = {}

if clear_btn:
    st.session_state["ohlcv_cache"] = {}
    st.session_state.pop("selected_codes", None)
    st.success("Cache cleared.")
    st.rerun()

# ─── Parse & apply ticker selection ──────────────────────────────────────────
def parse_codes(raw: str) -> list[str]:
    return list(dict.fromkeys(
        x.strip().zfill(6)
        for x in raw.replace("\n", ",").split(",")
        if x.strip()
    ))

if apply_btn:
    codes_in = parse_codes(code_input)[:max_tickers]
    st.session_state["selected_codes"] = codes_in
    st.session_state["last_input"] = code_input
    st.session_state["fetch_start"] = str(start_date)
    st.session_state["fetch_end"]   = str(end_date)
    st.rerun()

if "selected_codes" not in st.session_state:
    st.session_state["selected_codes"] = parse_codes(code_input)[:max_tickers]
    st.session_state["fetch_start"] = str(start_date)
    st.session_state["fetch_end"]   = str(end_date)

selected_codes = st.session_state["selected_codes"]
fetch_start    = st.session_state.get("fetch_start", str(start_date))
fetch_end      = st.session_state.get("fetch_end",   str(end_date))

# ─── Page header ──────────────────────────────────────────────────────────────
st.title("A-Share Risk-Return Dashboard")
st.caption(
    "Live data fetched from Tencent Finance / EastMoney on demand. "
    "Enter ticker codes on the left and click **✅ Apply**."
)

if not selected_codes:
    st.info("Enter at least one ticker code in the sidebar and click ✅ Apply.")
    st.stop()

# ─── Fetch data (with in-session cache) ──────────────────────────────────────
cache: dict = st.session_state["ohlcv_cache"]
ohlc_map: dict[str, pd.DataFrame] = {}
fetch_errors: list[str] = []

to_fetch = [c for c in selected_codes if c not in cache]

if to_fetch:
    progress_bar = st.progress(0, text="Fetching data…")
    for i, code in enumerate(to_fetch):
        name, exchange = sym_lookup.get(code, ("Unknown", infer_exchange(code)))
        progress_bar.progress(
            (i + 1) / len(to_fetch),
            text=f"Fetching {code} ({name}) from {exchange}…",
        )
        try:
            df = fetch_ohlcv(code, exchange, fetch_start, fetch_end)
            cache[code] = df
            time.sleep(0.08)   # polite delay
        except Exception as e:
            fetch_errors.append(f"**{code}** ({name}): {e}")
    progress_bar.empty()

for code in selected_codes:
    if code in cache:
        ohlc_map[code] = cache[code]
    elif code not in [c for c in fetch_errors if c.startswith(f"**{code}**")]:
        fetch_errors.append(f"**{code}**: not in cache (fetch may have failed)")

if fetch_errors:
    st.warning("Some tickers could not be fetched:\n\n- " + "\n- ".join(fetch_errors))

if not ohlc_map:
    st.error("No data loaded. Check your ticker codes or network connection.")
    st.stop()

# ─── Build close-price matrix ─────────────────────────────────────────────────
prices = (
    pd.concat([df["close"].rename(c) for c, df in ohlc_map.items()], axis=1)
    .sort_index().ffill().dropna(how="all")
)

if len(prices) < 10:
    st.error("Insufficient price data (need at least 10 trading days). Try a wider date range.")
    st.stop()

metrics = calc_metrics(prices)
codes   = list(prices.columns)

# ─── KPI Cards ────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.markdown(
    f"<div class='kpi'>📈 Top Total Return<b>{metrics['Total Return'].idxmax()}</b>"
    f"<small>{metrics['Total Return'].max():.1%}</small></div>",
    unsafe_allow_html=True,
)
c2.markdown(
    f"<div class='kpi'>🛡️ Lowest Volatility<b>{metrics['Ann. Volatility'].idxmin()}</b>"
    f"<small>{metrics['Ann. Volatility'].min():.1%}</small></div>",
    unsafe_allow_html=True,
)
c3.markdown(
    f"<div class='kpi'>🕳️ Deepest Drawdown<b>{metrics['Max Drawdown'].idxmin()}</b>"
    f"<small>{metrics['Max Drawdown'].min():.1%}</small></div>",
    unsafe_allow_html=True,
)
c4.markdown(
    f"<div class='kpi'>⭐ Best Sharpe<b>{metrics['Sharpe'].idxmax()}</b>"
    f"<small>{metrics['Sharpe'].max():.2f}</small></div>",
    unsafe_allow_html=True,
)
st.markdown("")

st.markdown("---")

# ─── Chart tabs ───────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📈 Normalised Price",
    "📊 Cumulative Return",
    "📉 Drawdown",
    "🌊 Rolling Volatility",
    "🎯 Risk-Return Scatter",
    "🎻 Return Distribution",
    "🔗 Correlation",
    "📅 Monthly Heatmap",
    "🕯️ Candlestick",
    "📋 Metrics Table",
])

with tabs[0]:
    st.markdown("#### Normalised Price Trend")
    st.plotly_chart(fig_price(prices), use_container_width=True)
    st.caption(
        "All stocks are rebased to 100 at the start date for a fair comparison. "
        "A steeper slope indicates stronger performance; staying below 100 means an overall loss."
    )

with tabs[1]:
    st.markdown("#### Cumulative Return (%)")
    st.plotly_chart(fig_cumret(prices), use_container_width=True)
    st.caption(
        "Direct percentage cumulative return over the period. "
        "Above zero = profit; below zero = loss. Equivalent to the normalised chart minus 100."
    )

with tabs[2]:
    st.markdown("#### Drawdown Curves")
    st.plotly_chart(fig_drawdown(prices), use_container_width=True)
    st.caption(
        "Drawdown = decline from the most recent peak (closer to 0 is better). "
        "The deepest point is the Maximum Drawdown — a key measure of downside risk."
    )

with tabs[3]:
    st.markdown(f"#### Rolling Annualised Volatility ({roll_window}-day)")
    st.plotly_chart(fig_rolling_vol(prices, roll_window), use_container_width=True)
    st.caption(
        f"Uses a {roll_window}-day rolling window to show how risk evolved over time. "
        "Volatility spikes usually correspond to market events, policy shocks, or earnings surprises."
    )

with tabs[4]:
    st.markdown("#### Risk-Return Scatter (Annualised)")
    st.plotly_chart(fig_scatter(metrics), use_container_width=True)
    st.caption(
        "X-axis = annualised volatility (risk); Y-axis = annualised return (reward). "
        "Ideal: upper-left (high return, low risk). Worst: lower-right (low return, high risk). "
        "Colour = Sharpe Ratio."
    )

with tabs[5]:
    st.markdown("#### Daily Return Distribution (Violin Plot)")
    st.plotly_chart(fig_violin(prices), use_container_width=True)
    st.caption(
        "Shows the distribution shape of daily returns. Wider violin = higher frequency at that return level. "
        "Thick tails indicate fat-tail risk — large gains or losses occur more often than a normal distribution predicts."
    )

with tabs[6]:
    st.markdown("#### Return Correlation Heatmap")
    if len(codes) >= 2:
        st.plotly_chart(fig_corr(prices), use_container_width=True)
        st.caption(
            "Deep red = strong positive correlation (move together). Deep blue = negative correlation (hedge effect). "
            "For portfolio construction, combining low-correlation stocks reduces overall risk."
        )
    else:
        st.info("At least 2 tickers are required to generate a correlation heatmap.")

with tabs[7]:
    st.markdown("#### Monthly Returns Calendar Heatmap")
    mc_code = st.selectbox("Select ticker", codes, key="monthly_sel")
    st.plotly_chart(fig_monthly(prices, mc_code), use_container_width=True)
    st.caption(
        "Each cell = that month's total return (green = positive, red = negative). "
        "Useful for identifying seasonal patterns or spotting months with abnormal performance."
    )

with tabs[8]:
    st.markdown("#### Candlestick & Volume Chart")
    candle_code = st.selectbox("Select ticker", codes, key="candle_sel")
    st.plotly_chart(fig_candle(ohlc_map[candle_code], candle_code), use_container_width=True)
    st.caption(
        "Candlestick shows open/high/low/close price structure. Volume bars confirm trend strength. "
        "High-volume up-days signal strong bullish sentiment; high-volume down-days signal bearish pressure."
    )

with tabs[9]:
    st.markdown("#### Risk-Return Metrics Summary")
    fmt = {
        "Total Return": "{:.2%}", "Ann. Return": "{:.2%}",
        "Ann. Volatility": "{:.2%}", "Max Drawdown": "{:.2%}",
        "Sharpe": "{:.2f}", "Calmar": "{:.2f}",
        "Win Rate": "{:.1%}", "Avg Up Day": "{:.2%}", "Avg Down Day": "{:.2%}",
    }
    st.dataframe(metrics.style.format(fmt), use_container_width=True)
    st.caption(
        "Sharpe = Ann. Return / Ann. Volatility (higher is better). "
        "Calmar = Ann. Return / |Max Drawdown| (higher is better). "
        "Win Rate = proportion of trading days with positive return. "
        "Evaluate stocks on multiple metrics, not total return alone."
    )
    out = metrics.reset_index().to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download Metrics CSV",
        out,
        file_name=f"metrics_{datetime.now().date()}.csv",
        mime="text/csv",
    )
