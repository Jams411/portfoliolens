"""Streamlit entrypoint for PortfolioLens."""
from __future__ import annotations

from datetime import date
from html import escape
import os
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from portfolio_dashboard.asset_pricing import capm_security_table, security_market_line
from portfolio_dashboard.config import PRESETS, TRADING_DAYS
from portfolio_dashboard.construction import (
    capital_allocation_line, constrained_portfolio_weights, constraint_validation_summary,
    complete_portfolio_statistics, complete_portfolio_weights, efficient_frontier,
    optimization_diagnostics, optimizer_statistics, parse_group_caps, target_return_weights,
    utility_optimal_complete_portfolio,
)
from portfolio_dashboard.data import (
    InputError, MarketDataError, allocation_percentages,
    download_prices, normalize_allocation, parse_allocation_values, parse_tickers,
    reconciled_allocation_percentages, resolve_benchmark_ticker, validate_dates,
)
from portfolio_dashboard.formatting import metric_value, money, pct, ratio
from portfolio_dashboard.fixed_income_ui import render_fixed_income_workspace
from portfolio_dashboard.evaluation import (
    fama_selectivity_decomposition, rolling_performance_evaluation,
)
from portfolio_dashboard.etf_research import (
    consolidated_security_exposure, etf_overlap, etf_research_metrics,
    filter_etf_research, holdings_coverage, parse_holdings_csv, rank_security_candidates,
)
from portfolio_dashboard.performance import (
    annualized_volatility, asset_risk_return_table, diversification_effect,
    drawdown_series, monthly_returns, normalized_holding_performance,
)
from portfolio_dashboard.pipeline import run_analysis
from portfolio_dashboard.rebalancing import compare_rebalancing_policies, rebalancing_plan
from portfolio_dashboard.reporting import generate_html_report, research_summary
from portfolio_dashboard.research import (
    deterministic_insights, portfolio_comparison, portfolio_health_score, what_if_analysis,
)
from portfolio_dashboard.risk import (
    historical_cvar, historical_var, security_single_index_table,
    single_index_regression_diagnostics,
)
from portfolio_dashboard.strategy import optional_momentum_analysis
from portfolio_dashboard.stress import custom_shock, historical_stress

st.set_page_config(page_title="PortfolioLens", page_icon=":material/analytics:", layout="wide")

SIMPLE_CHART_HEIGHT = 400
COMPLEX_CHART_HEIGHT = 440

PLOTLY_CONFIG = {
    "responsive": True,
    "displaylogo": False,
    "displayModeBar": True,
    "modeBarButtonsToRemove": [
        "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
        "autoScale2d", "toggleSpikelines",
    ],
    "toImageButtonOptions": {"format": "png", "filename": "portfoliolens_chart", "scale": 2},
}

RESPONSIVE_LAYOUT_CSS = """
<style>
[data-testid="stMainBlockContainer"],
[data-testid="stMain"] {
    max-width: 100%;
}
[data-testid="stMainBlockContainer"] {
    padding-top: 2.25rem !important;
}
[data-testid="stPlotlyChart"],
[data-testid="stPlotlyChart"] > div,
[data-testid="stPlotlyChart"] .js-plotly-plot,
[data-testid="stPlotlyChart"] .plot-container {
    width: 100% !important;
    max-width: 100% !important;
}
[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: auto;
    overscroll-behavior-inline: contain;
}
/* Keep the two primary actions in view while the sidebar scrolls. The
   container remains in normal flow, so it never obscures another control. */
[data-testid="stSidebar"] .st-key-primary-actions {
    position: sticky;
    bottom: 0;
    z-index: 20;
    margin: 0;
    padding: 0.05rem 0 0.1rem;
    background: transparent;
    border: 0;
}
[data-testid="stSidebar"] .st-key-primary-actions [data-testid="stHorizontalBlock"] {
    gap: 0.4rem;
}
/* Keep the date pair aligned with the other compact sidebar controls. */
[data-testid="stSidebar"] .st-key-analysis-period [data-testid="stDateInput"] {
    margin: 0 !important;
}
[data-testid="stSidebar"] .st-key-analysis-period [data-testid="stDateInput"] [data-baseweb="input"] {
    min-height: 2.25rem !important;
    height: 2.25rem !important;
}
[data-testid="stSidebar"] .st-key-analysis-period [data-testid="stDateInput"] input {
    padding-top: 0.25rem !important;
    padding-bottom: 0.25rem !important;
}
/* Reclaim modest vertical space in the sidebar while keeping controls at
   their normal size and preserving regular scrolling on narrow screens. */
[data-testid="stSidebar"] [data-testid="stExpander"] {
    margin-top: -0.1rem;
    margin-bottom: -0.1rem;
}
[data-testid="stSidebar"] .st-key-allocation-status {
    display: block;
    text-align: left;
    width: 100%;
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] .st-key-allocation-status [data-testid="stAlert"],
[data-testid="stSidebar"] .st-key-allocation-status [data-testid="stAlert"] > div {
    box-sizing: border-box;
    display: block;
    text-align: left;
    width: 100%;
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    border: 0 !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    font-size: 13px;
    line-height: 1.2;
    overflow: visible;
}
[data-testid="stSidebar"] .st-key-allocation-status [data-testid="stAlert"]::before,
[data-testid="stSidebar"] .st-key-allocation-status [data-testid="stAlert"]::after {
    display: none !important;
    content: none !important;
}
[data-testid="stSidebar"] .st-key-allocation-status [data-testid="stMarkdownContainer"] {
    display: block;
    width: 100%;
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] .st-key-allocation-status [data-testid="stAlert"] p {
    margin: 0 !important;
    text-align: left;
}
[data-testid="stSidebar"] .st-key-allocation-status [data-testid="stAlert"] svg {
    display: none !important;
}
@media (max-width: 700px) {
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {
        max-width: 100vw;
        overflow-x: clip;
    }
    [data-testid="stMainBlockContainer"] {
        width: 100%;
        max-width: 100%;
        padding: 2.75rem 0.75rem 3rem !important;
    }
    [data-testid="stVerticalBlock"] {
        gap: 0.75rem;
    }
    [data-testid="stPlotlyChart"] {
        margin-inline: 0 !important;
        overflow: hidden;
    }
    [data-testid="stPlotlyChart"] .modebar {
        top: 2.7rem !important;
        right: 0.2rem !important;
    }
    [data-testid="stDataFrame"],
    [data-testid="stDataEditor"] {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }
    h1 { font-size: 2.15rem !important; }
    h2 { font-size: 1.65rem !important; }
    h3 { font-size: 1.35rem !important; }
}
@media (max-width: 430px) {
    [data-testid="stMainBlockContainer"] {
        padding-inline: 0.625rem !important;
    }
}
</style>
"""

FOOTER_HTML = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap');
.portfolio-footer {
    width: 100%;
    margin-top: 1rem;
    padding: 14px 8px;
    border-top: 1px solid rgba(148, 163, 184, 0.24);
    color: rgba(226, 232, 240, 0.68);
    font-family: 'Poppins', sans-serif;
    font-size: clamp(12px, 1vw, 13px);
    font-weight: 400;
    line-height: 1.35;
    text-align: center;
    box-sizing: border-box;
}
.portfolio-footer a {
    color: inherit;
    text-decoration: none;
}
.portfolio-footer a:hover,
.portfolio-footer a:focus-visible {
    color: rgba(226, 232, 240, 0.92);
    text-decoration: underline;
    text-underline-offset: 2px;
}
.portfolio-footer a:focus-visible {
    outline: 2px solid #60a5fa;
    outline-offset: 3px;
}
.portfolio-footer__developer { font-weight: 400; }
.portfolio-footer__partner { font-weight: 600; }
</style>
<footer class="portfolio-footer" aria-label="PortfolioLens credits">
    <span class="portfolio-footer__developer">Developed by
        <a href="https://github.com/Jams411" target="_blank" rel="noopener noreferrer">Jameel Shaikh</a>
    </span>
    <span aria-hidden="true"> • </span>
    <a class="portfolio-footer__partner" href="https://outpartners.org/"
       target="_blank" rel="noopener noreferrer">OUT PARTNERS</a>
</footer>
"""

DASHBOARD_METRIC_GRID_CSS = """
<style>
.financial-metric-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    width: 100%;
    margin: 0 0 0.3rem;
}
.financial-metric-card {
    --metric-accent: #64748b;
    flex: 1 1 8.625rem;
    min-width: min(100%, 8.625rem);
    height: 6rem;
    padding: 0.3rem 0.75rem 0.25rem;
    border: 1px solid #334155;
    border-top: 3px solid var(--metric-accent);
    border-radius: 0.55rem;
    background: #111b2e;
    color: #f1f5f9;
    box-sizing: border-box;
}
.financial-metric-card:hover {
    border-color: #475569;
    background: #162033;
}
.financial-metric-card:focus-visible {
    outline: 2px solid #60a5fa;
    outline-offset: 2px;
}
.financial-metric-card--primary { --metric-accent: #60a5fa; }
.financial-metric-card--positive { --metric-accent: #34d399; }
.financial-metric-card--negative { --metric-accent: #f87171; }
.financial-metric-card--warning { --metric-accent: #fbbf24; }
.financial-metric-card__label {
    min-height: 2em;
    color: #cbd5e1;
    font-size: 0.8rem;
    font-weight: 600;
    line-height: 1rem;
}
.financial-metric-card__value {
    margin-top: 0.08rem;
    color: #f8fafc;
    font-size: clamp(1.35rem, 2vw, 1.85rem);
    font-weight: 600;
    line-height: 1;
    white-space: nowrap;
}
.financial-metric-card--positive .financial-metric-card__value { color: #6ee7b7; }
.financial-metric-card--negative .financial-metric-card__value { color: #fca5a5; }
.financial-metric-card__context {
    margin-top: 0.15rem;
    color: #94a3b8;
    font-size: 0.72rem;
    line-height: 0.95rem;
}
.financial-metric-card__context--positive { color: #6ee7b7; }
.financial-metric-card__context--negative { color: #fca5a5; }
@media (max-width: 700px) {
    .financial-metric-card {
        flex-basis: calc(50% - 0.35rem);
        min-width: min(100%, 8.25rem);
    }
}
@media (min-width: 701px) and (max-width: 900px) {
    .financial-metric-card { flex-basis: calc(33.333% - 0.5rem); }
}
@media (min-width: 901px) and (max-width: 1200px) {
    .financial-metric-grid--secondary .financial-metric-card { flex-basis: 12rem; }
}
@media (max-width: 420px) {
    .financial-metric-card { flex-basis: 100%; }
}
</style>
"""

@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def cached_prices(tickers: tuple[str, ...], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return download_prices(tickers, start, end)


def metric_frame(values: dict[str, float]) -> pd.DataFrame:
    """Return a numeric metric table suitable for export and reporting."""
    return pd.DataFrame({"Metric": list(values), "Value": list(values.values())}).set_index("Metric")


def display_metric_frame(values: dict[str, float]) -> pd.DataFrame:
    """Return a metric table with units selected by metric identity."""
    formatted = [metric_value(name, value) for name, value in values.items()]
    return pd.DataFrame({"Metric": list(values), "Value": formatted}).set_index("Metric")


def percent_table(frame: pd.DataFrame) -> pd.io.formats.style.Styler:
    return frame.style.format("{:.2%}", na_rep="—")


def compact_money(value: float) -> str:
    """Format an executive-card value to remain readable at laptop widths."""
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.1f}B"
    if magnitude >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if magnitude >= 1_000:
        return f"${value / 1_000:,.0f}K"
    return f"${value:,.0f}"


def compact_pct(value: float) -> str:
    """Format a dashboard percentage without crowding compact metric cards."""
    return f"{value:.1%}"


def compact_signed_money(value: float) -> str:
    """Format a signed currency change for concise, verified card context."""
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}{compact_money(abs(value))}"


def dashboard_metric_tone(label: str, value: float | None = None) -> str:
    """Return a restrained semantic tone only for directionally meaningful metrics."""
    if label == "Portfolio value":
        return "primary"
    if label == "Maximum drawdown":
        return "negative" if value is not None and value < 0 else "neutral"
    if label in {"Total return", "CAGR", "Sharpe ratio", "Information ratio", "Relative benchmark result"}:
        if value is not None and value > 0:
            return "positive"
        if value is not None and value < 0:
            return "negative"
    return "neutral"


def dashboard_metric_grid(cards: list[dict[str, object]], group_label: str, variant: str) -> None:
    """Render a responsive, accessible dashboard metric row without placeholder cards."""
    articles = []
    for card in cards:
        label = escape(str(card["label"]))
        value = escape(str(card["value"]))
        context = escape(str(card.get("context", "")))
        tone = str(card.get("tone", "neutral"))
        context_tone = str(card.get("context_tone", "neutral"))
        context_class = (
            f" financial-metric-card__context--{context_tone}"
            if context_tone in {"positive", "negative"}
            else ""
        )
        articles.append(
            f'<article class="financial-metric-card financial-metric-card--{tone}" '
            f'role="listitem" tabindex="0" aria-label="{label}: {value}">'
            f'<div class="financial-metric-card__label">{label}</div>'
            f'<div class="financial-metric-card__value">{value}</div>'
            f'<div class="financial-metric-card__context{context_class}">{context}</div>'
            "</article>"
        )
    st.html(
        f'<section class="financial-metric-grid financial-metric-grid--{escape(variant)}" '
        f'role="list" aria-label="{escape(group_label)}">'
        + "".join(articles)
        + "</section>",
        width="stretch",
    )


def render_footer() -> None:
    """Render the shared lightweight product footer."""
    st.html(FOOTER_HTML)


def render_plotly_chart(
    figure: go.Figure,
    *,
    complex_chart: bool = False,
    show_legend: bool = True,
    responsive_legend: bool = False,
) -> None:
    """Apply one responsive chart contract before rendering a Plotly figure."""
    height = COMPLEX_CHART_HEIGHT if complex_chart else SIMPLE_CHART_HEIGHT
    mobile = _mobile_client() if responsive_legend else False
    bottom_margin = (
        96 if show_legend and responsive_legend and mobile
        else 40 if show_legend and responsive_legend
        else 112 if show_legend and complex_chart
        else 88 if show_legend
        else 56
    )
    figure.update_layout(
        autosize=True,
        height=height,
        showlegend=show_legend,
        legend_title_text="Holding" if responsive_legend else "",
        margin=dict(l=44, r=12 if mobile else 152 if responsive_legend else 10, t=78, b=bottom_margin),
        title=dict(font=dict(size=17), x=0, xanchor="left", y=0.98, yanchor="top"),
        legend=dict(
            orientation="h" if mobile or not responsive_legend else "v",
            yanchor="top" if mobile or responsive_legend else "top",
            y=-0.18 if mobile or not responsive_legend else 1,
            xanchor="left",
            x=0 if mobile or not responsive_legend else 1.02,
            font=dict(size=10),
        ),
        font=dict(size=11),
    )
    figure.update_xaxes(
        automargin=True,
        title_font=dict(size=12),
        tickfont=dict(size=10),
    )
    figure.update_yaxes(
        automargin=True,
        title_font=dict(size=12),
        tickfont=dict(size=10),
    )
    st.plotly_chart(
        figure,
        width="stretch",
        theme="streamlit",
        config=PLOTLY_CONFIG,
    )


def line_chart(
    frame: pd.DataFrame,
    title: str,
    y_title: str,
    colors: list[str] | None = None,
) -> None:
    fig = px.line(
        frame,
        title=title,
        labels={"value": y_title, "index": "Date", "variable": "Series"},
        color_discrete_sequence=colors,
    )
    fig.update_layout(hovermode="x unified")
    render_plotly_chart(fig)


def _mobile_client() -> bool:
    """Use a compact Plotly legend when the browser identifies as mobile."""
    try:
        user_agent = st.context.headers.get("User-Agent", "")
    except Exception:
        user_agent = ""
    return any(token in user_agent for token in ("Android", "iPhone", "iPad", "Mobile"))


def normalized_holding_chart(
    normalized: pd.DataFrame,
    benchmark_label: str | None = None,
    *,
    log_scale: bool = False,
) -> None:
    """Render the common-start holding comparison with a responsive legend."""
    fig = go.Figure()
    palette = px.colors.qualitative.Safe
    holding_columns = [column for column in normalized.columns if column != benchmark_label]
    for position, column in enumerate(holding_columns):
        values = normalized[column]
        fig.add_trace(go.Scatter(
            x=normalized.index,
            y=values,
            mode="lines",
            name=str(column),
            line=dict(color=palette[position % len(palette)], width=2),
            customdata=(values - 1.0).to_numpy()[:, None],
            hovertemplate=(
                "Date: %{x|%Y-%m-%d}<br>Holding: " + str(column)
                + "<br>Growth of $1: %{y:.4f}<br>Cumulative change: %{customdata[0]:.2%}<extra></extra>"
            ),
        ))
    if benchmark_label and benchmark_label in normalized:
        values = normalized[benchmark_label]
        fig.add_trace(go.Scatter(
            x=normalized.index,
            y=values,
            mode="lines",
            name=str(benchmark_label),
            line=dict(color="#CBD5E1", width=2, dash="dash"),
            customdata=(values - 1.0).to_numpy()[:, None],
            hovertemplate=(
                "Date: %{x|%Y-%m-%d}<br>Benchmark: " + str(benchmark_label)
                + "<br>Growth of $1: %{y:.4f}<br>Cumulative change: %{customdata[0]:.2%}<extra></extra>"
            ),
        ))
    fig.add_hline(y=1.0, line_dash="dot", line_color="#94A3B8", annotation_text="Start = 1.00")
    mobile = _mobile_client()
    fig.update_layout(
        title="Normalized performance by holding",
        autosize=True,
        height=420,
        hovermode="x unified",
        legend_title_text="Holding",
        legend=(
            dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0, font=dict(size=10))
            if mobile else
            dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02, font=dict(size=10))
        ),
        margin=dict(l=52, r=12 if mobile else 152, t=78, b=96 if mobile else 40),
        font=dict(size=11),
    )
    fig.update_xaxes(title="Date", automargin=True)
    fig.update_yaxes(title="Growth of $1", type="log" if log_scale else "linear", automargin=True)
    render_plotly_chart(fig, complex_chart=True, responsive_legend=True)


@st.cache_data(show_spinner=False)
def build_identifier() -> str:
    """Return the deployed source revision without requiring a build-time secret."""
    for variable in ("STREAMLIT_GIT_COMMIT", "COMMIT_SHA", "GITHUB_SHA"):
        value = os.environ.get(variable, "").strip()
        if value:
            return value[:12]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


ANALYSIS_STATE_KEYS = (
    "result", "current_shocks", "selected_target_method", "normalized", "analysis_tab", "shock_editor",
    "what_if_weights", "what_if_shocks", "what_if_result", "what_if_weight_editor", "what_if_shock_editor",
    "target_return_result",
    "selected_rebalancing_policy",
    "constrained_result", "constraint_editor",
)

PRIMARY_WORKSPACES = (
    "Dashboard", "Analytics", "Research", "Portfolio Construction", "Strategies", "Reports",
)

WORKSPACE_SECTIONS = {
    "Dashboard": ("Dashboard",),
    "Analytics": (
        "Performance", "Performance Evaluation", "Risk", "Benchmark & Attribution", "Stress Testing",
    ),
    "Research": ("Security Analysis", "Asset Pricing", "ETF Research", "Fixed Income"),
    "Portfolio Construction": ("Portfolio Optimization & Rebalancing", "Asset Allocation"),
    "Strategies": ("Portfolio Strategies & Momentum",),
    "Reports": ("Research Workspace", "Research Report", "Methodology & Limitations"),
}

SECTION_TO_WORKSPACE = {
    section: workspace
    for workspace, sections in WORKSPACE_SECTIONS.items()
    for section in sections
}


def clear_analysis_state() -> None:
    """Remove outputs whose inputs no longer match the current widget values."""
    for key in ANALYSIS_STATE_KEYS:
        st.session_state.pop(key, None)


def apply_normalized_allocation(tickers: list[str], values: list[float]) -> None:
    """Store an explicit proportional normalization for the next UI rerun."""
    weights = normalize_allocation(tickers, values)
    percentages = reconciled_allocation_percentages(weights.to_numpy() * 100.0)
    st.session_state["normalized_allocation_text"] = ", ".join(
        f"{value:.2f}" for value in percentages
    )
    clear_analysis_state()


st.html(RESPONSIVE_LAYOUT_CSS)

with st.container(gap="xxsmall"):
    st.title("PortfolioLens")
    st.caption("Multi-asset portfolio analytics and investment research")

with st.sidebar:
    st.subheader("Analysis setup")
    with st.container(gap="xxsmall"):
        st.markdown("**Portfolio**")
        preset = st.selectbox("Portfolio preset", ["Custom"] + list(PRESETS), on_change=clear_analysis_state)
        default_tickers, default_weights = PRESETS.get(preset, ("SPY, AGG, GLD", "50, 35, 15"))
        ticker_text = st.text_input(
            "Portfolio tickers", value=default_tickers, help="Comma-separated; duplicates are removed.",
            on_change=clear_analysis_state,
        )
        equal = st.checkbox("Split equally across investments", value=False, on_change=clear_analysis_state)
        allocation_value = st.session_state.pop("normalized_allocation_text", default_weights)
        weight_text = st.text_input(
            "Portfolio allocation (%)", value=allocation_value, disabled=equal,
            help="Enter one percentage for each ticker. The total must equal 100%.",
            on_change=clear_analysis_state,
        )
        try:
            preview_tickers = parse_tickers(ticker_text)
        except (InputError, ValueError):
            preview_tickers = []

        allocation_values: list[float] = []
        allocation_percent_values = np.array([], dtype=float)
        allocation_error: str | None = None
        if equal and preview_tickers:
            equal_values = np.repeat(1.0 / len(preview_tickers), len(preview_tickers))
            allocation_percent_values = reconciled_allocation_percentages(
                equal_values * 100.0
            )
            allocation_values = equal_values.tolist()
        elif not equal:
            try:
                allocation_values = parse_allocation_values(weight_text)
                allocation_percent_values = allocation_percentages(allocation_values)
            except InputError as exc:
                allocation_error = str(exc)

        allocation_ready = bool(preview_tickers) and not allocation_error
        normalize_candidate = False
        if allocation_ready:
            if len(allocation_values) != len(preview_tickers):
                allocation_error = (
                    f"You entered {len(allocation_values)} allocation values for "
                    f"{len(preview_tickers)} investments. Add one percentage for each ticker."
                )
                allocation_ready = False
            elif (allocation_percent_values < 0).any():
                allocation_error = "Allocation values cannot be negative. Enter zero or a positive percentage for each ticker."
                allocation_ready = False
            elif not np.isfinite(allocation_percent_values).all():
                allocation_error = "Allocation values must be numeric and finite."
                allocation_ready = False
            elif allocation_percent_values.sum() <= 0:
                allocation_error = "At least one allocation must be positive; all-zero allocations cannot be analyzed."
                allocation_ready = False
            else:
                total_allocation = float(allocation_percent_values.sum())
                normalize_candidate = (
                    not equal
                    and (allocation_percent_values > 0).all()
                    and not np.isclose(total_allocation, 100.0, atol=1e-8)
                )
                def status_percent(value: float) -> str:
                    return f"{value:.2f}".rstrip("0").rstrip(".")

                with st.container(key="allocation-status", gap=None):
                    if np.isclose(total_allocation, 100.0, atol=1e-8):
                        st.success(f"Total allocation: {status_percent(total_allocation)}% ✓")
                    elif total_allocation < 100.0:
                        allocation_ready = False
                        st.warning(
                            f"Total allocation: {status_percent(total_allocation)}% · "
                            f"{status_percent(100.0 - total_allocation)}% remaining"
                        )
                    else:
                        allocation_ready = False
                        st.error(
                            f"Total allocation: {status_percent(total_allocation)}% · "
                            f"Reduce by {status_percent(total_allocation - 100.0)}%"
                        )
        if allocation_error:
            st.error(allocation_error)
        if equal and preview_tickers:
            equal_display = ", ".join(
                f"{ticker} {value:.2f}%"
                for ticker, value in zip(preview_tickers, allocation_percent_values)
            )
            st.caption(f"Calculated allocation: {equal_display}")
        if normalize_candidate:
            st.button(
                "Normalize to 100%",
                help="Adjust positive allocations proportionally while preserving their relative proportions.",
                on_click=apply_normalized_allocation,
                args=(preview_tickers, allocation_values),
                width="stretch",
            )
    with st.container(key="primary-actions", gap="xxsmall"):
        action_columns = st.columns([2, 1], gap="small")
        run = action_columns[0].button("Run analysis", type="primary", width="stretch", disabled=not allocation_ready)
        if action_columns[1].button("Reset", width="stretch"):
            st.session_state.clear()
            st.rerun()
    with st.container(key="analysis-period", gap="xxsmall"):
        st.markdown("**Analysis period**")
        period_columns = st.columns(2, gap="small")
        start_input = period_columns[0].date_input(
            "Start date", date(2018, 1, 1), on_change=clear_analysis_state,
        )
        end_input = period_columns[1].date_input(
            "End date", date.today(), on_change=clear_analysis_state,
        )
    with st.container(gap="xxsmall"):
        benchmark_ticker = st.text_input(
            "Benchmark", "SPX",
            help="Enter one ticker or supported index alias, such as SPX, DJIA, NASDAQ, VIX, or RUT.",
            on_change=clear_analysis_state,
        )
    with st.expander("Advanced assumptions", icon=":material/tune:"):
        initial_value = st.number_input(
            "Initial portfolio value", min_value=1.0, value=100000.0, step=5000.0,
            on_change=clear_analysis_state,
        )
        risk_free = st.number_input(
            "Annual risk-free rate (%)", min_value=-99.0, max_value=100.0, value=4.0, step=0.1,
            on_change=clear_analysis_state,
        ) / 100
    with st.expander("Implementation", icon=":material/tune:"):
        transaction_cost = st.number_input(
            "Transaction cost rate (%)", min_value=0.0, max_value=10.0, value=0.10, step=0.05,
            help="Applied proportionally to strategy position changes and rebalancing gross trade notional.",
            on_change=clear_analysis_state,
        ) / 100
        rebalancing_threshold = st.number_input(
            "Rebalancing drift threshold (%)", min_value=0.0, max_value=100.0, value=5.0, step=0.5,
            help="Threshold policy trades when any holding's absolute weight drift reaches this level.",
            on_change=clear_analysis_state,
        ) / 100
    with st.expander("Strategy settings", icon=":material/show_chart:"):
        short_window = st.number_input("Short moving average", 2, 500, 50, on_change=clear_analysis_state)
        long_window = st.number_input("Long moving average", 3, 1000, 200, on_change=clear_analysis_state)
    if len(pd.bdate_range(start_input, end_input)) <= int(long_window):
        st.caption(
            f"Momentum strategies generally require at least {int(long_window) + 1} trading observations."
        )
    with st.expander("About", icon=":material/info:"):
        st.caption("Historical investment research · not personalized financial advice")
        st.caption(f"Build `{build_identifier()}`")

if run:
    clear_analysis_state()
    try:
        tickers = parse_tickers(ticker_text)
        benchmark_candidates = parse_tickers(benchmark_ticker)
        if len(benchmark_candidates) != 1:
            raise ValueError("Enter exactly one benchmark ticker.")
        benchmark_resolution = resolve_benchmark_ticker(benchmark_candidates[0])
        benchmark = benchmark_resolution.display_symbol
        benchmark_provider = benchmark_resolution.provider_symbol
        start, end = validate_dates(start_input, end_input)
        if not allocation_ready or len(allocation_values) != len(tickers):
            raise InputError(
                f"You entered {len(allocation_values)} allocation values for {len(tickers)} investments. "
                "Add one percentage for each ticker."
            )
        weights = normalize_allocation(tickers, allocation_values)
        normalized = False
        with st.spinner("Downloading adjusted market history and running analytics…"):
            prices = cached_prices(tuple(tickers), start, end)
            benchmark_prices = cached_prices((benchmark_provider,), start, end)[benchmark_provider]
            analysis = run_analysis(prices, benchmark_prices, weights, risk_free)
            strategy_asset = tickers[0]
            momentum = optional_momentum_analysis(
                analysis.prices[strategy_asset], int(short_window), int(long_window), transaction_cost, risk_free
            )
            default_shocks = pd.Series(-0.10, index=tickers, dtype=float)
            historical = historical_stress(analysis.prices, weights, analysis.benchmark_prices)
            plans = {
                name: rebalancing_plan(weights, analysis.allocations[name], initial_value)
                for name in analysis.allocations.columns
            }
            policy_summary, policy_histories, policy_trades = compare_rebalancing_policies(
                asset_returns=analysis.asset_returns,
                target_weights=weights,
                initial_value=initial_value,
                transaction_cost_rate=transaction_cost,
                threshold=rebalancing_threshold,
                risk_free_rate=risk_free,
                benchmark_returns=analysis.benchmark_returns,
            )
            try:
                frontier, frontier_weights = efficient_frontier(analysis.asset_returns, risk_free, points=50)
                construction_stats = pd.DataFrame({
                    name: optimizer_statistics(analysis.asset_returns, analysis.allocations[name], risk_free)
                    for name in analysis.allocations.columns
                }).T
                tangency_stats = construction_stats.loc["Maximum Sharpe"].to_dict()
                cal = capital_allocation_line(tangency_stats, risk_free)
                construction_error = None
            except (ValueError, RuntimeError) as exc:
                frontier, frontier_weights, construction_stats, cal = (
                    pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
                )
                construction_error = str(exc)
        st.session_state["result"] = {
            "tickers": tickers, "benchmark_ticker": benchmark,
            "benchmark_provider_ticker": benchmark_provider,
            "benchmark_alias_notice": benchmark_resolution.notice,
            "weights": weights,
            "requested_start": start, "requested_end": end, "initial_value": initial_value,
            "risk_free": risk_free, "transaction_cost": transaction_cost, "analysis": analysis,
            "strategy_asset": strategy_asset, "momentum": momentum,
            "historical": historical, "plans": plans,
            "short_window": int(short_window), "long_window": int(long_window),
            "frontier": frontier, "frontier_weights": frontier_weights,
            "construction_stats": construction_stats, "cal": cal,
            "construction_error": construction_error,
            "rebalancing_threshold": rebalancing_threshold,
            "policy_summary": policy_summary, "policy_histories": policy_histories,
            "policy_trades": policy_trades,
        }
        st.session_state["current_shocks"] = default_shocks
        st.session_state["what_if_weights"] = weights.copy()
        st.session_state["what_if_shocks"] = default_shocks.copy()
        st.session_state["selected_target_method"] = "Equal Weight" if "Equal Weight" in plans else next(iter(plans))
        st.session_state["normalized"] = normalized
        st.session_state["analysis_tab"] = "Overview"
    except (ValueError, MarketDataError) as exc:
        st.error(f"Analysis could not run: {exc}")

requested_section = st.session_state.get("analysis_tab", "Dashboard")
requested_section = {
    "Overview": "Dashboard",
    "Portfolio Optimization": "Portfolio Optimization & Rebalancing",
    "Rebalancing": "Portfolio Optimization & Rebalancing",
    "Portfolio Strategies": "Portfolio Strategies & Momentum",
    "Momentum Strategy": "Portfolio Strategies & Momentum",
}.get(requested_section, requested_section)
if requested_section not in SECTION_TO_WORKSPACE:
    requested_section = "Dashboard"

# Preserve compatibility with saved sessions and deep links that address the former section key.
if requested_section != st.session_state.get("_navigation_section"):
    st.session_state["primary_workspace"] = SECTION_TO_WORKSPACE[requested_section]
    st.session_state["workspace_section"] = requested_section


def change_workspace() -> None:
    workspace = st.session_state["primary_workspace"]
    section = WORKSPACE_SECTIONS[workspace][0]
    st.session_state["workspace_section"] = section
    st.session_state["analysis_tab"] = section
    st.session_state["_navigation_section"] = section


def change_section() -> None:
    section = st.session_state["workspace_section"]
    st.session_state["analysis_tab"] = section
    st.session_state["_navigation_section"] = section


primary_workspace = st.segmented_control(
    "Primary workspace",
    PRIMARY_WORKSPACES,
    key="primary_workspace",
    on_change=change_workspace,
    label_visibility="collapsed",
    width="stretch",
)
if primary_workspace is None:
    primary_workspace = "Dashboard"
sections = WORKSPACE_SECTIONS[primary_workspace]
if st.session_state.get("workspace_section") not in sections:
    st.session_state["workspace_section"] = sections[0]
if len(sections) == 1:
    active_section = sections[0]
    st.session_state["workspace_section"] = active_section
else:
    active_section = st.selectbox(
        f"{primary_workspace} view",
        sections,
        key="workspace_section",
        on_change=change_section,
    )
st.session_state["analysis_tab"] = active_section
st.session_state["_navigation_section"] = active_section
section_container = st.container(gap="small")

if active_section == "Fixed Income":
    with section_container:
        render_fixed_income_workspace()
    render_footer()
    st.stop()

if "result" not in st.session_state:
    with section_container:
        st.subheader(active_section)
        if active_section == "Methodology & Limitations":
            st.subheader("Methodology and limitations")
            st.write(f"Application build: `{build_identifier()}`")
            st.info("Run an analysis to view methodology alongside the calculated results.")
        else:
            st.info("Configure the portfolio in the sidebar, then select **Run analysis**. Market data are requested only when you run the analysis.")
            if active_section == "Dashboard":
                with st.container(border=True):
                    st.markdown("**Executive research view**")
                    st.caption(
                        "Portfolio growth, benchmark-relative performance, allocation, drawdown, risk contribution, "
                        "portfolio construction, and deterministic insights appear here after analysis."
                    )
    render_footer()
    st.stop()

r = st.session_state["result"]
a = r["analysis"]
momentum = r["momentum"]
if r.get("benchmark_alias_notice"):
    st.info(r["benchmark_alias_notice"], icon=":material/swap_horiz:")
cvar95 = historical_cvar(a.portfolio_returns)
allocation_comparison = portfolio_comparison(a.asset_returns, a.allocations, r["weights"], r["risk_free"])
health_score, health_coverage, health_components = portfolio_health_score(
    a.performance, a.benchmark, r["weights"], cvar95,
)
insights = deterministic_insights(
    a.performance, a.benchmark, r["weights"], a.volatility_contributions, cvar95,
)
for warning in a.allocation_warnings:
    st.warning(warning)
st.caption(
    f"Common adjusted-price history: {a.prices.index.min().date()} to {a.prices.index.max().date()} · "
    f"{len(a.prices):,} observations · benchmark: {r['benchmark_ticker']}"
)
st.caption("Historical research only · constant portfolio weights · not personalized financial advice")

if active_section == "Dashboard":
    with section_container:
        st.subheader("Executive dashboard")
        ending_value = r["initial_value"] * (1 + a.performance["Total Return"])
        value_change = ending_value - r["initial_value"]
        primary_cards = [
            {
                "label": "Portfolio value", "value": compact_money(ending_value),
                "context": f"{compact_signed_money(value_change)} since inception",
                "tone": dashboard_metric_tone("Portfolio value"),
                "context_tone": "positive" if value_change > 0 else "negative" if value_change < 0 else "neutral",
            },
            {
                "label": "Total return", "value": compact_pct(a.performance["Total Return"]),
                "context": "Since inception",
                "tone": dashboard_metric_tone("Total return", a.performance["Total Return"]),
            },
            {
                "label": "CAGR", "value": compact_pct(a.performance["CAGR"]),
                "context": "Annualized compound return",
                "tone": dashboard_metric_tone("CAGR", a.performance["CAGR"]),
            },
            {
                "label": "Volatility", "value": compact_pct(a.performance["Annualized Volatility"]),
                "context": "Annualized variability", "tone": "neutral",
            },
            {
                "label": "Sharpe ratio", "value": ratio(a.performance["Sharpe Ratio"]),
                "context": "Risk-adjusted return",
                "tone": dashboard_metric_tone("Sharpe ratio", a.performance["Sharpe Ratio"]),
            },
            {
                "label": "Maximum drawdown", "value": compact_pct(a.performance["Maximum Drawdown"]),
                "context": "Peak-to-trough loss",
                "tone": dashboard_metric_tone("Maximum drawdown", a.performance["Maximum Drawdown"]),
            },
        ]
        relative_cards = [
            {
                "label": "Beta", "value": ratio(a.benchmark["Beta"]),
                "context": "Benchmark sensitivity", "tone": "neutral",
            },
            {
                "label": "Tracking error", "value": compact_pct(a.benchmark["Tracking Error"]),
                "context": "Active-return variability", "tone": "neutral",
            },
            {
                "label": "Information ratio", "value": ratio(a.benchmark["Information Ratio"]),
                "context": "Active return per unit of tracking error",
                "tone": dashboard_metric_tone("Information ratio", a.benchmark["Information Ratio"]),
            },
            {
                "label": "Largest risk contributor", "value": str(a.volatility_contributions.idxmax()),
                "context": "Highest volatility contribution", "tone": "neutral",
            },
            {
                "label": "Relative benchmark result", "value": compact_pct(a.benchmark["Annualized Active Return"]),
                "context": "Annualized active return",
                "tone": dashboard_metric_tone("Relative benchmark result", a.benchmark["Annualized Active Return"]),
            },
        ]
        st.html(DASHBOARD_METRIC_GRID_CSS)
        dashboard_metric_grid(primary_cards, "Portfolio summary metrics", "primary")
        dashboard_metric_grid(relative_cards, "Benchmark and risk metrics", "secondary")
        st.caption(
            f"Health score: {health_score:.0f}/100 with {health_coverage:.0%} metric coverage · "
            f"benchmark: {r['benchmark_ticker']}"
        )
        growth = pd.concat([
            (1 + a.portfolio_returns).cumprod().rename("Portfolio"),
            (1 + a.benchmark_returns).cumprod().rename(r["benchmark_ticker"]),
        ], axis=1)
        line_chart(
            growth * r["initial_value"],
            f"Portfolio vs {r['benchmark_ticker']}",
            "Portfolio value ($)",
            colors=["#60A5FA", "#34D399"],
        )
        line_chart(
            pd.concat([
                drawdown_series(a.portfolio_returns).rename("Portfolio"),
                drawdown_series(a.benchmark_returns).rename(r["benchmark_ticker"]),
            ], axis=1),
            "Drawdown",
            "Drawdown",
        )
        allocation_column, risk_column = st.columns(2)
        with allocation_column:
            allocation_figure = px.pie(
                values=r["weights"].values,
                names=r["weights"].index,
                title="Current allocation",
                hole=0.55,
            )
            render_plotly_chart(allocation_figure)
        with risk_column:
            risk_figure = px.bar(
                a.volatility_contributions.rename("Contribution").reset_index(),
                x="index",
                y="Contribution",
                title="Risk contribution",
                labels={"index": "Security", "Contribution": "Annualized volatility contribution"},
            )
            risk_figure.update_yaxes(tickformat=".1%")
            render_plotly_chart(risk_figure, show_legend=False)
        if not r["frontier"].empty:
            frontier_preview = px.line(
                r["frontier"],
                x="Optimizer Volatility",
                y="Optimizer Expected Return",
                title="Efficient frontier preview",
                labels={
                    "Optimizer Volatility": "Annualized volatility",
                    "Optimizer Expected Return": "Expected annual return",
                },
            )
            frontier_preview.update_xaxes(tickformat=".1%")
            frontier_preview.update_yaxes(tickformat=".1%")
            render_plotly_chart(frontier_preview, show_legend=False)
        st.markdown("### Key insights")
        for observation in insights["Observation"]:
            st.write(f"- {observation}")
        with st.expander("Insight evidence", icon=":material/fact_check:"):
            st.dataframe(insights, width="stretch", hide_index=True)

if active_section == "Performance":
    with section_container:
        st.subheader("Performance")
        st.caption(
            "Arithmetic return is the historical expected-return estimate used by Sharpe and optimization. "
            "CAGR is realized compound growth. Performance Sharpe and optimizer Sharpe use the same arithmetic convention."
        )
        st.dataframe(display_metric_frame(a.performance), width="stretch")
        growth = pd.concat([
            (1 + a.portfolio_returns).cumprod().rename("Portfolio"),
            (1 + a.benchmark_returns).cumprod().rename(r["benchmark_ticker"]),
        ], axis=1)
        line_chart(growth, "Portfolio versus benchmark growth", "Growth of $1", colors=["#60A5FA", "#CBD5E1"])

        st.markdown("#### Normalized performance by holding")
        st.caption(
            "Each series begins at 1.00 on the first common observation date. "
            "This is a security comparison using adjusted prices, not a portfolio return or a weighted result."
        )
        holding_options = list(a.prices.columns)
        selected_holdings = st.multiselect(
            "Holdings to display", holding_options, default=holding_options,
            key="normalized_holding_selection",
        )
        include_benchmark = st.checkbox(
            f"Include benchmark ({r['benchmark_ticker']})", value=False,
            key="normalized_include_benchmark",
        )
        scale = st.segmented_control(
            "Chart scale", ["Linear", "Log"], default="Linear", key="normalized_chart_scale"
        )
        if not selected_holdings:
            st.info("Select at least one holding to display normalized performance.")
        else:
            normalized_inputs = a.prices.loc[:, selected_holdings].copy()
            benchmark_label = None
            if include_benchmark:
                benchmark_label = f"Benchmark ({r['benchmark_ticker']})"
                normalized_inputs[benchmark_label] = a.benchmark_prices
            normalized, excluded = normalized_holding_performance(normalized_inputs)
            if excluded:
                details = "; ".join(f"{label}: {reason}" for label, reason in excluded.items())
                st.warning(f"Some series were excluded from normalized performance: {details}")
            if normalized.empty:
                st.error("No selected series can be normalized safely on a common date range.")
            else:
                if benchmark_label and benchmark_label not in normalized:
                    benchmark_label = None
                normalized_holding_chart(
                    normalized,
                    benchmark_label,
                    log_scale=scale == "Log",
                )
                export = normalized.copy()
                export.index.name = "Date"
                st.download_button(
                    "Download normalized holding performance CSV",
                    export.to_csv().encode("utf-8"),
                    "portfoliolens_normalized_holding_performance.csv",
                    "text/csv",
                    icon=":material/download:",
                )
        line_chart(drawdown_series(a.portfolio_returns).to_frame("Drawdown"), "Portfolio drawdown", "Drawdown")
        rolling_vol = a.portfolio_returns.rolling(63).std() * TRADING_DAYS ** 0.5
        line_chart(rolling_vol.to_frame("63-day volatility"), "Rolling annualized volatility", "Volatility")
        st.markdown("#### Monthly returns")
        st.dataframe(monthly_returns(a.portfolio_returns), width="stretch", column_config={
            month: st.column_config.NumberColumn(format="percent") for month in monthly_returns(a.portfolio_returns).columns
        })

if active_section == "Performance Evaluation":
    with section_container:
        st.subheader("Performance Evaluation")
        st.caption(
            "A consolidated historical evaluation of return, total risk, systematic risk, benchmark-relative risk, "
            "and manager-performance diagnostics. Results are descriptive and are not evidence that past skill will persist."
        )
        summary = {
            "Historical Arithmetic Annualized Return": a.performance["Historical Arithmetic Annualized Return"],
            "CAGR": a.performance["CAGR"],
            "Annualized Volatility": a.performance["Annualized Volatility"],
            "Maximum Drawdown": a.performance["Maximum Drawdown"],
        }
        risk_adjusted = {
            "Sharpe Ratio": a.performance["Sharpe Ratio"],
            "Sortino Ratio": a.performance["Sortino Ratio"],
            "Calmar Ratio": a.performance["Calmar Ratio"],
            "Treynor Ratio": a.benchmark["Treynor Ratio"],
            "Jensen's Alpha": a.benchmark["Jensen's Alpha"],
        }
        benchmark_evaluation = {
            "Benchmark Return": a.benchmark["Benchmark Return"],
            "Annualized Active Return": a.benchmark["Annualized Active Return"],
            "Tracking Error": a.benchmark["Tracking Error"],
            "Information Ratio": a.benchmark["Information Ratio"],
            "Beta": a.benchmark["Beta"],
            "R-Squared": a.benchmark["R-Squared"],
        }
        fama = fama_selectivity_decomposition(
            a.performance["Historical Arithmetic Annualized Return"],
            a.benchmark["Benchmark Return"], r["risk_free"],
            a.performance["Annualized Volatility"], annualized_volatility(a.benchmark_returns),
            a.benchmark["Beta"],
        )
        with st.container(horizontal=True):
            st.metric("Arithmetic annualized return", pct(summary["Historical Arithmetic Annualized Return"]), border=True)
            st.metric("Sharpe ratio", ratio(risk_adjusted["Sharpe Ratio"]), border=True)
            st.metric("Jensen's alpha", pct(risk_adjusted["Jensen's Alpha"]), border=True)
            st.metric("Information ratio", ratio(benchmark_evaluation["Information Ratio"]), border=True)
            st.metric("Net selectivity", pct(fama["Net Selectivity"]), border=True)
        left, right = st.columns(2)
        with left:
            st.markdown("### Performance Summary")
            st.dataframe(display_metric_frame(summary), width="stretch")
            st.markdown("### Risk-Adjusted Performance")
            st.dataframe(display_metric_frame(risk_adjusted), width="stretch")
        with right:
            st.markdown("### Benchmark Evaluation")
            st.dataframe(display_metric_frame(benchmark_evaluation), width="stretch")
            st.markdown("### Manager Evaluation")
            st.dataframe(display_metric_frame(fama), width="stretch")
        st.caption(
            "Fama selectivity compares realized arithmetic return with the CAPM required return. The diversification effect "
            "is the return difference between the CML- and CAPM-required returns at the portfolio's observed total risk; "
            "net selectivity removes that diversification effect. All inputs are annualized once and use the same aligned sample."
        )
        rolling = rolling_performance_evaluation(
            a.portfolio_returns, a.benchmark_returns, r["risk_free"], window=63,
        )
        st.markdown("### Historical Rolling Metrics")
        line_chart(rolling, "63-day rolling performance diagnostics", "Metric value")
        st.caption(
            "Rolling metrics are professional stability diagnostics, not source-derived manager-ranking rules. "
            "The 63-observation window uses annualized arithmetic means and sample standard deviations."
        )
        evaluation_export = pd.concat({
            "Performance Summary": metric_frame(summary),
            "Risk-Adjusted Performance": metric_frame(risk_adjusted),
            "Benchmark Evaluation": metric_frame(benchmark_evaluation),
            "Fama Evaluation": metric_frame(fama),
        })
        st.download_button(
            "Download performance evaluation CSV", evaluation_export.to_csv().encode("utf-8"),
            "portfoliolens_performance_evaluation.csv", "text/csv",
        )
        st.download_button(
            "Download rolling evaluation CSV", rolling.to_csv().encode("utf-8"),
            "portfoliolens_rolling_performance_evaluation.csv", "text/csv",
        )
        methodology = st.expander("Methodology and limitations", on_change="rerun")
        if methodology.open:
            with methodology:
                st.markdown("""
- Sharpe uses annual arithmetic excess return divided by annualized sample volatility; Sortino uses target downside deviation.
- Treynor divides annual arithmetic excess return by beta. Jensen's alpha is realized arithmetic return less CAPM required return.
- Tracking error is annualized sample volatility of aligned daily active returns; Information Ratio uses annualized arithmetic active return.
- Fama evaluation uses the benchmark as the market proxy. Its selectivity labels are historical diagnostics, not forecasts of manager skill.
- Category allocation and selection effects require explicit portfolio and benchmark category weights and returns. PortfolioLens does not infer those inputs from ticker names.
- Calmar, drawdown, tracking error, Information Ratio, and rolling diagnostics are professional product measures; they are not attributed to the source model reviewed for this integration.
""")

if active_section == "Risk":
    with section_container:
        st.subheader("Risk and diversification")
        var95, cvar95 = historical_var(a.portfolio_returns), historical_cvar(a.portfolio_returns)
        effective = 1 / float((r["weights"] ** 2).sum())
        diversification = diversification_effect(a.asset_returns, r["weights"])
        with st.container(horizontal=True):
            st.metric("Historical VaR (95%)", pct(var95), border=True)
            st.metric("Historical CVaR (95%)", pct(cvar95), border=True)
            st.metric("Effective holdings", f"{effective:.2f}", border=True)
            st.metric("Largest risk contributor", a.volatility_contributions.idxmax(), border=True)
        with st.container(horizontal=True):
            st.metric("Weighted standalone volatility", pct(diversification["Weighted Standalone Volatility"]), border=True)
            st.metric("Portfolio volatility", pct(diversification["Portfolio Volatility"]), border=True)
            st.metric("Diversification reduction", pct(diversification["Diversification Reduction"]), border=True)
            st.metric("Reduction vs. standalone", pct(diversification["Diversification Reduction Percentage"]), border=True)
        st.caption(
            "Diversification reduction compares portfolio volatility with the weighted average of standalone asset volatilities. "
            "It reflects observed covariance and is descriptive, not a forecast or a systematic-risk estimate."
        )
        st.markdown("**Asset-level return and risk foundations**")
        asset_foundations = asset_risk_return_table(a.asset_returns)
        st.dataframe(asset_foundations, width="stretch", column_config={
            "Periodic Arithmetic Mean": st.column_config.NumberColumn(format="percent"),
            "Periodic Geometric Mean": st.column_config.NumberColumn(format="percent"),
            "Historical Arithmetic Annualized Return": st.column_config.NumberColumn(format="percent"),
            "CAGR": st.column_config.NumberColumn(format="percent"),
            "Annualized Sample Variance": st.column_config.NumberColumn(format="%.4f"),
            "Annualized Sample Volatility": st.column_config.NumberColumn(format="percent"),
            "Coefficient of Variation": st.column_config.NumberColumn(format="%.2f"),
        })
        st.download_button(
            "Download asset risk-and-return table",
            asset_foundations.to_csv().encode("utf-8"),
            "portfoliolens_asset_risk_return.csv",
            "text/csv",
        )
        st.caption(
            "Returns are simple adjusted-price returns. Arithmetic mean is the historical expected-return estimate; "
            "geometric mean is periodic compound growth; CAGR annualizes compound growth. Historical variance and covariance use sample estimates (n−1)."
        )
        corr = a.asset_returns.corr(); cov = a.asset_returns.cov() * TRADING_DAYS
        fig = px.imshow(corr, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r", title="Daily return correlations")
        render_plotly_chart(fig, complex_chart=True, show_legend=False)
        covariance = st.expander("Annualized covariance matrix", on_change="rerun")
        if covariance.open:
            with covariance:
                st.dataframe(cov, width="stretch", column_config={
                    column: st.column_config.NumberColumn(format="%.4f") for column in cov.columns
                })
        concentration = pd.DataFrame({
            "Weight": r["weights"], "Weight Squared": r["weights"] ** 2,
            "Volatility Contribution": a.volatility_contributions,
        })
        st.dataframe(concentration, width="stretch", column_config={
            column: st.column_config.NumberColumn(format="percent") for column in concentration.columns
        })
        st.caption("Volatility contribution uses Euler decomposition: wᵢ(Σw)ᵢ / √(w′Σw); contributions reconcile to annualized portfolio volatility.")

if active_section == "Benchmark & Attribution":
    with section_container:
        st.subheader("Benchmark-relative results and attribution")
        relative_names = [
            "Portfolio Return", "Benchmark Return", "Excess Return", "Tracking Error",
            "Annualized Active Return", "Information Ratio", "Correlation", "Relative Drawdown",
        ]
        regression_names = [
            "Regression Alpha", "Beta", "R-Squared", "Residual Volatility",
            "Systematic Variance", "Idiosyncratic Variance", "Systematic Risk Share",
            "Idiosyncratic Risk Share", "Regression Observations",
        ]
        capm_names = ["CAPM Required Return", "Jensen's Alpha", "Treynor Ratio"]
        st.markdown("**Benchmark-relative performance**")
        st.dataframe(display_metric_frame({name: a.benchmark[name] for name in relative_names}), width="stretch")
        st.caption(
            "Excess Return is the difference between cumulative portfolio and benchmark returns over the selected path. "
            "Annualized Active Return is 252 times mean daily portfolio-minus-benchmark return and is the Information Ratio numerator."
        )
        st.markdown("**Excess-return single-index regression**")
        st.dataframe(display_metric_frame({name: a.benchmark[name] for name in regression_names}), width="stretch")
        st.caption(
            "Regression uses aligned daily excess returns: portfolio excess return = alpha + beta × benchmark excess return + residual. "
            "Risk shares decompose annualized excess-return variance; residual volatility uses the regression residual standard error."
        )
        st.markdown("**CAPM performance evaluation**")
        st.dataframe(display_metric_frame({name: a.benchmark[name] for name in capm_names}), width="stretch")
        st.caption(
            "CAPM required return is the risk-free rate plus beta times the benchmark risk premium. "
            "Jensen’s alpha is realized arithmetic return minus that required return; Treynor is excess return per unit of beta."
        )
if active_section == "Security Analysis":
    with section_container:
        st.subheader("Security Analysis")
        st.markdown("### Single-Index Security Analysis")
        st.caption(
            "Each portfolio security is fitted independently against the selected benchmark using aligned daily simple excess returns. "
            "Results are historical diagnostics, not forecasts, ratings, or investment recommendations."
        )
        st.caption(f"Benchmark: {r['benchmark_ticker']} · Annual risk-free rate: {r['risk_free']:.2%}")
        selected_security = st.selectbox(
            "Security to inspect", list(a.asset_returns.columns), key="single_index_security"
        )
        security_table = security_single_index_table(
            a.asset_returns, a.benchmark_returns, r["risk_free"]
        )
        comparison_columns = [
            "Regression Alpha", "Beta", "R-Squared", "Residual Volatility",
            "Systematic Risk Share", "Jensen's Alpha",
        ]
        diagnostic_columns = [
            "Regression Alpha", "Beta", "R-Squared", "Residual Volatility",
            "Systematic Volatility", "Systematic Variance", "Idiosyncratic Variance",
            "Systematic Risk Share", "Idiosyncratic Risk Share", "Jensen's Alpha",
            "Treynor Ratio", "Alpha / Residual Variance", "Regression Observations",
        ]
        st.dataframe(
            security_table[comparison_columns], width="stretch",
            column_config={
                "Regression Alpha": st.column_config.NumberColumn(format="percent"),
                "R-Squared": st.column_config.NumberColumn(format="percent"),
                "Residual Volatility": st.column_config.NumberColumn(format="percent"),
                "Systematic Volatility": st.column_config.NumberColumn(format="percent"),
                "Systematic Variance": st.column_config.NumberColumn(format="%.4f"),
                "Idiosyncratic Variance": st.column_config.NumberColumn(format="%.4f"),
                "Systematic Risk Share": st.column_config.NumberColumn(format="percent"),
                "Idiosyncratic Risk Share": st.column_config.NumberColumn(format="percent"),
                "Jensen's Alpha": st.column_config.NumberColumn(format="percent"),
            },
        )
        with st.expander("Cross-security diagnostics", icon=":material/table_chart:"):
            st.dataframe(
                security_table[diagnostic_columns],
                width="stretch",
                column_config={
                    "Regression Alpha": st.column_config.NumberColumn(format="percent"),
                    "R-Squared": st.column_config.NumberColumn(format="percent"),
                    "Residual Volatility": st.column_config.NumberColumn(format="percent"),
                    "Systematic Volatility": st.column_config.NumberColumn(format="percent"),
                    "Systematic Variance": st.column_config.NumberColumn(format="%.4f"),
                    "Idiosyncratic Variance": st.column_config.NumberColumn(format="%.4f"),
                    "Systematic Risk Share": st.column_config.NumberColumn(format="percent"),
                    "Idiosyncratic Risk Share": st.column_config.NumberColumn(format="percent"),
                    "Jensen's Alpha": st.column_config.NumberColumn(format="percent"),
                },
            )
        st.caption(
            "Alpha / Residual Variance is a historical screening diagnostic. A positive value does not imply that alpha will persist. "
            "Statistical significance and economic magnitude should be assessed separately."
        )
        security_metrics, security_observations = single_index_regression_diagnostics(
            a.asset_returns[selected_security], a.benchmark_returns, r["risk_free"]
        )
        with st.container(horizontal=True):
            st.metric("Annualized regression alpha", pct(security_metrics["Regression Alpha"]), border=True)
            st.metric("Beta", ratio(security_metrics["Beta"]), border=True)
            st.metric("R-squared", pct(security_metrics["R-Squared"]), border=True)
            st.metric("Residual volatility", pct(security_metrics["Residual Volatility"]), border=True)
            st.metric("Observations", f"{security_metrics['Regression Observations']:.0f}", border=True)

        ordered = security_observations.sort_values("Benchmark Excess Return")
        characteristic = go.Figure()
        characteristic.add_trace(go.Scatter(
            x=security_observations["Benchmark Excess Return"],
            y=security_observations["Security Excess Return"],
            mode="markers", name="Actual excess return",
            customdata=security_observations.index.astype(str),
            hovertemplate="Date: %{customdata}<br>Benchmark excess return: %{x:.2%}<br>Security excess return: %{y:.2%}<extra></extra>",
        ))
        characteristic.add_trace(go.Scatter(
            x=ordered["Benchmark Excess Return"], y=ordered["Fitted Excess Return"],
            mode="lines", name="Fitted characteristic line",
            hovertemplate="Benchmark excess return: %{x:.2%}<br>Fitted security excess return: %{y:.2%}<extra></extra>",
        ))
        characteristic.update_layout(
            title=f"Security Characteristic Line — {selected_security} vs {r['benchmark_ticker']}",
            xaxis_title="Benchmark excess return (daily)", yaxis_title="Security excess return (daily)",
        )
        render_plotly_chart(characteristic, complex_chart=True)

        residual_chart = px.scatter(
            security_observations, x=security_observations.index, y="Residual",
            title=f"Single-index residuals — {selected_security}",
            labels={"x": "Date", "Residual": "Residual excess return (daily)"},
        )
        residual_chart.add_hline(y=0, line_dash="dash", line_color="gray")
        render_plotly_chart(residual_chart, show_legend=False)

        regression_details = st.expander("Regression Diagnostics", on_change="rerun")
        if regression_details.open:
            with regression_details:
                diagnostic_names = [
                    "Regression Standard Error", "Systematic Variance", "Idiosyncratic Variance",
                    "Idiosyncratic Risk Share", "Alpha Standard Error", "Alpha t-Statistic",
                    "Alpha p-Value", "Alpha 95% Lower", "Alpha 95% Upper", "Beta Standard Error",
                    "Beta t-Statistic", "Beta p-Value", "Beta 95% Lower", "Beta 95% Upper",
                ]
                st.dataframe(
                    display_metric_frame({name: security_metrics[name] for name in diagnostic_names}),
                    width="stretch",
                )
                st.caption(
                    "Alpha and beta confidence intervals use a t distribution with n−2 residual degrees of freedom. "
                    "Residual volatility is the annualized sample standard deviation of residuals; regression standard error uses n−2."
                )
        st.download_button(
            "Download security comparison CSV", security_table.to_csv().encode("utf-8"),
            "portfoliolens_security_analysis.csv", "text/csv",
        )
        st.download_button(
            "Download selected regression observations CSV", security_observations.to_csv().encode("utf-8"),
            f"portfoliolens_{str(selected_security).lower()}_single_index.csv", "text/csv",
        )

if active_section == "Asset Pricing":
    with section_container:
        st.subheader("Asset Pricing")
        st.caption(
            "CAPM compares each security's historical arithmetic return with the return implied by its estimated beta, "
            "the selected benchmark's arithmetic return, and the annual risk-free rate. Results are historical diagnostics, not valuations or recommendations."
        )
        capm_table = capm_security_table(
            a.asset_returns, a.benchmark_returns, r["risk_free"]
        )
        market_return = float(a.benchmark_returns.mean() * TRADING_DAYS)
        st.caption(
            f"Benchmark: {r['benchmark_ticker']} · Historical arithmetic benchmark return: {market_return:.2%} · "
            f"Annual risk-free rate: {r['risk_free']:.2%}"
        )
        selected_asset_pricing_security = st.selectbox(
            "Security for CAPM review", list(capm_table.index), key="asset_pricing_security"
        )
        selected_capm = capm_table.loc[selected_asset_pricing_security]
        with st.container(horizontal=True):
            st.metric("Beta", ratio(selected_capm["Beta"]), border=True)
            st.metric("Historical arithmetic return", pct(selected_capm["Historical Arithmetic Return"]), border=True)
            st.metric("CAPM required return", pct(selected_capm["CAPM Required Return"]), border=True)
            st.metric("Jensen's alpha", pct(selected_capm["Jensen's Alpha"]), border=True)

        st.markdown("### Security Market Line")
        beta_min = min(0.0, float(capm_table["Beta"].min()))
        beta_max = max(1.0, float(capm_table["Beta"].max()))
        beta_padding = max(.1, (beta_max - beta_min) * .1)
        sml = security_market_line(
            pd.Series([beta_min - beta_padding, beta_max + beta_padding]),
            r["risk_free"], market_return,
        )
        sml_chart = go.Figure()
        sml_chart.add_trace(go.Scatter(
            x=sml["Beta"], y=sml["CAPM Required Return"], mode="lines",
            name="Security Market Line",
            hovertemplate="Beta: %{x:.3f}<br>CAPM required return: %{y:.2%}<extra></extra>",
        ))
        sml_chart.add_trace(go.Scatter(
            x=capm_table["Beta"], y=capm_table["Historical Arithmetic Return"],
            mode="markers", text=capm_table.index,
            name="Historical security return",
            customdata=capm_table[["CAPM Required Return", "Jensen's Alpha"]].to_numpy(),
            hovertemplate=(
                "Security: %{text}<br>Beta: %{x:.3f}<br>Historical arithmetic return: %{y:.2%}"
                "<br>CAPM required return: %{customdata[0]:.2%}<br>Jensen's alpha: %{customdata[1]:.2%}<extra></extra>"
            ),
        ))
        sml_chart.add_trace(go.Scatter(
            x=[1.0], y=[market_return], mode="markers", marker_symbol="diamond", marker_size=11,
            name=r["benchmark_ticker"],
            hovertemplate=f"{r['benchmark_ticker']}<br>Beta: 1.000<br>Historical arithmetic return: %{{y:.2%}}<extra></extra>",
        ))
        sml_chart.update_layout(
            title="Security Market Line — CAPM comparison",
            xaxis_title="Beta", yaxis_title="Annualized return",
        )
        render_plotly_chart(sml_chart, complex_chart=True)
        st.dataframe(
            capm_table, width="stretch",
            column_config={
                "Historical Arithmetic Return": st.column_config.NumberColumn(format="percent"),
                "CAPM Required Return": st.column_config.NumberColumn(format="percent"),
                "Jensen's Alpha": st.column_config.NumberColumn(format="percent"),
                "R-Squared": st.column_config.NumberColumn(format="percent"),
                "Residual Volatility": st.column_config.NumberColumn(format="percent"),
            },
        )
        st.download_button(
            "Download CAPM analysis CSV", capm_table.to_csv().encode("utf-8"),
            "portfoliolens_capm_analysis.csv", "text/csv",
        )
        st.caption(
            "Above or below the line means historical arithmetic return exceeded or fell short of the CAPM required return over this sample. "
            "It does not establish mispricing, intrinsic value, or an expected trading profit."
        )

        factor_scope = st.expander("Factor-pricing framework", on_change="rerun")
        if factor_scope.open:
            with factor_scope:
                st.dataframe(pd.DataFrame({
                    "Factor": ["Market excess return", "Size (SMB)", "Value (HML)", "Momentum"],
                    "Interpretation": [
                        "Broad-market return above the risk-free rate",
                        "Small-cap portfolio return less large-cap portfolio return",
                        "High book-to-market portfolio return less low book-to-market portfolio return",
                        "Prior winners' return less prior losers' return",
                    ],
                    "Live estimate": ["Available", "Not available", "Not available", "Not available"],
                }), width="stretch", hide_index=True)
                st.caption(
                    "PortfolioLens implements the deterministic linear factor-pricing calculation in its analytics layer, but does not estimate "
                    "SMB, HML, or momentum exposures from Yahoo Finance prices. Reliable factor series, frequency alignment, and source governance "
                    "are required before multifactor estimates can be presented as live research outputs."
                )

if active_section == "Benchmark & Attribution":
    with section_container:
        comparison = pd.concat([
            (1 + a.portfolio_returns).cumprod().rename("Portfolio"),
            (1 + a.benchmark_returns).cumprod().rename(r["benchmark_ticker"]),
        ], axis=1)
        line_chart(comparison, "Portfolio versus benchmark", "Growth of $1")
        relative = (comparison["Portfolio"] / comparison[r["benchmark_ticker"]]).rename("Relative wealth")
        line_chart(relative.to_frame(), "Rolling relative performance", "Portfolio / benchmark")
        attribution = pd.concat([a.return_contributions, a.volatility_contributions], axis=1)
        st.dataframe(attribution, width="stretch", column_config={
            column: st.column_config.NumberColumn(format="percent") for column in attribution.columns
        })
        st.caption(f"Return contributions sum to {a.return_contributions.sum():.2%}; portfolio total return is {a.performance['Total Return']:.2%}.")

if active_section == "Portfolio Optimization & Rebalancing":
    with section_container:
        st.subheader(active_section)
        st.caption(
            "Modern portfolio construction tools: long-only efficient frontier, global minimum-variance portfolio, "
            "constrained tangency portfolio, target-return portfolio, non-leveraged Capital Allocation Line, "
            "utility-based complete portfolio, and exportable optimized weights."
        )
        if r["construction_error"]:
            st.warning(f"Efficient frontier unavailable: {r['construction_error']}")
        else:
            st.markdown("**Historical mean-variance construction**")
            st.caption(
                "Optimizer expected return is the annualized arithmetic sample mean; optimizer volatility uses the annualized sample covariance matrix. "
                "These differ from realized CAGR and are historical estimates, not forecasts or recommendations."
            )
            tangency_stats = r["construction_stats"].loc["Maximum Sharpe"].to_dict()
            complete_method = st.segmented_control(
                "Complete portfolio selection method",
                ["Direct risky allocation", "Utility-Based Allocation"],
                default="Direct risky allocation",
                help="Choose a direct capital allocation or an explicit quadratic-utility model.",
            )
            direct_risky_allocation = st.slider(
                "Risk preference — allocation to the tangency portfolio (%)", 0, 100, 100, 5,
                disabled=complete_method != "Direct risky allocation",
                help=(
                    "The remainder is held in the risk-free asset. This directly selects the complete portfolio. "
                    "PortfolioLens models lending from 0% to 100% risky allocation; borrowing and leverage are not enabled."
                ),
            ) / 100
            risk_aversion = st.number_input(
                "Risk aversion coefficient (A)", min_value=0.1, max_value=30.0, value=3.0, step=0.1,
                disabled=complete_method != "Utility-Based Allocation",
                help=(
                    "The utility model uses U = E[r] − ½Aσ² and y* = (E[rT] − rf)/(AσT²). "
                    "Higher A implies lower risky allocation. This is a model input, not a personal risk assessment."
                ),
            )
            utility_result = utility_optimal_complete_portfolio(
                tangency_stats, r["risk_free"], risk_aversion,
            )
            risky_allocation = (
                direct_risky_allocation
                if complete_method == "Direct risky allocation"
                else float(utility_result["Risky Portfolio Weight"])
            )
            complete_stats = complete_portfolio_statistics(tangency_stats, r["risk_free"], risky_allocation)
            complete_weights = complete_portfolio_weights(
                a.allocations["Maximum Sharpe"], risky_allocation,
            )
            comparison_stats = r["construction_stats"].copy()
            comparison_stats.loc["Complete Portfolio"] = {
                key: complete_stats[key] for key in comparison_stats.columns
            }
            if "target_return_result" in st.session_state:
                _, saved_target_stats = st.session_state["target_return_result"]
                comparison_stats.loc["Target Return"] = saved_target_stats
            comparison_stats = comparison_stats.rename(index={
                "Minimum Variance": "Global Minimum Variance",
                "Maximum Sharpe": "Tangency (Maximum Sharpe)",
            })
            st.markdown("**Current and optimized portfolio statistics**")
            st.dataframe(comparison_stats, width="stretch", column_config={
                "Optimizer Expected Return": st.column_config.NumberColumn(format="percent"),
                "Optimizer Volatility": st.column_config.NumberColumn(format="percent"),
                "Optimizer Sharpe": st.column_config.NumberColumn(format="%.2f"),
            })
            frontier_plot = r["frontier"].reset_index()
            frontier_chart = px.line(
                frontier_plot, x="Optimizer Volatility", y="Optimizer Expected Return",
                title="Efficient Frontier and Capital Allocation Line",
                labels={
                    "Optimizer Volatility": "Annualized volatility",
                    "Optimizer Expected Return": "Annualized arithmetic expected return",
                },
                hover_data={
                    "Portfolio": True,
                    "Optimizer Volatility": ":.2%",
                    "Optimizer Expected Return": ":.2%",
                    "Optimizer Sharpe": ":.3f",
                },
            )
            frontier_chart.update_traces(name="Efficient Frontier", line=dict(color="#2C7FB8", width=3))
            frontier_chart.add_scatter(
                x=r["cal"]["Volatility"], y=r["cal"]["Expected Return"], mode="lines",
                customdata=r["cal"][["Risky Portfolio Weight", "Sharpe Ratio"]],
                hovertemplate=(
                    "Capital Allocation Line<br>Annualized volatility: %{x:.2%}<br>"
                    "Annualized expected return: %{y:.2%}<br>Risky allocation: %{customdata[0]:.0%}<br>"
                    "Sharpe ratio: %{customdata[1]:.3f}<extra></extra>"
                ),
                line=dict(color="#F28E2B", width=3, dash="dash"),
                name="CAL",
            )
            marker_styles = {
                "Current": ("Current", "Current Portfolio", "#7F7F7F", "circle"),
                "Minimum Variance": ("GMV", "Global Minimum Variance Portfolio", "#59A14F", "diamond"),
                "Maximum Sharpe": ("Tangency", "Tangency Portfolio", "#E15759", "star"),
            }
            for name, (legend_name, full_name, color, symbol) in marker_styles.items():
                if name in r["construction_stats"].index:
                    point = r["construction_stats"].loc[name]
                    frontier_chart.add_scatter(
                        x=[point["Optimizer Volatility"]], y=[point["Optimizer Expected Return"]],
                        mode="markers", name=legend_name,
                        customdata=[[point["Optimizer Sharpe"]]],
                        hovertemplate=(
                            f"{full_name}<br>Annualized volatility: %{{x:.2%}}<br>"
                            "Annualized expected return: %{y:.2%}<br>Sharpe ratio: %{customdata[0]:.3f}<extra></extra>"
                        ),
                        marker=dict(color=color, size=12, symbol=symbol),
                    )
            frontier_chart.add_scatter(
                x=[complete_stats["Optimizer Volatility"]], y=[complete_stats["Optimizer Expected Return"]],
                mode="markers", name="Complete",
                customdata=[[complete_stats["Optimizer Sharpe"]]],
                hovertemplate=(
                    "Complete Portfolio<br>Annualized volatility: %{x:.2%}<br>Annualized expected return: %{y:.2%}<br>"
                    "Sharpe ratio: %{customdata[0]:.3f}<extra></extra>"
                ),
                marker=dict(color="#B07AA1", size=12, symbol="cross"),
            )
            if "target_return_result" in st.session_state:
                _, saved_target_stats = st.session_state["target_return_result"]
                frontier_chart.add_scatter(
                    x=[saved_target_stats["Optimizer Volatility"]],
                    y=[saved_target_stats["Optimizer Expected Return"]],
                    mode="markers", name="Target",
                    customdata=[[saved_target_stats["Optimizer Sharpe"]]],
                    hovertemplate=(
                        "Target Return Portfolio<br>Annualized volatility: %{x:.2%}<br>"
                        "Annualized expected return: %{y:.2%}<br>Sharpe ratio: %{customdata[0]:.3f}<extra></extra>"
                    ),
                    marker=dict(color="#76B7B2", size=12, symbol="triangle-up"),
                )
            frontier_chart.update_layout(
                hovermode="closest",
            )
            render_plotly_chart(frontier_chart, complex_chart=True)
            st.caption(
                "The curve contains only feasible minimum-variance portfolios on the efficient upper branch, beginning at the global minimum-variance portfolio. "
                "The Capital Allocation Line uses the same long-only tangency portfolio and annual risk-free rate as the optimizer and stops at 100% risky exposure. "
                "The current portfolio is shown independently and may lie below the frontier. Results are historical estimates, not recommendations."
            )

            target_for_diagnostics = None
            diagnostic_weights = a.allocations["Maximum Sharpe"]
            if "target_return_result" in st.session_state:
                diagnostic_weights, saved_target_stats = st.session_state["target_return_result"]
                target_for_diagnostics = saved_target_stats["Optimizer Expected Return"]
            diagnostics = optimization_diagnostics(
                a.asset_returns,
                diagnostic_weights,
                r["risk_free"],
                target_return=target_for_diagnostics,
                frontier=r["frontier"],
                tangency_statistics=tangency_stats,
            )
            diagnostic_table = pd.DataFrame({
                "Diagnostic": list(diagnostics),
                "Value": [str(value) for value in diagnostics.values()],
            })
            with st.expander("Optimization Diagnostics"):
                st.dataframe(
                    diagnostic_table, width="stretch", hide_index=True,
                )
                st.caption(
                    "Residuals and distances are reported in annual decimal-return/volatility units. "
                    "No covariance regularization is applied; optimization failures are surfaced instead of replaced."
                )
            st.markdown("**Complete portfolio: risk-free asset plus tangency portfolio**")
            with st.container(horizontal=True):
                st.metric("Risky allocation", pct(complete_stats["Risky Portfolio Weight"]), border=True)
                st.metric("Risk-free allocation", pct(complete_stats["Risk-Free Asset Weight"]), border=True)
                st.metric("Expected return", pct(complete_stats["Optimizer Expected Return"]), border=True)
                st.metric("Volatility", pct(complete_stats["Optimizer Volatility"]), border=True)
            st.dataframe(complete_weights.to_frame(), width="stretch", column_config={
                "Complete Portfolio Weight": st.column_config.NumberColumn(format="percent")
            })
            st.caption(
                "This is a point on the non-leveraged CAL, not a recommendation. With zero risky allocation, expected return equals the entered risk-free rate and volatility is zero."
            )
            if complete_method == "Utility-Based Allocation":
                with st.container(horizontal=True):
                    st.metric(
                        "Unconstrained utility allocation",
                        pct(float(utility_result["Unconstrained Risky Portfolio Weight"])),
                        border=True,
                    )
                    st.metric("Applied non-leveraged allocation", pct(risky_allocation), border=True)
                    st.metric("Quadratic utility", ratio(float(utility_result["Quadratic Utility"]), 4), border=True)
                if utility_result["Allocation Constraint Binding"]:
                    st.warning(
                        "The unconstrained utility solution falls outside the permitted 0%–100% risky-allocation range. "
                        "PortfolioLens applies the selected long-only, non-leveraged constraint; it does not borrow, "
                        "use leverage, or short sell."
                    )
            utility_methodology = st.expander("Risk aversion and utility methodology")
            if utility_methodology.open:
                with utility_methodology:
                    st.write(
                        "The utility model uses U = E[rC] − ½AσC² and y* = (E[rT] − rf)/(AσT²). PortfolioLens applies "
                        "it to the historical long-only tangency estimate while retaining 0≤y≤1. The methodology does "
                        "not infer risk tolerance or suitability; the coefficient is an explicit user assumption."
                    )
            with st.container(horizontal=True):
                st.download_button(
                    "Download complete-portfolio weights", complete_weights.to_csv(),
                    "complete_portfolio_weights.csv", "text/csv",
                )
                st.download_button(
                    "Download efficient-frontier data", r["frontier"].to_csv(),
                    "efficient_frontier.csv", "text/csv",
                )
                st.download_button(
                    "Download frontier weights", r["frontier_weights"].to_csv(),
                    "frontier_weights.csv", "text/csv",
                )
            expected_assets = a.asset_returns.mean() * TRADING_DAYS
            with st.form("target_return_form", border=True):
                target_percent = st.number_input(
                    "Target arithmetic annual return (%)",
                    min_value=float(expected_assets.min() * 100),
                    max_value=float(expected_assets.max() * 100),
                    value=float(r["construction_stats"].loc["Current", "Optimizer Expected Return"] * 100),
                    step=0.25,
                )
                target_submit = st.form_submit_button("Construct target-return portfolio", icon=":material/target:")
            if target_submit:
                try:
                    target_weights = target_return_weights(a.asset_returns, target_percent / 100)
                    target_stats = optimizer_statistics(a.asset_returns, target_weights, r["risk_free"])
                    st.session_state["target_return_result"] = (target_weights, target_stats)
                except (ValueError, RuntimeError) as exc:
                    st.error(f"Target-return portfolio unavailable: {exc}")
            if "target_return_result" in st.session_state:
                target_weights, target_stats = st.session_state["target_return_result"]
                with st.container(horizontal=True):
                    st.metric("Target expected return", pct(target_stats["Optimizer Expected Return"]), border=True)
                    st.metric("Optimizer volatility", pct(target_stats["Optimizer Volatility"]), border=True)
                    st.metric("Optimizer Sharpe", ratio(target_stats["Optimizer Sharpe"]), border=True)
                st.dataframe(target_weights.rename("Target Weight").to_frame(), width="stretch", column_config={
                    "Target Weight": st.column_config.NumberColumn(format="percent")
                })
            constraints = st.expander("Custom construction constraints", icon=":material/rule:", on_change="rerun")
            if constraints.open:
                with constraints:
                    st.caption(
                        "Define every classification explicitly. PortfolioLens does not infer sectors or asset classes. "
                        "Excluding an asset sets its maximum weight to zero."
                    )
                    with st.form("constraint_form"):
                        objective = st.selectbox(
                            "Objective", ["Minimum Variance", "Maximum Sharpe", "Target Return"],
                        )
                        constraint_editor = st.data_editor(
                            pd.DataFrame({
                                "Ticker": r["tickers"], "Included": True,
                                "Minimum Weight (%)": 0.0, "Maximum Weight (%)": 100.0,
                                "User-defined Group": "",
                            }),
                            disabled=["Ticker"], hide_index=True, width="stretch", key="constraint_editor",
                            column_config={
                                "Included": st.column_config.CheckboxColumn(required=True),
                                "Minimum Weight (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, format="%.2f%%", required=True),
                                "Maximum Weight (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, format="%.2f%%", required=True),
                                "User-defined Group": st.column_config.TextColumn(help="Optional explicit group label, such as Growth."),
                            },
                        )
                        group_cap_text = st.text_input(
                            "Group caps (%)", placeholder="Growth:60, Defensive:50",
                            help="Optional comma-separated Group:percent pairs matching the editable group labels.",
                        )
                        constrained_target = st.number_input(
                            "Target arithmetic annual return (%)",
                            min_value=float(expected_assets.min() * 100),
                            max_value=float(expected_assets.max() * 100),
                            value=float(r["construction_stats"].loc["Current", "Optimizer Expected Return"] * 100),
                            step=0.25, help="Used only when the selected objective is Target Return.",
                        )
                        constraint_submit = st.form_submit_button(
                            "Run constrained optimization", type="primary", icon=":material/calculate:",
                        )
                    if constraint_submit:
                        try:
                            tickers_index = pd.Index(constraint_editor["Ticker"])
                            included = pd.Series(constraint_editor["Included"].to_numpy(dtype=bool), index=tickers_index)
                            minimums = pd.Series(
                                constraint_editor["Minimum Weight (%)"].to_numpy(dtype=float) / 100,
                                index=tickers_index,
                            )
                            maximums = pd.Series(
                                constraint_editor["Maximum Weight (%)"].to_numpy(dtype=float) / 100,
                                index=tickers_index,
                            )
                            minimums.loc[~included] = 0.0
                            maximums.loc[~included] = 0.0
                            groups = pd.Series(
                                constraint_editor["User-defined Group"].fillna("").astype(str).str.strip().to_numpy(),
                                index=tickers_index,
                            )
                            group_caps = parse_group_caps(group_cap_text)
                            constrained_weights = constrained_portfolio_weights(
                                a.asset_returns, objective, r["risk_free"],
                                constrained_target / 100 if objective == "Target Return" else None,
                                minimums, maximums, groups, group_caps,
                            )
                            constrained_stats = optimizer_statistics(
                                a.asset_returns, constrained_weights, r["risk_free"],
                            )
                            validation = constraint_validation_summary(
                                constrained_weights, minimums, maximums, groups, group_caps,
                            )
                            st.session_state["constrained_result"] = (
                                constrained_weights, constrained_stats, validation,
                            )
                        except (ValueError, RuntimeError) as exc:
                            st.error(f"Constrained optimization unavailable: {exc}")
                    if "constrained_result" in st.session_state:
                        constrained_weights, constrained_stats, validation = st.session_state["constrained_result"]
                        with st.container(horizontal=True):
                            st.metric("Expected return", pct(constrained_stats["Optimizer Expected Return"]), border=True)
                            st.metric("Volatility", pct(constrained_stats["Optimizer Volatility"]), border=True)
                            st.metric("Sharpe", ratio(constrained_stats["Optimizer Sharpe"]), border=True)
                        st.dataframe(constrained_weights.rename("Constrained Weight").to_frame(), width="stretch", column_config={
                            "Constrained Weight": st.column_config.NumberColumn(format="percent")
                        })
                        st.dataframe(validation, width="stretch", hide_index=True, column_config={
                            "Result": st.column_config.NumberColumn(format="percent"),
                            "Limit": st.column_config.NumberColumn(format="percent"),
                            "Pass": st.column_config.CheckboxColumn(),
                            "Breach": st.column_config.NumberColumn(format="percent"),
                        })
            optimized_weights = pd.DataFrame({
                "Current Portfolio": r["weights"],
                "Global Minimum Variance": a.allocations["Minimum Variance"],
                "Tangency (Maximum Sharpe)": a.allocations["Maximum Sharpe"],
            })
            if "target_return_result" in st.session_state:
                target_weights, _ = st.session_state["target_return_result"]
                optimized_weights["Target Return"] = target_weights
            optimized_weights = optimized_weights.reindex(complete_weights.index)
            optimized_weights["Complete Portfolio"] = complete_weights
            st.markdown("**Optimized weights**")
            st.dataframe(optimized_weights, width="stretch", column_config={
                column: st.column_config.NumberColumn(format="percent")
                for column in optimized_weights.columns
            })
            st.download_button(
                "Download optimized weights", optimized_weights.to_csv(),
                "portfolio_optimization_weights.csv", "text/csv",
            )
            st.caption(
                "All risky portfolios are long-only and fully invested. The complete portfolio adds the risk-free asset; "
                "historical arithmetic estimates are inputs, not forecasts or recommendations."
            )
        st.divider()
        st.markdown("### Rebalancing decision support")
        st.markdown("**Allocation weights and target trade plan**")
        st.dataframe(a.allocations, width="stretch", column_config={
            column: st.column_config.NumberColumn(format="percent") for column in a.allocations.columns
        })
        available = list(a.allocations.columns)
        if st.session_state.get("selected_target_method") not in available:
            st.session_state["selected_target_method"] = "Equal Weight" if "Equal Weight" in available else available[0]
        target_method = st.selectbox("Rebalance target", available, key="selected_target_method")
        plan = r["plans"][target_method]
        st.dataframe(plan, width="stretch", hide_index=True, column_config={
            "Current Weight": st.column_config.NumberColumn(format="percent"),
            "Target Weight": st.column_config.NumberColumn(format="percent"),
            "Weight Change": st.column_config.NumberColumn(format="percent"),
            "Current Dollar Allocation": st.column_config.NumberColumn(format="dollar"),
            "Target Dollar Allocation": st.column_config.NumberColumn(format="dollar"),
            "Estimated Buy / Sell": st.column_config.NumberColumn(format="dollar"),
        })
        st.caption("Positive estimated amounts are buys; negative amounts are sells. Totals reconcile before transaction costs and rounding.")
        st.download_button("Download rebalancing CSV", plan.to_csv(index=False), "rebalancing_plan.csv", "text/csv")
        st.markdown("**Rebalancing policy simulation**")
        st.caption(
            "Unlike the constant-weight analytical portfolio, these holdings drift with asset returns. Monthly, quarterly, and annual policies trade at completed period ends; "
            f"the threshold policy trades at {r['rebalancing_threshold']:.2%} maximum absolute drift. Costs apply only when trades occur."
        )
        st.dataframe(r["policy_summary"], width="stretch", column_config={
            column: st.column_config.NumberColumn(format="percent")
            for column in ["Total Return", "CAGR", "Annualized Volatility", "Maximum Drawdown", "Total Turnover", "Ending Maximum Drift"]
        } | {
            "Sharpe Ratio": st.column_config.NumberColumn(format="%.2f"),
            "Transaction Costs": st.column_config.NumberColumn(format="dollar"),
            "Rebalancing Dates": st.column_config.NumberColumn(format="%d"),
        })
        policies = list(r["policy_summary"].index)
        if st.session_state.get("selected_rebalancing_policy") not in policies:
            st.session_state["selected_rebalancing_policy"] = "Quarterly"
        selected_policy = st.selectbox(
            "Policy detail", policies, key="selected_rebalancing_policy",
            help="Select a policy to inspect value, drift, rebalance dates, and trades.",
        )
        policy_history = r["policy_histories"][selected_policy]
        line_chart(policy_history[["Portfolio Value"]], f"{selected_policy} portfolio value", "Value ($)")
        line_chart(policy_history[["Maximum Drift"]], f"{selected_policy} maximum drift", "Absolute weight drift")
        rebalance_dates = policy_history.loc[policy_history["Rebalanced"], ["Portfolio Value", "Turnover", "Transaction Costs"]]
        if rebalance_dates.empty:
            st.info("This policy produced no rebalancing dates in the selected history.")
        else:
            st.dataframe(rebalance_dates, width="stretch", column_config={
                "Portfolio Value": st.column_config.NumberColumn(format="dollar"),
                "Turnover": st.column_config.NumberColumn(format="percent"),
                "Transaction Costs": st.column_config.NumberColumn(format="dollar"),
            })
        selected_trades = r["policy_trades"][selected_policy]
        if selected_trades.empty:
            st.info("No trades were generated for this policy and sample.")
        else:
            st.dataframe(selected_trades, width="stretch", hide_index=True, column_config={
                "Date": st.column_config.DateColumn(format="MMM DD, YYYY"),
                "Before Weight": st.column_config.NumberColumn(format="percent"),
                "Target Weight": st.column_config.NumberColumn(format="percent"),
                "After Weight": st.column_config.NumberColumn(format="percent"),
                "Trade Before Cost": st.column_config.NumberColumn(format="dollar"),
                "Estimated Transaction Cost": st.column_config.NumberColumn(format="dollar"),
                "Drift Before Trade": st.column_config.NumberColumn(format="percent"),
            })
        with st.container(horizontal=True):
            st.download_button(
                "Download policy history", policy_history.to_csv(),
                f"{selected_policy.lower().replace(' ', '_')}_history.csv", "text/csv",
            )
            st.download_button(
                "Download trade history", selected_trades.to_csv(index=False),
                f"{selected_policy.lower().replace(' ', '_')}_trades.csv", "text/csv",
            )

if active_section == "Asset Allocation":
    with section_container:
        st.subheader("Asset Allocation")
        st.caption(
            "Compare the current security allocation with transparent long-only model portfolios. Ticker-to-asset-class labels are not inferred; "
            "group constraints require explicit user classifications in Portfolio Optimization."
        )
        st.markdown("### Current and model allocations")
        st.dataframe(a.allocations, width="stretch", column_config={
            column: st.column_config.NumberColumn(format="percent") for column in a.allocations.columns
        })
        st.markdown("### Risk and return comparison")
        st.dataframe(allocation_comparison, width="stretch", column_config={
            column: st.column_config.NumberColumn(format="percent")
            for column in ["Arithmetic Return", "CAGR", "Annualized Volatility", "Maximum Drawdown", "Largest Weight", "Weight Distance from Current"]
            if column in allocation_comparison.columns
        })
        st.markdown("### Current allocation contributions")
        allocation_contributions = pd.concat([a.return_contributions, a.volatility_contributions], axis=1)
        st.dataframe(allocation_contributions, width="stretch", column_config={
            column: st.column_config.NumberColumn(format="percent") for column in allocation_contributions.columns
        })
        selected_allocation = st.selectbox(
            "Allocation for implementation review", list(r["plans"]), key="asset_allocation_target"
        )
        st.markdown("### Implementation trades")
        st.dataframe(r["plans"][selected_allocation], width="stretch")
        st.caption(
            "Model allocations use historical arithmetic means and sample covariance. Implementation trades compare current holdings with the selected target at the entered portfolio value; "
            "they are not recommendations, strategic policy weights, or inferred suitability guidance."
        )
        with st.container(horizontal=True):
            st.download_button(
                "Download allocation comparison CSV", a.allocations.to_csv().encode("utf-8"),
                "portfoliolens_allocation_comparison.csv", "text/csv",
            )
            st.download_button(
                "Download allocation contributions CSV", allocation_contributions.to_csv().encode("utf-8"),
                "portfoliolens_allocation_contributions.csv", "text/csv",
            )
            st.download_button(
                "Download implementation trades CSV", r["plans"][selected_allocation].to_csv().encode("utf-8"),
                "portfoliolens_allocation_trades.csv", "text/csv",
            )

if active_section == "Portfolio Strategies & Momentum":
    with section_container:
        st.subheader(active_section)
        st.caption(
            f"Compare buy-and-hold and explicit rebalancing policies against {r['benchmark_ticker']} on one aligned history. "
            f"Initial value: {money(r['initial_value'])} · transaction-cost rate: {r['transaction_cost']:.2%} · "
            f"threshold band: {r['rebalancing_threshold']:.2%}."
        )
        st.markdown("### Rebalancing-policy comparison")
        st.dataframe(
            r["policy_summary"], width="stretch",
            column_config={
                column: st.column_config.NumberColumn(format="percent")
                for column in [
                    "Total Return", "CAGR", "Annualized Volatility", "Maximum Drawdown",
                    "Total Turnover", "Ending Maximum Drift", "Annualized Active Return",
                    "Mean Absolute Periodic Difference", "Tracking Error",
                ]
            } | {
                "Sharpe Ratio": st.column_config.NumberColumn(format="%.2f"),
                "Information Ratio": st.column_config.NumberColumn(format="%.2f"),
                "Transaction Costs": st.column_config.NumberColumn(format="dollar"),
                "Rebalancing Dates": st.column_config.NumberColumn(format="%d"),
            },
        )
        strategy_policies = list(r["policy_summary"].index)
        selected_strategy_policy = st.selectbox(
            "Strategy policy", strategy_policies, index=strategy_policies.index("Quarterly"),
            key="strategy_policy_detail",
        )
        strategy_history = r["policy_histories"][selected_strategy_policy]
        strategy_trades = r["policy_trades"][selected_strategy_policy]
        aligned_strategy = pd.concat([
            strategy_history["Daily Return"].rename(selected_strategy_policy),
            a.benchmark_returns.rename(r["benchmark_ticker"]),
        ], axis=1).dropna()
        strategy_growth = (1 + aligned_strategy).cumprod() * r["initial_value"]
        line_chart(strategy_growth, f"{selected_strategy_policy} versus {r['benchmark_ticker']}", "Portfolio value ($)")
        strategy_drawdowns = pd.concat([
            drawdown_series(aligned_strategy[selected_strategy_policy]).rename(selected_strategy_policy),
            drawdown_series(aligned_strategy[r["benchmark_ticker"]]).rename(r["benchmark_ticker"]),
        ], axis=1)
        line_chart(strategy_drawdowns, "Strategy drawdown comparison", "Drawdown")
        selected_policy_stats = r["policy_summary"].loc[selected_strategy_policy]
        with st.container(horizontal=True):
            st.metric("Active return", pct(selected_policy_stats["Annualized Active Return"]), border=True)
            st.metric("Tracking error", pct(selected_policy_stats["Tracking Error"]), border=True)
            st.metric("Information ratio", ratio(selected_policy_stats["Information Ratio"]), border=True)
            st.metric("Total turnover", pct(selected_policy_stats["Total Turnover"]), border=True)
        st.caption(
            "Buy and hold permits natural weight drift. Periodic policies trade only at completed month, quarter, or year ends; "
            "threshold rebalancing trades only after the configured absolute weight band is breached. Costs apply only on trade dates. "
            "Tracking error uses annualized sample standard deviation of daily active returns."
        )
        with st.container(horizontal=True):
            st.download_button(
                "Download strategy history", strategy_history.to_csv(),
                f"{selected_strategy_policy.lower().replace(' ', '_')}_strategy_history.csv", "text/csv",
            )
            st.download_button(
                "Download strategy trade log", strategy_trades.to_csv(index=False),
                f"{selected_strategy_policy.lower().replace(' ', '_')}_strategy_trades.csv", "text/csv",
            )

        st.divider()
        st.markdown("### Tactical momentum research")
        st.subheader(f"Dual-moving-average momentum · {r['strategy_asset']}")
        if not momentum.available:
            st.warning(
                "Momentum analysis was skipped because the selected period is too short."
                if momentum.reason == "insufficient_history" else momentum.detail
            )
            with st.container(horizontal=True):
                st.metric("Available observations", str(momentum.observations_available), border=True)
                st.metric("Required observations", str(momentum.observations_required), border=True)
            st.markdown("**Suggested action:** Choose an earlier start date.")
        else:
            strategy_data = momentum.data
            stats = momentum.metrics
            assert strategy_data is not None and stats is not None
            first_evaluation = strategy_data["Strategy Growth"].first_valid_index()
            st.caption(
                f"The first portfolio ticker is the explicit strategy instrument. Signals lag one trading day. "
                f"The shared strategy/buy-and-hold evaluation begins {first_evaluation.date()}."
            )
            with st.container(horizontal=True):
                st.metric("Strategy return", pct(stats["Total Return"]), border=True)
                st.metric("Buy & hold", pct(stats["Buy & Hold Total Return"]), border=True)
                st.metric("Position changes", str(stats["Position Changes"]), border=True)
                st.metric("Time in market", pct(stats["Time in Market"]), border=True)
            line_chart(strategy_data[["Price", "Short MA", "Long MA"]], "Price and moving averages", "Price")
            line_chart(strategy_data[["Strategy Growth", "Buy & Hold Growth"]], "Strategy versus buy-and-hold", "Growth of $1")
            dd_compare = pd.concat([
                drawdown_series(strategy_data.loc[first_evaluation:, "Strategy Return"]).rename("Strategy"),
                drawdown_series(strategy_data.loc[first_evaluation:, "Buy & Hold Return"]).rename("Buy & hold"),
            ], axis=1)
            line_chart(dd_compare, "Drawdown comparison", "Drawdown")
            st.dataframe(display_metric_frame(stats), width="stretch")
            st.download_button("Download strategy results CSV", strategy_data.to_csv(), "strategy_results.csv", "text/csv")

if active_section == "Stress Testing":
    with section_container:
        st.subheader("Custom shock test")
        st.caption("No asset classes are inferred. Enter a direct shock for every holding.")
        shock_seed = st.session_state["current_shocks"]
        edited = st.data_editor(
            pd.DataFrame({"Ticker": r["tickers"], "Shock (%)": [shock_seed[x] * 100 for x in r["tickers"]]}),
            disabled=["Ticker"], hide_index=True, width="stretch", key="shock_editor",
            column_config={"Shock (%)": st.column_config.NumberColumn(format="%.2f%%", required=True)},
        )
        shock_values = pd.Series(edited["Shock (%)"].to_numpy(dtype=float) / 100, index=edited["Ticker"])
        st.session_state["current_shocks"] = shock_values
        shock_table, shock_summary = custom_shock(r["weights"], shock_values, r["initial_value"])
        with st.container(horizontal=True):
            st.metric("Estimated impact", pct(shock_summary["Estimated Portfolio Impact"]), border=True)
            st.metric("After-shock value", money(shock_summary["After Value"]), border=True)
            st.metric("Largest loss contributor", shock_summary["Largest Loss Contributor"], border=True)
        st.dataframe(shock_table, width="stretch", column_config={
            "Weight": st.column_config.NumberColumn(format="percent"),
            "Shock": st.column_config.NumberColumn(format="percent"),
            "Portfolio Impact": st.column_config.NumberColumn(format="percent"),
            "Dollar Impact": st.column_config.NumberColumn(format="dollar"),
        })
        st.download_button("Download stress-test CSV", shock_table.to_csv(), "stress_test.csv", "text/csv")
        st.markdown("#### Historical windows")
        if r["historical"].empty:
            st.info("The selected common history does not fully cover a configured historical stress window.")
        else:
            st.dataframe(r["historical"], width="stretch", hide_index=True, column_config={
                "Portfolio Return": st.column_config.NumberColumn(format="percent"),
                "Benchmark Return": st.column_config.NumberColumn(format="percent"),
            })

if active_section == "Research Workspace":
    with section_container:
        st.subheader("Investment research workspace")
        with st.container(horizontal=True):
            st.metric("Portfolio Health Score", f"{health_score:.0f}/100", border=True)
            st.metric("Metric coverage", pct(health_coverage), border=True)
            st.metric("Compared portfolios", str(len(allocation_comparison)), border=True)
            st.metric("Traceable insights", str(len(insights)), border=True)
        st.caption(
            "The score is a bounded historical diagnostic. Every component, threshold, and point is disclosed below; "
            "it does not measure investor suitability or forecast performance."
        )
        st.markdown("**Health Score components**")
        st.dataframe(
            health_components, width="stretch",
            column_config={
                "Weight": st.column_config.NumberColumn(format="percent"),
                "Metric Value": st.column_config.NumberColumn(format="%.4f"),
                "Normalized Result": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent"),
                "Points": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        st.markdown("**Portfolio comparison**")
        st.dataframe(
            allocation_comparison, width="stretch",
            column_config={
                column: st.column_config.NumberColumn(format="percent")
                for column in ["Arithmetic Return", "CAGR", "Annualized Volatility", "Maximum Drawdown", "Largest Weight", "Weight Distance from Current"]
            },
        )
        st.caption("Each portfolio uses the same asset history, constant-weight return model, arithmetic Sharpe convention, and risk-free assumption. Weight distance is one-half the absolute allocation difference from current weights; it is not simulated turnover.")
        st.markdown("**Deterministic investment insights**")
        st.dataframe(insights, width="stretch", hide_index=True, column_config={
            "Value": st.column_config.NumberColumn(format="%.4f"),
        })
        st.caption("Observations are selected by the displayed rules using computed metrics only. They are not generated by an LLM and do not recommend trades.")

        st.markdown("**Interactive what-if analysis**")
        st.caption("Set hypothetical long-only weights and explicit instantaneous shocks. Submit to compare the scenario with the current constant-weight portfolio.")
        with st.form("what_if_form"):
            weight_editor = st.data_editor(
                pd.DataFrame({
                    "Ticker": r["tickers"],
                    "Weight (%)": [st.session_state["what_if_weights"][ticker] * 100 for ticker in r["tickers"]],
                }),
                disabled=["Ticker"], hide_index=True, width="stretch", key="what_if_weight_editor",
                column_config={"Weight (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, format="%.2f%%", required=True)},
            )
            shock_editor = st.data_editor(
                pd.DataFrame({
                    "Ticker": r["tickers"],
                    "Shock (%)": [st.session_state["what_if_shocks"][ticker] * 100 for ticker in r["tickers"]],
                }),
                disabled=["Ticker"], hide_index=True, width="stretch", key="what_if_shock_editor",
                column_config={"Shock (%)": st.column_config.NumberColumn(format="%.2f%%", required=True)},
            )
            submit_what_if = st.form_submit_button("Run what-if analysis", type="primary", icon=":material/science:")
        if submit_what_if:
            try:
                scenario_weights = pd.Series(
                    weight_editor["Weight (%)"].to_numpy(dtype=float) / 100,
                    index=weight_editor["Ticker"], dtype=float,
                )
                scenario_shocks = pd.Series(
                    shock_editor["Shock (%)"].to_numpy(dtype=float) / 100,
                    index=shock_editor["Ticker"], dtype=float,
                )
                scenario_result = what_if_analysis(
                    a.asset_returns, r["weights"], scenario_weights, scenario_shocks,
                    r["initial_value"], r["risk_free"],
                )
                st.session_state["what_if_weights"] = scenario_weights
                st.session_state["what_if_shocks"] = scenario_shocks
                st.session_state["what_if_result"] = scenario_result
            except ValueError as exc:
                st.error(f"What-if analysis could not run: {exc}")
        if "what_if_result" in st.session_state:
            scenario_comparison, scenario_shock_table, scenario_summary = st.session_state["what_if_result"]
            with st.container(horizontal=True):
                st.metric("Scenario shock impact", pct(scenario_summary["Estimated Portfolio Impact"]), border=True)
                st.metric("After-shock value", money(scenario_summary["After Value"]), border=True)
                st.metric("Largest loss contributor", str(scenario_summary["Largest Loss Contributor"]), border=True)
            st.dataframe(scenario_comparison, width="stretch", column_config={
                column: st.column_config.NumberColumn(format="percent")
                for column in ["Arithmetic Return", "CAGR", "Annualized Volatility", "Maximum Drawdown", "Largest Weight", "Weight Distance from Current"]
            })
            st.dataframe(scenario_shock_table, width="stretch", column_config={
                "Weight": st.column_config.NumberColumn(format="percent"),
                "Shock": st.column_config.NumberColumn(format="percent"),
                "Portfolio Impact": st.column_config.NumberColumn(format="percent"),
                "Dollar Impact": st.column_config.NumberColumn(format="dollar"),
            })

if active_section == "Research Report":
    with section_container:
        st.subheader("Deterministic investment-research report")
        current_shocks = st.session_state["current_shocks"]
        shock_table, shock_summary = custom_shock(r["weights"], current_shocks, r["initial_value"])
        summary = research_summary(
            a.performance, a.benchmark, r["weights"], a.return_contributions,
            a.volatility_contributions, momentum.metrics, shock_summary,
        )
        for item in summary:
            st.write("• " + item)
        attribution = pd.concat([a.return_contributions, a.volatility_contributions], axis=1)
        risk_values = {
            "Historical VaR (95%)": historical_var(a.portfolio_returns),
            "Historical CVaR (95%)": historical_cvar(a.portfolio_returns),
            "Effective Number of Holdings": 1 / float((r["weights"] ** 2).sum()),
        }
        selected_target = st.session_state.get("selected_target_method", "Equal Weight")
        if selected_target not in r["plans"]:
            selected_target = next(iter(r["plans"]))
        report_policy = st.session_state.get("selected_rebalancing_policy", "Quarterly")
        if report_policy not in r["policy_histories"]:
            report_policy = "Quarterly"
        constrained_report = st.session_state.get("constrained_result")
        report_security = security_single_index_table(a.asset_returns, a.benchmark_returns, r["risk_free"])
        report_capm = capm_security_table(a.asset_returns, a.benchmark_returns, r["risk_free"])
        report_etf = etf_research_metrics(a.asset_returns, r["risk_free"])
        report_screen = rank_security_candidates(report_security)
        report_evaluation = pd.DataFrame({
            "Portfolio": a.performance,
            "Benchmark-relative": a.benchmark,
        })
        fixed_income_report: dict[str, pd.DataFrame | pd.Series | str] = {}
        calculator_result = st.session_state.get("fi_calculator_result")
        if calculator_result is not None:
            terms = calculator_result["terms"]
            fixed_income_report["bond inputs"] = pd.Series({
                "Face value": terms.face_value,
                "Coupon rate": terms.coupon_rate,
                "Coupon frequency": terms.frequency,
                "Settlement": str(terms.settlement),
                "Maturity": str(terms.maturity),
                "Day count": terms.day_count,
            })
            fixed_income_report["bond analytics"] = pd.Series(calculator_result["metrics"])
            fixed_income_report["cash-flow schedule"] = calculator_result["cash_flows"]
            fixed_income_report["bond yield shock"] = pd.Series(calculator_result["scenario"])
        bond_analysis = st.session_state.get("fi_portfolio_analysis")
        if bond_analysis is not None:
            fixed_income_report["portfolio summary"] = bond_analysis.summary
            fixed_income_report["portfolio holdings and contributions"] = bond_analysis.holdings
        bond_scenario = st.session_state.get("fi_portfolio_scenario")
        if bond_scenario is not None:
            fixed_income_report["portfolio rate scenario summary"] = bond_scenario[1]
            fixed_income_report["portfolio rate scenario detail"] = bond_scenario[0]
        bond_selection = st.session_state.get("fi_selection_result")
        if bond_selection is not None:
            fixed_income_report["selection formula"] = bond_selection[1]
            fixed_income_report["selected bonds"] = bond_selection[0]
        bond_construction = st.session_state.get("fi_construction_result")
        if bond_construction is not None:
            fixed_income_report["constructed portfolio weights"] = bond_construction[0]
            fixed_income_report["constructed portfolio summary"] = bond_construction[1]
            fixed_income_report["construction constraints"] = bond_construction[2]
        report = generate_html_report(
            title="PortfolioLens Investment Research Report", tickers=r["tickers"], weights=r["weights"],
            start=a.prices.index.min().date(), end=a.prices.index.max().date(), summary=summary,
            performance=metric_frame(a.performance), risk=metric_frame(risk_values),
            benchmark=metric_frame(a.benchmark), attribution=attribution, allocations=a.allocations,
            rebalancing=r["plans"][selected_target], rebalancing_method=selected_target,
            strategy=(metric_frame(momentum.metrics) if momentum.metrics is not None else None),
            strategy_status=momentum.detail, stress=shock_table,
            benchmark_ticker=r["benchmark_ticker"], risk_free_rate=r["risk_free"],
            initial_value=r["initial_value"], health_score=health_score,
            health_coverage=health_coverage, health_components=health_components,
            comparison=allocation_comparison, insights=insights,
            what_if=st.session_state.get("what_if_result", (None, None, None))[0],
            efficient_frontier=r["frontier"] if not r["frontier"].empty else None,
            optimized_allocations=r["frontier_weights"] if not r["frontier_weights"].empty else None,
            rebalancing_policies=r["policy_summary"],
            rebalancing_history=r["policy_histories"][report_policy],
            constrained_allocation=(
                constrained_report[0].rename("Constrained Weight").to_frame()
                if constrained_report is not None else None
            ),
            constraint_validation=constrained_report[2] if constrained_report is not None else None,
            transaction_cost_rate=r["transaction_cost"],
            rebalancing_threshold=r["rebalancing_threshold"],
            selected_rebalancing_policy=report_policy,
            strategy_short_window=r["short_window"], strategy_long_window=r["long_window"],
            security_analysis=report_security,
            asset_pricing=report_capm,
            performance_evaluation=report_evaluation,
            etf_research=report_etf,
            security_screen=report_screen,
            fixed_income=fixed_income_report or None,
        )
        downloads = {
            "Performance metrics": metric_frame(a.performance).to_csv(),
            "Asset metrics": attribution.to_csv(),
            "Daily returns": a.asset_returns.assign(Portfolio=a.portfolio_returns).to_csv(),
            "Portfolio comparison": allocation_comparison.to_csv(),
            "Efficient frontier": r["frontier"].to_csv(),
            "Frontier weights": r["frontier_weights"].to_csv(),
            "Rebalancing policies": r["policy_summary"].to_csv(),
            "Deterministic insights": insights.to_csv(index=False),
            "Security analysis": report_security.to_csv(),
            "CAPM analysis": report_capm.to_csv(),
            "Performance evaluation": report_evaluation.to_csv(),
            "ETF research": report_etf.to_csv(),
            "Security screen": report_screen.to_csv(),
        }
        if bond_analysis is not None:
            downloads["Bond portfolio analytics"] = bond_analysis.holdings.to_csv(index=False)
        if bond_scenario is not None:
            downloads["Bond rate scenario"] = bond_scenario[0].to_csv(index=False)
        if bond_selection is not None:
            downloads["Selected bonds"] = bond_selection[0].to_csv(index=False)
        with st.container(horizontal=True):
            st.download_button("Download HTML report", report, "portfoliolens_research_report.html", "text/html")
            for label, payload in downloads.items():
                st.download_button(label + " CSV", payload, label.lower().replace(" ", "_") + ".csv", "text/csv")

if active_section == "ETF Research":
    with section_container:
        st.subheader("ETF Research")
        st.caption(
            "Research the user-selected universe using aligned historical returns, then optionally upload disclosed holdings "
            "for look-through analysis. Results are diagnostics, not fund ratings or investment recommendations."
        )
        with st.container(horizontal=True):
            st.metric("Pipeline status", "Ready", border=True)
            st.metric("Universe", f"{len(a.asset_returns.columns)} securities", border=True)
            st.metric("Holdings look-through", "Optional upload", border=True)
            st.metric("Optimization route", "Portfolio Construction", border=True)
        st.markdown("### Universe research")
        filter_columns = st.columns(3)
        min_history = filter_columns[0].number_input(
            "Minimum observations", min_value=2, value=60, step=1, key="etf_min_observations"
        )
        min_sharpe = filter_columns[1].number_input(
            "Minimum Sharpe ratio", value=0.50, step=0.05, key="etf_min_sharpe"
        )
        max_volatility = filter_columns[2].number_input(
            "Maximum annualized volatility (%)", min_value=0.0, value=25.0, step=1.0,
            key="etf_max_volatility",
        ) / 100
        universe_metrics = etf_research_metrics(a.asset_returns, r["risk_free"])
        screened_universe = filter_etf_research(
            universe_metrics, int(min_history), float(min_sharpe), float(max_volatility)
        )
        st.dataframe(
            universe_metrics, width="stretch",
            column_config={
                "Historical Arithmetic Return": st.column_config.NumberColumn(format="percent"),
                "Volatility": st.column_config.NumberColumn(format="percent"),
                "Cumulative Return": st.column_config.NumberColumn(format="percent"),
                "Maximum Drawdown": st.column_config.NumberColumn(format="percent"),
            },
        )
        st.caption(
            f"{len(screened_universe)} of {len(universe_metrics)} analyzed symbols pass the selected history, Sharpe, and volatility filters. "
            "Expected-return estimates are historical arithmetic annualized means; volatility uses annualized sample standard deviation."
        )
        st.download_button(
            "Download universe research CSV", universe_metrics.to_csv().encode("utf-8"),
            "portfoliolens_etf_universe_research.csv", "text/csv",
        )

        st.markdown("### Security screening")
        security_screen = rank_security_candidates(
            security_single_index_table(a.asset_returns, a.benchmark_returns, r["risk_free"]),
            minimum_alpha=0.0, maximum_p_value=0.10, minimum_observations=int(min_history),
        )
        screen_columns = [
            "Passes Screen", "Regression Alpha", "Alpha p-Value", "Beta", "R-Squared",
            "Residual Volatility", "Alpha / Residual Variance", "Regression Observations",
        ]
        st.dataframe(
            security_screen[screen_columns], width="stretch",
            column_config={
                "Regression Alpha": st.column_config.NumberColumn(format="percent"),
                "R-Squared": st.column_config.NumberColumn(format="percent"),
                "Residual Volatility": st.column_config.NumberColumn(format="percent"),
            },
        )
        st.caption(
            f"Screen: annualized regression alpha > 0%, two-sided alpha p-value ≤ 10%, and at least {int(min_history)} observations. "
            "Historical alpha and significance do not imply persistence. Portfolio construction remains in the Portfolio Optimization workspace."
        )
        st.download_button(
            "Download security screen CSV", security_screen.to_csv().encode("utf-8"),
            "portfoliolens_security_screen.csv", "text/csv",
        )

        st.markdown("### Holdings look-through")
        holdings_template = pd.DataFrame({
            "ETF": [a.asset_returns.columns[0]], "Security": ["EXAMPLE"], "Holding Weight": [0.05]
        })
        st.download_button(
            "Download holdings template", holdings_template.to_csv(index=False).encode("utf-8"),
            "portfoliolens_holdings_template.csv", "text/csv",
        )
        holdings_file = st.file_uploader(
            "Upload disclosed holdings CSV",
            type=["csv"],
            help="Required columns: ETF, Security, Holding Weight. Weights may be decimals or percentages.",
        )
        if holdings_file is None:
            st.info("Upload a holdings CSV to calculate disclosed-weight coverage, consolidated underlying exposure, and pairwise ETF overlap.")
        else:
            try:
                normalized_holdings = parse_holdings_csv(holdings_file.getvalue())
                relevant_allocations = r["weights"].reindex(
                    sorted(normalized_holdings["ETF"].unique()), fill_value=0.0
                )
                coverage = holdings_coverage(normalized_holdings)
                overlap = etf_overlap(normalized_holdings)
                st.markdown("**Disclosure coverage**")
                st.dataframe(coverage, width="stretch", column_config={
                    "Disclosed Weight": st.column_config.NumberColumn(format="percent")
                })
                if relevant_allocations.sum() == 0:
                    exposure = pd.DataFrame(columns=["Portfolio Exposure"])
                    st.warning("Uploaded ETF symbols do not match the current portfolio, so portfolio-level exposure is zero.")
                else:
                    exposure = consolidated_security_exposure(normalized_holdings, relevant_allocations)
                    st.markdown("**Consolidated underlying exposure**")
                    st.dataframe(exposure, width="stretch", column_config={
                        "Portfolio Exposure": st.column_config.NumberColumn(format="percent")
                    })
                st.markdown("**Pairwise ETF overlap**")
                st.dataframe(overlap, width="stretch", hide_index=True, column_config={
                    "Constituent Jaccard": st.column_config.NumberColumn(format="percent"),
                    "Weighted Overlap": st.column_config.NumberColumn(format="percent"),
                })
                st.download_button(
                    "Download consolidated exposure CSV", exposure.to_csv().encode("utf-8"),
                    "portfoliolens_consolidated_exposure.csv", "text/csv",
                )
                st.download_button(
                    "Download ETF overlap CSV", overlap.to_csv(index=False).encode("utf-8"),
                    "portfoliolens_etf_overlap.csv", "text/csv",
                )
            except ValueError as exc:
                st.error(f"Holdings analysis could not run: {exc}")
        st.caption(
            "Holdings are user-supplied and may omit cash, derivatives, or minor positions. PortfolioLens does not infer stale dates, "
            "issuer classifications, or undisclosed exposures. Weight overlap is the sum of pairwise minimum disclosed weights."
        )

if active_section == "Methodology & Limitations":
    with section_container:
        st.subheader("Methodology and limitations")
        st.caption(f"Application build: `{build_identifier()}`")
        st.markdown("""
**Returns and annualization.** Adjusted prices are converted to simple daily returns. Historical arithmetic annualized return is the daily sample mean × 252 and is the expected-return estimate used by Sharpe, Sortino, and maximum-Sharpe optimization. CAGR separately measures realized compound growth. Annualized variance is the daily sample variance × 252; volatility is its square root. Performance Sharpe and optimizer Sharpe both equal arithmetic annualized excess return divided by annualized volatility. Sortino uses the same arithmetic excess-return numerator and target downside deviation after converting the annual risk-free rate to an equivalent daily minimum acceptable return.

**Data and missing values.** yfinance is the sole data source. Holdings are aligned to complete common trading dates; prices are never filled or invented. Any unavailable requested ticker stops the analysis. The benchmark is downloaded separately and then inner-aligned for comparison.

**Risk and benchmark regression.** Historical 95% VaR and CVaR are nonnegative loss measures based on the empirical lower tail. The single-index model regresses aligned daily portfolio excess returns on benchmark excess returns. Its intercept and residual volatility are annualized; beta is the fitted slope; R² is the explained share of variation. Systematic and idiosyncratic variance are shown separately. CAPM required return, Jensen’s alpha, and Treynor use the same arithmetic return and annual risk-free assumptions. These are historical sample estimates, not forecasts or evidence of manager skill. Euler volatility contributions use the annualized sample covariance matrix and sum to portfolio volatility. Drawdowns include the initial portfolio value as the first peak.

**Portfolio construction.** Baseline analytics and historical stress periods use constant long-only weights. Equal weight and inverse volatility are deterministic comparison allocations; inverse volatility is not described as risk parity. The efficient frontier, global minimum-variance, maximum-Sharpe, and target-return portfolios use historical arithmetic annualized returns and the annualized sample covariance matrix. SLSQP portfolios have weights in [0,1] summing to one, with no leverage or short selling; custom asset bands, exclusions, and explicit user-defined group caps receive a separate feasibility check. The Capital Allocation Line is analytical and nonleveraged. A complete portfolio combines 0–100% in the long-only tangency portfolio with the remainder in the risk-free asset; borrowing and leverage are not modeled. Optimization failure is shown rather than replaced, and optimized portfolios are neither forecasts nor recommendations.

**Rebalancing simulation.** Rebalancing is a separate holdings-level simulation, not part of the constant-weight baseline. Buy-and-hold, monthly, quarterly, annual, and threshold policies allow weights to drift between trade dates. One-way turnover is half the gross traded value divided by pre-trade portfolio value; proportional transaction costs apply only when trades occur. Trade history records rebalancing dates and before/after allocations.

**Research diagnostics.** Portfolio comparison applies the same return history and methodology to each allocation. The Health Score is an explicitly weighted heuristic built from diversification, Sharpe, maximum drawdown, daily CVaR, and information ratio; unavailable components are excluded and metric coverage is disclosed. What-if analysis uses hypothetical long-only weights and explicit shocks without changing the saved portfolio. Deterministic insights are fixed rules tied to displayed metrics and contain no LLM-generated content or investment recommendations.

**Strategy.** The first requested holding is the explicit strategy instrument. It is long when its short moving average exceeds its long moving average, otherwise cash. Positions lag signals by one full day. Strategy and buy-and-hold statistics use the same post-warm-up period. Proportional transaction costs apply to every position change; no automatic parameter search is performed.

**Limitations.** yfinance can be delayed, revised, incomplete, or unavailable. Results exclude taxes, liquidity constraints, market impact, and slippage beyond the configured cost. Historical stress results appear only when full configured windows are covered. This application is for historical investment research only and is not personalized financial advice.
""")

render_footer()
