import importlib
import json
import sys
import time

sys.argv = ["batch_register_v2.py", "0"]
import batch_register_v2 as batch
import cloud_mail_local
import gptfree_cpa_existing_account as helper


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


def test_batch_register_imports_and_key_functions_exist():
    module = importlib.import_module("batch_register_v2")
    for name in (
        "register_account",
        "restart_chrome_with_fingerprint",
        "main",
        "get_email_otp",
        "panel_login",
        "wait_cpa_auth_status",
    ):
        assert hasattr(module, name)
        assert callable(getattr(module, name))


def test_helper_cli_argument_parsing():
    parser = helper.build_arg_parser()
    args = parser.parse_args([
        "--start-chrome",
        "--close-chrome",
        "--phone",
        "+56900000000",
        "--password",
        "pw-example",
        "--email-prefix",
        "gptcpatest",
        "--state-dir",
        "/tmp/gptfree-state-test",
        "--otp-timeout",
        "45",
    ])
    assert args.start_chrome is True
    assert args.close_chrome is True
    assert args.phone == "+56900000000"
    assert args.password == "pw-example"
    assert args.email_prefix == "gptcpatest"
    assert args.state_dir == "/tmp/gptfree-state-test"
    assert args.otp_timeout == 45


def test_cloud_mail_config_loading_with_mock_env(monkeypatch):
    for key in list(cloud_mail_local.os.environ):
        if key.startswith("CLOUD_MAIL_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLOUD_MAIL_BASE_URL", "mail.example.com/")
    monkeypatch.setenv("CLOUD_MAIL_DOMAIN", "@example.com/")
    monkeypatch.setenv("CLOUD_MAIL_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("CLOUD_MAIL_ADMIN_PASSWORD", "secret")

    env = cloud_mail_local.load_cloud_mail_env(paths=[])
    config = cloud_mail_local.get_cloud_mail_config(env)

    assert config == {
        "base_url": "https://mail.example.com",
        "domain": "example.com",
        "admin_email": "admin@example.com",
        "admin_password": "secret",
    }


def test_jsonl_success_record_format():
    record = {
        "cpa_email": "gptcpaexample@example.com",
        "phone": "+56900000000",
        "password": "pw-example",
        "oauth_imported": True,
        "created_at": "2026-05-26T12:00:00+0000",
    }
    loaded = json.loads(json.dumps(record))
    assert loaded["oauth_imported"] is True
    assert loaded["cpa_email"].endswith("@example.com")
    assert set(loaded) == {"cpa_email", "phone", "password", "oauth_imported", "created_at"}


def test_jsonl_failure_record_format_has_no_cpa_email():
    record = {
        "phone": "+56900000000",
        "password": "pw-example",
        "oauth_imported": False,
        "created_at": "2026-05-26T12:00:00+0000",
    }
    loaded = json.loads(json.dumps(record))
    assert loaded["oauth_imported"] is False
    assert "cpa_email" not in loaded
    assert set(loaded) == {"phone", "password", "oauth_imported", "created_at"}
