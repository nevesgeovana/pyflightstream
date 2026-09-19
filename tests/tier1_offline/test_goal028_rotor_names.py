"""A rotor's alias reaches a file name sanitised, and its table's header is read as a header.

NL-04. The rotor table's file name took the RAW alias while the passage
reductions of the same rotor sanitise theirs. An alias is an unconstrained string:
`Left/Right` wrote `polars/P0001-Left/Right_rotor.csv`, a file inside a subfolder
the manifest then keyed by a path with a slash in it; a colon on Windows writes an
NTFS stream nobody can see, or raises out of the stage.

NL-03. The union of what the workspace knows (FR-89) globs `polars/P*-*_*.csv`,
which matches the rotor table, and read its FIRST line as the header. That line is
the alias, alone, so the union carried `PUSHER` as if it were a column and never
the table's real header.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from pyflightstream.post.superfile import union_the_workspace_knows
from tests.tier1_offline.test_post_superfile import _post, _workspace


def _posted(tmp_path, alias: str):
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        "\n".join(
            [
                "area_m2 = 50.0",
                "chord_m = 2.526",
                "span_m = 20.0",
                "",
                f'[rotors."{alias}"]',
                f'alias = "{alias}"',
                "x_m = 0.0",
                "y_m = 0.0",
                "z_m = 0.0",
                'axis = "X"',
                "rpm_sign = 1",
                "diameter_m = 2.0",
                'families_blades = ["B"]',
                'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
                "",
            ]
        ),
        encoding="utf-8",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        written = [Path(path) for path in _post(workspace)]
    return workspace, written


def test_an_alias_with_a_slash_names_one_file_in_the_polars_folder(tmp_path):
    """Measured on the path the stage TARGETS, which the manifest names either way.

    This fixture's records state a speed for `PUSHER` alone, so the table of a rotor
    spelled otherwise has no row and is a named skip; the key of that skip is the
    path the table would have been written to, and that is what carried the slash.
    """
    import json

    workspace, _written = _posted(tmp_path, "Left/Right")
    (manifest,) = workspace.root.rglob("products.json")
    stated = json.loads(manifest.read_text(encoding="utf-8"))
    named = [
        key
        for key in (*stated.get("products", {}), *stated.get("skipped", {}))
        if key.endswith("_rotor.csv")
    ]
    assert named, "the stage names no rotor table, written or skipped"
    for key in named:
        assert key.count("/") == 1 and key.startswith("polars/"), key
        assert key.endswith("-Left_Right_rotor.csv"), key
    assert not (manifest.parent / "polars" / "P6002-Left").exists(), "the alias made a folder"


def test_the_union_reads_a_rotor_tables_header_and_not_its_alias_line(tmp_path):
    workspace, written = _posted(tmp_path, "PUSHER")
    rotor = next(path for path in written if path.name.endswith("_rotor.csv"))
    out = rotor.parent.parent
    known = union_the_workspace_knows(
        workspace.root, out, None, polars_dir="polars", probes_dir="probes"
    )
    assert "PUSHER" not in known, "the alias line was read as a header"
    assert "CT_PUSHER" in known and "J_PUSHER" in known, sorted(known)[:20]
