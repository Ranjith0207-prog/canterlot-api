from beanie import PydanticObjectId

from canterlot.models import RoundCompletionModel
from canterlot.repositories import RoundCompletionRepository


class BeanieRoundCompletionRepository(RoundCompletionRepository):
    async def find_majority_excluded_book_ids(
        self,
        club_id: PydanticObjectId,
        current_member_ids: set[PydanticObjectId],
    ) -> set[PydanticObjectId]:
        results = (
            await RoundCompletionModel.find(RoundCompletionModel.club_id == club_id)
            .aggregate(
                [
                    {
                        "$group": {
                            "_id": "$round_id",
                            "book_id": {"$first": "$book_id"},
                            "total_finishers": {"$sum": 1},
                            "current_finishers": {
                                "$sum": {"$cond": [{"$in": ["$user_id", list(current_member_ids)]}, 1, 0]}
                            },
                        }
                    },
                    {"$match": {"$expr": {"$gt": ["$current_finishers", {"$divide": ["$total_finishers", 2]}]}}},
                    {"$group": {"_id": None, "book_ids": {"$addToSet": "$book_id"}}},
                ]
            )
            .to_list()
        )

        return set(results[0]["book_ids"]) if results else set()
