# GPTFree ChatGPT 批量注册工具

> 中文优先说明；English notes are provided as secondary reference.

GPTFree 是一个公开脱敏后的 ChatGPT 手机号注册与账号导入自动化脚本集合。当前 v2 架构把“注册账号”和“CPA OAuth 导入”拆成两个脚本：主脚本完成手机号注册，然后通过 subprocess 调用 helper 完成 CPA OAuth、Cloud Mail 邮箱绑定和回调导入。

## 快速开始 / Quick start

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
set -a && source .env && set +a

python3 -m py_compile *.py
PYTHONPATH=. pytest -q
```

真实运行前配置自己的短信服务、Cloud Mail、CPA/Sub2API 面板、代理和 Chrome/CDP 环境。

单账号运行：

```bash
GPTFREE_ALLOW_REAL_REGISTRATION=1 python3 -u batch_register_v2.py 1
```

单独运行 CPA OAuth helper（已有手机号账号）：

```bash
python3 -u gptfree_cpa_existing_account.py \
  --phone +56900000000 \
  --password 'your-openai-password' \
  --email-prefix gptcpaexample \
  --start-chrome \
  --close-chrome \
  --otp-timeout 120
```

English: install dependencies, copy `.env.example`, run compile/tests, then run `batch_register_v2.py` only after configuring your own services.

## 架构概览 / Architecture overview

### v2 两脚本流程 / Two-script flow

```text
batch_register_v2.py
  Phase 1: HeroSMS 买号 → Chrome/CDP 注册 ChatGPT → SMS 验证 → 得到 phone/password
  Phase 2: subprocess 调用 helper
      ↓
gptfree_cpa_existing_account.py
  CPA OAuth URL/state → 手机号登录 → Cloud Mail 邮箱/OTP → OAuth consent → CPA callback
```

### 文件角色

- `batch_register_v2.py`：主流程。负责 Phase 1 注册，并在 Phase 2 通过 `subprocess.run()` 调用 helper。
- `gptfree_cpa_existing_account.py`：CPA OAuth helper。负责已有手机号账号登录、Cloud Mail 邮箱绑定、OTP、OAuth consent、CPA callback。
- `cloud_mail_local.py`：Cloud Mail API 客户端，提供配置读取、获取 token、创建邮箱、查询邮件。
- `auto_batch_monitor.py`：批量监控和库存辅助。
- `gptfree_local_dry_run.py` / `gptfree_sub2api_dry_run.py`：dry-run 检查脚本。
- `test_batch_cpa_helpers.py`：离线单元测试。

English: v2 delegates CPA OAuth import to a separate helper process. The main script registers accounts, then the helper performs phone login, email OTP, consent, and callback.

## 配置 / Configuration

复制模板：

```bash
cp .env.example .env
set -a
source .env
set +a
```

### 环境变量说明 / Environment variables

- `HEROSMS_API_KEY`: HeroSMS 兼容短信平台 API Key。
- `GPTFREE_HEROSMS_MAX_PRICE`: 单个号码最高价格。
- `GPTFREE_ALLOW_REAL_REGISTRATION`: 真实注册开关；`1` 才会购买号码并注册。
- `GPTFREE_PANEL_MODE`: 导入面板模式；`cpa` 或 `sub2api`。
- `GPTFREE_CPA_URL`: CPA 兼容管理 API 根地址。
- `GPTFREE_CPA_MANAGEMENT_KEY`: CPA management key，用于 OAuth URL、callback、status API。
- `GPTFREE_CPA_ENV_FILE`: 可选 CPA env 文件路径，helper 可从中读取 management key。
- `GPTFREE_CPA_STATE_DIR`: helper 保存 OAuth state/json 的目录。
- `GPTFREE_CPA_OAUTH_VERIFY_SCRIPT`: 可选 OAuth 验证脚本路径。
- `GPTFREE_SUB2API_URL`: Sub2API 面板根地址。
- `GPTFREE_SUB2API_EMAIL`: Sub2API 管理员邮箱。
- `GPTFREE_SUB2API_PASS`: Sub2API 管理员密码。
- `CLOUD_MAIL_BASE_URL` / `CLOUD_MAIL_API_URL` / `CLOUD_MAIL_URL`: Cloud Mail API 地址。
- `CLOUD_MAIL_DOMAIN`: Cloud Mail 生成收件箱使用的邮箱域名。
- `CLOUD_MAIL_ADMIN_EMAIL`: Cloud Mail 管理员邮箱。
- `CLOUD_MAIL_ADMIN_PASSWORD`: Cloud Mail 管理员密码。
- `GPTFREE_EMAIL_DOMAIN`: 主流程推导 helper 生成邮箱时使用的域名。
- `GPTFREE_CF_TEMP_EMAIL_URL`: 可选旧 Cloudflare Temp Email API 地址。
- `GPTFREE_CF_TEMP_EMAIL_AUTH`: 可选旧 Cloudflare Temp Email API token/header。
- `GPTFREE_CDP_PORT`: Chrome DevTools Protocol 端口，默认 `9336`。
- `GPTFREE_CHROME_PROFILE`: Chrome profile 路径。
- `GPTFREE_PROXY_SERVER`: 浏览器代理地址，可留空。
- `GPTFREE_AUTO_BATCH_LOG_DIR`: 自动批处理日志目录。
- `GPTFREE_AUTO_BATCH_STATE_FILE`: 自动批处理状态文件。

注：`cloud_mail_local.py` 优先读取 `CLOUD_MAIL_*` 变量，也可读取本地 `~/.gptfree/cloud-mail-*.env` 文件。`.env.example` 同时保留 `GPTFREE_CLOUD_MAIL_*` 说明变量便于理解，实际 Cloud Mail 客户端建议使用 `CLOUD_MAIL_*`。

## 运行 / Running

### 主流程：注册 + CPA helper 导入

```bash
export GPTFREE_PANEL_MODE=cpa
export GPTFREE_CPA_URL=http://127.0.0.1:8317
export GPTFREE_CPA_MANAGEMENT_KEY=your-management-key
export GPTFREE_ALLOW_REAL_REGISTRATION=1
python3 -u batch_register_v2.py 1
```

主脚本 Phase 2 调用形式等价于：

```bash
python3 -u gptfree_cpa_existing_account.py \
  --phone +<phone> \
  --password <password> \
  --email-prefix <generated-prefix> \
  --start-chrome \
  --close-chrome \
  --otp-timeout 120
```

### Helper Chrome flags

- `--start-chrome`：helper 自己启动一个新的 headless Chrome/CDP 实例。适合独立补导入或主流程 subprocess 调用。
- `--close-chrome`：helper 结束后关闭由 `--start-chrome` 启动的 Chrome；通常与 `--start-chrome` 一起使用。

### Helper 常用参数

- `--phone`: 完整手机号，例如 `+56900000000`。
- `--password`: OpenAI/ChatGPT 账号密码。
- `--email-prefix`: Cloud Mail 邮箱 local part；最终邮箱为 `<prefix>@<domain>`。
- `--email`: 使用已有邮箱，不自动创建。
- `--state-dir`: OAuth state 保存目录，适合并发隔离。
- `--otp-timeout`: 等待 OpenAI 邮箱验证码的秒数。
- `--dry-run`: 只检查 CPA key、Cloud Mail 配置和 CDP pages。

### Sub2API 模式

```bash
export GPTFREE_PANEL_MODE=sub2api
export GPTFREE_SUB2API_URL=http://127.0.0.1:8080
export GPTFREE_SUB2API_EMAIL=admin@example.com
export GPTFREE_SUB2API_PASS=your-password
GPTFREE_ALLOW_REAL_REGISTRATION=1 python3 -u batch_register_v2.py 1
```

## JSONL 记录格式 / JSONL record format

输出文件为运行时账号记录 JSONL。v2 只在 OAuth 成功时记录 `cpa_email`。

成功记录：

```json
{"cpa_email":"gptcpaexample@example.com","phone":"+56900000000","password":"example-password","oauth_imported":true,"created_at":"2026-05-26T12:00:00+0000"}
```

失败记录（无 `cpa_email`）：

```json
{"phone":"+56900000000","password":"example-password","oauth_imported":false,"created_at":"2026-05-26T12:00:00+0000"}
```

English: success records include `cpa_email` and `oauth_imported: true`; failure records keep only `phone`, `password`, `oauth_imported: false`, and `created_at` so failed accounts can be retried.

## 排障 / Troubleshooting

- 依赖检查：`python3 -m pip install -r requirements.txt`。
- 语法检查：`python3 -m py_compile *.py`。
- 测试：`PYTHONPATH=. pytest -q`。
- CDP 无页面：确认 Chrome 以 `--remote-debugging-port=$GPTFREE_CDP_PORT` 启动。
- Helper 连接失败：尝试增加 `--start-chrome`，或确认端口未被旧 Chrome 占用。
- Helper 结束后 Chrome 残留：同时使用 `--start-chrome --close-chrome`。
- Cloud Mail 缺配置：确认 `CLOUD_MAIL_BASE_URL`、`CLOUD_MAIL_DOMAIN`、`CLOUD_MAIL_ADMIN_EMAIL`、`CLOUD_MAIL_ADMIN_PASSWORD`。
- OTP 超时：增大 `--otp-timeout`，检查 Cloud Mail inbox 是否收到 OpenAI 邮件。
- CPA callback 失败：确认 `GPTFREE_CPA_URL` 和 `GPTFREE_CPA_MANAGEMENT_KEY`，并检查 state status API。
- 更多中文排障见 [docs/troubleshooting.zh.md](docs/troubleshooting.zh.md)。

## 发布说明 / Publishing notes

本仓库是公开脱敏快照：不包含真实账号、手机号、Token、API Key、邮箱密码或本机私有配置。`.env`、日志、账号记录、缓存、备份文件应保持在 `.gitignore` 外。

## English Summary

GPTFree is a sanitized public snapshot for phone-first ChatGPT registration and optional account import. v2 uses a two-script architecture: `batch_register_v2.py` registers accounts and calls `gptfree_cpa_existing_account.py` as a subprocess for CPA OAuth import. Configure your own HeroSMS-compatible provider, Cloud Mail, panel, proxy, and CDP Chrome before real runs.

## 许可证 / License

[MIT License](LICENSE)
