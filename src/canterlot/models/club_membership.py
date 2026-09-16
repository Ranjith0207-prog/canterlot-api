from datetime import datetime
from typing import ClassVar

from beanie import Document, PydanticObjectId
from pymongo import ASCENDING, IndexModel

from canterlot.types import MembershipStatus


class ClubMembershipModel(Document):
    club_id: PydanticObjectId
    user_id: PydanticObjectId
    status: MembershipStatus
    joined_at: datetime | None = None
    requested_at: datetime | None = None

    class Settings:
        name = "club_memberships"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("club_id", ASCENDING), ("user_id", ASCENDING)], unique=True, name="unique_club_user_idx"),
            IndexModel([("user_id", ASCENDING)], name="user_membership_idx"),
        ]
