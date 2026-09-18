from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from canterlot.dto.book import BookResponse
from canterlot.models.round import RoundModel
from canterlot.types import (
    DeadlineType,
    DeadlineUnit,
    RoundResolutionMethod,
    RoundSelectionMode,
    RoundStatus,
    UsernameStr,
)


class DeadlineRequest(BaseModel):
    type: DeadlineType
    value: int | None = Field(default=None, ge=1, le=52)
    unit: DeadlineUnit | None = None
    target_date: date | None = None

    @model_validator(mode="after")
    def check_shape_matches_type(self) -> "DeadlineRequest":
        if self.type == DeadlineType.PRESET:
            if self.value is None or self.unit is None:
                raise ValueError("A PRESET deadline requires both value and unit.")
            if self.target_date is not None:
                raise ValueError("A PRESET deadline must not set target_date.")
        else:
            if self.target_date is None:
                raise ValueError("A CUSTOM deadline requires target_date.")
            if self.value is not None or self.unit is not None:
                raise ValueError("A CUSTOM deadline must not set value or unit.")

        return self


class StartRoundRequest(BaseModel):
    selection_mode: RoundSelectionMode
    deadline: DeadlineRequest | None = None


class FinalizeRoundRequest(BaseModel):
    resolution_method: RoundResolutionMethod


class MarkRoundFinishedRequest(BaseModel):
    rating: float | None = Field(default=None, ge=0.5, le=5.0, multiple_of=0.5)


class RoundProgressEntryResponse(BaseModel):
    username: UsernameStr
    finished: bool


class RoundProgressResponse(BaseModel):
    entries: list[RoundProgressEntryResponse]


class RoundResponse(BaseModel):
    selection_mode: RoundSelectionMode
    status: RoundStatus
    resolution_method: RoundResolutionMethod | None
    book: BookResponse | None
    candidate_pool: list[BookResponse] | None
    deadline: date | None
    started_by: UsernameStr
    created_at: datetime
    decided_at: datetime | None

    @classmethod
    def from_model(
        cls,
        round_: RoundModel,
        started_by_username: UsernameStr,
        book: BookResponse | None,
        candidate_pool: list[BookResponse] | None,
    ) -> "RoundResponse":
        return cls(
            selection_mode=round_.selection_mode,
            status=round_.status,
            resolution_method=round_.resolution_method,
            book=book,
            candidate_pool=candidate_pool,
            deadline=round_.deadline.date() if round_.deadline else None,
            started_by=started_by_username,
            created_at=round_.created_at,
            decided_at=round_.decided_at,
        )
