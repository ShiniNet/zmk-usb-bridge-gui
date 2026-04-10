from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, SimpleQueue
from threading import Event, Lock, Thread
from typing import Callable

from .protocol import Message, ProtocolParseError, parse_message_line, serialize_message_line


class SessionOpenError(RuntimeError):
    """Raised when a serial session cannot be opened."""


@dataclass(slots=True)
class SessionMessageEvent:
    message: Message


@dataclass(slots=True)
class SessionProtocolErrorEvent:
    detail: str
    raw: str | None = None


@dataclass(slots=True)
class SessionDisconnectedEvent:
    detail: str


SessionEvent = SessionMessageEvent | SessionProtocolErrorEvent | SessionDisconnectedEvent
SessionProtocolTap = Callable[[str, str, Message | None, str | None], None]


def _load_serial() -> type:
    try:
        from serial import Serial
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without pyserial.
        raise SessionOpenError("pyserial is required for the receiver session") from exc
    return Serial


class SerialSession:
    def __init__(
        self,
        *,
        serial_factory: Callable[..., object] | None = None,
        timeout_s: float = 0.2,
        protocol_tap: SessionProtocolTap | None = None,
    ) -> None:
        self._serial_factory = serial_factory or _load_serial()
        self._timeout_s = timeout_s
        self._protocol_tap = protocol_tap
        self._events: SimpleQueue[SessionEvent] = SimpleQueue()
        self._stop_event = Event()
        self._write_lock = Lock()
        self._reader_thread: Thread | None = None
        self._serial = None
        self.device: str | None = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None

    def set_protocol_tap(self, protocol_tap: SessionProtocolTap | None) -> None:
        self._protocol_tap = protocol_tap

    def open(self, device: str, *, baudrate: int = 115200) -> None:
        self.close()
        try:
            serial_port = self._serial_factory(
                port=device,
                baudrate=baudrate,
                timeout=self._timeout_s,
                write_timeout=self._timeout_s,
            )
        except Exception as exc:  # pragma: no cover - depends on OS serial stack.
            raise SessionOpenError(f"Could not open receiver port {device}: {exc}") from exc
        self.device = device
        self._serial = serial_port
        self._stop_event.clear()
        self._reader_thread = Thread(target=self._reader_loop, name="receiver-session-reader", daemon=True)
        self._reader_thread.start()

    def close(self) -> None:
        self._stop_event.set()
        reader_thread = self._reader_thread
        self._reader_thread = None
        serial_port = self._serial
        self._serial = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
        if reader_thread is not None and reader_thread.is_alive():
            reader_thread.join(timeout=0.5)
        self.device = None

    def send_message(self, message: Message) -> None:
        serial_port = self._serial
        if serial_port is None:
            raise SessionOpenError("Receiver session is not open")
        payload_text = serialize_message_line(message)
        protocol_tap = self._protocol_tap
        if protocol_tap is not None:
            protocol_tap("tx", payload_text, message, None)
        payload = payload_text.encode("utf-8")
        try:
            with self._write_lock:
                serial_port.write(payload)
                if hasattr(serial_port, "flush"):
                    serial_port.flush()
        except Exception as exc:  # pragma: no cover - depends on OS serial stack.
            self._events.put(SessionDisconnectedEvent(f"Receiver port write failed: {exc}"))
            self.close()
            raise SessionOpenError(f"Receiver port write failed: {exc}") from exc

    def drain_events(self) -> list[SessionEvent]:
        events: list[SessionEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events

    def _reader_loop(self) -> None:
        serial_port = self._serial
        if serial_port is None:
            return
        disconnected_emitted = False
        try:
            while not self._stop_event.is_set():
                raw_line = serial_port.readline()
                if not raw_line:
                    continue
                decoded = raw_line.decode("utf-8", errors="replace")
                try:
                    message = parse_message_line(decoded)
                except ProtocolParseError as exc:
                    if self._protocol_tap is not None:
                        self._protocol_tap("rx", decoded, None, str(exc))
                    self._events.put(SessionProtocolErrorEvent(str(exc), raw=decoded))
                    continue
                if self._protocol_tap is not None:
                    self._protocol_tap("rx", decoded, message, None)
                self._events.put(SessionMessageEvent(message))
        except Exception as exc:  # pragma: no cover - depends on OS serial stack.
            if not self._stop_event.is_set():
                disconnected_emitted = True
                self._events.put(SessionDisconnectedEvent(f"Receiver port disconnected: {exc}"))
        finally:
            if not self._stop_event.is_set() and not disconnected_emitted:
                self._events.put(SessionDisconnectedEvent("Receiver port disconnected"))
