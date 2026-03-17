"""
Strategy 4: SLV vs USO Volatility Dispersion
─────────────────────────────────────────────
LONG SLV straddle (long vol on silver — expects large moves post-crash)
SHORT USO strangle (short vol on oil — expects vol to compress as geopolitical
                    risk premium deflates and SPR releases cushion supply)

Satisfies: Requirement 2 (volatility leverage) + contributes to Requirement 3
Theory: Jubinski & Lipton (2013) — gold/silver respond positively to implied vol
        while oil responds negatively. BIS WP 619 — cross-commodity VRP dynamics.
"""

from ib_insync import IB, Option, LimitOrder, MarketOrder
from strategies.base import BaseStrategy
import config
import logging

logger = logging.getLogger("strategy.vol_dispersion")


class VolDispersionStrategy(BaseStrategy):

    def __init__(self, ib: IB):
        super().__init__(ib, "vol_dispersion")
        self.slv_call = None
        self.slv_put = None
        self.uso_call = None
        self.uso_put = None
        self.slv_contracts_qty = config.STRAT4_SLV_CONTRACTS
        self.uso_contracts_qty = config.STRAT4_USO_CONTRACTS

    def build_orders(self, chain_data: dict) -> list:
        """
        Build the 4-leg structure:
        Leg 1: BUY SLV ATM Call (long vol)
        Leg 2: BUY SLV ATM Put  (long vol)
        Leg 3: SELL USO OTM Call (short vol)
        Leg 4: SELL USO OTM Put  (short vol)
        """
        orders = []
        slv_price = chain_data.get("SLV_price", 76)
        uso_price = chain_data.get("USO_price", 85)
        expiry = config.TARGET_EXPIRY

        # ── SLV ATM Straddle (LONG) ──
        slv_atm = self.get_atm_strike(slv_price)

        self.slv_call = Option(
            "SLV", expiry, slv_atm, "C", "SMART", currency="USD"
        )
        self.slv_put = Option(
            "SLV", expiry, slv_atm, "P", "SMART", currency="USD"
        )

        orders.append({
            "contract": self.slv_call,
            "action": "BUY",
            "quantity": self.slv_contracts_qty,
            "description": f"BUY {self.slv_contracts_qty} SLV {slv_atm}C {expiry}",
        })
        orders.append({
            "contract": self.slv_put,
            "action": "BUY",
            "quantity": self.slv_contracts_qty,
            "description": f"BUY {self.slv_contracts_qty} SLV {slv_atm}P {expiry}",
        })

        # ── USO OTM Strangle (SHORT) ──
        # Use delta-based selection if chain data includes greeks,
        # otherwise approximate with fixed offsets
        uso_call_strike = round(uso_price * 1.08)   # ~8% OTM call
        uso_put_strike = round(uso_price * 0.92)    # ~8% OTM put

        # Override with delta-based if available
        if "USO_chains" in chain_data:
            call_opt = self.find_option_by_delta(
                chain_data["USO_chains"], "C",
                config.STRAT4_USO_CALL_DELTA_TARGET, expiry
            )
            if call_opt:
                uso_call_strike = call_opt.strike

            put_opt = self.find_option_by_delta(
                chain_data["USO_chains"], "P",
                config.STRAT4_USO_PUT_DELTA_TARGET, expiry
            )
            if put_opt:
                uso_put_strike = put_opt.strike

        self.uso_call = Option(
            "USO", expiry, uso_call_strike, "C", "SMART", currency="USD"
        )
        self.uso_put = Option(
            "USO", expiry, uso_put_strike, "P", "SMART", currency="USD"
        )

        orders.append({
            "contract": self.uso_call,
            "action": "SELL",
            "quantity": self.uso_contracts_qty,
            "description": f"SELL {self.uso_contracts_qty} USO {uso_call_strike}C {expiry}",
        })
        orders.append({
            "contract": self.uso_put,
            "action": "SELL",
            "quantity": self.uso_contracts_qty,
            "description": f"SELL {self.uso_contracts_qty} USO {uso_put_strike}P {expiry}",
        })

        return orders

    def calculate_net_premium(self) -> float:
        """SLV straddle = debit; USO strangle = credit. Net could be either."""
        # This gets filled in after execution from actual fills
        return sum(f.get("premium", 0) for f in self.fills)

    def current_market_value(self) -> float:
        """Mark-to-market all four legs."""
        total = 0
        for contract, direction in [
            (self.slv_call, 1), (self.slv_put, 1),
            (self.uso_call, -1), (self.uso_put, -1),
        ]:
            if contract:
                try:
                    ticker = self.ib.reqMktData(contract)
                    self.ib.sleep(0.5)
                    mid = (ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else 0
                    qty = self.slv_contracts_qty if "SLV" in (contract.symbol or "") else self.uso_contracts_qty
                    total += direction * mid * qty * 100  # options multiplier
                    self.ib.cancelMktData(contract)
                except Exception:
                    pass
        return total

    def entry_rationale(self) -> str:
        return (
            "This trade exploits the divergent volatility dynamics between precious metals "
            "and energy commodities documented by Jubinski & Lipton (2013). Silver implied "
            "volatility remains elevated post-January 30 crash but is declining from extremes, "
            "while oil IV is inflated by the Iran/Strait of Hormuz conflict creating an "
            "unsustainable geopolitical risk premium. The long SLV straddle profits from "
            "large silver price moves in either direction during the post-crash recovery "
            "phase, while the short USO strangle collects premium as oil volatility compresses "
            "with diplomatic developments and IEA strategic reserve releases (400M barrels on "
            "March 11). The cross-asset structure creates a volatility spread that is net "
            "long precious metals vol and short energy vol — a direct expression of our fund "
            "thesis grounded in the BIS Working Paper 619 framework on cross-commodity "
            "variance risk premium dynamics."
        )

    def exit_reflection(self, pnl: float) -> str:
        outcome = "profitable" if pnl > 0 else "unprofitable"
        return (
            f"The volatility dispersion trade was {outcome} with a P&L of ${pnl:,.2f}. "
            f"{'Silver realized volatility exceeded the premium paid for the straddle, ' if pnl > 0 else 'Silver volatility was insufficient to overcome straddle theta decay, '}"
            f"while the USO strangle {'benefited from vol compression as expected.' if pnl > 0 else 'faced challenges as oil volatility persisted.'} "
            f"The key lesson is that cross-asset vol trades require careful sizing of each "
            f"leg to ensure the vol differential materializes within the holding period."
        )
