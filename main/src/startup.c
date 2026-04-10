#include "zmk_usb_bridge_gui/startup.h"

#include "zmk_usb_bridge_gui/protocol.h"
#include "zmk_usb_bridge_gui/runtime_state.h"
#include "zmk_usb_bridge_gui/usb_channel.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(zubg_startup, LOG_LEVEL_INF);

void zmk_usb_bridge_gui_startup_run(void)
{
    char line_buffer[CONFIG_ZMK_USB_BRIDGE_GUI_PROTOCOL_BUFFER_SIZE];
    size_t line_length = 0U;
    bool boot_snapshot_sent = false;
    bool discard_line = false;
    int err;

    zmk_usb_bridge_gui_state_init();

    err = zmk_usb_bridge_gui_usb_channel_init();
    if (err != 0) {
        LOG_ERR("USB channel init failed: %d", err);
        return;
    }

    zmk_usb_bridge_gui_usb_channel_write_log_line(
        "zmk-usb-bridge-gui log channel ready");

    while (true) {
        unsigned char byte = 0U;

        if (zmk_usb_bridge_gui_usb_channel_gui_ready() && !boot_snapshot_sent) {
            const struct zmk_usb_bridge_gui_state *state =
                zmk_usb_bridge_gui_state_get();

            zmk_usb_bridge_gui_protocol_emit_hello();
            zmk_usb_bridge_gui_protocol_emit_status_snapshot(state);
            zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(state);
            boot_snapshot_sent = true;
        }

        zmk_usb_bridge_gui_protocol_poll();

        if (!zmk_usb_bridge_gui_usb_channel_gui_ready()) {
            boot_snapshot_sent = false;
            line_length = 0U;
            discard_line = false;
            k_msleep(50);
            continue;
        }

        if (zmk_usb_bridge_gui_usb_channel_poll_gui_byte(&byte) == 0) {
            if (byte == '\r') {
                continue;
            }

            if (byte == '\n') {
                if (!discard_line) {
                    line_buffer[line_length] = '\0';
                    (void)zmk_usb_bridge_gui_protocol_handle_line(line_buffer);
                }
                line_length = 0U;
                discard_line = false;
                continue;
            }

            if (discard_line) {
                continue;
            }

            if (line_length + 1U < sizeof(line_buffer)) {
                line_buffer[line_length++] = (char)byte;
            } else {
                line_length = 0U;
                discard_line = true;
            }
        } else {
            k_msleep(10);
        }
    }
}
