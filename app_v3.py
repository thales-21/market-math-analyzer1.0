from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pandas as pd
import streamlit as st
import yfinance as yf

from market_math_analyzer_v2 import (
    BASE_DIR,
    FORMULAS_FILE,
    WATCHLIST_FILE,
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
    .stApp {
        background: linear-gradient(180deg, #F7F1F4 0%, #EEF3FA 100%);
        color: #111111;
    }

    .main-title {
        color: #111111;
        font-size: 2rem;
        font-weight: 800;
        margin-bottom: 0.15rem;
    }

    .sub-title {
        color: #444444;
        margin-bottom: 1rem;
    }

    div[data-testid="stMetric"] {
        background: #FFFFFF;
        color: #000000 !important;
        border-radius: 14px;
        padding: 0.6rem;
        border: 1px solid rgba(0,0,0,0.1);
    }

    div[data-testid="stMetricLabel"] {
        color: #333333 !important;
        font-weight: 600;
    }

    div[data-testid="stMetricValue"] {
        color: #000000 !important;
        font-weight: 800;
        font-size: 1.2rem;
    }

    .stDataFrame, .stDataFrame * {
        color: #000000 !important;
    }

    .stSelectbox, .stTextInput, .stTextArea {
        color: #000000 !important;
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #F3E4EA 0%, #F6F2F8 100%);
    }

    .accent-card {
        background: #FFFFFF;
        border-left: 6px solid #7A1F45;
        color: #000000;
        border-radius: 14px;
        padding: 0.9rem 1rem;
    }

    .accent-card-soft {
        background: #FFF9F0;
        border-left: 6px solid #D6B35A;
        color: #000000;
        border-radius: 14px;
        padding: 0.9rem 1rem;
    }

    .decision-buy {
        color: #126b3d;
        font-weight: 800;
    }

    .decision-watch {
        color: #8a5b00;
        font-weight: 800;
    }

    .decision-avoid {
        color: #a11b2b;
        font-weight: 800;
    }

    .small-note {
        color: #4a4a4a;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

ASSET_CONFIG = {
    "BTC-USD": {
        "label": "Bitcoin",
        "preferred_buy_price": 71000.0,
        "max_chase_pct": 0.05,
        "hard_overextended_pct": 0.10,
        "rsi_buy_min": 38,
        "rsi_buy_max": 58,
        "rsi_hot": 67,
        "volatility_tolerance": 0.045,
    },
    "SOL-USD": {
        "label": "Solana",
        "preferred_buy_price": 81.0,
        "max_chase_pct": 0.06,
        "hard_overextended_pct": 0.12,
        "rsi_buy_min": 36,
        "rsi_buy_max": 60,
        "rsi_hot": 70,
        "volatility_tolerance": 0.07,
    },
}

DEFAULT_PULLBACK_CONFIG = {
    "label": "Asset",
    "preferred_buy_price": 0.0,
    "max_chase_pct": 0.05,
    "hard_overextended_pct": 0.10,
    "rsi_buy_min": 40,
    "rsi_buy_max": 58,
    "rsi_hot": 68,
    "volatility_tolerance": 0.06,
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def pct_distance(current_price: float, anchor_price: float) -> float:
    if not anchor_price:
        return 0.0
    return (current_price - anchor_price) / anchor_price


def safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def format_value(value, is_percent: bool = False) -> str:
    if value is None or pd.isna(value):
        return "-"
    try:
        f = float(value)
    except Exception:
        return str(value)
    if is_percent:
        return f"{f:.2f}%"
    if abs(f) >= 1000:
        return f"{f:,.2f}"
    return f"{f:.2f}"


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
    required = {"High", "Low", "Close"}
    if not required.issubset(df.columns):
        return df

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    df["RSI14"] = 100 - (100 / (1 + rs))
    df["RSI14"] = df["RSI14"].fillna(50.0)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = close.ewm(span=21, adjust=False).mean()

    prev_close = close.shift(1)
    tr_components = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    )
    tr = tr_components.max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()
    df["ATR_PCT"] = (df["ATR14"] / close).replace([pd.NA, pd.NaT], 0.0)

    if "Volume" in df.columns:
        df["VOL_AVG20"] = df["Volume"].rolling(20).mean()
        df["VOLUME_RATIO"] = df["Volume"] / df["VOL_AVG20"]
    else:
        df["VOL_AVG20"] = pd.NA
        df["VOLUME_RATIO"] = pd.NA

    df["LOW20"] = low.rolling(20).min()
    df["LOW60"] = low.rolling(60).min()
    df["HIGH20"] = high.rolling(20).max()

    return df.dropna(how="all")


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


def label_strength(score: float) -> str:
    if score >= 75:
        return "Strong"
    if score >= 55:
        return "Moderate"
    if score >= 40:
        return "Mixed"
    return "Weak"


def infer_dynamic_buy_price(symbol: str, history: pd.DataFrame, current_price: float) -> float:
    cfg = {**DEFAULT_PULLBACK_CONFIG, **ASSET_CONFIG.get(symbol, {})}
    manual_preferred = safe_float(cfg.get("preferred_buy_price"), current_price)

    if history.empty or "Close" not in history.columns:
        return manual_preferred if manual_preferred > 0 else current_price

    last = history.iloc[-1]
    low20 = safe_float(last.get("LOW20"), current_price * 0.94)
    low60 = safe_float(last.get("LOW60"), low20)
    ema21 = safe_float(last.get("EMA21"), current_price)
    atr_pct = safe_float(last.get("ATR_PCT"), 0.03)

    adaptive_support = (low20 * 0.50) + (low60 * 0.20) + (ema21 * 0.30)

    if manual_preferred <= 0:
        preferred = adaptive_support
    else:
        if adaptive_support > manual_preferred * 1.03:
            preferred = adaptive_support
        elif adaptive_support < manual_preferred * 0.92:
            preferred = (manual_preferred * 0.60) + (adaptive_support * 0.40)
        else:
            preferred = (manual_preferred * 0.35) + (adaptive_support * 0.65)

    band_adjustment = 1 - min(max(atr_pct * 0.35, 0.0), 0.03)
    preferred *= band_adjustment

    ceiling = current_price * 0.995
    floor = current_price * 0.75
    preferred = clamp(preferred, floor, ceiling)
    return round(preferred, 2)


def analyze_pullback_setup(
    symbol: str,
    current_price: float,
    rsi: float,
    macd: float,
    macd_signal: float,
    preferred_buy: float,
    atr_pct: float | None = None,
    volume_ratio: float | None = None,
) -> dict:
    cfg = {**DEFAULT_PULLBACK_CONFIG, **ASSET_CONFIG.get(symbol, {})}
    max_chase_pct = safe_float(cfg.get("max_chase_pct"), 0.05)
    hard_overextended_pct = safe_float(cfg.get("hard_overextended_pct"), 0.10)
    rsi_buy_min = safe_float(cfg.get("rsi_buy_min"), 38)
    rsi_buy_max = safe_float(cfg.get("rsi_buy_max"), 58)
    rsi_hot = safe_float(cfg.get("rsi_hot"), 67)
    volatility_tolerance = safe_float(cfg.get("volatility_tolerance"), 0.05)

    distance_from_buy = pct_distance(current_price, preferred_buy)

    trend_score = 50
    if macd > macd_signal:
        trend_score += 15
    else:
        trend_score -= 15

    if macd > 0:
        trend_score += 10
    else:
        trend_score -= 10

    momentum_score = 50
    if rsi_buy_min <= rsi <= rsi_buy_max:
        momentum_score += 20
    elif rsi < rsi_buy_min:
        momentum_score -= 10
    elif rsi > rsi_hot:
        momentum_score -= 20
    else:
        momentum_score += 5

    pullback_score = 50
    if distance_from_buy <= 0:
        pullback_score += 25
    elif distance_from_buy <= max_chase_pct:
        pullback_score += 10
    elif distance_from_buy <= hard_overextended_pct:
        pullback_score -= 15
    else:
        pullback_score -= 35

    overextended_penalty = 0
    if distance_from_buy > max_chase_pct:
        overextended_penalty += 15
    if distance_from_buy > hard_overextended_pct:
        overextended_penalty += 20
    if rsi >= rsi_hot:
        overextended_penalty += 15

    volatility_score = 50
    if atr_pct is not None and not pd.isna(atr_pct):
        if atr_pct <= volatility_tolerance:
            volatility_score += 10
        else:
            volatility_score -= 15

    volume_score = 50
    if volume_ratio is not None and not pd.isna(volume_ratio):
        if volume_ratio >= 1.10:
            volume_score += 10
        elif volume_ratio < 0.85:
            volume_score -= 10

    raw_score = (
        trend_score * 0.25
        + momentum_score * 0.20
        + pullback_score * 0.30
        + volatility_score * 0.10
        + volume_score * 0.15
    ) - overextended_penalty

    final_score = round(clamp(raw_score, 0, 100), 1)
    entry_quality = label_strength(final_score)

    reasons = []
    if macd > macd_signal:
        reasons.append("MACD remains constructive")
    else:
        reasons.append("MACD is below its signal line")

    if rsi_buy_min <= rsi <= rsi_buy_max:
        reasons.append("RSI sits in a favorable pullback range")
    elif rsi > rsi_hot:
        reasons.append("RSI is overheated for fresh entries")
    elif rsi < rsi_buy_min:
        reasons.append("RSI is soft and still needs confirmation")
    else:
        reasons.append("RSI is neutral")

    if distance_from_buy <= 0:
        reasons.append("Price is at or below the preferred buy zone")
    elif distance_from_buy <= max_chase_pct:
        reasons.append("Price is close to the preferred buy zone")
    elif distance_from_buy <= hard_overextended_pct:
        reasons.append("Price is somewhat stretched above ideal entry")
    else:
        reasons.append("Price is too extended above ideal entry")

    if final_score >= 72 and distance_from_buy <= max_chase_pct and rsi < rsi_hot and macd >= macd_signal:
        decision = "BUY"
    elif final_score >= 45:
        decision = "HOLD / WAIT"
    else:
        decision = "AVOID"

    confidence = "High" if final_score >= 75 else "Medium" if final_score >= 55 else "Low"

    return {
        "signal": decision,
        "decision": decision,
        "score": final_score,
        "entry_score": final_score,
        "confidence": confidence,
        "entry_quality": entry_quality,
        "preferred_buy_price": preferred_buy,
        "distance_from_buy_pct": round(distance_from_buy * 100, 2),
        "trend_label": "Bullish" if trend_score >= 60 else "Mixed" if trend_score >= 45 else "Bearish",
        "momentum_label": "Favorable" if momentum_score >= 60 else "Neutral" if momentum_score >= 45 else "Weak",
        "notes": " | ".join(reasons),
    }


def enrich_results_with_pullback_system(df: pd.DataFrame, period: str, interval: str) -> pd.DataFrame:
    if df.empty or "symbol" not in df.columns:
        return df

    enriched_rows = []
    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            enriched_rows.append(row)
            continue

        history = get_symbol_history(symbol, period=period, interval=interval)
        if history.empty or "Close" not in history.columns:
            row["preferred_buy_price"] = safe_float(row.get("price"), 0.0)
            row["distance_from_buy_pct"] = 0.0
            row["confidence"] = "Low"
            row["entry_quality"] = "Weak"
            row["trend_label"] = "Mixed"
            row["momentum_label"] = "Neutral"
            row["notes"] = "Not enough price history to evaluate."
            row["decision"] = row.get("decision", "HOLD / WAIT")
            row["signal"] = row["decision"]
            enriched_rows.append(row)
            continue

        last = history.iloc[-1]
        current_price = safe_float(row.get("price"), safe_float(last.get("Close"), 0.0))
        if current_price <= 0:
            current_price = safe_float(last.get("Close"), 0.0)

        rsi = safe_float(last.get("RSI14"), safe_float(row.get("rsi_14"), 50.0))
        macd = safe_float(last.get("MACD"), safe_float(row.get("macd"), 0.0))
        macd_signal = safe_float(last.get("MACD_SIGNAL"), safe_float(row.get("macd_signal"), 0.0))
        atr_pct = safe_float(last.get("ATR_PCT"), pd.NA)
        volume_ratio = safe_float(last.get("VOLUME_RATIO"), pd.NA)

        preferred_buy = infer_dynamic_buy_price(symbol, history, current_price)
        pullback = analyze_pullback_setup(
            symbol=symbol,
            current_price=current_price,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            preferred_buy=preferred_buy,
            atr_pct=atr_pct,
            volume_ratio=volume_ratio,
        )

        row["price"] = round(current_price, 2)
        row["rsi_14"] = round(rsi, 1)
        row["macd"] = round(macd, 4)
        row["macd_signal"] = round(macd_signal, 4)
        row["preferred_buy_price"] = pullback["preferred_buy_price"]
        row["distance_from_buy_pct"] = pullback["distance_from_buy_pct"]
        row["entry_score"] = pullback["entry_score"]
        row["score"] = pullback["score"]
        row["signal"] = pullback["signal"]
        row["decision"] = pullback["decision"]
        row["confidence"] = pullback["confidence"]
        row["entry_quality"] = pullback["entry_quality"]
        row["trend_label"] = pullback["trend_label"]
        row["momentum_label"] = pullback["momentum_label"]
        row["notes"] = pullback["notes"]

        if "pullback_strength" in row.index:
            row["pullback_strength"] = pullback["entry_quality"]
        if "range_position" in row.index:
            row["range_position"] = pullback["distance_from_buy_pct"]

        enriched_rows.append(row)

    return pd.DataFrame(enriched_rows)


def classify_group_outlook(df: pd.DataFrame, label: str) -> Tuple[str, str]:
    if df.empty:
        return f"{label}: NEUTRAL", "No symbols available in this group."

    avg_entry_score = float(df["entry_score"].mean()) if "entry_score" in df.columns else 0.0
    avg_20d = float(df["20d_%"].mean()) if "20d_%" in df.columns else 0.0
    avg_5d = float(df["5d_%"].mean()) if "5d_%" in df.columns else 0.0
    buys = int(df["decision"].eq("BUY").sum()) if "decision" in df.columns else 0
    avoids = int(df["decision"].eq("AVOID").sum()) if "decision" in df.columns else 0
    holds = int(df["decision"].eq("HOLD / WAIT").sum()) if "decision" in df.columns else 0

    if avg_entry_score >= 62 and avg_20d > 0 and buys >= max(1, avoids):
        return f"{label}: CONSTRUCTIVE", "Trend quality is healthy, and several symbols are near usable pullback zones."
    if avg_entry_score <= 38 and avg_20d < 0 and avoids >= max(1, buys):
        return f"{label}: DEFENSIVE", "Risk is elevated and pullback quality is weak across the group."
    if holds >= max(1, buys) and avg_20d > 0:
        return f"{label}: BULLISH BUT EXTENDED", "Structure is still healthy, but many names are above preferred entry zones."
    if avg_5d < 0 < avg_20d:
        return f"{label}: PULLBACK IN PROGRESS", "Higher-timeframe structure is intact, but near-term pressure still needs to settle."
    return f"{label}: MIXED", "Signals are split, so selectivity is better than broad aggression."


def decision_class(decision: str) -> str:
    if decision == "BUY":
        return "decision-buy"
    if decision == "HOLD / WAIT":
        return "decision-watch"
    return "decision-avoid"


def build_top_summary(result: pd.DataFrame, top_n: int = 5) -> List[str]:
    if result.empty:
        return []

    working = result.copy()
    if "entry_score" in working.columns:
        working = working.sort_values(["decision", "entry_score"], ascending=[True, False])

    buy_first = pd.concat(
        [
            working[working["decision"] == "BUY"],
            working[working["decision"] == "HOLD / WAIT"],
        ]
    ).head(top_n)

    lines = []
    for _, row in buy_first.iterrows():
        symbol = str(row.get("symbol", "-"))
        price = format_value(row.get("price"))
        preferred = format_value(row.get("preferred_buy_price"))
        decision = str(row.get("decision", "-"))
        dist = format_value(row.get("distance_from_buy_pct"), is_percent=True)
        score = format_value(row.get("entry_score"))
        lines.append(f"{symbol}: {decision} | price {price} | buy zone {preferred} | distance {dist} | score {score}")
    return lines


def build_share_text(result: pd.DataFrame, crypto_title: str, stock_title: str) -> str:
    lines = ["Market Math Analyzer update:", crypto_title, stock_title]
    summary = build_top_summary(result, top_n=5)

    if summary:
        lines.append("Top setups:")
        lines.extend([f"- {line}" for line in summary])
    else:
        lines.append("No strong pullback entries right now.")

    if "decision" in result.columns:
        avoids = result[result["decision"] == "AVOID"]["symbol"].head(5).tolist()
        if avoids:
            lines.append("Weak / avoid zone:")
            lines.append("- " + ", ".join(avoids))

    lines.append("Built from live Yahoo Finance data with adaptive pullback logic.")
    return "\n".join(lines)


st.markdown('<div class="main-title">Market Math Analyzer V3</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Adaptive pullback intelligence with dynamic buy zones, cleaner metrics, and share-ready summaries.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Controls")

    period = st.selectbox("History period", options=["3mo", "6mo", "1y", "2y"], index=2)
    interval = st.selectbox("Data interval", options=["1d", "1h"], index=0)
    min_entry_score = st.slider("Minimum entry score", min_value=0, max_value=100, value=0, step=5)

    decision_options = ["ALL", "BUY", "HOLD / WAIT", "AVOID"]
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

st.info("📈 Scanning adaptive pullback setups...")

with st.spinner("Scanning adaptive pullback setups..."):
    result = get_analysis(period=period, interval=interval)
    result = enrich_results_with_pullback_system(result, period=period, interval=interval)

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
    actionable = int(result["decision"].eq("BUY").sum()) if "decision" in result.columns else 0
    st.metric("Buy-ready setups", actionable)
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
        st.write("No buy-ready pullback setups right now.")

with right:
    st.subheader("Share with friends")
    st.caption("Copy this summary into a text message, Slack, or social post.")
    st.text_area("Share-ready summary", value=share_text, height=220)

st.subheader("Results")

preferred_order = [
    "symbol", "asset_class", "price", "decision", "confidence", "entry_score",
    "preferred_buy_price", "distance_from_buy_pct", "trend_label", "momentum_label",
    "entry_quality", "1d_%", "5d_%", "20d_%", "rsi_14", "macd", "macd_signal", "notes",
]
existing_cols = [col for col in preferred_order if col in filtered.columns]
display_df = filtered[existing_cols].copy()

if "distance_from_buy_pct" in display_df.columns:
    display_df["distance_from_buy_pct"] = display_df["distance_from_buy_pct"].map(
        lambda x: f"{float(x):.2f}%" if pd.notna(x) else "-"
    )

if "entry_score" in display_df.columns:
    display_df["entry_score"] = display_df["entry_score"].map(lambda x: f"{float(x):.1f}" if pd.notna(x) else "-")

if "price" in display_df.columns:
    display_df["price"] = display_df["price"].map(lambda x: f"${float(x):,.2f}" if pd.notna(x) else "-")

if "preferred_buy_price" in display_df.columns:
    display_df["preferred_buy_price"] = display_df["preferred_buy_price"].map(
        lambda x: f"${float(x):,.2f}" if pd.notna(x) else "-"
    )

st.dataframe(display_df, width="stretch", hide_index=True)

st.subheader("Single symbol detail")
symbols = filtered["symbol"].dropna().tolist() if "symbol" in filtered.columns else []

if symbols:
    selected_symbol = st.selectbox("Choose a symbol", options=symbols)
    selected_row = filtered[filtered["symbol"] == selected_symbol].iloc[0]
    history = get_symbol_history(selected_symbol, period=period, interval=interval)

    d1, d2, d3, d4 = st.columns(4)
    detail_metrics = [
        ("Price", f"${safe_float(selected_row.get('price')):,.2f}"),
        ("Decision", selected_row.get("decision", "-")),
        ("Entry score", f"{safe_float(selected_row.get('entry_score')):.1f}"),
        ("Confidence", selected_row.get("confidence", "-")),
        ("Preferred buy", f"${safe_float(selected_row.get('preferred_buy_price')):,.2f}"),
        ("Distance from buy", f"{safe_float(selected_row.get('distance_from_buy_pct')):.2f}%"),
        ("RSI 14", f"{safe_float(selected_row.get('rsi_14')):.1f}"),
        ("MACD", f"{safe_float(selected_row.get('macd')):.4f}"),
    ]
    columns = [d1, d2, d3, d4]
    for idx, (label, value) in enumerate(detail_metrics):
        columns[idx % 4].metric(label, value)

    decision_text = str(selected_row.get("decision", "-"))
    st.markdown(
        f'<div class="accent-card"><span class="{decision_class(decision_text)}">{decision_text}</span><br>'
        f'<span class="small-note">{selected_row.get("notes", "-")}</span></div>',
        unsafe_allow_html=True,
    )

    if not history.empty and "Close" in history.columns:
        st.write("**Price chart**")
        chart_df = history[["Close"]].copy().tail(120)
        chart_df["Preferred Buy"] = safe_float(selected_row.get("preferred_buy_price"))
        if "EMA21" in history.columns:
            chart_df["EMA21"] = history["EMA21"].tail(len(chart_df))
        st.line_chart(chart_df, height=340)
else:
    st.write("No symbols available after filtering.")

csv_data = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download results as CSV",
    data=csv_data,
    file_name="market_math_results_v3_adaptive.csv",
    mime="text/csv",
    width="stretch",
)
