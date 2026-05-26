import sys
import time

sys.argv = ["batch_register_v2.py", "0"]
import batch_register_v2 as batch


def test_extract_openai_code_ignores_css_colors_and_returns_real_code():
    msg = {
        "sendEmail": "noreply@tm.openai.com",
        "subject": "OpenAI 验证码",
        "content": """
        <style>.x{color:#202123;background:#353740}</style>
        输入此临时验证码以继续：
        <div>369102</div>
        """,
    }
    assert batch.extract_openai_code(msg) == "369102"


def test_wait_cpa_auth_status_retries_until_ok(monkeypatch):
    calls = []

    def fake_cpa_request(method, path, data=None):
        calls.append((method, path, data))
        if len(calls) < 3:
            return {"status": "wait"}
        return {"status": "ok"}

    monkeypatch.setattr(batch, "cpa_request", fake_cpa_request)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    assert batch.wait_cpa_auth_status("abc123", timeout=5, interval=0.01) is True
    assert len(calls) == 3
    assert calls[-1][1] == "/v0/management/get-auth-status?state=abc123"
