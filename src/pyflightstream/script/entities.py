"""Label-aware registry of the entities a script creates or declares.

Pipeline role: the state behind the cross-reference checks of the
script builder (SAD Section 4.2). FlightStream commands cite auxiliary
entities (local coordinate systems, actuators, motions, and mesh
boundaries) by 1-based integer index; the registry counts what the
script has created or declared, optionally maps user labels to those
indices, and turns a bad citation into a build-time error instead of a
silent solver failure. Labels let recipes speak in configuration terms
("wing", "prop_disc") while the library maintains the label-to-index
dictionary.

Mesh boundaries are special: they come from the loaded geometry, not
from script commands, so their total is unknowable statically. The
registry only enforces boundary ranges after the inventory was
declared through :meth:`pyflightstream.script.Script.declare_existing`;
until then boundary citations pass unverified.
"""

from __future__ import annotations

from collections.abc import Mapping

#: Entity kinds the registry tracks, in the vocabulary of the builder.
ENTITY_KINDS = ("frames", "actuators", "motions", "boundaries")

#: Kinds a script command can create (boundaries come from geometry).
CREATED_KINDS = ("frames", "actuators", "motions")

_NOUNS = {
    "frames": "local coordinate system",
    "actuators": "actuator",
    "motions": "motion",
    "boundaries": "mesh boundary",
}


class ScriptReferenceError(ValueError):
    """A command cites an entity that does not exist at that point.

    FlightStream resolves frame, actuator, motion, and mesh boundary
    indices at execution time and fails silently or cryptically when
    they do not exist; the builder counts the objects the script
    creates and rejects the citation at build time instead (SAD
    Section 4.2). Raised both for an index outside the created or
    declared range and for a label the registry does not know.
    Objects already present in the opened project file are declared
    with :meth:`pyflightstream.script.Script.declare_existing`.
    """


class ScriptLabelError(ValueError):
    """A label registration collides with a label already recorded.

    Labels identify exactly one entity per kind, because they resolve
    to a single FlightStream index at emission; reusing a label would
    silently redirect every earlier citation. Pick a distinct label or
    cite the existing entity by its index.
    """


class EntityRegistry:
    """Ledger of created and declared entities with optional labels.

    Tracks, per entity kind (``frames``, ``actuators``, ``motions``,
    ``boundaries``), the number of entities the script has created or
    declared and a label-to-index mapping for the entities the user
    named. Indices are 1-based, in FlightStream order: frame index 1
    is the always-present reference frame (SRC-003 p.329) and created
    local frames take indices 2 upward; actuators and motions start at
    1; mesh boundaries are numbered from 1 in geometry-tree order.

    The mesh boundary total starts unknown (``None``) because it is a
    property of the loaded geometry file, not of the script; range
    checks on boundary citations only run once the inventory was
    declared.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {kind: 0 for kind in CREATED_KINDS}
        self._boundary_total: int | None = None
        self._labels: dict[str, dict[str, int]] = {kind: {} for kind in ENTITY_KINDS}

    @staticmethod
    def _require_kind(kind: str) -> None:
        if kind not in ENTITY_KINDS:
            raise ValueError(f"unknown entity kind {kind!r}; kinds are {', '.join(ENTITY_KINDS)}")

    def count(self, kind: str) -> int | None:
        """Return the created or declared entity count of ``kind``.

        Parameters
        ----------
        kind : str
            One of ``frames``, ``actuators``, ``motions``,
            ``boundaries``.

        Returns
        -------
        int or None
            The count. For ``frames`` this excludes the always-present
            reference frame (index 1). For ``boundaries`` it is None
            while the inventory has not been declared, because the
            boundary total lives in the geometry file and cannot be
            known statically.
        """
        self._require_kind(kind)
        if kind == "boundaries":
            return self._boundary_total
        return self._counts[kind]

    def limit(self, kind: str) -> int | None:
        """Return the highest currently valid index of ``kind``.

        Returns
        -------
        int or None
            Highest valid 1-based index: the count plus one for frames
            (the reference frame occupies index 1), the count itself
            otherwise; None for an undeclared boundary inventory.
        """
        count = self.count(kind)
        if count is None:
            return None
        return count + 1 if kind == "frames" else count

    def labels(self, kind: str) -> dict[str, int]:
        """Return a copy of the label-to-index mapping of ``kind``."""
        self._require_kind(kind)
        return dict(self._labels[kind])

    def assert_label_free(self, kind: str, label: str) -> None:
        """Reject a label that is invalid or already taken for ``kind``.

        Parameters
        ----------
        kind : str
            Entity kind the label would be registered under.
        label : str
            Candidate label.

        Raises
        ------
        ScriptLabelError
            If the label is not a non-empty string, or already names
            another entity of the same kind.
        """
        self._require_kind(kind)
        noun = _NOUNS[kind]
        if not isinstance(label, str) or not label:
            raise ScriptLabelError(
                f"a {noun} label must be a non-empty string, got {label!r}; the label is "
                "the configuration-level name that resolves to one FlightStream index"
            )
        existing = self._labels[kind].get(label)
        if existing is not None:
            raise ScriptLabelError(
                f"label {label!r} already names {noun} {existing}; one label identifies "
                f"one {noun}, so pick a distinct label or cite index {existing} directly"
            )

    def create(self, kind: str, label: str | None = None) -> int:
        """Record one created entity, optionally under a label.

        Parameters
        ----------
        kind : str
            One of ``frames``, ``actuators``, ``motions``; mesh
            boundaries come from the loaded geometry and are declared,
            never created by a script command.
        label : str, optional
            Label registered for the new entity.

        Returns
        -------
        int
            1-based index of the created entity (frames start at 2
            because the reference frame occupies index 1).

        Raises
        ------
        ScriptLabelError
            If the label is invalid or already taken for this kind.
        """
        if kind not in CREATED_KINDS:
            raise ValueError(
                f"entity kind {kind!r} is not script-created; mesh boundaries come from "
                "the loaded geometry and are declared with declare_existing(boundaries=...)"
            )
        if label is not None:
            self.assert_label_free(kind, label)
        self._counts[kind] += 1
        index = self._counts[kind] + (1 if kind == "frames" else 0)
        if label is not None:
            self._labels[kind][label] = index
        return index

    def delete(self, kind: str) -> None:
        """Record one deleted entity and drop labels left dangling.

        FlightStream renumbers the surviving entities of the kind, so
        the ledger only tracks the count; labels whose index now
        exceeds the shrunken range are removed, because they can no
        longer resolve to an existing entity.
        """
        if kind not in CREATED_KINDS:
            raise ValueError(f"entity kind {kind!r} is not script-created, so not deletable")
        self._counts[kind] -= 1
        limit = self.limit(kind)
        self._labels[kind] = {
            label: index for label, index in self._labels[kind].items() if index <= limit
        }

    def declare(self, kind: str, extra: int) -> None:
        """Add ``extra`` project-carried entities of a created kind.

        Parameters
        ----------
        kind : str
            One of ``frames``, ``actuators``, ``motions``.
        extra : int
            Number of entities the opened project file already holds;
            must be zero or positive.
        """
        if kind not in CREATED_KINDS:
            raise ValueError(
                f"entity kind {kind!r} is not count-declared; declare mesh boundaries "
                "through declare_existing(boundaries=...)"
            )
        if extra < 0:
            raise ValueError(f"declared {kind} must be zero or positive, got {extra}")
        self._counts[kind] += extra

    def declare_boundaries(self, declaration: int | Mapping[str, int]) -> None:
        """Declare the mesh boundary inventory of the loaded geometry.

        Declaring the inventory turns on range verification for every
        boundary-citing argument; until then boundary citations pass
        unverified, because the boundary total lives in the geometry
        file and cannot be known statically.

        Parameters
        ----------
        declaration : int or mapping of str to int
            Either the total boundary count (added to any previous
            declaration; zero is a no-op that keeps the inventory
            unknown), or a mapping of configuration labels to 1-based
            boundary indices in geometry-tree order, for example
            ``{"fuselage": 1, "wing": 2}``. A mapping raises the known
            total to its highest index.

        Raises
        ------
        ScriptLabelError
            If a mapping entry has an invalid label or index, or a
            label collides with one already declared.
        """
        # Seam (PLN-023): a licensed probe of the OBJ surface-mesh
        # export will decide whether an fsm-to-obj inspector can fill
        # this mapping automatically; until then declaration is manual.
        if isinstance(declaration, Mapping):
            if not declaration:
                return
            for label, index in declaration.items():
                self.assert_label_free("boundaries", label)
                if isinstance(index, bool) or not isinstance(index, int) or index < 1:
                    raise ScriptLabelError(
                        f"boundary label {label!r} must map to a positive 1-based mesh "
                        f"boundary index, got {index!r}; FlightStream numbers mesh "
                        "boundaries from 1 in geometry-tree order"
                    )
            self._labels["boundaries"].update(declaration)
            self._boundary_total = max(self._boundary_total or 0, max(declaration.values()))
            return
        if isinstance(declaration, bool) or not isinstance(declaration, int):
            raise TypeError(
                f"boundaries takes a total count or a label-to-index mapping, got "
                f"{declaration!r}; the count enables range checks, the mapping also "
                "enables citation by label"
            )
        if declaration < 0:
            raise ValueError(f"declared boundaries must be zero or positive, got {declaration}")
        if declaration > 0:
            self._boundary_total = (self._boundary_total or 0) + declaration

    def resolve(
        self, kind: str, value: object, *, context: str, citation: str | None = None
    ) -> object:
        """Resolve a label citation to its index; pass other values through.

        Parameters
        ----------
        kind : str
            Entity kind the citation refers to.
        value : object
            The cited value; a string is treated as a label, anything
            else is returned unchanged (type checks happen elsewhere).
        context : str
            Prefix naming the citing location in the error message,
            for example ``"SET_ACTUATOR_AXIS: argument 'frame'"``.
        citation : str, optional
            Manual citation appended to the error message.

        Returns
        -------
        object
            The resolved 1-based index for a known label, or ``value``
            unchanged when it is not a string.

        Raises
        ------
        ScriptReferenceError
            If the label is unknown; the message lists the labels the
            registry knows for this kind.
        """
        self._require_kind(kind)
        if not isinstance(value, str):
            return value
        index = self._labels[kind].get(value)
        if index is not None:
            return index
        noun = _NOUNS[kind]
        known = self._labels[kind]
        if known:
            listing = ", ".join(f"{label!r} -> {idx}" for label, idx in sorted(known.items()))
            hint = f"known {noun} labels are {listing}"
        else:
            hint = f"no {noun} labels are registered yet"
        raise ScriptReferenceError(
            f"{context} cites unknown {noun} label {value!r}; {hint}. Labels are "
            "attached at creation with label= or declared with declare_existing()."
            + (f" ({citation})" if citation else "")
        )

    def check_index(
        self, kind: str, value: object, *, context: str, citation: str | None = None
    ) -> None:
        """Reject an index outside the created or declared range.

        The check is skipped for non-integer values (type errors are
        reported elsewhere), for an undeclared boundary inventory
        (the total is unknowable statically, so the build stays
        permissive), and for the -1 all-boundaries form.

        Parameters
        ----------
        kind : str
            Entity kind the index refers to.
        value : object
            The cited index, 1-based.
        context : str
            Prefix naming the citing location in the error message.
        citation : str, optional
            Manual citation appended to the error message.

        Raises
        ------
        ScriptReferenceError
            If the index falls outside the valid range 1..limit.
        """
        self._require_kind(kind)
        if isinstance(value, bool) or not isinstance(value, int):
            return
        limit = self.limit(kind)
        if limit is None:
            return
        if kind == "boundaries" and value == -1:
            return
        if 1 <= value <= limit:
            return
        noun = _NOUNS[kind]
        if kind == "frames":
            available = (
                f"the reference frame is index 1 and the script has created or declared "
                f"{self._counts[kind]} local frame(s), so valid indices run 1 to {limit}"
            )
            guidance = (
                "FlightStream expects auxiliary definitions before they are referenced; "
                "create the object earlier in the script, or declare objects carried by "
                "the opened project with declare_existing()."
            )
        elif kind == "boundaries":
            available = (
                f"the declared mesh boundary inventory holds {limit} boundary(ies), so "
                f"valid indices run 1 to {limit}, with -1 selecting all boundaries"
            )
            guidance = (
                "Mesh boundaries come from the loaded geometry; check the inventory "
                "declared with declare_existing(boundaries=...) against the geometry "
                "the script opens or imports."
            )
        else:
            available = (
                f"the script has created or declared {self._counts[kind]} {noun}(s), "
                f"so valid indices run 1 to {limit}"
            )
            guidance = (
                "FlightStream expects auxiliary definitions before they are referenced; "
                "create the object earlier in the script, or declare objects carried by "
                "the opened project with declare_existing()."
            )
        raise ScriptReferenceError(
            f"{context} cites {noun} {value!r}, but {available}. {guidance}"
            + (f" ({citation})" if citation else "")
        )

    def check_boundary_count(
        self, value: object, *, context: str, citation: str | None = None
    ) -> None:
        """Reject a boundary count above the declared inventory.

        Count arguments such as NUM_BOUNDARIES say how many boundaries
        the following list selects; a count above the inventory means
        the command will cite boundaries that do not exist. Skipped
        for non-integer values, for an undeclared inventory, and for
        the -1 all-boundaries form.

        Parameters
        ----------
        value : object
            The count value; -1 selects every boundary.
        context : str
            Prefix naming the citing location in the error message.
        citation : str, optional
            Manual citation appended to the error message.

        Raises
        ------
        ScriptReferenceError
            If the count exceeds the declared boundary total or is
            negative without being -1.
        """
        total = self._boundary_total
        if total is None or isinstance(value, bool) or not isinstance(value, int):
            return
        if value == -1 or 0 <= value <= total:
            return
        raise ScriptReferenceError(
            f"{context} counts {value} mesh boundaries, but the declared boundary "
            f"inventory holds {total}; a count above the inventory cites boundaries "
            "that do not exist. Use -1 to select every boundary, or fix the "
            "declaration given to declare_existing(boundaries=...)."
            + (f" ({citation})" if citation else "")
        )
