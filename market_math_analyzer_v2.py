from __future__ import annotations

import ast
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except Exception as exc:
    raise ImportError(
        "yfinance is required. Install with: python3 -m pip install yfinance pandas numpy streamlit"
    ) from exc


# ============================================================
# MARKET MATH ANALYZER V2
# ------------------------------------------------------------
# App-ready cleanup version.
# - Uses project-relative files instead of current working directory
# - Keeps analysis logic separated from display logic
# - Supports custom formulas safely
# - Adds decision engine + top opportunities summary
# - Can run as a terminal app today and be imported by a GUI/web app later
# ============================================================


BASE_DIR = Path(__file__).resolve().parent
WATCHLIST_FILE = BASE_DIR / "watchlist.txt"
FORMULAS_FILE = BASE_DIR / "formulas.txt"


@dataclass
class Snapshot:
    symbol: str
    price: float
    change_1d_pct: float
    change_5d_pct: float
    change_20d_pct: float
    sma_10: float
    sma_20: float
    sma_50: float
    ema_12: float
    ema_26: float
    macd: float
    macd_signal: float
    rsi_14: float
    volatility_20d: float
    high_20: float
    low_20: float
    volume: float
    avg_volume_20: float


class SafeMathEvaluator:
    """Safely evaluate simple math expressions over market variables."""

    ALLOWED_FUNCS = {
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "sqrt": math.sqrt,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "floor": math.floor,
        "ceil": math.ceil,
        "pow": pow,
    }

    ALLOWED_NODES = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.USub,
        ast.UAdd,
        ast.Call,
        ast.Tuple,
        ast.List,
    )

    def evaluate(self, expression: str, variables: Dict[str, float]) -> float:
        tree = ast.parse(expression, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, self.ALLOWED_NODES):
                raise ValueError(f"Unsupported operation: {type(node).__name__}")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in self.ALLOWED_FUNCS:
                    raise ValueError("Function not allowed")
            if isinstance(node, ast.Name):
                if node.id not in variables and node.id not in self.ALLOWED_FUNCS:
                    raise ValueError(f"Unknown variable: {node.id}")

        compiled = compile(tree, filename="<expr>", mode="eval")
        scope = dict(self.ALLOWED_FUNCS)
        scope.update(variables)
        result = eval(compiled, {"__builtins__": {}}, scope)
        return float(result)


class MarketDataEngine:
    def __init__(self, period: str = "6mo", interval: str = "1d") -> None:
        self.period = period
        self.interval = interval

    def fetch_history(self, symbol: str) -> pd.DataFrame:
        df = yf.download(
            symbol,
            period=self.period,
            interval=self.interval,
            auto_adjust=True,
            progress=False,
        )
        if df is None or df.empty:
            raise ValueError(f"No data returned for {symbol}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns for {symbol}: {', '.join(missing)}")

        return df.dropna().copy()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gains = delta.clip(lower=0)
        losses = -delta.clip(upper=0)
        avg_gain = gains.rolling(period).mean()
        avg_loss = losses.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def ema(series: pd.Series, span: int) -> pd.Series:
        return series.ewm(span=span, adjust=False).mean()

    def build_snapshot(self, symbol: str, df: pd.DataFrame) -> Snapshot:
        if len(df) < 60:
            raise ValueError(f"Not enough historical data for {symbol}. Need at least 60 rows.")

        close = df["Close"].astype(float)
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        volume = df["Volume"].astype(float)
        returns = close.pct_change()

        ema_12_series = self.ema(close, 12)
        ema_26_series = self.ema(close, 26)
        macd_series = ema_12_series - ema_26_series
        macd_signal_series = self.ema(macd_series, 9)
        rsi_series = self.rsi(close, 14)

        return Snapshot(
            symbol=symbol,
            price=float(close.iloc[-1]),
            change_1d_pct=float((close.iloc[-1] / close.iloc[-2] - 1) * 100),
            change_5d_pct=float((close.iloc[-1] / close.iloc[-6] - 1) * 100),
            change_20d_pct=float((close.iloc[-1] / close.iloc[-21] - 1) * 100),
            sma_10=float(close.tail(10).mean()),
            sma_20=float(close.tail(20).mean()),
            sma_50=float(close.tail(50).mean()),
            ema_12=float(ema_12_series.iloc[-1]),
            ema_26=float(ema_26_series.iloc[-1]),
            macd=float(macd_series.iloc[-1]),
            macd_signal=float(macd_signal_series.iloc[-1]),
            rsi_14=float(rsi_series.iloc[-1]),
            volatility_20d=float(returns.tail(20).std() * np.sqrt(252) * 100),
            high_20=float(high.tail(20).max()),
            low_20=float(low.tail(20).min()),
            volume=float(volume.iloc[-1]),
            avg_volume_20=float(volume.tail(20).mean()),
        )


class Analyzer:
    def __init__(self, period: str = "6mo", interval: str = "1d") -> None:
        self.engine = MarketDataEngine(period=period, interval=interval)
        self.math_eval = SafeMathEvaluator()

    def score_symbol(self, snap: Snapshot) -> Tuple[float, str]:
        score = 0.0
        notes: List[str] = []

        if snap.price > snap.sma_20:
            score += 1.0
            notes.append("price > sma_20")
        else:
            score -= 1.0
            notes.append("price < sma_20")

        if snap.sma_20 > snap.sma_50:
            score += 1.0
            notes.append("sma_20 > sma_50")
        else:
            score -= 1.0
            notes.append("sma_20 < sma_50")

        if snap.macd > snap.macd_signal:
            score += 0.75
            notes.append("macd bullish")
        else:
            score -= 0.75
            notes.append("macd bearish")

        if 45 <= snap.rsi_14 <= 65:
            score += 0.5
            notes.append("rsi balanced")
        elif snap.rsi_14 < 30:
            score += 0.25
            notes.append("rsi oversold")
        elif snap.rsi_14 > 70:
            score -= 0.5
            notes.append("rsi overbought")

        if snap.change_20d_pct > 0:
            score += 0.75
            notes.append("20d trend positive")
        else:
            score -= 0.75
            notes.append("20d trend negative")

        if snap.volume > snap.avg_volume_20:
            score += 0.25
            notes.append("volume above average")

        return score, ", ".join(notes)

    def snapshot_to_dict(self, snap: Snapshot) -> Dict[str, float]:
        return asdict(snap)

    def analyze(self, symbols: List[str], custom_formulas: Optional[Dict[str, str]] = None) -> pd.DataFrame:
        custom_formulas = custom_formulas or {}
        rows: List[Dict[str, Any]] = []

        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            if not symbol:
                continue

            try:
                history = self.engine.fetch_history(symbol)
                snap = self.engine.build_snapshot(symbol, history)
                score, note = self.score_symbol(snap)

                row: Dict[str, Any] = {
                    "symbol": snap.symbol,
                    "price": round(snap.price, 4),
                    "1d_%": round(snap.change_1d_pct, 4),
                    "5d_%": round(snap.change_5d_pct, 4),
                    "20d_%": round(snap.change_20d_pct, 4),
                    "sma_10": round(snap.sma_10, 4),
                    "sma_20": round(snap.sma_20, 4),
                    "sma_50": round(snap.sma_50, 4),
                    "ema_12": round(snap.ema_12, 4),
                    "ema_26": round(snap.ema_26, 4),
                    "macd": round(snap.macd, 4),
                    "macd_signal": round(snap.macd_signal, 4),
                    "rsi_14": round(snap.rsi_14, 4),
                    "vol_20d_%": round(snap.volatility_20d, 4),
                    "high_20": round(snap.high_20, 4),
                    "low_20": round(snap.low_20, 4),
                    "volume": round(snap.volume, 2),
                    "avg_volume_20": round(snap.avg_volume_20, 2),
                    "score": round(score, 4),
                    "notes": note,
                }

                variables = self.snapshot_to_dict(snap)
                for formula_name, expression in custom_formulas.items():
                    try:
                        row[formula_name] = round(self.math_eval.evaluate(expression, variables), 6)
                    except Exception as formula_error:
                        row[formula_name] = f"ERROR: {formula_error}"

                rows.append(row)
            except Exception as exc:
                rows.append(
                    {
                        "symbol": symbol,
                        "price": None,
                        "score": None,
                        "notes": f"ERROR: {exc}",
                    }
                )

        result = pd.DataFrame(rows)
        if "score" in result.columns:
            result = result.sort_values(by="score", ascending=False, na_position="last")
        return result


def load_watchlist(file_path: Path = WATCHLIST_FILE) -> List[str]:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            symbols = [line.strip() for line in file if line.strip()]
        if symbols:
            return symbols
    except FileNotFoundError:
        pass

    return ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "NVDA", "TSLA", "SPY", "GLD"]


def load_formulas(file_path: Path = FORMULAS_FILE) -> Dict[str, str]:
    formulas: Dict[str, str] = {}
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                clean = line.strip()
                if not clean or clean.startswith("#"):
                    continue
                if "=" not in clean:
                    continue
                name, expr = clean.split("=", 1)
                formulas[name.strip()] = expr.strip()
    except FileNotFoundError:
        pass
    return formulas


def compute_signal_score(row: pd.Series) -> int:
    score = 0

    if row["price"] > row["sma_20"]:
        score += 10
    if row["sma_20"] > row["sma_50"]:
        score += 10

    if row["macd"] > row["macd_signal"]:
        score += 15

    if 40 < row["rsi_14"] < 60:
        score += 10
    elif row["rsi_14"] < 30:
        score += 20
    elif row["rsi_14"] > 70:
        score -= 10

    if row["5d_%"] > 0:
        score += 10
    if row["20d_%"] > 0:
        score += 10

    if row["volume"] > row["avg_volume_20"]:
        score += 10

    return score


def classify_signal(score: float) -> str:
    if score >= 70:
        return "STRONG BUY"
    if score >= 50:
        return "BUY"
    if score >= 30:
        return "NEUTRAL"
    return "WEAK"


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def decision_engine(row: pd.Series) -> str:
    score = _safe_float(row.get("entry_score"), 0.0)
    pullback = _safe_float(row.get("pullback_strength"), 0.0)
    range_pos = _safe_float(row.get("range_position"), 50.0)

    if score >= 60 and range_pos < 65:
        return "HIGH PROBABILITY BUY"
    if score >= 45 and range_pos < 75:
        return "BUY"
    if score >= 40 and pullback < -2:
        return "PULLBACK BUY"
    if range_pos > 80:
        return "OVEREXTENDED"
    return "AVOID"


def build_top_summary(result: pd.DataFrame, top_n: int = 3) -> List[str]:
    if result.empty or "decision" not in result.columns:
        return []

    shortlist = result[result["decision"].isin(["HIGH PROBABILITY BUY", "BUY", "PULLBACK BUY"])]
    shortlist = shortlist.head(top_n)

    lines: List[str] = []
    for _, row in shortlist.iterrows():
        lines.append(f"{row['symbol']}: {row['decision']} (score {row['entry_score']})")
    return lines


def run_analysis(period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    symbols = load_watchlist()
    formulas = load_formulas()

    analyzer = Analyzer(period=period, interval=interval)
    result = analyzer.analyze(symbols, formulas)

    if result.empty:
        return result

    result["entry_score"] = result.apply(compute_signal_score, axis=1)
    result["signal"] = result["entry_score"].apply(classify_signal)
    result["decision"] = result.apply(decision_engine, axis=1)
    result = result.sort_values(by=["entry_score", "score"], ascending=False, na_position="last")
    return result


def main() -> None:
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 260)

    result = run_analysis()

    print("\nMARKET MATH ANALYZER V2\n")
    if result.empty:
        print("No results returned.")
        return

    top_summary = build_top_summary(result)
    if top_summary:
        print("TOP SETUPS:")
        for line in top_summary:
            print(f"- {line}")
        print()

    print(result.to_string(index=False))

    print("\nFiles you can edit:")
    print(f"- {WATCHLIST_FILE.name}  -> one ticker per line")
    print(f"- {FORMULAS_FILE.name}   -> one custom formula per line")
    print(f"\nProject folder: {BASE_DIR}")


if __name__ == "__main__":
    main()
