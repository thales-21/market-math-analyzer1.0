ufrom __future__ import annotations

import re
from pathlib import Path

SOURCE_FILE = Path("app_v15_1_visual_refine_fixed2.py")
OUTPUT_FILE = Path("app_v16_neurotrade.py")

src = SOURCE_FILE.read_text(encoding="utf-8")

css_insert = """
    .rank-card {
        border-radius: 20px;
        padding: 1rem;
        min-height: 180px;
        border: 1px solid rgba(255,255,255,0.08);
        background: linear-gradient(180deg, rgba(10,16,28,0.96) 0%, rgba(6,10,20,0.98) 100%);
        box-shadow: 0 14px 34px rgba(0,0,0,0.34);
    }
    .crypto-card {
        border: 1px solid rgba(255,215,90,0.34);
        box-shadow:
            0 14px 34px rgba(0,0,0,0.34),
            0 0 18px rgba(255,215,90,0.12),
            inset 0 0 16px rgba(255,215,90,0.04);
    }
    .stock-card {
        border: 1px solid rgba(120,217,255,0.34);
        box-shadow:
            0 14px 34px rgba(0,0,0,0.34),
            0 0 18px rgba(120,217,255,0.12),
            inset 0 0 16px rgba(120,217,255,0.04);
    }
    .rank-symbol {
        font-size: 1.05rem;
        font-weight: 900;
        color: #ffffff;
        margin-bottom: 0.45rem;
        letter-spacing: 0.02em;
    }
    .rank-line {
        font-size: 0.9rem;
        margin-top: 0.28rem;
        color: #d8edf7;
    }
    div[data-testid="stDataFrame"] {
        background: linear-gradient(180deg, rgba(7,11,20,0.96) 0%, rgba(10,13,23,0.98) 100%) !important;
        border: 1px solid rgba(120,217,255,0.18);
        border-radius: 18px;
        padding: 0.25rem;
        box-shadow: 0 14px 30px rgba(0,0,0,0.30);
    }
"""

if ".rank-card {" not in src:
    src = src.replace('    .stDataFrame, .stDataFrame * {{ color: #fff7ef !important; }}', '    .stDataFrame, .stDataFrame * {{ color: #fff7ef !important; }}\n' + css_insert)

intraday_func = """
@st.cache_data(ttl=600, show_spinner=False)
def get_intraday_anchor(symbol: str) -> dict:
    try:
        intraday = yf.download(symbol, period="10d", interval="1h", auto_adjust=False, progress=False)
    except Exception:
        intraday = pd.DataFrame()

    if intraday.empty or len(intraday) < 20:
        return {
            "fast_anchor": 0.0,
            "fast_ema9": 0.0,
            "fast_ema21": 0.0,
            "week_vwap": 0.0,
            "valid": False,
        }

    df = intraday.copy()
    df.columns = [str(c).title() for c in df.columns]

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series([0.0] * len(df), index=df.index)

    df["EMA9_FAST"] = close.ewm(span=9, adjust=False).mean()
    df["EMA21_FAST"] = close.ewm(span=21, adjust=False).mean()
    typical = (high + low + close) / 3.0

    if volume.fillna(0).sum() > 0:
        df["PV"] = typical * volume
        week_cut = df.index.max() - pd.Timedelta(days=7)
        week_df = df[df.index >= week_cut].copy()
        if week_df["Volume"].fillna(0).sum() > 0:
            week_vwap = float(week_df["PV"].sum() / week_df["Volume"].sum())
        else:
            week_vwap = float(typical.tail(30).mean())
    else:
        week_vwap = float(typical.tail(30).mean())

    fast_ema9 = float(df["EMA9_FAST"].iloc[-1])
    fast_ema21 = float(df["EMA21_FAST"].iloc[-1])
    fast_anchor = (fast_ema9 * 0.45) + (fast_ema21 * 0.30) + (week_vwap * 0.25)

    return {
        "fast_anchor": round(float(fast_anchor), 2),
        "fast_ema9": round(fast_ema9, 2),
        "fast_ema21": round(fast_ema21, 2),
        "week_vwap": round(float(week_vwap), 2),
        "valid": True,
    }

"""

if "def get_intraday_anchor(" not in src:
    src = src.replace("def detect_support_resistance(history: pd.DataFrame, current_price: float) -> tuple[float, float]:", intraday_func + "\ndef detect_support_resistance(history: pd.DataFrame, current_price: float) -> tuple[float, float]:")

preferred_replacement = """
def infer_preferred_buy(symbol: str, history: pd.DataFrame, current_price: float, support: float) -> float:
    cfg = ASSET_CONFIG.get(symbol, {})
    manual_anchor = safe_float(cfg.get("preferred_buy_price"), 0.0)
    tol_pct = safe_float(cfg.get("anchor_tolerance_pct"), 0.035)

    if history.empty:
        if manual_anchor > 0:
            return round(manual_anchor, 2)
        return round(current_price * 0.975, 2)

    ema21 = safe_float(history["EMA21"].iloc[-1], current_price)
    ema50 = safe_float(history["EMA50"].iloc[-1], ema21) if "EMA50" in history.columns else ema21
    low20 = safe_float(history["LOW20"].iloc[-1], support)
    low60 = safe_float(history["LOW60"].iloc[-1], low20) if "LOW60" in history.columns else low20
    atr_pct = safe_float(history["ATR_PCT"].iloc[-1], 0.03)

    daily_adaptive = (ema21 * 0.40) + (ema50 * 0.10) + (low20 * 0.22) + (support * 0.18) + (low60 * 0.10)

    fast = get_intraday_anchor(symbol)
    fast_anchor = safe_float(fast.get("fast_anchor"), 0.0)

    if fast.get("valid") and fast_anchor > 0:
        adaptive = (daily_adaptive * 0.62) + (fast_anchor * 0.38)
    else:
        adaptive = daily_adaptive

    if manual_anchor > 0:
        preferred = (manual_anchor * 0.58) + (adaptive * 0.42)
        drift = manual_anchor * tol_pct
        preferred = clamp(preferred, manual_anchor - drift, manual_anchor + drift)
    else:
        preferred = adaptive
        preferred = clamp(preferred, current_price * 0.92, current_price * 1.003)

    preferred *= 1 - min(max(atr_pct * 0.06, 0.0), 0.007)

    floor = max(current_price * 0.94, support * 0.995)
    ceiling = min(current_price * 1.002, max(ema21, fast_anchor if fast_anchor > 0 else ema21) * 1.01)
    preferred = clamp(preferred, floor, ceiling)

    if manual_anchor > 0:
        preferred = clamp(preferred, manual_anchor * (1 - tol_pct), manual_anchor * (1 + tol_pct))

    return round(preferred, 2)
"""

src = re.sub(
    r'def infer_preferred_buy\(symbol: str, history: pd\.DataFrame, current_price: float, support: float\) -> float:\n(?:    .*\n)+?    return round\(preferred, 2\)\n',
    preferred_replacement + "\n",
    src,
    flags=re.MULTILINE
)

news_replacement = """
@st.cache_data(ttl=900, show_spinner=False)
def get_watchlist_headlines(symbols: tuple[str, ...]) -> List[dict]:
    items: List[dict] = []
    diagnostics: List[tuple[str, int]] = []

    for symbol in symbols:
        fetched = 0
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news or []
            fetched = len(news)
            for x in news[:6]:
                title = str(x.get("title", "")).strip()
                if not title:
                    continue
                publisher = str(x.get("publisher", "Yahoo Finance")).strip() or "Yahoo Finance"
                link = str(x.get("link", "")).strip()
                provider_time = x.get("providerPublishTime") or x.get("provider_publish_time") or 0
                items.append({
                    "symbol": symbol,
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "published": provider_time,
                })
        except Exception:
            fetched = 0

        diagnostics.append((symbol, fetched))

    st.session_state["news_diagnostics"] = diagnostics

    items.sort(key=lambda x: x.get("published", 0), reverse=True)
    seen = set()
    deduped = []
    for item in items:
        key = (item["symbol"], item["title"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:40]
"""

src = re.sub(
    r'@st\.cache_data\(ttl=900, show_spinner=False\)\ndef get_watchlist_headlines\(symbols: tuple\[str, \.\]\) -> List\[dict\]:\n(?:    .*\n)+?    return deduped\[:30\]\n',
    news_replacement + "\n",
    src,
    flags=re.MULTILINE
)

styled_replacement = """
def styled_scan_table(df: pd.DataFrame):
    working = df.copy()

    def asset_style(v):
        if str(v) == "Crypto":
            return (
                "background-color: rgba(255,215,90,0.08); "
                "color: #ffd75a; font-weight: 900; "
                "text-shadow: 0 0 8px rgba(255,215,90,0.38);"
            )
        return (
            "background-color: rgba(120,217,255,0.08); "
            "color: #78d9ff; font-weight: 900; "
            "text-shadow: 0 0 8px rgba(120,217,255,0.34);"
        )

    def entry_style(v):
        m = {
            "Strong Buy": "background-color: rgba(60,255,170,0.08); color:#8fffd0; font-weight:900; text-shadow: 0 0 8px rgba(143,255,208,0.28);",
            "Weak Buy": "background-color: rgba(125,235,255,0.08); color:#78d9ff; font-weight:900; text-shadow: 0 0 8px rgba(120,217,255,0.28);",
            "Hold / Wait": "background-color: rgba(255,220,120,0.08); color:#ffd75a; font-weight:800; text-shadow: 0 0 8px rgba(255,215,90,0.22);",
            "Sell / Avoid": "background-color: rgba(255,120,150,0.08); color:#ff8ea8; font-weight:800;",
        }
        return m.get(str(v), "color:#d8edf7;")

    def transition_style(v):
        m = {
            "Improving": "background-color: rgba(60,255,170,0.08); color:#8fffd0; font-weight:900;",
            "Weakening": "background-color: rgba(255,120,150,0.08); color:#ff8ea8; font-weight:800;",
            "Unchanged": "background-color: rgba(120,217,255,0.08); color:#78d9ff; font-weight:700;",
            "New": "background-color: rgba(255,220,120,0.08); color:#ffd75a; font-weight:700;",
        }
        return m.get(str(v), "color:#d8edf7;")

    def numeric_glow(row):
        asset = str(row.get("asset_class", ""))
        glow = "#ffd75a" if asset == "Crypto" else "#78d9ff"
        out = []
        for v in row:
            if isinstance(v, str) and any(ch.isdigit() for ch in v):
                out.append(f"color:{glow}; text-shadow: 0 0 8px {glow}; font-weight:800;")
            else:
                out.append("")
        return out

    styler = working.style
    if "asset_class" in working.columns:
        styler = styler.map(asset_style, subset=["asset_class"])
    if "entry_quality" in working.columns:
        styler = styler.map(entry_style, subset=["entry_quality"])
    if "signal_transition" in working.columns:
        styler = styler.map(transition_style, subset=["signal_transition"])

    styler = styler.apply(numeric_glow, axis=1)
    styler = styler.set_table_styles([
        {"selector": "th", "props": [
            ("background", "rgba(8,12,22,0.98)"),
            ("color", "#dff7ff"),
            ("border-bottom", "1px solid rgba(120,217,255,0.16)"),
            ("font-weight", "800"),
        ]},
        {"selector": "td", "props": [
            ("background", "rgba(10,14,24,0.94)"),
            ("border-bottom", "1px solid rgba(255,255,255,0.04)"),
        ]},
        {"selector": "table", "props": [
            ("background", "rgba(7,11,20,0.98)"),
            ("color", "#eaf7ff"),
        ]},
    ])
    return styler
"""

src = re.sub(
    r'def styled_scan_table\(df: pd\.DataFrame\):\n(?:    .*\n)+?    return styler\n',
    styled_replacement + "\n",
    src,
    flags=re.MULTILINE
)

src = src.replace("NeuroTrade v15", "NeuroTrade v16")
src = src.replace(
    "NeuroTrade thinks like market neurons: sharper entries, cleaner organization, and a faster workstation.",
    "NeuroTrade thinks like market neurons: current-week entry logic, darker neon scan intelligence, and a faster futuristic workstation."
)

top_rank_replacement = """
    st.markdown('<div class="section-header">Top ranked today</div>', unsafe_allow_html=True)

    crypto_top = scan_df[scan_df["asset_class"] == "Crypto"].head(3)
    stock_top = scan_df[scan_df["asset_class"] != "Crypto"].head(3)

    top_cards = pd.concat([crypto_top, stock_top], axis=0).head(6)
    if top_cards.empty:
        st.info("No ranked symbols available yet.")
    else:
        cols = st.columns(min(6, len(top_cards)))
        for col, (_, row) in zip(cols, top_cards.iterrows()):
            badge_class = (
                "pill-good" if row["entry_quality"] in ["Strong Buy", "Weak Buy"]
                else "pill-wait" if row["entry_quality"] == "Hold / Wait"
                else "pill-risk"
            )
            asset_pill = "pill-crypto" if row["asset_class"] == "Crypto" else "pill-stock"
            card_class = "rank-card crypto-card" if row["asset_class"] == "Crypto" else "rank-card stock-card"

            col.markdown(
                f"""
                <div class="{card_class}">
                    <div class="rank-symbol">{row["symbol"]}</div>
                    <div class="rank-pills">
                        <span class="pill {asset_pill}">{row["asset_class"]}</span>
                        <span class="pill {badge_class}">{row["entry_quality"]}</span>
                        <span class="pill pill-good">{row["trend_strength"]}</span>
                    </div>
                    <div class="rank-line">Setup: {row["setup_name"]}</div>
                    <div class="rank-line">Signal: {row["signal_transition"]}</div>
                    <div class="rank-line">Buy score: {row['buy_score']:.1f}</div>
                    <div class="rank-line">Today: {row["today_change_pct"]:+.2f}%</div>
                    <div class="rank-line">2-day run: {row["two_day_run_pct"]:+.2f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
"""

src = re.sub(
    r'    top = scan_df\.head\(5\)\n    st\.markdown\(\'<div class="section-header">Top ranked today</div>\', unsafe_allow_html=True\)\n(?:    .*\n)+?            unsafe_allow_html=True,\n        \)\n',
    top_rank_replacement,
    src,
    flags=re.MULTILINE
)

chart_replacement = """
def build_chart(chart_history: pd.DataFrame, symbol: str, preferred_buy: float, support: float, resistance: float, overlays: dict[str, bool]) -> go.Figure:
    df = chart_history.copy()
    fig = go.Figure()

    asset_is_crypto = is_crypto(symbol)
    up_color = "#ffd75a" if asset_is_crypto else "#78d9ff"
    down_color = "#ff6d8f"

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            increasing_line_color=up_color,
            increasing_fillcolor="rgba(255,215,90,0.78)" if asset_is_crypto else "rgba(120,217,255,0.78)",
            decreasing_line_color=down_color,
            decreasing_fillcolor="rgba(255,109,143,0.65)",
            name=symbol,
        )
    )

    overlay_specs = [
        ("EMA9", "#9ae6b4"),
        ("EMA21", "#ffd75a"),
        ("SMA20", "#78d9ff"),
        ("SMA50", "#b794f4"),
    ]
    for col, color in overlay_specs:
        if overlays.get(col, False) and col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[col],
                    mode="lines",
                    name=col,
                    line=dict(width=2, color=color),
                    opacity=0.95,
                )
            )

    if "Close" in df.columns and len(df) >= 20:
        mid = df["Close"].rolling(20).mean()
        heat = df["Close"].rolling(20).std()
        upper = mid + heat
        lower = mid - heat

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=upper,
                mode="lines",
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
                name="Thermal Upper",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=lower,
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(120,217,255,0.07)" if not asset_is_crypto else "rgba(255,215,90,0.07)",
                hoverinfo="skip",
                showlegend=False,
                name="Thermal Layer",
            )
        )

    level_specs = [
        ("Preferred Buy", preferred_buy, "#ffd75a"),
        ("Support", support, "#7dd3fc"),
        ("Resistance", resistance, "#f472b6"),
    ]
    for label, value, color in level_specs:
        if value and value > 0:
            fig.add_hline(
                y=value,
                line_dash="dot",
                line_width=1.25,
                line_color=color,
                annotation_text=label,
                annotation_position="top left",
            )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#07111c",
        font=dict(color="#e8f7ff"),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(120,217,255,0.06)",
            zeroline=False,
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(120,217,255,0.06)",
            zeroline=False,
        ),
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(
            bgcolor="rgba(7,17,28,0.65)",
            bordercolor="rgba(120,217,255,0.12)",
            borderwidth=1,
        ),
        dragmode="pan",
    )

    return fig
"""

src = re.sub(
    r'def build_chart\(chart_history: pd\.DataFrame, symbol: str, preferred_buy: float, support: float, resistance: float, overlays: dict\[str, bool\]\) -> go\.Figure:\n(?:    .*\n)+?    return fig\n',
    chart_replacement + "\n",
    src,
    flags=re.MULTILINE
)

needle = 'with news_tab:\n'
if needle in src and 'news_diagnostics' not in src.split(needle, 1)[1][:1000]:
    src = src.replace(
        needle,
        needle + '    diag = st.session_state.get("news_diagnostics", [])\n'
                 '    if diag:\n'
                 '        diag_text = " | ".join([f"{sym}: {count}" for sym, count in diag[:10]])\n'
                 '        st.markdown(\n'
                 '            f\'<div class="soft-box"><strong>News scan diagnostics</strong><br><span class="small-note">{diag_text}</span></div>\',\n'
                 '            unsafe_allow_html=True,\n'
                 '        )\n'
    )

OUTPUT_FILE.write_text(src, encoding="utf-8")
print(f"Created {OUTPUT_FILE}")
