"""Launch CPU policy, re-expressed from the GOAL-076 detection and rules kit.

Windows EfficiencyClass distinguishes higher-performance cores from lower classes.
The homogeneous single-socket and multi-socket policies are inferred from GOAL-076,
not measured: conservative starting points for the kit's calibration to confirm.
No priority, power policy, or campaign concurrency is changed.
"""

from __future__ import annotations

import ctypes
import os
import platform
from pathlib import Path
from typing import Any

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.settings import RuntimeSettings


def resolve_runtime(settings: RuntimeSettings, topology: dict[str, Any]) -> dict[str, Any]:
    """Resolve explicit settings against a recorded topology, without consulting the host."""
    env: dict[str, str] = {}
    hybrid = (
        topology["vendor"] == "GenuineIntel" and topology["p_cores"] > 0 and topology["e_cores"] > 0
    )
    nodes = topology["numa_nodes"]
    multi = topology["sockets"] > 1 or len(nodes) > 1
    if hybrid:
        automatic = topology["p_logical"]
        if settings.affinity == "auto":
            env = {
                "KMP_HW_SUBSET": f"{topology['p_cores']}c:intel_core,{topology['p_smt']}t",
                "KMP_AFFINITY": "granularity=fine,compact",
            }
    elif multi:
        node = min(nodes, key=lambda item: item["id"])
        automatic = len(node["logical_processors"])
        if settings.affinity == "auto":
            processors = ",".join(str(cpu) for cpu in node["logical_processors"])
            env = {"KMP_AFFINITY": f"granularity=fine,proclist=[{processors}],explicit"}
    else:
        automatic = topology["logical_cores"]
    threads = automatic if settings.max_threads == "auto" else settings.max_threads
    return {
        "max_threads": threads,
        "affinity": settings.affinity,
        "environment": env,
        "topology": topology,
    }


def _summary(
    cores: list[dict[str, Any]], sockets: int, nodes: list[dict[str, Any]], vendor: str
) -> dict[str, Any]:
    """Normalize native core classes and membership into the recorded schema."""
    classes = {core["efficiency_class"] for core in cores}
    highest = max(classes)
    performance = [core for core in cores if core["efficiency_class"] == highest]
    hybrid = vendor == "GenuineIntel" and len(classes) > 1
    return {
        "vendor": vendor,
        "physical_cores": len(cores),
        "logical_cores": sum(len(c["logical_processors"]) for c in cores),
        "p_cores": len(performance) if hybrid else 0,
        "e_cores": len(cores) - len(performance) if hybrid else 0,
        "p_logical": sum(len(c["logical_processors"]) for c in performance) if hybrid else 0,
        "p_smt": max(len(c["logical_processors"]) for c in performance),
        "smt_per_core": [len(c["logical_processors"]) for c in cores],
        "cores": cores,
        "sockets": sockets,
        "numa_nodes": nodes,
    }


def _windows_relationships(
    data: bytes, size: int
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    """Parse native relationship records, retaining core and NUMA membership."""
    offset = 0
    cores: list[dict[str, Any]] = []
    nodes: dict[int, dict[str, Any]] = {}
    sockets = 0
    while offset < size:
        relation = int.from_bytes(data[offset : offset + 4], "little")
        length = int.from_bytes(data[offset + 4 : offset + 8], "little")
        if length < 8 or offset + length > size:
            raise CampaignConfigError("Invalid CPU relationship record")
        row = data[offset : offset + length]
        if relation in (0, 1, 3, 6):
            count = int.from_bytes(row[30:32], "little") if relation != 1 else 1
            if count < 1 or 32 + 16 * count > length:
                raise CampaignConfigError("Invalid CPU group affinity record")
            processors: list[int] = []
            for index in range(count):
                start = 32 + 16 * index
                mask = int.from_bytes(row[start : start + 8], "little")
                group = int.from_bytes(row[start + 8 : start + 10], "little")
                processors.extend(group * 64 + bit for bit in range(64) if mask & (1 << bit))
            if relation == 0:
                cores.append({"efficiency_class": row[9], "logical_processors": processors})
            elif relation == 3:
                sockets += 1
            else:
                number = int.from_bytes(row[8:12], "little")
                existing = nodes.get(number, {}).get("logical_processors", [])
                nodes[number] = {
                    "id": number,
                    "logical_processors": sorted(set(existing) | set(processors)),
                }
        offset += length
    return cores, sockets, list(nodes.values())


def _windows_topology() -> dict[str, Any]:
    """Read core, package and NUMA relationships through the Windows API."""
    import winreg
    from ctypes import wintypes

    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise CampaignConfigError("Runtime topology requires 64-bit Python on Windows")
    query = ctypes.WinDLL("kernel32", use_last_error=True).GetLogicalProcessorInformationEx  # type: ignore[attr-defined]
    query.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    query.restype = wintypes.BOOL
    size = wintypes.DWORD()
    query(0xFFFF, None, ctypes.byref(size))
    if not size.value:
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
    buffer = ctypes.create_string_buffer(size.value)
    if not query(0xFFFF, buffer, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
    cores, sockets, nodes = _windows_relationships(buffer.raw, size.value)
    with winreg.OpenKey(  # type: ignore[attr-defined]
        winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
        r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
    ) as key:
        vendor = str(winreg.QueryValueEx(key, "VendorIdentifier")[0])  # type: ignore[attr-defined]
    if not cores or not sockets or not nodes:
        raise CampaignConfigError("Incomplete CPU topology")
    return _summary(cores, sockets, nodes, vendor)


def _linux_topology() -> dict[str, Any]:
    """Read online processor, package, core type and NUMA membership from sysfs."""
    base = Path("/sys/devices/system/cpu")
    grouped: dict[tuple[int, int], dict[str, Any]] = {}
    nodes: dict[int, list[int]] = {}
    for folder in base.glob("cpu[0-9]*"):
        cpu = int(folder.name[3:])
        online = folder / "online"
        if online.exists() and online.read_text().strip() == "0":
            continue
        topology = folder / "topology"
        socket = int((topology / "physical_package_id").read_text())
        core = int((topology / "core_id").read_text())
        kind = topology / "core_type"
        try:
            efficiency = int(kind.read_text()) if kind.exists() else 0
        except ValueError:
            efficiency = 0
        entry = grouped.setdefault(
            (socket, core), {"efficiency_class": efficiency, "logical_processors": []}
        )
        entry["logical_processors"].append(cpu)
        memberships = list(folder.glob("node[0-9]*"))
        node = int(memberships[0].name[4:]) if memberships else socket
        nodes.setdefault(node, []).append(cpu)
    vendor = "unknown"
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("vendor_id"):
            vendor = line.split(":", 1)[1].strip()
            break
    if not grouped:
        raise CampaignConfigError("No online CPU topology")
    return _summary(
        list(grouped.values()),
        len({key[0] for key in grouped}),
        [{"id": key, "logical_processors": sorted(value)} for key, value in nodes.items()],
        vendor,
    )


def detect_topology() -> dict[str, Any]:
    """Read topology on the launch host, refusing platforms without a detector."""
    if os.name == "nt":
        return _windows_topology()
    if platform.system() == "Linux":
        return _linux_topology()
    raise CampaignConfigError("Runtime topology detection supports Windows and Linux")
