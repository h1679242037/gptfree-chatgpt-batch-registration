# Module: tests

当前仓库只有一个测试文件：`test_batch_cpa_helpers.py`。它通过导入 `batch_register_v2` 测试验证码提取和一个预期存在的 CPA auth status 轮询 helper。

## Key Files

- [`test_batch_cpa_helpers.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/test_batch_cpa_helpers.py) — pytest 测试文件。
- [`batch_register_v2.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/batch_register_v2.py) — 被测模块。

## 测试内容

### `test_extract_openai_code_ignores_css_colors_and_returns_real_code()`

- 构造一个 OpenAI 验证码邮件样例。
- 邮件 HTML 中包含 CSS 颜色值 `#202123`、`#353740`。
- 真实验证码为 `369102`。
- 断言 `batch.extract_openai_code(msg) == "369102"`。

对应源码函数存在：`batch_register_v2.extract_openai_code(message)`。

### `test_wait_cpa_auth_status_retries_until_ok(monkeypatch)`

- monkeypatch `batch.cpa_request`，前两次返回 `{"status": "wait"}`，第三次返回 `{"status": "ok"}`。
- monkeypatch `time.sleep` 为空操作。
- 期望调用 `batch.wait_cpa_auth_status("abc123", timeout=5, interval=0.01)` 返回 `True`。
- 期望最后请求路径为 `/v0/management/get-auth-status?state=abc123`。

当前源码问题：`batch_register_v2.py` 中不存在 `wait_cpa_auth_status()`，因此测试失败。

## 验证结果

在项目根目录运行：

```bash
python3 -m py_compile *.py
PYTHONPATH=. pytest -q
```

结果：

- `py_compile`：通过。
- `pytest`：1 个测试通过，1 个测试失败。
- 失败：`AttributeError: module 'batch_register_v2' has no attribute 'wait_cpa_auth_status'`。

## 依赖与副作用

- 测试文件在导入前设置 `sys.argv = ["batch_register_v2.py", "0"]`，用于规避 `batch_register_v2` 顶层 argparse 默认 count 参数。
- 测试没有真实调用 HeroSMS、CDP、CPA 或 Cloud Mail；`cpa_request` 被 monkeypatch。

## 后续修复方向

- 若 CPA status 轮询仍属于主脚本职责，应在 `batch_register_v2.py` 中补回 `wait_cpa_auth_status(state, timeout, interval)`。
- 若该逻辑已迁移到 `gptfree_cpa_existing_account.py`，应删除或更新该测试，改测 `generate_cpa_oauth()` / `callback_parts()` / `run_oauth()` 的可单测部分。
