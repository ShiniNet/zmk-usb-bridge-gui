from __future__ import annotations

import importlib
import sys
from typing import Sequence

from ..runtime import AppRuntime


def _load_qt():
    try:
        widgets = importlib.import_module("PySide6.QtWidgets")
        qtcore = importlib.import_module("PySide6.QtCore")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PySide6 is required to launch the GUI. Run `uv sync` first."
        ) from exc
    return widgets, qtcore


def build_main_window():
    widgets, qtcore = _load_qt()
    runtime = AppRuntime()

    window = widgets.QMainWindow()
    window.setWindowTitle("zmk-usb-bridge-gui")
    window.resize(1040, 640)

    central = widgets.QWidget(window)
    root = widgets.QVBoxLayout(central)
    root.setContentsMargins(20, 20, 20, 20)
    root.setSpacing(12)

    title = widgets.QLabel("zmk-usb-bridge-gui")
    title.setStyleSheet("font-size: 22px; font-weight: 700;")
    subtitle = widgets.QLabel(
        "Receiver status, candidate discovery, and manual connect flow for the ZMK USB bridge GUI PoC."
    )
    subtitle.setWordWrap(True)

    summary = widgets.QFrame()
    summary.setFrameShape(widgets.QFrame.Shape.StyledPanel)
    summary_layout = widgets.QGridLayout(summary)
    summary_layout.setHorizontalSpacing(18)
    summary_layout.setVerticalSpacing(8)

    connection_value = widgets.QLabel("searching")
    port_value = widgets.QLabel("n/a")
    protocol_value = widgets.QLabel("n/a")
    peer_name_value = widgets.QLabel("n/a")
    receiver_state_value = widgets.QLabel("idle")
    battery_value = widgets.QLabel("Disconnected")
    modifiers_value = widgets.QLabel("Disconnected")
    last_key_value = widgets.QLabel("Disconnected")
    mouse_buttons_value = widgets.QLabel("Disconnected")
    connection_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    port_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    protocol_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    peer_name_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    receiver_state_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    battery_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    modifiers_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    last_key_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    mouse_buttons_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)

    summary_layout.addWidget(widgets.QLabel("Connection"), 0, 0)
    summary_layout.addWidget(connection_value, 0, 1)
    summary_layout.addWidget(widgets.QLabel("Receiver Port"), 1, 0)
    summary_layout.addWidget(port_value, 1, 1)
    summary_layout.addWidget(widgets.QLabel("Protocol Version"), 2, 0)
    summary_layout.addWidget(protocol_value, 2, 1)
    summary_layout.addWidget(widgets.QLabel("Peer Name"), 3, 0)
    summary_layout.addWidget(peer_name_value, 3, 1)
    summary_layout.addWidget(widgets.QLabel("Receiver State"), 4, 0)
    summary_layout.addWidget(receiver_state_value, 4, 1)
    summary_layout.addWidget(widgets.QLabel("Battery"), 5, 0)
    summary_layout.addWidget(battery_value, 5, 1)
    summary_layout.addWidget(widgets.QLabel("Modifiers"), 6, 0)
    summary_layout.addWidget(modifiers_value, 6, 1)
    summary_layout.addWidget(widgets.QLabel("Last Key"), 7, 0)
    summary_layout.addWidget(last_key_value, 7, 1)
    summary_layout.addWidget(widgets.QLabel("Mouse Buttons"), 8, 0)
    summary_layout.addWidget(mouse_buttons_value, 8, 1)

    candidates_group = widgets.QGroupBox("Candidates")
    candidates_layout = widgets.QVBoxLayout(candidates_group)
    candidates_layout.setContentsMargins(12, 12, 12, 12)
    candidates_layout.setSpacing(8)

    candidates_table = widgets.QTableWidget(0, 4)
    candidates_table.setHorizontalHeaderLabels(["Display Name", "Address", "RSSI", "Tier"])
    candidates_table.setSelectionBehavior(widgets.QAbstractItemView.SelectionBehavior.SelectRows)
    candidates_table.setSelectionMode(widgets.QAbstractItemView.SelectionMode.SingleSelection)
    candidates_table.setEditTriggers(widgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    candidates_table.verticalHeader().setVisible(False)
    header = candidates_table.horizontalHeader()
    header.setSectionResizeMode(0, widgets.QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, widgets.QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, widgets.QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(3, widgets.QHeaderView.ResizeMode.ResizeToContents)
    candidates_layout.addWidget(candidates_table)

    error_frame = widgets.QFrame()
    error_layout = widgets.QVBoxLayout(error_frame)
    error_layout.setContentsMargins(12, 12, 12, 12)
    error_layout.setSpacing(6)
    error_label_title = widgets.QLabel("Last Error")
    error_label_title.setStyleSheet("font-weight: 600;")
    error_value = widgets.QLabel("None")
    error_value.setWordWrap(True)
    error_layout.addWidget(error_label_title)
    error_layout.addWidget(error_value)

    debug_group = widgets.QGroupBox("Debug Capture")
    debug_layout = widgets.QGridLayout(debug_group)
    debug_layout.setHorizontalSpacing(18)
    debug_layout.setVerticalSpacing(8)
    capture_status_value = widgets.QLabel("Unavailable")
    session_id_value = widgets.QLabel("n/a")
    log_path_value = widgets.QLabel("n/a")
    receiver_debug_port_value = widgets.QLabel("n/a")
    keyboard_log_port_value = widgets.QLabel("n/a")
    debug_error_value = widgets.QLabel("None")
    debug_error_value.setWordWrap(True)
    capture_status_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    session_id_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    log_path_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    receiver_debug_port_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    keyboard_log_port_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    debug_error_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    debug_layout.addWidget(widgets.QLabel("Capture Status"), 0, 0)
    debug_layout.addWidget(capture_status_value, 0, 1)
    debug_layout.addWidget(widgets.QLabel("Session ID"), 1, 0)
    debug_layout.addWidget(session_id_value, 1, 1)
    debug_layout.addWidget(widgets.QLabel("Log File"), 2, 0)
    debug_layout.addWidget(log_path_value, 2, 1)
    debug_layout.addWidget(widgets.QLabel("Receiver Debug Port"), 3, 0)
    debug_layout.addWidget(receiver_debug_port_value, 3, 1)
    debug_layout.addWidget(widgets.QLabel("Keyboard Log Port"), 4, 0)
    debug_layout.addWidget(keyboard_log_port_value, 4, 1)
    debug_layout.addWidget(widgets.QLabel("Capture Error"), 5, 0)
    debug_layout.addWidget(debug_error_value, 5, 1)

    controls = widgets.QHBoxLayout()
    scan_button = widgets.QPushButton("Scan")
    refresh_button = widgets.QPushButton("Refresh")
    connect_button = widgets.QPushButton("Connect")
    bond_erase_button = widgets.QPushButton("Bond Erase")
    retry_button = widgets.QPushButton("Retry")
    start_keyboard_log_button = widgets.QPushButton("Start Keyboard Log")
    stop_keyboard_log_button = widgets.QPushButton("Stop Keyboard Log")
    scan_button.setDefault(True)
    controls.addWidget(scan_button)
    controls.addWidget(refresh_button)
    controls.addWidget(connect_button)
    controls.addWidget(bond_erase_button)
    controls.addWidget(retry_button)
    controls.addWidget(start_keyboard_log_button)
    controls.addWidget(stop_keyboard_log_button)
    controls.addStretch(1)

    status_bar = widgets.QStatusBar()
    window.setStatusBar(status_bar)

    def update_candidate_selection_from_table() -> None:
        selected_items = candidates_table.selectedItems()
        if not selected_items:
            runtime.select_candidate(None)
            return
        row = selected_items[0].row()
        candidate_id = candidates_table.item(row, 0).data(qtcore.Qt.ItemDataRole.UserRole)
        runtime.select_candidate(candidate_id)

    def update_ui() -> None:
        state = runtime.state
        if state.discovery_state == "attached":
            connection_text = "receiver attached"
        elif state.discovery_state == "multiple_receivers":
            connection_text = "multiple receivers detected"
        elif state.discovery_state == "receiver_not_found":
            connection_text = "receiver not found"
        elif state.discovery_state == "discovering":
            connection_text = "searching"
        elif state.discovery_state == "disconnected":
            connection_text = "receiver disconnected"
        else:
            connection_text = state.discovery_detail

        connection_value.setText(connection_text)
        port_value.setText(state.receiver_port or "n/a")
        protocol_value.setText(f"v{state.protocol_version}" if state.protocol_version is not None else "n/a")
        peer_name_value.setText(state.peer_name or "n/a")
        receiver_state_value.setText(state.receiver_state)
        battery_value.setText(state.battery_text)
        modifiers_value.setText(state.modifiers_text)
        last_key_value.setText(state.last_key_text)
        mouse_buttons_value.setText(state.mouse_buttons_text)
        error_value.setText(state.last_error or "None")
        capture_status_value.setText("Active" if state.debug_capture_active else "Unavailable")
        session_id_value.setText(state.debug_session_id or "n/a")
        log_path_value.setText(state.debug_log_path or "n/a")
        receiver_debug_port_value.setText(state.receiver_debug_port or "n/a")
        keyboard_log_port_value.setText(state.keyboard_log_port or "n/a")
        debug_error_value.setText(state.debug_capture_error or "None")

        candidates_table.blockSignals(True)
        candidates_table.setRowCount(len(state.candidate_list))
        for row, candidate in enumerate(state.candidate_list):
            name_item = widgets.QTableWidgetItem(candidate.display_label)
            name_item.setData(qtcore.Qt.ItemDataRole.UserRole, candidate.candidate_id)
            address_item = widgets.QTableWidgetItem(candidate.ble_address)
            rssi_item = widgets.QTableWidgetItem("" if candidate.rssi is None else str(candidate.rssi))
            tier_item = widgets.QTableWidgetItem(candidate.tier_label)
            candidates_table.setItem(row, 0, name_item)
            candidates_table.setItem(row, 1, address_item)
            candidates_table.setItem(row, 2, rssi_item)
            candidates_table.setItem(row, 3, tier_item)

        selected_candidate = state.selected_candidate
        if selected_candidate is not None:
            for row in range(candidates_table.rowCount()):
                item = candidates_table.item(row, 0)
                if item is not None and item.data(qtcore.Qt.ItemDataRole.UserRole) == selected_candidate.candidate_id:
                    candidates_table.selectRow(row)
                    break
        candidates_table.blockSignals(False)

        scan_button.setEnabled(state.can_scan)
        refresh_button.setEnabled(state.can_refresh)
        connect_button.setEnabled(state.can_connect_selected)
        bond_erase_button.setEnabled(state.can_bond_erase)
        retry_button.setEnabled(state.can_retry)
        start_keyboard_log_button.setEnabled(state.can_start_keyboard_log)
        stop_keyboard_log_button.setEnabled(state.can_stop_keyboard_log)

        if state.discovery_state == "multiple_receivers" and state.multiple_receiver_ports:
            status_bar.showMessage(
                "Multiple receivers detected: " + ", ".join(state.multiple_receiver_ports)
            )
        else:
            status_bar.showMessage(state.discovery_detail)

    def on_scan_clicked() -> None:
        runtime.scan_start()
        update_ui()

    def on_refresh_clicked() -> None:
        runtime.refresh()
        update_ui()

    def on_connect_clicked() -> None:
        runtime.connect_selected()
        update_ui()

    def on_bond_erase_clicked() -> None:
        answer = widgets.QMessageBox.question(
            window,
            "Bond Erase",
            "Erase receiver bonds and return to idle state?",
        )
        if answer != widgets.QMessageBox.StandardButton.Yes:
            return
        runtime.bond_erase()
        update_ui()

    def on_retry_clicked() -> None:
        runtime.retry_discovery()
        update_ui()

    def on_start_keyboard_log_clicked() -> None:
        candidates = runtime.list_keyboard_log_candidates()
        if not candidates:
            runtime.note_keyboard_log_attach_skipped(
                "no serial ports are currently available for keyboard log capture"
            )
            widgets.QMessageBox.information(
                window,
                "Keyboard Log Capture",
                "No serial ports are currently available for keyboard log capture.",
            )
            update_ui()
            return

        labels = [runtime.format_keyboard_log_candidate(port) for port in candidates]
        preferred_index = 0
        for index, port in enumerate(candidates):
            if (
                runtime.state.preferred_keyboard_serial_number
                and port.serial_number == runtime.state.preferred_keyboard_serial_number
            ) or (
                runtime.state.preferred_keyboard_device_path
                and (
                    port.location == runtime.state.preferred_keyboard_device_path
                    or port.device == runtime.state.preferred_keyboard_device_path
                )
            ):
                preferred_index = index
                break

        choice, accepted = widgets.QInputDialog.getItem(
            window,
            "Keyboard Log Capture",
            "Select keyboard debug serial port:",
            labels,
            preferred_index,
            False,
        )
        if not accepted:
            runtime.note_keyboard_log_attach_skipped("keyboard log attach was cancelled by the user")
            update_ui()
            return

        selected_index = labels.index(choice)
        selected_port = candidates[selected_index]
        if not runtime.attach_keyboard_log(selected_port.device):
            widgets.QMessageBox.warning(
                window,
                "Keyboard Log Capture",
                "Could not start keyboard log capture. Check the capture error field for details.",
            )
        update_ui()

    def on_stop_keyboard_log_clicked() -> None:
        runtime.detach_keyboard_log()
        update_ui()

    def pump_runtime() -> None:
        runtime.tick()
        update_ui()

    scan_button.clicked.connect(on_scan_clicked)
    refresh_button.clicked.connect(on_refresh_clicked)
    connect_button.clicked.connect(on_connect_clicked)
    bond_erase_button.clicked.connect(on_bond_erase_clicked)
    retry_button.clicked.connect(on_retry_clicked)
    start_keyboard_log_button.clicked.connect(on_start_keyboard_log_clicked)
    stop_keyboard_log_button.clicked.connect(on_stop_keyboard_log_clicked)
    candidates_table.itemSelectionChanged.connect(update_candidate_selection_from_table)

    root.addWidget(title)
    root.addWidget(subtitle)
    root.addWidget(summary)
    root.addLayout(controls)
    root.addWidget(candidates_group, 1)
    root.addWidget(error_frame)
    root.addWidget(debug_group)
    window.setCentralWidget(central)
    window.setStatusTip("Phase 1 GUI for the zmk-usb-bridge-gui PoC.")

    poll_timer = qtcore.QTimer(window)
    poll_timer.setInterval(150)
    poll_timer.timeout.connect(pump_runtime)
    poll_timer.start()

    app = widgets.QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(runtime.shutdown)

    pump_runtime()
    return window


def launch_gui(argv: Sequence[str] | None = None) -> int:
    widgets, _ = _load_qt()
    qt_argv = list(argv) if argv is not None else sys.argv[:1]
    if not qt_argv:
        qt_argv = [sys.argv[0]]
    app = widgets.QApplication(qt_argv)
    window = build_main_window()
    window.show()
    return app.exec()
