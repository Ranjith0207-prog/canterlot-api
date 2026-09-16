import pytest
from beanie import PydanticObjectId

from canterlot.repositories.beanie.round_completion import BeanieRoundCompletionRepository
from tools.factories import RoundCompletionFactory

pytestmark = pytest.mark.asyncio(loop_scope="session")

repo = BeanieRoundCompletionRepository()


def _id(document) -> PydanticObjectId:
    return PydanticObjectId(document.id)


def describe_find_majority_excluded_book_ids():
    async def it_excludes_a_book_when_a_majority_of_a_rounds_finishers_are_still_current_members():
        club_id = PydanticObjectId()
        round_id = PydanticObjectId()
        book_id = PydanticObjectId()
        finisher_a, finisher_b, finisher_c = PydanticObjectId(), PydanticObjectId(), PydanticObjectId()
        for user_id in (finisher_a, finisher_b, finisher_c):
            await RoundCompletionFactory.create_async(
                club_id=club_id,
                round_id=round_id,
                book_id=book_id,
                user_id=user_id,
            )

        excluded = await repo.find_majority_excluded_book_ids(club_id, {finisher_a, finisher_b})

        assert excluded == {book_id}

    async def it_does_not_exclude_a_book_when_finishers_have_dropped_to_a_minority():
        club_id = PydanticObjectId()
        round_id = PydanticObjectId()
        book_id = PydanticObjectId()
        finisher_a, finisher_b, finisher_c = PydanticObjectId(), PydanticObjectId(), PydanticObjectId()
        for user_id in (finisher_a, finisher_b, finisher_c):
            await RoundCompletionFactory.create_async(
                club_id=club_id,
                round_id=round_id,
                book_id=book_id,
                user_id=user_id,
            )

        excluded = await repo.find_majority_excluded_book_ids(club_id, {finisher_a})

        assert excluded == set()

    async def it_does_not_exclude_when_exactly_half_of_finishers_remain():
        club_id = PydanticObjectId()
        round_id = PydanticObjectId()
        book_id = PydanticObjectId()
        finisher_a, finisher_b = PydanticObjectId(), PydanticObjectId()
        for user_id in (finisher_a, finisher_b):
            await RoundCompletionFactory.create_async(
                club_id=club_id,
                round_id=round_id,
                book_id=book_id,
                user_id=user_id,
            )

        excluded = await repo.find_majority_excluded_book_ids(club_id, {finisher_a})

        assert excluded == set()

    async def it_evaluates_each_round_completion_independently_for_the_same_book():
        club_id = PydanticObjectId()
        book_id = PydanticObjectId()
        majority_round_id = PydanticObjectId()
        minority_round_id = PydanticObjectId()
        majority_finisher_a, majority_finisher_b = PydanticObjectId(), PydanticObjectId()
        minority_finisher_a, minority_finisher_b, minority_finisher_c = (
            PydanticObjectId(),
            PydanticObjectId(),
            PydanticObjectId(),
        )
        for user_id in (majority_finisher_a, majority_finisher_b):
            await RoundCompletionFactory.create_async(
                club_id=club_id,
                round_id=majority_round_id,
                book_id=book_id,
                user_id=user_id,
            )
        for user_id in (minority_finisher_a, minority_finisher_b, minority_finisher_c):
            await RoundCompletionFactory.create_async(
                club_id=club_id,
                round_id=minority_round_id,
                book_id=book_id,
                user_id=user_id,
            )

        excluded = await repo.find_majority_excluded_book_ids(
            club_id,
            {majority_finisher_a, majority_finisher_b, minority_finisher_a},
        )

        assert excluded == {book_id}

    async def it_returns_an_empty_set_when_the_club_has_no_completions():
        club_id = PydanticObjectId()

        excluded = await repo.find_majority_excluded_book_ids(club_id, {PydanticObjectId()})

        assert excluded == set()
