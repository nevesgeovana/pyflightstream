"""Validation boundary shared by the probe geometry models."""

from functools import wraps
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationError

from pyflightstream.probes.errors import ProbeGeometryError


def _geometry_initializer(initializer: Any) -> Any:
    """Wrap construction after schema creation, preserving the base-init marker."""

    @wraps(initializer)
    def initialize(self: Any, **data: Any) -> None:
        try:
            initializer(self, **data)
        except ValidationError as error:
            raise ProbeGeometryError(str(error)) from error

    return initialize


class ProbeModel(BaseModel):
    """Preserve the geometry refusal after Pydantic has collected field errors.

    Pydantic collects ValueError subclasses, including ProbeGeometryError,
    into ValidationError. Translate at each validation entry point so callers
    receive the probe layer's documented refusal with its field diagnostics.
    Finite values retain Pydantic's existing coercion and geometry validators.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Translate constructor errors without making validation call a custom init.

        The schema is already built at this hook. functools.wraps retains
        Pydantic's base-init marker for descendants and schema rebuilds, so
        explicit validation options continue through the validation engine.
        """
        super().__pydantic_init_subclass__(**kwargs)
        type.__setattr__(cls, "__init__", _geometry_initializer(cls.__init__))

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Any = None,
        **kwargs: Any,
    ) -> Self:
        try:
            return super().model_validate(
                obj,
                strict=strict,
                from_attributes=from_attributes,
                context=context,
                **kwargs,
            )
        except ValidationError as error:
            raise ProbeGeometryError(str(error)) from error

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        context: Any = None,
        **kwargs: Any,
    ) -> Self:
        try:
            return super().model_validate_json(json_data, strict=strict, context=context, **kwargs)
        except ValidationError as error:
            raise ProbeGeometryError(str(error)) from error

    @classmethod
    def model_validate_strings(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        context: Any = None,
        **kwargs: Any,
    ) -> Self:
        try:
            return super().model_validate_strings(obj, strict=strict, context=context, **kwargs)
        except ValidationError as error:
            raise ProbeGeometryError(str(error)) from error
