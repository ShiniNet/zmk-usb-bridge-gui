#ifndef ZMK_USB_BRIDGE_GUI_RUNTIME_STATE_H_
#define ZMK_USB_BRIDGE_GUI_RUNTIME_STATE_H_

#include <stdbool.h>

struct zmk_usb_bridge_gui_candidate {
    int candidate_id;
    const char *ble_address;
    const char *display_name;
    bool connectable;
    bool has_hid_service;
    bool has_keyboard_appearance;
    int rssi;
};

struct zmk_usb_bridge_gui_state {
    const char *receiver_state;
    const char *peer_name;
    const char *peer_address;
    bool scan_in_progress;
    int candidate_generation;
    int candidate_count;
    struct zmk_usb_bridge_gui_candidate active_candidate;
};

void zmk_usb_bridge_gui_state_init(void);
const struct zmk_usb_bridge_gui_state *zmk_usb_bridge_gui_state_get(void);
void zmk_usb_bridge_gui_state_prepare_scan(void);
void zmk_usb_bridge_gui_state_complete_scan(void);
void zmk_usb_bridge_gui_state_connect_candidate(void);
void zmk_usb_bridge_gui_state_set_connected(void);
void zmk_usb_bridge_gui_state_reset_bonds(void);
bool zmk_usb_bridge_gui_state_candidate_matches(
    int candidate_id);

#endif
