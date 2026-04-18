from __future__ import annotations

import hashlib
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

try:
    from supabase import Client, create_client
except Exception:
    Client = object  # type: ignore
    create_client = None  # type: ignore

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    def st_autorefresh(*args, **kwargs):
        return None

from market_math_analyzer_v2 import BASE_DIR, FORMULAS_FILE, WATCHLIST_FILE, load_watchlist

st.set_page_config(page_title="NeuroTrade", layout="wide")

ACCENT = "#78D9FF"
ACCENT_SOFT = "rgba(120, 217, 255, 0.18)"
ACCENT_BORDER = "rgba(120, 217, 255, 0.48)"
GOLD = "#F0D86A"
DEFAULT_WATCHLIST = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD",
    "HBAR-USD", "ATOM-USD", "BNB-USD", "AAPL", "MSFT", "NVDA",
]
BAR_OPTIONS = ["5m", "15m", "30m", "1h", "4h", "1d"]
ASSET_CONFIG: dict[str, dict[str, float]] = {}
CHART_WINDOWS = {
    "5m": "5d",
    "15m": "5d",
    "30m": "1mo",
    "1h": "2mo",
    "4h": "6mo",
    "1d": "1y",
}
CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC")
CRYPTO_KEYWORDS = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "HBAR", "ATOM", "BNB", "AVAX", "LINK"}

st.markdown(
    f"""
    <style>
    .stApp {{
        background:
            radial-gradient(circle at top left, rgba(255, 182, 92, 0.28) 0%, rgba(255, 182, 92, 0.02) 32%),
            radial-gradient(circle at top right, rgba(255, 106, 136, 0.22) 0%, rgba(255, 106, 136, 0.03) 28%),
            linear-gradient(180deg, #1f1029 0%, #34142f 24%, #5b2245 48%, #8a3b4a 72%, #f09a61 100%);
        color: #fff7ef;
    }}
    .main-title {{ color: #fff7ef; font-size: 2.2rem; font-weight: 900; margin-bottom: 0.15rem; text-shadow: 0 0 18px rgba(125,235,255,0.35); }}
    .sub-title {{ color: #c8f7ff; margin-bottom: 1rem; font-size: 1rem; }}
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, rgba(30, 15, 42, 0.98) 0%, rgba(58, 21, 50, 0.98) 48%, rgba(92, 36, 61, 0.98) 100%);
        border-right: 1px solid rgba(125, 235, 255, 0.16);
    }}
    div[data-testid="stMetric"] {{
        background: linear-gradient(180deg, rgba(18, 40, 56, 0.96) 0%, rgba(21, 24, 38, 0.98) 100%);
        border: 1px solid {ACCENT_BORDER};
        border-radius: 18px; padding: 0.85rem; box-shadow: 0 12px 30px rgba(0,0,0,0.28);
    }}
    div[data-testid="stMetricLabel"] {{ color: #dffcff !important; font-weight: 800; opacity: 1 !important; text-shadow: 0 0 10px rgba(125,235,255,0.20); }}
    div[data-testid="stMetricValue"] {{ color: #aaff9c !important; font-size: 1.42rem !important; font-weight: 900; text-shadow: 0 0 12px rgba(170,255,156,0.30); }}
    .header-box {{
        border-radius: 18px; padding: 0.8rem 1rem; margin-bottom: 0.6rem;
        border: 1px solid {ACCENT_BORDER}; background: linear-gradient(180deg, rgba(16,38,60,0.94) 0%, rgba(24,22,38,0.98) 100%);
        box-shadow: 0 12px 28px rgba(0,0,0,0.22);
    }}
    .section-header {{
        display: inline-block; padding: 0.35rem 0.8rem; border-radius: 999px; margin: 0.45rem 0 0.75rem 0;
        background: {ACCENT_SOFT}; border: 1px solid {ACCENT_BORDER}; color: {ACCENT}; font-weight: 800; letter-spacing: 0.02em;
    }}
    .gold-box {{
        border-radius: 18px; padding: 1rem; margin-bottom: 0.75rem;
        background: linear-gradient(180deg, rgba(61, 49, 8, 0.92) 0%, rgba(34, 26, 16, 0.98) 100%);
        border: 1px solid rgba(240, 216, 106, 0.40); color: #fff1a2;
        box-shadow: 0 12px 28px rgba(0,0,0,0.22);
    }}
    .soft-box {{
        border-radius: 18px; padding: 1rem; margin-bottom: 0.75rem;
        background: linear-gradient(180deg, rgba(17, 35, 52, 0.94) 0%, rgba(23, 24, 39, 0.98) 100%);
        border: 1px solid {ACCENT_BORDER}; color: #effcff;
    }}
    .stat-card {{
        border-radius: 18px; padding: 0.95rem; margin-bottom: 0.75rem;
        background: linear-gradient(180deg, rgba(18, 39, 57, 0.96) 0%, rgba(20, 24, 38, 0.98) 100%);
        border: 1px solid {ACCENT_BORDER}; color: #effcff;
        box-shadow: 0 10px 24px rgba(0,0,0,0.20);
    }}
    .stat-title {{ color: {ACCENT}; font-weight: 800; font-size: 0.92rem; margin-bottom: 0.25rem; }}
    .stat-value {{ color: #ffffff; font-size: 1.35rem; font-weight: 900; }}
    .stat-sub {{ color: #d5fbff; font-size: 0.93rem; }}
    .pill {{ display:inline-block; padding:0.28rem 0.6rem; border-radius:999px; font-size:0.82rem; font-weight:800; margin-right:0.35rem; margin-bottom:0.25rem; }}
    .pill-good {{ background: rgba(125,235,255,0.16); border:1px solid {ACCENT_BORDER}; color:{ACCENT}; }}
    .pill-wait {{ background: rgba(255,228,107,0.16); border:1px solid rgba(255,228,107,0.36); color:#fff3a7; }}
    .pill-risk {{ background: rgba(255,146,165,0.16); border:1px solid rgba(255,146,165,0.34); color:#ffc3ce; }}
    .small-note {{ color: #d5fbff; }}
    .stDataFrame, .stDataFrame * {{ color: #fff7ef !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def format_num(value: float | int | None, decimals: int = 2, prefix: str = "") -> str:
    if value is None or pd.isna(value):
        return "-"
    try:
        v = float(value)
    except Exception:
        return str(value)
    if abs(v) >= 1000:
        return f"{prefix}{v:,.{decimals}f}"
    return f"{prefix}{v:.{decimals}f}"


def is_crypto(symbol: str) -> bool:
    upper = symbol.upper()
    if upper.endswith(CRYPTO_SUFFIXES):
        return True
    return upper.split("-")[0] in CRYPTO_KEYWORDS


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


def get_current_user_id() -> Optional[str]:
    session = st.session_state.get("sb_session")
    if not session:
        return None
    user = getattr(session, "user", None) or (session.get("user") if isinstance(session, dict) else None)
    if user is None:
        return None
    return getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)


def get_current_user_email() -> Optional[str]:
    session = st.session_state.get("sb_session")
    if not session:
        return None
    user = getattr(session, "user", None) or (session.get("user") if isinstance(session, dict) else None)
    if user is None:
        return None
    return getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)


def persist_session_tokens(session) -> None:
    access_token = getattr(session, "access_token", None) or (session.get("access_token") if isinstance(session, dict) else None)
    refresh_token = getattr(session, "refresh_token", None) or (session.get("refresh_token") if isinstance(session, dict) else None)
    if access_token:
        st.session_state["sb_access_token"] = access_token
    if refresh_token:
        st.session_state["sb_refresh_token"] = refresh_token
    st.session_state["sb_session"] = session


def restore_session() -> None:
    client = get_supabase_client()
    if client is None or st.session_state.get("sb_session") is not None:
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


def auth_sign_up(email: str, password: str) -> Tuple[bool, str]:
    client = get_supabase_client()
    if client is None:
        return False, "Supabase is not configured yet."
    try:
        response = client.auth.sign_up({"email": email, "password": password})
        session = getattr(response, "session", None) or (response.get("session") if isinstance(response, dict) else None)
        if session:
            persist_session_tokens(session)
        return True, "Account created."
    except Exception as exc:
        return False, f"Signup failed: {exc}"


def auth_sign_out() -> None:
    client = get_supabase_client()
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    for key in ["sb_access_token", "sb_refresh_token", "sb_session"]:
        st.session_state.pop(key, None)


def local_watchlist() -> List[str]:
    symbols = load_watchlist()
    return symbols if symbols else DEFAULT_WATCHLIST.copy()


def save_local_watchlist(symbols: List[str]) -> None:
    cleaned = []
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


def local_formulas() -> str:
    if FORMULAS_FILE.exists():
        return FORMULAS_FILE.read_text(encoding="utf-8")
    return ""


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
    client = get_supabase_client()
    user_id = get_current_user_id()
    cleaned = [s.strip().upper() for s in symbols if s.strip()]
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


def load_alert_rows() -> pd.DataFrame:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return pd.DataFrame(columns=["symbol", "alert_type", "target_value", "note", "created_at"])
    try:
        rows = client.table("user_alerts").select("symbol,alert_type,target_value,note,created_at").eq("user_id", user_id).eq("is_active", True).order("created_at", desc=True).execute()
        return pd.DataFrame(getattr(rows, "data", None) or [])
    except Exception:
        return pd.DataFrame(columns=["symbol", "alert_type", "target_value", "note", "created_at"])


def add_alert(symbol: str, alert_type: str, target_value: float, note: str) -> Tuple[bool, str]:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return False, "Login required to save alerts."
    try:
        client.table("user_alerts").insert({"user_id": user_id, "symbol": symbol.upper(), "alert_type": alert_type, "target_value": target_value, "note": note.strip(), "is_active": True}).execute()
        return True, "Alert saved."
    except Exception as exc:
        return False, f"Could not save alert: {exc}"


def load_journal_rows() -> pd.DataFrame:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return pd.DataFrame(columns=["symbol", "side", "entry_price", "status", "thesis", "created_at"])
    try:
        rows = client.table("trade_journal").select("symbol,side,entry_price,status,thesis,created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
        return pd.DataFrame(getattr(rows, "data", None) or [])
    except Exception:
        return pd.DataFrame(columns=["symbol", "side", "entry_price", "status", "thesis", "created_at"])


def add_journal_row(symbol: str, side: str, entry_price: float, thesis: str, status: str) -> Tuple[bool, str]:
    client = get_supabase_client()
    user_id = get_current_user_id()
    if client is None or user_id is None:
        return False, "Login required to save journal entries."
    try:
        client.table("trade_journal").insert({"user_id": user_id, "symbol": symbol.upper(), "side": side, "entry_price": entry_price, "thesis": thesis.strip(), "status": status}).execute()
        return True, "Journal entry saved."
    except Exception as exc:
        return False, f"Could not save journal entry: {exc}"


@st.cache_data(ttl=900, show_spinner=False)
def get_symbol_history(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False, threads=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.dropna().copy()
    if not {"Open", "High", "Low", "Close"}.issubset(df.columns):
        return df
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean().replace(0, pd.NA)
    rs = avg_gain / avg_loss
    df["RSI14"] = (100 - (100 / (1 + rs))).fillna(50.0)
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["EMA9"] = ema9
    df["EMA21"] = close.ewm(span=21, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()
    df["EMA200"] = close.ewm(span=200, adjust=False).mean()
    df["SMA20"] = close.rolling(20).mean()
    df["SMA50"] = close.rolling(50).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()
    df["ATR_PCT"] = (df["ATR14"] / close).fillna(0.0)
    df["LOW20"] = low.rolling(20).min()
    df["LOW60"] = low.rolling(60).min()
    df["HIGH20"] = high.rolling(20).max()
    df["HIGH60"] = high.rolling(60).max()
    if "Volume" in df.columns:
        df["VOL_AVG20"] = df["Volume"].rolling(20).mean()
        df["VOLUME_RATIO"] = df["Volume"] / df["VOL_AVG20"]
    return df


def detect_support_resistance(history: pd.DataFrame, current_price: float) -> tuple[float, float]:
    if history.empty:
        return current_price * 0.95, current_price * 1.05
    low20 = safe_float(history["LOW20"].iloc[-1], current_price * 0.96) if "LOW20" in history.columns else current_price * 0.96
    high20 = safe_float(history["HIGH20"].iloc[-1], current_price * 1.04) if "HIGH20" in history.columns else current_price * 1.04
    low60 = safe_float(history["LOW60"].iloc[-1], low20)
    high60 = safe_float(history["HIGH60"].iloc[-1], high20)
    support = (low20 * 0.7) + (low60 * 0.3)
    resistance = (high20 * 0.7) + (high60 * 0.3)
    return round(support, 2), round(resistance, 2)


def infer_preferred_buy(symbol: str, history: pd.DataFrame, current_price: float, support: float) -> float:
    cfg = ASSET_CONFIG.get(symbol, {})
    manual_anchor = safe_float(cfg.get("preferred_buy_price"), 0.0)
    tol_pct = safe_float(cfg.get("anchor_tolerance_pct"), 0.035)
    if history.empty:
        if manual_anchor > 0:
            return round(manual_anchor, 2)
        return round(current_price * 0.97, 2)

    ema21 = safe_float(history["EMA21"].iloc[-1], current_price)
    low20 = safe_float(history["LOW20"].iloc[-1], support)
    low60 = safe_float(history["LOW60"].iloc[-1], low20) if "LOW60" in history.columns else low20
    atr_pct = safe_float(history["ATR_PCT"].iloc[-1], 0.03)

    if manual_anchor > 0:
        adaptive = (ema21 * 0.50) + (low20 * 0.22) + (support * 0.18) + (low60 * 0.10)
        preferred = (manual_anchor * 0.72) + (adaptive * 0.28)
        drift = manual_anchor * tol_pct
        lower_bound = manual_anchor - drift
        upper_bound = manual_anchor + drift
        preferred = clamp(preferred, lower_bound, upper_bound)
    else:
        preferred = (ema21 * 0.45) + (support * 0.35) + (low20 * 0.20)
        preferred = clamp(preferred, current_price * 0.90, current_price * 0.995)

    preferred *= 1 - min(max(atr_pct * 0.10, 0.0), 0.01)
    if manual_anchor > 0:
        preferred = clamp(preferred, manual_anchor * (1 - tol_pct), manual_anchor * (1 + tol_pct))
    return round(preferred, 2)


def trend_strength_label(score: float) -> str:
    if score >= 72:
        return "Strong Uptrend"
    if score >= 57:
        return "Constructive Trend"
    if score >= 42:
        return "Mixed"
    return "Weak / Downtrend"


def entry_quality_label(score: float, trend_score: float = 50.0, dist_buy_pct: float = 0.0, today_pct: float = 0.0) -> str:
    if score >= 72:
        return "Strong Buy"
    if score >= 56:
        return "Weak Buy"
    if score >= 36:
        return "Hold / Wait"
    if trend_score >= 57 or today_pct >= 0 or dist_buy_pct > 0:
        return "Hold / Wait"
    return "Sell / Avoid"


def setup_name(trend_score: float, entry_score: float, two_day_run: float, today_pct: float, dist_buy_pct: float, extension_score: float) -> str:
    if trend_score >= 68 and dist_buy_pct <= 2.5 and today_pct <= 0 and extension_score < 48:
        return "Constructive Dip"
    if trend_score >= 60 and two_day_run >= 3.5 and today_pct < 0:
        return "Cooling Pullback"
    if trend_score >= 70 and dist_buy_pct > 4.5:
        return "Extended Runner"
    if trend_score >= 60 and today_pct > 0 and dist_buy_pct <= 3.0:
        return "Breakout Watch"
    if trend_score < 45 and today_pct < 0 and entry_score < 36:
        return "Falling Knife Risk"
    return "Balanced Setup"


def build_why_signal(trend_score: float, entry_score: float, dist_buy_pct: float, today_pct: float, two_day_run: float, rsi: float, resistance_room_pct: float) -> str:
    reasons: list[str] = []
    if trend_score >= 68:
        reasons.append("trend is constructive")
    elif trend_score < 45:
        reasons.append("trend is soft")
    if dist_buy_pct <= 2.5:
        reasons.append("price is near preferred buy")
    elif dist_buy_pct > 6:
        reasons.append("price is still above preferred buy")
    if two_day_run >= 3.5 and today_pct < 0:
        reasons.append("recent strength is cooling off")
    elif two_day_run >= 3.5 and today_pct > 0.5:
        reasons.append("recent run is still extended")
    if 38 <= rsi <= 58:
        reasons.append("RSI is in a healthier buy zone")
    elif rsi >= 66:
        reasons.append("RSI is elevated")
    if resistance_room_pct < 6:
        reasons.append("room to resistance is tight")
    if not reasons:
        reasons.append("setup is balanced but not exceptional")
    return "; ".join(reasons[:3])


def score_row(history: pd.DataFrame, symbol: str) -> dict:
    if history.empty or len(history) < 70:
        return {"symbol": symbol, "valid": False}
    last = history.iloc[-1]
    price = safe_float(last.get("Close"), 0.0)
    prev = history.iloc[-2] if len(history) > 1 else last
    today_pct = ((price / safe_float(prev.get("Close"), price)) - 1) * 100 if safe_float(prev.get("Close"), 0) else 0.0
    two_day_run = 0.0
    if len(history) >= 4:
        a = safe_float(history["Close"].iloc[-4], price)
        b = safe_float(history["Close"].iloc[-2], price)
        if a:
            two_day_run = ((b / a) - 1) * 100
    support, resistance = detect_support_resistance(history, price)
    preferred_buy = infer_preferred_buy(symbol, history, price, support)
    rsi = safe_float(last.get("RSI14"), 50.0)
    macd = safe_float(last.get("MACD"), 0.0)
    macd_signal = safe_float(last.get("MACD_SIGNAL"), 0.0)
    ema21 = safe_float(last.get("EMA21"), price)
    ema50 = safe_float(last.get("EMA50"), price)
    ema200 = safe_float(last.get("EMA200"), price)
    atr_pct = safe_float(last.get("ATR_PCT"), 0.03)

    trend_score = 50.0
    trend_score += 8 if price > ema21 else -8
    trend_score += 10 if price > ema50 else -10
    trend_score += 12 if price > ema200 else -12
    trend_score += 10 if macd > macd_signal else -10
    trend_score += 5 if macd > 0 else -5
    trend_score = clamp(trend_score, 0, 100)

    dist_buy_pct = ((price - preferred_buy) / preferred_buy) * 100 if preferred_buy else 0.0
    resistance_room_pct = ((resistance - price) / price) * 100 if price else 0.0
    support_gap_pct = ((price - support) / support) * 100 if support else 0.0

    entry_score = 56.0
    if dist_buy_pct <= -1.0:
        entry_score += 16
    elif dist_buy_pct <= 1.0:
        entry_score += 12
    elif dist_buy_pct <= 3.0:
        entry_score += 6
    elif dist_buy_pct <= 6.0:
        entry_score -= 4
    else:
        entry_score -= 14

    if 38 <= rsi <= 58:
        entry_score += 10
    elif 58 < rsi <= 63:
        entry_score += 2
    elif rsi >= 67:
        entry_score -= 10
    elif rsi < 34:
        entry_score -= 6

    if support_gap_pct <= 2.5:
        entry_score += 8
    elif support_gap_pct > 6.5:
        entry_score -= 8

    if resistance_room_pct < 6.5:
        entry_score -= 6
    if resistance_room_pct < 4.5:
        entry_score -= 6

    if two_day_run >= 4.0 and today_pct < 0:
        entry_score += 8
    elif two_day_run >= 4.0 and today_pct > 0.5:
        entry_score -= 8

    if dist_buy_pct > 2.0 and rsi >= 62:
        entry_score -= 8
    if dist_buy_pct > 2.0 and resistance_room_pct < 8.0:
        entry_score -= 6

    if trend_score >= 60 and entry_score < 38:
        entry_score += 6
    elif trend_score >= 70 and dist_buy_pct <= 8.0 and rsi < 66:
        entry_score += 4

    if trend_score >= 57 and dist_buy_pct <= 12.0:
        entry_score = max(entry_score, 38.0)
    if trend_score >= 72 and dist_buy_pct <= 9.0 and rsi < 66:
        entry_score = max(entry_score, 44.0)

    entry_score = clamp(entry_score, 0, 100)

    setup_quality = round((trend_score * 0.42) + (entry_score * 0.58), 1)
    pullback_quality = round(clamp(50 + min(two_day_run, 8) * 3 - max(today_pct, 0) * 2.2 + (8 - max(dist_buy_pct, 0)) * 2.3, 0, 100), 1)
    stop_price = min(support * 0.99, preferred_buy * (1 - max(atr_pct * 0.7, 0.012)))
    risk = max(preferred_buy - stop_price, preferred_buy * 0.005)
    reward = max(resistance - preferred_buy, 0)
    risk_adjusted_entry = round(clamp((reward / risk) * 20 if risk > 0 else 0, 0, 100), 1)
    extension_score = round(clamp(max(dist_buy_pct, 0) * 6.5 + max(rsi - 58, 0) * 2.0 + max(5 - resistance_room_pct, 0) * 6.5, 0, 100), 1)
    trend_entry_gap = round(trend_score - entry_score, 1)

    buy_score = round(clamp(
        (trend_score * 0.26)
        + (entry_score * 0.38)
        + (pullback_quality * 0.16)
        + (risk_adjusted_entry * 0.12)
        + ((100 - extension_score) * 0.08),
        0, 100,
    ), 1)

    return {
        "symbol": symbol,
        "asset_class": "Crypto" if is_crypto(symbol) else "Stock / ETF",
        "price": round(price, 2),
        "today_change_pct": round(today_pct, 2),
        "two_day_run_pct": round(two_day_run, 2),
        "support": support,
        "resistance": resistance,
        "preferred_buy_price": preferred_buy,
        "distance_from_buy_pct": round(dist_buy_pct, 2),
        "rsi_14": round(rsi, 1),
        "trend_strength_score": round(trend_score, 1),
        "trend_strength": trend_strength_label(trend_score),
        "entry_quality_score": round(entry_score, 1),
        "entry_quality": entry_quality_label(entry_score, trend_score, dist_buy_pct, today_pct),
        "setup_name": setup_name(trend_score, entry_score, two_day_run, today_pct, dist_buy_pct, extension_score),
        "why_signal": build_why_signal(trend_score, entry_score, dist_buy_pct, today_pct, two_day_run, rsi, resistance_room_pct),
        "buy_score": buy_score,
        "setup_quality": setup_quality,
        "pullback_quality": pullback_quality,
        "risk_adjusted_entry": risk_adjusted_entry,
        "extension_score": extension_score,
        "trend_entry_gap": trend_entry_gap,
        "valid": True,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def scan_watchlist(symbols: tuple[str, ...], daily_period: str) -> pd.DataFrame:
    rows: List[dict] = []
    for symbol in symbols:
        history = get_symbol_history(symbol, period=daily_period, interval="1d")
        scored = score_row(history, symbol)
        if scored.get("valid"):
            rows.append(scored)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["entry_quality_score", "buy_score", "trend_strength_score"], ascending=[False, False, False]).reset_index(drop=True)
    df["best_buy_today_rank"] = range(1, len(df) + 1)
    return df


def apply_signal_memory(current_df: pd.DataFrame, previous_df: pd.DataFrame | None) -> pd.DataFrame:
    if current_df.empty:
        return current_df
    df = current_df.copy()
    if previous_df is None or previous_df.empty or "symbol" not in previous_df.columns:
        df["signal_transition"] = "New"
        df["preferred_buy_change_pct"] = 0.0
        return df
    prev = previous_df[[c for c in ["symbol", "entry_quality", "preferred_buy_price", "buy_score"] if c in previous_df.columns]].copy()
    prev = prev.rename(columns={"entry_quality": "prev_entry_quality", "preferred_buy_price": "prev_preferred_buy", "buy_score": "prev_buy_score"})
    df = df.merge(prev, on="symbol", how="left")
    order = {"Strong Buy": 4, "Weak Buy": 3, "Hold / Wait": 2, "Sell / Avoid": 1}
    def transition(row):
        cur = row.get("entry_quality")
        prevq = row.get("prev_entry_quality")
        if pd.isna(prevq):
            return "New"
        if cur == prevq:
            return "Unchanged"
        if order.get(str(cur), 0) > order.get(str(prevq), 0):
            return "Improving"
        return "Weakening"
    df["signal_transition"] = df.apply(transition, axis=1)
    def buy_delta(row):
        prevv = safe_float(row.get("prev_preferred_buy"), 0.0)
        curv = safe_float(row.get("preferred_buy_price"), 0.0)
        if prevv <= 0:
            return 0.0
        return round(((curv - prevv) / prevv) * 100, 2)
    df["preferred_buy_change_pct"] = df.apply(buy_delta, axis=1)
    df = df.drop(columns=[c for c in ["prev_entry_quality", "prev_preferred_buy", "prev_buy_score"] if c in df.columns])
    return df


def build_scan_signature(symbols: List[str], daily_period: str, formulas_text: str) -> str:
    payload = "|".join(symbols) + f"::{daily_period}::{formulas_text.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resample_ohlcv(data: pd.DataFrame, rule: str) -> pd.DataFrame:
    if data.empty:
        return data
    working = data.copy()
    if not isinstance(working.index, pd.DatetimeIndex):
        working.index = pd.to_datetime(working.index)
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    if "Volume" in working.columns:
        agg["Volume"] = "sum"
    resampled = working.resample(rule).agg(agg).dropna(subset=["Open", "High", "Low", "Close"])
    return resampled


def get_chart_history(symbol: str, bar_interval: str) -> pd.DataFrame:
    window = CHART_WINDOWS.get(bar_interval, "1y")
    if bar_interval == "4h":
        raw = get_symbol_history(symbol, period=window, interval="1h")
        if raw.empty:
            return raw
        return resample_ohlcv(raw[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in raw.columns]], "4h")
    yf_map = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "60m", "1d": "1d"}
    return get_symbol_history(symbol, period=window, interval=yf_map.get(bar_interval, "1d"))


def limit_chart_bars(history: pd.DataFrame, bar_interval: str) -> pd.DataFrame:
    limits = {"5m": 180, "15m": 180, "30m": 160, "1h": 140, "4h": 120, "1d": 180}
    return history.tail(limits.get(bar_interval, 180)).copy()


def build_chart(history: pd.DataFrame, symbol: str, preferred_buy: float, support: float, resistance: float, overlays: dict[str, bool]) -> go.Figure:
    fig = go.Figure()
    if history.empty:
        return fig
    fig.add_trace(go.Candlestick(
        x=history.index, open=history["Open"], high=history["High"], low=history["Low"], close=history["Close"], name=symbol,
        increasing_line_color="#86f7ff", decreasing_line_color="#ffd28e"
    ))
    if overlays.get("EMA9") and "EMA9" in history.columns:
        fig.add_trace(go.Scatter(x=history.index, y=history["EMA9"], mode="lines", name="EMA9", line=dict(color="#7DEBFF", width=1.5)))
    if overlays.get("EMA21") and "EMA21" in history.columns:
        fig.add_trace(go.Scatter(x=history.index, y=history["EMA21"], mode="lines", name="EMA21", line=dict(color="#9AF7FF", width=1.8)))
    if overlays.get("SMA20") and "SMA20" in history.columns:
        fig.add_trace(go.Scatter(x=history.index, y=history["SMA20"], mode="lines", name="SMA20", line=dict(color="#FFE46B", width=1.4)))
    if overlays.get("SMA50") and "SMA50" in history.columns:
        fig.add_trace(go.Scatter(x=history.index, y=history["SMA50"], mode="lines", name="SMA50", line=dict(color="#FFB37D", width=1.4)))

    band = preferred_buy * 0.01 if preferred_buy else 0
    if preferred_buy > 0:
        fig.add_hrect(y0=preferred_buy - band * 1.4, y1=preferred_buy + band * 1.4, fillcolor="rgba(125,235,255,0.09)", line_width=0)
        fig.add_hrect(y0=preferred_buy - band * 0.6, y1=preferred_buy + band * 0.6, fillcolor="rgba(125,235,255,0.18)", line_width=0)
        fig.add_hline(y=preferred_buy, line_color="#7DEBFF", line_dash="dot", annotation_text="Preferred Buy")
    if support > 0:
        fig.add_hline(y=support, line_color="#9AF7FF", line_dash="dash", annotation_text="Support")
    if resistance > 0:
        fig.add_hline(y=resistance, line_color="#FFE46B", line_dash="dash", annotation_text="Resistance")

    fig.update_layout(
        title=f"{symbol} chart",
        height=560,
        xaxis_rangeslider_visible=False,
        dragmode="pan",
        hovermode="x unified",
        bargap=0.03,
        uirevision=f"{symbol}-chart",
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(tickformat=",.2f", automargin=True, nticks=12)
    return fig


def build_comparison(symbol_a: str, symbol_b: str) -> go.Figure:
    fig = go.Figure()
    if not symbol_b:
        return fig
    a = get_symbol_history(symbol_a, period="6mo", interval="1d")
    b = get_symbol_history(symbol_b, period="6mo", interval="1d")
    if a.empty or b.empty:
        return fig
    a_norm = (a["Close"] / safe_float(a["Close"].iloc[0], 1.0)) * 100
    b_norm = (b["Close"] / safe_float(b["Close"].iloc[0], 1.0)) * 100
    fig.add_trace(go.Scatter(x=a.index, y=a_norm, mode="lines", name=symbol_a, line=dict(color="#7DEBFF", width=2)))
    fig.add_trace(go.Scatter(x=b.index, y=b_norm, mode="lines", name=symbol_b, line=dict(color="#FFE46B", width=2)))
    fig.update_layout(title="Relative performance (start = 100)", height=320, margin=dict(l=20, r=20, t=50, b=20), dragmode="pan")
    return fig


def compute_short_term_context(history: pd.DataFrame, selected_row: pd.Series) -> dict:
    if history.empty:
        return {}
    trend_strength = selected_row.get("trend_strength", "Mixed")
    entry_quality = selected_row.get("entry_quality", "No Setup")
    buy_score = safe_float(selected_row.get("buy_score"), 0)
    today_pct = safe_float(selected_row.get("today_change_pct"), 0)
    run_pct = safe_float(selected_row.get("two_day_run_pct"), 0)
    reason = []
    if run_pct >= 4 and today_pct < 0:
        reason.append("recent run-up is cooling off")
    elif run_pct >= 4 and today_pct > 0:
        reason.append("still extended after recent run-up")
    if safe_float(selected_row.get("distance_from_buy_pct"), 0) <= 2.5:
        reason.append("price is near preferred buy")
    elif safe_float(selected_row.get("distance_from_buy_pct"), 0) > 5:
        reason.append("price is still above preferred buy")
    if safe_float(selected_row.get("extension_score"), 0) > 55:
        reason.append("extension is elevated")
    return {
        "trend_strength": trend_strength,
        "entry_quality": entry_quality,
        "buy_score": round(buy_score, 1),
        "read_text": "; ".join(reason[:3]) if reason else "setup is balanced but not exceptional",
    }


def compute_annual_scenarios(history: pd.DataFrame, selected_row: pd.Series) -> dict:
    if history.empty:
        return {"bear": "-", "base": "-", "bull": "-"}
    price = safe_float(selected_row.get("price"), safe_float(history["Close"].iloc[-1], 0))
    trend = safe_float(selected_row.get("trend_strength_score"), 50)
    entry = safe_float(selected_row.get("entry_quality_score"), 50)
    six_month_change = 0.0
    if len(history) >= 126 and safe_float(history["Close"].iloc[-126], 0):
        six_month_change = ((price / safe_float(history["Close"].iloc[-126], price)) - 1) * 100
    vol = safe_float(history["ATR_PCT"].iloc[-1], 0.03) * 100
    base = clamp((six_month_change * 0.45) + ((trend - 50) * 0.55), -18, 42)
    bull = clamp(base + max(10, vol * 2.4) + max((entry - 50) * 0.3, 0), 0, 95)
    bear = clamp(base - max(12, vol * 2.8) - max((60 - trend) * 0.35, 0), -65, 20)
    return {"bear": f"{bear:+.1f}%", "base": f"{base:+.1f}%", "bull": f"{bull:+.1f}%"}


def estimate_trade_plan(selected_row: pd.Series) -> dict:
    price = safe_float(selected_row.get("price"), 0)
    entry = safe_float(selected_row.get("preferred_buy_price"), price)
    support = safe_float(selected_row.get("support"), entry * 0.95)
    resistance = safe_float(selected_row.get("resistance"), entry * 1.06)
    stop = min(support * 0.99, entry * 0.965)
    risk = max(entry - stop, entry * 0.005)
    target = max(resistance, entry + risk * 2)
    rr = (target - entry) / risk if risk > 0 else 0.0
    return {"entry": round(entry, 2), "stop": round(stop, 2), "target": round(target, 2), "rr": round(rr, 2)}


def get_selected_headlines(symbol: str) -> List[str]:
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news or []
        titles = [str(x.get("title", "")).strip() for x in news[:5] if str(x.get("title", "")).strip()]
        return titles
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def get_watchlist_headlines(symbols: tuple[str, ...]) -> List[dict]:
    items: List[dict] = []
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news or []
            for x in news[:4]:
                title = str(x.get("title", "")).strip()
                if not title:
                    continue
                publisher = str(x.get("publisher", "Yahoo Finance")).strip() or "Yahoo Finance"
                link = str(x.get("link", "")).strip()
                provider_time = x.get("providerPublishTime") or x.get("provider_publish_time")
                items.append({"symbol": symbol, "title": title, "publisher": publisher, "link": link, "published": provider_time or 0})
        except Exception:
            continue
    items.sort(key=lambda x: x.get("published", 0), reverse=True)
    seen = set()
    deduped = []
    for item in items:
        key = (item["symbol"], item["title"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:30]


def stat_card(title: str, value: str, subtitle: str = "") -> str:
    return f'<div class="stat-card"><div class="stat-title">{title}</div><div class="stat-value">{value}</div><div class="stat-sub">{subtitle}</div></div>'


restore_session()

st.markdown('<div class="main-title">NeuroTrade v15</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">NeuroTrade thinks like market neurons: sharper entries, cleaner organization, and a faster workstation.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Account")
    if get_supabase_client() is None:
        st.caption("Supabase not configured. Local mode is active.")
    elif get_current_user_id():
        st.success(f"Signed in as {get_current_user_email() or 'user'}")
        if st.button("Sign out", use_container_width=True):
            auth_sign_out()
            st.rerun()
    else:
        mode = st.radio("Auth", ["Login", "Sign up"], horizontal=True)
        with st.form("auth_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Continue", use_container_width=True)
        if submitted:
            ok, msg = auth_sign_in(email.strip(), password) if mode == "Login" else auth_sign_up(email.strip(), password)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.divider()
    st.header("Scan controls")
    daily_period = st.selectbox("Dashboard scan range", ["6mo", "1y", "2y"], index=1)
    max_scan = st.slider("Symbols to scan", min_value=6, max_value=20, value=10, step=1)
    scan_now = st.button("Scan market now", use_container_width=True)

    st.divider()
    st.header("Workstation")
    chart_bar = st.selectbox("Chart bar interval", BAR_OPTIONS, index=4)
    auto_refresh_chart = st.toggle("Auto-refresh workstation", value=False)
    refresh_seconds = st.selectbox("Refresh every", [15, 30, 60, 120], index=1)
    show_ema9 = st.toggle("Show EMA9", value=True)
    show_ema21 = st.toggle("Show EMA21", value=True)
    show_sma20 = st.toggle("Show SMA20", value=False)
    show_sma50 = st.toggle("Show SMA50", value=False)
    if auto_refresh_chart:
        st_autorefresh(interval=refresh_seconds * 1000, key="workstation_refresh")

    st.divider()
    st.header("Watchlist")
    if "watchlist_editor_v12" not in st.session_state:
        st.session_state.watchlist_editor_v12 = "\n".join(load_user_watchlist())
    watchlist_text = st.text_area("Tickers", key="watchlist_editor_v12", height=180)
    if st.button("Save watchlist", use_container_width=True):
        symbols = [line.strip().upper() for line in watchlist_text.splitlines() if line.strip()]
        ok, msg = save_user_watchlist(symbols)
        st.success(msg) if ok else st.warning(msg)
        st.session_state.pop("scan_df", None)
        st.session_state.pop("scan_signature", None)
        st.rerun()

    st.divider()
    st.header("Formulas")
    if "formula_editor_v12" not in st.session_state:
        st.session_state.formula_editor_v12 = load_user_formulas()
    formula_text = st.text_area("Notes / custom formulas", key="formula_editor_v12", height=150)
    if st.button("Save formulas", use_container_width=True):
        ok, msg = save_user_formulas(formula_text)
        st.success(msg) if ok else st.warning(msg)
        st.session_state.pop("scan_df", None)
        st.session_state.pop("scan_signature", None)

watchlist_symbols = [s.strip().upper() for s in st.session_state.watchlist_editor_v12.splitlines() if s.strip()][:max_scan]
formulas_text = st.session_state.formula_editor_v12
scan_signature = build_scan_signature(watchlist_symbols, daily_period, formulas_text)

needs_scan = st.session_state.get("scan_signature") != scan_signature or "scan_df" not in st.session_state or scan_now
if needs_scan:
    with st.spinner(f"Scanning {len(watchlist_symbols)} symbols..."):
        previous_scan = st.session_state.get("scan_df", pd.DataFrame())
        fresh_scan = scan_watchlist(tuple(watchlist_symbols), daily_period)
        st.session_state.previous_scan_df = previous_scan
        st.session_state.scan_df = apply_signal_memory(fresh_scan, previous_scan)
        st.session_state.scan_signature = scan_signature
        st.session_state.scan_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

scan_df: pd.DataFrame = st.session_state.get("scan_df", pd.DataFrame())

if scan_df.empty:
    st.warning("No scan results. Check your watchlist symbols.")
    st.stop()

st.caption(f"Using cached market scan from {st.session_state.get('scan_timestamp', '-')}. The dashboard stays fast while the workstation loads only the selected ticker. Signal memory tracks whether setups are improving or weakening between scans.")

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Tracked symbols", len(scan_df))
with m2:
    st.metric("Strong/Weak buys", int(scan_df["entry_quality"].isin(["Strong Buy", "Weak Buy"]).sum()))
with m3:
    st.metric("Avg buy score", f"{scan_df['buy_score'].mean():.1f}")
with m4:
    st.metric("Constructive trends", int(scan_df["trend_strength"].isin(["Strong Uptrend", "Constructive Trend"]).sum()))

crypto_df = scan_df[scan_df["asset_class"] == "Crypto"]
stock_df = scan_df[scan_df["asset_class"] != "Crypto"]
crypto_text = f"Crypto summary — {len(crypto_df)} tracked | avg buy score {crypto_df['buy_score'].mean():.1f}" if not crypto_df.empty else "Crypto summary — no crypto in watchlist"
stock_text = f"Stock / ETF summary — {len(stock_df)} tracked | avg buy score {stock_df['buy_score'].mean():.1f}" if not stock_df.empty else "Stock / ETF summary — no stock / ETF in watchlist"
left_summary, right_summary = st.columns(2)
with left_summary:
    st.markdown(f'<div class="gold-box"><strong>{crypto_text}</strong><br><span class="small-note">Use trend strength first, entry quality second, buy score third.</span></div>', unsafe_allow_html=True)
with right_summary:
    st.markdown(f'<div class="soft-box"><strong>{stock_text}</strong><br><span class="small-note">Fast dashboard, deeper selected-ticker view with signal memory and setup intelligence.</span></div>', unsafe_allow_html=True)

dashboard_tab, workstation_tab, news_tab, saved_tab, settings_tab = st.tabs(["Dashboard", "Workstation", "News / Media", "Saved Tools", "Settings"])

with dashboard_tab:
    st.markdown('<div class="section-header">Scan results</div>', unsafe_allow_html=True)
    st.markdown('<div class="soft-box"><strong>Short-term scan</strong><br><span class="small-note">Today % and 2-day run % help spot cooling pullbacks after short runs. Trend strength shows the broader path, while entry quality now separates buyable dips from names that are better left on watch.</span></div>', unsafe_allow_html=True)
    display_cols = [
        "best_buy_today_rank", "symbol", "asset_class", "price", "trend_strength", "entry_quality", "signal_transition", "buy_score",
        "today_change_pct", "two_day_run_pct", "preferred_buy_price", "preferred_buy_change_pct", "distance_from_buy_pct",
        "setup_name", "setup_quality", "pullback_quality", "risk_adjusted_entry", "extension_score", "trend_entry_gap",
    ]
    display_df = scan_df[display_cols].copy()
    for col in ["price", "preferred_buy_price"]:
        display_df[col] = display_df[col].map(lambda x: f"${safe_float(x):,.2f}")
    for col in [
        "buy_score", "today_change_pct", "two_day_run_pct", "preferred_buy_change_pct", "distance_from_buy_pct", "setup_quality",
        "pullback_quality", "risk_adjusted_entry", "extension_score", "trend_entry_gap",
    ]:
        display_df[col] = display_df[col].map(lambda x: f"{safe_float(x):.1f}")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    top = scan_df.head(5)
    st.markdown('<div class="section-header">Top ranked today</div>', unsafe_allow_html=True)
    cols = st.columns(min(5, len(top)))
    for col, (_, row) in zip(cols, top.iterrows()):
        badge_class = "pill-good" if row["entry_quality"] in ["Strong Buy", "Weak Buy"] else "pill-wait" if row["entry_quality"] == "Hold / Wait" else "pill-risk"
        col.markdown(
            f'<div class="soft-box"><strong>{row["symbol"]}</strong><br>'
            f'<span class="pill {badge_class}">{row["entry_quality"]}</span>'
            f'<span class="pill pill-good">{row["trend_strength"]}</span><br>'
            f'<span class="small-note">{row["setup_name"]} | {row["signal_transition"]} | Buy score {row["buy_score"]:.1f} | Today {row["today_change_pct"]:+.2f}% | 2-day run {row["two_day_run_pct"]:+.2f}%</span></div>',
            unsafe_allow_html=True,
        )

with workstation_tab:
    st.markdown('<div class="section-header">Selected ticker workstation</div>', unsafe_allow_html=True)
    selected_symbol = st.selectbox("Select ticker", options=scan_df["symbol"].tolist(), index=0)
    selected_row = scan_df[scan_df["symbol"] == selected_symbol].iloc[0]
    chart_history = get_chart_history(selected_symbol, chart_bar)
    if chart_history.empty:
        st.warning("No chart data available for this symbol.")
    else:
        chart_history = limit_chart_bars(chart_history, chart_bar)
        daily_history = get_symbol_history(selected_symbol, period="1y", interval="1d")
        if not daily_history.empty:
            # merge indicator columns for slower intervals when available
            for col in ["EMA9", "EMA21", "SMA20", "SMA50"]:
                if col in daily_history.columns and col not in chart_history.columns and chart_bar == "1d":
                    chart_history[col] = daily_history[col]
        overlays = {"EMA9": show_ema9, "EMA21": show_ema21, "SMA20": show_sma20, "SMA50": show_sma50}
        work_left, work_right = st.columns([1.35, 0.95])
        with work_left:
            fig = build_chart(chart_history, selected_symbol, safe_float(selected_row["preferred_buy_price"]), safe_float(selected_row["support"]), safe_float(selected_row["resistance"]), overlays)
            st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})
            compare_options = [s for s in scan_df["symbol"].tolist() if s != selected_symbol]
            compare_symbol = st.selectbox("Compare against", options=compare_options, index=0 if compare_options else None)
            if compare_options:
                compare_fig = build_comparison(selected_symbol, compare_symbol)
                st.plotly_chart(compare_fig, use_container_width=True, config={"scrollZoom": True, "displaylogo": False})
        with work_right:
            short_term = compute_short_term_context(daily_history if not daily_history.empty else chart_history, selected_row)
            st.markdown(stat_card("Trend Strength", str(short_term.get("trend_strength", "-")), short_term.get("read_text", "")), unsafe_allow_html=True)
            st.markdown(stat_card("Entry Quality", str(short_term.get("entry_quality", "-")), f"Preferred buy {format_num(selected_row['preferred_buy_price'], prefix='$')} | Distance {safe_float(selected_row['distance_from_buy_pct']):+.1f}%"), unsafe_allow_html=True)
            st.markdown(stat_card("Buy Score", f"{safe_float(short_term.get('buy_score'), 0):.1f}", "Secondary ranking signal, not a chase signal."), unsafe_allow_html=True)
            st.markdown(stat_card("Setup Name", str(selected_row.get("setup_name", "Balanced Setup")), str(selected_row.get("why_signal", ""))), unsafe_allow_html=True)
            st.markdown(stat_card("Signal Memory", str(selected_row.get("signal_transition", "Unchanged")), f"Preferred buy change {safe_float(selected_row.get('preferred_buy_change_pct'), 0):+.2f}%"), unsafe_allow_html=True)

            scenarios = compute_annual_scenarios(daily_history if not daily_history.empty else chart_history, selected_row)
            st.markdown('<div class="section-header">12-month scenario estimates</div>', unsafe_allow_html=True)
            s1, s2, s3 = st.columns(3)
            s1.markdown(stat_card("Bear", scenarios["bear"], "Lower path"), unsafe_allow_html=True)
            s2.markdown(stat_card("Base", scenarios["base"], "Expected path"), unsafe_allow_html=True)
            s3.markdown(stat_card("Bull", scenarios["bull"], "High path"), unsafe_allow_html=True)

            plan = estimate_trade_plan(selected_row)
            st.markdown('<div class="section-header">Trade plan</div>', unsafe_allow_html=True)
            p0, p1, p2 = st.columns(3)
            p0.markdown(stat_card("Current Price", f"${safe_float(selected_row['price']):,.2f}", f"Preferred buy ${plan['entry']:,.2f}"), unsafe_allow_html=True)
            p1.markdown(stat_card("Entry", f"${plan['entry']:,.2f}", f"Target ${plan['target']:,.2f}"), unsafe_allow_html=True)
            p2.markdown(stat_card("Stop", f"${plan['stop']:,.2f}", f"R:R {plan['rr']:.2f}"), unsafe_allow_html=True)

            st.markdown('<div class="section-header">Formula layer</div>', unsafe_allow_html=True)
            f1, f2 = st.columns(2)
            f1.markdown(stat_card("Setup Quality", f"{safe_float(selected_row['setup_quality']):.1f}", "Trend + entry blend"), unsafe_allow_html=True)
            f2.markdown(stat_card("Pullback Quality", f"{safe_float(selected_row['pullback_quality']):.1f}", "2-day run + current pullback"), unsafe_allow_html=True)
            f3, f4 = st.columns(2)
            f3.markdown(stat_card("Risk-Adjusted Entry", f"{safe_float(selected_row['risk_adjusted_entry']):.1f}", "Reward vs stop risk"), unsafe_allow_html=True)
            f4.markdown(stat_card("Extension Score", f"{safe_float(selected_row['extension_score']):.1f}", "Higher = more extended"), unsafe_allow_html=True)
            st.markdown(stat_card("Trend vs Entry Gap", f"{safe_float(selected_row['trend_entry_gap']):+.1f}", "Positive means trend is better than the entry right now."), unsafe_allow_html=True)
            st.markdown(stat_card("Why This Signal", str(selected_row.get("entry_quality", "-")), str(selected_row.get("why_signal", ""))), unsafe_allow_html=True)

            if st.button("Check selected ticker news", use_container_width=True):
                headlines = get_selected_headlines(selected_symbol)
                if headlines:
                    st.markdown('<div class="section-header">Selected ticker headlines</div>', unsafe_allow_html=True)
                    for headline in headlines:
                        st.write(f"• {headline}")
                else:
                    st.info("No fresh Yahoo headlines found for this ticker right now.")


with news_tab:
    st.markdown('<div class="section-header">Watchlist news / media</div>', unsafe_allow_html=True)
    st.markdown('<div class="soft-box"><strong>Saved tickers only</strong><br><span class="small-note">This tab scans Yahoo Finance headlines only for the tickers currently saved in your watchlist. Use Refresh News when you want a fresh pull.</span></div>', unsafe_allow_html=True)
    refresh_news = st.button("Refresh watchlist news", use_container_width=True)
    news_signature = "|".join(watchlist_symbols)
    if refresh_news or st.session_state.get("news_signature") != news_signature or "watchlist_news" not in st.session_state:
        with st.spinner("Scanning watchlist headlines..."):
            st.session_state.watchlist_news = get_watchlist_headlines(tuple(watchlist_symbols))
            st.session_state.news_signature = news_signature
    news_items = st.session_state.get("watchlist_news", [])
    if not news_items:
        st.info("No recent Yahoo Finance headlines found for your saved tickers right now.")
    else:
        for item in news_items:
            title = item.get("title", "")
            symbol = item.get("symbol", "")
            publisher = item.get("publisher", "Yahoo Finance")
            link = item.get("link", "")
            if link:
                st.markdown(f'<div class="soft-box"><strong>{symbol}</strong><br><span class="small-note">{publisher}</span><br><a href="{link}" target="_blank">{title}</a></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="soft-box"><strong>{symbol}</strong><br><span class="small-note">{publisher}</span><br>{title}</div>', unsafe_allow_html=True)

with saved_tab:
    st.markdown('<div class="section-header">Private saved tools</div>', unsafe_allow_html=True)
    if get_current_user_id() is None:
        st.info("Sign in to use saved alerts and journal entries. Other users only see their own saved data.")
    else:
        alert_col, journal_col = st.columns(2)
        with alert_col:
            st.markdown('<div class="soft-box"><strong>Saved alerts</strong></div>', unsafe_allow_html=True)
            with st.form("alert_form"):
                alert_symbol = st.selectbox("Alert ticker", options=scan_df["symbol"].tolist())
                alert_type = st.selectbox("Alert type", ["price_above", "price_below", "near_preferred_buy"])
                alert_value = st.number_input("Target value", min_value=0.0, value=safe_float(scan_df.iloc[0]["preferred_buy_price"], 0.0))
                alert_note = st.text_input("Note")
                add_alert_submit = st.form_submit_button("Save alert")
            if add_alert_submit:
                ok, msg = add_alert(alert_symbol, alert_type, alert_value, alert_note)
                st.success(msg) if ok else st.warning(msg)
            alerts_df = load_alert_rows()
            if not alerts_df.empty:
                st.dataframe(alerts_df, use_container_width=True, hide_index=True)

        with journal_col:
            st.markdown('<div class="soft-box"><strong>Trade journal</strong></div>', unsafe_allow_html=True)
            with st.form("journal_form"):
                journal_symbol = st.selectbox("Journal ticker", options=scan_df["symbol"].tolist(), key="journal_symbol")
                journal_side = st.selectbox("Side", ["Long", "Short", "Watch"], key="journal_side")
                journal_entry = st.number_input("Entry price", min_value=0.0, value=safe_float(scan_df.iloc[0]["price"], 0.0), key="journal_entry")
                journal_status = st.selectbox("Status", ["Open", "Closed", "Watchlist"], key="journal_status")
                journal_thesis = st.text_area("Thesis", key="journal_thesis")
                add_journal_submit = st.form_submit_button("Save entry")
            if add_journal_submit:
                ok, msg = add_journal_row(journal_symbol, journal_side, journal_entry, journal_thesis, journal_status)
                st.success(msg) if ok else st.warning(msg)
            journal_df = load_journal_rows()
            if not journal_df.empty:
                st.dataframe(journal_df, use_container_width=True, hide_index=True)

with settings_tab:
    st.markdown('<div class="section-header">App notes</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="soft-box"><strong>NeuroTrade v15</strong><br>'
        f'<span class="small-note">Dashboard scans only the watchlist and caches the result. Workstation loads deeper analysis only for the selected ticker. News and media stay in their own tab and only scan saved watchlist tickers. Sunset background stays while key headers and cards use sky-blue accents. Project folder: {BASE_DIR}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="section-header">Suggested custom formulas</div>', unsafe_allow_html=True)
    st.code(
        """Setup Quality = 45% Trend Strength + 55% Entry Quality
Pullback Quality = recent 2-day run + current red day + distance to preferred buy
Risk-Adjusted Entry = reward to resistance versus downside to stop
Extension Score = extension above preferred buy + hot RSI + limited room to resistance
Trend vs Entry Gap = trend score - entry score
Preferred Buy Engine = EMA21 + pullback structure + support clustering + ATR cooloff""",
        language="text",
    )

