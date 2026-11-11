"""Fetch a VM token with the Muse SDK, connect over Noise, then probe a custom route."""

import argparse
import asyncio
import getpass
import json
import logging
import secrets
import urllib.error
import urllib.request
import warnings
from pathlib import Path

from musegadget.link_client import DeviceDescription, LinkSession
from musegadget.muse_api import user_agent
from musegadget.noise import Header
from websockets.asyncio.client import connect


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class NoRedirectConnect(connect):
    def process_redirect(self, exc):
        return exc


async def connect_vm(url, headers):
    return await NoRedirectConnect(
        url,
        additional_headers=headers,
        user_agent_header=user_agent(),
        open_timeout=15,
        max_size=128 * 1024,
    )


def fetch_vms_with_status(token, root):
    # Match the SDK account request, but never forward credentials on redirects.
    if root != "https://api.muse.ai":
        raise ValueError("Only the Muse account API is supported by this probe")
    request = urllib.request.Request(
        root + "/fetch_vms",
        headers={
            "Authorization": f"Bearer {token}",
            "X-API-Version": "1.0.0",
            "User-Agent": user_agent(),
        },
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
            body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise ValueError("Account response too large")
            data = json.loads(body)
            return [
                {**vm, "is_default": bool(vm.get("default"))}
                for vm in data["vm_list"]
                if isinstance(vm, dict) and vm.get("vm_id") and vm.get("vm_auth_token")
            ], 200
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        return [], status


def select_vm(vms, vm_id):
    if vm_id:
        choices = [vm for vm in vms if vm["vm_id"] == vm_id]
    elif len(vms) == 1:
        choices = vms
    else:
        choices = [vm for vm in vms if vm["is_default"]]
    if len(choices) != 1:
        raise ValueError("Specify --vm-id to select exactly one VM")
    return choices[0]


async def probe(session, path):
    stop = asyncio.Event()
    task = asyncio.create_task(session.run(stop))
    try:
        await session.wait_transport_ready(timeout=20)
        print("Noise: authenticated connection ready")
        nonce = secrets.token_hex(16)
        result = await session.request(
            "GET",
            f"{path}?nonce={nonce}",
            headers=[Header("content-type", "application/json")],
            timeout=15,
        )
        print(f"Echo route: HTTP {result['status']}")
        if not result["ok"] or result["response"] != {
            "server": "muse-vm-probe",
            "nonce": nonce,
        }:
            print("Echo not confirmed. Check the VM router mapping and server log.")
            return False
        print("PASS: client -> Muse authentication/Noise -> VM-local echo -> client")
        return True
    finally:
        stop.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except TimeoutError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairing-file", type=Path, help="Existing SDK pairing.json (read only)")
    parser.add_argument("--vm-id", default="")
    parser.add_argument("--noise-host", help="Host only; defaults to SDK pairing data")
    parser.add_argument("--path", default="/probe/echo", help="Route configured in the VM router")
    parser.add_argument("--fetch-only", action="store_true", help="Only test VM token retrieval")
    args = parser.parse_args()
    # Never print SDK exceptions or server response bodies: they may contain credentials.
    logging.disable(logging.CRITICAL)
    try:
        pairing = json.loads(args.pairing_file.read_text()) if args.pairing_file else {}
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = pairing.get("access_token") or getpass.getpass("Muse access/device token: ")
        if not token:
            raise ValueError("Missing access token")
        root = pairing.get("api_url_v2") or "https://api.muse.ai"
        if not root.startswith("https://"):
            raise ValueError("Account API must use HTTPS")
        vms, status = fetch_vms_with_status(token, root.rstrip("/"))
        print(f"fetch_vms: HTTP {status}, {len(vms)} VM(s)")
        if status != 200 or not vms:
            print("VM token retrieval failed; check the initial credential and network.")
            return 1
        vm = select_vm(vms, args.vm_id)
        print("VM selected; VM token acquired (not displayed or saved)")
        if args.fetch_only:
            return 0
        host = args.noise_host or pairing.get("noise_host") or "hatch.metaaivm.com"
        if not args.noise_host and host != "hatch.metaaivm.com":
            raise ValueError("Use --noise-host explicitly for a custom host")
        if (
            any(c in host for c in "/@?#\\ \r\n")
            or not args.path.startswith("/")
            or "?" in args.path
            or "#" in args.path
        ):
            raise ValueError("Invalid host or path")
        session = LinkSession(
            noise_host=host,
            vm_id=vm["vm_id"],
            vm_auth_token=vm["vm_auth_token"],
            device=DeviceDescription("vm-probe", "VM probe", "0.1", {}),
            run_command=lambda *_args: {},
            register_device=False,
            connect=connect_vm,
        )
        return 0 if asyncio.run(probe(session, args.path)) else 1
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Probe stopped ({type(exc).__name__}); no credentials or raw response printed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
