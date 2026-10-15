"""Plan-time inflow maps using the same resolved wheel inputs as its validity check."""

from pathlib import Path

from pyflightstream.cases import SimCase
from pyflightstream.cases.freestream import field_rows_in_metres
from pyflightstream.cases.workflows._freestream import _the_custom_freestream
from pyflightstream.cases.workflows._qsteady_rotor import (
    _blade_stations_from_the_mesh,
    _the_fields_native_unit,
    qsteady_inflow_fft,
)
from pyflightstream.cases.workflows._rows import _qsteady_speed, _the_isolated_rotor, _velocity
from pyflightstream.post.inflow_tools import inflow_harmonics_map, write_inflow_harmonics
from pyflightstream.workspace._plan_products import register


def _write(case: SimCase, folder: Path) -> list[Path]:
    fft = qsteady_inflow_fft(case)
    if not fft or "radius_m" not in fft:
        return []
    custom = _the_custom_freestream(case)
    assert custom is not None
    rotor = _the_isolated_rotor(case)
    rpm = float(_qsteady_speed(case, rotor).rpm)
    speed = _velocity(case)
    _, rows = field_rows_in_metres(
        Path(custom.path),
        form=custom.form,
        source_units=custom.source_units,
        native_unit=_the_fields_native_unit(case),
    )
    stations = _blade_stations_from_the_mesh(case, rotor)
    chords = None if isinstance(stations, str) else stations[1]
    radii = fft["radius_m"]
    assert isinstance(radii, list)
    result = inflow_harmonics_map(
        rows,
        hub=rotor.origin,
        axis=rotor.axis_vector,
        radii_m=radii,
        diameter_m=rotor.diameter_m,
        v_inf_m_s=speed,
        advance_ratios=[speed / (abs(rpm) / 60 * rotor.diameter_m)],
        blades=rotor.blade_count,
        chords_m=chords,
        sense=1 if rpm > 0 else -1,
    )
    return list(write_inflow_harmonics(folder, result, overwrite=True))


register(_write)
