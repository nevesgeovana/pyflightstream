"""P0560-BASECP: an EMPIRICAL or AXISYMMETRIC base is stated by its create alone (FR-3740).

The solver stops a script at ``SET_BASE_REGION_CP <n> EMPIRICAL <cp>`` and at
``<n> AXISYMMETRIC <cp>`` on every build the marking pass serves (measured on 26.100,
26.124, 26.125, 26.126 and 26.127, reports/compat/CMP-26127_2026-11-05_base-region-cp.md),
while ``CREATE_NEW_BASE_REGION <surface> <model> <cp>`` saves both the model and the value.
So a marking that declares such a base must not emit the setter; a USER or CUSTOM base keeps
its ``<n> CUSTOM <cp>`` setter, the form the 26.124 and 26.125 marking campaigns verified.
"""

from __future__ import annotations

import pytest

from tests.tier1_offline.test_p0540_mark_26100 import _capped_strip

BUILDS = ["26.124", "26.125", "26.126", "26.127"]


def _base_lines(tmp_path, build, model):
    from pyflightstream.workspace import plan_mark_boundaries

    mesh = _capped_strip(
        tmp_path,
        f'[base_regions.wing]\nmodel = "{model}"\ncp = -0.2\n'
        'trailing_edges = {file = "top.te.txt", type = "STANDARD"}\n'
        f'[base_regions.cap]\nmodel = "{model}"\ncp = -0.3\ntrailing_edges = "auto"\n',
    )
    sidecar = mesh.with_name(mesh.name + ".boundaries.toml")
    sidecar.write_text(sidecar.read_text().replace("26.100", build))
    return [
        line.split()[0] if line.startswith("IMPORT_WAKE") else line
        for line in plan_mark_boundaries(mesh).script.splitlines()
        if line.startswith(("CREATE_NEW_BASE", "SET_BASE", "IMPORT_WAKE"))
    ]


def _in_build_order(build, lines):
    """On 26.127 every base is created first, then every import, then the auto rims
    (R1-MARK-S3, receipt wheel-routes-0550.json: imports before the creates are lost at save)."""
    if build != "26.127":
        return lines
    imports = [line for line in lines if line == "IMPORT_WAKE_EDGES_FROM_FILE"]
    autos = [line for line in lines if line.startswith("SET_BASE_REGION_TRAILING_EDGES")]
    return [line for line in lines if line not in imports + autos] + imports + autos


@pytest.mark.requirement("FR-3740")
@pytest.mark.parametrize("build", BUILDS)
@pytest.mark.parametrize("model", ["EMPIRICAL", "AXISYMMETRIC"])
def test_p0560_v127_a_stated_model_base_is_created_without_the_setter(tmp_path, build, model):
    """P0560-BASECP: the create carries model and Cp; no setter line can stop the script."""
    assert _base_lines(tmp_path, build, model) == _in_build_order(
        build,
        [
            f"CREATE_NEW_BASE_REGION 1 {model} -0.2",
            "IMPORT_WAKE_EDGES_FROM_FILE",
            f"CREATE_NEW_BASE_REGION 2 {model} -0.3",
            "SET_BASE_REGION_TRAILING_EDGES 2",
        ],
    )


@pytest.mark.requirement("FR-3740")
@pytest.mark.parametrize("build", BUILDS)
@pytest.mark.parametrize("model", ["USER", "CUSTOM"])
def test_p0560_v127_a_user_base_keeps_its_custom_setter(tmp_path, build, model):
    """P0560-BASECP: USER and CUSTOM save their value only through <n> CUSTOM <cp>."""
    assert _base_lines(tmp_path, build, model) == _in_build_order(
        build,
        [
            f"CREATE_NEW_BASE_REGION 1 {model} -0.2",
            "SET_BASE_REGION_CP 1 CUSTOM -0.2",
            "IMPORT_WAKE_EDGES_FROM_FILE",
            f"CREATE_NEW_BASE_REGION 2 {model} -0.3",
            "SET_BASE_REGION_CP 2 CUSTOM -0.3",
            "SET_BASE_REGION_TRAILING_EDGES 2",
        ],
    )
