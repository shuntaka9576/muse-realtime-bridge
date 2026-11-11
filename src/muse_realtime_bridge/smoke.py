"""Native device emulator: send one PCM WAV turn and save the audio response."""

import argparse
import asyncio
import base64
import json
import os
import wave
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from websockets.asyncio.client import connect


async def exchange(url, token, input_path=None, output_path=None):
    parts = urlsplit(url)
    if parts.scheme not in {"ws", "wss"} or parts.path != "/realtime" or parts.query:
        raise ValueError("Use ws(s)://host:port/realtime without query parameters")
    if parts.scheme == "ws" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Use wss:// outside localhost")
    if not token and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Direct remote access requires BRIDGE_TOKEN")
    pcm = None
    if input_path:
        with wave.open(str(input_path), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (
                1,
                2,
                24000,
            ):
                raise ValueError("Input must be 24 kHz mono PCM16 WAV")
            if not 2400 <= source.getnframes() <= 24000 * 60:
                raise ValueError("Input duration must be between 100 ms and 60 seconds")
            pcm = source.readframes(source.getnframes())
        if output_path.exists():
            raise ValueError("Output already exists; choose a new path")

    async with asyncio.timeout(120):
        async with connect(
            url,
            additional_headers={"Authorization": f"Bearer {token}"} if token else {},
            max_size=1024 * 1024,
            max_queue=8,
            open_timeout=20,
            close_timeout=2,
            compression=None,
            proxy=None,
        ) as ws:
            ready = json.loads(await ws.recv())
            if ready.get("type") != "bridge.ready":
                raise RuntimeError("Bridge did not become ready")
            if pcm is None:
                print("bridge.ready: OpenAI session configured successfully")
                return

            async def upload():
                for offset in range(0, len(pcm), 1920):
                    await ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": base64.b64encode(pcm[offset : offset + 1920]).decode(),
                            }
                        )
                    )
                    await asyncio.sleep(0.04)
                await ws.send('{"type":"input_audio_buffer.commit"}')
                await ws.send('{"type":"response.create"}')

            task = asyncio.create_task(upload())
            try:
                # Exclusive create prevents accidental replacement of another recording.
                with output_path.open("xb") as file, wave.open(file, "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(24000)
                    audio_bytes = 0
                    async for raw in ws:
                        event = json.loads(raw)
                        if event["type"] == "bridge.error":
                            raise RuntimeError("Bridge error: " + event["code"])
                        if event["type"] == "response.output_audio.delta":
                            chunk = base64.b64decode(event["delta"], validate=True)
                            audio_bytes += len(chunk)
                            if audio_bytes > 48000 * 120:
                                raise RuntimeError("Reply audio exceeds 120 seconds")
                            output.writeframesraw(chunk)
                        if event["type"] == "response.done":
                            if event["response"]["status"] != "completed" or not audio_bytes:
                                raise RuntimeError("Response did not complete with audio")
                            await task
                            print(f"Saved response: {output_path} ({audio_bytes // 48} ms)")
                            return
                    raise RuntimeError("Connection closed before response.done")
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--url", default="ws://127.0.0.1:8787/realtime")
    parser.add_argument("--input", type=Path, help="24 kHz mono PCM16 WAV; omit for handshake only")
    parser.add_argument("--output", type=Path, default=Path("reply.wav"))
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    try:
        asyncio.run(exchange(args.url, os.environ.get("BRIDGE_TOKEN", ""), args.input, args.output))
    except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
