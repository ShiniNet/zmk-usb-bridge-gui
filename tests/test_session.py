from __future__ import annotations

import time
import unittest
from threading import Event

from zmk_usb_bridge_gui.protocol import CommandMessage
from zmk_usb_bridge_gui.session import (
    SerialSession,
    SessionDisconnectedEvent,
    SessionMessageEvent,
    SessionProtocolErrorEvent,
)


class ExplodingSerial:
    def __init__(self, **_kwargs) -> None:
        self.closed = False

    def readline(self) -> bytes:
        raise RuntimeError("boom")

    def close(self) -> None:
        self.closed = True


class BlockingWriteSerial:
    release_write = Event()
    write_started = Event()
    writes: list[bytes] = []

    def __init__(self, **_kwargs) -> None:
        self.closed = False

    def readline(self) -> bytes:
        time.sleep(0.01)
        return b""

    def write(self, payload: bytes) -> int:
        type(self).write_started.set()
        type(self).release_write.wait(timeout=1.0)
        type(self).writes.append(payload)
        return len(payload)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True
        type(self).release_write.set()


class DtrTrackingSerial:
    def __init__(self, **_kwargs) -> None:
        self.closed = False
        self.dtr = False
        self.timeout = None
        self.write_timeout = None
        self.reset_input_buffer_called = False
        self.reset_output_buffer_called = False

    def readline(self) -> bytes:
        time.sleep(0.01)
        return b""

    def reset_input_buffer(self) -> None:
        self.reset_input_buffer_called = True

    def reset_output_buffer(self) -> None:
        self.reset_output_buffer_called = True

    def close(self) -> None:
        self.closed = True


class PreopenedSerial(DtrTrackingSerial):
    pass


class ChunkedLineSerial:
    def __init__(self, **_kwargs) -> None:
        self.closed = False
        self._reads = [
            b'{"type":"hello","product":"zmk-usb-bridge-',
            b'gui","protocol_version":1,"channel":"gui"}\n',
        ]

    def readline(self) -> bytes:
        if not self._reads:
            time.sleep(0.01)
            return b""
        return self._reads.pop(0)

    def close(self) -> None:
        self.closed = True


class SessionTests(unittest.TestCase):
    def test_open_asserts_dtr_and_resets_input_buffer(self) -> None:
        serial_instances: list[DtrTrackingSerial] = []

        def serial_factory(**kwargs) -> DtrTrackingSerial:
            serial_port = DtrTrackingSerial(**kwargs)
            serial_instances.append(serial_port)
            return serial_port

        session = SerialSession(serial_factory=serial_factory, timeout_s=0.01)
        session.open("COM5")
        time.sleep(0.02)
        session.close()

        self.assertEqual(len(serial_instances), 1)
        self.assertTrue(serial_instances[0].dtr)
        self.assertTrue(serial_instances[0].reset_input_buffer_called)
        self.assertTrue(serial_instances[0].reset_output_buffer_called)
        self.assertEqual(serial_instances[0].timeout, 0.01)
        self.assertEqual(serial_instances[0].write_timeout, 0.01)

    def test_reader_emits_single_disconnect_event_on_failure(self) -> None:
        session = SerialSession(serial_factory=ExplodingSerial, timeout_s=0.01)
        session.open("COM5")
        time.sleep(0.05)
        events = session.drain_events()
        session.close()

        disconnect_events = [event for event in events if isinstance(event, SessionDisconnectedEvent)]
        self.assertEqual(len(disconnect_events), 1)

    def test_send_message_returns_without_waiting_for_serial_write(self) -> None:
        BlockingWriteSerial.release_write.clear()
        BlockingWriteSerial.write_started.clear()
        BlockingWriteSerial.writes.clear()

        session = SerialSession(serial_factory=BlockingWriteSerial, timeout_s=0.01)
        session.open("COM5")

        started = time.monotonic()
        session.send_message(CommandMessage(request_id=1, name="get_status"))
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.05)
        self.assertTrue(BlockingWriteSerial.write_started.wait(timeout=0.2))

        BlockingWriteSerial.release_write.set()
        time.sleep(0.05)
        session.close()

        self.assertEqual(
            BlockingWriteSerial.writes,
            [b'{"type":"command","request_id":1,"name":"get_status"}\n'],
        )

    def test_attach_open_port_reprimes_existing_serial_without_toggling_dtr(self) -> None:
        serial_port = PreopenedSerial()
        serial_port.dtr = True

        session = SerialSession(timeout_s=0.01)
        session.attach_open_port("COM5", serial_port)
        time.sleep(0.02)
        session.close()

        self.assertTrue(serial_port.dtr)
        self.assertTrue(serial_port.reset_input_buffer_called)
        self.assertFalse(serial_port.reset_output_buffer_called)
        self.assertEqual(serial_port.timeout, 0.01)
        self.assertEqual(serial_port.write_timeout, 0.01)

    def test_reader_reassembles_partial_lines_before_parsing(self) -> None:
        session = SerialSession(serial_factory=ChunkedLineSerial, timeout_s=0.01)
        session.open("COM5")
        time.sleep(0.05)
        events = session.drain_events()
        session.close()

        message_events = [event for event in events if isinstance(event, SessionMessageEvent)]
        protocol_errors = [event for event in events if isinstance(event, SessionProtocolErrorEvent)]

        self.assertEqual(len(protocol_errors), 0)
        self.assertEqual(len(message_events), 1)


if __name__ == "__main__":
    unittest.main()
