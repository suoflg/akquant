# 执行语义切换清单

本清单用于将 legacy `execution_mode` / `timer_execution_policy` 最终切换到 `fill_policy`。

## 范围

- 不改公开入口名（`run_backtest` / `run_warm_start`）
- 继续保持 `symbols` 为唯一标的参数
- 将 `fill_policy` 作为执行语义主路径
- 通过 `legacy_execution_policy_compat` 分阶段推进

## 阶段 A：告警清理

- 先跑全量检查，确保无回归：

```bash
uv run ruff check .
uv run mypy .
uv run pytest -q
```

- 检索 legacy 调用残留：

```bash
rg 'execution_mode='
rg 'timer_execution_policy='
```

- 内部调用全部改写为 `fill_policy`
- 清理剩余 `execution_mode` / `timer_execution_policy` 调用点

## 阶段 B：测试/灰度验证

- 验证关键场景：
  - backtest + `fill_policy` 正常
  - warm start + `fill_policy` 正常
  - legacy 调用能给出明确迁移报错
- 生成并审核黄金基线报告：

```bash
uv run python scripts/golden_baseline_report.py
```

## 阶段 C：生产彻底移除 legacy

- 重点观察：
  - 是否仍有 legacy 调用触发迁移错误
  - 策略行为是否出现突变
- 准备回滚路径：
  - 快速回滚：环境变量改回 `true`
  - 版本回滚：回退部署版本

## 回滚点

- **R1：运行时回滚**
  - 仅改环境变量：
  - `AKQ_LEGACY_EXECUTION_POLICY_COMPAT=true`
- **R2：版本回滚**
  - 回滚到上一版发布产物
- **R3：调用点回滚**
  - 对个别问题调用点临时显式传 `legacy_execution_policy_compat=True`

## 完成标准

- 生产调用方不再依赖 legacy 执行语义
- 一个完整观察窗口内无 legacy execution policy 相关告警/报错
- 黄金基线回归报告通过策略负责人审核
