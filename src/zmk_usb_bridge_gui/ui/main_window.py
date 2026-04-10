from __future__ import annotations

import importlib
import sys
from typing import Sequence

from ..protocol import PROTOCOL_CHANNEL, PROTOCOL_PRODUCT

DEFAULT_RECEIVER_VID_PID_ALLOWLIST = ((0x2FE3, 0x0012),)


def _load_qt():
    try:
        widgets = importlib.import_module("PySide6.QtWidgets")
        qtcore = importlib.import_module("PySide6.QtCore")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PySide6 is required to launch the GUI. Install the optional 'gui' dependency group first."
        ) from exc
    return widgets, qtcore


def build_main_window():
    widgets, qtcore = _load_qt()

    window = widgets.QMainWindow()
    window.setWindowTitle("zmk-usb-bridge-gui")
    window.resize(960, 560)

    central = widgets.QWidget(window)
    root = widgets.QVBoxLayout(central)
    root.setContentsMargins(20, 20, 20, 20)
    root.setSpacing(12)

    title = widgets.QLabel("zmk-usb-bridge-gui")
    title.setStyleSheet("font-size: 22px; font-weight: 700;")
    subtitle = widgets.QLabel(
        "Desktop app skeleton for the ZMK USB bridge GUI PoC. "
        "Discovery and protocol parsing are wired, but receiver control is still stubbed."
    )
    subtitle.setWordWrap(True)

    summary = widgets.QFrame()
    summary.setFrameShape(widgets.QFrame.Shape.StyledPanel)
    summary_layout = widgets.QGridLayout(summary)
    summary_layout.setHorizontalSpacing(18)
    summary_layout.setVerticalSpacing(8)

    connection_value = widgets.QLabel("not connected")
    discovery_value = widgets.QLabel("idle")
    protocol_value = widgets.QLabel("v1")
    connection_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    discovery_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)
    protocol_value.setTextInteractionFlags(qtcore.Qt.TextInteractionFlag.TextSelectableByMouse)

    summary_layout.addWidget(widgets.QLabel("Connection"), 0, 0)
    summary_layout.addWidget(connection_value, 0, 1)
    summary_layout.addWidget(widgets.QLabel("Discovery"), 1, 0)
    summary_layout.addWidget(discovery_value, 1, 1)
    summary_layout.addWidget(widgets.QLabel("Protocol"), 2, 0)
    summary_layout.addWidget(protocol_value, 2, 1)

    ports_view = widgets.QPlainTextEdit()
    ports_view.setReadOnly(True)
    ports_view.setPlaceholderText("Serial discovery results will appear here.")

    controls = widgets.QHBoxLayout()
    refresh_button = widgets.QPushButton("Refresh port discovery")
    refresh_button.setDefault(True)
    clear_button = widgets.QPushButton("Clear")
    controls.addWidget(refresh_button)
    controls.addWidget(clear_button)
    controls.addStretch(1)

    status_bar = widgets.QStatusBar()
    window.setStatusBar(status_bar)

    def is_gui_port(candidate) -> bool:
        return (
            candidate.hello_verified
            and candidate.hello_product == PROTOCOL_PRODUCT
            and candidate.hello_channel == PROTOCOL_CHANNEL
        )

    def refresh_ports() -> None:
        try:
            from ..serial_discovery import (
                DiscoveryConfig,
                SerialDiscoveryError,
                discover_receiver_ports,
                format_receiver_port,
            )
        except ImportError as exc:  # pragma: no cover - dependency absence is expected in this environment.
            discovery_value.setText("unavailable")
            ports_view.setPlainText(f"Serial discovery unavailable: {exc}")
            status_bar.showMessage("serial discovery unavailable")
            return

        try:
            candidates = discover_receiver_ports(
                DiscoveryConfig(vid_pid_allowlist=DEFAULT_RECEIVER_VID_PID_ALLOWLIST),
                probe_hello=True,
            )
        except SerialDiscoveryError as exc:
            discovery_value.setText("unavailable")
            ports_view.setPlainText(str(exc))
            status_bar.showMessage("serial discovery unavailable")
            return
        if not candidates:
            discovery_value.setText("0 candidates")
            connection_value.setText("receiver not found")
            protocol_value.setText("n/a")
            ports_view.setPlainText("No serial ports matched the receiver scaffold.")
            status_bar.showMessage("no serial ports found")
            return

        gui_candidates = [candidate for candidate in candidates if is_gui_port(candidate)]
        other_candidates = [candidate for candidate in candidates if not is_gui_port(candidate)]

        lines = [format_receiver_port(candidate) for candidate in gui_candidates]
        if other_candidates:
            if lines:
                lines.append("")
            lines.append("Ignored non-GUI ports:")
            lines.extend(format_receiver_port(candidate) for candidate in other_candidates)

        ports_view.setPlainText(
            "\n".join(lines) if lines else "No GUI control port replied to hello."
        )

        if not gui_candidates:
            discovery_value.setText("0 gui port(s)")
            connection_value.setText("receiver not verified")
            protocol_value.setText("n/a")
            status_bar.showMessage("no GUI control port verified")
            return

        if len(gui_candidates) == 1:
            connection_value.setText("receiver detected")
        else:
            connection_value.setText("multiple receivers")

        first_protocol_version = gui_candidates[0].hello_protocol_version
        protocol_value.setText(
            f"v{first_protocol_version}" if first_protocol_version is not None else "n/a"
        )
        discovery_value.setText(f"{len(gui_candidates)} gui port(s)")
        status_bar.showMessage(f"verified {len(gui_candidates)} GUI control port(s)")

    def clear_ports() -> None:
        ports_view.clear()
        discovery_value.setText("idle")
        status_bar.showMessage("cleared")

    refresh_button.clicked.connect(refresh_ports)
    clear_button.clicked.connect(clear_ports)

    root.addWidget(title)
    root.addWidget(subtitle)
    root.addWidget(summary)
    root.addLayout(controls)
    root.addWidget(ports_view, 1)
    window.setCentralWidget(central)
    window.setStatusTip("Skeleton GUI for the zmk-usb-bridge-gui PoC.")
    refresh_ports()
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
