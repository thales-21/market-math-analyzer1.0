
from __future__ import annotations

import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from supabase import create_client
import streamlit as st

# Initialize Supabase
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_ANON_KEY"]
)

# Session state
if "user" not in st.session_state:
    st.session_state.user = None

def login_ui():
    st.sidebar.title("Account")

    if st.session_state.user is None:
        email = st.sidebar.text_input("Email")
        password = st.sidebar.text_input("Password", type="password")

        col1, col2 = st.sidebar.columns(2)

        with col1:
            if st.button("Login"):
                try:
                    res = supabase.auth.sign_in_with_password({
                        "email": email,
                        "password": password
                    })
                    st.session_state.user = res.user
                    st.success("Logged in")
                    st.rerun()
                except Exception as e:
                    st.error("Login failed")

        with col2:
            if st.button("Sign Up"):
                try:
                    supabase.auth.sign_up({
                        "email": email,
                        "password": password
                    })
                    st.success("Account created")
                except Exception:
                    st.error("Signup failed")

    else:
        st.sidebar.success(f"Logged in as {st.session_state.user.email}")
        if st.sidebar.button("Logout"):
            st.session_state.user = None
            st.rerun()
try:
    from supabase import Client, create_client
except Exception:
    Client = object  # type: ignore
    create_client = None  # type: ignore

from market_math_analyzer_v2 import (
    BASE_DIR,
    FORMULAS_FILE,
    WATCHLIST_FILE,
    load_watchlist,
    run_analysis,
)

st.set_page_config(page_title="Market Math Analyzer V4 Pro", layout="wide")

CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC")
CRYPTO_KEYWORDS = {
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE",
    "HBAR", "ATOM", "BNB", "AVAX", "LINK",
}

ASSET_CONFIG = {
    "BTC-USD": {
        "label": "Bitcoin",
        "preferred_buy_price": 71000.0,
        "max_chase_pct": 0.045,
        "hard_overextended_pct": 0.09,
        "rsi_buy_min": 38,
        "rsi_buy_max": 58,
        "rsi_hot": 67,
        "volatility_tolerance": 0.04,
    },
    "SOL-USD": {
        "label": "Solana",
        "preferred_buy_price": 81.0,
        "max_chase_pct": 0.06,
        "hard_overextended_pct": 0.11,
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

POSITIVE_WORDS = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "approval", "approved",
    "partnership", "adoption", "adopts", "record", "records", "strong", "bullish",
    "breakout", "launch", "growth", "gains", "gain", "upgrade", "upgrades", "buyback",
    "profit", "profits", "demand", "expansion", "wins", "win", "momentum",
}
NEGATIVE_WORDS = {
    "miss", "misses", "drop", "drops", "plunge", "plunges", "lawsuit", "probe", "fraud",
    "hack", "hacked", "risk", "risks", "downgrade", "downgrades", "bearish", "weak",
    "delay", "delays", "selloff", "loss", "losses", "fall", "falls", "concern", "warning",
    "uncertain", "volatility", "volatile", "cuts", "cut", "recession", "tariff", "ban",
}

CHART_PERIOD_OPTIONS = ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"]
DEFAULT_WATCHLIST = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD",
    "HBAR-USD", "ATOM-USD", "BNB-USD", "AAPL", "MSFT", "NVDA", "TSLA",
    "AMZN", "META", "GOOGL", "SPY", "QQQ", "GLD", "SLV",
]

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(255, 182, 92, 0.28) 0%, rgba(255, 182, 92, 0.02) 32%),
            radial-gradient(circle at top right, rgba(255, 106, 136, 0.22) 0%, rgba(255, 106, 136, 0.03) 28%),
            linear-gradient(180deg, #1f1029 0%, #34142f 24%, #5b2245 48%, #8a3b4a 72%, #f09a61 100%);
        color: #fff7ef;
    }
    .main-title { color: #fff7ef; font-size: 2rem; font-weight: 800; margin-bottom: 0.15rem; text-shadow: 0 0 14px rgba(255, 182, 92, 0.22); }
    .sub-title { color: #ffd7c0; margin-bottom: 1rem; }
    div[data-testid="stMetric"] {
        background: linear-gradient(180deg, rgba(66, 25, 56, 0.92) 0%, rgba(37, 16, 46, 0.94) 100%);
        color: #fff7ef !important; border-radius: 18px; padding: 0.75rem;
        border: 1px solid rgba(255, 190, 120, 0.22);
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.26);
    }
    div[data-testid="stMetricLabel"] { color: #ffd7c0 !important; font-weight: 600; }
    div[data-testid="stMetricValue"] { color: #fff7ef !important; font-weight: 800; font-size: 1.2rem; }
    .stDataFrame, .stDataFrame * { color: #fff7ef !important; }
    div[data-baseweb="select"] > div, .stTextInput > div > div > input, .stTextArea textarea, .stNumberInput input {
        background: rgba(42, 18, 49, 0.82) !important; color: #fff7ef !important;
        border: 1px solid rgba(255, 190, 120, 0.18) !important;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(30, 15, 42, 0.98) 0%, rgba(58, 21, 50, 0.98) 48%, rgba(92, 36, 61, 0.98) 100%);
        border-right: 1px solid rgba(255, 190, 120, 0.12);
    }
    .accent-card, .accent-card-soft, .setup-line, .alert-card {
        border-radius: 18px; padding: 0.95rem 1rem; box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
    }
    .accent-card {
        background: linear-gradient(180deg, rgba(70, 24, 57, 0.92) 0%, rgba(41, 17, 48, 0.95) 100%);
        border-left: 6px solid #ff9f68; color: #fff7ef;
    }
    .accent-card-soft {
        background: linear-gradient(180deg, rgba(84, 34, 53, 0.92) 0%, rgba(47, 20, 49, 0.95) 100%);
        border-left: 6px solid #ffd36e; color: #fff7ef;
    }
    .alert-card {
        background: linear-gradient(180deg, rgba(88, 38, 53, 0.92) 0%, rgba(41, 17, 48, 0.95) 100%);
        border-left: 6px solid #ffd36e; color: #fff7ef; margin-bottom: 0.6rem;
    }
    .decision-buy { color: #ffe88a; font-weight: 800; text-shadow: 0 0 10px rgba(255, 232, 138, 0.55); }
    .decision-watch { color: #ffd39f; font-weight: 800; }
    .decision-avoid { color: #ff9ba6; font-weight: 800; }
    .small-note { color: #ffe7d7; }
    .signal-pill {
        display: inline-block; padding: 0.38rem 0.72rem; border-radius: 999px; font-size: 0.88rem;
        font-weight: 800; margin-bottom: 0.45rem; letter-spacing: 0.01em;
    }
    .pill-strong-buy {
        background: rgba(255, 224, 118, 0.16); border: 1px solid rgba(255, 224, 118, 0.45);
        color: #fff2a6; box-shadow: 0 0 14px rgba(255, 224, 118, 0.62), 0 0 28px rgba(255, 172, 73, 0.28);
    }
    .pill-moderate-buy, .pill-buy {
        background: rgba(255, 169, 94, 0.14); border: 1px solid rgba(255, 169, 94, 0.42);
        color: #ffd9a8; box-shadow: 0 0 12px rgba(255, 169, 94, 0.42);
    }
    .pill-hold {
        background: rgba(255, 209, 136, 0.10); border: 1px solid rgba(255, 209, 136, 0.30); color: #ffe0b0;
    }
    .pill-avoid {
        background: rgba(255, 130, 146, 0.12); border: 1px solid rgba(255, 130, 146, 0.28); color: #ffbac3;
    }
    .setup-line {
        background: linear-gradient(180deg, rgba(66, 25, 56, 0.75) 0%, rgba(37, 16, 46, 0.88) 100%);
        border: 1px solid rgba(255, 190, 120, 0.16); margin-bottom: 0.6rem;
    }
    .setup-title { color: #fff7ef; font-weight: 800; margin-bottom: 0.2rem; }
    .setup-note { color: #ffd7c0; font-size: 0.92rem; }
    .overview-box {
        background: linear-gradient(180deg, rgba(66, 25, 56, 0.72) 0%, rgba(37, 16, 46, 0.92) 100%);
        border: 1px solid rgba(255, 190, 120, 0.18);
        border-radius: 18px;
        padding: 1rem;
        margin-bottom: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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


def get_secret_value(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)


@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Optional[Client]:
    url = get_secret_value("SUPABASE_URL")
    key = get_secret_value("SUPABASE_ANON_KEY")
    if not url or not key or create_client is None:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


def supabase_ready() -> bool:
    return get_supabase_client() is not None


def get_current_user_id() -> Optional[str]:
    session = st.session_state.get("sb_session")
    if not session:
        return None
    user = getattr(session, "user", None)
    if user is None and isinstance(session, dict):
        user = session.get("user")
    if user is None:
        return None
    return getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)


def get_current_user_email() -> Optional[str]:
    session = st.session_state.get("sb_session")
    if not session:
        return None
    user = getattr(session, "user", None)
    if user is None and isinstance(session, dict):
        user = session.get("user")
    if user is None:
        return None
    return getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)


def restore_supabase_session() -> None:
    client = get_supabase_client()
    if client is None:
        return
    if st.session_state.get("sb_session") is not None:
        return
    access = st.session_state.get("sb_access_token")
    refresh = st.session_state.get("sb_refresh_token")
    if not access or not refresh:
        return
    try:
        session = client.auth.set_session(access, refresh)
        st.session_state["sb_session"] = session
    except Exception:
        st.session_state.pop("sb_access_token", None)
        st.session_state.pop("sb_refresh_token", None)
        st.session_state.pop("sb_session", None)


def persist_session_tokens(session) -> None:
    access_token = getattr(session, "access_token", None) or (session.get("access_token") if isinstance(session, dict) else None)
    refresh_token = getattr(session, "refresh_token", None) or (session.get("refresh_token") if isinstance(session, dict) else None)
    if access_token:
        st.session_state["sb_access_token"] = access_token
    if refresh_token:
        st.session_state["sb_refresh_token"] = refresh_token
    st.session_state["sb_session"] = session


def auth_sign_up(email: str, password: str) -> Tuple[bool, str]:
    client = get_supabase_client()
    if client is None:
        return False, "Supabase is not configured yet."
    try:
        response = client.auth.sign_up({"email": email, "password": password})
        session = getattr(response, "session", None) or (response.get("session") if isinstance(response, dict) else None)
        if session:
            persist_session_tokens(session)
        return True, "Account created. Check your email if confirmation is enabled."
    except Exception as exc:
        return False, f"Signup failed: {exc}"


def auth_sign_in(email: str, password: str) -> Tuple[bool, str]:
    client = get_supabase_client()
    if client is None:
        return False, "Supabase is not configured yet."
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        session = getattr(response, "session", None) or (response.get("session") if isinstance(response, dict) else response)
        persist_session_tokens(session)
        return True, "Signed in successfully."
    except Exception as exc:
        return False, f"Login failed: {exc}"


def auth_sign_out() -> Tuple[bool, str]:
    client = get_supabase_client()
    try:
        if client is not None:
            client.auth.sign_out()
        for key in ["sb_access_token", "sb_refresh_token", "sb_session"]:
            st.session_state.pop(key, None)
        return True, "Signed out."
    except Exception as exc:
        return False, f"Logout failed: {exc}"


def local_watchlist() -> List[str]:
    symbols = load_watchlist()
    return symbols if symbols else DEFAULT_WATCHLIST.copy()


def local_formulas() -> str:
    if FORMULAS_FILE.exists():
        return FORMULAS_FILE.read_text(encoding="utf-8")
    return ""


def save_local_watchlist(symbols: List[str]) -> None:
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


def save_local_formulas(text: str) -> None:
    content = text.strip()
    if content:
        content += "\n"
    FORMULAS_FILE.write_text(content, encoding="utf-8")


def load_user_watchlist() -> List[str]:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return local_watchlist()
    try:
        rows = client.table("user_watchlists").select("symbols").eq("user_id", user_id).limit(1).execute()
        data = getattr(rows, "data", None) or []
        if data and data[0].get("symbols"):
            return [str(x).upper() for x in data[0]["symbols"] if str(x).strip()]
    except Exception:
        pass
    return local_watchlist()


def save_user_watchlist(symbols: List[str]) -> Tuple[bool, str]:
    cleaned: List[str] = []
    seen = set()
    for symbol in symbols:
        s = symbol.strip().upper()
        if s and s not in seen:
            cleaned.append(s)
            seen.add(s)
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        save_local_watchlist(cleaned)
        return True, "Watchlist saved locally."
    try:
        client.table("user_watchlists").upsert({"user_id": user_id, "symbols": cleaned}, on_conflict="user_id").execute()
        return True, "Watchlist saved to your account."
    except Exception as exc:
        save_local_watchlist(cleaned)
        return False, f"Supabase save failed, so it was saved locally instead: {exc}"


def load_user_formulas() -> str:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return local_formulas()
    try:
        rows = client.table("user_formulas").select("formula_text").eq("user_id", user_id).limit(1).execute()
        data = getattr(rows, "data", None) or []
        if data:
            return str(data[0].get("formula_text") or "")
    except Exception:
        pass
    return local_formulas()


def save_user_formulas(text: str) -> Tuple[bool, str]:
    client = get_supabase_client()
    user_id = get_current_user_id()
    cleaned = text.strip()
    if client is None or user_id is None:
        save_local_formulas(cleaned)
        return True, "Formulas saved locally."
    try:
        client.table("user_formulas").upsert({"user_id": user_id, "formula_text": cleaned}, on_conflict="user_id").execute()
        return True, "Formulas saved to your account."
    except Exception as exc:
        save_local_formulas(cleaned)
        return False, f"Supabase save failed, so formulas were saved locally instead: {exc}"


def load_user_preferences(defaults: Dict[str, object]) -> Dict[str, object]:
    prefs = defaults.copy()
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return prefs
    try:
        rows = client.table("user_preferences").select("preferences").eq("user_id", user_id).limit(1).execute()
        data = getattr(rows, "data", None) or []
        if data and isinstance(data[0].get("preferences"), dict):
            prefs.update(data[0]["preferences"])
    except Exception:
        pass
    return prefs


def save_user_preferences(preferences: Dict[str, object]) -> Tuple[bool, str]:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return False, "Preferences require Supabase login to persist across devices."
    try:
        client.table("user_preferences").upsert({"user_id": user_id, "preferences": preferences}, on_conflict="user_id").execute()
        return True, "Preferences saved to your account."
    except Exception as exc:
        return False, f"Could not save preferences: {exc}"


def load_alert_rows() -> pd.DataFrame:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return pd.DataFrame(columns=["id", "symbol", "alert_type", "target_value", "note", "is_active", "created_at"])
    try:
        rows = client.table("user_alerts").select("id,symbol,alert_type,target_value,note,is_active,created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
        return pd.DataFrame(getattr(rows, "data", None) or [])
    except Exception:
        return pd.DataFrame(columns=["id", "symbol", "alert_type", "target_value", "note", "is_active", "created_at"])


def add_alert(symbol: str, alert_type: str, target_value: float, note: str) -> Tuple[bool, str]:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return False, "Login required to save alerts."
    try:
        client.table("user_alerts").insert({
            "user_id": user_id,
            "symbol": symbol.upper(),
            "alert_type": alert_type,
            "target_value": target_value,
            "note": note.strip(),
            "is_active": True,
        }).execute()
        return True, "Alert saved."
    except Exception as exc:
        return False, f"Could not add alert: {exc}"


def load_trade_journal() -> pd.DataFrame:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return pd.DataFrame(columns=["id", "symbol", "side", "entry_price", "thesis", "status", "created_at"])
    try:
        rows = client.table("trade_journal").select("id,symbol,side,entry_price,stop_price,target_price,thesis,status,created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
        return pd.DataFrame(getattr(rows, "data", None) or [])
    except Exception:
        return pd.DataFrame(columns=["id", "symbol", "side", "entry_price", "thesis", "status", "created_at"])


def add_trade_journal_entry(symbol: str, side: str, entry_price: float, stop_price: float, target_price: float, thesis: str, status: str) -> Tuple[bool, str]:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return False, "Login required to save journal entries."
    try:
        client.table("trade_journal").insert({
            "user_id": user_id,
            "symbol": symbol.upper(),
            "side": side,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "thesis": thesis.strip(),
            "status": status,
        }).execute()
        return True, "Journal entry saved."
    except Exception as exc:
        return False, f"Could not save journal entry: {exc}"


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
    df["RSI14"] = (100 - (100 / (1 + rs))).fillna(50.0)

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["EMA9"] = ema9
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = close.ewm(span=21, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()
    df["EMA200"] = close.ewm(span=200, adjust=False).mean()
    df["SMA20"] = close.rolling(20).mean()
    df["SMA50"] = close.rolling(50).mean()

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
    df["HIGH60"] = high.rolling(60).max()
    return df.dropna(how="all")


@st.cache_data(ttl=300, show_spinner=False)
def get_multi_timeframe_history(symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    hourly = get_symbol_history(symbol, period="3mo", interval="1h")
    daily = get_symbol_history(symbol, period="1y", interval="1d")
    weekly = get_symbol_history(symbol, period="5y", interval="1wk")
    return hourly, daily, weekly


@st.cache_data(ttl=900, show_spinner=False)
def get_symbol_profile(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info if hasattr(ticker, "fast_info") else {}
        if hasattr(info, "items"):
            info = dict(info)
        basic = ticker.info if hasattr(ticker, "info") else {}
    except Exception:
        info = {}
        basic = {}
    profile = {}
    profile["market_cap"] = basic.get("marketCap") or info.get("market_cap")
    profile["fifty_two_week_high"] = basic.get("fiftyTwoWeekHigh") or info.get("year_high")
    profile["fifty_two_week_low"] = basic.get("fiftyTwoWeekLow") or info.get("year_low")
    profile["day_high"] = basic.get("dayHigh") or info.get("day_high")
    profile["day_low"] = basic.get("dayLow") or info.get("day_low")
    profile["volume"] = basic.get("volume") or info.get("last_volume")
    profile["average_volume"] = basic.get("averageVolume") or basic.get("averageVolume10days")
    profile["exchange"] = basic.get("exchange") or info.get("exchange")
    profile["quote_type"] = basic.get("quoteType")
    profile["short_name"] = basic.get("shortName") or basic.get("longName") or symbol
    return profile


@st.cache_data(ttl=900, show_spinner=False)
def get_earnings_snapshot(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        cal = getattr(ticker, "calendar", None)
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            cal_df = cal.reset_index()
            return {"calendar": cal_df.to_dict(orient="records")}
        earnings_dates = ticker.get_earnings_dates(limit=4)
        if isinstance(earnings_dates, pd.DataFrame) and not earnings_dates.empty:
            edf = earnings_dates.reset_index()
            return {"earnings_dates": edf.to_dict(orient="records")}
    except Exception:
        pass
    return {}


def is_crypto_symbol(symbol: str) -> bool:
    upper = symbol.upper()
    if upper.endswith(CRYPTO_SUFFIXES):
        return True
    token = upper.split("-")[0]
    return token in CRYPTO_KEYWORDS


@st.cache_data(ttl=300, show_spinner=False)
def validate_ticker(symbol: str) -> bool:
    symbol = symbol.strip().upper()
    if not symbol:
        return False
    try:
        test = yf.download(symbol, period="5d", interval="1d", auto_adjust=True, progress=False)
        if test is None or test.empty:
            return False
        if isinstance(test.columns, pd.MultiIndex):
            test.columns = [c[0] for c in test.columns]
        return "Close" in test.columns and test["Close"].dropna().shape[0] > 0
    except Exception:
        return False


def signal_badge_html(decision: str, entry_quality: str = "") -> str:
    decision_upper = str(decision).upper()
    entry_upper = str(entry_quality).upper()
    if decision_upper == "BUY" and entry_upper == "STRONG":
        return '<span class="signal-pill pill-strong-buy">● Strong Buy</span>'
    if decision_upper == "BUY" and entry_upper in {"MODERATE", "MIXED"}:
        return '<span class="signal-pill pill-moderate-buy">● Moderate Buy</span>'
    if decision_upper == "BUY":
        return '<span class="signal-pill pill-buy">● Buy</span>'
    if decision_upper == "HOLD / WAIT":
        return '<span class="signal-pill pill-hold">● Hold / Wait</span>'
    return '<span class="signal-pill pill-avoid">● Avoid</span>'


def label_strength(score: float) -> str:
    if score >= 75:
        return "Strong"
    if score >= 55:
        return "Moderate"
    if score >= 40:
        return "Mixed"
    return "Weak"


def detect_support_resistance(history: pd.DataFrame, current_price: float) -> dict:
    if history.empty or len(history) < 40 or not {"High", "Low", "Close"}.issubset(history.columns):
        fallback_support = current_price * 0.95
        fallback_resistance = current_price * 1.05
        return {
            "support": round(fallback_support, 2),
            "resistance": round(fallback_resistance, 2),
            "support_strength": 0,
            "resistance_strength": 0,
            "support_zone": f"{fallback_support * 0.995:,.2f} - {fallback_support * 1.005:,.2f}",
            "resistance_zone": f"{fallback_resistance * 0.995:,.2f} - {fallback_resistance * 1.005:,.2f}",
        }

    lows = history["Low"].tail(120)
    highs = history["High"].tail(120)
    tol = max(current_price * 0.0125, safe_float(history["ATR14"].tail(1).mean(), current_price * 0.01))

    support_candidates = []
    resistance_candidates = []

    low_values = lows.tolist()
    high_values = highs.tolist()
    for i in range(2, len(low_values) - 2):
        window_low = low_values[i - 2:i + 3]
        val_low = low_values[i]
        if val_low == min(window_low) and val_low < current_price:
            support_candidates.append(val_low)

        window_high = high_values[i - 2:i + 3]
        val_high = high_values[i]
        if val_high == max(window_high) and val_high > current_price:
            resistance_candidates.append(val_high)

    def choose_level(candidates: List[float], side: str) -> Tuple[float, int]:
        if not candidates:
            return (current_price * (0.95 if side == "support" else 1.05), 0)
        best_level = candidates[-1]
        best_count = 1
        for level in candidates:
            count = sum(abs(level - other) <= tol for other in candidates)
            if side == "support":
                better = count > best_count or (count == best_count and level > best_level)
            else:
                better = count > best_count or (count == best_count and level < best_level)
            if better:
                best_level = level
                best_count = count
        return best_level, best_count

    support, support_strength = choose_level(support_candidates, "support")
    resistance, resistance_strength = choose_level(resistance_candidates, "resistance")

    return {
        "support": round(float(support), 2),
        "resistance": round(float(resistance), 2),
        "support_strength": int(support_strength),
        "resistance_strength": int(resistance_strength),
        "support_zone": f"{support * 0.995:,.2f} - {support * 1.005:,.2f}",
        "resistance_zone": f"{resistance * 0.995:,.2f} - {resistance * 1.005:,.2f}",
    }


def infer_dynamic_buy_price(symbol: str, history: pd.DataFrame, current_price: float, levels: dict | None = None) -> float:
    cfg = {**DEFAULT_PULLBACK_CONFIG, **ASSET_CONFIG.get(symbol, {})}
    manual_preferred = safe_float(cfg.get("preferred_buy_price"), current_price)

    if history.empty or "Close" not in history.columns:
        return manual_preferred if manual_preferred > 0 else current_price

    last = history.iloc[-1]
    low20 = safe_float(last.get("LOW20"), current_price * 0.94)
    low60 = safe_float(last.get("LOW60"), low20)
    ema21 = safe_float(last.get("EMA21"), current_price)
    atr_pct = safe_float(last.get("ATR_PCT"), 0.03)
    support = safe_float((levels or {}).get("support"), low20)

    adaptive_support = (low20 * 0.35) + (low60 * 0.15) + (ema21 * 0.20) + (support * 0.30)

    if manual_preferred <= 0:
        preferred = adaptive_support
    else:
        if adaptive_support > manual_preferred * 1.03:
            preferred = (manual_preferred * 0.20) + (adaptive_support * 0.80)
        elif adaptive_support < manual_preferred * 0.94:
            preferred = (manual_preferred * 0.70) + (adaptive_support * 0.30)
        else:
            preferred = (manual_preferred * 0.35) + (adaptive_support * 0.65)

    band_adjustment = 1 - min(max(atr_pct * 0.22, 0.0), 0.02)
    preferred *= band_adjustment

    ceiling = min(current_price * 0.995, safe_float((levels or {}).get("resistance"), current_price * 1.05))
    floor = max(current_price * 0.82, support * 0.985)
    preferred = clamp(preferred, floor, ceiling)
    return round(preferred, 2)


def analyze_timeframe(history: pd.DataFrame) -> dict:
    if history.empty or len(history) < 30:
        return {"bias": "Mixed", "score": 50.0, "reason": "Not enough timeframe data."}

    last = history.iloc[-1]
    close = safe_float(last.get("Close"), 0.0)
    ema21 = safe_float(last.get("EMA21"), close)
    ema50 = safe_float(last.get("EMA50"), close)
    ema200 = safe_float(last.get("EMA200"), close)
    macd = safe_float(last.get("MACD"), 0.0)
    macd_signal = safe_float(last.get("MACD_SIGNAL"), 0.0)
    rsi = safe_float(last.get("RSI14"), 50.0)

    score = 50.0
    reasons: List[str] = []

    if close > ema21:
        score += 8
        reasons.append("price above EMA21")
    else:
        score -= 8
        reasons.append("price below EMA21")

    if close > ema50:
        score += 10
        reasons.append("price above EMA50")
    else:
        score -= 10
        reasons.append("price below EMA50")

    if close > ema200:
        score += 12
        reasons.append("price above EMA200")
    else:
        score -= 12
        reasons.append("price below EMA200")

    if macd > macd_signal:
        score += 10
        reasons.append("MACD constructive")
    else:
        score -= 10
        reasons.append("MACD weak")

    if 42 <= rsi <= 62:
        score += 8
        reasons.append("RSI healthy")
    elif rsi > 70:
        score -= 8
        reasons.append("RSI hot")
    elif rsi < 35:
        score -= 6
        reasons.append("RSI soft")

    score = clamp(score, 0, 100)
    if score >= 65:
        bias = "Bullish"
    elif score <= 40:
        bias = "Bearish"
    else:
        bias = "Mixed"

    return {"bias": bias, "score": round(score, 1), "reason": ", ".join(reasons[:3])}


def multi_timeframe_confirmation(symbol: str) -> dict:
    hourly, daily, weekly = get_multi_timeframe_history(symbol)
    h = analyze_timeframe(hourly)
    d = analyze_timeframe(daily)
    w = analyze_timeframe(weekly)
    combined = round((h["score"] * 0.25) + (d["score"] * 0.45) + (w["score"] * 0.30), 1)
    aligned = h["bias"] == d["bias"] == w["bias"] and h["bias"] != "Mixed"
    label = "Aligned" if aligned else "Mixed"
    if combined >= 65 and d["bias"] == "Bullish":
        label = "Bullish Alignment"
    elif combined <= 40 and d["bias"] == "Bearish":
        label = "Bearish Alignment"
    return {
        "mtf_hourly": h["bias"],
        "mtf_daily": d["bias"],
        "mtf_weekly": w["bias"],
        "mtf_score": combined,
        "mtf_label": label,
        "mtf_reason": f"1H: {h['reason']} | 1D: {d['reason']} | 1W: {w['reason']}",
        "daily_history": daily,
        "hourly_history": hourly,
        "weekly_history": weekly,
    }


@st.cache_data(ttl=900, show_spinner=False)
def get_news_sentiment(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        news_items = ticker.news or []
    except Exception:
        news_items = []

    if not news_items:
        return {
            "news_sentiment_score": 0.0,
            "news_sentiment_label": "Neutral",
            "news_headline_count": 0,
            "top_headlines": [],
        }

    scores = []
    headlines = []
    for item in news_items[:10]:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        text = re.sub(r"[^a-zA-Z0-9\s]", " ", title.lower())
        words = [w for w in text.split() if w]
        pos = sum(1 for w in words if w in POSITIVE_WORDS)
        neg = sum(1 for w in words if w in NEGATIVE_WORDS)
        base = (pos - neg) / max(1, len(words) ** 0.5)
        if "bitcoin" in text or "solana" in text or symbol.split("-")[0].lower() in text:
            base *= 1.1
        scores.append(base)
        headlines.append(title)

    avg_score = round(sum(scores) / max(1, len(scores)), 3)
    if avg_score >= 0.18:
        label = "Positive"
    elif avg_score <= -0.18:
        label = "Negative"
    else:
        label = "Neutral"

    return {
        "news_sentiment_score": avg_score,
        "news_sentiment_label": label,
        "news_headline_count": len(headlines),
        "top_headlines": headlines[:5],
    }


def estimate_trade_plan(current_price: float, preferred_buy: float, support: float, resistance: float, atr_pct: float, account_size: float, risk_pct: float, max_exposure_pct: float) -> dict:
    entry_price = preferred_buy if preferred_buy > 0 else current_price
    atr_buffer = max(current_price * atr_pct * 0.75, current_price * 0.01)
    stop_price = min(entry_price - atr_buffer, support * 0.99)
    stop_price = max(stop_price, entry_price * 0.85)
    risk_per_unit = max(entry_price - stop_price, entry_price * 0.005)
    target_price = max(resistance, entry_price + risk_per_unit * 2.0)
    reward_per_unit = max(target_price - entry_price, 0.0)
    rr_ratio = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0.0

    capital_at_risk = account_size * (risk_pct / 100)
    exposure_cap = account_size * (max_exposure_pct / 100)
    position_units_risk = capital_at_risk / risk_per_unit if risk_per_unit > 0 else 0.0
    position_units_exposure = exposure_cap / entry_price if entry_price > 0 else 0.0
    units = max(0.0, min(position_units_risk, position_units_exposure))
    position_value = units * entry_price

    return {
        "entry_price": round(entry_price, 2),
        "stop_price": round(stop_price, 2),
        "target_price": round(target_price, 2),
        "rr_ratio": round(rr_ratio, 2),
        "units": round(units, 4),
        "position_value": round(position_value, 2),
        "capital_at_risk": round(capital_at_risk, 2),
        "exposure_cap": round(exposure_cap, 2),
    }


def analyze_pullback_setup(
    symbol: str,
    current_price: float,
    rsi: float,
    macd: float,
    macd_signal: float,
    preferred_buy: float,
    support: float,
    resistance: float,
    mtf_score: float,
    news_score: float,
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
    support_gap_pct = pct_distance(current_price, support)
    resistance_gap_pct = pct_distance(resistance, current_price)

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
        pullback_score += 22
    elif distance_from_buy <= max_chase_pct:
        pullback_score += 10
    elif distance_from_buy <= hard_overextended_pct:
        pullback_score -= 15
    else:
        pullback_score -= 35

    level_score = 50
    if current_price >= support * 0.995 and current_price <= support * 1.03:
        level_score += 18
    elif support_gap_pct > 0.08:
        level_score -= 14
    if resistance_gap_pct < 0.05:
        level_score -= 8

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
            volatility_score -= 12

    volume_score = 50
    if volume_ratio is not None and not pd.isna(volume_ratio):
        if volume_ratio >= 1.10:
            volume_score += 10
        elif volume_ratio < 0.85:
            volume_score -= 10

    raw_score = (
        trend_score * 0.18
        + momentum_score * 0.14
        + pullback_score * 0.20
        + level_score * 0.14
        + volatility_score * 0.08
        + volume_score * 0.08
        + mtf_score * 0.12
        + (50 + news_score * 60) * 0.06
    ) - overextended_penalty

    final_score = round(clamp(raw_score, 0, 100), 1)
    entry_quality = label_strength(final_score)

    reasons = []
    reasons.append("MACD constructive" if macd > macd_signal else "MACD below signal")
    if rsi_buy_min <= rsi <= rsi_buy_max:
        reasons.append("RSI in favorable pullback range")
    elif rsi > rsi_hot:
        reasons.append("RSI overheated")
    elif rsi < rsi_buy_min:
        reasons.append("RSI still soft")
    else:
        reasons.append("RSI neutral")

    if distance_from_buy <= 0:
        reasons.append("Price at or under preferred buy")
    elif distance_from_buy <= max_chase_pct:
        reasons.append("Price near preferred buy")
    elif distance_from_buy <= hard_overextended_pct:
        reasons.append("Price somewhat extended")
    else:
        reasons.append("Price too extended")

    if current_price >= support * 0.995 and current_price <= support * 1.03:
        reasons.append("Trading near support zone")
    if news_score >= 0.18:
        reasons.append("Headline sentiment supportive")
    elif news_score <= -0.18:
        reasons.append("Headline sentiment weak")
    if mtf_score >= 65:
        reasons.append("Timeframes aligned")
    elif mtf_score <= 40:
        reasons.append("Higher timeframe weak")

    if (
        final_score >= 72
        and distance_from_buy <= max_chase_pct
        and rsi < rsi_hot
        and macd >= macd_signal
        and mtf_score >= 55
    ):
        decision = "BUY"
    elif final_score >= 45:
        decision = "HOLD / WAIT"
    else:
        decision = "AVOID"

    confidence = "High" if final_score >= 75 else "Medium" if final_score >= 55 else "Low"
    wait_price = preferred_buy if current_price > preferred_buy else current_price
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
        "wait_price": round(wait_price, 2),
        "notes": " | ".join(reasons[:6]),
    }


def enrich_results_with_pullback_system(df: pd.DataFrame, period: str, interval: str, include_news: bool = True) -> pd.DataFrame:
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

        levels = detect_support_resistance(history, current_price)
        mtf = multi_timeframe_confirmation(symbol)
        news = get_news_sentiment(symbol) if include_news else {
            "news_sentiment_score": 0.0,
            "news_sentiment_label": "Neutral",
            "news_headline_count": 0,
            "top_headlines": [],
        }

        preferred_buy = infer_dynamic_buy_price(symbol, history, current_price, levels=levels)
        pullback = analyze_pullback_setup(
            symbol=symbol,
            current_price=current_price,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            preferred_buy=preferred_buy,
            support=levels["support"],
            resistance=levels["resistance"],
            mtf_score=safe_float(mtf["mtf_score"], 50.0),
            news_score=safe_float(news["news_sentiment_score"], 0.0),
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
        row["support"] = levels["support"]
        row["resistance"] = levels["resistance"]
        row["support_strength"] = levels["support_strength"]
        row["resistance_strength"] = levels["resistance_strength"]
        row["support_zone"] = levels["support_zone"]
        row["resistance_zone"] = levels["resistance_zone"]
        row["mtf_score"] = mtf["mtf_score"]
        row["mtf_label"] = mtf["mtf_label"]
        row["mtf_hourly"] = mtf["mtf_hourly"]
        row["mtf_daily"] = mtf["mtf_daily"]
        row["mtf_weekly"] = mtf["mtf_weekly"]
        row["news_sentiment_score"] = news["news_sentiment_score"]
        row["news_sentiment_label"] = news["news_sentiment_label"]
        row["news_headline_count"] = news["news_headline_count"]
        row["top_headlines"] = " || ".join(news["top_headlines"])
        row["wait_price"] = pullback["wait_price"]
        row["notes"] = pullback["notes"]
        row["strength_score"] = round(
            (safe_float(row["entry_score"], 50) * 0.45)
            + (safe_float(row["mtf_score"], 50) * 0.30)
            + ((50 + safe_float(row["news_sentiment_score"], 0) * 60) * 0.10)
            + (55 if row["decision"] == "BUY" else 40 if row["decision"] == "HOLD / WAIT" else 20) * 0.15,
            1,
        )
        row["signal_badge"] = signal_badge_html(str(row.get("decision", "")), str(row.get("entry_quality", "")))
        enriched_rows.append(row)

    return pd.DataFrame(enriched_rows)


def classify_group_outlook(df: pd.DataFrame, label: str) -> Tuple[str, str]:
    if df.empty:
        return f"{label}: NEUTRAL", "No symbols available in this group."

    avg_entry_score = float(df["entry_score"].mean()) if "entry_score" in df.columns else 0.0
    avg_20d = float(df["20d_%"].mean()) if "20d_%" in df.columns else 0.0
    buys = int(df["decision"].eq("BUY").sum()) if "decision" in df.columns else 0
    avoids = int(df["decision"].eq("AVOID").sum()) if "decision" in df.columns else 0
    holds = int(df["decision"].eq("HOLD / WAIT").sum()) if "decision" in df.columns else 0

    if avg_entry_score >= 62 and avg_20d > 0 and buys >= max(1, avoids):
        return f"{label}: CONSTRUCTIVE", "Trend quality is healthy, and several symbols are near usable pullback zones."
    if avg_entry_score <= 38 and avg_20d < 0 and avoids >= max(1, buys):
        return f"{label}: DEFENSIVE", "Risk is elevated and pullback quality is weak across the group."
    if holds >= max(1, buys) and avg_20d > 0:
        return f"{label}: BULLISH BUT EXTENDED", "Structure is still healthy, but many names are above preferred entry zones."
    return f"{label}: MIXED", "Signals are split, so selectivity is better than broad aggression."


def decision_class(decision: str) -> str:
    if decision == "BUY":
        return "decision-buy"
    if decision == "HOLD / WAIT":
        return "decision-watch"
    return "decision-avoid"


def build_top_summary(result: pd.DataFrame, top_n: int = 5) -> List[dict]:
    if result.empty:
        return []
    working = result.copy()
    working["decision_rank"] = working["decision"].map({"BUY": 0, "HOLD / WAIT": 1, "AVOID": 2}).fillna(9)
    if "entry_score" in working.columns:
        working = working.sort_values(["decision_rank", "entry_score"], ascending=[True, False])
    top = working.head(top_n)

    lines = []
    for _, row in top.iterrows():
        lines.append(
            {
                "symbol": str(row.get("symbol", "-")),
                "decision": str(row.get("decision", "-")),
                "entry_quality": str(row.get("entry_quality", "")),
                "price": format_value(row.get("price")),
                "preferred": format_value(row.get("preferred_buy_price")),
                "distance": format_value(row.get("distance_from_buy_pct"), is_percent=True),
                "score": format_value(row.get("entry_score")),
                "wait_price": format_value(row.get("wait_price")),
                "notes": str(row.get("notes", "")),
            }
        )
    return lines


def build_share_text(result: pd.DataFrame, crypto_title: str, stock_title: str) -> str:
    lines = ["Market Math Analyzer update:", crypto_title, stock_title]
    summary = build_top_summary(result, top_n=5)
    if summary:
        lines.append("Top setups:")
        lines.extend([
            f"- {item['symbol']}: {item['decision']} | price {item['price']} | buy zone {item['preferred']} | wait price {item['wait_price']} | score {item['score']}"
            for item in summary
        ])
    else:
        lines.append("No strong pullback entries right now.")
    lines.append("Built from live Yahoo Finance price, structure, multi-timeframe, and headline sentiment data.")
    return "\n".join(lines)


def build_alerts(result: pd.DataFrame) -> pd.DataFrame:
    if result.empty:
        return pd.DataFrame()
    alerts = result.copy()
    alerts = alerts[(alerts["decision"] == "BUY") | ((alerts["decision"] == "HOLD / WAIT") & (alerts["distance_from_buy_pct"] <= 2.5))]
    if alerts.empty:
        return alerts
    alerts = alerts.sort_values(["entry_score", "distance_from_buy_pct"], ascending=[False, True])
    return alerts[[c for c in ["symbol", "decision", "price", "preferred_buy_price", "distance_from_buy_pct", "entry_score", "confidence", "notes"] if c in alerts.columns]].head(8)


def run_backtest(symbol: str, holding_days: int = 10, stop_loss_pct: float = 0.05, take_profit_pct: float = 0.10) -> dict:
    history = get_symbol_history(symbol, period="2y", interval="1d")
    if history.empty or len(history) < 250:
        return {"trades": 0, "win_rate": 0.0, "avg_return": 0.0, "equity_return": 0.0, "max_drawdown": 0.0, "results": pd.DataFrame()}

    history = history.copy().dropna(subset=["Close", "RSI14", "MACD", "MACD_SIGNAL", "EMA21", "ATR_PCT", "LOW20", "LOW60", "HIGH20"])
    trades = []
    for idx in range(60, len(history) - holding_days - 1):
        subset = history.iloc[: idx + 1]
        row = history.iloc[idx]
        current_price = safe_float(row["Close"], 0.0)
        levels = detect_support_resistance(subset.tail(120), current_price)
        preferred_buy = infer_dynamic_buy_price(symbol, subset, current_price, levels=levels)
        mtf_score = 60.0 if current_price > safe_float(row.get("EMA50"), current_price) else 40.0
        result = analyze_pullback_setup(
            symbol=symbol,
            current_price=current_price,
            rsi=safe_float(row["RSI14"], 50.0),
            macd=safe_float(row["MACD"], 0.0),
            macd_signal=safe_float(row["MACD_SIGNAL"], 0.0),
            preferred_buy=preferred_buy,
            support=levels["support"],
            resistance=levels["resistance"],
            mtf_score=mtf_score,
            news_score=0.0,
            atr_pct=safe_float(row["ATR_PCT"], 0.03),
            volume_ratio=safe_float(row.get("VOLUME_RATIO"), 1.0),
        )
        if result["decision"] != "BUY":
            continue

        entry = current_price
        future = history.iloc[idx + 1: idx + 1 + holding_days]
        stop_price = entry * (1 - stop_loss_pct)
        take_price = entry * (1 + take_profit_pct)
        exit_price = safe_float(future["Close"].iloc[-1], entry)
        outcome = "timeout"

        for _, frow in future.iterrows():
            low = safe_float(frow.get("Low"), exit_price)
            high = safe_float(frow.get("High"), exit_price)
            if low <= stop_price:
                exit_price = stop_price
                outcome = "stop"
                break
            if high >= take_price:
                exit_price = take_price
                outcome = "target"
                break

        trade_return = (exit_price - entry) / entry
        trades.append({
            "entry_date": subset.index[-1],
            "entry": entry,
            "exit": exit_price,
            "return_pct": trade_return * 100,
            "outcome": outcome,
        })

    if not trades:
        return {"trades": 0, "win_rate": 0.0, "avg_return": 0.0, "equity_return": 0.0, "max_drawdown": 0.0, "results": pd.DataFrame()}

    results = pd.DataFrame(trades)
    results["equity_curve"] = (1 + results["return_pct"] / 100).cumprod()
    peak = results["equity_curve"].cummax()
    dd = (results["equity_curve"] / peak) - 1

    return {
        "trades": int(len(results)),
        "win_rate": round(float((results["return_pct"] > 0).mean() * 100), 1),
        "avg_return": round(float(results["return_pct"].mean()), 2),
        "equity_return": round(float((results["equity_curve"].iloc[-1] - 1) * 100), 2),
        "max_drawdown": round(float(dd.min() * 100), 2),
        "results": results,
    }


def get_interval_for_chart(period: str) -> str:
    return {
        "5d": "15m",
        "1mo": "1h",
        "3mo": "1d",
        "6mo": "1d",
        "1y": "1d",
        "2y": "1d",
        "5y": "1wk",
    }.get(period, "1d")


def build_price_chart(history: pd.DataFrame, symbol: str, overlays: Dict[str, bool], preferred_buy: float, support: float, resistance: float) -> go.Figure:
    fig = go.Figure()
    if history.empty:
        return fig

    use_candles = {"Open", "High", "Low", "Close"}.issubset(history.columns)
    if use_candles:
        fig.add_trace(go.Candlestick(
            x=history.index,
            open=history["Open"],
            high=history["High"],
            low=history["Low"],
            close=history["Close"],
            name=symbol,
        ))
    else:
        fig.add_trace(go.Scatter(x=history.index, y=history["Close"], mode="lines", name=symbol))

    for name, enabled in overlays.items():
        if enabled and name in history.columns:
            fig.add_trace(go.Scatter(x=history.index, y=history[name], mode="lines", name=name))

    for value, label in [(preferred_buy, "Preferred Buy"), (support, "Support"), (resistance, "Resistance")]:
        if value > 0:
            fig.add_hline(y=value, line_dash="dot", annotation_text=label)

    fig.update_layout(
        title=f"{symbol} technical chart",
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        height=580,
        margin=dict(l=20, r=20, t=55, b=20),
    )
    return fig


def build_rsi_chart(history: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not history.empty and "RSI14" in history.columns:
        fig.add_trace(go.Scatter(x=history.index, y=history["RSI14"], mode="lines", name="RSI14"))
        fig.add_hline(y=70, line_dash="dash")
        fig.add_hline(y=30, line_dash="dash")
        fig.update_layout(title="RSI", height=260, margin=dict(l=20, r=20, t=40, b=20))
    return fig


def build_macd_chart(history: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not history.empty and "MACD" in history.columns and "MACD_SIGNAL" in history.columns:
        fig.add_trace(go.Scatter(x=history.index, y=history["MACD"], mode="lines", name="MACD"))
        fig.add_trace(go.Scatter(x=history.index, y=history["MACD_SIGNAL"], mode="lines", name="Signal"))
        fig.update_layout(title="MACD", height=260, margin=dict(l=20, r=20, t=40, b=20))
    return fig


def build_comparison_chart(symbol_a: str, symbol_b: str, period: str) -> go.Figure:
    interval = get_interval_for_chart(period)
    a = get_symbol_history(symbol_a, period=period, interval=interval)
    b = get_symbol_history(symbol_b, period=period, interval=interval)
    fig = go.Figure()
    if not a.empty and "Close" in a.columns:
        base = safe_float(a["Close"].iloc[0], 1.0) or 1.0
        fig.add_trace(go.Scatter(x=a.index, y=(a["Close"] / base) * 100, mode="lines", name=symbol_a))
    if not b.empty and "Close" in b.columns:
        base = safe_float(b["Close"].iloc[0], 1.0) or 1.0
        fig.add_trace(go.Scatter(x=b.index, y=(b["Close"] / base) * 100, mode="lines", name=symbol_b))
    fig.update_layout(title="Relative performance (start = 100)", height=420, margin=dict(l=20, r=20, t=50, b=20), yaxis_title="Indexed return")
    return fig


def overview_html(symbol: str, selected_row: pd.Series, profile: dict) -> str:
    price = safe_float(selected_row.get("price"), 0)
    decision = str(selected_row.get("decision", "-"))
    entry_score = safe_float(selected_row.get("entry_score"), 0)
    strength = safe_float(selected_row.get("strength_score"), 0)
    market_cap = profile.get("market_cap")
    volume = profile.get("volume")
    high52 = profile.get("fifty_two_week_high")
    low52 = profile.get("fifty_two_week_low")
    return (
        f'<div class="overview-box"><strong>{profile.get("short_name", symbol)}</strong> ({symbol})<br>'
        f'<span class="small-note">Price: ${price:,.2f} | Decision: {decision} | Entry score: {entry_score:.1f} | Strength score: {strength:.1f}<br>'
        f'Market cap: {format_value(market_cap)} | Volume: {format_value(volume)} | 52W High: {format_value(high52)} | 52W Low: {format_value(low52)}</span></div>'
    )


restore_supabase_session()

st.markdown('<div class="main-title">Market Math Analyzer V4 Pro</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Supabase-ready multi-user trading workstation with adaptive buy zones, charting, comparison mode, alerts, preferences, journal, and backtesting.</div>',
    unsafe_allow_html=True,
)

DEFAULT_PREFS = {
    "history_period": "1y",
    "data_interval": "1d",
    "chart_period": "6mo",
    "show_sma20": True,
    "show_sma50": True,
    "show_ema9": True,
    "show_ema21": True,
    "show_ema50": False,
    "show_rsi": True,
    "show_macd": True,
    "include_news": True,
}

prefs = load_user_preferences(DEFAULT_PREFS)

with st.sidebar:
    st.header("Account")
    if supabase_ready():
        if get_current_user_id():
            st.success(f"Signed in as {get_current_user_email() or 'user'}")
            if st.button("Sign out", width="stretch"):
                ok, msg = auth_sign_out()
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            auth_mode = st.radio("Auth mode", ["Login", "Sign up"], horizontal=True)
            with st.form("auth_form"):
                auth_email = st.text_input("Email")
                auth_password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Continue", use_container_width=True)
            if submitted:
                if auth_mode == "Login":
                    ok, msg = auth_sign_in(auth_email.strip(), auth_password)
                else:
                    ok, msg = auth_sign_up(auth_email.strip(), auth_password)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    else:
        st.warning("Supabase is not configured yet. The app will still work locally until you add SUPABASE_URL and SUPABASE_ANON_KEY.")

    st.divider()
    st.header("Controls")
    period = st.selectbox("History period", options=["3mo", "6mo", "1y", "2y"], index=["3mo", "6mo", "1y", "2y"].index(str(prefs.get("history_period", "1y"))))
    interval = st.selectbox("Data interval", options=["1d", "1h"], index=["1d", "1h"].index(str(prefs.get("data_interval", "1d"))))
    chart_period = st.selectbox("Chart timeframe", options=CHART_PERIOD_OPTIONS, index=CHART_PERIOD_OPTIONS.index(str(prefs.get("chart_period", "6mo"))))
    min_entry_score = st.slider("Minimum entry score", min_value=0, max_value=100, value=0, step=5)
    selected_decision = st.selectbox("Decision filter", options=["ALL", "BUY", "HOLD / WAIT", "AVOID"], index=0)
    include_news = st.toggle("Include Yahoo Finance headlines", value=bool(prefs.get("include_news", True)))

    st.subheader("Chart overlays")
    show_sma20 = st.toggle("SMA 20", value=bool(prefs.get("show_sma20", True)))
    show_sma50 = st.toggle("SMA 50", value=bool(prefs.get("show_sma50", True)))
    show_ema9 = st.toggle("EMA 9", value=bool(prefs.get("show_ema9", True)))
    show_ema21 = st.toggle("EMA 21", value=bool(prefs.get("show_ema21", True)))
    show_ema50 = st.toggle("EMA 50", value=bool(prefs.get("show_ema50", False)))
    show_rsi = st.toggle("RSI panel", value=bool(prefs.get("show_rsi", True)))
    show_macd = st.toggle("MACD panel", value=bool(prefs.get("show_macd", True)))

    if st.button("Save display preferences", width="stretch"):
        ok, msg = save_user_preferences({
            "history_period": period,
            "data_interval": interval,
            "chart_period": chart_period,
            "show_sma20": show_sma20,
            "show_sma50": show_sma50,
            "show_ema9": show_ema9,
            "show_ema21": show_ema21,
            "show_ema50": show_ema50,
            "show_rsi": show_rsi,
            "show_macd": show_macd,
            "include_news": include_news,
        })
        if ok:
            st.success(msg)
        else:
            st.info(msg)

    if st.button("Refresh market data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.subheader("Portfolio / risk")
    account_size = st.number_input("Account size ($)", min_value=100.0, value=10000.0, step=500.0)
    risk_pct = st.number_input("Risk per trade (%)", min_value=0.25, max_value=10.0, value=1.0, step=0.25)
    max_exposure_pct = st.number_input("Max position exposure (%)", min_value=1.0, max_value=100.0, value=15.0, step=1.0)

watchlist_symbols = load_user_watchlist()
formulas_text_default = load_user_formulas()

with st.spinner("Scanning pullback setups with structure, timeframes, and headlines..."):
    result = get_analysis(period=period, interval=interval)
    result = enrich_results_with_pullback_system(result, period=period, interval=interval, include_news=include_news)

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
alerts_df = build_alerts(result)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Tracked symbols", len(result))
with c2:
    st.metric("Buy-ready setups", int(result["decision"].eq("BUY").sum()))
with c3:
    st.metric("Average entry score", round(float(result["entry_score"].mean()), 1))
with c4:
    st.metric("Average strength score", round(float(result["strength_score"].mean()), 1))

card1, card2 = st.columns(2)
with card1:
    st.markdown(f'<div class="accent-card"><strong>{crypto_title}</strong><br><span class="small-note">{crypto_detail}</span></div>', unsafe_allow_html=True)
with card2:
    st.markdown(f'<div class="accent-card-soft"><strong>{stock_title}</strong><br><span class="small-note">{stock_detail}</span></div>', unsafe_allow_html=True)

main_tab, chart_tab, compare_tab, journal_tab, settings_tab = st.tabs([
    "Dashboard", "Symbol Lab", "Compare", "Journal & Alerts", "Settings"
])

with main_tab:
    st.subheader("Alert center")
    if alerts_df.empty:
        st.write("No alert-ready setups right now.")
    else:
        for _, arow in alerts_df.iterrows():
            badge = signal_badge_html(str(arow.get("decision", "")), "Strong" if safe_float(arow.get("entry_score"), 0) >= 75 else "Moderate")
            st.markdown(
                f'<div class="alert-card">{badge}<br><strong>{arow.get("symbol", "-")}</strong> '
                f'near trigger zone — price ${safe_float(arow.get("price"), 0):,.2f} | preferred buy ${safe_float(arow.get("preferred_buy_price"), 0):,.2f} '
                f'| distance {safe_float(arow.get("distance_from_buy_pct"), 0):.2f}% | score {safe_float(arow.get("entry_score"), 0):.1f}<br>'
                f'<span class="small-note">{arow.get("notes", "")}</span></div>',
                unsafe_allow_html=True,
            )

    left, right = st.columns([1.05, 1.25])
    with left:
        st.subheader("Top setups")
        if summary_lines:
            for item in summary_lines:
                badge = signal_badge_html(item["decision"], item["entry_quality"])
                st.markdown(
                    f'<div class="setup-line">{badge}<div class="setup-title">{item["symbol"]} — price {item["price"]} | buy zone {item["preferred"]}</div>'
                    f'<div class="setup-note">Wait price {item["wait_price"]} | Distance {item["distance"]} | Score {item["score"]} | {item["notes"]}</div></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.write("No buy-ready pullback setups right now.")
    with right:
        st.subheader("Share with friends")
        st.caption("Copy this summary into a text message, Slack, or social post.")
        st.text_area("Share-ready summary", value=share_text, height=220)

    st.subheader("Results")
    preferred_order = [
        "symbol", "asset_class", "price", "decision", "confidence", "entry_score", "strength_score", "preferred_buy_price", "wait_price",
        "distance_from_buy_pct", "support", "resistance", "mtf_label", "mtf_score", "news_sentiment_label",
        "news_sentiment_score", "trend_label", "momentum_label", "entry_quality", "rsi_14", "macd", "macd_signal", "notes",
    ]
    existing_cols = [col for col in preferred_order if col in filtered.columns]
    display_df = filtered[existing_cols].copy()
    for col in ["distance_from_buy_pct", "news_sentiment_score"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].map(lambda x: f"{float(x):.2f}%" if pd.notna(x) and col == "distance_from_buy_pct" else (f"{float(x):.3f}" if pd.notna(x) else "-"))
    for col in ["entry_score", "mtf_score", "rsi_14", "strength_score"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].map(lambda x: f"{float(x):.1f}" if pd.notna(x) else "-")
    for col in ["price", "preferred_buy_price", "wait_price", "support", "resistance"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].map(lambda x: f"${float(x):,.2f}" if pd.notna(x) else "-")
    st.dataframe(display_df, width="stretch", hide_index=True)

with chart_tab:
    st.subheader("Single symbol detail")
    symbols = filtered["symbol"].dropna().tolist() if "symbol" in filtered.columns else []
    if symbols:
        selected_symbol = st.selectbox("Choose a symbol", options=symbols)
        selected_row = filtered[filtered["symbol"] == selected_symbol].iloc[0]
        history = get_symbol_history(selected_symbol, period=chart_period, interval=get_interval_for_chart(chart_period))
        mtf = multi_timeframe_confirmation(selected_symbol)
        news = get_news_sentiment(selected_symbol) if include_news else {"top_headlines": [], "news_sentiment_label": "Neutral", "news_sentiment_score": 0.0}
        profile = get_symbol_profile(selected_symbol)
        earnings = get_earnings_snapshot(selected_symbol)
        trade_plan = estimate_trade_plan(
            current_price=safe_float(selected_row.get("price"), 0.0),
            preferred_buy=safe_float(selected_row.get("preferred_buy_price"), 0.0),
            support=safe_float(selected_row.get("support"), 0.0),
            resistance=safe_float(selected_row.get("resistance"), 0.0),
            atr_pct=safe_float(history["ATR_PCT"].tail(1).mean(), 0.03) if not history.empty and "ATR_PCT" in history.columns else 0.03,
            account_size=account_size,
            risk_pct=risk_pct,
            max_exposure_pct=max_exposure_pct,
        )
        backtest = run_backtest(selected_symbol)

        st.markdown(overview_html(selected_symbol, selected_row, profile), unsafe_allow_html=True)
        d1, d2, d3, d4 = st.columns(4)
        detail_metrics = [
            ("Price", f"${safe_float(selected_row.get('price')):,.2f}"),
            ("Decision", selected_row.get("decision", "-")),
            ("Entry score", f"{safe_float(selected_row.get('entry_score')):.1f}"),
            ("Strength score", f"{safe_float(selected_row.get('strength_score')):.1f}"),
            ("Preferred buy", f"${safe_float(selected_row.get('preferred_buy_price')):,.2f}"),
            ("Support", f"${safe_float(selected_row.get('support')):,.2f}"),
            ("Resistance", f"${safe_float(selected_row.get('resistance')):,.2f}"),
            ("Wait price", f"${safe_float(selected_row.get('wait_price')):,.2f}"),
        ]
        columns = [d1, d2, d3, d4]
        for idx, (label, value) in enumerate(detail_metrics):
            columns[idx % 4].metric(label, value)

        badge = signal_badge_html(str(selected_row.get("decision", "")), str(selected_row.get("entry_quality", "")))
        st.markdown(
            f'<div class="accent-card">{badge}<br><span class="{decision_class(str(selected_row.get("decision", "-")))}">{selected_row.get("decision", "-")}</span><br>'
            f'<span class="small-note">{selected_row.get("notes", "-")}</span></div>',
            unsafe_allow_html=True,
        )

        lcol, rcol = st.columns(2)
        with lcol:
            st.markdown(
                f'<div class="accent-card-soft"><strong>Multi-timeframe confirmation</strong><br>'
                f'<span class="small-note">1H: {selected_row.get("mtf_hourly", "-")} | 1D: {selected_row.get("mtf_daily", "-")} | 1W: {selected_row.get("mtf_weekly", "-")}<br>'
                f'Label: {selected_row.get("mtf_label", "-")} | Score: {safe_float(selected_row.get("mtf_score"), 0):.1f}<br>'
                f'{mtf.get("mtf_reason", "")}</span></div>',
                unsafe_allow_html=True,
            )
        with rcol:
            st.markdown(
                f'<div class="accent-card-soft"><strong>News sentiment</strong><br>'
                f'<span class="small-note">Sentiment: {selected_row.get("news_sentiment_label", "Neutral")} | '
                f'Score: {safe_float(selected_row.get("news_sentiment_score"), 0):.3f} | Headlines: {int(safe_float(selected_row.get("news_headline_count"), 0))}</span></div>',
                unsafe_allow_html=True,
            )
            if news.get("top_headlines"):
                for headline in news["top_headlines"][:3]:
                    st.write(f"- {headline}")

        if earnings:
            st.subheader("Events / earnings snapshot")
            if earnings.get("calendar"):
                st.dataframe(pd.DataFrame(earnings["calendar"]), width="stretch", hide_index=True)
            elif earnings.get("earnings_dates"):
                st.dataframe(pd.DataFrame(earnings["earnings_dates"]), width="stretch", hide_index=True)

        st.subheader("Technical chart")
        price_fig = build_price_chart(
            history.tail(220),
            selected_symbol,
            overlays={
                "SMA20": show_sma20,
                "SMA50": show_sma50,
                "EMA9": show_ema9,
                "EMA21": show_ema21,
                "EMA50": show_ema50,
            },
            preferred_buy=safe_float(selected_row.get("preferred_buy_price"), 0.0),
            support=safe_float(selected_row.get("support"), 0.0),
            resistance=safe_float(selected_row.get("resistance"), 0.0),
        )
        st.plotly_chart(price_fig, use_container_width=True)

        ind1, ind2 = st.columns(2)
        with ind1:
            if show_rsi:
                st.plotly_chart(build_rsi_chart(history.tail(220)), use_container_width=True)
        with ind2:
            if show_macd:
                st.plotly_chart(build_macd_chart(history.tail(220)), use_container_width=True)

        st.subheader("Trade plan")
        t1, t2, t3, t4 = st.columns(4)
        with t1:
            st.metric("Entry", f"${trade_plan['entry_price']:,.2f}")
        with t2:
            st.metric("Stop", f"${trade_plan['stop_price']:,.2f}")
        with t3:
            st.metric("Target", f"${trade_plan['target_price']:,.2f}")
        with t4:
            st.metric("R:R", f"{trade_plan['rr_ratio']:.2f}")
        t5, t6, t7 = st.columns(3)
        with t5:
            st.metric("Suggested units", f"{trade_plan['units']:,.4f}")
        with t6:
            st.metric("Position value", f"${trade_plan['position_value']:,.2f}")
        with t7:
            st.metric("Capital at risk", f"${trade_plan['capital_at_risk']:,.2f}")

        st.subheader("Backtest snapshot")
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            st.metric("Trades", backtest["trades"])
        with b2:
            st.metric("Win rate", f"{backtest['win_rate']:.1f}%")
        with b3:
            st.metric("Avg return", f"{backtest['avg_return']:.2f}%")
        with b4:
            st.metric("Max drawdown", f"{backtest['max_drawdown']:.2f}%")
        if isinstance(backtest.get("results"), pd.DataFrame) and not backtest["results"].empty:
            bt_df = backtest["results"].copy()
            bt_df["entry_date"] = bt_df["entry_date"].astype(str)
            st.dataframe(bt_df.tail(15), width="stretch", hide_index=True)
    else:
        st.write("No symbols available after filtering.")

with compare_tab:
    st.subheader("Comparison mode")
    compare_symbols = result["symbol"].dropna().tolist()
    if len(compare_symbols) >= 2:
        cmp1, cmp2, cmp3 = st.columns(3)
        with cmp1:
            compare_a = st.selectbox("First symbol", options=compare_symbols, index=0, key="compare_a")
        with cmp2:
            compare_b = st.selectbox("Second symbol", options=compare_symbols, index=min(1, len(compare_symbols) - 1), key="compare_b")
        with cmp3:
            compare_period = st.selectbox("Comparison timeframe", options=CHART_PERIOD_OPTIONS, index=CHART_PERIOD_OPTIONS.index(chart_period), key="compare_period")
        st.plotly_chart(build_comparison_chart(compare_a, compare_b, compare_period), use_container_width=True)
        compare_table = filtered[filtered["symbol"].isin([compare_a, compare_b])][[c for c in ["symbol", "price", "decision", "entry_score", "strength_score", "mtf_score", "news_sentiment_label", "preferred_buy_price"] if c in filtered.columns]].copy()
        st.dataframe(compare_table, width="stretch", hide_index=True)
    else:
        st.write("Need at least two symbols to compare.")

with journal_tab:
    st.subheader("Saved alerts")
    alert_cols = st.columns([1.2, 1.2, 1, 1.3])
    with alert_cols[0]:
        alert_symbol = st.text_input("Alert symbol", value="BTC-USD")
    with alert_cols[1]:
        alert_type = st.selectbox("Alert type", ["price_above", "price_below", "strength_above", "entry_score_above"])
    with alert_cols[2]:
        alert_target = st.number_input("Target", value=0.0, step=0.5)
    with alert_cols[3]:
        alert_note = st.text_input("Alert note")
    if st.button("Save alert"):
        ok, msg = add_alert(alert_symbol, alert_type, alert_target, alert_note)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.info(msg)
    saved_alerts = load_alert_rows()
    if not saved_alerts.empty:
        st.dataframe(saved_alerts, width="stretch", hide_index=True)
    else:
        st.caption("No saved alerts yet.")

    st.subheader("Trade journal")
    j1, j2, j3 = st.columns(3)
    with j1:
        journal_symbol = st.text_input("Journal symbol", value="AAPL")
        journal_side = st.selectbox("Side", ["Long", "Short"])
    with j2:
        journal_entry = st.number_input("Entry price", value=0.0, step=0.5)
        journal_stop = st.number_input("Stop price", value=0.0, step=0.5)
    with j3:
        journal_target = st.number_input("Target price", value=0.0, step=0.5)
        journal_status = st.selectbox("Status", ["Open", "Closed", "Idea"])
    journal_thesis = st.text_area("Thesis / notes", height=120)
    if st.button("Save journal entry"):
        ok, msg = add_trade_journal_entry(journal_symbol, journal_side, journal_entry, journal_stop, journal_target, journal_thesis, journal_status)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.info(msg)
    journal_df = load_trade_journal()
    if not journal_df.empty:
        st.dataframe(journal_df, width="stretch", hide_index=True)
    else:
        st.caption("No trade journal entries yet.")

with settings_tab:
    st.subheader("Watchlist editor")
    preset_symbols = [
        "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD",
        "HBAR-USD", "ATOM-USD", "BNB-USD", "AVAX-USD", "LINK-USD",
        "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
        "MSTR", "COIN", "SPY", "QQQ", "GLD", "SLV", "IBIT",
    ]
    if "watchlist_editor_v4" not in st.session_state:
        st.session_state.watchlist_editor_v4 = "\n".join(watchlist_symbols)
    chosen_presets = st.multiselect("Add common tickers", options=preset_symbols)
    st.caption("Search any Yahoo Finance ticker, validate it, then add it to your watchlist.")
    search_ticker = st.text_input("Ticker search", placeholder="Example: BTC-USD, SOL-USD, AAPL, MSTR, IBIT")
    col_check, col_add = st.columns(2)
    with col_check:
        if st.button("Check ticker", width="stretch"):
            ticker = search_ticker.strip().upper()
            if not ticker:
                st.warning("Enter a ticker first.")
            elif validate_ticker(ticker):
                st.success(f"{ticker} is available.")
            else:
                st.error(f"{ticker} was not found or has no recent data.")
    with col_add:
        if st.button("Add ticker", width="stretch"):
            ticker = search_ticker.strip().upper()
            current_lines = [x.strip().upper() for x in st.session_state.watchlist_editor_v4.splitlines() if x.strip()]
            if not ticker:
                st.warning("Enter a ticker first.")
            elif not validate_ticker(ticker):
                st.error(f"{ticker} is not available from Yahoo Finance.")
            elif ticker in current_lines:
                st.info(f"{ticker} is already in the watchlist.")
            else:
                current_lines.append(ticker)
                st.session_state.watchlist_editor_v4 = "\n".join(current_lines)
                st.success(f"Added {ticker} to the watchlist editor.")

    editable_watchlist = st.text_area("Current watchlist", key="watchlist_editor_v4", height=220)
    if st.button("Save watchlist", width="stretch"):
        lines = editable_watchlist.splitlines()
        lines.extend(chosen_presets)
        ok, msg = save_user_watchlist(lines)
        st.cache_data.clear()
        if ok:
            st.success(msg)
        else:
            st.info(msg)

    st.divider()
    st.subheader("Formulas editor")
    formulas_text = st.text_area("Custom formulas", value=formulas_text_default, height=180)
    if st.button("Save formulas", width="stretch"):
        ok, msg = save_user_formulas(formulas_text)
        st.cache_data.clear()
        if ok:
            st.success(msg)
        else:
            st.info(msg)

    st.divider()
    st.caption(f"Project folder: {BASE_DIR}")
    st.caption("Supabase tables expected: user_watchlists, user_formulas, user_preferences, user_alerts, trade_journal")

csv_data = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download results as CSV",
    data=csv_data,
    file_name="market_math_results_v4_pro.csv",
    mime="text/csv",
    width="stretch",
)


