from akquant.gateway.ctp_adapter import CTPTraderAdapter
from akquant.gateway.mapper import create_default_mapper
from akquant.gateway.models import UnifiedOrderRequest


def _build_adapter(connected: bool = True) -> CTPTraderAdapter:
    adapter = CTPTraderAdapter.__new__(CTPTraderAdapter)
    adapter.mapper = create_default_mapper()
    adapter.order_callback = None
    adapter.trade_callback = None
    adapter.execution_callback = None
    adapter.orders = {}
    adapter.trades = []
    adapter.client_to_broker_order_ids = {}
    adapter.broker_to_client_order_ids = {}
    adapter._order_seq = 0
    adapter.gateway = type("Gateway", (), {"connected": connected})()
    return adapter


def test_ctp_adapter_place_and_cancel_order() -> None:
    """Place and cancel order should emit callbacks and update state."""
    adapter = _build_adapter(connected=True)
    order_ids: list[str] = []
    report_ids: list[str] = []
    adapter.on_order(lambda order: order_ids.append(order.broker_order_id))
    adapter.on_execution_report(
        lambda report: report_ids.append(report.broker_order_id)
    )

    broker_order_id = adapter.place_order(
        UnifiedOrderRequest(
            client_order_id="c1",
            symbol="au2606",
            side="Buy",
            quantity=1.0,
        )
    )
    adapter.cancel_order(broker_order_id)

    assert broker_order_id.startswith("ctp-c1-")
    assert order_ids[0] == broker_order_id
    assert report_ids[0] == broker_order_id
    assert report_ids[-1] == broker_order_id
    assert adapter.query_order(broker_order_id) is not None


def test_ctp_adapter_deduplicates_active_client_order_id() -> None:
    """Duplicate active client_order_id should return existing broker order id."""
    adapter = _build_adapter(connected=True)
    req = UnifiedOrderRequest(
        client_order_id="dup-c1",
        symbol="ag2606",
        side="Buy",
        quantity=1.0,
    )
    first = adapter.place_order(req)
    second = adapter.place_order(req)

    assert first == second
    assert len(adapter.orders) == 1


def test_ctp_adapter_ingest_events_update_state() -> None:
    """Ingested order/trade events should update adapter state."""
    adapter = _build_adapter(connected=True)
    trades: list[str] = []
    adapter.on_trade(lambda trade: trades.append(trade.trade_id))

    snapshot = adapter.ingest_order_event(
        {
            "client_order_id": "c2",
            "broker_order_id": "b2",
            "symbol": "rb2605",
            "status": "submitted",
            "timestamp_ns": 1,
        }
    )
    trade = adapter.ingest_trade_event(
        {
            "trade_id": "t2",
            "broker_order_id": "b2",
            "client_order_id": "c2",
            "symbol": "rb2605",
            "side": "Buy",
            "quantity": 1.0,
            "price": 100.0,
            "timestamp_ns": 2,
        }
    )

    assert snapshot.broker_order_id == "b2"
    assert trade.trade_id == "t2"
    assert trades == ["t2"]
    assert adapter.query_trades()[-1].trade_id == "t2"


def test_ctp_adapter_place_order_requires_connection() -> None:
    """Placing order without connection should fail fast."""
    adapter = _build_adapter(connected=False)
    try:
        adapter.place_order(
            UnifiedOrderRequest(
                client_order_id="c3",
                symbol="au2606",
                side="Sell",
                quantity=1.0,
            )
        )
    except RuntimeError as exc:
        assert "not connected" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for disconnected ctp trader")


def test_ctp_adapter_sync_open_orders_excludes_terminal_orders() -> None:
    """Cancelled orders should be excluded from open order sync."""
    adapter = _build_adapter(connected=True)
    broker_order_id = adapter.place_order(
        UnifiedOrderRequest(
            client_order_id="c4",
            symbol="ag2606",
            side="Buy",
            quantity=1.0,
        )
    )
    open_orders = adapter.sync_open_orders()
    assert any(order.broker_order_id == broker_order_id for order in open_orders)

    adapter.cancel_order(broker_order_id)
    open_orders_after_cancel = adapter.sync_open_orders()
    assert all(
        order.broker_order_id != broker_order_id for order in open_orders_after_cancel
    )
