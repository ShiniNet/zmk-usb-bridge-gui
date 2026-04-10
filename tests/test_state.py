from __future__ import annotations

import unittest

from zmk_usb_bridge_gui.state import AppState, CandidateView, MAX_PUBLIC_CANDIDATES, sort_public_candidates


class StateTests(unittest.TestCase):
    def test_candidate_sorting_and_limit_follow_policy(self) -> None:
        candidates = [
            CandidateView(1, "AA", "TierA-strong", True, True, True, -30, 900),
            CandidateView(2, "BB", "TierA-weak", True, True, True, -40, 1000),
            CandidateView(3, "CC", "TierB-strong", True, True, False, -20, 1100),
            CandidateView(4, "DD", None, True, True, False, -10, 1200),
        ]
        candidates.extend(
            CandidateView(
                candidate_id=10 + index,
                ble_address=f"E4:B6:69:12:34:{index:02X}",
                display_name=f"Keyboard {index}",
                connectable=True,
                has_hid_service=True,
                has_keyboard_appearance=index % 2 == 0,
                rssi=-50 - index,
                last_seen_ms=500 - index,
            )
            for index in range(20)
        )

        sorted_candidates = sort_public_candidates(candidates)

        self.assertEqual(len(sorted_candidates), MAX_PUBLIC_CANDIDATES)
        self.assertEqual(sorted_candidates[0].display_label, "TierA-strong")
        self.assertEqual(sorted_candidates[1].display_label, "TierA-weak")
        self.assertEqual(sorted_candidates[2].display_label, "Keyboard 0")
        self.assertNotIn("Unnamed HID device", [candidate.display_label for candidate in sorted_candidates])

    def test_control_enablement_follows_receiver_state(self) -> None:
        candidate = CandidateView(3, "E4:B6:69:12:34:56", "LaLapadGen2", True, True, True, -49, 1234)
        state = AppState(
            attached=True,
            candidate_cache={3: candidate},
            selected_candidate_id=3,
        )

        self.assertTrue(state.can_scan)
        self.assertTrue(state.can_refresh)
        self.assertTrue(state.can_connect_selected)
        self.assertTrue(state.can_bond_erase)
        self.assertFalse(state.can_retry)

        state.receiver_state = "connected"
        self.assertFalse(state.can_connect_selected)
        self.assertTrue(state.can_scan)
        self.assertTrue(state.can_refresh)
        self.assertTrue(state.can_bond_erase)

        state.receiver_state = "scanning"
        self.assertFalse(state.can_scan)
        self.assertFalse(state.can_refresh)
        self.assertFalse(state.can_connect_selected)
        self.assertFalse(state.can_bond_erase)

        state.attached = False
        state.receiver_state = "idle"
        self.assertFalse(state.can_scan)
        self.assertFalse(state.can_refresh)
        self.assertFalse(state.can_connect_selected)
        self.assertFalse(state.can_bond_erase)
        self.assertTrue(state.can_retry)


if __name__ == "__main__":
    unittest.main()
