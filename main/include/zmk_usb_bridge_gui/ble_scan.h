#ifndef ZMK_USB_BRIDGE_GUI_BLE_SCAN_H_
#define ZMK_USB_BRIDGE_GUI_BLE_SCAN_H_

int zmk_usb_bridge_gui_ble_init(void);
int zmk_usb_bridge_gui_ble_scan_start(void);
void zmk_usb_bridge_gui_ble_scan_cancel(const char *result, const char *code);
void zmk_usb_bridge_gui_ble_poll(void);

#endif
