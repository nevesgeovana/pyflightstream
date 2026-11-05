"""Usage: rotor_sections with induction='all' (default) or 'rotor'."""

import numpy as np
import pytest

from pyflightstream.cases import PprocSpec


@pytest.mark.requirement("FR-3630")
def test_p0551_h03_default_and_explicit_induction():
    for mode in (None, "all", "rotor"):
        entry = dict(variant="rotor_sections", rotor="ROTOR")
        if mode is not None:
            entry["induction"] = mode
        try:
            spec = PprocSpec.model_validate({"farfields": [entry]}).farfields[0]
        except ValueError as error:
            pytest.fail(f"declared induction must be accepted: {error}")
        assert getattr(spec, "induction", None) == (mode or "all")
    _mirror_edge_cases()


def _snapshot(root, mode, *, mirror=False, external=True, exported_image=False, copies=1):
    import csv
    from dataclasses import replace

    from tests.tier1_offline.test_p0551_rotor_sections import _blade_exports
    from tests.tier1_offline.test_regression_farfield_numerics import _p0470_helical_wake
    from tests.tier1_offline.test_regression_farfield_products import _p0470_post_rotor_wake

    root.mkdir()
    lines, values = _p0470_helical_wake(
        2,
        gamma=np.zeros(4) if external else np.arange(1.0, 5.0),
        radii=np.array([0.3, 0.5, 0.7, 0.9, 1.0]),
        v=30.0,
        omega=100.0,
        turns=1.0,
    )
    lines = [line + [3.1, 0.0, 2.0] for line in lines]
    if external:
        other = np.array([[3.1, 3.0, 3.0], [7.1, 3.0, 3.0]])
        lines.append(other)
        values = np.append(values, -4.0)
        if exported_image:
            lines.append(other * [1, -1, 1])
            values = np.append(values, 4.0 * exported_image)

    def prepare(ctx):
        _blade_exports(root)
        entry = dict(variant="rotor_sections", rotor="ROTOR")
        ctx.pproc = PprocSpec.model_validate({"farfields": [entry]})
        ctx.pproc.farfields[0] = ctx.pproc.farfields[0].model_copy(
            update={"induction": mode or "all"}
        )
        ctx.record_of["point"].inventory = ["Blade1", "Blade2"] + (["Wing"] if external else [])
        if mirror:
            ctx.matrix_row.variables.update(SYMMETRY="MIRROR", SYMMETRY_LOADS="true")
        point = ctx.points[0]
        ctx.points[0] = replace(
            point,
            loads=replace(point.loads, surfaces={"Blade1": {"Cx": 1.0}, "Blade2": {"Cx": 1.0}}),
        )

    with pytest.warns(UserWarning):
        _p0470_post_rotor_wake(
            root, lines, values, rotor=True, sector_copies=copies, prepare=prepare
        )
    folder = root / "post/farfield"
    with next(folder.glob("*_rotor_sections_ROTOR_strips.csv")).open() as stream:
        strips = [r for r in csv.DictReader(stream) if r["BLADE"] == "Blade1"]
    with next(folder.glob("*_rotor_sections_ROTOR.csv")).open() as stream:
        total = next(csv.DictReader(stream))
    assert total["LOCAL_VALIDATED"].lower() == str(not external).lower()
    return total, strips


@pytest.mark.requirement("FR-3630")
@pytest.mark.parametrize(
    "mirror,exported_image",
    [(False, False), (True, False), (True, True), (True, -1)],
    ids=[
        "P0551-other",
        "P0551-missing-image",
        "P0551-exported-image",
        "P0551-recorded-image-value",
    ],
)
def test_p0551_h03_other_wake_analytic_amount(tmp_path, mirror, exported_image):
    _, rotor = _snapshot(tmp_path / "rotor", "rotor", mirror=mirror, exported_image=exported_image)
    _, all_wakes = _snapshot(tmp_path / "all", None, mirror=mirror, exported_image=exported_image)
    # Finite straight vortex: Gamma (ex cross displacement)/(4 pi d^2)
    # times endpoint direction cosines. The cut quarter chord is x=2.95.
    sample = np.array([0.4, 0.6, 0.8, 0.95])

    def uz(dy, gamma):
        d2, x = dy * dy + 1.0, -0.15
        cosine = (4 - x) / np.sqrt((4 - x) ** 2 + d2) + x / np.sqrt(x * x + d2)
        return gamma * dy * cosine / (4 * np.pi * d2)

    image_gamma = -4.0 * (exported_image or 1)
    expected = uz(sample - 3.0, 4.0) + (uz(sample + 3.0, image_gamma) if mirror else 0.0)
    radii = np.array([float(r["R_M"]) for r in rotor])
    actual = np.array(
        [float(a["WT_M_S"]) - float(b["WT_M_S"]) for a, b in zip(all_wakes, rotor, strict=True)]
    )
    # CSV velocity cells are rounded to five decimal places.
    np.testing.assert_allclose(actual, np.interp(radii, sample, expected), rtol=0, atol=5e-6)


@pytest.mark.requirement("FR-3630")
@pytest.mark.parametrize("copies", [1, 3], ids=["P0551-isolated", "P0551-periodic"])
def test_p0551_h03_isolated_modes_identical(tmp_path, copies):
    a, sa = _snapshot(tmp_path / "all", "all", external=False, copies=copies)
    b, sb = _snapshot(tmp_path / "rotor", "rotor", external=False, copies=copies)
    for key in ("T_FF_RS_ROTOR", "Q_FF_RS_ROTOR"):
        assert a[key] == b[key]
    assert [r["WT_M_S"] for r in sa] == [r["WT_M_S"] for r in sb]


@pytest.mark.requirement("FR-3630")
@pytest.mark.parametrize("mode", ["all", "rotor"], ids=["P0551-all", "P0551-rotor"])
def test_p0551_h03_selection_in_both_tables(tmp_path, mode):
    total, strips = _snapshot(tmp_path / mode, mode)
    assert total.get("INDUCTION") == mode
    assert all(row.get("INDUCTION") == mode for row in strips)


@pytest.mark.requirement("FR-3630")
def test_p0551_h03_invalid_mode_and_other_variants_refused():
    for variant, mode in [("rotor_sections", "wing"), ("wake", "all")]:
        with pytest.raises(ValueError):
            PprocSpec.model_validate(
                {"farfields": [{"variant": variant, "rotor": "ROTOR", "induction": mode}]}
            )


def _mirror_edge_cases():
    from pyflightstream.farfield.rotor_sections import complete_induction_wake

    line = np.array([[0.0, 2.0, 0.0], [1.0, 2.0, 0.0]])
    lines, values, _ = complete_induction_wake(
        [], [], [], [line, line], np.array([3.0, 3.0]), mirror=True
    )
    assert len(lines) == 4
    np.testing.assert_array_equal(values, [3.0, 3.0, -3.0, -3.0])
    left = np.array([[0.0, 0.0, 0.0], [1.0, -2.0, 0.0]])
    right = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 0.0]])
    lines, _, _ = complete_induction_wake(
        [], [], [], [left, right], np.array([3.0, -3.0]), mirror=True
    )
    assert len(lines) == 2
