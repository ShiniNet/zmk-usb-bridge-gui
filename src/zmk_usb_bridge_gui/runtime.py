from __future__ import annotations

import time
from dataclasses import replace
from queue import Empty, SimpleQueue
from threading import Thread
from typing import Callable

from .controller import AppController
from .protocol import PROTOCOL_CHANNEL, PROTOCOL_PRODUCT, PROTOCOL_VERSION
from .serial_discovery import (
    DEFAULT_BAUDRATE,
    DiscoveryConfig,
    ReceiverPortCandidate,
    SerialDiscoveryError,
    discover_receiver_ports,
)
from .session import (
    SerialSession,
    SessionDisconnectedEvent,
    SessionMessageEvent,
    SessionOpenError,
    SessionProtocolErrorEvent,
)

DEFAULT_RECEIVER_VID_PID_ALLOWLIST = ((0x2FE3, 0x0012),)


class AppRuntime:
    def __init__(
        self,
        *,
        discover_ports: Callable[..., list[ReceiverPortCandidate]] = discover_receiver_ports,
        session_factory: Callable[[], SerialSession] = SerialSession,
        time_fn: Callable[[], float] = time.monotonic,
        discovery_config: DiscoveryConfig | None = None,
        scan_watchdog_timeout_s: float = 12.0,
    ) -> None:
        self._discover_ports = discover_ports
        self._session_factory = session_factory
        self._time_fn = time_fn
        self._scan_watchdog_timeout_s = scan_watchdog_timeout_s
        self._discovery_config = discovery_config or DiscoveryConfig(
            vid_pid_allowlist=DEFAULT_RECEIVER_VID_PID_ALLOWLIST,
            baudrate=DEFAULT_BAUDRATE,
        )
        self.controller = AppController(time_fn=time_fn)
        self._session: SerialSession | None = None
        self._next_discovery_at = 0.0
        self._discovery_results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._discovery_thread: Thread | None = None

    @property
    def state(self):
        return self.controller.state

    def tick(self) -> None:
        self._drain_discovery_results()
        self._drain_session_events()
        if self.controller.expire_scan_watchdog(self._scan_watchdog_timeout_s):
            self.refresh()
        if self.state.attached:
            return
        if self._discovery_thread is not None:
            return
        if self._time_fn() >= self._next_discovery_at:
            self._start_discovery()

    def shutdown(self) -> None:
        session = self._session
        self._session = None
        if session is not None:
            session.close()

    def retry_discovery(self) -> None:
        if self.state.attached:
            return
        self._next_discovery_at = 0.0

    def refresh(self) -> None:
        if not self.state.can_refresh:
            return
        self.controller.clear_last_error_for_user_action()
        self._send_command("get_status")
        self._send_command("get_candidates")

    def scan_start(self) -> None:
        if not self.state.can_scan:
            return
        self.controller.clear_last_error_for_user_action()
        self._send_command("scan_start")

    def bond_erase(self) -> None:
        if not self.state.can_bond_erase:
            return
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
        self.controller.clear_last_error_for_user_action()
        self._send_command(
            "connect_candidate",
            candidate_generation=self.state.candidate_generation,
            candidate_id=candidate.candidate_id,
        )

    def select_candidate(self, candidate_id: int | None) -> None:
        self.controller.state.selected_candidate_id = candidate_id

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
            candidates = self._discover_ports(discovery_config, probe_hello=True)
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
            self.controller.mark_receiver_not_found()
            self._schedule_next_discovery()
            return
        if len(gui_candidates) > 1:
            self.controller.mark_multiple_receivers([candidate.port.device for candidate in gui_candidates])
            self._schedule_next_discovery()
            return

        candidate = gui_candidates[0]
        session = self._session_factory()
        try:
            session.open(candidate.port.device, baudrate=baudrate)
        except SessionOpenError as exc:
            self.controller.mark_discovery_error(str(exc))
            self._schedule_next_discovery()
            return
        self._session = session
        self.controller.mark_attached(candidate)

    def _detach(self, detail: str) -> None:
        session = self._session
        self._session = None
        if session is not None:
            session.close()
        self.controller.mark_disconnected(detail)
        self._schedule_next_discovery()

    def _schedule_next_discovery(self) -> None:
        self._next_discovery_at = self._time_fn() + self._discovery_config.retry_interval_s

    def _build_discovery_config(self) -> DiscoveryConfig:
        return replace(
            self._discovery_config,
            preferred_serial_number=self.state.preferred_serial_number,
            preferred_device_path=self.state.preferred_device_path,
        )

    @staticmethod
    def _is_supported_gui_candidate(candidate: ReceiverPortCandidate) -> bool:
        return (
            candidate.hello_verified
            and candidate.hello_product == PROTOCOL_PRODUCT
            and candidate.hello_channel == PROTOCOL_CHANNEL
            and candidate.hello_protocol_version == PROTOCOL_VERSION
        )
