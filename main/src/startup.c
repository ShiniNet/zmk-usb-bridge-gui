#include "zmk_usb_bridge_gui/ble_scan.h"
#include "zmk_usb_bridge_gui/startup.h"

#include "zmk_usb_bridge_gui/protocol.h"
#include "zmk_usb_bridge_gui/runtime_state.h"
#include "zmk_usb_bridge_gui/usb_channel.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(zubg_startup, LOG_LEVEL_INF);

#define BOOT_SNAPSHOT_RETRY_MS 250

static void emit_boot_snapshot(void)
{
    const struct zmk_usb_bridge_gui_state *state =
        zmk_usb_bridge_gui_state_get();

    zmk_usb_bridge_gui_protocol_emit_hello();
    zmk_usb_bridge_gui_protocol_emit_status_snapshot(state);
    zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(state);
}

void zmk_usb_bridge_gui_startup_run(void)
{
    char line_buffer[CONFIG_ZMK_USB_BRIDGE_GUI_PROTOCOL_BUFFER_SIZE];
    size_t line_length = 0U;
    bool boot_snapshot_sent = false;
    bool discard_line = false;
    bool previous_gui_ready = false;
    bool host_command_seen = false;
    int64_t next_boot_snapshot_at_ms = 0;
    int err;

    zmk_usb_bridge_gui_state_init();
    err = zmk_usb_bridge_gui_ble_init();
    if (err != 0) {
        LOG_ERR("Bluetooth init failed: %d", err);
    }

    err = zmk_usb_bridge_gui_usb_channel_init();
    if (err != 0) {
        LOG_ERR("USB channel init failed: %d", err);
        return;
    }

    zmk_usb_bridge_gui_usb_channel_write_log_line(
        "zmk-usb-bridge-gui log channel ready");

    while (true) {
        unsigned char byte = 0U;
        bool gui_ready = zmk_usb_bridge_gui_usb_channel_gui_ready();

        if (gui_ready != previous_gui_ready) {
            zmk_usb_bridge_gui_usb_channel_write_log_line(
                gui_ready ? "gui channel ready" : "gui channel not ready");
            previous_gui_ready = gui_ready;
            boot_snapshot_sent = false;
            host_command_seen = false;
            next_boot_snapshot_at_ms = 0;
        }

        if (gui_ready &&
            (!boot_snapshot_sent ||
             (!host_command_seen && k_uptime_get() >= next_boot_snapshot_at_ms))) {
            emit_boot_snapshot();
            boot_snapshot_sent = true;
            next_boot_snapshot_at_ms = k_uptime_get() + BOOT_SNAPSHOT_RETRY_MS;
        }

        zmk_usb_bridge_gui_protocol_poll();

        if (!gui_ready) {
            boot_snapshot_sent = false;
            host_command_seen = false;
            next_boot_snapshot_at_ms = 0;
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
                    int handle_result;

                    line_buffer[line_length] = '\0';
                    handle_result = zmk_usb_bridge_gui_protocol_handle_line(line_buffer);
                    if (handle_result == 0) {
                        host_command_seen = true;
                    }
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
