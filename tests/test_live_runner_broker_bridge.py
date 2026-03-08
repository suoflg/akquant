import time
from types import SimpleNamespace
from typing import Any, Callable, cast

from akquant.live import LiveRunner


def test_live_runner_broker_bridge_dispatches_events() -> None:
    """Dispatch broker events to strategy callbacks."""

    class _DummyTraderGateway:
        def __init__(self) -> None:
            self._on_order: Callable[[Any], None] | None = None
            self._on_trade: Callable[[Any], None] | None = None
            self._on_execution_report: Callable[[Any], None] | None = None

        def on_order(self, callback: Callable[[Any], None]) -> None:
            self._on_order = callback

        def on_trade(self, callback: Callable[[Any], None]) -> None:
            self._on_trade = callback

        def on_execution_report(self, callback: Callable[[Any], None]) -> None:
            self._on_execution_report = callback

        def emit_order(self, payload: Any) -> None:
            if self._on_order is not None:
                self._on_order(payload)

        def emit_trade(self, payload: Any) -> None:
            if self._on_trade is not None:
                self._on_trade(payload)

        def emit_execution_report(self, payload: Any) -> None:
            if self._on_execution_report is not None:
                self._on_execution_report(payload)

    class _DummyStrategy:
        def __init__(self) -> None:
            self.orders: list[Any] = []
            self.trades: list[Any] = []
            self.reports: list[Any] = []
            self.errors: list[tuple[str, Any]] = []

        def on_order(self, order: Any) -> None:
            self.orders.append(order)

        def on_trade(self, trade: Any) -> None:
            self.trades.append(trade)

        def on_execution_report(self, report: Any) -> None:
            self.reports.append(report)

        def on_error(self, error: Exception, source: str, payload: Any = None) -> None:
            self.errors.append((source, payload))

    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "miniqmt"
    runner._init_broker_bridge_state()
    gateway = _DummyTraderGateway()
    strategy = _DummyStrategy()
    runner._bind_broker_callbacks(gateway, cast(Any, strategy))

    gateway.emit_order({"id": "o1"})
    gateway.emit_trade({"id": "t1"})
    gateway.emit_execution_report({"id": "r1"})
    time.sleep(0.2)
    runner._stop_broker_dispatcher()

    assert strategy.orders == [{"id": "o1"}]
    assert strategy.trades == [{"id": "t1"}]
    assert strategy.reports == [{"id": "r1"}]


def test_live_runner_broker_bridge_forwards_errors() -> None:
    """Forward callback exceptions to strategy on_error."""

    class _DummyTraderGateway:
        def __init__(self) -> None:
            self._on_trade: Callable[[Any], None] | None = None

        def on_order(self, callback: Callable[[Any], None]) -> None:
            return None

        def on_trade(self, callback: Callable[[Any], None]) -> None:
            self._on_trade = callback

        def on_execution_report(self, callback: Callable[[Any], None]) -> None:
            return None

        def emit_trade(self, payload: Any) -> None:
            if self._on_trade is not None:
                self._on_trade(payload)

    class _DummyErrorStrategy:
        def __init__(self) -> None:
            self.errors: list[tuple[str, Any]] = []

        def on_trade(self, trade: Any) -> None:
            raise RuntimeError("trade callback failed")

        def on_error(self, error: Exception, source: str, payload: Any = None) -> None:
            self.errors.append((source, payload))

    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "ptrade"
    runner._init_broker_bridge_state()
    gateway = _DummyTraderGateway()
    strategy = _DummyErrorStrategy()
    runner._bind_broker_callbacks(gateway, cast(Any, strategy))

    gateway.emit_trade({"id": "t2"})
    time.sleep(0.2)
    runner._stop_broker_dispatcher()

    assert strategy.errors
    assert strategy.errors[0][0] == "on_trade"


def test_live_runner_broker_bridge_deduplicates_events() -> None:
    """Deduplicate repeated broker events by semantic keys."""

    class _DummyStrategy:
        def __init__(self) -> None:
            self.orders: list[Any] = []

        def on_order(self, order: Any) -> None:
            self.orders.append(order)

    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "miniqmt"
    runner._init_broker_bridge_state()
    strategy = _DummyStrategy()
    payload = SimpleNamespace(
        broker_order_id="b1",
        status="Submitted",
        filled_quantity=0.0,
        timestamp_ns=100,
    )

    runner._queue_broker_event("order", payload)
    runner._queue_broker_event("order", payload)
    runner._drain_broker_events(cast(Any, strategy))

    assert len(strategy.orders) == 1


def test_live_runner_broker_bridge_recovers_from_sync() -> None:
    """Recover order and trade snapshots from trader gateway sync methods."""

    class _DummyTraderGateway:
        def __init__(self) -> None:
            self._on_order: Callable[[Any], None] | None = None
            self._on_trade: Callable[[Any], None] | None = None
            self._on_execution_report: Callable[[Any], None] | None = None
            self.connected = False

        def on_order(self, callback: Callable[[Any], None]) -> None:
            self._on_order = callback

        def on_trade(self, callback: Callable[[Any], None]) -> None:
            self._on_trade = callback

        def on_execution_report(self, callback: Callable[[Any], None]) -> None:
            self._on_execution_report = callback

        def heartbeat(self) -> bool:
            return self.connected

        def connect(self) -> None:
            self.connected = True

        def sync_open_orders(self) -> list[Any]:
            return [
                SimpleNamespace(
                    broker_order_id="b-sync-1",
                    status="Submitted",
                    filled_quantity=0.0,
                    timestamp_ns=101,
                )
            ]

        def sync_today_trades(self) -> list[Any]:
            return [
                SimpleNamespace(
                    trade_id="t-sync-1",
                    broker_order_id="b-sync-1",
                    timestamp_ns=102,
                )
            ]

    class _DummyStrategy:
        def __init__(self) -> None:
            self.orders: list[Any] = []
            self.trades: list[Any] = []

        def on_order(self, order: Any) -> None:
            self.orders.append(order)

        def on_trade(self, trade: Any) -> None:
            self.trades.append(trade)

        def on_execution_report(self, report: Any) -> None:
            return None

        def on_error(self, error: Exception, source: str, payload: Any = None) -> None:
            return None

    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "ptrade"
    runner._init_broker_bridge_state()
    runner._broker_recovery_interval_sec = 0.05
    gateway = _DummyTraderGateway()
    strategy = _DummyStrategy()
    runner._bind_broker_callbacks(gateway, cast(Any, strategy))
    runner._run_broker_recovery_cycle()
    runner._drain_broker_events(cast(Any, strategy))
    runner._stop_broker_dispatcher()

    assert strategy.orders
    assert strategy.trades
    assert "b-sync-1" in runner._broker_order_states
    assert "t-sync-1" in runner._broker_trade_keys


def test_live_runner_syncs_client_broker_order_id_mapping() -> None:
    """Sync id mapping from order, report and trade events."""
    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "miniqmt"
    runner._init_broker_bridge_state()

    runner._update_broker_state(
        "order",
        {
            "client_order_id": "c-map-1",
            "broker_order_id": "b-map-1",
            "status": "Submitted",
        },
    )
    runner._update_broker_state(
        "execution_report",
        {
            "client_order_id": "c-map-1",
            "broker_order_id": "b-map-1",
            "status": "Submitted",
            "timestamp_ns": 1,
        },
    )
    runner._update_broker_state(
        "trade",
        {
            "trade_id": "t-map-1",
            "broker_order_id": "b-map-1",
        },
    )

    assert runner._resolve_broker_order_id("c-map-1") == "b-map-1"
    assert runner._resolve_client_order_id("b-map-1") == "c-map-1"


def test_live_runner_cleans_mapping_on_terminal_status() -> None:
    """Cleanup active mapping when order enters terminal status."""
    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "miniqmt"
    runner._init_broker_bridge_state()

    runner._update_broker_state(
        "order",
        {
            "client_order_id": "c-term-1",
            "broker_order_id": "b-term-1",
            "status": "Submitted",
        },
    )
    assert not runner.can_submit_client_order("c-term-1")

    runner._update_broker_state(
        "execution_report",
        {
            "client_order_id": "c-term-1",
            "broker_order_id": "b-term-1",
            "status": "Cancelled",
            "timestamp_ns": 2,
        },
    )

    assert runner.can_submit_client_order("c-term-1")
    assert "b-term-1" in runner._closed_broker_order_ids
    assert runner._resolve_broker_order_id("c-term-1") == ""


def test_live_runner_submitter_checks_idempotency_and_maps() -> None:
    """Install submitter and map ids after broker placement."""

    class _DummyTraderGateway:
        def __init__(self) -> None:
            self.last_client_order_id = ""

        def place_order(self, req: Any) -> str:
            self.last_client_order_id = req.client_order_id
            return f"b-{req.client_order_id}"

    class _DummyStrategy:
        def __init__(self) -> None:
            self.errors: list[tuple[str, Any]] = []

        def on_error(self, error: Exception, source: str, payload: Any = None) -> None:
            self.errors.append((source, payload))

    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "miniqmt"
    runner._init_broker_bridge_state()
    gateway = _DummyTraderGateway()
    strategy = _DummyStrategy()
    runner._install_broker_order_submitter(cast(Any, gateway), cast(Any, strategy))
    strategy_any = cast(Any, strategy)

    broker_order_id = strategy_any.submit_order(
        symbol="000001.SZ",
        side="Buy",
        quantity=10.0,
        client_order_id="coid-1",
    )

    assert broker_order_id == "b-coid-1"
    assert runner._resolve_broker_order_id("coid-1") == "b-coid-1"
    assert runner._resolve_client_order_id("b-coid-1") == "coid-1"


def test_live_runner_submitter_forwards_duplicate_error() -> None:
    """Raise and forward error when submitting duplicate active client order id."""

    class _DummyTraderGateway:
        def place_order(self, req: Any) -> str:
            return f"b-{req.client_order_id}"

    class _DummyStrategy:
        def __init__(self) -> None:
            self.errors: list[tuple[str, Any]] = []

        def on_error(self, error: Exception, source: str, payload: Any = None) -> None:
            self.errors.append((source, payload))

    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "ptrade"
    runner._init_broker_bridge_state()
    runner._sync_order_id_mapping("coid-dup", "b-coid-dup")
    runner._broker_order_states["b-coid-dup"] = {"status": "Submitted"}
    gateway = _DummyTraderGateway()
    strategy = _DummyStrategy()
    runner._install_broker_order_submitter(cast(Any, gateway), cast(Any, strategy))
    strategy_any = cast(Any, strategy)

    try:
        strategy_any.submit_order(
            symbol="000002.SZ",
            side="Sell",
            quantity=5.0,
            client_order_id="coid-dup",
        )
    except RuntimeError as exc:
        assert "duplicate active client_order_id" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for duplicate client_order_id")

    assert strategy.errors
    assert strategy.errors[0][0] == "submit_order"


def test_live_runner_submit_order_supports_buy_and_sell_side() -> None:
    """Unified submit_order should support both buy and sell side."""

    class _DummyTraderGateway:
        def __init__(self) -> None:
            self.last_side = ""
            self.last_client_order_id = ""

        def place_order(self, req: Any) -> str:
            self.last_side = req.side
            self.last_client_order_id = req.client_order_id
            return f"b-{req.side}-{req.client_order_id}"

    class _DummyStrategy:
        def __init__(self) -> None:
            self.errors: list[tuple[str, Any]] = []

        def on_error(self, error: Exception, source: str, payload: Any = None) -> None:
            self.errors.append((source, payload))

    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "miniqmt"
    runner._init_broker_bridge_state()
    gateway = _DummyTraderGateway()
    strategy = _DummyStrategy()
    runner._install_broker_order_submitter(cast(Any, gateway), cast(Any, strategy))
    strategy_any = cast(Any, strategy)

    buy_broker_order_id = strategy_any.submit_order(
        symbol="000001.SZ",
        side="Buy",
        quantity=10.0,
        client_order_id="coid-buy-1",
    )
    sell_broker_order_id = strategy_any.submit_order(
        symbol="000001.SZ",
        side="Sell",
        quantity=5.0,
        client_order_id="coid-sell-1",
    )

    assert buy_broker_order_id == "b-Buy-coid-buy-1"
    assert sell_broker_order_id == "b-Sell-coid-sell-1"
    assert runner._resolve_broker_order_id("coid-buy-1") == "b-Buy-coid-buy-1"
    assert runner._resolve_broker_order_id("coid-sell-1") == "b-Sell-coid-sell-1"


def test_live_runner_injects_execution_capabilities() -> None:
    """Expose broker-live capabilities after submitter injection."""

    class _DummyTraderGateway:
        def place_order(self, req: Any) -> str:
            return f"b-{req.client_order_id}"

    class _DummyStrategy:
        def on_error(self, error: Exception, source: str, payload: Any = None) -> None:
            return None

    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "ptrade"
    runner._init_broker_bridge_state()
    gateway = _DummyTraderGateway()
    strategy = _DummyStrategy()
    runner._install_broker_order_submitter(cast(Any, gateway), cast(Any, strategy))
    strategy_any = cast(Any, strategy)
    capabilities = strategy_any.get_execution_capabilities()

    assert capabilities["broker_live"] is True
    assert capabilities["client_order_id"] is True


def test_live_runner_does_not_inject_removed_broker_aliases() -> None:
    """Keep unified submit_order as the only injected order entry."""

    class _DummyTraderGateway:
        def place_order(self, req: Any) -> str:
            return f"b-{req.client_order_id}"

    class _DummyStrategy:
        def on_error(self, error: Exception, source: str, payload: Any = None) -> None:
            return None

    runner = LiveRunner.__new__(LiveRunner)
    runner.broker = "ptrade"
    runner._init_broker_bridge_state()
    gateway = _DummyTraderGateway()
    strategy = _DummyStrategy()
    runner._install_broker_order_submitter(cast(Any, gateway), cast(Any, strategy))
    strategy_any = cast(Any, strategy)

    assert hasattr(strategy_any, "submit_order")
    assert not hasattr(strategy_any, "submit_broker_order")
    assert not hasattr(strategy_any, "broker_buy")
    assert not hasattr(strategy_any, "broker_sell")
