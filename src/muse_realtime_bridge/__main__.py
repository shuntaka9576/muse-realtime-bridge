import argparse
import asyncio
import logging
import signal
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from openai import AsyncOpenAI

from .config import Config
from .server import Bridge


async def run(config):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    async with AsyncExitStack() as stack:
        client = None
        if config.openai_api_key:
            # Do not inherit OPENAI_BASE_URL from the environment.
            client = await stack.enter_async_context(
                AsyncOpenAI(
                    api_key=config.openai_api_key,
                    base_url="https://api.openai.com/v1",
                    max_retries=0,
                )
            )
        async with Bridge(config, client).serve():
            logging.getLogger("muse_realtime_bridge").info(
                "listening host=%s port=%d model=%s", config.host, config.port, config.model
            )
            await stop.wait()


def main():
    parser = argparse.ArgumentParser(description="Muse Realtime Bridge")
    parser.add_argument("--env-file", help="Explicit dotenv file (existing environment wins)")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    try:
        config = Config.from_env()
    except ValueError as exc:
        parser.error(str(exc))
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    # OPENAI_LOG may otherwise enable SDK debug logs containing event payloads.
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("muse_realtime_bridge").setLevel(logging.INFO)
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
