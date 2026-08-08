"""Offline smoke tests for the Streamlit entrypoint."""

import base64
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def fake_download_prices(tickers, start, end):
    """Return deterministic adjusted-price-like history without network access."""
    index = pd.bdate_range("2020-01-01", periods=320)
    x = np.arange(len(index))
    return pd.DataFrame(
        {
            ticker: 100 * np.cumprod(1 + 0.0003 + 0.002 * np.sin(x / (11 + offset)))
            for offset, ticker in enumerate(tickers)
        },
        index=index,
    )


@pytest.fixture
def offline_app(monkeypatch):
    monkeypatch.setattr("portfolio_dashboard.data.download_prices", fake_download_prices)
    return AppTest.from_file(APP_PATH).run(timeout=20)


def widget(items, label):
    return next(item for item in items if item.label == label)


def run_analysis(app):
    widget(app.button, "Run analysis").click()
    return app.run(timeout=20)


def plotly_values(value):
    """Decode Plotly's compact numeric-array representation used by AppTest."""
    if isinstance(value, dict) and "bdata" in value:
        return np.frombuffer(base64.b64decode(value["bdata"]), dtype=np.dtype(value["dtype"]))
    return np.asarray(value)


def test_app_renders_helpful_initial_state():
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    assert not app.exception
    assert app.title[0].value == "PortfolioLens"
    assert any("Multi-asset portfolio analytics and investment research" in item.value for item in app.caption)
    assert any(item.value == "Analysis setup" for item in app.subheader)
    expected_controls = {
        "Portfolio tickers", "Portfolio allocation (%)", "Benchmark", "Initial portfolio value",
        "Annual risk-free rate (%)", "Transaction cost rate (%)",
        "Rebalancing drift threshold (%)",
    }
    assert expected_controls <= {
        item.label for collection in (app.text_input, app.number_input) for item in collection
    }
    assert any(item.label == "Portfolio preset" for item in app.selectbox)
    assert any(item.label == "Split equally across investments" for item in app.checkbox)
    assert any(item.label == "Run analysis" for item in app.button)
    assert widget(app.text_input, "Benchmark").value == "SPX"
    assert any("Market data are requested only" in item.value for item in app.info)
    primary = widget(app.get("button_group"), "Primary workspace")
    assert primary.value == "Dashboard"
    assert len(primary.options) == 6
    assert primary.options == [
        "Dashboard", "Analytics", "Research", "Portfolio Construction", "Strategies", "Reports",
    ]
    assert not any("Application build:" in item.value for item in app.caption)
    assert not app.metric


def test_allocation_preview_and_live_summary_are_retail_friendly():
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    assert any(item.label == "Portfolio allocation (%)" for item in app.text_input)
    assert any(item.label == "Split equally across investments" for item in app.checkbox)
    assert not any(item.label == "Allocation details" for item in app.expander)
    assert any("Total allocation: 100% ✓" in item.value for item in app.success)

    allocation = widget(app.text_input, "Portfolio allocation (%)")
    allocation.set_value("50, 35")
    app.run(timeout=20)
    assert any("You entered 2 allocation values for 3 investments" in item.value for item in app.error)
    assert widget(app.button, "Run analysis").disabled
    assert not any(item.label == "Allocation details" for item in app.expander)



def test_compact_allocation_status_for_under_and_overallocation():
    under = AppTest.from_file(APP_PATH).run(timeout=20)
    widget(under.text_input, "Portfolio allocation (%)").set_value("40, 30, 15")
    under.run(timeout=20)
    assert any("Total allocation: 85% · 15% remaining" in item.value for item in under.warning)

    over = AppTest.from_file(APP_PATH).run(timeout=20)
    widget(over.text_input, "Portfolio allocation (%)").set_value("50, 35, 20")
    over.run(timeout=20)
    assert any("Total allocation: 105% · Reduce by 5%" in item.value for item in over.error)


def test_normalize_to_100_is_explicit_and_proportional():
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    widget(app.text_input, "Portfolio allocation (%)").set_value("50, 35, 20")
    app.run(timeout=20)
    normalize_button = widget(app.button, "Normalize to 100%")
    assert not normalize_button.disabled
    normalize_button.click()
    app.run(timeout=20)
    assert widget(app.text_input, "Portfolio allocation (%)").value == "47.62, 33.33, 19.05"
    assert any("Total allocation: 100% ✓" in item.value for item in app.success)
    assert not widget(app.button, "Run analysis").disabled


def test_professional_footer_renders_on_initial_analysis_and_fixed_income_paths(offline_app):
    def assert_footer(app):
        matching = [
            item.proto.body for item in app.get("html")
            if 'class="portfolio-footer"' in item.proto.body
        ]
        assert len(matching) == 1
        footer = matching[0]
        assert "Developed by" in footer
        assert "Jameel Shaikh" in footer
        assert "OUT PARTNERS" in footer
        assert 'href="https://github.com/Jams411"' in footer
        assert 'href="https://outpartners.org/"' in footer
        assert footer.count('target="_blank"') == 2
        assert "font-family: 'Poppins', sans-serif" in footer
        assert ".portfolio-footer__developer { font-weight: 400; }" in footer
        assert ".portfolio-footer__partner { font-weight: 600; }" in footer

    assert_footer(offline_app)
    run_analysis(offline_app)
    assert_footer(offline_app)
    offline_app.session_state["analysis_tab"] = "Fixed Income"
    offline_app.run(timeout=20)
    assert not offline_app.exception
    assert_footer(offline_app)


def test_performance_evaluation_tab_exposes_scorecard_and_fama_diagnostics(offline_app):
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Performance Evaluation"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "Performance Evaluation" for item in offline_app.subheader)
    headings = {item.value for item in offline_app.markdown}
    assert {"### Performance Summary", "### Risk-Adjusted Performance", "### Benchmark Evaluation", "### Manager Evaluation"} <= headings
    assert {"Sharpe ratio", "Jensen's alpha", "Information ratio", "Net selectivity"} <= {
        item.label for item in offline_app.metric
    }
    assert any(
        {"Selectivity", "Diversification Effect", "Net Selectivity"} <= set(item.value.index)
        for item in offline_app.dataframe
    )
    labels = {item.label for item in offline_app.get("download_button")}
    assert {"Download performance evaluation CSV", "Download rolling evaluation CSV"} <= labels


def test_performance_tab_exposes_normalized_holding_chart_and_export(offline_app):
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Performance"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "Performance" for item in offline_app.subheader)
    assert any(item.label == "Holdings to display" for item in offline_app.multiselect)
    assert any(item.label == "Include benchmark (SPX)" for item in offline_app.checkbox)
    assert any(item.label == "Chart scale" for item in offline_app.get("button_group"))
    titles = [
        json.loads(item.proto.spec).get("layout", {}).get("title", {}).get("text", "")
        for item in offline_app.get("plotly_chart")
    ]
    assert "Normalized performance by holding" in titles
    labels = {item.label for item in offline_app.get("download_button")}
    assert "Download normalized holding performance CSV" in labels

    normalized_spec = json.loads(
        next(item.proto.spec for item in offline_app.get("plotly_chart")
             if json.loads(item.proto.spec).get("layout", {}).get("title", {}).get("text", "")
             == "Normalized performance by holding")
    )
    assert normalized_spec["layout"]["yaxis"]["title"]["text"] == "Growth of $1"
    assert normalized_spec["layout"]["legend"]["title"]["text"] == "Holding"
    assert all(float(np.asarray(plotly_values(trace["y"]))[0]) == pytest.approx(1.0)
               for trace in normalized_spec["data"] if trace.get("name") != "Benchmark (SPX)")


def test_portfolio_optimization_is_visible_before_analysis():
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    app.session_state["analysis_tab"] = "Portfolio Optimization"
    app.run(timeout=20)
    assert not app.exception
    assert any(item.value == "Portfolio Optimization & Rebalancing" for item in app.subheader)
    assert any("Market data are requested only" in item.value for item in app.info)
    assert widget(app.get("button_group"), "Primary workspace").value == "Portfolio Construction"


def test_app_rejects_multiple_benchmark_tickers_before_download():
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    benchmark = next(item for item in app.text_input if item.label == "Benchmark")
    benchmark.set_value("SPY, VTI")
    next(item for item in app.button if item.label == "Run analysis").click()
    app.run(timeout=20)
    assert not app.exception
    assert any("exactly one benchmark ticker" in item.value for item in app.error)


def test_default_spx_uses_provider_symbol_without_mapping_banner(offline_app):
    run_analysis(offline_app)
    assert not offline_app.exception and not offline_app.error
    result = offline_app.session_state["result"]
    assert result["benchmark_ticker"] == "SPX"
    assert result["benchmark_provider_ticker"] == "^GSPC"
    assert result["analysis"].benchmark_prices.name == "Benchmark"
    assert result["benchmark_alias_notice"] is None
    assert not any("mapped to Yahoo Finance symbol" in item.value for item in offline_app.info)
    assert any("benchmark: SPX" in item.value for item in offline_app.caption)
    offline_app.session_state["analysis_tab"] = "Benchmark & Attribution"
    offline_app.run(timeout=30)
    chart_payload = " ".join(item.proto.spec for item in offline_app.get("plotly_chart"))
    assert "SPX" in chart_payload
    assert "^GSPC" not in chart_payload


def test_security_analysis_is_visible_with_offline_data(offline_app):
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Security Analysis"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "Security Analysis" for item in offline_app.subheader)
    assert any("Single-Index Security Analysis" in item.value for item in offline_app.markdown)
    assert any("Benchmark: SPX" in item.value for item in offline_app.caption)
    assert any(item.label == "Security to inspect" for item in offline_app.selectbox)
    assert any(item.label == "Annualized regression alpha" for item in offline_app.metric)
    assert any(
        {
            "Regression Alpha", "Beta", "R-Squared", "Residual Volatility",
            "Systematic Variance", "Idiosyncratic Variance",
            "Systematic Risk Share", "Idiosyncratic Risk Share",
            "Jensen's Alpha", "Treynor Ratio",
        } <= set(item.value.columns)
        for item in offline_app.dataframe
    )
    titles = " ".join(
        json.loads(item.proto.spec).get("layout", {}).get("title", {}).get("text", "")
        for item in offline_app.get("plotly_chart")
    )
    assert "Security Characteristic Line" in titles
    assert "Single-index residuals" in titles
    labels = {item.label for item in offline_app.get("download_button")}
    assert "Download security comparison CSV" in labels
    assert "Download selected regression observations CSV" in labels


def test_asset_pricing_tab_exposes_capm_and_security_market_line(offline_app):
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Asset Pricing"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "Asset Pricing" for item in offline_app.subheader)
    assert any(item.label == "Security for CAPM review" for item in offline_app.selectbox)
    metric_labels = {item.label for item in offline_app.metric}
    assert {"Beta", "Historical arithmetic return", "CAPM required return", "Jensen's alpha"} <= metric_labels
    assert any("Benchmark: SPX" in item.value for item in offline_app.caption)
    assert any(
        {"Beta", "Historical Arithmetic Return", "CAPM Required Return", "Jensen's Alpha", "Position vs SML"}
        <= set(item.value.columns)
        for item in offline_app.dataframe
    )
    titles = " ".join(
        json.loads(item.proto.spec).get("layout", {}).get("title", {}).get("text", "")
        for item in offline_app.get("plotly_chart")
    )
    assert "Security Market Line" in titles
    assert any(item.label == "Download CAPM analysis CSV" for item in offline_app.get("download_button"))


def test_portfolio_strategies_tab_exposes_policy_and_benchmark_comparison(offline_app):
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Portfolio Strategies"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "Portfolio Strategies & Momentum" for item in offline_app.subheader)
    assert any(item.label == "Strategy policy" for item in offline_app.selectbox)
    assert {"Active return", "Tracking error", "Information ratio", "Total turnover"} <= {
        item.label for item in offline_app.metric
    }
    assert any(
        {"Annualized Active Return", "Mean Absolute Periodic Difference", "Tracking Error", "Information Ratio"}
        <= set(item.value.columns)
        for item in offline_app.dataframe
    )
    labels = {item.label for item in offline_app.get("download_button")}
    assert {"Download strategy history", "Download strategy trade log"} <= labels
    assert not any("Momentum analysis was skipped" in item.value for item in offline_app.warning)
    assert any(item.label == "Download strategy results CSV" for item in offline_app.get("download_button"))


def test_short_history_renders_dashboard_and_explains_skipped_momentum(monkeypatch):
    def short_prices(tickers, start, end):
        index = pd.bdate_range("2026-04-01", periods=89)
        x = np.arange(len(index))
        return pd.DataFrame(
            {
                ticker: 100 * np.cumprod(1 + 0.0003 + 0.002 * np.sin(x / (11 + offset)))
                for offset, ticker in enumerate(tickers)
            },
            index=index,
        )

    monkeypatch.setattr("portfolio_dashboard.data.download_prices", short_prices)
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    widget(app.date_input, "Start date").set_value("2026-04-01")
    widget(app.date_input, "End date").set_value("2026-08-08")
    app.run(timeout=20)
    assert any("at least 201 trading observations" in item.value for item in app.caption)

    run_analysis(app)
    assert not app.exception
    assert "result" in app.session_state
    momentum = app.session_state["result"]["momentum"]
    assert not momentum.available
    assert momentum.data is None and momentum.metrics is None
    assert not any("Analysis could not run" in item.value for item in app.error)
    dashboard_html = "".join(item.proto.body for item in app.get("html"))
    assert "Portfolio value" in dashboard_html
    chart_titles = {
        json.loads(item.proto.spec).get("layout", {}).get("title", {}).get("text", "")
        for item in app.get("plotly_chart")
    }
    assert "Portfolio vs SPX" in chart_titles

    non_strategy_sections = {
        "Dashboard": "Dashboard",
        "Analytics": "Performance",
        "Research": "Security Analysis",
        "Portfolio Construction": "Portfolio Optimization & Rebalancing",
        "Reports": "Research Workspace",
    }
    for workspace, section in non_strategy_sections.items():
        app.session_state["analysis_tab"] = section
        app.run(timeout=30)
        assert not app.exception, workspace
        assert not any("Momentum analysis was skipped" in item.value for item in app.warning), workspace
        assert not any("Analysis could not run" in item.value for item in app.error), workspace
        assert app.session_state["result"]["momentum"].observations_available == 89

    app.session_state["analysis_tab"] = "Portfolio Strategies"
    app.run(timeout=30)
    assert not app.exception
    assert any(
        item.value == "Momentum analysis was skipped because the selected period is too short."
        for item in app.warning
    )
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Available observations"] == "89"
    assert metrics["Required observations"] == "201"
    assert any("Choose an earlier start date" in item.value for item in app.markdown)
    assert not any(item.label == "Download strategy results CSV" for item in app.get("download_button"))

    app.session_state["analysis_tab"] = "Dashboard"
    app.run(timeout=30)
    assert not any("Momentum analysis was skipped" in item.value for item in app.warning)
    assert app.session_state["result"]["momentum"].observations_available == 89


def test_asset_allocation_tab_exposes_comparison_contributions_and_trades(offline_app):
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Asset Allocation"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "Asset Allocation" for item in offline_app.subheader)
    headings = {item.value for item in offline_app.markdown}
    assert {"### Current and model allocations", "### Risk and return comparison", "### Current allocation contributions", "### Implementation trades"} <= headings
    assert any(item.label == "Allocation for implementation review" for item in offline_app.selectbox)
    labels = {item.label for item in offline_app.get("download_button")}
    assert {"Download allocation comparison CSV", "Download allocation contributions CSV", "Download implementation trades CSV"} <= labels


def test_etf_research_tab_exposes_screening_and_holdings_workflow(offline_app):
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "ETF Research"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "ETF Research" for item in offline_app.subheader)
    headings = {item.value for item in offline_app.markdown}
    assert {"### Universe research", "### Security screening", "### Holdings look-through"} <= headings
    assert any({"Historical Arithmetic Return", "Volatility", "Sharpe Ratio"} <= set(item.value.columns) for item in offline_app.dataframe)
    assert any({"Passes Screen", "Regression Alpha", "Alpha p-Value"} <= set(item.value.columns) for item in offline_app.dataframe)
    labels = {item.label for item in offline_app.get("download_button")}
    assert {"Download universe research CSV", "Download security screen CSV", "Download holdings template"} <= labels
    assert any("Upload a holdings CSV" in item.value for item in offline_app.info)


def test_nondefault_benchmark_alias_shows_mapping_banner(offline_app):
    widget(offline_app.text_input, "Benchmark").set_value("sp500")
    run_analysis(offline_app)
    result = offline_app.session_state["result"]
    assert result["benchmark_ticker"] == "SP500"
    assert result["benchmark_provider_ticker"] == "^GSPC"
    assert any(
        "SP500 was mapped to Yahoo Finance symbol ^GSPC." in item.value
        for item in offline_app.info
    )


def test_equal_weight_mode_ignores_invalid_manual_weights(offline_app):
    widget(offline_app.text_input, "Portfolio tickers").set_value("SPY, AGG, GLD")
    widget(offline_app.text_input, "Portfolio allocation (%)").set_value("invalid, stale, weights")
    widget(offline_app.checkbox, "Split equally across investments").set_value(True)
    run_analysis(offline_app)
    assert not offline_app.exception and not offline_app.error
    weights = offline_app.session_state["result"]["weights"]
    assert weights.tolist() == pytest.approx([1 / 3, 1 / 3, 1 / 3])
    assert widget(offline_app.text_input, "Portfolio allocation (%)").disabled


def test_research_workspace_is_initialized_from_computed_analysis(offline_app):
    widget(offline_app.text_input, "Portfolio tickers").set_value("SPY, AGG, GLD")
    widget(offline_app.text_input, "Portfolio allocation (%)").set_value("50,35,15")
    run_analysis(offline_app)
    assert not offline_app.exception
    assert "what_if_weights" in offline_app.session_state
    assert "what_if_shocks" in offline_app.session_state
    assert "Portfolio value" in "".join(item.proto.body for item in offline_app.get("html"))
    offline_app.session_state["analysis_tab"] = "Research Workspace"
    offline_app.run(timeout=20)
    assert not offline_app.exception
    assert any(item.value == "Investment research workspace" for item in offline_app.subheader)
    assert any(button.label == "Run what-if analysis" for button in offline_app.button)


def test_portfolio_optimization_view_exposes_workbook_two_tools_offline(offline_app):
    widget(offline_app.text_input, "Portfolio tickers").set_value("SPY, QQQ, TLT, GLD")
    widget(offline_app.text_input, "Portfolio allocation (%)").set_value("40,30,20,10")
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Portfolio Optimization"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "Portfolio Optimization & Rebalancing" for item in offline_app.subheader)
    assert any(item.label == "Policy detail" for item in offline_app.selectbox)
    assert any(item.label == "Construct target-return portfolio" for item in offline_app.button)
    assert any(
        item.label == "Risk preference — allocation to the tangency portfolio (%)"
        for item in offline_app.slider
    )
    assert any(item.label == "Risk aversion coefficient (A)" for item in offline_app.number_input)
    assert any(item.label == "Complete portfolio selection method" for item in offline_app.get("button_group"))
    assert any("Modern portfolio construction tools" in item.value for item in offline_app.caption)
    assert any("Current and optimized portfolio statistics" in item.value for item in offline_app.markdown)
    assert any("Optimized weights" in item.value for item in offline_app.markdown)
    assert any(item.label == "Download complete-portfolio weights" for item in offline_app.get("download_button"))
    assert any(item.label == "Download optimized weights" for item in offline_app.get("download_button"))


def test_frontier_chart_reconciles_professional_traces_offline(offline_app):
    widget(offline_app.text_input, "Portfolio tickers").set_value("SPY, AGG, GLD")
    widget(offline_app.text_input, "Portfolio allocation (%)").set_value("50,35,15")
    widget(offline_app.number_input, "Annual risk-free rate (%)").set_value(4.0)
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Portfolio Optimization"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    specification = json.loads(offline_app.get("plotly_chart")[0].proto.spec)
    assert specification["layout"]["title"]["text"] == "Efficient Frontier and Capital Allocation Line"
    names = {trace.get("name") for trace in specification["data"]}
    assert {
        "Efficient Frontier", "CAL", "Current", "GMV", "Tangency", "Complete",
    } <= names
    line = next(trace for trace in specification["data"] if trace.get("name") == "CAL")
    line_x, line_y = plotly_values(line["x"]), plotly_values(line["y"])
    assert line_x[0] == pytest.approx(0.0)
    assert line_y[0] == pytest.approx(.04)
    tangency = next(trace for trace in specification["data"] if trace.get("name") == "Tangency")
    tangency_x, tangency_y = plotly_values(tangency["x"]), plotly_values(tangency["y"])
    assert line_x[-1] == pytest.approx(tangency_x[0])
    assert line_y[-1] == pytest.approx(tangency_y[0])
    for name in ("Current", "GMV", "Tangency", "Complete"):
        trace = next(item for item in specification["data"] if item.get("name") == name)
        assert trace["mode"] == "markers"
        assert "Portfolio" in trace["hovertemplate"]
    assert any(item.label == "Optimization Diagnostics" for item in offline_app.expander)


def test_workbook_one_risk_foundations_render_and_export_offline(offline_app):
    widget(offline_app.text_input, "Portfolio tickers").set_value("SPY, QQQ, TLT, GLD")
    widget(offline_app.text_input, "Portfolio allocation (%)").set_value("40,30,20,10")
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Risk"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "Risk and diversification" for item in offline_app.subheader)
    labels = {item.label for item in offline_app.metric}
    assert {
        "Weighted standalone volatility", "Portfolio volatility",
        "Diversification reduction", "Reduction vs. standalone",
    } <= labels
    assert any("Asset-level return and risk foundations" in item.value for item in offline_app.markdown)
    assert any(
        button.label == "Download asset risk-and-return table"
        for button in offline_app.get("download_button")
    )


def test_failed_run_clears_prior_results_and_successful_rerun_recovers(offline_app):
    widget(offline_app.text_input, "Portfolio tickers").set_value("SPY, AGG, GLD")
    widget(offline_app.text_input, "Portfolio allocation (%)").set_value("50,35,15")
    run_analysis(offline_app)
    assert "result" in offline_app.session_state
    assert widget(offline_app.get("button_group"), "Primary workspace")

    widget(offline_app.text_input, "Benchmark").set_value("SPY, VTI")
    offline_app.run(timeout=20)
    assert "result" not in offline_app.session_state
    assert widget(offline_app.get("button_group"), "Primary workspace")
    run_analysis(offline_app)
    assert any("exactly one benchmark ticker" in item.value for item in offline_app.error)
    assert "result" not in offline_app.session_state
    assert widget(offline_app.get("button_group"), "Primary workspace")
    assert not offline_app.metric

    widget(offline_app.text_input, "Benchmark").set_value("SPY")
    run_analysis(offline_app)
    assert not offline_app.error
    assert "result" in offline_app.session_state
    assert widget(offline_app.get("button_group"), "Primary workspace")
    assert offline_app.session_state["result"]["weights"].tolist() == pytest.approx([.50, .35, .15])


def test_grouped_navigation_keeps_every_major_section_reachable():
    expected = {
        "Dashboard": ("Dashboard",),
        "Analytics": ("Performance", "Performance Evaluation", "Risk", "Benchmark & Attribution", "Stress Testing"),
        "Research": ("Security Analysis", "Asset Pricing", "ETF Research", "Fixed Income"),
        "Portfolio Construction": ("Portfolio Optimization & Rebalancing", "Asset Allocation"),
        "Strategies": ("Portfolio Strategies & Momentum",),
        "Reports": ("Research Workspace", "Research Report", "Methodology & Limitations"),
    }
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    primary = widget(app.get("button_group"), "Primary workspace")
    assert primary.options == list(expected)
    assert len(primary.options) <= 6
    for workspace, sections in expected.items():
        for section in sections:
            app.session_state["analysis_tab"] = section
            app.run(timeout=20)
            assert not app.exception
            assert app.session_state["primary_workspace"] == workspace
            assert app.session_state["workspace_section"] == section
            assert any(item.value == section for item in app.subheader)


def test_sidebar_groups_and_compact_header_contract():
    source = APP_PATH.read_text()
    for label in ("Advanced assumptions", "Implementation", "Strategy settings", "About"):
        assert f'st.expander("{label}"' in source
    assert source.index('.button("Run analysis"') < source.index('st.expander("Advanced assumptions"')
    assert source.index('key="primary-actions"') < source.index('**Analysis period**')
    assert "position: sticky" in source
    assert "padding: 0.05rem 0 0.1rem" in source
    assert "gap=\"xxsmall\"" in source
    assert "margin-top: -0.1rem" in source
    assert "margin-bottom: -0.1rem" in source
    assert 'key="analysis-period"' in source
    assert '[data-testid="stDateInput"] [data-baseweb="input"]' in source
    assert "background: transparent" in source
    assert "border: 0" in source
    assert 'key="allocation-status"' in source
    assert "display: block" in source
    assert "text-align: left" in source
    assert ".st-key-allocation-status [data-testid=\"stAlert\"] p" in source
    assert "Total allocation:" in source
    assert "Allocation details" not in source
    assert "height: auto !important" in source
    assert "min-height: 0 !important" in source
    assert "max-height: none !important" in source
    assert "padding: 0 !important" in source
    assert "background: transparent !important" in source
    assert "border: 0 !important" in source
    assert "border-radius: 0 !important" in source
    assert "box-shadow: none !important" in source
    assert "font-size: 13px" in source
    assert "line-height: 1.2" in source
    assert "overflow: visible" in source
    assert "::before" in source and "::after" in source
    assert "padding-top: 2.25rem !important" in source
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    assert app.title[0].value == "PortfolioLens"
    assert any(button.label == "Run analysis" for button in app.button)
    assert any(button.label == "Reset" for button in app.button)
    assert any(item.value.startswith("Total allocation:") for item in app.success)
    assert not any("Application build:" in caption.value for caption in app.caption)


def test_portfolio_construction_retains_allocation_and_rebalancing_details(offline_app):
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Portfolio Optimization"
    offline_app.run(timeout=30)
    assert not offline_app.exception
    assert any(item.value == "Portfolio Optimization & Rebalancing" for item in offline_app.subheader)
    assert any(
        {"Current Portfolio", "Global Minimum Variance", "Tangency (Maximum Sharpe)"}
        <= set(item.value.columns)
        for item in offline_app.dataframe
    )
    assert any(
        {"Current Weight", "Target Weight", "Weight Change"} <= set(item.value.columns)
        for item in offline_app.dataframe
    )


def test_dashboard_key_metrics_and_state_survive_navigation(offline_app):
    widget(offline_app.text_input, "Portfolio tickers").set_value("SPY, QQQ, TLT, GLD")
    widget(offline_app.text_input, "Portfolio allocation (%)").set_value("40,25,20,15")
    run_analysis(offline_app)
    expected_order = [
        "Portfolio value", "Total return", "CAGR", "Volatility", "Sharpe ratio", "Maximum drawdown",
        "Beta", "Tracking error", "Information ratio", "Largest risk contributor",
        "Relative benchmark result",
    ]
    metric_html = "".join(item.proto.body for item in offline_app.get("html"))
    assert all(label in metric_html for label in expected_order)
    assert [metric_html.index(label) for label in expected_order] == sorted(
        metric_html.index(label) for label in expected_order
    )
    assert re.search(r"Portfolio value: \$[\d,.]+[KMB]?", metric_html)
    saved_weights = offline_app.session_state["result"]["weights"].copy()
    for section in ("Risk", "ETF Research", "Research Report", "Dashboard"):
        offline_app.session_state["analysis_tab"] = section
        offline_app.run(timeout=30)
        assert not offline_app.exception
        pd.testing.assert_series_equal(offline_app.session_state["result"]["weights"], saved_weights)
    assert any(item.label == "Download HTML report" for item in offline_app.get("download_button")) is False
    offline_app.session_state["analysis_tab"] = "Research Report"
    offline_app.run(timeout=30)
    assert any(item.label == "Download HTML report" for item in offline_app.get("download_button"))


def test_dashboard_uses_responsive_semantic_metric_grid_without_placeholders(offline_app):
    run_analysis(offline_app)
    html_bodies = [item.proto.body for item in offline_app.get("html")]
    combined = "".join(html_bodies)
    dashboard_chart = json.loads(offline_app.get("plotly_chart")[0].proto.spec)
    assert dashboard_chart["layout"]["height"] == 400
    assert sum('<section class="financial-metric-grid' in body for body in html_bodies) == 2
    assert combined.count('financial-metric-grid financial-metric-grid--') == 2
    assert combined.count('role="listitem"') == 11
    assert "display: flex" in combined
    assert "flex-wrap: wrap" in combined
    assert "flex: 1 1 8.625rem" in combined
    assert "height: 6rem" in combined
    assert "padding: 0.3rem 0.75rem 0.25rem" in combined
    assert "gap: 0.4rem" in combined
    assert "margin: 0 0 0.3rem" in combined
    assert "line-height: 1rem" in combined
    assert "line-height: 0.95rem" in combined
    assert "@media (max-width: 700px)" in combined
    assert "financial-metric-grid--secondary" in combined
    assert "placeholder" not in combined.lower()


def test_mobile_plotly_and_table_contract_is_shared_across_dashboard(offline_app):
    run_analysis(offline_app)
    source = APP_PATH.read_text()
    html = "".join(item.proto.body for item in offline_app.get("html"))
    assert "@media (max-width: 700px)" in html
    assert 'padding: 2.75rem 0.75rem 3rem' in html
    assert 'padding-top: 2.25rem !important' in html
    assert '[data-testid="stPlotlyChart"]' in html
    assert '[data-testid="stDataFrame"]' in html
    assert "overflow-x: auto" in html
    assert "calc(33.333% - 0.5rem)" in html
    assert 'r=12 if mobile else 152 if responsive_legend else 10' in source
    assert 'orientation="h" if mobile or not responsive_legend else "v"' in source
    assert source.count("st.plotly_chart(") == 1
    assert 'width="stretch"' in source

    charts = offline_app.get("plotly_chart")
    assert charts
    for chart in charts:
        specification = json.loads(chart.proto.spec)
        configuration = json.loads(chart.proto.config)
        layout = specification["layout"]
        assert configuration["responsive"] is True
        assert configuration["displaylogo"] is False
        assert configuration["displayModeBar"] is True
        assert {"pan2d", "select2d", "lasso2d", "autoScale2d"} <= set(
            configuration["modeBarButtonsToRemove"]
        )
        assert layout["autosize"] is True
        assert "width" not in layout
        assert layout["height"] <= 440
        if layout.get("showlegend"):
            assert layout["legend"]["orientation"] == "h"
            assert layout["legend"]["y"] < 0
            assert layout["margin"]["r"] == 10


def test_asset_pricing_uses_marker_only_mobile_labels(offline_app):
    run_analysis(offline_app)
    offline_app.session_state["analysis_tab"] = "Asset Pricing"
    offline_app.run(timeout=30)
    specification = json.loads(offline_app.get("plotly_chart")[0].proto.spec)
    securities = next(
        trace for trace in specification["data"] if trace.get("name") == "Historical security return"
    )
    assert securities["mode"] == "markers"
    assert "Security: %{text}" in securities["hovertemplate"]


def test_dashboard_color_classes_only_mark_directional_metrics(offline_app):
    run_analysis(offline_app)
    combined = "".join(item.proto.body for item in offline_app.get("html"))
    articles = re.findall(r'<article class="([^"]+)"[^>]*>(.*?)</article>', combined, re.DOTALL)
    tones_by_label = {}
    for classes, body in articles:
        label = re.search(r'financial-metric-card__label">([^<]+)', body).group(1)
        tone = re.search(r"financial-metric-card--([a-z]+)", classes).group(1)
        tones_by_label[label] = tone
    assert tones_by_label["Portfolio value"] == "primary"
    assert tones_by_label["Maximum drawdown"] == "negative"
    assert tones_by_label["Volatility"] == "neutral"
    assert tones_by_label["Beta"] == "neutral"
    assert tones_by_label["Tracking error"] == "neutral"
    assert tones_by_label["Largest risk contributor"] == "neutral"
    assert {label for label, tone in tones_by_label.items() if tone in {"positive", "negative"}} <= {
        "Total return", "CAGR", "Sharpe ratio", "Maximum drawdown",
        "Information ratio", "Relative benchmark result",
    }


def test_fixed_income_workspace_is_reachable_without_market_data_and_preserves_state():
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    app.session_state["analysis_tab"] = "Fixed Income"
    app.run(timeout=20)
    assert not app.exception
    assert app.session_state["primary_workspace"] == "Research"
    assert any(item.value == "Fixed Income" for item in app.subheader)
    view = widget(app.get("button_group"), "Fixed-income view")
    assert view.options == ["Bond calculator", "Bond portfolio", "Rate scenarios", "Bond selection"]
    assert any(item.label == "Calculate bond analytics" for item in app.button)
    widget(app.button, "Calculate bond analytics").click()
    app.run(timeout=20)
    assert not app.exception
    assert {
        "Clean price", "Dirty price", "Accrued interest", "Current yield", "YTM",
        "Macaulay duration", "Modified duration", "Dollar duration", "DV01 / PVBP", "Convexity",
    } <= {item.label for item in app.metric}
    assert "fi_calculator_result" in app.session_state
    app.session_state["analysis_tab"] = "Dashboard"
    app.run(timeout=20)
    app.session_state["analysis_tab"] = "Fixed Income"
    app.run(timeout=20)
    assert "fi_calculator_result" in app.session_state


def test_fixed_income_portfolio_scenario_selection_and_exports_render_offline():
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    app.session_state["analysis_tab"] = "Fixed Income"
    app.run(timeout=20)
    view = widget(app.get("button_group"), "Fixed-income view")
    view.set_value("Bond portfolio")
    app.run(timeout=20)
    widget(app.button, "Analyze bond portfolio").click()
    app.run(timeout=20)
    assert not app.exception and "fi_portfolio_analysis" in app.session_state
    assert {"Market value", "Weighted YTM", "Modified duration", "Portfolio DV01", "Portfolio convexity"} <= {
        item.label for item in app.metric
    }
    assert any(item.label == "Download bond portfolio analytics CSV" for item in app.get("download_button"))

    widget(app.get("button_group"), "Fixed-income view").set_value("Rate scenarios")
    app.run(timeout=20)
    widget(app.button, "Run rate scenario").click()
    app.run(timeout=20)
    assert not app.exception and "fi_portfolio_scenario" in app.session_state
    assert any(item.label == "Download rate scenario CSV" for item in app.get("download_button"))

    widget(app.get("button_group"), "Fixed-income view").set_value("Bond selection")
    app.run(timeout=20)
    widget(app.button, "Apply filters and rank").click()
    app.run(timeout=20)
    assert not app.exception and "fi_selection_result" in app.session_state
    assert any("Ranking formula:" in item.value for item in app.info)
    assert any(item.label == "Download selected bonds CSV" for item in app.get("download_button"))
