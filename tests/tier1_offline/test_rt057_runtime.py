# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.1
# artifact_id: tests/tier1_offline/test_rt057_runtime.py
# last_modified_at: 2026-11-07T21:44:09.638270+00:00
# last_modified_by: OpenAI / Codex / GPT-6 / gated-reviewer
# dependencies: [PFS-2201.01]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: F2 regression for non-integer Linux core type metadata.
# revision_source: git
# GEOVERSE_HEADER_END
"""PFS-2201.01: recorded synthetic topologies, never the test host."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
