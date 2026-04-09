from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy.orm import DeclarativeBase


class ValidatedModelMixin:
    __required_fields__: Sequence[str] = ()

    def __init__(self, **kwargs: object) -> None:
        missing_fields = [field for field in self.__required_fields__ if kwargs.get(field) is None]
        if missing_fields:
            raise ValidationError.from_exception_data(
                title=self.__class__.__name__,
                line_errors=[
                    {
                        "type": "missing",
                        "loc": (field,),
                        "input": kwargs,
                    }
                    for field in missing_fields
                ],
            )
        for key, value in kwargs.items():
            setattr(self, key, value)


class Base(ValidatedModelMixin, DeclarativeBase):
    pass
