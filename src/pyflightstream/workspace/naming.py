"""Output-only naming templates for human-readable run file names.

Pipeline role: renders the human-readable names of generated scripts,
per-point exports, and simulation archives from a user-configurable
template. Names are a reading convenience for people and external
tools, nothing more: run identity lives in the campaign manifest
(``runs.json``), never in a file or folder name, and no API in this
package parses a generated name back into its parts (SAD Section 6).
That absence is enforced by a test, so a parse-back helper can never
appear silently.

Available placeholders:

- ``{campaign}``: the campaign name.
- ``{sim}``: the ``sim_id`` of the case.
- ``{point}``: the point name of :func:`pyflightstream.cases.point_name`, every
  variable the row's flight condition declares, in its order, for example
  ``M144RE438AL+000BE+000J+080`` (0.21.0).
- ``{alpha}``, ``{beta}``: sweep angles in deg, compact (``2``, ``-3.5``).
- ``{advance_ratio}``: rotor advance ratio J, dimensionless, compact.
- ``{mach}``: free-stream Mach number of the case, compact.
- ``{polar}``: the file stem of the point, ``P<sim>-<point name>``, so
  ``P2001-M144RE438AL+000BE+000J+080`` (0.21.0; until 0.20.x it was
  ``POLAR-<sim>_M<mach*100>AL..BE..J..``).
- ``{name}``, in OUTPUT names only: the rendered point stem, so every
  export hangs off the point's name whatever template produced it.

The default templates are ``{point}`` for per-point files and
``sim_{sim}`` for archives; the matrix command line names points by
:data:`MATRIX_POINT_NAME`, ``P<sim>-<point name>``. A workspace written
before 0.21.0 carries the old names and is renamed by
``pyfs-matrix rename`` (docs/migrating-to-0.21.0.md).
"""

from __future__ import annotations

import getpass
import re
from pathlib import PurePosixPath, PureWindowsPath
from string import Formatter

from pydantic import BaseModel, ConfigDict, field_validator

from pyflightstream._errors import ProductError, PyflightstreamError

_POINT_PLACEHOLDERS = (
    "campaign",
    "sim",
    "point",
    "alpha",
    "beta",
    "mach",
    "advance_ratio",
    "polar",
)
_OUTPUT_PLACEHOLDERS = (*_POINT_PLACEHOLDERS, "name")
_ARCHIVE_PLACEHOLDERS = ("campaign", "sim")

#: The simulation subfolder holding ONE FOLDER PER DATAPOINT, which is
#: where a campaign collects since 0.16.0 (FR-92). Every point of one case
#: used to collect into a single `outputs/`, so from the second point of a
#: swept row onward that folder held two files that both read as loads
#: tables and nothing in the filesystem said which point either belonged
#: to. The layout answers it now: a point's evidence is what is in its own
#: folder, and the question "which of these is mine" cannot be asked.
SIM_DATAPOINTS_DIR = "datapoints"

#: What every datapoint folder name begins with, so a reader scanning
#: `datapoints/` sees at once that the entries are points and not files.
DATAPOINT_PREFIX = "DP-"

#: What every file of a point begins with, before its simulation id: the stem
#: of a point is ``P<sim>-<point name>`` (0.21.0).
POINT_FILE_PREFIX = "P"

#: What a superfile begins with, in place of :data:`POINT_FILE_PREFIX`.
SUPER_FILE_PREFIX = "SUPER-"


class PointName(str):
    """A point's name, as :func:`pyflightstream.cases.point_name` wrote it (0.21.0).

    A ``str`` that has been CHECKED: not empty, a portable file name, and not
    already carrying the ``DP-`` folder prefix. The datapoint folder is rendered
    from it and never from a bare string, because a string that already held the
    prefix, or a tag of the earlier scheme, put files in a folder the assessor
    never looks in.

    THE ONE SANCTIONED CALLER OF THE EARLIER SCHEME, since 0.21.1:
    :func:`datapoint_name_of` builds one of these from a folder that ALREADY
    EXISTS under a pre-0.21.0 tag, for a collector that read that folder off the
    record rather than recomputing it. The harm above is a name INVENTED in the
    old scheme, which files outputs where nothing looks; reading back a folder
    that is already there is its opposite. That function answers None rather
    than raising for anything it cannot check, which is what keeps this class's
    refusal out of a caller that could not handle it.
    """

    def __new__(cls, value: str) -> PointName:  # noqa: D102 -- the class docstring states the check
        text = str(value)
        if not text or not is_portable_name(text):
            raise NamingTemplateError(f"{text!r} is not a point name: it is empty or not portable")
        if text.startswith(DATAPOINT_PREFIX):
            raise NamingTemplateError(
                f"{text!r} already carries the {DATAPOINT_PREFIX} folder prefix; a point name "
                "does not, and the folder is rendered from the name"
            )
        return super().__new__(cls, text)


#: What an archive folder is called, wherever something is archived rather
#: than lost: beside the thing it replaces, never above it.
ARCHIVE_DIR = "archive"

#: How an archive stamp is spelled. Sortable, no separator a file system
#: objects to, and to the SECOND: two rebuilds in one minute are two
#: rebuilds.
#:
#: IT LIVES HERE AND NOT IN THE POST LAYER, since 0.18.0, because a
#: continuation archives a DATAPOINT under the same stamp and the workspace
#: cannot import from post: dependencies flow downward and the layering
#: guard carries no allowlist. A stamp format is a NAME, and names are this
#: module's subject, so the constant moved down rather than being copied
#: into a second home that would drift from the first.
ARCHIVE_STAMP = "%Y%m%d-%H%M%S"


def datapoint_dir_name(name: PointName) -> str:
    """Return the folder name one datapoint collects its outputs into (FR-92).

    :data:`DATAPOINT_PREFIX` and the point name that already ends the
    ``run_id`` and is the stem of every file of the point, so the folder, the
    files and the run record carry ONE identity
    (``DP-M144RE438AL+000BE+000J+080``).

    Parameters
    ----------
    name : PointName
        The point's name, checked.

    Returns
    -------
    str
        Folder name, relative to :data:`SIM_DATAPOINTS_DIR`.

    Raises
    ------
    NamingTemplateError
        If ``name`` is a bare string rather than a :class:`PointName`.
    """
    if not isinstance(name, PointName):
        raise NamingTemplateError(
            f"datapoint_dir_name takes a PointName, not {type(name).__name__} {name!r}: the "
            "folder is rendered from a checked name"
        )
    return f"{DATAPOINT_PREFIX}{name}"


def datapoint_name_of(folder: str) -> PointName | None:
    """Return the point a datapoint FOLDER belongs to, or None if it names none.

    The inverse of :func:`datapoint_dir_name`, and it lives beside it because a
    rule and its inverse drifting apart is the defect this module already
    records for :data:`ARCHIVE_STAMP`.

    Returns
    -------
    PointName or None
        The checked name, or None when ``folder`` does not carry
        :data:`DATAPOINT_PREFIX` or what follows it is not a point name.

    WHY NONE AND NOT A RAISE, which is the whole reason this is a function and
    not two lines at the call site. The caller is a COLLECTOR reading a folder
    name off disk, where anything can be written and a hand-made directory is
    ordinary; `PointName` refuses what is not portable, and its refusal is a
    `NamingTemplateError`, which is a ValueError and not a WorkspaceError. Fed
    an unvalidated tag, the collector's sweep did not catch it and one folder
    named `DP-a b` aborted the collection of every other point in the
    workspace, measured 2026-09-16. A reader that answers "not a point's
    folder" lets the caller refuse in its own vocabulary.
    """
    if not folder.startswith(DATAPOINT_PREFIX):
        return None
    try:
        return PointName(folder[len(DATAPOINT_PREFIX) :])
    except NamingTemplateError:
        return None


def point_file_stem(sim: str, name: PointName) -> str:
    """Return the stem of every file of one point: ``P<sim>-<point name>`` (0.21.0)."""
    return f"{POINT_FILE_PREFIX}{sim}-{name}"


#: A group name that reads as the NUMBERED era's suffix, which the rename must
#: be able to tell apart from a name of its own. It sits here rather than in
#: `post` because the MATRIX BINDER refuses the colliding shape one stage
#: earlier, and `workspace` may not import `post`. Two copies of one naming
#: rule is how a refusal and the file it is about come to disagree.
_NUMBERED_GROUP = re.compile(r"^g\d+$", re.IGNORECASE)


def group_token(group: str | int) -> str:
    """Return what a product file carries for one group: its NAME, or ``gNN``.

    The one place the two eras are told apart, so the rename that moves her
    products and the stage that writes new ones cannot drift into two
    conventions -- which is the drift a technical-writing lens flagged, since
    the migration page's whole promise is that the renamed file IS the file the
    next post writes.
    """
    token = str(group).strip()
    if not token:
        raise ProductError("a polar group has no name, and the product file is named after it")
    if token.isdigit():
        return f"g{int(token):02d}"
    if _NUMBERED_GROUP.match(token):
        raise ProductError(
            f"the polar group is named {token!r}, which is the shape this release "
            "replaced; a file named after it could not be told from the numbered "
            "form it supersedes, and the rename of existing products needs that "
            "difference. Choose a name for the group"
        )
    return token


def sweep_file_stem(sim: str, sweep: str, *, prefix: str = POINT_FILE_PREFIX) -> str:
    """Return the stem of a file about a whole sweep: ``P<sim>-<sweep>`` or ``SUPER-<sim>-...``."""
    return f"{prefix}{sim}-{sweep}"


#: The point name the matrix command line uses unless told otherwise
#: (PFS-2029.19.01): the file stem ``P<sim>-<point name>`` (0.21.0).
MATRIX_POINT_NAME = "{polar}"


# Characters that break file names on at least one supported platform;
# rendered names and substituted values must stay clear of them.
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\s]')


def is_portable_name(text: str) -> bool:
    """Whether ``text`` is a plain file-name-safe token: no separators, no whitespace, not empty."""
    return bool(text) and _UNSAFE_CHARS.search(text) is None


class NamingTemplateError(PyflightstreamError, ValueError):
    """A naming template cannot be validated or rendered.

    Raised when a template names an unknown placeholder, when a
    placeholder has no value on the current point (for example
    ``{mach}`` on a case without a Mach number), or when a rendered
    name would not be a portable file name. The message lists what is
    available, because a naming mistake must surface before any solver
    run, not as a cryptic OS error mid-campaign.
    """


class NamingTemplate(BaseModel):
    """User-configurable output names for scripts, exports, and archives.

    The template is output only: it decorates files for human reading,
    while run identity stays in the manifest. Configure it per
    workspace by passing it to
    :class:`~pyflightstream.workspace.CampaignWorkspace`.

    Attributes
    ----------
    point_name : str
        Template of per-point file stems (generated scripts and
        rendered export names). Default ``"{point}"`` reproduces the
        historical script names, for example ``a+02.0_b+00.0``.
    archive_name : str
        Template of simulation archive stems; only ``{campaign}`` and
        ``{sim}`` apply (an archive spans every point of a
        simulation). Default ``"sim_{sim}"`` reproduces the historical
        zip names.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    point_name: str = "{point}"
    archive_name: str = "sim_{sim}"

    @field_validator("point_name")
    @classmethod
    def _point_placeholders_are_known(cls, value: str) -> str:
        _check_placeholders(value, _POINT_PLACEHOLDERS, "point_name")
        return value

    @field_validator("archive_name")
    @classmethod
    def _archive_placeholders_are_known(cls, value: str) -> str:
        _check_placeholders(value, _ARCHIVE_PLACEHOLDERS, "archive_name")
        return value

    def render_point(
        self,
        *,
        campaign: str,
        sim: str,
        point: dict[str, float],
        mach: float | None = None,
        advance_ratio: float | None = None,
        name: str | None = None,
    ) -> str:
        """Render the file stem of one sweep point.

        Parameters
        ----------
        campaign : str
            Campaign name for ``{campaign}``.
        sim : str
            Case ``sim_id`` for ``{sim}``.
        point : dict of str to float
            Sweep point coordinates (alpha and beta in deg,
            advance_ratio dimensionless), as produced by
            :meth:`pyflightstream.cases.SweepAxis.points`; feeds
            ``{point}`` and the per-axis placeholders.
        mach : float, optional
            Free-stream Mach number of the case for ``{mach}`` and
            ``{polar}``; None when the case declares none.
        advance_ratio : float, optional
            The case's advance ratio for ``{advance_ratio}`` when the sweep
            does not vary it.
        name : str, optional
            The point's name (:func:`pyflightstream.cases.point_name`), for
            ``{point}`` and ``{polar}``; a template naming either refuses
            without it.

        Returns
        -------
        str
            The rendered stem, without extension.
        """
        return _render(
            self.point_name,
            _values(campaign, sim, point, mach, advance_ratio, name=name),
            "point_name",
        )

    def render_output(
        self,
        name: str,
        *,
        campaign: str,
        sim: str,
        point: dict[str, float],
        mach: float | None = None,
        advance_ratio: float | None = None,
        stem: str | None = None,
        point_name: str | None = None,
    ) -> str:
        """Render the placeholders inside one declared output name.

        A name without placeholders passes through unchanged, which
        only a single-point case may declare: with placeholders (for
        example ``"loads_{point}.txt"``) each point exports under a
        unique name, and the campaign loop blocks a case whose points
        would render the same name, because a later point of the same
        simulation would otherwise overwrite an earlier export.

        Parameters
        ----------
        name : str
            Declared output name, possibly holding placeholders.
        campaign, sim, point, mach
            Same meaning as in :meth:`render_point`.

        Returns
        -------
        str
            The rendered output name.
        """
        # PYFS-005. Containment is checked FIRST and unconditionally.
        #
        # This function used to return `name` untouched whenever it held no
        # brace, on the reasoning that a name with no placeholder has nothing
        # to render. True, and irrelevant: the check it skipped was not about
        # placeholders. A declared output of "../outside.txt" holds no brace,
        # so it took the early return, never reached any validation, resolved
        # OUTSIDE the simulation folder, and was then collected with
        # shutil.move, which does not copy. The file was not read, it was
        # taken, and the run recorded it as its own evidence.
        #
        # An early return that also skips a check the slow path performs is
        # the shape to distrust here, so the check moved ahead of it.
        _check_output_containment(name)
        if "{" not in name and "}" not in name:
            return name
        _check_placeholders(name, _OUTPUT_PLACEHOLDERS, "output name")
        rendered = _render(
            name,
            _values(campaign, sim, point, mach, advance_ratio, stem, name=point_name),
            "output name",
            check_name=False,
        )
        # Re-checked after rendering: a placeholder value could reintroduce
        # what the template did not contain.
        _check_output_containment(rendered)
        return rendered

    def render_archive(self, *, sim: str, campaign: str | None = None) -> str:
        """Render the archive file stem of one simulation.

        Parameters
        ----------
        sim : str
            The ``sim_id`` for ``{sim}``.
        campaign : str, optional
            Campaign name for ``{campaign}``; required only when the
            archive template uses that placeholder (the workspace does
            not know the campaign name on its own).

        Returns
        -------
        str
            The rendered stem; the workspace appends ``.zip``.
        """
        values: dict[str, str] = {"sim": sim}
        if campaign is not None:
            values["campaign"] = campaign
        return _render(self.archive_name, values, "archive_name")


class _CompactFormatter(Formatter):
    """Formats placeholder floats compactly unless a spec is given.

    Without an explicit format spec a float renders through ``%g``
    (``2``, ``-3.5``, ``0.25``), keeping names short; an explicit spec
    such as ``{alpha:+05.1f}`` is honored unchanged.
    """

    def format_field(self, value: object, format_spec: str) -> str:
        if format_spec == "" and isinstance(value, float):
            return format(value, "g")
        return super().format_field(value, format_spec)


_FORMATTER = _CompactFormatter()


def _values(
    campaign: str,
    sim: str,
    point: dict[str, float],
    mach: float | None,
    advance_ratio: float | None = None,
    stem: str | None = None,
    name: str | None = None,
) -> dict[str, object]:
    """Assemble the placeholder values available on one point."""
    values: dict[str, object] = {
        "campaign": campaign,
        "sim": sim,
    }
    if name is not None:
        values["point"] = name
        values["polar"] = point_file_stem(sim, name)
    for axis in ("alpha", "beta", "advance_ratio"):
        if axis in point:
            values[axis] = float(point[axis])
    if advance_ratio is not None and "advance_ratio" not in values:
        values["advance_ratio"] = float(advance_ratio)
    if mach is not None:
        values["mach"] = float(mach)
    if stem is not None:
        values["name"] = stem
    return values


def _check_placeholders(template: str, known: tuple[str, ...], role: str) -> None:
    """Refuse a template naming placeholders outside the known set."""
    try:
        fields = [field for _, field, _, _ in Formatter().parse(template) if field is not None]
    except ValueError as error:
        raise NamingTemplateError(
            f"the {role} template {template!r} is not a valid format string: {error}"
        ) from error
    unknown = [field for field in fields if field not in known]
    if unknown:
        raise NamingTemplateError(
            f"the {role} template {template!r} names unknown placeholder(s) "
            f"{', '.join(sorted(set(unknown)))}; available placeholders are "
            f"{', '.join(known)}. Names are output only; anything beyond these "
            "belongs in the manifest, not in a file name."
        )
    if not fields and not template:
        raise NamingTemplateError(f"the {role} template is empty; a name needs content")


def _check_output_containment(name: str) -> None:
    """Refuse a declared output name that leaves the simulation folder.

    Implements FR-33d, which is the requirement this refusal is published
    under and the one place the exception TYPE is part of the promise:
    what is raised here is :class:`NamingTemplateError` and not
    ``WorkspaceError``, because the refusal comes from the naming
    template, so a caller keying on the workspace error alone never sees
    it. The sibling refusals are FR-33e for collection and FR-33f for
    staging, and they do raise ``WorkspaceError``.

    An output name is a name, not a route. It may carry subdirectories,
    because a solver export can legitimately land in a subfolder, but it may
    not be absolute, may not start from a drive or share, and may not climb
    out with ``..``. The consequence of allowing it is not a confusing path:
    collection MOVES the file, so a name that resolves outside the run takes
    a file the run does not own and records it as evidence it produced
    (PYFS-005).

    Checked on the string rather than by resolving against the run folder,
    so the refusal does not depend on what happens to exist on disk and
    reads the same on every platform.
    """
    if not name or not name.strip():
        raise NamingTemplateError("an output name is empty; declare the file the recipe exports.")
    candidate = PurePosixPath(name.replace("\\", "/"))
    if candidate.is_absolute() or PureWindowsPath(name).is_absolute():
        raise NamingTemplateError(
            f"the output name {name!r} is an absolute path. Declared outputs are "
            "named relative to the simulation folder, because collection moves "
            "them into the point's own datapoints/ folder and an absolute name would "
            "move a file from outside "
            "the run into the run's own evidence."
        )
    if any(part == ".." for part in candidate.parts):
        raise NamingTemplateError(
            f"the output name {name!r} climbs out of the simulation folder with "
            "'..'. Collection MOVES a declared output into the point's own datapoints/ "
            "folder, so this would "
            "not copy a file from outside the run, it would take it: the source "
            "would be gone and the run would record it as evidence it produced. "
            "Name outputs relative to the simulation folder."
        )


def _render(template: str, values: dict[str, object], role: str, check_name: bool = True) -> str:
    """Render one template, turning gaps into didactic errors."""
    try:
        rendered = _FORMATTER.vformat(template, (), values)
    except KeyError as error:
        missing = error.args[0]
        raise NamingTemplateError(
            f"the {role} template {template!r} needs {{{missing}}}, but this point "
            f"provides only: {', '.join(sorted(values))}. A sweep axis placeholder "
            "is only available when the sweep varies that axis, {mach} and {polar} only "
            "when the case declares a Mach number, and {name} only inside an output name."
        ) from error
    for name, value in values.items():
        text = _FORMATTER.format_field(value, "")
        if f"{{{name}}}" in template and _UNSAFE_CHARS.search(text):
            raise NamingTemplateError(
                f"the value of {{{name}}} ({text!r}) contains characters that are "
                f"not portable in file names; rename it so the rendered {role} "
                "stays a plain file name (letters, digits, dot, underscore, "
                "plus, hyphen)."
            )
    if check_name and (_UNSAFE_CHARS.search(rendered) or not rendered):
        raise NamingTemplateError(
            f"the rendered {role} {rendered!r} is not a portable file name; avoid "
            'path separators, whitespace, and the characters <>:"|?* in the '
            "template. Names are generated for human reading only; identity "
            "lives in the manifest."
        )
    return rendered


#: The standard-library resolver for the operator, bound so a test can take it
#: away. `getpass.getuser` reads LOGNAME, USER, LNAME and USERNAME in turn and
#: falls back to the password database where there is one, which is what makes
#: ONE call right on Windows and on the cluster alike.
_getuser = getpass.getuser


def submitted_by() -> str | None:
    """Return the operator running this process, or None if the host names nobody.

    v0.23.0 item 12, the owner's question of 2026-09-17: how to name the user
    who ran, transparently for Linux and Windows. One call, not a pair of
    `sys.platform` branches, which would be two paths that drift.

    IT LIVES HERE AND NOT BESIDE THE PRODUCTS because `run` captures it and
    `post` writes it, and `post` imports `workspace` rather than the reverse.
    Putting it beside the products would have inverted the dependency
    direction, which is a design error rather than a lint finding.

    IT RETURNS None AND NOT `NA`. The product layer spells the absence, because
    the token belongs to the CSV and provenance surface and this function is
    below it. A host that cannot say who is running is a real path rather than
    a defensive one: a batch submission with a scrubbed environment and no
    password entry reaches it, and inventing a name there would put a false
    claim into the one artifact whose purpose is to be believed.
    """
    try:
        who = _getuser()
    except (OSError, KeyError, ImportError):
        return None
    who = str(who).strip()
    return who or None
