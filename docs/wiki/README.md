# chatgpt-batch-registration 代码 Wiki

这是一个脚本化的 ChatGPT/OpenAI 批量注册与账号导入项目。核心流程由 `batch_register_v2.py` 驱动：先通过 HeroSMS 兼容接口购买手机号，再通过 Chrome DevTools Protocol（CDP）自动完成 ChatGPT 手机号注册，随后通过 `gptfree_cpa_existing_account.py` 发起 CPA/Codex OAuth 导入，并用 `cloud_mail_local.py` 对接 Cloud Mail 风格临时邮箱收取 OpenAI 邮箱验证码。

## 核心概念

- **手机号注册** — `buy_number()`、`get_sms()`、`finish_number()`、`cancel_number()` 围绕 HeroSMS `getNumber` / `getStatus` / `setStatus` 管理号码生命周期。
- **CDP 浏览器自动化** — `batch_register_v2.CDP` 和 `gptfree_cpa_existing_account.CDP` 直接通过 websocket 调 Chrome DevTools Protocol，执行导航、DOM 注入、输入、点击、截图。
- **指纹轮换** — `restart_chrome_with_fingerprint()` 和 `start_chrome()` 使用随机窗口尺寸、User-Agent、独立 Chrome profile 与部分 navigator/canvas 覆写降低账号间重复特征。
- **Cloud Mail 邮箱** — `cloud_mail_local.py` 读取本地/环境配置，调用 `/api/public/genToken`、`/api/public/addUser`、`/api/public/emailList` 创建邮箱并拉取验证码邮件。
- **CPA OAuth 导入** — `gptfree_cpa_existing_account.py` 调 CPA 管理端 `/v0/management/codex-auth-url`、`/v0/management/oauth-callback`、`/v0/management/get-auth-status` 完成 Codex provider 授权导入。
- **库存监控批处理** — `auto_batch_monitor.py` 用 HeroSMS 非购买库存预览、Mihomo 代理切换和状态文件驱动批量运行 `batch_register_v2.py`。

## 入口点

- [`batch_register_v2.py`](../skills/browser/gptfree/references/chatgpt-batch-registration-main/batch_register_v2.py) — 主入口；批量注册账号并调用 CPA helper 做 Phase 2 导入。
- [`gptfree_cpa_existing_account.py`](../skills/browser/gptfree/references/chatgpt-batch-registration-main/gptfree_cpa_existing_account.py) — 已存在 OpenAI 手机号账号的 CPA/Codex OAuth 导入入口。
- [`auto_batch_monitor.py`](../skills/browser/gptfree/references/chatgpt-batch-registration-main/auto_batch_monitor.py) — 长驻库存监控和批量注册调度入口。
- [`gptfree_local_dry_run.py`](../skills/browser/gptfree/references/chatgpt-batch-registration-main/gptfree_local_dry_run.py) — 本地依赖与 Cloud Mail dry-run 检查入口。
- [`gptfree_sub2api_dry_run.py`](../skills/browser/gptfree/references/chatgpt-batch-registration-main/gptfree_sub2api_dry_run.py) — Sub2API 管理登录与 auth URL dry-run 入口。

## 高层架构

项目不是包化服务，而是一组同目录 Python 脚本。`batch_register_v2.py` 是最大脚本，直接持有配置、HeroSMS 调用、CDP 封装、注册状态机和批处理循环；它复用 `cloud_mail_local.py`，并在注册成功后以子进程方式调用 `gptfree_cpa_existing_account.py`。监控层 `auto_batch_monitor.py` 作为外部调度器，按库存和代理状态启动主脚本。

详见 [architecture.md](architecture.md)。

## 模块地图

- [`modules/batch_register_v2.md`](modules/batch_register_v2.md) — 主批量注册、HeroSMS 号码管理、CDP 注册状态机、CPA helper 调用。
- [`modules/cloud_mail_local.md`](modules/cloud_mail_local.md) — Cloud Mail 配置解析、鉴权、邮箱创建、邮件列表与 6 位验证码提取。
- [`modules/gptfree_cpa_existing_account.md`](modules/gptfree_cpa_existing_account.md) — 已有账号 CPA/Codex OAuth 导入、手机号登录、邮箱绑定/验证、callback 回传。
- [`modules/auto_batch_monitor.md`](modules/auto_batch_monitor.md) — HeroSMS 库存轮询、Mihomo 代理轮换、批处理日志和状态持久化。
- [`modules/dry_run_tools.md`](modules/dry_run_tools.md) — `gptfree_local_dry_run.py` 与 `gptfree_sub2api_dry_run.py` 的预检查职责。
- [`modules/tests.md`](modules/tests.md) — `test_batch_cpa_helpers.py` 当前测试覆盖与源码不一致点。

## 图表

- [architecture.md](architecture.md) — 系统组件与数据流 flowchart。
- [diagrams/class-diagram.md](diagrams/class-diagram.md) — 关键类/类型关系。
- [diagrams/sequences.md](diagrams/sequences.md) — 批量注册、CPA OAuth、Cloud Mail、监控调度关键序列。

## 快速开始

见 [getting-started.md](getting-started.md)。

## 当前源码核验摘要

- Python 文件数：7 个。
- 依赖文件：`requirements.txt` 包含 `websockets`、`requests`、`pytest`。
- `python3 -m py_compile *.py`：通过。
- `PYTHONPATH=. pytest -q`：1 通过、1 失败；失败原因是测试引用 `batch_register_v2.wait_cpa_auth_status`，但该函数在源码中不存在。
