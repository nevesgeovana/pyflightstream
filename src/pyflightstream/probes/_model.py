"""Validation boundary shared by the probe geometry models."""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationError

from pyflightstream.probes.errors import ProbeGeometryError


class ProbeModel(BaseModel):
    """Preserve the geometry refusal after Pydantic has collected field errors.

    Pydantic collects ValueError subclasses, including ProbeGeometryError,
    into ValidationError. Translate at each validation entry point so callers
    receive the probe layer's documented refusal with its field diagnostics.
    Finite values retain Pydantic's existing coercion and geometry validators.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    def __init__(self, **data: Any) -> None:
        try:
            super().__init__(**data)
        except ValidationError as error:
            raise ProbeGeometryError(str(error)) from error

    @classmethod
    def model_validate(cls, *args: Any, **kwargs: Any) -> Self:
        try:
            return super().model_validate(*args, **kwargs)
        except ValidationError as error:
            raise ProbeGeometryError(str(error)) from error

    @classmethod
    def model_validate_json(cls, *args: Any, **kwargs: Any) -> Self:
        try:
            return super().model_validate_json(*args, **kwargs)
        except ValidationError as error:
            raise ProbeGeometryError(str(error)) from error

    @classmethod
    def model_validate_strings(cls, *args: Any, **kwargs: Any) -> Self:
        try:
            return super().model_validate_strings(*args, **kwargs)
        except ValidationError as error:
            raise ProbeGeometryError(str(error)) from error
