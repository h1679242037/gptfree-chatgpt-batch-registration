#!/usr/bin/env python3
"""Small Cloud Mail client for local dry-run and batch_register_v2.py."""
import json
import os
import random
import re
import string
import time
import urllib.error
import urllib.request

ENV_FILES = (
    "~/.gptfree/cloud-mail-deploy.env",
    "~/.gptfree/cloud-mail-admin.env",
)


def _strip_quotes(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def load_cloud_mail_env(paths=ENV_FILES):
    """Load Cloud Mail variables from known env files and CLOUD_MAIL_* env vars.

    Later sources override earlier file values; process environment variables win.
    """
    env = {}
    for path in paths:
        try:
            with open(os.path.expanduser(path), "r") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip().lstrip("export ").strip()
                    if key:
                        env[key] = _strip_quotes(value)
        except FileNotFoundError:
            continue
    env.update({k: v for k, v in os.environ.items() if k.startswith("CLOUD_MAIL_")})
    return env


def _first(env, names):
    for name in names:
        value = str(env.get(name, "")).strip()
        if value:
            return value
    return ""


def normalize_cloud_mail_base_url(value):
    """Normalize a Cloud Mail API host/base URL to an HTTPS URL without trailing slash."""
    value = str(value or "").strip().rstrip("/")
    if not value:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        value = "https://" + value
    return value.rstrip("/")


def normalize_cloud_mail_domain(value):
    """Normalize a Cloud Mail inbox domain by stripping protocol, @, paths, and slash."""
    value = str(value or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.lstrip("@").split("/", 1)[0]
    return value.rstrip("/")


def get_cloud_mail_config(env=None):
    """Return Cloud Mail configuration derived from env files or supplied mapping."""
    env = env or load_cloud_mail_env()
    # API is served on CLOUD_MAIL_CUSTOM_DOMAIN (mail.*), while inbox addresses
    # should use CLOUD_MAIL_DOMAIN. Keep them separate.
    domain_source = _first(env, ("CLOUD_MAIL_DOMAIN", "CLOUD_MAIL_CUSTOM_DOMAIN"))
    base_url = normalize_cloud_mail_base_url(_first(env, (
        "CLOUD_MAIL_BASE_URL",
        "CLOUD_MAIL_API_URL",
        "CLOUD_MAIL_URL",
        "CLOUD_MAIL_ADMIN_URL",
        "CLOUD_MAIL_CUSTOM_DOMAIN",
        "CLOUD_MAIL_DOMAIN",
    )))
    return {
        "base_url": base_url,
        "domain": normalize_cloud_mail_domain(domain_source),
        "admin_email": _first(env, ("CLOUD_MAIL_ADMIN_EMAIL",)),
        "admin_password": _first(env, ("CLOUD_MAIL_ADMIN_PASSWORD",)),
    }


def mask_value(value):
    """Return a short redacted representation for logging config values."""
    value = str(value or "")
    if not value:
        return "<empty>"
    if len(value) <= 6:
        return "***"
    return value[:3] + "..." + value[-3:]


def _cloud_mail_request(config, path, payload, token=None, timeout=20):
    url = config["base_url"] + path
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36",
        "Origin": config["base_url"].rstrip("/"),
        "Referer": config["base_url"].rstrip("/") + "/",
    }
    if token:
        headers["Authorization"] = token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cloud Mail HTTP {exc.code}: {text[:200]}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cloud Mail request failed: {exc.reason}") from None
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        raise RuntimeError(f"Cloud Mail returned non-JSON response: {text[:120]}") from None
    code = data.get("code") if isinstance(data, dict) else None
    if code not in (None, 0, 200, "0", "200"):
        msg = data.get("message") or data.get("msg") or data.get("error") or f"code={code}"
        raise RuntimeError(f"Cloud Mail API error: {msg}")
    return data


def get_cloud_mail_token(config=None):
    """Authenticate to Cloud Mail and return an API token/accessToken string."""
    config = config or get_cloud_mail_config()
    if not config["base_url"]:
        raise RuntimeError("Cloud Mail API address is missing")
    if not config["admin_email"] or not config["admin_password"]:
        raise RuntimeError("Cloud Mail admin email/password is missing")
    data = _cloud_mail_request(config, "/api/public/genToken", {
        "email": config["admin_email"],
        "password": config["admin_password"],
    }, token=None)
    token = ""
    if isinstance(data, dict):
        token = data.get("token") or data.get("accessToken") or ""
        nested = data.get("data") if isinstance(data.get("data"), dict) else {}
        token = token or nested.get("token") or nested.get("accessToken") or ""
    if not token:
        raise RuntimeError("Cloud Mail did not return token/accessToken")
    return token


def generate_cloud_mail_local_part():
    """Generate a random local part suitable for a temporary Cloud Mail address."""
    chars = string.ascii_lowercase + string.digits
    return "gpt" + "".join(random.choices(chars, k=10))


def create_cloud_mail_address(local_part=None, config=None, token=None):
    """Create a Cloud Mail inbox and return the full email address."""
    config = config or get_cloud_mail_config()
    if not config["domain"]:
        raise RuntimeError("Cloud Mail mail domain is missing")
    token = token or get_cloud_mail_token(config)
    local = (local_part or generate_cloud_mail_local_part()).strip().lower()
    address = f"{local}@{config['domain']}"
    _cloud_mail_request(config, "/api/public/addUser", {"list": [{"email": address}]}, token=token)
    return address


def get_cloud_mail_messages(to_email, config=None, token=None, num=1, size=20):
    """Fetch recent Cloud Mail messages for an inbox in newest-first order."""
    config = config or get_cloud_mail_config()
    token = token or get_cloud_mail_token(config)
    data = _cloud_mail_request(config, "/api/public/emailList", {
        "toEmail": to_email,
        "type": 0,
        "isDel": 0,
        "timeSort": "desc",
        "num": num,
        "size": size,
    }, token=token)
    candidates = []
    if isinstance(data, list):
        candidates.append(data)
    elif isinstance(data, dict):
        candidates.extend([
            data.get("data"),
            data.get("list"),
            data.get("items"),
            data.get("rows"),
            data.get("records"),
        ])
        if isinstance(data.get("data"), dict):
            nested = data["data"]
            candidates.extend([nested.get("list"), nested.get("records"), nested.get("rows")])
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
    return []


def extract_six_digit_code(message):
    """Extract the first standalone six-digit code from common message fields."""
    if not isinstance(message, dict):
        return None
    fields = [
        message.get("subject"),
        message.get("title"),
        message.get("content"),
        message.get("html"),
        message.get("text"),
        message.get("plainText"),
        message.get("body"),
    ]
    combined = " ".join(str(v or "") for v in fields)
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", combined)
    return match.group(1) if match else None


def poll_cloud_mail_otp(to_email, after_ts=0, timeout=90, interval=5):
    """Poll Cloud Mail until a six-digit code is found or the timeout expires."""
    config = get_cloud_mail_config()
    token = get_cloud_mail_token(config)
    deadline = time.time() + timeout
    while time.time() < deadline:
        messages = get_cloud_mail_messages(to_email, config=config, token=token, size=10)
        for message in messages:
            code = extract_six_digit_code(message)
            if code:
                return code
        time.sleep(interval)
    return None
