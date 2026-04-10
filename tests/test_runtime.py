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
        self.device = None

    def open(self, device: str, *, baudrate: int = 115200) -> None:
        self.open_calls.append(device)
        self.device = device

    def close(self) -> None:
        self.closed = True

    def send_message(self, message) -> None:
        self.sent_messages.append(message)

    def drain_events(self):
        events = list(self.events)
        self.events.clear()
        return events


class FakeCapture:
    def __init__(self) -> None:
        self.active = True
        self.session_id = "20260410_120000_test"
        self.log_path = "logs/sessions/20260410_120000_test.jsonl"
        self.started = False
        self.stopped = False
        self.app_events: list[tuple[str, str, dict | None, str | None]] = []
        self.lifecycle_events: list[tuple[str, str, dict | None, str | None, str | None]] = []
        self.reader_failures: list[tuple[str, str, str | None, str | None]] = []
        self.debug_text: list[tuple[str, str, str]] = []
        self.protocol_records: list[tuple[str, str, dict | None, str | None, str | None]] = []
        self.errors: list[str] = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def drain_errors(self) -> list[str]:
        errors = list(self.errors)
        self.errors.clear()
        return errors

    def record_app_event(self, event: str, *, kind: str, fields=None, detail=None) -> None:
        self.app_events.append((event, kind, fields, detail))

    def record_capture_lifecycle(
        self,
        *,
        source: str,
        event: str,
        fields=None,
        port=None,
        device_path=None,
        serial_number=None,
        detail=None,
    ) -> None:
        self.lifecycle_events.append((source, event, fields, detail, port))

    def record_reader_failure(self, *, source: str, reason: str, port_info=None, exception_class=None) -> None:
        self.reader_failures.append(
            (source, reason, getattr(port_info, "device", None), exception_class)
        )

    def record_debug_text(self, *, source: str, raw: str, port_info: SerialPortInfo) -> None:
        self.debug_text.append((source, raw, port_info.device))

    def record_protocol(self, *, direction: str, raw: str, parsed=None, detail=None, port=None) -> None:
        self.protocol_records.append((direction, raw, parsed, detail, port))


class FakeTextLogReader:
    def __init__(self, *, port_info, on_line, on_failure, baudrate) -> None:
        self.port_info = port_info
        self.on_line = on_line
        self.on_failure = on_failure
        self.baudrate = baudrate
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True


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
    def _build_runtime(self, **kwargs) -> tuple[AppRuntime, FakeCapture]:
        capture = FakeCapture()
        runtime = AppRuntime(capture_factory=lambda: capture, **kwargs)
        return runtime, capture

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

        runtime, _capture = self._build_runtime(
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
        runtime, _capture = self._build_runtime(
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

        runtime, _capture = self._build_runtime(
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
        runtime, _capture = self._build_runtime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5", product="other-product")],
            session_factory=FakeSession,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.discovery_state == "receiver_not_found")

        self.assertEqual(runtime.state.discovery_state, "receiver_not_found")
        self.assertFalse(runtime.state.attached)

    def test_log_channel_port_is_ignored(self) -> None:
        clock = FakeClock()
        runtime, _capture = self._build_runtime(
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

        runtime, capture = self._build_runtime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5")],
            session_factory=session_factory,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.attached)
        runtime.refresh()

        self.assertEqual([message.name for message in sessions[0].sent_messages], ["get_status", "get_candidates"])
        self.assertIn(("refresh_requested", "lifecycle", None, None), capture.app_events)

    def test_refresh_does_not_send_while_busy(self) -> None:
        clock = FakeClock()
        sessions: list[FakeSession] = []

        def session_factory() -> FakeSession:
            session = FakeSession()
            sessions.append(session)
            return session

        runtime, _capture = self._build_runtime(
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

        runtime, _capture = self._build_runtime(
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

    def test_receiver_debug_port_attaches_to_unique_sibling(self) -> None:
        clock = FakeClock()
        ports = [
            SerialPortInfo(device="COM5", vid=0x2FE3, pid=0x0012, serial_number="abc123", location="usb-1"),
            SerialPortInfo(device="COM6", vid=0x2FE3, pid=0x0012, serial_number="abc123", location="usb-1"),
        ]
        runtime, capture = self._build_runtime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5", serial_number="abc123", location="usb-1")],
            list_ports=lambda: ports,
            session_factory=FakeSession,
            text_log_reader_factory=FakeTextLogReader,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.attached)
        runtime.tick()

        self.assertEqual(runtime.state.receiver_debug_port, "COM6")
        self.assertIn(("receiver", "receiver_debug_attach_started", None, None, None), capture.lifecycle_events)
        self.assertIn(("receiver", "receiver_debug_attached", None, None, "COM6"), capture.lifecycle_events)

    def test_receiver_debug_attach_skip_is_logged_when_sibling_is_ambiguous(self) -> None:
        clock = FakeClock()
        ports = [
            SerialPortInfo(device="COM5", vid=0x2FE3, pid=0x0012, serial_number="abc123", location="usb-1"),
            SerialPortInfo(device="COM6", vid=0x2FE3, pid=0x0012, serial_number="abc123", location="usb-1"),
            SerialPortInfo(device="COM7", vid=0x2FE3, pid=0x0012, serial_number="abc123", location="usb-1"),
        ]
        runtime, capture = self._build_runtime(
            discover_ports=lambda *_args, **_kwargs: [make_candidate("COM5", serial_number="abc123", location="usb-1")],
            list_ports=lambda: ports,
            session_factory=FakeSession,
            text_log_reader_factory=FakeTextLogReader,
            time_fn=clock,
        )

        self._wait_until(runtime, lambda: runtime.state.attached)
        runtime.tick()

        self.assertIsNone(runtime.state.receiver_debug_port)
        skip_events = [event for event in capture.lifecycle_events if event[1] == "receiver_debug_attach_skipped"]
        self.assertEqual(len(skip_events), 1)
        self.assertIn("multiple receiver debug sibling ports", skip_events[0][3] or "")

    def test_manual_keyboard_log_attach_updates_state_and_records_lifecycle(self) -> None:
        clock = FakeClock()
        keyboard_port = SerialPortInfo(
            device="COM12",
            vid=0x1209,
            pid=0x0001,
            serial_number="kbd-1",
            location="usb-9",
            description="Keyboard debug CDC",
        )
        runtime, capture = self._build_runtime(
            discover_ports=lambda *_args, **_kwargs: [],
            list_ports=lambda: [keyboard_port],
            session_factory=FakeSession,
            text_log_reader_factory=FakeTextLogReader,
            time_fn=clock,
        )

        attached = runtime.attach_keyboard_log("COM12")

        self.assertTrue(attached)
        self.assertEqual(runtime.state.keyboard_log_port, "COM12")
        self.assertEqual(runtime.state.preferred_keyboard_serial_number, "kbd-1")
        self.assertIn(("keyboard", "keyboard_log_attach_started", None, None, "COM12"), capture.lifecycle_events)
        self.assertIn(("keyboard", "keyboard_log_attached", None, None, "COM12"), capture.lifecycle_events)


if __name__ == "__main__":
    unittest.main()
