# GPTFree ChatGPT 批量注册工具

> 中文为主说明；English summary is provided below as auxiliary reference.

这是一个经过公开发布脱敏处理的 ChatGPT 手机号注册与账号导入自动化脚本集合。项目保留了原始运维脚本的形态，适合已经具备短信服务、临时邮箱服务、代理环境和账号管理面板的操作者继续改造。

## 功能概览

- 通过 Chrome DevTools Protocol（CDP）驱动浏览器
- 使用 HeroSMS 兼容接口购买号码、轮询短信、完成/取消激活
- 支持手机号优先的 ChatGPT 注册流程
- 支持 Cloud Mail 风格临时邮箱接口，用于 OpenAI 邮箱验证码
- 支持两类导入模式：CPA 兼容管理 API、Sub2API 兼容面板
- 包含已有手机号账号的 CPA OAuth 补导入脚本
- 包含基础 dry-run 脚本和少量 CPA helper 测试

## 目录结构

```text
.
├── batch_register_v2.py              # 主流程：注册 + 可选导入
├── auto_batch_monitor.py             # 批量监控 / HeroSMS 库存辅助
├── cloud_mail_local.py               # Cloud Mail API 辅助
├── gptfree_cpa_existing_account.py   # 已有手机号账号的 Phase-2 CPA 导入
├── gptfree_local_dry_run.py          # 本地 dry-run
├── gptfree_sub2api_dry_run.py        # Sub2API dry-run
├── test_batch_cpa_helpers.py         # CPA helper 最小测试
├── .env.example                      # 环境变量示例
└── requirements.txt                  # Python 依赖
```

## 环境要求

- Linux 主机
- Python 3.10+
- Google Chrome / Chromium，需支持 remote debugging
- `curl`
- 自备短信服务、邮箱服务、代理和管理面板

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

## 快速开始

```bash
# 1. 安装依赖
python3 -m pip install -r requirements.txt

# 2. 准备本地配置
cp .env.example .env
set -a
source .env
set +a

# 3. 先跑不触网检查
python3 -m py_compile *.py
PYTHONPATH=. pytest -q
```

真实注册前，还需要确认 Chrome/CDP、短信服务、邮箱服务和导入面板都已经可用。

## 配置方式

复制环境变量模板：

```bash
cp .env.example .env
set -a
source .env
set +a
```

## 配置矩阵

### 通用必填

- `HEROSMS_API_KEY`：HeroSMS 兼容 API Key
- `GPTFREE_ALLOW_REAL_REGISTRATION`：真实注册开关，真实跑时设为 `1`
- `GPTFREE_CLOUD_MAIL_URL`：Cloud Mail API 地址
- `GPTFREE_CLOUD_MAIL_EMAIL`：Cloud Mail 管理员邮箱
- `GPTFREE_CLOUD_MAIL_PASS`：Cloud Mail 管理员密码
- `GPTFREE_EMAIL_DOMAIN`：生成邮箱使用的域名

### CPA 模式

- `GPTFREE_PANEL_MODE=cpa`
- `GPTFREE_CPA_URL`：CPA 兼容管理 API 地址
- `GPTFREE_CPA_MANAGEMENT_KEY`：CPA 管理密钥

### Sub2API 模式

- `GPTFREE_PANEL_MODE=sub2api`
- `GPTFREE_SUB2API_URL`：Sub2API 地址
- `GPTFREE_SUB2API_EMAIL`：Sub2API 管理员邮箱
- `GPTFREE_SUB2API_PASS`：Sub2API 管理员密码

### 浏览器/CDP

- `GPTFREE_CDP_PORT`：Chrome CDP 端口，默认 `9336`
- `GPTFREE_CHROME_PROFILE`：Chrome profile 路径
- `GPTFREE_PROXY_SERVER`：浏览器代理地址，可留空

## 快速检查

语法检查：

```bash
python3 -m py_compile *.py
```

运行测试：

```bash
PYTHONPATH=. pytest -q
```

dry-run：

```bash
python3 gptfree_local_dry_run.py
python3 gptfree_sub2api_dry_run.py
```

## 运行示例

单账号真实注册：

```bash
GPTFREE_ALLOW_REAL_REGISTRATION=1 python3 -u batch_register_v2.py 1
```

CPA 模式：

```bash
export GPTFREE_PANEL_MODE=cpa
export GPTFREE_CPA_URL=http://127.0.0.1:8317
export GPTFREE_CPA_MANAGEMENT_KEY=your-management-key
GPTFREE_ALLOW_REAL_REGISTRATION=1 python3 -u batch_register_v2.py 1
```

Sub2API 模式：

```bash
export GPTFREE_PANEL_MODE=sub2api
export GPTFREE_SUB2API_URL=http://127.0.0.1:8080
export GPTFREE_SUB2API_EMAIL=admin@example.com
export GPTFREE_SUB2API_PASS=your-password
GPTFREE_ALLOW_REAL_REGISTRATION=1 python3 -u batch_register_v2.py 1
```

## 常见文件说明

### `batch_register_v2.py`

主流程脚本，负责购买手机号、启动/连接 CDP Chrome、执行 ChatGPT 手机号注册、轮询短信验证码、处理 about-you / 邮箱验证 / OAuth consent 等页面，并按配置导入 CPA 或 Sub2API。

### `gptfree_cpa_existing_account.py`

用于“账号已经存在，只需要重新登录并导入 CPA”的场景。

### `cloud_mail_local.py`

封装 Cloud Mail 风格 API，用于创建临时邮箱、查询邮件和提取验证码。

## 文档

- [排障指南](docs/troubleshooting.zh.md)

## 发布说明

这个仓库是公开脱敏快照：

- 不包含真实账号、手机号、Token、API Key、邮箱密码或本机私有配置
- `.env`、日志、账号记录、缓存、备份文件已被 `.gitignore` 排除
- 运行时凭据请通过环境变量或本地 `.env` 注入
- 代码保留脚本化风格，没有强行重构成库

## 许可证

本项目使用 [MIT License](LICENSE)。

---

## English Summary

GPTFree ChatGPT Batch Registration is a sanitized public snapshot of a local automation workflow for phone-first ChatGPT registration and optional account import.

Main capabilities:

- Browser automation through Chrome DevTools Protocol (CDP)
- HeroSMS-compatible phone purchase and SMS polling
- Cloud Mail-compatible temporary email helper
- CPA-compatible and Sub2API-compatible import modes
- Existing-account CPA OAuth helper
- Minimal dry-run utilities and tests

Basic setup:

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
set -a && source .env && set +a
PYTHONPATH=. pytest -q
```

Run one real registration only after configuring your own services:

```bash
GPTFREE_ALLOW_REAL_REGISTRATION=1 python3 -u batch_register_v2.py 1
```
