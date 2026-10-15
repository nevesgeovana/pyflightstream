"""Complete matrix example and explanatory text for workspace input guides."""

from collections.abc import Mapping

from pyflightstream.cases.matrix import COLUMN_MEANINGS

#: The run matrix of the template, one mapping per row, by column. A column the
#: layout gains and a row does not state is written ``-``, the matrix's word
#: for "states nothing", so the header is always the layout the reader reads.
_MATRIX_ROWS: tuple[Mapping[str, str], ...] = (
    {
        "POL": "1001",
        "HIDDEN": "1",
        "RUN": "1",
        "AIRCRAFT": "WingBody",
        "CONFIGURATION": "clean",
        "DESCRIPTION": "ALPHA_SWEEP",
        "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
        "SWEEP_VALUES": "-2.0,0.0,2.0,4.0",
        "GEOMETRY": "aircraft.fsm",
        "REF": "r001",
        "SET": "s001",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "SYMMETRY_LOADS": "-",
        "NCPUS": "8",
        "WALLTIME": "2h",
        "FS_BUILD": "26.124",
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": "digits: 6",
    },
    {
        "POL": "1002",
        "HIDDEN": "1",
        "RUN": "1",
        "AIRCRAFT": "WingBody",
        "CONFIGURATION": "disc",
        "DESCRIPTION": "DISC_FROM_A_PROFILE",
        "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
        "SWEEP_VALUES": "0.0,4.0",
        "GEOMETRY": "aircraft.fsm",
        "REF": "r001",
        "SET": "s001",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "NCPUS": "8",
        "WALLTIME": "2h",
        "FS_BUILD": "26.124",
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": "ACTUATOR: DISC / ACTUATOR_RPM: 2400 / PROFILE: prop_thrust",
    },
    {
        "POL": "1003",
        "HIDDEN": "1",
        "RUN": "1",
        "AIRCRAFT": "WingBody",
        "CONFIGURATION": "gust",
        "DESCRIPTION": "CUSTOM_FREE_STREAM",
        "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
        "SWEEP_VALUES": "0.0",
        "GEOMETRY": "aircraft.fsm",
        "REF": "r001",
        "SET": "s001",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "NCPUS": "8",
        "WALLTIME": "2h",
        "FS_BUILD": "26.124",
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": "FREESTREAM: gust",
    },
)


def _matrix_example() -> str:
    """Return the template's run matrix: the layout's header, a dashed line, the rows."""
    columns = list(COLUMN_MEANINGS)
    table = [columns, *([row.get(column, "-") for column in columns] for row in _MATRIX_ROWS)]
    widths = [max(len(line[index]) for line in table) for index in range(len(columns))]
    lines = [
        " | ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in table
    ]
    return "\n".join([lines[0], "-" * len(lines[0]), *lines[1:]]) + "\n"


def _matrix_after() -> str:
    """How the matrix file is laid out, its columns read from the layout's registry."""
    # The glossary's own pointers ("see the table below") point into the
    # glossary, so they are cut here, where no such table follows.
    columns = "\n".join(
        f"{index}. `{name}`: {meaning.meaning}"
        + (f" ({meaning.values.split('; see ')[0]})" if meaning.values else "")
        for index, (name, meaning) in enumerate(COLUMN_MEANINGS.items(), start=1)
    )
    return (
        "The file is a pipe-separated table: the header line names the columns in "
        "exactly this order, a line of dashes may follow it, and then one row per "
        "line. A cell that states nothing holds `-`. The file carries no comment "
        "lines: every line after the header is a row, so a note goes in "
        "`DESCRIPTION`. A row runs only when `RUN` reads 1.\n\n"
        f"{columns}\n\n"
        "`FLIGHT_CONDITION` holds `KEY:value` pairs separated by commas, and exactly "
        "one key carries the word `sweep` where its value would be: that is the "
        "variable the row varies, over the values of `SWEEP_VALUES`, one point "
        "each. `VAR_NAMES_VALUES` holds `KEY: value` pairs separated by ` / `, the "
        "keys the row's run type reads. `REF`, `SET` and `PPROC` name the three "
        "artifacts below by id, and `GEOMETRY` names a file of "
        "`inputs/geometries/` with its extension.\n\n"
        "The first row sweeps the angle of attack, and writes `digits: 6`, a word "
        "the setup below declares as a flag. The second turns the actuator disc "
        "`DISC` of the reference with the radial thrust profile "
        "`inputs/profiles/prop_thrust.txt`, named by its stem. The third flies "
        "through the custom free stream `inputs/freestreams/gust.txt`, also by "
        "its stem, at zero angles, since the field sets the flow's direction."
    )
