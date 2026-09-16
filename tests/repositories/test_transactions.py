import pytest
from beanie import PydanticObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from canterlot.models.club import ClubModel
from canterlot.repositories.beanie.transactions import (
    TransactionError,
    transactional,
    transactional_or_false,
    transactional_or_none,
)
from tools.factories import ClubFactory

pytestmark = pytest.mark.asyncio(loop_scope="session")


class _Boom(Exception):
    pass


class _Conflict(TransactionError):
    pass


class _SampleRepository:
    @transactional(ClubModel)
    async def create_two_clubs(
        self,
        session: AsyncClientSession,
        slug_a: str,
        slug_b: str,
    ) -> list[ClubModel]:
        club_a = ClubModel(name="Club A", slug=slug_a)
        club_b = ClubModel(name="Club B", slug=slug_b)
        await club_a.insert(session=session)
        await club_b.insert(session=session)
        return [club_a, club_b]

    @transactional(ClubModel)
    async def insert_then_raise(self, session: AsyncClientSession, slug: str) -> None:
        await ClubModel(name="Rolled Back", slug=slug).insert(session=session)
        raise _Boom("unhandled")

    @transactional_or_false(ClubModel)
    async def rename_or_conflict(
        self,
        session: AsyncClientSession,
        club_id: PydanticObjectId,
        new_slug: str,
    ) -> None:
        club = await ClubModel.get(club_id, session=session)
        if club is None:
            raise _Conflict
        club.slug = new_slug
        await club.save(session=session)

    @transactional_or_false(ClubModel)
    async def raise_unrelated_bool(self, _session: AsyncClientSession) -> None:
        raise _Boom("unhandled")

    @transactional_or_none(ClubModel)
    async def rename_or_conflict_returning(
        self,
        session: AsyncClientSession,
        club_id: PydanticObjectId,
        new_slug: str,
    ) -> ClubModel:
        club = await ClubModel.get(club_id, session=session)
        if club is None:
            raise _Conflict
        club.slug = new_slug
        await club.save(session=session)
        return club

    @transactional_or_none(ClubModel)
    async def raise_unrelated_optional(self, _session: AsyncClientSession) -> ClubModel:
        raise _Boom("unhandled")


def describe_transactional():
    async def it_commits_every_write_made_inside_the_body():
        repo = _SampleRepository()

        created = await repo.create_two_clubs("txn-slug-a", "txn-slug-b")

        assert len(created) == 2
        assert await ClubModel.find(ClubModel.slug == "txn-slug-a").count() == 1
        assert await ClubModel.find(ClubModel.slug == "txn-slug-b").count() == 1

    async def it_rolls_back_and_propagates_on_an_unhandled_exception():
        repo = _SampleRepository()

        with pytest.raises(_Boom):
            await repo.insert_then_raise("txn-slug-rolled-back")

        assert await ClubModel.find(ClubModel.slug == "txn-slug-rolled-back").count() == 0


def describe_transactional_or_false():
    async def it_returns_true_and_persists_the_write_on_success():
        club = await ClubFactory.create_async()
        repo = _SampleRepository()

        matched = await repo.rename_or_conflict(PydanticObjectId(club.id), "renamed-via-decorator")

        assert matched is True
        found = await ClubModel.get(club.id)
        assert found is not None
        assert found.slug == "renamed-via-decorator"

    async def it_returns_false_and_rolls_back_on_the_declared_conflict():
        repo = _SampleRepository()

        matched = await repo.rename_or_conflict(PydanticObjectId(), "does-not-matter")

        assert matched is False

    async def it_still_propagates_an_exception_that_is_not_the_declared_conflict():
        repo = _SampleRepository()

        with pytest.raises(_Boom):
            await repo.raise_unrelated_bool()


def describe_transactional_or_none():
    async def it_returns_the_bodys_result_on_success():
        club = await ClubFactory.create_async()
        repo = _SampleRepository()

        renamed = await repo.rename_or_conflict_returning(PydanticObjectId(club.id), "renamed-again")

        assert renamed is not None
        assert renamed.slug == "renamed-again"

    async def it_returns_none_on_the_declared_conflict():
        repo = _SampleRepository()

        result = await repo.rename_or_conflict_returning(PydanticObjectId(), "does-not-matter")

        assert result is None

    async def it_still_propagates_an_exception_that_is_not_the_declared_conflict():
        repo = _SampleRepository()

        with pytest.raises(_Boom):
            await repo.raise_unrelated_optional()
