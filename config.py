"""
Aurum Contra Oleum — Configuration
All tunable parameters in one place. Adjust strikes/expirations based on
live IBKR option chains when you first connect.
"""

from datetime import date, datetime

# ─────────────────────────────────────────────
# IBKR CONNECTION
# ─────────────────────────────────────────────
TWS_HOST = "127.0.0.1"
TWS_PORT = 7497          # Paper trading default (live = 7496)
CLIENT_ID = 1            # Unique per concurrent connection

# ─────────────────────────────────────────────
# TRADING WINDOW
# ─────────────────────────────────────────────
TRADING_START = date(2026, 3, 16)
TRADING_END = date(2026, 4, 3)
FORCE_CLOSE_DATE = date(2026, 4, 3)  # All positions closed EOD

# ─────────────────────────────────────────────
# PORTFOLIO PARAMETERS
# ─────────────────────────────────────────────
INITIAL_CAPITAL = 1_000_000       # IBKR paper account default ($1M)
MAX_SINGLE_TRADE_PCT = 0.30       # Max 30% of capital per trade
MAX_PORTFOLIO_DRAWDOWN = 0.25     # Liquidate all if NAV drops 25% from peak
CASH_RESERVE_PCT = 0.15           # Keep 15% in cash minimum
PREMIUM_STOP_LOSS_PCT = 0.50      # Stop loss at 50% of premium paid
PROFIT_TARGET_PCT = 0.50          # Take profit at 50% of max profit (spreads)
TIME_DECAY_EXIT_DTE = 3           # Close positions with ≤3 DTE remaining

# ─────────────────────────────────────────────
# UNDERLYING CONTRACTS
# ─────────────────────────────────────────────
UNDERLYINGS = {
    "SLV": {"exchange": "ARCA", "currency": "USD", "sec_type": "STK"},
    "GLD": {"exchange": "ARCA", "currency": "USD", "sec_type": "STK"},
    "USO": {"exchange": "ARCA", "currency": "USD", "sec_type": "STK"},
}

# ─────────────────────────────────────────────
# OPTIONS EXPIRATION
# Target: April 17, 2026 (monthly expiry, gives buffer past April 3 close)
# Adjust if this exact date isn't available in IBKR chain
# ─────────────────────────────────────────────
TARGET_EXPIRY = "20260417"    # YYYYMMDD format for ib_insync
BACKUP_EXPIRY = "20260424"    # Next weekly if monthly unavailable

# ─────────────────────────────────────────────
# STRATEGY 4: SLV vs USO VOLATILITY DISPERSION
# Long SLV straddle + Short USO strangle
# ─────────────────────────────────────────────
STRAT4_ENABLED = True
STRAT4_ALLOC_PCT = 0.25          # 25% of capital

# SLV long straddle (ATM)
STRAT4_SLV_CONTRACTS = 5         # Number of straddle units
STRAT4_SLV_STRIKE_OFFSET = 0     # 0 = ATM, +1 = $1 OTM, etc.

# USO short strangle (OTM)
STRAT4_USO_CONTRACTS = 5
STRAT4_USO_CALL_DELTA_TARGET = 0.25   # ~25 delta OTM calls
STRAT4_USO_PUT_DELTA_TARGET = -0.25   # ~25 delta OTM puts

# Entry signals
STRAT4_SLV_IV_PERCENTILE_MAX = 70    # Enter when SLV IV below 70th percentile
STRAT4_USO_IV_PERCENTILE_MIN = 60    # Enter when USO IV above 60th percentile
STRAT4_RSI_SLV_MAX = 55             # SLV not overbought (room to move)

# ─────────────────────────────────────────────
# STRATEGY 6: USO BEAR PUT SPREAD
# Buy ATM put, sell OTM put
# ─────────────────────────────────────────────
STRAT6_ENABLED = True
STRAT6_ALLOC_PCT = 0.20          # 20% of capital
STRAT6_CONTRACTS = 10
STRAT6_LONG_PUT_OFFSET = 0       # ATM or slightly OTM
STRAT6_SHORT_PUT_WIDTH = 5       # Spread width in dollars (e.g., $5 wide)

# Entry signals
STRAT6_USO_RSI_MIN = 55          # USO RSI above 55 (still overbought-ish)
STRAT6_USO_BB_POSITION_MIN = 0.6 # Price above 60% of Bollinger Band range
STRAT6_OIL_GEOPOLITICAL_FLAG = True  # Manual flag: is oil still war-premium?

# ─────────────────────────────────────────────
# STRATEGY 8: SLV/GLD RELATIVE VALUE
# Sell GLD OTM puts, buy SLV OTM calls
# ─────────────────────────────────────────────
STRAT8_ENABLED = True
STRAT8_ALLOC_PCT = 0.25          # 25% of capital

# GLD short puts
STRAT8_GLD_PUT_CONTRACTS = 3
STRAT8_GLD_PUT_DELTA_TARGET = -0.20  # ~20 delta (8-10% OTM)

# SLV long calls
STRAT8_SLV_CALL_CONTRACTS = 10
STRAT8_SLV_CALL_DELTA_TARGET = 0.35  # ~35 delta (moderate OTM)

# Entry signals — Gold/Silver ratio
STRAT8_GS_RATIO_ENTRY_MIN = 60       # Enter when G/S ratio > 60 (silver cheap)
STRAT8_GS_RATIO_EXIT_TARGET = 55     # Target exit when ratio compresses to 55
STRAT8_SLV_RSI_MAX = 50             # Silver not overbought at entry

# ─────────────────────────────────────────────
# TECHNICAL INDICATOR PARAMETERS
# ─────────────────────────────────────────────
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD_DEV = 2.0
IV_LOOKBACK_DAYS = 252    # 1 year for IV percentile rank
GS_RATIO_MA_PERIOD = 20   # Moving average for gold/silver ratio

# ─────────────────────────────────────────────
# SCHEDULING
# ─────────────────────────────────────────────
MARKET_OPEN = "09:30"     # ET
MARKET_CLOSE = "16:00"    # ET
SIGNAL_CHECK_INTERVAL_MIN = 15     # Check signals every 15 min
NAV_SNAPSHOT_TIME = "15:55"        # Record daily NAV 5 min before close

# ─────────────────────────────────────────────
# FILE PATHS
# ─────────────────────────────────────────────
TRADES_CSV = "data/trades.csv"
NAV_CSV = "data/daily_nav.csv"
SIGNALS_CSV = "data/signals.csv"
LOG_FILE = "logs/bot.log"
