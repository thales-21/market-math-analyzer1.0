from __future__ import annotations

from pathlib import Path
from typing import Any, List, Tuple

import pandas as pd
import streamlit as st
import yfinance as yf

from market_math_analyzer_v2 import (
    BASE_DIR,
    FORMULAS_FILE,
    WATCHLIST_FILE,
    build_top_summary,
    load_watchlist,
    run_analysis,
)

st.set_page_config(page_title="Market Math Analyzer V3", layout="wide")

BURGUNDY = "#7A1F45"
BURGUNDY_SOFT = "#A14B73"
ROSE = "#D48AA7"
GOLD = "#D6B35A"
BG_TOP = "#F7F1F4"
BG_BOTTOM = "#EEF3FA"
CARD = "#FFFFFF"
CARD_ALT = "#F8FAFD"
TEXT = "#1F2430"
MUTED = "#5E6573"
BORDER = "rgba(122,31,69,0.20)"

CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC")
CRYPTO_KEYWORDS = {
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE",
    "HBAR", "ATOM", "BNB", "AVAX", "LINK",
}

st.markdown(
    """
    <style>

    /* App background */
    .stApp {
        background: linear-gradient(180deg, #F7F1F4 0%, #EEF3FA 100%);
        color: #111111;
    }

    /* Titles */
    .main-title {
        color: #111111;
    }

    .sub-title {
        color: #444444;
    }

    /* Metric cards (THIS fixes your numbers) */
    div[data-testid="stMetric"] {
        background: #FFFFFF;
        color: #000000 !important;
        border-radius: 14px;
        padding: 0.6rem;
        border: 1px solid rgba(0,0,0,0.1);
    }

    /* Metric LABEL */
    div[data-testid="stMetricLabel"] {
        color: #333333 !important;
        font-weight: 600;
    }

    /* Metric VALUE (RSI, price, etc) */
    div[data-testid="stMetricValue"] {
        color: #000000 !important;
        font-weight: 800;
        font-size: 1.2rem;
    }

    /* Data table (THIS fixes washed out rows) */
    .stDataFrame, .stDataFrame * {
        color: #000000 !important;
    }

    /* Dropdown + inputs */
    .stSelectbox, .stTextInput, .stTextArea {
        color: #000000 !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #F3E4EA 0%, #F6F2F8 100%);
    }

    /* Cards */
    .accent-card {
        background: #FFFFFF;
        border-left: 6px solid #7A1F45;
        color: #000000;
    }

    .accent-card-soft {
        background: #FFF9F0;
        border-left: 6px solid #D6B35A;
        color: #000000;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300, show_spinner=False)
def get_analysis(period: str, interval: str) -> pd.DataFrame:
    return run_analysis(period=period, interval=interval)


@st.cache_data(ttl=300, show_spinner=False)
def get_symbol_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.dropna().copy()
    if "Close" in df.columns:
        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
    return df


def read_text_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def save_watchlist(symbols: List[str]) -> None:
    cleaned: List[str] = []
    seen = set()

    for symbol in symbols:
        s = symbol.strip().upper()
        if s and s not in seen:
            cleaned.append(s)
            seen.add(s)

    content = "\n".join(cleaned)
    if content:
        content += "\n"

    WATCHLIST_FILE.write_text(content, encoding="utf-8")


def save_formulas(text: str) -> None:
    content = text.strip()
    if content:
        content += "\n"

    FORMULAS_FILE.write_text(content, encoding="utf-8")


def current_watchlist() -> List[str]:
    symbols = load_watchlist()
    if symbols:
        return symbols
    return [
        "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD",
        "HBAR-USD", "ATOM-USD", "BNB-USD", "AAPL", "MSFT", "NVDA", "TSLA",
        "AMZN", "META", "GOOGL", "SPY", "QQQ", "GLD", "SLV",
    ]


def is_crypto_symbol(symbol: str) -> bool:
    upper = symbol.upper()
    if upper.endswith(CRYPTO_SUFFIXES):
        return True
    token = upper.split("-")[0]
    return token in CRYPTO_KEYWORDS


def classify_group_outlook(df: pd.DataFrame, label: str) -> Tuple[str, str]:
    if df.empty:
        return f"{label}: NEUTRAL", "No symbols available in this group."

    avg_entry_score = float(df["entry_score"].mean()) if "entry_score" in df.columns else 0.0
    avg_20d = float(df["20d_%"].mean()) if "20d_%" in df.columns else 0.0
    avg_5d = float(df["5d_%"].mean()) if "5d_%" in df.columns else 0.0
    buys = int(df["decision"].isin(["HIGH PROBABILITY BUY", "BUY", "PULLBACK BUY"]).sum()) if "decision" in df.columns else 0
    avoids = int(df["decision"].isin(["AVOID", "OVEREXTENDED"]).sum()) if "decision" in df.columns else 0

    if avg_entry_score >= 45 and avg_20d > 0 and buys >= max(1, avoids):
        return f"{label}: BULLISH", "Breadth and medium-term structure lean constructive."
    if avg_entry_score <= 28 and avg_20d < 0 and avoids >= max(1, buys):
        return f"{label}: BEARISH", "Trend breadth leans defensive and rallies look less confirmed."
    if avg_5d < 0 < avg_20d:
        return f"{label}: BULLISH WITH PULLBACK RISK", "Higher-timeframe structure is intact, but near-term pressure is present."
    return f"{label}: MIXED", "Signals are split, which favors selectivity over broad aggression."


def decision_class(decision: str) -> str:
    if decision in {"HIGH PROBABILITY BUY", "BUY", "PULLBACK BUY"}:
        return "decision-buy"
    if decision in {"OVEREXTENDED"}:
        return "decision-watch"
    return "decision-avoid"


def build_share_text(result: pd.DataFrame, crypto_title: str, stock_title: str) -> str:
    lines = ["Market Math Analyzer update:", crypto_title, stock_title]
    summary = build_top_summary(result, top_n=5)

    if summary:
        lines.append("Top setups:")
        lines.extend([f"- {line}" for line in summary])
    else:
        lines.append("No strong buy setups right now.")

    if "decision" in result.columns:
        avoids = result[result["decision"] == "AVOID"]["symbol"].head(5).tolist()
        if avoids:
            lines.append("Avoid / weak zone:")
            lines.append("- " + ", ".join(avoids))

    lines.append("Built from live Yahoo Finance data in my custom analyzer.")
    return "\n".join(lines)


st.markdown('<div class="main-title">Market Math Analyzer V3</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Live watchlist intelligence with editable symbols, brighter styling, separate crypto and stock outlooks, charts, and share-ready summaries.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Controls")

    period = st.selectbox("History period", options=["3mo", "6mo", "1y", "2y"], index=2)
    interval = st.selectbox("Data interval", options=["1d", "1h"], index=0)
    min_entry_score = st.slider("Minimum entry score", min_value=0, max_value=100, value=0, step=5)

    decision_options = ["ALL", "HIGH PROBABILITY BUY", "BUY", "PULLBACK BUY", "OVEREXTENDED", "AVOID"]
    selected_decision = st.selectbox("Decision filter", options=decision_options, index=0)

    if st.button("Refresh market data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.subheader("Watchlist editor")

    preset_symbols = [
        "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD",
        "HBAR-USD", "ATOM-USD", "BNB-USD", "AVAX-USD", "LINK-USD",
        "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
        "MSTR", "COIN", "SPY", "QQQ", "GLD", "SLV", "IBIT",
    ]
    chosen_presets = st.multiselect("Add common tickers", options=preset_symbols)
    manual_ticker = st.text_input("Add ticker manually", placeholder="Example: MSTR or AVAX-USD")

    editable_watchlist = st.text_area("Current watchlist", value="\n".join(current_watchlist()), height=220)

    if st.button("Save watchlist", width="stretch"):
        lines = editable_watchlist.splitlines()
        if manual_ticker.strip():
            lines.append(manual_ticker.strip())
        lines.extend(chosen_presets)
        save_watchlist(lines)
        st.cache_data.clear()
        st.success("Watchlist saved.")

    st.divider()
    st.subheader("Formulas editor")
    formulas_text = st.text_area("Custom formulas", value=read_text_file(FORMULAS_FILE), height=180)

    if st.button("Save formulas", width="stretch"):
        save_formulas(formulas_text)
        st.cache_data.clear()
        st.success("Formulas saved.")

    st.divider()
    st.caption(f"Project folder: {BASE_DIR}")

with st.spinner("Analyzing live market data..."):
    result = get_analysis(period=period, interval=interval)

if result.empty:
    st.warning("No results returned. Check your watchlist, formulas, or internet connection.")
    st.stop()

result = result.copy()
result["asset_class"] = result["symbol"].apply(lambda s: "Crypto" if is_crypto_symbol(str(s)) else "Stock / ETF")

filtered = result.copy()
if selected_decision != "ALL" and "decision" in filtered.columns:
    filtered = filtered[filtered["decision"] == selected_decision]
if "entry_score" in filtered.columns:
    filtered = filtered[filtered["entry_score"] >= min_entry_score]

crypto_df = result[result["asset_class"] == "Crypto"].copy()
stock_df = result[result["asset_class"] == "Stock / ETF"].copy()

crypto_title, crypto_detail = classify_group_outlook(crypto_df, "Crypto outlook")
stock_title, stock_detail = classify_group_outlook(stock_df, "Stock outlook")

summary_lines = build_top_summary(result, top_n=5)
share_text = build_share_text(result, crypto_title, stock_title)

top1, top2, top3, top4 = st.columns(4)
with top1:
    st.metric("Tracked symbols", len(result))
with top2:
    actionable = int(result["decision"].isin(["HIGH PROBABILITY BUY", "BUY", "PULLBACK BUY"]).sum()) if "decision" in result.columns else 0
    st.metric("Actionable setups", actionable)
with top3:
    avg_score = round(float(result["entry_score"].mean()), 1) if "entry_score" in result.columns else 0.0
    st.metric("Average entry score", avg_score)
with top4:
    st.metric("Crypto / Stock split", f"{len(crypto_df)} / {len(stock_df)}")

card1, card2 = st.columns(2)
with card1:
    st.markdown(
        f'<div class="accent-card"><strong>{crypto_title}</strong><br><span class="small-note">{crypto_detail}</span></div>',
        unsafe_allow_html=True,
    )
with card2:
    st.markdown(
        f'<div class="accent-card-soft"><strong>{stock_title}</strong><br><span class="small-note">{stock_detail}</span></div>',
        unsafe_allow_html=True,
    )

left, right = st.columns([1.05, 1.25])
with left:
    st.subheader("Top setups")
    if summary_lines:
        for line in summary_lines:
            st.write(f"- {line}")
    else:
        st.write("No buy setups right now.")

with right:
    st.subheader("Share with friends")
    st.caption("Copy this summary into a text message, Slack, or social post.")
    st.text_area("Share-ready summary", value=share_text, height=220)

st.subheader("Results")

preferred_order = [
    "symbol", "asset_class", "price", "1d_%", "5d_%", "20d_%",
    "entry_score", "signal", "decision", "pullback_strength",
    "range_position", "score", "rsi_14", "macd", "macd_signal",
    "sma_20", "sma_50", "high_20", "low_20", "volume",
    "avg_volume_20", "notes",
]
existing_cols = [col for col in preferred_order if col in filtered.columns]
remaining_cols = [col for col in filtered.columns if col not in existing_cols]
display_df = filtered[existing_cols + remaining_cols].copy()

st.dataframe(display_df, width="stretch", hide_index=True)

st.subheader("Single symbol detail")
symbols = filtered["symbol"].dropna().tolist() if "symbol" in filtered.columns else []

if symbols:
    selected_symbol = st.selectbox("Choose a symbol", options=symbols)
    selected_row = filtered[filtered["symbol"] == selected_symbol].iloc[0]
    history = get_symbol_history(selected_symbol, period=period, interval=interval)

    d1, d2, d3, d4 = st.columns(4)
    detail_metrics = [
        ("Price", selected_row.get("price", "-")),
        ("Entry score", selected_row.get("entry_score", "-")),
        ("Signal", selected_row.get("signal", "-")),
        ("Decision", selected_row.get("decision", "-")),
        ("1d %", selected_row.get("1d_%", "-")),
        ("5d %", selected_row.get("5d_%", "-")),
        ("20d %", selected_row.get("20d_%", "-")),
        ("RSI 14", selected_row.get("rsi_14", "-")),
    ]
    columns = [d1, d2, d3, d4]
    for idx, (label, value) in enumerate(detail_metrics):
        columns[idx % 4].metric(label, value)

    decision_text = str(selected_row.get("decision", "-"))
    st.markdown(
        f'<div class="accent-card"><span class="{decision_class(decision_text)}">{decision_text}</span><br><span class="small-note">{selected_row.get("notes", "-")}</span></div>',
        unsafe_allow_html=True,
    )

    if not history.empty and "Close" in history.columns:
        st.write("**Price chart**")
        chart_df = history[["Close"]].copy()
        if "SMA20" in history.columns:
            chart_df["SMA20"] = history["SMA20"]
        if "SMA50" in history.columns:
            chart_df["SMA50"] = history["SMA50"]
        st.line_chart(chart_df, height=340)
else:
    st.write("No symbols available after filtering.")

csv_data = display_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download results as CSV",
    data=csv_data,
    file_name="market_math_results_v3.csv",
    mime="text/csv",
    width="stretch",
)