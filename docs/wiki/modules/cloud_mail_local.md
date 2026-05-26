# Module: `cloud_mail_local.py`

`cloud_mail_local.py` 是项目的 Cloud Mail 风格 API 客户端。它负责从本地 env 文件和 `CLOUD_MAIL_*` 环境变量读取邮箱服务配置，获取管理 token，创建收件地址，查询邮件列表，并提供一个通用 6 位验证码轮询器。

## 职责

- 读取 `~/.gptfree/cloud-mail-deploy.env`、`~/.gptfree/cloud-mail-admin.env` 以及当前进程 `CLOUD_MAIL_*` 环境变量。
- 规范化 Cloud Mail API base URL 和邮箱域名。
- 调用 Cloud Mail `/api/public/genToken` 获取管理 token。
- 调用 `/api/public/addUser` 创建邮箱用户。
- 调用 `/api/public/emailList` 查询指定收件地址的邮件。
- 从邮件标题/正文/html 中提取第一组 6 位数字验证码。

## Key Files

- [`cloud_mail_local.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/cloud_mail_local.py) — Cloud Mail 客户端实现。
- [`.env.example`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/.env.example) — 项目级 Cloud Mail 配置示例；注意本模块实际读取的是 `CLOUD_MAIL_*` 名称，而 README 中列出的是 `GPTFREE_CLOUD_MAIL_*`。

## Public API

- `load_cloud_mail_env(paths=ENV_FILES)` — 返回配置 dict；本地 env 文件值会被进程环境中的 `CLOUD_MAIL_*` 覆盖。
- `normalize_cloud_mail_base_url(value)` — 清理尾部 `/`，缺 scheme 时补 `https://`。
- `normalize_cloud_mail_domain(value)` — 去掉 scheme、`@`、路径并转小写。
- `get_cloud_mail_config(env=None)` — 返回 `{"base_url", "domain", "admin_email", "admin_password"}`。
- `mask_value(value)` — 用于 dry-run 输出脱敏值。
- `get_cloud_mail_token(config=None)` — POST `/api/public/genToken`，从顶层或 `data` 嵌套字段中取 `token` / `accessToken`。
- `generate_cloud_mail_local_part()` — 生成 `gpt` + 10 位小写字母/数字 local part。
- `create_cloud_mail_address(local_part=None, config=None, token=None)` — 创建邮箱，返回完整地址。
- `get_cloud_mail_messages(to_email, config=None, token=None, num=1, size=20)` — 查询邮件列表，兼容多种响应字段：`data`、`list`、`items`、`rows`、`records`。
- `extract_six_digit_code(message)` — 从 `subject/title/content/html/text/plainText/body` 拼接文本提取第一个 6 位码。
- `poll_cloud_mail_otp(to_email, after_ts=0, timeout=90, interval=5)` — 轮询邮箱并返回验证码；当前实现没有使用 `after_ts` 过滤时间。

## 内部结构

- `ENV_FILES` 固定包含两个默认配置文件路径。
- `_strip_quotes()` 去除 env value 外层单/双引号。
- `_first(env, names)` 按候选 key 顺序取第一个非空值。
- `_cloud_mail_request(config, path, payload, token=None, timeout=20)` 是唯一 HTTP POST 封装；统一设置 JSON headers、Origin/Referer、Authorization，并校验响应 `code`。

## 依赖

- **Used by:**
  - `batch_register_v2.py`：创建账号邮箱、轮询 OpenAI OTP。
  - `gptfree_cpa_existing_account.py`：创建/复用 CPA OAuth 绑定邮箱、读取 OTP。
  - `gptfree_local_dry_run.py`：检查配置、token、可选创建测试邮箱。
- **Uses:** Python 标准库 `urllib.request`、`urllib.error`、`json`、`os`、`random`、`re`、`string`、`time`。

## 注意点 / Gotchas

- 本模块只合并 `CLOUD_MAIL_*` 环境变量；README/.env.example 中的 `GPTFREE_CLOUD_MAIL_URL`、`GPTFREE_CLOUD_MAIL_EMAIL`、`GPTFREE_CLOUD_MAIL_PASS` 不会被 `load_cloud_mail_env()` 直接读取。
- `get_cloud_mail_config()` 将 API base URL 与邮箱域名分开：base URL 可来自 `CLOUD_MAIL_BASE_URL` 等字段，邮箱域名优先来自 `CLOUD_MAIL_DOMAIN`。
- `_cloud_mail_request()` 要求响应 JSON；非 JSON 会抛 `RuntimeError("Cloud Mail returned non-JSON response")`。
- `poll_cloud_mail_otp()` 形参含 `after_ts`，但当前代码没有按消息时间过滤；上层 `batch_register_v2.poll_latest_openai_otp()` 和 `gptfree_cpa_existing_account.poll_latest_openai_otp()` 自己实现了时间过滤和 OpenAI 上下文过滤。
