from __future__ import annotations

import time
import unittest
from threading import Event

from zmk_usb_bridge_gui.serial_discovery import (
    DiscoveryConfig,
    diagnose_gui_port_via_receiver_log,
    GuiProtocolProbeResult,
    HelloMessage,
    ReceiverPortCandidate,
    SerialPortInfo,
    discover_receiver_ports,
    probe_gui_hello,
    probe_gui_protocol,
)


class FakeSerial:
    lines: list[bytes] = []
    on_write_lines: list[bytes] = []
    on_dtr_lines: list[bytes] = []
    writes: list[bytes] = []
    flush_called = False

    def __init__(self, **_kwargs) -> None:
        self._lines = list(type(self).lines)
        type(self).writes = []
        type(self).flush_called = False
        self._dtr = False

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        self._dtr = value
        if value:
            self._lines.extend(type(self).on_dtr_lines)

    def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)

    def write(self, payload: bytes) -> int:
        type(self).writes.append(payload)
        self._lines.extend(type(self).on_write_lines)
        return len(payload)

    def flush(self) -> None:
        type(self).flush_called = True
        return None

    def reset_input_buffer(self) -> None:
        return None

    def close(self) -> None:
        return None


class CloseBlockingSerial(FakeSerial):
    release_close = Event()

    def close(self) -> None:
        type(self).release_close.wait(timeout=1.0)


class DiagnosticSerial:
    instances: dict[str, "DiagnosticSerial"] = {}
    gui_to_log_ready: dict[str, str] = {}

    def __init__(self, *, port: str, **_kwargs) -> None:
        self.port = port
        self._dtr = False
        self._lines: list[bytes] = []
        type(self).instances[port] = self

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        self._dtr = value
        if value:
            self._emit_ready_line_if_pair_is_active()

    def _emit_ready_line_if_pair_is_active(self) -> None:
        for gui_device, log_device in type(self).gui_to_log_ready.items():
            gui_serial = type(self).instances.get(gui_device)
            log_serial = type(self).instances.get(log_device)
            if gui_serial is None or log_serial is None:
                continue
            if gui_serial._dtr and log_serial._dtr:
                log_serial._lines.append(b"[00:00:00.000] gui channel ready\n")

    def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)

    def reset_input_buffer(self) -> None:
        return None

    def close(self) -> None:
        type(self).instances.pop(self.port, None)


class BlockingDiagnosticSerial(DiagnosticSerial):
    release_close = Event()

    def close(self) -> None:
        type(self).release_close.wait(timeout=1.0)
        super().close()


class HangingDiagnosticSerial(DiagnosticSerial):
    release_read = Event()

    def readline(self) -> bytes:
        type(self).release_read.wait(timeout=1.0)
        return b""


class SerialDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeSerial.lines = []
        FakeSerial.on_write_lines = []
        FakeSerial.on_dtr_lines = []
        FakeSerial.writes = []
        CloseBlockingSerial.lines = []
        CloseBlockingSerial.on_write_lines = []
        CloseBlockingSerial.on_dtr_lines = []
        CloseBlockingSerial.writes = []
        CloseBlockingSerial.release_close.set()
        DiagnosticSerial.instances = {}
        DiagnosticSerial.gui_to_log_ready = {}
        BlockingDiagnosticSerial.instances = {}
        BlockingDiagnosticSerial.gui_to_log_ready = {}
        BlockingDiagnosticSerial.release_close.set()
        HangingDiagnosticSerial.instances = {}
        HangingDiagnosticSerial.gui_to_log_ready = {}
        HangingDiagnosticSerial.release_read.set()

    def test_probe_gui_hello_skips_non_hello_lines_until_hello_arrives(self) -> None:
        FakeSerial.lines = [
            b'{"type":"status_snapshot","receiver_state":"idle","peer_name":null,"peer_address":null,"scan_in_progress":false,"candidate_generation":0,"candidate_count":0,"battery_supported":true,"battery_percent":null,"modifiers_supported":true,"modifiers":null,"last_key_supported":true,"last_key":null,"mouse_buttons_supported":true,"mouse_buttons":null}\n',
            b'{"type":"hello","product":"zmk-usb-bridge-gui","protocol_version":1,"channel":"gui"}\n',
        ]

        hello = probe_gui_hello("COM8", timeout_s=0.05, serial_factory=FakeSerial)

        self.assertIsNotNone(hello)
        self.assertEqual(hello.product, "zmk-usb-bridge-gui")
        self.assertEqual(hello.channel, "gui")

    def test_probe_gui_hello_ignores_malformed_lines(self) -> None:
        FakeSerial.lines = [
            b"not-json\n",
            b'{"type":"hello","product":"zmk-usb-bridge-gui","protocol_version":1,"channel":"gui"}\n',
        ]

        hello = probe_gui_hello("COM8", timeout_s=0.05, serial_factory=FakeSerial)

        self.assertIsNotNone(hello)
        self.assertEqual(hello.protocol_version, 1)

    def test_probe_gui_protocol_accepts_get_status_response_without_hello(self) -> None:
        FakeSerial.on_write_lines = [
            b'{"type":"ack","request_id":0,"name":"get_status","accepted":true}\n',
            b'{"type":"status_snapshot","receiver_state":"idle","peer_name":null,"peer_address":null,"scan_in_progress":false,"candidate_generation":0,"candidate_count":0}\n',
        ]

        result = probe_gui_protocol("COM8", timeout_s=0.05, serial_factory=FakeSerial)

        self.assertTrue(result.protocol_verified)
        self.assertEqual(result.verified_via, "ack")
        self.assertIsNone(result.hello)
        self.assertTrue(FakeSerial.writes)
        self.assertFalse(FakeSerial.flush_called)

    def test_probe_gui_protocol_accepts_passive_hello_after_dtr(self) -> None:
        FakeSerial.on_dtr_lines = [
            b'{"type":"hello","product":"zmk-usb-bridge-gui","protocol_version":1,"channel":"gui"}\n',
        ]

        result = probe_gui_protocol("COM8", timeout_s=0.05, serial_factory=FakeSerial)

        self.assertTrue(result.protocol_verified)
        self.assertEqual(result.verified_via, "hello")
        self.assertIsNotNone(result.hello)
        self.assertEqual(FakeSerial.writes, [])

    def test_probe_gui_protocol_returns_promptly_when_close_blocks(self) -> None:
        CloseBlockingSerial.on_dtr_lines = [
            b'{"type":"hello","product":"zmk-usb-bridge-gui","protocol_version":1,"channel":"gui"}\n',
        ]
        CloseBlockingSerial.release_close.clear()

        started = time.monotonic()
        result = probe_gui_protocol("COM8", timeout_s=0.05, serial_factory=CloseBlockingSerial)
        elapsed = time.monotonic() - started

        CloseBlockingSerial.release_close.set()

        self.assertLess(elapsed, 0.30)
        self.assertTrue(result.protocol_verified)

    def test_discovery_skips_sibling_probe_after_protocol_is_verified(self) -> None:
        ports = [
            SerialPortInfo(device="COM7", vid=0x2FE3, pid=0x0012, serial_number="receiver-1"),
            SerialPortInfo(device="COM8", vid=0x2FE3, pid=0x0012, serial_number="receiver-1"),
        ]
        probe_calls: list[str] = []

        def fake_list_serial_ports() -> list[SerialPortInfo]:
            return ports

        def fake_probe(device: str, **_kwargs) -> GuiProtocolProbeResult:
            probe_calls.append(device)
            if device == "COM7":
                return GuiProtocolProbeResult(
                    hello=HelloMessage(),
                    protocol_verified=True,
                    verified_via="hello",
                )
            self.fail("second sibling should not be probed once the first port is verified")

        original_list_serial_ports = discover_receiver_ports.__globals__["list_serial_ports"]
        discover_receiver_ports.__globals__["list_serial_ports"] = fake_list_serial_ports
        try:
            candidates = discover_receiver_ports(
                DiscoveryConfig(vid_pid_allowlist=((0x2FE3, 0x0012),)),
                probe_hello=True,
                probe_protocol_fn=fake_probe,
            )
        finally:
            discover_receiver_ports.__globals__["list_serial_ports"] = original_list_serial_ports

        self.assertEqual(probe_calls, ["COM7"])
        self.assertEqual(len(candidates), 2)
        self.assertTrue(candidates[0].protocol_verified)

    def test_discovery_can_identify_gui_port_via_receiver_log_diagnostic(self) -> None:
        ports = [
            SerialPortInfo(device="COM7", vid=0x2FE3, pid=0x0012, serial_number="receiver-1"),
            SerialPortInfo(device="COM8", vid=0x2FE3, pid=0x0012, serial_number="receiver-1"),
        ]
        DiagnosticSerial.gui_to_log_ready = {"COM7": "COM8"}

        def fake_list_serial_ports() -> list[SerialPortInfo]:
            return ports

        def fake_probe(_device: str, **_kwargs) -> GuiProtocolProbeResult:
            return GuiProtocolProbeResult()

        original_list_serial_ports = discover_receiver_ports.__globals__["list_serial_ports"]
        discover_receiver_ports.__globals__["list_serial_ports"] = fake_list_serial_ports
        try:
            candidates = discover_receiver_ports(
                DiscoveryConfig(vid_pid_allowlist=((0x2FE3, 0x0012),)),
                probe_hello=True,
                probe_protocol_fn=fake_probe,
                diagnostic_serial_factory=DiagnosticSerial,
            )
        finally:
            discover_receiver_ports.__globals__["list_serial_ports"] = original_list_serial_ports

        self.assertEqual(candidates[0].port.device, "COM7")
        self.assertTrue(candidates[0].protocol_verified)
        self.assertEqual(candidates[0].protocol_verified_via, "gui_ready_diagnostic")

    def test_gui_ready_diagnostic_returns_timeout_result_promptly(self) -> None:
        HangingDiagnosticSerial.release_read.clear()

        started = time.monotonic()
        result = diagnose_gui_port_via_receiver_log(
            "COM8",
            "COM7",
            timeout_s=0.05,
            serial_factory=HangingDiagnosticSerial,
        )
        elapsed = time.monotonic() - started

        HangingDiagnosticSerial.release_read.set()

        self.assertLess(elapsed, 0.30)
        self.assertFalse(result.observed)
        self.assertFalse(result.completed)
        self.assertEqual(result.detail, "diagnostic timed out")


if __name__ == "__main__":
    unittest.main()
