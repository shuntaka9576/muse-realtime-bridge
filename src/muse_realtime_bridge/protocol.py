"""A deliberately small subset of Realtime client events for a PTT device."""

import base64
import binascii
import json
import re
import time
from dataclasses import dataclass, field

RATE = 24000
BYTES_PER_SECOND = RATE * 2
MAX_MESSAGE = 16 * 1024
MAX_AUDIO_CHUNK = 9600  # 200 ms PCM16 mono; 40 ms chunks are recommended.
MAX_TURN_BYTES = BYTES_PER_SECOND * 60


class ProtocolError(Exception):
    """Safe, fixed diagnostic code. Never includes the incoming payload."""


@dataclass
class InputState:
    buffered_bytes: int = 0
    committed: bool = False
    response_pending: bool = False
    # Audio sent to the device, used to bound the device's playback report.
    audio_items: dict[str, int] = field(default_factory=dict)
    audio_credit: float = BYTES_PER_SECOND * 2
    event_credit: float = 100
    last_tick: float = field(default_factory=time.monotonic)

    def accept(self, raw: str | bytes) -> dict:
        if not isinstance(raw, str):
            raise ProtocolError("text_json_required")
        now = time.monotonic()
        elapsed = now - self.last_tick
        self.last_tick = now
        self.audio_credit = min(
            BYTES_PER_SECOND * 2, self.audio_credit + elapsed * BYTES_PER_SECOND
        )
        self.event_credit = min(100, self.event_credit + elapsed * 100)
        self.event_credit -= 1
        if self.event_credit < 0:
            raise ProtocolError("event_rate_exceeded")
        try:
            event = json.loads(raw)
        except (ValueError, RecursionError):
            raise ProtocolError("invalid_json") from None
        if not isinstance(event, dict):
            raise ProtocolError("object_required")
        kind = event.get("type")
        fields = {
            "input_audio_buffer.append": {"audio"},
            "input_audio_buffer.commit": set(),
            "input_audio_buffer.clear": set(),
            "response.create": set(),
            "response.cancel": set(),
            "conversation.item.truncate": {"item_id", "content_index", "audio_end_ms"},
        }
        if not isinstance(kind, str) or kind not in fields:
            raise ProtocolError("unsupported_event")
        if set(event) != {"type"} | fields[kind]:
            raise ProtocolError("invalid_fields")
        if kind == "input_audio_buffer.append":
            audio = event["audio"]
            if not isinstance(audio, str):
                raise ProtocolError("invalid_audio")
            try:
                pcm = base64.b64decode(audio, validate=True)
            except (ValueError, binascii.Error):
                raise ProtocolError("invalid_audio") from None
            if not pcm or len(pcm) % 2 or len(pcm) > MAX_AUDIO_CHUNK:
                raise ProtocolError("invalid_audio_size")
            self.audio_credit -= len(pcm)
            if self.audio_credit < 0:
                raise ProtocolError("audio_rate_exceeded")
            self.buffered_bytes += len(pcm)
            if self.buffered_bytes > MAX_TURN_BYTES:
                raise ProtocolError("turn_too_long")
        elif kind == "input_audio_buffer.commit":
            if self.buffered_bytes < BYTES_PER_SECOND // 10:
                raise ProtocolError("audio_too_short")
            if self.committed:
                raise ProtocolError("response_required")
            self.buffered_bytes = 0
            self.committed = True
        elif kind == "input_audio_buffer.clear":
            self.buffered_bytes = 0
        elif kind == "response.create":
            if self.response_pending:
                raise ProtocolError("response_still_pending")
            if not self.committed:
                raise ProtocolError("audio_commit_required")
            self.committed = False
            self.response_pending = True
        elif kind == "conversation.item.truncate":
            item = event["item_id"]
            ms = event["audio_end_ms"]
            index = event["content_index"]
            if (
                not isinstance(item, str)
                or not re.fullmatch(r"[\w-]{1,128}", item)
                or item not in self.audio_items
                or type(ms) is not int
                or type(index) is not int
                or index != 0
                or not 0 <= ms <= self.audio_items[item] * 1000 // BYTES_PER_SECOND
            ):
                raise ProtocolError("invalid_playback_position")
            del self.audio_items[item]
        return event

    def observe(self, event: dict):
        if event["type"] == "response.done":
            self.response_pending = False
        elif event["type"] == "response.output_audio.delta":
            item = event["item_id"]
            self.audio_items[item] = self.audio_items.get(item, 0) + len(
                base64.b64decode(event["delta"], validate=True)
            )
            while len(self.audio_items) > 16:
                del self.audio_items[next(iter(self.audio_items))]
