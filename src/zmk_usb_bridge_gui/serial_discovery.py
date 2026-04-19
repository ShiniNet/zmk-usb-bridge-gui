from __future__ import annotations

import time
from dataclasses import dataclass
from queue import Empty, SimpleQueue
from threading import Thread
from typing import Callable
from typing import Sequence

from .protocol import (
    AckMessage,
    CandidateSnapshot,
    CommandMessage,
    ErrorMessage,
    HelloMessage,
    ProtocolParseError,
    StatusSnapshot,
    parse_message_line,
    serialize_message_line,
)

DEFAULT_BAUDRATE = 115200
DEFAULT_PROBE_TIMEOUT_S = 1.0
DEFAULT_PASSIVE_HELLO_GRACE_S = 0.35
DEFAULT_GUI_READY_DIAGNOSTIC_TIMEOUT_S = 0.6


class SerialDiscoveryError(RuntimeError):
    """Raised when serial discovery cannot be completed."""


@dataclass(slots=True)
class SerialPortInfo:
    device: str
    description: str | None = None
    hwid: str | None = None
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    location: str | None = None
    manufacturer: str | None = None


@dataclass(slots=True)
class ReceiverPortCandidate:
    port: SerialPortInfo
    vid_pid_match: bool
    hello_verified: bool = False
    hello_product: str | None = None
    hello_channel: str | None = None
    hello_protocol_version: int | None = None
    protocol_verified: bool = False
    protocol_verified_via: str | None = None
    probe_serial_port: object | None = None


@dataclass(slots=True)
class DiscoveryConfig:
    vid_pid_allowlist: Sequence[tuple[int, int]] = ()
    baudrate: int = DEFAULT_BAUDRATE
    probe_timeout_s: float = DEFAULT_PROBE_TIMEOUT_S
    retry_interval_s: float = 2.0
    preferred_serial_number: str | None = None
    preferred_device_path: str | None = None
    enable_gui_ready_diagnostic: bool = False
    keep_probe_port_open_on_success: bool = False


@dataclass(slots=True)
class GuiProtocolProbeResult:
    hello: HelloMessage | None = None
    protocol_verified: bool = False
    verified_via: str | None = None
    retained_serial_port: object | None = None
    failure_detail: str | None = None
    failure_exception_class: str | None = None


@dataclass(slots=True)
class GuiReadyDiagnosticResult:
    observed: bool = False
    completed: bool = False
    detail: str | None = None


def _update_probe_result_from_message(
    result: GuiProtocolProbeResult,
    message: object,
) -> GuiProtocolProbeResult:
    if isinstance(message, HelloMessage):
        return GuiProtocolProbeResult(
            hello=message,
            protocol_verified=True,
            verified_via="hello",
            retained_serial_port=result.retained_serial_port,
            failure_detail=result.failure_detail,
            failure_exception_class=result.failure_exception_class,
        )
    if isinstance(message, StatusSnapshot):
        if not result.protocol_verified:
            return GuiProtocolProbeResult(
                protocol_verified=True,
                verified_via="status_snapshot",
                retained_serial_port=result.retained_serial_port,
                failure_detail=result.failure_detail,
                failure_exception_class=result.failure_exception_class,
            )
        return result
    if isinstance(message, CandidateSnapshot):
        if not result.protocol_verified:
            return GuiProtocolProbeResult(
                protocol_verified=True,
                verified_via="candidate_snapshot",
                retained_serial_port=result.retained_serial_port,
                failure_detail=result.failure_detail,
                failure_exception_class=result.failure_exception_class,
            )
        return result
    if isinstance(message, AckMessage) and message.request_id == 0 and message.name == "get_status":
        if not result.protocol_verified:
            return GuiProtocolProbeResult(
                protocol_verified=True,
                verified_via="ack",
                retained_serial_port=result.retained_serial_port,
                failure_detail=result.failure_detail,
                failure_exception_class=result.failure_exception_class,
            )
        return result
    if isinstance(message, ErrorMessage) and message.request_id == 0 and message.name == "get_status":
        if not result.protocol_verified:
            return GuiProtocolProbeResult(
                protocol_verified=True,
                verified_via="error",
                retained_serial_port=result.retained_serial_port,
                failure_detail=result.failure_detail,
                failure_exception_class=result.failure_exception_class,
            )
        return result
    return result


def _read_probe_messages_until(
    serial_port: object,
    *,
    deadline: float,
    fallback_result: GuiProtocolProbeResult,
) -> GuiProtocolProbeResult:
    result = fallback_result
    while time.monotonic() < deadline:
        raw_line = serial_port.readline()
        if not raw_line:
            continue
        try:
            message = parse_message_line(raw_line.decode("utf-8", errors="replace"))
        except ProtocolParseError:
            continue
        result = _update_probe_result_from_message(result, message)
        if result.hello is not None:
            return result
    return result


def _probe_gui_protocol_on_open_port(
    serial_port: object,
    *,
    timeout_s: float,
) -> GuiProtocolProbeResult:
    deadline = time.monotonic() + timeout_s
    passive_deadline = min(
        deadline,
        time.monotonic() + min(DEFAULT_PASSIVE_HELLO_GRACE_S, max(timeout_s * 0.5, 0.01)),
    )
    probe_command = serialize_message_line(CommandMessage(request_id=0, name="get_status")).encode("utf-8")
    fallback_result = GuiProtocolProbeResult()

    if hasattr(serial_port, "reset_input_buffer"):
        try:
            serial_port.reset_input_buffer()
        except Exception:
            pass
    if hasattr(serial_port, "dtr"):
        try:
            serial_port.dtr = True
        except Exception:
            pass

    result = _read_probe_messages_until(
        serial_port,
        deadline=passive_deadline,
        fallback_result=fallback_result,
    )
    if result.hello is not None:
        return result

    try:
        # Some sibling CDC ports do not consume host writes reliably; avoid flush()
        # here so a bad probe cannot stall discovery for tens of seconds.
        serial_port.write(probe_command)
    except Exception:
        pass

    return _read_probe_messages_until(
        serial_port,
        deadline=deadline,
        fallback_result=result,
    )


def _probe_gui_protocol_worker(
    result_queue: SimpleQueue[GuiProtocolProbeResult],
    *,
    device: str,
    baudrate: int,
    timeout_s: float,
    serial_factory: Callable[..., object],
    keep_port_open_on_success: bool,
) -> None:
    per_read_timeout_s = min(timeout_s, 0.1)
    serial_port = None
    try:
        serial_port = serial_factory(
            port=device,
            baudrate=baudrate,
            timeout=per_read_timeout_s,
            write_timeout=per_read_timeout_s,
        )
        result = _probe_gui_protocol_on_open_port(serial_port, timeout_s=timeout_s)
        if keep_port_open_on_success and result.protocol_verified:
            result.retained_serial_port = serial_port
            serial_port = None
    except Exception as exc:
        result = GuiProtocolProbeResult(
            failure_detail=str(exc),
            failure_exception_class=exc.__class__.__name__,
        )
    result_queue.put(result)
    if serial_port is not None:
        try:
            serial_port.close()
        except Exception:
            pass


def _group_receiver_candidates_by_identity(
    candidates: list[ReceiverPortCandidate],
) -> dict[tuple[str, str], list[ReceiverPortCandidate]]:
    groups: dict[tuple[str, str], list[ReceiverPortCandidate]] = {}
    for candidate in candidates:
        if not candidate.vid_pid_match:
            continue
        identity_key = _probe_identity_key(candidate.port)
        if identity_key is None:
            continue
        groups.setdefault(identity_key, []).append(candidate)
    return groups


def diagnose_gui_port_via_receiver_log(
    gui_device: str,
    log_device: str,
    *,
    baudrate: int = DEFAULT_BAUDRATE,
    timeout_s: float = DEFAULT_GUI_READY_DIAGNOSTIC_TIMEOUT_S,
    serial_factory: Callable[..., object] | None = None,
) -> GuiReadyDiagnosticResult:
    Serial = serial_factory or _load_serial()
    result_queue: SimpleQueue[GuiReadyDiagnosticResult] = SimpleQueue()
    worker = Thread(
        target=_diagnose_gui_port_via_receiver_log_worker,
        kwargs={
            "result_queue": result_queue,
            "gui_device": gui_device,
            "log_device": log_device,
            "baudrate": baudrate,
            "timeout_s": timeout_s,
            "serial_factory": Serial,
        },
        name=f"gui-ready-diagnostic-{gui_device}",
        daemon=True,
    )
    worker.start()
    worker.join(timeout=timeout_s + 0.15)
    try:
        return result_queue.get_nowait()
    except Empty:
        return GuiReadyDiagnosticResult(completed=False, detail="diagnostic timed out")


def _diagnose_gui_port_via_receiver_log_worker(
    result_queue: SimpleQueue[GuiReadyDiagnosticResult],
    *,
    gui_device: str,
    log_device: str,
    baudrate: int = DEFAULT_BAUDRATE,
    timeout_s: float = DEFAULT_GUI_READY_DIAGNOSTIC_TIMEOUT_S,
    serial_factory: Callable[..., object],
) -> None:
    Serial = serial_factory
    per_read_timeout_s = min(timeout_s, 0.1)
    log_serial = None
    gui_serial = None
    try:
        log_serial = Serial(
            port=log_device,
            baudrate=baudrate,
            timeout=per_read_timeout_s,
            write_timeout=per_read_timeout_s,
        )
        gui_serial = Serial(
            port=gui_device,
            baudrate=baudrate,
            timeout=per_read_timeout_s,
            write_timeout=per_read_timeout_s,
        )
        for serial_port in (log_serial, gui_serial):
            if hasattr(serial_port, "reset_input_buffer"):
                try:
                    serial_port.reset_input_buffer()
                except Exception:
                    pass
        if hasattr(log_serial, "dtr"):
            try:
                log_serial.dtr = True
            except Exception:
                pass
        if hasattr(gui_serial, "dtr"):
            try:
                gui_serial.dtr = True
            except Exception:
                pass

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            raw_line = log_serial.readline()
            if not raw_line:
                continue
            decoded = raw_line.decode("utf-8", errors="replace").strip()
            if "gui channel ready" in decoded.lower():
                result_queue.put(GuiReadyDiagnosticResult(observed=True, completed=True))
                return
        result_queue.put(GuiReadyDiagnosticResult(observed=False, completed=True))
    except Exception as exc:
        result_queue.put(
            GuiReadyDiagnosticResult(
                observed=False,
                completed=True,
                detail=f"{exc.__class__.__name__}: {exc}",
            )
        )
    finally:
        for serial_port in (gui_serial, log_serial):
            if serial_port is None:
                continue
            try:
                serial_port.close()
            except Exception:
                pass


def _apply_gui_ready_diagnostic(
    candidates: list[ReceiverPortCandidate],
    *,
    config: DiscoveryConfig,
    trace_fn: Callable[[str, dict[str, object]], None] | None,
    serial_factory: Callable[..., object] | None = None,
) -> None:
    candidate_groups = _group_receiver_candidates_by_identity(candidates)
    for group in candidate_groups.values():
        if len(group) != 2:
            continue
        if any(candidate.protocol_verified or candidate.hello_verified for candidate in group):
            continue

        diagnostic_hits: list[ReceiverPortCandidate] = []
        for gui_candidate in group:
            log_candidate = next(item for item in group if item is not gui_candidate)
            if trace_fn is not None:
                trace_fn(
                    "discovery_gui_ready_diagnostic_started",
                    {
                        "gui_probe_device": gui_candidate.port.device,
                        "log_monitor_device": log_candidate.port.device,
                        "timeout_s": DEFAULT_GUI_READY_DIAGNOSTIC_TIMEOUT_S,
                    },
                )
            started_at = time.monotonic()
            observed = diagnose_gui_port_via_receiver_log(
                gui_candidate.port.device,
                log_candidate.port.device,
                baudrate=config.baudrate,
                timeout_s=DEFAULT_GUI_READY_DIAGNOSTIC_TIMEOUT_S,
                serial_factory=serial_factory,
            )
            if trace_fn is not None:
                trace_fn(
                    "discovery_gui_ready_diagnostic_finished",
                    {
                        "gui_probe_device": gui_candidate.port.device,
                        "log_monitor_device": log_candidate.port.device,
                        "elapsed_ms": int((time.monotonic() - started_at) * 1000),
                        "gui_ready_observed": observed.observed,
                        "diagnostic_completed": observed.completed,
                        "diagnostic_detail": observed.detail,
                    },
                )
            if observed.observed:
                diagnostic_hits.append(gui_candidate)

        if len(diagnostic_hits) == 1:
            diagnostic_hits[0].protocol_verified = True
            diagnostic_hits[0].protocol_verified_via = "gui_ready_diagnostic"


def _load_list_ports():
    try:
        from serial.tools import list_ports
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised when pyserial is absent.
        raise SerialDiscoveryError("pyserial is required for serial discovery") from exc
    return list_ports


def _load_serial():
    try:
        from serial import Serial
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised when pyserial is absent.
        raise SerialDiscoveryError("pyserial is required to probe a serial port") from exc
    return Serial


def list_serial_ports() -> list[SerialPortInfo]:
    """Return the local serial port inventory without opening any port."""

    list_ports = _load_list_ports()
    ports: list[SerialPortInfo] = []
    for port in list_ports.comports():
        ports.append(
            SerialPortInfo(
                device=port.device,
                description=getattr(port, "description", None),
                hwid=getattr(port, "hwid", None),
                vid=getattr(port, "vid", None),
                pid=getattr(port, "pid", None),
                serial_number=getattr(port, "serial_number", None),
                location=getattr(port, "location", None),
                manufacturer=getattr(port, "manufacturer", None),
            )
        )
    return ports


def _matches_allowlist(port: SerialPortInfo, allowlist: Sequence[tuple[int, int]]) -> bool:
    if not allowlist:
        return True
    if port.vid is None or port.pid is None:
        return False
    return any((port.vid, port.pid) == item for item in allowlist)


def _port_preference_rank(
    port: SerialPortInfo,
    *,
    preferred_serial_number: str | None,
    preferred_device_path: str | None,
) -> tuple[int, int, int, str]:
    serial_match = preferred_serial_number is not None and port.serial_number == preferred_serial_number
    path_match = preferred_device_path is not None and (
        port.location == preferred_device_path or port.device == preferred_device_path
    )
    return (
        0 if serial_match else 1,
        0 if path_match else 1,
        0 if port.location is not None else 1,
        port.device.lower(),
    )


def _probe_identity_key(port: SerialPortInfo) -> tuple[str, str] | None:
    if port.serial_number:
        return ("serial_number", port.serial_number)
    if port.location:
        return ("location", port.location)
    return None


def probe_gui_protocol(
    device: str,
    *,
    baudrate: int = DEFAULT_BAUDRATE,
    timeout_s: float = DEFAULT_PROBE_TIMEOUT_S,
    serial_factory: Callable[..., object] | None = None,
    keep_port_open_on_success: bool = False,
) -> GuiProtocolProbeResult:
    """Attempt to verify that a port speaks the GUI protocol."""

    Serial = serial_factory or _load_serial()
    result_queue: SimpleQueue[GuiProtocolProbeResult] = SimpleQueue()
    worker = Thread(
        target=_probe_gui_protocol_worker,
        kwargs={
            "result_queue": result_queue,
            "device": device,
            "baudrate": baudrate,
            "timeout_s": timeout_s,
            "serial_factory": Serial,
            "keep_port_open_on_success": keep_port_open_on_success,
        },
        name=f"probe-{device}",
        daemon=True,
    )
    worker.start()
    worker.join(timeout=timeout_s + 0.15)
    try:
        return result_queue.get_nowait()
    except Empty:
        return GuiProtocolProbeResult(
            failure_detail="probe worker timed out",
            failure_exception_class="TimeoutError",
        )


def probe_gui_hello(
    device: str,
    *,
    baudrate: int = DEFAULT_BAUDRATE,
    timeout_s: float = DEFAULT_PROBE_TIMEOUT_S,
    serial_factory: Callable[..., object] | None = None,
) -> HelloMessage | None:
    """Attempt to read the initial hello line from a receiver GUI CDC port."""

    return probe_gui_protocol(
        device,
        baudrate=baudrate,
        timeout_s=timeout_s,
        serial_factory=serial_factory,
    ).hello


def discover_receiver_ports(
    config: DiscoveryConfig | None = None,
    *,
    probe_hello: bool = False,
    trace_fn: Callable[[str, dict[str, object]], None] | None = None,
    probe_protocol_fn: Callable[..., GuiProtocolProbeResult] | None = None,
    diagnostic_serial_factory: Callable[..., object] | None = None,
) -> list[ReceiverPortCandidate]:
    """Return all visible serial ports, sorted so receiver-like matches come first."""

    config = config or DiscoveryConfig()
    candidates: list[ReceiverPortCandidate] = []
    verified_identity_keys: set[tuple[str, str]] = set()
    probe_protocol = probe_protocol_fn or (
        lambda device, **kwargs: probe_gui_protocol(
            device,
            keep_port_open_on_success=config.keep_probe_port_open_on_success,
            **kwargs,
        )
    )
    ports = sorted(
        list_serial_ports(),
        key=lambda port: _port_preference_rank(
            port,
            preferred_serial_number=config.preferred_serial_number,
            preferred_device_path=config.preferred_device_path,
        ),
    )
    for port in ports:
        vid_pid_match = _matches_allowlist(port, config.vid_pid_allowlist)
        candidate = ReceiverPortCandidate(port=port, vid_pid_match=vid_pid_match)
        if trace_fn is not None:
            trace_fn(
                "discovery_port_seen",
                {
                    "device": port.device,
                    "vid": port.vid,
                    "pid": port.pid,
                    "serial_number": port.serial_number,
                    "location": port.location,
                    "vid_pid_match": vid_pid_match,
                },
            )
        if probe_hello and vid_pid_match:
            identity_key = _probe_identity_key(port)
            if identity_key is not None and identity_key in verified_identity_keys:
                if trace_fn is not None:
                    trace_fn(
                        "discovery_probe_skipped",
                        {
                            "device": port.device,
                            "reason": "protocol_verified_on_sibling",
                        },
                    )
                candidates.append(candidate)
                continue
            if trace_fn is not None:
                trace_fn(
                    "discovery_probe_started",
                    {
                        "device": port.device,
                        "baudrate": config.baudrate,
                        "timeout_s": config.probe_timeout_s,
                    },
                )
            started_at = time.monotonic()
            probe_result = probe_protocol(
                port.device,
                baudrate=config.baudrate,
                timeout_s=config.probe_timeout_s,
            )
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            if trace_fn is not None:
                trace_fn(
                    "discovery_probe_finished",
                    {
                        "device": port.device,
                        "elapsed_ms": elapsed_ms,
                        "hello_verified": probe_result.hello is not None,
                        "hello_product": probe_result.hello.product if probe_result.hello is not None else None,
                        "hello_channel": probe_result.hello.channel if probe_result.hello is not None else None,
                        "hello_protocol_version": (
                            probe_result.hello.protocol_version if probe_result.hello is not None else None
                        ),
                        "protocol_verified": probe_result.protocol_verified,
                        "protocol_verified_via": probe_result.verified_via,
                        "probe_failure_detail": probe_result.failure_detail,
                        "probe_failure_exception_class": probe_result.failure_exception_class,
                    },
                )
            if probe_result.hello is not None:
                candidate.hello_verified = True
                candidate.hello_product = probe_result.hello.product
                candidate.hello_channel = probe_result.hello.channel
                candidate.hello_protocol_version = probe_result.hello.protocol_version
            if probe_result.protocol_verified:
                candidate.protocol_verified = True
                candidate.protocol_verified_via = probe_result.verified_via
                candidate.probe_serial_port = probe_result.retained_serial_port
                if identity_key is not None:
                    verified_identity_keys.add(identity_key)
        candidates.append(candidate)
    if probe_hello and config.enable_gui_ready_diagnostic:
        _apply_gui_ready_diagnostic(
            candidates,
            config=config,
            trace_fn=trace_fn,
            serial_factory=diagnostic_serial_factory,
        )
    candidates.sort(
        key=lambda item: (
            not item.vid_pid_match,
            not item.protocol_verified,
            not item.hello_verified,
            *_port_preference_rank(
                item.port,
                preferred_serial_number=config.preferred_serial_number,
                preferred_device_path=config.preferred_device_path,
            ),
        )
    )
    return candidates


def format_receiver_port(candidate: ReceiverPortCandidate) -> str:
    port = candidate.port
    hello_version = candidate.hello_protocol_version
    vid_pid = "unknown"
    if port.vid is not None and port.pid is not None:
        vid_pid = f"{port.vid:04x}:{port.pid:04x}"
    pieces = [port.device, f"vid/pid={vid_pid}"]
    if port.description:
        pieces.append(port.description)
    if candidate.hello_verified:
        pieces.append(
            f"hello={candidate.hello_product or 'unknown'}"
            f"/{candidate.hello_channel or 'unknown'}"
            f"/v{hello_version if hello_version is not None else '?'}"
        )
    elif candidate.vid_pid_match:
        pieces.append("vid/pid-match")
    return " | ".join(pieces)
