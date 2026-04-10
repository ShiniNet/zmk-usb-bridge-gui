#include "zmk_usb_bridge_gui/runtime_state.h"

#include <stddef.h>

static struct zmk_usb_bridge_gui_state runtime_state;

#define STUB_SCAN_CANDIDATE_COUNT 3

static const struct zmk_usb_bridge_gui_candidate stub_scan_candidates[STUB_SCAN_CANDIDATE_COUNT] = {
    {
        .candidate_id = 1,
        .ble_address = "E4:B6:69:12:34:56",
        .display_name = "LaLapadGen2",
        .connectable = true,
        .has_hid_service = true,
        .has_keyboard_appearance = true,
        .rssi = -49,
        .last_seen_ms = 1320,
    },
    {
        .candidate_id = 2,
        .ble_address = "F1:82:31:AB:CD:02",
        .display_name = "ZMK Split",
        .connectable = true,
        .has_hid_service = true,
        .has_keyboard_appearance = false,
        .rssi = -61,
        .last_seen_ms = 1280,
    },
    {
        .candidate_id = 3,
        .ble_address = "D0:77:AA:44:55:66",
        .display_name = NULL,
        .connectable = false,
        .has_hid_service = true,
        .has_keyboard_appearance = false,
        .rssi = -72,
        .last_seen_ms = 1200,
    },
};

static void clear_stub_telemetry(void)
{
    runtime_state.battery_supported = true;
    runtime_state.battery_percent = -1;
    runtime_state.modifiers_supported = true;
    runtime_state.modifiers_reported = false;
    runtime_state.modifiers.count = 0U;
    runtime_state.last_key_supported = true;
    runtime_state.last_key = NULL;
    runtime_state.mouse_buttons_supported = true;
    runtime_state.mouse_buttons_reported = false;
    runtime_state.mouse_buttons.count = 0U;
}

static void clear_peer_connection(void)
{
    runtime_state.peer_name = NULL;
    runtime_state.peer_address = NULL;
    clear_stub_telemetry();
}

static int find_candidate_index(int candidate_id)
{
    for (int index = 0; index < runtime_state.candidate_count; ++index) {
        if (runtime_state.candidates[index].candidate_id == candidate_id) {
            return index;
        }
    }

    return -1;
}

void zmk_usb_bridge_gui_state_init(void)
{
    runtime_state.receiver_state = "idle";
    runtime_state.scan_in_progress = false;
    runtime_state.candidate_generation = 0;
    runtime_state.candidate_count = 0;
    runtime_state.active_candidate_id = -1;
    runtime_state.bonded_peer_count = 0;
    clear_peer_connection();
}

const struct zmk_usb_bridge_gui_state *zmk_usb_bridge_gui_state_get(void)
{
    return &runtime_state;
}

void zmk_usb_bridge_gui_state_prepare_scan(void)
{
    runtime_state.receiver_state = "scanning";
    runtime_state.scan_in_progress = true;
    runtime_state.candidate_generation += 1;
    runtime_state.candidate_count = 0;
    runtime_state.active_candidate_id = -1;
    clear_peer_connection();
}

bool zmk_usb_bridge_gui_state_publish_scan_candidate(void)
{
    if (!zmk_usb_bridge_gui_state_scan_has_pending_candidates()) {
        return false;
    }

    runtime_state.candidates[runtime_state.candidate_count] =
        stub_scan_candidates[runtime_state.candidate_count];
    runtime_state.candidate_count += 1;
    return true;
}

bool zmk_usb_bridge_gui_state_scan_has_pending_candidates(void)
{
    return runtime_state.candidate_count < STUB_SCAN_CANDIDATE_COUNT &&
           runtime_state.candidate_count < ZMK_USB_BRIDGE_GUI_MAX_CANDIDATES;
}

void zmk_usb_bridge_gui_state_complete_scan(void)
{
    runtime_state.receiver_state = "idle";
    runtime_state.scan_in_progress = false;
}

bool zmk_usb_bridge_gui_state_select_candidate(int candidate_id)
{
    if (find_candidate_index(candidate_id) < 0) {
        return false;
    }

    runtime_state.active_candidate_id = candidate_id;
    return true;
}

void zmk_usb_bridge_gui_state_connect_candidate(void)
{
    runtime_state.receiver_state = "connecting";
    runtime_state.scan_in_progress = false;
    clear_peer_connection();
}

void zmk_usb_bridge_gui_state_set_connected(void)
{
    const struct zmk_usb_bridge_gui_candidate *candidate =
        zmk_usb_bridge_gui_state_get_candidate_by_id(runtime_state.active_candidate_id);

    runtime_state.receiver_state = "connected";
    runtime_state.scan_in_progress = false;
    runtime_state.peer_name = candidate != NULL ? candidate->display_name : NULL;
    runtime_state.peer_address = candidate != NULL ? candidate->ble_address : NULL;
    runtime_state.bonded_peer_count = candidate != NULL ? 1 : 0;
    runtime_state.battery_supported = true;
    runtime_state.battery_percent = 84;
    runtime_state.modifiers_supported = true;
    runtime_state.modifiers_reported = true;
    runtime_state.modifiers.count = 0U;
    runtime_state.last_key_supported = true;
    runtime_state.last_key = "A";
    runtime_state.mouse_buttons_supported = true;
    runtime_state.mouse_buttons_reported = true;
    runtime_state.mouse_buttons.count = 0U;
}

int zmk_usb_bridge_gui_state_reset_bonds(void)
{
    int cleared_count = runtime_state.bonded_peer_count;

    runtime_state.receiver_state = "idle";
    runtime_state.scan_in_progress = false;
    runtime_state.candidate_count = 0;
    runtime_state.active_candidate_id = -1;
    runtime_state.bonded_peer_count = 0;
    clear_peer_connection();
    return cleared_count;
}

const struct zmk_usb_bridge_gui_candidate *zmk_usb_bridge_gui_state_get_candidate_by_index(
    size_t index)
{
    if (index >= (size_t)runtime_state.candidate_count) {
        return NULL;
    }

    return &runtime_state.candidates[index];
}

const struct zmk_usb_bridge_gui_candidate *zmk_usb_bridge_gui_state_get_candidate_by_id(
    int candidate_id)
{
    int candidate_index = find_candidate_index(candidate_id);

    if (candidate_index < 0) {
        return NULL;
    }

    return &runtime_state.candidates[candidate_index];
}
