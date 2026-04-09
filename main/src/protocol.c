#include "zmk_usb_bridge_gui/protocol.h"

#include "zmk_usb_bridge_gui/runtime_state.h"
#include "zmk_usb_bridge_gui/usb_channel.h"

#include <stdio.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/util.h>

#define PROTOCOL_BUFFER_SIZE CONFIG_ZMK_USB_BRIDGE_GUI_PROTOCOL_BUFFER_SIZE
#define JSON_SHORT_VALUE_BUFFER_SIZE 64
#define JSON_TEXT_VALUE_BUFFER_SIZE 160
#define OPTIONAL_DETAIL_SUFFIX_BUFFER_SIZE \
    (JSON_SHORT_VALUE_BUFFER_SIZE + JSON_TEXT_VALUE_BUFFER_SIZE + 32)
#define ZMK_USB_BRIDGE_GUI_FIRMWARE_VERSION "0.1.0"

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

static void format_active_candidate_json(
    const struct zmk_usb_bridge_gui_state *state,
    char *ble_address_json,
    size_t ble_address_json_size,
    char *display_name_json,
    size_t display_name_json_size)
{
    json_string_or_null(
        state->active_candidate.ble_address, ble_address_json, ble_address_json_size);
    json_string_or_null(
        state->active_candidate.display_name, display_name_json, display_name_json_size);
}

static void format_optional_code_suffix(
    const char *code,
    char *suffix_buffer,
    size_t suffix_buffer_size)
{
    char code_json[JSON_SHORT_VALUE_BUFFER_SIZE];

    if (code == NULL) {
        snprintk(suffix_buffer, suffix_buffer_size, "");
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
        snprintk(suffix_buffer, suffix_buffer_size, "");
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
    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"hello\",\"product\":\"zmk-usb-bridge-gui\","
        "\"protocol_version\":1,\"channel\":\"gui\","
        "\"board\":%s,\"firmware_version\":%s}",
        board_json,
        firmware_version_json);
    emit_line(buffer);
}

void zmk_usb_bridge_gui_protocol_emit_status_snapshot(
    const struct zmk_usb_bridge_gui_state *state)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char receiver_state_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char peer_name_json[JSON_TEXT_VALUE_BUFFER_SIZE];
    char peer_address_json[JSON_SHORT_VALUE_BUFFER_SIZE];

    json_string_or_null(state->receiver_state, receiver_state_json, sizeof(receiver_state_json));
    json_string_or_null(state->peer_name, peer_name_json, sizeof(peer_name_json));
    json_string_or_null(state->peer_address, peer_address_json, sizeof(peer_address_json));

    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"status_snapshot\",\"receiver_state\":%s,"
        "\"peer_name\":%s,\"peer_address\":%s,\"scan_in_progress\":%s,"
        "\"candidate_generation\":%d,\"candidate_count\":%d}",
        receiver_state_json,
        peer_name_json,
        peer_address_json,
        state->scan_in_progress ? "true" : "false",
        state->candidate_generation,
        state->candidate_count);
    emit_line(buffer);
}

void zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(
    const struct zmk_usb_bridge_gui_state *state)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char ble_address_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char display_name_json[JSON_TEXT_VALUE_BUFFER_SIZE];

    if (state->candidate_count == 0) {
        snprintk(
            buffer,
            sizeof(buffer),
            "{\"type\":\"candidate_snapshot\",\"candidate_generation\":%d,"
            "\"candidates\":[]}",
            state->candidate_generation);
        emit_line(buffer);
        return;
    }

    format_active_candidate_json(
        state,
        ble_address_json,
        sizeof(ble_address_json),
        display_name_json,
        sizeof(display_name_json));

    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"candidate_snapshot\",\"candidate_generation\":%d,"
        "\"candidates\":[{\"candidate_id\":%d,\"ble_address\":%s,"
        "\"display_name\":%s,\"connectable\":true,"
        "\"has_hid_service\":true,\"has_keyboard_appearance\":true,"
        "\"rssi\":%d}]}",
        state->candidate_generation,
        state->active_candidate.candidate_id,
        ble_address_json,
        display_name_json,
        state->active_candidate.rssi);
    emit_line(buffer);
}

void zmk_usb_bridge_gui_protocol_emit_scan_started(int candidate_generation)
{
    char buffer[PROTOCOL_BUFFER_SIZE];

    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"event\",\"name\":\"scan_started\","
        "\"candidate_generation\":%d}",
        candidate_generation);
    emit_line(buffer);
}

void zmk_usb_bridge_gui_protocol_emit_candidate_upsert(
    const struct zmk_usb_bridge_gui_state *state)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char ble_address_json[JSON_SHORT_VALUE_BUFFER_SIZE];
    char display_name_json[JSON_TEXT_VALUE_BUFFER_SIZE];

    format_active_candidate_json(
        state,
        ble_address_json,
        sizeof(ble_address_json),
        display_name_json,
        sizeof(display_name_json));

    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"event\",\"name\":\"candidate_upsert\","
        "\"candidate_generation\":%d,\"candidate\":{\"candidate_id\":%d,\"ble_address\":%s,"
        "\"display_name\":%s,"
        "\"connectable\":true,\"has_hid_service\":true,"
        "\"has_keyboard_appearance\":true,\"rssi\":%d}}",
        state->candidate_generation,
        state->active_candidate.candidate_id,
        ble_address_json,
        display_name_json,
        state->active_candidate.rssi);
    emit_line(buffer);
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
    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"event\",\"name\":\"scan_complete\","
        "\"candidate_generation\":%d,\"result\":%s,"
        "\"candidate_count\":%d%s}",
        candidate_generation,
        result_json,
        candidate_count,
        optional_code_suffix);

    emit_line(buffer);
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
    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"event\",\"name\":\"connection_state\","
        "\"state\":%s,\"peer_name\":%s,\"peer_address\":%s%s}",
        state_json,
        peer_name_json,
        peer_address_json,
        optional_detail_suffix);

    emit_line(buffer);
}

void zmk_usb_bridge_gui_protocol_emit_bonds_cleared(int cleared_count)
{
    char buffer[PROTOCOL_BUFFER_SIZE];

    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"event\",\"name\":\"bonds_cleared\","
        "\"cleared_count\":%d}",
        cleared_count);
    emit_line(buffer);
}

void zmk_usb_bridge_gui_protocol_emit_ack(int request_id, const char *name)
{
    char buffer[PROTOCOL_BUFFER_SIZE];
    char name_json[JSON_SHORT_VALUE_BUFFER_SIZE];

    json_string_or_null(name, name_json, sizeof(name_json));
    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"ack\",\"request_id\":%d,\"name\":%s,"
        "\"accepted\":true}",
        request_id,
        name_json);
    emit_line(buffer);
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
    snprintk(
        buffer,
        sizeof(buffer),
        "{\"type\":\"error\",\"request_id\":%d,\"name\":%s,"
        "\"code\":%s,\"message\":%s}",
        request_id,
        name_json,
        code_json,
        message_json);
    emit_line(buffer);
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

    zmk_usb_bridge_gui_state_prepare_scan();
    state = zmk_usb_bridge_gui_state_get();

    zmk_usb_bridge_gui_protocol_emit_ack(request_id, "scan_start");
    zmk_usb_bridge_gui_protocol_emit_scan_started(state->candidate_generation);
    zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(state);

    k_msleep(50);
    zmk_usb_bridge_gui_state_complete_scan();
    state = zmk_usb_bridge_gui_state_get();
    zmk_usb_bridge_gui_protocol_emit_candidate_upsert(state);
    zmk_usb_bridge_gui_protocol_emit_scan_complete(
        state->candidate_generation, "ok", state->candidate_count, NULL);
}

static void handle_connect_candidate(const char *line, int request_id)
{
    int candidate_generation = -1;
    int candidate_id = -1;
    const struct zmk_usb_bridge_gui_state *state;

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
    if (candidate_generation != state->candidate_generation) {
        zmk_usb_bridge_gui_protocol_emit_error(
            request_id,
            "connect_candidate",
            "stale_candidate_generation",
            "candidate_generation is stale");
        return;
    }

    if (!zmk_usb_bridge_gui_state_candidate_matches(candidate_id)) {
        zmk_usb_bridge_gui_protocol_emit_error(
            request_id,
            "connect_candidate",
            "candidate_not_found",
            "candidate_id not found");
        return;
    }

    zmk_usb_bridge_gui_protocol_emit_ack(request_id, "connect_candidate");
    zmk_usb_bridge_gui_state_connect_candidate();
    zmk_usb_bridge_gui_protocol_emit_connection_state(
        "connecting", NULL, NULL, NULL, NULL);

    k_msleep(150);
    zmk_usb_bridge_gui_state_set_connected();
    state = zmk_usb_bridge_gui_state_get();
    zmk_usb_bridge_gui_protocol_emit_connection_state(
        "connected", state->peer_name, state->peer_address, NULL, NULL);
}

static void handle_bond_erase(int request_id)
{
    const struct zmk_usb_bridge_gui_state *state;

    zmk_usb_bridge_gui_protocol_emit_ack(request_id, "bond_erase");
    zmk_usb_bridge_gui_state_reset_bonds();
    zmk_usb_bridge_gui_protocol_emit_connection_state(
        "idle", NULL, NULL, NULL, NULL);
    zmk_usb_bridge_gui_protocol_emit_bonds_cleared(1);
    state = zmk_usb_bridge_gui_state_get();
    zmk_usb_bridge_gui_protocol_emit_status_snapshot(state);
    zmk_usb_bridge_gui_protocol_emit_candidate_snapshot(state);
}

int zmk_usb_bridge_gui_protocol_handle_line(const char *line)
{
    int request_id = -1;

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
        "unknown",
        "unsupported_command",
        "command name is not supported in the stub");
    return -1;
}
