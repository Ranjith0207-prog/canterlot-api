import asyncio
from collections.abc import Sequence
from typing import Any, NoReturn, cast

from beanie import Document, init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import AutoReconnect, OperationFailure
from pymongo.uri_parser import parse_uri
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

from canterlot.utils import get_logger

logger = get_logger(__name__)

_REPL_SET_NOT_YET_INITIALIZED = 94
_STATUS_CHECK_ATTEMPTS = 5


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _raise_never_connectable(_retry_state: RetryCallState) -> NoReturn:
    raise RuntimeError("mongod never became connectable")


def _raise_never_primary(_retry_state: RetryCallState) -> NoReturn:
    raise RuntimeError("mongod replica set never reached PRIMARY state")


def _is_not_primary(status: dict[str, Any]) -> bool:
    return bool(status["members"][0]["stateStr"] != "PRIMARY")


@retry(
    stop=stop_after_attempt(30),
    wait=wait_fixed(1),
    retry=retry_if_exception_type((AutoReconnect, OperationFailure)),
    sleep=_sleep,
    retry_error_callback=_raise_never_connectable,
)
async def _wait_for_connectable(client: AsyncMongoClient) -> None:
    await client.admin.command("ping")


@retry(
    stop=stop_after_attempt(_STATUS_CHECK_ATTEMPTS),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(AutoReconnect),
    sleep=_sleep,
    reraise=True,
)
async def _get_replica_set_status(probe_client: AsyncMongoClient) -> dict[str, Any]:
    return await probe_client.admin.command("replSetGetStatus")


@retry(
    stop=stop_after_attempt(30),
    wait=wait_fixed(1),
    retry=retry_if_result(_is_not_primary),
    sleep=_sleep,
    retry_error_callback=_raise_never_primary,
)
async def _poll_until_primary(probe_client: AsyncMongoClient) -> dict[str, Any]:
    return cast(dict[str, Any], await _get_replica_set_status(probe_client))


async def _ensure_replica_set_initiated(
    mongodb_url: str,
    *,
    replica_set_member_host: str | None = None,
) -> None:
    is_srv_or_multi_host = mongodb_url.startswith("mongodb+srv://") or mongodb_url.count(",") > 0
    # directConnection sidesteps the pre-initiation "RSGhost" state; Atlas/SRV don't need it.
    probe_client: AsyncMongoClient = AsyncMongoClient(
        mongodb_url,
        directConnection=not is_srv_or_multi_host,
    )
    try:
        await _wait_for_connectable(probe_client)
        try:
            await _get_replica_set_status(probe_client)
            return
        except OperationFailure as e:
            if e.code != _REPL_SET_NOT_YET_INITIALIZED:
                raise

        if replica_set_member_host is None:
            parsed = parse_uri(mongodb_url)
            node_host, node_port = parsed["nodelist"][0]
            replica_set_member_host = f"{node_host}:{node_port}"

        await probe_client.admin.command(
            "replSetInitiate",
            {"_id": "rs0", "members": [{"_id": 0, "host": replica_set_member_host}]},
        )
        await _poll_until_primary(probe_client)
        logger.info("Initiated single-node replica set for local MongoDB instance.")
    finally:
        # A pre-initiation handshake caches a stale session-support description, so it's never reused.
        await probe_client.close()


async def init_beanie_when_primary(
    database: AsyncDatabase,
    document_models: Sequence[type[Document]],
    *,
    max_attempts: int = 5,
    initial_delay: float = 0.25,
) -> None:
    # create_indexes isn't a retryable write, so a lingering not-primary window is retried directly.
    log = logger.bind(max_attempts=max_attempts)

    def _log_retry(retry_state: RetryCallState) -> None:
        error = retry_state.outcome.exception() if retry_state.outcome else None
        log.warn(
            "Beanie initialization hit a transient not-primary window, retrying.",
            attempt=retry_state.attempt_number,
            error=str(error),
        )

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=initial_delay, exp_base=2),
        retry=retry_if_exception_type(AutoReconnect),
        sleep=_sleep,
        before_sleep=_log_retry,
        reraise=True,
    )
    async def _init_beanie() -> None:
        await init_beanie(database=database, document_models=document_models)

    try:
        await _init_beanie()
    except AutoReconnect as e:
        log.error("Beanie initialization never reached a writable primary.", error=str(e))
        raise


async def bootstrap_beanie(
    mongodb_url: str,
    database: AsyncDatabase,
    document_models: Sequence[type[Document]],
    *,
    replica_set_member_host: str | None = None,
) -> None:
    await _ensure_replica_set_initiated(mongodb_url, replica_set_member_host=replica_set_member_host)
    await init_beanie_when_primary(database, document_models)
