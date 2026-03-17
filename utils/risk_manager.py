"""
Risk manager — position sizing, drawdown monitoring, stop-loss enforcement.
"""

import logging
from datetime import date, datetime
from typing import Optional
import config

logger = logging.getLogger("risk_manager")


class RiskManager:
    """
    Centralized risk management. Tracks NAV, enforces limits.
    """

    def __init__(self, initial_capital: float = config.INITIAL_CAPITAL):
        self.initial_capital = initial_capital
        self.peak_nav = initial_capital
        self.current_nav = initial_capital
        self.positions = {}           # strategy_name -> position_info dict
        self.is_liquidation_mode = False

    def update_nav(self, nav: float):
        """Update current NAV and check drawdown limits."""
        self.current_nav = nav
        if nav > self.peak_nav:
            self.peak_nav = nav

        drawdown = (self.peak_nav - nav) / self.peak_nav
        if drawdown >= config.MAX_PORTFOLIO_DRAWDOWN:
            logger.critical(
                f"DRAWDOWN LIMIT BREACHED: {drawdown:.1%} "
                f"(peak={self.peak_nav:,.0f}, current={nav:,.0f}). "
                f"LIQUIDATING ALL POSITIONS."
            )
            self.is_liquidation_mode = True

        return {
            "nav": nav,
            "peak": self.peak_nav,
            "drawdown_pct": drawdown,
            "liquidation_triggered": self.is_liquidation_mode,
        }

    def check_position_size(self, premium_cost: float, strategy_name: str) -> dict:
        """
        Validate that a new trade doesn't exceed allocation limits.
        Returns {approved: bool, reason: str, max_allowed: float}
        """
        max_for_trade = self.current_nav * config.MAX_SINGLE_TRADE_PCT
        cash_floor = self.current_nav * config.CASH_RESERVE_PCT

        # Sum of all current position premiums
        total_deployed = sum(
            p.get("premium_paid", 0) for p in self.positions.values()
        )
        available = self.current_nav - total_deployed - cash_floor

        if self.is_liquidation_mode:
            return {
                "approved": False,
                "reason": "Portfolio in LIQUIDATION MODE — no new trades",
                "max_allowed": 0,
            }

        if premium_cost > max_for_trade:
            return {
                "approved": False,
                "reason": f"Premium ${premium_cost:,.0f} exceeds single-trade max "
                          f"${max_for_trade:,.0f} ({config.MAX_SINGLE_TRADE_PCT:.0%})",
                "max_allowed": max_for_trade,
            }

        if premium_cost > available:
            return {
                "approved": False,
                "reason": f"Premium ${premium_cost:,.0f} exceeds available capital "
                          f"${available:,.0f} (after reserve)",
                "max_allowed": available,
            }

        return {
            "approved": True,
            "reason": "Within limits",
            "max_allowed": max_for_trade,
        }

    def register_position(self, strategy_name: str, position_info: dict):
        """Register a new position for tracking."""
        self.positions[strategy_name] = {
            "entry_date": datetime.now(),
            "premium_paid": position_info.get("premium_paid", 0),
            "premium_received": position_info.get("premium_received", 0),
            "net_premium": position_info.get("net_premium", 0),
            "current_value": position_info.get("net_premium", 0),
            "stop_loss_level": position_info.get("net_premium", 0)
                               * config.PREMIUM_STOP_LOSS_PCT,
            "status": "OPEN",
        }
        logger.info(f"Position registered: {strategy_name} | {position_info}")

    def check_stop_losses(self, current_values: dict) -> list:
        """
        Check all open positions against stop-loss levels.
        current_values: {strategy_name: current_market_value_of_position}
        Returns list of strategies that should be closed.
        """
        close_list = []
        for name, pos in self.positions.items():
            if pos["status"] != "OPEN":
                continue

            if name not in current_values:
                continue

            current_val = current_values[name]
            pos["current_value"] = current_val
            net_premium = pos["net_premium"]

            # For debit positions (net_premium < 0 = we paid), stop if value
            # drops below 50% of what we paid
            if net_premium < 0:  # We paid premium (debit)
                loss = net_premium - current_val  # Both negative; loss if more neg
                if current_val < net_premium * config.PREMIUM_STOP_LOSS_PCT:
                    close_list.append(name)
                    logger.warning(
                        f"STOP LOSS triggered for {name}: "
                        f"value={current_val:.2f}, threshold={pos['stop_loss_level']:.2f}"
                    )

            # For credit positions (net_premium > 0), stop if loss exceeds premium
            elif net_premium > 0:
                if current_val < -net_premium:
                    close_list.append(name)
                    logger.warning(
                        f"STOP LOSS triggered for {name} (credit): "
                        f"loss={current_val:.2f} exceeds premium={net_premium:.2f}"
                    )

        return close_list

    def check_profit_targets(self, current_values: dict) -> list:
        """Check if any positions hit profit targets."""
        close_list = []
        for name, pos in self.positions.items():
            if pos["status"] != "OPEN" or name not in current_values:
                continue

            current_val = current_values[name]
            net_premium = pos["net_premium"]

            # For debit positions, profit target = current value > entry * (1 + target%)
            if net_premium < 0:
                profit_threshold = abs(net_premium) * config.PROFIT_TARGET_PCT
                unrealized = current_val - net_premium
                if unrealized >= profit_threshold:
                    close_list.append(name)
                    logger.info(
                        f"PROFIT TARGET hit for {name}: "
                        f"unrealized={unrealized:.2f}, target={profit_threshold:.2f}"
                    )

        return close_list

    def check_time_exit(self, positions_dte: dict) -> list:
        """Close positions with DTE <= threshold."""
        close_list = []
        for name, dte in positions_dte.items():
            if name in self.positions and self.positions[name]["status"] == "OPEN":
                if dte <= config.TIME_DECAY_EXIT_DTE:
                    close_list.append(name)
                    logger.info(f"TIME EXIT for {name}: DTE={dte}")
        return close_list

    def should_force_close_all(self) -> bool:
        """Check if we're at or past the force-close date."""
        return date.today() >= config.FORCE_CLOSE_DATE or self.is_liquidation_mode

    def mark_closed(self, strategy_name: str, exit_info: dict):
        """Mark a position as closed."""
        if strategy_name in self.positions:
            self.positions[strategy_name]["status"] = "CLOSED"
            self.positions[strategy_name]["exit_date"] = datetime.now()
            self.positions[strategy_name].update(exit_info)
            logger.info(f"Position closed: {strategy_name} | {exit_info}")

    def portfolio_summary(self) -> dict:
        """Generate portfolio summary for dashboard."""
        open_positions = {
            k: v for k, v in self.positions.items() if v["status"] == "OPEN"
        }
        closed_positions = {
            k: v for k, v in self.positions.items() if v["status"] == "CLOSED"
        }
        total_premium_deployed = sum(
            abs(v.get("net_premium", 0)) for v in open_positions.values()
        )
        drawdown = (self.peak_nav - self.current_nav) / self.peak_nav if self.peak_nav > 0 else 0

        return {
            "current_nav": self.current_nav,
            "peak_nav": self.peak_nav,
            "drawdown_pct": drawdown,
            "initial_capital": self.initial_capital,
            "total_return_pct": (self.current_nav - self.initial_capital)
                                / self.initial_capital,
            "open_positions": len(open_positions),
            "closed_positions": len(closed_positions),
            "capital_deployed": total_premium_deployed,
            "cash_available": self.current_nav - total_premium_deployed,
            "liquidation_mode": self.is_liquidation_mode,
        }
