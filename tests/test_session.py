from __future__ import annotations

import time
import unittest

from zmk_usb_bridge_gui.session import SerialSession, SessionDisconnectedEvent


class ExplodingSerial:
    def __init__(self, **_kwargs) -> None:
        self.closed = False

    def readline(self) -> bytes:
        raise RuntimeError("boom")

    def close(self) -> None:
        self.closed = True


class SessionTests(unittest.TestCase):
    def test_reader_emits_single_disconnect_event_on_failure(self) -> None:
        session = SerialSession(serial_factory=ExplodingSerial, timeout_s=0.01)
        session.open("COM5")
        time.sleep(0.05)
        events = session.drain_events()
        session.close()

        disconnect_events = [event for event in events if isinstance(event, SessionDisconnectedEvent)]
        self.assertEqual(len(disconnect_events), 1)


if __name__ == "__main__":
    unittest.main()
