import httpx
import pytest

from muse_realtime_bridge.config import Config
from muse_realtime_bridge.server import Bridge


async def test_local_echo_without_openai():
    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus

    async with Bridge(Config(port=0), None).serve() as server:
        port = server.sockets[0].getsockname()[1]
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://127.0.0.1:{port}/probe/echo?nonce={'a' * 32}")
            assert response.json() == {"server": "muse-vm-probe", "nonce": "a" * 32}
            for query in ["", "?nonce=bad", f"?nonce={'a' * 32}&nonce={'b' * 32}"]:
                assert (
                    await client.get(f"http://127.0.0.1:{port}/probe/echo{query}")
                ).status_code == 400
        with pytest.raises(InvalidStatus) as error:
            async with connect(f"ws://127.0.0.1:{port}/realtime", proxy=None):
                pytest.fail("Missing OpenAI configuration must refuse audio")
        assert error.value.response.status_code == 503
