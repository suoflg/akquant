from typing import Any

from .utils import parse_duration_to_bars


def _resolve_validation_windows(strategy: Any) -> tuple[int, int, int]:
    """解析模型 walk-forward 配置窗口."""
    if strategy.model is None or strategy.model.validation_config is None:
        return 0, 0, 0

    cfg = strategy.model.validation_config
    train_window = parse_duration_to_bars(cfg.train_window, cfg.frequency)
    test_window = parse_duration_to_bars(cfg.test_window, cfg.frequency)
    rolling_step = parse_duration_to_bars(cfg.rolling_step, cfg.frequency)
    return train_window, test_window, rolling_step


def _effective_training_step(test_window: int, rolling_step: int) -> int:
    """计算有效训练步长."""
    if rolling_step > 0:
        return rolling_step
    if test_window > 0:
        return test_window
    return 0


def auto_configure_model(strategy: Any) -> None:
    """应用模型校验配置（如滚动训练窗口参数）."""
    if strategy._model_configured:
        return

    if strategy.model and strategy.model.validation_config:
        try:
            train_window, test_window, rolling_step = _resolve_validation_windows(
                strategy
            )
            effective_step = _effective_training_step(test_window, rolling_step)
            strategy.set_rolling_window(train_window, effective_step)
            setattr(strategy, "_rolling_test_window", test_window)
            setattr(strategy, "_rolling_last_train_bar", 0)
            setattr(strategy, "_rolling_window_index", 0)
            setattr(strategy, "_rolling_next_train_bar", max(train_window, 1))
        except Exception as e:
            print(f"Failed to configure model validation: {e}")

    strategy._model_configured = True


def should_trigger_training(strategy: Any) -> bool:
    """返回当前 bar 是否应触发自动训练."""
    if strategy._rolling_step <= 0:
        return False

    validation_config = getattr(
        getattr(strategy, "model", None),
        "validation_config",
        None,
    )
    if validation_config is None:
        return bool(int(strategy._bar_count) % int(strategy._rolling_step) == 0)

    next_train_bar = int(
        getattr(strategy, "_rolling_next_train_bar", strategy._rolling_train_window)
    )
    return bool(
        int(strategy._bar_count)
        >= max(next_train_bar, int(strategy._rolling_train_window))
    )


def consume_training_trigger(strategy: Any) -> None:
    """消费一次训练触发并推进下一窗口."""
    validation_config = getattr(
        getattr(strategy, "model", None),
        "validation_config",
        None,
    )
    if validation_config is None or strategy._rolling_step <= 0:
        return

    setattr(strategy, "_rolling_last_train_bar", int(strategy._bar_count))
    setattr(
        strategy,
        "_rolling_next_train_bar",
        int(strategy._bar_count) + int(strategy._rolling_step),
    )
    setattr(
        strategy,
        "_rolling_window_index",
        int(getattr(strategy, "_rolling_window_index", 0)) + 1,
    )


def on_train_signal(strategy: Any, context: Any) -> None:
    """滚动训练信号回调."""
    if strategy.model:
        try:
            X_df, _ = strategy.get_rolling_data()

            if (
                strategy.model.validation_config
                and strategy.model.validation_config.verbose
            ):
                ts_str = ""
                if strategy.current_bar:
                    ts_str = strategy.format_time(strategy.current_bar.timestamp)
                train_window = int(getattr(strategy, "_rolling_train_window", 0))
                test_window = int(getattr(strategy, "_rolling_test_window", 0))
                window_index = int(getattr(strategy, "_rolling_window_index", 0))
                print(
                    f"[{ts_str}] Auto-training triggered | "
                    f"Window={window_index} | "
                    f"Train Size={len(X_df)} | "
                    f"Train Window={train_window} | "
                    f"Test Window={test_window}"
                )

            X, y = strategy.prepare_features(X_df, mode="training")
            strategy.model.fit(X, y)
        except NotImplementedError:
            pass
        except Exception as e:
            print(f"Auto-training failed at bar {strategy._bar_count}: {e}")
