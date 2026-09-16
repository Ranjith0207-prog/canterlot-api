from beanie import PydanticObjectId

from canterlot.types import RoundSelectionMode, RoundStatus
from tools.factories import RoundFactory

SOME_CLUB_ID = PydanticObjectId("507f1f77bcf86cd799439011")
SOME_USER_ID = PydanticObjectId("507f1f77bcf86cd799439012")


def describe_round_model():
    def it_builds_a_valid_round_with_defaults():
        round_ = RoundFactory.build(
            club_id=SOME_CLUB_ID,
            started_by=SOME_USER_ID,
            selection_mode=RoundSelectionMode.RANDOM,
            status=RoundStatus.DECIDED,
        )

        assert round_.club_id == SOME_CLUB_ID
        assert round_.started_by == SOME_USER_ID
        assert round_.candidate_pool == []
        assert round_.resolution_method is None
        assert round_.book_id is None
        assert round_.decided_at is None
