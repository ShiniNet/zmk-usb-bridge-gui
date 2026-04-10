#ifndef ZMK_USB_BRIDGE_GUI_RUNTIME_STATE_H_
#define ZMK_USB_BRIDGE_GUI_RUNTIME_STATE_H_

#include <stdbool.h>
#include <stddef.h>

#define ZMK_USB_BRIDGE_GUI_MAX_CANDIDATES 12
#define ZMK_USB_BRIDGE_GUI_MAX_TELEMETRY_ITEMS 8

struct zmk_usb_bridge_gui_candidate {
    int candidate_id;
    const char *ble_address;
    const char *display_name;
    bool connectable;
    bool has_hid_service;
    bool has_keyboard_appearance;
    int rssi;
    int last_seen_ms;
};

struct zmk_usb_bridge_gui_string_list {
    const char *items[ZMK_USB_BRIDGE_GUI_MAX_TELEMETRY_ITEMS];
    size_t count;
};

struct zmk_usb_bridge_gui_state {
    const char *receiver_state;
    const char *peer_name;
    const char *peer_address;
    bool scan_in_progress;
    int candidate_generation;
    int candidate_count;
    bool battery_supported;
    int battery_percent;
    bool modifiers_supported;
    bool modifiers_reported;
    struct zmk_usb_bridge_gui_string_list modifiers;
    bool last_key_supported;
    const char *last_key;
    bool mouse_buttons_supported;
    bool mouse_buttons_reported;
    struct zmk_usb_bridge_gui_string_list mouse_buttons;
    struct zmk_usb_bridge_gui_candidate candidates[ZMK_USB_BRIDGE_GUI_MAX_CANDIDATES];
    int active_candidate_id;
    int bonded_peer_count;
};

void zmk_usb_bridge_gui_state_init(void);
const struct zmk_usb_bridge_gui_state *zmk_usb_bridge_gui_state_get(void);
void zmk_usb_bridge_gui_state_prepare_scan(void);
void zmk_usb_bridge_gui_state_complete_scan(void);
const struct zmk_usb_bridge_gui_candidate *zmk_usb_bridge_gui_state_observe_scan_candidate(
    const char *ble_address,
    const char *display_name,
    bool connectable,
    bool has_hid_service,
    bool has_keyboard_appearance,
    int rssi,
    int last_seen_ms);
bool zmk_usb_bridge_gui_state_select_candidate(int candidate_id);
void zmk_usb_bridge_gui_state_connect_candidate(void);
void zmk_usb_bridge_gui_state_set_connected(void);
int zmk_usb_bridge_gui_state_reset_bonds(void);
const struct zmk_usb_bridge_gui_candidate *zmk_usb_bridge_gui_state_get_candidate_by_index(
    size_t index);
const struct zmk_usb_bridge_gui_candidate *zmk_usb_bridge_gui_state_get_candidate_by_id(
    int candidate_id);

#endif
