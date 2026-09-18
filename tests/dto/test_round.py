from datetime import date

import pytest
from pydantic import ValidationError

from canterlot.dto.round import (
    DeadlineRequest,
    MarkRoundFinishedRequest,
    RoundProgressEntryResponse,
    RoundProgressResponse,
)
from canterlot.types import DeadlineType, DeadlineUnit


def describe_deadline_request():
    def it_accepts_a_valid_preset_deadline():
        request = DeadlineRequest(type=DeadlineType.PRESET, value=2, unit=DeadlineUnit.WEEKS)

        assert request.value == 2
        assert request.unit == DeadlineUnit.WEEKS

    def it_accepts_a_valid_custom_deadline():
        request = DeadlineRequest(type=DeadlineType.CUSTOM, target_date=date(2026, 6, 1))

        assert request.target_date == date(2026, 6, 1)

    def it_rejects_a_preset_deadline_missing_value_or_unit():
        with pytest.raises(ValidationError, match="requires both value and unit"):
            DeadlineRequest(type=DeadlineType.PRESET, unit=DeadlineUnit.WEEKS)

    def it_rejects_a_preset_deadline_with_a_target_date():
        with pytest.raises(ValidationError, match="must not set target_date"):
            DeadlineRequest(type=DeadlineType.PRESET, value=1, unit=DeadlineUnit.MONTHS, target_date=date(2026, 6, 1))

    def it_rejects_a_custom_deadline_missing_a_target_date():
        with pytest.raises(ValidationError, match="requires target_date"):
            DeadlineRequest(type=DeadlineType.CUSTOM)

    def it_rejects_a_custom_deadline_with_value_or_unit():
        with pytest.raises(ValidationError, match="must not set value or unit"):
            DeadlineRequest(type=DeadlineType.CUSTOM, target_date=date(2026, 6, 1), value=1, unit=DeadlineUnit.DAYS)

    def it_rejects_a_preset_value_below_the_minimum():
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            DeadlineRequest(type=DeadlineType.PRESET, value=0, unit=DeadlineUnit.WEEKS)

    def it_rejects_a_preset_value_above_the_maximum():
        with pytest.raises(ValidationError, match="less than or equal to 52"):
            DeadlineRequest(type=DeadlineType.PRESET, value=53, unit=DeadlineUnit.WEEKS)


def describe_mark_round_finished_request():
    def it_defaults_rating_to_none():
        request = MarkRoundFinishedRequest()

        assert request.rating is None

    @pytest.mark.parametrize("rating", [0.5, 1.0, 2.5, 5.0])
    def it_accepts_half_step_ratings_within_bounds(rating: float):
        request = MarkRoundFinishedRequest(rating=rating)

        assert request.rating == rating

    @pytest.mark.parametrize("rating", [0.0, 0.4, 5.5])
    def it_rejects_ratings_outside_bounds(rating: float):
        with pytest.raises(ValidationError):
            MarkRoundFinishedRequest(rating=rating)

    def it_rejects_a_rating_not_on_a_half_step():
        with pytest.raises(ValidationError):
            MarkRoundFinishedRequest(rating=1.2)


def describe_round_progress_response():
    def it_wraps_a_list_of_member_entries():
        response = RoundProgressResponse(
            entries=[
                RoundProgressEntryResponse(username="alice", finished=True),
                RoundProgressEntryResponse(username="bob", finished=False),
            ]
        )

        assert [entry.username for entry in response.entries] == ["alice", "bob"]
        assert [entry.finished for entry in response.entries] == [True, False]
