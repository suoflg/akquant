"""Strategy detailed plotting module."""

from typing import TYPE_CHECKING, Dict, Optional

import pandas as pd

from .utils import check_plotly, get_color, go, make_subplots

if TYPE_CHECKING:
    from ..backtest import BacktestResult


def _format_hover_value(
    row: pd.Series,
    key: str,
    kind: str = "str",
    default: str = "N/A",
) -> str:
    value = row.get(key)
    if value is None or pd.isna(value):
        return default
    if kind == "pct":
        return f"{float(value):.2%}"
    if kind == "num2":
        return f"{float(value):.2f}"
    if kind == "num4":
        return f"{float(value):.4f}"
    if kind == "int":
        return f"{int(float(value))}"
    if kind == "datetime" and hasattr(value, "strftime"):
        return str(value.strftime("%Y-%m-%d %H:%M:%S"))
    return str(value)


def _build_trade_hover_text(row: pd.Series) -> str:
    return "<br>".join(
        [
            f"方向: {_format_hover_value(row, 'side')}",
            f"开仓时间: {_format_hover_value(row, 'entry_time', 'datetime')}",
            f"平仓时间: {_format_hover_value(row, 'exit_time', 'datetime')}",
            f"数量: {_format_hover_value(row, 'quantity', 'num2')}",
            f"开仓价: {_format_hover_value(row, 'entry_price', 'num4')}",
            f"平仓价: {_format_hover_value(row, 'exit_price', 'num4')}",
            f"毛盈亏: {_format_hover_value(row, 'pnl', 'num2')}",
            f"净盈亏: {_format_hover_value(row, 'net_pnl', 'num2')}",
            f"收益率: {_format_hover_value(row, 'return_pct', 'pct')}",
            f"手续费: {_format_hover_value(row, 'commission', 'num2')}",
            f"持仓K线数: {_format_hover_value(row, 'duration_bars', 'int')}",
            f"持仓时长: {_format_hover_value(row, 'duration')}",
            f"MAE: {_format_hover_value(row, 'mae', 'pct')}",
            f"MFE: {_format_hover_value(row, 'mfe', 'pct')}",
            f"最大回撤: {_format_hover_value(row, 'max_drawdown_pct', 'pct')}",
            f"开仓标签: {_format_hover_value(row, 'entry_tag')}",
            f"平仓标签: {_format_hover_value(row, 'exit_tag')}",
        ]
    )


def plot_strategy(
    result: "BacktestResult",
    symbol: str,
    data: pd.DataFrame,
    indicators: Optional[Dict[str, pd.Series]] = None,
    title: Optional[str] = None,
    theme: str = "light",
    show: bool = True,
    filename: Optional[str] = None,
) -> Optional["go.Figure"]:
    """
    Plot detailed strategy execution for a specific symbol.

    Args:
        result: BacktestResult object.
        symbol: Symbol to plot.
        data: OHLCV DataFrame for the symbol (must have index as datetime).
        indicators: Dictionary of indicator series to overlay or plot in subplots.
        title: Chart title.
        theme: "light" or "dark".
        show: Whether to show the plot.
        filename: File path to save the plot.
    """
    if not check_plotly():
        return None

    if data.empty:
        print(f"No data provided for symbol {symbol}.")
        return None

    # Filter trades for this symbol
    trades_df = result.trades_df
    symbol_trades = pd.DataFrame()
    if not trades_df.empty:
        symbol_trades = trades_df[trades_df["symbol"] == symbol]

    # Layout:
    # Row 1: Candlestick + Overlays (Main) + Trade Markers
    # Row 2: Volume
    # Row 3+: Additional Indicators (if any, optional)

    rows = 2
    row_heights = [0.7, 0.3]

    # Check for separate subplots required by indicators?
    # For simplicity, we overlay all indicators on main chart unless
    # specified otherwise?
    # Let's assume indicators are overlays for now.

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )

    # 1. Candlestick
    fig.add_trace(
        go.Candlestick(
            x=data.index,
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            name="OHLC",
        ),
        row=1,
        col=1,
    )
    low_series = pd.to_numeric(data["low"], errors="coerce")
    high_series = pd.to_numeric(data["high"], errors="coerce")
    plot_price_min = low_series.min()
    plot_price_max = high_series.max()
    has_valid_price_band = (
        pd.notna(plot_price_min)
        and pd.notna(plot_price_max)
        and isinstance(plot_price_min, (int, float))
        and isinstance(plot_price_max, (int, float))
        and plot_price_max > plot_price_min
    )

    # 2. Indicators (Overlay)
    if indicators:
        colors = ["orange", "purple", "blue", "brown", "pink"]
        for i, (name, series) in enumerate(indicators.items()):
            color = colors[i % len(colors)]
            fig.add_trace(
                go.Scatter(
                    x=series.index,
                    y=series,
                    mode="lines",
                    name=name,
                    line=dict(color=color, width=1),
                ),
                row=1,
                col=1,
            )

    # 3. Trade Markers
    if not symbol_trades.empty:
        # Buy Markers (Entries)
        buys = symbol_trades[
            symbol_trades["side"].astype(str).str.upper().str.strip() == "LONG"
        ]
        if not buys.empty:
            buy_actual_prices = pd.to_numeric(buys["entry_price"], errors="coerce")
            buy_marker_prices = (
                buy_actual_prices.clip(lower=plot_price_min, upper=plot_price_max)
                if has_valid_price_band
                else buy_actual_prices
            )
            fig.add_trace(
                go.Scatter(
                    x=buys["entry_time"],
                    y=buy_marker_prices,
                    mode="markers",
                    name="Buy (Long)",
                    marker=dict(symbol="triangle-up", size=10, color="red"),
                    text=buys.apply(_build_trade_hover_text, axis=1),
                    customdata=buy_actual_prices.to_frame(name="price").to_numpy(),
                    hovertemplate=(
                        "<b>买入点 (Buy)</b><br>"
                        "价格: %{customdata[0]:.4f}<br>%{text}<extra></extra>"
                    ),
                ),
                row=1,
                col=1,
            )

        # Sell Markers (Exits for Long, Entries for Short)
        # For simplicity, we just mark entry and exit of closed trades
        # Exits
        exit_actual_prices = pd.to_numeric(symbol_trades["exit_price"], errors="coerce")
        exit_marker_prices = (
            exit_actual_prices.clip(lower=plot_price_min, upper=plot_price_max)
            if has_valid_price_band
            else exit_actual_prices
        )
        fig.add_trace(
            go.Scatter(
                x=symbol_trades["exit_time"],
                y=exit_marker_prices,
                mode="markers",
                name="Exit",
                marker=dict(
                    symbol="triangle-down",
                    size=10,
                    color="green",
                ),
                text=symbol_trades.apply(_build_trade_hover_text, axis=1),
                customdata=exit_actual_prices.to_frame(name="price").to_numpy(),
                hovertemplate=(
                    "<b>卖出点 (Exit)</b><br>"
                    "价格: %{customdata[0]:.4f}<br>%{text}<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )

    # 4. Volume
    if "volume" in data.columns:
        volume_series = pd.to_numeric(data["volume"], errors="coerce").fillna(0.0)
        if "open" in data.columns and "close" in data.columns:
            open_series = pd.to_numeric(data["open"], errors="coerce")
            close_series = pd.to_numeric(data["close"], errors="coerce")
            volume_colors = [
                "rgba(220, 38, 38, 0.8)" if c >= o else "rgba(22, 163, 74, 0.8)"
                for o, c in zip(open_series, close_series)
            ]
        else:
            volume_colors = ["rgba(107, 114, 128, 0.8)"] * len(volume_series)
        fig.add_trace(
            go.Bar(
                x=data.index,
                y=volume_series,
                name="Volume",
                marker=dict(color=volume_colors, line=dict(width=0)),
                opacity=0.9,
                hovertemplate=(
                    "<b>成交量</b><br>时间: %{x}<br>数量: %{y:,.0f}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )

    # Update Layout
    bg_color = get_color(theme, "bg_color")
    text_color = get_color(theme, "text_color")
    grid_color = get_color(theme, "grid_color")
    x_min = data.index.min()
    x_max = data.index.max()

    title = title or f"Strategy Analysis: {symbol}"

    fig.update_layout(
        title=title,
        height=800,
        template="plotly_white" if theme == "light" else "plotly_dark",
        plot_bgcolor=bg_color,
        paper_bgcolor=bg_color,
        font=dict(color=text_color),
        xaxis_rangeslider_visible=False,
        dragmode="zoom",
    )

    xaxis_kwargs = {"gridcolor": grid_color, "fixedrange": False}
    if pd.notna(x_min) and pd.notna(x_max):
        xaxis_kwargs["range"] = [x_min, x_max]
        xaxis_kwargs["minallowed"] = x_min
        xaxis_kwargs["maxallowed"] = x_max
    fig.update_xaxes(**xaxis_kwargs)
    fig.update_yaxes(gridcolor=grid_color, fixedrange=False)
    if "volume" in data.columns:
        fig.update_yaxes(
            title_text="成交量 (股)",
            tickformat="~s",
            separatethousands=True,
            rangemode="tozero",
            row=2,
            col=1,
        )

    if filename:
        if filename.endswith(".html"):
            fig.write_html(filename)
        else:
            fig.write_image(filename)

    if show:
        fig.show()

    return fig
