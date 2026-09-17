from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import AutoReconnect, NotPrimaryError, OperationFailure

from canterlot.config import bootstrap


class _FakeAdmin:
    def __init__(self, command: AsyncMock) -> None:
        self.command = command


class _FakeProbeClient:
    def __init__(self, command: AsyncMock) -> None:
        self.admin = _FakeAdmin(command)
        self.close = AsyncMock()


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr(bootstrap.asyncio, "sleep", sleep)
    return sleep


@pytest.fixture(autouse=True)
def _init_beanie(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(bootstrap, "init_beanie", mock)
    return mock


def _patch_probe_client(monkeypatch: pytest.MonkeyPatch, command: AsyncMock) -> MagicMock:
    constructor = MagicMock(return_value=_FakeProbeClient(command))
    monkeypatch.setattr(bootstrap, "AsyncMongoClient", constructor)
    return constructor


async def _bootstrap(**overrides: object) -> None:
    kwargs: dict[str, object] = {
        "mongodb_url": "mongodb://localhost:27017/",
        "database": MagicMock(),
        "document_models": [],
    }
    kwargs.update(overrides)
    await bootstrap.bootstrap_beanie(**kwargs)  # type: ignore[arg-type]


def describe_bootstrap_beanie():
    async def it_initializes_beanie_immediately_when_the_replica_set_is_already_ready(
        monkeypatch: pytest.MonkeyPatch,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(return_value={"ok": 1.0, "members": [{"stateStr": "PRIMARY"}]})
        constructor = _patch_probe_client(monkeypatch, command)

        await _bootstrap()

        assert command.await_count == 2
        assert command.await_args_list[-1].args == ("replSetGetStatus",)
        constructor.return_value.close.assert_awaited_once()
        _init_beanie.assert_awaited_once()

    async def it_reraises_unexpected_replica_set_status_errors_without_touching_beanie(
        monkeypatch: pytest.MonkeyPatch,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(side_effect=[{"ok": 1.0}, OperationFailure("unauthorized", code=13)])
        _patch_probe_client(monkeypatch, command)

        with pytest.raises(OperationFailure) as exc_info:
            await _bootstrap()

        assert exc_info.value.code == 13
        _init_beanie.assert_not_awaited()

    async def it_initiates_the_replica_set_and_waits_for_primary_before_initializing_beanie(
        monkeypatch: pytest.MonkeyPatch,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(
            side_effect=[
                {"ok": 1.0},
                OperationFailure("not yet initialized", code=94),
                {"ok": 1.0},
                {"members": [{"stateStr": "STARTUP"}]},
                {"members": [{"stateStr": "PRIMARY"}]},
            ],
        )
        _patch_probe_client(monkeypatch, command)

        await _bootstrap(replica_set_member_host="localhost:27017")

        initiate_call = command.await_args_list[2]
        assert initiate_call.args[0] == "replSetInitiate"
        assert initiate_call.args[1]["members"] == [{"_id": 0, "host": "localhost:27017"}]
        _init_beanie.assert_awaited_once()

    async def it_derives_the_member_host_from_the_url_when_not_given(
        monkeypatch: pytest.MonkeyPatch,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(
            side_effect=[
                {"ok": 1.0},
                OperationFailure("not yet initialized", code=94),
                {"ok": 1.0},
                {"members": [{"stateStr": "PRIMARY"}]},
            ],
        )
        _patch_probe_client(monkeypatch, command)

        await _bootstrap(mongodb_url="mongodb://mongo:27017/canterlot")

        initiate_call = command.await_args_list[2]
        assert initiate_call.args[1]["members"] == [{"_id": 0, "host": "mongo:27017"}]
        _init_beanie.assert_awaited_once()

    async def it_raises_when_the_replica_set_never_reaches_primary(
        monkeypatch: pytest.MonkeyPatch,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(
            side_effect=[
                {"ok": 1.0},
                OperationFailure("not yet initialized", code=94),
                {"ok": 1.0},
                *[{"members": [{"stateStr": "STARTUP"}]}] * 30,
            ],
        )
        _patch_probe_client(monkeypatch, command)

        with pytest.raises(RuntimeError, match="never reached PRIMARY"):
            await _bootstrap()

        _init_beanie.assert_not_awaited()

    async def it_closes_the_probe_connection_even_when_initiation_fails(monkeypatch: pytest.MonkeyPatch):
        command = AsyncMock(side_effect=[{"ok": 1.0}, OperationFailure("unauthorized", code=13)])
        constructor = _patch_probe_client(monkeypatch, command)

        with pytest.raises(OperationFailure):
            await _bootstrap()

        constructor.return_value.close.assert_awaited_once()

    async def it_skips_direct_connection_for_srv_urls(monkeypatch: pytest.MonkeyPatch):
        command = AsyncMock(return_value={"ok": 1.0, "members": [{"stateStr": "PRIMARY"}]})
        constructor = _patch_probe_client(monkeypatch, command)

        await _bootstrap(mongodb_url="mongodb+srv://cluster0.example.mongodb.net/canterlot")

        assert constructor.call_args.kwargs["directConnection"] is False

    async def it_uses_direct_connection_for_a_single_local_host(monkeypatch: pytest.MonkeyPatch):
        command = AsyncMock(return_value={"ok": 1.0, "members": [{"stateStr": "PRIMARY"}]})
        constructor = _patch_probe_client(monkeypatch, command)

        await _bootstrap()

        assert constructor.call_args.kwargs["directConnection"] is True

    async def it_waits_out_transient_connection_errors_before_checking_replica_set_status(
        monkeypatch: pytest.MonkeyPatch,
        _no_real_sleeping: AsyncMock,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(
            side_effect=[
                AutoReconnect("not up yet"),
                OperationFailure("still starting"),
                {"ok": 1.0},
                {"ok": 1.0, "members": [{"stateStr": "PRIMARY"}]},
            ],
        )
        _patch_probe_client(monkeypatch, command)

        await _bootstrap()

        assert command.await_count == 4
        assert _no_real_sleeping.await_count == 2
        _init_beanie.assert_awaited_once()

    async def it_retries_a_transient_connection_error_on_the_initial_status_check(
        monkeypatch: pytest.MonkeyPatch,
        _no_real_sleeping: AsyncMock,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(
            side_effect=[
                {"ok": 1.0},
                AutoReconnect("dropped"),
                {"ok": 1.0, "members": [{"stateStr": "PRIMARY"}]},
            ],
        )
        _patch_probe_client(monkeypatch, command)

        await _bootstrap()

        assert command.await_count == 3
        assert _no_real_sleeping.await_count == 1
        _init_beanie.assert_awaited_once()

    async def it_reraises_after_exhausting_status_check_retries(
        monkeypatch: pytest.MonkeyPatch,
        _no_real_sleeping: AsyncMock,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(side_effect=[{"ok": 1.0}, *[AutoReconnect("dropped")] * 5])
        _patch_probe_client(monkeypatch, command)

        with pytest.raises(AutoReconnect):
            await _bootstrap()

        assert command.await_count == 6
        _init_beanie.assert_not_awaited()

    async def it_retries_a_transient_connection_error_while_polling_for_primary(
        monkeypatch: pytest.MonkeyPatch,
        _no_real_sleeping: AsyncMock,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(
            side_effect=[
                {"ok": 1.0},
                OperationFailure("not yet initialized", code=94),
                {"ok": 1.0},
                AutoReconnect("dropped"),
                {"members": [{"stateStr": "PRIMARY"}]},
            ],
        )
        _patch_probe_client(monkeypatch, command)

        await _bootstrap()

        assert command.await_count == 5
        _init_beanie.assert_awaited_once()

    async def it_raises_when_mongod_never_becomes_connectable(
        monkeypatch: pytest.MonkeyPatch,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(side_effect=AutoReconnect("down"))
        _patch_probe_client(monkeypatch, command)

        with pytest.raises(RuntimeError, match="never became connectable"):
            await _bootstrap()

        assert command.await_count == 30
        _init_beanie.assert_not_awaited()

    async def it_retries_beanie_initialization_on_not_primary_until_it_succeeds(
        monkeypatch: pytest.MonkeyPatch,
        _no_real_sleeping: AsyncMock,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(return_value={"ok": 1.0, "members": [{"stateStr": "PRIMARY"}]})
        _patch_probe_client(monkeypatch, command)
        _init_beanie.side_effect = [NotPrimaryError("not primary"), NotPrimaryError("not primary"), None]

        await _bootstrap()

        assert _init_beanie.await_count == 3
        assert _no_real_sleeping.await_count == 2

    async def it_retries_beanie_initialization_on_autoreconnect_until_it_succeeds(
        monkeypatch: pytest.MonkeyPatch,
        _no_real_sleeping: AsyncMock,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(return_value={"ok": 1.0, "members": [{"stateStr": "PRIMARY"}]})
        _patch_probe_client(monkeypatch, command)
        _init_beanie.side_effect = [AutoReconnect("dropped"), None]

        await _bootstrap()

        assert _init_beanie.await_count == 2
        assert _no_real_sleeping.await_count == 1

    async def it_reraises_after_exhausting_beanie_initialization_retries(
        monkeypatch: pytest.MonkeyPatch,
        _no_real_sleeping: AsyncMock,
        _init_beanie: AsyncMock,
    ):
        command = AsyncMock(return_value={"ok": 1.0, "members": [{"stateStr": "PRIMARY"}]})
        _patch_probe_client(monkeypatch, command)
        _init_beanie.side_effect = NotPrimaryError("still not primary")

        with pytest.raises(NotPrimaryError):
            await _bootstrap()

        assert _init_beanie.await_count == 5
        assert _no_real_sleeping.await_count == 4

    async def it_ensures_the_replica_set_before_initializing_beanie(
        monkeypatch: pytest.MonkeyPatch,
        _init_beanie: AsyncMock,
    ):
        call_order: list[str] = []

        async def _tracked_command(*args: object, **_kwargs: object) -> dict[str, object]:
            if args[0] == "replSetGetStatus":
                call_order.append("replica_set_check")
            return {"ok": 1.0, "members": [{"stateStr": "PRIMARY"}]}

        _init_beanie.side_effect = lambda *_a, **_kw: call_order.append("init_beanie")
        command = AsyncMock(side_effect=_tracked_command)
        _patch_probe_client(monkeypatch, command)

        await _bootstrap()

        assert call_order == ["replica_set_check", "init_beanie"]
