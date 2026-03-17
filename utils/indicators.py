"""
Technical indicators for entry/exit signal generation.
RSI, Bollinger Bands, IV Percentile Rank, Gold/Silver Ratio Z-Score.
"""

import numpy as np
import pandas as pd
from typing import Optional
import config


def rsi(prices: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    """Relative Strength Index."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bollinger_bands(
    prices: pd.Series,
    period: int = config.BB_PERIOD,
    std_dev: float = config.BB_STD_DEV,
) -> dict:
    """Bollinger Bands — returns upper, middle, lower, and %B position."""
    middle = prices.rolling(period).mean()
    std = prices.rolling(period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    pct_b = (prices - lower) / (upper - lower)  # 0 = lower band, 1 = upper
    return {"upper": upper, "middle": middle, "lower": lower, "pct_b": pct_b}


def iv_percentile_rank(
    current_iv: float,
    iv_history: pd.Series,
    lookback: int = config.IV_LOOKBACK_DAYS,
) -> float:
    """
    IV Percentile Rank: what % of the past `lookback` days had IV below current.
    Returns 0-100. High = IV is elevated relative to history.
    """
    recent = iv_history.tail(lookback).dropna()
    if len(recent) == 0:
        return 50.0  # default if no history
    return float((recent < current_iv).sum() / len(recent) * 100)


def gold_silver_ratio(gold_price: float, silver_price: float) -> float:
    """Gold/Silver ratio — higher means silver is cheap relative to gold."""
    if silver_price <= 0:
        return float("nan")
    return gold_price / silver_price


def gs_ratio_zscore(
    ratio_series: pd.Series, period: int = config.GS_RATIO_MA_PERIOD
) -> float:
    """
    Z-score of current G/S ratio vs its rolling mean/std.
    Positive = ratio is elevated (silver cheap). Negative = silver expensive.
    """
    if len(ratio_series) < period:
        return 0.0
    mean = ratio_series.rolling(period).mean().iloc[-1]
    std = ratio_series.rolling(period).std().iloc[-1]
    if std == 0 or np.isnan(std):
        return 0.0
    return float((ratio_series.iloc[-1] - mean) / std)


def vwap(prices: pd.Series, volumes: pd.Series) -> pd.Series:
    """Volume-Weighted Average Price (intraday)."""
    cum_vol = volumes.cumsum()
    cum_pv = (prices * volumes).cumsum()
    return cum_pv / cum_vol


class SignalEngine:
    """
    Aggregates indicators into actionable entry/exit signals for each strategy.
    Call `evaluate()` with current market data to get signal dict.
    """

    def __init__(self):
        self.price_history = {}   # symbol -> pd.Series of closes
        self.iv_history = {}      # symbol -> pd.Series of IV
        self.gs_ratio_history = pd.Series(dtype=float)

    def update_price(self, symbol: str, price: float, timestamp: pd.Timestamp):
        if symbol not in self.price_history:
            self.price_history[symbol] = pd.Series(dtype=float)
        self.price_history[symbol].loc[timestamp] = price

    def update_iv(self, symbol: str, iv: float, timestamp: pd.Timestamp):
        if symbol not in self.iv_history:
            self.iv_history[symbol] = pd.Series(dtype=float)
        self.iv_history[symbol].loc[timestamp] = iv

    def update_gs_ratio(self, ratio: float, timestamp: pd.Timestamp):
        self.gs_ratio_history.loc[timestamp] = ratio

    def evaluate_strategy4(self) -> dict:
        """
        Strategy 4: SLV vs USO Vol Dispersion
        Entry when: SLV IV percentile < threshold AND USO IV percentile > threshold
                     AND SLV RSI < 55 (room to move)
        """
        signals = {"strategy": "vol_dispersion", "action": "HOLD", "reasons": []}

        slv_prices = self.price_history.get("SLV", pd.Series(dtype=float))
        slv_iv = self.iv_history.get("SLV", pd.Series(dtype=float))
        uso_iv = self.iv_history.get("USO", pd.Series(dtype=float))

        if len(slv_prices) < config.RSI_PERIOD:
            signals["reasons"].append("Insufficient price history for RSI")
            return signals

        # RSI check
        slv_rsi = rsi(slv_prices).iloc[-1]
        signals["slv_rsi"] = round(slv_rsi, 2)

        # IV percentile checks
        if len(slv_iv) > 20:
            slv_iv_pct = iv_percentile_rank(slv_iv.iloc[-1], slv_iv)
            signals["slv_iv_percentile"] = round(slv_iv_pct, 1)
        else:
            slv_iv_pct = 50  # default
            signals["reasons"].append("Limited SLV IV history")

        if len(uso_iv) > 20:
            uso_iv_pct = iv_percentile_rank(uso_iv.iloc[-1], uso_iv)
            signals["uso_iv_percentile"] = round(uso_iv_pct, 1)
        else:
            uso_iv_pct = 50
            signals["reasons"].append("Limited USO IV history")

        # Entry logic
        entry_conditions = [
            slv_rsi < config.STRAT4_RSI_SLV_MAX,
            slv_iv_pct < config.STRAT4_SLV_IV_PERCENTILE_MAX,
            uso_iv_pct > config.STRAT4_USO_IV_PERCENTILE_MIN,
        ]

        if all(entry_conditions):
            signals["action"] = "ENTER"
            signals["reasons"].append(
                f"SLV RSI={slv_rsi:.1f}<{config.STRAT4_RSI_SLV_MAX}, "
                f"SLV IV%={slv_iv_pct:.0f}<{config.STRAT4_SLV_IV_PERCENTILE_MAX}, "
                f"USO IV%={uso_iv_pct:.0f}>{config.STRAT4_USO_IV_PERCENTILE_MIN}"
            )
        else:
            signals["reasons"].append("Entry conditions not all met")

        return signals

    def evaluate_strategy6(self) -> dict:
        """
        Strategy 6: USO Bear Put Spread
        Entry when: USO RSI > 55 AND USO Bollinger %B > 0.6
        """
        signals = {"strategy": "uso_bear_put", "action": "HOLD", "reasons": []}

        uso_prices = self.price_history.get("USO", pd.Series(dtype=float))

        if len(uso_prices) < config.BB_PERIOD:
            signals["reasons"].append("Insufficient USO price history")
            return signals

        uso_rsi_val = rsi(uso_prices).iloc[-1]
        bb = bollinger_bands(uso_prices)
        uso_bb_pct = bb["pct_b"].iloc[-1]

        signals["uso_rsi"] = round(uso_rsi_val, 2)
        signals["uso_bb_pctb"] = round(uso_bb_pct, 2)

        entry_conditions = [
            uso_rsi_val > config.STRAT6_USO_RSI_MIN,
            uso_bb_pct > config.STRAT6_USO_BB_POSITION_MIN,
        ]

        if all(entry_conditions):
            signals["action"] = "ENTER"
            signals["reasons"].append(
                f"USO RSI={uso_rsi_val:.1f}>{config.STRAT6_USO_RSI_MIN}, "
                f"USO BB%B={uso_bb_pct:.2f}>{config.STRAT6_USO_BB_POSITION_MIN}"
            )
        else:
            signals["reasons"].append("USO not sufficiently overbought for entry")

        return signals

    def evaluate_strategy8(self) -> dict:
        """
        Strategy 8: Sell GLD Puts / Buy SLV Calls (Relative Value)
        Entry when: G/S ratio > 60 AND SLV RSI < 50
        """
        signals = {"strategy": "relative_value", "action": "HOLD", "reasons": []}

        slv_prices = self.price_history.get("SLV", pd.Series(dtype=float))

        if len(slv_prices) < config.RSI_PERIOD:
            signals["reasons"].append("Insufficient SLV price history")
            return signals

        slv_rsi_val = rsi(slv_prices).iloc[-1]
        signals["slv_rsi"] = round(slv_rsi_val, 2)

        if len(self.gs_ratio_history) > 0:
            current_ratio = self.gs_ratio_history.iloc[-1]
            signals["gs_ratio"] = round(current_ratio, 2)

            if len(self.gs_ratio_history) >= config.GS_RATIO_MA_PERIOD:
                z = gs_ratio_zscore(self.gs_ratio_history)
                signals["gs_ratio_zscore"] = round(z, 2)
        else:
            current_ratio = 62  # approximate current
            signals["reasons"].append("No G/S ratio history yet")

        entry_conditions = [
            current_ratio > config.STRAT8_GS_RATIO_ENTRY_MIN,
            slv_rsi_val < config.STRAT8_SLV_RSI_MAX,
        ]

        if all(entry_conditions):
            signals["action"] = "ENTER"
            signals["reasons"].append(
                f"G/S Ratio={current_ratio:.1f}>{config.STRAT8_GS_RATIO_ENTRY_MIN}, "
                f"SLV RSI={slv_rsi_val:.1f}<{config.STRAT8_SLV_RSI_MAX}"
            )
        else:
            signals["reasons"].append("G/S ratio or SLV RSI not at entry level")

        return signals

    def evaluate_all(self) -> dict:
        """Run all strategy evaluations and return consolidated signals."""
        return {
            "strategy4": self.evaluate_strategy4(),
            "strategy6": self.evaluate_strategy6(),
            "strategy8": self.evaluate_strategy8(),
        }
