# BU423 Hedge Fund Commodities Options Bot

> Automated options trading bot for the BU423 Hedge Fund Options Challenge.
> Connects to IBKR Paper Trading via TWS API. Local execution with Streamlit dashboard.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Your Laptop                                     │
│                                                   │
│  ┌──────────┐    TCP:7497    ┌──────────────┐    │
│  │ TWS Paper │◄─────────────►│  Trading Bot  │    │
│  │ Trading   │               │  (Python)     │    │
│  └──────────┘               └──────┬───────┘    │
│                                     │            │
│                              ┌──────▼───────┐    │
│                              │  Streamlit    │    │
│                              │  Dashboard    │    │
│                              │  localhost:   │    │
│                              │  8501         │    │
│                              └──────────────┘    │
│                                                   │
│  ┌──────────────────────────────────────────┐    │
│  │  GitHub Repo (version control + collab)   │    │
│  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/YOUR_USERNAME/aurum-contra-oleum.git
cd aurum-contra-oleum

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Open TWS Paper Trading (must be running before bot)
# Settings > API > Enable ActiveX and Socket Clients
# Settings > API > Socket port = 7497
# Settings > API > Uncheck "Read-Only API"

# 5. Run the bot (background)
python bot.py

# 6. Run the dashboard (separate terminal)
streamlit run dashboard.py
```

## Strategy Mapping to Requirements

| Requirement | Strategy | Implementation |
|-------------|----------|---------------|
| Req 1: ≥2 Underlyings | SLV + GLD + USO | 3 ETFs traded |
| Req 2a: Leveraged Directional | SLV Straddle (long vol) | `strategies/vol_dispersion.py` |
| Req 2b: Leveraged Directional | USO Bear Put Spread | `strategies/uso_bear_put.py` |
| Req 3: Cross-Asset RV | Sell GLD Puts → Buy SLV Calls + Short USO vol | `strategies/relative_value.py` |

## File Structure

```
aurum-contra-oleum/
├── README.md
├── SETUP_GUIDE.md          # Detailed step-by-step walkthrough
├── requirements.txt
├── config.py               # All configuration (strikes, sizes, thresholds)
├── bot.py                  # Main orchestrator — run this
├── dashboard.py            # Streamlit control panel — run this
├── strategies/
│   ├── __init__.py
│   ├── base.py             # Abstract strategy class
│   ├── vol_dispersion.py   # Strategy 4: Long SLV vol / Short USO vol
│   ├── uso_bear_put.py     # Strategy 6: USO bear put spread
│   └── relative_value.py   # Strategy 8: Sell GLD puts / Buy SLV calls
├── utils/
│   ├── __init__.py
│   ├── indicators.py       # RSI, Bollinger, IV percentile, G/S ratio
│   ├── risk_manager.py     # Position sizing, drawdown, stop-losses
│   ├── journal.py          # Trade journal CSV generation
│   └── nav_tracker.py      # Daily NAV/PnL recording
├── data/
│   ├── trades.csv          # Auto-generated trade log
│   ├── daily_nav.csv       # Auto-generated NAV series
│   └── signals.csv         # Signal history
├── logs/
│   └── bot.log             # Runtime logs
└── screenshots/            # IBKR confirmation screenshots (manual)
```

## Important Notes

- **This bot is a TOOL, not autopilot.** Review every signal before it executes.
- **IBKR paper trading uses simulated fills** — real spreads may differ.
- **All positions must be closed by April 3, 2026 EOD.**
- **Take IBKR screenshots** of every trade confirmation for the journal.
