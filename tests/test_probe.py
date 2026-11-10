import asyncio
import importlib.util
import json
import threading
import urllib.request
from pathlib import Path

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(
        f"probe_{name}", Path(__file__).parents[1] / "probe" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_echo():
    module = load("server")
    server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        nonce = "a" * 32
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/probe/echo",
            json.dumps({"nonce": nonce}).encode(), {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            assert json.load(response) == {"server": "muse-vm-probe", "nonce": nonce}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("matches", [True, False])
async def test_noise_probe_response_and_cleanup(matches):
    pytest.importorskip("musegadget")
    client = load("client")

    class Session:
        stopped = False

        async def run(self, stop):
            await stop.wait()
            self.stopped = True

        async def wait_transport_ready(self, **kwargs):
            await asyncio.sleep(0)

        async def request(self, method, path, body, **kwargs):
            assert method == "POST" and path == "/probe/echo"
            return {"ok": matches, "status": 200 if matches else 404,
                    "response": {"server": "muse-vm-probe", **json.loads(body)}}

    session = Session()
    assert await client.probe(session, "/probe/echo") is matches
    assert session.stopped


def test_fetch_flow_keeps_vm_token_private(monkeypatch, capsys):
    pytest.importorskip("musegadget")
    client = load("client")
    monkeypatch.setattr("sys.argv", ["client.py", "--fetch-only"])
    monkeypatch.setattr(client.getpass, "getpass", lambda _: "test-access-secret")

    def fetch(token, root):
        assert token == "test-access-secret"
        assert root == "https://api.muse.ai"
        return [{"vm_id": "test-vm", "vm_auth_token": "test-vm-secret"}], 200

    monkeypatch.setattr(client, "fetch_vms_with_status", fetch)
    assert client.main() == 0
    output = capsys.readouterr().out
    assert "test-access-secret" not in output and "test-vm-secret" not in output
    assert "VM token acquired" in output
    # main() suppresses SDK logs for its CLI lifetime, not other tests.
    client.logging.disable(client.logging.NOTSET)


def test_account_host_is_restricted():
    pytest.importorskip("musegadget")
    client = load("client")
    with pytest.raises(ValueError):
        client.fetch_vms_with_status("fixture-secret", "https://untrusted.invalid")


def test_hidden_input_failure_stops_before_fetch(monkeypatch, capsys):
    pytest.importorskip("musegadget")
    client = load("client")
    monkeypatch.setattr("sys.argv", ["client.py", "--fetch-only"])

    def unavailable(_prompt):
        client.warnings.warn("fixture-secret", client.getpass.GetPassWarning, stacklevel=1)
        raise AssertionError("Must not fall back to visible input")

    monkeypatch.setattr(client.getpass, "getpass", unavailable)
    assert client.main() == 1
    assert "fixture-secret" not in capsys.readouterr().out
    client.logging.disable(client.logging.NOTSET)


def test_http_redirect_does_not_forward_credentials():
    pytest.importorskip("musegadget")
    client = load("client")
    module = load("server")
    paths = []

    class Redirect(module.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            paths.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/credential-leak")
            self.end_headers()

    server = module.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/fetch_vms",
            headers={"Authorization": "Bearer fixture-secret"},
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.build_opener(client.NoRedirect()).open(req, timeout=2)
        assert error.value.code == 302
        error.value.close()
        assert paths == ["/fetch_vms"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def test_websocket_redirect_does_not_forward_credentials():
    pytest.importorskip("musegadget")
    from http import HTTPStatus

    from websockets.asyncio.server import serve
    from websockets.exceptions import InvalidStatus

    client = load("client")
    paths = []

    def redirect(connection, request):
        paths.append(request.path)
        response = connection.respond(HTTPStatus.FOUND, "redirect")
        response.headers["Location"] = "/credential-leak"
        return response

    async def unused(connection):
        pass

    async with serve(unused, "127.0.0.1", 0, process_request=redirect) as server:
        port = server.sockets[0].getsockname()[1]
        with pytest.raises(InvalidStatus):
            async with client.NoRedirectConnect(
                f"ws://127.0.0.1:{port}/noise",
                additional_headers={"Authorization": "Bearer fixture-secret"},
            ):
                pytest.fail("Redirect must not establish a connection")
        assert paths == ["/noise"]
