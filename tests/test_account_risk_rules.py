from typing import Any

import pandas as pd
from akquant import Bar, Strategy, run_backtest
from akquant.config import RiskConfig


class AlwaysBuyStrategy(Strategy):
    """Submit a buy order on every bar."""

    def on_bar(self, bar: Bar) -> None:
        """Submit fixed-size market buy."""
        self.buy(bar.symbol, 30)


def _build_bars(
    timestamps: list[pd.Timestamp], prices: list[float], symbol: str = "RISK"
) -> list[Bar]:
    bars: list[Bar] = []
    for ts, price in zip(timestamps, prices):
        bars.append(
            Bar(
                timestamp=ts.value,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=10000.0,
                symbol=symbol,
            )
        )
    return bars


def _reject_reasons(result: Any) -> list[str]:
    orders_df = result.orders_df
    if orders_df.empty or "reject_reason" not in orders_df.columns:
        return []
    reasons = orders_df["reject_reason"].fillna("").astype(str).tolist()
    return [r for r in reasons if r.strip()]


def test_account_max_drawdown_rule_rejects_new_orders() -> None:
    """Reject new orders after drawdown breaches threshold."""
    bars = _build_bars(
        [
            pd.Timestamp("2023-01-01 10:00:00", tz="Asia/Shanghai"),
            pd.Timestamp("2023-01-01 11:00:00", tz="Asia/Shanghai"),
        ],
        [100.0, 50.0],
    )
    result = run_backtest(
        data=bars,
        strategy=AlwaysBuyStrategy,
        symbol="RISK",
        initial_cash=100000.0,
        show_progress=False,
        execution_mode="current_close",
        lot_size=1,
        risk_config=RiskConfig(max_account_drawdown=0.01),
    )
    reasons = _reject_reasons(result)
    assert any("Max drawdown" in r for r in reasons), reasons


def test_account_max_daily_loss_rule_rejects_new_orders_same_day() -> None:
    """Reject new orders after intraday daily-loss breach."""
    bars = _build_bars(
        [
            pd.Timestamp("2023-01-01 10:00:00", tz="Asia/Shanghai"),
            pd.Timestamp("2023-01-01 14:00:00", tz="Asia/Shanghai"),
        ],
        [100.0, 50.0],
    )
    result = run_backtest(
        data=bars,
        strategy=AlwaysBuyStrategy,
        symbol="RISK",
        initial_cash=100000.0,
        show_progress=False,
        execution_mode="current_close",
        lot_size=1,
        risk_config=RiskConfig(max_daily_loss=0.01),
    )
    reasons = _reject_reasons(result)
    assert any("Daily loss" in r for r in reasons), reasons


def test_account_stop_loss_threshold_rule_rejects_new_orders() -> None:
    """Reject new orders when equity falls below stop-loss threshold."""
    bars = _build_bars(
        [
            pd.Timestamp("2023-01-01 10:00:00", tz="Asia/Shanghai"),
            pd.Timestamp("2023-01-01 11:00:00", tz="Asia/Shanghai"),
        ],
        [100.0, 50.0],
    )
    result = run_backtest(
        data=bars,
        strategy=AlwaysBuyStrategy,
        symbol="RISK",
        initial_cash=100000.0,
        show_progress=False,
        execution_mode="current_close",
        lot_size=1,
        risk_config=RiskConfig(stop_loss_threshold=0.99),
    )
    reasons = _reject_reasons(result)
    assert any("stop-loss threshold" in r for r in reasons), reasons
