#include "zmk_usb_bridge_gui/ble_scan.h"

#include "zmk_usb_bridge_gui/protocol.h"
#include "zmk_usb_bridge_gui/runtime_state.h"
#include "zmk_usb_bridge_gui/usb_channel.h"

#include <errno.h>
#include <string.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#define ZMK_USB_BRIDGE_GUI_SCAN_WINDOW_MS 8000
#define ZMK_USB_BRIDGE_GUI_SCAN_NAME_TEXT_SIZE 64

struct scan_observation {
    char ble_address[BT_ADDR_LE_STR_LEN];
    char display_name[ZMK_USB_BRIDGE_GUI_SCAN_NAME_TEXT_SIZE];
    bool has_display_name;
    bool connectable;
    bool has_hid_service;
    bool has_keyboard_appearance;
    int8_t rssi;
    int32_t last_seen_ms;
};

struct scan_parse_context {
    char display_name[ZMK_USB_BRIDGE_GUI_SCAN_NAME_TEXT_SIZE];
    size_t display_name_length;
    bool has_display_name;
    bool has_hid_service;
    bool has_keyboard_appearance;
};

K_MSGQ_DEFINE(scan_observation_queue, sizeof(struct scan_observation), 48, 4);

static bool bluetooth_ready;
static bool bluetooth_failed;
static bool scan_active;
static int64_t scan_deadline_ms;

static bool adv_type_is_connectable(uint8_t adv_type)
{
    return adv_type == BT_GAP_ADV_TYPE_ADV_IND || adv_type == BT_GAP_ADV_TYPE_ADV_DIRECT_IND;
}

static bool data_parse_cb(struct bt_data *data, void *user_data)
{
    struct scan_parse_context *context = user_data;

    switch (data->type) {
    case BT_DATA_NAME_SHORTENED:
    case BT_DATA_NAME_COMPLETE: {
        size_t copy_length;

        if (context == NULL || data->data_len == 0U) {
            return true;
        }

        copy_length = MIN((size_t)data->data_len, sizeof(context->display_name) - 1U);
        if (!context->has_display_name || copy_length > context->display_name_length) {
            memcpy(context->display_name, data->data, copy_length);
            context->display_name[copy_length] = '\0';
            context->display_name_length = copy_length;
            context->has_display_name = true;
        }
        return true;
    }
    case BT_DATA_UUID16_SOME:
    case BT_DATA_UUID16_ALL:
        if (data->data_len >= 2U) {
            for (size_t offset = 0U; offset + 1U < data->data_len; offset += 2U) {
                if (sys_get_le16(&data->data[offset]) == BT_UUID_HIDS_VAL) {
                    context->has_hid_service = true;
                    break;
                }
            }
        }
        return true;
    case BT_DATA_GAP_APPEARANCE:
        if (data->data_len >= 2U &&
            sys_get_le16(data->data) == BT_APPEARANCE_HID_KEYBOARD) {
            context->has_keyboard_appearance = true;
        }
        return true;
    default:
        return true;
    }
}

static void device_found(
    const bt_addr_le_t *addr,
    int8_t rssi,
    uint8_t adv_type,
    struct net_buf_simple *ad)
{
    struct scan_observation observation = {0};
    struct scan_parse_context context = {0};
    struct net_buf_simple ad_copy;

    if (!scan_active || addr == NULL || ad == NULL) {
        return;
    }

    bt_addr_le_to_str(addr, observation.ble_address, sizeof(observation.ble_address));
    observation.connectable = adv_type_is_connectable(adv_type);
    observation.rssi = rssi;
    observation.last_seen_ms = (int32_t)k_uptime_get();

    ad_copy = *ad;
    bt_data_parse(&ad_copy, data_parse_cb, &context);
    if (context.has_display_name) {
        memcpy(observation.display_name, context.display_name, sizeof(observation.display_name));
        observation.has_display_name = true;
    }
    observation.has_hid_service = context.has_hid_service;
    observation.has_keyboard_appearance = context.has_keyboard_appearance;

    (void)k_msgq_put(&scan_observation_queue, &observation, K_NO_WAIT);
}

static void log_scan_status(const char *message, int err)
{
    char line[96];

    if (err == 0) {
        snprintk(line, sizeof(line), "ble scan: %s", message);
    } else {
        snprintk(line, sizeof(line), "ble scan: %s (%d)", message, err);
    }
    zmk_usb_bridge_gui_usb_channel_write_log_line(line);
}

static void complete_scan(const char *result, const char *code)
{
    const struct zmk_usb_bridge_gui_state *state;
    int stop_err;

    if (!scan_active) {
        return;
    }

    stop_err = bt_le_scan_stop();
    if (stop_err != 0 && stop_err != -EALREADY) {
        log_scan_status("stop failed", stop_err);
    }

    scan_active = false;
    scan_deadline_ms = 0;
    state = zmk_usb_bridge_gui_state_get();
    zmk_usb_bridge_gui_state_complete_scan();
    state = zmk_usb_bridge_gui_state_get();
    zmk_usb_bridge_gui_protocol_emit_scan_complete(
        state->candidate_generation, result, state->candidate_count, code);
}

int zmk_usb_bridge_gui_ble_init(void)
{
    int err;

    if (bluetooth_ready) {
        return 0;
    }

    if (bluetooth_failed) {
        return -EIO;
    }

    err = bt_enable(NULL);
    if (err != 0) {
        bluetooth_failed = true;
        log_scan_status("bt_enable failed", err);
        return err;
    }

    bluetooth_ready = true;
    log_scan_status("bluetooth ready", 0);
    return 0;
}

int zmk_usb_bridge_gui_ble_scan_start(void)
{
    static const struct bt_le_scan_param scan_param = {
        .type = BT_LE_SCAN_TYPE_ACTIVE,
        .options = BT_LE_SCAN_OPT_FILTER_DUPLICATE,
        .interval = BT_GAP_SCAN_FAST_INTERVAL,
        .window = BT_GAP_SCAN_FAST_WINDOW,
    };
    int err;

    if (!bluetooth_ready) {
        return bluetooth_failed ? -EIO : -EAGAIN;
    }

    if (scan_active) {
        return -EBUSY;
    }

    k_msgq_purge(&scan_observation_queue);
    zmk_usb_bridge_gui_state_prepare_scan();
    err = bt_le_scan_start(&scan_param, device_found);
    if (err != 0) {
        zmk_usb_bridge_gui_state_complete_scan();
        log_scan_status("start failed", err);
        return err;
    }

    scan_active = true;
    scan_deadline_ms = k_uptime_get() + ZMK_USB_BRIDGE_GUI_SCAN_WINDOW_MS;
    log_scan_status("started", 0);
    return 0;
}

void zmk_usb_bridge_gui_ble_scan_cancel(const char *result, const char *code)
{
    if (!scan_active) {
        return;
    }

    k_msgq_purge(&scan_observation_queue);
    complete_scan(result, code);
}

void zmk_usb_bridge_gui_ble_poll(void)
{
    struct scan_observation observation;

    while (k_msgq_get(&scan_observation_queue, &observation, K_NO_WAIT) == 0) {
        const struct zmk_usb_bridge_gui_candidate *candidate =
            zmk_usb_bridge_gui_state_observe_scan_candidate(
                observation.ble_address,
                observation.has_display_name ? observation.display_name : NULL,
                observation.connectable,
                observation.has_hid_service,
                observation.has_keyboard_appearance,
                observation.rssi,
                observation.last_seen_ms);

        if (candidate != NULL) {
            zmk_usb_bridge_gui_protocol_emit_candidate_upsert(
                zmk_usb_bridge_gui_state_get(), candidate);
        }
    }

    if (scan_active && k_uptime_get() >= scan_deadline_ms) {
        complete_scan("ok", NULL);
    }
}
