#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  build_receiver_firmware.sh [--board BOARD]
                             [--build-dir DIR]
                             [--pristine]
                             [--run-id ID]
                             [--workspace-dir DIR]

Build the zmk-usb-bridge-gui receiver firmware using the Zephyr workspace that
contains this repository. The script auto-detects the local Zephyr SDK under
<workspace>/toolchains unless ZEPHYR_SDK_INSTALL_DIR is already set. Successful
builds are copied into artifacts/builds/ with a timestamped history directory
plus a refreshed latest/receiver_<board>/ snapshot.
EOF
}

detect_zephyr_sdk_dir() {
    local toolchain_root="$1/toolchains"
    if [[ ! -d "$toolchain_root" ]]; then
        return 0
    fi

    find "$toolchain_root" -mindepth 1 -maxdepth 1 -type d -name 'zephyr-sdk-*' | sort -V | tail -n 1
}

copy_if_exists() {
    local source="$1"
    local destination="$2"

    if [[ -f "$source" ]]; then
        cp "$source" "$destination"
    fi
}

BOARD="seeeduino_xiao_ble"
PRISTINE=0
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR=""
RUN_ID="$(date '+%Y%m%d_%H%M%S')"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --board)
            BOARD="${2:?missing value for --board}"
            shift 2
            ;;
        --build-dir)
            BUILD_DIR="${2:?missing value for --build-dir}"
            shift 2
            ;;
        --pristine)
            PRISTINE=1
            shift
            ;;
        --run-id)
            RUN_ID="${2:?missing value for --run-id}"
            shift 2
            ;;
        --workspace-dir)
            WORKSPACE_DIR="${2:?missing value for --workspace-dir}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n\n' "$1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

PROJECT_DIR="$WORKSPACE_DIR/zmk-usb-bridge-gui"
BUILD_DIR="${BUILD_DIR:-$PROJECT_DIR/build/firmware/$BOARD}"
ZEPHYR_SDK_INSTALL_DIR="${ZEPHYR_SDK_INSTALL_DIR:-$(detect_zephyr_sdk_dir "$WORKSPACE_DIR")}"
ARTIFACT_ROOT="$WORKSPACE_DIR/artifacts/builds"
RUN_ARTIFACT_DIR="$ARTIFACT_ROOT/${RUN_ID}_receiver_${BOARD}"
LATEST_DIR="$ARTIFACT_ROOT/latest/receiver_${BOARD}"
DEBUG_ARTIFACT_DIR="$RUN_ARTIFACT_DIR/debug"

if ! command -v west >/dev/null 2>&1; then
    printf 'west is not installed. Run the workspace bootstrap first.\n' >&2
    exit 1
fi

if [[ ! -d "$WORKSPACE_DIR/.west" ]]; then
    printf 'west workspace is not initialized in %s\n' "$WORKSPACE_DIR" >&2
    exit 1
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
    printf 'project directory not found: %s\n' "$PROJECT_DIR" >&2
    exit 1
fi

if [[ -z "$ZEPHYR_SDK_INSTALL_DIR" ]] || [[ ! -d "$ZEPHYR_SDK_INSTALL_DIR" ]]; then
    printf 'Zephyr SDK not found. Set ZEPHYR_SDK_INSTALL_DIR or install it under %s/toolchains.\n' "$WORKSPACE_DIR" >&2
    exit 1
fi

mkdir -p "$RUN_ARTIFACT_DIR" "$DEBUG_ARTIFACT_DIR" "$(dirname "$LATEST_DIR")"

BUILD_CMD=(
    west
    build
    -b "$BOARD"
    "$PROJECT_DIR"
    -d "$BUILD_DIR"
)

if [[ "$PRISTINE" -eq 1 ]]; then
    BUILD_CMD+=(--pristine)
fi

printf 'Building receiver firmware\n'
printf '  workspace: %s\n' "$WORKSPACE_DIR"
printf '  project:   %s\n' "$PROJECT_DIR"
printf '  board:     %s\n' "$BOARD"
printf '  sdk:       %s\n' "$ZEPHYR_SDK_INSTALL_DIR"
printf '  build dir: %s\n\n' "$BUILD_DIR"

(
    cd "$PROJECT_DIR"
    export ZEPHYR_SDK_INSTALL_DIR
    printf '%q ' "${BUILD_CMD[@]}" >"$DEBUG_ARTIFACT_DIR/command.txt"
    printf '\n' >>"$DEBUG_ARTIFACT_DIR/command.txt"
    "${BUILD_CMD[@]}" 2>&1 | tee "$DEBUG_ARTIFACT_DIR/build.log"
)

cat >"$RUN_ARTIFACT_DIR/README.txt" <<EOF
zmk-usb-bridge-gui receiver firmware build

board: $BOARD
run_id: $RUN_ID
project_dir: $PROJECT_DIR
build_dir: $BUILD_DIR
sdk: $ZEPHYR_SDK_INSTALL_DIR

Primary artifact:
- zephyr.uf2

Detailed build outputs are mirrored under debug/.
EOF

copy_if_exists "$BUILD_DIR/zephyr/zephyr.uf2" "$RUN_ARTIFACT_DIR/zephyr.uf2"
copy_if_exists "$BUILD_DIR/zephyr/zephyr.uf2" "$DEBUG_ARTIFACT_DIR/zephyr.uf2"
copy_if_exists "$BUILD_DIR/zephyr/zephyr.elf" "$DEBUG_ARTIFACT_DIR/zephyr.elf"
copy_if_exists "$BUILD_DIR/zephyr/zephyr.bin" "$DEBUG_ARTIFACT_DIR/zephyr.bin"
copy_if_exists "$BUILD_DIR/zephyr/zephyr.hex" "$DEBUG_ARTIFACT_DIR/zephyr.hex"
copy_if_exists "$BUILD_DIR/zephyr/zephyr.map" "$DEBUG_ARTIFACT_DIR/zephyr.map"
copy_if_exists "$BUILD_DIR/zephyr/.config" "$DEBUG_ARTIFACT_DIR/zephyr.config"
copy_if_exists "$BUILD_DIR/zephyr/zephyr.dts" "$DEBUG_ARTIFACT_DIR/zephyr.dts"

rm -rf "$LATEST_DIR"
mkdir -p "$LATEST_DIR"
cp -a "$RUN_ARTIFACT_DIR/." "$LATEST_DIR/"

printf '\nBuild outputs\n'
printf '  elf: %s/zephyr/zephyr.elf\n' "$BUILD_DIR"
printf '  uf2: %s/zephyr/zephyr.uf2\n' "$BUILD_DIR"
printf '  run: %s\n' "$RUN_ARTIFACT_DIR"
printf '  latest: %s\n' "$LATEST_DIR"
