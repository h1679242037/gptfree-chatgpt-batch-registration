#!/usr/bin/env python3
"""Dry-run the local Sub2API wiring for gptfree.

This script does not buy SMS numbers, start Chrome, register accounts, or print secrets.
It only loads local Sub2API admin credentials from ~/.gptfree/sub2api.env,
checks the service is reachable, and probes the login/auth-url functions.
"""
import os
import sys
from pathlib import Path

ENV_PATH = Path("~/.gptfree/sub2api.env")


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        raise FileNotFoundError(f"missing {path}")
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {"ADMIN_EMAIL", "ADMIN_PASSWORD"}:
            os.environ.setdefault(
                "GPTFREE_SUB2API_EMAIL" if key == "ADMIN_EMAIL" else "GPTFREE_SUB2API_PASS",
                value,
            )
    os.environ.setdefault("GPTFREE_SUB2API_URL", "http://127.0.0.1:8080")


def main() -> int:
    load_env()
    import batch_register_v2 as br

    print(f"Sub2API URL: {br.SUB2API}")
    print(f"Sub2API email: {'[set]' if br.SUB2API_EMAIL and 'YOUR_' not in br.SUB2API_EMAIL else '[missing]'}")
    print(f"Sub2API password: {'[set]' if br.SUB2API_PASS and 'YOUR_' not in br.SUB2API_PASS else '[missing]'}")

    try:
        token = br.sub2api_login()
    except Exception as exc:
        print(f"login: FAIL ({type(exc).__name__}: {str(exc)[:240]})")
        return 2
    print("login: OK (token redacted)")

    try:
        auth_url, session_id, state = br.generate_auth_url(token)
    except Exception as exc:
        print(f"generate_auth_url: FAIL ({type(exc).__name__}: {str(exc)[:240]})")
        return 3
    print(f"generate_auth_url: OK (url_len={len(auth_url)}, session_id_set={bool(session_id)}, state_set={bool(state)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
