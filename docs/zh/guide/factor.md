# 因子表达式引擎速查

本页定位为“查表 + 排障”，用于快速回答三个问题：

1. 表达式怎么写才符合语义？
2. 算子有哪些、参数怎么填？
3. 报错或结果异常时先查什么？

如果你想系统学习从想法到落地的完整路径，请先看 [第 14 章：高性能因子挖掘与表达式引擎](../textbook/14_factor.md)。

## 1. 最小使用模板

```python
from akquant.factor import FactorEngine

engine = FactorEngine(catalog)
df = engine.run("Rank(Ts_Mean(Close, 10))")
df_batch = engine.run_batch(
    [
        "Ts_Mean(Close, 5)",
        "Rank(Volume)",
        "If(Close > Open, 1, 0)",
    ]
)
```

输入数据建议至少包含：

- `symbol`
- `date`
- `open`, `high`, `low`, `close`, `volume`（按策略实际需求）

## 2. 语法规则速览

### 2.1 变量与常量

- 列名不区分大小写：`Close` 与 `close` 等价。
- 数值常量可直接写：`1`、`0.5`。
- 变量名必须能映射到真实列；如数据是 `ClosePrice`，写 `Close` 会失败。

### 2.2 运算符

- 算术运算：`+`, `-`, `*`, `/`
- 比较运算：`>`, `<`, `>=`, `<=`, `==`, `!=`
- 逻辑组合：可在条件中使用 `&`, `|`

示例：

```python
If((Close > Open) & (Volume > Ts_Mean(Volume, 20)), 1, 0)
```

### 2.3 三类分区语义

- **TS（时序）**：按 `symbol` 分组滚动。
- **CS（截面）**：按 `date` 分组横截面。
- **EL（元素级）**：逐元素变换，不引入窗口。

跨分区嵌套（如 `Rank(Ts_Mean(...))`）会被拆步执行并物化中间结果。

## 3. 算子速查

### 3.1 时序算子 (TS)

| 算子 | 别名 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `Ts_Mean(X, d)` | `Mean` | 过去 `d` 期移动平均 | `Ts_Mean(Close, 5)` |
| `Ts_Std(X, d)` | `Std` | 过去 `d` 期移动标准差 | `Ts_Std(Close, 20)` |
| `Ts_Max(X, d)` | `Max` | 过去 `d` 期最大值 | `Ts_Max(High, 10)` |
| `Ts_Min(X, d)` | `Min` | 过去 `d` 期最小值 | `Ts_Min(Low, 10)` |
| `Ts_Sum(X, d)` | `Sum` | 过去 `d` 期求和 | `Ts_Sum(Volume, 5)` |
| `Ts_ArgMax(X, d)` | `ArgMax` | 过去 `d` 期最大值距今天数 | `Ts_ArgMax(Close, 5)` |
| `Ts_ArgMin(X, d)` | `ArgMin` | 过去 `d` 期最小值距今天数 | `Ts_ArgMin(Close, 5)` |
| `Ts_Rank(X, d)` | - | 当前值在过去 `d` 期分位排名 | `Ts_Rank(Close, 5)` |
| `Delta(X, d)` | - | `X(t) - X(t-d)` | `Delta(Close, 1)` |
| `Delay(X, d)` | `Ref` | 滞后 `d` 期数值 | `Delay(Close, 1)` |
| `Ts_Corr(X, Y, d)` | `Corr` | 过去 `d` 期相关系数 | `Ts_Corr(Close, Volume, 20)` |
| `Ts_Cov(X, Y, d)` | `Cov` | 过去 `d` 期协方差 | `Ts_Cov(Close, Open, 20)` |

### 3.2 截面算子 (CS)

| 算子 | 说明 | 示例 |
| :--- | :--- | :--- |
| `Rank(X)` | 同日横截面百分比排名（0~1） | `Rank(Close)` |
| `Scale(X)` | 同日归一化，`sum(abs(X)) = 1` | `Scale(Close)` |

### 3.3 逻辑与数学算子 (EL)

| 算子 | 说明 | 示例 |
| :--- | :--- | :--- |
| `If(Cond, A, B)` | 条件判断 | `If(Close > Open, 1, -1)` |
| `Sign(X)` | 符号函数（1, 0, -1） | `Sign(Close - Open)` |
| `Abs(X)` | 绝对值 | `Abs(Close - Open)` |
| `Log(X)` | 自然对数 | `Log(Volume)` |
| `SignedPower(X, e)` | 保持符号的幂运算 | `SignedPower(Close, 2)` |

## 4. 排障手册（按优先级）

### 4.1 结果全是 NaN

优先检查：

1. `d` 是否大于可用历史长度（Warmup 不足）。
2. 原始列是否有大量 NaN。
3. 列名是否真实可映射。

### 4.2 嵌套表达式明显变慢

常见原因是跨分区嵌套触发拆步物化。处理方式：

1. 先单独运行内层表达式。
2. 确认内层结果合理后再加外层。
3. 批量场景再考虑 `run_batch`。

### 4.3 窗口语义与预期不一致

若数据有停牌/缺失日期，滚动窗口按行推进，可能偏离“自然日”理解。建议先做交易日对齐。

### 4.4 列名看着对却报错

引擎会做大小写归一，但不会猜测别名。`ClosePrice` 与 `Close` 不是同一列。

### 4.5 同策略跨市场结果漂移

先检查时区与本地化：

1. 默认时区为 `Asia/Shanghai`。
2. 非 A 股必须显式设置 `timezone`。
3. 时间列需要显式 `tz_localize`。

更多时区细节见 [时区处理指南](../advanced/timezone.md)。

## 5. 性能建议

1. 先 `run` 调通，再 `run_batch` 扩展。
2. 减少不必要的深层嵌套，优先可解释的组合结构。
3. 使用最小必要列，降低 IO 与内存占用。
4. 对停牌和缺失日期提前清洗，减少窗口偏差导致的反复调试。

## 6. FAQ

**Q: 支持分钟线吗？**
A: 支持。`date` 包含时间戳即可；`d=60` 表示过去 60 根 bar。

**Q: 为什么同一表达式在不同数据源结果不同？**
A: 通常不是算子问题，而是数据对齐、复权、缺失值处理与时区设置差异。

**Q: 什么时候优先用 `run_batch`？**
A: 同样本池、同时间段、多因子并行评估时优先；单表达式调试时优先 `run`。
