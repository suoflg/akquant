# Factor Expression Engine

AKQuant includes a high-performance factor expression engine (`akquant.factor`) that allows users to define complex Alpha factors using concise string formulas. It is built on **Polars** (Rust), providing extreme performance and parallel processing capabilities.

## Key Features

*   **High Performance**: Based on Polars Lazy API, optimizing query plans and utilizing Rust multi-threaded execution.
*   **Concise Syntax**: Uses WorldQuant Alpha101-like syntax, e.g., `Rank(Ts_Mean(Close, 5))`.
*   **Future-Data Prevention**: Encapsulated time-series operators (like `Ts_Mean`) handle windows and shifts automatically, reducing the risk of look-ahead bias.
*   **Automatic Alignment**: The engine automatically handles panel data alignment and grouping (Group By Symbol/Date).

## Quick Start

### 1. Prepare Data

The engine uses `ParquetDataCatalog` by default. To ensure the factor engine works correctly, you need to organize your data in a panel format and ensure it includes the following key columns:

*   **`symbol`** (String): Ticker symbol, used to distinguish different assets (for group-by operations).
*   **`date`** (Datetime): Date or timestamp, used for time-series sorting and alignment.
*   **OHLCV Fields**: Such as `open`, `high`, `low`, `close`, `volume`, etc., used for factor calculation.

**Example: Building Simulation Data and Writing**

```python
import pandas as pd
import numpy as np
from akquant.data import ParquetDataCatalog

# 1. Create simulation data
dates = pd.date_range(start="2023-01-01", periods=100, freq="D")
symbols = ["AAPL", "MSFT", "GOOG"]

data_list = []
for symbol in symbols:
    # Simulate random prices
    price = 100 + np.cumsum(np.random.randn(len(dates)))
    df = pd.DataFrame({
        "date": dates,
        "symbol": symbol,
        "open": price + np.random.randn(len(dates)),
        "high": price + 5,
        "low": price - 5,
        "close": price,
        "volume": np.random.randint(1000, 10000, len(dates))
    })
    # Ensure date is datetime type
    df["date"] = pd.to_datetime(df["date"])
    data_list.append(df)

# Write to catalog
# ParquetDataCatalog.write accepts a DataFrame for a single symbol
catalog = ParquetDataCatalog("./data_catalog")

for df in data_list:
    symbol = df["symbol"].iloc[0]
    # Note: write method handles index automatically.
    # Recommended to set date as index or keep as a column.
    df.set_index("date", inplace=True)
    catalog.write(symbol, df)

print("Data preparation complete! Directory: ./data_catalog")
```

### 2. Calculate Factors

```python
from akquant.factor import FactorEngine

# Initialize engine
engine = FactorEngine(catalog)

# Run a single expression
# Returns a DataFrame with [date, symbol, factor_value]
df = engine.run("Rank(Ts_Mean(Close, 10))")
print(df.head())

# Run batch expressions
df_batch = engine.run_batch([
    "Ts_Mean(Close, 5)",
    "Rank(Volume)",
    "If(Close > Open, 1, 0)"
])
```

## Operators Reference

Expressions support variables (column names, case-insensitive, e.g., `Close`, `open`) and constants.

### Time Series Operators

Calculated independently for each symbol over time.

| Operator | Description | Example |
| :--- | :--- | :--- |
| `Ts_Mean(X, d)` | Rolling mean over past `d` days | `Ts_Mean(Close, 5)` |
| `Ts_Std(X, d)` | Rolling std dev over past `d` days | `Ts_Std(Close, 20)` |
| `Ts_Max(X, d)` | Rolling max over past `d` days | `Ts_Max(High, 10)` |
| `Ts_Min(X, d)` | Rolling min over past `d` days | `Ts_Min(Low, 10)` |
| `Ts_Sum(X, d)` | Rolling sum over past `d` days | `Ts_Sum(Volume, 5)` |
| `Ts_Corr(X, Y, d)` | Rolling correlation of X and Y | `Ts_Corr(Close, Volume, 20)` |
| `Ts_Cov(X, Y, d)` | Rolling covariance of X and Y | `Ts_Cov(Close, Open, 20)` |
| `Delay(X, d)` | Lagged value by `d` days (Ref) | `Delay(Close, 1)` |
| `Delta(X, d)` | Difference: `X(t) - X(t-d)` | `Delta(Close, 1)` |

### Cross Sectional Operators

Calculated across all symbols at the same timestamp.

| Operator | Description | Example |
| :--- | :--- | :--- |
| `Rank(X)` | Percentile rank (0 to 1) | `Rank(Ts_Mean(Close, 5))` |
| `Scale(X)` | Scale such that `sum(abs(X)) = 1` | `Scale(Close)` |

### Math & Logic Operators

| Operator | Description | Example |
| :--- | :--- | :--- |
| `Log(X)` | Natural logarithm | `Log(Volume)` |
| `Abs(X)` | Absolute value | `Abs(Return)` |
| `Sign(X)` | Sign function (1, 0, -1) | `Sign(Close - Open)` |
| `SignedPower(X, e)` | Power preserving sign | `SignedPower(Close, 2)` |
| `If(Cond, A, B)` | Conditional (If-Else) | `If(Close > Open, 1, -1)` |

### Basic Operations

Supports arithmetic `+`, `-`, `*`, `/` and comparison `>`, `<`, `>=`, `<=`, `==`, `!=`.

Example:
```
(Close - Open) / Open
```

## Advanced Tips

### 1. Alignment & Padding

The engine uses Polars `LazyFrame` for calculation. For time-series operations (e.g., `Ts_Mean`), Polars operates on data grouped by `symbol`.
**Note**: If data is missing for certain dates (e.g., trading halts), `rolling` window calculations might be based on physical rows rather than time. To ensure precision, it is recommended to reindex/pad your data against a trading calendar before writing it to the catalog.

### 2. Memory Optimization

`FactorEngine` uses Lazy Evaluation:
1.  `engine.run()` does not load all data into memory immediately.
2.  Polars constructs a query plan and only reads the columns required for calculation (Projection Pushdown).
3.  For example, when calculating `Ts_Mean(Close, 5)`, the engine only reads `symbol`, `date`, and `close` columns, ignoring `open`, `high`, etc., saving significant memory.

### 3. Composite Factor Examples

You can nest multiple operators to build complex Alpha factors:

*   **Price-Volume Divergence**: `Ts_Corr(Close, Volume, 20)` (Correlation between price and volume)
*   **Momentum Reversal**: `Rank(Ts_Mean(Close, 5)) - Rank(Ts_Mean(Close, 20))` (Short-term momentum minus long-term momentum)
*   **Volatility Adjusted Momentum**: `Ts_Mean(Close, 20) / Ts_Std(Close, 20)`

## FAQ

**Q: Is intraday data (minute bars) supported?**
A: Yes. As long as the `date` column contains timestamps. Time-series operators (e.g., `Ts_Mean`) are based on window length (number of rows). For minute bars, `d=60` represents the past 60 minute bars.

**Q: How to handle trading halts?**
A: It is recommended to pad records for halted days (using forward fill or NaN) before storing data. If the date is missing from the data, `rolling` functions will skip that date and take the previous row as `t-1`, which might not be intended behavior.

**Q: Why is my result full of NaNs?**
A:
1.  Check if window size `d` is larger than data length (Warmup period).
2.  Check if data contains many NaNs.
3.  Check if column names are correct (e.g., `Close` vs `close`; the engine auto-converts to lowercase, but `ClosePrice` won't match `close`).
