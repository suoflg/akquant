import importlib.util
from pathlib import Path
from types import ModuleType


def _load_live_web_module() -> ModuleType:
    module_path = (
        Path(__file__).resolve().parents[1] / "examples" / "64_indicator_live_web.py"
    )
    spec = importlib.util.spec_from_file_location(
        "indicator_live_web_example", module_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_state_payload_returns_full_snapshot_window() -> None:
    """Full state reads should return the current window payload."""
    module = _load_live_web_module()
    state = module.IndicatorLiveState(
        started=True,
        finished=False,
        run_id="demo-run",
    )
    state.latest_indicator_values["close_echo"] = 101.5
    state.point_messages.extend(
        [
            {"seq": 5, "type": "point", "indicator": {"indicator_key": "close_echo"}},
            {"seq": 7, "type": "point", "indicator": {"indicator_key": "close_echo"}},
        ]
    )
    state.snapshot_messages.append(
        {"seq": 6, "type": "snapshot", "snapshot": {"indicator_count": 1}}
    )

    payload = module._build_state_payload(state)

    assert payload["run_id"] == "demo-run"
    assert payload["cursor"] == {
        "latest_seq": 7,
        "since_seq": None,
        "incremental": False,
    }
    assert payload["counts"] == {
        "point_messages": 2,
        "snapshot_messages": 1,
    }
    assert "window" in payload
    assert "delta" not in payload
    assert len(payload["window"]["point_messages"]) == 2
    assert len(payload["window"]["snapshot_messages"]) == 1


def test_build_state_payload_returns_incremental_delta_only() -> None:
    """Incremental state reads should return only delta payloads."""
    module = _load_live_web_module()
    state = module.IndicatorLiveState(
        started=True,
        finished=True,
        run_id="demo-run",
    )
    state.point_messages.extend(
        [
            {"seq": 10, "type": "point", "indicator": {"indicator_key": "close_echo"}},
            {"seq": 14, "type": "point", "indicator": {"indicator_key": "close_echo"}},
        ]
    )
    state.snapshot_messages.extend(
        [
            {"seq": 11, "type": "snapshot", "snapshot": {"indicator_count": 1}},
            {"seq": 15, "type": "snapshot", "snapshot": {"indicator_count": 1}},
        ]
    )

    payload = module._build_state_payload(state, since_seq=11)

    assert payload["cursor"] == {
        "latest_seq": 15,
        "since_seq": 11,
        "incremental": True,
    }
    assert payload["counts"] == {
        "point_messages": 2,
        "snapshot_messages": 2,
    }
    assert "delta" in payload
    assert "window" not in payload
    assert [message["seq"] for message in payload["delta"]["point_messages"]] == [14]
    assert [message["seq"] for message in payload["delta"]["snapshot_messages"]] == [15]
