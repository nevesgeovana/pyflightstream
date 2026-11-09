"""PFS-2216 (0.57.0): the moment a fixed wing's beam receives does not depend on the cut frame.

The XZ cut's ``Moment`` is about the origin of the cut's frame, not the section's quarter chord,
so a frame off the section carries the lever of the section's forces. The same section, cut in
two frames, must give the beam one moment. The rotor route is not measured and stays as read.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.fsi.config import FixedWing, FsiConfig
from pyflightstream.fsi.loads import SectionBlock, to_elastic_axis
from tests.tier1_offline.conftest import make_uniform_blade_config

_SPAN = np.linspace(0.25, 1.85, 9)


def _block(x_qc: float, z_qc: float, *, fx: float, fz: float, about_qc: float) -> SectionBlock:
    """A section with a pure moment about its quarter chord, as exported about a frame origin.

    My about the origin = My about the quarter chord + z Fx - x Fz, nose up about +y.
    """
    k = len(_SPAN)
    return SectionBlock(
        family="wing",
        offset_m=_SPAN,
        chord_m=np.full(k, 1.0),
        x_qc_m=np.full(k, x_qc),
        z_qc_m=np.full(k, z_qc),
        fx_n_per_m=np.full(k, fx),
        fz_n_per_m=np.full(k, fz),
        moment_qc_nm_per_m=np.full(k, about_qc + z_qc * fx - x_qc * fz),
    )


def _wing(*, span_axis: str = "+Y", e_chordwise: float = 0.0) -> FsiConfig:
    data = make_uniform_blade_config(root_radius_m=0.25, tip_radius_m=1.85).model_dump()
    n = len(data["blade"]["station_radii_m"])
    data["blade"]["elastic_axis_offset_chordwise_m"] = [e_chordwise] * n
    data["blade_count"] = 1
    data["omega_rad_per_s"] = 0.0
    data["wing"] = FixedWing(self_weight=False, span_axis=span_axis).model_dump()
    return FsiConfig.model_validate(data)


def test_p0570_fix6_a_wing_cut_off_the_section_gives_the_quarter_chord_moment():
    block = _block(0.31, -0.05, fx=20.0, fz=400.0, about_qc=-30.0)
    loads = to_elastic_axis(block, _wing())
    assert loads.moment_pa_nm_per_m == pytest.approx(np.full(len(_SPAN), -30.0))


def test_p0570_fix6_the_wing_moment_does_not_depend_on_the_cut_frame():
    on_section = _block(0.0, 0.0, fx=20.0, fz=400.0, about_qc=-30.0)
    off_section = _block(0.31, -0.05, fx=20.0, fz=400.0, about_qc=-30.0)
    cfg = _wing(e_chordwise=0.04)
    near = to_elastic_axis(on_section, cfg)
    far = to_elastic_axis(off_section, cfg)
    assert far.moment_pa_nm_per_m == pytest.approx(near.moment_pa_nm_per_m)
    assert far.moment_ea_nm_per_m == pytest.approx(near.moment_ea_nm_per_m)


def test_p0570_fix6_the_wing_on_its_quarter_chord_keeps_the_export():
    block = _block(0.0, 0.0, fx=20.0, fz=400.0, about_qc=-30.0)
    loads = to_elastic_axis(block, _wing())
    assert np.array_equal(loads.moment_pa_nm_per_m, block.moment_qc_nm_per_m)


def test_p0570_fix6_a_left_wing_takes_the_same_transfer():
    block = _block(0.31, -0.05, fx=20.0, fz=400.0, about_qc=-30.0)
    mirrored = SectionBlock(
        **{
            **{name: getattr(block, name) for name in block.__dataclass_fields__},
            "offset_m": -_SPAN,
        }
    )
    loads = to_elastic_axis(mirrored, _wing(span_axis="-Y"))
    assert loads.moment_pa_nm_per_m == pytest.approx(np.full(len(_SPAN), -30.0))


def test_p0570_fix6_the_rotor_route_is_left_as_read():
    """A rotating blade is not measured: its moment stays the export's, its sign flipped."""
    data = make_uniform_blade_config(root_radius_m=0.25, tip_radius_m=1.85).model_dump()
    data["omega_rad_per_s"] = 100.0
    data["blade_count"] = 2
    cfg = FsiConfig.model_validate(data)
    block = _block(0.31, -0.05, fx=20.0, fz=400.0, about_qc=-30.0)
    loads = to_elastic_axis(block, cfg)
    assert np.array_equal(loads.moment_pa_nm_per_m, -block.moment_qc_nm_per_m)
