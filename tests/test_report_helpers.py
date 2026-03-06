import pandas as pd
from akquant.plot.report import (
    _build_analysis_table_sections,
    _build_metrics_html,
    _build_summary_context,
)


class DummyMetrics:
    """Minimal metrics object for report helper tests."""

    total_return_pct = 10.0
    annualized_return = 5.0
    sharpe_ratio = 1.2
    max_drawdown_pct = 3.0
    volatility = 0.2
    win_rate = 55.0


class DummyResult:
    """Minimal backtest result-like object for helper function tests."""

    def __init__(self, with_data: bool) -> None:
        """Initialize fixture with or without analysis data."""
        self.initial_cash = 100000.0
        idx = pd.to_datetime(
            ["2023-01-01 10:00:00", "2023-01-02 10:00:00"], utc=True
        ).tz_convert("Asia/Shanghai")
        self.equity_curve = (
            pd.Series([100000.0, 101000.0], index=idx)
            if with_data
            else pd.Series(dtype=float)
        )
        self.metrics = DummyMetrics()
        self._trades_df = pd.DataFrame({"pnl": [1.0], "symbol": ["TEST"]})

    @property
    def trades_df(self) -> pd.DataFrame:
        """Return synthetic trades dataframe."""
        return self._trades_df

    @property
    def metrics_df(self) -> pd.DataFrame:
        """Return synthetic metrics dataframe fallback."""
        return pd.DataFrame({"value": [1.5, 1.0]}, index=["profit_factor", "avg_pnl"])

    def exposure_df(self) -> pd.DataFrame:
        """Return synthetic exposure decomposition data."""
        return pd.DataFrame(
            {
                "net_exposure_pct": [0.1],
                "gross_exposure_pct": [0.2],
                "leverage": [0.3],
            }
        )

    def capacity_df(self) -> pd.DataFrame:
        """Return synthetic capacity data."""
        return pd.DataFrame(
            {
                "order_count": [2.0],
                "filled_value": [1000.0],
                "fill_rate_qty": [1.0],
                "turnover": [0.01],
            }
        )

    def attribution_df(self, by: str = "symbol") -> pd.DataFrame:
        """Return synthetic attribution data."""
        _ = by
        return pd.DataFrame(
            {
                "group": ["TEST"],
                "trade_count": [1],
                "total_pnl": [100.0],
                "contribution_pct": [1.0],
                "total_commission": [0.0],
            }
        )


def test_build_summary_context_with_equity_data() -> None:
    """Summary context should render dates and final equity when equity exists."""
    context = _build_summary_context(DummyResult(with_data=True))
    assert context["start_date"] == "2023-01-01"
    assert context["end_date"] == "2023-01-02"
    assert context["final_equity"] == "101,000.00"


def test_build_analysis_table_sections_with_and_without_data() -> None:
    """Analysis section builder should render data and empty fallbacks."""
    result = DummyResult(with_data=True)
    sections = _build_analysis_table_sections(result)
    assert "最新净暴露比 (Latest Net Exposure %)" in sections["exposure_summary_html"]
    assert "平均换手率 (Avg Turnover)" in sections["capacity_summary_html"]
    assert "分组 (Group)" in sections["attribution_summary_html"]
    assert "TEST" in sections["attribution_summary_html"]
    assert "10.000000%" in sections["exposure_summary_html"]
    assert "1.000000%" in sections["capacity_summary_html"]
    assert "100.000000%" in sections["attribution_summary_html"]
    assert "1.00K" in sections["capacity_summary_html"]

    sections_raw = _build_analysis_table_sections(result, compact_currency=False)
    assert "1,000.000000" in sections_raw["capacity_summary_html"]

    class EmptyResult(DummyResult):
        """Override to simulate empty analysis outputs."""

        def exposure_df(self) -> pd.DataFrame:
            return pd.DataFrame()

        def capacity_df(self) -> pd.DataFrame:
            return pd.DataFrame()

        def attribution_df(self, by: str = "symbol") -> pd.DataFrame:
            _ = by
            return pd.DataFrame()

    empty_sections = _build_analysis_table_sections(EmptyResult(with_data=False))
    assert empty_sections["exposure_summary_html"] == "<div>暂无暴露数据</div>"
    assert empty_sections["capacity_summary_html"] == "<div>暂无容量数据</div>"
    assert empty_sections["attribution_summary_html"] == "<div>暂无归因数据</div>"


def test_build_metrics_html_contains_key_labels() -> None:
    """Metrics HTML should contain expected labels and formatted values."""
    html = _build_metrics_html(DummyResult(with_data=True))
    assert "累计收益率 (Total Return)" in html
    assert "交易次数 (Trades)" in html
