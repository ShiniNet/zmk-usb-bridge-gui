#include "zmk_usb_bridge_gui/runtime_state.h"

#include <stddef.h>

static struct zmk_usb_bridge_gui_state runtime_state;

static const struct zmk_usb_bridge_gui_candidate default_candidate = {
    .candidate_id = 1,
    .ble_address = "E4:B6:69:12:34:56",
    .display_name = "LaLapadGen2",
    .connectable = true,
    .has_hid_service = true,
    .has_keyboard_appearance = true,
    .rssi = -49,
};

void zmk_usb_bridge_gui_state_init(void)
{
    runtime_state.receiver_state = "idle";
    runtime_state.peer_name = NULL;
    runtime_state.peer_address = NULL;
    runtime_state.scan_in_progress = false;
    runtime_state.candidate_generation = 0;
    runtime_state.candidate_count = 0;
    runtime_state.active_candidate = default_candidate;
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
    runtime_state.peer_name = NULL;
    runtime_state.peer_address = NULL;
}

void zmk_usb_bridge_gui_state_complete_scan(void)
{
    runtime_state.receiver_state = "idle";
    runtime_state.scan_in_progress = false;
    runtime_state.candidate_count = 1;
}

void zmk_usb_bridge_gui_state_connect_candidate(void)
{
    runtime_state.receiver_state = "connecting";
    runtime_state.scan_in_progress = false;
    runtime_state.peer_name = NULL;
    runtime_state.peer_address = NULL;
}

void zmk_usb_bridge_gui_state_set_connected(void)
{
    runtime_state.receiver_state = "connected";
    runtime_state.scan_in_progress = false;
    runtime_state.peer_name = runtime_state.active_candidate.display_name;
    runtime_state.peer_address = runtime_state.active_candidate.ble_address;
}

void zmk_usb_bridge_gui_state_reset_bonds(void)
{
    runtime_state.receiver_state = "idle";
    runtime_state.peer_name = NULL;
    runtime_state.peer_address = NULL;
    runtime_state.scan_in_progress = false;
    runtime_state.candidate_count = 0;
}

bool zmk_usb_bridge_gui_state_candidate_matches(
    int candidate_id)
{
    return candidate_id == runtime_state.active_candidate.candidate_id &&
           runtime_state.candidate_count > 0;
}
