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
- ``{point}``: the fixed point tag of :func:`pyflightstream.cases.point_tag`,
  for example ``a+02.0_b+00.0`` (alpha and beta in deg, signed,
  fixed width).
- ``{alpha}``, ``{beta}``: sweep angles in deg, compact (``2``, ``-3.5``).
- ``{advance_ratio}``: propeller advance ratio J, dimensionless, compact.
- ``{mach}``: free-stream Mach number of the case, compact.
- ``{polar}``: the author's own convention (PFS-2029.19),
  ``POLAR-<sim>_M<mach*100:02d>AL<alpha*10:+04d>BE<beta*10:+04d>`` and
  ``J<J*100:+04d>`` appended when the case has an advance ratio, so
  ``POLAR-3207_M20AL-020BE+000`` and ``POLAR-9001_M14AL+000BE+000J+170``;
  fixed width, so the names sort. It needs the case's Mach number; an
  angle the sweep does not vary is zero.
- ``{name}``, in OUTPUT names only: the rendered point stem, so every
  export hangs off the point's name whatever template produced it.

The default templates reproduce the historical names exactly
(``{point}`` for per-point files, ``sim_{sim}`` for archives), so
existing campaign roots, goldens, and manifests stay valid; the matrix
command line names points by :data:`MATRIX_POINT_NAME`, her convention,
because a matrix row always resolves a Mach number.

The default templates reproduce the historical names exactly
(``{point}`` for per-point files, ``sim_{sim}`` for archives), so
existing campaign roots, goldens, and manifests stay valid.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from string import Formatter

from pydantic import BaseModel, ConfigDict, field_validator

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import point_tag

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

#: The point name the matrix command line uses unless told otherwise
#: (PFS-2029.19.01): the author's own convention, whose every field a
#: matrix row resolves.
MATRIX_POINT_NAME = "{polar}"


def polar_name(
    sim: str,
    mach: float,
    alpha_deg: float = 0.0,
    beta_deg: float = 0.0,
    advance_ratio: float | None = None,
) -> str:
    """Render the author's point convention (PFS-2029.19.01).

    ``POLAR-<sim>_M<mach*100:02d>AL<alpha*10:+04d>BE<beta*10:+04d>``, with
    ``J<J*100:+04d>`` appended when an advance ratio is known: her
    ``POLAR-{polar:03d}_M{mach*100:02d}AL{alpha*10:+04d}BE{beta*10:+04d}``
    and, for a rotor case, ``J{advance_ratio*100:+04d}``. Fixed width, so
    a directory of them sorts by polar, Mach, angle and ratio.
    """
    name = (
        f"POLAR-{sim}_M{round(mach * 100):02d}"
        f"AL{round(alpha_deg * 10):+04d}BE{round(beta_deg * 10):+04d}"
    )
    if advance_ratio is not None:
        name += f"J{round(advance_ratio * 100):+04d}"
    return name


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
            The case's advance ratio for ``{advance_ratio}`` and the J
            field of ``{polar}`` when the sweep does not vary it.

        Returns
        -------
        str
            The rendered stem, without extension.
        """
        return _render(
            self.point_name, _values(campaign, sim, point, mach, advance_ratio), "point_name"
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
            _values(campaign, sim, point, mach, advance_ratio, stem),
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
) -> dict[str, object]:
    """Assemble the placeholder values available on one point."""
    values: dict[str, object] = {
        "campaign": campaign,
        "sim": sim,
        "point": point_tag(point),
    }
    for axis in ("alpha", "beta", "advance_ratio"):
        if axis in point:
            values[axis] = float(point[axis])
    if advance_ratio is not None and "advance_ratio" not in values:
        values["advance_ratio"] = float(advance_ratio)
    if mach is not None:
        values["mach"] = float(mach)
        ratio = values.get("advance_ratio")
        values["polar"] = polar_name(
            sim,
            float(mach),
            float(point.get("alpha", 0.0)),
            float(point.get("beta", 0.0)),
            None if ratio is None else float(ratio),
        )
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
            "them into raw/ and an absolute name would move a file from outside "
            "the run into the run's own evidence."
        )
    if any(part == ".." for part in candidate.parts):
        raise NamingTemplateError(
            f"the output name {name!r} climbs out of the simulation folder with "
            "'..'. Collection MOVES a declared output into raw/, so this would "
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
