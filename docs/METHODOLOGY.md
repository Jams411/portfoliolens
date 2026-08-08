# Methodology and limitations

## Presentation architecture

The six-workspace navigation and executive Dashboard are presentation layers only. Dashboard cards read the same `Analysis` result dictionaries and contribution series used by detailed workspaces and reports; they do not recompute formulas. Secondary workspace navigation changes only Streamlit session-state selectors. It does not download data, rerun the analytical pipeline, change weights, alter the benchmark, or mutate saved results. Input changes and failed runs clear dependent output state before new results can render.

The Dashboard ending value is `initial value × (1 + total return)`. Allocation and Euler volatility contribution use the existing portfolio weights and risk-contribution series. Its efficient-frontier preview uses the already calculated frontier. Deterministic insights use the same fixed evidence rules documented below. Detailed assumptions and limitations remain authoritative in this document and the Methodology & Limitations report view.

## Fixed-income analytics

Fixed income is a separate explicit-instrument model. It never derives coupon, maturity, issuer, sector, credit quality, callable status, tax status, or cash flows from a ticker or adjusted-price history. Standard option-free fixed-rate bonds and zero-coupon bonds support annual, semiannual, quarterly, and monthly frequencies.

### Cash flows, dates, and price convention

For face value `F`, annual coupon rate `c`, and frequency `m`, each coupon is `C=F×c/m`; principal `F` is paid at maturity. Coupon dates are generated backward from maturity. Future payment times are expressed in coupon periods from settlement, including the fractional first period. Actual/Actual uses actual elapsed days divided by actual days in the coupon period. The supported 30/360 convention uses the standard day-adjustment rule implemented in `fixed_income.py`. No other day-count basis is silently approximated.

For nominal annual YTM `y` compounded `m` times per year and payment-period exponent `k`:

- Dirty price: `P_dirty = Σ CF_k / (1+y/m)^k`
- Accrued interest: `AI = C × elapsed coupon-period fraction`
- Clean price: `P_clean = P_dirty − AI`
- Current yield: `F×c / P_clean`
- YTM: the bracketed numerical root that reconciles entered clean price to the discounted contractual cash flows

Clean price is the quoted price excluding accrued interest. Dirty price is the settlement value including accrued interest and is therefore the basis for market value and rate-risk aggregation. Zero-coupon schedules expose only the maturity payment and have zero accrued interest/current yield.

### Duration, DV01, convexity, and repricing

Let `PV_k` be the present value of cash flow `k`, and let `k/m` be years from settlement:

- Macaulay duration: `D_Mac = Σ[(k/m)×PV_k] / P_dirty`
- Modified duration: `D_Mod = D_Mac / (1+y/m)`
- Dollar duration: `D_$ = D_Mod × P_dirty`
- DV01/PVBP: `DV01 = D_$ × 0.0001`
- Discrete convexity: `Cvx = Σ[PV_k×k×(k+1)/(m²×(1+y/m)²)] / P_dirty`
- Duration-only proportional change: `−D_Mod×Δy`
- Duration-plus-convexity proportional change: `−D_Mod×Δy + 0.5×Cvx×(Δy)²`
- Full repricing: rebuild dirty price at `y+Δy`
- Approximation error: approximation minus full repricing, reported in price and proportional units

Macaulay duration is a present-value-weighted time measure; modified duration is yield sensitivity. Effective duration is not calculated and modified duration is never relabeled as effective duration. Yield shocks are entered and displayed in basis points, with `100 bps = 0.01` in annual yield.

### Bond portfolio aggregation

For holding quantity `q_i`, dirty price `P_i`, and market value `MV_i=q_iP_i`, portfolio weight is `w_i=MV_i/ΣMV`. Portfolio Macaulay duration, modified duration, and convexity are market-value-weighted sums. Portfolio dollar duration and DV01 are direct position-level sums. Duration contribution is `w_i×D_Mod,i`; DV01 contribution is `q_i×DV01_i`; convexity contribution is `w_i×Cvx_i`. Each contribution family reconciles to its portfolio total.

The displayed portfolio YTM is `Σw_i×YTM_i`, explicitly labeled a market-value-weighted descriptive average. It is not the IRR of the aggregate portfolio cash-flow stream and is not presented as a single portfolio yield.

### Scenarios, selection, and construction

Parallel-rate scenarios reprice every holding at its own YTM plus one common basis-point shock. Holding impacts sum to portfolio impact; contribution is holding full-repricing impact divided by starting portfolio value. A parallel shift does not measure curve-shape, key-rate, spread, liquidity, optionality, credit, tax, or liability risk.

Selection filters are inclusive and act only on explicit numeric terms or user-supplied classifications. Ranking uses one displayed rule: highest YTM, lowest modified duration, YTM per unit of modified duration, lowest instrument DV01, highest convexity, absolute maturity-target gap, or absolute duration-target gap. There is no hidden composite score.

Bond construction is a long-only linear program that maximizes the displayed weighted YTM subject to chosen position limits, target duration or duration band, maturity-bucket targets, issuer/credit-quality/sector caps, yield floor, and duration ceiling. Classifications are never inferred. Minimum positions apply to every included candidate and therefore do not implement binary security selection.

### Fixed-income limitations

The implementation excludes floating-rate notes, irregular stubs, amortizing principal, inflation linkage, embedded-option valuation, effective duration, option-adjusted spread, credit/default/recovery modeling, key-rate duration, nonparallel curve construction, liability immunization, liability-driven investing, tax optimization, execution costs, and yield-pickup swap analysis. Full immunization remains unsupported because the reviewed source does not provide a complete liability schedule and production-ready matching method.

### Deterministic two-bond reconciliation

At settlement 2026-01-01 with semiannual compounding, Bond A (`F=1000`, coupon 4%, maturity 2031-01-01, YTM 5%) produces clean/dirty price `956.239680`, current yield `4.183052%`, Macaulay duration `4.569508`, modified duration `4.458056`, DV01 `0.426297`, and convexity `23.194410`. Bond B (`F=1000`, coupon 6%, maturity 2036-01-01, YTM 5.5%) produces price `1038.068130`, current yield `5.779967%`, Macaulay duration `7.712185`, modified duration `7.505776`, DV01 `0.779151`, and convexity `69.711538`.

For the UI defaults of 10 units of Bond A and 5 units of Bond B, dirty market value is `14,752.737455`, portfolio modified duration `5.530312`, portfolio DV01 `8.158724`, and portfolio convexity `39.560169`. A +100 bp shock fully reprices the portfolio to `13,965.237889`, a `−5.337999%` impact. Duration-plus-convexity estimates `13,966.046127`, an aggregate price error of `0.808237`. Duration, DV01, convexity and scenario contribution totals reconcile to the displayed portfolio totals within floating-point tolerance.

## Data and returns

### Benchmark ticker resolution

Benchmark input defaults to `SPX`, is normalized to uppercase, and is checked against the explicit `BENCHMARK_TICKER_ALIASES` mapping in `portfolio_dashboard/config.py` before the Yahoo Finance request. The provider-native `^GSPC` symbol is used only for download and internal retrieval state; `SPX` remains the label in charts, tables, reports and exports. Because this is the documented default, its routine mapping notice is suppressed. Other mapped aliases receive an explicit notice. Direct Yahoo symbols and unknown tickers pass through unchanged. Alias resolution is intentionally limited to the benchmark input: PortfolioLens does not infer or rewrite portfolio holdings, including ambiguous equity symbols such as `DOW`.

Supported mappings are `SPX`, `S&P500`, and `SP500` → `^GSPC`; `DJIA` and `DOW` → `^DJI`; `NASDAQ` → `^IXIC`; `VIX` → `^VIX`; and `RUT` → `^RUT`. This changes symbol interoperability only and does not alter returns, alignment, benchmark regression, or any financial formula.

The data source is yfinance adjusted close, falling back to its close field only when adjusted close is absent from the response. The portfolio and benchmark are fetched separately. Each requested holding must be available; analysis never silently drops a symbol. Holding prices are inner-aligned on complete common trading dates, and no prices are filled or invented. Benchmark comparisons use a further inner alignment.

Daily return is the simple return `r_t = P_t / P_(t-1) - 1`. Portfolio return assumes constant target weights: `r_p,t = Σ w_i r_i,t`. This describes a daily rebalanced analytical portfolio and does not claim to reproduce an un-rebalanced brokerage account.

### Portfolio allocation input

The public setup uses the retail label **Portfolio allocation (%)**, while this document retains the formal term portfolio weights. Users enter one percentage per ticker; the count must match the parsed investment list and the total must equal 100%. Negative, nonnumeric, and all-zero allocations are blocked before analysis. The live summary and preview are presentation aids and do not alter calculations.

The explicit **Normalize to 100%** action is available only when every investment has a strictly positive numeric allocation. It applies `w_i = a_i / Σa_i`, preserving relative proportions, and corrects the final stored value to make `Σw_i = 1` within floating-point tolerance. It never fills missing entries or silently changes input. Equal allocation uses exact internal weights `w_i = 1/n`; display percentages round to two decimals and assign the rounding remainder to the final investment (for three investments, 33.33%, 33.33%, 33.34%).

## Performance

### Normalized performance by holding

Analytics → Performance includes a security-comparison chart titled **Normalized performance by holding**. For each selected holding, the plotted value is:

`normalized_price_i,t = adjusted_price_i,t / adjusted_price_i,0`

The calculation uses the same adjusted-price data and complete common-date alignment as the main analysis. Alignment occurs before normalization; missing prices are not forward-filled. Each valid series therefore starts at exactly `1.00` on the first common observation date. Portfolio weights are deliberately not used: this chart compares hypothetical growth paths for individual holdings rather than portfolio performance. A normalized price is not itself a return; cumulative change shown in hover is `(normalized value − 1) × 100`.

An optional benchmark is normalized on the same displayed common range and styled separately. Non-numeric, non-finite, non-positive, or otherwise unusable series are excluded with an explanation. Adjusted prices generally incorporate provider treatment of distributions, but provider revisions, corporate actions, and incomplete histories can change the result. Linear and logarithmic y-axis views change presentation only, not calculations.

- Total return: `Π(1+r_t)-1`
- Historical arithmetic annualized return: `252 × mean(r_t)`; this is the historical expected-return estimate used by Sharpe, Sortino, and maximum-Sharpe optimization
- CAGR: `(Π(1+r_t))^(252/n)-1`
- Annualized variance: sample variance of daily returns times `252`
- Annualized volatility: sample standard deviation of daily returns times `sqrt(252)`

### Portfolio Management Workbook 1 — Risk & Return of Portfolio Investments

The explicit holding-period-return helper follows the workbook relationship
`HPR = (ending value - beginning value + cash income) / beginning value`. The
live market pipeline uses simple adjusted-price returns, `P_t/P_(t-1)-1`;
because adjusted prices embed distributions, separately adding those same
distributions would double count income. Log returns are not used.

Periodic arithmetic mean is `sum(r_t)/n`. Periodic geometric mean is
`[product(1+r_t)]^(1/n)-1`; CAGR is the same compound path annualized as
`[product(1+r_t)]^(252/n)-1`. The app labels arithmetic annualized return as a
historical expected-return estimate and CAGR as realized compound growth.

Workbook probability tables and short finite exercises use population
variance, `sum[p_s(r_s-E[r])^2]`, or Excel `VAR.P`/`STDEV.P`. PortfolioLens does
not silently carry that classroom convention into observed market estimation:
historical asset variance, covariance, and correlation use sample estimators
(`ddof=1`) because the observations estimate an unknown return distribution.
Annualized covariance is daily sample covariance times 252; annualized
portfolio variance is `w'Σw` and volatility is its square root. This convention
is explicitly labeled in the UI and exports.

Coefficient of variation is the unitless relationship `CV=σ/E[r]`, computed
with annualized volatility and annualized arithmetic expected return so its
numerator and denominator share a horizon. It is undefined at zero expected
return; negative expected returns produce mathematically valid negative values
whose rankings require care.

The displayed diversification reduction is
`sum(w_i σ_i) - sqrt(w'Σw)` for long-only weights. The percentage divides that
gap by weighted standalone volatility. It describes the effect of observed
cross-asset covariance; it is neither a forecast nor a systematic-risk measure.
Return and Euler volatility contributions remain separate reconciled analyses.
- Performance Sharpe: `(historical arithmetic annualized return - annual risk-free rate) / annualized volatility`
- Optimizer Sharpe: the same arithmetic annualized excess-return formula evaluated for candidate weights; it is mathematically identical to performance Sharpe for the same return series and weights
- Sortino: `(historical arithmetic annualized return - annual risk-free rate) / annualized target downside deviation`; the annual risk-free rate is converted to an equivalent daily minimum acceptable return, and every observation contributes either its squared shortfall or zero
- Drawdown: wealth divided by its running peak minus one, with the initial portfolio value included as the first peak
- Calmar: CAGR divided by the absolute maximum drawdown

Arithmetic return and CAGR answer different questions. Arithmetic annualized return is a historical mean estimate suitable for one-period mean-variance comparisons; CAGR is the realized compound growth rate over the selected path. Neither is presented as a forecast. The annual risk-free input is subtracted from annualized ratio numerators. For Sortino's downside target only, it is converted to an equivalent daily rate. A 252-trading-day convention is used throughout.

### Performance evaluation and Fama decomposition

The Performance Evaluation workspace consolidates existing return, risk-adjusted and benchmark-relative measures without changing their formulas. Its Fama diagnostics use the same aligned annual arithmetic inputs:

- overall performance: `R_p - R_f`
- CAPM required return: `R_f + beta_p(R_m - R_f)`
- CML required return at portfolio total risk: `R_f + (R_m - R_f)(sigma_p / sigma_m)`
- selectivity: `R_p - CAPM required return`
- diversification effect: `CML required return - CAPM required return`
- net selectivity: `selectivity - diversification effect = R_p - CML required return`

`R_p`, `R_m`, and `R_f` are annual decimal returns; `sigma_p` and `sigma_m` are annual sample volatilities; beta is unitless. The benchmark is the selected market proxy. These are historical diagnostics, not proof that manager skill exists or persists.

The reviewed source's allocation effect is `sum((w_p-w_b)(r_b-R_b))`. Its selection effect is `sum(w_p(r_p-r_b))`; because it uses portfolio rather than benchmark weights, this term includes the conventional interaction effect. PortfolioLens preserves that formula in `evaluation.allocation_selection_attribution` and names it **Selection Effect Including Interaction**. It is not displayed from market-price data because category-level portfolio and benchmark weights and returns are not available and are not inferred.

Modified Dietz is available as `(V_end - V_begin - sum(CF_i)) / (V_begin + sum((1-t_i)CF_i))`, where `t_i` is the elapsed fraction of the period when an external contribution occurs. Time-weighted return compounds subperiod returns as `product(1+r_t)-1`. They remain reusable calculation primitives rather than default price-history outputs because the application does not collect external account cash flows.

The 63-observation rolling chart is a professional enhancement. Rolling Sharpe uses annualized arithmetic return and sample volatility; rolling tracking error is the annualized sample standard deviation of active returns; rolling Information Ratio divides rolling annualized arithmetic active return by rolling tracking error. Calmar, drawdown, tracking error, Information Ratio and rolling metrics are existing PortfolioLens measures and are not attributed to this source workbook.

The source Sortino example defines semideviation around each manager's arithmetic mean using only observations below that mean and a population denominator equal to the number of downside observations. PortfolioLens intentionally retains its established target-downside convention: the annual risk-free rate is converted to a daily target, all observations enter the denominator, and non-shortfall observations contribute zero. The UI and tests document this methodological difference.

## Risk and benchmark comparison

Historical 95% VaR is reported as a nonnegative loss magnitude at the empirical fifth percentile. Historical 95% CVaR is the nonnegative magnitude of mean returns at or below that percentile. If the observed lower tail contains gains rather than losses, the reported loss measure is zero. These are backward-looking one-day statistics and can understate unseen tail events.

Active daily return is `r_p,t-r_m,t`. Annualized Active Return is `252 × mean(r_p,t-r_m,t)` and Tracking Error is `std(r_p,t-r_m,t, ddof=1) × sqrt(252)`. Information Ratio is Annualized Active Return divided by Tracking Error. The separately labeled cumulative Excess Return is portfolio total return minus benchmark total return over the selected path; it is not the Information Ratio numerator. Relative drawdown is computed from portfolio wealth divided by benchmark wealth.

The single-index model uses the same aligned daily observations and regresses portfolio excess return on benchmark excess return:

`r_p,t - r_f,t = α_t + β(r_m,t - r_f,t) + ε_t`

The annual risk-free input is divided by `252` for this arithmetic daily model. OLS beta is `Cov(r_p-r_f, r_m-r_f) / Var(r_m-r_f)`, daily intercept is the mean portfolio excess return minus beta times mean benchmark excess return, and regression alpha is `252 × α_t`. R² is `1-SSE/SST`. Residual volatility is the residual standard error `std(ε, ddof=2) × sqrt(252)` because an intercept and slope are estimated.

Systematic variance is `β² Var(r_m-r_f) × 252`; idiosyncratic variance is `Var(ε, ddof=1) × 252`. Their displayed risk shares divide each component by their sum and therefore reconcile to 100%. Residual volatility and idiosyncratic variance intentionally use different degrees of freedom: the former estimates regression error volatility, while the latter is the sample variance component needed for exact historical variance decomposition.

CAPM required return is `r_f + β(E[r_m]-r_f)`, using arithmetic annualized benchmark return. Jensen's alpha is `E[r_p] - CAPM required return`; under these shared arithmetic conventions it reconciles to annualized regression alpha. Treynor ratio is `(E[r_p]-r_f)/β` and is unavailable when beta is effectively zero. These historical estimates are highly sample- and benchmark-dependent; alpha is not a forecast or proof of manager skill, R² is not a measure of performance quality, and low idiosyncratic risk is not inherently preferable.

## Attribution and concentration

Return contribution allocates each day's weighted asset return through the prior day's portfolio wealth. Summing all assets and dates therefore reconciles exactly to portfolio total return under the constant-weight return model.

For annualized covariance matrix `Σ`, weights `w`, and portfolio volatility `σ_p = sqrt(w′Σw)`, asset `i` volatility contribution is `w_i(Σw)_i / σ_p`. Euler homogeneity makes contributions sum to `σ_p`, including negative contributions where covariance makes an asset a hedge.

Weight concentration is shown directly and through effective number of holdings `1 / Σw_i²`.

## Construction and rebalancing

Manual UI weights may be entered as percentage points (for example `50,35,15`) or decimal weights (`0.50,0.35,0.15`) and are converted to decimal weights exactly once. Equal-weight mode ignores the disabled manual field and constructs `1/N` directly from the validated ticker count.

Equal weights allocate `1/N`. Inverse-volatility weights are proportional to `1/σ_i`. For arithmetic annualized asset-return vector `μ`, annualized sample covariance matrix `Σ`, and weights `w`, portfolio expected return is `w′μ` and portfolio variance is `w′Σw`; volatility is `sqrt(w′Σw)`. Minimum variance minimizes `w′Σw`. Maximum Sharpe maximizes `(w′μ-r_f)/sqrt(w′Σw)`, using the same Sharpe formula as the displayed scorecard. Both optimized methods constrain every weight to `[0,1]` and the sum to one. A failed solver result is never displayed as valid. Historical inputs are estimates, not forecasts, and “maximum Sharpe” names the mathematical objective rather than a recommendation.

The optimizer first aligns complete daily simple returns. Its annual arithmetic expected-return vector and annual sample covariance matrix are

`μ = 252 × mean(r_daily)` and `Σ = 252 × cov(r_daily, ddof=1)`.

For weights `w`, expected return is `μ_p=w′μ`, variance is `σ_p²=w′Σw`, volatility is `σ_p=sqrt(w′Σw)`, and Sharpe is `(μ_p−r_f)/σ_p`. The annual risk-free rate is therefore in the same units as `μ`; volatility is annualized exactly once through `Σ`. CAGR is a realized compound-growth statistic and is never an optimizer input. The separately downloaded benchmark is inner-aligned for benchmark analysis but is never included in the portfolio asset matrix.

The long-only efficient frontier is only the upper mean-variance branch from the global minimum-variance portfolio to the highest-return individual asset in the sample. PortfolioLens minimizes `w′Σw` at monotonically increasing feasible arithmetic target returns subject to `w′μ=μ_target`, `Σw_i=1`, and `0≤w_i≤1`. It explicitly inserts the constrained tangency target, removes duplicate or numerically dominated points, skips failed target solves, and never connects a failed result. The plotted current portfolio is an independent marker and may lie below the frontier. Fifty base targets provide visual resolution without interpolating or altering calculated values.

The constrained tangency portfolio maximizes `(w′μ−r_f)/sqrt(w′Σw)` under the same bounds and sum constraint. The non-leveraged Capital Allocation Line is

`E[r_C]=r_f+[(E[r_T]−r_f)/σ_T]σ_C = r_f+y(E[r_T]−r_f)`, with `σ_C=yσ_T` and `0≤y≤1`.

The CAL is calculated directly from the same tangency return, volatility, and annual risk-free rate used by the optimizer; it does not trust a separately cached Sharpe value. It begins at `(0,r_f)`, passes through `(σ_T,E[r_T])`, and ends at the tangency portfolio because borrowing/leverage is disabled. Complete-portfolio points use the identical equations and therefore lie on the CAL within floating-point tolerance.

SLSQP uses a 1,000-iteration limit and `ftol=1e-12`; linear feasibility is checked first with HiGHS. Post-solve weight-sum, long-only and target-return residual tolerances are `1e-7`. Covariance matrices are not regularized: their condition number is disclosed, exact or near singularity is handled by the constrained numerical solver where possible, and genuine non-convergence is surfaced. This avoids hiding estimation or identification problems behind an undocumented stabilization rule.

### Portfolio Management Workbook 3 — Capital & Asset Classes Allocation

Workbook 3 defines quadratic mean-variance utility as `U=E[r_C]−0.5Aσ_C²` and the unconstrained optimal risky allocation as `y*=(E[r_T]−r_f)/(Aσ_T²)`, where `A>0`, `r_T` and `σ_T` describe the optimal risky portfolio, and the risk-free asset has zero volatility and covariance. PortfolioLens applies this formula to its long-only tangency portfolio using annual decimal arithmetic estimates. It reports the unconstrained `y*`, then applies the existing product constraint `0≤y≤1`. A binding boundary is disclosed; borrowing, leverage, and short selling are not silently introduced.

The workbook's inputs are classroom assumptions, while PortfolioLens estimates `μ` and `Σ` from historical daily simple returns and annualizes them by 252. The resulting allocation is therefore a historical sensitivity scenario, not a forecast, suitability assessment, or recommendation. Users may instead select `y` directly. The embedded third-party risk questionnaire and the workbook's linear score transformation `A=30(1−score/100)` are not used: PortfolioLens asks directly for `A` and does not claim to assess an investor.

Workbook cell `Optimal Complete Pf!C32` double-weights components that are already weighted in `D32` and `F32`. PortfolioLens uses the financially consistent identity `E[r_C]=r_f+y(E[r_T]−r_f)` and documents, rather than reproduces, that source inconsistency.

### Security-level single-index analysis

For each security, PortfolioLens aligns daily simple returns with the benchmark and fits `R_i−R_f/252 = α_i + β_i(R_M−R_f/252) + ε_i`. The slope is `Cov(i,M)/Var(M)` and the intercept is mean security excess return less beta times mean benchmark excess return. Annual alpha is `252α_i`. Systematic variance is `β_i²Var(R_M−R_f)×252`; idiosyncratic variance is `Var(ε_i)×252`; their sum is model total variance.

Residual volatility uses the sample residual variance (`n−1`). Separately labeled regression standard error uses `SSE/(n−2)`. `R²=1−SSE/SST`; coefficient standard errors, t statistics, two-sided p values, and 95% intervals use `n−2` residual degrees of freedom. The characteristic line overlays fitted excess returns on actual observations; the residual chart retains dates. Alpha and alpha-to-residual-variance are historical diagnostics, not forecasts or security recommendations. Results depend on benchmark choice, alignment, frequency, outliers, parameter stability, and cross-security residual correlation.

### Portfolio Management Workbook 2 — Mean-Variance Efficient Frontier & Capital Market Line

Workbook 2 separates two optimization conventions. Its global-frontier worksheet minimizes portfolio standard deviation for a specified target mean using weights bounded from 0 to 1, weights summing to one, and an exact target-return equality. Its optimal-risky-portfolio worksheet instead maximizes an excess-return Sharpe ratio with only a sum-to-one constraint; saved negative weights confirm that this classroom tangency model permits short sales. PortfolioLens intentionally uses the first worksheet's long-only convention for GMV, target-return, frontier, and maximum-Sharpe construction. Therefore its tangency estimate will not reproduce the workbook's unconstrained country-index weights.

The workbook expresses its CML in excess-return space as `risk premium = σ_c × Sharpe_T`, with the risk-free intercept implicit. PortfolioLens displays the equivalent total-return CAL, `E[r_c]=r_f+y(E[r_T]-r_f)`, and `σ_c=yσ_T`. A complete portfolio allocates `y` to the long-only tangency portfolio and `1-y` to the risk-free asset. The UI restricts `0≤y≤1`: lending is supported, but the workbook's illustrated borrowing region (`y>1`) remains educational-only because PortfolioLens does not enable leverage.

Workbook expected returns, standard deviations, correlations, covariances, and excess returns are entered assumptions with no recoverable source period or annualization process. PortfolioLens instead estimates arithmetic annual returns and annualized sample covariance from aligned daily adjusted-price returns. Realized CAGR remains separate. The risk-free input is annual and is subtracted from arithmetic expected return for Sharpe; optimized results are historical estimates, not forecasts or recommendations.

The workbook mentions expected utility, diminishing marginal utility, and risk aversion but provides no risk-aversion coefficient, quadratic utility formula, indifference-curve calculation, or Solver model for optimal complete-portfolio selection. PortfolioLens therefore does not manufacture a utility optimizer from this source.

Custom constrained construction retains `Σw_i=1` and long-only weights while allowing explicit user-entered asset minimums and maximums, exclusions represented by a zero maximum, and group caps `Σ(i in group)w_i ≤ cap_group`. Group membership is never inferred: users must enter labels and matching caps. A linear feasibility program first verifies the complete constraint set; only a feasible point is passed to the nonlinear minimum-variance, maximum-Sharpe, or target-return optimizer. The validation table reports every minimum, maximum, group cap, sum result, pass/fail outcome, breach magnitude, and affected asset. Maximum-volatility constraints are not implemented because approved course traceability does not establish them as a required stable feature.

Optimizer expected return is the arithmetic historical estimate `w′μ`, optimizer volatility is `sqrt(w′Σw)`, and optimizer Sharpe is `(w′μ-r_f)/sqrt(w′Σw)`. Realized CAGR remains the compound growth of the observed return path and is not used as an optimizer input. Frontier points and optimized weights are shown with restrained display precision, and all solver failures or infeasible targets are surfaced rather than silently replaced.

Rebalancing assumes the stated portfolio value, no cash flow, fractional trading, and no taxes. Estimated trade is target dollars minus current dollars. Buys and sells reconcile before costs and rounding. By default, only an exactly unchanged weight is labeled Hold; callers may opt into a display threshold, which changes the action label but not the disclosed target-allocation gap.

The rebalancing simulator is path-dependent and distinct from the main constant-weight analytical portfolio. It initializes dollar holdings at target weights, applies each asset’s daily return to its own holding, calculates pre-trade drift, and trades only when the selected policy triggers. Monthly, quarterly, and annual policies trade after the last available trading observation of a completed calendar period; the final sample date is not treated as a scheduled rebalance because no subsequent holding period remains. Threshold policy trades when any absolute asset-weight drift reaches the user’s band. Buy and hold never trades.

At a trigger, pre-cost trade for asset `i` is `target weight_i × gross portfolio value - holding_i`. These trades sum to zero before costs. Gross traded notional is `Σ|trade_i|`; displayed one-way turnover is `0.5 × gross traded notional / pre-trade portfolio value`; estimated cost is `cost rate × gross traded notional`. Cost is deducted once, only on a triggered trade, and remaining value is allocated to target weights. Daily net return links prior post-trade value to current post-trade value, so the compounded return path reconciles to portfolio value. The simulator assumes fractional trading and excludes taxes, bid/ask spreads beyond the configured proportional rate, liquidity limits, cash flows, and market impact.

## Research workspace and Portfolio Health Score

Portfolio comparison evaluates every available allocation method on the same aligned asset-return history, annual risk-free rate, constant-weight portfolio-return model, and performance formulas. The displayed weight distance from current is `0.5 × Σ|w_scenario,i - w_current,i|`. It describes allocation difference only; it is not realized turnover, a trade-cost estimate, or a rebalance simulation.

The Portfolio Health Score is an application-specific historical diagnostic, not a formula copied from the Portfolio Management course. It is a bounded weighted average of five disclosed components:

| Component | Weight | Normalized rule |
|---|---:|---|
| Diversification | 25% | `effective holdings / number of holdings` |
| Risk-adjusted return | 25% | Sharpe linearly mapped from `-1 → 0%` to `2 → 100%` |
| Drawdown resilience | 20% | `1 - abs(maximum drawdown) / 50%` |
| Tail resilience | 15% | `1 - daily historical 95% CVaR / 10%` |
| Benchmark efficiency | 15% | information ratio linearly mapped from `-1 → 0%` to `1 → 100%` |

Every normalized result is clipped to `[0,1]`. If a metric is unavailable, its component is excluded and the remaining weighted points are rescaled to 100; metric coverage is always displayed. Formally, `score = Σ(weight_i × normalized_i) / Σ(available weight_i)`. The thresholds are transparent presentation choices, not universal investment standards. The score does not measure suitability, forecast return, diversification across unobserved risk factors, or portfolio optimality.

What-if analysis accepts hypothetical nonnegative weights that must sum to 100% and one explicit finite shock per holding. Historical comparison uses the same constant-weight formulas as the main analysis. Instantaneous shock impact is `Σw_i s_i`, and the scenario does not overwrite the analyzed portfolio, simulate a rebalance path, or include taxes, market impact, and trading costs.

Deterministic insights are selected by fixed rules using computed Sharpe, cumulative excess return, maximum drawdown, largest weight, effective holdings, beta, idiosyncratic risk share, Euler volatility contribution, and CVaR. The interface displays the supporting metric, value, and rule beside every observation. No LLM or generative model creates, ranks, or rewrites insights, and the statements do not instruct users to buy, sell, or change an allocation.

## Momentum strategy

The strategy operates on the first requested holding so the traded instrument is explicit. It is long when the short simple moving average is above the long simple moving average and otherwise in cash. A signal observed at close on day `t` becomes the position for day `t+1`; the signal is shifted one full period to avoid look-ahead bias. Before both averages exist, the strategy remains in cash. Performance comparison begins only after the long-window warm-up, so strategy and buy-and-hold use the same evaluation period. Proportional transaction cost is deducted on each absolute position change. The MVP does not search or optimize parameters.

With the default 200-day long window, momentum requires at least 201 aligned price observations: 200 observations for warm-up and one subsequent observation for evaluation. This is a strategy-specific requirement, not a global portfolio-analysis minimum. A shorter period can still support core portfolio, benchmark, risk, construction, attribution, rebalancing, stress, and report outputs when each feature's own data requirement is met. In that case momentum is explicitly marked unavailable, its real aligned observation count is shown, and no empty series, zero return, or placeholder metric is substituted. Alignment can reduce the count because missing holding dates, a later-listed ticker, or shorter benchmark history restricts all analysis to complete common dates.

Momentum validation and calculation failures are isolated after core analysis completes. Insufficient history produces an actionable strategy warning. Other calculation failures are logged and disclosed as strategy errors while the safely computed non-momentum results remain available.

Positive active-day rate is the fraction of in-market daily returns above zero. Daily-return profit factor is the sum of positive in-market daily returns divided by the absolute sum of negative in-market daily returns. Turnover is the sum of absolute position changes, and position changes count entries and exits separately. These definitions are intentionally simple and are not trade-level round-trip analytics.

## Stress tests

Custom shocks are explicit per-asset instantaneous percentage shocks; the application does not infer asset classes or silently replace a missing shock with zero. Portfolio impact is `Σw_i s_i`. Historical windows and exact configured dates live in `portfolio_dashboard/config.py`. A window is shown only when the selected common history covers both endpoints, and the displayed result includes the actual first and last trading dates used. Historical portfolio returns use the same daily constant-weight method as the main analysis.

The downloadable report uses the actual common-price analysis dates, the currently edited custom shocks, and the rebalancing method currently selected in the application. Percentage, currency, count, and unitless ratio fields are formatted according to their metric definitions.

## Asset pricing and Security Market Line

For each security, PortfolioLens uses the beta from its aligned excess-return regression and compares the security's annualized arithmetic sample return with the CAPM required return:

`E[R_i]CAPM = R_f + β_i(E[R_M] - R_f)`

`Jensen's alpha = arithmetic sample return_i - E[R_i]CAPM`

The benchmark arithmetic return is calculated from the same aligned observations used for that security's regression. The risk-free input, security return, benchmark return, and required return are annual decimals; beta is unitless. The Security Market Line is the straight line through `(β=0, R_f)` and `(β=1, E[R_M])`. A point above or below that historical line is descriptive sample evidence, not proof of persistent mispricing and not a recommendation.

The source-supported APT and four-factor calculations are linear assumption models. For supplied exposures `b_k`, supplied factor premia `λ_k`, and a supplied base return `λ_0`, PortfolioLens can reconcile `E[R_i]=λ_0+Σ b_ik λ_k` and each contribution `b_ik λ_k`. The source identifies market excess, size (SMB), value (HML), and momentum factors, but supplies no recoverable factor-return acquisition or exposure-estimation workflow. The public application therefore labels this as a framework and does not fabricate live multifactor estimates from Yahoo Finance data.

## Portfolio-strategy and benchmark comparison

Portfolio Strategies compares buy and hold, monthly, quarterly, annual, and threshold rebalancing on one holdings-level return history. Buy and hold allows weights to drift. Periodic policies trade only after the final available observation of a completed calendar period; the final sample date is not silently treated as a rebalance. Threshold policy trades only when maximum absolute drift reaches the selected band. Trade notional, one-way turnover and proportional costs use the same formulas documented in the rebalancing section.

For each policy, daily active return is `r_policy−r_benchmark`. Annualized active return is `252×mean(active return)`. Tracking error is `sqrt(252)×sample SD(active return)`, and information ratio is annualized active return divided by tracking error. Mean absolute periodic difference is `mean(|r_policy−r_benchmark|)` and deliberately remains in daily units. The source uses population standard deviation for a finite ten-period manager table; PortfolioLens retains its existing sample convention because live history is treated as an estimate from a broader return process. The difference is explicit and tested.

The separate moving-average strategy remains a PortfolioLens product feature, not a source-derived rule. Its signal is shifted one trading day before returns are applied, and costs occur only when the position changes. Neither historical rebalancing-policy results nor momentum outcomes are recommendations or forecasts.

## General limitations and disclaimer

## ETF research and holdings look-through

Universe metrics use aligned simple returns: arithmetic annualized return is `mean(r) × 252`, sample volatility is `std(r, ddof=1) × sqrt(252)`, Sharpe is `(arithmetic return − annual risk-free rate) / volatility`, cumulative return compounds the observed path, and maximum drawdown includes initial wealth. Filters apply explicit observation, Sharpe and volatility thresholds; they are not ratings.

Security screening reuses the exact excess-return single-index regression documented above and requires a positive annualized intercept, a user-visible p-value threshold and a minimum observation count. It does not use current analyst targets or imply alpha persistence. Holdings analysis accepts explicit ETF/security/weight disclosures, consolidates duplicate rows, and permits totals below 100% to represent omitted cash or minor holdings. Portfolio exposure is `ETF portfolio weight × disclosed holding weight`; weighted overlap is `sum(min(weight_i, weight_j))` across the union of constituents. No security, issuer, sector or stale-date inference is made.

## Shared formula registry and report consistency

UI and report layers consume pure functions from `performance.py`, `risk.py`, `asset_pricing.py`, `construction.py`, `rebalancing.py`, `strategy.py`, `evaluation.py`, and `etf_research.py`; they do not maintain independent financial formulas. The consolidated convention registry and source-to-feature status are in [PORTFOLIO_MANAGEMENT_COVERAGE.md](PORTFOLIO_MANAGEMENT_COVERAGE.md). Asset Allocation compares existing model portfolios and implementation trades without inferring asset classes, strategic policy or suitability.

Historical data may contain provider errors and do not predict future performance. The system excludes taxes, liquidity and position-size limits, financing, corporate-action edge cases, market impact, and slippage beyond the configured proportional cost. It has no live execution, authentication, persistence, or intraday data. For research and educational use only; not personalized financial advice.
