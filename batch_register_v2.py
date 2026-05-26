#!/usr/bin/env python3
"""
Batch ChatGPT Registration + Sub2API Import v2
Fixed: Sub2API address, auth headers, country code, fingerprint protection
"""
import json, subprocess, asyncio, websockets, time, sys, random, string, imaplib, email, re, os
from email.utils import parsedate_to_datetime

from cloud_mail_local import (
    create_cloud_mail_address,
    get_cloud_mail_config,
    get_cloud_mail_messages,
    get_cloud_mail_token,
)

# Config
SUB2API = os.environ.get("GPTFREE_SUB2API_URL", "http://127.0.0.1:8080").rstrip("/")
SUB2API_EMAIL = os.environ.get("GPTFREE_SUB2API_EMAIL", "")
SUB2API_PASS = os.environ.get("GPTFREE_SUB2API_PASS", "")
PANEL_MODE = os.environ.get("GPTFREE_PANEL_MODE", "cpa").strip().lower()
CPA_URL = os.environ.get("GPTFREE_CPA_URL", "http://127.0.0.1:8317").rstrip("/")
CPA_MANAGEMENT_KEY = os.environ.get("GPTFREE_CPA_MANAGEMENT_KEY", "")
GMAIL_USER = os.environ.get("GPTFREE_GMAIL_USER", "")
GMAIL_PASS = os.environ.get("GPTFREE_GMAIL_PASS", "")
# Cloudflare Temp Email API
CF_TEMP_EMAIL_URL = os.environ.get("GPTFREE_CF_TEMP_EMAIL_URL", "https://example.com").rstrip("/")
CF_TEMP_EMAIL_AUTH = os.environ.get("GPTFREE_CF_TEMP_EMAIL_AUTH", "")
CF_TEMP_EMAIL_DOMAIN = os.environ.get("GPTFREE_EMAIL_DOMAIN", "example.com")
HEROSMS = "https://hero-sms.com/stubs/handler_api.php"
HEROSMS_KEY = os.environ.get("HEROSMS_API_KEY", "")
CDP_PORT = 9336
EMAIL_DOMAIN = os.environ.get("GPTFREE_EMAIL_DOMAIN", "example.com")
COUNTRY = 151  # Chile
DIAL_CODE = "56"
COUNTRY_NAME = "Chile"
COUNTRY_ISO = "CL"

# Parse command-line country override
import argparse as _ap
_parser = _ap.ArgumentParser()
_parser.add_argument("count", nargs="?", type=int, default=2)
_parser.add_argument("--country", type=int)
_parser.add_argument("--dial", type=str)
_parser.add_argument("--iso", type=str)
_args, _ = _parser.parse_known_args()
if _args.country:
    COUNTRY = _args.country
if _args.dial:
    DIAL_CODE = _args.dial
if _args.iso:
    COUNTRY_ISO = _args.iso

# Fingerprint randomization
WINDOW_SIZES = [
    (1366, 768), (1440, 900), (1536, 864), (1600, 900),
    (1280, 800), (1920, 1080), (1680, 1050), (1360, 768),
]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]
TIMEZONES = ["America/Santiago", "America/New_York", "America/Los_Angeles", "Europe/London"]
LANGUAGES = ["en-US,en;q=0.9", "en-US,en;q=0.9,es;q=0.8", "en-GB,en;q=0.9"]

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

PHONE_ERROR_PATTERNS = [
    ("phone_number_used", re.compile(r"phone_max_usage_exceeded|phone_number_in_use|already\s+linked\s+to\s+the\s+maximum\s+number\s+of\s+accounts|phone\s+number\s+is\s+already\s+(?:in\s+use|linked|registered)|phone\s+number\s+has\s+already\s+been\s+used|already\s+associated\s+with\s+another\s+account|not\s+eligible\s+to\s+be\s+used|cannot\s+be\s+used\s+for\s+verification|号码.*(?:已|被).*(?:使用|占用|绑定|注册)|手机号.*(?:已|被).*(?:使用|占用|绑定|注册)|该手机号.*(?:已|被).*(?:使用|占用|绑定|注册)", re.I)),
    ("phone_number_invalid", re.compile(r"phone\s+number\s+is\s+not\s+valid|invalid\s+phone\s+number|invalid\s+phone|not\s+a\s+valid\s+phone|号码.*无效|手机号.*无效|电话号码.*无效", re.I)),
    ("sms_delivery_refused", re.compile(r"无法向此电话号码发送验证码|无法向.*(?:电话号码|手机号|号码).*发送(?:验证码|短信)|(?:不能|无法).*发送.*(?:验证码|短信).*(?:电话号码|手机号|号码)|(?:cannot|can't|could\s*not|couldn't|unable\s+to)\s+(?:send|deliver).{0,80}(?:verification\s+code|code|sms|text(?:\s+message)?).{0,80}(?:phone|number)|(?:verification\s+code|sms|text(?:\s+message)?).{0,80}(?:cannot|can't|could\s*not|couldn't|unable\s+to).{0,80}(?:send|deliver)", re.I)),
    ("resend_throttled", re.compile(r"tried\s+to\s+resend\s+too\s+many\s+times|please\s+try\s+again\s+later|too\s+many\s+resend|resend\s+too\s+many|发送.*过于频繁|稍后再试", re.I)),
    ("resend_phone_banned", re.compile(r"无法向此电话号码发送短信|无法向此手机号发送短信|无法发送短信到此电话号码|无法发送短信到此手机号|can(?:not|'t)\s+send\s+(?:an?\s+)?(?:sms|text(?:\s+message)?)\s+to\s+(?:this|that)\s+(?:phone\s+)?number|unable\s+to\s+send\s+(?:an?\s+)?(?:sms|text(?:\s+message)?)\s+to\s+(?:this|that)\s+(?:phone\s+)?number", re.I)),
    ("resend_server_error", re.compile(r"this\s+page\s+isn['’]?t\s+working|currently\s+unable\s+to\s+handle\s+this\s+request|http\s+error\s+500|500\s+internal\s+server\s+error", re.I)),
    ("whatsapp_resend_channel", re.compile(r"whats\s*app", re.I)),
    ("code_rejected", re.compile(r"incorrect\s+code|invalid\s+code|wrong\s+code|code\s+is\s+incorrect|验证码.*(?:错误|无效|不正确)|代码.*(?:错误|无效|不正确)", re.I)),
]

PHONE_ERROR_ACTION = {
    "phone_number_used": "replace_number",
    "phone_number_invalid": "replace_number",
    "sms_delivery_refused": "replace_number",
    "resend_phone_banned": "replace_number",
    "phone_max_usage_exceeded": "replace_number",
    "resend_throttled": "retry_later",
    "resend_server_error": "retry_later",
    "whatsapp_resend_channel": "replace_number",
    "code_rejected": "replace_number",
}

def classify_phone_verification_error(text):
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if not compact:
        return None, None
    for reason, pattern in PHONE_ERROR_PATTERNS:
        if pattern.search(compact):
            if reason == "phone_number_used" and "phone_max_usage_exceeded" in compact.lower():
                reason = "phone_max_usage_exceeded"
            return reason, PHONE_ERROR_ACTION.get(reason, "replace_number")
    return None, None

async def snapshot_phone_error(cdp, limit=1600):
    try:
        text = await cdp.ev(f"document.body ? document.body.innerText.substring(0,{int(limit)}) : ''")
    except Exception:
        text = ""
    reason, action = classify_phone_verification_error(text)
    return {"reason": reason, "action": action, "text": text or ""}

def should_replace_phone(reason):
    return PHONE_ERROR_ACTION.get(reason) == "replace_number"

def create_or_reuse_cloud_mail_address(local_part=None):
    """Create a Cloud Mail address, or reuse it when the local address already exists."""
    try:
        return create_cloud_mail_address(local_part)
    except RuntimeError as exc:
        msg = str(exc)
        if local_part and ("已存在" in msg or "exist" in msg.lower()):
            config = get_cloud_mail_config()
            domain = config.get("domain") or ""
            if domain:
                return f"{local_part.strip().lower()}@{domain}"
        raise


def random_email():
    """Create an email via self-hosted Cloud Mail, return (address, provider)."""
    return create_or_reuse_cloud_mail_address(), "cloudmail"

def random_password():
    mid = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"Gx{mid}!2"

MAX_PRICE = float(os.environ.get("GPTFREE_HEROSMS_MAX_PRICE", "0.03"))
SERVICE = "dr"

def _hero_sms_url(**params):
    from urllib.parse import urlencode
    query = {"api_key": HEROSMS_KEY, **params}
    return f"{HEROSMS}?{urlencode(query)}"

def _hero_sms_get(**params):
    r = subprocess.run(["curl", "-sS", "--max-time", "20", _hero_sms_url(**params)],
        capture_output=True, text=True)
    return (r.stdout or "").strip()

def _parse_json_payload(text):
    try:
        return json.loads(text)
    except Exception:
        return None

def hero_sms_price_tiers(country=COUNTRY, max_price=MAX_PRICE):
    """FlowPilot-style non-purchasing stock preview.

    Prefer getTopCountriesByService/freePrice=true because getPrices can expose only
    the cheapest visible tier and miss higher-price stock. Returns [(price, count)].
    """
    payload = _parse_json_payload(_hero_sms_get(
        action="getTopCountriesByService", service=SERVICE, freePrice="true"
    ))
    tiers = {}
    if isinstance(payload, dict):
        for entry in payload.values():
            if not isinstance(entry, dict) or int(entry.get("country") or 0) != int(country):
                continue
            for price_raw, count_raw in (entry.get("freePriceMap") or {}).items():
                try:
                    price = round(float(price_raw), 4)
                    count = int(float(count_raw))
                except Exception:
                    continue
                if price > 0 and count > 0 and price <= max_price:
                    tiers[price] = max(tiers.get(price, 0), count)
            # Keep cost/count as a fallback tier if present.
            try:
                price = round(float(entry.get("price") or entry.get("retail_price") or 0), 4)
                count = int(float(entry.get("count") or 0))
                if price > 0 and count > 0 and price <= max_price:
                    tiers[price] = max(tiers.get(price, 0), count)
            except Exception:
                pass
            break
    if not tiers:
        payload = _parse_json_payload(_hero_sms_get(action="getPrices", service=SERVICE, country=country))
        info = (payload or {}).get(str(country), {}).get(SERVICE, {}) if isinstance(payload, dict) else {}
        try:
            price = round(float(info.get("cost") or 0), 4)
            count = int(float(info.get("physicalCount") or info.get("count") or 0))
            if price > 0 and count > 0 and price <= max_price:
                tiers[price] = count
        except Exception:
            pass
    return sorted(tiers.items())

def buy_number():
    pre_act = os.environ.pop("GPTFREE_PREBOUGHT_ACT_ID", "").strip()
    pre_phone = os.environ.pop("GPTFREE_PREBOUGHT_PHONE", "").strip()
    if pre_act and pre_phone:
        log("  using pre-bought HeroSMS activation")
        return pre_act, pre_phone
    if os.environ.get("GPTFREE_ALLOW_REAL_REGISTRATION") != "1":
        log("  real phone purchase is disabled; set GPTFREE_ALLOW_REAL_REGISTRATION=1 to opt in")
        return None, None

    country_plan = [(COUNTRY, DIAL_CODE, COUNTRY_NAME)]
    if int(COUNTRY) == 151:
        country_plan.append((16, "44", "United Kingdom"))

    # Direct buy first — skip tier pre-check
    for country, dial_code, country_name in country_plan:
        for action in ("getNumberV2", "getNumber"):
            resp = _hero_sms_get(action=action, service=SERVICE, country=country,
                maxPrice=f"{MAX_PRICE:.4f}", fixedPrice="false")
            log(f"  direct {action} {country_name} maxPrice={MAX_PRICE:.4f}: {resp[:120]}")
            if "ACCESS_NUMBER" in resp:
                parts = resp.split(":")
                globals()["DIAL_CODE"] = dial_code
                globals()["COUNTRY_NAME"] = country_name
                return parts[1], parts[2]
        if "NO_NUMBERS" not in resp:
            break  # unexpected error on this country, try next

    last_resp = ""
    for country, dial_code, country_name in country_plan:
        tiers = hero_sms_price_tiers(country, MAX_PRICE)
        if not tiers and MAX_PRICE > 0:
            # HeroSMS read-only stock endpoints can under-report countries that are
            # still purchasable. Synthetic fallback should still buy low-to-high,
            # not jump straight to the user's maxPrice.
            synthetic_prices = [round(p / 1000, 4) for p in range(20, int(round(MAX_PRICE * 1000)) + 1)]
            tiers = [(p, 1) for p in synthetic_prices if 0 < p <= MAX_PRICE]
            log(f"  HeroSMS preview empty for {country_name}; trying synthetic low-to-high price probes: " + ", ".join(f"{p:.4f}" for p, _ in tiers))
        if not tiers:
            log(f"  HeroSMS no stock within maxPrice={MAX_PRICE} for country={country} ({country_name})")
            continue
        log(f"  HeroSMS {country_name} price tiers: " + ", ".join(f"{p:.4f}=>{c}" for p, c in tiers))

        for price, _count in tiers:
            for action in ("getNumberV2", "getNumber"):
                resp = _hero_sms_get(action=action, service=SERVICE, country=country,
                    maxPrice=f"{price:.4f}", fixedPrice="true")
                last_resp = resp
                if "ACCESS_NUMBER" in resp:
                    parts = resp.split(":")
                    globals()["DIAL_CODE"] = dial_code
                    globals()["COUNTRY_NAME"] = country_name
                    return parts[1], parts[2]
                if "WRONG_MAX_PRICE" in resp:
                    log(f"  {action} {country_name} price={price:.4f}: {resp[:120]}")
                    continue
                if "NO_NUMBERS" not in resp:
                    log(f"  {action} {country_name} price={price:.4f}: {resp[:120]}")
        log(f"  buy_number {country_name} response: {last_resp[:120]}")
    return None, None

def cancel_number(act_id):
    subprocess.run(["curl","-sS","--max-time","10",
        f"{HEROSMS}?api_key={HEROSMS_KEY}&action=setStatus&id={act_id}&status=8"],
        capture_output=True, text=True)

def schedule_cancel_number(act_id, delay=125):
    """Cancel an activation later in a detached helper so retries can continue immediately."""
    code = """
import os, subprocess, time
act_id = os.environ['GPTFREE_CANCEL_ACT_ID']
delay = int(os.environ.get('GPTFREE_CANCEL_DELAY', '125'))
api = os.environ['GPTFREE_CANCEL_API']
key = os.environ['GPTFREE_CANCEL_KEY']
time.sleep(delay)
url = f'{api}?api_key={key}&action=setStatus&id={act_id}&status=8'
r = subprocess.run(['curl', '-sS', '--max-time', '10', url], capture_output=True, text=True)
with open(os.path.expanduser('~/.hermes/logs/gptfree-delayed-cancel.log'), 'a') as f:
    f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} act_id={act_id} resp={r.stdout.strip()[:120]}\\n')
"""
    env = os.environ.copy()
    env.update({
        "GPTFREE_CANCEL_ACT_ID": str(act_id),
        "GPTFREE_CANCEL_DELAY": str(delay),
        "GPTFREE_CANCEL_API": HEROSMS,
        "GPTFREE_CANCEL_KEY": HEROSMS_KEY,
    })
    subprocess.Popen([sys.executable, "-c", code], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    log(f"  scheduled delayed cancel for activation {act_id} in {delay}s")

def finish_number(act_id):
    subprocess.run(["curl","-sS","--max-time","10",
        f"{HEROSMS}?api_key={HEROSMS_KEY}&action=setStatus&id={act_id}&status=6"],
        capture_output=True, text=True)

def get_sms(act_id, timeout=150):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(["curl","-sS","--max-time","10",
            f"{HEROSMS}?api_key={HEROSMS_KEY}&action=getStatus&id={act_id}"],
            capture_output=True, text=True)
        if "STATUS_OK" in r.stdout:
            return r.stdout.split(":")[1]
        if "STATUS_CANCEL" in r.stdout:
            return None
        time.sleep(10)
    return None

def message_ts(message):
    for key in ("createdAt", "created_at", "date", "time", "timestamp", "receivedAt", "createTime"):
        value = message.get(key) if isinstance(message, dict) else None
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value) / (1000 if value > 10_000_000_000 else 1)
        text = str(value)
        try:
            return parsedate_to_datetime(text).timestamp()
        except Exception:
            pass
        try:
            return time.mktime(time.strptime(text[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            pass
    return 0.0


def extract_openai_code(message):
    if not isinstance(message, dict):
        return None
    fields = [str(message.get(k) or "") for k in (
        "from", "fromEmail", "sender", "sendEmail", "sendName",
        "subject", "title", "content", "html", "text", "plainText", "body",
    )]
    combined = "\n".join(fields)
    if not re.search(r"openai|chatgpt|verify|verification|验证码|验证", combined, re.I):
        return None
    marker_patterns = [
        r"输入此临时验证码以继续[：:\s<>=\"'A-Za-z0-9;#/!\[\]().,-]*?(?<!\d)(\d{6})(?!\d)",
        r"temporary verification code[\s\S]{0,800}?(?<!\d)(\d{6})(?!\d)",
        r"verification code[\s\S]{0,800}?(?<!\d)(\d{6})(?!\d)",
    ]
    for pat in marker_patterns:
        m = re.search(pat, combined, re.I)
        if m:
            return m.group(1)
    codes = re.findall(r"(?<!\d)(\d{6})(?!\d)", combined)
    filtered = [c for c in codes if c not in {"202123", "353740"}]
    return filtered[-1] if filtered else (codes[-1] if codes else None)


def poll_latest_openai_otp(address, after_ts=0, timeout=120, interval=5):
    config = get_cloud_mail_config()
    token = get_cloud_mail_token(config)
    deadline = time.time() + timeout
    while time.time() < deadline:
        messages = get_cloud_mail_messages(address, config=config, token=token, size=20)
        candidates = []
        for msg in messages:
            code = extract_openai_code(msg)
            if not code:
                continue
            ts = message_ts(msg)
            if after_ts and ts and ts < after_ts:
                continue
            candidates.append((ts, code))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
        if messages:
            newest = messages[0]
            summary = json.dumps({k: newest.get(k) for k in ("sendEmail", "sendName", "subject", "title", "createdAt", "createTime", "date") if isinstance(newest, dict)}, ensure_ascii=False)[:240]
            log(f"    [email] checked Cloud Mail; no matching OpenAI OTP yet; newest={summary}")
        else:
            log("    [email] checked Cloud Mail; inbox empty")
        time.sleep(interval)
    return None


def get_email_otp(target_email, after_ts, timeout=90, jwt=None):
    """Get email OTP via local Cloud Mail only. Legacy CF/Gmail branches are disabled."""
    if jwt == "cloudmail":
        return poll_latest_openai_otp(target_email, after_ts, timeout=timeout)
    log("    [email] non-Cloud Mail providers disabled in local gptfree patch")
    return None

def sub2api_request(method, path, token=None, data=None):
    """Helper for Sub2API API calls."""
    cmd = ["curl", "-sS", "--max-time", "15", "-X", method]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    cmd += ["-H", "Content-Type: application/json"]
    if data is not None:
        cmd += ["-d", json.dumps(data)]
    cmd.append(f"{SUB2API}{path}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Sub2API curl failed: {r.stderr.strip() or r.returncode}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Sub2API returned non-JSON response: {r.stdout[:200]}") from exc

def cpa_request(method, path, data=None):
    """Helper for CPA management API calls (FlowPilot-compatible)."""
    if not CPA_MANAGEMENT_KEY:
        raise RuntimeError("CPA management key not configured; set GPTFREE_CPA_MANAGEMENT_KEY")
    cmd = ["curl", "-sS", "--max-time", "20", "-X", method,
        "-H", f"Authorization: Bearer {CPA_MANAGEMENT_KEY}",
        "-H", f"X-Management-Key: {CPA_MANAGEMENT_KEY}",
        "-H", "Content-Type: application/json"]
    if data is not None:
        cmd += ["-d", json.dumps(data)]
    cmd.append(f"{CPA_URL}{path}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"CPA curl failed: {r.stderr.strip() or r.returncode}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CPA returned non-JSON response: {r.stdout[:200]}") from exc

def sub2api_login():
    resp = sub2api_request("POST", "/api/v1/auth/login",
        data={"email": SUB2API_EMAIL, "password": SUB2API_PASS})
    return resp["data"]["access_token"]

def panel_login():
    if PANEL_MODE == "cpa":
        return None
    return sub2api_login()


def wait_cpa_auth_status(state, timeout=120, interval=2):
    """Poll CPA auth status until success or timeout."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = cpa_request("GET", f"/v0/management/get-auth-status?state={state}")
        status = str(last.get("status", "")).lower() if isinstance(last, dict) else ""
        if status in {"ok", "success", "done", "completed"}:
            return True
        if status in {"error", "failed", "fail"}:
            return False
        time.sleep(interval)
    return False


def restart_chrome_with_fingerprint():
    """Kill Chrome and restart with randomized fingerprint (runs on OC24 locally)"""
    w, h = random.choice(WINDOW_SIZES)
    ua = random.choice(USER_AGENTS)
    
    # Kill only stale registration Chrome instances. Avoid broad pkill -f patterns:
    # they can match the shell command itself and leave split IPv4/IPv6 CDP listeners.
    killed = []
    try:
        ps = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
        for line in ps.splitlines()[1:]:
            pid_s, _, args = line.strip().partition(" ")
            if not pid_s.isdigit() or not args.startswith("/opt/google/chrome/chrome "):
                continue
            if "remote-debugging-port=9336" in args or "--user-data-dir=/tmp/chrome-reg-current" in args:
                try:
                    os.kill(int(pid_s), 9)
                    killed.append(pid_s)
                except ProcessLookupError:
                    pass
    except Exception as exc:
        log(f"  Chrome cleanup warning: {exc}")
    if killed:
        log(f"  killed stale Chrome pids: {','.join(killed[:8])}")
    time.sleep(1)
    subprocess.run(["rm", "-rf", "/tmp/chrome-reg-current"], capture_output=True, text=True)

    # Write launch script using simple string concatenation (no triple quotes)
    lines = []
    lines.append("#!/bin/bash")
    lines.append("export DISPLAY=${DISPLAY:-}")
    # Chrome command - each arg on its own append to avoid escaping issues
    chrome = "/usr/bin/google-chrome"
    chrome += " --remote-debugging-port=9336 --remote-allow-origins='*'"
    chrome += " --user-data-dir=/tmp/chrome-reg-current"
    chrome += " --no-first-run --no-default-browser-check"
    chrome += " --disable-background-networking --disable-sync"
    chrome += f" --disable-extensions --window-size={w},{h}"
    chrome += " --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage"
    chrome += " --disable-save-password-bubble --disable-infobars"
    chrome += " --hide-crash-restore-bubble --disable-session-crashed-bubble"
    chrome += " --disable-features=PasswordManager"
    chrome += " --disable-popup-blocking --password-store=basic"
    chrome += f" --user-agent='{ua}'"
    chrome += " --proxy-server=http://127.0.0.1:7890"
    chrome += " --proxy-bypass-list='localhost,127.0.0.1'"
    chrome += " 'about:blank' > /dev/null 2>" + chr(38) + "1 " + chr(38)
    lines.append(chrome)
    lines.append("CPID=$!")
    lines.append("echo Chrome_PID:$CPID")
    lines.append("sleep 6")
    lines.append("python3 - <<'PY'")
    lines.append("import json, urllib.request")
    lines.append("try:")
    lines.append("    targets=json.load(urllib.request.urlopen('http://127.0.0.1:9336/json/list', timeout=3))")
    lines.append("    pages=[t for t in targets if t.get('type')=='page']")
    lines.append("    print('CDP_PAGES:' + ','.join((t.get('url') or '')[:80] for t in pages))")
    lines.append("    raise SystemExit(0 if any((t.get('url') or '')=='about:blank' for t in pages) else 2)")
    lines.append("except Exception as e:")
    lines.append("    print('CDP_ERROR:' + repr(e))")
    lines.append("    raise SystemExit(1)")
    lines.append("PY")
    lines.append("test $? -eq 0 && echo CDP_SUCCESS || echo CDP_FAIL")
    
    script_content = chr(10).join(lines) + chr(10)
    with open("/tmp/launch_chrome_fp.sh", "w") as f:
        f.write(script_content)
    
    r = subprocess.run(["bash", "/tmp/launch_chrome_fp.sh"],
        capture_output=True, text=True, timeout=30)
    ok = "CDP_SUCCESS" in r.stdout
    log(f"  Chrome restarted: {w}x{h}, UA: ...{ua[-30:]}, CDP: {'OK' if ok else 'FAIL'}")
    log(f"  Chrome check: {r.stdout[-300:].strip()}")
    if not ok and r.stderr:
        log(f"  stderr: {r.stderr[:200]}")
    return ok

class CDP:
    def __init__(self, ws):
        self.ws = ws
        self.mid = 0
    
    async def send(self, method, params=None, timeout=15):
        self.mid += 1
        mid = self.mid
        cmd = {"id": mid, "method": method}
        if params:
            cmd["params"] = params
        await self.ws.send(json.dumps(cmd))
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=min(3, timeout-(time.time()-t0)))
                r = json.loads(raw)
                if r.get("id") == mid:
                    return r
            except asyncio.TimeoutError:
                continue
        return None
    
    async def ev(self, expr, timeout=10):
        r = await self.send("Runtime.evaluate",
            {"expression": expr, "returnByValue": True}, timeout=timeout)
        if r and "result" in r:
            res = r["result"].get("result", {})
            if "exceptionDetails" in r.get("result", {}):
                return None
            return res.get("value")
        return None
    
    async def url(self):
        return await self.ev("location.href")
    
    async def text(self, max_len=500):
        return await self.ev(f"document.body.innerText.substring(0, {max_len})")
    
    async def type_text(self, text):
        await self.send("Input.insertText", {"text": text})
        await asyncio.sleep(0.3)
    
    async def type_password(self, password):
        """Fill password using native setter (FlowPilot-compatible, React-safe)"""
        result = await self.fill_input('input[type="password"]', password)
        if isinstance(result, dict) and result.get('ok'):
            return result.get('length', 0)
        return 0

    async def fill_input(self, selector, text):
        """React-compatible input fill: native setter + input/change events."""
        return await self.ev(f"""(function(){{
            const selector = {json.dumps(selector)};
            const value = {json.dumps(str(text))};
            function visible(el) {{
                if (!el) return false;
                const s = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
            }}
            const candidates = Array.from(document.querySelectorAll(selector));
            const el = candidates.find(visible) || candidates[0];
            if (!el) return {{ok:false, reason:'not_found'}};
            el.scrollIntoView({{block:'center', inline:'center'}});
            el.focus();
            try {{ el.click(); }} catch(e) {{}}
            const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            const desc = Object.getOwnPropertyDescriptor(proto, 'value');
            if (desc && desc.set) desc.set.call(el, ''); else el.value = '';
            el.dispatchEvent(new Event('input', {{bubbles:true}}));
            if (desc && desc.set) desc.set.call(el, value); else el.value = value;
            el.dispatchEvent(new Event('input', {{bubbles:true}}));
            el.dispatchEvent(new Event('change', {{bubbles:true}}));
            el.dispatchEvent(new KeyboardEvent('keyup', {{bubbles:true, key:'Unidentified'}}));
            return {{ok:true, value:el.value, length:(el.value || '').length}};
        }})()""")

    async def focus_and_type(self, selector, text):
        result = await self.fill_input(selector, text)
        if isinstance(result, dict) and result.get('ok'):
            return True
        # Fallback to CDP text insertion if native setter path failed.
        doc = await self.send("DOM.getDocument", {"depth": 1})
        if not doc or "result" not in doc:
            return False
        root = doc["result"]["root"]["nodeId"]
        inp = await self.send("DOM.querySelector", {"nodeId": root, "selector": selector})
        if not inp or not inp.get("result", {}).get("nodeId"):
            return False
        nid = inp["result"]["nodeId"]
        await self.send("DOM.focus", {"nodeId": nid})
        await asyncio.sleep(0.1)
        await self.type_text(text)
        return True

    async def _click_center(self, rect):
        if not rect:
            return False
        x = float(rect.get('x', 0)) + float(rect.get('width', 0)) / 2
        y = float(rect.get('y', 0)) + float(rect.get('height', 0)) / 2
        if x <= 0 or y <= 0:
            return False
        await self.send("Page.bringToFront", {})
        await self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "none"})
        await self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        return True

    async def click_submit_exact(self, values=None):
        """Click an enabled submit button, preferring exact button/input values.

        OpenAI auth pages often render multiple visible `继续` buttons. Exact
        values such as `phone_number` and `validate` avoid accidentally clicking
        OAuth/social-login buttons.
        """
        values = values or []
        result = await self.ev(f"""(function(){{
            const values = {json.dumps(values)};
            function visible(el){{ if(!el) return false; const s=getComputedStyle(el), r=el.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }}
            function enabled(el){{ return !!el && !el.disabled && el.getAttribute('aria-disabled') !== 'true'; }}
            const btns = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]')).filter(visible).filter(enabled);
            let btn = values.length ? btns.find(b => values.includes(b.value || '')) : null;
            if(!btn) btn = btns.find(function(b){{ var t=(b.innerText||b.value||b.textContent||'').trim().toLowerCase(); return ['continue','next','submit','sign up','verify','allow','authorize','继续','下一步','提交','注册','验证','允许','授权'].some(function(x){{return t.includes(x);}}); }});
            if(!btn) return {{ok:false, reason:'not_found'}};
            btn.scrollIntoView({{block:'center', inline:'center'}});
            btn.focus();
            const r = btn.getBoundingClientRect();
            const rect = {{x:r.x,y:r.y,width:r.width,height:r.height}};
            var form = btn.form || btn.closest('form');
            if(form && typeof form.requestSubmit === 'function') {{ try {{ form.requestSubmit(btn); return {{ok:true, method:'requestSubmit', rect:rect, text:(btn.innerText||btn.value||btn.textContent||'').trim(), value:btn.value||''}}; }} catch(e){{}} }}
            try {{ btn.click(); return {{ok:true, method:'nativeClick', rect:rect, text:(btn.innerText||btn.value||btn.textContent||'').trim(), value:btn.value||''}}; }} catch(e){{}}
            try {{ btn.dispatchEvent(new MouseEvent('click', {{bubbles:true,cancelable:true,view:window}})); return {{ok:true, method:'dispatchClick', rect:rect, text:(btn.innerText||btn.value||btn.textContent||'').trim(), value:btn.value||''}}; }} catch(e){{}}
            return {{ok:false, reason:'dom_click_failed', rect:rect}};
        }})()""", timeout=10)
        if isinstance(result, dict) and result.get('ok'):
            return result
        if isinstance(result, dict) and result.get('rect'):
            clicked = await self._click_center(result.get('rect'))
            if clicked:
                return {'ok': True, 'method': 'cdpMouse', 'rect': result.get('rect')}
        return result

    async def click_text_any(self, needles):
        if isinstance(needles, str):
            needles = [needles]
        result = await self.ev(f"""(function(){{
            const needles = {json.dumps([str(x).lower() for x in needles], ensure_ascii=False)};
            function visible(el){{ if(!el) return false; const s=getComputedStyle(el), r=el.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }}
            const all = Array.from(document.querySelectorAll('button, a, [role="button"], [role="link"], span, div')).filter(visible);
            const el = all.find(e => {{ const t=(e.innerText||e.value||e.textContent||'').trim().toLowerCase(); return needles.some(n => t.includes(n)); }});
            if(!el) return {{ok:false, reason:'not_found', texts:all.map(e=>(e.innerText||e.value||e.textContent||'').trim()).slice(0,12)}};
            el.scrollIntoView({{block:'center', inline:'center'}}); el.focus();
            const r = el.getBoundingClientRect();
            try {{ el.click(); return {{ok:true, method:'nativeClick', rect:{{x:r.x,y:r.y,width:r.width,height:r.height}}, text:(el.innerText||el.value||el.textContent||'').trim()}}; }} catch(e) {{}}
            try {{ el.dispatchEvent(new MouseEvent('click', {{bubbles:true,cancelable:true,view:window}})); return {{ok:true, method:'dispatchClick', rect:{{x:r.x,y:r.y,width:r.width,height:r.height}}, text:(el.innerText||el.value||el.textContent||'').trim()}}; }} catch(e) {{}}
            return {{ok:false, reason:'dom_click_failed', rect:{{x:r.x,y:r.y,width:r.width,height:r.height}}}};
        }})()""", timeout=10)
        if isinstance(result, dict) and result.get('ok'):
            return result
        if isinstance(result, dict) and result.get('rect'):
            clicked = await self._click_center(result.get('rect'))
            if clicked:
                return {'ok': True, 'method': 'cdpMouse', 'rect': result.get('rect')}
        return result

    async def click_submit(self):
        """FlowPilot-style submit click: requestSubmit -> native click -> dispatch click -> CDP mouse."""
        result = await self.ev("""(function(){
            function visible(el){ if(!el) return false; var s=getComputedStyle(el), r=el.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }
            function enabled(el){ return !!el && !el.disabled && el.getAttribute('aria-disabled') !== 'true'; }
            var btns = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]')).filter(visible);
            var btn = document.querySelector('button[type="submit"], input[type="submit"]');
            if(!visible(btn)) btn = null;
            if(!btn) btn = btns.find(function(b){ var t=(b.innerText||b.value||b.textContent||'').trim().toLowerCase(); return ['continue','next','submit','sign up','verify','allow','authorize','继续','下一步','提交','注册','验证','允许','授权'].some(function(x){return t.includes(x);}); });
            if(!btn) return {ok:false, reason:'not_found'};
            btn.scrollIntoView({block:'center', inline:'center'});
            btn.focus();
            var r=btn.getBoundingClientRect();
            var rect={x:r.x,y:r.y,width:r.width,height:r.height};
            if(!enabled(btn)) return {ok:false, reason:'disabled', rect:rect, text:(btn.innerText||btn.value||btn.textContent||'').trim()};
            var form = btn.form || btn.closest('form');
            if(form && typeof form.requestSubmit === 'function') { try { form.requestSubmit(btn); return {ok:true, method:'requestSubmit', rect:rect}; } catch(e){} }
            try { btn.click(); return {ok:true, method:'nativeClick', rect:rect}; } catch(e){}
            try { btn.dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true,view:window})); return {ok:true, method:'dispatchClick', rect:rect}; } catch(e){}
            return {ok:false, reason:'dom_click_failed', rect:rect};
        })()""")
        if isinstance(result, dict) and result.get('ok'):
            return result
        if isinstance(result, dict) and result.get('rect'):
            clicked = await self._click_center(result.get('rect'))
            if clicked:
                return {'ok': True, 'method': 'cdpMouse', 'rect': result.get('rect')}
        return result

    async def click_text(self, text):
        needle = str(text).lower()
        result = await self.ev(f"""(function(){{
            const needle = {json.dumps(str(text).lower())};
            function visible(el){{ if(!el) return false; const s=getComputedStyle(el), r=el.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }}
            const all = Array.from(document.querySelectorAll('button, a, [role="button"], [role="link"], span, div')).filter(visible);
            const el = all.find(e => (e.innerText || e.textContent || '').trim().toLowerCase().includes(needle));
            if(!el) return {{ok:false, reason:'not_found'}};
            el.scrollIntoView({{block:'center', inline:'center'}}); el.focus();
            const r = el.getBoundingClientRect();
            try {{ el.click(); return {{ok:true, method:'nativeClick', rect:{{x:r.x,y:r.y,width:r.width,height:r.height}}}}; }} catch(e) {{}}
            try {{ el.dispatchEvent(new MouseEvent('click', {{bubbles:true,cancelable:true,view:window}})); return {{ok:true, method:'dispatchClick', rect:{{x:r.x,y:r.y,width:r.width,height:r.height}}}}; }} catch(e) {{}}
            return {{ok:false, reason:'dom_click_failed', rect:{{x:r.x,y:r.y,width:r.width,height:r.height}}}};
        }})()""")
        if isinstance(result, dict) and result.get('ok'):
            return result
        if isinstance(result, dict) and result.get('rect'):
            clicked = await self._click_center(result.get('rect'))
            if clicked:
                return {'ok': True, 'method': 'cdpMouse', 'rect': result.get('rect')}
        return result

    async def click_oauth_consent(self, rounds=5):
        """FlowPilot-style OAuth consent click: requestSubmit, CDP mouse, native, dispatch, CDP retry."""
        strategies = ['requestSubmit', 'cdpMouse', 'nativeClick', 'dispatchClick', 'cdpMouse']
        baseline = await self.url()
        for idx, strategy in enumerate(strategies[:rounds], 1):
            result = await self.ev(f"""(function(){{
                const strategy = {json.dumps(strategy)};
                function visible(el){{ if(!el) return false; const s=getComputedStyle(el), r=el.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }}
                function enabled(el){{ return !!el && !el.disabled && el.getAttribute('aria-disabled') !== 'true' && getComputedStyle(el).pointerEvents !== 'none'; }}
                const candidates = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]')).filter(visible);
                const btn = candidates.find(b => {{ const t=(b.innerText||b.value||b.textContent||'').trim().toLowerCase(); return ['continue','allow','authorize','approve','继续','允许','授权','确认'].some(x => t.includes(x)); }}) || candidates.find(b => enabled(b));
                if(!btn) return {{ok:false, reason:'not_found'}};
                btn.scrollIntoView({{block:'center', inline:'center'}}); btn.focus();
                const r = btn.getBoundingClientRect();
                const rect = {{x:r.x,y:r.y,width:r.width,height:r.height}};
                if(!enabled(btn)) return {{ok:false, reason:'disabled', rect:rect}};
                if(strategy === 'requestSubmit') {{ const form=btn.form||btn.closest('form'); if(form && typeof form.requestSubmit === 'function') {{ try {{ form.requestSubmit(btn); return {{ok:true, method:'requestSubmit', rect:rect}}; }} catch(e){{}} }} }}
                if(strategy === 'nativeClick') {{ try {{ btn.click(); return {{ok:true, method:'nativeClick', rect:rect}}; }} catch(e){{}} }}
                if(strategy === 'dispatchClick') {{ try {{ btn.dispatchEvent(new MouseEvent('click', {{bubbles:true,cancelable:true,view:window}})); return {{ok:true, method:'dispatchClick', rect:rect}}; }} catch(e){{}} }}
                return {{ok:false, reason:'needs_cdp_or_failed', rect:rect}};
            }})()""")
            if strategy == 'cdpMouse' or (isinstance(result, dict) and result.get('rect') and not result.get('ok')):
                await self._click_center(result.get('rect') if isinstance(result, dict) else None)
            await asyncio.sleep(3 if idx < 3 else 5)
            current = await self.url()
            if current and current != baseline:
                return {'ok': True, 'round': idx, 'strategy': strategy, 'reason': 'url_changed', 'url': current}
            text = (await self.text(500) or '').lower()
            if 'localhost:1455' in (current or '') or 'callback' in (current or ''):
                return {'ok': True, 'round': idx, 'strategy': strategy, 'reason': 'callback', 'url': current}
            if 'consent' not in (current or '').lower() and ('continue' not in text and 'allow' not in text):
                return {'ok': True, 'round': idx, 'strategy': strategy, 'reason': 'left_consent', 'url': current}
        return {'ok': False, 'reason': 'no_effect', 'url': await self.url()}

    async def inject_fingerprint(self):
        """Inject fingerprint overrides to avoid detection"""
        tz = random.choice(TIMEZONES)
        lang = random.choice(LANGUAGES)
        await self.ev(f"""(function(){{
            // Override timezone
            var DateOrig = Date;
            // Override navigator properties
            Object.defineProperty(navigator, 'webdriver', {{get: function(){{ return false; }}}});
            Object.defineProperty(navigator, 'languages', {{get: function(){{ return '{lang}'.split(',').map(function(l){{return l.split(';')[0]}}); }}}});
            // Override plugins to look real
            Object.defineProperty(navigator, 'plugins', {{get: function(){{ return [1,2,3,4,5]; }}}});
            // Canvas noise
            var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type){{
                var ctx = this.getContext('2d');
                if(ctx) {{
                    var imgData = ctx.getImageData(0, 0, Math.min(this.width,2), Math.min(this.height,2));
                    imgData.data[0] = imgData.data[0] ^ {random.randint(1,3)};
                    ctx.putImageData(imgData, 0, 0);
                }}
                return origToDataURL.apply(this, arguments);
            }};
        }})()""")


async def register_account():
    """Phase 1: Register new account with phone number"""
    act_id, phone = buy_number()
    if not act_id:
        log("  ✗ Failed to buy number")
        return None
    
    log(f"  Phone: +{phone}")
    password = random_password()
    log(f"  Password: {password}")
    
    # Connect to browser
    r = subprocess.run(["curl","-sS","--max-time","10",f"http://127.0.0.1:{CDP_PORT}/json/list"],
                      capture_output=True, text=True)
    try:
        targets = json.loads(r.stdout)
    except json.JSONDecodeError:
        log(f"  ✗ CDP targets returned non-JSON/empty response: {r.stdout[:120]!r}")
        cancel_number(act_id)
        return None
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        log("  ✗ CDP returned no page target")
        cancel_number(act_id)
        return None
    page = pages[0]
    
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=10**7, open_timeout=10) as ws:
        cdp = CDP(ws)
        
        # Inject fingerprint protection
        await cdp.inject_fingerprint()
        
        # Clear cookies + navigate to chatgpt.com to establish session
        await cdp.send("Network.clearBrowserCookies")
        await asyncio.sleep(0.5)
        await cdp.send('Page.navigate', {'url': 'https://chatgpt.com/auth/login'})
        await asyncio.sleep(10)
        
        # Re-inject after navigation
        await cdp.inject_fingerprint()
        
        url = await cdp.url()
        log(f"  [1] Landed: {url}")
        
        # Wait for page to fully load (CF challenge etc)
        for wait_i in range(15):
            title = await cdp.ev("document.title || ''")
            body_len = await cdp.ev("document.body ? document.body.innerText.length : 0")
            if wait_i == 0 or wait_i == 5:
                snip = await cdp.ev("document.body ? document.body.innerText.substring(0,100) : ''")
                log(f"    [wait {wait_i}] title={title} len={body_len} text={str(snip)[:80]}")
            if title and "moment" not in title.lower() and "just" not in title.lower() and body_len and body_len > 20:
                break
            await asyncio.sleep(5)
        
        # Handle "Unable to load site" / VPN error
        body_text = await cdp.ev("document.body ? document.body.innerText.substring(0,200) : ''")
        if "unable to load" in (body_text or "").lower() or "vpn" in (body_text or "").lower():
            log("  [!] Site blocked, retrying...")
            await cdp.ev("location.reload()")
            await asyncio.sleep(8)
            body_text = await cdp.ev("document.body ? document.body.innerText.substring(0,200) : ''")
            if "unable to load" in (body_text or "").lower():
                log("  ✗ Site still blocked after retry")
                cancel_number(act_id)
                return None
        
        # Step 2: Detect UI type and navigate to phone registration
        # Check if inline auth UI (English or localized buttons)
        has_inline_auth = await cdp.ev("""
            !!Array.from(document.querySelectorAll("button, a, [role=button]"))
                .find(function(e) {
                    var t = e.textContent || '';
                    return /Continue with Google|More options|phone/i.test(t) || t.includes('电话') || t.includes('手機') || t.includes('手机');
                })
        """)
        
        if has_inline_auth:
            log("  [2] Inline auth UI detected")
            # Try clicking "phone" directly, or "More options" first
            phone_clicked = await cdp.ev("""(function(){
                var btns = Array.from(document.querySelectorAll('button, a, [role=button]'));
                var p = btns.find(function(b){
                    var t = b.textContent || '';
                    return /phone/i.test(t) || t.includes('电话') || t.includes('手機') || t.includes('手机');
                });
                if(p) { p.click(); return true; }
                return false;
            })()""")
            if not phone_clicked:
                log("    Clicking 'More options' first...")
                await cdp.ev("""(function(){
                    var btns = Array.from(document.querySelectorAll('button, a, [role=button]'));
                    var p = btns.find(function(b){ return /more options/i.test(b.textContent || ''); });
                    if(p) p.click();
                })()""")
                await asyncio.sleep(3)
                await cdp.ev("""(function(){
                    var btns = Array.from(document.querySelectorAll('button, a, [role=button]'));
                    var p = btns.find(function(b){
                        var t = b.textContent || '';
                        return /phone/i.test(t) || t.includes('电话') || t.includes('手機') || t.includes('手机');
                    });
                    if(p) p.click();
                })()""")
            await asyncio.sleep(8)
        else:
            # Old UI: click "Sign up" first, then navigate to auth.openai.com
            log("  [2] Old UI - clicking Sign up...")
            clicked = await cdp.ev("""(function(){
                var els = Array.from(document.querySelectorAll("a, button, [role=button]"));
                var el = els.find(function(e) { return /sign up/i.test(e.textContent); });
                if(el) { el.click(); return true; }
                return false;
            })()""")
            if not clicked:
                log("  [!] No Sign up button, trying direct URL...")
                await cdp.ev("window.location.href = 'https://auth.openai.com/log-in-or-create-account?usernameKind=phone_number'")
                await asyncio.sleep(8)
                await cdp.inject_fingerprint()
            else:
                # Wait for redirect to auth.openai.com
                for i in range(15):
                    await asyncio.sleep(4)
                    url = await cdp.url()
                    title = await cdp.ev("document.title || ''")
                    if url and "auth.openai.com" in url:
                        if title and "moment" not in title.lower():
                            break
                
                url = await cdp.url()
                if "auth.openai.com" not in (url or ""):
                    log(f"  [!] Not on auth page: {url}, trying direct URL...")
                    await cdp.ev("window.location.href = 'https://auth.openai.com/log-in-or-create-account?usernameKind=phone_number'")
                    await asyncio.sleep(8)
                    await cdp.inject_fingerprint()
                else:
                    # Wait for form + click phone
                    await asyncio.sleep(3)
                    await cdp.inject_fingerprint()
                    await cdp.ev("""(function(){
                        var btns = Array.from(document.querySelectorAll('button'));
                        var p = btns.find(function(b){ return /phone/i.test(b.textContent); });
                        if(p) p.click();
                    })()""")
                    await asyncio.sleep(4)
        
        # Verify we have the phone input
        has_tel = False
        for check_i in range(30):
            has_tel = await cdp.ev("!!document.querySelector(\"input[type='tel']\")")
            if has_tel:
                break
            if check_i == 0:
                await cdp.ev("""(function(){
                    var btns = Array.from(document.querySelectorAll('button, a, [role=button]'));
                    var p = btns.find(function(b){
                        var t = b.textContent || '';
                        return /phone/i.test(t) || t.includes('电话') || t.includes('手機') || t.includes('手机');
                    });
                    if(p) p.click();
                })()""")
            if check_i in (5, 10, 20):
                wait_url = await cdp.url()
                wait_body = await cdp.ev("document.body ? document.body.innerText.substring(0,120) : ''")
                log(f"  [2w] waiting for phone input #{check_i}: {wait_url} text={str(wait_body)[:80]}")
            await asyncio.sleep(2)
        
        if not has_tel:
            # Fallback: navigate directly to phone registration URL
            log("  [!] No tel input found, trying direct phone registration URL...")
            await cdp.ev("window.location.href = 'https://auth.openai.com/log-in-or-create-account?usernameKind=phone_number'")
            await asyncio.sleep(8)
            await cdp.inject_fingerprint()
            has_tel = await cdp.ev("!!document.querySelector(\"input[type='tel']\")")
            if not has_tel:
                url = await cdp.url()
                body = await cdp.ev("document.body ? document.body.innerText.substring(0,200) : ''")
                log(f"  ✗ Cannot reach phone input. URL: {url}")
                log(f"    Body: {body[:100]}")
                cancel_number(act_id)
                return None
        
        url = await cdp.url()
        log(f"  [2] Ready for phone input: {url}")
        
        # Input phone number - full international format (auto-detect country)
        full_phone = f"+{phone}"
        await cdp.focus_and_type('input[type="tel"]', full_phone)
        await asyncio.sleep(1)

        # Click Continue
        await cdp.click_submit()
        await asyncio.sleep(8)
        url = await cdp.url()
        log(f"  [4] After phone submit: {url}")
        phone_err = await snapshot_phone_error(cdp)
        if phone_err["reason"]:
            log(f"  [4e] Phone verification error: {phone_err['reason']} action={phone_err['action']}")
        
        # Check if number already registered / rejected
        if "log-in/password" in (url or "") or should_replace_phone(phone_err["reason"]):
            log("  [!] Number rejected/used, trying another...")
            cancel_number(act_id)
            for retry_num in range(1, 4):
                await asyncio.sleep(2)
                act_id, phone = buy_number()
                if not act_id:
                    log("  ✗ Failed to buy replacement number")
                    return None
                full_phone = f"+{phone}"
                log(f"  [4r] Retry #{retry_num}: +{phone}")
                await cdp.ev("window.location.href = 'https://auth.openai.com/log-in-or-create-account?usernameKind=phone_number'")
                await asyncio.sleep(6)
                await cdp.inject_fingerprint()
                # Select country again
                await cdp.ev(f"""(function(){{
                    var sel = document.querySelector('select');
                    if(sel) {{
                        sel.value = '{COUNTRY_ISO}';
                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}
                }})()""")
                await asyncio.sleep(1)
                await cdp.focus_and_type('input[type="tel"]', full_phone)
                await asyncio.sleep(0.5)
                await cdp.click_submit()
                await asyncio.sleep(8)
                url = await cdp.url()
                retry_err = await snapshot_phone_error(cdp)
                if "log-in/password" not in (url or "") and not should_replace_phone(retry_err["reason"]):
                    break
                log(f"  [!] Number #{retry_num} also rejected: {retry_err['reason'] or 'already_registered'}")
                cancel_number(act_id)
            final_retry_err = await snapshot_phone_error(cdp)
            if "log-in/password" in (url or "") or should_replace_phone(final_retry_err["reason"]):
                log(f"  ✗ All numbers rejected/used! last_reason={final_retry_err['reason'] or 'already_registered'}")
                return None
            password = random_password()
            log(f"  Password (updated): {password}")
        
        # Should be on create-account/password page
        if "password" not in (url or ""):
            # Wait a bit more
            await asyncio.sleep(4)
            url = await cdp.url()
            log(f"  [4b] Recheck: {url}")
        
        if "password" not in (url or ""):
            log(f"  ✗ Unexpected page: {url}")
            cancel_number(act_id)
            return None
        
        # Set password - type character by character via CDP keyboard events
        # First click and focus the password field
        await cdp.ev("var el=document.querySelector('input[type=\"password\"]'); if(el){el.focus(); el.click();}")
        await asyncio.sleep(0.3)
        # Type each character
        for ch in password:
            await cdp.send("Input.dispatchKeyEvent", {
                "type": "keyDown", "text": ch, "key": ch,
                "code": "", "windowsVirtualKeyCode": ord(ch)
            })
            await cdp.send("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": ch,
                "code": "", "windowsVirtualKeyCode": ord(ch)
            })
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.5)
        pwd_len = await cdp.ev("document.querySelector('input[type=\"password\"]')?.value?.length || 0")
        log(f"  [5] Password typed char-by-char, length={pwd_len}")
        if not pwd_len or pwd_len == 0:
            log("  [5] WARNING: password field still empty after typing!")

        # Submit password form
        await asyncio.sleep(0.5)
        pwd_submit_result = await cdp.click_submit_exact(["validate"])
        log(f"  [5] password submit result: {pwd_submit_result}")
        await asyncio.sleep(10)
        url = await cdp.url()
        # Diagnostic: capture page state after submit
        page_text_after = await cdp.text(500)
        log(f"  [5d] URL after submit: {url}")
        log(f"  [5d] Page text (first 300): {(page_text_after or '')[:300]}")
        # Check for error messages
        error_text = await cdp.ev("(function(){ var el = document.querySelector('[role=alert], .error, [class*=error], [class*=Error]'); return el ? el.textContent.trim().slice(0,200) : ''; })()")
        log(f"  [5d] Error element: {error_text}")
        # Check if password input still has value
        pwd_val = await cdp.ev("document.querySelector('input[type=\"password\"]')?.value?.length || 0")
        log(f"  [5d] Password input length: {pwd_val}")
        
        # Handle timeout errors and retry
        for retry_i in range(3):
            page_text = await cdp.text(300)
            if "timed out" in (page_text or "").lower() or "error occurred" in (page_text or "").lower():
                log(f"  [5r] Timeout/error detected (attempt {retry_i+1}/3), clicking Try again...")
                # Click "Try again" button
                await cdp.ev("""(function(){
                    var btns = Array.from(document.querySelectorAll('button, a'));
                    var btn = btns.find(function(b){ return b.textContent.trim().toLowerCase().includes('try again'); });
                    if(btn) { btn.click(); return 'clicked'; }
                    // Also try reload
                    location.reload();
                    return 'reloaded';
                })()"""  )
                await asyncio.sleep(8)
                url = await cdp.url()
                # If back on password page, re-enter password and submit
                if "password" in (url or ""):
                    await cdp.type_password(password)
                    await asyncio.sleep(0.5)
                    await cdp.click_submit_exact(["validate"])
                    await asyncio.sleep(10)
                    url = await cdp.url()
                    page_text = await cdp.text(200)
                    if "timed out" not in (page_text or "").lower():
                        break
            elif "create-account/password" in (url or ""):
                log("  [5r] Still on password page, retrying submit...")
                await cdp.click_submit_exact(["validate"])
                await asyncio.sleep(10)
                url = await cdp.url()
            else:
                break
        
        log(f"  [5] After password: {url}")
        pwd_phone_err = await snapshot_phone_error(cdp)
        if pwd_phone_err["reason"]:
            log(f"  [5e] Phone verification error after password: {pwd_phone_err['reason']} action={pwd_phone_err['action']}")
        
        if should_replace_phone(pwd_phone_err["reason"]):
            log("  ✗ Phone rejected after password submit")
            cancel_number(act_id)
            return None
        if "create-account/password" in (url or "") or "error" in (page_text or "").lower():
            log("  ✗ Password submit failed after retries")
            cancel_number(act_id)
            return None
        
        # Wait for SMS
        sms_code = None
        for sms_attempt in range(1, 4):
            if sms_attempt > 1:
                schedule_cancel_number(act_id)
                await asyncio.sleep(1)
                act_id, phone = buy_number()
                if not act_id:
                    log("  ✗ Failed to buy replacement number")
                    return None
                log(f"  [6c] New number #{sms_attempt}: +{phone}")
                # Go back and re-enter
                await cdp.ev("window.history.back()")
                await asyncio.sleep(4)
                await cdp.ev("window.history.back()")
                await asyncio.sleep(4)
                full_phone = f"+{phone}"
                await cdp.ev(f"""(function(){{
                    var sel = document.querySelector('select');
                    if(sel) {{
                        sel.value = '{COUNTRY_ISO}';
                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}
                }})()""")
                await asyncio.sleep(1)
                await cdp.focus_and_type('input[type="tel"]', full_phone)
                await asyncio.sleep(0.5)
                await cdp.click_submit()
                await asyncio.sleep(6)
                await cdp.type_password(password)
                await asyncio.sleep(0.5)
                await cdp.click_submit()
                await asyncio.sleep(8)
                repl_err = await snapshot_phone_error(cdp)
                if should_replace_phone(repl_err["reason"]):
                    log(f"  [6e] Replacement number rejected after submit: {repl_err['reason']}")
                    continue
            
            page_err = await snapshot_phone_error(cdp)
            if page_err["reason"]:
                log(f"  [6e] Phone/SMS page error before polling: {page_err['reason']} action={page_err['action']}")
                if should_replace_phone(page_err["reason"]):
                    sms_code = None
                    continue
            log(f"  [6] Waiting for SMS (attempt {sms_attempt}/3, timeout=60s)...")
            sms_code = get_sms(act_id, timeout=60)
            if sms_code:
                break
            if sms_attempt < 3:
                log("  [6b] SMS timeout, trying next number...")
        
        if not sms_code:
            log("  ✗ SMS failed after 3 attempts!")
            cancel_number(act_id)
            return None
        log(f"  [6] SMS code: {sms_code}")
        
        # Enter SMS code
        await cdp.focus_and_type('input', sms_code)
        await asyncio.sleep(0.3)
        await cdp.click_submit()
        await asyncio.sleep(8)
        url = await cdp.url()
        log(f"  [7] After SMS code: {url}")
        code_err = await snapshot_phone_error(cdp)
        if code_err["reason"]:
            log(f"  [7e] Verification code/page error: {code_err['reason']} action={code_err['action']}")
            if should_replace_phone(code_err["reason"]):
                cancel_number(act_id)
                return None
        
        # Handle about-you/profile page
        if "about-you" in (url or "") or "signup/profile" in (url or "") or "create-account/profile" in (url or ""):
            log("  [8] Filling about-you/profile...")
            first_names = ["Alex","Sam","Jordan","Taylor","Morgan","Casey","Riley","Quinn"]
            last_names = ["Martin","Taylor","Brown","Wilson","Clark","Lewis","Walker","Hall"]
            full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
            birth_year = random.randint(1988, 2002)
            birth_month = random.randint(1, 12)
            birth_day = random.randint(1, 28)
            age = str(max(18, min(35, time.localtime().tm_year - birth_year)))

            about_state = await cdp.ev(f"""(function(){{
                const fullName = {json.dumps(full_name)};
                const age = {json.dumps(age)};
                const birthday = {json.dumps(f'{birth_year}-{birth_month:02d}-{birth_day:02d}')};
                function vis(e) {{ const s=getComputedStyle(e), r=e.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }}
                function setVal(el, val) {{
                    if (!el) return false;
                    el.scrollIntoView({{block:'center'}}); el.focus(); try {{ el.click(); }} catch(e) {{}}
                    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
                    if (desc && desc.set) desc.set.call(el, ''); else el.value = '';
                    el.dispatchEvent(new Event('input', {{bubbles:true}}));
                    if (desc && desc.set) desc.set.call(el, val); else el.value = val;
                    el.dispatchEvent(new Event('input', {{bubbles:true}}));
                    el.dispatchEvent(new Event('change', {{bubbles:true}}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {{bubbles:true, key:'Unidentified'}}));
                    return true;
                }}
                const nameInput = Array.from(document.querySelectorAll('input[name="name"], input[autocomplete="name"], input[placeholder*="全名"], input[placeholder*="name" i]')).find(vis);
                const ageInput = Array.from(document.querySelectorAll('input[name="age"]')).find(vis);
                const birthdayInput = document.querySelector('input[name="birthday"]');
                const y = document.querySelector('[role="spinbutton"][data-type="year"]');
                const m = document.querySelector('[role="spinbutton"][data-type="month"]');
                const d = document.querySelector('[role="spinbutton"][data-type="day"]');
                const filled = {{name:setVal(nameInput, fullName), age:false, birthday:false, consent:false}};
                if (ageInput) filled.age = setVal(ageInput, age);
                if (!ageInput && birthdayInput) filled.birthday = setVal(birthdayInput, birthday);
                if (!ageInput && y && m && d) {{ filled.birthday = setVal(y, String({birth_year})) && setVal(m, String({birth_month}).padStart(2,'0')) && setVal(d, String({birth_day}).padStart(2,'0')); }}
                const cb = Array.from(document.querySelectorAll('input[type="checkbox"]')).find(vis);
                if (cb && !cb.checked) {{ const label = cb.closest('label'); try {{ (label || cb).click(); filled.consent = true; }} catch(e) {{}} }}
                const buttons = Array.from(document.querySelectorAll('button,input[type=submit]')).filter(vis).map(b=>({{text:(b.innerText||b.value||b.textContent||'').trim(), disabled:!!b.disabled, ariaDisabled:b.getAttribute('aria-disabled')||''}}));
                return {{filled, buttons, text:(document.body && document.body.innerText || '').slice(0,500)}};
            }})()""", timeout=15)
            log(f"  [8] about-you state: {json.dumps(about_state, ensure_ascii=False)[:800]}")
            await asyncio.sleep(0.8)

            for submit_i in range(1, 4):
                finish_rect = await cdp.ev("""(function(){
                    function vis(e){ if(!e) return false; var s=getComputedStyle(e), r=e.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }
                    var btn = Array.from(document.querySelectorAll('button,input[type=submit],[role=button]')).find(function(b){
                        var t = (b.innerText||b.value||b.textContent||'').trim().toLowerCase();
                        return vis(b) && !b.disabled && b.getAttribute('aria-disabled') !== 'true' && ['完成帐户创建','完成','创建','continue','finish','done'].some(function(x){ return t.includes(x); });
                    });
                    if(!btn) return null;
                    btn.scrollIntoView({block:'center', inline:'center'});
                    var r = btn.getBoundingClientRect();
                    return {x:r.x,y:r.y,width:r.width,height:r.height,text:(btn.innerText||btn.value||btn.textContent||'').trim()};
                })()""", timeout=10)
                if finish_rect:
                    clicked = await cdp._click_center(finish_rect)
                    click_result = {'ok': bool(clicked), 'method': 'cdpMouseFirst', 'rect': finish_rect}
                else:
                    click_result = await cdp.click_submit()
                log(f"  [8] submit attempt {submit_i}: {click_result}")
                await asyncio.sleep(5 if submit_i == 1 else 3)
                await cdp.ev("""(function(){
                    var btns = Array.from(document.querySelectorAll('button,input[type=submit]'));
                    var c = btns.find(function(b){
                        var t = (b.innerText||b.value||b.textContent||'').trim().toLowerCase();
                        return ['confirm','确定','continue','继续','done','finish'].some(function(x){return t.includes(x);});
                    });
                    if(c && !c.disabled && c.getAttribute('aria-disabled') !== 'true') c.click();
                })()""")
                await asyncio.sleep(4)
                url = await cdp.url()
                if "about-you" not in (url or "") and "signup/profile" not in (url or "") and "create-account/profile" not in (url or ""):
                    break
            if "about-you" in (url or "") or "signup/profile" in (url or "") or "create-account/profile" in (url or ""):
                about_diag = await cdp.ev("""(function(){
                    function vis(e){const s=getComputedStyle(e), r=e.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;}
                    return {
                      inputs:Array.from(document.querySelectorAll('input')).filter(vis).map(i=>({name:i.name||'', type:i.type||'', placeholder:i.placeholder||'', aria:i.getAttribute('aria-label')||'', value:i.value||'', disabled:!!i.disabled})).slice(0,12),
                      buttons:Array.from(document.querySelectorAll('button,input[type=submit]')).filter(vis).map(b=>({text:(b.innerText||b.value||b.textContent||'').trim(), disabled:!!b.disabled, ariaDisabled:b.getAttribute('aria-disabled')||''})).slice(0,12),
                      text:(document.body && document.body.innerText || '').slice(0,1000)
                    };
                })()""", timeout=10)
                log(f"  [8] about-you still visible: {json.dumps(about_diag, ensure_ascii=False)[:1200]}")
            log(f"  [8] After about-you: {url}")
        
        # Check success
        if "chatgpt.com" in (url or "") and "auth" not in (url or ""):
            log("  ✓ Registration successful!")
            finish_number(act_id)
            return {"phone": phone, "password": password, "act_id": act_id}
        
        # Error recovery
        if "error" in (url or "") or "500" in (url or ""):
            log("  [!] Error page, checking if account was created...")
            await cdp.ev("window.location.href = 'https://chatgpt.com/'")
            await asyncio.sleep(8)
            url = await cdp.url()
            if "chatgpt.com" in (url or "") and "auth" not in (url or ""):
                log("  ✓ Account created despite error!")
                finish_number(act_id)
                return {"phone": phone, "password": password, "act_id": act_id}
        
        log(f"  ✗ Registration failed, final URL: {url}")
        cancel_number(act_id)
        return None


async def main():
    target_count = _args.count
    
    log("=" * 60)
    log(f"  BATCH REGISTER + IMPORT v2 ({target_count} accounts)")
    log("=" * 60)
    
    # Login/import backend once
    token = panel_login()
    log(f"[0] Panel mode: {PANEL_MODE} OK")
    
    success = 0
    failed = 0
    
    for i in range(1, target_count + 1):
        log(f"\n{'='*60}")
        log(f"  ACCOUNT {i}/{target_count}")
        log(f"{'='*60}")
        
        # Restart Chrome with fresh fingerprint for each account
        log("[Fingerprint] Restarting Chrome with new profile...")
        if not restart_chrome_with_fingerprint():
            log("  ✗ Chrome CDP failed before buying number; skipping account")
            failed += 1
            continue
        await asyncio.sleep(3)
        
        # Phase 1: Register
        log("[Phase 1] Registering...")
        result = await register_account()
        
        if not result:
            failed += 1
            log(f"  Registration failed. Success: {success}, Failed: {failed}")
            # Random delay between attempts
            delay = random.randint(10, 30)
            log(f"  Waiting {delay}s before next attempt...")
            await asyncio.sleep(delay)
            continue
        
        phone = result["phone"]
        password = result["password"]
        account_email, email_jwt = random_email()
        
        log(f"\n[Phase 2] OAuth import...")
        log(f"  Email: {account_email}")
        
        # Phase 2: OAuth import
        import subprocess as _sp
        helper = os.path.join(os.path.dirname(__file__), "gptfree_cpa_existing_account.py")
        prefix = "gptcpa" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        cmd = [sys.executable, "-u", helper,
               "--phone", f"+{phone}", "--password", password,
               "--email-prefix", prefix, "--start-chrome", "--close-chrome",
               "--otp-timeout", "120"]
        log(f"  Calling helper: phone=+{phone} prefix={prefix}")
        proc = _sp.run(cmd, capture_output=True, text=True, timeout=300)
        helper_output = proc.stdout + proc.stderr
        log(helper_output.strip()[-500:])  # last 500 chars
        imported = proc.returncode == 0 and ("callback" in helper_output.lower() or "ok" in helper_output.lower())
        account_email = f"{prefix}@{EMAIL_DOMAIN}"  # Cloud Mail email used by helper
        
        if imported:
            success += 1
            record = {
                "cpa_email": account_email,
                "phone": f"+{phone}",
                "password": password,
                "oauth_imported": True,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")
            }
            with open(os.path.expanduser("~/.hermes/accounts/gptfree-chatgpt-accounts-new.jsonl"), "a") as f:
                f.write(json.dumps(record) + "\n")
            log(f"  ✓ DONE! Total success: {success}/{i}")
        else:
            failed += 1
            record = {
                "phone": f"+{phone}",
                "password": password,
                "oauth_imported": False,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")
            }
            with open(os.path.expanduser("~/.hermes/accounts/gptfree-chatgpt-accounts-new.jsonl"), "a") as f:
                f.write(json.dumps(record) + "\n")
            log(f"  ✗ OAuth failed, saved phone+password for retry. Total: {success} success, {failed} failed")
        
        # Random delay between accounts to avoid patterns
        delay = random.randint(15, 45)
        log(f"  Waiting {delay}s before next account...")
        await asyncio.sleep(delay)
    
    log(f"\n{'='*60}")
    log(f"  FINAL: {success} imported, {failed} failed out of {target_count}")
    log(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
