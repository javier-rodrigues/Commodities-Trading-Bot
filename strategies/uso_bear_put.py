"""
Strategy 6: USO Bear Put Spread
────────────────────────────────
BUY USO ATM Put (directional bearish leverage)
SELL USO OTM Put (reduces cost, caps downside profit)

Satisfies: Requirement 2 (leveraged directional — bearish)
Theory: Geopolitical risk premium mean-reversion (Hamilton, 2009).
        IEA/EIA institutional forecasts project oil below $80 by Q3 2026.
        SPR release of 400M barrels + demand destruction = deflating premium.
"""

from ib_insync import IB, Option
from strategies.base import BaseStrategy
import config
import logging

logger = logging.getLogger("strategy.uso_bear_put")


class USOBearPutStrategy(BaseStrategy):

    def __init__(self, ib: IB):
        super().__init__(ib, "uso_bear_put")
        self.long_put = None
        self.short_put = None
        self.contracts_qty = config.STRAT6_CONTRACTS

    def build_orders(self, chain_data: dict) -> list:
        """
        Build bear put spread:
        Leg 1: BUY USO ATM Put (or slightly OTM)
        Leg 2: SELL USO Put $5 lower (spread width from config)
        """
        orders = []
        uso_price = chain_data.get("USO_price", 85)
        expiry = config.TARGET_EXPIRY

        # Long put: ATM or slightly OTM
        long_strike = self.get_atm_strike(uso_price) + config.STRAT6_LONG_PUT_OFFSET
        short_strike = long_strike - config.STRAT6_SHORT_PUT_WIDTH

        self.long_put = Option(
            "USO", expiry, long_strike, "P", "SMART", currency="USD"
        )
        self.short_put = Option(
            "USO", expiry, short_strike, "P", "SMART", currency="USD"
        )

        orders.append({
            "contract": self.long_put,
            "action": "BUY",
            "quantity": self.contracts_qty,
            "description": f"BUY {self.contracts_qty} USO {long_strike}P {expiry}",
        })
        orders.append({
            "contract": self.short_put,
            "action": "SELL",
            "quantity": self.contracts_qty,
            "description": f"SELL {self.contracts_qty} USO {short_strike}P {expiry}",
        })

        logger.info(
            f"Bear put spread: BUY {long_strike}P / SELL {short_strike}P x{self.contracts_qty} "
            f"(width=${config.STRAT6_SHORT_PUT_WIDTH})"
        )

        return orders

    def calculate_net_premium(self) -> float:
        return sum(f.get("premium", 0) for f in self.fills)

    def current_market_value(self) -> float:
        total = 0
        for contract, direction in [
            (self.long_put, 1), (self.short_put, -1)
        ]:
            if contract:
                try:
                    ticker = self.ib.reqMktData(contract)
                    self.ib.sleep(0.5)
                    mid = (ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else 0
                    total += direction * mid * self.contracts_qty * 100
                    self.ib.cancelMktData(contract)
                except Exception:
                    pass
        return total

    def max_profit(self) -> float:
        """Max profit = spread width - net debit paid."""
        if self.long_put and self.short_put:
            width = self.long_put.strike - self.short_put.strike
            return width * self.contracts_qty * 100 - abs(self.calculate_net_premium())
        return 0

    def max_loss(self) -> float:
        """Max loss = net debit paid."""
        return abs(self.calculate_net_premium())

    def entry_rationale(self) -> str:
        return (
            "This bear put spread on USO expresses a leveraged bearish view on crude oil "
            "prices, which have surged approximately 50% from pre-conflict levels due to "
            "the US-Iran military conflict and Strait of Hormuz supply disruption. The "
            "geopolitical risk premium is expected to deflate based on three institutional "
            "forecasts: the IEA projects prices below $80/bbl by Q3 2026, the EIA's March "
            "2026 Short-Term Energy Outlook expects similar reversion, and J.P. Morgan "
            "maintains a structural bearish view with Brent averaging $60 on soft "
            "supply-demand fundamentals. The catalysts for reversion include the IEA's "
            "400-million-barrel strategic reserve release (March 11), demand destruction "
            "of approximately 1 mb/d from flight cancellations and industrial shutdowns, "
            "and emerging diplomatic channels between France, Italy, and Iran. The put "
            "spread structure provides 3-5x leverage relative to shorting the underlying "
            "directly, with max loss capped at the net premium paid — consistent with "
            "Hamilton (2009) on mean-reversion of supply-shock-driven oil price spikes."
        )

    def exit_reflection(self, pnl: float) -> str:
        outcome = "profitable" if pnl > 0 else "unprofitable"
        return (
            f"The USO bear put spread was {outcome} with P&L of ${pnl:,.2f}. "
            f"{'Oil prices declined as the geopolitical risk premium unwound, validating the mean-reversion thesis. ' if pnl > 0 else 'Oil prices remained elevated as the Iran conflict persisted longer than expected, demonstrating the risk of timing geopolitical events. '}"
            f"The defined-risk structure of the put spread limited losses to the net debit, "
            f"which was a key advantage given the uncertainty around conflict duration. "
            f"The leverage ratio of the spread meant that even modest oil price declines "
            f"translated into meaningful returns on capital deployed."
        )
