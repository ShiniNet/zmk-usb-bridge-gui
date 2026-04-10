from __future__ import annotations

import unittest

from zmk_usb_bridge_gui.protocol import (
    Candidate,
    CandidateSnapshot,
    HelloMessage,
    ProtocolParseError,
    parse_message_line,
    serialize_message_line,
)


class ProtocolTests(unittest.TestCase):
    def test_hello_roundtrip(self) -> None:
        line = serialize_message_line(HelloMessage(board="xiao_nrf52840", firmware_version="0.1.0"))
        parsed = parse_message_line(line)
        self.assertIsInstance(parsed, HelloMessage)
        self.assertEqual(parsed.channel, "gui")
        self.assertEqual(parsed.board, "xiao_nrf52840")

    def test_candidate_snapshot_roundtrip(self) -> None:
        snapshot = CandidateSnapshot(
            candidate_generation=7,
            candidates=[
                Candidate(
                    candidate_id=3,
                    ble_address="E4:B6:69:12:34:56",
                    display_name="LaLapadGen2",
                    connectable=True,
                    has_hid_service=True,
                    has_keyboard_appearance=True,
                    rssi=-49,
                    last_seen_ms=1234,
                )
            ],
        )
        parsed = parse_message_line(serialize_message_line(snapshot))
        self.assertIsInstance(parsed, CandidateSnapshot)
        self.assertEqual(parsed.candidate_generation, 7)
        self.assertEqual(parsed.candidates[0].display_name, "LaLapadGen2")
        self.assertEqual(parsed.candidates[0].last_seen_ms, 1234)

    def test_invalid_json_raises_protocol_error(self) -> None:
        with self.assertRaises(ProtocolParseError) as context:
            parse_message_line("{not json}\n")
        self.assertIn("invalid JSON payload", str(context.exception))


if __name__ == "__main__":
    unittest.main()
