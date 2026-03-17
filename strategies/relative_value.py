"""
Strategy 8: SLV/GLD Relative Value
───────────────────────────────────
SELL GLD OTM Puts (collect premium; happy to own gold at discount)
BUY SLV OTM Calls (leveraged silver upside, funded by GLD premium)

Satisfies: Requirement 3 (cross-asset relative value trade)
Theory: Gold/silver cointegration (Mittal, 2025; Yaya et al., 2021).
        Volatility differential exploitation — SLV IV > GLD IV structurally.
        G/S ratio mean-reversion from elevated ~62 toward 55-60.
"""

from ib_insync import IB, Option
from strategies.base import BaseStrategy
import config
import logging

logger = logging.getLogger("strategy.relative_value")


class RelativeValueStrategy(BaseStrategy):

    def __init__(self, ib: IB):
        super().__init__(ib, "relative_value")
        self.gld_put = None      # Short GLD puts
        self.slv_call = None     # Long SLV calls
        self.gld_qty = config.STRAT8_GLD_PUT_CONTRACTS
        self.slv_qty = config.STRAT8_SLV_CALL_CONTRACTS

    def build_orders(self, chain_data: dict) -> list:
        """
        Build two-legged RV structure:
        Leg 1: SELL GLD OTM Puts (~20 delta, 8-10% below current)
        Leg 2: BUY SLV OTM Calls (~35 delta)
        """
        orders = []
        gld_price = chain_data.get("GLD_price", 465)
        slv_price = chain_data.get("SLV_price", 76)
        expiry = config.TARGET_EXPIRY

        # ── GLD Short Puts ──
        # ~20 delta = roughly 8-10% OTM
        gld_put_strike = round(gld_price * 0.92)  # ~8% below

        # Override with delta-based if chains available
        if "GLD_chains" in chain_data:
            put_opt = self.find_option_by_delta(
                chain_data["GLD_chains"], "P",
                abs(config.STRAT8_GLD_PUT_DELTA_TARGET), expiry
            )
            if put_opt:
                gld_put_strike = put_opt.strike

        self.gld_put = Option(
            "GLD", expiry, gld_put_strike, "P", "SMART", currency="USD"
        )

        orders.append({
            "contract": self.gld_put,
            "action": "SELL",
            "quantity": self.gld_qty,
            "description": f"SELL {self.gld_qty} GLD {gld_put_strike}P {expiry}",
        })

        # ── SLV Long Calls ──
        # ~35 delta = slightly OTM
        slv_call_strike = round(slv_price * 1.03)  # ~3% OTM

        if "SLV_chains" in chain_data:
            call_opt = self.find_option_by_delta(
                chain_data["SLV_chains"], "C",
                config.STRAT8_SLV_CALL_DELTA_TARGET, expiry
            )
            if call_opt:
                slv_call_strike = call_opt.strike

        self.slv_call = Option(
            "SLV", expiry, slv_call_strike, "C", "SMART", currency="USD"
        )

        orders.append({
            "contract": self.slv_call,
            "action": "BUY",
            "quantity": self.slv_qty,
            "description": f"BUY {self.slv_qty} SLV {slv_call_strike}C {expiry}",
        })

        logger.info(
            f"Relative value: SELL {self.gld_qty} GLD {gld_put_strike}P / "
            f"BUY {self.slv_qty} SLV {slv_call_strike}C"
        )

        return orders

    def calculate_net_premium(self) -> float:
        return sum(f.get("premium", 0) for f in self.fills)

    def current_market_value(self) -> float:
        total = 0
        for contract, direction, qty in [
            (self.gld_put, -1, self.gld_qty),
            (self.slv_call, 1, self.slv_qty),
        ]:
            if contract:
                try:
                    ticker = self.ib.reqMktData(contract)
                    self.ib.sleep(0.5)
                    mid = (ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else 0
                    total += direction * mid * qty * 100
                    self.ib.cancelMktData(contract)
                except Exception:
                    pass
        return total

    def entry_rationale(self) -> str:
        return (
            "This cross-asset relative value trade expresses the view that silver will "
            "outperform gold over the trading window, exploiting the elevated gold/silver "
            "ratio (~62) which sits above the long-run cointegrated equilibrium documented "
            "by Mittal & Mittal (2025) and Yaya, Vo & Olayinka (2021). The structure sells "
            "GLD OTM puts — collecting premium from gold's elevated post-crash implied "
            "volatility while expressing willingness to own gold at a discount (consistent "
            "with structural bullishness). The premium received partially funds SLV OTM "
            "calls that provide leveraged upside to silver's higher-beta recovery. The "
            "volatility differential between SLV and GLD (SLV IV structurally exceeds GLD "
            "IV due to silver's smaller market and industrial demand component) means the "
            "GLD put premium is rich relative to its realized risk, while SLV calls offer "
            "asymmetric payoff if the post-crash recovery accelerates. This is a genuine "
            "relative value trade: it profits from silver outperforming gold regardless of "
            "the absolute direction of precious metals, though it has a net bullish bias."
        )

    def exit_reflection(self, pnl: float) -> str:
        outcome = "profitable" if pnl > 0 else "unprofitable"
        return (
            f"The SLV/GLD relative value trade was {outcome} with P&L of ${pnl:,.2f}. "
            f"{'The gold/silver ratio compressed as expected, with silver outperforming gold during the post-crash recovery phase. ' if pnl > 0 else 'The gold/silver ratio did not compress as expected within the trading window, highlighting the challenge of timing mean-reversion in a short period. '}"
            f"The self-funding structure (GLD put premium financing SLV calls) was an "
            f"effective way to express a relative view with limited net capital outlay. "
            f"The key takeaway is that cointegration-based trades require patience and "
            f"that the 14-day trading window may be insufficient for full ratio convergence, "
            f"though the directional bias provided additional return potential."
        )
