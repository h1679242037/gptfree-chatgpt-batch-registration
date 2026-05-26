#!/usr/bin/env python3
"""
Auto-monitor Chile SMS stock and batch register when available.
- Checks stock every 5 minutes
- Runs 5 accounts per batch, verifies no phone waste
- Rotates proxy every 10 accounts
- Proxies: direct (no proxy), jp-residential, us99-ss, kkyun-ss
"""
import subprocess, json, time, os, sys
from datetime import datetime

HEROSMS_KEY = os.environ.get("HEROSMS_API_KEY", "")
HEROSMS = "https://hero-sms.com/stubs/handler_api.php"
# Chile only for now
COUNTRIES = [
    {"id": 151, "name": "Chile", "dial": "56", "iso": "CL"},
]
SERVICE = "dr"  # OpenAI
MAX_PRICE = 0.03  # Max price per number

MIHOMO_API = "http://127.0.0.1:9090"
PROXY_PORT = 7890

# Proxy rotation: each proxy gets 10 accounts max before switching
PROXIES = [
    {"name": "direct", "mihomo": None},           # No proxy (OC24 direct)
    {"name": "jp-residential", "mihomo": "jp-residential"},
    {"name": "us99-ss", "mihomo": "us99-ss"},
    {"name": "kkyun-ss", "mihomo": "kkyun-ss"},
]

BATCH_SIZE = 5
MAX_PER_PROXY = 10
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_register_v2.py")
LOG_DIR = os.path.expanduser(os.environ.get("GPTFREE_AUTO_BATCH_LOG_DIR", "~/.gptfree/auto_batch_logs"))
STATE_FILE = os.path.expanduser(os.environ.get("GPTFREE_AUTO_BATCH_STATE_FILE", "~/.gptfree/auto_batch_state.json"))

os.makedirs(LOG_DIR, exist_ok=True)

def log(msg):
    ts = datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"proxy_idx": 0, "accounts_on_current_proxy": 0, "total_success": 0, "total_failed": 0, "total_wasted_numbers": 0}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def _herosms_url(**params):
    from urllib.parse import urlencode
    return f"{HEROSMS}?{urlencode({'api_key': HEROSMS_KEY, **params})}"

def _curl_json(**params):
    r = subprocess.run(["curl", "-sS", "--max-time", "20", _herosms_url(**params)],
        capture_output=True, text=True, timeout=25)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

def check_stock_country(country_id):
    """FlowPilot-style non-purchasing stock preview for one country.

    Uses getTopCountriesByService/freePrice=true first so higher-price tiers are
    visible; falls back to getPrices. Returns (count, physical, lowest_price).
    """
    tiers = {}
    data = _curl_json(action="getTopCountriesByService", service=SERVICE, freePrice="true")
    if isinstance(data, dict):
        for entry in data.values():
            if not isinstance(entry, dict) or int(entry.get("country") or 0) != int(country_id):
                continue
            for price_raw, count_raw in (entry.get("freePriceMap") or {}).items():
                try:
                    price = round(float(price_raw), 4)
                    count = int(float(count_raw))
                except Exception:
                    continue
                if price > 0 and count > 0 and price <= MAX_PRICE:
                    tiers[price] = max(tiers.get(price, 0), count)
            try:
                price = round(float(entry.get("price") or entry.get("retail_price") or 0), 4)
                count = int(float(entry.get("count") or 0))
                if price > 0 and count > 0 and price <= MAX_PRICE:
                    tiers[price] = max(tiers.get(price, 0), count)
            except Exception:
                pass
            break
    if not tiers:
        data = _curl_json(action="getPrices", service=SERVICE, country=country_id)
        info = (data or {}).get(str(country_id), {}).get(SERVICE, {}) if isinstance(data, dict) else {}
        try:
            price = round(float(info.get("cost") or 0), 4)
            count = int(float(info.get("physicalCount") or info.get("count") or 0))
            if price > 0 and count > 0 and price <= MAX_PRICE:
                tiers[price] = count
        except Exception:
            pass
    if not tiers:
        # Preview endpoints can under-report stock while direct getNumber with
        # maxPrice still succeeds. Report one synthetic candidate so the batch
        # runner gets a chance to perform its real maxPrice probe.
        return 1, 1, MAX_PRICE
    lowest = min(tiers)
    total_visible = max(tiers.values())
    return total_visible, total_visible, lowest

def check_stock():
    """Check all countries, return first with stock: (country_info, count, physical, price)"""
    for c in COUNTRIES:
        count, physical, price = check_stock_country(c["id"])
        if count > 0 and price <= MAX_PRICE:
            return c, count, physical, price
    return None, 0, 0, 0

def switch_proxy(proxy_info):
    """Log selected proxy and optionally switch mihomo."""
    if proxy_info["mihomo"] is None:
        log(f"  Proxy: DIRECT (OC24 IP)")
    else:
        subprocess.run(["curl", "-s", "-X", "PUT",
            f"{MIHOMO_API}/proxies/GLOBAL",
            "-d", json.dumps({"name": proxy_info["mihomo"]})],
            capture_output=True, timeout=5)
        # Verify
        try:
            r = subprocess.run(["curl", "-s", "--proxy", f"http://127.0.0.1:{PROXY_PORT}",
                "--max-time", "10", "https://api.ipify.org"],
                capture_output=True, text=True, timeout=15)
            ip = r.stdout.strip()
            log(f"  Proxy: {proxy_info['name']} (IP: {ip})")
        except:
            log(f"  Proxy: {proxy_info['name']} (IP check failed)")

def run_batch(batch_size, country_info=None):
    """Run a batch of registrations, return (success, failed, wasted_numbers)."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    logfile = f"{LOG_DIR}/batch_{ts}.log"
    
    env = os.environ.copy()
    env["DISPLAY"] = ":99"
    
    # Pass country info to batch script
    cmd = ["python3", "-u", SCRIPT, str(batch_size)]
    if country_info:
        cmd += ["--country", str(country_info["id"]), "--dial", country_info["dial"], "--iso", country_info["iso"]]
    
    log(f"  Running batch of {batch_size} ({country_info['name'] if country_info else 'default'})...")
    output_lines = []
    timed_out = False
    with open(logfile, "w", buffering=1) as f:
        f.write(f"$ {' '.join(cmd)}\n")
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
        deadline = time.time() + 1800
        try:
            while True:
                line = p.stdout.readline() if p.stdout else ""
                if line:
                    output_lines.append(line)
                    f.write(line)
                    print(line, end="", flush=True)
                elif p.poll() is not None:
                    break
                elif time.time() > deadline:
                    timed_out = True
                    p.kill()
                    break
                else:
                    time.sleep(0.2)
        finally:
            rc = p.wait()
        footer = f"\n[monitor] returncode={rc} timed_out={timed_out}\n"
        output_lines.append(footer)
        f.write(footer)
        print(footer, end="", flush=True)
    
    output = "".join(output_lines)
    
    # Parse results
    success = 0
    failed = 0
    wasted = 0
    
    for line in output.split("\n"):
        if "✓✓✓ Account imported" in line:
            success += 1
        if "FINAL:" in line:
            # Parse "FINAL: X imported, Y failed out of Z"
            import re
            m = re.search(r"FINAL: (\d+) imported, (\d+) failed", line)
            if m:
                success = int(m.group(1))
                failed = int(m.group(2))
        # Detect wasted numbers: SMS received but then failed
        if "SMS code:" in line:
            # Check if this account eventually failed after getting SMS
            pass
    
    # Check for wasted numbers: count SMS codes received vs successful registrations
    sms_received = output.count("[6] SMS code:")
    registrations_ok = output.count("✓ Registration successful!")
    wasted = sms_received - registrations_ok  # If SMS received but registration failed = waste
    
    log(f"  Result: {success} imported, {failed} failed, {wasted} wasted numbers")
    log(f"  Log: {logfile}")
    
    return success, failed, wasted

def main():
    log("=" * 50)
    log("AUTO BATCH REGISTER - Chile SMS Monitor")
    log("=" * 50)
    
    state = load_state()
    log(f"State: proxy_idx={state['proxy_idx']}, on_current={state['accounts_on_current_proxy']}, total_success={state['total_success']}")
    
    consecutive_no_stock = 0
    
    while True:
        # Check stock across all countries
        active_country, count, physical, price = check_stock()
        
        if active_country is None or count == 0:
            consecutive_no_stock += 1
            # Adaptive wait: 5min normally, 15min after many checks
            wait = 300 if consecutive_no_stock < 12 else 900
            log(f"No stock (check #{consecutive_no_stock}). Next check in {wait//60}min...")
            time.sleep(wait)
            continue
        
        consecutive_no_stock = 0
        log(f"✓ Stock reported: {active_country['name']} count={count}, physical={physical}, price=${price}")
        
        # Do not verify stock with getNumber here: getNumber buys a real activation.
        # The batch script will buy using the same FlowPilot-style price tier logic.
        log("  Stock verified by non-purchasing FlowPilot-style price preview")
        
        # Check if we need to rotate proxy
        if state["accounts_on_current_proxy"] >= MAX_PER_PROXY:
            state["proxy_idx"] = (state["proxy_idx"] + 1) % len(PROXIES)
            state["accounts_on_current_proxy"] = 0
            log(f"  Rotating proxy -> {PROXIES[state['proxy_idx']]['name']}")
        
        # Set proxy
        proxy = PROXIES[state["proxy_idx"]]
        switch_proxy(proxy)
        
        # Run batch
        batch = min(BATCH_SIZE, count)
        try:
            success, failed, wasted = run_batch(batch, active_country)
        except subprocess.TimeoutExpired:
            log("  ⚠ Batch timed out (30min). Continuing...")
            success, failed, wasted = 0, batch, 0
        except Exception as e:
            log(f"  ⚠ Batch error: {e}. Continuing...")
            success, failed, wasted = 0, batch, 0
        
        # Update state
        state["total_success"] += success
        state["total_failed"] += failed
        state["total_wasted_numbers"] += wasted
        state["accounts_on_current_proxy"] += success
        save_state(state)
        
        # Report
        log(f"  TOTAL: {state['total_success']} success, {state['total_failed']} failed, {state['total_wasted_numbers']} wasted")
        
        # If wasted numbers detected, STOP and alert
        if wasted > 0:
            log("⚠️  WASTED NUMBERS DETECTED! Stopping for review.")
            break
        
        # If all failed (likely stock ran out mid-batch), wait before retry
        if success == 0 and failed > 0:
            log("  All failed, waiting 5min before retry...")
            time.sleep(300)
        else:
            # Brief pause between batches
            log("  Waiting 30s before next batch...")
            time.sleep(30)

if __name__ == "__main__":
    main()
