import base64
import json

import pytest

from muse_realtime_bridge.config import Config
from muse_realtime_bridge.protocol import MAX_TURN_BYTES, InputState, ProtocolError


def append(state, pcm):
    return state.accept(
        json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode()})
    )


@pytest.mark.parametrize("pcm", [b"", b"x", bytes(9602)])
def test_audio_requires_bounded_pcm16(pcm):
    with pytest.raises(ProtocolError, match="invalid_audio_size"):
        append(InputState(), pcm)


def test_audio_rate_is_limited():
    state = InputState()
    with pytest.raises(ProtocolError, match="audio_rate_exceeded"):
        for _ in range(12):
            append(state, bytes(9600))


def test_turn_length_limit():
    state = InputState(buffered_bytes=MAX_TURN_BYTES)
    with pytest.raises(ProtocolError, match="turn_too_long"):
        append(state, bytes(1920))


@pytest.mark.parametrize("payload", [b"binary", "{", "[]", "null"])
def test_bad_messages(payload):
    with pytest.raises(ProtocolError):
        InputState().accept(payload)


def test_event_rate_limit():
    state = InputState()
    with pytest.raises(ProtocolError, match="event_rate_exceeded"):
        for _ in range(110):
            state.accept('{"type":"input_audio_buffer.clear"}')


def test_config_keeps_openai_credential_private():
    with pytest.raises(ValueError):
        Config("replace-placeholder")
    assert "sensitive" not in repr(Config("sensitive-openai-key"))


def test_server_is_always_loopback_only():
    assert Config().host == "127.0.0.1"
    assert Config(host="::1")
    for host in ["0.0.0.0", "::", "example.com", "localhost"]:
        with pytest.raises(ValueError, match="loopback"):
            Config(host=host)
