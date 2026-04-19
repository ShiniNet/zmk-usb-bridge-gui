from __future__ import annotations

import unittest

from zmk_usb_bridge_gui.controller import AppController
from zmk_usb_bridge_gui.protocol import AckMessage, Candidate, CandidateSnapshot, ErrorMessage, EventMessage, HelloMessage, StatusSnapshot


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def build_controller() -> tuple[AppController, FakeClock]:
    clock = FakeClock()
    return AppController(time_fn=clock), clock


class ControllerTests(unittest.TestCase):
    def test_hello_mismatch_sets_last_error(self) -> None:
        controller, _ = build_controller()

        controller.apply_message(HelloMessage(product="wrong-product"))

        self.assertIn("did not match the expected GUI protocol", controller.state.last_error or "")

    def test_scan_sequence_updates_candidate_list(self) -> None:
        controller, _ = build_controller()

        controller.apply_message(EventMessage(name="scan_started", fields={"candidate_generation": 8}))
        controller.apply_message(
            CandidateSnapshot(
                candidate_generation=8,
                candidates=[
                    Candidate(
                        candidate_id=3,
                        ble_address="E4:B6:69:12:34:56",
                        display_name="LaLapadGen2",
                        connectable=True,
                        has_hid_service=True,
                        has_keyboard_appearance=True,
                        rssi=-49,
                    )
                ],
            )
        )
        controller.apply_message(
            EventMessage(
                name="candidate_upsert",
                fields={
                    "candidate_generation": 8,
                    "candidate": {
                        "candidate_id": 3,
                        "ble_address": "E4:B6:69:12:34:56",
                        "display_name": "LaLapadGen2",
                        "connectable": True,
                        "has_hid_service": True,
                        "has_keyboard_appearance": True,
                        "rssi": -47,
                    },
                },
            )
        )
        controller.apply_message(
            EventMessage(
                name="scan_complete",
                fields={"candidate_generation": 8, "result": "ok", "candidate_count": 1},
            )
        )

        self.assertEqual(controller.state.receiver_state, "idle")
        self.assertFalse(controller.state.scan_in_progress)
        self.assertEqual(len(controller.state.candidate_list), 1)
        self.assertEqual(controller.state.candidate_list[0].rssi, -47)

    def test_scan_complete_stopped_clears_scanning_state(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(EventMessage(name="scan_started", fields={"candidate_generation": 4}))
        controller.apply_message(
            EventMessage(
                name="scan_complete",
                fields={"candidate_generation": 4, "result": "stopped", "candidate_count": 1},
            )
        )
        self.assertEqual(controller.state.receiver_state, "connecting")
        self.assertFalse(controller.state.scan_in_progress)

    def test_scan_complete_error_sets_last_error(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(EventMessage(name="scan_started", fields={"candidate_generation": 4}))

        controller.apply_message(
            EventMessage(
                name="scan_complete",
                fields={"candidate_generation": 4, "result": "error", "candidate_count": 0, "code": "scan_failed"},
            )
        )

        self.assertEqual(controller.state.receiver_state, "idle")
        self.assertEqual(controller.state.last_error, "Scan failed (scan_failed)")

    def test_connection_state_preserves_peer_when_fields_are_omitted(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            StatusSnapshot(
                receiver_state="connected",
                peer_name="LaLapadGen2",
                peer_address="E4:B6:69:12:34:56",
                scan_in_progress=False,
                candidate_generation=8,
                candidate_count=1,
            )
        )
        controller.apply_message(EventMessage(name="connection_state", fields={"state": "connecting"}))

        self.assertEqual(controller.state.receiver_state, "connecting")
        self.assertEqual(controller.state.peer_name, "LaLapadGen2")
        self.assertEqual(controller.state.peer_address, "E4:B6:69:12:34:56")

    def test_connection_state_discards_non_string_peer_fields(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            EventMessage(
                name="connection_state",
                fields={"state": "connected", "peer_name": 42, "peer_address": False},
            )
        )

        self.assertEqual(controller.state.receiver_state, "connected")
        self.assertIsNone(controller.state.peer_name)
        self.assertIsNone(controller.state.peer_address)

    def test_status_snapshot_clears_last_error_after_resync(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            ErrorMessage(
                request_id=7,
                name="connect_candidate",
                code="candidate_not_found",
                message="candidate_id not found",
            )
        )
        self.assertIsNotNone(controller.state.last_error)

        controller.apply_message(
            StatusSnapshot(
                receiver_state="idle",
                peer_name=None,
                peer_address=None,
                scan_in_progress=False,
                candidate_generation=8,
                candidate_count=0,
            )
        )

        self.assertIsNone(controller.state.last_error)

    def test_status_snapshot_uses_scan_in_progress_field_directly(self) -> None:
        controller, _ = build_controller()

        controller.apply_message(
            StatusSnapshot(
                receiver_state="scanning",
                peer_name=None,
                peer_address=None,
                scan_in_progress=False,
                candidate_generation=8,
                candidate_count=0,
            )
        )

        self.assertEqual(controller.state.receiver_state, "scanning")
        self.assertFalse(controller.state.scan_in_progress)

    def test_bond_erase_sequence_returns_to_idle_with_empty_candidates(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            CandidateSnapshot(
                candidate_generation=2,
                candidates=[
                    Candidate(
                        candidate_id=1,
                        ble_address="E4:B6:69:12:34:56",
                        display_name="LaLapadGen2",
                        connectable=True,
                        has_hid_service=True,
                        has_keyboard_appearance=True,
                        rssi=-49,
                    )
                ],
            )
        )
        controller.apply_message(EventMessage(name="bonds_cleared", fields={"cleared_count": 1}))
        self.assertEqual(controller.state.candidate_list, [])
        controller.apply_message(
            StatusSnapshot(
                receiver_state="idle",
                peer_name=None,
                peer_address=None,
                scan_in_progress=False,
                candidate_generation=2,
                candidate_count=0,
            )
        )
        controller.apply_message(CandidateSnapshot(candidate_generation=2, candidates=[]))

        self.assertEqual(controller.state.receiver_state, "idle")
        self.assertIsNone(controller.state.peer_name)
        self.assertEqual(controller.state.candidate_list, [])

    def test_scan_watchdog_timeout_requests_recovery(self) -> None:
        controller, clock = build_controller()
        controller.apply_message(EventMessage(name="scan_started", fields={"candidate_generation": 9}))
        clock.now += 13.0

        expired = controller.expire_scan_watchdog(12.0)

        self.assertTrue(expired)
        self.assertEqual(controller.state.receiver_state, "idle")
        self.assertIsNotNone(controller.state.last_error)

    def test_scan_watchdog_timeout_recovers_when_ack_never_arrives(self) -> None:
        controller, clock = build_controller()
        controller.build_command("scan_start")
        self.assertIn("scan_start", controller.state.pending_command_names)
        self.assertIsNotNone(controller.state.scan_watchdog_started_at)

        clock.now += 13.0
        expired = controller.expire_scan_watchdog(12.0)

        self.assertTrue(expired)
        self.assertEqual(controller.state.receiver_state, "idle")
        self.assertFalse(controller.state.scan_in_progress)
        self.assertNotIn("scan_start", controller.state.pending_command_names)
        self.assertIn("receiver response", controller.state.last_error or "")

    def test_error_message_surfaces_stale_generation(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            ErrorMessage(
                request_id=3,
                name="connect_candidate",
                code="stale_candidate_generation",
                message="candidate_generation is stale",
            )
        )

        self.assertIn("stale_candidate_generation", controller.state.last_error or "")

    def test_candidate_upsert_with_stale_generation_is_ignored(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(EventMessage(name="scan_started", fields={"candidate_generation": 8}))

        controller.apply_message(
            EventMessage(
                name="candidate_upsert",
                fields={
                    "candidate_generation": 7,
                    "candidate": {
                        "candidate_id": 3,
                        "ble_address": "E4:B6:69:12:34:56",
                        "display_name": "LaLapadGen2",
                        "connectable": True,
                        "has_hid_service": True,
                        "has_keyboard_appearance": True,
                        "rssi": -47,
                    },
                },
            )
        )

        self.assertEqual(controller.state.candidate_list, [])
        self.assertIsNone(controller.state.last_error)

    def test_connection_error_keeps_idle_state(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            EventMessage(
                name="connection_state",
                fields={"state": "idle", "code": "connect_busy", "message": "connect in progress"},
            )
        )

        self.assertEqual(controller.state.receiver_state, "idle")
        self.assertIn("connect_busy", controller.state.last_error or "")

    def test_connect_success_reaches_connected(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            EventMessage(name="connection_state", fields={"state": "connecting", "peer_name": None, "peer_address": None})
        )
        controller.apply_message(
            EventMessage(
                name="connection_state",
                fields={
                    "state": "connected",
                    "peer_name": "LaLapadGen2",
                    "peer_address": "E4:B6:69:12:34:56",
                },
            )
        )

        self.assertEqual(controller.state.receiver_state, "connected")
        self.assertEqual(controller.state.peer_name, "LaLapadGen2")

    def test_connect_failure_returns_to_idle(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            EventMessage(name="connection_state", fields={"state": "connecting", "peer_name": None, "peer_address": None})
        )
        controller.apply_message(
            EventMessage(
                name="connection_state",
                fields={"state": "idle", "code": "candidate_not_found", "message": "candidate_id not found"},
            )
        )

        self.assertEqual(controller.state.receiver_state, "idle")
        self.assertIsNone(controller.state.peer_name)
        self.assertIn("candidate_not_found", controller.state.last_error or "")

    def test_status_snapshot_applies_telemetry_fields(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            StatusSnapshot(
                receiver_state="connected",
                peer_name="LaLapadGen2",
                peer_address="E4:B6:69:12:34:56",
                scan_in_progress=False,
                candidate_generation=8,
                candidate_count=1,
                battery_percent=81,
                battery_supported=True,
                modifiers=("LALT",),
                modifiers_supported=True,
                last_key="A",
                last_key_supported=True,
                mouse_buttons=("LEFT",),
                mouse_buttons_supported=True,
            )
        )

        self.assertEqual(controller.state.battery_text, "81%")
        self.assertEqual(controller.state.modifiers_text, "LALT")
        self.assertEqual(controller.state.last_key_text, "A")
        self.assertEqual(controller.state.mouse_buttons_text, "LEFT")

    def test_telemetry_update_event_updates_live_values(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            EventMessage(name="connection_state", fields={"state": "connected", "peer_name": "LaLapadGen2"})
        )
        controller.apply_message(
            EventMessage(
                name="telemetry_update",
                fields={
                    "battery_supported": True,
                    "battery_percent": 63,
                    "modifiers_supported": True,
                    "modifiers": ["LCTRL", "LSHIFT"],
                    "last_key_supported": True,
                    "last_key": "Enter",
                    "mouse_buttons_supported": True,
                    "mouse_buttons": [],
                },
            )
        )

        self.assertEqual(controller.state.battery_text, "63%")
        self.assertEqual(controller.state.modifiers_text, "LCTRL, LSHIFT")
        self.assertEqual(controller.state.last_key_text, "Enter")
        self.assertEqual(controller.state.mouse_buttons_text, "None")

    def test_disconnect_clears_live_telemetry_values(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            StatusSnapshot(
                receiver_state="connected",
                peer_name="LaLapadGen2",
                peer_address="E4:B6:69:12:34:56",
                scan_in_progress=False,
                candidate_generation=8,
                candidate_count=1,
                battery_percent=81,
                battery_supported=True,
                modifiers=("LALT",),
                modifiers_supported=True,
            )
        )

        controller.apply_message(EventMessage(name="connection_state", fields={"state": "idle"}))

        self.assertEqual(controller.state.battery_text, "Disconnected")
        self.assertEqual(controller.state.modifiers_text, "Disconnected")
        self.assertTrue(controller.state.battery_supported)

    def test_malformed_telemetry_update_surfaces_error(self) -> None:
        controller, _ = build_controller()
        controller.apply_message(
            EventMessage(name="telemetry_update", fields={"modifiers": "not-a-list"})
        )

        self.assertIn("telemetry_update payload was malformed", controller.state.last_error or "")

    def test_multiple_pending_commands_keep_busy_until_all_are_acked(self) -> None:
        controller, _ = build_controller()
        controller.build_command("get_status")
        controller.build_command("get_candidates")

        self.assertTrue(controller.state.busy)

        controller.apply_message(AckMessage(request_id=1, name="get_status", accepted=True))
        self.assertTrue(controller.state.busy)

        controller.apply_message(AckMessage(request_id=2, name="get_candidates", accepted=True))
        self.assertFalse(controller.state.busy)

    def test_pending_command_name_tracks_latest_pending_command_deterministically(self) -> None:
        controller, _ = build_controller()
        controller.build_command("get_status")
        controller.build_command("get_candidates")

        self.assertEqual(controller.state.pending_command_name, "get_candidates")

        controller.apply_message(AckMessage(request_id=2, name="get_candidates", accepted=True))

        self.assertEqual(controller.state.pending_command_name, "get_status")


if __name__ == "__main__":
    unittest.main()
