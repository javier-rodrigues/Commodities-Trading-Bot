"""
Aurum Contra Oleum — Streamlit Dashboard
═════════════════════════════════════════
Local dashboard for monitoring positions, signals, NAV, and risk.
Run: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
import os
from datetime import datetime, date, timedelta

import config

st.set_page_config(
    page_title="Aurum Contra Oleum",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@400;600;700&display=swap');

    .stApp { background-color: #0a0e17; }
    h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; color: #e8c547; }
    .metric-card {
        background: linear-gradient(135deg, #111827 0%, #1a1f2e 100%);
        border: 1px solid #2d3748;
        border-radius: 12px;
        padding: 20px;
        margin: 8px 0;
    }
    .metric-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 28px;
        font-weight: 700;
        color: #e8c547;
    }
    .metric-label { color: #8892a4; font-size: 13px; text-transform: uppercase; }
    .positive { color: #10b981; }
    .negative { color: #ef4444; }
    .strat-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
    }
    .badge-vol { background: #1e3a5f; color: #60a5fa; border: 1px solid #3b82f6; }
    .badge-bear { background: #3b1f1f; color: #f87171; border: 1px solid #ef4444; }
    .badge-rv { background: #1a3a2a; color: #34d399; border: 1px solid #10b981; }
</style>
""", unsafe_allow_html=True)


def load_nav_data():
    if os.path.exists(config.NAV_CSV):
        df = pd.read_csv(config.NAV_CSV)
        if len(df) > 0:
            df["date"] = pd.to_datetime(df["date"])
        return df
    return pd.DataFrame()


def load_trade_data():
    if os.path.exists(config.TRADES_CSV):
        return pd.read_csv(config.TRADES_CSV)
    return pd.DataFrame()


def compute_performance_stats(df):
    """Compute all Section 6 statistics from NAV data."""
    if len(df) < 2:
        return {}

    returns = df["daily_return"].dropna()
    bench_returns = df["benchmark_return"].dropna()

    stats = {
        "cumulative_pnl": df["nav"].iloc[-1] - config.INITIAL_CAPITAL,
        "cumulative_return": (df["nav"].iloc[-1] - config.INITIAL_CAPITAL) / config.INITIAL_CAPITAL,
        "avg_daily_return": returns.mean(),
        "daily_vol": returns.std(),
        "annualized_return": returns.mean() * 252,
        "annualized_vol": returns.std() * np.sqrt(252),
        "bench_cumulative_return": df["benchmark_cumulative_return"].iloc[-1] if "benchmark_cumulative_return" in df else 0,
        "bench_avg_daily": bench_returns.mean() if len(bench_returns) > 0 else 0,
        "bench_daily_vol": bench_returns.std() if len(bench_returns) > 0 else 0,
    }

    # Sharpe (assume 0 risk-free for simplicity over 14 days)
    stats["sharpe"] = (
        stats["annualized_return"] / stats["annualized_vol"]
        if stats["annualized_vol"] > 0 else 0
    )

    # Max drawdown
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    stats["max_drawdown"] = drawdown.min()

    return stats


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("# ⚗️ Aurum Contra Oleum")
    st.markdown("*Gold Against Oil*")
    st.markdown("---")

    today = date.today()
    trading_day = (today - config.TRADING_START).days + 1
    total_days = (config.TRADING_END - config.TRADING_START).days + 1
    days_remaining = max(0, (config.TRADING_END - today).days)

    st.markdown(f"**Trading Day:** {trading_day} / {total_days}")
    st.progress(min(trading_day / total_days, 1.0))
    st.markdown(f"**Days Remaining:** {days_remaining}")
    st.markdown(f"**Force Close:** {config.FORCE_CLOSE_DATE.strftime('%b %d')}")

    st.markdown("---")
    st.markdown("### Strategy Status")

    strategies_status = {
        "Vol Dispersion (SLV/USO)": ("badge-vol", "Req 2 + 3"),
        "Bear Put Spread (USO)": ("badge-bear", "Req 2"),
        "Relative Value (SLV/GLD)": ("badge-rv", "Req 3"),
    }
    for name, (badge, req) in strategies_status.items():
        st.markdown(
            f'<span class="strat-badge {badge}">{req}</span> {name}',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("### Bot Commands")
    st.code("python bot.py              # Signals only", language="bash")
    st.code("python bot.py --execute    # Place orders", language="bash")
    st.code("python bot.py --nav-snapshot  # Record NAV", language="bash")
    st.code("python bot.py --loop       # Auto-check", language="bash")


# ─────────────────────────────────────────────
# MAIN CONTENT
# ─────────────────────────────────────────────
st.markdown("# ⚗️ Aurum Contra Oleum — Trading Dashboard")
st.markdown("*BU423 Hedge Fund Options Challenge | March 16 – April 3, 2026*")

# ── TOP METRICS ROW ──
nav_df = load_nav_data()

col1, col2, col3, col4, col5 = st.columns(5)

if len(nav_df) > 0:
    stats = compute_performance_stats(nav_df)
    current_nav = nav_df["nav"].iloc[-1]
    cum_pnl = stats.get("cumulative_pnl", 0)
    cum_ret = stats.get("cumulative_return", 0)
    sharpe = stats.get("sharpe", 0)
    mdd = stats.get("max_drawdown", 0)

    with col1:
        color = "positive" if cum_pnl >= 0 else "negative"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Net Asset Value</div>
            <div class="metric-value">${current_nav:,.0f}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Cumulative P&L</div>
            <div class="metric-value {color}">${cum_pnl:+,.0f}</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Total Return</div>
            <div class="metric-value {color}">{cum_ret:+.2%}</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Sharpe Ratio</div>
            <div class="metric-value">{sharpe:.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    with col5:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Max Drawdown</div>
            <div class="metric-value negative">{mdd:.2%}</div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info(
        "No NAV data yet. Run `python bot.py --nav-snapshot` at market close "
        "to begin recording your daily return series."
    )

st.markdown("---")

# ── CHARTS ──
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Performance", "📊 Trade Journal", "🎯 Signals", "📋 Section 6 Stats"
])

with tab1:
    if len(nav_df) > 0:
        # Cumulative return chart (Fund vs Benchmark)
        fig = make_subplots(
            rows=2, cols=1, row_heights=[0.7, 0.3],
            shared_xaxes=True, vertical_spacing=0.08,
            subplot_titles=("Cumulative Returns: Fund vs Benchmark (GLD)",
                            "Drawdown")
        )

        fig.add_trace(
            go.Scatter(
                x=nav_df["date"], y=nav_df["cumulative_return"] * 100,
                name="Fund", line=dict(color="#e8c547", width=2.5),
                fill="tozeroy", fillcolor="rgba(232,197,71,0.1)",
            ), row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=nav_df["date"], y=nav_df["benchmark_cumulative_return"] * 100,
                name="Benchmark (GLD)", line=dict(color="#60a5fa", width=2, dash="dot"),
            ), row=1, col=1
        )

        # Drawdown chart
        returns = nav_df["daily_return"]
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = ((cumulative - running_max) / running_max) * 100

        fig.add_trace(
            go.Scatter(
                x=nav_df["date"], y=drawdown,
                name="Drawdown", line=dict(color="#ef4444", width=1.5),
                fill="tozeroy", fillcolor="rgba(239,68,68,0.2)",
            ), row=2, col=1
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0a0e17",
            plot_bgcolor="#111827",
            height=550,
            font=dict(family="JetBrains Mono", color="#8892a4"),
            legend=dict(x=0.02, y=0.98),
        )
        fig.update_yaxes(title_text="Return (%)", row=1, col=1)
        fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Performance chart will appear once NAV data is recorded.")

with tab2:
    trades_df = load_trade_data()
    if len(trades_df) > 0:
        st.dataframe(
            trades_df,
            use_container_width=True,
            height=400,
        )

        # Summary by strategy
        if "realized_pnl" in trades_df.columns:
            pnl_by_strat = trades_df.groupby("strategy")["realized_pnl"].sum()
            st.markdown("### P&L by Strategy")
            for strat, pnl in pnl_by_strat.items():
                color = "🟢" if pnl > 0 else "🔴"
                st.markdown(f"{color} **{strat}**: ${pnl:+,.2f}")

        # Export button
        if st.button("📥 Export Trade Journal to Excel"):
            from utils.journal import TradeJournal
            journal = TradeJournal()
            path = journal.export_to_excel()
            st.success(f"Exported to {path}")
    else:
        st.info("No trades recorded yet. Trades appear after running `python bot.py --execute`.")

with tab3:
    st.markdown("### Current Signal State")
    st.markdown(
        "These indicators are evaluated each time the bot runs. "
        "Values update when you run `python bot.py`."
    )

    # Display signal config as reference
    sig_col1, sig_col2, sig_col3 = st.columns(3)

    with sig_col1:
        st.markdown("#### 🌊 Vol Dispersion (Strat 4)")
        st.markdown(f"- SLV IV Pct Max: **{config.STRAT4_SLV_IV_PERCENTILE_MAX}**")
        st.markdown(f"- USO IV Pct Min: **{config.STRAT4_USO_IV_PERCENTILE_MIN}**")
        st.markdown(f"- SLV RSI Max: **{config.STRAT4_RSI_SLV_MAX}**")
        st.markdown(f"- SLV Contracts: **{config.STRAT4_SLV_CONTRACTS}**")
        st.markdown(f"- USO Contracts: **{config.STRAT4_USO_CONTRACTS}**")

    with sig_col2:
        st.markdown("#### 🐻 USO Bear Put (Strat 6)")
        st.markdown(f"- USO RSI Min: **{config.STRAT6_USO_RSI_MIN}**")
        st.markdown(f"- USO BB %B Min: **{config.STRAT6_USO_BB_POSITION_MIN}**")
        st.markdown(f"- Contracts: **{config.STRAT6_CONTRACTS}**")
        st.markdown(f"- Spread Width: **${config.STRAT6_SHORT_PUT_WIDTH}**")

    with sig_col3:
        st.markdown("#### 🔄 Relative Value (Strat 8)")
        st.markdown(f"- G/S Ratio Entry: **>{config.STRAT8_GS_RATIO_ENTRY_MIN}**")
        st.markdown(f"- G/S Ratio Exit: **<{config.STRAT8_GS_RATIO_EXIT_TARGET}**")
        st.markdown(f"- SLV RSI Max: **{config.STRAT8_SLV_RSI_MAX}**")
        st.markdown(f"- GLD Put δ: **{config.STRAT8_GLD_PUT_DELTA_TARGET}**")
        st.markdown(f"- SLV Call δ: **{config.STRAT8_SLV_CALL_DELTA_TARGET}**")

    if os.path.exists(config.SIGNALS_CSV):
        sig_df = pd.read_csv(config.SIGNALS_CSV)
        st.dataframe(sig_df.tail(20), use_container_width=True)

with tab4:
    st.markdown("### Section 6: Performance Analysis (auto-computed from NAV data)")

    if len(nav_df) > 1:
        stats = compute_performance_stats(nav_df)

        # Summary table matching Section 6.1 format
        summary_data = {
            "Metric": [
                "Cumulative P&L ($)",
                "Cumulative Return (%)",
                "Avg Daily Return",
                "Daily Return Volatility",
                "Annualized Return",
                "Annualized Volatility",
                "Sharpe Ratio",
                "Maximum Drawdown",
            ],
            "Fund": [
                f"${stats['cumulative_pnl']:+,.2f}",
                f"{stats['cumulative_return']:+.4%}",
                f"{stats['avg_daily_return']:.6f}",
                f"{stats['daily_vol']:.6f}",
                f"{stats['annualized_return']:.4%}",
                f"{stats['annualized_vol']:.4%}",
                f"{stats['sharpe']:.4f}",
                f"{stats['max_drawdown']:.4%}",
            ],
            "Benchmark (GLD)": [
                f"—",
                f"{stats['bench_cumulative_return']:.4%}",
                f"{stats['bench_avg_daily']:.6f}",
                f"{stats['bench_daily_vol']:.6f}",
                f"{stats['bench_avg_daily'] * 252:.4%}",
                f"{stats['bench_daily_vol'] * np.sqrt(252):.4%}",
                f"{stats['bench_avg_daily'] * 252 / (stats['bench_daily_vol'] * np.sqrt(252)) if stats['bench_daily_vol'] > 0 else 0:.4f}",
                f"—",
            ],
        }
        st.table(pd.DataFrame(summary_data))

        st.markdown("### Section 6.2: Alpha/Beta Regression")
        if len(nav_df) > 3:
            from scipy import stats as scipy_stats
            fund_r = nav_df["daily_return"].dropna().values
            bench_r = nav_df["benchmark_return"].dropna().values
            n = min(len(fund_r), len(bench_r))
            if n > 2:
                slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(
                    bench_r[:n], fund_r[:n]
                )
                st.markdown(f"- **Alpha (daily):** {intercept:.6f} (annualized: {intercept * 252:.4%})")
                st.markdown(f"- **Beta:** {slope:.4f} (SE: {std_err:.4f})")
                st.markdown(f"- **R-squared:** {r_value**2:.4f}")
                st.markdown(f"- **p-value (beta):** {p_value:.4f}")

                st.markdown(
                    f"\n*Note: With ~{n} observations, statistical significance is limited. "
                    f"Interpret with appropriate caution per assignment guidance (Section 6.2).*"
                )

        st.markdown("---")
        st.info(
            "⚠️ Reminder: With ~14 trading days, your return series will be short. "
            "The assignment explicitly states: 'Be candid about the limitations this "
            "imposes on statistical estimates. Acknowledging and discussing these "
            "limitations is a sign of rigour, not weakness.'"
        )
    else:
        st.info("Need at least 2 days of NAV data for performance statistics.")


# ── FOOTER ──
st.markdown("---")
st.markdown(
    '<p style="color: #4a5568; font-size: 12px; text-align: center;">'
    "Aurum Contra Oleum Capital | BU423 Winter 2026 | "
    "Built with ib_insync + Streamlit | "
    "AI tools (Claude/Anthropic) used per course policy"
    "</p>",
    unsafe_allow_html=True,
)
