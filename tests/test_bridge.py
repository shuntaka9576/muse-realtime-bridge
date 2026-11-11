import asyncio
import base64
import json
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest
from openai import AsyncOpenAI
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed, InvalidStatus

from muse_realtime_bridge.config import Config
from muse_realtime_bridge.server import Bridge

KEY = "test-upstream-key-never-forward"
PCM = base64.b64encode(bytes(1920)).decode()


class FakeOpenAI:
    def __init__(self, ready=True):
        self.ready = ready
        self.events = asyncio.Queue()
        self.connected = asyncio.Event()
        self.closed = asyncio.Event()
        self.connections = 0

    async def handle(self, socket):
        self.connections += 1
        self.socket = socket
        self.headers = socket.request.headers
        self.path = socket.request.path
        self.connected.set()
        try:
            async for raw in socket:
                event = json.loads(raw)
                await self.events.put(event)
                if event["type"] == "session.update" and self.ready:
                    await self.emit("session.created", session={"id": "session_test"})
                    await self.emit("session.updated", session=event["session"])
        except ConnectionClosed:
            pass
        finally:
            self.closed.set()

    async def emit(self, kind, **fields):
        await self.socket.send(json.dumps({"type": kind, "event_id": "event_test", **fields}))

    async def next(self):
        return await asyncio.wait_for(self.events.get(), 2)


@asynccontextmanager
async def running(*, ready=True, **overrides):
    fake = FakeOpenAI(ready)
    async with serve(fake.handle, "127.0.0.1", 0) as upstream:
        port = upstream.sockets[0].getsockname()[1]
        async with AsyncOpenAI(api_key=KEY, base_url=f"http://127.0.0.1:{port}/v1") as client:
            cfg = replace(Config(KEY, port=0), **overrides)
            bridge = Bridge(cfg, client)
            async with bridge.serve() as server:
                port = server.sockets[0].getsockname()[1]
                yield f"ws://127.0.0.1:{port}", bridge, fake


def device(url, **kwargs):
    return connect(
        url + "/realtime",
        proxy=None,
        **kwargs,
    )


async def recv(ws):
    return json.loads(await asyncio.wait_for(ws.recv(), 2))


async def send(ws, kind, **fields):
    await ws.send(json.dumps({"type": kind, **fields}))


async def turn(ws):
    for _ in range(3):
        await send(ws, "input_audio_buffer.append", audio=PCM)
    await send(ws, "input_audio_buffer.commit")
    await send(ws, "response.create")


async def test_origin_health_and_paths_do_not_connect_upstream():
    async with running() as (url, _, fake):
        async with httpx.AsyncClient() as client:
            response = await client.get(url.replace("ws:", "http:") + "/healthz")
            assert response.status_code == 200
        for path in ["/realtime?token=unused", "/voice/realtime"]:
            with pytest.raises(InvalidStatus) as exc:
                async with connect(url + path, proxy=None):
                    pass
            assert exc.value.response.status_code == 404
        with pytest.raises(InvalidStatus) as exc:
            async with device(url, origin="https://untrusted.example"):
                pass
        assert exc.value.response.status_code == 403
        assert fake.connections == 0


async def test_sdk_session_and_bidirectional_audio():
    async with running() as (url, _, fake):
        async with device(url) as ws:
            ready = await recv(ws)
            assert ready["type"] == "bridge.ready"
            assert KEY not in json.dumps(ready)
            session = (await fake.next())["session"]
            assert session["audio"]["input"]["turn_detection"] is None
            assert session["audio"]["output"]["format"]["rate"] == 24000
            assert session["tools"] == []
            assert fake.headers["Authorization"] == f"Bearer {KEY}"
            assert "model=gpt-realtime" in fake.path
            await turn(ws)
            events = [await fake.next() for _ in range(5)]
            assert [e["type"] for e in events] == ["input_audio_buffer.append"] * 3 + [
                "input_audio_buffer.commit",
                "response.create",
            ]
            assert events[0]["audio"] == PCM
            await fake.emit("response.created", response={"id": "resp_1"})
            await fake.emit(
                "response.output_audio.delta",
                response_id="resp_1",
                item_id="item_1",
                output_index=0,
                content_index=0,
                delta=PCM,
            )
            await fake.emit("response.done", response={"id": "resp_1", "status": "completed"})
            assert (await recv(ws))["type"] == "response.created"
            assert (await recv(ws))["delta"] == PCM
            assert (await recv(ws))["response"]["status"] == "completed"
        await asyncio.wait_for(fake.closed.wait(), 2)


@pytest.mark.parametrize(
    "event,code",
    [
        ({"type": "session.update", "session": {"instructions": "override"}}, "unsupported_event"),
        ({"type": "response.create", "response": {"instructions": "override"}}, "invalid_fields"),
        ({"type": "response.create"}, "audio_commit_required"),
        ({"type": "input_audio_buffer.append", "audio": "!!"}, "invalid_audio"),
        ({"type": "input_audio_buffer.commit"}, "audio_too_short"),
        (
            {
                "type": "conversation.item.truncate",
                "item_id": "unknown",
                "content_index": 0,
                "audio_end_ms": 1,
            },
            "invalid_playback_position",
        ),
        ({"type": []}, "unsupported_event"),
    ],
)
async def test_reject_invalid_events(event, code):
    async with running() as (url, _, fake):
        async with device(url) as ws:
            await recv(ws)
            await fake.next()
            await ws.send(json.dumps(event))
            assert await recv(ws) == {"type": "bridge.error", "code": code}
        await asyncio.wait_for(fake.closed.wait(), 2)
        assert fake.events.empty()


async def test_cancel_truncate_and_next_turn():
    async with running() as (url, _, fake):
        async with device(url) as ws:
            await recv(ws)
            await fake.next()
            await turn(ws)
            for _ in range(5):
                await fake.next()
            await fake.emit(
                "response.output_audio.delta",
                response_id="resp_1",
                item_id="item_1",
                output_index=0,
                content_index=0,
                delta=PCM,
            )
            await recv(ws)
            await send(ws, "response.cancel")
            await send(
                ws, "conversation.item.truncate", item_id="item_1", content_index=0, audio_end_ms=20
            )
            assert (await fake.next())["type"] == "response.cancel"
            assert (await fake.next())["audio_end_ms"] == 20
            await fake.emit("response.done", response={"id": "resp_1", "status": "cancelled"})
            await recv(ws)
            await turn(ws)
            assert [(await fake.next())["type"] for _ in range(5)][-1] == "response.create"


async def test_connection_limit_and_disconnect_releases_slot():
    async with running() as (url, bridge, fake):
        async with device(url) as first:
            await recv(first)
            async with device(url) as second:
                with pytest.raises(ConnectionClosed) as exc:
                    await second.recv()
                assert exc.value.rcvd.code == 1013
            assert fake.connections == 1
        await asyncio.wait_for(fake.closed.wait(), 2)
        async with asyncio.timeout(2):
            while bridge.active:  # noqa: ASYNC110 - observes server cleanup completion
                await asyncio.sleep(0.01)
        async with device(url) as third:
            assert (await recv(third))["type"] == "bridge.ready"


async def test_disconnect_during_startup_closes_upstream():
    async with running(ready=False) as (url, _, fake):
        async with device(url):
            await asyncio.wait_for(fake.connected.wait(), 2)
        await asyncio.wait_for(fake.closed.wait(), 2)


@pytest.mark.parametrize(
    "overrides,ready,code",
    [
        ({"connect_seconds": 0.1}, False, "session_timeout"),
        ({"idle_seconds": 0.1}, True, "input_idle_timeout"),
        ({"session_seconds": 0.2}, True, "session_timeout"),
    ],
)
async def test_timeouts_close_both_sides(overrides, ready, code):
    async with running(ready=ready, **overrides) as (url, _, fake):
        async with device(url) as ws:
            if ready:
                await recv(ws)
            assert (await recv(ws))["code"] == code
        await asyncio.wait_for(fake.closed.wait(), 2)


async def test_upstream_errors_do_not_leak_payloads():
    async with running() as (url, _, fake):
        async with device(url) as ws:
            await recv(ws)
            await fake.emit("error", error={"type": "invalid_request_error", "message": KEY})
            event = await recv(ws)
            assert event == {"type": "bridge.error", "code": "upstream_event_rejected"}
            assert KEY not in json.dumps(event)


async def test_oversize_device_message_closes_connection():
    async with running() as (url, _, fake):
        async with device(url) as ws:
            await recv(ws)
            await ws.send("x" * 17000)
            with pytest.raises(ConnectionClosed) as exc:
                await ws.recv()
            assert exc.value.rcvd.code == 1009
        await asyncio.wait_for(fake.closed.wait(), 2)


async def test_large_output_audio_is_split_without_loss():
    pcm = bytes(range(256)) * 24
    async with running() as (url, _, fake):
        async with device(url) as ws:
            await recv(ws)
            await fake.emit(
                "response.output_audio.delta",
                response_id="resp_1",
                item_id="item_1",
                output_index=0,
                content_index=0,
                delta=base64.b64encode(pcm).decode(),
            )
            events = [await recv(ws) for _ in range(4)]
            chunks = [base64.b64decode(e["delta"]) for e in events]
            assert b"".join(chunks) == pcm
            assert all(len(chunk) <= 1920 for chunk in chunks)
            assert len({e["event_id"] for e in events}) == 4


async def test_smoke_wav_round_trip(tmp_path):
    import wave

    from muse_realtime_bridge.smoke import exchange

    source = tmp_path / "input.wav"
    reply = tmp_path / "reply.wav"
    with wave.open(str(source), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(bytes(5760))
    async with running() as (url, _, fake):
        task = asyncio.create_task(exchange(url + "/realtime", source, reply))
        try:
            events = [await fake.next() for _ in range(6)]
            assert events[-1]["type"] == "response.create"
            await fake.emit(
                "response.output_audio.delta",
                response_id="resp_1",
                item_id="item_1",
                output_index=0,
                content_index=0,
                delta=PCM,
            )
            await fake.emit("response.done", response={"id": "resp_1", "status": "completed"})
            await asyncio.wait_for(task, 2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    with wave.open(str(reply), "rb") as wav:
        assert wav.getframerate() == 24000
        assert wav.getnchannels() == 1
        assert wav.readframes(1000) == base64.b64decode(PCM)


async def test_smoke_handshake_closes_session():
    from muse_realtime_bridge.smoke import exchange

    async with running() as (url, _, fake):
        await exchange(url + "/realtime")
        await asyncio.wait_for(fake.closed.wait(), 2)


async def test_upstream_close_after_ready_notifies_device():
    async with running() as (url, _, fake):
        async with device(url) as ws:
            await recv(ws)
            await fake.socket.close()
            assert (await recv(ws))["code"] == "upstream_closed"


async def test_echo_and_audio_share_one_server():
    async with running() as (url, _, fake):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url.replace("ws:", "http:") + "/probe/echo?nonce=" + "a" * 32
            )
            assert response.json() == {"server": "muse-vm-probe", "nonce": "a" * 32}
        assert fake.connections == 0
        async with connect(url + "/realtime", proxy=None) as ws:
            assert (await recv(ws))["type"] == "bridge.ready"
            await fake.next()  # session.update
            await turn(ws)
            for _ in range(5):
                await fake.next()  # three appends, commit, response.create
            await fake.emit(
                "response.output_audio.delta",
                delta=PCM,
                item_id="echo_audio",
                response_id="response_test",
                content_index=0,
            )
            assert (await recv(ws))["delta"] == PCM
        assert fake.connections == 1
