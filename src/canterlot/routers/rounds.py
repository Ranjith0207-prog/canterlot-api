from datetime import UTC, datetime
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Response, status

from canterlot.dto.book import BookResponse
from canterlot.dto.round import (
    FinalizeRoundRequest,
    MarkRoundFinishedRequest,
    RoundProgressEntryResponse,
    RoundProgressResponse,
    RoundResponse,
    StartRoundRequest,
)
from canterlot.models import BookModel, ClubModel, RatingStats, UserModel
from canterlot.models.round import RoundModel
from canterlot.routers.responses import (
    FINALIZE_READING_ROUND_RESPONSES,
    GET_ROUND_PROGRESS_RESPONSES,
    MARK_ROUND_FINISHED_RESPONSES,
    START_READING_ROUND_RESPONSES,
)
from canterlot.services import RoundService

from .dependencies.providers import (
    get_club_from_slug,
    get_club_id_from_slug,
    get_current_user,
    get_current_user_id,
    get_round_service,
)
from .dependencies.rate_limiter import rate_limit_club_moderation

router = APIRouter(prefix="/clubs/{club_slug}", tags=["Reading Rounds"])

_START_ROUND_RATE_LIMIT = Depends(rate_limit_club_moderation("start_round"))
_FINALIZE_ROUND_RATE_LIMIT = Depends(rate_limit_club_moderation("finalize_round"))

_NEUTRAL_RATING_STATS = RatingStats(average_rating=None, rating_count=0)


def _to_book_response(book: BookModel, rating_stats_by_book: dict[PydanticObjectId, RatingStats]) -> BookResponse:
    stats = rating_stats_by_book.get(PydanticObjectId(book.id), _NEUTRAL_RATING_STATS)
    return BookResponse.with_rating_stats(book, stats)


async def _build_response(round_service: RoundService, round_: RoundModel, started_by_username: str) -> RoundResponse:
    display = await round_service.resolve_display(round_)

    book = _to_book_response(display.book, display.rating_stats) if display.book else None
    candidate_pool = (
        [_to_book_response(pool_book, display.rating_stats) for pool_book in display.pool_books]
        if round_.candidate_pool
        else None
    )

    return RoundResponse.from_model(round_, started_by_username, book, candidate_pool)


@router.post(
    "/rounds",
    operation_id="startReadingRound",
    response_model=RoundResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_START_ROUND_RATE_LIMIT],
    responses=START_READING_ROUND_RESPONSES,
)
async def start_reading_round(
    club_slug: str,
    club: Annotated[ClubModel, Depends(get_club_from_slug)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
    payload: StartRoundRequest,
    round_service: Annotated[RoundService, Depends(get_round_service)],
    response: Response,
) -> RoundResponse:
    round_ = await round_service.start_round(
        club,
        PydanticObjectId(current_user.id),
        payload,
        datetime.now(UTC),
    )

    response.headers["Location"] = f"/v1/clubs/{club_slug}/round"

    return await _build_response(round_service, round_, current_user.username)


@router.patch(
    "/round",
    operation_id="finalizeReadingRound",
    response_model=RoundResponse,
    dependencies=[_FINALIZE_ROUND_RATE_LIMIT],
    responses=FINALIZE_READING_ROUND_RESPONSES,
)
async def finalize_reading_round(
    club: Annotated[ClubModel, Depends(get_club_from_slug)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
    payload: FinalizeRoundRequest,
    round_service: Annotated[RoundService, Depends(get_round_service)],
) -> RoundResponse:
    round_ = await round_service.finalize_round(
        club,
        PydanticObjectId(current_user.id),
        payload.resolution_method,
        datetime.now(UTC),
    )

    return await _build_response(round_service, round_, current_user.username)


@router.get(
    "/round/progress",
    operation_id="getRoundProgress",
    response_model=RoundProgressResponse,
    responses=GET_ROUND_PROGRESS_RESPONSES,
)
async def get_round_progress(
    club_id: Annotated[PydanticObjectId, Depends(get_club_id_from_slug)],
    current_user_id: Annotated[PydanticObjectId, Depends(get_current_user_id)],
    round_service: Annotated[RoundService, Depends(get_round_service)],
) -> RoundProgressResponse:
    progress = await round_service.get_progress(club_id, current_user_id)

    return RoundProgressResponse(
        entries=[RoundProgressEntryResponse(username=entry.username, finished=entry.finished) for entry in progress]
    )


@router.put(
    "/round/me",
    operation_id="markRoundFinished",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=MARK_ROUND_FINISHED_RESPONSES,
)
async def mark_round_finished(
    club_id: Annotated[PydanticObjectId, Depends(get_club_id_from_slug)],
    current_user_id: Annotated[PydanticObjectId, Depends(get_current_user_id)],
    round_service: Annotated[RoundService, Depends(get_round_service)],
    payload: MarkRoundFinishedRequest | None = None,
) -> None:
    rating = payload.rating if payload is not None else None
    await round_service.mark_finished(club_id, current_user_id, rating, datetime.now(UTC))
