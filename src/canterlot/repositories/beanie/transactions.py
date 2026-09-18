import functools
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Concatenate

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.mongo_client import AsyncMongoClient

from canterlot.models import BEANIE_DOCUMENT_MODELS


class TransactionError(Exception):
    """Base for an expected, business-rule conflict raised inside a transactional method body."""


def _shared_client() -> AsyncMongoClient:
    # Every model in BEANIE_DOCUMENT_MODELS is initialized against the same database/client
    # (see bootstrap_beanie), so any one of them resolves to the client the whole app shares.
    return BEANIE_DOCUMENT_MODELS[0].get_pymongo_collection().database.client


def transactional[S, T, **P](
    func: Callable[Concatenate[S, AsyncClientSession, P], Awaitable[T]],
) -> Callable[Concatenate[S, P], Coroutine[Any, Any, T]]:
    @functools.wraps(func)
    async def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> T:
        async def _do(session: AsyncClientSession) -> T:
            return await func(self, session, *args, **kwargs)

        async with _shared_client().start_session() as session:
            return await session.with_transaction(_do)

    return wrapper


def transactional_or_false[S, **P](
    func: Callable[Concatenate[S, AsyncClientSession, P], Awaitable[None]],
) -> Callable[Concatenate[S, P], Coroutine[Any, Any, bool]]:
    @functools.wraps(func)
    async def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> bool:
        async def _do(session: AsyncClientSession) -> None:
            await func(self, session, *args, **kwargs)

        try:
            async with _shared_client().start_session() as session:
                await session.with_transaction(_do)
        except TransactionError:
            return False
        return True

    return wrapper


def transactional_or_none[S, T, **P](
    func: Callable[Concatenate[S, AsyncClientSession, P], Awaitable[T]],
) -> Callable[Concatenate[S, P], Coroutine[Any, Any, T | None]]:
    @functools.wraps(func)
    async def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> T | None:
        async def _do(session: AsyncClientSession) -> T:
            return await func(self, session, *args, **kwargs)

        try:
            async with _shared_client().start_session() as session:
                return await session.with_transaction(_do)
        except TransactionError:
            return None

    return wrapper
