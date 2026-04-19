#ifndef ZMK_USB_BRIDGE_GUI_BLE_CONNECT_H_
#define ZMK_USB_BRIDGE_GUI_BLE_CONNECT_H_

#include <stdbool.h>

struct zmk_usb_bridge_gui_candidate;

int zmk_usb_bridge_gui_ble_connect_start(
    const struct zmk_usb_bridge_gui_candidate *candidate);
void zmk_usb_bridge_gui_ble_connect_cancel(void);
bool zmk_usb_bridge_gui_ble_connect_is_busy(void);
int zmk_usb_bridge_gui_ble_bond_erase(void);
void zmk_usb_bridge_gui_ble_connect_poll(void);

#endif
