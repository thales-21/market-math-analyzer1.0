
# coding: utf-8
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import hashlib
import httpx
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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

from market_math_analyzer_v2 import BASE_DIR, FORMULAS_FILE, WATCHLIST_FILE, load_watchlist, run_analysis

st.set_page_config(page_title="Market Math Analyzer V5 Live", layout="wide")

CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC")
CRYPTO_KEYWORDS = {"BTC","ETH","SOL","XRP","ADA","DOGE","HBAR","ATOM","BNB","AVAX","LINK"}
CHART_PERIOD_OPTIONS = ["1d","5d","1mo","3mo","6mo","1y","2y","5y"]
DEFAULT_WATCHLIST = ["BTC-USD","ETH-USD","SOL-USD","XRP-USD","ADA-USD","DOGE-USD","HBAR-USD","ATOM-USD","BNB-USD","AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL","SPY","QQQ","GLD","SLV"]
DATA_FEED_OPTIONS = ["Yahoo Finance", "Polygon", "Finnhub", "Alpaca", "Twelve Data"]
ASSET_CONFIG = {
    "BTC-USD": {"preferred_buy_price": 71000.0, "max_chase_pct": 0.045, "hard_overextended_pct": 0.09, "rsi_buy_min": 38, "rsi_buy_max": 58, "rsi_hot": 67, "volatility_tolerance": 0.04},
    "SOL-USD": {"preferred_buy_price": 81.0, "max_chase_pct": 0.06, "hard_overextended_pct": 0.11, "rsi_buy_min": 36, "rsi_buy_max": 60, "rsi_hot": 70, "volatility_tolerance": 0.07},
}
DEFAULT_PULLBACK_CONFIG = {"preferred_buy_price": 0.0, "max_chase_pct": 0.05, "hard_overextended_pct": 0.10, "rsi_buy_min": 40, "rsi_buy_max": 58, "rsi_hot": 68, "volatility_tolerance": 0.06}
POSITIVE_WORDS = {"beat","beats","surge","surges","rally","approval","approved","partnership","adoption","record","strong","bullish","breakout","launch","growth","gains","upgrade","buyback","profit","profits","demand","expansion","wins","momentum"}
NEGATIVE_WORDS = {"miss","misses","drop","drops","plunge","plunges","lawsuit","probe","fraud","hack","hacked","risk","downgrade","bearish","weak","delay","selloff","loss","losses","fall","falls","concern","warning","uncertain","volatility","cuts","cut","recession","tariff","ban"}

st.markdown("""
<style>
.stApp {background: radial-gradient(circle at top left, rgba(255, 182, 92, 0.28) 0%, rgba(255, 182, 92, 0.02) 32%), radial-gradient(circle at top right, rgba(255, 106, 136, 0.22) 0%, rgba(255, 106, 136, 0.03) 28%), linear-gradient(180deg, #1f1029 0%, #34142f 24%, #5b2245 48%, #8a3b4a 72%, #f09a61 100%); color: #fff7ef;}
.main-title { color: #fff7ef; font-size: 2rem; font-weight: 800; margin-bottom: 0.15rem; text-shadow: 0 0 14px rgba(255, 182, 92, 0.22); }
.sub-title { color: #ffd7c0; margin-bottom: 1rem; }
.overview-box, .accent-card, .accent-card-soft, .alert-card { border-radius: 18px; padding: 0.95rem 1rem; box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22); }
.overview-box { background: linear-gradient(180deg, rgba(66, 25, 56, 0.72) 0%, rgba(37, 16, 46, 0.92) 100%); border: 1px solid rgba(255, 190, 120, 0.18); margin-bottom: 0.8rem; }
.accent-card { background: linear-gradient(180deg, rgba(70, 24, 57, 0.92) 0%, rgba(41, 17, 48, 0.95) 100%); border-left: 6px solid #ff9f68; color: #fff7ef; }
.accent-card-soft { background: linear-gradient(180deg, rgba(84, 34, 53, 0.92) 0%, rgba(47, 20, 49, 0.95) 100%); border-left: 6px solid #ffd36e; color: #fff7ef; }
.signal-pill { display: inline-block; padding: 0.38rem 0.72rem; border-radius: 999px; font-size: 0.88rem; font-weight: 800; margin-bottom: 0.45rem; }
.pill-strong-buy { background: rgba(255, 224, 118, 0.16); border: 1px solid rgba(255, 224, 118, 0.45); color: #fff2a6; }
.pill-buy, .pill-moderate-buy { background: rgba(255, 169, 94, 0.14); border: 1px solid rgba(255, 169, 94, 0.42); color: #ffd9a8; }
.pill-hold { background: rgba(255, 209, 136, 0.10); border: 1px solid rgba(255, 209, 136, 0.30); color: #ffe0b0; }
.pill-avoid { background: rgba(255, 130, 146, 0.12); border: 1px solid rgba(255, 130, 146, 0.28); color: #ffbac3; }
.small-note { color: #ffe7d7; }
div[data-testid="stMetric"] { background: linear-gradient(180deg, rgba(66, 25, 56, 0.92) 0%, rgba(37, 16, 46, 0.94) 100%); border-radius: 18px; padding: 0.75rem; border: 1px solid rgba(255, 190, 120, 0.22); }
</style>
""", unsafe_allow_html=True)

def get_secret_value(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

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

def persist_session_tokens(session) -> None:
    access_token = getattr(session, "access_token", None) or (session.get("access_token") if isinstance(session, dict) else None)
    refresh_token = getattr(session, "refresh_token", None) or (session.get("refresh_token") if isinstance(session, dict) else None)
    if access_token:
        st.session_state["sb_access_token"] = access_token
    if refresh_token:
        st.session_state["sb_refresh_token"] = refresh_token
    st.session_state["sb_session"] = session

def restore_supabase_session() -> None:
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
        for key in ["sb_access_token", "sb_refresh_token", "sb_session"]:
            st.session_state.pop(key, None)

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
    cleaned, seen = [], set()
    for symbol in symbols:
        s = symbol.strip().upper()
        if s and s not in seen:
            cleaned.append(s); seen.add(s)
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
    client, user_id = get_supabase_client(), get_current_user_id()
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
    cleaned, seen = [], set()
    for symbol in symbols:
        s = symbol.strip().upper()
        if s and s not in seen:
            cleaned.append(s); seen.add(s)
    client, user_id = get_supabase_client(), get_current_user_id()
    if client is None or user_id is None:
        save_local_watchlist(cleaned)
        return True, "Watchlist saved locally."
    try:
        client.table("user_watchlists").upsert({"user_id": user_id, "symbols": cleaned}, on_conflict="user_id").execute()
        return True, "Watchlist saved to your account."
    except Exception as exc:
        save_local_watchlist(cleaned)
        return False, f"Supabase save failed, saved locally instead: {exc}"

def load_user_formulas() -> str:
    client, user_id = get_supabase_client(), get_current_user_id()
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
    client, user_id = get_supabase_client(), get_current_user_id()
    cleaned = text.strip()
    if client is None or user_id is None:
        save_local_formulas(cleaned)
        return True, "Formulas saved locally."
    try:
        client.table("user_formulas").upsert({"user_id": user_id, "formula_text": cleaned}, on_conflict="user_id").execute()
        return True, "Formulas saved to your account."
    except Exception as exc:
        save_local_formulas(cleaned)
        return False, f"Supabase save failed, formulas saved locally instead: {exc}"

def load_user_preferences(defaults: Dict[str, object]) -> Dict[str, object]:
    prefs = defaults.copy()
    client, user_id = get_supabase_client(), get_current_user_id()
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
    client, user_id = get_supabase_client(), get_current_user_id()
    if client is None or user_id is None:
        return False, "Preferences require login to sync."
    try:
        client.table("user_preferences").upsert({"user_id": user_id, "preferences": preferences}, on_conflict="user_id").execute()
        return True, "Preferences saved."
    except Exception as exc:
        return False, f"Could not save preferences: {exc}"

def load_alert_rows() -> pd.DataFrame:
    client, user_id = get_supabase_client(), get_current_user_id()
    if client is None or user_id is None:
        return pd.DataFrame(columns=["id","symbol","alert_type","target_value","note","is_active","created_at"])
    try:
        rows = client.table("user_alerts").select("id,symbol,alert_type,target_value,note,is_active,created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
        return pd.DataFrame(getattr(rows, "data", None) or [])
    except Exception:
        return pd.DataFrame(columns=["id","symbol","alert_type","target_value","note","is_active","created_at"])

def add_alert(symbol: str, alert_type: str, target_value: float, note: str) -> Tuple[bool, str]:
    client, user_id = get_supabase_client(), get_current_user_id()
    if client is None or user_id is None:
        return False, "Login required to save alerts."
    try:
        client.table("user_alerts").insert({"user_id": user_id, "symbol": symbol.upper(), "alert_type": alert_type, "target_value": target_value, "note": note.strip(), "is_active": True}).execute()
        return True, "Alert saved."
    except Exception as exc:
        return False, f"Could not add alert: {exc}"

def load_trade_journal() -> pd.DataFrame:
    client, user_id = get_supabase_client(), get_current_user_id()
    if client is None or user_id is None:
        return pd.DataFrame(columns=["id","symbol","side","entry_price","thesis","status","created_at"])
    try:
        rows = client.table("trade_journal").select("id,symbol,side,entry_price,stop_price,target_price,thesis,status,created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
        return pd.DataFrame(getattr(rows, "data", None) or [])
    except Exception:
        return pd.DataFrame(columns=["id","symbol","side","entry_price","thesis","status","created_at"])

def add_trade_journal_entry(symbol: str, side: str, entry_price: float, stop_price: float, target_price: float, thesis: str, status: str) -> Tuple[bool, str]:
    client, user_id = get_supabase_client(), get_current_user_id()
    if client is None or user_id is None:
        return False, "Login required to save journal entries."
    try:
        client.table("trade_journal").insert({"user_id": user_id, "symbol": symbol.upper(), "side": side, "entry_price": entry_price, "stop_price": stop_price, "target_price": target_price, "thesis": thesis.strip(), "status": status}).execute()
        return True, "Journal entry saved."
    except Exception as exc:
        return False, f"Could not save journal entry: {exc}"

def is_crypto_symbol(symbol: str) -> bool:
    upper = symbol.upper()
    return upper.endswith(CRYPTO_SUFFIXES) or upper.split("-")[0] in CRYPTO_KEYWORDS

@st.cache_data(ttl=300, show_spinner=False)
def get_analysis(period: str, interval: str) -> pd.DataFrame:
    return run_analysis(period=period, interval=interval)

def get_interval_for_chart(period: str, feed: str = "Yahoo Finance") -> str:
    if feed == "Polygon":
        return {"1d":"minute","5d":"minute","1mo":"hour","3mo":"day","6mo":"day","1y":"day","2y":"day","5y":"week"}.get(period, "day")
    if feed in {"Finnhub", "Twelve Data"}:
        return {"1d":"1","5d":"5","1mo":"15","3mo":"60","6mo":"D","1y":"D","2y":"D","5y":"W"}.get(period, "D")
    return {"1d":"1m","5d":"5m","1mo":"15m","3mo":"1h","6mo":"1d","1y":"1d","2y":"1d","5y":"1wk"}.get(period, "1d")

def get_period_date_range(period: str):
    end = datetime.now(timezone.utc)
    days = {"1d":1,"5d":5,"1mo":30,"3mo":90,"6mo":180,"1y":365,"2y":730,"5y":1825}.get(period, 180)
    start = end - pd.Timedelta(days=days)
    return start.to_pydatetime(), end

def normalize_feed_symbol(symbol: str, feed: str) -> str:
    upper = symbol.upper()
    if feed in {"Polygon","Finnhub"} and upper.endswith("-USD"):
        return upper.replace("-USD", "")
    if feed in {"Alpaca","Twelve Data"} and upper.endswith("-USD"):
        return upper.replace("-USD", "/USD")
    return upper

def dataframe_from_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rename_map = {}
    for col in df.columns:
        low = str(col).lower()
        if low in {"o","open"}: rename_map[col] = "Open"
        elif low in {"h","high"}: rename_map[col] = "High"
        elif low in {"l","low"}: rename_map[col] = "Low"
        elif low in {"c","close"}: rename_map[col] = "Close"
        elif low in {"v","volume"}: rename_map[col] = "Volume"
        elif low in {"t","timestamp","datetime","date","index"}: rename_map[col] = "Date"
    out = df.rename(columns=rename_map).copy()
    if "Date" in out.columns:
        out["Date"] = pd.to_datetime(out["Date"], utc=True, errors="coerce")
        out = out.set_index("Date")
    out.index = pd.to_datetime(out.index, utc=True, errors="coerce")
    keep = [c for c in ["Open","High","Low","Close","Volume"] if c in out.columns]
    return out[keep].dropna(subset=[c for c in ["Open","High","Low","Close"] if c in out.columns]).sort_index()

@st.cache_data(ttl=15, show_spinner=False)
def fetch_polygon_bars(symbol: str, period: str) -> pd.DataFrame:
    key = get_secret_value("POLYGON_API_KEY")
    if not key: return pd.DataFrame()
    ticker = normalize_feed_symbol(symbol, "Polygon")
    start, end = get_period_date_range(period)
    span = get_interval_for_chart(period, "Polygon")
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/{span}/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
    try:
        resp = httpx.get(url, params={"adjusted":"true","sort":"asc","limit":5000,"apiKey":key}, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        frame = pd.DataFrame([{"Date": pd.to_datetime(r.get("t"), unit="ms", utc=True), "Open": r.get("o"), "High": r.get("h"), "Low": r.get("l"), "Close": r.get("c"), "Volume": r.get("v")} for r in results])
        return dataframe_from_ohlcv(frame)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=15, show_spinner=False)
def fetch_finnhub_bars(symbol: str, period: str) -> pd.DataFrame:
    key = get_secret_value("FINNHUB_API_KEY")
    if not key: return pd.DataFrame()
    ticker = normalize_feed_symbol(symbol, "Finnhub")
    resolution = get_interval_for_chart(period, "Finnhub")
    start, end = get_period_date_range(period)
    try:
        resp = httpx.get("https://finnhub.io/api/v1/stock/candle", params={"symbol":ticker,"resolution":resolution,"from":int(start.timestamp()),"to":int(end.timestamp()),"token":key}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("s") != "ok": return pd.DataFrame()
        frame = pd.DataFrame({"Date": pd.to_datetime(data.get("t", []), unit="s", utc=True), "Open": data.get("o", []), "High": data.get("h", []), "Low": data.get("l", []), "Close": data.get("c", []), "Volume": data.get("v", [])})
        return dataframe_from_ohlcv(frame)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=15, show_spinner=False)
def fetch_alpaca_bars(symbol: str, period: str) -> pd.DataFrame:
    key = get_secret_value("ALPACA_API_KEY"); secret = get_secret_value("ALPACA_SECRET_KEY")
    if not key or not secret: return pd.DataFrame()
    ticker = normalize_feed_symbol(symbol, "Alpaca")
    timeframe = {"1d":"1Min","5d":"5Min","1mo":"15Min","3mo":"1Hour","6mo":"1Day","1y":"1Day","2y":"1Day","5y":"1Week"}.get(period, "1Day")
    start, end = get_period_date_range(period)
    try:
        resp = httpx.get("https://data.alpaca.markets/v2/stocks/bars", params={"symbols":ticker,"timeframe":timeframe,"start":start.isoformat(),"end":end.isoformat(),"limit":10000,"adjustment":"raw","feed":"iex"}, headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret}, timeout=20)
        resp.raise_for_status()
        bars = resp.json().get("bars", {}).get(ticker, [])
        frame = pd.DataFrame([{"Date":b.get("t"),"Open":b.get("o"),"High":b.get("h"),"Low":b.get("l"),"Close":b.get("c"),"Volume":b.get("v")} for b in bars])
        return dataframe_from_ohlcv(frame)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=15, show_spinner=False)
def fetch_twelve_data_bars(symbol: str, period: str) -> pd.DataFrame:
    key = get_secret_value("TWELVE_DATA_API_KEY")
    if not key: return pd.DataFrame()
    ticker = normalize_feed_symbol(symbol, "Twelve Data")
    interval = {"1d":"1min","5d":"5min","1mo":"15min","3mo":"1h","6mo":"1day","1y":"1day","2y":"1day","5y":"1week"}.get(period, "1day")
    outputsize = {"1d":390,"5d":500,"1mo":800,"3mo":500,"6mo":500,"1y":1000,"2y":1000,"5y":1000}.get(period, 500)
    try:
        resp = httpx.get("https://api.twelvedata.com/time_series", params={"symbol":ticker,"interval":interval,"outputsize":outputsize,"apikey":key}, timeout=20)
        resp.raise_for_status()
        values = resp.json().get("values", [])
        frame = pd.DataFrame([{"Date":v.get("datetime"),"Open":v.get("open"),"High":v.get("high"),"Low":v.get("low"),"Close":v.get("close"),"Volume":v.get("volume")} for v in values])
        return dataframe_from_ohlcv(frame)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=15, show_spinner=False)
def fetch_yfinance_bars(symbol: str, period: str) -> pd.DataFrame:
    interval = get_interval_for_chart(period, "Yahoo Finance")
    try:
        df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        return dataframe_from_ohlcv(df.reset_index())
    except Exception:
        return pd.DataFrame()

def add_technicals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Close" not in df.columns: return df
    out = df.copy()
    close, high, low = out["Close"], out["High"], out["Low"]
    delta = close.diff()
    gain = delta.clip(lower=0.0); loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean(); avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    out["RSI14"] = (100 - (100/(1+rs))).fillna(50.0)
    ema12 = close.ewm(span=12, adjust=False).mean(); ema26 = close.ewm(span=26, adjust=False).mean()
    out["EMA9"] = close.ewm(span=9, adjust=False).mean(); out["EMA21"] = close.ewm(span=21, adjust=False).mean(); out["EMA50"] = close.ewm(span=50, adjust=False).mean(); out["EMA200"] = close.ewm(span=200, adjust=False).mean()
    out["SMA20"] = close.rolling(20).mean(); out["SMA50"] = close.rolling(50).mean()
    out["MACD"] = ema12 - ema26; out["MACD_SIGNAL"] = out["MACD"].ewm(span=9, adjust=False).mean()
    prev_close = close.shift(1); tr = pd.concat([(high-low),(high-prev_close).abs(),(low-prev_close).abs()], axis=1).max(axis=1)
    out["ATR14"] = tr.rolling(14).mean(); out["ATR_PCT"] = (out["ATR14"]/close).replace([pd.NA, pd.NaT],0.0)
    if "Volume" in out.columns:
        out["VOL_AVG20"] = out["Volume"].rolling(20).mean(); out["VOLUME_RATIO"] = out["Volume"]/out["VOL_AVG20"]
    out["LOW20"] = low.rolling(20).min(); out["LOW60"] = low.rolling(60).min(); out["HIGH20"] = high.rolling(20).max(); out["HIGH60"] = high.rolling(60).max()
    return out

@st.cache_data(ttl=15, show_spinner=False)
def get_symbol_history(symbol: str, period: str, feed: str) -> pd.DataFrame:
    base = fetch_yfinance_bars(symbol, period)
    if feed == "Polygon":
        base = fetch_polygon_bars(symbol, period) or base
    elif feed == "Finnhub":
        fb = fetch_finnhub_bars(symbol, period)
        if not fb.empty: base = fb
    elif feed == "Alpaca":
        ab = fetch_alpaca_bars(symbol, period)
        if not ab.empty: base = ab
    elif feed == "Twelve Data":
        td = fetch_twelve_data_bars(symbol, period)
        if not td.empty: base = td
    return add_technicals(base)

def signal_badge_html(decision: str, entry_quality: str = "") -> str:
    if str(decision).upper() == "BUY" and str(entry_quality).upper() == "STRONG":
        return '<span class="signal-pill pill-strong-buy">● Strong Buy</span>'
    if str(decision).upper() == "BUY":
        return '<span class="signal-pill pill-buy">● Buy</span>'
    if str(decision).upper() == "HOLD / WAIT":
        return '<span class="signal-pill pill-hold">● Hold / Wait</span>'
    return '<span class="signal-pill pill-avoid">● Avoid</span>'

def label_strength(score: float) -> str:
    return "Strong" if score >= 75 else "Moderate" if score >= 55 else "Mixed" if score >= 40 else "Weak"

def detect_support_resistance(history: pd.DataFrame, current_price: float) -> dict:
    if history.empty or len(history) < 40:
        return {"support": round(current_price*0.95,2), "resistance": round(current_price*1.05,2)}
    support = float(history["Low"].tail(120).quantile(0.15)); resistance = float(history["High"].tail(120).quantile(0.85))
    return {"support": round(support,2), "resistance": round(resistance,2)}

def infer_dynamic_buy_price(symbol: str, history: pd.DataFrame, current_price: float, levels: dict | None = None) -> float:
    cfg = {**DEFAULT_PULLBACK_CONFIG, **ASSET_CONFIG.get(symbol, {})}
    manual = safe_float(cfg.get("preferred_buy_price"), current_price)
    if history.empty: return manual if manual > 0 else current_price
    last = history.iloc[-1]
    low20 = safe_float(last.get("LOW20"), current_price*0.94); low60 = safe_float(last.get("LOW60"), low20); ema21 = safe_float(last.get("EMA21"), current_price); support = safe_float((levels or {}).get("support"), low20)
    adaptive = (low20*0.35)+(low60*0.15)+(ema21*0.2)+(support*0.3)
    pref = adaptive if manual <= 0 else (manual*0.35)+(adaptive*0.65)
    return round(clamp(pref, current_price*0.82, current_price*0.995),2)

def analyze_pullback_setup(symbol: str, current_price: float, rsi: float, macd: float, macd_signal: float, preferred_buy: float, support: float, resistance: float, mtf_score: float, news_score: float, atr_pct: float | None = None, volume_ratio: float | None = None) -> dict:
    cfg = {**DEFAULT_PULLBACK_CONFIG, **ASSET_CONFIG.get(symbol, {})}
    dist = (current_price - preferred_buy)/preferred_buy if preferred_buy else 0.0
    support_gap = (current_price - support)/support if support else 0.0
    resistance_gap = (resistance - current_price)/current_price if resistance and current_price else 0.0

    score = 50.0
    score += 10 if macd > macd_signal else -10

    # Tighter short-term buy logic: only reward cooling pullbacks, not continued extension.
    if cfg["rsi_buy_min"] <= rsi <= min(cfg["rsi_buy_max"], 56):
        score += 14
    elif 56 < rsi <= 60:
        score += 2
    elif rsi >= 64:
        score -= 18
    elif rsi < 35:
        score -= 8

    if dist <= -0.01:
        score += 20
    elif dist <= 0.01:
        score += 8
    elif dist <= 0.03:
        score -= 6
    elif dist <= cfg["hard_overextended_pct"]:
        score -= 18
    else:
        score -= 30

    if support and current_price <= support * 1.025:
        score += 10
    elif support_gap > 0.05:
        score -= 10

    if resistance and resistance_gap < 0.06:
        score -= 10

    if atr_pct is not None and not pd.isna(atr_pct):
        score += 6 if atr_pct <= cfg["volatility_tolerance"] else -6
    if volume_ratio is not None and not pd.isna(volume_ratio):
        score += 6 if volume_ratio >= 1.05 else -4 if volume_ratio < 0.85 else 0

    score += (mtf_score - 50) * 0.18 + news_score * 6

    overextended = dist > 0.02
    hot_rsi = rsi >= 60
    near_resistance = resistance_gap < 0.08 if resistance else False

    if overextended and hot_rsi:
        score -= 14
    if overextended and near_resistance:
        score -= 10

    final = round(clamp(score, 0, 100), 1)

    buy_ready = (
        final >= 76
        and dist <= 0.015
        and rsi <= 58
        and macd > macd_signal
        and mtf_score >= 55
        and (support == 0 or current_price <= support * 1.035)
        and not near_resistance
    )

    if buy_ready:
        decision = "BUY"
    elif final >= 48:
        decision = "HOLD / WAIT"
    else:
        decision = "AVOID"

    buy_day_hint = "Wait for cooling / pullback" if overextended or hot_rsi or near_resistance else "Entry zone improving"
    return {
        "decision": decision,
        "signal": decision,
        "entry_score": final,
        "score": final,
        "entry_quality": label_strength(final),
        "confidence": "High" if final >= 78 else "Medium" if final >= 58 else "Low",
        "preferred_buy_price": preferred_buy,
        "distance_from_buy_pct": round(dist * 100, 2),
        "wait_price": round(preferred_buy if current_price > preferred_buy else current_price, 2),
        "buy_day_hint": buy_day_hint,
        "notes": f"RSI {rsi:.1f} | MACD {'constructive' if macd > macd_signal else 'weak'} | Buy dist {dist*100:.1f}% | Support {support:.2f} | Resistance {resistance:.2f}",
    }

def analyze_timeframe(history: pd.DataFrame) -> dict:
    if history.empty or len(history) < 30: return {"bias":"Mixed","score":50.0}
    last = history.iloc[-1]
    close = safe_float(last.get("Close"),0.0); ema21 = safe_float(last.get("EMA21"),close); ema50 = safe_float(last.get("EMA50"),close); ema200 = safe_float(last.get("EMA200"),close); macd = safe_float(last.get("MACD"),0.0); signal = safe_float(last.get("MACD_SIGNAL"),0.0)
    score = clamp(50 + (8 if close > ema21 else -8) + (10 if close > ema50 else -10) + (12 if close > ema200 else -12) + (10 if macd > signal else -10), 0, 100)
    return {"bias":"Bullish" if score >= 65 else "Bearish" if score <= 40 else "Mixed", "score":round(score,1)}

def multi_timeframe_confirmation(symbol: str) -> dict:
    h = analyze_timeframe(get_symbol_history(symbol, "3mo", "Yahoo Finance")); d = analyze_timeframe(get_symbol_history(symbol, "1y", "Yahoo Finance")); w = analyze_timeframe(get_symbol_history(symbol, "5y", "Yahoo Finance"))
    combined = round((h["score"]*0.25)+(d["score"]*0.45)+(w["score"]*0.30),1)
    label = "Bullish Alignment" if combined >= 65 and d["bias"] == "Bullish" else "Bearish Alignment" if combined <= 40 and d["bias"] == "Bearish" else "Mixed"
    return {"mtf_hourly":h["bias"],"mtf_daily":d["bias"],"mtf_weekly":w["bias"],"mtf_score":combined,"mtf_label":label}

@st.cache_data(ttl=900, show_spinner=False)
def get_news_sentiment(symbol: str) -> dict:
    try: news_items = yf.Ticker(symbol).news or []
    except Exception: news_items = []
    if not news_items: return {"news_sentiment_score":0.0,"news_sentiment_label":"Neutral","news_headline_count":0,"top_headlines":[]}
    scores, headlines = [], []
    for item in news_items[:10]:
        title = str(item.get("title","")).strip()
        if not title: continue
        text = re.sub(r"[^a-zA-Z0-9\s]"," ",title.lower()); words = [w for w in text.split() if w]
        scores.append((sum(1 for w in words if w in POSITIVE_WORDS)-sum(1 for w in words if w in NEGATIVE_WORDS))/max(1, len(words)**0.5)); headlines.append(title)
    avg = round(sum(scores)/max(1,len(scores)),3); label = "Positive" if avg >= 0.18 else "Negative" if avg <= -0.18 else "Neutral"
    return {"news_sentiment_score":avg,"news_sentiment_label":label,"news_headline_count":len(headlines),"top_headlines":headlines[:5]}

def enrich_results_with_pullback_system(df: pd.DataFrame, period: str, include_news: bool = True) -> pd.DataFrame:
    if df.empty or "symbol" not in df.columns: return df
    rows = []
    for _, row in df.iterrows():
        symbol = str(row.get("symbol","")).strip(); history = get_symbol_history(symbol, period, "Yahoo Finance")
        if history.empty: rows.append(row); continue
        last = history.iloc[-1]; current_price = safe_float(row.get("price"), safe_float(last.get("Close"),0.0))
        levels = detect_support_resistance(history, current_price); mtf = multi_timeframe_confirmation(symbol); news = get_news_sentiment(symbol) if include_news else {"news_sentiment_score":0.0,"news_sentiment_label":"Neutral","news_headline_count":0}
        preferred_buy = infer_dynamic_buy_price(symbol, history, current_price, levels)
        pullback = analyze_pullback_setup(symbol, current_price, safe_float(last.get("RSI14"),50.0), safe_float(last.get("MACD"),0.0), safe_float(last.get("MACD_SIGNAL"),0.0), preferred_buy, levels["support"], levels["resistance"], safe_float(mtf["mtf_score"],50.0), safe_float(news["news_sentiment_score"],0.0), safe_float(last.get("ATR_PCT"),0.03), safe_float(last.get("VOLUME_RATIO"),1.0))
        short_term = compute_short_term_buy_context(history if len(history) >= 6 else get_daily_context_history(symbol), pd.Series({"preferred_buy_price": preferred_buy, "support": levels["support"], "mtf_score": mtf["mtf_score"], "entry_score": pullback["entry_score"]}))
        row["price"] = round(current_price,2); row["decision"] = pullback["decision"]; row["signal"] = pullback["signal"]; row["entry_score"] = pullback["entry_score"]; row["score"] = pullback["score"]; row["confidence"] = pullback["confidence"]; row["entry_quality"] = pullback["entry_quality"]; row["preferred_buy_price"] = pullback["preferred_buy_price"]; row["distance_from_buy_pct"] = pullback["distance_from_buy_pct"]; row["wait_price"] = pullback["wait_price"]; row["notes"] = pullback["notes"]; row["buy_day_hint"] = pullback.get("buy_day_hint", ""); row["support"] = levels["support"]; row["resistance"] = levels["resistance"]; row["mtf_score"] = mtf["mtf_score"]; row["mtf_label"] = mtf["mtf_label"]; row["mtf_hourly"] = mtf["mtf_hourly"]; row["mtf_daily"] = mtf["mtf_daily"]; row["mtf_weekly"] = mtf["mtf_weekly"]; row["news_sentiment_score"] = news["news_sentiment_score"]; row["news_sentiment_label"] = news["news_sentiment_label"]; row["news_headline_count"] = news["news_headline_count"]; row["two_day_run_pct"] = short_term["two_day_run_pct"]; row["today_change_pct"] = short_term["today_change_pct"]; row["buy_day_score"] = short_term["buy_day_score"]; row["buy_day_label"] = short_term["buy_day_label"]; row["pullback_type"] = short_term["pullback_type"]
        row["strength_score"] = round((safe_float(row["entry_score"],50)*0.55)+(safe_float(row["mtf_score"],50)*0.20)+((50+safe_float(row["news_sentiment_score"],0)*60)*0.10)+(safe_float(row["buy_day_score"],50)*0.15),1)
        buy_rank = (safe_float(row["buy_day_score"],50)*0.45) + (safe_float(row["entry_score"],50)*0.30) + (safe_float(row["mtf_score"],50)*0.15) - max(0, safe_float(row["distance_from_buy_pct"],0))*1.5
        if safe_float(row["today_change_pct"],0) > 0.5: buy_rank -= 4
        if safe_float(row["two_day_run_pct"],0) < 0: buy_rank -= 3
        row["best_buy_today_rank"] = round(clamp(buy_rank, 0, 100), 1)
        rows.append(row)
    return pd.DataFrame(rows)

def classify_group_outlook(df: pd.DataFrame, label: str) -> Tuple[str, str]:
    if df.empty: return f"{label}: NEUTRAL", "No symbols available."
    avg = float(df["entry_score"].mean()) if "entry_score" in df.columns else 0.0; buys = int(df["decision"].eq("BUY").sum()) if "decision" in df.columns else 0; avoids = int(df["decision"].eq("AVOID").sum()) if "decision" in df.columns else 0
    if avg >= 62 and buys >= max(1, avoids): return f"{label}: CONSTRUCTIVE", "Trend quality is healthy and several names are near usable pullback zones."
    if avg <= 38 and avoids >= max(1, buys): return f"{label}: DEFENSIVE", "Risk is elevated and pullback quality is weak across the group."
    return f"{label}: MIXED", "Signals are split, so selectivity matters."

def build_share_text(result: pd.DataFrame, crypto_title: str, stock_title: str) -> str:
    lines = ["Market Math Analyzer update:", crypto_title, stock_title]
    if not result.empty:
        top = result.sort_values(["best_buy_today_rank","entry_score"], ascending=[False,False]).head(5); lines.append("Top setups:")
        for _, row in top.iterrows(): lines.append(f"- {row.get('symbol')}: {row.get('decision')} | price {format_value(row.get('price'))} | buy zone {format_value(row.get('preferred_buy_price'))} | score {format_value(row.get('entry_score'))}")
    return "\n".join(lines)

def build_advanced_chart(history: pd.DataFrame, symbol: str, preferred_buy: float, support: float, resistance: float, overlays: Dict[str, bool], show_rsi: bool, show_macd: bool) -> go.Figure:
    rows = 1 + int("Volume" in history.columns) + int(show_rsi) + int(show_macd); heights = [0.55] + ([0.15] if "Volume" in history.columns else []) + ([0.15] if show_rsi else []) + ([0.15] if show_macd else [])
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=heights)
    fig.add_trace(go.Candlestick(x=history.index, open=history["Open"], high=history["High"], low=history["Low"], close=history["Close"], name=symbol), row=1, col=1)
    for col, enabled in overlays.items():
        if enabled and col in history.columns: fig.add_trace(go.Scatter(x=history.index, y=history[col], mode="lines", name=col), row=1, col=1)
    for value, label in [(preferred_buy,"Preferred Buy"),(support,"Support"),(resistance,"Resistance")]:
        if value > 0: fig.add_hline(y=value, line_dash="dot", annotation_text=label, row=1, col=1)
    current_row = 2
    if "Volume" in history.columns:
        fig.add_trace(go.Bar(x=history.index, y=history["Volume"], name="Volume"), row=current_row, col=1); current_row += 1
    if show_rsi and "RSI14" in history.columns:
        fig.add_trace(go.Scatter(x=history.index, y=history["RSI14"], mode="lines", name="RSI14"), row=current_row, col=1); fig.add_hline(y=70, line_dash="dash", row=current_row, col=1); fig.add_hline(y=30, line_dash="dash", row=current_row, col=1); current_row += 1
    if show_macd and "MACD" in history.columns and "MACD_SIGNAL" in history.columns:
        fig.add_trace(go.Scatter(x=history.index, y=history["MACD"], mode="lines", name="MACD"), row=current_row, col=1); fig.add_trace(go.Scatter(x=history.index, y=history["MACD_SIGNAL"], mode="lines", name="MACD Signal"), row=current_row, col=1)
    fig.update_layout(height=920, title=f"{symbol} live workstation chart", xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=50, b=20))
    return fig

def build_comparison_chart(symbol_a: str, symbol_b: str, period: str, feed: str) -> go.Figure:
    a = get_symbol_history(symbol_a, period, feed); b = get_symbol_history(symbol_b, period, feed); fig = go.Figure()
    if not a.empty and "Close" in a.columns:
        base = safe_float(a["Close"].iloc[0],1.0) or 1.0; fig.add_trace(go.Scatter(x=a.index, y=(a["Close"]/base)*100, mode="lines", name=symbol_a))
    if not b.empty and "Close" in b.columns:
        base = safe_float(b["Close"].iloc[0],1.0) or 1.0; fig.add_trace(go.Scatter(x=b.index, y=(b["Close"]/base)*100, mode="lines", name=symbol_b))
    fig.update_layout(title="Relative performance (start = 100)", height=360, yaxis_title="Indexed return", margin=dict(l=20, r=20, t=40, b=20)); return fig

@st.cache_data(ttl=900, show_spinner=False)
def get_symbol_profile(symbol: str) -> dict:
    try: info = yf.Ticker(symbol).info
    except Exception: info = {}
    return {"short_name": info.get("shortName") or info.get("longName") or symbol, "market_cap": info.get("marketCap"), "fifty_two_week_high": info.get("fiftyTwoWeekHigh"), "fifty_two_week_low": info.get("fiftyTwoWeekLow"), "volume": info.get("volume")}

def overview_html(symbol: str, selected_row: pd.Series, profile: dict, feed: str) -> str:
    return f'<div class="overview-box"><strong>{profile.get("short_name", symbol)}</strong> ({symbol})<br><span class="small-note">Feed: {feed} | Price: ${safe_float(selected_row.get("price"),0):,.2f} | Decision: {selected_row.get("decision","-")} | Entry score: {safe_float(selected_row.get("entry_score"),0):.1f} | Strength score: {safe_float(selected_row.get("strength_score"),0):.1f}<br>Market cap: {format_value(profile.get("market_cap"))} | Volume: {format_value(profile.get("volume"))} | 52W High: {format_value(profile.get("fifty_two_week_high"))} | 52W Low: {format_value(profile.get("fifty_two_week_low"))}</span></div>'

def estimate_trade_plan(current_price: float, preferred_buy: float, support: float, resistance: float, atr_pct: float, account_size: float, risk_pct: float, max_exposure_pct: float) -> dict:
    entry = preferred_buy if preferred_buy > 0 else current_price; atr_buffer = max(current_price*atr_pct*0.75, current_price*0.01); stop = max(min(entry-atr_buffer, support*0.99), entry*0.85); risk_per_unit = max(entry-stop, entry*0.005); target = max(resistance, entry+risk_per_unit*2.0)
    capital_at_risk = account_size*(risk_pct/100); exposure_cap = account_size*(max_exposure_pct/100); units = max(0.0, min(capital_at_risk/risk_per_unit if risk_per_unit > 0 else 0.0, exposure_cap/entry if entry > 0 else 0.0)); rr = (target-entry)/risk_per_unit if risk_per_unit > 0 else 0.0
    return {"entry_price":round(entry,2),"stop_price":round(stop,2),"target_price":round(target,2),"rr_ratio":round(rr,2),"units":round(units,4),"position_value":round(units*entry,2),"capital_at_risk":round(capital_at_risk,2)}



@st.cache_data(ttl=120, show_spinner=False)
def get_daily_context_history(symbol: str) -> pd.DataFrame:
    return get_symbol_history(symbol, "1y", "Yahoo Finance")

def compute_short_term_buy_context(history: pd.DataFrame, selected_row: pd.Series) -> dict:
    if history.empty or "Close" not in history.columns or len(history) < 6:
        return {
            "two_day_run_pct": 0.0,
            "today_change_pct": 0.0,
            "five_day_pct": 0.0,
            "buy_day_score": 50.0,
            "buy_day_label": "Insufficient data",
            "pullback_type": "N/A",
            "summary": "Not enough daily candles yet to score a short-term setup.",
        }

    close = history["Close"].dropna()
    if len(close) < 6:
        return {
            "two_day_run_pct": 0.0,
            "today_change_pct": 0.0,
            "five_day_pct": 0.0,
            "buy_day_score": 50.0,
            "buy_day_label": "Insufficient data",
            "pullback_type": "N/A",
            "summary": "Not enough daily candles yet to score a short-term setup.",
        }

    current_price = safe_float(close.iloc[-1], 0.0)
    prev_close = safe_float(close.iloc[-2], current_price)
    close_2d_back = safe_float(close.iloc[-4], prev_close)
    close_5d_back = safe_float(close.iloc[-6], prev_close)

    two_day_run_pct = ((prev_close / close_2d_back) - 1) * 100 if close_2d_back else 0.0
    today_change_pct = ((current_price / prev_close) - 1) * 100 if prev_close else 0.0
    five_day_pct = ((current_price / close_5d_back) - 1) * 100 if close_5d_back else 0.0

    last = history.iloc[-1]
    ema21 = safe_float(last.get("EMA21"), current_price)
    rsi = safe_float(last.get("RSI14"), 50.0)
    preferred_buy = safe_float(selected_row.get("preferred_buy_price"), current_price)
    support = safe_float(selected_row.get("support"), current_price * 0.97)
    mtf_score = safe_float(selected_row.get("mtf_score"), 50.0)
    entry_score = safe_float(selected_row.get("entry_score"), 50.0)

    score = 50.0

    if two_day_run_pct >= 2.0:
        score += 12
    elif two_day_run_pct <= -2.0:
        score -= 8

    if -3.5 <= today_change_pct <= -0.4:
        score += 18
        pullback_type = "Healthy pullback"
    elif -5.5 <= today_change_pct < -3.5:
        score += 4
        pullback_type = "Deeper dip"
    elif today_change_pct < -5.5:
        score -= 16
        pullback_type = "Falling knife risk"
    elif today_change_pct > 1.5:
        score -= 8
        pullback_type = "Still extended"
    else:
        pullback_type = "Flat / neutral"

    if current_price >= ema21:
        score += 8
    else:
        score -= 10

    if 40 <= rsi <= 58:
        score += 10
    elif rsi > 68:
        score -= 10
    elif rsi < 35:
        score -= 6

    if preferred_buy and current_price <= preferred_buy * 1.02:
        score += 10
    if support and current_price <= support * 1.03:
        score += 8

    if mtf_score >= 60:
        score += 8
    elif mtf_score <= 40:
        score -= 8

    if entry_score >= 68:
        score += 10
    elif entry_score <= 42:
        score -= 10

    buy_day_score = round(clamp(score, 0, 100), 1)
    if buy_day_score >= 74:
        buy_day_label = "Decent Buy Day"
    elif buy_day_score >= 58:
        buy_day_label = "Watch Buy Day"
    else:
        buy_day_label = "No Edge Today"

    summary = (
        f"Previous two sessions moved {two_day_run_pct:.2f}%. Today's move is {today_change_pct:.2f}%. "
        f"Price is {'above' if current_price >= ema21 else 'below'} EMA21, with RSI at {rsi:.1f}. "
        f"Overall trend score is {mtf_score:.1f} and setup score is {entry_score:.1f}."
    )

    return {
        "two_day_run_pct": round(two_day_run_pct, 2),
        "today_change_pct": round(today_change_pct, 2),
        "five_day_pct": round(five_day_pct, 2),
        "buy_day_score": buy_day_score,
        "buy_day_label": buy_day_label,
        "pullback_type": pullback_type,
        "summary": summary,
    }

def compute_annual_run_estimates(history: pd.DataFrame, selected_row: pd.Series) -> dict:
    if history.empty or "Close" not in history.columns or len(history) < 60:
        return {
            "bull_return_pct": 20.0,
            "base_return_pct": 8.0,
            "bear_return_pct": -18.0,
            "bull_target": safe_float(selected_row.get("price"), 0.0) * 1.20,
            "base_target": safe_float(selected_row.get("price"), 0.0) * 1.08,
            "bear_target": safe_float(selected_row.get("price"), 0.0) * 0.82,
            "summary": "Using fallback scenario ranges because there is not enough history yet.",
        }

    close = history["Close"].dropna()
    current_price = safe_float(close.iloc[-1], 0.0)
    r_6m = ((current_price / safe_float(close.iloc[-min(len(close), 126)], current_price)) - 1) if len(close) >= 2 else 0.0
    r_1y = ((current_price / safe_float(close.iloc[0], current_price)) - 1) if len(close) >= 2 else 0.0
    daily_returns = close.pct_change().dropna()
    annual_vol = float(daily_returns.std() * (252 ** 0.5)) if not daily_returns.empty else 0.30

    mtf_bias = (safe_float(selected_row.get("mtf_score"), 50.0) - 50.0) / 100.0
    strength_bias = (safe_float(selected_row.get("strength_score"), 50.0) - 50.0) / 100.0
    news_bias = safe_float(selected_row.get("news_sentiment_score"), 0.0)

    base_return = clamp((r_6m * 0.50) + (r_1y * 0.20) + (mtf_bias * 0.70) + (strength_bias * 0.45) + (news_bias * 0.10), -0.18, 0.28)
    upside_band = max(0.16, annual_vol * 0.55)
    downside_band = max(0.18, annual_vol * 0.65)

    bull_return = clamp(base_return + upside_band, 0.08, 0.95)
    bear_return = clamp(base_return - downside_band, -0.75, -0.05)

    bull_target = current_price * (1 + bull_return)
    base_target = current_price * (1 + base_return)
    bear_target = current_price * (1 + bear_return)

    summary = (
        f"12-month scenarios are based on trailing 6-month momentum ({r_6m*100:.1f}%), "
        f"1-year trend ({r_1y*100:.1f}%), multi-timeframe score, strength score, and realized volatility."
    )

    return {
        "bull_return_pct": round(bull_return * 100, 1),
        "base_return_pct": round(base_return * 100, 1),
        "bear_return_pct": round(bear_return * 100, 1),
        "bull_target": round(bull_target, 2),
        "base_target": round(base_target, 2),
        "bear_target": round(bear_target, 2),
        "summary": summary,
    }

restore_supabase_session()

st.markdown('<div class="main-title">Market Math Analyzer V5 Live</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Multi-user market workstation with Supabase login, advanced live charting, side-by-side comparison, alerts, journal, and feed switching.</div>', unsafe_allow_html=True)

DEFAULT_PREFS = {"history_period":"1y","chart_period":"5d","show_sma20":True,"show_sma50":True,"show_ema9":True,"show_ema21":True,"show_ema50":False,"show_rsi":True,"show_macd":True,"include_news":True,"feed_provider":"Yahoo Finance","auto_refresh":True,"refresh_seconds":15}
prefs = load_user_preferences(DEFAULT_PREFS)

with st.sidebar:
    st.header("Account")
    if supabase_ready():
        if get_current_user_id():
            st.success(f"Signed in as {get_current_user_email() or 'user'}")
            if st.button("Sign out", use_container_width=True):
                auth_sign_out(); st.rerun()
        else:
            auth_mode = st.radio("Auth mode", ["Login", "Sign up"], horizontal=True)
            with st.form("auth_form"):
                auth_email = st.text_input("Email")
                auth_password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Continue", use_container_width=True)
            if submitted:
                ok, msg = auth_sign_in(auth_email.strip(), auth_password) if auth_mode == "Login" else auth_sign_up(auth_email.strip(), auth_password)
                st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()
    else:
        st.warning("Supabase is not configured yet. The app still works locally.")

    st.divider(); st.header("Controls")
    period = st.selectbox("History period", ["3mo","6mo","1y","2y"], index=["3mo","6mo","1y","2y"].index(str(prefs.get("history_period","1y"))))
    chart_period = st.selectbox("Chart timeframe", CHART_PERIOD_OPTIONS, index=CHART_PERIOD_OPTIONS.index(str(prefs.get("chart_period","5d"))))
    min_entry_score = st.slider("Minimum entry score", 0, 100, 0, 5)
    selected_decision = st.selectbox("Decision filter", ["ALL","BUY","HOLD / WAIT","AVOID"])
    include_news = st.toggle("Include Yahoo Finance headlines", value=bool(prefs.get("include_news", True)))
    feed_provider = st.selectbox("Live feed provider", DATA_FEED_OPTIONS, index=DATA_FEED_OPTIONS.index(str(prefs.get("feed_provider","Yahoo Finance"))))
    auto_refresh = st.toggle("Auto refresh live chart", value=bool(prefs.get("auto_refresh", True)))
    refresh_seconds = st.selectbox("Refresh every", [5,10,15,30,60], index=[5,10,15,30,60].index(int(prefs.get("refresh_seconds",15))))
    st.subheader("Chart overlays")
    show_sma20 = st.toggle("SMA 20", value=bool(prefs.get("show_sma20",True))); show_sma50 = st.toggle("SMA 50", value=bool(prefs.get("show_sma50",True))); show_ema9 = st.toggle("EMA 9", value=bool(prefs.get("show_ema9",True))); show_ema21 = st.toggle("EMA 21", value=bool(prefs.get("show_ema21",True))); show_ema50 = st.toggle("EMA 50", value=bool(prefs.get("show_ema50",False))); show_rsi = st.toggle("RSI panel", value=bool(prefs.get("show_rsi",True))); show_macd = st.toggle("MACD panel", value=bool(prefs.get("show_macd",True)))
    st.subheader("Portfolio / risk")
    account_size = st.number_input("Account size ($)", min_value=100.0, value=10000.0, step=500.0); risk_pct = st.number_input("Risk per trade (%)", min_value=0.25, max_value=10.0, value=1.0, step=0.25); max_exposure_pct = st.number_input("Max position exposure (%)", min_value=1.0, max_value=100.0, value=15.0, step=1.0)
    if st.button("Save display preferences", use_container_width=True):
        ok, msg = save_user_preferences({"history_period":period,"chart_period":chart_period,"show_sma20":show_sma20,"show_sma50":show_sma50,"show_ema9":show_ema9,"show_ema21":show_ema21,"show_ema50":show_ema50,"show_rsi":show_rsi,"show_macd":show_macd,"include_news":include_news,"feed_provider":feed_provider,"auto_refresh":auto_refresh,"refresh_seconds":refresh_seconds})
        st.success(msg) if ok else st.info(msg)
    scan_now = st.button("Scan market now", use_container_width=True)
    if st.button("Refresh chart view", use_container_width=True):
        st.rerun()
    st.caption("Optional live feed keys: POLYGON_API_KEY, FINNHUB_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY, TWELVE_DATA_API_KEY")

watchlist_symbols = load_user_watchlist(); formulas_text_default = load_user_formulas()

def build_scan_signature(period: str, include_news: bool, watchlist_symbols: list[str], formulas_text: str) -> str:
    payload = f"{period}|{include_news}|{'|'.join(watchlist_symbols)}|{formulas_text.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

scan_signature = build_scan_signature(period, include_news, watchlist_symbols, formulas_text_default)
needs_scan = (
    scan_now
    or st.session_state.get("scan_force_refresh", False)
    or st.session_state.get("scan_result") is None
    or st.session_state.get("scan_signature") != scan_signature
)

if needs_scan:
    with st.spinner("Scanning pullback setups with structure, timeframes, and headlines..."):
        fresh_result = get_analysis(period=period, interval="1d")
        fresh_result = enrich_results_with_pullback_system(fresh_result, period=period, include_news=include_news)
    st.session_state["scan_result"] = fresh_result.copy()
    st.session_state["scan_signature"] = scan_signature
    st.session_state["scan_force_refresh"] = False
    st.session_state["scan_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

result = st.session_state.get("scan_result", pd.DataFrame()).copy()
if result.empty:
    st.warning("No results returned. Check your watchlist, formulas, or internet connection."); st.stop()

result = result.copy(); result["asset_class"] = result["symbol"].apply(lambda s: "Crypto" if is_crypto_symbol(str(s)) else "Stock / ETF")
filtered = result.copy()
if selected_decision != "ALL": filtered = filtered[filtered["decision"] == selected_decision]
filtered = filtered[filtered["entry_score"] >= min_entry_score]

crypto_df = result[result["asset_class"] == "Crypto"].copy(); stock_df = result[result["asset_class"] == "Stock / ETF"].copy()
crypto_title, crypto_detail = classify_group_outlook(crypto_df, "Crypto outlook"); stock_title, stock_detail = classify_group_outlook(stock_df, "Stock outlook")
alerts_df = filtered.sort_values(["entry_score"], ascending=False).head(8); share_text = build_share_text(filtered, crypto_title, stock_title)

c1,c2,c3,c4 = st.columns(4)
with c1: st.metric("Tracked symbols", len(result))
with c2: st.metric("Buy-ready setups", int(result["decision"].eq("BUY").sum()))
with c3: st.metric("Average entry score", round(float(result["entry_score"].mean()),1))
with c4: st.metric("Last scan", st.session_state.get("scan_timestamp", "Not scanned"))

card1, card2 = st.columns(2)
with card1: st.markdown(f'<div class="accent-card"><strong>{crypto_title}</strong><br><span class="small-note">{crypto_detail}</span></div>', unsafe_allow_html=True)
with card2: st.markdown(f'<div class="accent-card-soft"><strong>{stock_title}</strong><br><span class="small-note">{stock_detail}</span></div>', unsafe_allow_html=True)

st.caption('Scan status: ' + ('fresh scan completed' if needs_scan else 'reusing cached market scan') + f' | Live chart feed: {feed_provider}')

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard","Workstation","Journal & Alerts","Settings"])
with tab1:
    st.subheader("Top setups")
    top = filtered.sort_values(["best_buy_today_rank","entry_score"], ascending=[False,False]).head(12)
    cols = [c for c in ["symbol","asset_class","price","decision","best_buy_today_rank","buy_day_score","buy_day_label","entry_score","strength_score","preferred_buy_price","distance_from_buy_pct","today_change_pct","two_day_run_pct","mtf_label","news_sentiment_label"] if c in top.columns]
    st.dataframe(top[cols], use_container_width=True, hide_index=True)
    st.subheader("Share-ready summary")
    st.text_area("Copy summary", value=share_text, height=220)
    st.subheader("Alert center")
    if alerts_df.empty:
        st.caption("No alert-ready setups right now.")
    else:
        for _, row in alerts_df.iterrows():
            st.markdown(f'<div class="accent-card-soft">{signal_badge_html(str(row.get("decision","")), str(row.get("entry_quality","")))}<br><strong>{row.get("symbol","-")}</strong> — price ${safe_float(row.get("price"),0):,.2f} | preferred buy ${safe_float(row.get("preferred_buy_price"),0):,.2f} | score {safe_float(row.get("entry_score"),0):.1f}<br><span class="small-note">{row.get("notes","")}</span></div>', unsafe_allow_html=True)


with tab2:
    st.subheader("Ticker workstation")
    if auto_refresh:
        st_autorefresh(interval=refresh_seconds*1000, key="live_autorefresh_workstation")
    symbols = filtered["symbol"].dropna().tolist()
    if not symbols:
        st.caption("No symbols available after filtering.")
    else:
        selected_symbol = st.selectbox("Choose a symbol", options=symbols)
        compare_options = [s for s in result["symbol"].dropna().tolist() if s != selected_symbol]
        compare_symbol = st.selectbox("Compare against", options=compare_options, index=0 if compare_options else None)
        selected_row = filtered[filtered["symbol"] == selected_symbol].iloc[0]

        live_history = get_symbol_history(selected_symbol, chart_period, feed_provider)
        context_history = get_daily_context_history(selected_symbol)
        profile = get_symbol_profile(selected_symbol)
        short_term = compute_short_term_buy_context(context_history, selected_row)
        annual_est = compute_annual_run_estimates(context_history, selected_row)

        st.markdown(overview_html(selected_symbol, selected_row, profile, feed_provider), unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("2-day run before today", f"{short_term['two_day_run_pct']:.2f}%")
        with m2:
            st.metric("Today / latest daily move", f"{short_term['today_change_pct']:.2f}%")
        with m3:
            st.metric("Buy-day score", f"{short_term['buy_day_score']:.1f}")
        with m4:
            st.metric("Short-term read", short_term["buy_day_label"])

        st.markdown(
            f'<div class="accent-card-soft"><strong>{short_term["pullback_type"]}</strong><br>'
            f'<span class="small-note">{short_term["summary"]}</span></div>',
            unsafe_allow_html=True,
        )

        left, right = st.columns([1.55, 1.0])
        with left:
            if not live_history.empty:
                chart = build_advanced_chart(
                    live_history.tail(350),
                    selected_symbol,
                    safe_float(selected_row.get("preferred_buy_price"), 0.0),
                    safe_float(selected_row.get("support"), 0.0),
                    safe_float(selected_row.get("resistance"), 0.0),
                    overlays={"SMA20": show_sma20, "SMA50": show_sma50, "EMA9": show_ema9, "EMA21": show_ema21, "EMA50": show_ema50},
                    show_rsi=show_rsi,
                    show_macd=show_macd,
                )
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.caption("Live chart unavailable for this symbol and feed.")

        with right:
            st.subheader("Comparison")
            if compare_symbol:
                st.plotly_chart(build_comparison_chart(selected_symbol, compare_symbol, chart_period, feed_provider), use_container_width=True)
                compare_table = filtered[filtered["symbol"].isin([selected_symbol, compare_symbol])][
                    [c for c in ["symbol","price","decision","entry_score","strength_score","mtf_score","news_sentiment_label","preferred_buy_price"] if c in filtered.columns]
                ].copy()
                st.dataframe(compare_table, use_container_width=True, hide_index=True)

            st.subheader("12-month scenario estimates")
            a1, a2, a3 = st.columns(3)
            with a1:
                st.metric("Bull target", f"${annual_est['bull_target']:,.2f}", f"{annual_est['bull_return_pct']:.1f}%")
            with a2:
                st.metric("Base target", f"${annual_est['base_target']:,.2f}", f"{annual_est['base_return_pct']:.1f}%")
            with a3:
                st.metric("Bear target", f"${annual_est['bear_target']:,.2f}", f"{annual_est['bear_return_pct']:.1f}%")
            st.caption(annual_est["summary"])

            if include_news:
                with st.expander("Headline sentiment", expanded=False):
                    news = get_news_sentiment(selected_symbol)
                    st.caption(f"{news['news_sentiment_label']} | score {news['news_sentiment_score']:.3f} | headlines {news['news_headline_count']}")
                    for headline in news.get("top_headlines", [])[:5]:
                        st.write(f"- {headline}")

            if not live_history.empty:
                plan = estimate_trade_plan(
                    safe_float(selected_row.get("price"), 0.0),
                    safe_float(selected_row.get("preferred_buy_price"), 0.0),
                    safe_float(selected_row.get("support"), 0.0),
                    safe_float(selected_row.get("resistance"), 0.0),
                    safe_float(live_history["ATR_PCT"].tail(1).mean(), 0.03),
                    account_size,
                    risk_pct,
                    max_exposure_pct,
                )
                st.subheader("Trade plan")
                tp1, tp2, tp3, tp4 = st.columns(4)
                with tp1:
                    st.metric("Entry", f"${plan['entry_price']:,.2f}")
                with tp2:
                    st.metric("Stop", f"${plan['stop_price']:,.2f}")
                with tp3:
                    st.metric("Target", f"${plan['target_price']:,.2f}")
                with tp4:
                    st.metric("R:R", f"{plan['rr_ratio']:.2f}")
                tp5, tp6, tp7 = st.columns(3)
                with tp5:
                    st.metric("Suggested units", f"{plan['units']:,.4f}")
                with tp6:
                    st.metric("Position value", f"${plan['position_value']:,.2f}")
                with tp7:
                    st.metric("Capital at risk", f"${plan['capital_at_risk']:,.2f}")

        st.subheader("Short-term swing read")
        s1, s2, s3 = st.columns(3)
        with s1:
            st.metric("5-day momentum", f"{short_term['five_day_pct']:.2f}%")
        with s2:
            st.metric("Overall outlook", str(selected_row.get("mtf_label", "-")))
        with s3:
            st.metric("Current setup", str(selected_row.get("decision", "-")))

        st.caption(
            "This short-term read is tuned for buying dips inside healthier trends. "
            "It looks for a recent 2-day push, a current pullback, the setup score, and the broader trend before calling today decent."
        )

        st.subheader("Backtest snapshot")
        backtest_key = f"backtest_{selected_symbol}"
        if st.button("Run backtest for selected symbol", use_container_width=True):
            with st.spinner(f"Running backtest for {selected_symbol}..."):
                st.session_state[backtest_key] = run_backtest(selected_symbol)
        backtest = st.session_state.get(backtest_key)
        if backtest:
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
                if "entry_date" in bt_df.columns:
                    bt_df["entry_date"] = bt_df["entry_date"].astype(str)
                st.dataframe(bt_df.tail(15), use_container_width=True, hide_index=True)
        else:
            st.caption("Backtest runs only when requested so the workstation stays fast.")


with tab3:
    st.subheader("Saved alerts")
    a1,a2,a3,a4 = st.columns([1.1,1.3,1,1.3])
    with a1: alert_symbol = st.text_input("Alert symbol", value="BTC-USD")
    with a2: alert_type = st.selectbox("Alert type", ["price_above","price_below","strength_above","entry_score_above"])
    with a3: alert_target = st.number_input("Target", value=0.0, step=0.5)
    with a4: alert_note = st.text_input("Alert note")
    if st.button("Save alert"):
        ok, msg = add_alert(alert_symbol, alert_type, alert_target, alert_note); st.success(msg) if ok else st.info(msg)
    saved_alerts = load_alert_rows()
    st.dataframe(saved_alerts, use_container_width=True, hide_index=True) if not saved_alerts.empty else st.caption("No saved alerts yet.")
    st.subheader("Trade journal")
    j1,j2,j3 = st.columns(3)
    with j1: journal_symbol = st.text_input("Journal symbol", value="AAPL"); journal_side = st.selectbox("Side", ["Long","Short"])
    with j2: journal_entry = st.number_input("Entry price", value=0.0, step=0.5); journal_stop = st.number_input("Stop price", value=0.0, step=0.5)
    with j3: journal_target = st.number_input("Target price", value=0.0, step=0.5); journal_status = st.selectbox("Status", ["Open","Closed","Idea"])
    journal_thesis = st.text_area("Thesis / notes", height=120)
    if st.button("Save journal entry"):
        ok, msg = add_trade_journal_entry(journal_symbol, journal_side, journal_entry, journal_stop, journal_target, journal_thesis, journal_status); st.success(msg) if ok else st.info(msg)
    journal_df = load_trade_journal()
    st.dataframe(journal_df, use_container_width=True, hide_index=True) if not journal_df.empty else st.caption("No journal entries yet.")

with tab4:
    st.subheader("Watchlist editor")
    if "watchlist_editor" not in st.session_state: st.session_state.watchlist_editor = "\n".join(watchlist_symbols)
    preset_symbols = DEFAULT_WATCHLIST + ["AVAX-USD","LINK-USD","MSTR","COIN","IBIT"]
    chosen_presets = st.multiselect("Add common tickers", options=preset_symbols)
    search_ticker = st.text_input("Ticker search", placeholder="BTC-USD, SOL-USD, AAPL, IBIT")
    editable_watchlist = st.text_area("Current watchlist", key="watchlist_editor", height=220)
    cw1,cw2 = st.columns(2)
    with cw1:
        if st.button("Add ticker to editor"):
            ticker = search_ticker.strip().upper(); current_lines = [x.strip().upper() for x in st.session_state.watchlist_editor.splitlines() if x.strip()]
            if ticker and ticker not in current_lines: current_lines.append(ticker); st.session_state.watchlist_editor = "\n".join(current_lines); st.rerun()
    with cw2:
        if st.button("Save watchlist"):
            lines = editable_watchlist.splitlines(); lines.extend(chosen_presets); ok, msg = save_user_watchlist(lines); st.session_state["scan_force_refresh"] = True; st.success(msg) if ok else st.info(msg)
    st.subheader("Formulas editor")
    formulas_text = st.text_area("Custom formulas", value=formulas_text_default, height=180)
    if st.button("Save formulas"):
        ok, msg = save_user_formulas(formulas_text); st.session_state["scan_force_refresh"] = True; st.success(msg) if ok else st.info(msg)
    st.subheader("Feed setup")
    keys_status = pd.DataFrame([
        {"Provider":"Yahoo Finance","Key detected":True,"Secret name":"Built in"},
        {"Provider":"Polygon","Key detected":bool(get_secret_value("POLYGON_API_KEY")),"Secret name":"POLYGON_API_KEY"},
        {"Provider":"Finnhub","Key detected":bool(get_secret_value("FINNHUB_API_KEY")),"Secret name":"FINNHUB_API_KEY"},
        {"Provider":"Alpaca","Key detected":bool(get_secret_value("ALPACA_API_KEY") and get_secret_value("ALPACA_SECRET_KEY")),"Secret name":"ALPACA_API_KEY + ALPACA_SECRET_KEY"},
        {"Provider":"Twelve Data","Key detected":bool(get_secret_value("TWELVE_DATA_API_KEY")),"Secret name":"TWELVE_DATA_API_KEY"},
    ])
    st.dataframe(keys_status, use_container_width=True, hide_index=True)
    st.caption(f"Project folder: {BASE_DIR}")

csv_data = filtered.to_csv(index=False).encode("utf-8")
st.download_button("Download results as CSV", data=csv_data, file_name="market_math_results_v5_live.csv", mime="text/csv", use_container_width=True)
