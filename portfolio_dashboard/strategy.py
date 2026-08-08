"""Explainable long/cash dual-moving-average momentum backtest."""

from __future__ import annotations

from dataclasses import dataclass
import logging

import numpy as np
import pandas as pd

from .performance import performance_metrics

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MomentumAnalysis:
    """Outcome of the optional module on the core pipeline's aligned history."""

    available: bool
    observations_available: int
    observations_required: int
    data: pd.DataFrame | None = None
    metrics: dict[str, float] | None = None
    reason: str | None = None
    detail: str | None = None


def optional_momentum_analysis(
    prices: pd.Series,
    short_window: int = 50,
    long_window: int = 200,
    transaction_cost: float = 0.001,
    risk_free_rate: float = 0.0,
) -> MomentumAnalysis:
    """Run momentum when ready and isolate strategy-only failures from core analysis."""
    observations = int(prices.dropna().shape[0])
    required = int(long_window) + 1
    if observations < required:
        return MomentumAnalysis(
            available=False,
            observations_available=observations,
            observations_required=required,
            reason="insufficient_history",
            detail=(
                f"Momentum analysis was skipped because the selected period contains {observations} price "
                f"observations. At least {required} observations are required. Choose an earlier start date "
                "to enable this strategy."
            ),
        )
    try:
        data, metrics = momentum_backtest(
            prices, short_window, long_window, transaction_cost, risk_free_rate
        )
    except Exception as exc:
        LOGGER.exception("Momentum analysis failed after core analysis completed")
        return MomentumAnalysis(
            available=False,
            observations_available=observations,
            observations_required=required,
            reason="calculation_error",
            detail=f"Momentum analysis could not run: {exc}",
        )
    return MomentumAnalysis(
        available=True,
        observations_available=observations,
        observations_required=required,
        data=data,
        metrics=metrics,
    )


def momentum_backtest(prices: pd.Series, short_window: int = 50, long_window: int = 200,
                      transaction_cost: float = 0.001, risk_free_rate: float = 0.0) -> tuple[pd.DataFrame, dict[str, float]]:
    """Backtest short-MA above long-MA, lagged one day, long or cash only.

    Transaction cost is charged as a fraction of capital on each absolute
    position change. The warm-up period remains in cash.
    """
    clean = prices.dropna().astype(float)
    if short_window < 2 or long_window <= short_window:
        raise ValueError("Require 2 <= short window < long window.")
    if not 0 <= transaction_cost < 1:
        raise ValueError("Transaction cost must be between 0 and 100%.")
    if len(clean) <= long_window:
        raise ValueError(
            f"Momentum analysis requires more than {long_window} price observations; received {len(clean)}."
        )
    frame = pd.DataFrame({"Price": clean})
    frame["Short MA"] = clean.rolling(short_window, min_periods=short_window).mean()
    frame["Long MA"] = clean.rolling(long_window, min_periods=long_window).mean()
    ready = frame[["Short MA", "Long MA"]].notna().all(axis=1)
    frame["Signal"] = np.where(ready, (frame["Short MA"] > frame["Long MA"]).astype(float), np.nan)
    frame["Position"] = frame["Signal"].shift(1).fillna(0.0)
    frame["Buy & Hold Return"] = clean.pct_change(fill_method=None).fillna(0.0)
    frame["Turnover"] = frame["Position"].diff().abs().fillna(frame["Position"].abs())
    frame["Transaction Cost"] = frame["Turnover"] * transaction_cost
    frame["Strategy Return"] = frame["Position"] * frame["Buy & Hold Return"] - frame["Transaction Cost"]
    evaluation = frame.iloc[long_window:]
    frame["Strategy Growth"] = (1 + evaluation["Strategy Return"]).cumprod()
    frame["Buy & Hold Growth"] = (1 + evaluation["Buy & Hold Return"]).cumprod()
    metrics = performance_metrics(evaluation["Strategy Return"], risk_free_rate)
    metrics["Buy & Hold Total Return"] = float((1 + evaluation["Buy & Hold Return"]).prod() - 1)
    changes = evaluation["Turnover"] > 0
    active = evaluation.loc[evaluation["Position"] > 0, "Strategy Return"]
    gains, losses = active[active > 0].sum(), -active[active < 0].sum()
    metrics.update({"Position Changes": int(changes.sum()), "Turnover": float(evaluation["Turnover"].sum()),
                    "Positive Active-Day Rate": float((active > 0).mean()) if not active.empty else float("nan"),
                    "Daily-Return Profit Factor": float(gains / losses) if losses > 0 else float("nan"),
                    "Time in Market": float(evaluation["Position"].mean()),
                    "Warm-up Observations": int(long_window)})
    return frame, metrics
