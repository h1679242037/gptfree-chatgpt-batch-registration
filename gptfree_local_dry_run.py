#!/usr/bin/env python3
"""Local dry-run for gptfree environment.

No ChatGPT registration, no HeroSMS getNumber, no phone purchase.
Prints only masked/non-secret values.
"""
import argparse
import json
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request

from cloud_mail_local import (
    create_cloud_mail_address,
    get_cloud_mail_config,
    get_cloud_mail_messages,
    get_cloud_mail_token,
    mask_value,
)


def ok(name, detail=""):
    print(f"OK   {name}{': ' + detail if detail else ''}")


def warn(name, detail=""):
    print(f"WARN {name}{': ' + detail if detail else ''}")


def fail(name, detail=""):
    print(f"FAIL {name}{': ' + detail if detail else ''}")


def tcp_check(host, port, timeout=2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-mail", action="store_true", help="create one dry-run Cloud Mail address")
    args = parser.parse_args()

    chrome = shutil.which("google-chrome") or "/usr/bin/google-chrome"
    if shutil.which("google-chrome") or shutil.which("/usr/bin/google-chrome") or shutil.which("chrome"):
        ok("chrome", chrome)
    elif subprocess.run(["test", "-x", chrome]).returncode == 0:
        ok("chrome", chrome)
    else:
        warn("chrome", f"not executable at {chrome}")

    if tcp_check("127.0.0.1", 7890):
        ok("proxy", "127.0.0.1:7890 listening")
    else:
        warn("proxy", "127.0.0.1:7890 not listening")

    try:
        data = http_json("http://127.0.0.1:9090/proxies")
        ok("mihomo", f"127.0.0.1:9090 /proxies keys={len(data) if isinstance(data, dict) else 'n/a'}")
    except Exception as exc:
        warn("mihomo", str(exc)[:160])

    try:
        config = get_cloud_mail_config()
        safe = {
            "base_url": config.get("base_url"),
            "domain": config.get("domain"),
            "admin_email": mask_value(config.get("admin_email")),
            "admin_password": "***" if config.get("admin_password") else "<empty>",
        }
        ok("cloud-mail-env", json.dumps(safe, ensure_ascii=False))
    except Exception as exc:
        fail("cloud-mail-env", str(exc)[:200])
        return 2

    try:
        token = get_cloud_mail_token(config)
        ok("cloud-mail-token", mask_value(token))
    except Exception as exc:
        fail("cloud-mail-token", str(exc)[:200])
        return 3

    if args.create_mail:
        try:
            address = create_cloud_mail_address(config=config, token=token)
            ok("cloud-mail-create", address)
            messages = get_cloud_mail_messages(address, config=config, token=token, size=3)
            ok("cloud-mail-emailList", f"{len(messages)} messages")
        except Exception as exc:
            fail("cloud-mail-create/emailList", str(exc)[:200])
            return 4
    else:
        ok("cloud-mail-create", "skipped (pass --create-mail to create a test inbox)")

    ok("safety", "dry-run only; did not buy phone number or register ChatGPT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
