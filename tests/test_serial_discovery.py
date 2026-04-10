from __future__ import annotations

import unittest

from zmk_usb_bridge_gui.serial_discovery import (
    DiscoveryConfig,
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
    writes: list[bytes] = []

    def __init__(self, **_kwargs) -> None:
        self._lines = list(type(self).lines)
        type(self).writes = []
        self.dtr = False

    def __enter__(self) -> "FakeSerial":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)

    def write(self, payload: bytes) -> int:
        type(self).writes.append(payload)
        self._lines.extend(type(self).on_write_lines)
        return len(payload)

    def flush(self) -> None:
        return None

    def reset_input_buffer(self) -> None:
        return None


class SerialDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeSerial.lines = []
        FakeSerial.on_write_lines = []
        FakeSerial.writes = []

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


if __name__ == "__main__":
    unittest.main()
