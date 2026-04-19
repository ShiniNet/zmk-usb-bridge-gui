from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, SimpleQueue
from threading import Event, Thread, current_thread
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
SessionLifecycleTap = Callable[[str, dict[str, object] | None, str | None], None]


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
        lifecycle_tap: SessionLifecycleTap | None = None,
    ) -> None:
        self._serial_factory = serial_factory or _load_serial()
        self._timeout_s = timeout_s
        self._protocol_tap = protocol_tap
        self._lifecycle_tap = lifecycle_tap
        self._events: SimpleQueue[SessionEvent] = SimpleQueue()
        self._write_queue: SimpleQueue[bytes | None] = SimpleQueue()
        self._stop_event = Event()
        self._reader_thread: Thread | None = None
        self._writer_thread: Thread | None = None
        self._serial = None
        self.device: str | None = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None

    def set_protocol_tap(self, protocol_tap: SessionProtocolTap | None) -> None:
        self._protocol_tap = protocol_tap

    def set_lifecycle_tap(self, lifecycle_tap: SessionLifecycleTap | None) -> None:
        self._lifecycle_tap = lifecycle_tap

    def open(self, device: str, *, baudrate: int = 115200) -> None:
        self.close()
        self._write_queue = SimpleQueue()
        try:
            serial_port = self._serial_factory(
                port=device,
                baudrate=baudrate,
                timeout=self._timeout_s,
                write_timeout=self._timeout_s,
            )
        except Exception as exc:  # pragma: no cover - depends on OS serial stack.
            raise SessionOpenError(f"Could not open receiver port {device}: {exc}") from exc
        self._activate_serial_port(device, serial_port, prepare_port=True)

    def attach_open_port(self, device: str, serial_port: object) -> None:
        self._emit_lifecycle("session_attach_open_port_started", {"device": device})
        self._emit_lifecycle("session_attach_open_port_close_started", {"device": device})
        self.close()
        self._emit_lifecycle("session_attach_open_port_close_finished", {"device": device})
        self._write_queue = SimpleQueue()
        self._activate_serial_port(device, serial_port, prepare_port=False)
        self._emit_lifecycle("session_attach_open_port_finished", {"device": device})

    def _activate_serial_port(self, device: str, serial_port: object, *, prepare_port: bool) -> None:
        self._emit_lifecycle(
            "session_activate_serial_started",
            {"device": device, "prepare_port": prepare_port},
        )
        self._prepare_serial_port(serial_port, prepare_port=prepare_port)
        self._emit_lifecycle(
            "session_prepare_serial_finished",
            {"device": device, "prepare_port": prepare_port},
        )
        self.device = device
        self._serial = serial_port
        self._stop_event.clear()
        self._reader_thread = Thread(target=self._reader_loop, name="receiver-session-reader", daemon=True)
        self._writer_thread = Thread(target=self._writer_loop, name="receiver-session-writer", daemon=True)
        self._emit_lifecycle("session_reader_thread_starting", {"device": device})
        self._reader_thread.start()
        self._emit_lifecycle("session_reader_thread_started", {"device": device})
        self._emit_lifecycle("session_writer_thread_starting", {"device": device})
        self._writer_thread.start()
        self._emit_lifecycle("session_writer_thread_started", {"device": device})

    def _prepare_serial_port(self, serial_port: object, *, prepare_port: bool) -> None:
        if not prepare_port:
            return

        for attribute_name in ("timeout", "write_timeout"):
            if not hasattr(serial_port, attribute_name):
                continue
            try:
                setattr(serial_port, attribute_name, self._timeout_s)
            except Exception:
                pass

        if hasattr(serial_port, "reset_input_buffer"):
            try:
                serial_port.reset_input_buffer()
            except Exception:
                pass

        if hasattr(serial_port, "reset_output_buffer"):
            try:
                serial_port.reset_output_buffer()
            except Exception:
                pass

        if hasattr(serial_port, "dtr"):
            try:
                # Firmware gates the GUI channel on DTR, so assert it before the reader starts.
                serial_port.dtr = True
            except Exception:
                pass

    def _emit_lifecycle(
        self,
        event: str,
        fields: dict[str, object] | None = None,
        detail: str | None = None,
    ) -> None:
        if self._lifecycle_tap is None:
            return
        self._lifecycle_tap(event, fields, detail)

    def close(self) -> None:
        self._stop_event.set()
        reader_thread = self._reader_thread
        self._reader_thread = None
        writer_thread = self._writer_thread
        self._writer_thread = None
        self._write_queue.put(None)
        serial_port = self._serial
        self._serial = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
        active_thread = current_thread()
        if reader_thread is not None and reader_thread.is_alive() and reader_thread is not active_thread:
            reader_thread.join(timeout=0.5)
        if writer_thread is not None and writer_thread.is_alive() and writer_thread is not active_thread:
            writer_thread.join(timeout=0.5)
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
        if self._stop_event.is_set():
            raise SessionOpenError("Receiver session is not open")
        self._write_queue.put(payload)

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
        pending_text = ""
        try:
            while not self._stop_event.is_set():
                raw_line = serial_port.readline()
                if not raw_line:
                    continue
                pending_text += raw_line.decode("utf-8", errors="replace")
                while True:
                    newline_index = pending_text.find("\n")
                    if newline_index < 0:
                        break
                    decoded = pending_text[: newline_index + 1]
                    pending_text = pending_text[newline_index + 1 :]
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
                self._stop_event.set()
                disconnected_emitted = True
                self._events.put(SessionDisconnectedEvent(f"Receiver port disconnected: {exc}"))
        finally:
            if not self._stop_event.is_set() and not disconnected_emitted:
                self._events.put(SessionDisconnectedEvent("Receiver port disconnected"))

    def _writer_loop(self) -> None:
        serial_port = self._serial
        if serial_port is None:
            return

        while not self._stop_event.is_set():
            try:
                payload = self._write_queue.get(timeout=0.1)
            except Empty:
                continue

            if payload is None:
                return

            try:
                # pyserial flush() can block badly on some CDC ACM ports; write() is enough
                # for these short line-delimited commands.
                serial_port.write(payload)
            except Exception as exc:  # pragma: no cover - depends on OS serial stack.
                if not self._stop_event.is_set():
                    self._stop_event.set()
                    self._events.put(SessionDisconnectedEvent(f"Receiver port write failed: {exc}"))
                return
