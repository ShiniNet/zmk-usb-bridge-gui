#include "zmk_usb_bridge_gui/ble_connect.h"

#include "zmk_usb_bridge_gui/ble_scan.h"
#include "zmk_usb_bridge_gui/protocol.h"
#include "zmk_usb_bridge_gui/runtime_state.h"
#include "zmk_usb_bridge_gui/usb_channel.h"

#include <errno.h>
#include <string.h>

#include <zephyr/bluetooth/addr.h>
#include <zephyr/bluetooth/att.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#define ZMK_USB_BRIDGE_GUI_CONNECT_VALIDATE_TIMEOUT_MS 12000
#define ZMK_USB_BRIDGE_GUI_CONNECT_START_DEFER_MS 50
#define ZMK_USB_BRIDGE_GUI_CONNECT_WORKER_STACK_SIZE 4096
#define ZMK_USB_BRIDGE_GUI_CONNECT_WORKER_THREAD_PRIORITY 10
#define ZMK_USB_BRIDGE_GUI_CONNECT_MESSAGE_SIZE 96

enum connect_event_type {
    CONNECT_EVENT_CONNECTED,
    CONNECT_EVENT_FAILED,
    CONNECT_EVENT_DISCONNECTED,
};

struct connect_event {
    enum connect_event_type type;
    char code[32];
    char message[ZMK_USB_BRIDGE_GUI_CONNECT_MESSAGE_SIZE];
};

K_MSGQ_DEFINE(connect_event_queue, sizeof(struct connect_event), 8, 4);
K_SEM_DEFINE(connect_start_request, 0, 1);
K_THREAD_STACK_DEFINE(
    connect_worker_stack,
    ZMK_USB_BRIDGE_GUI_CONNECT_WORKER_STACK_SIZE);

static struct bt_conn *active_conn;
static bt_addr_le_t target_addr;
static bool pending_start;
static bool connect_worker_started;
static bool connect_start_requested;
static bool connect_started;
static bool hids_discovery_done;
static bool hids_service_found;
static bool security_done;
static bool terminal_event_queued;
static int64_t validation_deadline_ms;
static int64_t connect_start_not_before_ms;
static struct k_thread connect_worker_thread;
static struct bt_gatt_discover_params hids_discover_params;
static struct bt_uuid_16 hids_uuid = BT_UUID_INIT_16(BT_UUID_HIDS_VAL);

static void connect_worker(void *unused_a, void *unused_b, void *unused_c);
static void start_connect_worker(void);
static int start_connect_now(void);

static void queue_event(
    enum connect_event_type type,
    const char *code,
    const char *message)
{
    struct connect_event event = {
        .type = type,
    };

    if (code != NULL) {
        snprintk(event.code, sizeof(event.code), "%s", code);
    }
    if (message != NULL) {
        snprintk(event.message, sizeof(event.message), "%s", message);
    }

    (void)k_msgq_put(&connect_event_queue, &event, K_NO_WAIT);
}

static void log_connect_status(const char *message, int err)
{
    char line[128];

    if (err == 0) {
        snprintk(line, sizeof(line), "ble connect: %s", message);
    } else {
        snprintk(line, sizeof(line), "ble connect: %s (%d)", message, err);
    }
    zmk_usb_bridge_gui_usb_channel_write_log_line(line);
}

static void clear_connect_state(void)
{
    pending_start = false;
    connect_start_requested = false;
    connect_started = false;
    hids_discovery_done = false;
    hids_service_found = false;
    security_done = false;
    terminal_event_queued = false;
    validation_deadline_ms = 0;
    connect_start_not_before_ms = 0;
    (void)memset(&hids_discover_params, 0, sizeof(hids_discover_params));
}

static void connect_worker(void *unused_a, void *unused_b, void *unused_c)
{
    ARG_UNUSED(unused_a);
    ARG_UNUSED(unused_b);
    ARG_UNUSED(unused_c);

    while (true) {
        int err;

        k_sem_take(&connect_start_request, K_FOREVER);

        if (!pending_start || connect_started || active_conn != NULL) {
            connect_start_requested = false;
            continue;
        }

        if (!zmk_usb_bridge_gui_ble_is_ready()) {
            connect_start_requested = false;
            continue;
        }

        err = start_connect_now();
        connect_start_requested = false;
        if (err != 0) {
            queue_event(
                CONNECT_EVENT_FAILED,
                "connect_failed",
                "BLE connection could not be started");
        }
    }
}

static void start_connect_worker(void)
{
    if (connect_worker_started) {
        return;
    }

    connect_worker_started = true;
    k_thread_create(
        &connect_worker_thread,
        connect_worker_stack,
        K_THREAD_STACK_SIZEOF(connect_worker_stack),
        connect_worker,
        NULL,
        NULL,
        NULL,
        ZMK_USB_BRIDGE_GUI_CONNECT_WORKER_THREAD_PRIORITY,
        0,
        K_NO_WAIT);
}

static int parse_candidate_address(const char *text, bt_addr_le_t *addr)
{
    const char *type_start;
    const char *type_end;
    char address_text[BT_ADDR_STR_LEN];
    char type_text[16];
    size_t address_length;
    size_t type_length;

    if (text == NULL || addr == NULL) {
        return -EINVAL;
    }

    type_start = strchr(text, '(');
    type_end = strchr(text, ')');
    if (type_start == NULL || type_end == NULL || type_end <= type_start) {
        return -EINVAL;
    }

    address_length = (size_t)(type_start - text);
    while (address_length > 0U && text[address_length - 1U] == ' ') {
        address_length -= 1U;
    }
    type_length = (size_t)(type_end - type_start - 1);
    if (address_length >= sizeof(address_text) || type_length >= sizeof(type_text)) {
        return -EINVAL;
    }

    memcpy(address_text, text, address_length);
    address_text[address_length] = '\0';
    memcpy(type_text, type_start + 1, type_length);
    type_text[type_length] = '\0';

    return bt_addr_le_from_str(address_text, type_text, addr);
}

static void unref_active_conn(void)
{
    if (active_conn == NULL) {
        return;
    }

    bt_conn_unref(active_conn);
    active_conn = NULL;
}

static void fail_active_connection(const char *code, const char *message)
{
    if (terminal_event_queued) {
        return;
    }

    terminal_event_queued = true;
    queue_event(CONNECT_EVENT_FAILED, code, message);
    if (active_conn != NULL) {
        (void)bt_conn_disconnect(active_conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
    }
}

static void maybe_complete_connection_validation(void)
{
    if (terminal_event_queued || active_conn == NULL) {
        return;
    }

    if (!hids_discovery_done || !security_done) {
        return;
    }

    if (!hids_service_found) {
        fail_active_connection(
            "hid_service_not_found",
            "connected peer does not expose HID service");
        return;
    }

    terminal_event_queued = true;
    queue_event(CONNECT_EVENT_CONNECTED, NULL, NULL);
}

static uint8_t hids_discover_cb(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr,
    struct bt_gatt_discover_params *params)
{
    ARG_UNUSED(params);

    if (conn != active_conn || terminal_event_queued) {
        return BT_GATT_ITER_STOP;
    }

    if (attr == NULL) {
        hids_discovery_done = true;
        maybe_complete_connection_validation();
        return BT_GATT_ITER_STOP;
    }

    hids_service_found = true;
    hids_discovery_done = true;
    maybe_complete_connection_validation();
    return BT_GATT_ITER_STOP;
}

static int start_hids_discovery(void)
{
    (void)memset(&hids_discover_params, 0, sizeof(hids_discover_params));
    hids_discover_params.uuid = &hids_uuid.uuid;
    hids_discover_params.func = hids_discover_cb;
    hids_discover_params.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
    hids_discover_params.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
    hids_discover_params.type = BT_GATT_DISCOVER_PRIMARY;

    return bt_gatt_discover(active_conn, &hids_discover_params);
}

static int start_connect_now(void)
{
    struct bt_conn *conn = NULL;
    int err;

    pending_start = false;
    connect_started = true;
    validation_deadline_ms =
        k_uptime_get() + ZMK_USB_BRIDGE_GUI_CONNECT_VALIDATE_TIMEOUT_MS;

    err = bt_conn_le_create(
        &target_addr,
        BT_CONN_LE_CREATE_CONN,
        BT_LE_CONN_PARAM_DEFAULT,
        &conn);
    if (err != 0) {
        connect_started = false;
        validation_deadline_ms = 0;
        log_connect_status("create failed", err);
        return err;
    }

    active_conn = conn;
    log_connect_status("create requested", 0);
    return 0;
}

static void connected_cb(struct bt_conn *conn, uint8_t err)
{
    int security_err;
    int discovery_err;
    struct bt_conn_info info;

    if (conn != active_conn) {
        return;
    }

    if (err != 0U) {
        char message[ZMK_USB_BRIDGE_GUI_CONNECT_MESSAGE_SIZE];

        snprintk(message, sizeof(message), "BLE connection failed with HCI status %u", err);
        terminal_event_queued = true;
        queue_event(CONNECT_EVENT_FAILED, "connect_failed", message);
        unref_active_conn();
        clear_connect_state();
        return;
    }

    log_connect_status("connected, validating peer", 0);

    security_err = bt_conn_set_security(conn, BT_SECURITY_L2);
    if (security_err != 0) {
        log_connect_status("security request failed", security_err);
        fail_active_connection(
            "security_failed",
            "BLE security could not be requested");
        return;
    }
    if (bt_conn_get_info(conn, &info) == 0 && info.security.level >= BT_SECURITY_L2) {
        security_done = true;
    }

    discovery_err = start_hids_discovery();
    if (discovery_err != 0) {
        log_connect_status("HID service discovery failed", discovery_err);
        fail_active_connection(
            "hid_discovery_failed",
            "HID service discovery could not be started");
        return;
    }
}

static void disconnected_cb(struct bt_conn *conn, uint8_t reason)
{
    if (conn != active_conn) {
        return;
    }

    if (!terminal_event_queued) {
        char message[ZMK_USB_BRIDGE_GUI_CONNECT_MESSAGE_SIZE];

        snprintk(message, sizeof(message), "BLE peer disconnected with reason 0x%02x", reason);
        queue_event(CONNECT_EVENT_DISCONNECTED, "peer_disconnected", message);
    }

    unref_active_conn();
    clear_connect_state();
}

static void security_changed_cb(
    struct bt_conn *conn,
    bt_security_t level,
    enum bt_security_err err)
{
    ARG_UNUSED(level);

    if (conn != active_conn || terminal_event_queued) {
        return;
    }

    if (err != BT_SECURITY_ERR_SUCCESS) {
        char message[ZMK_USB_BRIDGE_GUI_CONNECT_MESSAGE_SIZE];

        snprintk(message, sizeof(message), "BLE security failed with status %u", err);
        fail_active_connection("security_failed", message);
        return;
    }

    security_done = true;
    maybe_complete_connection_validation();
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected = connected_cb,
    .disconnected = disconnected_cb,
    .security_changed = security_changed_cb,
};

int zmk_usb_bridge_gui_ble_connect_start(
    const struct zmk_usb_bridge_gui_candidate *candidate)
{
    int err;

    if (candidate == NULL || candidate->ble_address == NULL) {
        return -EINVAL;
    }

    if (zmk_usb_bridge_gui_ble_connect_is_busy()) {
        return -EBUSY;
    }

    err = parse_candidate_address(candidate->ble_address, &target_addr);
    if (err != 0) {
        log_connect_status("candidate address parse failed", err);
        return err;
    }

    k_msgq_purge(&connect_event_queue);
    clear_connect_state();
    start_connect_worker();

    pending_start = true;
    connect_start_not_before_ms =
        k_uptime_get() + ZMK_USB_BRIDGE_GUI_CONNECT_START_DEFER_MS;
    log_connect_status("queued", 0);

    err = zmk_usb_bridge_gui_ble_init();
    if (err != 0 && err != -EINPROGRESS) {
        pending_start = false;
        connect_start_not_before_ms = 0;
        log_connect_status("bluetooth init failed", err);
        return err;
    }

    return 0;
}

void zmk_usb_bridge_gui_ble_connect_cancel(void)
{
    pending_start = false;

    if (active_conn != NULL) {
        terminal_event_queued = true;
        (void)bt_conn_disconnect(active_conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        return;
    }

    clear_connect_state();
    k_msgq_purge(&connect_event_queue);
}

bool zmk_usb_bridge_gui_ble_connect_is_busy(void)
{
    return pending_start || connect_start_requested || connect_started ||
           active_conn != NULL;
}

int zmk_usb_bridge_gui_ble_bond_erase(void)
{
    zmk_usb_bridge_gui_ble_connect_cancel();
    return bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY);
}

void zmk_usb_bridge_gui_ble_connect_poll(void)
{
    struct connect_event event;

    if (pending_start && zmk_usb_bridge_gui_ble_has_failed()) {
        pending_start = false;
        connect_start_requested = false;
        connect_start_not_before_ms = 0;
        queue_event(
            CONNECT_EVENT_FAILED,
            "bluetooth_init_failed",
            "Bluetooth initialization failed");
    }

    if (pending_start && !zmk_usb_bridge_gui_ble_is_ready() &&
        !zmk_usb_bridge_gui_ble_has_failed() &&
        connect_start_not_before_ms > 0 &&
        k_uptime_get() >= connect_start_not_before_ms) {
        int err = zmk_usb_bridge_gui_ble_init();

        if (err != 0 && err != -EINPROGRESS) {
            pending_start = false;
            connect_start_requested = false;
            connect_start_not_before_ms = 0;
            queue_event(
                CONNECT_EVENT_FAILED,
                "bluetooth_init_failed",
                "Bluetooth initialization failed");
        }
    }

    if (pending_start && zmk_usb_bridge_gui_ble_is_ready() &&
        !connect_start_requested && !connect_started &&
        active_conn == NULL && connect_start_not_before_ms > 0 &&
        k_uptime_get() >= connect_start_not_before_ms) {
        connect_start_requested = true;
        start_connect_worker();
        k_sem_give(&connect_start_request);
    }

    if (active_conn != NULL &&
        !terminal_event_queued &&
        validation_deadline_ms > 0 &&
        k_uptime_get() >= validation_deadline_ms) {
        fail_active_connection(
            "validation_timeout",
            "BLE connect validation timed out");
    }

    while (k_msgq_get(&connect_event_queue, &event, K_NO_WAIT) == 0) {
        const struct zmk_usb_bridge_gui_state *state;

        switch (event.type) {
        case CONNECT_EVENT_CONNECTED:
            connect_started = false;
            validation_deadline_ms = 0;
            terminal_event_queued = false;
            zmk_usb_bridge_gui_state_set_connected();
            state = zmk_usb_bridge_gui_state_get();
            zmk_usb_bridge_gui_protocol_emit_connection_state(
                "connected",
                state->peer_name,
                state->peer_address,
                NULL,
                NULL);
            zmk_usb_bridge_gui_protocol_emit_telemetry_update(state);
            break;
        case CONNECT_EVENT_FAILED:
            zmk_usb_bridge_gui_state_fail_connect();
            zmk_usb_bridge_gui_protocol_emit_connection_state(
                "idle",
                NULL,
                NULL,
                event.code[0] != '\0' ? event.code : "connect_failed",
                event.message[0] != '\0' ? event.message : "BLE connection failed");
            break;
        case CONNECT_EVENT_DISCONNECTED:
            zmk_usb_bridge_gui_state_fail_connect();
            zmk_usb_bridge_gui_protocol_emit_connection_state(
                "idle",
                NULL,
                NULL,
                event.code[0] != '\0' ? event.code : "peer_disconnected",
                event.message[0] != '\0' ? event.message : "BLE peer disconnected");
            break;
        default:
            break;
        }
    }
}
