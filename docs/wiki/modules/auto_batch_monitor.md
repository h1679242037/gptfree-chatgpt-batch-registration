# Module: `auto_batch_monitor.py`

`auto_batch_monitor.py` 是长驻批量注册调度器。它不直接操作 ChatGPT 页面，而是周期性检查 HeroSMS 库存、按状态轮换代理、启动 `batch_register_v2.py` 子进程、解析批次日志，并在检测到“收到短信但注册未成功”的浪费号码场景时停止。

## 职责

- 维护 Chile 目标国家配置、HeroSMS service `dr`、最大号码价格 `0.03`。
- 通过非购买接口检查 HeroSMS 库存和价格档位。
- 维护代理列表和每个代理最多成功账号数。
- 调用 Mihomo API 切换 `GLOBAL` 代理组。
- 运行批量注册子进程并写日志到 `~/auto_batch_logs/`。
- 保存调度状态到 `~/auto_batch_state.json`。
- 根据批次输出统计成功、失败和浪费号码数。

## Key Files

- [`auto_batch_monitor.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/auto_batch_monitor.py) — 监控与调度逻辑。
- [`batch_register_v2.py`](../../skills/browser/gptfree/references/chatgpt-batch-registration-main/batch_register_v2.py) — 被 `run_batch()` 启动的注册主脚本。

## Public API / 主要函数

- `load_state()` — 从 `~/auto_batch_state.json` 读取 `proxy_idx`、`accounts_on_current_proxy`、累计成功/失败/浪费数；不存在时返回默认状态。
- `save_state(state)` — 写回状态 JSON。
- `check_stock_country(country_id)` — 优先用 HeroSMS `getTopCountriesByService` + `freePrice=true` 解析价格档；失败时回退 `getPrices`；仍无结果时返回一个合成候选 `(1, 1, MAX_PRICE)`。
- `check_stock()` — 遍历 `COUNTRIES`，返回第一个有库存且价格不超过 `MAX_PRICE` 的国家。
- `switch_proxy(proxy_info)` — `direct` 只打日志；其他代理向 `MIHOMO_API/proxies/GLOBAL` PUT `{ "name": <mihomo> }`，然后通过 `127.0.0.1:7890` 查外网 IP。
- `run_batch(batch_size, country_info=None)` — 构造 `python3 -u batch_register_v2.py <batch_size> --country ... --dial ... --iso ...`，实时转发 stdout，30 分钟 deadline，返回 `(success, failed, wasted)`。
- `main()` — 无限循环：库存检查 → 必要时代理轮换 → 运行批次 → 更新状态 → 按结果等待或停止。

## 内部结构

- `COUNTRIES` 当前只包含 Chile：`id=151`、`dial=56`、`iso=CL`。
- `PROXIES` 包含 `direct`、`jp-residential`、`us99-ss`、`kkyun-ss`，每个代理最多累计 `MAX_PER_PROXY=10` 个成功账号后轮换。
- `BATCH_SIZE=5`，实际批量大小为 `min(BATCH_SIZE, count)`。
- `SCRIPT` 动态指向同目录 `batch_register_v2.py`。
- `LOG_DIR=~/auto_batch_logs`，`STATE_FILE=~/auto_batch_state.json`。

## 依赖

- **Uses:** HeroSMS API、Mihomo API、本地 HTTP 代理 `127.0.0.1:7890`、`batch_register_v2.py` 子进程。
- **Used by:** 无其他源码导入；作为独立长驻入口运行。

## 注意点 / Gotchas

- `check_stock_country()` 明确不调用 `getNumber`，避免库存探测误买手机号。
- 当 HeroSMS 预览接口低报/空报时，函数会返回合成候选，让主批处理脚本自己用真实购买逻辑尝试。
- `run_batch()` 通过输出文本解析结果：`FINAL: X imported, Y failed` 会覆盖计数；浪费号码通过 `"[6] SMS code:"` 次数减 `"✓ Registration successful!"` 次数估算。
- 如果 `wasted > 0`，`main()` 会停止循环。
- `env["DISPLAY"] = ":99"` 被设置后传入子进程，但主脚本实际使用 headless Chrome。
