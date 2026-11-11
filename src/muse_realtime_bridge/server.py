import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
from contextlib import suppress
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from openai import AsyncOpenAI
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from .config import Config
from .protocol import MAX_MESSAGE, InputState, ProtocolError

log = logging.getLogger("muse_realtime_bridge")


class Bridge:
    def __init__(self, config: Config, client: AsyncOpenAI | None):
        self.config = config
        self.client = client
        self.active = 0
        self.token_hash = hashlib.sha256(config.bridge_token.encode()).digest()

    def process_request(self, connection, request):
        if request.path == "/healthz":
            return connection.respond(HTTPStatus.OK, '{"status":"ok"}\n')
        route = urlsplit(request.path)
        if route.path == "/probe/echo":
            query = parse_qs(route.query, keep_blank_values=True)
            nonce = query.get("nonce", [])
            if (
                set(query) != {"nonce"}
                or len(nonce) != 1
                or not re.fullmatch(r"[0-9a-f]{32}", nonce[0])
            ):
                return connection.respond(HTTPStatus.BAD_REQUEST, "Invalid nonce\n")
            return connection.respond(
                HTTPStatus.OK, json.dumps({"server": "muse-vm-probe", "nonce": nonce[0]}) + "\n"
            )
        if request.path != "/realtime":
            return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
        # This endpoint is for firmware/native clients, not arbitrary browser origins.
        if request.headers.get_all("Origin"):
            return connection.respond(HTTPStatus.FORBIDDEN, "Origin not allowed\n")
        if not self.config.bridge_token:
            # Config restricts this mode to loopback. Muse's ingress, not this
            # process, must authenticate remote callers before forwarding.
            if self.client is None:
                return connection.respond(HTTPStatus.SERVICE_UNAVAILABLE, "OpenAI not configured\n")
            return None
        headers = request.headers.get_all("Authorization")
        if len(headers) != 1 or not headers[0].startswith("Bearer "):
            return connection.respond(HTTPStatus.UNAUTHORIZED, "Unauthorized\n")
        candidate = hashlib.sha256(headers[0][7:].encode()).digest()
        if not hmac.compare_digest(candidate, self.token_hash):
            return connection.respond(HTTPStatus.UNAUTHORIZED, "Unauthorized\n")
        if self.client is None:
            return connection.respond(HTTPStatus.SERVICE_UNAVAILABLE, "OpenAI not configured\n")
        return None

    async def send(self, device, event):
        async with asyncio.timeout(self.config.send_seconds):
            await device.send(json.dumps(event, ensure_ascii=False, separators=(",", ":")))

    async def fail(self, device, code):
        with suppress(ConnectionClosed, TimeoutError):
            await self.send(device, {"type": "bridge.error", "code": code})
        await device.close(1011, code)

    async def handle(self, device: ServerConnection):
        if self.active >= self.config.max_connections:
            await device.close(1013, "bridge_busy")
            return
        self.active += 1
        session_id = uuid4().hex[:12]
        log.info("session=%s opened active=%d", session_id, self.active)
        worker = asyncio.create_task(self.run_session(device))
        disconnected = asyncio.create_task(device.wait_closed())
        try:
            async with asyncio.timeout(self.config.session_seconds):
                done, _ = await asyncio.wait(
                    [worker, disconnected], return_when=asyncio.FIRST_COMPLETED
                )
                if worker in done:
                    await worker
        except ProtocolError as exc:
            await self.fail(device, str(exc))
        except TimeoutError:
            await self.fail(device, "session_timeout")
        except ConnectionClosed:
            pass
        except Exception as exc:
            # SDK exceptions can contain credentials, headers or user data. Never log them.
            log.warning("session=%s failed class=%s", session_id, type(exc).__name__)
            await self.fail(device, "upstream_unavailable")
        finally:
            for task in (worker, disconnected):
                task.cancel()
            await asyncio.gather(worker, disconnected, return_exceptions=True)
            await device.close()
            self.active -= 1
            log.info("session=%s closed active=%d", session_id, self.active)

    async def run_session(self, device):
        cfg = self.config
        # Bound connection AND session.update acknowledgement, including a silent upstream.
        async with asyncio.timeout(cfg.connect_seconds) as startup:
            async with self.client.realtime.connect(
                model=cfg.model,
                websocket_connection_options={
                    "open_timeout": cfg.connect_seconds,
                    "close_timeout": 2,
                    "max_size": 1024 * 1024,
                    "max_queue": 8,
                    "write_limit": 32768,
                },
            ) as upstream:
                await upstream.session.update(
                    session={
                        "type": "realtime",
                        "instructions": cfg.instructions,
                        "output_modalities": ["audio"],
                        "tools": [],
                        "max_output_tokens": 1024,
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcm", "rate": 24000},
                                "turn_detection": None,
                            },
                            "output": {
                                "format": {"type": "audio/pcm", "rate": 24000},
                                "voice": cfg.voice,
                            },
                        },
                    }
                )
                async for event in upstream:
                    if event.type == "error":
                        raise ProtocolError("upstream_session_rejected")
                    if event.type == "session.updated":
                        break
                else:
                    raise ProtocolError("upstream_closed_before_ready")
                startup.reschedule(None)
                await self.send(
                    device,
                    {
                        "type": "bridge.ready",
                        "protocol_version": 1,
                        "audio": {"encoding": "pcm_s16le", "sample_rate": 24000, "channels": 1},
                    },
                )
                state = InputState()
                uploads = asyncio.create_task(self.upload(device, upstream, state))
                downloads = asyncio.create_task(self.download(device, upstream, state))
                try:
                    done, _ = await asyncio.wait(
                        [uploads, downloads], return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        await task
                finally:
                    for task in (uploads, downloads):
                        task.cancel()
                    await asyncio.gather(uploads, downloads, return_exceptions=True)

    async def upload(self, device, upstream, state):
        while True:
            try:
                async with asyncio.timeout(self.config.idle_seconds):
                    raw = await device.recv()
            except TimeoutError:
                raise ProtocolError("input_idle_timeout") from None
            event = state.accept(raw)
            # Cancel is idempotent from the device's perspective.
            if event["type"] == "response.cancel" and not state.response_pending:
                continue
            async with asyncio.timeout(self.config.send_seconds):
                await upstream.send(event)

    async def download(self, device, upstream, state):
        async for event in upstream:
            data = event.to_dict()
            if event.type == "error":
                raise ProtocolError("upstream_event_rejected")
            # Session settings stay server-side. The device cannot override them.
            if event.type in {"session.created", "session.updated", "rate_limits.updated"}:
                continue
            if event.type == "response.output_audio.delta":
                pcm = base64.b64decode(data["delta"], validate=True)
                if len(pcm) % 2:
                    raise ProtocolError("invalid_upstream_audio")
                # Keep firmware receive buffers small, even when the provider batches audio.
                for offset in range(0, len(pcm), 1920):
                    chunk = {
                        **data,
                        "delta": base64.b64encode(pcm[offset : offset + 1920]).decode(),
                        "event_id": f"{data['event_id']}_{offset // 1920}",
                    }
                    state.observe(chunk)
                    await self.send(device, chunk)
            else:
                state.observe(data)
                await self.send(device, data)
        raise ProtocolError("upstream_closed")

    def serve(self):
        return serve(
            self.handle,
            self.config.host,
            self.config.port,
            process_request=self.process_request,
            max_size=MAX_MESSAGE,
            max_queue=8,
            write_limit=32768,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=2,
            compression=None,
            server_header=None,
        )
