# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.2
# artifact_id: tests/tier1_offline/test_rt057_runtime.py
# last_modified_at: 2026-11-07T21:50:05.819391+00:00
# last_modified_by: OpenAI / Codex / GPT-6 / gated-reviewer
# dependencies: [PFS-2201.01]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: F1 exercises native topology parsers with fixed raw offline fixtures.
# revision_source: git
# GEOVERSE_HEADER_END
"""PFS-2201.01: recorded synthetic topologies, never the test host."""

import ctypes
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from pyflightstream.cases import SimCase, SolverSettings
from pyflightstream.cases.runtime import RuntimeSettings
from pyflightstream.cases.workflows._solver_settings import _settings
from pyflightstream.run import LocalExecutor, _runtime
from pyflightstream.run._runtime import resolve_runtime
from pyflightstream.script import Script
from pyflightstream.workspace import RunRecord, RunStatus
from pyflightstream.workspace._matrix_binding import _solver_from_setup
from pyflightstream.workspace.inputs import resolve_setup

# Recorded policy fixtures: hybrid Intel, homogeneous SMT, homogeneous no SMT,
# and two sockets with two NUMA nodes. Counts and expected results are independent.
TOPOLOGIES = [
    (
        {
            "vendor": "GenuineIntel",
            "physical_cores": 14,
            "logical_cores": 20,
            "p_cores": 6,
            "e_cores": 8,
            "p_logical": 12,
            "p_smt": 2,
            "smt_per_core": [2] * 6 + [1] * 8,
            "sockets": 1,
            "numa_nodes": [{"id": 0, "logical_processors": list(range(20))}],
        },
        12,
        {"KMP_HW_SUBSET": "6c:intel_core,2t", "KMP_AFFINITY": "granularity=fine,compact"},
    ),
    (
        {
            "vendor": "AuthenticAMD",
            "physical_cores": 4,
            "logical_cores": 8,
            "p_cores": 0,
            "e_cores": 0,
            "p_logical": 0,
            "p_smt": 2,
            "smt_per_core": [2] * 4,
            "sockets": 1,
            "numa_nodes": [{"id": 0, "logical_processors": list(range(8))}],
        },
        8,
        {},
    ),
    (
        {
            "vendor": "GenuineIntel",
            "physical_cores": 4,
            "logical_cores": 4,
            "p_cores": 0,
            "e_cores": 0,
            "p_logical": 0,
            "p_smt": 1,
            "smt_per_core": [1] * 4,
            "sockets": 1,
            "numa_nodes": [{"id": 0, "logical_processors": list(range(4))}],
        },
        4,
        {},
    ),
    (
        {
            "vendor": "AuthenticAMD",
            "physical_cores": 4,
            "logical_cores": 8,
            "p_cores": 0,
            "e_cores": 0,
            "p_logical": 0,
            "p_smt": 2,
            "smt_per_core": [2] * 4,
            "sockets": 2,
            "numa_nodes": [
                {"id": 0, "logical_processors": [0, 2, 4, 6]},
                {"id": 1, "logical_processors": [1, 3, 5, 7]},
            ],
        },
        4,
        {"KMP_AFFINITY": "granularity=fine,proclist=[0,2,4,6],explicit"},
    ),
]


# Fixed synthetic x64 SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX bytes, not a
# hardware capture and not built by the parser under test. Layout references:
# https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-processor_relationship
# https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-numa_node_relationship
# https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-group_affinity
# Three cores: class 8 CPUs 0/2, class 0 CPU 1, class 8 CPU 67 (group 1).
# One package spans both groups. Legacy NUMA and NUMA-Ex overlap at node 7.
# The final unrelated relationship must be skipped by its declared size.
WINDOWS_RELATIONSHIPS = bytes.fromhex("""
    00000000 30000000 01080000 00000000 00000000 00000000 00000000 00000100
    05000000 00000000 00000000 00000000
    00000000 30000000 00000000 00000000 00000000 00000000 00000000 00000100
    02000000 00000000 00000000 00000000
    00000000 30000000 00080000 00000000 00000000 00000000 00000000 00000100
    08000000 00000000 01000000 00000000
    03000000 40000000 00000000 00000000 00000000 00000000 00000000 00000200
    07000000 00000000 00000000 00000000 08000000 00000000 01000000 00000000
    01000000 30000000 07000000 00000000 00000000 00000000 00000000 00000000
    07000000 00000000 00000000 00000000
    06000000 40000000 07000000 00000000 00000000 00000000 00000000 00000200
    07000000 00000000 00000000 00000000 08000000 00000000 01000000 00000000
    02000000 08000000
""")


def windows_fixture_topology(data=WINDOWS_RELATIONSHIPS):
    """Drive detection through a fake two-call native API with literal raw bytes."""

    def query(relation, buffer, size):
        assert relation == 0xFFFF
        size._obj.value = len(data)
        if buffer is None:
            return 0
        ctypes.memmove(buffer, data, len(data))
        return 1

    native_query = MagicMock(side_effect=query)
    registry = MagicMock()
    registry.QueryValueEx.return_value = ("GenuineIntel", 1)
    # Windows DWORD is 32 bits on every host, including LP64 test runners.
    wintypes = SimpleNamespace(DWORD=ctypes.c_uint32, BOOL=ctypes.c_int32)
    with (
        patch.dict(sys.modules, {"winreg": registry, "ctypes.wintypes": wintypes}),
        patch.object(ctypes, "wintypes", wintypes, create=True),
        patch.object(
            ctypes,
            "WinDLL",
            create=True,
            return_value=SimpleNamespace(GetLogicalProcessorInformationEx=native_query),
        ),
        patch.object(_runtime, "os", SimpleNamespace(name="nt")),
    ):
        result = _runtime.detect_topology()
    assert native_query.call_count == 2
    registry.QueryValueEx.assert_called_once_with(
        registry.OpenKey.return_value.__enter__.return_value, "VendorIdentifier"
    )
    return result


class RuntimeTopologyParserTests(unittest.TestCase):
    def test_windows_raw_relationships(self):
        self.assertEqual(
            windows_fixture_topology(),
            {
                "vendor": "GenuineIntel",
                "physical_cores": 3,
                "logical_cores": 4,
                "p_cores": 2,
                "e_cores": 1,
                "p_logical": 3,
                "p_smt": 2,
                "smt_per_core": [2, 1, 1],
                "sockets": 1,
                "cores": [
                    {"efficiency_class": 8, "logical_processors": [0, 2]},
                    {"efficiency_class": 0, "logical_processors": [1]},
                    {"efficiency_class": 8, "logical_processors": [67]},
                ],
                "numa_nodes": [{"id": 7, "logical_processors": [0, 1, 2, 67]}],
            },
        )

    def test_windows_malformed_and_incomplete_relationships_are_refused(self):
        cases = [
            (b"\0" * 8, "Invalid CPU relationship record"),
            (WINDOWS_RELATIONSHIPS[:-1], "Invalid CPU relationship record"),
            (WINDOWS_RELATIONSHIPS[:48], "Incomplete CPU topology"),
            (
                WINDOWS_RELATIONSHIPS[:30] + b"\x02\0" + WINDOWS_RELATIONSHIPS[32:],
                "Invalid CPU group affinity record",
            ),
        ]
        for data, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                windows_fixture_topology(data)

    def test_linux_raw_sysfs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # CPU 4 is CPU 0's SMT sibling. Core IDs repeat across packages.
            # CPU 3 is offline and deliberately has no topology files.
            rows = [
                (0, 0, 0, 2, 7),
                (1, 0, 1, 1, 7),
                (2, 1, 0, 2, 3),
                (4, 0, 0, 2, 7),
                (5, 1, 1, None, None),
            ]
            for cpu, socket, core, kind, node in rows:
                cpu_dir = root / "cpu" / f"cpu{cpu}"
                topology = cpu_dir / "topology"
                topology.mkdir(parents=True)
                (topology / "physical_package_id").write_text(f"{socket}\n")
                (topology / "core_id").write_text(f"{core}\n")
                if kind is not None:
                    (topology / "core_type").write_text(f"{kind}\n")
                if node is not None:
                    (cpu_dir / f"node{node}").mkdir()
                if cpu != 0:
                    (cpu_dir / "online").write_text("1\n")
            offline = root / "cpu/cpu3"
            offline.mkdir()
            (offline / "online").write_text("0\n")
            cpuinfo = root / "cpuinfo"
            cpuinfo.write_text("processor\t: 0\nvendor_id\t: GenuineIntel\n")
            paths = {"/sys/devices/system/cpu": root / "cpu", "/proc/cpuinfo": cpuinfo}
            with (
                patch.object(_runtime, "Path", side_effect=paths.__getitem__),
                patch.object(_runtime, "os", SimpleNamespace(name="posix")),
                patch.object(_runtime, "platform", SimpleNamespace(system=lambda: "Linux")),
            ):
                detected = _runtime.detect_topology()
            self.assertEqual(detected["vendor"], "GenuineIntel")
            self.assertEqual(detected["physical_cores"], 4)
            self.assertEqual(detected["logical_cores"], 5)
            self.assertEqual(detected["sockets"], 2)
            self.assertEqual((detected["p_cores"], detected["e_cores"]), (2, 2))
            self.assertEqual((detected["p_logical"], detected["p_smt"]), (3, 2))
            self.assertEqual(sorted(detected["smt_per_core"]), [1, 1, 1, 2])
            self.assertEqual(
                sorted(
                    (c["efficiency_class"], sorted(c["logical_processors"]))
                    for c in detected["cores"]
                ),
                [(0, [5]), (1, [1]), (2, [0, 4]), (2, [2])],
            )
            self.assertEqual(
                sorted(detected["numa_nodes"], key=lambda n: n["id"]),
                [
                    {"id": 1, "logical_processors": [5]},
                    {"id": 3, "logical_processors": [2]},
                    {"id": 7, "logical_processors": [0, 1, 4]},
                ],
            )


class RuntimeTests(unittest.TestCase):
    def test_linux_non_integer_core_type_falls_back_to_zero(self):
        # Raw sysfs text reaches the real detector; no normalized topology is mocked.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            topology = root / "cpu/cpu0/topology"
            topology.mkdir(parents=True)
            (topology / "physical_package_id").write_text("0\n")
            (topology / "core_id").write_text("0\n")
            (topology / "core_type").write_text("unknown\n")
            (root / "cpuinfo").write_text("vendor_id\t: GenuineIntel\n")
            paths = {"/sys/devices/system/cpu": root / "cpu", "/proc/cpuinfo": root / "cpuinfo"}
            with patch.object(_runtime, "Path", side_effect=paths.__getitem__):
                try:
                    detected = _runtime._linux_topology()
                except ValueError as error:
                    self.fail(f"Non-integer core_type must degrade to class 0: {error}")
            self.assertEqual(
                detected["cores"], [{"efficiency_class": 0, "logical_processors": [0]}]
            )
            self.assertEqual(detected["p_cores"], 0)
            self.assertEqual(detected["e_cores"], 0)
            self.assertEqual(detected["numa_nodes"], [{"id": 0, "logical_processors": [0]}])

    def test_fixture_emission_environment_and_record(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "solver.exe"
            exe.touch()
            executor = LocalExecutor(exe)
            for topology, threads, environment in TOPOLOGIES:
                for affinity in ("auto", "all"):
                    with self.subTest(topology=topology, affinity=affinity):
                        case = SimCase(
                            sim_id="1",
                            aircraft="fixture",
                            recipe="steady",
                            sweep={"type": "alpha", "values": [0.0]},
                            variables={"VELOCITY": "10"},
                            solver=SolverSettings(
                                runtime=RuntimeSettings(max_threads="auto", affinity=affinity)
                            ),
                        )
                        with patch(
                            "pyflightstream.run._runtime.detect_topology", return_value=topology
                        ):
                            resolved = executor.resolve_case_runtime(case)
                        script = Script("26.124")
                        _settings(resolved, script)
                        self.assertIn(f"SET_MAX_PARALLEL_THREADS {threads}\n", script.render())
                        self.assertEqual(
                            executor.runtime_environment, environment if affinity == "auto" else {}
                        )
                        evidence = script.solver_setup.model_dump(mode="json")["runtime"]
                        self.assertEqual(evidence["topology"], topology)
                        self.assertEqual(evidence["max_threads"], threads)
                        self.assertEqual(evidence["affinity"], affinity)
                        record = RunRecord(
                            run_id="runtime",
                            sim_id="1",
                            point={},
                            fs_version_requested="26.124",
                            package_version="0.56.0",
                            script_sha256="0" * 64,
                            raw_flag=False,
                            status=RunStatus.CONVERGED,
                            solver_setup=script.solver_setup.model_dump(mode="json"),
                        )
                        restored = RunRecord.model_validate_json(record.model_dump_json())
                        self.assertEqual(restored.solver_setup["runtime"], evidence)

                        script_path = Path(folder) / "script.txt"
                        script_path.write_text(script.render())
                        # Windows local runs use the progress helper even without reporting.
                        # Intercept that launch boundary: no executable is started.
                        with (
                            patch(
                                "pyflightstream.run._executors._run_with_progress",
                                return_value=(0, "", "", False),
                            ) as launch,
                            patch.dict(
                                os.environ, {"KMP_HW_SUBSET": "stale", "KMP_AFFINITY": "stale"}
                            ),
                            patch(
                                "pyflightstream.run._executors._counter_total_steps", return_value=1
                            ),
                        ):
                            executor.run_script(script_path, Path(folder))
                            effective = launch.call_args.kwargs["env"]
                            self.assertEqual(
                                {
                                    key: value
                                    for key, value in effective.items()
                                    if key in ("KMP_HW_SUBSET", "KMP_AFFINITY")
                                },
                                environment if affinity == "auto" else {},
                            )
                            self.assertEqual(os.environ["KMP_HW_SUBSET"], "stale")

            legacy = case.model_copy(update={"solver": SolverSettings()})
            with patch("pyflightstream.run._runtime.detect_topology", side_effect=AssertionError):
                self.assertIs(executor.resolve_case_runtime(legacy), legacy)
            self.assertEqual(executor.runtime_environment, {})
            legacy_script = Script("26.124")
            _settings(legacy, legacy_script)
            self.assertNotIn("SET_MAX_PARALLEL_THREADS", legacy_script.render())

    def test_integer_unset_and_input_validation(self):
        for topology, _, _ in TOPOLOGIES:
            self.assertEqual(
                resolve_runtime(RuntimeSettings(max_threads=3, affinity="all"), topology)[
                    "max_threads"
                ],
                3,
            )
            resolved = resolve_runtime(RuntimeSettings(), topology)
            self.assertIsNone(resolved["max_threads"])
            self.assertEqual(resolved["environment"], {})
        for value in (0, -1, True, 1.5, "4", "automatic"):
            with self.assertRaises(ValidationError):
                RuntimeSettings(max_threads=value)
        with self.assertRaises(ValidationError):
            RuntimeSettings(affinity="compact")
        with tempfile.TemporaryDirectory() as folder:
            inputs = Path(folder)
            (inputs / "setups").mkdir()
            (inputs / "setups/s001.toml").write_text(
                '[runtime]\nmax_threads = "auto"\naffinity = "all"\n'
            )
            artifact = resolve_setup(inputs, "s001")
            self.assertEqual(artifact.settings["runtime"]["max_threads"], "auto")
            self.assertEqual(_solver_from_setup(artifact, "s001").runtime.affinity, "all")


if __name__ == "__main__":
    unittest.main()
