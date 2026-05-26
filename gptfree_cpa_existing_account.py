#!/usr/bin/env python3
"""CPA OAuth import for an already-created ChatGPT/OpenAI account.

This is the Phase-2-only companion to batch_register_v2.py:
- generate a fresh CPA Codex OAuth URL/state
- open it in an existing Chrome CDP session
- select the current logged-in OpenAI account or perform phone/password login
- create/use a local Cloud Mail inbox for add-email
- submit only the newest OpenAI verification OTP
- complete CPA callback and optionally verify the new auth file

It does NOT buy HeroSMS numbers and does NOT register a new ChatGPT account.
"""
import argparse
import asyncio
import json
import os
import random
import shutil
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import websockets

from cloud_mail_local import (
    create_cloud_mail_address,
    extract_six_digit_code,
    get_cloud_mail_config,
    get_cloud_mail_messages,
    get_cloud_mail_token,
)

DEFAULT_CPA_URL = os.environ.get("GPTFREE_CPA_URL", "http://127.0.0.1:8317").rstrip("/")
DEFAULT_CDP_PORT = int(os.environ.get("GPTFREE_CDP_PORT", "9336"))
DEFAULT_STATE_DIR = Path(os.path.expanduser(os.environ.get(
    "GPTFREE_CPA_STATE_DIR", "~/.gptfree/state/gptfree-cpa-existing-account"
)))

# Dial code → ISO country code mapping (most common for GPTFree)
_DIAL_TO_ISO = {
    "44": "GB", "56": "CL", "1": "US", "81": "JP", "86": "CN",
    "91": "IN", "55": "BR", "49": "DE", "33": "FR", "39": "IT",
    "34": "ES", "7": "RU", "82": "KR", "61": "AU",
    "31": "NL", "46": "SE", "47": "NO", "45": "DK", "358": "FI",
    "48": "PL", "43": "AT", "41": "CH", "32": "BE", "351": "PT",
    "90": "TR", "52": "MX", "54": "AR", "57": "CO", "51": "PE",
    "63": "PH", "66": "TH", "84": "VN", "62": "ID", "60": "MY",
    "65": "SG", "852": "HK", "886": "TW", "234": "NG", "27": "ZA",
}

def _split_phone(phone_digits):
    """Split phone digits into (dial_code, national_number).
    Tries longest dial code match first."""
    for length in (3, 2, 1):
        prefix = phone_digits[:length]
        if prefix in _DIAL_TO_ISO:
            return prefix, phone_digits[length:]
    return "", phone_digits

def _dial_to_iso(dial_code):
    """Map dial code string to ISO country code."""
    return _DIAL_TO_ISO.get(dial_code, "")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def read_cpa_management_key():
    key = os.environ.get("GPTFREE_CPA_MANAGEMENT_KEY")
    if key:
        return key.strip().strip('"').strip("'")
    env_path = Path(os.path.expanduser(os.environ.get("GPTFREE_CPA_ENV_FILE", "~/.gptfree/cpa.env")))
    if env_path.exists():
        for line in env_path.read_text(errors="ignore").splitlines():
            if line.startswith("MANAGEMENT_PASSWORD="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def cpa_request(method, path, data=None, cpa_url=DEFAULT_CPA_URL, management_key=None, timeout=25):
    management_key = management_key or read_cpa_management_key()
    if not management_key:
        raise RuntimeError("CPA management key missing; set GPTFREE_CPA_MANAGEMENT_KEY or GPTFREE_CPA_ENV_FILE")
    url = cpa_url + path
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-Management-Key", management_key)
    req.add_header("Authorization", f"Bearer {management_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CPA HTTP {exc.code}: {text[:300]}") from None
    try:
        return json.loads(text) if text else {}
    except json.JSONDecodeError:
        raise RuntimeError(f"CPA returned non-JSON: {text[:300]}") from None


def generate_cpa_oauth(cpa_url=DEFAULT_CPA_URL, management_key=None):
    resp = cpa_request("GET", "/v0/management/codex-auth-url", cpa_url=cpa_url, management_key=management_key)
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    url = data.get("auth_url") or data.get("url")
    state = data.get("state") or ""
    if not url or not state:
        raise RuntimeError(f"CPA OAuth response missing url/state: {json.dumps(resp)[:300]}")
    return {"url": url, "state": state, "raw": resp}


def save_oauth_json(oauth, state_dir=DEFAULT_STATE_DIR):
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "oauth.json"
    path.write_text(json.dumps(oauth, ensure_ascii=False, indent=2))
    return path


def list_pages(cdp_port):
    with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=5) as resp:
        targets = json.load(resp)
    return [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]


def create_tab(cdp_port, url="about:blank"):
    req = urllib.request.Request(f"http://127.0.0.1:{cdp_port}/json/new?{urllib.parse.quote(url, safe=':/?=&')}", method="PUT")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.load(resp)


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self.mid = 0

    async def send(self, method, params=None, timeout=20):
        self.mid += 1
        mid = self.mid
        cmd = {"id": mid, "method": method}
        if params is not None:
            cmd["params"] = params
        await self.ws.send(json.dumps(cmd))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=min(3, max(0.1, deadline - time.time())))
            except asyncio.TimeoutError:
                continue
            msg = json.loads(raw)
            if msg.get("id") == mid:
                if "error" in msg:
                    return msg
                return msg.get("result", {})
        return None

    async def ev(self, expr, timeout=15):
        r = await self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, timeout=timeout)
        if not isinstance(r, dict):
            return None
        if "result" in r:
            return r.get("result", {}).get("value")
        return r.get("value")

    async def url(self):
        return await self.ev("location.href")

    async def title(self):
        return await self.ev("document.title")

    async def text(self, n=1200):
        return await self.ev(f"(document.body && document.body.innerText || '').slice(0,{int(n)})")

    async def snapshot(self):
        return {
            "url": await self.url(),
            "title": await self.title(),
            "text": await self.text(1200),
        }

    async def screenshot(self, path):
        r = await self.send("Page.captureScreenshot", {"format": "png", "fromSurface": True}, timeout=20)
        if not isinstance(r, dict) or not r.get("data"):
            return None
        import base64
        Path(path).write_bytes(base64.b64decode(r["data"]))
        return path

    async def click_text(self, needles):
        if isinstance(needles, str):
            needles = [needles]
        return await self.ev(f"""(() => {{
            const needles = {json.dumps([str(x).lower() for x in needles], ensure_ascii=False)};
            function vis(e) {{ const s=getComputedStyle(e), r=e.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }}
            const els = Array.from(document.querySelectorAll('button,a,[role=button],input[type=submit]')).filter(vis);
            const el = els.find(e => {{
              const t=((e.innerText||e.value||e.textContent||'')+'').trim().toLowerCase();
              return needles.some(n => t.includes(n));
            }});
            if (!el) return {{ok:false, reason:'not_found', texts:els.map(e=>(e.innerText||e.value||e.textContent||'').trim()).slice(0,10)}};
            el.scrollIntoView({{block:'center'}}); el.focus();
            try {{ el.click(); return {{ok:true, text:(el.innerText||el.value||el.textContent||'').trim()}}; }} catch(e) {{}}
            el.dispatchEvent(new MouseEvent('click', {{bubbles:true,cancelable:true,view:window}}));
            return {{ok:true, text:(el.innerText||el.value||el.textContent||'').trim(), method:'dispatch'}};
        }})()""", timeout=10)

    async def click_account_card(self):
        return await self.ev(r"""(() => {
            function vis(e) { const s=getComputedStyle(e), r=e.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }
            const els = Array.from(document.querySelectorAll('button,a,[role=button]')).filter(vis);
            const el = els.find(e => /选择帐户|choose account|Lucy|\+56|@/.test((e.innerText||e.textContent||''))) || els[0];
            if (!el) return {ok:false, reason:'not_found'};
            el.scrollIntoView({block:'center'}); el.focus(); el.click();
            return {ok:true, text:(el.innerText||el.textContent||'').trim()};
        })()""", timeout=10)

    async def cdp_type_text(self, text):
        """Type text character by character using CDP key events — triggers React handlers."""
        for ch in text:
            await self.ws.send(json.dumps({"id": 1, "method": "Input.dispatchKeyEvent", "params": {"type": "keyDown", "text": ch, "key": ch, "unmodifiedText": ch}}))
            await self.ws.send(json.dumps({"id": 1, "method": "Input.dispatchKeyEvent", "params": {"type": "keyUp", "key": ch}}))

    async def cdp_fill_input(self, selector, value):
        """Focus element, select all, then type via CDP — works with React phone inputs."""
        focus_ok = await self.ev(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return false;
            el.scrollIntoView({{block:'center'}});
            el.focus();
            el.click();
            el.setSelectionRange(0, el.value.length);
            return true;
        }})()""")
        if not focus_ok:
            return {"ok": False, "reason": "not_found"}
        # Delete selected text via Ctrl+A then Backspace
        for key in ["a", "Backspace"]:
            mods = 2 if key == "a" else 0
            down = {"type": "keyDown", "key": key, "code": f"Key{key.upper()}" if key == "a" else key, "modifiers": mods}
            up = {"type": "keyUp", "key": key, "code": f"Key{key.upper()}" if key == "a" else key, "modifiers": mods}
            await self.ws.send(json.dumps({"id": 1, "method": "Input.dispatchKeyEvent", "params": down}))
            await self.ws.send(json.dumps({"id": 1, "method": "Input.dispatchKeyEvent", "params": up}))
        # Type the value char by char (triggers React handlers)
        await self.cdp_type_text(value)
        # Read back
        actual = await self.ev(f"document.querySelector({json.dumps(selector)})?.value || ''")
        return {"ok": True, "value": actual}

    async def fill_visible_input(self, selector, value):
        """FlowPilot-compatible: native setter clear → click → set → input + change + keyup."""
        return await self.ev(f"""(() => {{
            const selector = {json.dumps(selector)};
            const value = {json.dumps(str(value))};
            function vis(e) {{ const s=getComputedStyle(e), r=e.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }}
            const el = Array.from(document.querySelectorAll(selector)).find(vis);
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
            return {{ok:true, value:el.value, length:(el.value||'').length}};
        }})()""", timeout=10)

    async def click_submit_exact(self, values=None):
        values = values or []
        return await self.ev(f"""(() => {{
            const values = {json.dumps(values)};
            function vis(e) {{ const s=getComputedStyle(e), r=e.getBoundingClientRect(); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; }}
            let btns = Array.from(document.querySelectorAll('button,input[type=submit]')).filter(vis).filter(b => !b.disabled && b.getAttribute('aria-disabled') !== 'true');
            let btn = values.length ? btns.find(b => values.includes(b.value)) : null;
            if (!btn) btn = btns.find(b => /继续|continue|allow|authorize|允许|授权/.test((b.innerText||b.value||b.textContent||'')));
            if (!btn) return {{ok:false, reason:'not_found'}};
            btn.scrollIntoView({{block:'center'}}); btn.focus(); btn.click();
            return {{ok:true, text:(btn.innerText||btn.value||btn.textContent||'').trim(), value:btn.value||''}};
        }})()""", timeout=10)


def message_ts(message):
    for key in ("createdAt", "created_at", "date", "time", "timestamp", "receivedAt"):
        value = message.get(key) if isinstance(message, dict) else None
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value) / (1000 if value > 10_000_000_000 else 1)
        text = str(value)
        try:
            from email.utils import parsedate_to_datetime
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
    fields = [str(message.get(k) or "") for k in ("from", "fromEmail", "sender", "sendEmail", "sendName", "subject", "title", "content", "html", "text", "plainText", "body")]
    combined = "\n".join(fields)
    if not re.search(r"openai|chatgpt|verify|verification|验证码|验证", combined, re.I):
        return None
    # OpenAI HTML emails contain CSS color values such as #202123/#353740 before the real code.
    # Prefer the 6-digit number immediately after the explicit verification sentence.
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
    # In current OpenAI HTML templates the real code is usually the last 6-digit token;
    # earlier tokens are CSS colors. Avoid known color constants if present.
    filtered = [c for c in codes if c not in {"202123", "353740"}]
    return filtered[-1] if filtered else (codes[-1] if codes else None)


def create_or_reuse_cloud_mail_address(local_part):
    """Create a Cloud Mail address or return the existing address on duplicate.

    Cloud Mail reports duplicates as API errors. For deterministic helper runs the
    requested local part may already exist, so duplicate responses are treated as a
    successful reuse and reconstructed from the configured mail domain.
    """
    try:
        return create_cloud_mail_address(local_part)
    except RuntimeError as exc:
        msg = str(exc)
        if "已存在" in msg or "exist" in msg.lower():
            config = get_cloud_mail_config()
            domain = config.get("domain") or ""
            if not domain:
                raise
            return f"{local_part.strip().lower()}@{domain}"
        raise


def poll_latest_openai_otp(address, after_ts=0, timeout=120, interval=5):
    """Poll Cloud Mail and return the newest matching OpenAI verification code."""
    config = get_cloud_mail_config()
    token = get_cloud_mail_token(config)
    deadline = time.time() + timeout
    last_summary = ""
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
            candidates.append((ts, code, msg))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
        if messages:
            newest = messages[0]
            last_summary = json.dumps({k: newest.get(k) for k in ("from", "subject", "title", "createdAt", "date") if isinstance(newest, dict)}, ensure_ascii=False)[:240]
            log(f"  Cloud Mail checked, no matching OpenAI OTP yet; newest={last_summary}")
        else:
            log("  Cloud Mail checked, inbox empty")
        time.sleep(interval)
    return None


def wait_for_otp(address, after_ts=0, timeout=120, interval=5):
    """Wait for and return the latest OpenAI six-digit OTP from Cloud Mail.

    This public wrapper keeps the helper API explicit for tests and manual reuse;
    internally it delegates to poll_latest_openai_otp.
    """
    return poll_latest_openai_otp(address, after_ts=after_ts, timeout=timeout, interval=interval)


async def wait_until(cdp, pred, timeout=60, interval=2):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        snap = await cdp.snapshot()
        last = snap
        if pred(snap):
            return snap
        await asyncio.sleep(interval)
    return last


def callback_parts(url):
    if not url:
        return "", ""
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    return qs.get("code", [""])[0], qs.get("state", [""])[0]




# Chrome startup configuration (matching batch_register_v2.py)
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

def start_chrome(port=9336, user_data_dir="/tmp/chrome-gptfree-helper"):
    """Launch an isolated headless Chrome instance for Phase-2 OAuth.

    Existing helper Chrome processes for the same CDP port/profile are removed,
    a fresh temporary profile is started with remote debugging enabled, and the
    function returns the subprocess handle after CDP readiness succeeds.
    """
    # Kill existing Chrome instances
    try:
        ps = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
        for line in ps.splitlines()[1:]:
            pid_s, _, args = line.strip().partition(" ")
            if not pid_s.isdigit() or not args.startswith("/opt/google/chrome/chrome "):
                continue
            if f"remote-debugging-port={port}" in args or f"--user-data-dir={user_data_dir}" in args:
                try:
                    os.kill(int(pid_s), 9)
                except ProcessLookupError:
                    pass
    except Exception as exc:
        log(f"Chrome cleanup warning: {exc}")
    
    time.sleep(1)
    subprocess.run(["rm", "-rf", user_data_dir], capture_output=True, text=True)
    
    w, h = random.choice(WINDOW_SIZES)
    ua = random.choice(USER_AGENTS)
    
    # Build Chrome command
    chrome = shutil.which("google-chrome-stable") or shutil.which("google-chrome") or "/usr/bin/google-chrome"
    chrome += f" --remote-debugging-port={port} --remote-allow-origins='*'"
    chrome += f" --user-data-dir={user_data_dir}"
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
    chrome += " 'about:blank'"
    
    log(f"Starting Chrome: {w}x{h}, UA: ...{ua[-30:]}")
    proc = subprocess.Popen(chrome, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for Chrome to start
    for _ in range(10):
        time.sleep(1)
        try:
            import urllib.request
            targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3).read())
            pages = [t for t in targets if t.get("type") == "page"]
            if any((t.get("url") or "") == "about:blank" for t in pages):
                log(f"Chrome started successfully (PID: {proc.pid})")
                return proc
        except:
            pass
    
    log("Chrome failed to start within 10 seconds")
    return None

async def run_oauth(args):
    management_key = read_cpa_management_key()
    if args.dry_run:
        log(f"CPA URL: {args.cpa_url}")
        log(f"CPA key present: {bool(management_key)}")
        log(f"Cloud Mail domain: {get_cloud_mail_config().get('domain')}")
        pages = list_pages(args.cdp_port)
        log(f"CDP pages on {args.cdp_port}: {len(pages)}")
        return 0

    oauth = generate_cpa_oauth(args.cpa_url, management_key)
    state_dir = Path(args.state_dir) if args.state_dir else DEFAULT_STATE_DIR
    oauth_path = save_oauth_json(oauth, state_dir=state_dir)
    log(f"Generated fresh CPA OAuth state: {oauth['state'][:12]}... saved {oauth_path}")

    if args.email:
        account_email = args.email
        log(f"Using provided Cloud Mail email: {account_email}")
    else:
        account_email = create_or_reuse_cloud_mail_address(args.email_prefix)
        log(f"Created/reused Cloud Mail email: {account_email}")

    # Start Chrome if --start-chrome is set
    chrome_proc = None
    if args.start_chrome:
        chrome_proc = start_chrome(port=args.cdp_port)
        if not chrome_proc:
            log("Failed to start Chrome")
            return 1
    
    target = create_tab(args.cdp_port, "about:blank")
    ws_url = target["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url, max_size=10**7, open_timeout=10) as ws:
        cdp = CDP(ws)
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")
        await cdp.send("Network.enable")
        await cdp.send("Page.navigate", {"url": oauth["url"]}, timeout=10)
        await asyncio.sleep(8)
        snap = await cdp.snapshot()
        log(f"Landed: {snap['url']} | {str(snap['text']).splitlines()[0:2]}")

        if "choose-an-account" in (snap["url"] or "") or "选择一个帐户" in (snap["text"] or ""):
            r = await cdp.click_account_card()
            log(f"Clicked account card: {r}")
            await asyncio.sleep(8)
            snap = await cdp.snapshot()

        if "log-in" in (snap["url"] or "") and args.phone:
            # 1. Append usernameKind=phone_number to current URL and navigate
            current_url = snap["url"] or ""
            sep = "&" if "?" in current_url else "?"
            phone_url = current_url + sep + "usernameKind=phone_number"
            log(f"Navigating to phone login: {phone_url}")
            await cdp.send("Page.navigate", {"url": phone_url}, timeout=10)
            # 2. wait_until for phone input to appear (max 10s)
            snap = await wait_until(
                cdp,
                lambda s: "电话号码" in (s.get("text") or "") or "tel" in (s.get("text") or "").lower(),
                timeout=10, interval=1,
            )
            log(f"Phone page: {snap.get('url', '?')} | {str(snap.get('text', '')).splitlines()[:2]}")
            # 3. Select country + fill national number (FlowPilot pattern)
            phone_raw = re.sub(r'\D', '', args.phone.lstrip("+"))
            dial_code, national = _split_phone(phone_raw)
            iso = _dial_to_iso(dial_code)
            log(f"Dial: +{dial_code} ISO: {iso} national: {national}")
            if iso:
                sel = await cdp.ev(f"""(() => {{
                    const s = document.querySelector('select');
                    if (!s) return 'no_select';
                    s.value = {json.dumps(iso)};
                    s.dispatchEvent(new Event('change', {{bubbles:true}}));
                    return s.options[s.selectedIndex]?.text || s.value;
                }})()""")
                log(f"Country: {sel}")
                await asyncio.sleep(0.5)
            filled = await cdp.fill_visible_input('input[type="tel"]', national)
            log(f"Phone fill: {filled}")
            submitted = await cdp.click_submit_exact(["phone_number"])
            log(f"Submit: {submitted}")
            await asyncio.sleep(6)
            snap = await cdp.snapshot()
            log(f"After submit: {snap['url']} | {str(snap['text']).splitlines()[0:2]}")

        if "password" in (snap["url"] or "") and args.password:
            await cdp.fill_visible_input('input[type="password"]', args.password)
            await cdp.click_submit_exact(["validate"])
            await asyncio.sleep(8)
            snap = await cdp.snapshot()
            log(f"After password submit: {snap['url']} | {str(snap['text']).splitlines()[0:2]}")

        # Handle direct email-verification after password login (account already has email)
        if "email-verification" in (snap["url"] or "") and "add-email" not in (snap["url"] or ""):
            # Extract email from page text such as "code sent to user at domain".
            page_text = snap.get("text") or ""
            email_match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', page_text)
            otp_target_email = email_match.group(0) if email_match else account_email
            log(f"Direct email-verification: OTP sent to {otp_target_email}")
            otp_after = time.time() - 30  # OTP was likely sent before we arrived
            otp = poll_latest_openai_otp(otp_target_email, after_ts=otp_after, timeout=args.otp_timeout)
            if not otp:
                await cdp.screenshot(args.screenshot)
                log(f"No matching OpenAI OTP before timeout. Screenshot: {args.screenshot}")
                return 2
            log(f"Got OpenAI OTP: {otp}")
            await cdp.fill_visible_input('input[name="code"], input[type="text"]', otp)
            value = await cdp.ev("document.querySelector('input[name=code], input[type=text]')?.value || ''")
            if value != otp:
                log(f"OTP field mismatch, expected {otp}, got {value!r}; stopping before submit")
                return 3
            await cdp.click_submit_exact()
            await asyncio.sleep(8)
            snap = await cdp.snapshot()
            log(f"After OTP submit: {snap['url']} | {str(snap['text']).splitlines()[0:2]}")
            if "代码不正确" in (snap["text"] or "") or "incorrect" in (snap["text"] or "").lower():
                await cdp.screenshot(args.screenshot)
                log(f"OTP rejected once; stopping to avoid max_check_attempts. Screenshot: {args.screenshot}")
                return 4

        if "add-email" in (snap["url"] or "") or "要求提供电子邮件地址" in (snap["text"] or ""):
            log("Reached add-email; submitting Cloud Mail address")
            otp_after = time.time() - 5
            await cdp.fill_visible_input('input[type="email"]', account_email)
            await cdp.click_submit_exact()
            await asyncio.sleep(6)
            snap = await cdp.snapshot()
            if "email-verification" in (snap["url"] or "") or "验证码" in (snap["text"] or ""):
                log("Waiting latest OpenAI verification email")
                otp = poll_latest_openai_otp(account_email, after_ts=otp_after, timeout=args.otp_timeout)
                if not otp:
                    await cdp.screenshot(args.screenshot)
                    log(f"No matching OpenAI OTP before timeout. Screenshot: {args.screenshot}")
                    return 2
                log(f"Got OpenAI OTP: {otp}")
                await cdp.fill_visible_input('input[name="code"], input[type="text"]', otp)
                value = await cdp.ev("document.querySelector('input[name=code], input[type=text]')?.value || ''")
                if value != otp:
                    log(f"OTP field mismatch, expected {otp}, got {value!r}; stopping before submit")
                    return 3
                await cdp.click_submit_exact()
                await asyncio.sleep(8)
                snap = await cdp.snapshot()
                if "代码不正确" in (snap["text"] or "") or "incorrect" in (snap["text"] or "").lower():
                    await cdp.screenshot(args.screenshot)
                    log(f"OTP rejected once; stopping to avoid max_check_attempts. Screenshot: {args.screenshot}")
                    return 4

        if "consent" in (snap["url"] or "") or "authorize" in (snap["url"] or "").lower() or "授权" in (snap["text"] or ""):
            log("Trying Codex consent continue/allow")
            for _ in range(4):
                await cdp.click_submit_exact()
                await asyncio.sleep(5)
                snap = await cdp.snapshot()
                if "callback" in (snap["url"] or "") or "Authentication successful" in (snap["text"] or ""):
                    break

        current = await cdp.url()
        if "callback" not in (current or ""):
            hist = await cdp.send("Page.getNavigationHistory", timeout=10)
            entries = hist.get("entries", []) if isinstance(hist, dict) else []
            for entry in reversed(entries):
                u = entry.get("url", "")
                if "callback" in u and "code=" in u:
                    current = u
                    break
        log(f"Final OAuth URL: {current}")
        await cdp.screenshot(args.screenshot)

    code, cb_state = callback_parts(current)
    if not code:
        log(f"No callback code found. Screenshot: {args.screenshot}")
        return 5
    if cb_state and cb_state != oauth["state"]:
        log(f"State mismatch: callback={cb_state[:12]} expected={oauth['state'][:12]}")
        return 6

    callback_url = current
    resp = cpa_request("POST", "/v0/management/oauth-callback", {"provider": "codex", "redirect_url": callback_url}, cpa_url=args.cpa_url, management_key=management_key)
    log(f"CPA callback response: {json.dumps(resp, ensure_ascii=False)[:240]}")
    status = cpa_request("GET", f"/v0/management/get-auth-status?state={urllib.parse.quote(oauth['state'])}", cpa_url=args.cpa_url, management_key=management_key)
    log(f"CPA state status: {json.dumps(status, ensure_ascii=False)[:240]}")

    if args.verify:
        verify = subprocess.run([
            sys.executable,
            os.path.expanduser(os.environ.get(
                "GPTFREE_CPA_OAUTH_VERIFY_SCRIPT",
                "~/.gptfree/scripts/cpa-oauth-verify.py",
            )),
            "--email", account_email,
            "--oauth-json", str(oauth_path),
            "--marker", f"gptfree-existing-{int(time.time())}",
        ], capture_output=True, text=True, timeout=120)
        log("verify stdout:\n" + verify.stdout[-2000:])
        if verify.returncode != 0:
            log("verify stderr:\n" + verify.stderr[-1000:])
            return 7
    return 0


def build_arg_parser():
    """Build the command-line parser used by the CPA OAuth helper."""
    p = argparse.ArgumentParser(description="GPTFree Phase-2-only CPA OAuth for existing ChatGPT account")
    p.add_argument("--phone", help="Full phone number, e.g. +569****4304; optional when browser already has account chooser")
    p.add_argument("--password", help="OpenAI password; optional when browser session is already logged in")
    p.add_argument("--email", help="Existing email to bind/use; defaults to creating Cloud Mail address")
    p.add_argument("--email-prefix", help="Cloud Mail local part prefix/name, e.g. lucymartin2042")
    p.add_argument("--cdp-port", type=int, default=DEFAULT_CDP_PORT)
    p.add_argument("--cpa-url", default=DEFAULT_CPA_URL)
    p.add_argument("--otp-timeout", type=int, default=120)
    p.add_argument("--screenshot", default="/tmp/gptfree-cpa-existing-account.png")
    p.add_argument("--verify", action="store_true", help="Run CPA marker chat verification after callback")
    p.add_argument("--state-dir", default=None, help="Override state directory (for parallel runs)")
    p.add_argument("--start-chrome", action="store_true", help="Start a new Chrome instance before running")
    p.add_argument("--close-chrome", action="store_true", help="Kill Chrome after finishing (only if --start-chrome)")
    p.add_argument("--dry-run", action="store_true", help="Only check CPA key, Cloud Mail config, and CDP pages")
    return p


def main():
    """Parse helper CLI flags and execute Phase-2 CPA OAuth import.

    The helper can connect to an existing CDP browser or self-launch Chrome with
    --start-chrome. When paired with --close-chrome it also tears down the
    launched Chrome instance after OAuth completion.
    """
    p = build_arg_parser()
    args = p.parse_args()
    rc = asyncio.run(run_oauth(args))
    # Kill Chrome if --close-chrome is set
    if args.close_chrome and args.start_chrome:
        import subprocess as _sp
        _sp.run(["pkill", "-f", f"chrome.*remote-debugging-port={args.cdp_port}"],
                capture_output=True, timeout=5)
        log(f"Chrome on port {args.cdp_port} killed")
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
