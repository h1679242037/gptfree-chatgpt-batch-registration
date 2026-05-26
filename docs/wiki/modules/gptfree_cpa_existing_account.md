# Module: `gptfree_cpa_existing_account.py`

`gptfree_cpa_existing_account.py` 是“账号已注册，只做 CPA/Codex OAuth 导入”的 Phase 2 脚本。它不购买手机号，也不创建 ChatGPT 账号；它生成 CPA OAuth URL/state，打开 OpenAI 授权页，必要时用手机号和密码登录，处理邮箱绑定/邮箱验证码/consent，最后把 callback URL 交回 CPA 管理 API。

## 职责

- 读取 CPA management key（环境变量或 `~/.gptfree/cpa.env`）。
- 调 CPA `/v0/management/codex-auth-url` 获取 OAuth URL 和 state，并保存到 state 目录。
- 启动或复用 CDP Chrome，在新 tab 中打开 OAuth URL。
- 在 OpenAI Auth 页面中选择账号、手机号登录、密码登录、添加邮箱、提交邮箱验证码、点击 consent。
- 从 Cloud Mail inbox 中筛选最新 OpenAI/ChatGPT 验证码。
- 从 callback URL 解析 `code` / `state`，校验 state 后 POST `/v0/management/oauth-callback`。
- 可选执行外部 `cpa-oauth-verify.py` 做 marker chat 验证。

## Key Files

- [`gptfree_cpa_existing_account.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/gptfree_cpa_existing_account.py) — 本模块实现。
- [`cloud_mail_local.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/cloud_mail_local.py) — 邮箱创建和邮件读取。
- [`batch_register_v2.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/batch_register_v2.py) — 主脚本注册成功后以子进程调用本模块。

## Public API / 主要函数

### CPA 与 OAuth state

- `read_cpa_management_key()` — 优先取 `GPTFREE_CPA_MANAGEMENT_KEY`，否则读 `GPTFREE_CPA_ENV_FILE` 或 `~/.gptfree/cpa.env` 中的 `MANAGEMENT_PASSWORD`。
- `cpa_request(method, path, data=None, cpa_url=DEFAULT_CPA_URL, management_key=None, timeout=25)` — 用 `urllib.request` 请求 CPA 管理 API，带 `X-Management-Key` 和 `Authorization`。
- `generate_cpa_oauth(cpa_url=DEFAULT_CPA_URL, management_key=None)` — GET `/v0/management/codex-auth-url`，返回 `{"url", "state", "raw"}`。
- `save_oauth_json(oauth, state_dir=DEFAULT_STATE_DIR)` — 写 `oauth.json` 到 `~/.hermes/state/gptfree-cpa-existing-account/` 或指定目录。
- `callback_parts(url)` — 从 callback URL query 中解析 `code` 和 `state`。

### CDP/Chrome

- `list_pages(cdp_port)` — GET `http://127.0.0.1:<port>/json/list`，返回 page targets。
- `create_tab(cdp_port, url="about:blank")` — PUT `/json/new?...` 创建新 tab。
- `start_chrome(port=9336, user_data_dir="/tmp/chrome-gptfree-helper")` — 清理同端口/同 profile Chrome，启动 headless Chrome，等待 about:blank target 可用。
- `run_oauth(args)` — 主异步工作流；驱动 OAuth 导入并返回进程退出码。
- `main()` — argparse CLI，支持 `--phone`、`--password`、`--email`、`--email-prefix`、`--cdp-port`、`--cpa-url`、`--otp-timeout`、`--verify`、`--start-chrome`、`--close-chrome`、`--dry-run`。

### 手机号与验证码

- `_split_phone(phone_digits)` — 从纯数字手机号中按最长拨号码前缀拆出 `(dial_code, national_number)`。
- `_dial_to_iso(dial_code)` — 将拨号码映射到 ISO 国家代码。
- `message_ts(message)` — 解析 Cloud Mail message 时间。
- `extract_openai_code(message)` — 从 OpenAI/ChatGPT 邮件中提取验证码，过滤 CSS 色值。
- `create_or_reuse_cloud_mail_address(local_part)` — 创建邮箱；如果已存在则按当前 Cloud Mail domain 复用。
- `poll_latest_openai_otp(address, after_ts=0, timeout=120, interval=5)` — 轮询最新 OpenAI OTP，并按 `after_ts` 过滤旧邮件。
- `wait_until(cdp, pred, timeout=60, interval=2)` — 周期性抓 `cdp.snapshot()` 直到谓词满足。

## `CDP` 类

本模块的 `CDP` 与主脚本同名但实现不同，偏向 OAuth 登录/验证路径：

- `send(method, params=None, timeout=20)` — CDP JSON-RPC 调用。
- `ev(expr, timeout=15)` — `Runtime.evaluate`，启用 `awaitPromise`。
- `url()`、`title()`、`text(n=1200)`、`snapshot()` — 页面状态读取。
- `screenshot(path)` — `Page.captureScreenshot`，写 PNG。
- `click_text(needles)` — 文本匹配点击按钮/链接。
- `click_account_card()` — 在 choose-account 页面选择账号卡片。
- `cdp_type_text(text)` / `cdp_fill_input(selector, value)` — 用 CDP key events 触发 React handlers。
- `fill_visible_input(selector, value)` — native setter + input/change/keyup 填充可见输入框。
- `click_submit_exact(values=None)` — 按 submit value 或授权/继续文本点击。

## OAuth 工作流内部结构

1. `run_oauth()` 先读 management key；`--dry-run` 只输出 CPA key、Cloud Mail domain、CDP pages。
2. 正常模式调用 `generate_cpa_oauth()` 并 `save_oauth_json()`。
3. 选择或创建 Cloud Mail 地址：传 `--email` 则复用，否则用 `--email-prefix` 创建/复用。
4. 如有 `--start-chrome`，调用 `start_chrome()`。
5. 通过 `create_tab()` 创建 tab，连接 websocket，启用 `Page/Runtime/Network`。
6. 打开 OAuth URL；如遇 choose-account，调用 `click_account_card()`。
7. 如遇 log-in 且提供 `--phone`，切到 `usernameKind=phone_number`，拆拨号码/ISO，填写 national number 并提交。
8. 如遇 password 且提供 `--password`，填写密码并提交。
9. 如遇 email-verification 或 add-email，创建/使用邮箱并通过 `poll_latest_openai_otp()` 获取验证码。
10. 如遇 consent/authorize，循环 `click_submit_exact()` 直到 callback 或授权成功文本。
11. 从当前 URL 或导航历史中找 callback URL，解析 code/state，POST CPA callback，再 GET auth status。

## 依赖

- **Used by:** `batch_register_v2.py` 子进程调用。
- **Uses:** `cloud_mail_local.py`、`websockets`、Chrome CDP、CPA Management API、OpenAI Auth/OAuth 页面、可选外部脚本 `~/.hermes/skills/devops/cliproxyapi-deploy/scripts/cpa-oauth-verify.py`。

## 注意点 / Gotchas

- `_DIAL_TO_ISO` 是内置静态映射，覆盖常见拨号码；未知拨号码会返回空 ISO。
- `start_chrome()` 固定加入 `--proxy-server=http://127.0.0.1:7890`，与主脚本一致。
- `run_oauth()` 在 OTP 字段填充值后会读回校验；不一致时返回 3，验证码被拒时返回 4，未找到 callback code 返回 5，state mismatch 返回 6，verify 失败返回 7。
- `--close-chrome` 只在同时设置 `--start-chrome` 时执行 `pkill -f chrome.*remote-debugging-port=<port>`。
