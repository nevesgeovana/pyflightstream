# %% [markdown]
# # Steady polar of a synthetic NACA 0012 wing
#
# This example runs a steady angle-of-attack polar end to end:
#
# 1. generate a committable NACA 0012 wing mesh from code alone;
# 2. build one version-validated FlightStream script per angle;
# 3. show the version awareness: the same build request is refused for a
#    FlightStream version without recorded evidence;
# 4. optionally execute the solver and assemble the polar table.
#
# Without a FlightStream installation the example still runs steps 1 to 3
# (everything up to the solver is pure Python). To execute the sweep, pass
# the explicit path of your licensed FlightStream executable:
#
# ```
# python examples/steady_polar.py C:/path/to/FlightStream.exe
# ```
#
# The executable path is always explicit input, never read from
# environment variables or guessed.

# %%
"""Steady polar example: synthetic wing, version-validated scripts, optional run."""

import sys
import tempfile
from pathlib import Path

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.qa.geometry import WingSpec, generate_wing_stl
from pyflightstream.results import parse_loads
from pyflightstream.run import LocalExecutor
from pyflightstream.script import Script

FS_VERSION = "26.12"  # vendor alias; the canonical identifier 26.120 works too
ALPHAS_DEG = [-4.0, -2.0, 0.0, 2.0, 4.0, 6.0, 8.0]
VELOCITY_M_S = 30.0

workdir = Path(tempfile.mkdtemp(prefix="pyfs_steady_polar_"))
print(f"working directory: {workdir}")

# %% [markdown]
# ## 1. Synthetic geometry
#
# The wing comes from `pyflightstream.qa.geometry`: a rectangular
# aspect-ratio-8 NACA 0012 wing written as ASCII STL in meters, chord
# along +X, span along +Y. Being generated from code, it is fully
# reproducible and no proprietary geometry is involved. Finite-wing
# theory anchors the expected lift slope near
# 2*pi / (1 + 2/AR) = 5.0 per radian, a built-in sanity check.

# %%
wing = WingSpec(naca="0012", chord_m=1.0, span_m=8.0)
stl_path = generate_wing_stl(wing, (workdir / "naca0012.stl").resolve())
print(f"wing STL: {stl_path} (AR {wing.aspect_ratio:g}, area {wing.area_m2:g} m^2)")


# %% [markdown]
# ## 2. Version-validated scripts
#
# Every `emit` is validated against the command database for the
# requested FlightStream version: name, argument types, enum values,
# and emission phase ordering. A typo or a command unavailable in the
# version fails here, at build time, with the manual citation, instead
# of failing silently inside the solver.


# %%
def build_polar_point(version: str, alpha_deg: float, loads_name: str) -> Script:
    """Build the steady one-point script for one angle of attack.

    Parameters
    ----------
    version : str
        Target FlightStream version, canonical or alias.
    alpha_deg : float
        Angle of attack in degrees, positive nose up.
    loads_name : str
        File name of the loads spreadsheet, written into the solver's
        working directory.

    Returns
    -------
    Script
        The validated script, ready to render.
    """
    script = Script(version=version)
    script.comment(f"steady polar example, alpha {alpha_deg:+.1f} deg")
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "STL", str(stl_path), clear=True)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    script.emit(
        "FLUID_PROPERTIES",  # sea-level ISA air
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.7894e-05,
        specific_heat_ratio=1.4,
    )
    script.emit("SET_FREESTREAM", "CONSTANT")
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="INCOMPRESSIBLE",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="NONE",
        wall_collision_avoidance="DISABLE",
    )
    script.emit("SOLVER_SET_AOA", alpha_deg)
    script.emit("SOLVER_SET_VELOCITY", VELOCITY_M_S)
    script.emit("SOLVER_SET_REF_VELOCITY", VELOCITY_M_S)
    script.emit("SOLVER_SET_REF_AREA", wing.area_m2)
    script.emit("SOLVER_SET_REF_LENGTH", wing.chord_m)
    script.emit("SOLVER_SET_ITERATIONS", 500)
    script.emit("SOLVER_SET_CONVERGENCE", 1e-5)
    script.emit("START_SOLVER")
    script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    script.emit("SET_LOADS_AND_MOMENTS_UNITS", "COEFFICIENTS")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", loads_name)
    script.emit("CLOSE_FLIGHTSTREAM")
    return script


scripts = {
    alpha: build_polar_point(FS_VERSION, alpha, f"loads_a{i}.txt")
    for i, alpha in enumerate(ALPHAS_DEG)
}
print(f"built {len(scripts)} validated scripts for FlightStream {FS_VERSION}")
print("--- first script ---")
print(scripts[ALPHAS_DEG[0]].render())

# %% [markdown]
# ## 3. Version awareness
#
# The same build request against FlightStream 26.0 is refused: the
# database records no evidence for that version yet (its column in the
# compatibility matrix is honestly empty), and the builder refuses to
# emit what it cannot back with evidence.

# %%
try:
    build_polar_point("26.0", 0.0, "loads.txt")
except CommandNotInVersionError as error:
    print(f"refused for 26.0, as it should be:\n  {error}")

# %% [markdown]
# ## 4. Optional: execute the sweep
#
# With a licensed executable the sweep runs headless (`-hidden
# --script`), each loads spreadsheet is parsed, and the polar table is
# assembled with the lift slope against the finite-wing anchor.

# %%
fs_exe = sys.argv[1] if len(sys.argv) > 1 else None
if fs_exe is None:
    print("no executable given: stopping after the dry build (pass the .exe path to run)")
else:
    import numpy as np

    executor = LocalExecutor(fs_exe)
    rows = []
    for i, alpha in enumerate(ALPHAS_DEG):
        script_path = (workdir / f"polar_a{i}.txt").resolve()
        script_path.write_text(scripts[alpha].render(), encoding="utf-8")
        result = executor.run_script(script_path, working_dir=workdir, timeout_s=900.0)
        if result.failed:
            evidence = result.log_text or result.stderr or f"return code {result.return_code}"
            raise RuntimeError(f"solver failed at alpha {alpha:+.1f} deg: {evidence}")
        loads_text = (workdir / f"loads_a{i}.txt").read_text(encoding="utf-8", errors="replace")
        report = parse_loads(loads_text, requested_version=FS_VERSION)
        rows.append((alpha, report.total["CL"], report.total["CDi"], report.current_iteration))
        print(f"alpha {alpha:+5.1f} deg: CL {rows[-1][1]:+.4f}  CDi {rows[-1][2]:.5f}")

    alphas_rad = np.radians([row[0] for row in rows])
    slope = float(np.polyfit(alphas_rad, [row[1] for row in rows], 1)[0])
    anchor = 2 * np.pi / (1 + 2 / wing.aspect_ratio)
    print(f"lift slope {slope:.2f} per rad (finite-wing anchor {anchor:.2f})")
