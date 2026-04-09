from __future__ import annotations

import argparse
from typing import Sequence

from . import __version__
from .app import DiscoverOptions, run_discovery, run_gui


def _parse_vidpid(value: str) -> tuple[int, int]:
    try:
        vendor, product = value.split(":", 1)
        return int(vendor, 16), int(product, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("vid/pid must look like 1209:0001") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zmk-usb-bridge-gui")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    gui_parser = subparsers.add_parser("gui", help="Launch the PySide6 window.")
    gui_parser.set_defaults(command="gui")

    discover_parser = subparsers.add_parser("discover", help="List candidate serial ports.")
    discover_parser.add_argument(
        "--vidpid",
        action="append",
        type=_parse_vidpid,
        default=[],
        metavar="VVVV:PPPP",
        help="Optional VID/PID allowlist entry; may be repeated.",
    )
    discover_parser.add_argument(
        "--probe",
        action="store_true",
        help="Read the initial hello line from matching ports when pyserial is available.",
    )
    discover_parser.add_argument("--timeout", type=float, default=0.4, help="Probe timeout in seconds.")
    discover_parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate for hello probing.")
    discover_parser.set_defaults(command="discover")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "discover":
        options = DiscoverOptions(
            probe_hello=bool(args.probe),
            vid_pid_allowlist=tuple(args.vidpid),
            timeout_s=float(args.timeout),
            baudrate=int(args.baudrate),
        )
        try:
            lines = run_discovery(options)
        except RuntimeError as exc:
            parser.exit(2, f"{exc}\n")
        if not lines:
            print("No serial ports matched the receiver scaffold.")
            return 0
        for line in lines:
            print(line)
        return 0

    if args.command == "gui" or args.command is None:
        try:
            return run_gui([parser.prog])
        except RuntimeError as exc:
            parser.exit(2, f"{exc}\n")

    parser.print_help()
    return 0
