"""The custom free-stream fields of the tier-3 workspace (G15, the licensed probe T14).

Rows 5012 and 5014 of ``matriz_gui.fs`` run the 12_WING_PHY wing under a custom
free stream at 0 deg, each against the CONSTANT control 5013, which differs from
it in the free stream alone (``test_freestream.py``). Their two fields are written HERE, from the
wing's own mesh block, so the grid covers the body's YZ extent with a margin
this module states, and ``tests/tier1_offline/test_g15_custom_freestream.py``
holds the committed files to what this module writes.

* ``fs_uniform.txt``: vx = 30 m/s everywhere, the rows' own ``TASmps``, and
  vy = vz = 0, so the field IS the uniform free stream the control solves;
* ``fs_shear.txt``: vx = 30 + 2.5 z m/s, sheared in z about the rows' speed.

Both are the manual's STRUCTURED form: a first line ``Npts Mpts``, then the rows
``x y z vx vy vz``, y the outer index and z the inner, in metres and metres per
second in the global frame, every row at x = 0.

    python -m tests.tier3_licensed.freestreams           # report: extents, grid, files current
    python -m tests.tier3_licensed.freestreams --write   # rewrite the fields and their provenance
"""

from __future__ import annotations

import sys

from tests.support_tier3 import (
    FIELDS as FIELDS,
)
from tests.support_tier3 import (
    FOLDER as FOLDER,
)
from tests.support_tier3 import HERE as HERE
from tests.support_tier3 import (
    MARGIN_M as MARGIN_M,
)
from tests.support_tier3 import (
    MEANING as MEANING,
)
from tests.support_tier3 import (
    SHEAR_PER_S as SHEAR_PER_S,
)
from tests.support_tier3 import (
    SPEED_M_S as SPEED_M_S,
)
from tests.support_tier3 import (
    STEP_Y_M as STEP_Y_M,
)
from tests.support_tier3 import (
    STEP_Z_M as STEP_Z_M,
)
from tests.support_tier3 import (
    WING as WING,
)
from tests.support_tier3 import (
    axis as axis,
)
from tests.support_tier3 import (
    expected as expected,
)
from tests.support_tier3 import (
    extents as extents,
)
from tests.support_tier3 import (
    field_text as field_text,
)
from tests.support_tier3 import (
    grid as grid,
)
from tests.support_tier3 import (
    provenance_text as provenance_text,
)
from tests.support_tier3 import (
    stale as stale,
)

#: The rows' own speed, the ``TASmps`` of rows 5010 to 5014, m/s.
#: How far the grid reaches past the body on each side, m: half the wing's span,
#: so the tip vortices and the wake's roll-up stay inside the field.
#: The grid's spacing in y and in z, m. A linear field is reproduced exactly by
#: any spacing; these keep the file small and its rows readable.
#: The sheared field's gradient of vx in z, (m/s) per m.

#: Each field's vx at a height z, m/s, by the stem a row's FREESTREAM names.
#: What each field is, for its provenance record.


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--write" in args:
        FOLDER.mkdir(parents=True, exist_ok=True)
        for path, text in expected().items():
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(HERE).as_posix()}")
        return 0
    ymin, ymax, zmin, zmax = extents()
    ys, zs = grid()
    print(f"12_WING_PHY: y {ymin:g} to {ymax:g} m, z {zmin:g} to {zmax:g} m")
    print(
        f"grid: {len(ys)} y from {ys[0]:g} to {ys[-1]:g}, {len(zs)} z from {zs[0]:g} to {zs[-1]:g}"
    )
    differing = stale()
    print(f"{len(expected()) - len(differing)} of {len(expected())} files current: {differing}")
    return 1 if differing else 0


if __name__ == "__main__":
    raise SystemExit(main())
