"""Build preparation, refinement and refusal inspection pages from planner records."""

from __future__ import annotations

import json
import textwrap
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._visual_inspect import (
    BOTTOM,
    DIRECTION_COLORS,
    PAGE,
    RIGHT,
    TOP,
    Mesh,
    Points,
    Scene,
    _skipped,
    patch_colors,
    read_obj,
    standard_views,
    views_page,
)


class Inspection:
    """Carry the outer refusal hook and optional level PDF through refinement."""

    def __init__(self, source, obj, enabled):
        self.source, self.obj, self.enabled = source, obj, enabled
        self.work: Any = None

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if isinstance(error, InputArtifactError):
            refusal_diagnostic(self.source, self.obj, error, self.work)
        return False

    def write(self, writer, work, *args):
        """Write the level and append its inspection before the final record."""
        written = writer(work, *args)
        if self.enabled:
            written.insert(-1, refined_pdf(work, written[0], written[-1]))
        return written


def _directions_page(
    pdf,
    drawn,
    names,
    layouts,
    views,
    *,
    family,
    unit,
    dpi,
    governing,
    arc_verts=None,
):
    """Render directions exclusively from planner records, without classifying geometry."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    colors = {n: (0.85, 0.85, 0.85, 1.0 if n in layouts else 0.25) for n in names}
    scene = Scene(drawn, names, colors, None, edges=False, perimeter_width=0.3)
    leads = {
        f"{n} leads {d}"
        for n in names
        for d, yes in zip(("normal", "parallel"), governing.get(n, (False, False)), strict=True)
        if yes
    }
    seen = set()
    for name in names:
        layout = layouts.get(name)
        if layout is None:
            continue
        labels = getattr(layout, "labels", {})
        dominant = getattr(layout, "leads", {})
        for patch, records in layout.directions.items():
            if layout.names[layout.owner[patch]] != name:
                continue
            for arc, record in records.items():
                key = (id(layout), arc, record.direction)
                if key in seen:
                    continue
                seen.add(key)
                label = labels.get(arc, "")
                lead = dominant.get(label)
                is_lead = lead is not None and lead[1] == arc
                if lead is not None:
                    leads.add(f"{lead[0]} leads {label}")
                vertices = drawn.verts if arc_verts is None else arc_verts
                xyz = vertices[list(layout.blocks.arcs[arc])]
                scene.direction_arcs.append((xyz, record.direction, label, is_lead))
    fig = plt.figure(figsize=PAGE)
    views_page(fig, scene, views, [], [], labels=False, unit=unit)
    handles = [Line2D([], [], color=c, lw=2, label=d) for d, c in DIRECTION_COLORS.items()]
    handles += [Line2D([], [], color="none", label=s) for s in sorted(leads)]
    fig.legend(
        handles=handles,
        loc="upper left",
        fontsize=6,
        title_fontsize=7,
        title="parallel / normal to the reference\n(trailing edge, else the longest side)",
        bbox_to_anchor=((PAGE[0] - RIGHT) / PAGE[0], (PAGE[1] - TOP) / PAGE[1]),
    )
    fig.suptitle(f"{drawn.path.name}: family {family}, directions", fontsize=10)
    pdf.savefig(fig, dpi=dpi)
    plt.close(fig)


def patches_pdf(
    mesh: str | Path | Mesh,
    groups: dict[str, list[str]],
    governing: dict[str, tuple[bool, bool]] | set[str],
    out: Path,
    *,
    mesh_unit: str | None = None,
    dpi: int = 200,
    layouts: Mapping[str, Any] | None = None,
    refusal: InputArtifactError | None = None,
    notes: Mapping[str, str] | None = None,
    arc_verts: np.ndarray | None = None,
) -> Path:
    """Write one page per original family of a prepared mesh: its patches colored and named.

    ``groups`` maps each original family to its patches (the families of the
    patches OBJ ``mesh``); ``governing`` maps a patch to its normal and parallel
    flags. Each lead is labelled GOVERNING NORMAL or GOVERNING PARALLEL in a red
    frame and listed so beside the views. A set of names means both directions.
    The pages are the four views of the
    technical drawing; a family whose patches hold no face is skipped.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Patch

    drawn = mesh if isinstance(mesh, Mesh) else read_obj(Path(mesh))
    flags = governing if isinstance(governing, dict) else dict.fromkeys(governing, (True, True))
    labels = {
        n: "\n".join(
            f"GOVERNING {direction}"
            for direction, leads in (("PARALLEL", pair[1]), ("NORMAL", pair[0]))
            if leads
        )
        for n, pair in flags.items()
    }
    views = standard_views((1.0, -1.0, 1.0))
    with PdfPages(out) as pdf:
        if refusal is not None:
            _refusal_page(pdf, drawn, refusal, views, unit=mesh_unit, dpi=dpi)
        for family, patches in groups.items():
            names = [p for p in patches if drawn.patches.get(p)]
            if not names:
                continue
            colors, _ = patch_colors(names, "tab20" if len(names) <= 20 else "turbo")
            scene = Scene(drawn, names, colors, None, edges=True, perimeter_width=1.2)
            scene.highlight = {n for n in names if n in governing}
            scene.highlight_labels = labels
            if refusal is not None:
                involved = set(refusal.where.get("families", ())) & set(names)
                scene.highlight |= involved
                scene.highlight_labels = {**labels, **dict.fromkeys(involved, "REFUSAL")}
            fig = plt.figure(figsize=PAGE)
            views_page(fig, scene, views, [], [], labels=True, unit=mesh_unit)
            pw, ph = fig.get_size_inches()
            handles = [
                Patch(
                    facecolor=colors[n],
                    edgecolor="#d62728" if n in scene.highlight else "0.2",
                    linewidth=1.5 if n in scene.highlight else 0.5,
                    label=f"{n}  ({scene.highlight_labels[n].replace(chr(10), ', ')})"
                    if n in scene.highlight
                    else n,
                )
                for n in names
            ]
            add_legend = partial(
                fig.legend,
                handles=handles,
                loc="upper left",
                title=f"{family}: {len(names)} patches, {len(scene.highlight)} governing",
                bbox_to_anchor=((pw - RIGHT + 0.1) / pw, (ph - TOP - 0.05) / ph),
                ncol=1 if len(names) <= 40 else 2,
                borderaxespad=0,
            )
            legend = add_legend(fontsize=6, title_fontsize=7)
            bounds = legend.get_window_extent()
            width, height = bounds.width / fig.dpi, bounds.height / fig.dpi
            fit = min(1.0, (RIGHT - 0.2) / width, (ph - TOP - BOTTOM - 0.05) / height)
            if fit < 1:
                legend.remove()
                # Leave room for font metric rounding between the screen and PDF renderers.
                fit *= 0.9
                add_legend(fontsize=6 * fit, title_fontsize=7 * fit)
            fig.suptitle(
                f"{drawn.path.name}: family {family}", fontsize=10, y=1 - 0.2 / PAGE[1], va="top"
            )
            if notes:
                fig.text(0.03, 0.02, "\n".join(notes[n] for n in names if n in notes), fontsize=6)
            pdf.savefig(fig, dpi=dpi)
            plt.close(fig)
            if layouts is not None:
                _directions_page(
                    pdf,
                    drawn,
                    names,
                    layouts,
                    views,
                    family=family,
                    unit=mesh_unit,
                    dpi=dpi,
                    governing=flags,
                    arc_verts=arc_verts,
                )
    return out


def _refusal_page(pdf, mesh, error, views, *, unit, dpi):
    """Draw the whole source with only structurally supplied locations highlighted."""
    import matplotlib.pyplot as plt

    names = list(mesh.patches)
    involved = set(error.where.get("families", ()))
    colors = {n: (0.9, 0.3, 0.2, 1.0) if n in involved else (0.8, 0.8, 0.8, 0.4) for n in names}
    scene = Scene(mesh, names, colors, None)
    xyz = list(error.where.get("points", ()))
    xyz += [mesh.verts[i] for i in error.where.get("nodes", ()) if 0 <= i < len(mesh.verts)]
    points = [Points(mesh.path, "refusal", np.asarray(xyz, dtype=float).reshape(-1, 3))]
    fig = plt.figure(figsize=PAGE)
    views_page(fig, scene, views, points, [{"color": "red", "s": 14}], labels=False, unit=unit)
    fig.suptitle(f"{mesh.path.name}: refinement refused", fontsize=10)
    message = str(error).removesuffix("Nothing was written.").rstrip()
    text = textwrap.fill(f"{message} No level was written.", width=42, break_long_words=True)
    fig.text(
        (PAGE[0] - RIGHT + 0.1) / PAGE[0],
        0.9,
        text,
        va="top",
        fontsize=min(7, 410 / max(len(text.splitlines()), 1)),
    )
    pdf.savefig(fig, dpi=dpi)
    plt.close(fig)


def refusal_diagnostic(source, obj, error: InputArtifactError, work=None) -> None:
    """Attempt the diagnostic without ever replacing the original refinement refusal."""
    target = source.with_name(source.stem + ".refine-refusal.pdf")
    try:
        drawn = Mesh(source, obj.verts, dict(obj.families) if work is None else work.original)
        governing = (
            {} if work is None else {n: s.leads for n, s in work.specs.items() if any(s.leads)}
        )
        patches_pdf(
            drawn,
            _family_groups(drawn.patches, {} if work is None else work.request.components),
            governing,
            target,
            layouts={} if work is None else work.layouts,
            refusal=error,
        )
    except Exception as drawing_error:
        try:
            _skipped(f"{source}: could not write the diagnostic PDF ({drawing_error})")
        except Warning:
            pass  # Warnings-as-errors must not replace the original refusal either.
    else:
        message = str(error).removesuffix("Nothing was written.").rstrip()
        error.args = (f"{message} No level was written. A diagnostic PDF: {target}.",)


def refined_pdf(work, source: Path, record: Path) -> Path:
    """Draw the completed parts under their output components, with recorded continuity notes."""
    data = json.loads(record.read_text(encoding="utf-8"))
    vertices = [work.mesh.verts]
    patches = {n: list(faces) for n, faces in work.mesh.families.items() if n not in work.bands}
    offset = len(work.mesh.verts)
    for points, families, _ in work.parts.values():
        vertices.append(points)
        for name, faces in families.items():
            moved = [[v + offset for v in face] for face in faces]
            if name in work.bands:
                patches[work.bands[name]] += moved
            else:
                patches[name] = moved
        offset += len(points)
    drawn = Mesh(source, np.vstack(vertices), patches)
    grouped = _family_groups(patches, data.get("components", {}))
    governing = {n: s.leads for n, s in work.specs.items() if any(s.leads)}
    notes = {
        n: f"{n}: continuity {entry['continuity']}"
        if entry.get("continuity")
        else f"{n}: continuity remeshed band ({entry['band']} source faces)"
        for n, entry in data["families"].items()
        if entry.get("continuity") or entry.get("band")
    }
    return patches_pdf(
        drawn,
        grouped,
        governing,
        source.with_suffix(".inspect.pdf"),
        layouts=work.layouts,
        notes=notes,
        mesh_unit=work.te_unit,
        arc_verts=work.mesh.verts,
    )


def _family_groups(patches, components):
    """Read component membership, keeping ungrouped families as their own pages."""
    grouped = {n: list(members) for n, members in components.items()}
    members = {n for group in grouped.values() for n in group}
    grouped.update({n: [n] for n in patches if n not in members})
    return grouped
