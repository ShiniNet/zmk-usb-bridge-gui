from __future__ import annotations

import time
from dataclasses import replace
from queue import Empty, SimpleQueue
from threading import Thread
from typing import Callable

from .controller import AppController
from .debug_log import (
    GuiAppEventEmitter,
    LogCaptureCoordinator,
    ReceiverProtocolTap,
    SerialTextLogOpenError,
    SerialTextLogReader,
    format_serial_port_label,
    select_receiver_debug_port,
)
from .protocol import PROTOCOL_CHANNEL, PROTOCOL_PRODUCT, PROTOCOL_VERSION
from .serial_discovery import (
    DEFAULT_BAUDRATE,
    DiscoveryConfig,
    ReceiverPortCandidate,
    SerialDiscoveryError,
    SerialPortInfo,
    discover_receiver_ports,
    list_serial_ports,
)
from .session import (
    SerialSession,
    SessionDisconnectedEvent,
    SessionMessageEvent,
    SessionOpenError,
    SessionProtocolErrorEvent,
)

DEFAULT_RECEIVER_VID_PID_ALLOWLIST = ((0x2FE3, 0x0012),)
DEFAULT_RECEIVER_BOOTLOADER_VID_PID_ALLOWLIST = ((0x2886, 0x0045),)
RECEIVER_BOOTLOADER_DISCOVERY_DETAIL = (
    "Receiver appears to be in bootloader mode; flash latest zephyr.uf2."
)
OPEN_RETRYABLE_ERROR_MARKERS = (
    "permissionerror",
    "access is denied",
    "access denied",
    "resource busy",
    "device or resource busy",
    "filenotfounderror",
    "file not found",
    "指定されたファイルが見つかりません",
)
ATTACH_OPEN_RETRY_DELAY_S = 0.25
ATTACH_OPEN_RETRY_ATTEMPTS = 3
ATTACH_OPERATION_TIMEOUT_S = 3.0


class AppRuntime:
    def __init__(
        self,
        *,
        discover_ports: Callable[..., list[ReceiverPortCandidate]] = discover_receiver_ports,
        list_ports: Callable[[], list[SerialPortInfo]] = list_serial_ports,
        session_factory: Callable[[], SerialSession] = SerialSession,
        text_log_reader_factory: Callable[..., SerialTextLogReader] = SerialTextLogReader,
        capture_factory: Callable[[], LogCaptureCoordinator] | None = None,
        time_fn: Callable[[], float] = time.monotonic,
        discovery_config: DiscoveryConfig | None = None,
        scan_watchdog_timeout_s: float = 12.0,
        auto_attach_receiver_debug: bool = False,
    ) -> None:
        self._discover_ports = discover_ports
        self._list_ports = list_ports
        self._session_factory = session_factory
        self._text_log_reader_factory = text_log_reader_factory
        self._time_fn = time_fn
        self._scan_watchdog_timeout_s = scan_watchdog_timeout_s
        self._auto_attach_receiver_debug = auto_attach_receiver_debug
        self._discovery_config = discovery_config or DiscoveryConfig(
            vid_pid_allowlist=DEFAULT_RECEIVER_VID_PID_ALLOWLIST,
            baudrate=DEFAULT_BAUDRATE,
            keep_probe_port_open_on_success=True,
        )
        self._capture = capture_factory() if capture_factory is not None else LogCaptureCoordinator()
        self._capture.start()
        self._gui_event_emitter = GuiAppEventEmitter(self._capture)
        self.controller = AppController(time_fn=time_fn, app_event_sink=self._emit_app_event)
        self._session: SerialSession | None = None
        self._protocol_tap = ReceiverProtocolTap(self._capture, port_fn=lambda: self.state.receiver_port)
        self._next_discovery_at = 0.0
        self._discovery_results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._discovery_thread: Thread | None = None
        self._attach_results: SimpleQueue[tuple[str, int, object]] = SimpleQueue()
        self._attach_thread: Thread | None = None
        self._attach_attempt_token = 0
        self._active_attach_token: int | None = None
        self._active_attach_candidate: ReceiverPortCandidate | None = None
        self._active_attach_session: SerialSession | None = None
        self._attach_started_at = 0.0
        self._reader_failures: SimpleQueue[tuple[str, str, str | None, SerialPortInfo]] = SimpleQueue()
        self._receiver_debug_reader: SerialTextLogReader | None = None
        self._receiver_debug_epoch_key: tuple[str | None, str | None, str | None] | None = None
        self._receiver_debug_attach_started = False
        self._receiver_debug_skip_logged = False
        self._receiver_debug_retry_at = 0.0
        self._keyboard_debug_reader: SerialTextLogReader | None = None
        self._refresh_capture_state()

    @property
    def state(self):
        return self.controller.state

    def tick(self) -> None:
        self._drain_discovery_results()
        self._drain_attach_results()
        self._drain_session_events()
        self._drain_reader_failures()
        self._drain_capture_errors()
        self._expire_attach_timeout()

        if self.controller.expire_scan_watchdog(self._scan_watchdog_timeout_s):
            self.refresh(clear_last_error=False)

        self._sync_receiver_debug_reader()

        if self.state.attached:
            return
        if self._discovery_thread is not None:
            return
        if self._attach_thread is not None:
            return
        if self._time_fn() >= self._next_discovery_at:
            self._start_discovery()

    def shutdown(self) -> None:
        self._stop_receiver_debug_reader(emit_detached=True)
        self.detach_keyboard_log()
        session = self._session
        self._session = None
        if session is not None:
            session.close()
        self._capture.stop()

    def retry_discovery(self) -> None:
        if self.state.attached:
            return
        self._emit_app_event("retry_discovery_requested", "lifecycle", None, None)
        self._next_discovery_at = 0.0

    def refresh(self, *, clear_last_error: bool = True) -> None:
        if not self.state.can_refresh:
            return
        self._emit_app_event("refresh_requested", "lifecycle", None, None)
        if clear_last_error:
            self.controller.clear_last_error_for_user_action()
        self._send_command("get_status")
        self._send_command("get_candidates")

    def scan_start(self) -> None:
        if not self.state.can_scan:
            return
        self._emit_app_event("scan_start_requested", "lifecycle", None, None)
        self.controller.clear_last_error_for_user_action()
        self._send_command("scan_start")

    def bond_erase(self) -> None:
        if not self.state.can_bond_erase:
            return
        self._emit_app_event("bond_erase_requested", "lifecycle", None, None)
        self.controller.clear_last_error_for_user_action()
        self._send_command("bond_erase")

    def connect_selected(self) -> None:
        if not self.state.attached:
            return
        candidate = self.state.selected_candidate
        if candidate is None:
            self.controller.set_last_error("Select a candidate before connecting.")
            return
        if not self.state.can_connect_selected:
            return
        self._emit_app_event(
            "connect_candidate_requested",
            "lifecycle",
            {"candidate_id": candidate.candidate_id},
            None,
        )
        self.controller.clear_last_error_for_user_action()
        self._send_command(
            "connect_candidate",
            candidate_generation=self.state.candidate_generation,
            candidate_id=candidate.candidate_id,
        )

    def select_candidate(self, candidate_id: int | None) -> None:
        self.controller.state.selected_candidate_id = candidate_id

    def list_keyboard_log_candidates(self) -> list[SerialPortInfo]:
        try:
            ports = self._list_ports()
        except SerialDiscoveryError as exc:
            self._set_debug_capture_error(str(exc))
            return []

        excluded = {
            self.state.receiver_port,
            self.state.receiver_debug_port,
            self.state.keyboard_log_port,
        }
        return [port for port in ports if port.device not in excluded]

    def attach_keyboard_log(self, device: str) -> bool:
        if not self.state.debug_capture_active:
            self._set_debug_capture_error("Debug capture session is not active.")
            return False

        port = next((item for item in self.list_keyboard_log_candidates() if item.device == device), None)
        if port is None:
            self.note_keyboard_log_attach_skipped("selected keyboard log port is no longer available")
            return False

        self._capture.record_capture_lifecycle(
            source="keyboard",
            event="keyboard_log_attach_started",
            port=port.device,
            device_path=port.location or port.device,
            serial_number=port.serial_number,
        )
        reader = self._build_text_log_reader(source="keyboard", port_info=port)
        try:
            reader.start()
        except SerialTextLogOpenError as exc:
            self._capture.record_reader_failure(
                source="keyboard",
                reason=str(exc),
                port_info=port,
                exception_class=exc.__class__.__name__,
            )
            self._set_debug_capture_error(str(exc))
            return False

        self._stop_keyboard_debug_reader(emit_detached=True)
        self._keyboard_debug_reader = reader
        self.state.keyboard_log_port = port.device
        self.state.preferred_keyboard_serial_number = port.serial_number
        self.state.preferred_keyboard_device_path = port.location or port.device
        self._set_debug_capture_error(None)
        self._capture.record_capture_lifecycle(
            source="keyboard",
            event="keyboard_log_attached",
            port=port.device,
            device_path=port.location or port.device,
            serial_number=port.serial_number,
        )
        return True

    def detach_keyboard_log(self) -> None:
        self._stop_keyboard_debug_reader(emit_detached=True)

    def note_keyboard_log_attach_skipped(self, reason: str) -> None:
        self._capture.record_capture_lifecycle(
            source="keyboard",
            event="keyboard_log_attach_skipped",
            fields={"reason": reason},
            detail=reason,
        )
        self._set_debug_capture_error(reason)

    @staticmethod
    def format_keyboard_log_candidate(port: SerialPortInfo) -> str:
        return format_serial_port_label(port)

    def _emit_app_event(
        self,
        event: str,
        kind: str,
        fields: dict[str, object] | None,
        detail: str | None,
    ) -> None:
        self._gui_event_emitter.emit(event, kind=kind, fields=fields, detail=detail)

    def _send_command(self, name: str, **fields: object) -> None:
        session = self._session
        if session is None:
            self.controller.mark_disconnected("Receiver session is not attached")
            self._next_discovery_at = 0.0
            return
        message = self.controller.build_command(name, **fields)
        try:
            session.send_message(message)
        except SessionOpenError as exc:
            self._detach(str(exc))

    def _drain_session_events(self) -> None:
        session = self._session
        if session is None:
            return
        for event in session.drain_events():
            if isinstance(event, SessionMessageEvent):
                self.controller.apply_message(event.message)
                continue
            if isinstance(event, SessionProtocolErrorEvent):
                self.controller.handle_protocol_error(event.detail)
                continue
            if isinstance(event, SessionDisconnectedEvent):
                self._detach(event.detail)
                return

    def _drain_reader_failures(self) -> None:
        while True:
            try:
                source, detail, exception_class, port_info = self._reader_failures.get_nowait()
            except Empty:
                return

            self._capture.record_reader_failure(
                source=source,
                reason=detail,
                port_info=port_info,
                exception_class=exception_class,
            )
            self._set_debug_capture_error(detail)

            if source == "receiver":
                self._stop_receiver_debug_reader(emit_detached=True)
                self._receiver_debug_retry_at = self._time_fn() + self._discovery_config.retry_interval_s
                continue

            self._stop_keyboard_debug_reader(emit_detached=True)

    def _drain_capture_errors(self) -> None:
        errors = self._capture.drain_errors()
        if not errors:
            return
        self._refresh_capture_state()
        self._set_debug_capture_error(errors[-1])

    def _start_discovery(self) -> None:
        if self._discovery_thread is not None:
            return
        self.controller.mark_discovering()
        discovery_config = self._build_discovery_config()
        self._discovery_thread = Thread(
            target=self._discovery_worker,
            args=(discovery_config,),
            name="receiver-discovery",
            daemon=True,
        )
        self._discovery_thread.start()

    def _discovery_worker(self, discovery_config: DiscoveryConfig) -> None:
        try:
            candidates = self._discover_ports(
                discovery_config,
                probe_hello=True,
                trace_fn=lambda event, fields: self._emit_app_event(event, "lifecycle", fields, None),
            )
        except SerialDiscoveryError as exc:
            self._discovery_results.put(("error", str(exc)))
            return
        self._discovery_results.put(("candidates", (candidates, discovery_config.baudrate)))

    def _drain_discovery_results(self) -> None:
        while True:
            try:
                result_type, payload = self._discovery_results.get_nowait()
            except Empty:
                return
            self._discovery_thread = None
            if result_type == "error":
                self.controller.mark_discovery_error(str(payload))
                self._schedule_next_discovery()
                continue
            candidates, baudrate = payload
            self._handle_discovery_candidates(candidates, baudrate=baudrate)

    def _handle_discovery_candidates(
        self,
        candidates: list[ReceiverPortCandidate],
        *,
        baudrate: int,
    ) -> None:
        gui_candidates = [candidate for candidate in candidates if self._is_supported_gui_candidate(candidate)]
        if not gui_candidates:
            bootloader_candidates = self._receiver_bootloader_candidates(candidates)
            self._release_discovery_probe_ports(candidates)
            if bootloader_candidates:
                self._emit_app_event(
                    "receiver_bootloader_detected",
                    "lifecycle",
                    {
                        "ports": [candidate.port.device for candidate in bootloader_candidates],
                        "vid_pid": "2886:0045",
                        "serial_numbers": [
                            candidate.port.serial_number for candidate in bootloader_candidates
                        ],
                    },
                    RECEIVER_BOOTLOADER_DISCOVERY_DETAIL,
                )
                self.controller.mark_receiver_not_found(RECEIVER_BOOTLOADER_DISCOVERY_DETAIL)
            else:
                self.controller.mark_receiver_not_found()
            self._schedule_next_discovery()
            return
        if len(gui_candidates) > 1:
            self._release_discovery_probe_ports(candidates)
            self.controller.mark_multiple_receivers([candidate.port.device for candidate in gui_candidates])
            self._schedule_next_discovery()
            return

        candidate = gui_candidates[0]
        self._release_discovery_probe_ports(candidates, keep_candidate=candidate)
        self._start_attach(candidate, baudrate=baudrate)

    def _start_attach(self, candidate: ReceiverPortCandidate, *, baudrate: int) -> None:
        session = self._session_factory()
        self._attach_attempt_token += 1
        token = self._attach_attempt_token
        self._active_attach_token = token
        self._active_attach_candidate = candidate
        self._active_attach_session = session
        self._attach_started_at = self._time_fn()
        self._attach_thread = Thread(
            target=self._attach_worker,
            args=(token, candidate, session, baudrate),
            name="receiver-attach",
            daemon=True,
        )
        self._attach_thread.start()

    def _attach_worker(
        self,
        token: int,
        candidate: ReceiverPortCandidate,
        session: SerialSession,
        baudrate: int,
    ) -> None:
        if hasattr(session, "set_protocol_tap"):
            session.set_protocol_tap(
                lambda direction, raw, message, detail: self._protocol_tap(
                    direction=direction,
                    raw=raw,
                    message=message,
                    detail=detail,
                )
            )
        if hasattr(session, "set_lifecycle_tap"):
            session.set_lifecycle_tap(
                lambda event, fields, detail: self._emit_app_event(event, "lifecycle", fields, detail)
            )
        try:
            self._open_discovered_session(
                session,
                candidate=candidate,
                baudrate=baudrate,
            )
        except SessionOpenError as exc:
            self._attach_results.put(("error", token, (candidate, str(exc))))
            return
        self._attach_results.put(("attached", token, (candidate, session)))

    def _drain_attach_results(self) -> None:
        while True:
            try:
                result_type, token, payload = self._attach_results.get_nowait()
            except Empty:
                return

            if token != self._active_attach_token:
                if self._active_attach_token is None:
                    self._attach_thread = None
                if result_type == "attached":
                    candidate, session = payload
                    self._release_discovery_probe_ports([candidate])
                    try:
                        session.close()
                    except Exception:
                        pass
                elif result_type == "error":
                    candidate, _detail = payload
                    self._release_discovery_probe_ports([candidate])
                continue

            self._attach_thread = None
            self._active_attach_token = None
            self._active_attach_candidate = None
            self._active_attach_session = None
            self._attach_started_at = 0.0

            if result_type == "error":
                candidate, detail = payload
                self._release_discovery_probe_ports([candidate])
                self.controller.mark_discovery_error(detail)
                self._schedule_next_discovery()
                continue

            candidate, session = payload
            self._release_discovery_probe_ports([candidate], keep_candidate=candidate)
            if getattr(session, "device", None) is None:
                session.device = candidate.port.device
            self._session = session
            self.controller.mark_attached(candidate)
            self._receiver_debug_epoch_key = None

    def _expire_attach_timeout(self) -> None:
        active_token = self._active_attach_token
        if active_token is None:
            return
        if self._time_fn() - self._attach_started_at < ATTACH_OPERATION_TIMEOUT_S:
            return

        candidate = self._active_attach_candidate
        session = self._active_attach_session
        if candidate is not None:
            self._release_discovery_probe_ports([candidate])
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        self._active_attach_token = None
        self._active_attach_candidate = None
        self._active_attach_session = None
        self._attach_started_at = 0.0
        self.controller.mark_discovery_error("Receiver attach timed out")
        self._schedule_next_discovery()

    def _open_discovered_session(
        self,
        session: SerialSession,
        *,
        candidate: ReceiverPortCandidate,
        baudrate: int,
    ) -> None:
        last_error: SessionOpenError | None = None

        for attempt in range(1, ATTACH_OPEN_RETRY_ATTEMPTS + 1):
            retained_probe_port = candidate.probe_serial_port
            open_mode = "attach_open_port" if retained_probe_port is not None else "open"
            started_at = time.monotonic()
            self._emit_app_event(
                "receiver_attach_open_started",
                "lifecycle",
                {
                    "device": candidate.port.device,
                    "attempt": attempt,
                    "mode": open_mode,
                },
                None,
            )
            try:
                if retained_probe_port is not None and hasattr(session, "attach_open_port"):
                    session.attach_open_port(candidate.port.device, retained_probe_port)
                    candidate.probe_serial_port = None
                else:
                    session.open(candidate.port.device, baudrate=baudrate)
                self._emit_app_event(
                    "receiver_attach_open_finished",
                    "lifecycle",
                    {
                        "device": candidate.port.device,
                        "attempt": attempt,
                        "mode": open_mode,
                        "elapsed_ms": int((time.monotonic() - started_at) * 1000),
                    },
                    None,
                )
                return
            except SessionOpenError as exc:
                last_error = exc
                self._emit_app_event(
                    "receiver_attach_open_failed",
                    "lifecycle",
                    {
                        "device": candidate.port.device,
                        "attempt": attempt,
                        "mode": open_mode,
                        "elapsed_ms": int((time.monotonic() - started_at) * 1000),
                    },
                    str(exc),
                )
                if not self._should_retry_discovered_session_open(candidate, exc, attempt):
                    raise
                self._emit_app_event(
                    "receiver_attach_open_retry_scheduled",
                    "lifecycle",
                    {
                        "device": candidate.port.device,
                        "attempt": attempt,
                        "delay_s": ATTACH_OPEN_RETRY_DELAY_S,
                    },
                    str(exc),
                )
                time.sleep(ATTACH_OPEN_RETRY_DELAY_S)

        if last_error is not None:
            raise last_error

    @staticmethod
    def _release_discovery_probe_ports(
        candidates: list[ReceiverPortCandidate],
        *,
        keep_candidate: ReceiverPortCandidate | None = None,
    ) -> None:
        for candidate in candidates:
            if keep_candidate is not None and candidate is keep_candidate:
                continue
            serial_port = candidate.probe_serial_port
            candidate.probe_serial_port = None
            if serial_port is None:
                continue
            try:
                serial_port.close()
            except Exception:
                pass

    @staticmethod
    def _should_retry_discovered_session_open(
        candidate: ReceiverPortCandidate,
        error: SessionOpenError,
        attempt: int,
    ) -> bool:
        if not candidate.protocol_verified:
            return False
        if attempt >= ATTACH_OPEN_RETRY_ATTEMPTS:
            return False

        error_text = str(error).lower()
        return any(marker in error_text for marker in OPEN_RETRYABLE_ERROR_MARKERS)

    def _detach(self, detail: str) -> None:
        self._stop_receiver_debug_reader(emit_detached=True)
        session = self._session
        self._session = None
        if session is not None:
            session.close()
        self.controller.mark_disconnected(detail)
        self._schedule_next_discovery()

    def _sync_receiver_debug_reader(self) -> None:
        if not self.state.attached:
            self._stop_receiver_debug_reader(emit_detached=True)
            self._receiver_debug_epoch_key = None
            self._receiver_debug_attach_started = False
            self._receiver_debug_skip_logged = False
            self._receiver_debug_retry_at = 0.0
            self.state.receiver_debug_port = None
            return

        epoch_key = (
            self.state.receiver_port,
            self.state.preferred_serial_number,
            self.state.preferred_device_path,
        )
        if epoch_key != self._receiver_debug_epoch_key:
            self._stop_receiver_debug_reader(emit_detached=True)
            self._receiver_debug_epoch_key = epoch_key
            self._receiver_debug_attach_started = False
            self._receiver_debug_skip_logged = False
            self._receiver_debug_retry_at = 0.0
            self.state.receiver_debug_port = None

        if not self._auto_attach_receiver_debug:
            self._log_receiver_debug_attach_skipped("receiver debug auto-attach is disabled")
            return

        if self._receiver_debug_reader is not None or self._time_fn() < self._receiver_debug_retry_at:
            return

        if not self._receiver_debug_attach_started:
            self._capture.record_capture_lifecycle(
                source="receiver",
                event="receiver_debug_attach_started",
            )
            self._receiver_debug_attach_started = True

        try:
            ports = self._list_ports()
        except SerialDiscoveryError as exc:
            self._log_receiver_debug_attach_skipped(str(exc))
            self._receiver_debug_retry_at = self._time_fn() + self._discovery_config.retry_interval_s
            return

        selected_port, reason = select_receiver_debug_port(
            ports=ports,
            gui_port=self.state.receiver_port or "",
            vid_pid_allowlist=tuple(self._discovery_config.vid_pid_allowlist),
            serial_number=self.state.preferred_serial_number,
            device_path=self.state.preferred_device_path,
        )
        if selected_port is None:
            self._log_receiver_debug_attach_skipped(reason or "receiver debug port was not uniquely identified")
            self._receiver_debug_retry_at = self._time_fn() + self._discovery_config.retry_interval_s
            return

        reader = self._build_text_log_reader(source="receiver", port_info=selected_port)
        try:
            reader.start()
        except SerialTextLogOpenError as exc:
            self._capture.record_reader_failure(
                source="receiver",
                reason=str(exc),
                port_info=selected_port,
                exception_class=exc.__class__.__name__,
            )
            self._set_debug_capture_error(str(exc))
            self._receiver_debug_retry_at = self._time_fn() + self._discovery_config.retry_interval_s
            return

        self._receiver_debug_reader = reader
        self.state.receiver_debug_port = selected_port.device
        self._set_debug_capture_error(None)
        self._capture.record_capture_lifecycle(
            source="receiver",
            event="receiver_debug_attached",
            port=selected_port.device,
            device_path=selected_port.location or selected_port.device,
            serial_number=selected_port.serial_number,
        )

    def _log_receiver_debug_attach_skipped(self, reason: str) -> None:
        if self._receiver_debug_skip_logged:
            return
        self._receiver_debug_skip_logged = True
        self._capture.record_capture_lifecycle(
            source="receiver",
            event="receiver_debug_attach_skipped",
            fields={"reason": reason},
            detail=reason,
        )

    def _build_text_log_reader(self, *, source: str, port_info: SerialPortInfo) -> SerialTextLogReader:
        return self._text_log_reader_factory(
            port_info=port_info,
            on_line=lambda raw, info: self._capture.record_debug_text(source=source, raw=raw, port_info=info),
            on_failure=lambda detail, exception_class, info: self._reader_failures.put(
                (source, detail, exception_class, info)
            ),
            baudrate=self._discovery_config.baudrate,
        )

    def _stop_receiver_debug_reader(self, *, emit_detached: bool) -> None:
        reader = self._receiver_debug_reader
        self._receiver_debug_reader = None
        self.state.receiver_debug_port = None
        if reader is None:
            return
        port_info = reader.port_info
        reader.close()
        if emit_detached:
            self._capture.record_capture_lifecycle(
                source="receiver",
                event="receiver_debug_detached",
                port=port_info.device,
                device_path=port_info.location or port_info.device,
                serial_number=port_info.serial_number,
            )

    def _stop_keyboard_debug_reader(self, *, emit_detached: bool) -> None:
        reader = self._keyboard_debug_reader
        self._keyboard_debug_reader = None
        self.state.keyboard_log_port = None
        if reader is None:
            return
        port_info = reader.port_info
        reader.close()
        if emit_detached:
            self._capture.record_capture_lifecycle(
                source="keyboard",
                event="keyboard_log_detached",
                port=port_info.device,
                device_path=port_info.location or port_info.device,
                serial_number=port_info.serial_number,
            )

    def _schedule_next_discovery(self) -> None:
        self._next_discovery_at = self._time_fn() + self._discovery_config.retry_interval_s

    def _build_discovery_config(self) -> DiscoveryConfig:
        return replace(
            self._discovery_config,
            preferred_serial_number=self.state.preferred_serial_number,
            preferred_device_path=self.state.preferred_device_path,
        )

    def _refresh_capture_state(self) -> None:
        self.state.debug_capture_active = self._capture.active
        self.state.debug_session_id = self._capture.session_id
        self.state.debug_log_path = self._capture.log_path

    def _set_debug_capture_error(self, detail: str | None) -> None:
        self._refresh_capture_state()
        self.state.debug_capture_error = detail

    @staticmethod
    def _is_supported_gui_candidate(candidate: ReceiverPortCandidate) -> bool:
        if candidate.protocol_verified and not candidate.hello_verified:
            return True
        return (
            candidate.hello_verified
            and candidate.hello_product == PROTOCOL_PRODUCT
            and candidate.hello_channel == PROTOCOL_CHANNEL
            and candidate.hello_protocol_version == PROTOCOL_VERSION
        )

    @staticmethod
    def _receiver_bootloader_candidates(
        candidates: list[ReceiverPortCandidate],
    ) -> list[ReceiverPortCandidate]:
        return [
            candidate
            for candidate in candidates
            if (
                candidate.port.vid,
                candidate.port.pid,
            )
            in DEFAULT_RECEIVER_BOOTLOADER_VID_PID_ALLOWLIST
        ]
