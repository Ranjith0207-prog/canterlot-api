import re
from datetime import datetime
from typing import cast

from beanie import PydanticObjectId
from beanie.operators import Pull, Push
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.results import UpdateResult

from canterlot.exceptions import ClubNotFoundError
from canterlot.models import BookModel, ClubMembershipModel, ClubModel
from canterlot.models.club import CatalogEntryModel
from canterlot.pagination import Page, SortDirection
from canterlot.repositories import ClubRepository
from canterlot.repositories.beanie.transactions import transactional
from canterlot.types import ClubNameStr, ClubSlugStr, JoinPolicy, LanguageStr, MembershipStatus

_CATALOG_SORT_FIELD_PATHS = {
    "suggested_at": "catalog.suggested_at",
    "title": "book.title",
    "author": "book.authors",
    "year": "book.year",
}
_BOOK_JOINED_SORT_FIELDS = {"title", "author", "year"}


class AllowSuggestionProjection(BaseModel):
    allow_suggestions: bool


class PreferredLanguagesProjection(BaseModel):
    preferred_languages: list[LanguageStr]


class NameProjection(BaseModel):
    name: ClubNameStr


class IdProjection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PydanticObjectId = Field(alias="_id")


class CatalogProjection(BaseModel):
    catalog: list[CatalogEntryModel]


class BeanieClubRepository(ClubRepository):
    async def find_by_id(self, club_id: PydanticObjectId) -> ClubModel | None:
        return await ClubModel.get(club_id)

    async def find_club_name_by_id(self, club_id: PydanticObjectId) -> ClubNameStr | None:
        projection = await ClubModel.find_one(ClubModel.id == club_id).project(NameProjection)

        if not projection:
            return None
        return projection.name

    async def get_preferred_languages_by_id(self, club_id: PydanticObjectId) -> list[LanguageStr]:
        query = ClubModel.find_one(ClubModel.id == club_id)

        projection = await query.project(PreferredLanguagesProjection)

        if not projection:
            raise ClubNotFoundError("This club no longer exists.")

        return projection.preferred_languages

    async def find_by_slug(self, slug: ClubSlugStr) -> ClubModel | None:
        return await ClubModel.find_one(ClubModel.slug == slug)

    async def find_id_by_slug(self, slug: ClubSlugStr) -> PydanticObjectId | None:
        projection = await ClubModel.find_one(ClubModel.slug == slug).project(IdProjection)

        if not projection:
            return None
        return projection.id

    async def exists_by_club_slug(self, slug: ClubSlugStr) -> bool:
        return await ClubModel.find(ClubModel.slug == slug).exists()

    async def exists_by_club_id_and_catalog_book_id(
        self,
        club_id: PydanticObjectId,
        book_id: PydanticObjectId,
    ) -> bool:
        return await ClubModel.find(ClubModel.id == club_id, ClubModel.catalog.book_id == book_id).exists()

    async def find_catalog_entry_by_club_id_and_book_id(
        self,
        club_id: PydanticObjectId,
        book_id: PydanticObjectId,
    ) -> CatalogEntryModel | None:
        query = ClubModel.find_one(ClubModel.id == club_id, ClubModel.catalog.book_id == book_id)

        projected = await query.project(CatalogProjection)

        if not projected or not projected.catalog:
            return None

        return next((entry for entry in projected.catalog if entry.book_id == book_id), None)

    async def find_catalog_page_by_club_id(
        self,
        club_id: PydanticObjectId,
        page: int,
        limit: int,
        sort_by: str | None = None,
        sort_direction: SortDirection = SortDirection.DESC,
        suggested_by: PydanticObjectId | None = None,
        q: str | None = None,
    ) -> Page[CatalogEntryModel]:
        sort_field = sort_by if sort_by in _CATALOG_SORT_FIELD_PATHS else "suggested_at"
        sort_path = _CATALOG_SORT_FIELD_PATHS[sort_field]
        direction = 1 if sort_direction == SortDirection.ASC else -1

        pipeline: list[dict] = [{"$match": {"_id": club_id}}, {"$unwind": "$catalog"}]

        if suggested_by is not None:
            pipeline.append({"$match": {"catalog.suggested_by": suggested_by}})

        if sort_field in _BOOK_JOINED_SORT_FIELDS or q is not None:
            pipeline.append(
                {
                    "$lookup": {
                        "from": BookModel.get_settings().name,
                        "localField": "catalog.book_id",
                        "foreignField": "_id",
                        "as": "book",
                    }
                }
            )
            pipeline.append({"$unwind": {"path": "$book", "preserveNullAndEmptyArrays": True}})

        if q is not None:
            pattern = re.escape(q)
            pipeline.append(
                {
                    "$match": {
                        "$or": [
                            {"book.title": {"$regex": pattern, "$options": "i"}},
                            {"book.authors": {"$regex": pattern, "$options": "i"}},
                        ]
                    }
                }
            )

        pipeline.append({"$sort": {sort_path: direction}})
        pipeline.append(
            {
                "$facet": {
                    "items": [
                        {"$skip": (page - 1) * limit},
                        {"$limit": limit},
                        {"$replaceRoot": {"newRoot": "$catalog"}},
                    ],
                    "total": [{"$count": "count"}],
                }
            }
        )

        result = await ClubModel.aggregate(pipeline).to_list()
        facet = result[0] if result else {"items": [], "total": []}

        items = [CatalogEntryModel(**item) for item in facet["items"]]
        total_items = facet["total"][0]["count"] if facet["total"] else 0

        return Page(items=items, total_items=total_items, current_page=page, page_size=limit)

    async def is_suggestions_allowed(self, club_id: PydanticObjectId) -> bool:
        query = ClubModel.find_one(ClubModel.id == club_id)

        projection = await query.project(AllowSuggestionProjection)

        return projection.allow_suggestions if projection else False

    async def add_to_catalog(self, club_id: PydanticObjectId, entry: CatalogEntryModel) -> None:
        await ClubModel.find_one(ClubModel.id == club_id).update_one(Push({ClubModel.catalog: entry}))

    async def remove_from_catalog(self, club_id: PydanticObjectId, book_id: PydanticObjectId) -> None:
        await ClubModel.find_one(ClubModel.id == club_id).update_one(Pull({ClubModel.catalog: {"book_id": book_id}}))

    @transactional
    async def save_new_club_with_owner(
        self,
        session: AsyncClientSession,
        club: ClubModel,
        owner_id: PydanticObjectId,
        joined_at: datetime,
    ) -> ClubModel:
        await club.insert(session=session)
        await ClubMembershipModel(
            club_id=PydanticObjectId(club.id),
            user_id=owner_id,
            status=MembershipStatus.OWNER,
            joined_at=joined_at,
        ).insert(session=session)

        return club

    async def update_settings(
        self,
        club_id: PydanticObjectId,
        name: ClubNameStr | None = None,
        slug: ClubSlugStr | None = None,
        description: str | None = None,
        join_policy: JoinPolicy | None = None,
        allow_suggestions: bool | None = None,
        preferred_languages: list[LanguageStr] | None = None,
    ) -> bool:
        updates: dict[str, object] = {}
        if name is not None:
            updates["name"] = name
        if slug is not None:
            updates["slug"] = slug
        if description is not None:
            updates["description"] = description
        if join_policy is not None:
            updates["join_policy"] = join_policy
        if allow_suggestions is not None:
            updates["allow_suggestions"] = allow_suggestions
        if preferred_languages is not None:
            updates["preferred_languages"] = preferred_languages

        result = await ClubModel.find_one(ClubModel.id == club_id).update_one({"$set": updates})

        return cast(UpdateResult, result).matched_count > 0

    async def save(self, club: ClubModel) -> ClubModel:
        return await club.save()

    @transactional
    async def delete_with_memberships(self, session: AsyncClientSession, club_id: PydanticObjectId) -> None:
        await ClubModel.find_one(ClubModel.id == club_id, session=session).delete(session=session)
        await ClubMembershipModel.find(
            ClubMembershipModel.club_id == club_id,
            session=session,
        ).delete(session=session)
