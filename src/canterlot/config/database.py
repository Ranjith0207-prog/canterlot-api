import asyncio

from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure
from pymongo.uri_parser import parse_uri

from canterlot.models import BEANIE_DOCUMENT_MODELS
from canterlot.utils import get_logger

from .settings import get_settings

logger = get_logger(__name__)

_REPL_SET_NOT_YET_INITIALIZED = 94


async def _ensure_replica_set_initiated(mongodb_url: str) -> None:
    """No-op against an already-initiated replica set, e.g. any MongoDB Atlas cluster."""

    is_srv_or_multi_host = mongodb_url.startswith("mongodb+srv://") or mongodb_url.count(",") > 0
    # directConnection: a pre-initiation node reports as "RSGhost", which a normal
    # discovery-mode client refuses to route commands to. Skipped for Atlas/SRV URLs,
    # which reject the option and are always already initiated anyway.
    probe_client: AsyncMongoClient = AsyncMongoClient(
        mongodb_url,
        directConnection=not is_srv_or_multi_host,
    )
    try:
        try:
            await probe_client.admin.command("replSetGetStatus")
            return
        except OperationFailure as e:
            if e.code != _REPL_SET_NOT_YET_INITIALIZED:
                return

        parsed = parse_uri(mongodb_url)
        node_host, node_port = parsed["nodelist"][0]
        await probe_client.admin.command(
            "replSetInitiate",
            {"_id": "rs0", "members": [{"_id": 0, "host": f"{node_host}:{node_port}"}]},
        )
        for _ in range(30):
            status = await probe_client.admin.command("replSetGetStatus")
            if status["members"][0]["stateStr"] == "PRIMARY":
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("mongod replica set never reached PRIMARY state")
        logger.info("Initiated single-node replica set for local MongoDB instance.")
    finally:
        # Never reused as the app's client: a pre-initiation handshake keeps a stale
        # session-support description even after the replica set becomes healthy.
        await probe_client.close()


class DatabaseManager:
    def __init__(self) -> None:
        self.__client: AsyncMongoClient | None = None
        self.__database: AsyncDatabase | None = None

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def open(self):
        settings = get_settings().db
        mongodb_url = settings.mongodb_url.get_secret_value()

        await _ensure_replica_set_initiated(mongodb_url)

        self.__client = AsyncMongoClient(
            mongodb_url,
            maxPoolSize=10,
            minPoolSize=2,
            tz_aware=True,
        )
        self.__database = self.__client[settings.mongodb_db_name]

        await init_beanie(database=self.__database, document_models=BEANIE_DOCUMENT_MODELS)
        logger.info("Connected to MongoDB pool.")

    async def reinitialize_beanie(self) -> None:
        if self.__database is None:
            raise RuntimeError("DatabaseManager is not open.")

        await init_beanie(database=self.__database, document_models=BEANIE_DOCUMENT_MODELS)
        logger.info("Beanie reinitialized.")

    async def close(self):
        if self.__client:
            await self.__client.close()
            logger.info("Closed MongoDB connections.")
