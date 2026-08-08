"""Deterministic unit and integration tests for financial calculations."""
from io import StringIO
import inspect
import numpy as np
import pandas as pd
import pytest

from portfolio_dashboard.asset_pricing import (
    capm_alpha, capm_required_return, capm_security_table,
    factor_expected_return, security_market_line,
)
from portfolio_dashboard.construction import (
    annualized_optimizer_inputs,
    capital_allocation_line, complete_portfolio_statistics, complete_portfolio_weights,
    efficient_frontier, inverse_volatility_weights,
    maximum_sharpe_weights, minimum_variance_weights, optimizer_statistics,
    optimization_diagnostics,
    target_return_weights, constrained_portfolio_weights, constraint_validation_summary,
    parse_group_caps, quadratic_utility, utility_optimal_complete_portfolio,
)
from portfolio_dashboard.data import (
    InputError, MarketDataError, align_prices, allocation_percentages, allocation_preview,
    extract_adjusted_prices, normalize_allocation, parse_allocation_values, parse_tickers,
    parse_weight_input, reconciled_allocation_percentages, resolve_benchmark_ticker,
    validate_weights,
)
from portfolio_dashboard.evaluation import (
    allocation_selection_attribution, fama_selectivity_decomposition,
    modified_dietz_return, rolling_performance_evaluation, time_weighted_return,
)
from portfolio_dashboard.performance import (
    annualized_arithmetic_return, annualized_variance, annualized_volatility,
    arithmetic_mean_return, asset_risk_return_table, cagr, coefficient_of_variation,
    diversification_effect, geometric_mean_return, holding_period_return,
    drawdown_series, max_drawdown, performance_metrics, portfolio_expected_return,
    portfolio_returns, portfolio_variance, sharpe_from_statistics, sharpe_ratio,
    simple_returns, sortino_ratio, normalized_holding_performance,
)
from portfolio_dashboard.pipeline import run_analysis
from portfolio_dashboard.rebalancing import (
    compare_rebalancing_policies, rebalancing_plan, simulate_rebalancing,
)
from portfolio_dashboard.risk import (
    benchmark_metrics, beta, historical_cvar, historical_var, information_ratio,
    security_single_index_table, single_index_regression,
    single_index_regression_diagnostics, tracking_error, volatility_contributions,
)
from portfolio_dashboard.strategy import momentum_backtest, optional_momentum_analysis
from portfolio_dashboard.stress import custom_shock, historical_stress
from portfolio_dashboard.formatting import metric_value
from portfolio_dashboard.reporting import generate_html_report, research_summary
from portfolio_dashboard.research import (
    deterministic_insights, portfolio_comparison, portfolio_health_score, what_if_analysis,
)

@pytest.fixture
def returns() -> pd.DataFrame:
    index = pd.bdate_range("2020-01-01", periods=300)
    x = np.arange(300)
    return pd.DataFrame({"A": 0.0005 + 0.008 * np.sin(x / 9), "B": 0.0002 + 0.004 * np.cos(x / 13)}, index=index)


def returns_with_exact_annual_moments(expected: np.ndarray, covariance: np.ndarray, observations: int = 40) -> pd.DataFrame:
    """Build deterministic simple returns with exact sample annual moments."""
    columns = len(expected)
    raw = np.column_stack([
        np.sin(np.arange(observations) * (index + 1.3))
        for index in range(columns)
    ])
    centered = raw - raw.mean(axis=0)
    q, _ = np.linalg.qr(centered)
    standardized = q[:, :columns] * np.sqrt(observations - 1)
    daily_covariance = covariance / 252
    values = expected / 252 + standardized @ np.linalg.cholesky(daily_covariance).T
    return pd.DataFrame(values, columns=[chr(65 + index) for index in range(columns)])

def test_ticker_and_weight_validation():
    assert parse_tickers(" aapl, MSFT, aapl ") == ["AAPL", "MSFT"]
    weights, changed = validate_weights(["A", "B"], [60, 40])
    assert weights.sum() == pytest.approx(1); assert not changed
    normalized, changed = validate_weights(["A", "B"], [0.5002, 0.5002])
    assert normalized.sum() == pytest.approx(1); assert changed
    with pytest.raises(InputError): validate_weights(["A"], [-1])
    with pytest.raises(InputError): validate_weights(["A", "B"], [1])


@pytest.mark.parametrize("alias,provider", [
    ("SPX", "^GSPC"), ("S&P500", "^GSPC"), ("SP500", "^GSPC"),
    ("DJIA", "^DJI"), ("DOW", "^DJI"), ("NASDAQ", "^IXIC"),
    ("VIX", "^VIX"), ("RUT", "^RUT"),
])
def test_benchmark_aliases_resolve_explicitly(alias, provider):
    resolution = resolve_benchmark_ticker(alias)
    assert resolution.display_symbol == alias
    assert resolution.provider_symbol == provider
    expected_notice = None if alias == "SPX" else f"{alias} was mapped to Yahoo Finance symbol {provider}."
    assert resolution.notice == expected_notice


def test_benchmark_alias_resolution_handles_case_native_and_unknown_symbols():
    lower = resolve_benchmark_ticker(" spx ")
    assert lower.display_symbol == "SPX" and lower.provider_symbol == "^GSPC"
    native = resolve_benchmark_ticker("^gspc")
    assert native.display_symbol == "^GSPC" and native.provider_symbol == "^GSPC"
    assert native.notice is None
    unknown = resolve_benchmark_ticker("aapl")
    assert unknown.display_symbol == "AAPL" and unknown.provider_symbol == "AAPL"
    assert unknown.notice is None
    assert parse_tickers("DOW") == ["DOW"]  # Portfolio holdings are never alias-resolved.


def test_no_data_errors_suggest_a_yahoo_index_symbol():
    with pytest.raises(MarketDataError, match=r"\^GSPC for the S&P 500"):
        extract_adjusted_prices(pd.DataFrame(), ["SPX"])


def test_weight_input_parses_percentages_exactly_once():
    percentages, changed = parse_weight_input(["A", "B", "C"], "50,35,15")
    decimals, decimal_changed = parse_weight_input(["A", "B", "C"], "0.50,0.35,0.15")
    expected = pd.Series({"A": .50, "B": .35, "C": .15})
    pd.testing.assert_series_equal(percentages, expected)
    pd.testing.assert_series_equal(decimals, expected)
    assert not changed and not decimal_changed


def test_equal_weight_input_ignores_stale_manual_value():
    weights, changed = parse_weight_input(["A", "B", "C"], "invalid, stale, weights", equal_weight=True)
    assert weights.tolist() == pytest.approx([1 / 3, 1 / 3, 1 / 3])
    assert weights.sum() == pytest.approx(1.0)
    assert not changed


def test_retail_allocation_validation_and_summary_helpers():
    tickers = ["SPY", "AGG", "GLD"]
    assert parse_allocation_values("50, 35, 15") == [50.0, 35.0, 15.0]
    assert allocation_percentages([0.50, 0.35, 0.15]).tolist() == pytest.approx([50, 35, 15])
    with pytest.raises(InputError, match="2 allocation values for 3 investments"):
        normalize_allocation(tickers, [50, 35])
    with pytest.raises(InputError, match="4 allocation values for 3 investments"):
        normalize_allocation(tickers, [25, 25, 25, 25])
    with pytest.raises(InputError, match="numeric"):
        parse_allocation_values("50, no-number, 50")
    with pytest.raises(InputError, match="positive allocation"):
        normalize_allocation(tickers, [50, -35, 85])
    with pytest.raises(InputError, match="positive allocation"):
        normalize_allocation(tickers, [0, 0, 0])


def test_proportional_normalization_and_equal_allocation_reconcile_exactly():
    normalized = normalize_allocation(["SPY", "AGG", "GLD"], [50, 35, 20])
    assert normalized.tolist() == pytest.approx([50 / 105, 35 / 105, 20 / 105])
    assert normalized.sum() == pytest.approx(1.0)
    assert reconciled_allocation_percentages(normalized.to_numpy() * 100).tolist() == [47.62, 33.33, 19.05]

    equal = reconciled_allocation_percentages([100 / 3] * 3)
    assert equal.tolist() == [33.33, 33.33, 33.34]
    preview = allocation_preview(["SPY", "AGG", "GLD"], equal)
    assert preview.iloc[-1].to_dict() == {"Investment": "Total", "Allocation": 100.0}

def test_simple_and_portfolio_returns():
    prices = pd.DataFrame({"A": [100, 110, 99], "B": [100, 100, 110]})
    result = simple_returns(prices)
    assert result.iloc[0].tolist() == pytest.approx([.1, 0])
    p = portfolio_returns(result, pd.Series({"A": .6, "B": .4}))
    assert p.iloc[0] == pytest.approx(.06)


def test_normalized_holding_performance_aligns_before_normalizing_and_ignores_weights():
    prices = pd.DataFrame({
        "A": [np.nan, 10.0, 12.0, 15.0],
        "B": [20.0, 25.0, np.nan, 30.0],
    }, index=pd.date_range("2024-01-01", periods=4))
    normalized, excluded = normalized_holding_performance(prices)
    assert excluded == {}
    assert normalized.index.tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-04")]
    assert normalized.loc["2024-01-02", "A"] == pytest.approx(1.0)
    assert normalized.loc["2024-01-02", "B"] == pytest.approx(1.0)
    assert normalized.loc["2024-01-04", "A"] == pytest.approx(1.5)
    assert normalized.loc["2024-01-04", "B"] == pytest.approx(1.2)

    complete = pd.DataFrame({
        "A": [10.0, 12.0, 15.0],
        "B": [20.0, 25.0, 30.0],
    }, index=pd.date_range("2024-01-02", periods=3))
    expected, _ = normalized_holding_performance(complete)
    assert expected.loc["2024-01-03", "A"] == pytest.approx(1.2)
    assert expected.loc["2024-01-03", "B"] == pytest.approx(1.25)
    exported = pd.read_csv(
        StringIO(expected.rename_axis("Date").to_csv()),
        index_col="Date",
        parse_dates=["Date"],
    )
    pd.testing.assert_frame_equal(
        exported, expected.rename_axis("Date"), check_freq=False
    )
    # No portfolio weights are accepted or used by this security-comparison calculation.
    assert expected.iloc[0].tolist() == pytest.approx([1.0, 1.0])


def test_normalized_holding_performance_excludes_invalid_and_handles_single_series():
    prices = pd.DataFrame({
        "Good": [100.0, 110.0],
        "Bad": [100.0, 0.0],
        "Empty": [np.nan, np.nan],
    }, index=pd.date_range("2024-01-01", periods=2))
    normalized, excluded = normalized_holding_performance(prices)
    assert list(normalized.columns) == ["Good"]
    assert normalized.iloc[0, 0] == pytest.approx(1.0)
    assert normalized.iloc[1, 0] == pytest.approx(1.1)
    assert "non-positive" in excluded["Bad"]
    assert "numeric" in excluded["Empty"]

    one, excluded_one = normalized_holding_performance(
        pd.DataFrame({"Only": [5.0]}, index=pd.date_range("2024-01-01", periods=1))
    )
    assert excluded_one == {}
    assert one.iloc[0, 0] == pytest.approx(1.0)
    with pytest.raises(ValueError, match="unique"):
        normalized_holding_performance(pd.DataFrame([[1.0, 2.0]], columns=["A", "A"]))

def test_missing_data_policy():
    prices = pd.DataFrame({"A": [1, 2, np.nan, 4], "B": [1, np.nan, 3, 4]})
    aligned = align_prices(prices, ["A", "B"], min_observations=2)
    assert len(aligned) == 2 and not aligned.isna().any().any()
    with pytest.raises(MarketDataError): align_prices(prices, ["A", "C"], min_observations=1)


def test_core_history_minimum_remains_independent_of_momentum():
    index = pd.bdate_range("2024-01-01", periods=29)
    prices = pd.DataFrame({"A": np.arange(29.0), "B": np.arange(29.0)}, index=index)
    with pytest.raises(MarketDataError, match="at least 30"):
        align_prices(prices, ["A", "B"])

def test_extract_single_and_multiindex_prices():
    raw = pd.DataFrame({"Adj Close": [10, 11], "Close": [9, 10]})
    assert list(extract_adjusted_prices(raw, ["A"]).columns) == ["A"]
    columns = pd.MultiIndex.from_product([["Adj Close", "Close"], ["A", "B"]])
    multi = pd.DataFrame(np.arange(8).reshape(2, 4), columns=columns)
    assert list(extract_adjusted_prices(multi, ["A", "B"]).columns) == ["A", "B"]

def test_performance_formulas():
    r = pd.Series([.01, -.02, .03, .01])
    expected_arithmetic = r.mean() * 252
    expected_cagr = (np.prod(1 + r) ** (252 / 4)) - 1
    expected_variance = r.var(ddof=1) * 252
    assert annualized_arithmetic_return(r) == pytest.approx(expected_arithmetic)
    assert cagr(r) == pytest.approx(expected_cagr)
    assert annualized_variance(r) == pytest.approx(expected_variance)
    assert annualized_volatility(r) == pytest.approx(r.std(ddof=1) * np.sqrt(252))
    assert annualized_volatility(r) ** 2 == pytest.approx(expected_variance)
    assert sharpe_ratio(r, .02) == pytest.approx((expected_arithmetic - .02) / annualized_volatility(r))
    assert np.isfinite(sortino_ratio(pd.Series([.01, -.01, .02, -.03, .01])))
    dd = drawdown_series(pd.Series([.1, -.2, .1]))
    assert max_drawdown(pd.Series([.1, -.2, .1])) == pytest.approx(dd.min())


def test_workbook_one_holding_period_arithmetic_geometric_and_annualization():
    values = pd.Series([.10, -.10, .20])
    assert holding_period_return(100, 108, 4) == pytest.approx(.12)
    assert arithmetic_mean_return(values) == pytest.approx(values.mean())
    assert geometric_mean_return(values) == pytest.approx(np.prod(1 + values) ** (1 / 3) - 1)
    assert cagr(values, periods_per_year=12) == pytest.approx((1 + geometric_mean_return(values)) ** 12 - 1)
    with pytest.raises(ValueError, match="positive"):
        holding_period_return(0, 10)
    assert np.isnan(geometric_mean_return(pd.Series([-1.5])))
    assert np.isnan(geometric_mean_return(pd.Series([-2.0, -2.0])))
    assert np.isnan(cagr(pd.Series([-2.0, -2.0])))
    assert np.isnan(arithmetic_mean_return(pd.Series(dtype=float)))


def test_workbook_one_asset_table_uses_sample_risk_and_reconciles_units():
    values = pd.DataFrame({"A": [.01, -.02, .03], "B": [.02, .01, -.01]})
    table = asset_risk_return_table(values, periods_per_year=12)
    assert table.loc["A", "Periodic Arithmetic Mean"] == pytest.approx(values["A"].mean())
    assert table.loc["A", "Annualized Sample Variance"] == pytest.approx(values["A"].var(ddof=1) * 12)
    assert table.loc["A", "Annualized Sample Volatility"] ** 2 == pytest.approx(
        table.loc["A", "Annualized Sample Variance"]
    )
    assert table.loc["A", "Coefficient of Variation"] == pytest.approx(
        table.loc["A", "Annualized Sample Volatility"]
        / table.loc["A", "Historical Arithmetic Annualized Return"]
    )
    assert np.isnan(coefficient_of_variation(0.0, .1))
    assert coefficient_of_variation(.05, 0.0) == 0.0
    insufficient = asset_risk_return_table(pd.DataFrame({"A": [.01, np.nan]}), periods_per_year=12)
    assert np.isnan(insufficient.loc["A", "Annualized Sample Variance"])


def test_workbook_one_covariance_correlation_two_asset_and_diversification():
    values = pd.DataFrame({"A": [.01, -.02, .03, -.01], "B": [-.01, .02, -.03, .01]})
    weights = pd.Series({"A": .6, "B": .4})
    covariance = values.cov() * 12
    expected_two_asset = (
        weights["A"] ** 2 * covariance.loc["A", "A"]
        + weights["B"] ** 2 * covariance.loc["B", "B"]
        + 2 * weights["A"] * weights["B"] * covariance.loc["A", "B"]
    )
    assert portfolio_variance(values, weights, 12) == pytest.approx(expected_two_asset)
    assert values.corr().loc["A", "B"] == pytest.approx(-1.0)
    effect = diversification_effect(values, weights, 12)
    assert effect["Portfolio Volatility"] == pytest.approx(np.sqrt(expected_two_asset))
    assert effect["Diversification Reduction"] > 0
    assert effect["Weighted Standalone Volatility"] - effect["Diversification Reduction"] == pytest.approx(
        effect["Portfolio Volatility"]
    )
    with pytest.raises(ValueError, match="labels"):
        diversification_effect(values, pd.Series({"A": 1.0}), 12)


def test_drawdown_includes_initial_wealth_baseline():
    returns = pd.Series([-.10, .05], index=pd.bdate_range("2024-01-01", periods=2))
    assert drawdown_series(returns).iloc[0] == pytest.approx(-.10)
    assert max_drawdown(returns) == pytest.approx(-.10)


def test_sortino_uses_all_periods_for_target_downside_deviation():
    values = pd.Series([.01, -.02, .03, -.01])
    downside = np.sqrt(np.mean(np.minimum(values.to_numpy(), 0.0) ** 2)) * np.sqrt(252)
    expected = annualized_arithmetic_return(values) / downside
    assert sortino_ratio(values) == pytest.approx(expected)


def test_portfolio_expected_return_and_variance_match_matrix_formulas():
    asset_returns = pd.DataFrame({"A": [.01, -.02, .03], "B": [.02, .01, -.01]})
    weights = pd.Series({"A": .6, "B": .4})
    expected_return = float(weights @ (asset_returns.mean() * 252))
    expected_variance = float(weights @ (asset_returns.cov() * 252) @ weights)
    assert portfolio_expected_return(asset_returns, weights) == pytest.approx(expected_return)
    assert portfolio_variance(asset_returns, weights) == pytest.approx(expected_variance)
    with pytest.raises(ValueError, match="labels"):
        portfolio_variance(asset_returns, pd.Series({"A": 1.0}))


def test_optimizer_and_displayed_sharpe_share_one_formula(returns):
    risk_free_rate = .02
    weights = maximum_sharpe_weights(returns, risk_free_rate)
    optimized_returns = portfolio_returns(returns, weights)
    displayed = performance_metrics(optimized_returns, risk_free_rate)["Sharpe Ratio"]
    expected_return = portfolio_expected_return(returns, weights)
    volatility = np.sqrt(portfolio_variance(returns, weights))
    optimizer_formula = sharpe_from_statistics(expected_return, volatility, risk_free_rate)
    assert displayed == pytest.approx(optimizer_formula)


def test_performance_scorecard_separates_arithmetic_return_cagr_and_variance():
    values = pd.Series([.10, -.10])
    metrics = performance_metrics(values)
    assert metrics["Historical Arithmetic Annualized Return"] == pytest.approx(0.0)
    assert metrics["CAGR"] < 0
    assert metrics["Annualized Variance"] == pytest.approx(values.var(ddof=1) * 252)


def test_fama_selectivity_decomposition_reconciles_source_example():
    result = fama_selectivity_decomposition(
        portfolio_return=.264, benchmark_return=.1571, risk_free_rate=.062,
        portfolio_volatility=.2067, benchmark_volatility=.1325, portfolio_beta=1.351,
    )
    assert result["Overall Performance"] == pytest.approx(.202)
    assert result["CAPM Required Return"] == pytest.approx(.1904801)
    assert result["CML Required Return at Portfolio Risk"] == pytest.approx(.210356)
    assert result["Selectivity"] == pytest.approx(.0735199)
    assert result["Diversification Effect"] == pytest.approx(.0198759)
    assert result["Net Selectivity"] == pytest.approx(.053644)
    assert result["Selectivity"] - result["Diversification Effect"] == pytest.approx(
        result["Net Selectivity"]
    )
    with pytest.raises(ValueError, match="benchmark volatility"):
        fama_selectivity_decomposition(.1, .1, .02, .1, 0, 1)


def test_source_allocation_selection_effects_reconcile_active_return():
    labels = pd.Index(["Stock", "Bonds", "Cash"])
    benchmark_weights = pd.Series([.6, .3, .1], index=labels)
    benchmark_returns = pd.Series([-.05, -.035, .003], index=labels)
    portfolio_weights = pd.Series([.5, .2, .3], index=labels)
    portfolio_returns = pd.Series([-.04, -.025, .003], index=labels)
    result = allocation_selection_attribution(
        benchmark_weights, benchmark_returns, portfolio_weights, portfolio_returns,
    )
    assert result["Benchmark Return"] == pytest.approx(-.0402)
    assert result["Portfolio Return"] == pytest.approx(-.0241)
    assert result["Active Return"] == pytest.approx(.0161)
    assert result["Allocation Effect"] == pytest.approx(.0091)
    assert result["Selection Effect Including Interaction"] == pytest.approx(.007)
    assert result["Reconciliation Residual"] == pytest.approx(0, abs=1e-15)
    with pytest.raises(ValueError, match="identical ordered labels"):
        allocation_selection_attribution(
            benchmark_weights, benchmark_returns.sort_index(), portfolio_weights, portfolio_returns,
        )


def test_modified_dietz_and_time_weighted_return_match_fixed_cash_flow_case():
    cash_flows = pd.Series({"midpoint": 12_000.0})
    timings = pd.Series({"midpoint": .5})
    assert modified_dietz_return(500_000, 527_000, cash_flows, timings) == pytest.approx(
        (527_000 - 500_000 - 12_000) / (500_000 + .5 * 12_000)
    )
    returns = pd.Series([.03, -.008538899430740038, .02169811320754717])
    assert time_weighted_return(returns) == pytest.approx((1 + returns).prod() - 1)
    assert np.isnan(time_weighted_return(pd.Series([-1.0])))
    with pytest.raises(ValueError, match="between zero and one"):
        modified_dietz_return(100, 110, cash_flows, pd.Series({"midpoint": 1.2}))


def test_rolling_performance_evaluation_uses_aligned_sample_formulas():
    index = pd.bdate_range("2024-01-01", periods=8)
    portfolio = pd.Series([.01, -.005, .008, .002, -.003, .006, .004, -.002], index=index)
    benchmark = pd.Series([.008, -.004, .006, .001, -.002, .004, .003, -.001], index=index)
    result = rolling_performance_evaluation(portfolio, benchmark, .02, window=5, periods_per_year=12)
    last_portfolio = portfolio.iloc[-5:]
    last_active = (portfolio - benchmark).iloc[-5:]
    expected_sharpe = (last_portfolio.mean() * 12 - .02) / (last_portfolio.std(ddof=1) * np.sqrt(12))
    expected_tracking = last_active.std(ddof=1) * np.sqrt(12)
    assert result.iloc[-1]["Rolling Sharpe Ratio"] == pytest.approx(expected_sharpe)
    assert result.iloc[-1]["Rolling Tracking Error"] == pytest.approx(expected_tracking)
    assert result.iloc[-1]["Rolling Information Ratio"] == pytest.approx(
        last_active.mean() * 12 / expected_tracking
    )
    with pytest.raises(ValueError, match="at least three"):
        rolling_performance_evaluation(portfolio, benchmark, window=2)

def test_var_cvar_beta_and_relative_metrics():
    benchmark = pd.Series([-.03, -.02, -.01, 0, .01, .02])
    portfolio = benchmark * 1.5
    assert historical_var(portfolio, .95) > 0
    assert historical_cvar(portfolio, .95) >= historical_var(portfolio, .95)
    assert beta(portfolio, benchmark) == pytest.approx(1.5)
    assert tracking_error(portfolio, benchmark) > 0
    assert np.isfinite(information_ratio(portfolio + .001, benchmark))


def test_excess_return_single_index_regression_recovers_known_properties():
    periods = 252
    risk_free_rate = .0252
    periodic_risk_free = risk_free_rate / periods
    benchmark_excess = pd.Series(np.linspace(-.02, .025, 24))
    raw_noise = pd.Series(np.sin(np.arange(24)))
    orthogonal_noise = raw_noise - raw_noise.mean()
    orthogonal_noise -= (
        orthogonal_noise.cov(benchmark_excess) / benchmark_excess.var(ddof=1)
    ) * (benchmark_excess - benchmark_excess.mean())
    residual = orthogonal_noise * .001
    periodic_alpha = .0002
    known_beta = 1.4
    benchmark = benchmark_excess + periodic_risk_free
    portfolio = periodic_risk_free + periodic_alpha + known_beta * benchmark_excess + residual

    metrics = single_index_regression(portfolio, benchmark, risk_free_rate)

    assert metrics["Regression Alpha"] == pytest.approx(periodic_alpha * periods)
    assert metrics["Beta"] == pytest.approx(known_beta)
    assert metrics["R-Squared"] == pytest.approx(
        metrics["Systematic Risk Share"]
    )
    assert metrics["Systematic Risk Share"] + metrics["Idiosyncratic Risk Share"] == pytest.approx(1)
    assert metrics["Residual Volatility"] == pytest.approx(residual.std(ddof=2) * np.sqrt(periods))
    assert metrics["Systematic Variance"] + metrics["Idiosyncratic Variance"] == pytest.approx(
        (portfolio - periodic_risk_free).var(ddof=1) * periods
    )
    expected_capm = risk_free_rate + known_beta * (benchmark.mean() * periods - risk_free_rate)
    assert metrics["CAPM Required Return"] == pytest.approx(expected_capm)
    assert metrics["Jensen's Alpha"] == pytest.approx(periodic_alpha * periods)
    assert metrics["Treynor Ratio"] == pytest.approx(
        (portfolio.mean() * periods - risk_free_rate) / known_beta
    )
    assert metrics["Regression Observations"] == 24


def test_single_index_regression_validates_sample_and_benchmark_variance():
    with pytest.raises(ValueError, match="three aligned"):
        single_index_regression(pd.Series([.01, .02]), pd.Series([.01, .02]))
    with pytest.raises(ValueError, match="positive sample variance"):
        single_index_regression(pd.Series([.01, .02, .03]), pd.Series([.01, .01, .01]))


def test_security_single_index_diagnostics_recover_known_ols_and_reconcile_variance():
    periods = 12
    risk_free_rate = .024
    index = pd.date_range("2020-01-31", periods=60, freq="ME")
    market_excess = pd.Series(np.linspace(-.06, .07, 60), index=index)
    raw_residual = pd.Series(np.sin(np.arange(60) * 1.7), index=index)
    residual = raw_residual - raw_residual.mean()
    residual -= residual.cov(market_excess) / market_excess.var(ddof=1) * (market_excess - market_excess.mean())
    residual *= .004
    periodic_alpha, known_beta = .0015, 1.25
    benchmark = market_excess + risk_free_rate / periods
    security = risk_free_rate / periods + periodic_alpha + known_beta * market_excess + residual

    metrics, observations = single_index_regression_diagnostics(
        security, benchmark, risk_free_rate, periods
    )

    assert metrics["Regression Alpha"] == pytest.approx(periodic_alpha * periods)
    assert metrics["Beta"] == pytest.approx(known_beta)
    assert observations["Residual"].mean() == pytest.approx(0, abs=1e-14)
    np.testing.assert_allclose(
        observations["Fitted Excess Return"] + observations["Residual"],
        observations["Security Excess Return"], atol=1e-14,
    )
    modeled_variance = metrics["Systematic Variance"] + metrics["Idiosyncratic Variance"]
    assert modeled_variance == pytest.approx((security - risk_free_rate / periods).var(ddof=1) * periods)
    assert metrics["Total Model Volatility"] == pytest.approx(np.sqrt(modeled_variance))
    assert metrics["R-Squared"] == pytest.approx(metrics["Systematic Risk Share"])
    assert metrics["Jensen's Alpha"] == pytest.approx(metrics["Regression Alpha"])
    assert metrics["Alpha 95% Lower"] < metrics["Regression Alpha"] < metrics["Alpha 95% Upper"]
    assert metrics["Beta 95% Lower"] < known_beta < metrics["Beta 95% Upper"]


def test_security_single_index_table_ranks_and_aligns_each_security():
    index = pd.bdate_range("2024-01-01", periods=30)
    benchmark = pd.Series(np.linspace(-.02, .025, 30), index=index)
    assets = pd.DataFrame({
        "Higher Alpha": .0005 + 1.1 * benchmark,
        "Lower Alpha": -.0002 + .7 * benchmark,
    }, index=index)
    table = security_single_index_table(assets, benchmark)
    assert table.index.tolist() == ["Higher Alpha", "Lower Alpha"]
    assert table.loc["Higher Alpha", "Regression Alpha"] > table.loc["Lower Alpha", "Regression Alpha"]
    assert table.loc["Higher Alpha", "Beta"] == pytest.approx(1.1)
    assert table.loc["Lower Alpha", "Beta"] == pytest.approx(.7)


def test_security_single_index_diagnostics_handles_perfect_and_invalid_inputs():
    benchmark = pd.Series([-.02, -.01, 0, .01, .02])
    security = .001 + .8 * benchmark
    metrics, observations = single_index_regression_diagnostics(security, benchmark)
    assert metrics["R-Squared"] == pytest.approx(1)
    assert metrics["Residual Volatility"] == pytest.approx(0, abs=1e-12)
    assert observations["Residual"].abs().max() < 1e-12
    with pytest.raises(ValueError, match="positive sample variance"):
        single_index_regression_diagnostics(pd.Series([.01, .02, .03]), pd.Series([.01, .01, .01]))
    with pytest.raises(ValueError, match="three aligned"):
        single_index_regression_diagnostics(pd.Series([.01, np.nan, .02]), pd.Series([.01, .02, .03]))
    with pytest.raises(ValueError, match="Confidence"):
        single_index_regression_diagnostics(security, benchmark, confidence=1)


def test_capm_required_return_alpha_and_beta_scenarios():
    risk_free, market = .04, .10
    assert capm_required_return(0, risk_free, market) == pytest.approx(.04)
    assert capm_required_return(1, risk_free, market) == pytest.approx(.10)
    assert capm_required_return(2, risk_free, market) == pytest.approx(.16)
    assert capm_required_return(-.5, risk_free, market) == pytest.approx(.01)
    assert capm_alpha(.13, 1.2, risk_free, market) == pytest.approx(.018)
    assert capm_required_return(1.2, .05, market) < capm_required_return(1.2, .04, market)
    assert capm_required_return(.8, .05, market) > capm_required_return(.8, .04, market)
    assert capm_required_return(1.2, risk_free, .12) > capm_required_return(1.2, risk_free, market)
    with pytest.raises(ValueError, match="finite"):
        capm_required_return(np.nan, risk_free, market)


def test_security_market_line_coordinates_are_sorted_and_exact():
    line = security_market_line(pd.Series([1.5, 0, -.25, 1]), .03, .11)
    assert line["Beta"].is_monotonic_increasing
    assert line.iloc[0]["CAPM Required Return"] == pytest.approx(.01)
    assert line.loc[line["Beta"].eq(0), "CAPM Required Return"].iloc[0] == pytest.approx(.03)
    assert line.loc[line["Beta"].eq(1), "CAPM Required Return"].iloc[0] == pytest.approx(.11)
    with pytest.raises(ValueError, match="nonempty"):
        security_market_line([], .03, .11)


def test_capm_security_table_reconciles_known_synthetic_assets():
    periods, risk_free = 12, .024
    index = pd.date_range("2021-01-31", periods=48, freq="ME")
    market_excess = pd.Series(np.linspace(-.04, .05, len(index)), index=index)
    benchmark = market_excess + risk_free / periods
    assets = pd.DataFrame({
        "Zero Beta": risk_free / periods + .001,
        "High Beta": risk_free / periods + .0005 + 1.8 * market_excess,
        "Negative Beta": risk_free / periods - .0002 - .4 * market_excess,
    }, index=index)
    table = capm_security_table(assets, benchmark, risk_free, periods)
    assert table.loc["Zero Beta", "Beta"] == pytest.approx(0, abs=1e-12)
    assert table.loc["High Beta", "Beta"] == pytest.approx(1.8)
    assert table.loc["Negative Beta", "Beta"] == pytest.approx(-.4)
    assert table.loc["High Beta", "Jensen's Alpha"] == pytest.approx(.0005 * periods)
    assert table.loc["Zero Beta", "CAPM Required Return"] == pytest.approx(risk_free)
    assert table.loc["Negative Beta", "Position vs SML"] == "Below"


def test_assumption_based_factor_decomposition_reconciles_and_validates():
    exposures = pd.Series({"Market": 1.2, "SMB": -.3, "HML": .5, "Momentum": .2})
    premia = pd.Series({"Market": .06, "SMB": .02, "HML": .03, "Momentum": .04})
    expected, contributions = factor_expected_return(.03, exposures, premia)
    assert expected == pytest.approx(.03 + 1.2 * .06 - .3 * .02 + .5 * .03 + .2 * .04)
    assert contributions["Expected Return Contribution"].sum() == pytest.approx(expected - .03)
    with pytest.raises(ValueError, match="matching nonempty"):
        factor_expected_return(.03, exposures, premia.drop("Momentum"))
    with pytest.raises(ValueError, match="unique"):
        factor_expected_return(.03, pd.Series([1, 2], index=["M", "M"]), pd.Series({"M": .04}))


def test_benchmark_metrics_include_regression_and_capm_outputs():
    benchmark = pd.Series([-.02, -.01, 0, .01, .02])
    portfolio = .0001 + 1.2 * benchmark
    metrics = benchmark_metrics(portfolio, benchmark, .01)
    assert metrics["Beta"] == pytest.approx(1.2)
    assert metrics["Regression Alpha"] == pytest.approx((.0001 + .2 * (.01 / 252)) * 252)
    assert metrics["Jensen's Alpha"] == pytest.approx(metrics["Regression Alpha"])
    assert metrics["R-Squared"] == pytest.approx(1.0)
    active = (portfolio - benchmark).mean() * 252
    assert metrics["Annualized Active Return"] == pytest.approx(active)
    assert metrics["Mean Absolute Periodic Difference"] == pytest.approx(
        (portfolio - benchmark).abs().mean()
    )
    assert metrics["Information Ratio"] == pytest.approx(active / metrics["Tracking Error"])


def test_var_and_cvar_are_nonnegative_loss_measures():
    positive = pd.Series([.01, .02, .03])
    assert historical_var(positive) == 0.0
    assert historical_cvar(positive) == 0.0
    with pytest.raises(ValueError):
        historical_var(positive, 1.0)


def test_relative_drawdown_includes_initial_relative_wealth():
    portfolio = pd.Series([-.10, .05])
    benchmark = pd.Series([-.05, .01])
    metrics = __import__("portfolio_dashboard.risk", fromlist=["benchmark_metrics"]).benchmark_metrics(portfolio, benchmark)
    first_relative = (1 - .10) / (1 - .05) - 1
    assert metrics["Relative Drawdown"] == pytest.approx(first_relative)

def test_risk_contributions_reconcile(returns):
    weights = pd.Series({"A": .6, "B": .4})
    contribution = volatility_contributions(returns, weights)
    portfolio_vol = np.sqrt(float(weights @ (returns.cov() * 252) @ weights))
    assert contribution.sum() == pytest.approx(portfolio_vol)

def test_allocation_methods_and_constraints(returns):
    inverse = inverse_volatility_weights(returns)
    assert inverse.sum() == pytest.approx(1); assert (inverse >= 0).all()
    assert inverse["B"] > inverse["A"]
    for weights in (minimum_variance_weights(returns), maximum_sharpe_weights(returns)):
        assert weights.sum() == pytest.approx(1, abs=1e-6)
        assert ((weights >= 0) & (weights <= 1)).all()


def test_target_return_portfolio_is_feasible_and_rejects_impossible_target(returns):
    asset_expected = returns.mean() * 252
    target = float(asset_expected.mean())
    weights = target_return_weights(returns, target)
    assert weights.sum() == pytest.approx(1, abs=1e-6)
    assert weights.between(0, 1).all()
    assert optimizer_statistics(returns, weights)["Optimizer Expected Return"] == pytest.approx(target, abs=1e-7)
    with pytest.raises(ValueError, match="outside the long-only feasible range"):
        target_return_weights(returns, float(asset_expected.max() + .01))


def test_efficient_frontier_is_reproducible_and_monotonic(returns):
    frontier, frontier_weights = efficient_frontier(returns, .02, points=12)
    repeated, repeated_weights = efficient_frontier(returns, .02, points=12)
    pd.testing.assert_frame_equal(frontier, repeated)
    pd.testing.assert_frame_equal(frontier_weights, repeated_weights)
    assert frontier["Optimizer Expected Return"].is_monotonic_increasing
    assert frontier["Optimizer Volatility"].diff().iloc[1:].ge(-1e-7).all()
    assert np.allclose(frontier_weights.sum(axis=0), 1, atol=1e-6)
    assert ((frontier_weights >= 0) & (frontier_weights <= 1)).all().all()
    gmv = minimum_variance_weights(returns)
    assert frontier.iloc[0]["Optimizer Volatility"] == pytest.approx(
        optimizer_statistics(returns, gmv, .02)["Optimizer Volatility"]
    )


def test_maximum_sharpe_and_nonleveraged_cal_share_tangency_statistics(returns):
    tangency = maximum_sharpe_weights(returns, .02)
    stats = optimizer_statistics(returns, tangency, .02)
    line = capital_allocation_line(stats, .02, points=8)
    assert line.iloc[0]["Risky Portfolio Weight"] == 0
    assert line.iloc[0]["Expected Return"] == pytest.approx(.02)
    assert line.iloc[-1]["Risky Portfolio Weight"] == 1
    assert line.iloc[-1]["Expected Return"] == pytest.approx(stats["Optimizer Expected Return"])
    assert line.iloc[-1]["Volatility"] == pytest.approx(stats["Optimizer Volatility"])


def test_two_asset_frontier_matches_closed_form_and_endpoints():
    expected = np.array([.07, .13])
    covariance = np.array([[.04, .006], [.006, .09]])
    values = returns_with_exact_annual_moments(expected, covariance)
    denominator = covariance[0, 0] + covariance[1, 1] - 2 * covariance[0, 1]
    closed_gmv = np.array([
        (covariance[1, 1] - covariance[0, 1]) / denominator,
        (covariance[0, 0] - covariance[0, 1]) / denominator,
    ])
    gmv = minimum_variance_weights(values)
    assert gmv.to_numpy() == pytest.approx(closed_gmv, abs=1e-7)
    target = .10
    target_weights = target_return_weights(values, target)
    closed_target = np.array([(expected[1] - target) / (expected[1] - expected[0]),
                              (target - expected[0]) / (expected[1] - expected[0])])
    assert target_weights.to_numpy() == pytest.approx(closed_target, abs=1e-7)
    frontier, weights = efficient_frontier(values, .03, points=41)
    assert frontier.iloc[0]["Optimizer Expected Return"] == pytest.approx(closed_gmv @ expected)
    assert frontier.iloc[-1]["Optimizer Expected Return"] == pytest.approx(expected.max())
    assert weights.iloc[:, -1].to_numpy() == pytest.approx([0, 1], abs=1e-7)
    assert frontier["Optimizer Expected Return"].is_monotonic_increasing
    assert frontier["Optimizer Volatility"].is_monotonic_increasing


def test_three_asset_optimizers_match_dense_simplex_search_and_frontier_is_efficient():
    expected = np.array([.065, .095, .14])
    covariance = np.array([
        [.0225, .0040, .0060],
        [.0040, .0400, .0100],
        [.0060, .0100, .0900],
    ])
    values = returns_with_exact_annual_moments(expected, covariance, observations=60)
    grid = np.linspace(0, 1, 501)
    candidates = np.array([[a, b, 1 - a - b] for a in grid for b in grid if a + b <= 1])
    variances = np.einsum("ij,jk,ik->i", candidates, covariance, candidates)
    sharpes = (candidates @ expected - .03) / np.sqrt(variances)
    gmv = minimum_variance_weights(values).to_numpy()
    tangency = maximum_sharpe_weights(values, .03).to_numpy()
    assert gmv @ covariance @ gmv <= variances.min() + 2e-7
    assert (tangency @ expected - .03) / np.sqrt(tangency @ covariance @ tangency) >= sharpes.max() - 2e-5
    frontier, _ = efficient_frontier(values, .03, points=51)
    assert frontier["Optimizer Expected Return"].is_monotonic_increasing
    assert frontier["Optimizer Volatility"].is_monotonic_increasing
    coordinates = frontier[["Optimizer Expected Return", "Optimizer Volatility"]].to_numpy()
    for left, right in zip(coordinates[:-1], coordinates[1:]):
        assert not (
            right[1] <= left[1] and right[0] >= left[0]
        ), "An efficient-frontier point must not be dominated by its successor."
    tangency_stats = optimizer_statistics(values, pd.Series(tangency, index=values.columns), .03)
    distance = np.hypot(
        frontier["Optimizer Expected Return"] - tangency_stats["Optimizer Expected Return"],
        frontier["Optimizer Volatility"] - tangency_stats["Optimizer Volatility"],
    ).min()
    assert distance < 1e-7


def test_diagonal_and_near_singular_covariance_are_stable_without_regularization():
    diagonal = np.diag([.01, .04, .09])
    values = returns_with_exact_annual_moments(np.array([.06, .08, .11]), diagonal)
    gmv = minimum_variance_weights(values)
    inverse_variances = 1 / np.diag(diagonal)
    assert gmv.to_numpy() == pytest.approx(inverse_variances / inverse_variances.sum(), abs=1e-7)

    near_singular = np.array([[.04, .039999], [.039999, .04]])
    correlated = returns_with_exact_annual_moments(np.array([.08, .081]), near_singular)
    stable = minimum_variance_weights(correlated)
    assert stable.sum() == pytest.approx(1.0, abs=1e-7)
    assert stable.between(0, 1).all()
    diagnostics = optimization_diagnostics(correlated, stable, .02)
    assert diagnostics["Covariance condition number"] > 10_000
    assert diagnostics["Covariance stabilization"] == "None"


def test_cal_reconciles_from_tangency_return_not_stale_sharpe():
    tangency = {
        "Optimizer Expected Return": .11,
        "Optimizer Volatility": .20,
        "Optimizer Sharpe": 999.0,
    }
    line = capital_allocation_line(tangency, .03, points=11)
    assert line.iloc[0]["Volatility"] == 0
    assert line.iloc[0]["Expected Return"] == pytest.approx(.03)
    assert line.iloc[-1]["Volatility"] == pytest.approx(.20)
    assert line.iloc[-1]["Expected Return"] == pytest.approx(.11)
    assert line.iloc[-1]["Sharpe Ratio"] == pytest.approx(.40)
    complete = complete_portfolio_statistics(tangency, .03, .6)
    cal_point = line.iloc[6]
    assert complete["Optimizer Expected Return"] == pytest.approx(cal_point["Expected Return"])
    assert complete["Optimizer Volatility"] == pytest.approx(cal_point["Volatility"])


def test_optimization_diagnostics_reconcile_constraints_and_tangency(returns):
    tangency_weights = maximum_sharpe_weights(returns, .02)
    tangency = optimizer_statistics(returns, tangency_weights, .02)
    frontier, _ = efficient_frontier(returns, .02, points=31)
    diagnostics = optimization_diagnostics(
        returns, tangency_weights, .02, target_return=tangency["Optimizer Expected Return"],
        frontier=frontier, tangency_statistics=tangency,
    )
    assert diagnostics["Annualization factor"] == 252
    assert diagnostics["Weight-sum residual"] < 1e-10
    assert diagnostics["Target-return residual"] < 1e-10
    assert diagnostics["Tangency/frontier distance"] < 1e-7
    assert diagnostics["CAL tangency residual"] < 1e-12


def test_workbook_two_complete_portfolio_reconciles_with_cal(returns):
    risk_free_rate = .02
    tangency_weights = maximum_sharpe_weights(returns, risk_free_rate)
    tangency = optimizer_statistics(returns, tangency_weights, risk_free_rate)
    risky_weight = .65
    complete = complete_portfolio_statistics(tangency, risk_free_rate, risky_weight)
    weights = complete_portfolio_weights(tangency_weights, risky_weight)
    assert weights.sum() == pytest.approx(1.0)
    assert weights.loc["Risk-free asset"] == pytest.approx(1 - risky_weight)
    assert complete["Optimizer Expected Return"] == pytest.approx(
        risk_free_rate + risky_weight * (tangency["Optimizer Expected Return"] - risk_free_rate)
    )
    assert complete["Optimizer Volatility"] == pytest.approx(
        risky_weight * tangency["Optimizer Volatility"]
    )
    assert complete["Optimizer Sharpe"] == pytest.approx(tangency["Optimizer Sharpe"])
    cal = capital_allocation_line(tangency, risk_free_rate, points=21)
    cal_point = cal.loc[np.isclose(cal["Risky Portfolio Weight"], risky_weight)].iloc[0]
    assert complete["Optimizer Expected Return"] == pytest.approx(cal_point["Expected Return"])
    assert complete["Optimizer Volatility"] == pytest.approx(cal_point["Volatility"])


def test_workbook_two_complete_portfolio_zero_risky_and_boundaries(returns):
    tangency_weights = maximum_sharpe_weights(returns, .02)
    tangency = optimizer_statistics(returns, tangency_weights, .02)
    risk_free = complete_portfolio_statistics(tangency, .02, 0.0)
    assert risk_free["Optimizer Expected Return"] == pytest.approx(.02)
    assert risk_free["Optimizer Volatility"] == 0
    assert np.isnan(risk_free["Optimizer Sharpe"])
    weights = complete_portfolio_weights(tangency_weights, 0.0)
    assert weights.loc["Risk-free asset"] == 1
    assert weights.drop("Risk-free asset").eq(0).all()
    with pytest.raises(ValueError, match="without leverage"):
        complete_portfolio_statistics(tangency, .02, 1.01)
    with pytest.raises(ValueError, match="without leverage"):
        complete_portfolio_weights(tangency_weights, -0.01)


def test_workbook_two_complete_portfolio_handles_nonpositive_excess_return():
    tangency = {
        "Optimizer Expected Return": .01,
        "Optimizer Volatility": .10,
        "Optimizer Sharpe": -.10,
    }
    complete = complete_portfolio_statistics(tangency, .02, .50)
    assert complete["Optimizer Expected Return"] == pytest.approx(.015)
    assert complete["Optimizer Volatility"] == pytest.approx(.05)
    assert complete["Optimizer Sharpe"] == pytest.approx(-.10)


def test_workbook_three_quadratic_utility_and_optimal_complete_portfolio():
    tangency = {
        "Optimizer Expected Return": 0.10765426647647026,
        "Optimizer Volatility": 0.15807465678127394,
        "Optimizer Sharpe": 0.3647280826062194,
    }
    result = utility_optimal_complete_portfolio(tangency, 0.05, 3.0)
    assert result["Unconstrained Risky Portfolio Weight"] == pytest.approx(0.7691051178661094)
    assert result["Risky Portfolio Weight"] == pytest.approx(0.7691051178661094)
    assert result["Risk-Free Asset Weight"] == pytest.approx(0.2308948821338906)
    assert result["Optimizer Expected Return"] == pytest.approx(0.09434219141386974)
    assert result["Optimizer Volatility"] == pytest.approx(0.12157602753540647)
    assert result["Quadratic Utility"] == pytest.approx(
        quadratic_utility(
            result["Optimizer Expected Return"], result["Optimizer Volatility"], 3.0,
        )
    )
    assert result["Allocation Constraint Binding"] is False


def test_workbook_three_utility_allocation_respects_nonleveraged_boundary():
    tangency = {
        "Optimizer Expected Return": 0.15,
        "Optimizer Volatility": 0.10,
        "Optimizer Sharpe": 1.3,
    }
    capped = utility_optimal_complete_portfolio(tangency, 0.02, 1.0)
    assert capped["Unconstrained Risky Portfolio Weight"] == pytest.approx(13.0)
    assert capped["Risky Portfolio Weight"] == 1.0
    assert capped["Allocation Constraint Binding"] is True

    defensive = utility_optimal_complete_portfolio(
        {**tangency, "Optimizer Expected Return": 0.01, "Optimizer Sharpe": -0.1},
        0.02, 3.0,
    )
    assert defensive["Unconstrained Risky Portfolio Weight"] < 0
    assert defensive["Risky Portfolio Weight"] == 0
    assert defensive["Allocation Constraint Binding"] is True
    with pytest.raises(ValueError, match="positive"):
        utility_optimal_complete_portfolio(tangency, 0.02, 0.0)
    with pytest.raises(ValueError, match="positive"):
        quadratic_utility(0.08, 0.10, -1.0)


def test_workbook_two_singular_covariance_is_handled_deterministically():
    base = pd.Series([-.01, .00, .01, .02, -.005])
    singular = pd.DataFrame({"A": base, "B": base})
    weights = minimum_variance_weights(singular)
    assert weights.sum() == pytest.approx(1.0)
    assert weights.between(0, 1).all()
    assert optimizer_statistics(singular, weights)["Optimizer Volatility"] == pytest.approx(
        base.std(ddof=1) * np.sqrt(252)
    )


def test_workbook_two_optimizer_nonconvergence_fails_clearly(returns, monkeypatch):
    class FailedResult:
        success = False
        message = "synthetic non-convergence"
        x = np.array([.5, .5])

    monkeypatch.setattr("portfolio_dashboard.construction.minimize", lambda *args, **kwargs: FailedResult())
    with pytest.raises(RuntimeError, match="synthetic non-convergence"):
        minimum_variance_weights(returns)


def test_explicit_asset_bands_exclusion_and_group_cap_are_enforced(returns):
    minimum = pd.Series({"A": .20, "B": 0.0})
    maximum = pd.Series({"A": .60, "B": .80})
    groups = pd.Series({"A": "Growth", "B": "Defensive"})
    weights = constrained_portfolio_weights(
        returns, "Minimum Variance", minimum_weights=minimum, maximum_weights=maximum,
        groups=groups, group_caps={"Growth": .55},
    )
    assert weights.sum() == pytest.approx(1, abs=1e-6)
    assert weights["A"] >= .20 - 1e-6 and weights["A"] <= .55 + 1e-6
    summary = constraint_validation_summary(weights, minimum, maximum, groups, {"Growth": .55})
    assert summary["Pass"].all()
    assert summary["Breach"].max() <= 1e-6

    excluded = constrained_portfolio_weights(
        returns, "Minimum Variance", minimum_weights=pd.Series({"A": 0.0, "B": 0.0}),
        maximum_weights=pd.Series({"A": 0.0, "B": 1.0}),
    )
    assert excluded["A"] == pytest.approx(0, abs=1e-8)
    assert excluded["B"] == pytest.approx(1, abs=1e-8)


def test_infeasible_constraints_and_invalid_group_caps_fail_clearly(returns):
    with pytest.raises(ValueError, match="cannot satisfy"):
        constrained_portfolio_weights(
            returns, "Minimum Variance",
            minimum_weights=pd.Series({"A": .6, "B": .6}),
            maximum_weights=pd.Series({"A": 1.0, "B": 1.0}),
        )
    with pytest.raises(ValueError, match="infeasible"):
        constrained_portfolio_weights(
            returns, "Minimum Variance",
            minimum_weights=pd.Series({"A": 0.0, "B": 0.0}),
            maximum_weights=pd.Series({"A": 1.0, "B": 1.0}),
            groups=pd.Series({"A": "All", "B": "All"}), group_caps={"All": .9},
        )
    assert parse_group_caps("Growth:60, Defensive:40") == {"Growth": .6, "Defensive": .4}
    with pytest.raises(ValueError, match="Group:percent"):
        parse_group_caps("invalid")


def test_optional_allocation_failure_does_not_abort_pipeline():
    constant = pd.DataFrame({"A": [.01, .01, .01], "B": [.02, .02, .02]})
    from portfolio_dashboard.construction import allocation_methods
    methods, warnings = allocation_methods(constant, pd.Series({"A": .5, "B": .5}), 0.0)
    assert {"Current", "Equal Weight", "Minimum Variance"}.issubset(methods.columns)
    assert "Inverse Volatility" not in methods
    assert "Maximum Sharpe" not in methods
    assert len(warnings) == 2

def test_rebalancing_reconciles():
    plan = rebalancing_plan(pd.Series({"A": .7, "B": .3}), pd.Series({"A": .5, "B": .5}), 100_000)
    assert plan["Estimated Buy / Sell"].sum() == pytest.approx(0)
    assert plan.set_index("Ticker").loc["A", "Action"] == "Sell"
    assert plan.set_index("Ticker").loc["B", "Action"] == "Buy"


def test_rebalancing_default_only_holds_exact_target_weights():
    plan = rebalancing_plan(pd.Series({"A": .5001, "B": .4999}), pd.Series({"A": .5, "B": .5}), 100_000)
    assert plan.set_index("Ticker").loc["A", "Action"] == "Sell"
    exact = rebalancing_plan(pd.Series({"A": .5, "B": .5}), pd.Series({"A": .5, "B": .5}), 100_000)
    assert set(exact["Action"]) == {"Hold"}


def test_buy_and_hold_drifts_without_trades_and_preserves_value_continuity():
    index = pd.bdate_range("2024-01-01", periods=6)
    returns = pd.DataFrame({"A": [.10, 0, 0, 0, 0, 0], "B": [0, 0, 0, 0, 0, 0]}, index=index)
    daily, trades = simulate_rebalancing(returns, pd.Series({"A": .5, "B": .5}), 1_000, "Buy and Hold", .01)
    assert trades.empty and not daily["Rebalanced"].any()
    assert daily.iloc[-1]["Portfolio Value"] == pytest.approx(1_050)
    assert daily.iloc[-1]["Maximum Drift"] > 0
    reconstructed = 1_000 * (1 + daily["Daily Return"]).cumprod()
    assert reconstructed.tolist() == pytest.approx(daily["Portfolio Value"].tolist())


def test_monthly_schedule_trades_only_at_completed_month_end():
    index = pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-29", "2024-03-01"])
    returns = pd.DataFrame({"A": [.02] * 5, "B": [0] * 5}, index=index)
    daily, trades = simulate_rebalancing(returns, pd.Series({"A": .5, "B": .5}), 1_000, "Monthly")
    dates = list(daily.index[daily["Rebalanced"]])
    assert dates == [pd.Timestamp("2024-01-31"), pd.Timestamp("2024-02-29")]
    assert set(trades["Date"]) == set(dates)


@pytest.mark.parametrize(
    ("policy", "expected"),
    [("Quarterly", ["2024-03-29", "2024-06-28", "2024-09-30"]),
     ("Annual", [])],
)
def test_quarterly_and_annual_schedules_use_completed_periods(policy, expected):
    index = pd.bdate_range("2024-01-02", "2024-12-31")
    returns = pd.DataFrame({"A": .001, "B": 0.0}, index=index)
    daily, _ = simulate_rebalancing(returns, pd.Series({"A": .5, "B": .5}), 1_000, policy)
    dates = [date.date().isoformat() for date in daily.index[daily["Rebalanced"]]]
    assert dates == expected


def test_threshold_rebalancing_triggers_only_after_band_breach():
    index = pd.bdate_range("2024-01-01", periods=4)
    returns = pd.DataFrame({"A": [.01, .01, .50, 0], "B": [0, 0, 0, 0]}, index=index)
    daily, _ = simulate_rebalancing(
        returns, pd.Series({"A": .5, "B": .5}), 1_000, "Threshold", threshold=.05,
    )
    assert daily["Rebalanced"].sum() == 1
    trigger_date = daily.index[daily["Rebalanced"]][0]
    assert trigger_date == index[2]
    assert daily.loc[trigger_date, "Maximum Drift"] == pytest.approx(0)


def test_rebalancing_turnover_cost_and_trade_reconciliation():
    index = pd.to_datetime(["2024-01-31", "2024-02-01"])
    returns = pd.DataFrame({"A": [.20, 0], "B": [0, 0]}, index=index)
    daily, trades = simulate_rebalancing(
        returns, pd.Series({"A": .5, "B": .5}), 1_000, "Monthly", transaction_cost_rate=.01,
    )
    first = daily.iloc[0]
    assert first["Turnover"] == pytest.approx(50 / 1_100)
    assert first["Transaction Costs"] == pytest.approx(1.0)
    dated = trades[trades["Date"] == index[0]]
    assert dated["Trade Before Cost"].sum() == pytest.approx(0, abs=1e-10)
    assert dated["Estimated Transaction Cost"].sum() == pytest.approx(first["Transaction Costs"])
    assert first["Portfolio Value"] == pytest.approx(first["Gross Value Before Trade"] - first["Transaction Costs"])


def test_rebalancing_policy_comparison_uses_common_history():
    index = pd.bdate_range("2023-01-02", "2024-12-31")
    returns = pd.DataFrame({
        "A": np.sin(np.arange(len(index)) / 13) * .01,
        "B": np.cos(np.arange(len(index)) / 17) * .006,
    }, index=index)
    summary, histories, trades = compare_rebalancing_policies(
        asset_returns=returns,
        target_weights=pd.Series({"A": .6, "B": .4}),
        initial_value=10_000,
        transaction_cost_rate=.001,
        threshold=.04,
        risk_free_rate=.02,
    )
    assert set(summary.index) == {"Buy and Hold", "Monthly", "Quarterly", "Annual", "Threshold"}
    assert summary.loc["Buy and Hold", "Total Turnover"] == 0
    assert len({len(history) for history in histories.values()}) == 1
    assert set(trades) == set(summary.index)


def test_rebalancing_policy_api_contract_includes_benchmark_and_three_returns():
    signature = inspect.signature(compare_rebalancing_policies)
    assert list(signature.parameters) == [
        "asset_returns", "target_weights", "initial_value", "transaction_cost_rate",
        "threshold", "risk_free_rate", "benchmark_returns",
    ]
    assert signature.parameters["benchmark_returns"].default is None
    index = pd.bdate_range("2024-01-02", periods=12)
    x = np.arange(12)
    returns = pd.DataFrame({
        "A": .001 + .002 * np.sin(x),
        "B": .0005 + .001 * np.cos(x),
    }, index=index)
    result = compare_rebalancing_policies(
        asset_returns=returns,
        target_weights=pd.Series({"A": .6, "B": .4}),
        initial_value=10_000,
        benchmark_returns=pd.Series(.0008 + .0015 * np.sin(x / 2), index=index),
    )
    assert isinstance(result, tuple) and len(result) == 3


def test_rebalancing_policy_comparison_reconciles_benchmark_relative_metrics():
    index = pd.bdate_range("2024-01-02", periods=80)
    returns = pd.DataFrame({
        "A": np.sin(np.arange(len(index)) / 9) * .006 + .0004,
        "B": np.cos(np.arange(len(index)) / 11) * .004 + .0001,
    }, index=index)
    benchmark = pd.Series(np.sin(np.arange(len(index)) / 10) * .005 + .0002, index=index)
    summary, histories, _ = compare_rebalancing_policies(
        asset_returns=returns,
        target_weights=pd.Series({"A": .6, "B": .4}),
        initial_value=10_000,
        transaction_cost_rate=.001,
        threshold=.05,
        risk_free_rate=.02,
        benchmark_returns=benchmark,
    )
    policy = "Buy and Hold"
    active = histories[policy]["Daily Return"] - benchmark
    expected_active = active.mean() * 252
    expected_tracking_error = active.std(ddof=1) * np.sqrt(252)
    assert summary.loc[policy, "Annualized Active Return"] == pytest.approx(expected_active)
    assert summary.loc[policy, "Mean Absolute Periodic Difference"] == pytest.approx(active.abs().mean())
    assert summary.loc[policy, "Tracking Error"] == pytest.approx(expected_tracking_error)
    assert summary.loc[policy, "Information Ratio"] == pytest.approx(
        expected_active / expected_tracking_error
    )

def test_strategy_signal_lag_and_transaction_costs():
    prices = pd.Series([10, 11, 12, 13, 12, 11, 14, 15], index=pd.bdate_range("2024-01-01", periods=8))
    free, _ = momentum_backtest(prices, 2, 3, 0)
    costly, metrics = momentum_backtest(prices, 2, 3, .01)
    expected = free["Signal"].shift(1).fillna(0)
    pd.testing.assert_series_equal(free["Position"], expected, check_names=False)
    assert (costly["Strategy Return"] <= free["Strategy Return"] + 1e-15).all()
    evaluation = costly.iloc[3:]
    assert metrics["Position Changes"] == int((evaluation["Turnover"] > 0).sum())
    assert metrics["Warm-up Observations"] == 3
    assert costly["Strategy Growth"].iloc[:3].isna().all()


def test_strategy_rejects_insufficient_history():
    prices = pd.Series([10, 11, 12], index=pd.bdate_range("2024-01-01", periods=3))
    with pytest.raises(ValueError, match="requires more than 3"):
        momentum_backtest(prices, 2, 3)


@pytest.mark.parametrize("observations", [89, 200])
def test_optional_momentum_skips_without_fake_results(observations):
    prices = pd.Series(
        np.linspace(100, 120, observations),
        index=pd.bdate_range("2024-01-01", periods=observations),
    )
    result = optional_momentum_analysis(prices)
    assert not result.available
    assert result.reason == "insufficient_history"
    assert result.observations_available == observations
    assert result.observations_required == 201
    assert result.data is None
    assert result.metrics is None
    assert f"contains {observations} price observations" in result.detail


def test_optional_momentum_runs_at_201_aligned_observations():
    prices = pd.Series(
        np.linspace(100, 120, 202),
        index=pd.bdate_range("2024-01-01", periods=202),
    )
    prices.iloc[50] = np.nan
    result = optional_momentum_analysis(prices)
    assert result.available
    assert result.observations_available == 201
    assert result.observations_required == 201
    assert result.data is not None
    assert result.metrics is not None


def test_optional_momentum_isolates_and_logs_unexpected_failure(monkeypatch, caplog):
    prices = pd.Series(
        np.linspace(100, 120, 201),
        index=pd.bdate_range("2024-01-01", periods=201),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic strategy failure")

    monkeypatch.setattr("portfolio_dashboard.strategy.momentum_backtest", fail)
    with caplog.at_level("ERROR"):
        result = optional_momentum_analysis(prices)
    assert not result.available
    assert result.reason == "calculation_error"
    assert result.data is None and result.metrics is None
    assert "synthetic strategy failure" in result.detail
    assert "Momentum analysis failed after core analysis completed" in caplog.text

def test_custom_and_historical_stress():
    weights = pd.Series({"A": .6, "B": .4}); shocks = pd.Series({"A": -.2, "B": -.1})
    table, summary = custom_shock(weights, shocks, 1000)
    assert summary["Estimated Portfolio Impact"] == pytest.approx(-.16)
    assert summary["After Value"] == pytest.approx(840)
    dates = pd.bdate_range("2019-01-01", "2023-01-01")
    prices = pd.DataFrame({"A": np.linspace(100, 150, len(dates)), "B": np.linspace(100, 120, len(dates))}, index=dates)
    result = historical_stress(prices, weights, prices["A"])
    assert set(result["Scenario"]) == {"COVID-19 market decline", "2022 equity and rate shock"}
    assert result["Complete"].all()
    assert {"Configured Start", "Configured End", "Actual Start", "Actual End"}.issubset(result.columns)


def test_custom_shock_requires_explicit_complete_inputs():
    weights = pd.Series({"A": .6, "B": .4})
    with pytest.raises(ValueError, match="explicit shock"):
        custom_shock(weights, pd.Series({"A": -.1}), 1000)
    _, summary = custom_shock(weights, pd.Series({"A": .1, "B": .2}), 1000)
    assert summary["Largest Loss Contributor"] == "No loss contributors"


def test_historical_stress_uses_constant_weight_daily_returns(monkeypatch):
    monkeypatch.setattr("portfolio_dashboard.stress.HISTORICAL_STRESS_PERIODS", {"Test": ("2024-01-01", "2024-01-04")})
    dates = pd.bdate_range("2024-01-01", periods=4)
    prices = pd.DataFrame({"A": [100, 200, 100, 200], "B": [100, 100, 200, 200]}, index=dates)
    weights = pd.Series({"A": .5, "B": .5})
    result = historical_stress(prices, weights, prices["A"])
    expected = (1 + portfolio_returns(simple_returns(prices), weights)).prod() - 1
    assert result.loc[0, "Portfolio Return"] == pytest.approx(expected)

def test_main_pipeline_integration(returns):
    prices = 100 * (1 + returns).cumprod()
    benchmark_returns = .7 * returns["A"] + .3 * returns["B"]
    benchmark_prices = 100 * (1 + benchmark_returns).cumprod()
    weights = pd.Series({"A": .6, "B": .4})
    result = run_analysis(prices, benchmark_prices, weights, .02)
    assert result.performance["Total Return"] == pytest.approx((1 + result.portfolio_returns).prod() - 1)
    assert result.return_contributions.sum() == pytest.approx(result.performance["Total Return"])
    assert result.volatility_contributions.sum() == pytest.approx(result.performance["Annualized Volatility"])
    assert result.benchmark["Regression Observations"] == len(result.portfolio_returns)
    assert result.benchmark["Regression Alpha"] == pytest.approx(result.benchmark["Jensen's Alpha"])
    assert result.benchmark["Systematic Risk Share"] + result.benchmark["Idiosyncratic Risk Share"] == pytest.approx(1)
    assert set(["Current", "Equal Weight", "Inverse Volatility"]).issubset(result.allocations.columns)


def test_metric_formatting_preserves_ratios_and_percentages():
    assert metric_value("Total Return", .125) == "12.50%"
    assert metric_value("Historical Arithmetic Annualized Return", .125) == "12.50%"
    assert metric_value("Annualized Variance", .025) == "0.0250"
    assert metric_value("Regression Alpha", .0125) == "1.25%"
    assert metric_value("Systematic Variance", .025) == "0.0250"
    assert metric_value("Treynor Ratio", .08) == "8.00%"
    assert metric_value("Regression Observations", 252.0) == "252"
    assert metric_value("Rebalancing Dates", 4.0) == "4"
    assert metric_value("Sharpe Ratio", 1.25) == "1.25"
    assert metric_value("Position Changes", 3.0) == "3"


def test_report_uses_metric_units_and_selected_rebalancing_method():
    metric_frame = pd.DataFrame({"Value": [.125, 1.25]}, index=["Total Return", "Sharpe Ratio"])
    percentage_frame = pd.DataFrame({"Return Contribution": [.125]}, index=["A"])
    plan = rebalancing_plan(pd.Series({"A": 1.0}), pd.Series({"A": 1.0}), 1_000)
    html = generate_html_report(
        title="Test", tickers=["A"], weights=pd.Series({"A": 1.0}),
        start="2024-01-01", end="2024-12-31", summary=["Summary"],
        performance=metric_frame, risk=metric_frame, benchmark=metric_frame,
        attribution=percentage_frame, allocations=pd.DataFrame({"Current": [1.0]}, index=["A"]),
        rebalancing=plan, rebalancing_method="Current", strategy=metric_frame,
        stress=pd.DataFrame({"Portfolio Impact": [-.1]}, index=["A"]),
        benchmark_ticker="SPX", risk_free_rate=.04, initial_value=1_000,
        health_score=75.0, health_coverage=1.0,
        health_components=pd.DataFrame({
            "Weight": [.25], "Metric Value": [1.0], "Normalized Result": [.75],
            "Points": [18.75], "Rule": ["synthetic rule"], "Available": [True],
        }, index=["Diversification"]),
        comparison=pd.DataFrame({"CAGR": [.10], "Sharpe Ratio": [1.2]}, index=["Current"]),
        insights=pd.DataFrame({"Observation": ["Computed observation"], "Metric": ["Sharpe Ratio"],
                               "Value": [1.2], "Rule": ["Sharpe above zero"]}),
        what_if=pd.DataFrame({"CAGR": [.11]}, index=["What-if"]),
        efficient_frontier=pd.DataFrame({
            "Optimizer Expected Return": [.08], "Optimizer Volatility": [.12],
            "Optimizer Sharpe": [.33],
        }, index=["Frontier 1"]),
        optimized_allocations=pd.DataFrame({"Frontier 1": [1.0]}, index=["A"]),
        rebalancing_policies=pd.DataFrame({"Total Turnover": [.10]}, index=["Quarterly"]),
        rebalancing_history=pd.DataFrame({"Portfolio Value": [1_100], "Transaction Costs": [1.0]}),
        constrained_allocation=pd.DataFrame({"Constrained Weight": [1.0]}, index=["A"]),
        constraint_validation=pd.DataFrame({
            "Constraint": ["Weights sum to 100%"], "Result": [1.0], "Limit": [1.0],
            "Pass": [True], "Breach": [0.0], "Affected Asset": ["Portfolio"],
        }),
        transaction_cost_rate=.001, rebalancing_threshold=.05,
        selected_rebalancing_policy="Quarterly",
        strategy_short_window=50, strategy_long_window=200,
        fixed_income={
            "bond analytics": pd.Series({"Yield to Maturity": .05, "Modified Duration": 4.5, "DV01": .43}),
            "cash-flow schedule": pd.DataFrame({"Coupon": [20.0], "Principal": [1_000.0]}),
        },
    ).decode()
    assert "12.50%" in html
    assert ">1.25<" in html
    assert "Rebalancing plan — Current" in html
    assert "Holdings and weights" in html and "100.00%" in html
    assert "75/100" in html and "100% metric coverage" in html
    assert "Portfolio comparison" in html and "Deterministic research insights" in html
    assert "Efficient frontier" in html and "Optimized allocations" in html
    assert "Rebalancing policy comparison" in html and "Selected rebalancing history" in html
    assert "Custom constrained allocation" in html and "Constraint validation" in html
    assert "Portfolio inputs" in html and "Transaction-cost rate" in html
    assert "Threshold-policy absolute weight-drift trigger: 5.00%" in html
    assert "50/200 trading days" in html
    assert "Benchmark: SPX" in html and "Annual risk-free assumption: 4.00%" in html
    assert "Fixed income — bond analytics" in html and "Fixed-income limitations" in html
    assert "^GSPC" not in html


def test_research_summary_does_not_emit_nan_text():
    summary = research_summary(
        {}, {}, pd.Series({"A": 1.0}), pd.Series({"A": 0.0}), pd.Series({"A": 0.0}), {}, {},
    )
    assert "nan" not in " ".join(summary).lower()
    assert "unavailable" in " ".join(summary).lower()


def test_portfolio_comparison_reuses_constant_weight_performance(returns):
    current = pd.Series({"A": .6, "B": .4})
    allocations = pd.DataFrame({"Current": current, "Equal": [.5, .5]}, index=["A", "B"])
    comparison = portfolio_comparison(returns, allocations, current, .02)
    expected = performance_metrics(portfolio_returns(returns, current), .02)
    assert comparison.loc["Current", "Arithmetic Return"] == pytest.approx(
        expected["Historical Arithmetic Annualized Return"]
    )
    assert comparison.loc["Current", "Sharpe Ratio"] == pytest.approx(expected["Sharpe Ratio"])
    assert comparison.loc["Current", "Weight Distance from Current"] == 0
    assert comparison.loc["Equal", "Weight Distance from Current"] == pytest.approx(.1)


def test_health_score_is_transparent_bounded_and_reports_coverage():
    performance = {"Sharpe Ratio": 1.0, "Maximum Drawdown": -.25}
    benchmark = {"Information Ratio": 0.0}
    score, coverage, components = portfolio_health_score(
        performance, benchmark, pd.Series({"A": .5, "B": .5}), .05
    )
    assert score == pytest.approx(66.6666667)
    assert coverage == pytest.approx(1.0)
    assert components["Points"].sum() == pytest.approx(score)
    assert components["Rule"].str.len().gt(0).all()
    assert components["Normalized Result"].between(0, 1).all()


def test_health_score_rescales_available_components_without_hiding_coverage():
    score, coverage, components = portfolio_health_score(
        {"Sharpe Ratio": np.nan, "Maximum Drawdown": -.25},
        {"Information Ratio": np.nan}, pd.Series({"A": 1.0}), .05,
    )
    assert coverage == pytest.approx(.60)
    assert score == pytest.approx(70.8333333)
    assert components["Available"].sum() == 3


def test_what_if_analysis_reconciles_weights_metrics_and_shock(returns):
    current = pd.Series({"A": .6, "B": .4})
    scenario = pd.Series({"A": .4, "B": .6})
    shocks = pd.Series({"A": -.10, "B": -.20})
    comparison, shock_table, summary = what_if_analysis(
        returns, current, scenario, shocks, 100_000, .02
    )
    assert comparison.loc["What-if", "Weight Distance from Current"] == pytest.approx(.2)
    assert comparison.loc["Change", "Sharpe Ratio"] == pytest.approx(
        comparison.loc["What-if", "Sharpe Ratio"] - comparison.loc["Current", "Sharpe Ratio"]
    )
    assert shock_table["Portfolio Impact"].sum() == pytest.approx(-.16)
    assert summary["After Value"] == pytest.approx(84_000)
    with pytest.raises(ValueError, match="sum to 100"):
        what_if_analysis(returns, current, pd.Series({"A": .4, "B": .5}), shocks, 100_000)


def test_deterministic_insights_are_metric_traceable():
    insights = deterministic_insights(
        {"Sharpe Ratio": .5, "Maximum Drawdown": -.25, "Annualized Volatility": .20},
        {"Excess Return": .03, "Beta": 1.2, "Idiosyncratic Risk Share": .60},
        pd.Series({"A": .7, "B": .3}), pd.Series({"A": .12, "B": .08}), .03,
    )
    assert {"Observation", "Metric", "Value", "Rule"}.issubset(insights.columns)
    assert insights["Rule"].str.len().gt(0).all()
    assert np.isfinite(insights["Value"]).all()
    assert not insights["Observation"].str.contains("buy|sell|recommend", case=False).any()
