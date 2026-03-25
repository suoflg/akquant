from typing import Any

import pandas as pd
from akquant import (
    BacktestConfig,
    Bar,
    InstrumentConfig,
    Strategy,
    StrategyConfig,
    run_backtest,
)
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


def test_risk_config_accepts_check_cash_keyword() -> None:
    """RiskConfig supports check_cash as constructor argument."""
    rc = RiskConfig(check_cash=False)
    assert rc.check_cash is False


def test_check_cash_false_can_disable_margin_rejection_for_buy() -> None:
    """check_cash from Python RiskConfig should propagate to Rust engine config."""
    from akquant.akquant import Engine
    from akquant.risk import apply_risk_config

    engine = Engine()
    assert engine.risk_manager.config.check_cash is True

    apply_risk_config(engine, RiskConfig(check_cash=False))
    assert engine.risk_manager.config.check_cash is False


def test_short_option_margin_is_checked_and_account_margin_updates() -> None:
    """Short option opening orders should trigger margin checks and account margin."""

    class ShortPutStrategy(Strategy):
        account_snapshots: list[dict[str, float]] = []

        def __init__(self) -> None:
            self.order_count = 0

        def on_bar(self, bar: Bar) -> None:
            if bar.symbol != "PUT_OPT":
                return
            if self.order_count == 0:
                self.sell("PUT_OPT", 1)
                self.order_count += 1
            elif self.order_count == 1:
                self.sell("PUT_OPT", 100000)
                self.order_count += 1

        def on_trade(self, trade: Any) -> None:
            self.__class__.account_snapshots.append(self.get_account())

    dates = pd.date_range("2023-12-01 09:30", "2023-12-01 09:32", freq="1min")
    data_opt = pd.DataFrame(
        {
            "timestamp": dates,
            "open": 1.5,
            "high": 1.5,
            "low": 1.5,
            "close": 1.5,
            "volume": 100,
            "symbol": "PUT_OPT",
        }
    )
    data_ul = pd.DataFrame(
        {
            "timestamp": dates,
            "open": 105.0,
            "high": 105.0,
            "low": 105.0,
            "close": 105.0,
            "volume": 1000,
            "symbol": "UL",
        }
    )
    ShortPutStrategy.account_snapshots = []
    result = run_backtest(
        data={"PUT_OPT": data_opt, "UL": data_ul},
        strategy=ShortPutStrategy,
        show_progress=False,
        execution_mode="current_close",
        config=BacktestConfig(
            strategy_config=StrategyConfig(
                initial_cash=50000.0,
                commission_rate=0.0,
                risk=RiskConfig(check_cash=True, safety_margin=0.0001),
            ),
            instruments_config=[
                InstrumentConfig(
                    symbol="PUT_OPT",
                    asset_type="OPTION",
                    multiplier=100,
                    margin_ratio=0.35,
                    option_type="PUT",
                    strike_price=90,
                    expiry_date=20231201,
                    underlying_symbol="UL",
                ),
                InstrumentConfig(symbol="UL", asset_type="STOCK"),
            ],
        ),
    )

    reasons = _reject_reasons(result)
    assert any("Insufficient margin" in r for r in reasons), reasons
    assert ShortPutStrategy.account_snapshots
    assert any(s["margin"] > 0.0 for s in ShortPutStrategy.account_snapshots)
