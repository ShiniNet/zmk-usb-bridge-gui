#include "zmk_usb_bridge_gui/runtime_state.h"

#include <stddef.h>
#include <string.h>

#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#define ZMK_USB_BRIDGE_GUI_SCAN_CACHE_SIZE 24
#define ZMK_USB_BRIDGE_GUI_BLE_ADDRESS_TEXT_SIZE 32
#define ZMK_USB_BRIDGE_GUI_DISPLAY_NAME_TEXT_SIZE 64

struct scan_candidate_record {
    struct zmk_usb_bridge_gui_candidate candidate;
    bool in_use;
    char ble_address[ZMK_USB_BRIDGE_GUI_BLE_ADDRESS_TEXT_SIZE];
    char display_name[ZMK_USB_BRIDGE_GUI_DISPLAY_NAME_TEXT_SIZE];
};

static struct zmk_usb_bridge_gui_state runtime_state;
static struct scan_candidate_record scan_candidate_cache[ZMK_USB_BRIDGE_GUI_SCAN_CACHE_SIZE];
static int next_candidate_id = 1;

BUILD_ASSERT(
    ZMK_USB_BRIDGE_GUI_SCAN_CACHE_SIZE >= ZMK_USB_BRIDGE_GUI_MAX_CANDIDATES,
    "scan cache must fit the published candidate list");

static void clear_stub_telemetry(void)
{
    runtime_state.battery_supported = true;
    runtime_state.battery_percent = -1;
    runtime_state.modifiers_supported = true;
    runtime_state.modifiers_reported = false;
    runtime_state.modifiers.count = 0U;
    runtime_state.last_key_supported = true;
    runtime_state.last_key = NULL;
    runtime_state.mouse_buttons_supported = true;
    runtime_state.mouse_buttons_reported = false;
    runtime_state.mouse_buttons.count = 0U;
}

static void clear_peer_connection(void)
{
    runtime_state.peer_name = NULL;
    runtime_state.peer_address = NULL;
    clear_stub_telemetry();
}

static void clear_scan_cache(void)
{
    memset(scan_candidate_cache, 0, sizeof(scan_candidate_cache));
    memset(runtime_state.candidates, 0, sizeof(runtime_state.candidates));
    runtime_state.candidate_count = 0;
    next_candidate_id = 1;
}

static bool candidate_has_display_name(const struct zmk_usb_bridge_gui_candidate *candidate)
{
    return candidate != NULL && candidate->display_name != NULL && candidate->display_name[0] != '\0';
}

static int candidate_tier(const struct zmk_usb_bridge_gui_candidate *candidate)
{
    if (candidate == NULL || !candidate->connectable || !candidate->has_hid_service) {
        return 2;
    }

    if (candidate->has_keyboard_appearance) {
        return 0;
    }

    if (candidate_has_display_name(candidate)) {
        return 1;
    }

    return 2;
}

bool zmk_usb_bridge_gui_candidate_is_public(
    const struct zmk_usb_bridge_gui_candidate *candidate)
{
    return candidate_tier(candidate) < 2;
}

static bool candidate_is_storage_eligible(const struct zmk_usb_bridge_gui_candidate *candidate)
{
    return candidate != NULL &&
           (candidate->connectable || candidate->has_hid_service ||
            candidate->has_keyboard_appearance || candidate_has_display_name(candidate));
}

static int compare_candidate_records(
    const struct scan_candidate_record *left,
    const struct scan_candidate_record *right)
{
    int left_tier;
    int right_tier;
    bool left_has_name;
    bool right_has_name;

    if (left == NULL || !left->in_use) {
        return (right != NULL && right->in_use) ? 1 : 0;
    }

    if (right == NULL || !right->in_use) {
        return -1;
    }

    left_tier = candidate_tier(&left->candidate);
    right_tier = candidate_tier(&right->candidate);
    if (left_tier != right_tier) {
        return left_tier < right_tier ? -1 : 1;
    }

    if (left->candidate.rssi != right->candidate.rssi) {
        return left->candidate.rssi > right->candidate.rssi ? -1 : 1;
    }

    if (left->candidate.last_seen_ms != right->candidate.last_seen_ms) {
        return left->candidate.last_seen_ms > right->candidate.last_seen_ms ? -1 : 1;
    }

    left_has_name = candidate_has_display_name(&left->candidate);
    right_has_name = candidate_has_display_name(&right->candidate);
    if (left_has_name != right_has_name) {
        return left_has_name ? -1 : 1;
    }

    if (left->candidate.candidate_id != right->candidate.candidate_id) {
        return left->candidate.candidate_id < right->candidate.candidate_id ? -1 : 1;
    }

    return 0;
}

static void set_record_ble_address(struct scan_candidate_record *record, const char *ble_address)
{
    if (record == NULL || ble_address == NULL) {
        return;
    }

    snprintk(record->ble_address, sizeof(record->ble_address), "%s", ble_address);
    record->candidate.ble_address = record->ble_address;
}

static void set_record_display_name(struct scan_candidate_record *record, const char *display_name)
{
    if (record == NULL) {
        return;
    }

    if (display_name == NULL || display_name[0] == '\0') {
        record->display_name[0] = '\0';
        record->candidate.display_name = NULL;
        return;
    }

    snprintk(record->display_name, sizeof(record->display_name), "%s", display_name);
    record->candidate.display_name = record->display_name;
}

static struct scan_candidate_record *find_record_by_candidate_id(int candidate_id)
{
    for (size_t index = 0U; index < ARRAY_SIZE(scan_candidate_cache); ++index) {
        if (scan_candidate_cache[index].in_use &&
            scan_candidate_cache[index].candidate.candidate_id == candidate_id) {
            return &scan_candidate_cache[index];
        }
    }

    return NULL;
}

static struct scan_candidate_record *find_record_by_ble_address(const char *ble_address)
{
    if (ble_address == NULL || ble_address[0] == '\0') {
        return NULL;
    }

    for (size_t index = 0U; index < ARRAY_SIZE(scan_candidate_cache); ++index) {
        if (!scan_candidate_cache[index].in_use) {
            continue;
        }

        if (strcmp(scan_candidate_cache[index].ble_address, ble_address) == 0) {
            return &scan_candidate_cache[index];
        }
    }

    return NULL;
}

static struct scan_candidate_record *find_free_record(void)
{
    for (size_t index = 0U; index < ARRAY_SIZE(scan_candidate_cache); ++index) {
        if (!scan_candidate_cache[index].in_use) {
            return &scan_candidate_cache[index];
        }
    }

    return NULL;
}

static struct scan_candidate_record *find_worst_record(void)
{
    struct scan_candidate_record *worst = NULL;

    for (size_t index = 0U; index < ARRAY_SIZE(scan_candidate_cache); ++index) {
        struct scan_candidate_record *candidate = &scan_candidate_cache[index];

        if (!candidate->in_use) {
            continue;
        }

        if (worst == NULL || compare_candidate_records(candidate, worst) > 0) {
            worst = candidate;
        }
    }

    return worst;
}

static void rebuild_public_candidate_list(void)
{
    struct scan_candidate_record *ordered[ZMK_USB_BRIDGE_GUI_SCAN_CACHE_SIZE];
    size_t visible_count = 0U;

    memset(runtime_state.candidates, 0, sizeof(runtime_state.candidates));

    for (size_t index = 0U; index < ARRAY_SIZE(scan_candidate_cache); ++index) {
        struct scan_candidate_record *record = &scan_candidate_cache[index];
        size_t insert_index;

        if (!record->in_use || !zmk_usb_bridge_gui_candidate_is_public(&record->candidate)) {
            continue;
        }

        if (visible_count >= ARRAY_SIZE(ordered) &&
            compare_candidate_records(record, ordered[ARRAY_SIZE(ordered) - 1U]) >= 0) {
            continue;
        }

        insert_index = visible_count < ARRAY_SIZE(ordered)
                           ? visible_count
                           : ARRAY_SIZE(ordered) - 1U;
        while (insert_index > 0U &&
               compare_candidate_records(record, ordered[insert_index - 1U]) < 0) {
            ordered[insert_index] = ordered[insert_index - 1U];
            insert_index -= 1U;
        }

        ordered[insert_index] = record;
        if (visible_count < ARRAY_SIZE(ordered)) {
            visible_count += 1U;
        }
    }

    if (visible_count > ZMK_USB_BRIDGE_GUI_MAX_CANDIDATES) {
        visible_count = ZMK_USB_BRIDGE_GUI_MAX_CANDIDATES;
    }

    for (size_t index = 0U; index < visible_count; ++index) {
        runtime_state.candidates[index] = ordered[index]->candidate;
    }

    runtime_state.candidate_count = (int)visible_count;
}

static struct scan_candidate_record *allocate_or_replace_record(
    const char *ble_address,
    const char *display_name,
    bool connectable,
    bool has_hid_service,
    bool has_keyboard_appearance,
    int rssi,
    int64_t last_seen_ms)
{
    struct scan_candidate_record *record = find_free_record();

    if (record != NULL) {
        memset(record, 0, sizeof(*record));
        record->in_use = true;
        record->candidate.candidate_id = next_candidate_id++;
        set_record_ble_address(record, ble_address);
        set_record_display_name(record, display_name);
        record->candidate.connectable = connectable;
        record->candidate.has_hid_service = has_hid_service;
        record->candidate.has_keyboard_appearance = has_keyboard_appearance;
        record->candidate.rssi = rssi;
        record->candidate.last_seen_ms = last_seen_ms;
        return record;
    }

    record = find_worst_record();
    if (record == NULL) {
        return NULL;
    }

    {
        struct scan_candidate_record incoming = {0};

        incoming.in_use = true;
        incoming.candidate.candidate_id = next_candidate_id;
        set_record_ble_address(&incoming, ble_address);
        set_record_display_name(&incoming, display_name);
        incoming.candidate.connectable = connectable;
        incoming.candidate.has_hid_service = has_hid_service;
        incoming.candidate.has_keyboard_appearance = has_keyboard_appearance;
        incoming.candidate.rssi = rssi;
        incoming.candidate.last_seen_ms = last_seen_ms;
        if (compare_candidate_records(&incoming, record) >= 0) {
            return NULL;
        }
    }

    memset(record, 0, sizeof(*record));
    record->in_use = true;
    record->candidate.candidate_id = next_candidate_id++;
    set_record_ble_address(record, ble_address);
    set_record_display_name(record, display_name);
    record->candidate.connectable = connectable;
    record->candidate.has_hid_service = has_hid_service;
    record->candidate.has_keyboard_appearance = has_keyboard_appearance;
    record->candidate.rssi = rssi;
    record->candidate.last_seen_ms = last_seen_ms;
    return record;
}

void zmk_usb_bridge_gui_state_init(void)
{
    runtime_state.receiver_state = "idle";
    runtime_state.scan_in_progress = false;
    runtime_state.candidate_generation = 0;
    runtime_state.active_candidate_id = -1;
    runtime_state.bonded_peer_count = 0;
    clear_scan_cache();
    clear_peer_connection();
}

const struct zmk_usb_bridge_gui_state *zmk_usb_bridge_gui_state_get(void)
{
    return &runtime_state;
}

void zmk_usb_bridge_gui_state_prepare_scan(void)
{
    runtime_state.receiver_state = "scanning";
    runtime_state.scan_in_progress = true;
    runtime_state.candidate_generation += 1;
    runtime_state.active_candidate_id = -1;
    clear_scan_cache();
    clear_peer_connection();
}

void zmk_usb_bridge_gui_state_complete_scan(void)
{
    runtime_state.receiver_state = "idle";
    runtime_state.scan_in_progress = false;
}

const struct zmk_usb_bridge_gui_candidate *zmk_usb_bridge_gui_state_observe_scan_candidate(
    const char *ble_address,
    const char *display_name,
    bool connectable,
    bool has_hid_service,
    bool has_keyboard_appearance,
    int rssi,
    int64_t last_seen_ms)
{
    struct scan_candidate_record *record;

    if (ble_address == NULL || ble_address[0] == '\0') {
        return NULL;
    }

    record = find_record_by_ble_address(ble_address);
    if (record == NULL) {
        struct zmk_usb_bridge_gui_candidate incoming = {
            .ble_address = ble_address,
            .display_name = display_name,
            .connectable = connectable,
            .has_hid_service = has_hid_service,
            .has_keyboard_appearance = has_keyboard_appearance,
            .rssi = rssi,
            .last_seen_ms = last_seen_ms,
        };

        if (!candidate_is_storage_eligible(&incoming)) {
            return NULL;
        }

        record = allocate_or_replace_record(
            ble_address,
            display_name,
            connectable,
            has_hid_service,
            has_keyboard_appearance,
            rssi,
            last_seen_ms);
        if (record == NULL) {
            return NULL;
        }
    } else {
        if (connectable) {
            record->candidate.connectable = true;
        }
        if (has_hid_service) {
            record->candidate.has_hid_service = true;
        }
        if (has_keyboard_appearance) {
            record->candidate.has_keyboard_appearance = true;
        }
        if (display_name != NULL && display_name[0] != '\0') {
            set_record_display_name(record, display_name);
        }
        record->candidate.rssi = rssi;
        record->candidate.last_seen_ms = last_seen_ms;
    }

    rebuild_public_candidate_list();
    return zmk_usb_bridge_gui_state_get_candidate_by_id(record->candidate.candidate_id);
}

bool zmk_usb_bridge_gui_state_select_candidate(int candidate_id)
{
    if (zmk_usb_bridge_gui_state_get_candidate_by_id(candidate_id) == NULL) {
        return false;
    }

    runtime_state.active_candidate_id = candidate_id;
    return true;
}

void zmk_usb_bridge_gui_state_connect_candidate(void)
{
    runtime_state.receiver_state = "connecting";
    runtime_state.scan_in_progress = false;
    clear_peer_connection();
}

void zmk_usb_bridge_gui_state_set_connected(void)
{
    const struct zmk_usb_bridge_gui_candidate *candidate =
        zmk_usb_bridge_gui_state_get_candidate_by_id(runtime_state.active_candidate_id);

    runtime_state.receiver_state = "connected";
    runtime_state.scan_in_progress = false;
    runtime_state.peer_name = candidate != NULL ? candidate->display_name : NULL;
    runtime_state.peer_address = candidate != NULL ? candidate->ble_address : NULL;
    runtime_state.bonded_peer_count = candidate != NULL ? 1 : 0;
    clear_stub_telemetry();
}

void zmk_usb_bridge_gui_state_fail_connect(void)
{
    runtime_state.receiver_state = "idle";
    runtime_state.scan_in_progress = false;
    runtime_state.active_candidate_id = -1;
    clear_peer_connection();
}

int zmk_usb_bridge_gui_state_reset_bonds(void)
{
    int cleared_count = runtime_state.bonded_peer_count;

    runtime_state.receiver_state = "idle";
    runtime_state.scan_in_progress = false;
    runtime_state.active_candidate_id = -1;
    runtime_state.bonded_peer_count = 0;
    clear_scan_cache();
    clear_peer_connection();
    return cleared_count;
}

const struct zmk_usb_bridge_gui_candidate *zmk_usb_bridge_gui_state_get_candidate_by_index(
    size_t index)
{
    if (index >= (size_t)runtime_state.candidate_count) {
        return NULL;
    }

    return &runtime_state.candidates[index];
}

const struct zmk_usb_bridge_gui_candidate *zmk_usb_bridge_gui_state_get_candidate_by_id(
    int candidate_id)
{
    struct scan_candidate_record *record = find_record_by_candidate_id(candidate_id);

    return record != NULL ? &record->candidate : NULL;
}
