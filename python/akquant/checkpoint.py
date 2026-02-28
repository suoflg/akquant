import os
import pickle
from typing import Any, Optional, Tuple

import akquant as aq


def save_snapshot(engine: aq.Engine, strategy: Any, filepath: str) -> None:
    """
    保存当前运行状态到文件.

    :param engine: akquant.Engine 实例
    :param strategy: 策略实例
    :param filepath: 保存路径 (包含文件名)
    """
    # 1. Get binary state from Rust Engine
    # Note: engine.get_state_bytes returns bytes directly in Python
    engine_bytes = engine.get_state_bytes()  # type: ignore[attr-defined]

    # 2. Construct snapshot dict
    snapshot = {
        "engine_state": engine_bytes,
        "strategy": strategy,
        "version": aq.__version__,
    }

    # 3. Save to file
    with open(filepath, "wb") as f:
        pickle.dump(snapshot, f)
    print(f"Snapshot saved to {filepath}")


def warm_start(
    filepath: str, data_feed: Optional[aq.DataFeed] = None
) -> Tuple[aq.Engine, Any]:
    """
    从快照恢复并热启动.

    :param filepath: 快照文件路径
    :param data_feed: 新的数据源 (可选). 如果为 None，则引擎无数据源，需后续手动添加.
    :return: (engine, strategy)
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Snapshot file not found: {filepath}")

    with open(filepath, "rb") as f:
        snapshot = pickle.load(f)

    # 1. Restore Strategy
    strategy = snapshot["strategy"]

    # 2. Initialize new Engine
    engine = aq.Engine()

    # 3. Set DataFeed if provided
    if data_feed:
        engine.add_data(data_feed)

    # 4. Load Rust State
    # This restores portfolio, orders, and sets snapshot_time
    engine.load_state_bytes(snapshot["engine_state"])  # type: ignore[attr-defined]

    # 5. Restore Strategy reference to Engine if necessary
    # Note: Strategy class in akquant doesn't hold 'engine' reference explicitly.
    # But if user strategy does, they should handle it or we can try.
    if hasattr(strategy, "engine"):
        strategy.engine = engine

    # print(f"Warm start loaded from {filepath}. Snapshot time: {engine.snapshot_time}")

    return engine, strategy
