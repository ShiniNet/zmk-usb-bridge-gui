from __future__ import annotations

from dataclasses import dataclass, field
from json import JSONDecodeError, dumps, loads
from typing import Any, Literal, Sequence, TypeAlias

PROTOCOL_PRODUCT = "zmk-usb-bridge-gui"
PROTOCOL_VERSION = 1
PROTOCOL_CHANNEL = "gui"


class ProtocolError(ValueError):
    """Base class for protocol parsing and serialization errors."""


class ProtocolParseError(ProtocolError):
    """Raised when a JSON line does not match protocol v1."""


@dataclass(slots=True)
class HelloMessage:
    type: Literal["hello"] = "hello"
    product: str = PROTOCOL_PRODUCT
    protocol_version: int = PROTOCOL_VERSION
    channel: str = PROTOCOL_CHANNEL
    board: str | None = None
    firmware_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "product": self.product,
            "protocol_version": self.protocol_version,
            "channel": self.channel,
            "board": self.board,
            "firmware_version": self.firmware_version,
        }


@dataclass(slots=True)
class StatusSnapshot:
    type: Literal["status_snapshot"] = "status_snapshot"
    receiver_state: Literal["idle", "scanning", "connecting", "connected"] = "idle"
    peer_name: str | None = None
    peer_address: str | None = None
    scan_in_progress: bool = False
    candidate_generation: int = 0
    candidate_count: int = 0
    battery_percent: int | None = None
    battery_supported: bool | None = None
    modifiers: tuple[str, ...] | None = None
    modifiers_supported: bool | None = None
    last_key: str | None = None
    last_key_supported: bool | None = None
    mouse_buttons: tuple[str, ...] | None = None
    mouse_buttons_supported: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "type": self.type,
            "receiver_state": self.receiver_state,
            "peer_name": self.peer_name,
            "peer_address": self.peer_address,
            "scan_in_progress": self.scan_in_progress,
            "candidate_generation": self.candidate_generation,
            "candidate_count": self.candidate_count,
        }
        if self.battery_supported is not None:
            data["battery_supported"] = self.battery_supported
        if self.battery_percent is not None or self.battery_supported is not None:
            data["battery_percent"] = self.battery_percent
        if self.modifiers_supported is not None:
            data["modifiers_supported"] = self.modifiers_supported
        if self.modifiers is not None:
            data["modifiers"] = list(self.modifiers)
        if self.last_key_supported is not None:
            data["last_key_supported"] = self.last_key_supported
        if self.last_key is not None or self.last_key_supported is not None:
            data["last_key"] = self.last_key
        if self.mouse_buttons_supported is not None:
            data["mouse_buttons_supported"] = self.mouse_buttons_supported
        if self.mouse_buttons is not None:
            data["mouse_buttons"] = list(self.mouse_buttons)
        return data


@dataclass(slots=True)
class Candidate:
    candidate_id: int
    ble_address: str
    display_name: str | None
    connectable: bool
    has_hid_service: bool
    has_keyboard_appearance: bool
    rssi: int | None
    last_seen_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "candidate_id": self.candidate_id,
            "ble_address": self.ble_address,
            "display_name": self.display_name,
            "connectable": self.connectable,
            "has_hid_service": self.has_hid_service,
            "has_keyboard_appearance": self.has_keyboard_appearance,
            "rssi": self.rssi,
        }
        if self.last_seen_ms is not None:
            data["last_seen_ms"] = self.last_seen_ms
        return data


@dataclass(slots=True)
class CandidateSnapshot:
    type: Literal["candidate_snapshot"] = "candidate_snapshot"
    candidate_generation: int = 0
    candidates: list[Candidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "candidate_generation": self.candidate_generation,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(slots=True)
class CommandMessage:
    type: Literal["command"] = "command"
    request_id: int = 0
    name: str = ""
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {"type": self.type, "request_id": self.request_id, "name": self.name}
        data.update(self.fields)
        return data


@dataclass(slots=True)
class AckMessage:
    type: Literal["ack"] = "ack"
    request_id: int = 0
    name: str = ""
    accepted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "name": self.name,
            "accepted": self.accepted,
        }


@dataclass(slots=True)
class ErrorMessage:
    type: Literal["error"] = "error"
    request_id: int = 0
    name: str = ""
    code: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "name": self.name,
            "code": self.code,
            "message": self.message,
        }


@dataclass(slots=True)
class EventMessage:
    type: Literal["event"] = "event"
    name: str = ""
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {"type": self.type, "name": self.name}
        data.update(self.fields)
        return data


Message: TypeAlias = (
    HelloMessage
    | StatusSnapshot
    | CandidateSnapshot
    | CommandMessage
    | AckMessage
    | ErrorMessage
    | EventMessage
)


def serialize_message_line(message: Message) -> str:
    """Serialize a protocol message as a single UTF-8 JSON line."""

    return f"{dumps(message.to_dict(), ensure_ascii=False, separators=(',', ':'))}\n"


def _require_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProtocolParseError("protocol message must be a JSON object")
    return payload


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ProtocolParseError(f"{field_name} must be a string")
    return value


def _require_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProtocolParseError(f"{field_name} must be an integer")
    return value


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ProtocolParseError(f"{field_name} must be a boolean")
    return value


def _optional_string(value: Any, field_name: str) -> str | None:
    return None if value is None else _require_string(value, field_name)


def _optional_int(value: Any, field_name: str) -> int | None:
    return None if value is None else _require_int(value, field_name)


def _optional_bool(value: Any, field_name: str) -> bool | None:
    return None if value is None else _require_bool(value, field_name)


def _optional_string_tuple(value: Any, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ProtocolParseError(f"{field_name} must be a list")
    return tuple(_require_string(item, f"{field_name}[]") for item in value)


def parse_candidate_payload(payload: Any) -> Candidate:
    candidate = _require_dict(payload)
    candidate_id = _require_int(candidate.get("candidate_id"), "candidate_id")
    ble_address = _require_string(candidate.get("ble_address"), "ble_address")
    display_name = _optional_string(candidate.get("display_name"), "display_name")
    connectable = _require_bool(candidate.get("connectable"), "connectable")
    has_hid_service = _require_bool(candidate.get("has_hid_service"), "has_hid_service")
    has_keyboard_appearance = _require_bool(
        candidate.get("has_keyboard_appearance"), "has_keyboard_appearance"
    )
    rssi = _optional_int(candidate.get("rssi"), "rssi")
    last_seen_ms = _optional_int(candidate.get("last_seen_ms"), "last_seen_ms")
    return Candidate(
        candidate_id=candidate_id,
        ble_address=ble_address,
        display_name=display_name,
        connectable=connectable,
        has_hid_service=has_hid_service,
        has_keyboard_appearance=has_keyboard_appearance,
        rssi=rssi,
        last_seen_ms=last_seen_ms,
    )


def parse_message_line(line: str) -> Message:
    """Parse one JSON line into a typed protocol message."""

    stripped = line.strip()
    if not stripped:
        raise ProtocolParseError("empty protocol line")
    try:
        payload = loads(stripped)
    except JSONDecodeError as exc:
        raise ProtocolParseError("invalid JSON payload") from exc

    data = _require_dict(payload)
    message_type = _require_string(data.get("type"), "type")

    if message_type == "hello":
        return HelloMessage(
            product=_require_string(data.get("product"), "product"),
            protocol_version=_require_int(data.get("protocol_version"), "protocol_version"),
            channel=_require_string(data.get("channel"), "channel"),
            board=_optional_string(data.get("board"), "board"),
            firmware_version=_optional_string(data.get("firmware_version"), "firmware_version"),
        )
    if message_type == "status_snapshot":
        return StatusSnapshot(
            receiver_state=_require_string(data.get("receiver_state"), "receiver_state"),
            peer_name=_optional_string(data.get("peer_name"), "peer_name"),
            peer_address=_optional_string(data.get("peer_address"), "peer_address"),
            scan_in_progress=_require_bool(data.get("scan_in_progress"), "scan_in_progress"),
            candidate_generation=_require_int(data.get("candidate_generation"), "candidate_generation"),
            candidate_count=_require_int(data.get("candidate_count"), "candidate_count"),
            battery_percent=_optional_int(data.get("battery_percent"), "battery_percent"),
            battery_supported=_optional_bool(data.get("battery_supported"), "battery_supported"),
            modifiers=_optional_string_tuple(data.get("modifiers"), "modifiers"),
            modifiers_supported=_optional_bool(data.get("modifiers_supported"), "modifiers_supported"),
            last_key=_optional_string(data.get("last_key"), "last_key"),
            last_key_supported=_optional_bool(data.get("last_key_supported"), "last_key_supported"),
            mouse_buttons=_optional_string_tuple(data.get("mouse_buttons"), "mouse_buttons"),
            mouse_buttons_supported=_optional_bool(
                data.get("mouse_buttons_supported"), "mouse_buttons_supported"
            ),
        )
    if message_type == "candidate_snapshot":
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            raise ProtocolParseError("candidates must be a list")
        return CandidateSnapshot(
            candidate_generation=_require_int(data.get("candidate_generation"), "candidate_generation"),
            candidates=[parse_candidate_payload(candidate) for candidate in candidates],
        )
    if message_type == "command":
        request_id = _require_int(data.get("request_id"), "request_id")
        name = _require_string(data.get("name"), "name")
        fields = {key: value for key, value in data.items() if key not in {"type", "request_id", "name"}}
        return CommandMessage(request_id=request_id, name=name, fields=fields)
    if message_type == "ack":
        return AckMessage(
            request_id=_require_int(data.get("request_id"), "request_id"),
            name=_require_string(data.get("name"), "name"),
            accepted=_require_bool(data.get("accepted"), "accepted"),
        )
    if message_type == "error":
        return ErrorMessage(
            request_id=_require_int(data.get("request_id"), "request_id"),
            name=_require_string(data.get("name"), "name"),
            code=_require_string(data.get("code"), "code"),
            message=_require_string(data.get("message"), "message"),
        )
    if message_type == "event":
        name = _require_string(data.get("name"), "name")
        fields = {key: value for key, value in data.items() if key not in {"type", "name"}}
        return EventMessage(name=name, fields=fields)

    raise ProtocolParseError(f"unsupported message type: {message_type}")
