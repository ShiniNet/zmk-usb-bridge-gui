from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .protocol import HelloMessage, ProtocolParseError, parse_message_line

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


@dataclass(slots=True)
class DiscoveryConfig:
    vid_pid_allowlist: Sequence[tuple[int, int]] = ()
    baudrate: int = DEFAULT_BAUDRATE
    probe_timeout_s: float = DEFAULT_PROBE_TIMEOUT_S
    retry_interval_s: float = 2.0


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


def probe_gui_hello(
    device: str,
    *,
    baudrate: int = DEFAULT_BAUDRATE,
    timeout_s: float = DEFAULT_PROBE_TIMEOUT_S,
) -> HelloMessage | None:
    """Attempt to read the initial hello line from a receiver GUI CDC port."""

    Serial = _load_serial()
    with Serial(port=device, baudrate=baudrate, timeout=timeout_s, write_timeout=timeout_s) as serial_port:
        raw_line = serial_port.readline()
    if not raw_line:
        return None
    try:
        message = parse_message_line(raw_line.decode("utf-8", errors="replace"))
    except ProtocolParseError:
        return None
    if isinstance(message, HelloMessage):
        return message
    return None


def discover_receiver_ports(
    config: DiscoveryConfig | None = None,
    *,
    probe_hello: bool = False,
) -> list[ReceiverPortCandidate]:
    """Return all visible serial ports, sorted so receiver-like matches come first."""

    config = config or DiscoveryConfig()
    candidates: list[ReceiverPortCandidate] = []
    for port in list_serial_ports():
        vid_pid_match = _matches_allowlist(port, config.vid_pid_allowlist)
        candidate = ReceiverPortCandidate(port=port, vid_pid_match=vid_pid_match)
        if probe_hello and vid_pid_match:
            hello = probe_gui_hello(port.device, baudrate=config.baudrate, timeout_s=config.probe_timeout_s)
            if hello is not None:
                candidate.hello_verified = True
                candidate.hello_product = hello.product
                candidate.hello_channel = hello.channel
                candidate.hello_protocol_version = hello.protocol_version
        candidates.append(candidate)
    candidates.sort(
        key=lambda item: (
            not item.vid_pid_match,
            not item.hello_verified,
            item.port.device.lower(),
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
