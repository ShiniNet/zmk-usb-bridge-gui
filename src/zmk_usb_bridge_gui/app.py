from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .serial_discovery import DiscoveryConfig, discover_receiver_ports, format_receiver_port
from .ui import launch_gui


@dataclass(slots=True)
class DiscoverOptions:
    probe_hello: bool = False
    vid_pid_allowlist: tuple[tuple[int, int], ...] = ()
    timeout_s: float = 0.4
    baudrate: int = 115200


def run_discovery(options: DiscoverOptions) -> list[str]:
    candidates = discover_receiver_ports(
        DiscoveryConfig(
            vid_pid_allowlist=options.vid_pid_allowlist,
            probe_timeout_s=options.timeout_s,
            baudrate=options.baudrate,
        ),
        probe_hello=options.probe_hello,
    )
    return [format_receiver_port(candidate) for candidate in candidates]


def run_gui(argv: Sequence[str] | None = None) -> int:
    return launch_gui(argv)
