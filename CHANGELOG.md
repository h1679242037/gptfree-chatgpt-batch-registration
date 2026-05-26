# Changelog

本项目遵循简化的语义化版本记录。中文为主，English notes are secondary.

## v2.0.0 - Current

### Changed

- 引入两脚本架构：`batch_register_v2.py` 负责 Phase 1 注册，并通过 subprocess 调用 `gptfree_cpa_existing_account.py` 完成 Phase 2 CPA OAuth。
- CPA OAuth 从主流程中拆出为 helper：手机号登录、Cloud Mail 邮箱创建/复用、OTP 轮询、OAuth consent、CPA callback 都由 helper 处理。
- helper 支持 `--start-chrome` 自启动 Chrome/CDP，以及 `--close-chrome` 在结束后关闭 Chrome。
- JSONL 账号记录格式调整：OAuth 成功记录包含 `cpa_email` 与 `oauth_imported: true`；OAuth 失败记录只保留 `phone`、`password`、`oauth_imported: false`、`created_at`，不写入 `cpa_email`。
- README 全面更新为 v2 架构、配置、运行和排障说明。

### Added

- `wait_cpa_auth_status()` 作为 CPA OAuth 状态轮询工具函数，便于 standalone verification 和测试。
- 更完整的离线测试覆盖：模块导入、关键函数存在、helper CLI 参数、Cloud Mail 配置、JSONL 记录格式。
- 关键函数 docstrings，覆盖主流程、helper 和 Cloud Mail public helpers。

### English

v2 splits registration and CPA OAuth import. The main script registers accounts and delegates OAuth import to the helper process. JSONL records now distinguish successful CPA imports from retryable failures.

## v1.0.0 - Original public snapshot

### Initial

- 单脚本为主的批量注册流程。
- 通过 Chrome DevTools Protocol 驱动 ChatGPT/OpenAI 注册页面。
- 使用 HeroSMS 兼容接口买号、轮询短信、完成或取消激活。
- 支持 Cloud Mail 风格临时邮箱接口。
- 支持 CPA/Sub2API 兼容导入路径和基础 dry-run 工具。

### English

Initial sanitized release with CDP browser automation, HeroSMS-compatible phone registration, Cloud Mail helper support, and panel import utilities.
