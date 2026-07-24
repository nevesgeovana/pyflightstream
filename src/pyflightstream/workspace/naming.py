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

The default templates reproduce the historical names exactly
(``{point}`` for per-point files, ``sim_{sim}`` for archives), so
existing campaign roots, goldens, and manifests stay valid.
"""

from __future__ import annotations

import re
from string import Formatter

from pydantic import BaseModel, ConfigDict, field_validator

from pyflightstream.cases import point_tag

_POINT_PLACEHOLDERS = ("campaign", "sim", "point", "alpha", "beta", "mach", "advance_ratio")
_ARCHIVE_PLACEHOLDERS = ("campaign", "sim")
# Characters that break file names on at least one supported platform;
# rendered names and substituted values must stay clear of them.
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\s]')


class NamingTemplateError(ValueError):
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
            Free-stream Mach number of the case for ``{mach}``;
            None when the case declares none.

        Returns
        -------
        str
            The rendered stem, without extension.
        """
        return _render(self.point_name, _values(campaign, sim, point, mach), "point_name")

    def render_output(
        self,
        name: str,
        *,
        campaign: str,
        sim: str,
        point: dict[str, float],
        mach: float | None = None,
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
        if "{" not in name and "}" not in name:
            return name
        _check_placeholders(name, _POINT_PLACEHOLDERS, "output name")
        return _render(name, _values(campaign, sim, point, mach), "output name", check_name=False)

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
    campaign: str, sim: str, point: dict[str, float], mach: float | None
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
    if mach is not None:
        values["mach"] = float(mach)
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


def _render(template: str, values: dict[str, object], role: str, check_name: bool = True) -> str:
    """Render one template, turning gaps into didactic errors."""
    try:
        rendered = _FORMATTER.vformat(template, (), values)
    except KeyError as error:
        missing = error.args[0]
        raise NamingTemplateError(
            f"the {role} template {template!r} needs {{{missing}}}, but this point "
            f"provides only: {', '.join(sorted(values))}. A sweep axis placeholder "
            "is only available when the sweep varies that axis, and {mach} only "
            "when the case declares a Mach number."
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
