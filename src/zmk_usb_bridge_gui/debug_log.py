from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from json import dumps
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from .protocol import Message
from .serial_discovery import SerialPortInfo

SCHEMA_VERSION = 1
DEFAULT_LOG_DIR = Path("logs") / "sessions"
_STOP_WRITER = object()


def _load_serial() -> type:
    try:
        from serial import Serial
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without pyserial.
        raise RuntimeError("pyserial is required for debug log capture") from exc
    return Serial


def _session_id_now(now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    suffix = uuid4().hex[:4]
    return f"{current.strftime('%Y%m%d_%H%M%S')}_{suffix}"


def _relative_log_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _port_identity_matches(
    port: SerialPortInfo,
    *,
    serial_number: str | None,
    device_path: str | None,
) -> bool:
    if serial_number:
        return port.serial_number == serial_number
    if device_path:
        return port.location == device_path or port.device == device_path
    return False


def select_receiver_debug_port(
    *,
    ports: list[SerialPortInfo],
    gui_port: str,
    vid_pid_allowlist: tuple[tuple[int, int], ...],
    serial_number: str | None,
    device_path: str | None,
) -> tuple[SerialPortInfo | None, str | None]:
    if not serial_number and not device_path:
        return None, "receiver identity is unavailable for debug attach"

    siblings: list[SerialPortInfo] = []
    for port in ports:
        if port.device == gui_port:
            continue
        if vid_pid_allowlist and (port.vid, port.pid) not in vid_pid_allowlist:
            continue
        if _port_identity_matches(port, serial_number=serial_number, device_path=device_path):
            siblings.append(port)

    if len(siblings) == 1:
        return siblings[0], None
    if not siblings:
        return None, "no receiver debug sibling port matched the attached receiver"
    return None, "multiple receiver debug sibling ports matched the attached receiver"


def format_serial_port_label(port: SerialPortInfo) -> str:
    vid_pid = "unknown"
    if port.vid is not None and port.pid is not None:
        vid_pid = f"{port.vid:04x}:{port.pid:04x}"
    pieces = [port.device, f"vid/pid={vid_pid}"]
    if port.description:
        pieces.append(port.description)
    if port.serial_number:
        pieces.append(f"serial={port.serial_number}")
    elif port.location:
        pieces.append(f"path={port.location}")
    return " | ".join(pieces)


class LogFileWriter:
    def __init__(
        self,
        path: Path,
        *,
        wall_now_fn: Callable[[], datetime] | None = None,
        monotonic_fn: Callable[[], float] = monotonic,
        on_failure: Callable[[str], None] | None = None,
    ) -> None:
        self._path = path
        self._wall_now_fn = wall_now_fn or (lambda: datetime.now().astimezone())
        self._monotonic_fn = monotonic_fn
        self._on_failure = on_failure
        self._queue: SimpleQueue[dict[str, Any] | object] = SimpleQueue()
        self._thread: Thread | None = None
        self._handle = None
        self._sequence = 0
        self._failed = False

    def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("a", encoding="utf-8", newline="\n")
        self._thread = Thread(target=self._writer_loop, name="debug-log-writer", daemon=True)
        self._thread.start()

    def enqueue(self, record: dict[str, Any]) -> None:
        if self._failed:
            return
        self._queue.put(record)

    def stop(self) -> None:
        self._queue.put(_STOP_WRITER)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._thread = None

    def _writer_loop(self) -> None:
        try:
            while True:
                item = self._queue.get()
                if item is _STOP_WRITER:
                    break
                record = dict(item)
                self._sequence += 1
                record["sequence"] = self._sequence
                handle = self._handle
                if handle is None:
                    break
                handle.write(dumps(record, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
                handle.flush()
        except Exception as exc:  # pragma: no cover - depends on filesystem failure.
            self._failed = True
            if self._on_failure is not None:
                self._on_failure(f"Debug log writer failed: {exc}")
        finally:
            if self._handle is not None:
                try:
                    self._handle.flush()
                except Exception:
                    pass
                try:
                    self._handle.close()
                except Exception:
                    pass
                self._handle = None


class LogCaptureCoordinator:
    def __init__(
        self,
        *,
        log_dir: Path | None = None,
        wall_now_fn: Callable[[], datetime] | None = None,
        monotonic_fn: Callable[[], float] = monotonic,
    ) -> None:
        self._log_dir = log_dir or DEFAULT_LOG_DIR
        self._wall_now_fn = wall_now_fn or (lambda: datetime.now().astimezone())
        self._monotonic_fn = monotonic_fn
        self._writer: LogFileWriter | None = None
        self._errors: SimpleQueue[str] = SimpleQueue()
        self._active = False
        self.session_id: str | None = None
        self.log_path: str | None = None

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> None:
        if self.session_id is not None:
            return
        session_id = _session_id_now(self._wall_now_fn())
        absolute_path = self._log_dir / f"{session_id}.jsonl"
        writer = LogFileWriter(
            absolute_path,
            wall_now_fn=self._wall_now_fn,
            monotonic_fn=self._monotonic_fn,
            on_failure=self._record_writer_error,
        )
        try:
            writer.start()
        except Exception as exc:  # pragma: no cover - depends on filesystem failure.
            self._errors.put(f"Could not start debug capture session: {exc}")
            self.session_id = session_id
            self.log_path = _relative_log_path(absolute_path)
            self._active = False
            return

        self._writer = writer
        self.session_id = session_id
        self.log_path = _relative_log_path(absolute_path)
        self._active = True
        self.record_capture_lifecycle(
            source="gui",
            event="session_started",
            fields={"log_path": self.log_path},
        )

    def stop(self) -> None:
        if self._writer is None:
            return
        if self._active:
            self.record_capture_lifecycle(source="gui", event="session_stopped")
        writer = self._writer
        self._writer = None
        self._active = False
        writer.stop()

    def drain_errors(self) -> list[str]:
        errors: list[str] = []
        while True:
            try:
                errors.append(self._errors.get_nowait())
            except Empty:
                return errors

    def record_app_event(
        self,
        event: str,
        *,
        kind: str,
        fields: dict[str, Any] | None = None,
        detail: str | None = None,
    ) -> None:
        self._emit(
            source="gui",
            channel="app_event",
            kind=kind,
            event=event,
            fields=fields,
            detail=detail,
        )

    def record_capture_lifecycle(
        self,
        *,
        source: str,
        event: str,
        fields: dict[str, Any] | None = None,
        port: str | None = None,
        device_path: str | None = None,
        serial_number: str | None = None,
        detail: str | None = None,
    ) -> None:
        self._emit(
            source=source,
            channel="capture_lifecycle",
            kind="lifecycle",
            event=event,
            fields=fields,
            port=port,
            device_path=device_path,
            serial_number=serial_number,
            detail=detail,
        )

    def record_protocol(
        self,
        *,
        direction: str,
        raw: str,
        parsed: dict[str, Any] | None,
        detail: str | None = None,
        port: str | None = None,
    ) -> None:
        self._emit(
            source="receiver",
            channel=f"gui_protocol_{direction}",
            kind="protocol" if detail is None else "error",
            direction=direction,
            raw=raw,
            parsed=parsed,
            detail=detail,
            event="protocol_parse_error" if detail is not None else None,
            port=port,
        )

    def record_debug_text(
        self,
        *,
        source: str,
        raw: str,
        port_info: SerialPortInfo,
    ) -> None:
        self._emit(
            source=source,
            channel="debug_serial",
            kind="text",
            raw=raw,
            port=port_info.device,
            device_path=port_info.location or port_info.device,
            serial_number=port_info.serial_number,
        )

    def record_reader_failure(
        self,
        *,
        source: str,
        reason: str,
        port_info: SerialPortInfo | None = None,
        exception_class: str | None = None,
    ) -> None:
        fields = {"reason": reason}
        if exception_class is not None:
            fields["exception_class"] = exception_class
        self._emit(
            source=source,
            channel="debug_serial",
            kind="error",
            event="reader_failure",
            fields=fields,
            detail=reason,
            port=port_info.device if port_info is not None else None,
            device_path=(port_info.location or port_info.device) if port_info is not None else None,
            serial_number=port_info.serial_number if port_info is not None else None,
        )

    def _emit(
        self,
        *,
        source: str,
        channel: str,
        kind: str,
        event: str | None = None,
        fields: dict[str, Any] | None = None,
        detail: str | None = None,
        raw: str | None = None,
        parsed: dict[str, Any] | None = None,
        direction: str | None = None,
        port: str | None = None,
        device_path: str | None = None,
        serial_number: str | None = None,
    ) -> None:
        writer = self._writer
        if not self._active or writer is None or self.session_id is None:
            return
        wall_now = self._wall_now_fn()
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "ts_wall": wall_now.isoformat(timespec="milliseconds"),
            "ts_mono_ms": int(self._monotonic_fn() * 1000),
            "source": source,
            "channel": channel,
            "kind": kind,
        }
        if event is not None:
            record["event"] = event
        if fields is not None:
            record["fields"] = fields
        if detail is not None:
            record["detail"] = detail
        if raw is not None:
            record["raw"] = raw
        if parsed is not None:
            record["parsed"] = parsed
        if direction is not None:
            record["direction"] = direction
        if port is not None:
            record["port"] = port
        if device_path is not None:
            record["device_path"] = device_path
        if serial_number is not None:
            record["serial_number"] = serial_number
        writer.enqueue(record)

    def _record_writer_error(self, detail: str) -> None:
        self._active = False
        self._errors.put(detail)


class GuiAppEventEmitter:
    def __init__(self, capture: LogCaptureCoordinator) -> None:
        self._capture = capture
        self._last_state_signature: dict[str, str] = {}

    def emit(
        self,
        event: str,
        *,
        kind: str,
        fields: dict[str, Any] | None = None,
        detail: str | None = None,
    ) -> None:
        if kind == "state":
            signature = dumps(
                {
                    "fields": fields,
                    "detail": detail,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if self._last_state_signature.get(event) == signature:
                return
            self._last_state_signature[event] = signature
        self._capture.record_app_event(event, kind=kind, fields=fields, detail=detail)


class ReceiverProtocolTap:
    def __init__(self, capture: LogCaptureCoordinator, *, port_fn: Callable[[], str | None]) -> None:
        self._capture = capture
        self._port_fn = port_fn

    def __call__(
        self,
        *,
        direction: str,
        raw: str,
        message: Message | None,
        detail: str | None = None,
    ) -> None:
        parsed = message.to_dict() if message is not None else None
        self._capture.record_protocol(
            direction=direction,
            raw=raw,
            parsed=parsed,
            detail=detail,
            port=self._port_fn(),
        )


class SerialTextLogOpenError(RuntimeError):
    """Raised when a debug serial log reader cannot be started."""


class SerialTextLogReader:
    def __init__(
        self,
        *,
        port_info: SerialPortInfo,
        on_line: Callable[[str, SerialPortInfo], None],
        on_failure: Callable[[str, str | None, SerialPortInfo], None],
        serial_factory: Callable[..., object] | None = None,
        baudrate: int = 115200,
        timeout_s: float = 0.2,
    ) -> None:
        self.port_info = port_info
        self._on_line = on_line
        self._on_failure = on_failure
        self._serial_factory = serial_factory or _load_serial()
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._stop_event = Event()
        self._serial = None
        self._thread: Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._serial is not None

    def start(self) -> None:
        try:
            serial_port = self._serial_factory(
                port=self.port_info.device,
                baudrate=self._baudrate,
                timeout=self._timeout_s,
                write_timeout=self._timeout_s,
            )
        except Exception as exc:  # pragma: no cover - depends on OS serial stack.
            raise SerialTextLogOpenError(
                f"Could not open debug log port {self.port_info.device}: {exc}"
            ) from exc

        self._serial = serial_port
        self._stop_event.clear()
        self._thread = Thread(target=self._reader_loop, name=f"debug-log-{self.port_info.device}", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()
        serial_port = self._serial
        self._serial = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)

    def _reader_loop(self) -> None:
        serial_port = self._serial
        if serial_port is None:
            return
        try:
            while not self._stop_event.is_set():
                raw_line = serial_port.readline()
                if not raw_line:
                    continue
                decoded = raw_line.decode("utf-8", errors="replace")
                if not decoded.strip():
                    continue
                self._on_line(decoded.rstrip("\r\n"), self.port_info)
        except Exception as exc:  # pragma: no cover - depends on OS serial stack.
            if not self._stop_event.is_set():
                self._on_failure(
                    f"Debug log reader failed on {self.port_info.device}: {exc}",
                    exc.__class__.__name__,
                    self.port_info,
                )
