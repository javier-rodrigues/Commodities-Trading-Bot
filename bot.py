"""
Aurum Contra Oleum — Main Trading Bot
══════════════════════════════════════
Orchestrates connection to IBKR, signal evaluation, order execution,
risk management, and daily NAV tracking.

Usage:
    python bot.py                    # Normal mode — checks signals, proposes trades
    python bot.py --execute          # Execution mode — actually places orders
    python bot.py --close-all        # Emergency close all positions
    python bot.py --nav-snapshot     # Record daily NAV only (run at 3:55 PM)

IMPORTANT: TWS Paper Trading must be running on localhost:7497 before starting.
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, date

from ib_insync import IB, Stock, Option, MarketOrder, LimitOrder, util

import config
from utils.indicators import SignalEngine
from utils.risk_manager import RiskManager
from utils.journal import NAVTracker, TradeJournal
from strategies.vol_dispersion import VolDispersionStrategy
from strategies.uso_bear_put import USOBearPutStrategy
from strategies.relative_value import RelativeValueStrategy

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("bot")


class TradingBot:
    """
    Main bot class. Connects to IBKR, evaluates signals, proposes/executes trades.

    The bot operates in TWO modes:
    1. SIGNAL MODE (default): Evaluates indicators, prints recommendations.
       You review, then run with --execute to place orders.
    2. EXECUTE MODE (--execute): Actually places orders on IBKR.

    This two-step approach ensures you review every trade before execution,
    which is critical for both risk management and the assignment requirement
    that you understand every position.
    """

    def __init__(self, execute_mode: bool = False):
        self.ib = IB()
        self.execute_mode = execute_mode
        self.signals = SignalEngine()
        self.risk = RiskManager()
        self.nav_tracker = NAVTracker()
        self.journal = TradeJournal()

        # Initialize strategies
        self.strategies = {}

    def connect(self):
        """Connect to TWS Paper Trading."""
        try:
            self.ib.connect(
                config.TWS_HOST,
                config.TWS_PORT,
                clientId=config.CLIENT_ID,
                timeout=15,
            )
            logger.info(
                f"Connected to IBKR TWS at {config.TWS_HOST}:{config.TWS_PORT} "
                f"(Account: {self.ib.managedAccounts()})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to connect to TWS: {e}")
            logger.error(
                "Make sure TWS Paper Trading is running and API is enabled:\n"
                "  TWS > Edit > Global Configuration > API > Settings\n"
                "  - Enable ActiveX and Socket Clients: CHECKED\n"
                "  - Socket port: 7497\n"
                "  - Read-Only API: UNCHECKED"
            )
            return False

    def disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from TWS")

    def fetch_underlying_prices(self) -> dict:
        """Get current prices for all underlyings."""
        prices = {}
        for symbol, info in config.UNDERLYINGS.items():
            contract = Stock(symbol, info["exchange"], info["currency"])
            self.ib.qualifyContracts(contract)
            ticker = self.ib.reqMktData(contract)
            self.ib.sleep(2)  # Wait for data

            price = ticker.marketPrice()
            if price and price > 0:
                prices[f"{symbol}_price"] = price
                logger.info(f"{symbol}: ${price:.2f}")
            else:
                # Fallback to last close
                price = ticker.close or 0
                prices[f"{symbol}_price"] = price
                logger.warning(f"{symbol}: Using close ${price:.2f} (no live data)")

            self.ib.cancelMktData(contract)

        return prices

    def fetch_option_chains(self, prices: dict) -> dict:
        """Fetch option chains for greeks-based strike selection."""
        chains = {}
        for symbol in ["SLV", "GLD", "USO"]:
            try:
                contract = Stock(symbol, "ARCA", "USD")
                self.ib.qualifyContracts(contract)
                chain_def = self.ib.reqSecDefOptParams(
                    contract.symbol, "", contract.secType, contract.conId
                )

                if chain_def:
                    # Find the exchange with our target expiry
                    for cd in chain_def:
                        if config.TARGET_EXPIRY in cd.expirations:
                            # Get a range of strikes around current price
                            price = prices.get(f"{symbol}_price", 0)
                            strikes = sorted(
                                [s for s in cd.strikes if abs(s - price) < price * 0.15]
                            )

                            # Request market data for these options
                            option_contracts = []
                            for strike in strikes:
                                for right in ["C", "P"]:
                                    opt = Option(
                                        symbol, config.TARGET_EXPIRY, strike,
                                        right, cd.exchange, currency="USD"
                                    )
                                    option_contracts.append(opt)

                            qualified = self.ib.qualifyContracts(*option_contracts)
                            tickers = self.ib.reqTickers(*qualified)
                            self.ib.sleep(3)

                            chains[f"{symbol}_chains"] = tickers
                            logger.info(
                                f"{symbol} chain: {len(tickers)} contracts loaded "
                                f"({len(strikes)} strikes, expiry {config.TARGET_EXPIRY})"
                            )
                            break

            except Exception as e:
                logger.warning(f"Could not fetch {symbol} chain: {e}")

        return chains

    def get_account_nav(self) -> float:
        """Get current account NAV from IBKR."""
        account_values = self.ib.accountSummary()
        for av in account_values:
            if av.tag == "NetLiquidation":
                return float(av.value)
        # Fallback
        return config.INITIAL_CAPITAL

    def get_benchmark_price(self) -> float:
        """Get GLD closing price as benchmark."""
        contract = Stock("GLD", "ARCA", "USD")
        self.ib.qualifyContracts(contract)
        ticker = self.ib.reqMktData(contract)
        self.ib.sleep(2)
        price = ticker.marketPrice() or ticker.close or 0
        self.ib.cancelMktData(contract)
        return price

    def evaluate_signals(self, prices: dict):
        """Update indicators and evaluate all strategy signals."""
        now = datetime.now()

        # Update price history
        for symbol in ["SLV", "GLD", "USO"]:
            price = prices.get(f"{symbol}_price", 0)
            if price > 0:
                self.signals.update_price(symbol, price, now)

        # Update gold/silver ratio
        gold_p = prices.get("GLD_price", 0)
        slv_p = prices.get("SLV_price", 0)
        if gold_p > 0 and slv_p > 0:
            # GLD tracks gold at ~1/10 of spot, SLV tracks silver at ~1/1
            # Approximate spot: Gold ~= GLD * 10.8, Silver ~= SLV * 1.05
            gold_spot = gold_p * 10.8
            silver_spot = slv_p * 1.05
            ratio = gold_spot / silver_spot if silver_spot > 0 else 0
            self.signals.update_gs_ratio(ratio, now)

        # Evaluate
        all_signals = self.signals.evaluate_all()

        logger.info("=" * 60)
        logger.info("SIGNAL EVALUATION")
        logger.info("=" * 60)

        for strat_name, sig in all_signals.items():
            action = sig["action"]
            emoji = "🟢" if action == "ENTER" else "🔴" if action == "EXIT" else "⚪"
            logger.info(f"  {emoji} {sig['strategy']}: {action}")
            for reason in sig.get("reasons", []):
                logger.info(f"      → {reason}")
            for k, v in sig.items():
                if k not in ("strategy", "action", "reasons"):
                    logger.info(f"      {k}: {v}")

        return all_signals

    def propose_trades(self, signals: dict, chain_data: dict):
        """Generate trade proposals based on signals. Does NOT execute."""
        proposals = []

        # Strategy 4: Vol Dispersion
        if (config.STRAT4_ENABLED
                and signals["strategy4"]["action"] == "ENTER"
                and "vol_dispersion" not in self.strategies):

            strat = VolDispersionStrategy(self.ib)
            orders = strat.build_orders(chain_data)
            proposals.append({"strategy": strat, "orders": orders})

        # Strategy 6: USO Bear Put
        if (config.STRAT6_ENABLED
                and signals["strategy6"]["action"] == "ENTER"
                and "uso_bear_put" not in self.strategies):

            strat = USOBearPutStrategy(self.ib)
            orders = strat.build_orders(chain_data)
            proposals.append({"strategy": strat, "orders": orders})

        # Strategy 8: Relative Value
        if (config.STRAT8_ENABLED
                and signals["strategy8"]["action"] == "ENTER"
                and "relative_value" not in self.strategies):

            strat = RelativeValueStrategy(self.ib)
            orders = strat.build_orders(chain_data)
            proposals.append({"strategy": strat, "orders": orders})

        if proposals:
            logger.info("=" * 60)
            logger.info("TRADE PROPOSALS (review before executing)")
            logger.info("=" * 60)
            for i, prop in enumerate(proposals):
                logger.info(f"\n  Strategy: {prop['strategy'].name}")
                for order in prop["orders"]:
                    logger.info(f"    {order['description']}")
                logger.info(f"    Rationale: {prop['strategy'].entry_rationale()[:100]}...")
        else:
            logger.info("No new trade proposals at this time.")

        return proposals

    def execute_proposals(self, proposals: list):
        """Execute trade proposals on IBKR. Only runs in --execute mode."""
        if not self.execute_mode:
            logger.info(
                "DRY RUN — orders not placed. "
                "Run with --execute to place orders on IBKR."
            )
            return

        for prop in proposals:
            strat = prop["strategy"]
            logger.info(f"\nExecuting {strat.name}...")

            for order_spec in prop["orders"]:
                contract = order_spec["contract"]
                action = order_spec["action"]
                qty = order_spec["quantity"]

                try:
                    # Qualify the contract first
                    self.ib.qualifyContracts(contract)

                    # Use MarketOrder for paper trading (fills immediately)
                    order = MarketOrder(action, qty)
                    trade = self.ib.placeOrder(contract, order)
                    self.ib.sleep(3)  # Wait for fill

                    # Log fill
                    if trade.fills:
                        fill = trade.fills[0]
                        premium = fill.execution.price
                        logger.info(
                            f"  FILLED: {action} {qty} {contract.symbol} "
                            f"{contract.strike}{contract.right} @ ${premium:.4f}"
                        )

                        # Record in journal
                        trade_id = (
                            f"{strat.name}_{contract.symbol}_"
                            f"{contract.strike}{contract.right}_"
                            f"{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        )

                        multiplier = 1 if action == "BUY" else -1
                        strat.fills.append({
                            "trade_id": trade_id,
                            "premium": multiplier * premium * qty * 100,
                        })

                        self.journal.record_entry(
                            trade_id=trade_id,
                            strategy=strat.name,
                            underlying=contract.symbol,
                            option_type=contract.right,
                            strike=contract.strike,
                            expiration=contract.lastTradeDateOrContractMonth,
                            action=action,
                            contracts=qty,
                            entry_premium=premium,
                            iv_at_entry=0,  # TODO: capture from ticker
                            rationale=strat.entry_rationale(),
                        )
                    else:
                        logger.warning(
                            f"  NO FILL for {order_spec['description']} — "
                            f"check IBKR TWS manually"
                        )

                except Exception as e:
                    logger.error(f"  ORDER FAILED: {order_spec['description']} — {e}")

            # Register position with risk manager
            net_premium = strat.calculate_net_premium()
            self.risk.register_position(strat.name, {"net_premium": net_premium})
            self.strategies[strat.name] = strat
            strat.is_entered = True

    def check_exits(self):
        """Check all open positions for stop-loss, profit target, or time exit."""
        if not self.strategies:
            return []

        exits_needed = []

        # Get current market values
        current_values = {}
        for name, strat in self.strategies.items():
            if strat.is_entered:
                try:
                    val = strat.current_market_value()
                    current_values[name] = val
                except Exception:
                    pass

        # Check stops
        exits_needed.extend(self.risk.check_stop_losses(current_values))
        exits_needed.extend(self.risk.check_profit_targets(current_values))

        # Check force close
        if self.risk.should_force_close_all():
            exits_needed = list(self.strategies.keys())
            logger.critical("FORCE CLOSE ALL — end of trading window or drawdown limit")

        return list(set(exits_needed))

    def record_daily_nav(self):
        """Record end-of-day NAV snapshot (run at 3:55 PM ET)."""
        nav = self.get_account_nav()
        benchmark = self.get_benchmark_price()
        self.risk.update_nav(nav)
        self.nav_tracker.record(nav, benchmark)
        return nav, benchmark

    def run_cycle(self):
        """
        One full cycle: fetch data → evaluate signals → propose trades →
        check exits → (optional) execute.
        """
        logger.info("\n" + "=" * 70)
        logger.info(f"CYCLE START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)

        # 1. Fetch prices
        prices = self.fetch_underlying_prices()
        if not prices:
            logger.error("Could not fetch prices. Aborting cycle.")
            return

        # 2. Fetch option chains (for delta-based strike selection)
        chain_data = {**prices}
        # Only fetch chains if we need to enter new positions
        has_unentered = any(
            name not in self.strategies
            for name in ["vol_dispersion", "uso_bear_put", "relative_value"]
        )
        if has_unentered:
            chains = self.fetch_option_chains(prices)
            chain_data.update(chains)

        # 3. Evaluate signals
        signals = self.evaluate_signals(prices)

        # 4. Check exits on existing positions
        exits = self.check_exits()
        if exits:
            logger.warning(f"EXIT SIGNALS for: {exits}")

        # 5. Propose new trades
        proposals = self.propose_trades(signals, chain_data)

        # 6. Execute if in execute mode
        if proposals and self.execute_mode:
            self.execute_proposals(proposals)

        # 7. Update NAV
        nav = self.get_account_nav()
        self.risk.update_nav(nav)

        logger.info(f"\nPortfolio Summary: {self.risk.portfolio_summary()}")
        logger.info(f"CYCLE END: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


def main():
    parser = argparse.ArgumentParser(description="Aurum Contra Oleum Trading Bot")
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually place orders (default is signal-only mode)"
    )
    parser.add_argument(
        "--close-all", action="store_true",
        help="Close all open positions immediately"
    )
    parser.add_argument(
        "--nav-snapshot", action="store_true",
        help="Record daily NAV snapshot only"
    )
    parser.add_argument(
        "--loop", action="store_true",
        help=f"Run continuously, checking every {config.SIGNAL_CHECK_INTERVAL_MIN} min"
    )
    args = parser.parse_args()

    bot = TradingBot(execute_mode=args.execute)

    if not bot.connect():
        sys.exit(1)

    try:
        if args.nav_snapshot:
            nav, bench = bot.record_daily_nav()
            logger.info(f"NAV snapshot: ${nav:,.2f} | Benchmark (GLD): ${bench:.2f}")

        elif args.close_all:
            logger.warning("CLOSE ALL mode — liquidating all positions")
            bot.risk.is_liquidation_mode = True
            # You would add position-closing logic here
            logger.info("Manual close: use IBKR TWS to close all positions, "
                        "then record exits in the journal.")

        elif args.loop:
            logger.info(
                f"Entering loop mode — checking every "
                f"{config.SIGNAL_CHECK_INTERVAL_MIN} minutes"
            )
            while True:
                bot.run_cycle()
                logger.info(
                    f"Sleeping {config.SIGNAL_CHECK_INTERVAL_MIN} min until next check..."
                )
                time.sleep(config.SIGNAL_CHECK_INTERVAL_MIN * 60)

        else:
            # Single cycle
            bot.run_cycle()

    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    finally:
        bot.disconnect()


if __name__ == "__main__":
    main()
