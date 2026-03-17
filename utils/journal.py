"""
NAV tracker — records daily portfolio value for Section 5/6 of the assignment.
Trade journal — generates the Excel trade log required by Section 4.1.
"""

import os
import csv
import logging
from datetime import datetime, date
from typing import Optional
import pandas as pd
import config

logger = logging.getLogger("journal")


class NAVTracker:
    """Records end-of-day NAV, daily P&L, daily return, and benchmark."""

    def __init__(self, filepath: str = config.NAV_CSV):
        self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "date", "nav", "daily_pnl", "daily_return",
                    "benchmark_close", "benchmark_return",
                    "cumulative_return", "benchmark_cumulative_return",
                ])

    def record(
        self,
        nav: float,
        benchmark_close: float,
        record_date: Optional[date] = None,
    ):
        """Record a daily NAV snapshot."""
        if record_date is None:
            record_date = date.today()

        df = self.load()

        if len(df) > 0:
            prev_nav = df["nav"].iloc[-1]
            prev_bench = df["benchmark_close"].iloc[-1]
            daily_pnl = nav - prev_nav
            daily_return = daily_pnl / prev_nav if prev_nav != 0 else 0
            bench_return = (
                (benchmark_close - prev_bench) / prev_bench
                if prev_bench != 0
                else 0
            )
        else:
            daily_pnl = 0
            daily_return = 0
            bench_return = 0

        # Cumulative returns from initial values
        initial_nav = config.INITIAL_CAPITAL
        cum_return = (nav - initial_nav) / initial_nav

        if len(df) > 0:
            initial_bench = df["benchmark_close"].iloc[0]
            bench_cum_return = (
                (benchmark_close - initial_bench) / initial_bench
                if initial_bench != 0
                else 0
            )
        else:
            bench_cum_return = 0

        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                record_date.isoformat(),
                round(nav, 2),
                round(daily_pnl, 2),
                round(daily_return, 6),
                round(benchmark_close, 2),
                round(bench_return, 6),
                round(cum_return, 6),
                round(bench_cum_return, 6),
            ])

        logger.info(
            f"NAV recorded: {record_date} | NAV=${nav:,.2f} | "
            f"Daily P&L=${daily_pnl:,.2f} | Return={daily_return:.4%}"
        )

    def load(self) -> pd.DataFrame:
        """Load NAV history as DataFrame."""
        if os.path.exists(self.filepath):
            df = pd.read_csv(self.filepath)
            if len(df) > 0:
                df["date"] = pd.to_datetime(df["date"])
            return df
        return pd.DataFrame()


class TradeJournal:
    """
    Records every trade per Section 4.1 requirements:
    entry date, underlying, option type, strike, expiration, premium,
    contracts, IV at entry, rationale, exit date, closing premium, P&L, reflection.
    """

    def __init__(self, filepath: str = config.TRADES_CSV):
        self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "trade_id",
                    "strategy",
                    "entry_date",
                    "underlying",
                    "option_type",
                    "strike",
                    "expiration",
                    "action",
                    "contracts",
                    "entry_premium",
                    "iv_at_entry",
                    "rationale",
                    "exit_date",
                    "exit_premium",
                    "realized_pnl",
                    "reflection",
                    "screenshot_file",
                ])

    def record_entry(
        self,
        trade_id: str,
        strategy: str,
        underlying: str,
        option_type: str,
        strike: float,
        expiration: str,
        action: str,
        contracts: int,
        entry_premium: float,
        iv_at_entry: float,
        rationale: str,
    ):
        """Record a trade entry."""
        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                trade_id,
                strategy,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                underlying,
                option_type,
                strike,
                expiration,
                action,
                contracts,
                round(entry_premium, 4),
                round(iv_at_entry, 4),
                rationale,
                "",  # exit_date
                "",  # exit_premium
                "",  # realized_pnl
                "",  # reflection
                "",  # screenshot
            ])
        logger.info(f"Trade entry recorded: {trade_id} | {action} {contracts} {underlying} {strike}{option_type}")

    def record_exit(
        self,
        trade_id: str,
        exit_premium: float,
        realized_pnl: float,
        reflection: str,
    ):
        """Update a trade with exit information."""
        df = pd.read_csv(self.filepath)
        mask = df["trade_id"] == trade_id
        if mask.any():
            df.loc[mask, "exit_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df.loc[mask, "exit_premium"] = round(exit_premium, 4)
            df.loc[mask, "realized_pnl"] = round(realized_pnl, 2)
            df.loc[mask, "reflection"] = reflection
            df.to_csv(self.filepath, index=False)
            logger.info(f"Trade exit recorded: {trade_id} | P&L=${realized_pnl:,.2f}")

    def load(self) -> pd.DataFrame:
        if os.path.exists(self.filepath):
            return pd.read_csv(self.filepath)
        return pd.DataFrame()

    def export_to_excel(self, output_path: str = "data/trade_journal.xlsx"):
        """Export trade journal to Excel for submission."""
        df = self.load()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_excel(output_path, index=False, sheet_name="Trade Journal")
        logger.info(f"Trade journal exported to {output_path}")
        return output_path
