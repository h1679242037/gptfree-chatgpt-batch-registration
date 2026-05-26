# Getting Started

## 前置条件

来自 `README.md`、`requirements.txt` 和源码的实际要求：

- Linux 主机。
- Python 3.10+。
- Python 依赖：`websockets`、`requests`、`pytest`。
- Google Chrome / Chromium，且支持 remote debugging。
- `curl` 命令可用。
- HeroSMS 兼容 API key。
- Cloud Mail 兼容 API，需管理员邮箱/密码和收信域名。
- CPA management API 或 Sub2API 面板。
- 本地代理/Mihomo 环境：代码默认多处使用 `127.0.0.1:7890` 和 `127.0.0.1:9090`。

## 安装

```bash
cd /home/qiont/.hermes/skills/browser/gptfree/references/chatgpt-batch-registration-main
python3 -m pip install -r requirements.txt
cp .env.example .env
set -a
source .env
set +a
```

## 配置

### `.env.example` 中列出的项目变量

- `HEROSMS_API_KEY` — HeroSMS 兼容 API Key。
- `GPTFREE_HEROSMS_MAX_PRICE` — 单号码最大价格，默认示例 `0.03`。
- `GPTFREE_ALLOW_REAL_REGISTRATION` — 真实注册开关；主脚本 `buy_number()` 要求为 `1` 才会购买号码。
- `GPTFREE_PANEL_MODE` — `cpa` 或 `sub2api`。
- `GPTFREE_CPA_URL` — CPA management API 地址。
- `GPTFREE_CPA_MANAGEMENT_KEY` — CPA 管理密钥。
- `GPTFREE_SUB2API_URL` — Sub2API 地址。
- `GPTFREE_SUB2API_EMAIL` / `GPTFREE_SUB2API_PASS` — Sub2API 管理员凭据。
- `GPTFREE_CLOUD_MAIL_URL` / `GPTFREE_CLOUD_MAIL_EMAIL` / `GPTFREE_CLOUD_MAIL_PASS` / `GPTFREE_EMAIL_DOMAIN` — README 中描述的 Cloud Mail 配置。
- `GPTFREE_CDP_PORT` / `GPTFREE_CHROME_PROFILE` / `GPTFREE_PROXY_SERVER` — README 中描述的浏览器/CDP 配置。

### 源码实际读取的 Cloud Mail 变量

`cloud_mail_local.py` 实际读取的是 `CLOUD_MAIL_*`，以及两个本地文件：

- `~/.gptfree/cloud-mail-deploy.env`
- `~/.gptfree/cloud-mail-admin.env`

关键变量名：

- `CLOUD_MAIL_BASE_URL` / `CLOUD_MAIL_API_URL` / `CLOUD_MAIL_URL` / `CLOUD_MAIL_ADMIN_URL` / `CLOUD_MAIL_CUSTOM_DOMAIN` / `CLOUD_MAIL_DOMAIN`
- `CLOUD_MAIL_DOMAIN`
- `CLOUD_MAIL_ADMIN_EMAIL`
- `CLOUD_MAIL_ADMIN_PASSWORD`

如果只复制 `.env.example` 中的 `GPTFREE_CLOUD_MAIL_*`，`cloud_mail_local.get_cloud_mail_config()` 不会直接读取这些值；需要同步为 `CLOUD_MAIL_*` 或写入上述 `~/.gptfree/cloud-mail-*.env`。

## 本地自检

```bash
cd /home/qiont/.hermes/skills/browser/gptfree/references/chatgpt-batch-registration-main
python3 -m py_compile *.py
PYTHONPATH=. pytest -q
```

当前源码验证结果：

- `py_compile` 通过。
- `pytest` 有一个已存在失败：`test_batch_cpa_helpers.py` 调用了当前源码不存在的 `batch_register_v2.wait_cpa_auth_status()`。

## Dry-run

### 本地依赖 / Cloud Mail 检查

```bash
python3 gptfree_local_dry_run.py
python3 gptfree_local_dry_run.py --create-mail
```

`--create-mail` 会调用 Cloud Mail `/api/public/addUser` 创建测试邮箱；不购买 HeroSMS 号码，也不注册 ChatGPT。

### Sub2API 检查

```bash
python3 gptfree_sub2api_dry_run.py
```

该脚本会读 `~/.gptfree/sub2api.env` 中的 `ADMIN_EMAIL` / `ADMIN_PASSWORD` 并注入 `GPTFREE_SUB2API_*`。当前源码中 `batch_register_v2.generate_auth_url()` 不存在，因此 auth URL 探测阶段会失败，除非先补齐对应函数或更新脚本。

### CPA existing account dry-run

```bash
python3 gptfree_cpa_existing_account.py --dry-run
```

该命令检查 CPA key、Cloud Mail domain 和 CDP pages，不执行 OAuth callback。

## 第一次真实运行

单账号主流程示例：

```bash
cd /home/qiont/.hermes/skills/browser/gptfree/references/chatgpt-batch-registration-main
export GPTFREE_PANEL_MODE=cpa
export GPTFREE_CPA_URL=http://127.0.0.1:8317
export GPTFREE_CPA_MANAGEMENT_KEY=your-management-key
export GPTFREE_ALLOW_REAL_REGISTRATION=1
python3 -u batch_register_v2.py 1
```

指定国家参数示例：

```bash
GPTFREE_ALLOW_REAL_REGISTRATION=1 python3 -u batch_register_v2.py 1 --country 151 --dial 56 --iso CL
```

## 常见工作流

### 只做已有账号 CPA OAuth 导入

```bash
python3 -u gptfree_cpa_existing_account.py \
  --phone +56900000000 \
  --password 'your-openai-password' \
  --email-prefix gptcpaexample \
  --start-chrome \
  --close-chrome \
  --otp-timeout 120
```

### 长驻库存监控批处理

```bash
python3 -u auto_batch_monitor.py
```

监控脚本会：

- 读取/写入 `~/auto_batch_state.json`。
- 写批次日志到 `~/auto_batch_logs/batch_*.log`。
- 按 `PROXIES` 列表轮换代理。
- 调用 `batch_register_v2.py`。

## 输出与状态文件

- `~/.hermes/accounts/gptfree-chatgpt-accounts-new.jsonl` — 主脚本追加注册结果。
- `~/.hermes/state/gptfree-cpa-existing-account/oauth.json` — CPA OAuth URL/state。
- `/tmp/gptfree-cpa-existing-account.png` — CPA helper 默认截图路径。
- `~/auto_batch_state.json` — 监控器状态。
- `~/auto_batch_logs/*.log` — 监控器批次日志。
- `~/.hermes/logs/gptfree-delayed-cancel.log` — 延迟取消 HeroSMS activation 的 helper 日志。

## 下一步阅读

- 架构图：[architecture.md](architecture.md)
- 主流程模块：[modules/batch_register_v2.md](modules/batch_register_v2.md)
- CPA helper：[modules/gptfree_cpa_existing_account.md](modules/gptfree_cpa_existing_account.md)
- Cloud Mail：[modules/cloud_mail_local.md](modules/cloud_mail_local.md)
- 排障指南：源码仓库中的 `docs/troubleshooting.zh.md`
