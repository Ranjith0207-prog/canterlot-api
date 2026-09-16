from datetime import date

import pytest
from pydantic import ValidationError

from canterlot.dto.round import DeadlineRequest
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
