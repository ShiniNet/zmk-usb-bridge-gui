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

#define ZMK_USB_BRIDGE_GUI_SCAN_WINDOW_MS 10000
#define ZMK_USB_BRIDGE_GUI_SCAN_START_DEFER_MS 50
#define ZMK_USB_BRIDGE_GUI_BLUETOOTH_INIT_TIMEOUT_MS 5000
#define ZMK_USB_BRIDGE_GUI_PROTOCOL_ONLY_SMOKE_TEST 0
#define ZMK_USB_BRIDGE_GUI_BLUETOOTH_ENABLE_ONLY_SMOKE_TEST 0
#define ZMK_USB_BRIDGE_GUI_SCAN_START_STOP_SMOKE_TEST 0
#define ZMK_USB_BRIDGE_GUI_COMPLETE_ON_FIRST_CANDIDATE 1
#define ZMK_USB_BRIDGE_GUI_SCAN_INTERVAL 0x01E0
#define ZMK_USB_BRIDGE_GUI_SCAN_WINDOW 0x0030
#define ZMK_USB_BRIDGE_GUI_SCAN_NAME_TEXT_SIZE 64
#define ZMK_USB_BRIDGE_GUI_BLE_INIT_STACK_SIZE 4096
#define ZMK_USB_BRIDGE_GUI_BLE_INIT_THREAD_PRIORITY 10
#define ZMK_USB_BRIDGE_GUI_SCAN_SUPERVISOR_STACK_SIZE 1024
#define ZMK_USB_BRIDGE_GUI_SCAN_SUPERVISOR_THREAD_PRIORITY 8
#define ZMK_USB_BRIDGE_GUI_SCAN_SUPERVISOR_INTERVAL_MS 50
#define ZMK_USB_BRIDGE_GUI_SCAN_OBSERVATIONS_PER_POLL 8
#define ZMK_USB_BRIDGE_GUI_SCAN_OBSERVATION_FILTER_SIZE 24
#define ZMK_USB_BRIDGE_GUI_SCAN_OBSERVATION_MIN_INTERVAL_MS 250

struct scan_observation {
    char ble_address[BT_ADDR_LE_STR_LEN];
    char display_name[ZMK_USB_BRIDGE_GUI_SCAN_NAME_TEXT_SIZE];
    bool has_display_name;
    bool connectable;
    bool has_hid_service;
    bool has_keyboard_appearance;
    int8_t rssi;
    int64_t last_seen_ms;
};

struct scan_parse_context {
    char display_name[ZMK_USB_BRIDGE_GUI_SCAN_NAME_TEXT_SIZE];
    size_t display_name_length;
    bool has_display_name;
    bool has_hid_service;
    bool has_keyboard_appearance;
};

struct scan_observation_filter_record {
    char ble_address[BT_ADDR_LE_STR_LEN];
    char display_name[ZMK_USB_BRIDGE_GUI_SCAN_NAME_TEXT_SIZE];
    bool in_use;
    bool has_display_name;
    bool connectable;
    bool has_hid_service;
    bool has_keyboard_appearance;
    int64_t last_queued_ms;
};

K_MSGQ_DEFINE(scan_observation_queue, sizeof(struct scan_observation), 48, 4);
K_SEM_DEFINE(bluetooth_init_request, 0, 1);
K_THREAD_STACK_DEFINE(
    bluetooth_init_stack,
    ZMK_USB_BRIDGE_GUI_BLE_INIT_STACK_SIZE);
K_THREAD_STACK_DEFINE(
    scan_supervisor_stack,
    ZMK_USB_BRIDGE_GUI_SCAN_SUPERVISOR_STACK_SIZE);

static bool bluetooth_ready;
static bool bluetooth_init_started;
static bool bluetooth_init_worker_started;
static bool bluetooth_failed;
static bool scan_active;
static bool scan_start_pending;
static bool scan_start_worker_requested;
static bool scan_stop_worker_requested;
static bool scan_start_failed;
static bool scan_supervisor_started;
static int64_t scan_deadline_ms;
static int64_t scan_start_not_before_ms;
static struct k_thread bluetooth_init_thread;
static struct k_thread scan_supervisor_thread;
static struct scan_observation_filter_record
    observation_filter[ZMK_USB_BRIDGE_GUI_SCAN_OBSERVATION_FILTER_SIZE];

static void complete_scan(const char *result, const char *code);
static int begin_scan_now(void);
static void prepare_scan_start(void);
static void mark_scan_running(void);
static void log_scan_status(const char *message, int err);
static void bluetooth_init_worker(void *unused_a, void *unused_b, void *unused_c);
static void start_bluetooth_init_worker(void);
static void scan_supervisor_worker(void *unused_a, void *unused_b, void *unused_c);
static void start_scan_supervisor(void);

static void bluetooth_init_worker(void *unused_a, void *unused_b, void *unused_c)
{
    ARG_UNUSED(unused_a);
    ARG_UNUSED(unused_b);
    ARG_UNUSED(unused_c);

    while (true) {
        int err;

        k_sem_take(&bluetooth_init_request, K_FOREVER);

        if (!bluetooth_ready && !bluetooth_failed && bluetooth_init_started) {
            bluetooth_init_started = false;
            err = bt_enable(NULL);
            if (err == 0 || err == -EALREADY) {
                bluetooth_ready = true;
                log_scan_status(err == 0 ? "bluetooth ready" : "bluetooth already ready", 0);
            } else {
                bluetooth_failed = true;
                bluetooth_ready = false;
                log_scan_status("bt_enable failed", err);
            }
        }

        if (bluetooth_ready && scan_start_worker_requested) {
#if ZMK_USB_BRIDGE_GUI_BLUETOOTH_ENABLE_ONLY_SMOKE_TEST
            scan_start_worker_requested = false;
            log_scan_status("bluetooth-enable smoke complete", 0);
            complete_scan("ok", NULL);
            continue;
#endif

            err = begin_scan_now();
            scan_start_worker_requested = false;
            if (err != 0) {
                scan_start_failed = true;
                continue;
            }

#if ZMK_USB_BRIDGE_GUI_SCAN_START_STOP_SMOKE_TEST
            err = bt_le_scan_stop();
            if (err != 0 && err != -EALREADY) {
                log_scan_status("start-stop smoke stop failed", err);
                complete_scan("error", "scan_stop_failed");
                continue;
            }

            log_scan_status("start-stop smoke complete", 0);
            complete_scan("ok", NULL);
            continue;
#endif

            if (scan_start_pending) {
                mark_scan_running();
            } else {
                (void)bt_le_scan_stop();
            }
        }

        if (scan_stop_worker_requested) {
            err = bt_le_scan_stop();
            scan_stop_worker_requested = false;
            if (err != 0 && err != -EALREADY) {
                log_scan_status("stop failed", err);
            }
        }
    }
}

static void start_bluetooth_init_worker(void)
{
    if (bluetooth_init_worker_started) {
        return;
    }

    bluetooth_init_worker_started = true;
    k_thread_create(
        &bluetooth_init_thread,
        bluetooth_init_stack,
        K_THREAD_STACK_SIZEOF(bluetooth_init_stack),
        bluetooth_init_worker,
        NULL,
        NULL,
        NULL,
        ZMK_USB_BRIDGE_GUI_BLE_INIT_THREAD_PRIORITY,
        0,
        K_NO_WAIT);
}

static void scan_supervisor_worker(void *unused_a, void *unused_b, void *unused_c)
{
    ARG_UNUSED(unused_a);
    ARG_UNUSED(unused_b);
    ARG_UNUSED(unused_c);

    while (true) {
        int64_t now_ms = k_uptime_get();

        if (scan_start_pending && !scan_active && scan_deadline_ms > 0 &&
            now_ms >= scan_deadline_ms) {
            complete_scan(
                "error",
                bluetooth_ready ? "scan_start_timeout" : "bluetooth_init_timeout");
        } else if (scan_active && scan_deadline_ms > 0 &&
                   now_ms >= scan_deadline_ms) {
            complete_scan("ok", NULL);
        }

        k_msleep(ZMK_USB_BRIDGE_GUI_SCAN_SUPERVISOR_INTERVAL_MS);
    }
}

static void start_scan_supervisor(void)
{
    if (scan_supervisor_started) {
        return;
    }

    scan_supervisor_started = true;
    k_thread_create(
        &scan_supervisor_thread,
        scan_supervisor_stack,
        K_THREAD_STACK_SIZEOF(scan_supervisor_stack),
        scan_supervisor_worker,
        NULL,
        NULL,
        NULL,
        ZMK_USB_BRIDGE_GUI_SCAN_SUPERVISOR_THREAD_PRIORITY,
        0,
        K_NO_WAIT);
}

static bool adv_type_is_connectable(uint8_t adv_type)
{
    return adv_type == BT_GAP_ADV_TYPE_ADV_IND || adv_type == BT_GAP_ADV_TYPE_ADV_DIRECT_IND;
}

static void clear_observation_filter(void)
{
    memset(observation_filter, 0, sizeof(observation_filter));
}

static bool observation_has_public_signal(const struct scan_observation *observation)
{
    return observation != NULL &&
           (observation->connectable || observation->has_display_name ||
            observation->has_hid_service || observation->has_keyboard_appearance);
}

static struct scan_observation_filter_record *find_observation_filter_record(
    const char *ble_address)
{
    if (ble_address == NULL || ble_address[0] == '\0') {
        return NULL;
    }

    for (size_t index = 0U; index < ARRAY_SIZE(observation_filter); ++index) {
        if (observation_filter[index].in_use &&
            strcmp(observation_filter[index].ble_address, ble_address) == 0) {
            return &observation_filter[index];
        }
    }

    return NULL;
}

static struct scan_observation_filter_record *allocate_observation_filter_record(
    const char *ble_address)
{
    struct scan_observation_filter_record *oldest = NULL;

    if (ble_address == NULL || ble_address[0] == '\0') {
        return NULL;
    }

    for (size_t index = 0U; index < ARRAY_SIZE(observation_filter); ++index) {
        if (!observation_filter[index].in_use) {
            oldest = &observation_filter[index];
            break;
        }

        if (oldest == NULL ||
            observation_filter[index].last_queued_ms < oldest->last_queued_ms) {
            oldest = &observation_filter[index];
        }
    }

    if (oldest == NULL) {
        return NULL;
    }

    memset(oldest, 0, sizeof(*oldest));
    oldest->in_use = true;
    snprintk(oldest->ble_address, sizeof(oldest->ble_address), "%s", ble_address);
    return oldest;
}

static struct scan_observation_filter_record *get_observation_filter_record(
    const char *ble_address)
{
    struct scan_observation_filter_record *record =
        find_observation_filter_record(ble_address);

    return record != NULL ? record : allocate_observation_filter_record(ble_address);
}

static bool observation_adds_signal(
    const struct scan_observation_filter_record *record,
    const struct scan_observation *observation)
{
    if (record == NULL || observation == NULL) {
        return false;
    }

    if (observation->connectable && !record->connectable) {
        return true;
    }

    if (observation->has_hid_service && !record->has_hid_service) {
        return true;
    }

    if (observation->has_keyboard_appearance && !record->has_keyboard_appearance) {
        return true;
    }

    if (observation->has_display_name &&
        (!record->has_display_name ||
         strcmp(record->display_name, observation->display_name) != 0)) {
        return true;
    }

    return false;
}

static bool observation_should_queue(
    const struct scan_observation_filter_record *record,
    const struct scan_observation *observation)
{
    if (!observation_has_public_signal(observation) || record == NULL) {
        return false;
    }

    if (observation_adds_signal(record, observation)) {
        return true;
    }

    return observation->last_seen_ms - record->last_queued_ms >=
           ZMK_USB_BRIDGE_GUI_SCAN_OBSERVATION_MIN_INTERVAL_MS;
}

static void remember_queued_observation(
    struct scan_observation_filter_record *record,
    const struct scan_observation *observation)
{
    if (record == NULL || observation == NULL) {
        return;
    }

    if (observation->connectable) {
        record->connectable = true;
    }
    if (observation->has_hid_service) {
        record->has_hid_service = true;
    }
    if (observation->has_keyboard_appearance) {
        record->has_keyboard_appearance = true;
    }
    if (observation->has_display_name) {
        snprintk(
            record->display_name,
            sizeof(record->display_name),
            "%s",
            observation->display_name);
        record->has_display_name = true;
    }
    record->last_queued_ms = observation->last_seen_ms;
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
    struct scan_observation_filter_record *filter_record;
    struct net_buf_simple ad_copy;

    if ((!scan_active && !scan_start_pending) || addr == NULL || ad == NULL) {
        return;
    }

    bt_addr_le_to_str(addr, observation.ble_address, sizeof(observation.ble_address));
    observation.connectable = adv_type_is_connectable(adv_type);
    observation.rssi = rssi;
    observation.last_seen_ms = k_uptime_get();

    ad_copy = *ad;
    bt_data_parse(&ad_copy, data_parse_cb, &context);
    if (context.has_display_name) {
        memcpy(observation.display_name, context.display_name, sizeof(observation.display_name));
        observation.has_display_name = true;
    }
    observation.has_hid_service = context.has_hid_service;
    observation.has_keyboard_appearance = context.has_keyboard_appearance;

    if (!observation_has_public_signal(&observation) ||
        k_msgq_num_free_get(&scan_observation_queue) == 0U) {
        return;
    }

    filter_record = get_observation_filter_record(observation.ble_address);
    if (!observation_should_queue(filter_record, &observation)) {
        return;
    }

    if (k_msgq_put(&scan_observation_queue, &observation, K_NO_WAIT) == 0) {
        remember_queued_observation(filter_record, &observation);
    }
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

static int begin_scan_now(void)
{
    static const struct bt_le_scan_param scan_param = {
        .type = BT_LE_SCAN_TYPE_PASSIVE,
        .options = BT_LE_SCAN_OPT_FILTER_DUPLICATE,
        .interval = ZMK_USB_BRIDGE_GUI_SCAN_INTERVAL,
        .window = ZMK_USB_BRIDGE_GUI_SCAN_WINDOW,
    };
    int err;

    err = bt_le_scan_start(&scan_param, device_found);
    if (err != 0) {
        log_scan_status("start failed", err);
        return err;
    }

    return 0;
}

static void prepare_scan_start(void)
{
    zmk_usb_bridge_gui_state_prepare_scan();
    scan_start_pending = true;
    scan_start_worker_requested = false;
    scan_start_failed = false;
    scan_deadline_ms =
        k_uptime_get() + ZMK_USB_BRIDGE_GUI_BLUETOOTH_INIT_TIMEOUT_MS;
    scan_start_not_before_ms =
        k_uptime_get() + ZMK_USB_BRIDGE_GUI_SCAN_START_DEFER_MS;
}

static void mark_scan_running(void)
{
    scan_active = true;
    scan_start_pending = false;
    scan_deadline_ms = k_uptime_get() + ZMK_USB_BRIDGE_GUI_SCAN_WINDOW_MS;
    scan_start_not_before_ms = 0;
    log_scan_status("started", 0);
}

static void complete_scan(const char *result, const char *code)
{
    const struct zmk_usb_bridge_gui_state *state;

    if (!scan_active && !scan_start_pending) {
        return;
    }

    if (scan_active) {
        scan_stop_worker_requested = true;
        start_bluetooth_init_worker();
        k_sem_give(&bluetooth_init_request);
    }

    scan_active = false;
    scan_start_pending = false;
    scan_start_worker_requested = false;
    scan_start_failed = false;
    scan_deadline_ms = 0;
    scan_start_not_before_ms = 0;
    zmk_usb_bridge_gui_state_complete_scan();
    state = zmk_usb_bridge_gui_state_get();
    zmk_usb_bridge_gui_protocol_emit_scan_complete(
        state->candidate_generation, result, state->candidate_count, code);
}

int zmk_usb_bridge_gui_ble_init(void)
{
    if (bluetooth_ready) {
        return 0;
    }

    if (bluetooth_failed) {
        return -EIO;
    }

    if (bluetooth_init_started) {
        return -EINPROGRESS;
    }

    start_bluetooth_init_worker();
    bluetooth_init_started = true;
    k_sem_give(&bluetooth_init_request);
    return -EINPROGRESS;
}

bool zmk_usb_bridge_gui_ble_is_ready(void)
{
    return bluetooth_ready;
}

bool zmk_usb_bridge_gui_ble_has_failed(void)
{
    return bluetooth_failed;
}

int zmk_usb_bridge_gui_ble_scan_start(void)
{
    if (scan_active || scan_start_pending) {
        return -EBUSY;
    }

    k_msgq_purge(&scan_observation_queue);
    clear_observation_filter();
    start_scan_supervisor();
    prepare_scan_start();

    return 0;
}

void zmk_usb_bridge_gui_ble_scan_kick_after_response(void)
{
    if (!scan_start_pending || scan_active) {
        return;
    }

#if ZMK_USB_BRIDGE_GUI_PROTOCOL_ONLY_SMOKE_TEST
    log_scan_status("protocol-only smoke complete", 0);
    complete_scan("ok", NULL);
    return;
#endif

    if (!bluetooth_ready && !bluetooth_failed) {
        (void)zmk_usb_bridge_gui_ble_init();
        return;
    }

    if (bluetooth_ready && !scan_start_worker_requested) {
        scan_start_worker_requested = true;
        start_bluetooth_init_worker();
        k_sem_give(&bluetooth_init_request);
    }
}

void zmk_usb_bridge_gui_ble_scan_cancel(const char *result, const char *code)
{
    if (!scan_active && !scan_start_pending) {
        return;
    }

    k_msgq_purge(&scan_observation_queue);
    complete_scan(result, code);
}

void zmk_usb_bridge_gui_ble_poll(void)
{
    struct scan_observation observation;
    int processed_observations = 0;

    if (scan_start_pending && bluetooth_failed) {
        complete_scan("error", "bluetooth_init_failed");
    }

#if ZMK_USB_BRIDGE_GUI_PROTOCOL_ONLY_SMOKE_TEST
    if (scan_start_pending && !scan_active &&
        k_uptime_get() >= scan_start_not_before_ms) {
        log_scan_status("protocol-only smoke complete", 0);
        complete_scan("ok", NULL);
        return;
    }
#endif

    if (scan_start_pending && scan_start_failed) {
        scan_start_failed = false;
        complete_scan("error", "scan_start_failed");
        return;
    }

    if (scan_start_pending && !scan_active && scan_deadline_ms > 0 &&
        k_uptime_get() >= scan_deadline_ms) {
        complete_scan(
            "error",
            bluetooth_ready ? "scan_start_timeout" : "bluetooth_init_timeout");
        return;
    }

    if (scan_start_pending && !bluetooth_ready && !bluetooth_failed &&
        k_uptime_get() >= scan_start_not_before_ms) {
        int err = zmk_usb_bridge_gui_ble_init();

        if (err != 0 && err != -EINPROGRESS) {
            complete_scan("error", "bluetooth_init_failed");
            return;
        }
    }

    if (scan_start_pending && bluetooth_ready && !scan_active &&
        !scan_start_worker_requested &&
        k_uptime_get() >= scan_start_not_before_ms) {
        scan_start_worker_requested = true;
        start_bluetooth_init_worker();
        k_sem_give(&bluetooth_init_request);
    }

    if (scan_active && k_uptime_get() >= scan_deadline_ms) {
        complete_scan("ok", NULL);
        return;
    }

    while (processed_observations < ZMK_USB_BRIDGE_GUI_SCAN_OBSERVATIONS_PER_POLL &&
           k_msgq_get(&scan_observation_queue, &observation, K_NO_WAIT) == 0) {
        const struct zmk_usb_bridge_gui_candidate *candidate =
            zmk_usb_bridge_gui_state_observe_scan_candidate(
                observation.ble_address,
                observation.has_display_name ? observation.display_name : NULL,
                observation.connectable,
                observation.has_hid_service,
                observation.has_keyboard_appearance,
                observation.rssi,
                observation.last_seen_ms);

        if (candidate != NULL &&
            zmk_usb_bridge_gui_candidate_is_public(candidate)) {
            zmk_usb_bridge_gui_protocol_emit_candidate_upsert(
                zmk_usb_bridge_gui_state_get(), candidate);
#if ZMK_USB_BRIDGE_GUI_COMPLETE_ON_FIRST_CANDIDATE
            complete_scan("ok", NULL);
            return;
#endif
        }
        processed_observations++;
    }
}
