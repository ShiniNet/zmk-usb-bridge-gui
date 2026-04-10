#ifndef ZMK_USB_BRIDGE_GUI_PROTOCOL_H_
#define ZMK_USB_BRIDGE_GUI_PROTOCOL_H_

#include <stddef.h>

struct zmk_usb_bridge_gui_state;
struct zmk_usb_bridge_gui_candidate;

void zmk_usb_bridge_gui_protocol_emit_hello(void);
void zmk_usb_bridge_gui_protocol_emit_status_snapshot(
    const struct zmk_usb_bridge_gui_state *state);
void zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(
    const struct zmk_usb_bridge_gui_state *state);
void zmk_usb_bridge_gui_protocol_emit_scan_started(int candidate_generation);
void zmk_usb_bridge_gui_protocol_emit_candidate_upsert(
    const struct zmk_usb_bridge_gui_state *state,
    const struct zmk_usb_bridge_gui_candidate *candidate);
void zmk_usb_bridge_gui_protocol_emit_scan_complete(
    int candidate_generation,
    const char *result,
    int candidate_count,
    const char *code);
void zmk_usb_bridge_gui_protocol_emit_connection_state(
    const char *state,
    const char *peer_name,
    const char *peer_address,
    const char *code,
    const char *message);
void zmk_usb_bridge_gui_protocol_emit_telemetry_update(
    const struct zmk_usb_bridge_gui_state *state);
void zmk_usb_bridge_gui_protocol_emit_bonds_cleared(int cleared_count);
void zmk_usb_bridge_gui_protocol_emit_ack(int request_id, const char *name);
void zmk_usb_bridge_gui_protocol_emit_error(
    int request_id,
    const char *name,
    const char *code,
    const char *message);
int zmk_usb_bridge_gui_protocol_handle_line(const char *line);
void zmk_usb_bridge_gui_protocol_poll(void);

#endif
