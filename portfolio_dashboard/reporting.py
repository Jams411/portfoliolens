"""Deterministic research narrative and deployment-safe HTML report."""
from datetime import datetime, timezone
from html import escape
import pandas as pd

from .formatting import metric_value

def _pct(value: object) -> str:
    try:
        return f"{float(value):.2%}" if pd.notna(value) else "N/A"
    except (TypeError, ValueError):
        return "N/A"

def research_summary(performance: dict[str, float], benchmark: dict[str, float], weights: pd.Series,
                     return_contrib: pd.Series, risk_contrib: pd.Series,
                     strategy_metrics: dict[str, float] | None, stress_summary: dict[str, object]) -> list[str]:
    """Create careful, rules-based observations without investment advice."""
    excess = benchmark.get("Excess Return", float("nan"))
    comparison = "could not be compared with" if pd.isna(excess) else "exceeded" if excess > 0 else "trailed" if excess < 0 else "matched"
    effective = 1 / float((weights ** 2).sum())
    concentration = "concentrated" if weights.max() >= 0.5 or effective < max(1.5, len(weights) / 2) else "moderately diversified"
    strategy_metrics = strategy_metrics or {}
    strat_excess = strategy_metrics.get("Total Return", float("nan")) - strategy_metrics.get("Buy & Hold Total Return", float("nan"))
    strat_text = "outpaced" if strat_excess > 0 else "lagged" if strat_excess < 0 else "matched"
    benchmark_amount = "an unavailable amount" if pd.isna(excess) else f"{abs(excess):.2%}"
    strategy_observation = (
        "The momentum strategy was unavailable for the selected period."
        if pd.isna(strat_excess)
        else f"The momentum strategy {strat_text} buy-and-hold by {abs(strat_excess):.2%}, after configured transaction costs."
    )
    return [f"The portfolio {comparison} the benchmark by {benchmark_amount} over the selected period.",
            f"Annualized volatility was {_pct(performance.get('Annualized Volatility'))}; maximum drawdown was {_pct(performance.get('Maximum Drawdown'))}.",
            f"{risk_contrib.idxmax()} was the largest volatility contributor and {return_contrib.idxmax()} was the largest total-return contributor.",
            f"The weight profile appears {concentration}; its effective number of holdings is {effective:.2f}.",
            strategy_observation,
            f"The selected custom shock implies an estimated portfolio impact of {_pct(stress_summary.get('Estimated Portfolio Impact'))}."]

def _table(frame: pd.DataFrame) -> str:
    return frame.to_html(index=True, border=0, classes="data", na_rep="N/A", float_format=lambda x: f"{x:.4f}")


def _metric_table(frame: pd.DataFrame) -> str:
    """Render a one-column metric frame using semantically correct units."""
    formatted = frame.copy().astype(object)
    if "Value" in formatted.columns:
        formatted["Value"] = [metric_value(str(name), value) for name, value in frame["Value"].items()]
    return _table(formatted)


def _percentage_table(frame: pd.DataFrame) -> str:
    formatted = frame.copy().astype(object)
    for column in formatted.columns:
        formatted[column] = formatted[column].map(_pct)
    return _table(formatted)


def _financial_table(frame: pd.DataFrame) -> str:
    """Format mixed financial tables without changing their underlying exports."""
    formatted = frame.copy().astype(object)
    percent_columns = {"Weight", "Shock", "Portfolio Impact", "Current Weight", "Target Weight", "Weight Change"}
    money_columns = {"Dollar Impact", "Current Dollar Allocation", "Target Dollar Allocation", "Estimated Buy / Sell"}
    for column in formatted.columns:
        if column in percent_columns:
            formatted[column] = frame[column].map(_pct)
        elif column in money_columns:
            formatted[column] = frame[column].map(
                lambda value: f"${float(value):,.2f}" if pd.notna(value) else "N/A"
            )
    return _table(formatted)


def _comparison_table(frame: pd.DataFrame) -> str:
    formatted = frame.copy().astype(object)
    percent_columns = {
        "Total Return", "Arithmetic Return", "CAGR", "Annualized Volatility", "Maximum Drawdown",
        "Largest Weight", "Weight Distance from Current", "Target Return",
        "Optimizer Expected Return", "Optimizer Volatility",
        "Total Turnover", "Ending Maximum Drift",
        "Historical Arithmetic Return", "Volatility", "Cumulative Return",
        "Regression Alpha", "R-Squared", "Residual Volatility", "Systematic Volatility",
        "Systematic Risk Share", "Idiosyncratic Risk Share", "Jensen's Alpha",
        "CAPM Required Return", "Annualized Active Return", "Tracking Error",
    }
    for column in formatted.columns:
        if column in percent_columns:
            formatted[column] = frame[column].map(_pct)
        else:
            formatted[column] = frame[column].map(
                lambda value: (
                    f"{float(value):.2f}" if pd.notna(value) and pd.api.types.is_number(value)
                    else (str(value) if pd.notna(value) else "N/A")
                )
            )
    return _table(formatted)


def _health_table(frame: pd.DataFrame) -> str:
    formatted = frame.copy().astype(object)
    for column in ("Weight", "Normalized Result"):
        if column in formatted:
            formatted[column] = frame[column].map(_pct)
    if "Points" in formatted:
        formatted["Points"] = frame["Points"].map(
            lambda value: f"{float(value):.1f}" if pd.notna(value) else "N/A"
        )
    return _table(formatted)


def _constraint_table(frame: pd.DataFrame) -> str:
    formatted = frame.copy().astype(object)
    for column in ("Result", "Limit", "Breach"):
        if column in formatted:
            formatted[column] = frame[column].map(_pct)
    return _table(formatted)


def _fixed_income_report_sections(
    fixed_income: dict[str, pd.DataFrame | pd.Series | str] | None,
) -> list[tuple[str, str]]:
    """Render only completed fixed-income outputs supplied by the application."""
    if not fixed_income:
        return []
    rendered: list[tuple[str, str]] = []
    for name, value in fixed_income.items():
        if isinstance(value, pd.Series):
            content = _table(value.rename("Value").to_frame())
        elif isinstance(value, pd.DataFrame):
            if value.empty:
                continue
            content = _table(value)
        elif value:
            content = f"<p>{escape(str(value))}</p>"
        else:
            continue
        rendered.append((f"Fixed income — {name}", content))
    if rendered:
        rendered.append((
            "Fixed-income limitations",
            "<p>Bond prices use explicit option-free contractual cash flows and nominal annual YTM compounded at "
            "the coupon frequency. Portfolio YTM is a market-value-weighted descriptive average, not a portfolio "
            "IRR. Parallel yield shifts do not capture curve-shape, spread, liquidity, optionality, credit, tax, or "
            "liability risk. Outputs are research diagnostics, not personalized investment advice.</p>",
        ))
    return rendered

def generate_html_report(*, title: str, tickers: list[str], weights: pd.Series, start: object, end: object,
                         summary: list[str], performance: pd.DataFrame, risk: pd.DataFrame,
                         benchmark: pd.DataFrame, attribution: pd.DataFrame, allocations: pd.DataFrame,
                         rebalancing: pd.DataFrame, rebalancing_method: str,
                         strategy: pd.DataFrame | None, stress: pd.DataFrame,
                         strategy_status: str | None = None,
                         benchmark_ticker: str | None = None, risk_free_rate: float | None = None,
                         initial_value: float | None = None, health_score: float | None = None,
                         health_coverage: float | None = None, health_components: pd.DataFrame | None = None,
                         comparison: pd.DataFrame | None = None, insights: pd.DataFrame | None = None,
                         what_if: pd.DataFrame | None = None, efficient_frontier: pd.DataFrame | None = None,
                         optimized_allocations: pd.DataFrame | None = None,
                         rebalancing_policies: pd.DataFrame | None = None,
                         rebalancing_history: pd.DataFrame | None = None,
                         constrained_allocation: pd.DataFrame | None = None,
                         constraint_validation: pd.DataFrame | None = None,
                         transaction_cost_rate: float | None = None,
                         rebalancing_threshold: float | None = None,
                         selected_rebalancing_policy: str | None = None,
                         strategy_short_window: int | None = None,
                         strategy_long_window: int | None = None,
                         security_analysis: pd.DataFrame | None = None,
                         asset_pricing: pd.DataFrame | None = None,
                         performance_evaluation: pd.DataFrame | None = None,
                         etf_research: pd.DataFrame | None = None,
                         security_screen: pd.DataFrame | None = None,
                         fixed_income: dict[str, pd.DataFrame | pd.Series | str] | None = None) -> bytes:
    """Generate a self-contained, deterministic investment research report."""
    assumptions = [
        "Daily simple returns and a 252-trading-day annualization convention.",
        "Constant long-only weights for historical portfolio analytics.",
        "Historical estimates are descriptive and are not forecasts or recommendations.",
    ]
    if benchmark_ticker:
        assumptions.append(f"Benchmark: {escape(benchmark_ticker)}.")
    if risk_free_rate is not None:
        assumptions.append(f"Annual risk-free assumption: {risk_free_rate:.2%}.")
    if initial_value is not None:
        assumptions.append(f"Illustrative initial portfolio value: ${initial_value:,.2f}.")
    if transaction_cost_rate is not None:
        assumptions.append(f"Proportional transaction-cost rate: {transaction_cost_rate:.2%}.")
    if rebalancing_threshold is not None:
        assumptions.append(f"Threshold-policy absolute weight-drift trigger: {rebalancing_threshold:.2%}.")
    if selected_rebalancing_policy:
        assumptions.append(f"Detailed rebalancing policy: {escape(selected_rebalancing_policy)}.")
    input_rows = {
        "Holdings": ", ".join(tickers), "Analysis start": str(start), "Analysis end": str(end),
        "Benchmark": benchmark_ticker or "N/A",
        "Initial value": f"${initial_value:,.2f}" if initial_value is not None else "N/A",
        "Annual risk-free rate": f"{risk_free_rate:.2%}" if risk_free_rate is not None else "N/A",
        "Transaction-cost rate": f"{transaction_cost_rate:.2%}" if transaction_cost_rate is not None else "N/A",
        "Rebalancing threshold": f"{rebalancing_threshold:.2%}" if rebalancing_threshold is not None else "N/A",
        "Momentum windows": (
            f"{strategy_short_window}/{strategy_long_window} trading days"
            if strategy_short_window is not None and strategy_long_window is not None else "N/A"
        ),
    }
    health_content = "<p>Health diagnostic unavailable.</p>"
    if health_score is not None and pd.notna(health_score) and health_components is not None:
        coverage = "N/A" if health_coverage is None else f"{health_coverage:.0%}"
        health_content = (
            f"<div class='score'><strong>{health_score:.0f}/100</strong><span>Historical diagnostic · {coverage} metric coverage</span></div>"
            + _health_table(health_components)
            + "<p class='note'>This transparent heuristic summarizes selected historical diagnostics. It does not measure suitability, forecast returns, or prescribe an allocation.</p>"
        )
    sections = [("Executive summary", "<ul>" + "".join(f"<li>{escape(x)}</li>" for x in summary) + "</ul>"),
                ("Portfolio inputs", _table(pd.Series(input_rows, name="Value").to_frame())),
                ("Research assumptions", "<ul>" + "".join(f"<li>{item}</li>" for item in assumptions) + "</ul>"),
                ("Portfolio health diagnostic", health_content),
                ("Holdings and weights", _percentage_table(weights.rename("Weight").to_frame())),
                ("Performance metrics", _metric_table(performance)), ("Risk metrics", _metric_table(risk)),
                ("Benchmark comparison", _metric_table(benchmark)), ("Attribution", _percentage_table(attribution)),
                ("Performance evaluation", _comparison_table(performance_evaluation) if performance_evaluation is not None else "<p>Performance evaluation unavailable.</p>"),
                ("Single-index security analysis", _comparison_table(security_analysis) if security_analysis is not None else "<p>Security analysis unavailable.</p>"),
                ("CAPM and asset pricing", _comparison_table(asset_pricing) if asset_pricing is not None else "<p>Asset-pricing analysis unavailable.</p>"),
                ("Portfolio comparison", _comparison_table(comparison) if comparison is not None else "<p>Comparison unavailable.</p>"),
                ("Deterministic research insights", _table(insights) if insights is not None else "<p>Insights unavailable.</p>"),
                ("What-if comparison", _comparison_table(what_if) if what_if is not None else "<p>No hypothetical scenario was included.</p>"),
                ("Efficient frontier", _comparison_table(efficient_frontier) if efficient_frontier is not None else "<p>Efficient frontier unavailable.</p>"),
                ("Optimized allocations", _percentage_table(optimized_allocations) if optimized_allocations is not None else "<p>Optimized allocations unavailable.</p>"),
                ("Custom constrained allocation", _percentage_table(constrained_allocation) if constrained_allocation is not None else "<p>No custom constrained allocation was included.</p>"),
                ("Constraint validation", _constraint_table(constraint_validation) if constraint_validation is not None else "<p>No custom constraint validation was included.</p>"),
                ("Allocation comparison", _percentage_table(allocations)),
                (f"Rebalancing plan — {rebalancing_method}", _financial_table(rebalancing)),
                ("Rebalancing policy comparison", _comparison_table(rebalancing_policies) if rebalancing_policies is not None else "<p>Policy comparison unavailable.</p>"),
                ("Selected rebalancing history", _financial_table(rebalancing_history) if rebalancing_history is not None else "<p>Policy history unavailable.</p>"),
                ("Momentum-strategy results", _metric_table(strategy) if strategy is not None else f"<p>{escape(strategy_status or 'Momentum analysis unavailable.')}</p>"),
                ("Stress-test results", _financial_table(stress)),
                ("ETF universe research", _comparison_table(etf_research) if etf_research is not None else "<p>ETF research unavailable.</p>"),
                ("Security candidate screen", _comparison_table(security_screen) if security_screen is not None else "<p>Security screen unavailable.</p>")]
    sections.extend(_fixed_income_report_sections(fixed_income))
    sections.extend([("Methodology", "<p>Simple daily returns; arithmetic annualized return for Sharpe, Sortino, CAPM evaluation, and optimization; CAGR for realized compound growth; annualized sample variance and volatility; 252-day annualization; constant weights for baseline analytics; empirical 95% VaR/CVaR; excess-return single-index OLS with annualized alpha and residual volatility; CAPM required return, Jensen's alpha, and Treynor ratio; systematic/idiosyncratic variance decomposition; Euler volatility attribution; long-only efficient-frontier, minimum-variance, maximum-Sharpe, target-return, and explicit-constraint optimization; analytical nonleveraged Capital Allocation Line and lending-only complete portfolios; separate holdings-level buy-and-hold, periodic, and threshold rebalancing simulations with costs only on trade dates; one-day-lagged dual-moving-average signal; proportional transaction costs. Regression, CAPM, and optimization outputs are historical sample estimates, not forecasts, recommendations, or evidence of skill.</p>"),
                ("Limitations and disclaimer", "<p>Historical adjusted prices may contain provider errors and do not predict future results. Excludes taxes, liquidity constraints, market impact and slippage beyond configured cost. Optimization uses historical estimates. Historical investment research only; not personalized financial advice.</p>")])
    body = "".join(f"<section><h2>{escape(name)}</h2>{content}</section>" for name, content in sections)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>{escape(title)}</title><style>
    :root{{--ink:#172033;--navy:#102a43;--muted:#627d98;--line:#d9e2ec;--panel:#f5f8fb;--accent:#147d92}}
    *{{box-sizing:border-box}} body{{font:15px system-ui,-apple-system,sans-serif;max-width:1120px;margin:0 auto;padding:48px;color:var(--ink);line-height:1.55}}
    header{{border-bottom:3px solid var(--accent);padding-bottom:22px;margin-bottom:34px}} h1{{font-size:34px;margin:0;color:var(--navy)}}
    h2{{color:var(--navy);font-size:21px;margin-bottom:12px}} section{{margin:34px 0;break-inside:avoid}} table{{border-collapse:collapse;width:100%;font-size:12.5px}}
    th,td{{padding:8px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}} th{{background:var(--panel);color:var(--navy)}} th:first-child,td:first-child{{text-align:left}}
    .meta,.note{{color:var(--muted)}} .score{{display:flex;gap:18px;align-items:center;background:var(--panel);border-left:5px solid var(--accent);padding:18px;margin-bottom:16px}}
    .score strong{{font-size:30px;color:var(--navy)}} .score span{{color:var(--muted)}} footer{{margin-top:44px;border-top:1px solid var(--line);padding-top:16px;color:var(--muted);font-size:12px}}
    @media print{{body{{padding:20px}} section{{break-inside:auto}} a{{color:inherit;text-decoration:none}}}}
    </style></head><body><header><h1>{escape(title)}</h1><p class='meta'>PortfolioLens deterministic investment research</p><p class='meta'>Generated {generated} · Analysis period {escape(str(start))} to {escape(str(end))} · Holdings: {escape(', '.join(tickers))}</p></header>{body}<footer>PortfolioLens · Historical investment research only · Not personalized financial advice</footer></body></html>"""
    return html.encode("utf-8")
