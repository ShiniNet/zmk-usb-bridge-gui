from __future__ import annotations

import time
from dataclasses import dataclass
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
DEFAULT_PROBE_TIMEOUT_S = 0.4


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


@dataclass(slots=True)
class DiscoveryConfig:
    vid_pid_allowlist: Sequence[tuple[int, int]] = ()
    baudrate: int = DEFAULT_BAUDRATE
    probe_timeout_s: float = DEFAULT_PROBE_TIMEOUT_S
    retry_interval_s: float = 2.0
    preferred_serial_number: str | None = None
    preferred_device_path: str | None = None


@dataclass(slots=True)
class GuiProtocolProbeResult:
    hello: HelloMessage | None = None
    protocol_verified: bool = False
    verified_via: str | None = None


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
) -> tuple[int, int, str]:
    serial_match = preferred_serial_number is not None and port.serial_number == preferred_serial_number
    path_match = preferred_device_path is not None and (
        port.location == preferred_device_path or port.device == preferred_device_path
    )
    return (
        0 if serial_match else 1,
        0 if path_match else 1,
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
) -> GuiProtocolProbeResult:
    """Attempt to verify that a port speaks the GUI protocol."""

    Serial = serial_factory or _load_serial()
    per_read_timeout_s = min(timeout_s, 0.1)
    deadline = time.monotonic() + timeout_s
    probe_command = serialize_message_line(CommandMessage(request_id=0, name="get_status")).encode("utf-8")
    fallback_result = GuiProtocolProbeResult()

    with Serial(port=device, baudrate=baudrate, timeout=per_read_timeout_s, write_timeout=per_read_timeout_s) as serial_port:
        if hasattr(serial_port, "dtr"):
            try:
                serial_port.dtr = True
            except Exception:
                pass
        if hasattr(serial_port, "reset_input_buffer"):
            try:
                serial_port.reset_input_buffer()
            except Exception:
                pass
        try:
            serial_port.write(probe_command)
            if hasattr(serial_port, "flush"):
                serial_port.flush()
        except Exception:
            pass

        while time.monotonic() < deadline:
            raw_line = serial_port.readline()
            if not raw_line:
                continue
            try:
                message = parse_message_line(raw_line.decode("utf-8", errors="replace"))
            except ProtocolParseError:
                continue
            if isinstance(message, HelloMessage):
                return GuiProtocolProbeResult(
                    hello=message,
                    protocol_verified=True,
                    verified_via="hello",
                )
            if isinstance(message, StatusSnapshot):
                if not fallback_result.protocol_verified:
                    fallback_result = GuiProtocolProbeResult(
                        protocol_verified=True,
                        verified_via="status_snapshot",
                    )
                continue
            if isinstance(message, CandidateSnapshot):
                if not fallback_result.protocol_verified:
                    fallback_result = GuiProtocolProbeResult(
                        protocol_verified=True,
                        verified_via="candidate_snapshot",
                    )
                continue
            if isinstance(message, AckMessage) and message.request_id == 0 and message.name == "get_status":
                if not fallback_result.protocol_verified:
                    fallback_result = GuiProtocolProbeResult(protocol_verified=True, verified_via="ack")
                continue
            if isinstance(message, ErrorMessage) and message.request_id == 0 and message.name == "get_status":
                if not fallback_result.protocol_verified:
                    fallback_result = GuiProtocolProbeResult(protocol_verified=True, verified_via="error")
                continue
    return fallback_result


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
) -> list[ReceiverPortCandidate]:
    """Return all visible serial ports, sorted so receiver-like matches come first."""

    config = config or DiscoveryConfig()
    candidates: list[ReceiverPortCandidate] = []
    verified_identity_keys: set[tuple[str, str]] = set()
    probe_protocol = probe_protocol_fn or probe_gui_protocol
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
                if identity_key is not None:
                    verified_identity_keys.add(identity_key)
        candidates.append(candidate)
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
