"""
Abstract base class for all strategies.
Each strategy handles its own order construction and lifecycle.
"""

from abc import ABC, abstractmethod
from ib_insync import IB, Contract, Option, Trade
import logging
from typing import Optional

logger = logging.getLogger("strategy")


class BaseStrategy(ABC):
    """
    All strategies inherit from this. Provides common interface
    for the bot orchestrator to call.
    """

    def __init__(self, ib: IB, name: str):
        self.ib = ib
        self.name = name
        self.is_entered = False
        self.legs = []          # List of (contract, action, qty) tuples
        self.fills = []         # Completed fills
        self.entry_premiums = {}
        self.logger = logging.getLogger(f"strategy.{name}")

    @abstractmethod
    def build_orders(self, chain_data: dict) -> list:
        """
        Given option chain data, construct the list of orders.
        Returns list of dicts: [{contract, action, quantity, order_type, limit_price}, ...]
        """
        pass

    @abstractmethod
    def calculate_net_premium(self) -> float:
        """Calculate net premium paid (negative) or received (positive)."""
        pass

    @abstractmethod
    def current_market_value(self) -> float:
        """Current mark-to-market value of all legs."""
        pass

    def find_option_by_delta(
        self,
        chains: list,
        right: str,       # "C" or "P"
        target_delta: float,
        expiry: str,
    ) -> Optional[Contract]:
        """
        Find the option contract closest to target delta from available chains.
        `chains` is list of OptionChain or similar from IBKR.
        """
        best = None
        best_diff = float("inf")

        for chain in chains:
            if chain.right != right:
                continue
            if hasattr(chain, "lastGreeks") and chain.lastGreeks:
                delta = chain.lastGreeks.delta or 0
                diff = abs(abs(delta) - abs(target_delta))
                if diff < best_diff:
                    best_diff = diff
                    best = chain
            elif hasattr(chain, "modelGreeks") and chain.modelGreeks:
                delta = chain.modelGreeks.delta or 0
                diff = abs(abs(delta) - abs(target_delta))
                if diff < best_diff:
                    best_diff = diff
                    best = chain

        if best:
            self.logger.info(
                f"Found {right} option: strike={best.strike}, "
                f"delta={best.lastGreeks.delta if best.lastGreeks else 'N/A'}"
            )
        return best

    def find_option_by_strike(
        self,
        chains: list,
        right: str,
        target_strike: float,
        expiry: str,
    ) -> Optional[Contract]:
        """Find option closest to target strike price."""
        best = None
        best_diff = float("inf")

        for chain in chains:
            if chain.right != right:
                continue
            diff = abs(chain.strike - target_strike)
            if diff < best_diff:
                best_diff = diff
                best = chain

        return best

    def get_atm_strike(self, underlying_price: float, strike_increment: float = 1.0):
        """Round to nearest valid strike."""
        return round(underlying_price / strike_increment) * strike_increment

    def entry_rationale(self) -> str:
        """Generate the 3-5 sentence rationale required by the assignment."""
        return "Override in subclass."

    def exit_reflection(self, pnl: float) -> str:
        """Generate post-trade reflection required by the assignment."""
        return "Override in subclass."
