#ifndef ZMK_USB_BRIDGE_GUI_BLE_SCAN_H_
#define ZMK_USB_BRIDGE_GUI_BLE_SCAN_H_

#include <stdbool.h>

int zmk_usb_bridge_gui_ble_init(void);
bool zmk_usb_bridge_gui_ble_is_ready(void);
bool zmk_usb_bridge_gui_ble_has_failed(void);
int zmk_usb_bridge_gui_ble_scan_start(void);
void zmk_usb_bridge_gui_ble_scan_kick_after_response(void);
void zmk_usb_bridge_gui_ble_scan_cancel(const char *result, const char *code);
void zmk_usb_bridge_gui_ble_poll(void);

#endif
