#include "zmk_usb_bridge_gui/protocol.h"

#include "zmk_usb_bridge_gui/runtime_state.h"
#include "zmk_usb_bridge_gui/usb_channel.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/util.h>

#define PROTOCOL_BUFFER_SIZE CONFIG_ZMK_USB_BRIDGE_GUI_PROTOCOL_BUFFER_SIZE
#define JSON_SHORT_VALUE_BUFFER_SIZE 64
#define JSON_TEXT_VALUE_BUFFER_SIZE 160
#define JSON_ARRAY_VALUE_BUFFER_SIZE 256
#define JSON_CANDIDATE_VALUE_BUFFER_SIZE 384
#define OPTIONAL_DETAIL_SUFFIX_BUFFER_SIZE \
    (JSON_SHORT_VALUE_BUFFER_SIZE + JSON_TEXT_VALUE_BUFFER_SIZE + 32)
#define ZMK_USB_BRIDGE_GUI_FIRMWARE_VERSION "0.1.0"
#define STUB_SCAN_CANDIDATE_DELAY_MS 200
#define STUB_SCAN_COMPLETE_DELAY_MS 600
#define STUB_CONNECT_COMPLETE_DELAY_MS 300

enum stub_scan_stage {
    STUB_SCAN_STAGE_IDLE = 0,
    STUB_SCAN_STAGE_WAITING_FOR_CANDIDATE,
    STUB_SCAN_STAGE_WAITING_FOR_COMPLETE,
};

static enum stub_scan_stage stub_scan_stage = STUB_SCAN_STAGE_IDLE;
static int64_t stub_scan_candidate_due_at_ms;
static int64_t stub_scan_complete_due_at_ms;
static bool stub_connect_pending;
static int64_t stub_connect_complete_due_at_ms;

static void emit_line(const char *line);
static void log_stub_progress(const char *format, ...);

static bool append_json_fragment(
    char *buffer,
    size_t buffer_size,
    size_t *offset,
    const char *format,
    ...)
{
    int written;
    va_list args;

    if (buffer == NULL || offset == NULL || *offset >= buffer_size) {
        return false;
    }

    va_start(args, format);
    written = vsnprintk(buffer + *offset, buffer_size - *offset, format, args);
    va_end(args);
    if (written < 0 || (size_t)written >= buffer_size - *offset) {
        return false;
    }

    *offset += (size_t)written;
    return true;
}

static void log_protocol_drop(const char *context)
{
    char log_line[96];

    snprintk(log_line, sizeof(log_line), "protocol emit dropped: %s truncated", context);
    zmk_usb_bridge_gui_usb_channel_write_log_line(log_line);
}

static void log_stub_progress(const char *format, ...)
{
    char log_line[96];
    int written;
    va_list args;

    va_start(args, format);
    written = vsnprintk(log_line, sizeof(log_line), format, args);
    va_end(args);
    if (written < 0 || (size_t)written >= sizeof(log_line)) {
        zmk_usb_bridge_gui_usb_channel_write_log_line("stub progress log truncated");
        return;
    }

    zmk_usb_bridge_gui_usb_channel_write_log_line(log_line);
}

static bool emit_completed_line(
    const char *context,
    char *buffer,
    size_t buffer_size,
    int written)
{
    if (written < 0 || (size_t)written >= buffer_size) {
        log_protocol_drop(context);
        return false;
    }

    emit_line(buffer);
    return true;
}

static void json_string_or_null(const char *input, char *buffer, size_t buffer_size)
{
    size_t write_index = 0U;

    if (buffer_size == 0U) {
        return;
    }

    if (input == NULL) {
        snprintk(buffer, buffer_size, "null");
        return;
    }

    if (buffer_size < 3U) {
        buffer[0] = '\0';
        return;
    }

    buffer[write_index++] = '"';

    for (const char *cursor = input;
         *cursor != '\0' && write_index + 2U < buffer_size;
         ++cursor) {
        char current = *cursor;

        if (current == '\\' || current == '"') {
            if (write_index + 3U >= buffer_size) {
                break;
            }
            buffer[write_index++] = '\\';
            buffer[write_index++] = current;
            continue;
        }

        if (current == '\n' || current == '\r' || current == '\t') {
            char escape_code =
                (current == '\r') ? 'r' : (current == '\t') ? 't' : 'n';

            if (write_index + 3U >= buffer_size) {
                break;
            }
            buffer[write_index++] = '\\';
            buffer[write_index++] = escape_code;
            continue;
        }

        buffer[write_index++] = current;
    }

    if (write_index + 2U > buffer_size) {
        write_index = buffer_size - 2U;
    }

    buffer[write_index++] = '"';
    buffer[write_index] = '\0';
}

static bool format_string_list_json(
    const struct zmk_usb_bridge_gui_string_list *list,
    bool reported,
    char *buffer,
    size_t buffer_size)
{
    size_t offset = 0U;

    if (!reported) {
        snprintk(buffer, buffer_size, "null");
        return true;
    }

    if (!append_json_fragment(buffer, buffer_size, &offset, "[")) {
        return false;
    }

    for (size_t index = 0U; index < list->count; ++index) {
        char item_json[JSON_SHORT_VALUE_BUFFER_SIZE];

        json_string_or_null(list->items[index], item_json, sizeof(item_json));
        if (!append_json_fragment(
                buffer,
                buffer_size,
                &offset,
                "%s%s",
                index == 0U ? "" : ",",
                item_json)) {
            return false;
        }
    }

    return append_json_fragment(buffer, buffer_size, &offset, "]");
}

static void format_optional_code_suffix(
    const char *code,
    char *suffix_buffer,
    size_t suffix_buffer_size)
{
    char code_json[JSON_SHORT_VALUE_BUFFER_SIZE];

    if (code == NULL) {
        if (suffix_buffer_size > 0U) {
            suffix_buffer[0] = '\0';
        }
        return;
    }

    json_string_or_null(code, code_json, sizeof(code_json));
    snprintk(suffix_buffer, suffix_buffer_size, ",\"code\":%s", code_json);
}

static void format_optional_connection_detail_suffix(
    const char *code,
    const char *message,
    char *suffix_buffer,
    size_t suffix_buffer_size)
{
    char code_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char message_json[JSON_TEXT_VALUE_BUFFER_SIZE];

    if (code == NULL || message == NULL) {
        if (suffix_buffer_size > 0U) {
            suffix_buffer[0] = '\0';
        }
        return;
    }

    json_string_or_null(code, code_json, sizeof(code_json));
    json_string_or_null(message, message_json, sizeof(message_json));
    snprintk(
        suffix_buffer,
        suffix_buffer_size,
        ",\"code\":%s,\"message\":%s",
        code_json,
        message_json);
}

static bool format_candidate_json(
    const struct zmk_usb_bridge_gui_candidate *candidate,
    char *buffer,
    size_t buffer_size)
{
    size_t offset = 0U;
    char ble_address_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char display_name_json[JSON_TEXT_VALUE_BUFFER_SIZE];

    if (candidate == NULL) {
        return false;
    }

    json_string_or_null(candidate->ble_address, ble_address_json, sizeof(ble_address_json));
    json_string_or_null(candidate->display_name, display_name_json, sizeof(display_name_json));

    if (!append_json_fragment(
            buffer,
            buffer_size,
            &offset,
            "{\"candidate_id\":%d,\"ble_address\":%s,\"display_name\":%s,"
            "\"connectable\":%s,\"has_hid_service\":%s,"
            "\"has_keyboard_appearance\":%s,\"rssi\":%d",
            candidate->candidate_id,
            ble_address_json,
            display_name_json,
            candidate->connectable ? "true" : "false",
            candidate->has_hid_service ? "true" : "false",
            candidate->has_keyboard_appearance ? "true" : "false",
            candidate->rssi)) {
        return false;
    }

    if (candidate->last_seen_ms >= 0 &&
        !append_json_fragment(
            buffer,
            buffer_size,
            &offset,
            ",\"last_seen_ms\":%d",
            candidate->last_seen_ms)) {
        return false;
    }

    return append_json_fragment(buffer, buffer_size, &offset, "}");
}

static void format_battery_percent_json(
    const struct zmk_usb_bridge_gui_state *state,
    char *buffer,
    size_t buffer_size)
{
    if (state->battery_percent < 0) {
        snprintk(buffer, buffer_size, "null");
        return;
    }

    snprintk(buffer, buffer_size, "%d", state->battery_percent);
}

static void reset_stub_async_sequences(void)
{
    stub_scan_stage = STUB_SCAN_STAGE_IDLE;
    stub_scan_candidate_due_at_ms = 0;
    stub_scan_complete_due_at_ms = 0;
    stub_connect_pending = false;
    stub_connect_complete_due_at_ms = 0;
}

static int extract_integer_field(const char *line, const char *field_name, int *value)
{
    const char *found = strstr(line, field_name);

    if (found == NULL || value == NULL) {
        return -1;
    }

    found = strchr(found, ':');
    if (found == NULL) {
        return -1;
    }

    return sscanf(found + 1, "%d", value) == 1 ? 0 : -1;
}

static int extract_string_field(
    const char *line,
    const char *field_name,
    char *buffer,
    size_t buffer_size)
{
    const char *found = strstr(line, field_name);
    const char *start;
    size_t write_index = 0U;

    if (found == NULL || buffer == NULL || buffer_size == 0U) {
        return -1;
    }

    found = strchr(found, ':');
    if (found == NULL) {
        return -1;
    }

    start = strchr(found, '"');
    if (start == NULL) {
        return -1;
    }
    start += 1;

    while (*start != '\0') {
        char current = *start++;

        if (current == '"') {
            buffer[write_index] = '\0';
            return 0;
        }

        if (current == '\\') {
            if (*start == '\0') {
                return -1;
            }

            current = *start++;
            if (current == '"' || current == '\\' || current == '/') {
                /* current already holds the decoded character. */
            } else if (current == 'n') {
                current = '\n';
            } else if (current == 'r') {
                current = '\r';
            } else if (current == 't') {
                current = '\t';
            } else {
                return -1;
            }
        }

        if (write_index + 1U >= buffer_size) {
            return -1;
        }

        buffer[write_index++] = current;
    }

    return -1;
}

/* Keep a single transport handoff point so future queueing/log mirroring has one hook. */
static void emit_line(const char *line)
{
    zmk_usb_bridge_gui_usb_channel_write_gui_line(line);
}

void zmk_usb_bridge_gui_protocol_emit_hello(void)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char board_json[JSON_TEXT_VALUE_BUFFER_SIZE];
    char firmware_version_json[JSON_SHORT_VALUE_BUFFER_SIZE];

    json_string_or_null(CONFIG_BOARD, board_json, sizeof(board_json));
    /* TODO: Replace the stub version once the firmware build exports an app version. */
    json_string_or_null(
        ZMK_USB_BRIDGE_GUI_FIRMWARE_VERSION,
        firmware_version_json,
        sizeof(firmware_version_json));
    if (!emit_completed_line(
            "hello",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"hello\",\"product\":\"zmk-usb-bridge-gui\","
                "\"protocol_version\":1,\"channel\":\"gui\","
                "\"board\":%s,\"firmware_version\":%s}",
                board_json,
                firmware_version_json))) {
        return;
    }
}

void zmk_usb_bridge_gui_protocol_emit_status_snapshot(
    const struct zmk_usb_bridge_gui_state *state)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char receiver_state_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char peer_name_json[JSON_TEXT_VALUE_BUFFER_SIZE];
    char peer_address_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char battery_percent_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char modifiers_json[JSON_ARRAY_VALUE_BUFFER_SIZE];
    char last_key_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char mouse_buttons_json[JSON_ARRAY_VALUE_BUFFER_SIZE];

    json_string_or_null(state->receiver_state, receiver_state_json, sizeof(receiver_state_json));
    json_string_or_null(state->peer_name, peer_name_json, sizeof(peer_name_json));
    json_string_or_null(state->peer_address, peer_address_json, sizeof(peer_address_json));
    format_battery_percent_json(state, battery_percent_json, sizeof(battery_percent_json));
    json_string_or_null(state->last_key, last_key_json, sizeof(last_key_json));
    if (!format_string_list_json(
            &state->modifiers,
            state->modifiers_reported,
            modifiers_json,
            sizeof(modifiers_json)) ||
        !format_string_list_json(
            &state->mouse_buttons,
            state->mouse_buttons_reported,
            mouse_buttons_json,
            sizeof(mouse_buttons_json))) {
        log_protocol_drop("status_snapshot");
        return;
    }

    if (!emit_completed_line(
            "status_snapshot",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"status_snapshot\",\"receiver_state\":%s,"
                "\"peer_name\":%s,\"peer_address\":%s,\"scan_in_progress\":%s,"
                "\"candidate_generation\":%d,\"candidate_count\":%d,"
                "\"battery_supported\":%s,\"battery_percent\":%s,"
                "\"modifiers_supported\":%s,\"modifiers\":%s,"
                "\"last_key_supported\":%s,\"last_key\":%s,"
                "\"mouse_buttons_supported\":%s,\"mouse_buttons\":%s}",
                receiver_state_json,
                peer_name_json,
                peer_address_json,
                state->scan_in_progress ? "true" : "false",
                state->candidate_generation,
                state->candidate_count,
                state->battery_supported ? "true" : "false",
                battery_percent_json,
                state->modifiers_supported ? "true" : "false",
                modifiers_json,
                state->last_key_supported ? "true" : "false",
                last_key_json,
                state->mouse_buttons_supported ? "true" : "false",
                mouse_buttons_json))) {
        return;
    }
}

void zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(
    const struct zmk_usb_bridge_gui_state *state)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    size_t offset = 0U;

    if (!append_json_fragment(
            buffer,
            sizeof(buffer),
            &offset,
            "{\"type\":\"candidate_snapshot\",\"candidate_generation\":%d,\"candidates\":[",
            state->candidate_generation)) {
        log_protocol_drop("candidate_snapshot");
        return;
    }

    for (size_t index = 0U; index < (size_t)state->candidate_count; ++index) {
        char candidate_json[JSON_CANDIDATE_VALUE_BUFFER_SIZE];
        const struct zmk_usb_bridge_gui_candidate *candidate =
            zmk_usb_bridge_gui_state_get_candidate_by_index(index);

        if (!format_candidate_json(candidate, candidate_json, sizeof(candidate_json)) ||
            !append_json_fragment(
                buffer,
                sizeof(buffer),
                &offset,
                "%s%s",
                index == 0U ? "" : ",",
                candidate_json)) {
            log_protocol_drop("candidate_snapshot");
            return;
        }
    }

    if (!append_json_fragment(buffer, sizeof(buffer), &offset, "]}")) {
        log_protocol_drop("candidate_snapshot");
        return;
    }

    emit_line(buffer);
}

void zmk_usb_bridge_gui_protocol_emit_scan_started(int candidate_generation)
{
    char buffer[PROTOCOL_BUFFER_SIZE];

    if (!emit_completed_line(
            "scan_started",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"event\",\"name\":\"scan_started\","
                "\"candidate_generation\":%d}",
                candidate_generation))) {
        return;
    }
}

void zmk_usb_bridge_gui_protocol_emit_candidate_upsert(
    const struct zmk_usb_bridge_gui_state *state,
    const struct zmk_usb_bridge_gui_candidate *candidate)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char candidate_json[JSON_CANDIDATE_VALUE_BUFFER_SIZE];

    if (!format_candidate_json(candidate, candidate_json, sizeof(candidate_json)) ||
        !emit_completed_line(
            "candidate_upsert",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"event\",\"name\":\"candidate_upsert\","
                "\"candidate_generation\":%d,\"candidate\":%s}",
                state->candidate_generation,
                candidate_json))) {
        return;
    }
}

void zmk_usb_bridge_gui_protocol_emit_scan_complete(
    int candidate_generation,
    const char *result,
    int candidate_count,
    const char *code)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char optional_code_suffix[96];
    char result_json[JSON_SHORT_VALUE_BUFFER_SIZE];

    format_optional_code_suffix(code, optional_code_suffix, sizeof(optional_code_suffix));
    json_string_or_null(result, result_json, sizeof(result_json));
    if (!emit_completed_line(
            "scan_complete",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"event\",\"name\":\"scan_complete\","
                "\"candidate_generation\":%d,\"result\":%s,"
                "\"candidate_count\":%d%s}",
                candidate_generation,
                result_json,
                candidate_count,
                optional_code_suffix))) {
        return;
    }
}

void zmk_usb_bridge_gui_protocol_emit_connection_state(
    const char *state,
    const char *peer_name,
    const char *peer_address,
    const char *code,
    const char *message)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char state_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char peer_name_json[JSON_TEXT_VALUE_BUFFER_SIZE];
    char peer_address_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char optional_detail_suffix[OPTIONAL_DETAIL_SUFFIX_BUFFER_SIZE];

    json_string_or_null(state, state_json, sizeof(state_json));
    json_string_or_null(peer_name, peer_name_json, sizeof(peer_name_json));
    json_string_or_null(peer_address, peer_address_json, sizeof(peer_address_json));
    format_optional_connection_detail_suffix(
        code, message, optional_detail_suffix, sizeof(optional_detail_suffix));
    if (!emit_completed_line(
            "connection_state",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"event\",\"name\":\"connection_state\","
                "\"state\":%s,\"peer_name\":%s,\"peer_address\":%s%s}",
                state_json,
                peer_name_json,
                peer_address_json,
                optional_detail_suffix))) {
        return;
    }
}

void zmk_usb_bridge_gui_protocol_emit_telemetry_update(
    const struct zmk_usb_bridge_gui_state *state)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char battery_percent_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char modifiers_json[JSON_ARRAY_VALUE_BUFFER_SIZE];
    char last_key_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char mouse_buttons_json[JSON_ARRAY_VALUE_BUFFER_SIZE];

    format_battery_percent_json(state, battery_percent_json, sizeof(battery_percent_json));
    json_string_or_null(state->last_key, last_key_json, sizeof(last_key_json));
    if (!format_string_list_json(
            &state->modifiers,
            state->modifiers_reported,
            modifiers_json,
            sizeof(modifiers_json)) ||
        !format_string_list_json(
            &state->mouse_buttons,
            state->mouse_buttons_reported,
            mouse_buttons_json,
            sizeof(mouse_buttons_json))) {
        log_protocol_drop("telemetry_update");
        return;
    }
    if (!emit_completed_line(
            "telemetry_update",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"event\",\"name\":\"telemetry_update\","
                "\"battery_supported\":%s,\"battery_percent\":%s,"
                "\"modifiers_supported\":%s,\"modifiers\":%s,"
                "\"last_key_supported\":%s,\"last_key\":%s,"
                "\"mouse_buttons_supported\":%s,\"mouse_buttons\":%s}",
                state->battery_supported ? "true" : "false",
                battery_percent_json,
                state->modifiers_supported ? "true" : "false",
                modifiers_json,
                state->last_key_supported ? "true" : "false",
                last_key_json,
                state->mouse_buttons_supported ? "true" : "false",
                mouse_buttons_json))) {
        return;
    }
}

void zmk_usb_bridge_gui_protocol_emit_bonds_cleared(int cleared_count)
{
    char buffer[PROTOCOL_BUFFER_SIZE];

    if (!emit_completed_line(
            "bonds_cleared",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"event\",\"name\":\"bonds_cleared\","
                "\"cleared_count\":%d}",
                cleared_count))) {
        return;
    }
}

void zmk_usb_bridge_gui_protocol_emit_ack(int request_id, const char *name)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char name_json[JSON_SHORT_VALUE_BUFFER_SIZE];

    json_string_or_null(name, name_json, sizeof(name_json));
    if (!emit_completed_line(
            "ack",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"ack\",\"request_id\":%d,\"name\":%s,"
                "\"accepted\":true}",
                request_id,
                name_json))) {
        return;
    }
}

void zmk_usb_bridge_gui_protocol_emit_error(
    int request_id,
    const char *name,
    const char *code,
    const char *message)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char name_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char code_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char message_json[JSON_TEXT_VALUE_BUFFER_SIZE];

    json_string_or_null(name, name_json, sizeof(name_json));
    json_string_or_null(code, code_json, sizeof(code_json));
    json_string_or_null(message, message_json, sizeof(message_json));
    if (!emit_completed_line(
            "error",
            buffer,
            sizeof(buffer),
            snprintk(
                buffer,
                sizeof(buffer),
                "{\"type\":\"error\",\"request_id\":%d,\"name\":%s,"
                "\"code\":%s,\"message\":%s}",
                request_id,
                name_json,
                code_json,
                message_json))) {
        return;
    }
}

static void handle_get_status(int request_id)
{
    const struct zmk_usb_bridge_gui_state *state = zmk_usb_bridge_gui_state_get();

    zmk_usb_bridge_gui_protocol_emit_ack(request_id, "get_status");
    zmk_usb_bridge_gui_protocol_emit_status_snapshot(state);
    zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(state);
}

static void handle_get_candidates(int request_id)
{
    const struct zmk_usb_bridge_gui_state *state = zmk_usb_bridge_gui_state_get();

    zmk_usb_bridge_gui_protocol_emit_ack(request_id, "get_candidates");
    zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(state);
}

static void handle_scan_start(int request_id)
{
    const struct zmk_usb_bridge_gui_state *state;
    int64_t now_ms;

    state = zmk_usb_bridge_gui_state_get();
    if (strcmp(state->receiver_state, "scanning") == 0) {
        zmk_usb_bridge_gui_protocol_emit_error(
            request_id,
            "scan_start",
            "scan_busy",
            "scan already in progress");
        return;
    }

    if (strcmp(state->receiver_state, "connecting") == 0 || stub_connect_pending) {
        zmk_usb_bridge_gui_protocol_emit_error(
            request_id,
            "scan_start",
            "connect_busy",
            "connect in progress");
        return;
    }

    zmk_usb_bridge_gui_state_prepare_scan();
    state = zmk_usb_bridge_gui_state_get();
    now_ms = k_uptime_get();
    stub_scan_stage = STUB_SCAN_STAGE_WAITING_FOR_CANDIDATE;
    stub_scan_candidate_due_at_ms = now_ms + STUB_SCAN_CANDIDATE_DELAY_MS;
    stub_scan_complete_due_at_ms = now_ms + STUB_SCAN_COMPLETE_DELAY_MS;
    log_stub_progress(
        "stub scan started gen=%d due_candidate=%lld due_complete=%lld",
        state->candidate_generation,
        stub_scan_candidate_due_at_ms,
        stub_scan_complete_due_at_ms);

    zmk_usb_bridge_gui_protocol_emit_ack(request_id, "scan_start");
    zmk_usb_bridge_gui_protocol_emit_scan_started(state->candidate_generation);
    zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(state);
}

static void handle_connect_candidate(const char *line, int request_id)
{
    int candidate_generation = -1;
    int candidate_id = -1;
    const struct zmk_usb_bridge_gui_state *state;
    int64_t now_ms;

    if (extract_integer_field(line, "\"candidate_generation\"", &candidate_generation) != 0 ||
        extract_integer_field(line, "\"candidate_id\"", &candidate_id) != 0) {
        zmk_usb_bridge_gui_protocol_emit_error(
            request_id,
            "connect_candidate",
            "invalid_request",
            "candidate_generation and candidate_id are required");
        return;
    }

    state = zmk_usb_bridge_gui_state_get();
    if (strcmp(state->receiver_state, "connecting") == 0 || stub_connect_pending) {
        zmk_usb_bridge_gui_protocol_emit_error(
            request_id,
            "connect_candidate",
            "connect_busy",
            "connect in progress");
        return;
    }

    if (strcmp(state->receiver_state, "connected") == 0) {
        zmk_usb_bridge_gui_protocol_emit_error(
            request_id,
            "connect_candidate",
            "invalid_state",
            "connect_candidate is not allowed while connected");
        return;
    }

    if (candidate_generation != state->candidate_generation) {
        zmk_usb_bridge_gui_protocol_emit_error(
            request_id,
            "connect_candidate",
            "stale_candidate_generation",
            "candidate_generation is stale");
        return;
    }

    if (!zmk_usb_bridge_gui_state_select_candidate(candidate_id)) {
        zmk_usb_bridge_gui_protocol_emit_error(
            request_id,
            "connect_candidate",
            "candidate_not_found",
            "candidate_id not found");
        return;
    }

    zmk_usb_bridge_gui_protocol_emit_ack(request_id, "connect_candidate");
    if (strcmp(state->receiver_state, "scanning") == 0) {
        reset_stub_async_sequences();
        zmk_usb_bridge_gui_protocol_emit_scan_complete(
            state->candidate_generation, "stopped", state->candidate_count, NULL);
    }
    zmk_usb_bridge_gui_state_connect_candidate();
    zmk_usb_bridge_gui_protocol_emit_connection_state(
        "connecting", NULL, NULL, NULL, NULL);
    now_ms = k_uptime_get();
    stub_connect_pending = true;
    stub_connect_complete_due_at_ms = now_ms + STUB_CONNECT_COMPLETE_DELAY_MS;
}

static void handle_bond_erase(int request_id)
{
    int cleared_count;
    const struct zmk_usb_bridge_gui_state *state;

    zmk_usb_bridge_gui_protocol_emit_ack(request_id, "bond_erase");
    reset_stub_async_sequences();
    cleared_count = zmk_usb_bridge_gui_state_reset_bonds();
    zmk_usb_bridge_gui_protocol_emit_connection_state(
        "idle", NULL, NULL, NULL, NULL);
    zmk_usb_bridge_gui_protocol_emit_bonds_cleared(cleared_count);
    state = zmk_usb_bridge_gui_state_get();
    zmk_usb_bridge_gui_protocol_emit_status_snapshot(state);
    zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(state);
}

int zmk_usb_bridge_gui_protocol_handle_line(const char *line)
{
    int request_id = -1;
    char command_name[JSON_SHORT_VALUE_BUFFER_SIZE];

    if (line == NULL || strstr(line, "\"type\":\"command\"") == NULL) {
        return -1;
    }

    if (extract_integer_field(line, "\"request_id\"", &request_id) != 0) {
        return -1;
    }

    if (strstr(line, "\"name\":\"get_status\"") != NULL) {
        handle_get_status(request_id);
        return 0;
    }

    if (strstr(line, "\"name\":\"scan_start\"") != NULL) {
        handle_scan_start(request_id);
        return 0;
    }

    if (strstr(line, "\"name\":\"get_candidates\"") != NULL) {
        handle_get_candidates(request_id);
        return 0;
    }

    if (strstr(line, "\"name\":\"connect_candidate\"") != NULL) {
        handle_connect_candidate(line, request_id);
        return 0;
    }

    if (strstr(line, "\"name\":\"bond_erase\"") != NULL) {
        handle_bond_erase(request_id);
        return 0;
    }

    zmk_usb_bridge_gui_protocol_emit_error(
        request_id,
        extract_string_field(line, "\"name\"", command_name, sizeof(command_name)) == 0
            ? command_name
            : "unknown",
        "unsupported_command",
        "command name is not supported");
    return -1;
}

void zmk_usb_bridge_gui_protocol_poll(void)
{
    const struct zmk_usb_bridge_gui_state *state = zmk_usb_bridge_gui_state_get();
    int64_t now_ms = k_uptime_get();

    if (stub_scan_stage == STUB_SCAN_STAGE_WAITING_FOR_CANDIDATE &&
        strcmp(state->receiver_state, "scanning") == 0 &&
        now_ms >= stub_scan_candidate_due_at_ms) {
        const struct zmk_usb_bridge_gui_candidate *candidate;

        if (!zmk_usb_bridge_gui_state_publish_scan_candidate()) {
            log_stub_progress("stub scan publish returned no candidate");
            stub_scan_stage = STUB_SCAN_STAGE_WAITING_FOR_COMPLETE;
            return;
        }

        state = zmk_usb_bridge_gui_state_get();
        candidate =
            zmk_usb_bridge_gui_state_get_candidate_by_index((size_t)state->candidate_count - 1U);
        log_stub_progress(
            "stub scan candidate idx=%d id=%d name=%s",
            state->candidate_count,
            candidate != NULL ? candidate->candidate_id : -1,
            (candidate != NULL && candidate->display_name != NULL) ? candidate->display_name : "<null>");
        zmk_usb_bridge_gui_protocol_emit_candidate_upsert(state, candidate);
        if (zmk_usb_bridge_gui_state_scan_has_pending_candidates()) {
            stub_scan_candidate_due_at_ms = now_ms + STUB_SCAN_CANDIDATE_DELAY_MS;
        } else {
            stub_scan_stage = STUB_SCAN_STAGE_WAITING_FOR_COMPLETE;
        }
    }

    if (stub_scan_stage == STUB_SCAN_STAGE_WAITING_FOR_COMPLETE &&
        strcmp(state->receiver_state, "scanning") == 0 &&
        now_ms >= stub_scan_complete_due_at_ms) {
        zmk_usb_bridge_gui_state_complete_scan();
        state = zmk_usb_bridge_gui_state_get();
        log_stub_progress("stub scan complete count=%d", state->candidate_count);
        zmk_usb_bridge_gui_protocol_emit_scan_complete(
            state->candidate_generation, "ok", state->candidate_count, NULL);
        stub_scan_stage = STUB_SCAN_STAGE_IDLE;
    }

    if (stub_connect_pending &&
        strcmp(state->receiver_state, "connecting") == 0 &&
        now_ms >= stub_connect_complete_due_at_ms) {
        zmk_usb_bridge_gui_state_set_connected();
        state = zmk_usb_bridge_gui_state_get();
        zmk_usb_bridge_gui_protocol_emit_connection_state(
            "connected", state->peer_name, state->peer_address, NULL, NULL);
        zmk_usb_bridge_gui_protocol_emit_telemetry_update(state);
        stub_connect_pending = false;
    }
}
