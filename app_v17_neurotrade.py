import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import hmac

# =========================================================
# NEUROTRADE V20
# Fresh rewrite built to stay closer to V17 behavior
# - real search/add/save watchlist flow
# - manual preferred buy is allowed, but if it is above market it is auto-corrected down
# - suggested buy is the system entry anchor
# - stronger crypto bull calibration for BTC/SOL/AAVE/etc.
# =========================================================

st.set_page_config(
    page_title="Neurotrade V20",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

WATCHLIST_FILE = Path("watchlist_v20.json")
DEFAULT_WATCHLIST = {
    "BTC-USD": {"preferred_buy": None, "notes": "Core crypto", "category": "Crypto"},
    "SOL-USD": {"preferred_buy": None, "notes": "High beta crypto", "category": "Crypto"},
    "XRP-USD": {"preferred_buy": None, "notes": "Payments thesis", "category": "Crypto"},
    "AAVE-USD": {"preferred_buy": None, "notes": "DeFi", "category": "Crypto"},
    "SMR": {"preferred_buy": None, "notes": "Nuclear growth", "category": "Stock"},
    "XOM": {"preferred_buy": None, "notes": "Energy cash flow", "category": "Stock"},
    "IBIT": {"preferred_buy": None, "notes": "Spot BTC ETF", "category": "ETF"},
}

CRYPTO_ALIASES = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "AAVE": "AAVE-USD",
    "LINK": "LINK-USD",
    "HBAR": "HBAR-USD",
    "ADA": "ADA-USD",
    "ATOM": "ATOM-USD",
    "AVAX": "AVAX-USD",
    "DOGE": "DOGE-USD",
    "BNB": "BNB-USD",
}

ETF_HINTS = {"IBIT", "FBTC", "ARKB", "BITB", "HODL", "GLD", "SLV", "IAUM", "USO", "UNG", "UCO"}
INDEX_HINTS = {"SPY", "QQQ", "DIA", "IWM", "VOO", "^GSPC", "^NDX", "^DJI"}

TICKER_RATE_OVERRIDES = {
    "BTC-USD": {"bear": -0.20, "base": 0.32, "bull": 0.68},
    "ETH-USD": {"bear": -0.25, "base": 0.30, "bull": 0.72},
    "SOL-USD": {"bear": -0.32, "base": 0.42, "bull": 0.98},
    "XRP-USD": {"bear": -0.28, "base": 0.24, "bull": 0.58},
    "AAVE-USD": {"bear": -0.30, "base": 0.36, "bull": 0.88},
    "LINK-USD": {"bear": -0.26, "base": 0.28, "bull": 0.62},
    "IBIT": {"bear": -0.18, "base": 0.28, "bull": 0.58},
}

# =========================================================
# STYLE
# =========================================================
st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at 62% 18%, rgba(61,174,255,0.18) 0%, rgba(61,174,255,0.08) 16%, rgba(0,0,0,0) 36%),
            radial-gradient(circle at 50% 44%, rgba(0,200,255,0.10) 0%, rgba(0,0,0,0) 34%),
            linear-gradient(180deg, #071019 0%, #081321 100%);
        color: #eef6ff;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #08111d 0%, #0a1624 100%);
        border-right: 1px solid rgba(120, 210, 255, 0.10);
    }
    .main-title {
        font-size: 2.0rem;
        font-weight: 800;
        color: #f3f8ff;
        margin-bottom: 0.1rem;
        text-shadow: 0 0 16px rgba(86, 203, 255, 0.18);
    }
    .sub-title {
        color: #b6c9dc;
        font-size: 0.96rem;
        margin-bottom: 1rem;
    }
    .section-label {
        font-size: 1rem;
        font-weight: 700;
        color: #eef6ff;
        margin-top: 0.35rem;
        margin-bottom: 0.55rem;
    }
    .top-box {
        background: linear-gradient(180deg, rgba(7,18,33,0.96), rgba(6,15,28,0.99));
        border: 1px solid rgba(93, 205, 255, 0.18);
        border-radius: 18px;
        padding: 12px 14px;
        min-height: 96px;
        box-shadow:
            0 0 0 1px rgba(64, 180, 255, 0.06) inset,
            0 0 18px rgba(58, 177, 255, 0.12),
            0 10px 28px rgba(0,0,0,0.26);
    }
    .top-box-label {
        color: #90c9ea;
        font-size: 0.8rem;
        margin-bottom: 0.15rem;
    }
    .top-box-value {
        color: #f6fbff;
        font-size: 1.35rem;
        font-weight: 800;
        line-height: 1.15;
        margin-bottom: 0.15rem;
    }
    .top-box-sub {
        color: #9ec5df;
        font-size: 0.82rem;
    }
    .glass-card {
        background: linear-gradient(180deg, rgba(7,18,33,0.97), rgba(6,15,28,0.995));
        border: 1px solid rgba(93, 205, 255, 0.16);
        border-radius: 20px;
        padding: 16px;
        box-shadow:
            0 0 0 1px rgba(64, 180, 255, 0.05) inset,
            0 0 22px rgba(58, 177, 255, 0.12),
            0 12px 30px rgba(0,0,0,0.26);
    }
    .mini-card {
        background: linear-gradient(180deg, rgba(8,20,36,0.96), rgba(6,15,28,0.99));
        border: 1px solid rgba(93, 205, 255, 0.14);
        border-radius: 16px;
        padding: 12px;
        min-height: 88px;
        box-shadow: 0 0 14px rgba(58, 177, 255, 0.08);
    }
    .mini-card-label {
        color: #91c9e8;
        font-size: 0.8rem;
        margin-bottom: 0.2rem;
    }
    .mini-card-value {
        color: #f8fcff;
        font-size: 1.2rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .mini-card-sub {
        color: #9fc6de;
        font-size: 0.82rem;
        margin-top: 0.22rem;
    }
    .good-pill {
        display: inline-block;
        padding: 0.24rem 0.6rem;
        background: linear-gradient(180deg, rgba(27,73,54,0.95), rgba(21,55,42,0.98));
        color: #baf4ce;
        border: 1px solid rgba(111, 242, 166, 0.22);
        box-shadow: 0 0 12px rgba(46, 204, 113, 0.10);
        border-radius: 999px;
        margin-right: 0.38rem;
        font-size: 0.76rem;
        font-weight: 700;
    }
    .warn-pill {
        display: inline-block;
        padding: 0.24rem 0.6rem;
        background: linear-gradient(180deg, rgba(64,55,23,0.96), rgba(46,39,17,0.99));
        color: #f6df8f;
        border: 1px solid rgba(240, 202, 74, 0.24);
        box-shadow: 0 0 12px rgba(240, 202, 74, 0.08);
        border-radius: 999px;
        margin-right: 0.38rem;
        font-size: 0.76rem;
        font-weight: 700;
    }
    .bad-pill {
        display: inline-block;
        padding: 0.24rem 0.6rem;
        background: linear-gradient(180deg, rgba(64,26,31,0.96), rgba(45,18,22,0.99));
        color: #ffb8c0;
        border: 1px solid rgba(255, 128, 144, 0.22);
        box-shadow: 0 0 12px rgba(255, 128, 144, 0.08);
        border-radius: 999px;
        margin-right: 0.38rem;
        font-size: 0.76rem;
        font-weight: 700;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 18px;
        overflow: hidden;
        box-shadow: 0 0 18px rgba(58, 177, 255, 0.08);
    }
    div[data-testid="stDataFrame"] [data-testid="stTable"] {
        background: rgba(7,18,33,0.92);
    }
    div[data-testid="stSelectbox"] label,
    div[data-testid="stTextInput"] label,
    div[data-testid="stNumberInput"] label,
    div[data-testid="stMultiSelect"] label,
    div[data-testid="stToggle"] label {
        color: #c5d6e6;
    }
    div[data-testid="stButton"] > button {
        background: linear-gradient(180deg, rgba(245,248,252,0.96), rgba(223,232,241,0.98));
        color: #0b1624;
        border: 1px solid rgba(150, 220, 255, 0.28);
        border-radius: 12px;
        font-weight: 700;
        box-shadow: 0 0 16px rgba(86, 203, 255, 0.10);
    }
    div[data-testid="stButton"] > button:hover {
        border-color: rgba(120, 230, 255, 0.40);
        box-shadow: 0 0 20px rgba(86, 203, 255, 0.18);
    }
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div {
        background: rgba(7,18,33,0.92) !important;
        border: 1px solid rgba(105, 210, 255, 0.16) !important;
        box-shadow: 0 0 10px rgba(86, 203, 255, 0.06);
        border-radius: 12px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# AUTH HELPERS
# =========================================================
def get_auth_users() -> dict:
    default_users = {"admin@example.com": "demo123"}
    try:
        users = st.secrets.get("auth_users", {})
        if isinstance(users, dict) and users:
            return dict(users)
    except Exception:
        pass
    return default_users


def verify_login(email: str, password: str) -> bool:
    users = get_auth_users()
    if email not in users:
        return False
    return hmac.compare_digest(str(users[email]), str(password))

# =========================================================
# IO / STATE
# =========================================================
def load_watchlist() -> dict:
    if WATCHLIST_FILE.exists():
        try:
            data = json.loads(WATCHLIST_FILE.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    WATCHLIST_FILE.write_text(json.dumps(DEFAULT_WATCHLIST, indent=2))
    return DEFAULT_WATCHLIST.copy()


def save_watchlist(watchlist: dict) -> None:
    WATCHLIST_FILE.write_text(json.dumps(watchlist, indent=2))


def normalize_symbol(raw: str) -> str:
    symbol = (raw or "").strip().upper()
    return CRYPTO_ALIASES.get(symbol, symbol)


if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "auth_email" not in st.session_state:
    st.session_state.auth_email = ""

watchlist = st.session_state.watchlist

# =========================================================
# DATA HELPERS
# =========================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_info(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info if hasattr(ticker, "info") else {}
        fast = ticker.fast_info if hasattr(ticker, "fast_info") else {}
        return {"info": info or {}, "fast": dict(fast) if fast else {}}
    except Exception:
        return {"info": {}, "fast": {}}


@st.cache_data(ttl=300, show_spinner=False)
def get_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    try:
        df = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def search_candidates(raw_query: str) -> pd.DataFrame:
    query = normalize_symbol(raw_query)
    if not query:
        return pd.DataFrame(columns=["symbol", "name", "type", "exchange"])

    candidates = []
    for sym in [query, raw_query.strip().upper()]:
        if not sym:
            continue
        info = get_info(sym)
        full = info.get("info", {})
        if full or info.get("fast"):
            candidates.append(
                {
                    "symbol": sym,
                    "name": full.get("shortName") or full.get("longName") or sym,
                    "type": full.get("quoteType", "Unknown"),
                    "exchange": full.get("exchange", ""),
                }
            )

    if not candidates:
        return pd.DataFrame(columns=["symbol", "name", "type", "exchange"])
    return pd.DataFrame(candidates).drop_duplicates(subset=["symbol"])


def classify_asset(symbol: str, info: dict) -> str:
    if symbol in INDEX_HINTS:
        return "Index"
    if symbol in ETF_HINTS:
        return "ETF"
    if symbol.endswith("-USD"):
        return "Crypto"
    quote_type = str(info.get("info", {}).get("quoteType", "")).lower()
    if quote_type == "cryptocurrency":
        return "Crypto"
    if quote_type == "etf":
        return "ETF"
    if quote_type == "index":
        return "Index"
    if quote_type == "equity":
        return "Stock"
    return "Other"


def get_last_price(df: pd.DataFrame, info: dict) -> Optional[float]:
    fast = info.get("fast", {})
    px = fast.get("lastPrice") or fast.get("regularMarketPrice")
    if px is not None and not pd.isna(px):
        return float(px)
    if not df.empty and "Close" in df.columns:
        return float(df["Close"].iloc[-1])
    return None

# =========================================================
# MATH
# =========================================================
def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.bfill()


def calc_macd(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd, signal, hist


def annualized_vol(close: pd.Series) -> float:
    returns = close.pct_change().dropna()
    if returns.empty:
        return 0.0
    return float(returns.std() * np.sqrt(252))


def trailing_return(close: pd.Series, days: int) -> float:
    s = close.dropna()
    if len(s) < 2:
        return 0.0
    lookback = min(days, len(s) - 1)
    start = float(s.iloc[-lookback - 1])
    end = float(s.iloc[-1])
    if start <= 0:
        return 0.0
    return end / start - 1


def annualized_cagr(close: pd.Series) -> float:
    s = close.dropna()
    if len(s) < 60:
        return 0.0
    start = float(s.iloc[0])
    end = float(s.iloc[-1])
    if start <= 0 or end <= 0:
        return 0.0
    years = max(len(s) / 252, 0.25)
    return (end / start) ** (1 / years) - 1


def max_drawdown(close: pd.Series) -> float:
    s = close.dropna()
    if s.empty:
        return 0.0
    running_max = s.cummax()
    dd = s / running_max - 1
    return float(dd.min())


def project_price(price: Optional[float], annual_return: float, years: int = 1) -> float:
    if price is None or price <= 0:
        return np.nan
    return price * ((1 + annual_return) ** years)


def base_rate_template(symbol: str, asset_class: str) -> dict:
    if symbol in TICKER_RATE_OVERRIDES:
        return TICKER_RATE_OVERRIDES[symbol].copy()
    if asset_class == "Crypto":
        return {"bear": -0.28, "base": 0.22, "bull": 0.55}
    if asset_class == "Stock":
        return {"bear": -0.15, "base": 0.12, "bull": 0.24}
    if asset_class == "ETF":
        return {"bear": -0.10, "base": 0.10, "bull": 0.18}
    if asset_class == "Index":
        return {"bear": -0.10, "base": 0.09, "bull": 0.16}
    return {"bear": -0.12, "base": 0.09, "bull": 0.18}


def calibrate_scenario_rates(symbol: str, asset_class: str, close: pd.Series, rsi_now: float, above_sma50: bool, above_sma200: bool) -> dict:
    rates = base_rate_template(symbol, asset_class)

    cagr = annualized_cagr(close)
    ret_20d = trailing_return(close, 20)
    ret_60d = trailing_return(close, 60)
    vol = annualized_vol(close)
    dd = abs(max_drawdown(close))

    trend_adj = 0.0
    if above_sma50:
        trend_adj += 0.02
    if above_sma200:
        trend_adj += 0.03
    if ret_60d > 0.12:
        trend_adj += 0.04
    elif ret_60d < -0.12:
        trend_adj -= 0.04

    history_adj = float(np.clip(cagr, -0.50, 1.20) * 0.08)

    heat_penalty = 0.0
    if ret_20d > 0.10:
        heat_penalty += 0.02
    if ret_20d > 0.18:
        heat_penalty += 0.03
    if rsi_now > 72:
        heat_penalty += 0.03

    weakness_bonus = 0.0
    if rsi_now < 38:
        weakness_bonus += 0.02
    if ret_20d < -0.10:
        weakness_bonus += 0.02

    vol_penalty = min(vol, 1.30) * 0.04
    dd_penalty = min(dd, 0.85) * 0.04

    net = float(np.clip(trend_adj + history_adj + weakness_bonus - heat_penalty - vol_penalty - dd_penalty, -0.12, 0.15))

    rates["base"] += net
    rates["bull"] += net * 0.90
    rates["bear"] += net * 0.25

    if asset_class == "Crypto":
        rates["bear"] = float(np.clip(rates["bear"], -0.50, -0.05))
        rates["base"] = float(np.clip(rates["base"], 0.08, 0.60))
        rates["bull"] = float(np.clip(rates["bull"], 0.25, 1.20))
    else:
        rates["bear"] = float(np.clip(rates["bear"], -0.25, -0.03))
        rates["base"] = float(np.clip(rates["base"], 0.03, 0.28))
        rates["bull"] = float(np.clip(rates["bull"], 0.08, 0.50))

    return rates


def calculate_suggested_buy(current_price: Optional[float], asset_class: str, rsi_now: float, ret_20d: float, vol: float, above_sma50: bool, above_sma200: bool) -> Optional[float]:
    if current_price is None or current_price <= 0:
        return None

    # Suggested buy should be the closer, more actionable pullback.
    if asset_class == "Crypto":
        pullback = 0.06
    elif asset_class == "Stock":
        pullback = 0.03
    elif asset_class == "ETF":
        pullback = 0.025
    else:
        pullback = 0.03

    if ret_20d > 0.08:
        pullback += 0.02
    if ret_20d > 0.16:
        pullback += 0.02
    if rsi_now > 65:
        pullback += 0.02
    if rsi_now > 72:
        pullback += 0.02
    if above_sma50 and above_sma200:
        pullback += 0.01

    if asset_class == "Crypto" and vol > 0.80:
        pullback += 0.02
    elif asset_class != "Crypto" and vol > 0.45:
        pullback += 0.01

    if rsi_now < 38:
        pullback -= 0.02
    if ret_20d < -0.10:
        pullback -= 0.02

    if asset_class == "Crypto":
        pullback = float(np.clip(pullback, 0.03, 0.16))
    else:
        pullback = float(np.clip(pullback, 0.015, 0.10))

    suggested = current_price * (1 - pullback)
    suggested = min(suggested, current_price)
    return max(suggested, 0.0)


def calculate_buy_anchor(current_price: Optional[float], suggested_buy: Optional[float], asset_class: str, rsi_now: float, ret_20d: float, vol: float) -> Optional[float]:
    if current_price is None or current_price <= 0 or suggested_buy is None or suggested_buy <= 0:
        return None

    # Buy anchor is the deeper accumulation zone below the suggested buy.
    if asset_class == "Crypto":
        extra_pullback = 0.06
    elif asset_class == "Stock":
        extra_pullback = 0.03
    elif asset_class == "ETF":
        extra_pullback = 0.025
    else:
        extra_pullback = 0.03

    if ret_20d > 0.10:
        extra_pullback += 0.02
    if rsi_now > 70:
        extra_pullback += 0.02
    if asset_class == "Crypto" and vol > 0.85:
        extra_pullback += 0.02

    if rsi_now < 38:
        extra_pullback -= 0.015
    if ret_20d < -0.10:
        extra_pullback -= 0.015

    if asset_class == "Crypto":
        extra_pullback = float(np.clip(extra_pullback, 0.03, 0.12))
    else:
        extra_pullback = float(np.clip(extra_pullback, 0.015, 0.07))

    anchor = suggested_buy * (1 - extra_pullback)
    anchor = min(anchor, suggested_buy)
    anchor = min(anchor, current_price)
    return max(anchor, 0.0)


def conviction_score(asset_class: str, rsi_now: float, trend_ok: bool, macd_ok: bool, gap_to_anchor: Optional[float], vol: float) -> int:
    score = 50
    if trend_ok:
        score += 10
    if macd_ok:
        score += 8

    if 40 <= rsi_now <= 65:
        score += 8
    elif rsi_now < 35:
        score += 6
    elif rsi_now > 75:
        score -= 8

    if gap_to_anchor is not None:
        if gap_to_anchor <= 0:
            score += 10
        elif gap_to_anchor <= 0.08:
            score += 4
        else:
            score -= 6

    if asset_class == "Crypto" and vol > 0.90:
        score -= 6
    if asset_class != "Crypto" and vol > 0.55:
        score -= 6

    return int(np.clip(score, 1, 100))


def signal_label(score: int) -> str:
    if score >= 75:
        return "Strong"
    if score >= 60:
        return "Constructive"
    if score >= 45:
        return "Neutral"
    return "Cautious"

# =========================================================
# FORMATTERS
# =========================================================
def fmt_currency(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    x = float(x)
    if abs(x) >= 1:
        return f"${x:,.2f}"
    return f"${x:,.4f}"


def fmt_pct(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{float(x) * 100:,.1f}%"


def category_style(asset_class: str) -> str:
    asset_class = str(asset_class)
    if asset_class == "Crypto":
        return "background-color: rgba(245, 196, 69, 0.12); color: #f4c54f; font-weight: 700;"
    if asset_class in {"Stock", "ETF"}:
        return "background-color: rgba(91, 205, 255, 0.12); color: #69d6ff; font-weight: 700;"
    if asset_class == "Index":
        return "background-color: rgba(180, 118, 255, 0.12); color: #c99bff; font-weight: 700;"
    return "background-color: rgba(180, 180, 180, 0.10); color: #d7e0ea; font-weight: 700;"


def category_row_style(row):
    cls = str(row.get("Class", ""))
    styles = [""] * len(row)
    if "Class" in row.index:
        styles[list(row.index).index("Class")] = category_style(cls)
    if "Symbol" in row.index:
        if cls == "Crypto":
            styles[list(row.index).index("Symbol")] = "color: #f4c54f; font-weight: 700;"
        elif cls in {"Stock", "ETF"}:
            styles[list(row.index).index("Symbol")] = "color: #69d6ff; font-weight: 700;"
        elif cls == "Index":
            styles[list(row.index).index("Symbol")] = "color: #c99bff; font-weight: 700;"
    return styles


def top_box(label: str, value: str, sub: str) -> str:
    return f"""
    <div class='top-box'>
        <div class='top-box-label'>{label}</div>
        <div class='top-box-value'>{value}</div>
        <div class='top-box-sub'>{sub}</div>
    </div>
    """


def mini_card(label: str, value: str, sub: str) -> str:
    return f"""
    <div class='mini-card'>
        <div class='mini-card-label'>{label}</div>
        <div class='mini-card-value'>{value}</div>
        <div class='mini-card-sub'>{sub}</div>
    </div>
    """

# =========================================================
# ANALYSIS
# =========================================================
def analyze_symbol(symbol: str, preferred_buy_manual, notes: str, manual_category: Optional[str]):
    info = get_info(symbol)
    hist = get_history(symbol, period="1y")
    if hist.empty or "Close" not in hist.columns:
        return {"symbol": symbol, "error": "No data"}

    hist = hist.copy()
    hist["SMA20"] = hist["Close"].rolling(20).mean()
    hist["SMA50"] = hist["Close"].rolling(50).mean()
    hist["SMA200"] = hist["Close"].rolling(200).mean()
    hist["RSI"] = calc_rsi(hist["Close"])
    macd, macd_signal, macd_hist = calc_macd(hist["Close"])
    hist["MACD"] = macd
    hist["MACD_SIGNAL"] = macd_signal
    hist["MACD_HIST"] = macd_hist

    name = info.get("info", {}).get("shortName") or info.get("info", {}).get("longName") or symbol
    asset_class = manual_category if manual_category and manual_category != "Auto" else classify_asset(symbol, info)
    current = get_last_price(hist, info)
    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
    day_change = None if current is None or prev_close in (None, 0) else current / prev_close - 1

    rsi_now = float(hist["RSI"].iloc[-1]) if not pd.isna(hist["RSI"].iloc[-1]) else 50.0
    sma50 = float(hist["SMA50"].iloc[-1]) if not pd.isna(hist["SMA50"].iloc[-1]) else np.nan
    sma200 = float(hist["SMA200"].iloc[-1]) if not pd.isna(hist["SMA200"].iloc[-1]) else np.nan

    above_sma50 = bool(current is not None and not pd.isna(sma50) and current > sma50)
    above_sma200 = bool(current is not None and not pd.isna(sma200) and current > sma200)
    trend_ok = above_sma50
    macd_ok = bool(float(hist["MACD"].iloc[-1]) >= float(hist["MACD_SIGNAL"].iloc[-1]))

    vol = annualized_vol(hist["Close"])
    cagr_1y = annualized_cagr(hist["Close"])
    ret_20d = trailing_return(hist["Close"], 20)
    ret_60d = trailing_return(hist["Close"], 60)
    drawdown = max_drawdown(hist["Close"])

    scenario_rates = calibrate_scenario_rates(symbol, asset_class, hist["Close"], rsi_now, above_sma50, above_sma200)
    bear_1y = project_price(current, scenario_rates["bear"], 1)
    base_1y = project_price(current, scenario_rates["base"], 1)
    bull_1y = project_price(current, scenario_rates["bull"], 1)

    suggested_buy = calculate_suggested_buy(current, asset_class, rsi_now, ret_20d, vol, above_sma50, above_sma200)
    buy_anchor = calculate_buy_anchor(current, suggested_buy, asset_class, rsi_now, ret_20d, vol)

    # Manual preferred buy stays manual, but if it is above market it is invalid for display emphasis and scoring.
    preferred_buy_valid = None
    preferred_buy_invalid = False
    if preferred_buy_manual not in (None, 0) and current not in (None, 0):
        if preferred_buy_manual <= current:
            preferred_buy_valid = preferred_buy_manual
        else:
            preferred_buy_invalid = True

    gap_to_preferred = None
    if preferred_buy_valid not in (None, 0) and current not in (None, 0):
        gap_to_preferred = current / preferred_buy_valid - 1

    gap_to_suggested = None
    if suggested_buy not in (None, 0) and current not in (None, 0):
        gap_to_suggested = current / suggested_buy - 1

    gap_to_buy_anchor = None
    if buy_anchor not in (None, 0) and current not in (None, 0):
        gap_to_buy_anchor = current / buy_anchor - 1

    score = conviction_score(asset_class, rsi_now, trend_ok, macd_ok, gap_to_buy_anchor, vol)

    return {
        "symbol": symbol,
        "name": name,
        "asset_class": asset_class,
        "current": current,
        "preferred_buy_manual": preferred_buy_manual,
        "preferred_buy": preferred_buy_valid,
        "preferred_buy_invalid": preferred_buy_invalid,
        "suggested_buy": suggested_buy,
        "buy_anchor": buy_anchor,
        "gap_to_preferred": gap_to_preferred,
        "gap_to_suggested": gap_to_suggested,
        "day_change": day_change,
        "rsi": rsi_now,
        "above_sma50": above_sma50,
        "above_sma200": above_sma200,
        "trend_ok": trend_ok,
        "macd_ok": macd_ok,
        "vol": vol,
        "cagr_1y": cagr_1y,
        "ret_20d": ret_20d,
        "ret_60d": ret_60d,
        "drawdown": drawdown,
        "bear_rate": scenario_rates["bear"],
        "base_rate": scenario_rates["base"],
        "bull_rate": scenario_rates["bull"],
        "bear_1y": bear_1y,
        "base_1y": base_1y,
        "bull_1y": bull_1y,
        "score": score,
        "signal": signal_label(score),
        "notes": notes,
        "history": hist,
        "error": None,
    }

# =========================================================
# CHART
# =========================================================
def make_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.update_layout(template="plotly_dark", height=420, title=f"{symbol} — no data")
        return fig

    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="Close", line=dict(width=2)))
    if "SMA50" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], mode="lines", name="SMA 50", line=dict(width=1.4)))
    if "SMA200" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], mode="lines", name="SMA 200", line=dict(width=1.4)))

    fig.update_layout(
        template="plotly_dark",
        height=430,
        margin=dict(l=20, r=20, t=45, b=20),
        hovermode="x unified",
        title=f"{symbol} price trend",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )
    return fig

# =========================================================
# HEADER
# =========================================================
st.markdown("<div class='main-title'>Neurotrade V20</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-title'>Closer to the V17 workflow: watchlist first, detail second, simple but stronger scenario math, and buy prices that do not stay above the live market in the app.</div>",
    unsafe_allow_html=True,
)

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("### Account")
    if not st.session_state.authenticated:
        auth_mode = st.radio("Auth", ["Login", "Sign up", "Reset password"], horizontal=True, label_visibility="collapsed")
        if auth_mode == "Login":
            login_email = st.text_input("Email", key="login_email_input")
            login_password = st.text_input("Password", type="password", key="login_password_input")
            if st.button("Continue", use_container_width=True, key="login_continue_btn"):
                if verify_login(login_email.strip(), login_password):
                    st.session_state.authenticated = True
                    st.session_state.auth_email = login_email.strip()
                    st.success("Logged in")
                    st.rerun()
                else:
                    st.error("Invalid email or password")
        elif auth_mode == "Sign up":
            st.caption("Demo build: add users through Streamlit secrets under auth_users.")
        else:
            st.caption("Demo build: reset passwords by updating Streamlit secrets.")
    else:
        st.success(f"Logged in as {st.session_state.auth_email}")
        if st.button("Log out", use_container_width=True, key="logout_btn"):
            st.session_state.authenticated = False
            st.session_state.auth_email = ""
            st.rerun()

    st.markdown("---")
    st.markdown("### Controls")
    chart_period = st.selectbox("Chart period", ["6mo", "1y", "2y", "5y"], index=1)
    sort_by = st.selectbox(
        "Sort workbench by",
        ["Score", "Symbol", "Current", "Buy Anchor", "Gap vs Suggested", "1D", "RSI"],
        index=0,
    )
    ascending = st.toggle("Ascending sort", value=False)
    show_only_at_or_below_buy = st.toggle("Show only at/below buy anchor", value=False)

    st.markdown("---")
    st.markdown("### Search and add")
    search_raw = st.text_input("Ticker search", placeholder="SOL, BTC-USD, IBIT, SMR")
    search_results = search_candidates(search_raw)

    if not search_results.empty:
        chosen_symbol = st.selectbox(
            "Result",
            options=search_results["symbol"].tolist(),
            format_func=lambda s: f"{s} — {search_results.loc[search_results['symbol'] == s, 'name'].iloc[0]}",
        )
    else:
        chosen_symbol = normalize_symbol(search_raw)

    preferred_buy_input = st.number_input("Preferred buy (optional)", min_value=0.0, value=0.0, step=1.0)
    category_input = st.selectbox("Category", ["Auto", "Crypto", "Stock", "ETF", "Index", "Other"], index=0)
    notes_input = st.text_input("Notes", placeholder="Why it is on the list")

    if st.button("Add ticker", use_container_width=True):
        if not st.session_state.authenticated:
            st.warning("Log in to add tickers.")
        elif chosen_symbol:
            info = get_info(chosen_symbol)
            inferred = classify_asset(chosen_symbol, info)
            watchlist[chosen_symbol] = {
                "preferred_buy": None if preferred_buy_input <= 0 else float(preferred_buy_input),
                "notes": notes_input,
                "category": inferred if category_input == "Auto" else category_input,
            }
            save_watchlist(watchlist)
            st.success(f"Added {chosen_symbol}")
            st.rerun()

    st.markdown("---")
    if st.button("Reset watchlist to defaults", use_container_width=True):
        if not st.session_state.authenticated:
            st.warning("Log in to reset the watchlist.")
        else:
            st.session_state.watchlist = DEFAULT_WATCHLIST.copy()
            save_watchlist(st.session_state.watchlist)
            st.success("Watchlist reset")
            st.rerun()

# =========================================================
# RUN ANALYSIS
# =========================================================
analyses = []
for symbol, meta in watchlist.items():
    analyses.append(
        analyze_symbol(
            symbol=symbol,
            preferred_buy_manual=meta.get("preferred_buy"),
            notes=meta.get("notes", ""),
            manual_category=meta.get("category"),
        )
    )

analyses = [a for a in analyses if not a.get("error")]
if not analyses:
    st.error("No valid ticker data returned.")
    st.stop()

# =========================================================
# WORKBENCH
# =========================================================
st.markdown("<div class='section-label'>Workbench</div>", unsafe_allow_html=True)

rows = []
for a in analyses:
    if show_only_at_or_below_buy and a["buy_anchor"] not in (None, 0):
        if a["current"] is not None and a["current"] > a["buy_anchor"]:
            continue

    rows.append(
        {
            "Symbol": a["symbol"],
            "Name": a["name"],
            "Class": a["asset_class"],
            "Current": a["current"],
            "Suggested Buy": a["suggested_buy"],
            "Preferred Buy": a["preferred_buy"],
            "Buy Anchor": a["buy_anchor"],
            "Gap vs Suggested": a["gap_to_suggested"],
            "Gap vs Preferred": a["gap_to_preferred"],
            "1D": a["day_change"],
            "Bull 1Y": a["bull_1y"],
            "Base 1Y": a["base_1y"],
            "Bear 1Y": a["bear_1y"],
            "RSI": a["rsi"],
            "Trend": "Yes" if a["trend_ok"] else "No",
            "MACD": "Bullish" if a["macd_ok"] else "Weak",
            "Score": a["score"],
            "Signal": a["signal"],
        }
    )

workbench = pd.DataFrame(rows)

sort_map = {
    "Score": "Score",
    "Symbol": "Symbol",
    "Current": "Current",
    "Buy Anchor": "Buy Anchor",
    "Gap vs Suggested": "Gap vs Suggested",
    "1D": "1D",
    "RSI": "RSI",
}
workbench = workbench.sort_values(by=sort_map[sort_by], ascending=ascending, na_position="last")

cols = st.columns(4)
for i, sym in enumerate(workbench.head(4)["Symbol"].tolist()):
    a = next(x for x in analyses if x["symbol"] == sym)
    sub = f"Suggested {fmt_currency(a['suggested_buy'])} · Anchor {fmt_currency(a['buy_anchor'])}"
    with cols[i]:
        st.markdown(top_box(f"{sym} current", fmt_currency(a["current"]), sub), unsafe_allow_html=True)

show_df = workbench.copy()
for col in ["Current", "Suggested Buy", "Preferred Buy", "Buy Anchor", "Bull 1Y", "Base 1Y", "Bear 1Y"]:
    show_df[col] = show_df[col].map(fmt_currency)
for col in ["Gap vs Suggested", "Gap vs Preferred", "1D"]:
    show_df[col] = show_df[col].map(fmt_pct)
show_df["RSI"] = show_df["RSI"].map(lambda x: f"{x:,.1f}")

styled_workbench = show_df.style.apply(category_row_style, axis=1)
st.dataframe(styled_workbench, use_container_width=True, hide_index=True)

# =========================================================
# DETAIL VIEW
# =========================================================
st.markdown("<div class='section-label'>Detail view</div>", unsafe_allow_html=True)
selected_symbol = st.selectbox("Choose ticker", workbench["Symbol"].tolist(), index=0)
selected = next(x for x in analyses if x["symbol"] == selected_symbol)

chart_df = get_history(selected_symbol, chart_period)
if not chart_df.empty and "Close" in chart_df.columns:
    chart_df = chart_df.copy()
    chart_df["SMA50"] = chart_df["Close"].rolling(50).mean()
    chart_df["SMA200"] = chart_df["Close"].rolling(200).mean()

left, right = st.columns([1.2, 0.8])
with left:
    st.plotly_chart(make_chart(chart_df, selected_symbol), use_container_width=True)

with right:
    st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
    st.markdown(f"### {selected['symbol']} — {selected['name']}")
    st.markdown(
        f"<span class='{'good-pill' if selected['trend_ok'] else 'warn-pill'}'>{selected['asset_class']}</span>"
        f"<span class='{'good-pill' if selected['above_sma50'] else 'warn-pill'}'>{'Above SMA50' if selected['above_sma50'] else 'Below SMA50'}</span>"
        f"<span class='{'good-pill' if selected['macd_ok'] else 'bad-pill'}'>{'MACD bullish' if selected['macd_ok'] else 'MACD weak'}</span>",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(mini_card("Current", fmt_currency(selected["current"]), f"1D {fmt_pct(selected['day_change'])}"), unsafe_allow_html=True)
    with c2:
        st.markdown(mini_card("Buy anchor", fmt_currency(selected["buy_anchor"]), "Deeper accumulation zone below suggested"), unsafe_allow_html=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown(mini_card("Suggested buy", fmt_currency(selected["suggested_buy"]), f"Closer pullback · Gap {fmt_pct(selected['gap_to_suggested'])}"), unsafe_allow_html=True)
    with c4:
        pref_sub = f"Manual raw {fmt_currency(selected['preferred_buy_manual'])}"
        if selected["preferred_buy_invalid"]:
            pref_sub = f"Manual raw {fmt_currency(selected['preferred_buy_manual'])} · above market"
        st.markdown(mini_card("Preferred buy", fmt_currency(selected["preferred_buy"]), pref_sub), unsafe_allow_html=True)

    c5, c6 = st.columns(2)
    with c5:
        st.markdown(mini_card("RSI", f"{selected['rsi']:.1f}", "40–65 is healthier"), unsafe_allow_html=True)
    with c6:
        st.markdown(mini_card("1Y CAGR", fmt_pct(selected["cagr_1y"]), f"20D {fmt_pct(selected['ret_20d'])}"), unsafe_allow_html=True)

    st.write(f"**Signal:** {selected['signal']}  |  **Score:** {selected['score']}/100")
    st.write(f"**Notes:** {selected['notes'] or '—'}")
    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# SCENARIO VIEW
# =========================================================
st.markdown("<div class='section-label'>1-year scenario view</div>", unsafe_allow_html=True)
p1, p2, p3 = st.columns(3)
with p1:
    st.markdown(mini_card("Bear 1Y", fmt_currency(selected["bear_1y"]), f"Annual return {fmt_pct(selected['bear_rate'])}"), unsafe_allow_html=True)
with p2:
    st.markdown(mini_card("Base 1Y", fmt_currency(selected["base_1y"]), f"Annual return {fmt_pct(selected['base_rate'])}"), unsafe_allow_html=True)
with p3:
    st.markdown(mini_card("Bull 1Y", fmt_currency(selected["bull_1y"]), f"Annual return {fmt_pct(selected['bull_rate'])}"), unsafe_allow_html=True)

st.caption("Bull/base/bear now use stronger crypto-specific overrides and trend calibration. Suggested buy is the closer pullback level. Buy anchor is the deeper ideal accumulation level below suggested buy. Manual preferred buys above market are flagged as invalid and excluded from emphasis/scoring rather than being treated as real active buys.")

# =========================================================
# EDIT WATCHLIST
# =========================================================
st.markdown("<div class='section-label'>Edit and save watchlist</div>", unsafe_allow_html=True)
editor_rows = []
for symbol, meta in watchlist.items():
    editor_rows.append(
        {
            "symbol": symbol,
            "preferred_buy": 0.0 if meta.get("preferred_buy") is None else float(meta.get("preferred_buy")),
            "notes": meta.get("notes", ""),
            "category": meta.get("category", "Auto"),
            "remove": False,
        }
    )
editor_df = pd.DataFrame(editor_rows)

edited = st.data_editor(
    editor_df,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    column_config={
        "symbol": st.column_config.TextColumn("Symbol", disabled=True),
        "preferred_buy": st.column_config.NumberColumn("Preferred Buy", min_value=0.0, step=1.0),
        "notes": st.column_config.TextColumn("Notes"),
        "category": st.column_config.SelectboxColumn("Category", options=["Crypto", "Stock", "ETF", "Index", "Other", "Auto"]),
        "remove": st.column_config.CheckboxColumn("Remove"),
    },
)

save_col, reload_col = st.columns(2)
with save_col:
    if st.button("Save watchlist", use_container_width=True):
        if not st.session_state.authenticated:
            st.warning("Log in to save watchlist changes.")
        else:
            new_watchlist = {}
            for _, row in edited.iterrows():
                if bool(row["remove"]):
                    continue
                new_watchlist[str(row["symbol"])] = {
                    "preferred_buy": None if float(row["preferred_buy"]) <= 0 else float(row["preferred_buy"]),
                    "notes": str(row["notes"]),
                    "category": str(row["category"]),
                }
            st.session_state.watchlist = new_watchlist
            save_watchlist(new_watchlist)
            st.success("Watchlist saved")
            st.rerun()

with reload_col:
    if st.button("Reload saved file", use_container_width=True):
        st.session_state.watchlist = load_watchlist()
        st.rerun()

st.markdown("---")
st.caption("Data source: Yahoo Finance via yfinance. Research tool only, not financial advice.")
