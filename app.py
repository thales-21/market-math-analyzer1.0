from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from market_math_analyzer_v2 import (
    BASE_DIR,
    FORMULAS_FILE,
    WATCHLIST_FILE,
    build_top_summary,
    load_formulas,
    load_watchlist,
    run_analysis,
)


st.set_page_config(page_title="Market Math Analyzer", layout="wide")


@st.cache_data(ttl=300, show_spinner=False)
def get_analysis(period: str, interval: str) -> pd.DataFrame:
    return run_analysis(period=period, interval=interval)


@st.cache_data(show_spinner=False)
def read_text_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


@st.cache_data(show_spinner=False)
def current_watchlist() -> List[str]:
    return load_watchlist()


@st.cache_data(show_spinner=False)
def current_formulas() -> dict:
    return load_formulas()


st.title("Market Math Analyzer")
st.caption("Local watchlist dashboard for stocks and crypto using Yahoo Finance data.")


with st.sidebar:
    st.header("Settings")

    period = st.selectbox(
        "History period",
        options=["3mo", "6mo", "1y", "2y"],
        index=1,
    )

    interval = st.selectbox(
        "Data interval",
        options=["1d", "1h"],
        index=0,
    )

    min_entry_score = st.slider("Minimum entry score", min_value=0, max_value=100, value=0, step=5)

    decision_options = [
        "ALL",
        "HIGH PROBABILITY BUY",
        "BUY",
        "PULLBACK BUY",
        "OVEREXTENDED",
        "AVOID",
    ]
    selected_decision = st.selectbox("Decision filter", options=decision_options, index=0)

    refresh = st.button("Refresh data", use_container_width=True)

    st.divider()
    st.subheader("Project files")
    st.write(f"Folder: `{BASE_DIR}`")
    st.write(f"Watchlist file: `{WATCHLIST_FILE.name}`")
    st.write(f"Formulas file: `{FORMULAS_FILE.name}`")

    with st.expander("Watchlist preview", expanded=False):
        watchlist = current_watchlist()
        st.code("\n".join(watchlist) if watchlist else "No watchlist found.")

    with st.expander("Formulas preview", expanded=False):
        formulas_text = read_text_file(FORMULAS_FILE)
        st.code(formulas_text if formulas_text else "No formulas found.")


if refresh:
    st.cache_data.clear()

with st.spinner("Analyzing live market data..."):
    result = get_analysis(period=period, interval=interval)

if result.empty:
    st.warning("No results returned. Check your watchlist or internet connection.")
    st.stop()

filtered = result.copy()

if selected_decision != "ALL" and "decision" in filtered.columns:
    filtered = filtered[filtered["decision"] == selected_decision]

if "entry_score" in filtered.columns:
    filtered = filtered[filtered["entry_score"] >= min_entry_score]


summary_lines = build_top_summary(result, top_n=5)

col1, col2, col3 = st.columns([1.2, 1.2, 2.6])
with col1:
    st.metric("Tracked symbols", len(result))
with col2:
    buys = int(result["decision"].isin(["HIGH PROBABILITY BUY", "BUY", "PULLBACK BUY"]).sum()) if "decision" in result.columns else 0
    st.metric("Actionable setups", buys)
with col3:
    top_line = summary_lines[0] if summary_lines else "No current buy setups"
    st.metric("Top setup", top_line)


st.subheader("Top setups")
if summary_lines:
    for line in summary_lines:
        st.write(f"- {line}")
else:
    st.write("No buy setups right now.")


st.subheader("Results")

preferred_order = [
    "symbol",
    "price",
    "1d_%",
    "5d_%",
    "20d_%",
    "entry_score",
    "signal",
    "decision",
    "pullback_strength",
    "range_position",
    "score",
    "rsi_14",
    "macd",
    "macd_signal",
    "sma_20",
    "sma_50",
    "high_20",
    "low_20",
    "volume",
    "avg_volume_20",
    "notes",
]

existing_cols = [col for col in preferred_order if col in filtered.columns]
remaining_cols = [col for col in filtered.columns if col not in existing_cols]
display_df = filtered[existing_cols + remaining_cols].copy()

st.dataframe(display_df, use_container_width=True, hide_index=True)


st.subheader("Single symbol detail")
symbols = filtered["symbol"].dropna().tolist() if "symbol" in filtered.columns else []
if symbols:
    selected_symbol = st.selectbox("Choose a symbol", options=symbols)
    selected_row = filtered[filtered["symbol"] == selected_symbol].iloc[0]

    detail_cols = st.columns(4)
    metrics = [
        ("Price", selected_row.get("price", "-")),
        ("Entry score", selected_row.get("entry_score", "-")),
        ("Signal", selected_row.get("signal", "-")),
        ("Decision", selected_row.get("decision", "-")),
        ("1d %", selected_row.get("1d_%", "-")),
        ("5d %", selected_row.get("5d_%", "-")),
        ("20d %", selected_row.get("20d_%", "-")),
        ("RSI 14", selected_row.get("rsi_14", "-")),
    ]

    for idx, (label, value) in enumerate(metrics):
        detail_cols[idx % 4].metric(label, value)

    st.write("**Notes**")
    st.write(selected_row.get("notes", "-"))
else:
    st.write("No symbols available after filtering.")


csv_data = display_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download results as CSV",
    data=csv_data,
    file_name="market_math_results.csv",
    mime="text/csv",
)
