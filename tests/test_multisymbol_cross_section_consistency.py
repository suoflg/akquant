from collections import defaultdict
from typing import Any

import pandas as pd
from akquant import Bar, Strategy, run_backtest


def _build_symbol_df(
    symbol: str, timestamps: list[pd.Timestamp], closes: list[float]
) -> pd.DataFrame:
    rows = []
    for ts, close in zip(timestamps, closes):
        rows.append(
            {
                "date": ts,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 10000.0,
                "symbol": symbol,
            }
        )
    return pd.DataFrame(rows)


class BucketCrossSectionStrategy(Strategy):
    """Cross-section strategy that rebalances after timestamp completion."""

    def __init__(self, symbols: list[str], lookback: int = 2) -> None:
        """Initialize strategy state."""
        super().__init__()
        self.symbols = symbols
        self.lookback = lookback
        self.warmup_period = 0
        self.seen_by_ts: dict[int, set[str]] = defaultdict(set)
        self.complete_timestamps: list[int] = []
        self.selected_symbols: list[str] = []

    def on_bar(self, bar: Bar) -> None:
        """Collect symbols by timestamp and run cross-section logic once."""
        bucket = self.seen_by_ts[bar.timestamp]
        bucket.add(bar.symbol)
        if len(bucket) < len(self.symbols):
            return

        self.complete_timestamps.append(bar.timestamp)

        scores: dict[str, float] = {}
        for symbol in self.symbols:
            closes = self.get_history(count=self.lookback, symbol=symbol, field="close")
            if len(closes) < self.lookback:
                return
            scores[symbol] = float(closes[-1] / closes[0] - 1.0)

        best_symbol = max(scores, key=lambda symbol: scores[symbol])
        self.selected_symbols.append(best_symbol)

        for symbol in self.symbols:
            if symbol != best_symbol and self.get_position(symbol) > 0:
                self.close_position(symbol)
        self.order_target_percent(target_percent=0.8, symbol=best_symbol)


def _run_multisymbol_bucket(
    data_map: dict[str, pd.DataFrame], symbols: list[str]
) -> Any:
    return run_backtest(
        data=data_map,
        strategy=BucketCrossSectionStrategy,
        symbols=symbols,
        symbol="BENCHMARK",
        initial_cash=100000.0,
        commission_rate=0.0,
        stamp_tax_rate=0.0,
        transfer_fee_rate=0.0,
        min_commission=0.0,
        lot_size=1,
        execution_mode="current_close",
        history_depth=2,
        show_progress=False,
    )


def test_multisymbol_bucket_rebalances_once_per_complete_timestamp() -> None:
    """Rebalance exactly once for each complete timestamp slice."""
    timestamps = [
        pd.Timestamp("2023-01-02 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-03 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-04 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-05 10:00:00", tz="Asia/Shanghai"),
    ]

    data_map = {
        "AAA": _build_symbol_df("AAA", timestamps, [10.0, 10.0, 10.0, 10.0]),
        "BBB": _build_symbol_df("BBB", timestamps, [10.0, 11.0, 12.0, 13.0]),
        "CCC": _build_symbol_df("CCC", timestamps, [10.0, 9.0, 8.0, 7.0]),
    }
    symbols = ["AAA", "BBB", "CCC"]

    result = _run_multisymbol_bucket(data_map, symbols)
    strategy = result.strategy

    assert len(strategy.complete_timestamps) == len(timestamps)
    assert all(len(v) == len(symbols) for v in strategy.seen_by_ts.values())
    assert strategy.selected_symbols == ["AAA", "BBB", "BBB", "BBB"]


def test_multisymbol_bucket_is_invariant_to_data_dict_order() -> None:
    """Keep cross-section outputs stable across dict insertion orders."""
    timestamps = [
        pd.Timestamp("2023-01-02 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-03 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-04 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-05 10:00:00", tz="Asia/Shanghai"),
    ]

    map_a = {
        "AAA": _build_symbol_df("AAA", timestamps, [10.0, 10.0, 10.0, 10.0]),
        "BBB": _build_symbol_df("BBB", timestamps, [10.0, 11.0, 12.0, 13.0]),
        "CCC": _build_symbol_df("CCC", timestamps, [10.0, 9.0, 8.0, 7.0]),
    }
    map_b = {
        "CCC": _build_symbol_df("CCC", timestamps, [10.0, 9.0, 8.0, 7.0]),
        "AAA": _build_symbol_df("AAA", timestamps, [10.0, 10.0, 10.0, 10.0]),
        "BBB": _build_symbol_df("BBB", timestamps, [10.0, 11.0, 12.0, 13.0]),
    }
    symbols = ["AAA", "BBB", "CCC"]

    result_a = _run_multisymbol_bucket(map_a, symbols)
    result_b = _run_multisymbol_bucket(map_b, symbols)

    strategy_a = result_a.strategy
    strategy_b = result_b.strategy

    assert strategy_a.complete_timestamps == strategy_b.complete_timestamps
    assert strategy_a.selected_symbols == strategy_b.selected_symbols


def test_multisymbol_bucket_skips_incomplete_timestamp() -> None:
    """Skip timestamps that are missing at least one symbol."""
    timestamps = [
        pd.Timestamp("2023-01-02 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-03 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-04 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-05 10:00:00", tz="Asia/Shanghai"),
    ]

    ccc_df = _build_symbol_df("CCC", timestamps, [10.0, 9.0, 8.0, 7.0]).drop(index=[1])

    data_map = {
        "AAA": _build_symbol_df("AAA", timestamps, [10.0, 10.0, 10.0, 10.0]),
        "BBB": _build_symbol_df("BBB", timestamps, [10.0, 11.0, 12.0, 13.0]),
        "CCC": ccc_df,
    }
    symbols = ["AAA", "BBB", "CCC"]

    result = _run_multisymbol_bucket(data_map, symbols)
    strategy = result.strategy

    assert len(strategy.complete_timestamps) == 3
    assert strategy.selected_symbols == ["AAA", "BBB", "BBB"]


def test_multisymbol_bucket_keeps_single_winner_position() -> None:
    """Keep at most one long position after each timestamp rebalance."""
    timestamps = [
        pd.Timestamp("2023-01-02 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-03 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-04 10:00:00", tz="Asia/Shanghai"),
        pd.Timestamp("2023-01-05 10:00:00", tz="Asia/Shanghai"),
    ]

    data_map = {
        "AAA": _build_symbol_df("AAA", timestamps, [10.0, 10.0, 10.0, 10.0]),
        "BBB": _build_symbol_df("BBB", timestamps, [10.0, 11.0, 12.0, 13.0]),
        "CCC": _build_symbol_df("CCC", timestamps, [10.0, 9.0, 8.0, 7.0]),
    }
    symbols = ["AAA", "BBB", "CCC"]

    result = _run_multisymbol_bucket(data_map, symbols)
    positions = result.positions
    positive_counts = (positions > 0).sum(axis=1)

    assert (positive_counts <= 1).all()
