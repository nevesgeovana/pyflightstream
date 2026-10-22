"""How one validated command is rendered to script text, as a mixin of ``Script``."""

from __future__ import annotations

from pyflightstream.commands import ArgSpec, ArgType, CommandEntry, Layout, ListSeparator
from pyflightstream.script._arg_checks import CommandArgumentError


def _check_joins(entry: CommandEntry, bound: dict) -> None:
    """Refuse an argument that joins a preceding argument the call left out."""
    for position, spec in enumerate(entry.args):
        if spec.joins_previous and spec.name in bound:
            anchor = entry.args[position - 1]
            if anchor.name not in bound:
                raise CommandArgumentError(
                    f"{entry.name}: {spec.name} needs {anchor.name}, the preceding "
                    f"argument it joins ({entry.citation})"
                )


class _ScriptRendering:
    """The rendering methods of :class:`~pyflightstream.script.Script`, one per layout."""

    def _format_scalar(self, value: object) -> str:
        return str(value)

    def _list_lines(self, spec: ArgSpec, items: list) -> list[str]:
        rendered = [self._format_scalar(item) for item in items]
        if spec.separator is ListSeparator.NEWLINE:
            return rendered
        joiner = "," if spec.separator is ListSeparator.COMMA else " "
        return [joiner.join(rendered)]

    def _render_command(self, entry: CommandEntry, bound: dict) -> tuple[list[str], bool]:
        _check_joins(entry, bound)
        provided = [(spec, bound[spec.name]) for spec in entry.args if spec.name in bound]
        if entry.layout is Layout.BARE:
            return [entry.name], False
        if entry.layout in (Layout.INLINE, Layout.MIXED_INLINE):
            return self._render_inline(entry, provided)
        if entry.layout is Layout.PAYLOAD_LINES:
            return self._render_payload_lines(entry, provided)
        if entry.layout is Layout.PARAM_LINES:
            return self._render_param_lines(entry, provided)
        return self._render_keyword_block(entry, provided)

    def _render_inline(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render an inline command: its values on one line, own-line values after it."""
        inline_parts = [entry.name]
        tail_lines: list[str] = []
        for spec, value in provided:
            if spec.own_line:
                tail_lines.append(self._format_scalar(value))
            elif spec.is_list:
                inline_parts.append(" ".join(self._format_scalar(item) for item in value))  # type: ignore[attr-defined]
            else:
                from pyflightstream.script._build_forms import _check_inline_token

                _check_inline_token(entry, spec, value)
                inline_parts.append(self._format_scalar(value))
        return [" ".join(inline_parts), *tail_lines], bool(tail_lines)

    def _render_payload_lines(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render a payload-lines command: scalars inline, each list on lines after it."""
        inline_parts = [entry.name]
        tail_lines: list[str] = []
        for spec, value in provided:
            if spec.is_list:
                tail_lines.extend(self._list_lines(spec, value))  # type: ignore[arg-type]
            else:
                inline_parts.append(self._format_scalar(value))
        return [" ".join(inline_parts), *tail_lines], True

    def _render_param_lines(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render a param-lines command: one ``NAME value`` line per argument."""
        lines = [entry.name]
        for spec, value in provided:
            if spec.is_list:
                lines.extend(self._list_lines(spec, value))  # type: ignore[arg-type]
            elif spec.type is ArgType.PATH or spec.own_line:
                lines.append(self._format_scalar(value))
            else:
                lines.append(f"{spec.name.upper()} {self._format_scalar(value)}")
        return lines, True

    def _render_keyword_block(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render a keyword-block command: values on its line first, then one keyword per line."""
        lines = [entry.name]
        for spec, value in provided:
            if spec.on_command_line:
                # The leading arguments of a keyword block that sit on the
                # command's own line (WRAPPER_EDIT_LOCAL_CONTROL, FSM-26.120
                # p.314). The schema holds them to the leading positions,
                # so lines[0] is still the command name here.
                lines[0] += f" {self._format_scalar(value)}"
            elif spec.is_list:
                lines.extend(self._list_lines(spec, value))  # type: ignore[arg-type]
            elif spec.type is ArgType.BOOL:
                # Presence keyword (FSM-26.120 p.307): True is the bare keyword
                # line, False emits nothing.
                if value:
                    lines.append(spec.name.upper())
            elif spec.joins_previous:
                lines[-1] += f" {self._format_scalar(value)}"
            else:
                lines.append(f"{spec.name.upper()} {self._format_scalar(value)}")
        if entry.terminator is not None:
            lines.append(entry.terminator)
        return lines, True
