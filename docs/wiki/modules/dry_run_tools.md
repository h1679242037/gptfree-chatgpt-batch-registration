# Module: dry-run 工具

本模块覆盖两个独立 dry-run 脚本：`gptfree_local_dry_run.py` 和 `gptfree_sub2api_dry_run.py`。它们用于在真实注册前检查本地依赖和外部管理面板连通性，不购买手机号、不启动真实 ChatGPT 注册流程。

## `gptfree_local_dry_run.py`

### 职责

- 检查 Chrome 可执行文件。
- 检查本地代理端口 `127.0.0.1:7890`。
- 检查 Mihomo API `http://127.0.0.1:9090/proxies`。
- 读取 Cloud Mail 配置并脱敏输出。
- 获取 Cloud Mail token。
- 可选创建一个测试 Cloud Mail 地址并查询邮件列表。

### 主要函数

- `ok(name, detail="")` / `warn(name, detail="")` / `fail(name, detail="")` — 输出固定前缀的检查结果。
- `tcp_check(host, port, timeout=2)` — TCP 连接探测。
- `http_json(url, timeout=5)` — GET JSON endpoint。
- `main()` — argparse 入口，支持 `--create-mail`。

### 依赖

- `cloud_mail_local.create_cloud_mail_address()`
- `cloud_mail_local.get_cloud_mail_config()`
- `cloud_mail_local.get_cloud_mail_messages()`
- `cloud_mail_local.get_cloud_mail_token()`
- `cloud_mail_local.mask_value()`

## `gptfree_sub2api_dry_run.py`

### 职责

- 从 `~/.gptfree/sub2api.env` 读取 `ADMIN_EMAIL` 和 `ADMIN_PASSWORD`。
- 设置 `GPTFREE_SUB2API_EMAIL`、`GPTFREE_SUB2API_PASS`、默认 `GPTFREE_SUB2API_URL=http://127.0.0.1:8080`。
- 导入 `batch_register_v2`，输出 Sub2API URL 和凭据是否存在。
- 调用 `batch_register_v2.sub2api_login()` 检查登录。
- 尝试调用 `batch_register_v2.generate_auth_url(token)` 检查 auth URL 生成。

### 主要函数

- `load_env(path: Path = ENV_PATH) -> None` — 读取 `~/.gptfree/sub2api.env` 并注入 `GPTFREE_SUB2API_*` 环境变量。
- `main() -> int` — 执行 dry-run，失败时返回 2 或 3。

### 当前源码不一致点

`gptfree_sub2api_dry_run.py` 调用了 `br.generate_auth_url(token)`，但当前 `batch_register_v2.py` 中不存在 `generate_auth_url()`。因此即使 `sub2api_login()` 成功，auth URL 检查也会因为 `AttributeError` 失败，除非后续补回该函数或 dry-run 脚本改为使用现有 API。

## 运行方式

```bash
python3 gptfree_local_dry_run.py
python3 gptfree_local_dry_run.py --create-mail
python3 gptfree_sub2api_dry_run.py
```

## 注意点 / Gotchas

- `gptfree_local_dry_run.py` 不会购买号码，也不会注册 ChatGPT；`--create-mail` 只会创建 Cloud Mail 测试 inbox。
- `gptfree_sub2api_dry_run.py` 在导入 `batch_register_v2` 前没有修改 `sys.argv`，而 `batch_register_v2` 顶层会执行 `argparse.parse_known_args()`；普通运行 dry-run 时通常不会冲突，但这体现出主脚本的顶层副作用。
- `gptfree_sub2api_dry_run.py` 依赖 `~/.gptfree/sub2api.env`；项目 `.env.example` 中的 `GPTFREE_SUB2API_*` 不会被这个脚本的 `load_env()` 读取，除非已经存在于环境变量中。
