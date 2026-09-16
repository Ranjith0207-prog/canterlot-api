import pytest
from pydantic import ValidationError

from tools.factories import ClubFactory


def describe_club_name_constraints():
    @pytest.mark.parametrize("bad_name", ["ab", "a" * 51, "  "])
    def it_rejects_names_outside_the_length_bounds(bad_name: str):
        with pytest.raises(ValidationError):
            ClubFactory.build(name=bad_name)

    def it_accepts_a_name_within_bounds():
        assert ClubFactory.build(name="Book Club").name == "Book Club"
