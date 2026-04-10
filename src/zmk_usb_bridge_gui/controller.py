from __future__ import annotations

from typing import Any, Callable, Mapping

from .protocol import (
    AckMessage,
    CandidateSnapshot,
    CommandMessage,
    ErrorMessage,
    EventMessage,
    HelloMessage,
    Message,
    PROTOCOL_CHANNEL,
    PROTOCOL_PRODUCT,
    PROTOCOL_VERSION,
    ProtocolParseError,
    StatusSnapshot,
    parse_candidate_payload,
)
from .serial_discovery import ReceiverPortCandidate
from .state import AppState, CandidateView, sort_public_candidates


class AppController:
    def __init__(self, *, time_fn: Callable[[], float]) -> None:
        self._time_fn = time_fn
        self.state = AppState()
        self._next_request_id = 1

    def mark_discovering(self) -> None:
        self.state.discovery_state = "discovering"
        self.state.discovery_detail = "Searching for receiver..."
        self.state.multiple_receiver_ports = ()

    def mark_receiver_not_found(self) -> None:
        self._reset_attachment()
        self.state.discovery_state = "receiver_not_found"
        self.state.discovery_detail = "Receiver not found"
        self.state.multiple_receiver_ports = ()

    def mark_multiple_receivers(self, ports: list[str]) -> None:
        self._reset_attachment()
        self.state.discovery_state = "multiple_receivers"
        self.state.discovery_detail = "Multiple receivers detected"
        self.state.multiple_receiver_ports = tuple(ports)

    def mark_discovery_error(self, detail: str) -> None:
        self._reset_attachment()
        self.state.discovery_state = "error"
        self.state.discovery_detail = detail
        self.state.last_error = detail

    def mark_attached(self, candidate: ReceiverPortCandidate) -> None:
        self.state.discovery_state = "attached"
        self.state.discovery_detail = "Receiver attached"
        self.state.attached = True
        self.state.receiver_port = candidate.port.device
        self.state.protocol_version = candidate.hello_protocol_version
        self.state.preferred_serial_number = candidate.port.serial_number
        self.state.preferred_device_path = candidate.port.location or candidate.port.device
        self.state.multiple_receiver_ports = ()
        self.state.last_error = None

    def mark_disconnected(self, detail: str) -> None:
        self._reset_attachment()
        self.state.discovery_state = "disconnected"
        self.state.discovery_detail = detail
        self.state.last_error = detail

    def build_command(self, name: str, **fields: object) -> CommandMessage:
        self.state.pending_command_names.add(name)
        self.state.pending_command_name = name
        self.state.last_error = None
        request_id = self._next_request_id
        self._next_request_id += 1
        return CommandMessage(request_id=request_id, name=name, fields=dict(fields))

    def clear_last_error_for_user_action(self) -> None:
        self.state.last_error = None

    def apply_message(self, message: Message) -> None:
        if isinstance(message, HelloMessage):
            self._apply_hello(message)
            return
        if isinstance(message, StatusSnapshot):
            self._apply_status_snapshot(message)
            return
        if isinstance(message, CandidateSnapshot):
            self._apply_candidate_snapshot(message)
            return
        if isinstance(message, AckMessage):
            self._apply_ack(message)
            return
        if isinstance(message, ErrorMessage):
            self._apply_error(message)
            return
        if isinstance(message, EventMessage):
            self._apply_event(message)
            return

    def handle_protocol_error(self, detail: str) -> None:
        self.state.last_error = f"Protocol parse error: {detail}"

    def set_last_error(self, detail: str) -> None:
        self.state.last_error = detail

    def expire_scan_watchdog(self, timeout_s: float) -> bool:
        started_at = self.state.scan_watchdog_started_at
        if started_at is None:
            return False
        if self._time_fn() - started_at < timeout_s:
            return False
        self.state.scan_watchdog_started_at = None
        if self.state.receiver_state == "scanning" or self.state.scan_in_progress:
            self.state.receiver_state = "idle"
            self.state.scan_in_progress = False
            self._clear_pending_commands()
            self.state.last_error = "Scan timed out while waiting for scan_complete; requesting resync."
            return True
        return False

    def _apply_hello(self, message: HelloMessage) -> None:
        if (
            message.product != PROTOCOL_PRODUCT
            or message.channel != PROTOCOL_CHANNEL
            or message.protocol_version != PROTOCOL_VERSION
        ):
            self.state.last_error = "Receiver hello did not match the expected GUI protocol."
            return
        self.state.protocol_version = message.protocol_version

    def _apply_status_snapshot(self, message: StatusSnapshot) -> None:
        self.state.receiver_state = message.receiver_state
        self.state.scan_in_progress = message.scan_in_progress
        self.state.peer_name = message.peer_name
        self.state.peer_address = message.peer_address
        self.state.candidate_generation = message.candidate_generation
        self._replace_telemetry_from_snapshot(message)
        if not self.state.scan_in_progress:
            self.state.scan_watchdog_started_at = None
        if self.state.last_error and message.receiver_state in {"idle", "connected"}:
            self.state.last_error = None

    def _apply_candidate_snapshot(self, message: CandidateSnapshot) -> None:
        self.state.candidate_generation = message.candidate_generation
        self.state.candidate_cache = {
            candidate.candidate_id: CandidateView.from_protocol_candidate(candidate)
            for candidate in message.candidates
        }
        self._refresh_public_candidates()

    def _apply_ack(self, message: AckMessage) -> None:
        self._clear_pending_command(message.name)
        if message.name == "scan_start":
            self.state.scan_watchdog_started_at = self._time_fn()

    def _apply_error(self, message: ErrorMessage) -> None:
        self._clear_pending_command(message.name)
        self.state.last_error = f"{message.name}: {message.code}: {message.message}"

    def _apply_event(self, message: EventMessage) -> None:
        if message.name == "scan_started":
            generation = message.fields.get("candidate_generation")
            if isinstance(generation, int):
                self.state.candidate_generation = generation
            self.state.receiver_state = "scanning"
            self.state.scan_in_progress = True
            self.state.scan_watchdog_started_at = self._time_fn()
            self.state.candidate_cache = {}
            self._refresh_public_candidates()
            return

        if message.name == "candidate_upsert":
            generation = message.fields.get("candidate_generation")
            payload = message.fields.get("candidate")
            if generation != self.state.candidate_generation or not isinstance(payload, dict):
                return
            try:
                candidate = parse_candidate_payload(payload)
            except ProtocolParseError:
                self.state.last_error = "candidate_upsert payload was malformed"
                return
            candidate_view = CandidateView.from_protocol_candidate(candidate)
            self.state.candidate_cache[candidate_view.candidate_id] = candidate_view
            self._refresh_public_candidates()
            return

        if message.name == "scan_complete":
            result = message.fields.get("result")
            self.state.scan_in_progress = False
            self.state.scan_watchdog_started_at = None
            if result == "stopped" and self.state.receiver_state == "scanning":
                self.state.receiver_state = "connecting"
            elif self.state.receiver_state == "scanning":
                self.state.receiver_state = "idle"
            code = message.fields.get("code")
            if result == "error":
                suffix = f" ({code})" if isinstance(code, str) else ""
                self.state.last_error = f"Scan failed{suffix}"
            return

        if message.name == "connection_state":
            state = message.fields.get("state")
            previous_state = self.state.receiver_state
            if isinstance(state, str):
                self.state.receiver_state = state
            self.state.scan_in_progress = False
            self.state.scan_watchdog_started_at = None
            if "peer_name" in message.fields:
                self.state.peer_name = message.fields.get("peer_name")
            if "peer_address" in message.fields:
                self.state.peer_address = message.fields.get("peer_address")
            if state == "idle":
                self.state.peer_name = None
                self.state.peer_address = None
                self._clear_live_telemetry()
            elif state == "connected" and previous_state != "connected":
                self._clear_live_telemetry()
            code = message.fields.get("code")
            detail = message.fields.get("message")
            if isinstance(code, str) and isinstance(detail, str):
                self.state.last_error = f"{code}: {detail}"
            return

        if message.name == "bonds_cleared":
            self.state.receiver_state = "idle"
            self.state.scan_in_progress = False
            self.state.peer_name = None
            self.state.peer_address = None
            self._clear_live_telemetry(clear_support=True)
            return

        if message.name == "telemetry_update":
            self._apply_telemetry_event(message.fields)

    def _refresh_public_candidates(self) -> None:
        candidate_list = sort_public_candidates(list(self.state.candidate_cache.values()))
        self.state.candidate_list = candidate_list
        selected_candidate_id = self.state.selected_candidate_id
        if selected_candidate_id not in {candidate.candidate_id for candidate in candidate_list}:
            self.state.selected_candidate_id = candidate_list[0].candidate_id if candidate_list else None

    def _reset_attachment(self) -> None:
        self.state.attached = False
        self.state.receiver_port = None
        self.state.protocol_version = None
        self.state.receiver_state = "idle"
        self.state.scan_in_progress = False
        self.state.peer_name = None
        self.state.peer_address = None
        self.state.candidate_generation = 0
        self.state.candidate_cache = {}
        self.state.candidate_list = []
        self.state.selected_candidate_id = None
        self._clear_pending_commands()
        self.state.scan_watchdog_started_at = None
        self._clear_live_telemetry(clear_support=True)

    def _clear_pending_command(self, name: str) -> None:
        self.state.pending_command_names.discard(name)
        self.state.pending_command_name = next(iter(self.state.pending_command_names), None)

    def _clear_pending_commands(self) -> None:
        self.state.pending_command_names.clear()
        self.state.pending_command_name = None

    def _replace_telemetry_from_snapshot(self, message: StatusSnapshot) -> None:
        self.state.battery_percent = message.battery_percent
        self.state.battery_supported = message.battery_supported
        self.state.modifiers = message.modifiers
        self.state.modifiers_supported = message.modifiers_supported
        self.state.last_key = message.last_key
        self.state.last_key_supported = message.last_key_supported
        self.state.mouse_buttons = message.mouse_buttons
        self.state.mouse_buttons_supported = message.mouse_buttons_supported

    def _apply_telemetry_event(self, fields: Mapping[str, Any]) -> None:
        try:
            if "battery_percent" in fields:
                self.state.battery_percent = self._parse_optional_int_field(fields, "battery_percent")
            if "battery_supported" in fields:
                self.state.battery_supported = self._parse_optional_bool_field(fields, "battery_supported")
            if "modifiers" in fields:
                self.state.modifiers = self._parse_optional_string_tuple_field(fields, "modifiers")
            if "modifiers_supported" in fields:
                self.state.modifiers_supported = self._parse_optional_bool_field(
                    fields, "modifiers_supported"
                )
            if "last_key" in fields:
                self.state.last_key = self._parse_optional_string_field(fields, "last_key")
            if "last_key_supported" in fields:
                self.state.last_key_supported = self._parse_optional_bool_field(
                    fields, "last_key_supported"
                )
            if "mouse_buttons" in fields:
                self.state.mouse_buttons = self._parse_optional_string_tuple_field(
                    fields, "mouse_buttons"
                )
            if "mouse_buttons_supported" in fields:
                self.state.mouse_buttons_supported = self._parse_optional_bool_field(
                    fields, "mouse_buttons_supported"
                )
        except ProtocolParseError:
            self.state.last_error = "telemetry_update payload was malformed"

    def _clear_live_telemetry(self, *, clear_support: bool = False) -> None:
        self.state.battery_percent = None
        self.state.modifiers = None
        self.state.last_key = None
        self.state.mouse_buttons = None
        if clear_support:
            self.state.battery_supported = None
            self.state.modifiers_supported = None
            self.state.last_key_supported = None
            self.state.mouse_buttons_supported = None

    @staticmethod
    def _parse_optional_bool_field(fields: Mapping[str, Any], field_name: str) -> bool | None:
        value = fields.get(field_name)
        if value is None:
            return None
        if not isinstance(value, bool):
            raise ProtocolParseError(f"{field_name} must be a boolean")
        return value

    @staticmethod
    def _parse_optional_int_field(fields: Mapping[str, Any], field_name: str) -> int | None:
        value = fields.get(field_name)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ProtocolParseError(f"{field_name} must be an integer")
        return value

    @staticmethod
    def _parse_optional_string_field(fields: Mapping[str, Any], field_name: str) -> str | None:
        value = fields.get(field_name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ProtocolParseError(f"{field_name} must be a string")
        return value

    @staticmethod
    def _parse_optional_string_tuple_field(
        fields: Mapping[str, Any], field_name: str
    ) -> tuple[str, ...] | None:
        value = fields.get(field_name)
        if value is None:
            return None
        if not isinstance(value, list):
            raise ProtocolParseError(f"{field_name} must be a list")
        members: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ProtocolParseError(f"{field_name}[] must be a string")
            members.append(item)
        return tuple(members)
