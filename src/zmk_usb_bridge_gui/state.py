from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .protocol import Candidate

MAX_PUBLIC_CANDIDATES = 12
UNNAMED_HID_DEVICE_LABEL = "Unnamed HID device"
DiscoveryState = Literal[
    "idle",
    "discovering",
    "receiver_not_found",
    "multiple_receivers",
    "attached",
    "disconnected",
    "error",
]


@dataclass(slots=True)
class CandidateView:
    candidate_id: int
    ble_address: str
    display_name: str | None
    connectable: bool
    has_hid_service: bool
    has_keyboard_appearance: bool
    rssi: int | None
    last_seen_ms: int | None = None

    @property
    def tier(self) -> str:
        return "A" if self.has_keyboard_appearance else "B"

    @property
    def display_label(self) -> str:
        return self.display_name or UNNAMED_HID_DEVICE_LABEL

    @property
    def tier_label(self) -> str:
        if self.has_keyboard_appearance:
            return "Tier A"
        return "Tier B (keyboard appearance unverified)"

    @classmethod
    def from_protocol_candidate(cls, candidate: Candidate) -> "CandidateView":
        return cls(
            candidate_id=candidate.candidate_id,
            ble_address=candidate.ble_address,
            display_name=candidate.display_name,
            connectable=candidate.connectable,
            has_hid_service=candidate.has_hid_service,
            has_keyboard_appearance=candidate.has_keyboard_appearance,
            rssi=candidate.rssi,
            last_seen_ms=candidate.last_seen_ms,
        )


def candidate_is_public(candidate: CandidateView) -> bool:
    if not candidate.connectable:
        return False
    if not candidate.has_hid_service:
        return False
    return candidate.has_keyboard_appearance or candidate.display_name is not None


def sort_public_candidates(candidates: list[CandidateView]) -> list[CandidateView]:
    public_candidates = [candidate for candidate in candidates if candidate_is_public(candidate)]
    public_candidates.sort(
        key=lambda candidate: (
            0 if candidate.has_keyboard_appearance else 1,
            -(candidate.rssi if candidate.rssi is not None else -9999),
            -(candidate.last_seen_ms if candidate.last_seen_ms is not None else -1),
            0 if candidate.display_name is not None else 1,
            candidate.ble_address.lower(),
        )
    )
    return public_candidates[:MAX_PUBLIC_CANDIDATES]


@dataclass(slots=True)
class AppState:
    discovery_state: DiscoveryState = "idle"
    discovery_detail: str = "Idle"
    receiver_port: str | None = None
    protocol_version: int | None = None
    receiver_state: str = "idle"
    scan_in_progress: bool = False
    peer_name: str | None = None
    peer_address: str | None = None
    candidate_generation: int = 0
    candidate_cache: dict[int, CandidateView] = field(default_factory=dict)
    candidate_list: list[CandidateView] = field(default_factory=list)
    selected_candidate_id: int | None = None
    last_error: str | None = None
    pending_command_name: str | None = None
    pending_command_names: set[str] = field(default_factory=set)
    attached: bool = False
    multiple_receiver_ports: tuple[str, ...] = ()
    preferred_serial_number: str | None = None
    preferred_device_path: str | None = None
    scan_watchdog_started_at: float | None = None

    @property
    def busy(self) -> bool:
        return bool(self.pending_command_names) or self.receiver_state in {"scanning", "connecting"}

    @property
    def selected_candidate(self) -> CandidateView | None:
        if self.selected_candidate_id is None:
            return None
        return self.candidate_cache.get(self.selected_candidate_id)
