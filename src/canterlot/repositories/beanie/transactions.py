import functools
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Concatenate, ParamSpec, TypeVar

from beanie import Document
from pymongo.asynchronous.client_session import AsyncClientSession

P = ParamSpec("P")
S = TypeVar("S")
T = TypeVar("T")


class TransactionError(Exception):
    """Base for an expected, business-rule conflict raised inside a transactional method body."""


def transactional(
    model: type[Document],
) -> Callable[
    [Callable[Concatenate[S, AsyncClientSession, P], Awaitable[T]]],
    Callable[Concatenate[S, P], Coroutine[Any, Any, T]],
]:
    def decorator(
        func: Callable[Concatenate[S, AsyncClientSession, P], Awaitable[T]],
    ) -> Callable[Concatenate[S, P], Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> T:
            client = model.get_pymongo_collection().database.client

            async def _do(session: AsyncClientSession) -> T:
                return await func(self, session, *args, **kwargs)

            async with client.start_session() as session:
                return await session.with_transaction(_do)

        return wrapper

    return decorator


def transactional_or_false(
    model: type[Document],
) -> Callable[
    [Callable[Concatenate[S, AsyncClientSession, P], Awaitable[None]]],
    Callable[Concatenate[S, P], Coroutine[Any, Any, bool]],
]:
    def decorator(
        func: Callable[Concatenate[S, AsyncClientSession, P], Awaitable[None]],
    ) -> Callable[Concatenate[S, P], Coroutine[Any, Any, bool]]:
        @functools.wraps(func)
        async def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> bool:
            client = model.get_pymongo_collection().database.client

            async def _do(session: AsyncClientSession) -> None:
                await func(self, session, *args, **kwargs)

            try:
                async with client.start_session() as session:
                    await session.with_transaction(_do)
            except TransactionError:
                return False
            return True

        return wrapper

    return decorator


def transactional_or_none(
    model: type[Document],
) -> Callable[
    [Callable[Concatenate[S, AsyncClientSession, P], Awaitable[T]]],
    Callable[Concatenate[S, P], Coroutine[Any, Any, T | None]],
]:
    def decorator(
        func: Callable[Concatenate[S, AsyncClientSession, P], Awaitable[T]],
    ) -> Callable[Concatenate[S, P], Coroutine[Any, Any, T | None]]:
        @functools.wraps(func)
        async def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> T | None:
            client = model.get_pymongo_collection().database.client

            async def _do(session: AsyncClientSession) -> T:
                return await func(self, session, *args, **kwargs)

            try:
                async with client.start_session() as session:
                    return await session.with_transaction(_do)
            except TransactionError:
                return None

        return wrapper

    return decorator
