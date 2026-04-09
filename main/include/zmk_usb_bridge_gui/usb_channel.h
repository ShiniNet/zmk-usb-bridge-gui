#ifndef ZMK_USB_BRIDGE_GUI_USB_CHANNEL_H_
#define ZMK_USB_BRIDGE_GUI_USB_CHANNEL_H_

#include <stdbool.h>
#include <stddef.h>

int zmk_usb_bridge_gui_usb_channel_init(void);
bool zmk_usb_bridge_gui_usb_channel_gui_ready(void);
void zmk_usb_bridge_gui_usb_channel_write_gui_line(const char *line);
void zmk_usb_bridge_gui_usb_channel_write_log_line(const char *line);
int zmk_usb_bridge_gui_usb_channel_poll_gui_byte(unsigned char *byte);

#endif
