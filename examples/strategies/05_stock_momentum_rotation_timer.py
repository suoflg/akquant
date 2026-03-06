"""多股票轮动策略示例（on_timer 版本）."""

from typing import Any

import akquant as aq
import akshare as ak
import pandas as pd
from akquant import Bar, Strategy


class TimerMomentumRotationStrategy(Strategy):
    """使用 on_timer 执行横截面轮动."""

    def __init__(self, lookback_period: int = 20, *args: Any, **kwargs: Any) -> None:
        """初始化策略参数."""
        super().__init__(*args, **kwargs)
        self.lookback_period = lookback_period
        self.symbols = ["sh600519", "sz000858"]
        self.warmup_period = lookback_period + 1

    def on_start(self) -> None:
        """策略启动时注册每日调仓定时器."""
        self.add_daily_timer("14:55:00", "rebalance")

    def on_bar(self, bar: Bar) -> None:
        """Bar 回调."""
        _ = bar

    def on_timer(self, payload: str) -> None:
        """Timer 回调."""
        if payload != "rebalance":
            return

        scores: dict[str, float] = {}
        for symbol in self.symbols:
            closes = self.get_history(
                count=self.lookback_period, symbol=symbol, field="close"
            )
            if len(closes) < self.lookback_period:
                return
            start = float(closes[0])
            end = float(closes[-1])
            if start <= 0:
                continue
            scores[symbol] = (end - start) / start

        if not scores:
            return

        best_symbol = max(scores, key=lambda symbol: scores[symbol])
        best_score = scores[best_symbol]

        if best_score < 0:
            for symbol in self.symbols:
                if self.get_position(symbol) > 0:
                    self.close_position(symbol)
            return

        current_holding: str | None = None
        for symbol in self.symbols:
            if self.get_position(symbol) > 0:
                current_holding = symbol
                break

        if current_holding is None:
            self.order_target_percent(target_percent=0.95, symbol=best_symbol)
            return

        if current_holding != best_symbol:
            self.close_position(current_holding)
            self.order_target_percent(target_percent=0.95, symbol=best_symbol)


if __name__ == "__main__":
    symbols = ["sh600519", "sz000858"]
    data_map: dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        df = ak.stock_zh_a_daily(
            symbol=symbol, start_date="20220101", end_date="20231231", adjust="qfq"
        )
        if df.empty:
            continue
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["date"] = pd.to_datetime(df["date"])
        df["symbol"] = symbol
        df = df.sort_values("date").reset_index(drop=True)
        data_map[symbol] = df

    if not data_map:
        raise SystemExit(0)

    result = aq.run_backtest(
        data=data_map,
        strategy=TimerMomentumRotationStrategy,
        symbol="BENCHMARK",
        initial_cash=1_000_000.0,
        commission_rate=0.0003,
        stamp_tax_rate=0.001,
    )
    print(result)
