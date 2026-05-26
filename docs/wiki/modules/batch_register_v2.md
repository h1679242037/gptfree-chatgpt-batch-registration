# Module: `batch_register_v2.py`

`batch_register_v2.py` 是项目主流程脚本，负责“购买手机号 → CDP 注册 ChatGPT → 获取短信 → 账号完成注册 → 调用 CPA helper 导入”的完整批处理。它同时包含 HeroSMS 客户端、Cloud Mail OTP 解析、Sub2API/CPA 请求 helper、Chrome 指纹启动器和 `CDP` 浏览器封装。

## 职责

- 读取 `GPTFREE_*`、`HEROSMS_API_KEY` 等环境变量并设置面板、国家、价格、邮箱、CDP 参数。
- 用 HeroSMS 兼容接口预览价格档、购买手机号、轮询短信、取消/完成 activation。
- 重启带随机窗口尺寸和 User-Agent 的 Chrome，并连接 `http://127.0.0.1:9336/json/list` 返回的 page websocket。
- 通过 CDP 操作 OpenAI/ChatGPT 登录注册页：选择手机号注册、填写电话、设置密码、提交短信验证码、填写 about-you/profile。
- 处理手机号已用、号码无效、短信无法发送、验证码错误、页面 500/timeout 等页面文本错误。
- 注册成功后以子进程调用 `gptfree_cpa_existing_account.py` 完成 CPA/Codex OAuth 导入。
- 将注册结果追加到 `~/.hermes/accounts/gptfree-chatgpt-accounts-new.jsonl`。

## 关键文件

- [`batch_register_v2.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/batch_register_v2.py) — 本模块全部逻辑。
- [`cloud_mail_local.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/cloud_mail_local.py) — 被导入用于 Cloud Mail 地址创建和邮件列表读取。
- [`gptfree_cpa_existing_account.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/gptfree_cpa_existing_account.py) — 注册成功后由子进程调用的 Phase 2 helper。

## Public API / 主要函数

### 手机号与 HeroSMS

- `hero_sms_price_tiers(country=COUNTRY, max_price=MAX_PRICE)` — 读取 HeroSMS 价格/库存档位，返回 `[(price, count)]`。
- `buy_number()` — 购买或复用预购手机号；返回 `(act_id, phone)`，未启用真实注册时返回 `(None, None)`。
- `cancel_number(act_id)` — 调 HeroSMS `setStatus status=8` 取消 activation。
- `schedule_cancel_number(act_id, delay=125)` — 后台延迟取消 activation，日志写入 `~/.hermes/logs/gptfree-delayed-cancel.log`。
- `finish_number(act_id)` — 调 HeroSMS `setStatus status=6` 标记完成。
- `get_sms(act_id, timeout=150)` — 轮询 HeroSMS `getStatus`，收到 `STATUS_OK` 时返回短信码。

### 错误分类与 OTP

- `classify_phone_verification_error(text)` — 根据 `PHONE_ERROR_PATTERNS` 将页面文本归类为 `phone_number_used`、`phone_number_invalid`、`sms_delivery_refused`、`resend_throttled`、`code_rejected` 等。
- `snapshot_phone_error(cdp, limit=1600)` — 从页面 `document.body.innerText` 抽取错误并返回 `{"reason", "action", "text"}`。
- `should_replace_phone(reason)` — 判断错误是否需要换号。
- `message_ts(message)` — 从 Cloud Mail message 的多个时间字段解析时间戳。
- `extract_openai_code(message)` — 从 OpenAI/ChatGPT 邮件字段中提取 6 位验证码，过滤 CSS 色值。
- `poll_latest_openai_otp(address, after_ts=0, timeout=120, interval=5)` — 轮询 Cloud Mail 收件箱，返回最新 OpenAI 验证码。
- `get_email_otp(target_email, after_ts, timeout=90, jwt=None)` — 当前只支持 `jwt == "cloudmail"` 分支。

### 面板请求

- `sub2api_request(method, path, token=None, data=None)` — 用 `curl` 请求 Sub2API JSON endpoint。
- `sub2api_login()` — POST `/api/v1/auth/login` 并返回 `access_token`。
- `cpa_request(method, path, data=None)` — 用 `curl` 请求 CPA management API，带 `Authorization` 与 `X-Management-Key`。
- `panel_login()` — `PANEL_MODE == "cpa"` 时返回 `None`，否则调用 `sub2api_login()`。

### 浏览器与注册状态机

- `restart_chrome_with_fingerprint()` — 清理旧注册 Chrome，删除 `/tmp/chrome-reg-current`，启动 headless Chrome 并检查 CDP page。
- `register_account()` — 单账号注册主状态机；成功返回 `{"phone", "password", "act_id"}`，失败返回 `None`。
- `main()` — 批量循环入口；解析命令行 count/country/dial/iso，按账号数量重启 Chrome、注册、CPA 导入并记录结果。

## `CDP` 类

`CDP` 是本脚本的浏览器控制适配器，包装 websocket 与 CDP JSON-RPC。主要方法：

- `send(method, params=None, timeout=15)` — 发送 CDP method 并按 id 等待响应。
- `ev(expr, timeout=10)` — 执行 `Runtime.evaluate` 并返回 by-value 结果。
- `url()` / `text(max_len=500)` — 读取当前 URL 和页面文本。
- `type_text(text)` / `type_password(password)` — 输入文本/密码。
- `fill_input(selector, text)` / `focus_and_type(selector, text)` — React-safe native setter + input/change/keyup 输入。
- `_click_center(rect)` — 用 `Input.dispatchMouseEvent` 点击元素中心。
- `click_submit_exact(values=None)` — 优先匹配 submit value，例如 `phone_number`、`validate`。
- `click_submit()` — requestSubmit、native click、dispatch click、CDP mouse 多策略提交。
- `click_text(text)` / `click_text_any(needles)` — 按按钮/链接文本点击。
- `click_oauth_consent(rounds=5)` — OAuth consent 页多轮点击 allow/authorize/continue。
- `inject_fingerprint()` — 注入 navigator.webdriver、navigator.languages、plugins、canvas noise 等覆写。

## 内部结构

1. **配置区**：顶层常量从环境变量读入，包括 `PANEL_MODE`、`CPA_URL`、`MAX_PRICE`、国家代码、窗口尺寸、UA 列表。
2. **错误分类区**：`PHONE_ERROR_PATTERNS` 与 `PHONE_ERROR_ACTION` 映射决定换号/稍后重试策略。
3. **服务客户端区**：HeroSMS、Cloud Mail OTP、Sub2API、CPA helper 函数。
4. **浏览器控制区**：`restart_chrome_with_fingerprint()` 和 `CDP` 类。
5. **业务状态机区**：`register_account()` 执行注册页面路径；`main()` 批量循环并调 helper。

## 依赖

- **内部使用**：`cloud_mail_local.create_cloud_mail_address()`、`get_cloud_mail_config()`、`get_cloud_mail_messages()`、`get_cloud_mail_token()`。
- **被使用者**：`auto_batch_monitor.py` 通过子进程运行；`gptfree_sub2api_dry_run.py` 导入 `batch_register_v2` 并调用 `sub2api_login()`；`test_batch_cpa_helpers.py` 导入并测试 `extract_openai_code()`。
- **外部库/命令**：`websockets`、`curl`、Chrome/Chromium CDP、HeroSMS API、Cloud Mail API、CPA/Sub2API endpoint。

## 注意点 / Gotchas

- `CDP_PORT` 在源码中固定为 `9336`，没有读取 `GPTFREE_CDP_PORT`；`.env.example` 中虽有该变量，主脚本不使用它。
- `buy_number()` 只有在 `GPTFREE_ALLOW_REAL_REGISTRATION=1` 时才真实购买号码，除非设置了 `GPTFREE_PREBOUGHT_ACT_ID` 和 `GPTFREE_PREBOUGHT_PHONE`。
- `restart_chrome_with_fingerprint()` 固定使用 `/tmp/chrome-reg-current`、`--proxy-server=http://127.0.0.1:7890` 和 headless Chrome。
- `sub2api_request()` 与 `cpa_request()` 当前源码片段包含脱敏/破损的 Authorization 字符串；`py_compile` 在本地通过，说明文件中实际字符串语法可解析，但文档不应假定完整 token 格式。
- `main()` Phase 2 会先生成 `random_email()`，但随后实际 helper 使用 `--email-prefix prefix`，并将 `account_email` 设置为 `f"{prefix}@qintlab.ccwu.cc"`。
- 当前测试引用的 `wait_cpa_auth_status()` 在本文件中不存在。
