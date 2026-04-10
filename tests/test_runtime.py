from __future__ import annotations

import time
import unittest

from zmk_usb_bridge_gui.protocol import HelloMessage
from zmk_usb_bridge_gui.runtime import AppRuntime
from zmk_usb_bridge_gui.serial_discovery import ReceiverPortCandidate, SerialPortInfo
from zmk_usb_bridge_gui.session import SessionDisconnectedEvent


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeSession:
    def __init__(self) -> None:
        self.open_calls: list[str] = []
        self.sent_messages = []
        self.events = []
        self.closed = False

    def open(self, device: str, *, baudrate: int = 115200) -> None:
        self.open_calls.append(device)

    def close(self) -> None:
        self.closed = True

    def send_message(self, message) -> None:
        self.sent_messages.append(message)

    def drain_events(self):
        events = list(self.events)
        self.events.clear()
        return events


def make_candidate(
    device: str,
    *,
    product: str = "zmk-usb-bridge-gui",
    channel: str = "gui",
    protocol_version: int = 1,
    serial_number: str | None = None,
    location: str | None = None,
) -> ReceiverPortCandidate:
    hello = HelloMessage(product=product, channel=channel, protocol_version=protocol_version)
    return ReceiverPortCandidate(
        port=SerialPortInfo(
            device=device,
            vid=0x2FE3,
            pid=0x0012,
            serial_number=serial_number,
            location=location,
        ),
        vid_pid_match=True,
        hello_verified=True,
        hello_product=hello.product,
        hello_channel=hello.channel,
        hello_protocol_version=hello.protocol_version,
    )


class RuntimeTests(unittest.TestCase):
    def _wait_until(self, runtime: AppRuntime, predicate, *, timeout_s: float = 0.2) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            runtime.tick()
            if predicate():
                return
            time.sleep(0.01)
        runtime.tick()
        self.assertTrue(predicate())

    def test_multiple_receivers_do_not_auto_attach(self) -> None:
        clock = FakeClock()
        sessions: list[FakeSession] = []

        def session_factory() -> FakeSession:
            session = FakeSession()
            sessions.append(session)
            return session

        runtime = AppRuntime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5"), make_candidate("COM6")],
            session_factory=session_factory,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.discovery_state == "multiple_receivers")

        self.assertEqual(runtime.state.discovery_state, "multiple_receivers")
        self.assertFalse(runtime.state.attached)
        self.assertEqual(sessions, [])

    def test_mismatched_protocol_port_is_ignored(self) -> None:
        clock = FakeClock()
        runtime = AppRuntime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5", protocol_version=2)],
            session_factory=FakeSession,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.discovery_state == "receiver_not_found")

        self.assertEqual(runtime.state.discovery_state, "receiver_not_found")
        self.assertFalse(runtime.state.attached)

    def test_disconnect_returns_to_discovery(self) -> None:
        clock = FakeClock()
        sessions: list[FakeSession] = []

        def session_factory() -> FakeSession:
            session = FakeSession()
            sessions.append(session)
            return session

        runtime = AppRuntime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5")],
            session_factory=session_factory,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.attached)
        self.assertTrue(runtime.state.attached)

        sessions[0].events.append(SessionDisconnectedEvent("Receiver port disconnected"))
        self._wait_until(runtime, lambda: runtime.state.discovery_state == "disconnected")

        self.assertFalse(runtime.state.attached)
        self.assertEqual(runtime.state.discovery_state, "disconnected")

    def test_product_mismatch_port_is_ignored(self) -> None:
        clock = FakeClock()
        runtime = AppRuntime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5", product="other-product")],
            session_factory=FakeSession,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.discovery_state == "receiver_not_found")

        self.assertEqual(runtime.state.discovery_state, "receiver_not_found")
        self.assertFalse(runtime.state.attached)

    def test_log_channel_port_is_ignored(self) -> None:
        clock = FakeClock()
        runtime = AppRuntime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5", channel="log")],
            session_factory=FakeSession,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.discovery_state == "receiver_not_found")

        self.assertEqual(runtime.state.discovery_state, "receiver_not_found")
        self.assertFalse(runtime.state.attached)

    def test_refresh_requests_status_and_candidates(self) -> None:
        clock = FakeClock()
        sessions: list[FakeSession] = []

        def session_factory() -> FakeSession:
            session = FakeSession()
            sessions.append(session)
            return session

        runtime = AppRuntime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5")],
            session_factory=session_factory,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.attached)
        runtime.refresh()

        self.assertEqual([message.name for message in sessions[0].sent_messages], ["get_status", "get_candidates"])

    def test_refresh_does_not_send_while_busy(self) -> None:
        clock = FakeClock()
        sessions: list[FakeSession] = []

        def session_factory() -> FakeSession:
            session = FakeSession()
            sessions.append(session)
            return session

        runtime = AppRuntime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5")],
            session_factory=session_factory,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.attached)
        runtime.state.pending_command_names.add("scan_start")
        runtime.refresh()

        self.assertEqual(sessions[0].sent_messages, [])

    def test_scan_does_not_send_while_busy(self) -> None:
        clock = FakeClock()
        sessions: list[FakeSession] = []

        def session_factory() -> FakeSession:
            session = FakeSession()
            sessions.append(session)
            return session

        runtime = AppRuntime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5")],
            session_factory=session_factory,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.attached)
        runtime.state.receiver_state = "connecting"
        runtime.scan_start()

        self.assertEqual(sessions[0].sent_messages, [])

    def test_reconnect_discovery_reuses_preferred_identity(self) -> None:
        clock = FakeClock()
        configs = []
        sessions: list[FakeSession] = []
        first_round = True

        def discover_ports(config, **_kwargs):
            nonlocal first_round
            configs.append(config)
            if first_round:
                first_round = False
                return [make_candidate("COM5", serial_number="abc123", location="usb-1")]
            return []

        def session_factory() -> FakeSession:
            session = FakeSession()
            sessions.append(session)
            return session

        runtime = AppRuntime(
            discover_ports=discover_ports,
            session_factory=session_factory,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.attached)
        sessions[0].events.append(SessionDisconnectedEvent("Receiver port disconnected"))
        self._wait_until(runtime, lambda: runtime.state.discovery_state == "disconnected")
        clock.now += 2.1
        self._wait_until(runtime, lambda: len(configs) >= 2)

        self.assertIsNone(configs[0].preferred_serial_number)
        self.assertEqual(configs[1].preferred_serial_number, "abc123")
        self.assertEqual(configs[1].preferred_device_path, "usb-1")


if __name__ == "__main__":
    unittest.main()
