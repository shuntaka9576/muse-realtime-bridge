"""VM-local echo target. Muse's authenticated router must forward /probe/echo here."""

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class EchoHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.connection.settimeout(5)
        if self.path != "/probe/echo":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 256 or self.headers.get("Transfer-Encoding"):
                raise ValueError
            data = json.loads(self.rfile.read(length))
            nonce = data.get("nonce")
            if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", nonce):
                raise ValueError
        except (ValueError, AttributeError, OSError):
            self.send_error(400)
            return
        body = json.dumps({"server": "muse-vm-probe", "nonce": nonce}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print("echo received", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), EchoHandler) as server:
        print(f"Listening on http://127.0.0.1:{args.port}/probe/echo", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
